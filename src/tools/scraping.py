"""Outils d'extraction de profils depuis des pages web."""

import requests
from bs4 import BeautifulSoup
from langchain_classic.tools import tool


@tool
def extraire_page_web(url: str) -> str:
    """Extrait le texte principal d'une page web (profil candidat, page GitHub, etc.).

    Args:
        url: URL de la page à extraire
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Supprimer scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Limiter la taille pour le LLM
        if len(text) > 3000:
            text = text[:3000] + "\n[... tronqué]"

        return text if text.strip() else "Aucun contenu textuel extrait."
    except requests.RequestException as e:
        return f"Erreur d'extraction: {e}"


scraping_tools = [extraire_page_web]
