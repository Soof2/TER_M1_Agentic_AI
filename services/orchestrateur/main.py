"""
Microservice Orchestrateur — remplace LangGraph.

Coordonne le pipeline complet via appels HTTP aux autres microservices :
  A2 → A3 → A6 (dedup inline) → A4×N (parallèle) → A5×N (parallèle) → A7 ou rapport
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.agents.deduplicateur import deduplicateur_node
from src.agents.persistance import persistance_node

app = FastAPI(title="Orchestrateur", version="1.0")
log = logging.getLogger("svc-orchestrateur")

# URLs des microservices (configurables via env)
SVC_ANALYSTE    = os.getenv("SVC_ANALYSTE",    "http://svc-analyste:8001")
SVC_CHERCHEUR   = os.getenv("SVC_CHERCHEUR",   "http://svc-chercheur:8002")
SVC_EVALUATEUR  = os.getenv("SVC_EVALUATEUR",  "http://svc-evaluateur:8003")
SVC_VERIFICATEUR = os.getenv("SVC_VERIFICATEUR", "http://svc-verificateur:8004")
SVC_RECRUTEUR   = os.getenv("SVC_RECRUTEUR",   "http://svc-recruteur:8005")

SCORE_SEUIL_CONTACT = int(os.getenv("SCORE_SEUIL_CONTACT", "75"))
SCORE_SEUIL_VIABLE  = int(os.getenv("SCORE_SEUIL_VIABLE",  "40"))
TOP_N_RELATIF       = int(os.getenv("TOP_N_RELATIF", "3"))
TIMEOUT = 120.0


class PipelineRequest(BaseModel):
    fiche_poste: str
    run_id: str = ""


async def _evaluer_un(client: httpx.AsyncClient, candidat: dict, profil_competences: dict, fiche_poste: str) -> dict | None:
    try:
        r = await client.post(
            f"{SVC_EVALUATEUR}/evaluer",
            json={"candidat": candidat, "profil_competences": profil_competences, "fiche_poste": fiche_poste},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("candidat_score")
    except Exception as e:
        log.exception("Erreur A4 évaluateur pour %s", candidat.get("nom", "?"))
        return {"_error": str(e), "_stage": "evaluateur", "candidat_id": candidat.get("id")}


async def _verifier_un(client: httpx.AsyncClient, score: dict, profil_source: dict, profil_competences: dict) -> dict | None:
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "orchestrateur"}


@app.post("/pipeline")
async def pipeline(body: PipelineRequest):
    run_id = body.run_id or str(uuid.uuid4())
    ts_debut = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient() as client:

        # --- A2 : Analyste ---
        try:
            r = await client.post(
                f"{SVC_ANALYSTE}/analyser",
                json={"fiche_poste": body.fiche_poste},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            profil_competences = r.json().get("profil_competences", {})
        except Exception as e:
            raise HTTPException(502, f"A2 Analyste error: {e}")

        # --- A3 : Chercheur (Stratège + Collecteur + Filtre) ---
        try:
            r = await client.post(
                f"{SVC_CHERCHEUR}/chercher",
                json={"profil_competences": profil_competences, "fiche_poste": body.fiche_poste},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            chercheur_payload = r.json()
            profils_bruts = chercheur_payload.get("profils_bruts", [])
            requetes_recherche = chercheur_payload.get("requetes_recherche", {})
            resultats_bruts_count = chercheur_payload.get("resultats_bruts_count", 0)
        except Exception as e:
            raise HTTPException(502, f"A3 Chercheur error: {e}")

        # --- A6 : Déduplication ---
        profils = deduplicateur_node({"profils_bruts": profils_bruts}).get("profils_dedupliques", [])

        # --- A4 : Évaluateurs en parallèle ---
        scores_raw = await asyncio.gather(*[
            _evaluer_un(client, p, profil_competences, body.fiche_poste) for p in profils
        ])
        erreurs = [s for s in scores_raw if s and s.get("_error")]
        candidats_scores = [s for s in scores_raw if s and not s.get("_error")]

        # Construire index profil_source pour A5
        profil_index = {p["id"]: p for p in profils}

        # --- A5 : Vérificateurs en parallèle ---
        valides_raw = await asyncio.gather(*[
            _verifier_un(client, s, profil_index.get(s.get("candidat_id"), {}), profil_competences)
            for s in candidats_scores
        ])
        erreurs.extend(v for v in valides_raw if v and v.get("_error"))
        candidats_valides = [v for v in valides_raw if v and not v.get("_error")]

        # --- Injection RAG : candidats connus des runs précédents ---
        try:
            from src.tools.rag import get_memoire
            urls_actuels = {c.get("url") for c in candidats_valides if c.get("url")}
            ids_actuels = {c.get("candidat_id") for c in candidats_valides}
            connus = get_memoire().get_candidats_connus(body.fiche_poste)
            for c in connus:
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
        valides = [c for c in candidats_valides if c.get("statut") == "valide"]
        douteux = [c for c in candidats_valides if c.get("statut") == "douteux"]
        invalides = [c for c in candidats_valides if c.get("statut") == "invalide"]

        messages_envoyes = []
        if valides:
            # --- A7 : Recruteur ---
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
            except Exception as exc:  # noqa: BLE001
                log.exception("Erreur A7 recruteur")
                erreurs.append({"_stage": "recruteur", "_error": str(exc)})

        # --- A8 : Persistance RAG ---
        try:
            persistance_node({
                "fiche_poste": body.fiche_poste,
                "profils_dedupliques": profils,
                "candidats_valides": candidats_valides,
            })
        except Exception as exc:  # noqa: BLE001
            log.exception("Erreur A8 persistance")
            erreurs.append({"_stage": "persistance", "_error": str(exc)})

    # --- A8 : Persistance RAG ---
    try:
        from src.agents.persistance import persistance_node
        persistance_node({
            "candidats_valides": candidats_valides,
            "profils_dedupliques": profils,
            "fiche_poste": body.fiche_poste,
        })
    except Exception:
        pass

    return {
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
