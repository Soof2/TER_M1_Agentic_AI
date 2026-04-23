"""
API Gateway REST — FastAPI.

Expose le SMA de recrutement comme un service HTTP REST :
    POST /recruter          → lance le pipeline avec une fiche de poste
    GET  /rapport/{run_id}  → récupère l'état d'un run (rapport + candidats)
    GET  /health            → vérification de disponibilité du service

Chaque run est identifié par un UUID. Les résultats sont conservés en
mémoire pendant la durée de vie du processus (suffisant pour le prototype).
Le pipeline tourne dans un thread séparé (run_in_executor) pour ne pas
bloquer la boucle asyncio de FastAPI.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.graph import build_graph
from src.observabilite import reset_metrics

# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SMA Recrutement — API Gateway",
    description=(
        "API REST exposant le système multi-agents de recrutement (LangGraph). "
        "Permet de lancer des pipelines et de récupérer les rapports."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Stockage en mémoire des runs (prototype — pas de base de données)
# ---------------------------------------------------------------------------

# Structure : {run_id: RunInfo}
_runs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Schémas de requête / réponse
# ---------------------------------------------------------------------------

class RecruterRequest(BaseModel):
    fiche_poste: str
    no_interrupt: bool = True   # Par défaut pas d'interrupt via API


class RecruterResponse(BaseModel):
    run_id: str
    status: str          # "running"
    message: str


class RapportResponse(BaseModel):
    run_id: str
    status: str          # "running" | "done" | "error"
    rapport: Optional[str] = None
    candidats: Optional[list] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    erreur: Optional[str] = None


# ---------------------------------------------------------------------------
# Logique d'exécution du pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(run_id: str, fiche_poste: str, with_interrupt: bool) -> None:
    """Exécute le pipeline LangGraph dans un thread dédié.

    Modifie _runs[run_id] en place pour refléter l'avancement.
    Appelé via executor.submit() pour ne pas bloquer asyncio.
    """
    from src.logger import get_logger
    log = get_logger("api")

    try:
        log.info("Run %s : démarrage du pipeline.", run_id)
        _runs[run_id]["status"] = "running"

        # Réinitialiser les métriques pour ce run
        reset_metrics()

        app_graph = build_graph(with_interrupt=with_interrupt)
        thread_id = run_id
        config = {"configurable": {"thread_id": thread_id}}

        # Exécution complète (pas d'interaction humaine via API)
        for event in app_graph.stream(
            {"fiche_poste": fiche_poste},
            config=config,
            stream_mode="updates",
        ):
            for node_name in event:
                log.info("Run %s : nœud [%s] terminé.", run_id, node_name)

        # Récupérer l'état final
        final_state = app_graph.get_state(config)
        rapport = final_state.values.get("rapport_final", "")
        candidats = final_state.values.get("candidats_valides", [])

        _runs[run_id].update({
            "status": "done",
            "rapport": rapport,
            "candidats": candidats,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info("Run %s : pipeline terminé avec succès.", run_id)

    except Exception as exc:  # noqa: BLE001
        from src.logger import get_logger
        get_logger("api").exception("Run %s : erreur pipeline.", run_id)
        _runs[run_id].update({
            "status": "error",
            "erreur": str(exc),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Monitoring"])
async def health() -> JSONResponse:
    """Vérifie que le service est disponible."""
    runs_total = len(_runs)
    runs_running = sum(1 for r in _runs.values() if r["status"] == "running")
    return JSONResponse({
        "status": "ok",
        "runs_total": runs_total,
        "runs_running": runs_running,
    })


@app.post("/recruter", response_model=RecruterResponse, tags=["Pipeline"])
async def recruter(req: RecruterRequest, background_tasks: BackgroundTasks) -> RecruterResponse:
    """Lance un nouveau pipeline de recrutement.

    - **fiche_poste** : description du poste à pourvoir
    - **no_interrupt** : si True (défaut), désactive le human-in-the-loop
    """
    if not req.fiche_poste.strip():
        raise HTTPException(status_code=422, detail="fiche_poste ne peut pas être vide.")

    run_id = str(uuid.uuid4())
    _runs[run_id] = {
        "run_id": run_id,
        "fiche_poste": req.fiche_poste,
        "status": "running",
        "rapport": None,
        "candidats": None,
        "erreur": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }

    # Lancer le pipeline en tâche de fond (thread pool, non-bloquant)
    background_tasks.add_task(
        _run_pipeline,
        run_id,
        req.fiche_poste,
        not req.no_interrupt,
    )

    return RecruterResponse(
        run_id=run_id,
        status="running",
        message=f"Pipeline lancé. Consultez /rapport/{run_id} pour le résultat.",
    )


@app.get("/rapport/{run_id}", response_model=RapportResponse, tags=["Pipeline"])
async def get_rapport(run_id: str) -> RapportResponse:
    """Récupère le rapport d'un run de recrutement.

    - **status** : `running` | `done` | `error`
    - **rapport** : texte du rapport final (disponible quand `status=done`)
    - **candidats** : liste des candidats validés avec scores
    """
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' introuvable.")

    info = _runs[run_id]
    return RapportResponse(
        run_id=run_id,
        status=info["status"],
        rapport=info.get("rapport"),
        candidats=info.get("candidats"),
        started_at=info.get("started_at"),
        finished_at=info.get("finished_at"),
        erreur=info.get("erreur"),
    )


@app.get("/runs", tags=["Monitoring"])
async def list_runs() -> JSONResponse:
    """Liste tous les runs avec leur statut (sans les rapports complets)."""
    summary = [
        {
            "run_id": r["run_id"],
            "status": r["status"],
            "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"),
        }
        for r in _runs.values()
    ]
    summary.sort(key=lambda x: x["started_at"] or "", reverse=True)
    return JSONResponse({"runs": summary, "total": len(summary)})
