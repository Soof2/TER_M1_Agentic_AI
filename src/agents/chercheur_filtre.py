"""
A3c — Filtre Anti-Bruit.

Transforme les hits bruts de A3b en profils candidats exploitables :
    1. Pré-filtre par domaine URL  → élimine Indeed, Glassdoor, Jooble, etc.
    2. Pré-filtre par mots-clés    → élimine les offres d'emploi restantes
    3. Scraping des pages          → enrichit le profil_brut (3 000 chars max)
    4. Post-filtre après scraping  → le contenu complet révèle parfois plus de bruit

Responsabilité unique : décider QUOI garder (pur algorithmique, pas de LLM).
Le scraping est réalisé ici car il dépend de la décision de filtrage.

Output :
    profils_bruts : list[Candidat]  — profils enrichis, prêts pour A6
"""

import uuid

from src.state import GraphState, Candidat
from src.config import MAX_PROFILS_RECHERCHE
from src.tools.scraping import extraire_page_web_raw
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A3c_filtre")

# ---------------------------------------------------------------------------
# Listes de filtrage
# ---------------------------------------------------------------------------

# Mots-clés qui trahissent une offre d'emploi plutôt qu'un profil candidat.
# Testés en minuscules sur title + body (pré-filtre) et sur le contenu scrapé.
_NOISE_KEYWORDS = (
    # Français — offres d'emploi
    "nous recherchons",
    "nous recrutons",
    "rejoignez-nous",
    "rejoignez notre",
    "postuler",
    "postulez",
    "posez votre candidature",
    "candidature spontanée",
    "cdi à pourvoir",
    "cdd à pourvoir",
    "offre d'emploi",
    "offres d'emploi",
    "voir l'offre",
    "description du poste",
    "missions principales",
    "profil recherché",
    "votre profil",
    "type de contrat",
    "salaire",
    "temps plein",
    "télétravail partiel",
    "welcometothejungle",
    "hellowork",
    "pole-emploi",
    "france travail",
    # Anglais — job postings
    "we are hiring",
    "we are looking for",
    "job description",
    "job board",
    "apply now",
    "apply for this job",
    "submit your application",
    "send your cv",
    "requirements:",
    "responsibilities:",
    "what you will do",
    "what we offer",
    "about the role",
    "about the position",
    "years of experience required",
    "competitive salary",
    "equal opportunity employer",
    "full-time",
    "part-time",
    "remote ok",
    "hybrid",
    # Bases de CV agrégées (pas des profils individuels)
    "resume database",
    "hire it people",
    "search resumes",
    "post a job",
)

# Domaines d'agrégateurs. Testés sur l'URL uniquement (plus fiable que le
# texte car les agrégateurs ont des titres anodins).
_NOISE_DOMAINS = (
    "indeed.com",
    "indeed.fr",
    "glassdoor.com",
    "glassdoor.fr",
    "jooble.org",
    "monster.fr",
    "monster.com",
    "welcometothejungle.com",
    "hellowork.com",
    "apec.fr",
    "pole-emploi.fr",
    "francetravail.fr",
    "talent.com",
    "sagexa.com",
    "meteojob.com",
    "cadremploi.fr",
    "keljob.com",
    "regionsjob.com",
    "jobijoba.com",
    # Agrégateurs anglophones détectés en production
    "startup.jobs",
    "devjobsscanner.com",
    "hireitpeople.com",
    "python.org/jobs",
    "selbyjennings.com",
    "lever.co",
    "greenhouse.io",
    "workable.com",
    "recruiter.com",
    "ziprecruiter.com",
    "simplyhired.com",
    "careerbuilder.com",
    "dice.com",
    "reed.co.uk",
    "totaljobs.com",
    "jobsite.co.uk",
)

# Fragments de chemin URL qui trahissent une page d'offre (indépendamment du domaine)
_NOISE_URL_PATHS = (
    "/jobs/",
    "/job/",
    "/offre/",
    "/offres/",
    "/careers/",
    "/career/",
    "/recrutement/",
    "/emploi/",
    "/job-board/",
    "/job-offer/",
    "/senior-python-developer-",  # pattern titre de poste dans URL
    "/python-developer-jobs",
)


