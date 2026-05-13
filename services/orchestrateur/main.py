"""
Microservice Orchestrateur — remplace LangGraph.

Coordonne le pipeline complet via appels HTTP aux autres microservices :
  A2 → A3 → A6 (dedup inline) → A4×N (parallèle) → A5×N (parallèle) → A7 ou rapport
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Orchestrateur", version="1.0")

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


def _dedupliquer(profils: list) -> list:
    seen, out = set(), []
    for p in profils:
        url = (p.get("url") or "").strip().lower()
        key = url or p.get("nom", "")
        if key and key not in seen:
            seen.add(key)
            out.append(p)
    return out


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
        return None


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
        return None


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
            profils_bruts = r.json().get("profils_bruts", [])
        except Exception as e:
            raise HTTPException(502, f"A3 Chercheur error: {e}")

        # --- A6 : Déduplication (inline) ---
        profils = _dedupliquer(profils_bruts)

        # --- A4 : Évaluateurs en parallèle ---
        scores_raw = await asyncio.gather(*[
            _evaluer_un(client, p, profil_competences, body.fiche_poste) for p in profils
        ])
        candidats_scores = [s for s in scores_raw if s]

        # Construire index profil_source pour A5
        profil_index = {p["id"]: p for p in profils}

        # --- A5 : Vérificateurs en parallèle ---
        valides_raw = await asyncio.gather(*[
            _verifier_un(client, s, profil_index.get(s.get("candidat_id"), {}), profil_competences)
            for s in candidats_scores
        ])
        candidats_valides = [v for v in valides_raw if v]

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
            except Exception:
                pass
        elif not valides:
            # Mode relatif : top-N parmi les viables
            viables = sorted(
                [c for c in douteux if c.get("score_final", 0) >= SCORE_SEUIL_VIABLE],
                key=lambda x: x.get("score_final", 0),
                reverse=True,
            )[:TOP_N_RELATIF]
            if viables:
                try:
                    r = await client.post(
                        f"{SVC_RECRUTEUR}/recruter",
                        json={
                            "candidats_valides": viables,
                            "fiche_poste": body.fiche_poste,
                            "profil_competences": profil_competences,
                        },
                        timeout=TIMEOUT,
                    )
                    r.raise_for_status()
                    messages_envoyes = r.json().get("messages_envoyes", [])
                except Exception:
                    pass

    return {
        "run_id": run_id,
        "ts_debut": ts_debut,
        "ts_fin": datetime.now(timezone.utc).isoformat(),
        "profil_competences": profil_competences,
        "profils_trouves": len(profils_bruts),
        "profils_deduplication": len(profils),
        "candidats_scores": candidats_scores,
        "candidats_valides": valides,
        "candidats_douteux": douteux,
        "candidats_invalides": invalides,
        "messages_envoyes": messages_envoyes,
    }
