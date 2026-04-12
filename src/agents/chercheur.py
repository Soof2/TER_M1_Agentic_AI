"""
A3 — Chercheur de Profils.

Recherche des profils sur le web selon les critères fournis par A2.
Communication événementielle par lots vers A6, s'appuie sur le
blackboard d'A2 sans couplage direct.

Pipeline interne :
    1. Le LLM génère les requêtes (web / LinkedIn / GitHub).
    2. Collecte structurée via `_ddg_search_raw` (dicts title/url/body/source).
    3. Déduplication par URL.
    4. Pré-filtre algorithmique anti-bruit (offres d'emploi, agrégateurs).
    5. Scraping des pages restantes pour enrichir le `profil_brut`.
    6. Re-filtre post-scraping (le contenu complet révèle plus de bruit).
    7. Construction des Candidat finaux.

Le pré-filtre algorithmique évite d'envoyer des offres d'emploi à A4
(×N appels LLM inutiles) — c'est le chantier 1b du backlog.
"""

import json
import uuid

from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState, Candidat
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER, MAX_PROFILS_RECHERCHE
from src.tools.search import _ddg_search_raw, CV_SITE_TARGETS
from src.tools.scraping import extraire_page_web_raw


# Mots-clés qui trahissent une offre d'emploi ou une page d'agrégateur
# plutôt qu'un profil individuel. Détecté sur title + body (pré-filtre DDG)
# puis re-testé sur le contenu scrapé (les pages complètes révèlent plus).
_NOISE_KEYWORDS = (
    "nous recherchons",
    "nous recrutons",
    "rejoignez-nous",
    "rejoignez notre",
    "postuler",
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
    # agrégateurs / plateformes (pour _is_noise sur contenu textuel)
    "welcometothejungle",
    "hellowork",
    "pole-emploi",
    "france travail",
)

# Domaines d'agrégateurs d'emploi. Testés sur l'URL du résultat DDG.
# Séparé de _NOISE_KEYWORDS car un profil LinkedIn peut *mentionner* Indeed
# dans son texte sans être lui-même une page Indeed.
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
)


def _is_noise(text: str) -> bool:
    """Détecte si un texte ressemble à une offre d'emploi / agrégateur.

    Tout est testé en minuscules sur le texte complet (title + body ou
    contenu scrapé). Retourne True dès qu'un mot-clé match.
    """
    if not text:
        return False
    lowered = text.lower()
    return any(kw in lowered for kw in _NOISE_KEYWORDS)


def _is_noise_url(url: str) -> bool:
    """Détecte si une URL pointe vers un agrégateur d'offres d'emploi.

    Testé sur le domaine uniquement — plus fiable que le contenu textuel
    car les agrégateurs ont des titres anodins ("Python - Paris : 2 024 emplois").
    """
    if not url:
        return False
    lowered = url.lower()
    return any(domain in lowered for domain in _NOISE_DOMAINS)


CHERCHEUR_QUERIES_PROMPT = """Tu es un expert en sourcing de talents. À partir du profil de compétences ci-dessous, génère des requêtes de recherche pour trouver des PERSONNES (candidats), PAS des offres d'emploi ni des dépôts de code.

Produis un JSON avec exactement ces clés :
- "queries_generales": liste de 2-3 requêtes web générales ciblant des CV ou portfolios de personnes.
  Utilise des opérateurs comme intitle:CV, intitle:portfolio ou des termes comme "freelance" "portfolio" "profil" "expérience" combinés aux compétences et à la localisation.
  Exemples : intitle:CV "Python" "5 ans" Paris, "freelance" "portfolio" "React" senior Lyon.
- "queries_linkedin": liste de 2 requêtes pour chercher des profils LinkedIn (personnes, pas des pages entreprises).
- "queries_github": liste de 1-2 requêtes pour trouver des PROFILS UTILISATEURS GitHub (pas des repos).
  Cible les pages de profil avec bio : utilise des termes comme "contributions" "followers" ou "repositories" combinés aux compétences.
  Exemples : "contributions" "Python" "machine learning" site:github.com, "followers" "Django" "data engineer" site:github.com.
- "queries_cv_sites": liste de 2-3 requêtes ciblant des plateformes de CV et portfolios (doyoubuzz.com, malt.fr, viadeo.com, about.me, behance.net, dribbble.com, stackoverflow.com/users).
  Chaque requête doit inclure un opérateur site: vers l'un de ces domaines, combiné aux compétences clés.
  Exemples : site:malt.fr "Python" "data scientist" Paris, site:doyoubuzz.com "développeur fullstack" React.

Chaque requête doit combiner compétences techniques, expérience et localisation.
Important : formule les requêtes comme si tu cherchais des PERSONNES (CV, portfolios, profils publics), PAS des offres d'emploi.
Réponds UNIQUEMENT avec le JSON, sans texte avant ou après. Pas de markdown, pas de backticks."""


