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
    "les recherches suivantes",
    "recherche d'emploi",
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
    # Pages utiles pour un étudiant humain, mais pas des profils candidats.
    "groupe alternance",
    "école supérieure",
    "ecole supérieure",
    "formation en alternance",
    "recrutement en alternance",
    "trouver un emploi en alternance",
    "raisons de tenter le recrutement",
    "walt community",
    "adopte1alternant",
    "trouvez un freelance",
    "sélectionnez",
    "selectionnez",
    "recevez gratuitement",
    "les formations à",
    "les formations a",
    "formation react",
    "angular vs react",
    "quel framework front-end choisir",
    "spécialiste du travail",
    "specialiste du travail",
    "prof de python",
    "€/h",
    "avis",
    "élèves accompagnés",
    "eleves accompagnés",
)

# Domaines techniques à écarter avant analyse. On évite les blocklists de
# job boards : A4/A5 doivent voir la page et produire le score/statut.
_NOISE_DOMAINS = (
    "bing.com/aclick",
    "bing.com/maps",
)

# Fragments techniques qui trahissent une page de résultats ou une publicité,
# pas une page à analyser comme candidat.
_NOISE_URL_PATHS = (
    "/search?",
    "?q=",
    "/maps/",
)


def _is_aggregated_profile(title: str, profil_brut: str) -> bool:
    """Détecte les pages qui agrègent plusieurs profils (résultats de recherche LinkedIn)."""
    texte = f"{title} {profil_brut}"
    title_lower = title.lower()
    # Plusieurs URLs /in/ dans le contenu = page de résultats
    if texte.lower().count("linkedin.com/in/") >= 3:
        return True
    if texte.lower().count("fr.linkedin.com/in/") >= 3:
        return True
    # Titre DDG avec plusieurs personnes : "Nom1 - Titre | LinkedInNom2 - Titre"
    # Le mot "linkedin" apparaît plusieurs fois dans le titre (en minuscules ou majuscules)
    if title_lower.count("linkedin") >= 2:
        return True
    # Plusieurs " - LinkedIn" ou "| LinkedIn" dans le titre
    if title.count(" - LinkedIn") >= 2 or title.count("| LinkedIn") >= 2:
        return True
    # Titre avec plusieurs tirets séparateurs typiques des noms LinkedIn concaténés
    # Ex: "Nom1 - Titre1 ...Nom2 - Titre2 ...Nom3"
    if title.count(" ... ") >= 2 and title_lower.count("linkedin") >= 1:
        return True
    if title.count("...") >= 2 and title_lower.count("linkedin") >= 1:
        return True
    if title.count(" - ") >= 4 and title_lower.count("linkedin") >= 1:
        return True
    return False


def _is_noise_url(url: str) -> bool:
    """Vrai seulement pour le bruit technique évident avant analyse."""
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


def _triage_priority(hit: dict, profil_brut: str) -> int:
    """Priorise les pages les plus susceptibles d'être des profils directs.

    Ce n'est pas une décision finale : A4/A5 restent responsables du score
    et du statut. Le tri évite seulement que les pages de recherche occupent
    tous les slots quand MAX_PROFILS_RECHERCHE est limité.
    """
    url = (hit.get("url") or "").lower()
    texte = f"{hit.get('title', '')} {hit.get('body', '')} {profil_brut}".lower()
    if "linkedin." in url and "/in/" in url:
        return 0
    if "github.com/" in url and not any(p in url for p in ("/topics/", "/orgs/", "/marketplace/", "/search")):
        return 1
    if "malt.fr/profile/" in url or "doyoubuzz.com/" in url:
        return 2
    if _is_noise_text(texte):
        return 50
    return 20


# ---------------------------------------------------------------------------
# Nœud LangGraph
# ---------------------------------------------------------------------------

def filtre_node(state: GraphState) -> dict:
    """Filtre les hits bruts, scrape les pages, produit les profils candidats."""
    m = get_metrics()
    m.debut("A3c_filtre")

    hits = state.get("resultats_bruts", [])
    _log.info("Filtrage de %d hits bruts...", len(hits))

    # --- Étape 1 : pré-filtre technique minimal ---
    pre_filtered: list[dict] = []
    n_url_drop = 0
    for h in hits:
        if _is_noise_url(h.get("url", "")):
            n_url_drop += 1
            continue
        pre_filtered.append(h)

    _log.info(
        "Pré-filtre technique : %d URL éliminées, %d restantes.",
        n_url_drop, len(pre_filtered),
    )

    # Limiter le nombre de pages à scraper (marge pour le post-filtre)
    a_scraper = pre_filtered[: MAX_PROFILS_RECHERCHE * 3]

    # --- Étape 2 : scraping + triage ---
    candidats_priorises: list[tuple[int, Candidat]] = []
    n_post_drop = 0
    n_scrape_fail = 0
    n_pages_signalees = 0

    for i, h in enumerate(a_scraper, 1):
        url = h["url"]
        _log.info("  Scraping %d/%d : %s", i, len(a_scraper), url[:70])
        scraped = extraire_page_web_raw(url)

        if scraped.startswith("Erreur") or scraped.startswith("Aucun contenu"):
            # Fallback sur le snippet DDG
            profil_brut = f"{h.get('title', '')}\n\n{h.get('body', '')}"
            n_scrape_fail += 1
        else:
            profil_brut = scraped

        # Post-filtre strict : on retire seulement les pages agrégées qui
        # mélangent plusieurs personnes dans un seul résultat.
        if _is_aggregated_profile(h.get("title", ""), profil_brut):
            n_post_drop += 1
            continue

        priority = _triage_priority(h, profil_brut)
        if _is_noise_text(f"{h.get('title', '')} {h.get('body', '')} {profil_brut}"):
            n_pages_signalees += 1
            profil_brut = (
                "[Signal A3c] Cette page ressemble peut-être à une offre, "
                "une liste ou un contenu non-candidat. A4/A5 doivent le "
                "vérifier et scorer en conséquence.\n\n"
                + profil_brut
            )

        candidats_priorises.append((priority, Candidat(
            id=str(uuid.uuid4())[:8],
            nom=h.get("title", "Inconnu") or "Inconnu",
            source=h.get("source", "web"),
            profil_brut=profil_brut,
            url=url or None,
        )))

    candidats = [
        candidat
        for _, candidat in sorted(candidats_priorises, key=lambda item: item[0])
    ][:MAX_PROFILS_RECHERCHE]

    n_total_drop = n_url_drop + n_post_drop
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
        n_pages_signalees=n_pages_signalees,
        n_drop_post=n_post_drop,
        taux_bruit=taux_bruit,
        n_scrape_fail=n_scrape_fail,
    )

    return {"profils_bruts": candidats}
