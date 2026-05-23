"""
API Gateway REST — FastAPI.

Expose le SMA de recrutement comme un service HTTP REST :
    POST /recruter              → lance le pipeline avec une fiche de poste
    GET  /rapport/{run_id}      → récupère l'état d'un run (rapport + candidats)
    GET  /runs                  → liste tous les runs
    GET  /runs/{run_id}/stream  → flux SSE des événements du pipeline (live)
    POST /runs/{run_id}/hitl    → décision humaine pour reprendre un run
                                  interrompu avant A7 (approve/skip/edit)
    GET  /metrics               → métriques courantes + derniers exports JSON
    GET  /rag                   → état de la mémoire vectorielle ChromaDB
    GET  /health                → vérification de disponibilité

Chaque run est identifié par un UUID. Les résultats et la file d'événements
sont conservés en mémoire et persistés dans SQLite. Le pipeline tourne dans
un thread séparé pour ne pas bloquer la boucle asyncio de FastAPI.

Deux runtimes sont supportés :
    - défaut : LangGraph monolithique (`src.graph`)
    - microservices : orchestrateur HTTP si `SVC_ORCHESTRATEUR` est défini
"""

import asyncio
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.graph import build_graph
from src.observabilite import reset_metrics, get_metrics

# ---------------------------------------------------------------------------
# App FastAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SMA Recrutement — API Gateway",
    description=(
        "API REST exposant le système multi-agents de recrutement. "
        "Le runtime est LangGraph par défaut, ou microservices HTTP si "
        "SVC_ORCHESTRATEUR est défini. Supporte le streaming SSE et le "
        "human-in-the-loop en mode LangGraph."
    ),
    version="1.1.0",
)

# ---------------------------------------------------------------------------
# Stockage en mémoire des runs (prototype — pas de base de données)
# ---------------------------------------------------------------------------

# Structure : {run_id: RunInfo}. Les champs préfixés par "_" sont internes
# et ne sont pas exposés via /rapport.
_runs: dict[str, dict] = {}

# Délai max d'attente d'une décision HITL avant abandon du run (secondes).
_HITL_TIMEOUT = 600
_LOGS_DIR = Path("logs")
_CHROMA_DIR = Path("data/chromadb")
_RUNS_DB_PATH = Path(os.getenv("RUNS_DB_PATH", "data/runs.sqlite"))
_METRICS_HISTORY_LIMIT = 20
_DB_LOCK = threading.Lock()
_SVC_ORCHESTRATEUR = os.getenv("SVC_ORCHESTRATEUR", "").rstrip("/")


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
    status: str          # "running" | "awaiting_hitl" | "done" | "error"
    rapport: Optional[str] = None
    candidats: Optional[list] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    erreur: Optional[str] = None


class HitlDecision(BaseModel):
    action: str                              # "approve" | "skip" | "edit"
    candidats_retenus: Optional[list] = None  # requis si action=="edit"


# ---------------------------------------------------------------------------
# Helpers d'événements — poussés par le worker, lus par le flux SSE
# ---------------------------------------------------------------------------

def _push_event(run_id: str, event_type: str, data: dict) -> None:
    """Ajoute un événement typé à la file de diffusion du run.

    Thread-safe : `queue.Queue` supporte l'accès multi-thread. Les
    consommateurs SSE récupèrent les événements par polling non bloquant.
    """
    info = _runs.get(run_id)
    if info is None:
        return
    q = info.get("_event_queue")
    if q is None:
        return
    q.put({
        "type": event_type,
        "data": {**data, "ts": datetime.now(timezone.utc).isoformat()},
    })


def _close_event_stream(run_id: str) -> None:
    """Pousse le sentinel None : les flux SSE ouverts sortent de leur boucle."""
    info = _runs.get(run_id)
    if info is None:
        return
    q = info.get("_event_queue")
    if q is not None:
        q.put(None)


# ---------------------------------------------------------------------------
# Persistance SQLite des runs
# ---------------------------------------------------------------------------

def _internal_run_fields(info: dict) -> dict:
    """Champs internes non persistés, recréés à chaque démarrage API."""
    return {
        "_event_queue": queue.Queue(),
        "_hitl_event": threading.Event(),
        "_hitl_decision": {},
        "_candidats_pending_hitl": [],
        "_with_interrupt": info.get("_with_interrupt", False),
        "_cancel_event": threading.Event(),
    }