def chercheur_node(state: GraphState) -> dict:
    """Recherche des profils candidats à partir du profil de compétences."""
    print("\n[A3 Chercheur] Génération des requêtes de recherche...", flush=True)
    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    profil = state["profil_competences"]

    # --- Étape 1 : Le LLM génère les requêtes de recherche ---
    recherche_msg = f"""Profil de compétences :

Hard skills : {', '.join(profil.get('hard_skills', []))}
Soft skills : {', '.join(profil.get('soft_skills', []))}
Expérience minimum : {profil.get('experience_min', 0)} ans
Formation : {profil.get('formation', 'Non spécifié')}
Contraintes : {', '.join(profil.get('contraintes', []))}
Mots-clés : {', '.join(profil.get('mots_cles', []))}"""

    messages = [
        SystemMessage(content=CHERCHEUR_QUERIES_PROMPT),
        HumanMessage(content=recherche_msg)
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        queries = json.loads(content)
    except json.JSONDecodeError:
        mots = profil.get("mots_cles", profil.get("hard_skills", ["développeur"]))
        base_query = " ".join(mots[:5])
        queries = {
            "queries_generales": [base_query + " CV profil"],
            "queries_linkedin": [base_query],
            "queries_github": [base_query],
            "queries_cv_sites": [f"site:malt.fr {base_query}", f"site:doyoubuzz.com {base_query}"],
        }

    # --- Étape 2 : Collecte structurée via _ddg_search_raw ---
    n_gen = len(queries.get("queries_generales", []))
    n_li = len(queries.get("queries_linkedin", []))
    n_gh = len(queries.get("queries_github", []))
    n_cv = len(queries.get("queries_cv_sites", []))
    print(f"[A3 Chercheur] Lancement de {n_gen + n_li + n_gh + n_cv} recherches "
          f"({n_gen} web, {n_li} LinkedIn, {n_gh} GitHub, {n_cv} CV/portfolios)...", flush=True)

    all_hits: list[dict] = []

    for i, q in enumerate(queries.get("queries_generales", []), 1):
        print(f"[A3 Chercheur]   Web {i}/{n_gen} : {q[:60]}...", flush=True)
        all_hits.extend(_ddg_search_raw(q, site_filter=None, max_results=5))

    for i, q in enumerate(queries.get("queries_linkedin", []), 1):
        print(f"[A3 Chercheur]   LinkedIn {i}/{n_li} : {q[:60]}...", flush=True)
        all_hits.extend(_ddg_search_raw(q, site_filter="linkedin.com/in", max_results=5))

    for i, q in enumerate(queries.get("queries_github", []), 1):
        print(f"[A3 Chercheur]   GitHub {i}/{n_gh} : {q[:60]}...", flush=True)
        all_hits.extend(_ddg_search_raw(q, site_filter="github.com", max_results=5))

    print(f"[A3 Chercheur] {len(all_hits)} résultats bruts DDG collectés.", flush=True)

    # --- Étape 3 : Déduplication par URL ---
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for h in all_hits:
        url = h.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(h)
    print(f"[A3 Chercheur] {len(deduped)} résultats après déduplication par URL.", flush=True)

    # --- Étape 4 : Pré-filtre anti-bruit (sans LLM) ---
    #     4a. Domaine d'URL → élimine Indeed, Glassdoor, Jooble, etc.
    #     4b. Mots-clés dans title + body → élimine les offres restantes
    pre_filtered: list[dict] = []
    n_prefilter_drop = 0
    for h in deduped:
        if _is_noise_url(h.get("url", "")):
            n_prefilter_drop += 1
            continue
        snippet = f"{h.get('title', '')} {h.get('body', '')}"
        if _is_noise(snippet):
            n_prefilter_drop += 1
            continue
        pre_filtered.append(h)
    print(f"[A3 Chercheur] Pré-filtre : {n_prefilter_drop} offres/agrégateurs écartés, "
          f"{len(pre_filtered)} candidats potentiels.", flush=True)

    # Ne pas scraper plus que nécessaire : on garde une marge au cas où le
    # post-filtre en éliminerait.
    pre_filtered = pre_filtered[: MAX_PROFILS_RECHERCHE * 2]

    # --- Étape 5 : Scraping + re-filtre post-scraping ---
    candidats: list[Candidat] = []
    n_post_drop = 0
    for i, h in enumerate(pre_filtered, 1):
        if len(candidats) >= MAX_PROFILS_RECHERCHE:
            break

        url = h["url"]
        print(f"[A3 Chercheur]   Scraping {i}/{len(pre_filtered)} : {url[:70]}", flush=True)
        scraped = extraire_page_web_raw(url)

        # Si le scraping échoue, on retombe sur le snippet DDG (mieux que rien).
        if scraped.startswith("Erreur") or scraped.startswith("Aucun contenu"):
            profil_brut = f"{h.get('title', '')}\n\n{h.get('body', '')}"
        else:
            profil_brut = scraped

        # Re-filtre : le contenu complet peut révéler qu'on est sur une offre.
        if _is_noise(profil_brut):
            n_post_drop += 1
            continue

        candidats.append(Candidat(
            id=str(uuid.uuid4())[:8],
            nom=h.get("title", "") or "Inconnu",
            source=h.get("source", "web"),
            profil_brut=profil_brut,
            url=url or None,
        ))

    print(f"[A3 Chercheur] Post-filtre : {n_post_drop} pages écartées après scraping.", flush=True)
    print(f"[A3 Chercheur] {len(candidats)} profils bruts collectés (avec contenu scrapé).", flush=True)

    return {
        "profils_bruts": candidats,
        "messages": [response]
    }