def _is_noise_url(url: str) -> bool:
    """Vrai si l'URL appartient à un agrégateur d'offres d'emploi ou pointe vers une offre."""
    if not url:
        return False
    lowered = url.lower()
    if any(domain in lowered for domain in _NOISE_DOMAINS):
        return True
    if any(path in lowered for path in _NOISE_URL_PATHS):
        return True
    return False


def _is_noise_text(text: str) -> bool:
    """Vrai si le texte ressemble à une offre d'emploi (mots-clés)."""
    if not text:
        return False
    lowered = text.lower()
    return any(kw in lowered for kw in _NOISE_KEYWORDS)


# ---------------------------------------------------------------------------
# Nœud LangGraph
# ---------------------------------------------------------------------------

def filtre_node(state: GraphState) -> dict:
    """Filtre les hits bruts, scrape les pages, produit les profils candidats."""
    m = get_metrics()
    m.debut("A3c_filtre")

    hits = state.get("resultats_bruts", [])
    _log.info("Filtrage de %d hits bruts...", len(hits))

    # --- Étape 1 : pré-filtre (URL + mots-clés snippet) ---
    pre_filtered: list[dict] = []
    n_url_drop = 0
    n_kw_drop = 0
    for h in hits:
        if _is_noise_url(h.get("url", "")):
            n_url_drop += 1
            continue
        snippet = f"{h.get('title', '')} {h.get('body', '')}"
        if _is_noise_text(snippet):
            n_kw_drop += 1
            continue
        pre_filtered.append(h)

    _log.info(
        "Pré-filtre : %d URL domain + %d mots-clés = %d éliminés, %d restants.",
        n_url_drop, n_kw_drop, n_url_drop + n_kw_drop, len(pre_filtered),
    )

    # Limiter le nombre de pages à scraper (marge pour le post-filtre)
    a_scraper = pre_filtered[: MAX_PROFILS_RECHERCHE * 2]

    # --- Étape 2 : scraping + post-filtre ---
    candidats: list[Candidat] = []
    n_post_drop = 0
    n_scrape_fail = 0

    for i, h in enumerate(a_scraper, 1):
        if len(candidats) >= MAX_PROFILS_RECHERCHE:
            break

        url = h["url"]
        _log.info("  Scraping %d/%d : %s", i, len(a_scraper), url[:70])
        scraped = extraire_page_web_raw(url)

        if scraped.startswith("Erreur") or scraped.startswith("Aucun contenu"):
            # Fallback sur le snippet DDG
            profil_brut = f"{h.get('title', '')}\n\n{h.get('body', '')}"
            n_scrape_fail += 1
        else:
            profil_brut = scraped

        # Post-filtre : le contenu complet peut révéler une offre
        if _is_noise_text(profil_brut):
            n_post_drop += 1
            continue

        candidats.append(Candidat(
            id=str(uuid.uuid4())[:8],
            nom=h.get("title", "Inconnu") or "Inconnu",
            source=h.get("source", "web"),
            profil_brut=profil_brut,
            url=url or None,
        ))

    n_total_drop = n_url_drop + n_kw_drop + n_post_drop
    taux_bruit = round(n_total_drop / len(hits), 2) if hits else 0.0

    _log.info(
        "Post-filtre : %d éliminés. Résultat final : %d profils candidats (taux bruit: %.0f%%).",
        n_post_drop, len(candidats), taux_bruit * 100,
    )
    if n_scrape_fail:
        _log.info("  %d pages inaccessibles → fallback snippet DDG.", n_scrape_fail)

    m.fin(
        "A3c_filtre",
        n_entree=len(hits),
        n_sortie=len(candidats),
        n_drop_url=n_url_drop,
        n_drop_kw=n_kw_drop,
        n_drop_post=n_post_drop,
        taux_bruit=taux_bruit,
        n_scrape_fail=n_scrape_fail,
    )

    return {"profils_bruts": candidats}
