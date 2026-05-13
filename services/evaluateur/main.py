"""Microservice A4 — Évaluateur de profil."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.agents.evaluateur import evaluateur_node

app = FastAPI(title="A4 Evaluateur", version="1.0")


class EvalRequest(BaseModel):
    candidat: dict          # Candidat brut (id, nom, source, profil_brut, url)
    profil_competences: dict
    fiche_poste: str = ""


@app.get("/health")
def health():
    return {"status": "ok", "service": "evaluateur"}


@app.post("/evaluer")
def evaluer(body: EvalRequest):
    try:
        # evaluateur_node attend state["candidat"] et state["profil_competences"]
        state = {
            "candidat": body.candidat,
            "profil_competences": body.profil_competences,
            "fiche_poste": body.fiche_poste,
            "candidats_scores": [],
        }
        result = evaluateur_node(state)
        scores = result.get("candidats_scores", [])
        return {"candidat_score": scores[0] if scores else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
