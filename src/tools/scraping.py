"""Outils d'extraction de profils depuis des pages web.

Deux niveaux d'API :
    - `extraire_page_web_raw(url)` : fonction simple utilisable depuis n'importe
      quel agent sans passer par LangChain. Retourne le texte brut tronqué.
    - `@tool extraire_page_web` : wrapper LangChain qui enveloppe la fonction
      ci-dessus pour les cas où on veut l'exposer via bind_tools.
"""

import requests
from bs4 import BeautifulSoup


def extraire_page_web_raw(url: str, max_chars: int = 3000) -> str:
    """Extrait le texte principal d'une page web (version non-tool).

    Args:
        url: URL de la page à extraire.
        max_chars: Nombre max de caractères à garder.

    Returns:
        Le texte extrait, tronqué si nécessaire. Retourne une chaîne
        commençant par "Erreur" en cas d'échec HTTP.
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

        if len(text) > max_chars:
            text = text[:max_chars] + "\n[... tronqué]"

        return text if text.strip() else "Aucun contenu textuel extrait."
    except requests.RequestException as e:
        return f"Erreur d'extraction: {e}"


def extraire_page_web(url: str) -> str:
    """Extrait le texte principal d'une page web (profil candidat, page GitHub, etc.).

    Args:
        url: URL de la page à extraire
    """
    return extraire_page_web_raw(url)


scraping_tools = [extraire_page_web]
