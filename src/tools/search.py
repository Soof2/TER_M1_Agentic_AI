"""Outils de recherche de profils candidats."""

from langchain_classic.tools import tool
from ddgs import DDGS


@tool
def recherche_profils(query: str) -> str:
    """Recherche des profils de candidats sur le web via DuckDuckGo.

    Args:
        query: Requête de recherche (ex: "développeur Python senior Paris LinkedIn")
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "Aucun résultat trouvé."
        output = []
        for r in results:
            output.append(f"Titre: {r['title']}\nURL: {r['href']}\nExtrait: {r['body']}\n")
        return "\n---\n".join(output)
    except Exception as e:
        return f"Erreur de recherche: {e}"


@tool
def recherche_linkedin(query: str) -> str:
    """Recherche des profils LinkedIn via DuckDuckGo.

    Args:
        query: Mots-clés de recherche (compétences, poste, localisation)
    """
    search_query = f"site:linkedin.com/in {query}"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=5))
        if not results:
            return "Aucun profil LinkedIn trouvé."
        output = []
        for r in results:
            output.append(f"Nom: {r['title']}\nURL: {r['href']}\nRésumé: {r['body']}\n")
        return "\n---\n".join(output)
    except Exception as e:
        return f"Erreur de recherche LinkedIn: {e}"


@tool
def recherche_github(query: str) -> str:
    """Recherche des profils GitHub via DuckDuckGo.

    Args:
        query: Mots-clés de recherche (langages, technologies, projets)
    """
    search_query = f"site:github.com {query}"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=5))
        if not results:
            return "Aucun profil GitHub trouvé."
        output = []
        for r in results:
            output.append(f"Profil: {r['title']}\nURL: {r['href']}\nDescription: {r['body']}\n")
        return "\n---\n".join(output)
    except Exception as e:
        return f"Erreur de recherche GitHub: {e}"


# Liste des outils disponibles pour l'agent chercheur
search_tools = [recherche_profils, recherche_linkedin, recherche_github]
