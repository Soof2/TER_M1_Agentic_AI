"""
A4 — Évaluateur de Profil (×N instances).

Calcule un score de matching multicritères pour chaque candidat.
Massivement parallélisable via le pattern Send() de LangGraph —
N instances traitent N profils simultanément.
"""

import json
import time
import random
from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import CandidatScore
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER
from src.prompts import EVALUATEUR_SYSTEM
from src.observabilite import get_metrics
from src.logger import get_logger


def evaluateur_node(state: dict) -> dict:
    """Évalue UN candidat par rapport au profil de compétences.

    Note: Reçoit un state partiel via Send() contenant :
        - candidat: Candidat
        - profil_competences: dict
    """
    candidat = state["candidat"]
    profil = state["profil_competences"]
    log = get_logger("A4_evaluateur")
    m = get_metrics()
    m.debut(f"A4_{candidat['id']}")

    log.info("Évaluation de : %s (source: %s)", candidat['nom'], candidat['source'])

    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    eval_msg = f"""Profil de compétences requis :
{json.dumps(profil, ensure_ascii=False, indent=2)}

Profil du candidat :
Nom : {candidat['nom']}
Source : {candidat['source']}
Profil :
{candidat['profil_brut']}

Évalue ce candidat par rapport au profil requis."""

    messages = [
        SystemMessage(content=EVALUATEUR_SYSTEM),
        HumanMessage(content=eval_msg)
    ]

    # Retry avec backoff pour gérer les limites de requêtes concurrentes
    for attempt in range(5):
        try:
            response = llm.invoke(messages)
            break
        except Exception as e:
            if "429" in str(e) or "too many" in str(e).lower():
                wait = (2 ** attempt) + random.uniform(0, 1)
                log.warning("Rate limit pour %s, retry %d/5 dans %.1fs...", candidat['nom'], attempt + 1, wait)
                time.sleep(wait)
            else:
                raise
    else:
        # Toutes les tentatives échouées
        return {
            "candidats_scores": [CandidatScore(
                candidat_id=candidat["id"],
                nom=candidat["nom"],
                score_global=0.0,
                scores_detail={},
                resume=f"Évaluation échouée après 5 tentatives pour {candidat['nom']}"
            )]
        }

    content = response.content.strip()

    # Extraire le JSON
    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        scores = json.loads(content)
    except json.JSONDecodeError:
        scores = {
            "score_global": 50.0,
            "scores_detail": {
                "hard_skills": 50,
                "soft_skills": 50,
                "experience": 50,
                "culture_fit": 50
            },
            "resume": f"Évaluation non parsable pour {candidat['nom']}. Réponse brute: {content[:200]}"
        }

    score_global = float(scores.get("score_global", 50))
    candidat_score = CandidatScore(
        candidat_id=candidat["id"],
        nom=candidat["nom"],
        score_global=score_global,
        scores_detail=scores.get("scores_detail", {}),
        resume=scores.get("resume", "")
    )

    log.info("%s -> score: %.1f/100", candidat['nom'], score_global)
    m.fin(f"A4_{candidat['id']}", nom=candidat['nom'], score=score_global, source=candidat['source'])

    return {
        "candidats_scores": [candidat_score]
    }
