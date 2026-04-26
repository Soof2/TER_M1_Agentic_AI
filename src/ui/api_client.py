"""
Client HTTP asynchrone vers l'API Gateway FastAPI.

L'UI NiceGUI ne parle pas directement au graphe LangGraph : elle passe par
l'API REST (séparation claire pour l'argumentaire d'architecture). Toutes
les fonctions ici sont `async` pour être appelées naturellement depuis les
callbacks NiceGUI et `ui.timer`.

Le flux SSE est consommé par `stream_events()` qui produit des dicts
`{"type": str, "data": dict}` ligne par ligne, à brancher sur l'UI via
une tâche d'arrière-plan qui met à jour les widgets.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator, Optional

import httpx

API_URL = os.getenv("API_URL", "http://localhost:8000")
_SHORT_TIMEOUT = httpx.Timeout(10.0, read=10.0)


# ---------------------------------------------------------------------------
# Requêtes ponctuelles
# ---------------------------------------------------------------------------

async def launch_run(fiche_poste: str, no_interrupt: bool = False) -> dict:
    """POST /recruter — démarre un pipeline. Retourne {run_id, status, message}."""
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.post(
            f"{API_URL}/recruter",
            json={"fiche_poste": fiche_poste, "no_interrupt": no_interrupt},
        )
        resp.raise_for_status()
        return resp.json()


async def get_rapport(run_id: str) -> dict:
    """GET /rapport/{run_id} — état complet d'un run."""
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.get(f"{API_URL}/rapport/{run_id}")
        resp.raise_for_status()
        return resp.json()


async def list_runs() -> list[dict]:
    """GET /runs — historique des runs, trié décroissant par started_at."""
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.get(f"{API_URL}/runs")
        resp.raise_for_status()
        return resp.json().get("runs", [])


async def submit_hitl(
    run_id: str,
    action: str,
    candidats_retenus: Optional[list] = None,
) -> dict:
    """POST /runs/{run_id}/hitl — transmet la décision humaine."""
    payload: dict = {"action": action}
    if candidats_retenus is not None:
        payload["candidats_retenus"] = candidats_retenus
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.post(
            f"{API_URL}/runs/{run_id}/hitl", json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def health() -> dict:
    """GET /health — sonde de disponibilité de l'API."""
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.get(f"{API_URL}/health")
        resp.raise_for_status()
        return resp.json()


async def get_metrics_summary(limit: int = 20) -> dict:
    """GET /metrics — métriques courantes + derniers exports."""
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.get(f"{API_URL}/metrics", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()


async def get_rag_summary() -> dict:
    """GET /rag — état de la mémoire vectorielle."""
    async with httpx.AsyncClient(timeout=_SHORT_TIMEOUT) as client:
        resp = await client.get(f"{API_URL}/rag")
        resp.raise_for_status()
        return resp.json()


async def search_rag(q: str, fiche_poste: str | None = None, n: int = 5) -> dict:
    """GET /rag/search — recherche de profils similaires."""
    params: dict = {"q": q, "n": n}
    if fiche_poste:
        params["fiche_poste"] = fiche_poste
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=60.0)) as client:
        resp = await client.get(f"{API_URL}/rag/search", params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Stream SSE — parser minimal sans dépendance externe
# ---------------------------------------------------------------------------

def parse_sse_chunks(lines: list[str]) -> list[dict]:
    """Parser pur (testable sans réseau) : convertit un bloc de lignes SSE en
    liste d'événements typés. Un événement est un triplet de lignes séparé
    par une ligne vide :

        event: <type>
        data: <json>

    Les champs inconnus sont ignorés. Le JSON invalide est remonté en clair
    dans {"data": {"raw": ...}} pour ne pas perdre l'information.
    """
    events: list[dict] = []
    event_type: Optional[str] = None
    data_raw: Optional[str] = None

    for line in lines:
        if line == "":
            if event_type is not None and data_raw is not None:
                try:
                    parsed = json.loads(data_raw)
                except json.JSONDecodeError:
                    parsed = {"raw": data_raw}
                events.append({"type": event_type, "data": parsed})
            event_type = None
            data_raw = None
        elif line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_raw = line[5:].lstrip()

    return events


async def stream_events(run_id: str) -> AsyncIterator[dict]:
    """Consomme le flux SSE du run et produit un événement à chaque bloc.

    Arrête proprement le flux à réception de `stream_closed`. En cas
    d'erreur réseau, yield un événement {"type": "connection_error", ...}
    puis termine.
    """
    url = f"{API_URL}/runs/{run_id}/stream"
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    yield {
                        "type": "connection_error",
                        "data": {"status_code": response.status_code},
                    }
                    return

                buffer: list[str] = []
                async for line in response.aiter_lines():
                    buffer.append(line)
                    if line == "":
                        for ev in parse_sse_chunks(buffer):
                            yield ev
                            if ev["type"] == "stream_closed":
                                return
                        buffer = []
    except httpx.HTTPError as exc:
        yield {"type": "connection_error", "data": {"error": str(exc)}}