def _init_runs_db() -> None:
    """Crée la table SQLite des runs si nécessaire."""
    _RUNS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK, sqlite3.connect(_RUNS_DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                fiche_poste TEXT NOT NULL,
                status TEXT NOT NULL,
                rapport TEXT,
                candidats_json TEXT,
                erreur TEXT,
                started_at TEXT,
                finished_at TEXT,
                with_interrupt INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def _save_run(run_id: str) -> None:
    """Persiste l'état public d'un run en SQLite."""
    info = _runs.get(run_id)
    if info is None:
        return
    with _DB_LOCK, sqlite3.connect(_RUNS_DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, fiche_poste, status, rapport, candidats_json,
                erreur, started_at, finished_at, with_interrupt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                fiche_poste=excluded.fiche_poste,
                status=excluded.status,
                rapport=excluded.rapport,
                candidats_json=excluded.candidats_json,
                erreur=excluded.erreur,
                started_at=excluded.started_at,
                finished_at=excluded.finished_at,
                with_interrupt=excluded.with_interrupt
            """,
            (
                run_id,
                info.get("fiche_poste", ""),
                info.get("status", "running"),
                info.get("rapport"),
                json.dumps(info.get("candidats"), ensure_ascii=False),
                info.get("erreur"),
                info.get("started_at"),
                info.get("finished_at"),
                1 if info.get("_with_interrupt") else 0,
            ),
        )


def _load_runs_from_db() -> None:
    """Recharge les runs persistés au démarrage de l'API."""
    _init_runs_db()
    with _DB_LOCK, sqlite3.connect(_RUNS_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()

    for row in rows:
        try:
            candidats = json.loads(row["candidats_json"]) if row["candidats_json"] else None
        except json.JSONDecodeError:
            candidats = None
        status = row["status"]
        erreur = row["erreur"]
        finished_at = row["finished_at"]
        if status in ("running", "awaiting_hitl"):
            status = "error"
            erreur = "Run interrompu par redémarrage de l'API."
            finished_at = finished_at or datetime.now(timezone.utc).isoformat()

        info = {
            "run_id": row["run_id"],
            "fiche_poste": row["fiche_poste"],
            "status": status,
            "rapport": row["rapport"],
            "candidats": candidats,
            "erreur": erreur,
            "started_at": row["started_at"],
            "finished_at": finished_at,
            "_with_interrupt": bool(row["with_interrupt"]),
        }
        info.update(_internal_run_fields(info))
        _runs[row["run_id"]] = info
        if status != row["status"] or erreur != row["erreur"]:
            _save_run(row["run_id"])


# ---------------------------------------------------------------------------
# Logique d'exécution du pipeline (thread worker)
# ---------------------------------------------------------------------------

def _run_pipeline(run_id: str, fiche_poste: str, with_interrupt: bool) -> None:
    """Exécute le pipeline LangGraph dans un thread dédié.

    Chaque événement (entrée/sortie de nœud, score A4, statut HITL) est
    poussé dans la file du run pour diffusion SSE. Si `with_interrupt` est
    vrai et que le graphe s'arrête avant A7, le worker bloque sur l'événement
    `_hitl_event` jusqu'à réception d'une décision via POST /hitl.
    """
    from src.logger import get_logger
    log = get_logger("api")

    try:
        log.info("Run %s : démarrage du pipeline.", run_id)
        _runs[run_id]["status"] = "running"
        _save_run(run_id)
        _push_event(run_id, "run_started", {"fiche_poste": fiche_poste[:200]})

        reset_metrics()

        app_graph = build_graph(with_interrupt=with_interrupt)
        config = {"configurable": {"thread_id": run_id}}

        cancel_event: threading.Event = _runs[run_id]["_cancel_event"]

        # --- Première phase : exécution jusqu'à interrupt ou fin ---
        for event in app_graph.stream(
            {"fiche_poste": fiche_poste},
            config=config,
            stream_mode="updates",
        ):
            if cancel_event.is_set():
                raise InterruptedError("Run annulé par l'utilisateur.")
            for node_name, payload in event.items():
                log.info("Run %s : nœud [%s] terminé.", run_id, node_name)
                _push_event(run_id, "node_completed", {
                    "node": node_name,
                    "summary": _resume_payload(payload),
                })

        # --- Détection d'un interrupt (présence d'un nœud en attente) ---
        state = app_graph.get_state(config)
        if with_interrupt and state.next:
            candidats_en_attente = state.values.get("candidats_valides", [])
            log.info(
                "Run %s : interrupt détecté avant %s, %d candidat(s) en attente.",
                run_id, state.next, len(candidats_en_attente),
            )
            _runs[run_id]["status"] = "awaiting_hitl"
            _runs[run_id]["_candidats_pending_hitl"] = candidats_en_attente
            _save_run(run_id)
            _push_event(run_id, "awaiting_hitl", {
                "candidats": candidats_en_attente,
                "next_node": state.next[0] if state.next else None,
            })

            # Attente bloquante de la décision humaine
            hitl_event: threading.Event = _runs[run_id]["_hitl_event"]
            got_decision = hitl_event.wait(timeout=_HITL_TIMEOUT)
            if not got_decision:
                raise TimeoutError(
                    f"Aucune décision HITL reçue en {_HITL_TIMEOUT}s, run abandonné."
                )

            decision = _runs[run_id]["_hitl_decision"]
            log.info("Run %s : décision HITL reçue : %s", run_id, decision["action"])
            _push_event(run_id, "hitl_decision", {"action": decision["action"]})

            # Application de la décision sur l'état du graphe
            if decision["action"] == "skip":
                # Marquer tous les candidats invalides → A7 ne contactera personne,
                # A8 ne les persistera pas (cf. filtre par statut).
                modifies = [
                    {**c, "statut": "invalide", "remarques": "Rejeté par HITL"}
                    for c in candidats_en_attente
                ]
                app_graph.update_state(config, {"candidats_valides": modifies})
            elif decision["action"] == "edit":
                app_graph.update_state(
                    config, {"candidats_valides": decision.get("candidats_retenus", [])}
                )
            # "approve" → on reprend tel quel

            _runs[run_id]["status"] = "running"
            _save_run(run_id)

            # --- Reprise du graphe après la décision ---
            for event in app_graph.stream(None, config=config, stream_mode="updates"):
                if cancel_event.is_set():
                    raise InterruptedError("Run annulé par l'utilisateur.")
                for node_name, payload in event.items():
                    log.info("Run %s : nœud [%s] terminé (post-HITL).", run_id, node_name)
                    _push_event(run_id, "node_completed", {
                        "node": node_name,
                        "summary": _resume_payload(payload),
                    })

        # --- État final ---
        final_state = app_graph.get_state(config)
        rapport = final_state.values.get("rapport_final", "")
        candidats = final_state.values.get("candidats_valides", [])

        _runs[run_id].update({
            "status": "done",
            "rapport": rapport,
            "candidats": candidats,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_run(run_id)
        _push_event(run_id, "run_done", {
            "rapport_chars": len(rapport),
            "candidats": len(candidats),
        })
        log.info("Run %s : pipeline terminé avec succès.", run_id)

    except Exception as exc:
        from src.logger import get_logger
        get_logger("api").exception("Run %s : erreur pipeline.", run_id)
        _runs[run_id].update({
            "status": "error",
            "erreur": str(exc),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_run(run_id)
        _push_event(run_id, "run_error", {"erreur": str(exc)})
    finally:
        _close_event_stream(run_id)


def _rapport_microservices(fiche_poste: str, payload: dict) -> str:
    """Construit un rapport Markdown court depuis la réponse de l'orchestrateur HTTP."""
    valides = payload.get("candidats_valides", [])
    douteux = payload.get("candidats_douteux", [])
    invalides = payload.get("candidats_invalides", [])
    messages = payload.get("messages_envoyes", [])
    requetes = payload.get("requetes_recherche", {})

    def table(candidats: list[dict]) -> str:
        if not candidats:
            return "Aucun."
        rows = [
            "| Nom | Score | Statut | Source | Remarques |",
            "| --- | ---: | --- | --- | --- |",
        ]
        for c in sorted(candidats, key=lambda x: x.get("score_final", 0), reverse=True):
            rows.append(
                "| "
                + " | ".join([
                    str(c.get("nom", "?")).replace("|", "/"),
                    f"{float(c.get('score_final', 0)):.1f}",
                    str(c.get("statut", "")).replace("|", "/"),
                    str(c.get("source", "")).replace("|", "/"),
                    str(c.get("remarques", "")).replace("\n", " ").replace("|", "/"),
                ])
                + " |"
            )
        return "\n".join(rows)

    messages_section = "Aucun message généré."
    if messages:
        messages_section = "\n".join(
            f"- {m.get('nom', 'Candidat')} ({m.get('canal', 'canal non précisé')}) : {m.get('objet', 'Sans objet')}"
            for m in messages
        )

    labels = {
        "queries_generales": "Web général / CV / portfolios",
        "queries_linkedin": "LinkedIn",
        "queries_github": "GitHub Users API",
        "queries_cv_sites": "Sites CV / freelances",
        "tags_stackoverflow": "Tags Stack Overflow",
    }
    recherches_lignes = [
        "| Source | N° | Requête |",
        "| --- | ---: | --- |",
    ]
    for key, label in labels.items():
        valeurs = requetes.get(key, []) if isinstance(requetes, dict) else []
        for index, valeur in enumerate(valeurs, 1):
            safe_valeur = str(valeur).replace("|", "/")
            recherches_lignes.append(f"| {label} | {index} | `{safe_valeur}` |")
    recherches_section = (
        "\n".join(recherches_lignes)
        if len(recherches_lignes) > 2
        else "Aucune requête enregistrée."
    )

    return f"""# Rapport final de recrutement

## Mode d'exécution
- Architecture : microservices HTTP
- Orchestrateur : service `svc-orchestrateur`

## Résumé du poste
- Fiche de poste : {fiche_poste}

## Statistiques de recherche
- Résultats bruts collectés : {payload.get('resultats_bruts_count', 0)}
- Profils trouvés : {payload.get('profils_trouves', 0)}
- Profils après déduplication : {payload.get('profils_deduplication', 0)}
- Candidats évalués : {len(payload.get('candidats_scores', []))}
- Candidats valides : {len(valides)}
- Candidats douteux : {len(douteux)}
- Profils invalides / non-candidats : {len(invalides)}
- Messages générés : {len(messages)}

## Recherches effectuées
{recherches_section}

## Candidats valides à contacter
{table(valides)}

## Candidats douteux à vérifier manuellement
{table(douteux)}

## Profils invalides ou non-candidats
{table(invalides)}

## Messages générés
{messages_section}
"""


def _run_pipeline_microservices(run_id: str, fiche_poste: str, with_interrupt: bool) -> None:
    """Exécute le pipeline distribué via le microservice orchestrateur HTTP.

    Lance le pipeline en mode non-bloquant (POST /pipeline retourne immédiatement),
    puis poll GET /pipeline/{run_id}/status toutes les 2 s. Si la pause HITL est
    activée et que l'orchestrateur passe à "awaiting_hitl", bloque sur l'événement
    local _hitl_event, puis transmet la décision à l'orchestrateur via
    POST /hitl/{run_id}.
    """
    from src.logger import get_logger

    log = get_logger("api.microservices")
    try:
        _runs[run_id]["status"] = "running"
        _runs[run_id]["mode_execution"] = "microservices"
        _save_run(run_id)
        _push_event(run_id, "run_started", {
            "fiche_poste": fiche_poste[:200],
            "mode_execution": "microservices",
        })

        cancel_event: threading.Event = _runs[run_id]["_cancel_event"]
        hitl_event: threading.Event   = _runs[run_id]["_hitl_event"]

        # --- Démarrage non-bloquant ---
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{_SVC_ORCHESTRATEUR}/pipeline",
                json={
                    "run_id": run_id,
                    "fiche_poste": fiche_poste,
                    "with_interrupt": with_interrupt,
                },
            )
            r.raise_for_status()

        # --- Polling jusqu'à "done" ou "error" ---
        payload: dict | None = None
        while payload is None:
            if cancel_event.is_set():
                raise InterruptedError("Run annulé par l'utilisateur.")

            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{_SVC_ORCHESTRATEUR}/pipeline/{run_id}/status")
                r.raise_for_status()
                status_data = r.json()

            orch_status = status_data.get("status")

            if orch_status == "awaiting_hitl" and _runs[run_id]["status"] != "awaiting_hitl":
                # Transition locale vers l'état d'attente HITL
                candidats = status_data.get("candidats_pending", [])
                _runs[run_id]["status"] = "awaiting_hitl"
                _runs[run_id]["_candidats_pending_hitl"] = candidats
                _save_run(run_id)
                _push_event(run_id, "awaiting_hitl", {
                    "candidats": candidats,
                    "next_node": "recruteur",
                })
                log.info(
                    "Run %s : pause HITL — %d candidat(s) en attente.", run_id, len(candidats)
                )

                # Attente bloquante de la décision humaine (via POST /runs/{run_id}/hitl)
                got = hitl_event.wait(timeout=_HITL_TIMEOUT)
                if not got:
                    raise TimeoutError(
                        f"Aucune décision HITL reçue en {_HITL_TIMEOUT}s, run abandonné."
                    )
                if cancel_event.is_set():
                    raise InterruptedError("Run annulé par l'utilisateur.")

                decision = _runs[run_id]["_hitl_decision"]
                log.info("Run %s : décision HITL reçue : %s", run_id, decision["action"])
                _push_event(run_id, "hitl_decision", {"action": decision["action"]})

                # Transmission de la décision à l'orchestrateur
                with httpx.Client(timeout=10.0) as client:
                    r = client.post(
                        f"{_SVC_ORCHESTRATEUR}/hitl/{run_id}",
                        json=decision,
                    )
                    r.raise_for_status()

                _runs[run_id]["status"] = "running"
                _save_run(run_id)

            elif orch_status == "done":
                payload = status_data.get("result") or {}

            elif orch_status == "error":
                raise RuntimeError(
                    status_data.get("error") or "Erreur inconnue dans l'orchestrateur."
                )

            else:
                # "running" : attendre avant le prochain poll
                time.sleep(2)

        # --- Traitement du résultat final ---
        for node in (
            "analyste",
            "chercheur_stratege",
            "chercheur_collecteur",
            "chercheur_filtre",
            "deduplicateur",
            "evaluateur",
            "verificateur",
            "recruteur",
            "rapport",
        ):
            _push_event(run_id, "node_completed", {
                "node": node,
                "summary": {"mode": "microservices"},
            })

        candidats = (
            payload.get("candidats_valides", [])
            + payload.get("candidats_douteux", [])
            + payload.get("candidats_invalides", [])
        )
        rapport = payload.get("rapport") or _rapport_microservices(fiche_poste, payload)

        _runs[run_id].update({
            "status": "done",
            "rapport": rapport,
            "candidats": candidats,
            "mode_execution": "microservices",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_run(run_id)
        _push_event(run_id, "run_done", {
            "rapport_chars": len(rapport),
            "candidats": len(candidats),
            "mode_execution": "microservices",
        })
        log.info("Run %s : pipeline microservices terminé avec succès.", run_id)

    except Exception as exc:  # noqa: BLE001
        log.exception("Run %s : erreur pipeline microservices.", run_id)
        _runs[run_id].update({
            "status": "error",
            "erreur": str(exc),
            "mode_execution": "microservices",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_run(run_id)
        _push_event(run_id, "run_error", {"erreur": str(exc)})
    finally:
        _close_event_stream(run_id)


def _run_pipeline_entry(run_id: str, fiche_poste: str, with_interrupt: bool) -> None:
    """Choisit le runtime selon la configuration.

    Sans SVC_ORCHESTRATEUR : runtime LangGraph monolithique.
    Avec SVC_ORCHESTRATEUR : runtime microservices HTTP.
    """
    if _SVC_ORCHESTRATEUR:
        _run_pipeline_microservices(run_id, fiche_poste, with_interrupt)
    else:
        _run_pipeline(run_id, fiche_poste, with_interrupt)


def _resume_payload(payload) -> dict:
    """Résumé court d'un payload de nœud pour l'émission SSE.

    Les payloads bruts peuvent contenir des listes longues ou des textes
    volumineux ; on ne renvoie qu'un aperçu numérique/textuel par clé.
    """
    if not isinstance(payload, dict):
        return {}
    resume = {}
    for key, value in payload.items():
        if isinstance(value, list):
            resume[key] = f"list({len(value)})"
        elif isinstance(value, str):
            resume[key] = value[:80]
        elif isinstance(value, dict):
            resume[key] = f"dict({len(value)})"
        else:
            resume[key] = str(value)[:80]
    return resume


def _metrics_snapshot() -> dict:
    """Retourne un snapshot non destructif des métriques en mémoire."""
    metrics = get_metrics()
    started = getattr(metrics, "_debut_run", datetime.now().timestamp())
    return {
        "run_id": getattr(metrics, "_run_id", None),
        "duree_totale_s": round(datetime.now().timestamp() - started, 2),
        "etapes": getattr(metrics, "_etapes", {}),
    }


def _load_metrics_history(limit: int = _METRICS_HISTORY_LIMIT) -> list[dict]:
    """Charge les derniers exports JSON de métriques depuis logs/."""
    if not _LOGS_DIR.exists():
        return []

    history: list[dict] = []
    files = sorted(_LOGS_DIR.glob("metriques_*.json"), reverse=True)[:limit]
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        payload["_file"] = path.name
        history.append(payload)
    return history


def _rag_counts() -> dict:
    """Compte les collections ChromaDB sans initialiser SentenceTransformer."""
    if not _CHROMA_DIR.exists():
        return {
            "available": False,
            "persist_dir": str(_CHROMA_DIR),
            "candidats": 0,
            "fiches_poste": 0,
            "error": None,
        }

    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        candidats = client.get_or_create_collection("candidats_evalues").count()
        fiches = client.get_or_create_collection("fiches_poste").count()
        return {
            "available": True,
            "persist_dir": str(_CHROMA_DIR),
            "candidats": candidats,
            "fiches_poste": fiches,
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "persist_dir": str(_CHROMA_DIR),
            "candidats": 0,
            "fiches_poste": 0,
            "error": str(exc),
        }


_load_runs_from_db()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Monitoring"])
async def health() -> JSONResponse:
    """Vérifie que le service est disponible."""
    runs_total = len(_runs)
    runs_running = sum(
        1 for r in _runs.values() if r["status"] in ("running", "awaiting_hitl")
    )
    return JSONResponse({
        "status": "ok",
        "mode_execution": "microservices" if _SVC_ORCHESTRATEUR else "langgraph",
        "runs_total": runs_total,
        "runs_running": runs_running,
    })


@app.post("/recruter", response_model=RecruterResponse, tags=["Pipeline"])
async def recruter(
    req: RecruterRequest, background_tasks: BackgroundTasks
) -> RecruterResponse:
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
        "mode_execution": "microservices" if _SVC_ORCHESTRATEUR else "langgraph",
        # Champs internes pour SSE et HITL
        "_event_queue": queue.Queue(),
        "_hitl_event": threading.Event(),
        "_hitl_decision": {},
        "_candidats_pending_hitl": [],
        "_with_interrupt": not req.no_interrupt,
        "_cancel_event": threading.Event(),
    }
    _save_run(run_id)

    background_tasks.add_task(
        _run_pipeline_entry,
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
    """Récupère le rapport d'un run de recrutement."""
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
            "fiche_poste": r.get("fiche_poste", "")[:120],
            "mode_execution": r.get("mode_execution", "microservices" if _SVC_ORCHESTRATEUR else "langgraph"),
            "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"),
        }
        for r in _runs.values()
    ]
    summary.sort(key=lambda x: x["started_at"] or "", reverse=True)
    return JSONResponse({"runs": summary, "total": len(summary)})


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics_summary(
    limit: int = Query(default=_METRICS_HISTORY_LIMIT, ge=1, le=100),
) -> JSONResponse:
    """Retourne les métriques en mémoire et les derniers exports JSON."""
    return JSONResponse({
        "current": _metrics_snapshot(),
        "history": _load_metrics_history(limit),
    })


@app.get("/rag", tags=["Monitoring"])
async def get_rag_summary() -> JSONResponse:
    """Retourne l'état de la mémoire RAG locale."""
    return JSONResponse(_rag_counts())


@app.get("/rag/search", tags=["Monitoring"])
async def search_rag(
    q: str = Query(..., min_length=1),
    fiche_poste: Optional[str] = Query(default=None),
    n: int = Query(default=5, ge=1, le=20),
) -> JSONResponse:
    """Recherche des profils similaires dans ChromaDB.

    Cet endpoint initialise SentenceTransformer uniquement sur demande,
    car le chargement du modèle peut être coûteux.
    """
    try:
        from src.tools.rag import get_memoire

        results = get_memoire().rechercher_similaires(
            profil_brut=q,
            fiche_poste=fiche_poste,
            n_results=n,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return JSONResponse({"results": results, "total": len(results)})


@app.get("/runs/{run_id}/stream", tags=["Pipeline"])
async def stream_run(run_id: str) -> StreamingResponse:
    """Flux Server-Sent Events (SSE) des événements du pipeline.

    Événements typés :
        run_started     — début du pipeline
        node_completed  — fin d'un nœud du graphe (payload résumé)
        awaiting_hitl   — interrupt avant A7, candidats en attente
        hitl_decision   — décision humaine reçue
        run_done        — pipeline terminé, rapport prêt
        run_error       — erreur fatale

    Format respecté : `event: <type>\\ndata: <json>\\n\\n`.
    """
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' introuvable.")

    q: queue.Queue = _runs[run_id]["_event_queue"]

    async def event_generator():
        if _runs[run_id]["status"] in ("done", "error") and q.empty():
            yield "event: stream_closed\ndata: {}\n\n"
            return
        # Petit délai de polling : compromis latence/CPU. 100 ms suffisent
        # pour une UI temps réel et évitent de saturer un worker.
        while True:
            try:
                event = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.1)
                continue
            if event is None:
                # Sentinel de fin : terminer proprement le flux.
                yield "event: stream_closed\ndata: {}\n\n"
                break
            yield (
                f"event: {event['type']}\n"
                f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # désactive le buffering côté proxy nginx
        },
    )


@app.post("/runs/{run_id}/hitl", tags=["Pipeline"])
async def submit_hitl(run_id: str, decision: HitlDecision) -> JSONResponse:
    """Transmet une décision humaine pour reprendre un run interrompu.

    - **action** : `approve` (reprend tel quel), `skip` (ne contacte aucun
      candidat), `edit` (remplace la liste de candidats validés).
    - **candidats_retenus** : requis si `action == "edit"`, doit être une
      liste de candidats au format `CandidatValide`.
    """
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' introuvable.")

    info = _runs[run_id]
    if info["status"] != "awaiting_hitl":
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' n'est pas en attente de décision (statut: {info['status']}).",
        )

    if decision.action not in ("approve", "skip", "edit"):
        raise HTTPException(
            status_code=422,
            detail="action doit être parmi : approve, skip, edit.",
        )

    if decision.action == "edit" and decision.candidats_retenus is None:
        raise HTTPException(
            status_code=422,
            detail="candidats_retenus est requis pour action=edit.",
        )

    info["_hitl_decision"] = {
        "action": decision.action,
        "candidats_retenus": decision.candidats_retenus or [],
    }
    info["_hitl_event"].set()
    _save_run(run_id)

    return JSONResponse({
        "run_id": run_id,
        "action": decision.action,
        "message": "Décision prise en compte, reprise du pipeline en cours.",
    })


@app.post("/runs/{run_id}/cancel", tags=["Pipeline"])
async def cancel_run(run_id: str) -> JSONResponse:
    """Annule un run en cours. Le pipeline s'arrête proprement entre deux nœuds."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' introuvable.")

    info = _runs[run_id]
    if info["status"] not in ("running", "awaiting_hitl"):
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' ne peut pas être annulé (statut: {info['status']}).",
        )

    info["_cancel_event"].set()
    # Si en attente HITL, débloquer aussi le thread worker
    if info["status"] == "awaiting_hitl":
        info["_hitl_event"].set()

    return JSONResponse({"run_id": run_id, "message": "Annulation demandée."})
