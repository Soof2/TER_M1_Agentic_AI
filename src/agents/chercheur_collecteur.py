"""
A3b — Collecteur de Profils.

Exécute le plan de recherche produit par A3a :
    - Requêtes web générales  → DuckDuckGo
    - Requêtes LinkedIn       → DuckDuckGo (site:linkedin.com/in)
    - Requêtes GitHub         → API officielle GitHub Search Users
    - Requêtes CV/portfolios  → DuckDuckGo (site:malt.fr, doyoubuzz.com, etc.)

Responsabilité unique : collecte des hits bruts (COMMENT chercher).
Pas de LLM, pas de filtrage : produit des résultats bruts structurés.

Output :
    resultats_bruts : list[dict]  — hits {title, url, body, source}
                                    dédupliqués par URL
"""

import time

from src.state import GraphState
from src.tools.search import _ddg_search_raw
from src.tools.github_api import search_github_users
from src.tools.stackoverflow_api import search_stackoverflow_users
from src.observabilite import get_metrics
from src.logger import get_logger

_DDG_DELAY = 1.5  # secondes entre chaque appel DDG pour éviter le rate-limit

_log = get_logger("A3b_collecteur")


def collecteur_node(state: GraphState) -> dict:
    """Collecte les profils bruts depuis DDG et l'API GitHub."""
    m = get_metrics()
    m.debut("A3b_collecteur")

    requetes = state.get("requetes_recherche", {})

    n_gen = len(requetes.get("queries_generales", []))
    n_li = len(requetes.get("queries_linkedin", []))
    n_gh = len(requetes.get("queries_github", []))
    n_cv = len(requetes.get("queries_cv_sites", []))
    tags_so = requetes.get("tags_stackoverflow", [])
    n_so = 1 if tags_so else 0

    _log.info(
        "Lancement : %d sources (%d web DDG, %d LinkedIn DDG, %d GitHub API, %d CV DDG, %d Stack Overflow API)",
        n_gen + n_li + n_gh + n_cv + n_so, n_gen, n_li, n_gh, n_cv, n_so,
    )

    all_hits: list[dict] = []

    # --- Web général (DDG — gratuit, sans limite explicite) ---
    for i, q in enumerate(requetes.get("queries_generales", []), 1):
        _log.info("  Web DDG %d/%d : %s...", i, n_gen, q[:60])
        all_hits.extend(_ddg_search_raw(q, site_filter=None, max_results=8))
        time.sleep(_DDG_DELAY)

    # --- LinkedIn (DDG avec filtre site: — gratuit) ---
    for i, q in enumerate(requetes.get("queries_linkedin", []), 1):
        _log.info("  LinkedIn DDG %d/%d : %s...", i, n_li, q[:60])
        all_hits.extend(_ddg_search_raw(q, site_filter="linkedin.com/in", max_results=8))
        time.sleep(_DDG_DELAY)

    # --- GitHub (API officielle gratuite — 60 req/h sans token, 5000 avec) ---
    for i, q in enumerate(requetes.get("queries_github", []), 1):
        _log.info("  GitHub API %d/%d : %s...", i, n_gh, q[:60])
        all_hits.extend(search_github_users(q, max_results=8))

    # --- Sites CV/portfolios (DDG — gratuit) ---
    for i, q in enumerate(requetes.get("queries_cv_sites", []), 1):
        _log.info("  CV/Portfolio DDG %d/%d : %s...", i, n_cv, q[:60])
        all_hits.extend(_ddg_search_raw(q, site_filter=None, max_results=8))
        time.sleep(_DDG_DELAY)

    # --- Stack Overflow (API officielle gratuite — 300/j sans clé, 10 000/j avec clé gratuite) ---
    if tags_so:
        _log.info("  Stack Overflow API : tags=%s...", tags_so[:3])
        all_hits.extend(search_stackoverflow_users(tags_so, max_results=5))

    n_bruts = len(all_hits)
    _log.info("%d résultats bruts collectés.", n_bruts)

    # --- Déduplication par URL ---
    seen: set[str] = set()
    deduped: list[dict] = []
    for h in all_hits:
        url = h.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(h)

    n_dedup = len(deduped)
    _log.info("%d résultats après déduplication URL (%d doublons supprimés).", n_dedup, n_bruts - n_dedup)

    m.fin(
        "A3b_collecteur",
        n_bruts=n_bruts,
        n_apres_dedup=n_dedup,
        sources={"ddg_web": n_gen, "ddg_linkedin": n_li, "github_api": n_gh, "ddg_cv": n_cv, "stackoverflow_api": n_so},
    )

    return {"resultats_bruts": deduped}
