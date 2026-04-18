"""Outils de recherche de profils candidats.

Deux niveaux d'API :
    - `_ddg_search_raw(...)` : helper interne qui retourne une liste de dicts
      structurés {title, url, body, source}. Utilisé par A3 pour pouvoir
      filtrer / scraper / dédupliquer sur des objets typés.
    - `@tool recherche_*` : wrappers LangChain qui renvoient du texte formaté,
      conservés pour compatibilité si un agent veut utiliser bind_tools.
"""

from langchain_classic.tools import tool
from ddgs import DDGS


# Exclusions DuckDuckGo pour réduire le bruit (offres d'emploi, annonces).
# Le problème : une requête "développeur Python Paris" ramène en majorité
# des offres d'emploi au lieu de candidats. Ces exclusions filtrent ça à
# la source avant même le scraping.
DDG_EXCLUSIONS = (
    '-"offre d\'emploi" -"postuler" -"nous recrutons" '
    '-"rejoignez-nous" -"CDI à pourvoir" -"candidature"'
)

# Domaines utiles pour cibler des CV, portfolios et profils de freelances.
# Utilisé comme référence documentaire par le prompt du chercheur et peut
# servir à construire des requêtes « site: » ciblées à l'avenir.
CV_SITE_TARGETS = (
    "doyoubuzz.com",
    "malt.fr",
    "viadeo.com",
    "about.me",
    "behance.net",
    "dribbble.com",
    "stackoverflow.com/users",
)


def _ddg_search_raw(
    query: str,
    site_filter: str | None = None,
    max_results: int = 5,
) -> list[dict]:
    """Exécute une recherche DuckDuckGo et retourne des résultats structurés.

    Args:
        query: Requête de recherche brute (sera enrichie avec les exclusions).
        site_filter: Filtre "site:" optionnel (ex: "linkedin.com/in", "github.com").
        max_results: Nombre max de résultats à retourner.

    Returns:
        Liste de dicts avec les clés : title, url, body, source.
        Retourne une liste vide en cas d'erreur ou si aucun résultat.
    """
    # Construire la requête finale avec exclusions + filtre site éventuel
    parts = []
    if site_filter:
        parts.append(f"site:{site_filter}")
    parts.append(query)
    parts.append(DDG_EXCLUSIONS)
    final_query = " ".join(parts)

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(final_query, max_results=max_results))
    except Exception as e:
        from src.logger import get_logger
        get_logger("tools.search").warning("Erreur DDG pour '%s...': %s", query[:50], e)
        return []

    hits = []
    for r in results:
        url = r.get("href", "") or ""
        # Déterminer la source à partir de l'URL
        if "linkedin.com" in url:
            source = "linkedin"
        elif "github.com" in url:
            source = "github"
        elif "indeed" in url or "indeed.fr" in url:
            source = "indeed"
        else:
            source = "web"

        hits.append({
            "title": r.get("title", "") or "",
            "url": url,
            "body": r.get("body", "") or "",
            "source": source,
        })

    return hits


@tool
def recherche_profils(query: str) -> str:
    """Recherche des profils de candidats sur le web via DuckDuckGo.

    Args:
        query: Requête de recherche (ex: "développeur Python senior Paris LinkedIn")
    """
    hits = _ddg_search_raw(query, site_filter=None, max_results=5)
    if not hits:
        return "Aucun résultat trouvé."
    return "\n---\n".join(
        f"Titre: {h['title']}\nURL: {h['url']}\nExtrait: {h['body']}\n"
        for h in hits
    )


@tool
def recherche_linkedin(query: str) -> str:
    """Recherche des profils LinkedIn via DuckDuckGo.

    Args:
        query: Mots-clés de recherche (compétences, poste, localisation)
    """
    hits = _ddg_search_raw(query, site_filter="linkedin.com/in", max_results=5)
    if not hits:
        return "Aucun profil LinkedIn trouvé."
    return "\n---\n".join(
        f"Nom: {h['title']}\nURL: {h['url']}\nRésumé: {h['body']}\n"
        for h in hits
    )


@tool
def recherche_github(query: str) -> str:
    """Recherche des profils GitHub via DuckDuckGo.

    Args:
        query: Mots-clés de recherche (langages, technologies, projets)
    """
    hits = _ddg_search_raw(query, site_filter="github.com", max_results=5)
    if not hits:
        return "Aucun profil GitHub trouvé."
    return "\n---\n".join(
        f"Profil: {h['title']}\nURL: {h['url']}\nDescription: {h['body']}\n"
        for h in hits
    )


# Liste des outils disponibles pour l'agent chercheur
search_tools = [recherche_profils, recherche_linkedin, recherche_github]
