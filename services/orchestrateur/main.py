"""
Microservice Orchestrateur — remplace LangGraph.

Coordonne le pipeline complet via appels HTTP aux autres microservices :
  A2 → A3 → A6 (dedup inline) → A4×N (parallèle) → A5×N (parallèle) → [HITL] → A7 → A8

Le pipeline tourne en tâche de fond asyncio ; l'endpoint POST /pipeline
retourne immédiatement. Les clients polent GET /pipeline/{run_id}/status
et soumettent les décisions HITL via POST /hitl/{run_id}.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.agents.deduplicateur import deduplicateur_node
from src.agents.persistance import persistance_node

app = FastAPI(title="Orchestrateur", version="1.1")
log = logging.getLogger("svc-orchestrateur")

# URLs des microservices (configurables via env)
SVC_ANALYSTE     = os.getenv("SVC_ANALYSTE",     "http://svc-analyste:8001")
SVC_CHERCHEUR    = os.getenv("SVC_CHERCHEUR",    "http://svc-chercheur:8002")
SVC_EVALUATEUR   = os.getenv("SVC_EVALUATEUR",   "http://svc-evaluateur:8003")
SVC_VERIFICATEUR = os.getenv("SVC_VERIFICATEUR", "http://svc-verificateur:8004")
SVC_RECRUTEUR    = os.getenv("SVC_RECRUTEUR",    "http://svc-recruteur:8005")

SCORE_SEUIL_CONTACT = int(os.getenv("SCORE_SEUIL_CONTACT", "75"))
SCORE_SEUIL_VIABLE  = int(os.getenv("SCORE_SEUIL_VIABLE",  "40"))
TOP_N_RELATIF       = int(os.getenv("TOP_N_RELATIF", "3"))
TIMEOUT      = 120.0
HITL_TIMEOUT = 600  # secondes avant abandon si aucune décision humaine

# État des runs en cours (en mémoire — prototype ; nettoyé au redémarrage)
_active_runs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Schémas
# ---------------------------------------------------------------------------

class PipelineRequest(BaseModel):
    fiche_poste: str
    run_id: str = ""
    with_interrupt: bool = False  # active la pause HITL avant A7


class HitlDecision(BaseModel):
    action: str                              # "approve" | "skip" | "edit"
    candidats_retenus: Optional[list] = None  # requis si action == "edit"


# ---------------------------------------------------------------------------
# Helpers A4 / A5
# ---------------------------------------------------------------------------

async def _evaluer_un(
    client: httpx.AsyncClient,
    candidat: dict,
    profil_competences: dict,
    fiche_poste: str,
) -> dict | None:
    try:
        r = await client.post(
            f"{SVC_EVALUATEUR}/evaluer",
            json={
                "candidat": candidat,
                "profil_competences": profil_competences,
                "fiche_poste": fiche_poste,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("candidat_score")
    except Exception as e:
        log.exception("Erreur A4 évaluateur pour %s", candidat.get("nom", "?"))
        return {"_error": str(e), "_stage": "evaluateur", "candidat_id": candidat.get("id")}


async def _verifier_un(
    client: httpx.AsyncClient,
    score: dict,
    profil_source: dict,
    profil_competences: dict,
) -> dict | None:
    try:
        r = await client.post(
            f"{SVC_VERIFICATEUR}/verifier",
            json={
                "candidat_score": score,
                "profil_source": profil_source,
                "profil_competences": profil_competences,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("candidat_valide")
    except Exception as e:
        log.exception("Erreur A5 vérificateur pour %s", score.get("nom", "?"))
        return {"_error": str(e), "_stage": "verificateur", "candidat_id": score.get("candidat_id")}


# ---------------------------------------------------------------------------
# Pipeline en tâche de fond
# ---------------------------------------------------------------------------

async def _run_pipeline_bg(run_id: str, body: PipelineRequest) -> None:
    """Exécute le pipeline complet dans une coroutine asyncio."""
    run = _active_runs[run_id]
    ts_debut = datetime.now(timezone.utc).isoformat()

    try:
        async with httpx.AsyncClient() as client:

            # --- A2 : Analyste ---
            r = await client.post(
                f"{SVC_ANALYSTE}/analyser",
                json={"fiche_poste": body.fiche_poste},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            profil_competences = r.json().get("profil_competences", {})

            # --- A3 : Chercheur ---
            r = await client.post(
                f"{SVC_CHERCHEUR}/chercher",
                json={"profil_competences": profil_competences, "fiche_poste": body.fiche_poste},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            chercheur_payload = r.json()
            profils_bruts          = chercheur_payload.get("profils_bruts", [])
            requetes_recherche     = chercheur_payload.get("requetes_recherche", {})
            resultats_bruts_count  = chercheur_payload.get("resultats_bruts_count", 0)

            # --- A6 : Déduplication ---
            profils = deduplicateur_node({"profils_bruts": profils_bruts}).get("profils_dedupliques", [])

            # --- A4 : Évaluateurs en parallèle ---
            scores_raw = await asyncio.gather(*[
                _evaluer_un(client, p, profil_competences, body.fiche_poste)
                for p in profils
            ])
            erreurs = [s for s in scores_raw if s and s.get("_error")]
            candidats_scores = [s for s in scores_raw if s and not s.get("_error")]

            profil_index = {p["id"]: p for p in profils}

            # --- A5 : Vérificateurs en parallèle ---
            valides_raw = await asyncio.gather(*[
                _verifier_un(
                    client,
                    s,
                    profil_index.get(s.get("candidat_id"), {}),
                    profil_competences,
                )
                for s in candidats_scores
            ])
            erreurs.extend(v for v in valides_raw if v and v.get("_error"))
            candidats_valides = [v for v in valides_raw if v and not v.get("_error")]

            # --- Injection RAG ---
            try:
                from src.tools.rag import get_memoire
                urls_actuels = {c.get("url") for c in candidats_valides if c.get("url")}
                ids_actuels  = {c.get("candidat_id") for c in candidats_valides}
                for c in get_memoire().get_candidats_connus(body.fiche_poste):
                    if c.get("url") in urls_actuels or c["candidat_id"] in ids_actuels:
                        continue
                    candidats_valides.append({
                        "candidat_id": c["candidat_id"],
                        "nom": c["nom"],
                        "score_final": c["score"],
                        "statut": "valide",
                        "remarques": f"[RAG] Candidat connu (run précédent). {c['remarques'][:120]}".strip(),
                        "source": c.get("source", ""),
                        "url": c.get("url") or None,
                    })
            except Exception:
                pass

            # --- Routage ---
            valides   = [c for c in candidats_valides if c.get("statut") == "valide"]
            douteux   = [c for c in candidats_valides if c.get("statut") == "douteux"]
            invalides = [c for c in candidats_valides if c.get("statut") == "invalide"]

            # --- Pause HITL (si activée et candidats valides présents) ---
            if body.with_interrupt and valides:
                log.info(
                    "Run %s : pause HITL — %d candidat(s) en attente de validation humaine.",
                    run_id, len(valides),
                )
                run["status"] = "awaiting_hitl"
                run["candidats_pending"] = valides

                try:
                    await asyncio.wait_for(
                        run["_hitl_event"].wait(),
                        timeout=HITL_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(
                        f"Aucune décision HITL reçue en {HITL_TIMEOUT}s, run abandonné."
                    )

                decision = run["_hitl_decision"]
                action = decision.get("action", "approve")
                log.info("Run %s : décision HITL reçue : %s", run_id, action)

                if action == "skip":
                    valides = []
                elif action == "edit":
                    valides = decision.get("candidats_retenus") or []
                # approve → valides inchangés

                run["status"] = "running"

            # --- A7 : Recruteur ---
            messages_envoyes: list = []
            if valides:
                try:
                    r = await client.post(
                        f"{SVC_RECRUTEUR}/recruter",
                        json={
                            "candidats_valides": valides,
                            "fiche_poste": body.fiche_poste,
                            "profil_competences": profil_competences,
                        },
                        timeout=TIMEOUT,
                    )
                    r.raise_for_status()
                    messages_envoyes = r.json().get("messages_envoyes", [])
                except Exception as exc:
                    log.exception("Erreur A7 recruteur")
                    erreurs.append({"_stage": "recruteur", "_error": str(exc)})

        # --- A8 : Persistance RAG (hors client HTTP) ---
        try:
            persistance_node({
                "fiche_poste": body.fiche_poste,
                "profils_dedupliques": profils,
                "candidats_valides": candidats_valides,
            })
        except Exception as exc:
            log.exception("Erreur A8 persistance")
            erreurs.append({"_stage": "persistance", "_error": str(exc)})

        run["status"] = "done"
        run["result"] = {
            "run_id": run_id,
            "mode_execution": "microservices",
            "ts_debut": ts_debut,
            "ts_fin": datetime.now(timezone.utc).isoformat(),
            "profil_competences": profil_competences,
            "requetes_recherche": requetes_recherche,
            "resultats_bruts_count": resultats_bruts_count,
            "profils_trouves": len(profils_bruts),
            "profils_deduplication": len(profils),
            "candidats_scores": candidats_scores,
            "candidats_valides": valides,
            "candidats_douteux": douteux,
            "candidats_invalides": invalides,
            "messages_envoyes": messages_envoyes,
            "erreurs_partielles": erreurs,
        }
        log.info("Run %s : pipeline terminé (%d valide(s)).", run_id, len(valides))

    except Exception as exc:
        log.exception("Run %s : erreur pipeline.", run_id)
        run["status"] = "error"
        run["error"] = str(exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "orchestrateur"}


@app.post("/pipeline")
async def pipeline(body: PipelineRequest):
    """Démarre le pipeline en tâche de fond et retourne immédiatement."""
    run_id = body.run_id or str(uuid.uuid4())
    _active_runs[run_id] = {
        "status": "running",
        "result": None,
        "error": None,
        "candidats_pending": [],
        "_hitl_event": asyncio.Event(),
        "_hitl_decision": None,
    }
    asyncio.create_task(_run_pipeline_bg(run_id, body))
    return {"run_id": run_id, "status": "running"}


@app.get("/pipeline/{run_id}/status")
async def pipeline_status(run_id: str):
    """Retourne le statut courant du pipeline (polling par le gateway)."""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' introuvable.")
    run = _active_runs[run_id]
    return {
        "run_id": run_id,
        "status": run["status"],
        "candidats_pending": (
            run["candidats_pending"] if run["status"] == "awaiting_hitl" else []
        ),
        "result": run["result"],
        "error": run["error"],
    }


@app.post("/hitl/{run_id}")
async def hitl(run_id: str, decision: HitlDecision):
    """Transmet la décision humaine pour reprendre un pipeline en pause HITL."""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' introuvable.")
    run = _active_runs[run_id]
    if run["status"] != "awaiting_hitl":
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' n'est pas en attente HITL (statut: {run['status']}).",
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
    run["_hitl_decision"] = decision.dict()
    run["_hitl_event"].set()
    log.info("Run %s : décision HITL '%s' transmise.", run_id, decision.action)
    return {"run_id": run_id, "action": decision.action}
