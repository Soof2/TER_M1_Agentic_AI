"""Microservice A7 — Recruteur."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.agents.recruteur import recruteur_node

app = FastAPI(title="A7 Recruteur", version="1.0")


class RecrutRequest(BaseModel):
    candidats_valides: list
    fiche_poste: str
    profil_competences: dict = {}


@app.get("/health")
def health():
    return {"status": "ok", "service": "recruteur"}


@app.post("/recruter")
def recruter(body: RecrutRequest):
    try:
        state = {
            "candidats_valides": body.candidats_valides,
            "fiche_poste": body.fiche_poste,
            "profil_competences": body.profil_competences,
            "messages_envoyes": [],
            "messages": [],
        }
        result = recruteur_node(state)
        return {"messages_envoyes": result.get("messages_envoyes", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
