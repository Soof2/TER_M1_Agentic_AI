"""
Stack Overflow / Stack Exchange API — Recherche de développeurs.

API publique 100% gratuite :
    - Sans clé  : 300 req/jour
    - Avec clé  : 10 000 req/jour (clé gratuite sur stackapps.com)

Stratégie : chercher les utilisateurs les plus actifs sur un tag
donné (python, machine-learning, django...) — ce sont des devs réels
avec un profil vérifiable, pas des bots ni des offres d'emploi.

Usage :
    from src.tools.stackoverflow_api import search_stackoverflow_users
    hits = search_stackoverflow_users(["python", "machine-learning"], max_results=5)
"""

import os
import requests

from src.logger import get_logger

_log = get_logger("tools.stackoverflow")
_SO_API = "https://api.stackexchange.com/2.3"


def search_stackoverflow_users(tags: list[str], max_results: int = 5) -> list[dict]:
    """Recherche des utilisateurs Stack Overflow actifs sur des tags donnés.

    Args:
        tags: Liste de tags SO (ex: ["python", "machine-learning", "django"]).
              Correspond aux compétences techniques du profil recherché.
        max_results: Nombre max de profils retournés.

    Returns:
        Liste de dicts {title, url, body, source} — même format que
        _ddg_search_raw pour intégration transparente dans A3b.
    """
    # Limiter à 3 tags max pour rester pertinent
    tags_query = ";".join(t.lower().replace(" ", "-") for t in tags[:3])

    params = {
        "order": "desc",
        "sort": "reputation",       # les plus réputés = les plus actifs
        "tagged": tags_query,
        "site": "stackoverflow",
        "pagesize": min(max_results, 10),
        "filter": "!nNPvSNdWme",    # inclut location, website_url, about_me
    }

    # Clé optionnelle pour augmenter le quota (gratuit sur stackapps.com)
    so_key = os.getenv("STACKOVERFLOW_KEY", "")
    if so_key:
        params["key"] = so_key

    try:
        resp = requests.get(
            f"{_SO_API}/users",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        _log.warning("Stack Overflow API indisponible : %s", e)
        return []

    users = data.get("items", [])
    _log.info(
        "Stack Overflow API : %d profils pour tags=[%s]",
        len(users), tags_query,
    )

    results = []
    for user in users[:max_results]:
        name = user.get("display_name", "Inconnu")
        profile_url = user.get("link", "")
        reputation = user.get("reputation", 0)
        location = user.get("location", "")
        about = user.get("about_me", "")
        website = user.get("website_url", "")

        # Nettoyer le champ about_me (peut contenir du HTML)
        if about:
            try:
                from bs4 import BeautifulSoup
                about = BeautifulSoup(about, "html.parser").get_text(separator=" ", strip=True)[:500]
            except Exception:
                about = about[:500]

        body_parts = [f"Réputation Stack Overflow: {reputation}"]
        if location:
            body_parts.append(f"Localisation: {location}")
        if about:
            body_parts.append(f"À propos: {about}")
        if website:
            body_parts.append(f"Site: {website}")
        body_parts.append(f"Tags actifs: {', '.join(tags[:3])}")

        results.append({
            "title": name,
            "url": profile_url,
            "body": "\n".join(body_parts),
            "source": "stackoverflow",
        })

    return results
