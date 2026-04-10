"""
A2 — Analyste de Poste.

Analyse la fiche de poste et produit une structure de compétences.
Publie sur le blackboard (profil_competences) — les autres agents
s'abonnent à ses résultats sans couplage direct.
"""

import json
from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER
from src.prompts import ANALYSTE_SYSTEM


def analyste_node(state: GraphState) -> dict:
    """Analyse la fiche de poste et extrait le profil de compétences."""
    print("\n[A2 Analyste] Analyse de la fiche de poste en cours...", flush=True)
    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    messages = [
        SystemMessage(content=ANALYSTE_SYSTEM),
        HumanMessage(content=f"Fiche de poste :\n\n{state['fiche_poste']}")
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # Extraire le JSON de la réponse
    try:
        # Nettoyer les éventuels backticks markdown
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        profil = json.loads(content)
    except json.JSONDecodeError:
        # Fallback : extraction basique si le LLM ne produit pas du JSON valide
        profil = {
            "hard_skills": [],
            "soft_skills": [],
            "experience_min": 0,
            "formation": "",
            "contraintes": [],
            "mots_cles": [],
            "raw_response": content
        }

    print(f"[A2 Analyste] Profil extrait : {len(profil.get('hard_skills', []))} hard skills, "
          f"{len(profil.get('soft_skills', []))} soft skills, "
          f"{len(profil.get('mots_cles', []))} mots-clés.", flush=True)

    return {
        "profil_competences": profil,
        "messages": [response]
    }
