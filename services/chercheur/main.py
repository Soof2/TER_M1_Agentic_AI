"""Microservice A3 — Chercheur (Stratège + Collecteur + Filtre)."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.agents.chercheur_stratege import stratege_node
from src.agents.chercheur_collecteur import collecteur_node
from src.agents.chercheur_filtre import filtre_node

app = FastAPI(title="A3 Chercheur", version="1.0")


class ProfilCompetences(BaseModel):
    profil_competences: dict
    fiche_poste: str = ""


@app.get("/health")
def health():
    return {"status": "ok", "service": "chercheur"}


@app.post("/chercher")
def chercher(body: ProfilCompetences):
    try:
        state = {
            "profil_competences": body.profil_competences,
            "fiche_poste": body.fiche_poste,
            "messages": [],
        }
        # A3a — Stratège
        state.update(stratege_node(state))
        # A3b — Collecteur
        state.update(collecteur_node(state))
        # A3c — Filtre
        state.update(filtre_node(state))
        return {
            "profils_bruts": state.get("profils_bruts", []),
            "requetes_recherche": state.get("requetes_recherche", {}),
            "resultats_bruts_count": len(state.get("resultats_bruts", [])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
