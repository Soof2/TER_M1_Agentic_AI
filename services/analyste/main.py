"""Microservice A2 — Analyste de poste."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.agents.analyste import analyste_node

app = FastAPI(title="A2 Analyste", version="1.0")


class FichePoste(BaseModel):
    fiche_poste: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "analyste"}


@app.post("/analyser")
def analyser(body: FichePoste):
    try:
        # analyste_node retourne {"profil_competences": {...}, "messages": [...]}
        result = analyste_node({"fiche_poste": body.fiche_poste, "messages": []})
        return {"profil_competences": result["profil_competences"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
