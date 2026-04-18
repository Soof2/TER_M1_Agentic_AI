"""
Outil de recherche GitHub via l'API officielle.

Remplace la recherche DuckDuckGo pour GitHub : l'API retourne
des profils utilisateurs réels (pas des repos, pas du bruit).

Auth :
    - Sans GITHUB_TOKEN : 60 req/h (suffisant pour un run)
    - Avec GITHUB_TOKEN  : 5 000 req/h (recommandé en prod)

Usage :
    from src.tools.github_api import search_github_users
    hits = search_github_users("python machine learning Paris", max_results=5)
"""

import os
import time
import requests

from src.logger import get_logger

_log = get_logger("tools.github")
_GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    """Construit les headers HTTP avec ou sans token."""
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get_user_profile(login: str, hdrs: dict) -> dict:
    """Récupère le profil détaillé d'un utilisateur GitHub."""
    try:
        resp = requests.get(
            f"{_GITHUB_API}/users/{login}",
            headers=hdrs,
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def search_github_users(query: str, max_results: int = 5) -> list[dict]:
    """Recherche des utilisateurs GitHub par compétences / localisation.

    Args:
        query: Requête GitHub (ex: "python machine learning location:Paris").
               Les opérateurs GitHub Search sont supportés :
               location:, language:, followers:>N, repos:>N
        max_results: Nombre max de profils retournés.

    Returns:
        Liste de dicts {title, url, body, source} — même format que
        _ddg_search_raw pour une intégration transparente dans A3b.
    """
    hdrs = _headers()

    try:
        resp = requests.get(
            f"{_GITHUB_API}/search/users",
            params={"q": query, "per_page": min(max_results, 10), "type": "Users"},
            headers=hdrs,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            _log.warning("GitHub API : rate limit atteint. Ajouter GITHUB_TOKEN dans .env")
        else:
            _log.warning("GitHub API erreur HTTP : %s", e)
        return []
    except Exception as e:
        _log.warning("GitHub API indisponible : %s", e)
        return []

    users = data.get("items", [])
    _log.info("GitHub API : %d résultats pour '%s...'", len(users), query[:50])

    results = []
    for user in users[:max_results]:
        login = user.get("login", "")
        profile_url = user.get("html_url", f"https://github.com/{login}")

        # Fetch profil complet (bio, location, company, stats)
        profile = _get_user_profile(login, hdrs)

        # Pause légère pour ne pas spammer l'API sur les profils détaillés
        time.sleep(0.1)

        bio = profile.get("bio") or ""
        location = profile.get("location") or ""
        company = (profile.get("company") or "").strip().lstrip("@")
        repos = profile.get("public_repos", 0)
        followers = profile.get("followers", 0)
        name = profile.get("name") or login

        # Construire un "body" lisible pour le filtre et l'évaluateur
        body_parts = []
        if bio:
            body_parts.append(f"Bio: {bio}")
        if location:
            body_parts.append(f"Localisation: {location}")
        if company:
            body_parts.append(f"Entreprise: {company}")
        body_parts.append(f"Dépôts publics: {repos} | Followers: {followers}")
        body = "\n".join(body_parts)

        results.append({
            "title": name,
            "url": profile_url,
            "body": body,
            "source": "github",
        })

    return results
