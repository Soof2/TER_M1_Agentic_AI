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
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A2_analyste")


def analyste_node(state: GraphState) -> dict:
    """Analyse la fiche de poste et extrait le profil de compétences."""
    m = get_metrics()
    m.debut("A2_analyste")
    _log.info("Analyse de la fiche de poste en cours...")
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

    n_hard = len(profil.get('hard_skills', []))
    n_soft = len(profil.get('soft_skills', []))
    _log.info("Profil extrait : %d hard skills, %d soft skills, %d mots-clés.", n_hard, n_soft, len(profil.get('mots_cles', [])))
    m.fin("A2_analyste", n_hard_skills=n_hard, n_soft_skills=n_soft)

    return {
        "profil_competences": profil,
        "messages": [response]
    }
