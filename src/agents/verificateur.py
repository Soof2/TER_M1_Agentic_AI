"""
A5 — Vérificateur.

Vérifie la cohérence des profils scorés par A4. Validation pair-à-pair
formelle : A4 produit, A5 contrôle indépendamment. La séparation des
sous-champs (candidats_scores / candidats_valides) impose cette contrainte.
"""

import json
import re
from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState, CandidatValide
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER
from src.prompts import VERIFICATEUR_SYSTEM
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A5_verificateur")


def _profil_trop_experimente(profil_brut: str) -> bool:
    """Détecte les signaux simples de profil trop senior pour alternance/junior."""
    texte = profil_brut.lower()
    marqueurs = (
        "senior", "lead", "manager", "architecte", "principal",
        "confirmé", "confirme", "head of", "cto", "directeur",
        "10 ans", "10+ ans", "15 ans", "20 ans",
    )
    return any(m in texte for m in marqueurs)


def verificateur_node(state: GraphState) -> dict:
    """Vérifie et valide les scores des candidats."""
    m = get_metrics()
    m.debut("A5_verificateur")
    candidats_scores = state.get("candidats_scores", [])
    _log.info("Vérification de %d candidats scorés...", len(candidats_scores))

    if not candidats_scores:
        _log.warning("Aucun candidat à vérifier.")
        return {"candidats_valides": []}

    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    # Construire un index des profils bruts par ID pour croisement
    profils_par_id = {}
    for p in state.get("profils_dedupliques", []):
        profils_par_id[p["id"]] = p

    # Préparer les données complètes : scores + profils bruts
    profil_requis = state.get("profil_competences", {})
    candidats_info = []
    for cs in candidats_scores:
        entry = {
            "candidat_id": cs["candidat_id"],
            "nom": cs["nom"],
            "score_global": cs["score_global"],
            "scores_detail": cs["scores_detail"],
            "resume_evaluateur": cs["resume"]
        }
        # Ajouter le profil brut pour que A5 puisse vérifier les incohérences
        profil_brut = profils_par_id.get(cs["candidat_id"])
        if profil_brut:
            entry["profil_brut"] = profil_brut["profil_brut"]
            entry["source"] = profil_brut["source"]
        candidats_info.append(entry)

    verif_msg = f"""Voici les candidats évalués à vérifier. Pour chaque candidat, tu as :
- Le score et le résumé de l'évaluateur (A4)
- Le profil brut original pour croiser les informations

Profil requis :
{json.dumps(profil_requis, ensure_ascii=False, indent=2)}

Candidats :

{json.dumps(candidats_info, ensure_ascii=False, indent=2)}

Pour chaque candidat, vérifie :
1. Les incohérences entre le profil brut et le score attribué
2. Les dates suspectes (expérience irréaliste, chevauchements)
3. Les CV gonflés (trop de compétences sans preuves, titres vagues)
4. Les profils qui ne sont PAS des candidats (offres d'emploi, pages d'entreprise, agrégateurs)
5. Le niveau attendu : si le profil requis indique alternant/stagiaire/junior, rejette ou baisse fortement les profils clairement confirmés/senior/lead/manager

Invalide les profils qui ne sont clairement pas des candidats individuels.
Marque comme "douteux" ceux avec des incohérences.
Ajuste le score_final si nécessaire."""

    messages = [
        SystemMessage(content=VERIFICATEUR_SYSTEM),
        HumanMessage(content=verif_msg)
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # Extraire le JSON (Mistral ajoute souvent du texte avant/après)
    try:
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        # Chercher un array JSON n'importe où dans la réponse
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            content = match.group()
        validations = json.loads(content)
        if not isinstance(validations, list):
            validations = [validations]
    except (json.JSONDecodeError, AttributeError):
        _log.warning("JSON non parsable depuis le vérificateur — fallback score original.")
        validations = [
            {
                "candidat_id": cs["candidat_id"],
                "nom": cs["nom"],
                "score_final": cs["score_global"],
                "statut": "douteux",
                "remarques": "Vérification automatique non parsable"
            }
            for cs in candidats_scores
        ]

    # Construire les CandidatValide
    candidats_valides = []
    profils_par_candidat_id = {
        p["id"]: p.get("profil_brut", "")
        for p in state.get("profils_dedupliques", [])
    }
    niveau_requis = profil_requis.get("niveau_seniorite", "indifferent")
    for v in validations:
        candidat_id = v.get("candidat_id", "")
        score_final = float(v.get("score_final", 0))
        statut = v.get("statut", "douteux")
        remarques = v.get("remarques", "")
        if niveau_requis in ("alternant", "stagiaire", "junior") and _profil_trop_experimente(
            profils_par_candidat_id.get(candidat_id, "")
        ):
            score_final = min(score_final, 45.0)
            statut = "douteux" if statut == "valide" else statut
            remarques = f"{remarques} Niveau trop expérimenté pour un poste {niveau_requis}.".strip()
        candidats_valides.append(CandidatValide(
            candidat_id=candidat_id,
            nom=v.get("nom", ""),
            score_final=score_final,
            statut=statut,
            remarques=remarques
        ))

    n_valides = sum(1 for c in candidats_valides if c["statut"] == "valide")
    n_invalides = sum(1 for c in candidats_valides if c["statut"] == "invalide")
    n_douteux = sum(1 for c in candidats_valides if c["statut"] == "douteux")
    _log.info("Résultat : %d valides, %d douteux, %d invalides.", n_valides, n_douteux, n_invalides)
    for c in sorted(candidats_valides, key=lambda x: x["score_final"], reverse=True):
        _log.info("  %s | %.1f/100 | %s", c['nom'], c['score_final'], c['statut'])
    m.fin("A5_verificateur", n_entree=len(candidats_scores), n_valides=n_valides, n_douteux=n_douteux, n_invalides=n_invalides)

    return {
        "candidats_valides": candidats_valides,
        "messages": [response]
    }
