"""
A5 — Vérificateur.

Vérifie la cohérence des profils scorés par A4. Validation pair-à-pair
formelle : A4 produit, A5 contrôle indépendamment. La séparation des
sous-champs (candidats_scores / candidats_valides) impose cette contrainte.
"""

import json
from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState, CandidatValide
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER
from src.prompts import VERIFICATEUR_SYSTEM


def verificateur_node(state: GraphState) -> dict:
    """Vérifie et valide les scores des candidats."""
    candidats_scores = state.get("candidats_scores", [])
    print(f"\n[A5 Vérificateur] Vérification de {len(candidats_scores)} candidats scorés...", flush=True)

    if not candidats_scores:
        print("[A5 Vérificateur] Aucun candidat à vérifier.", flush=True)
        return {"candidats_valides": []}

    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    # Construire un index des profils bruts par ID pour croisement
    profils_par_id = {}
    for p in state.get("profils_dedupliques", []):
        profils_par_id[p["id"]] = p

    # Préparer les données complètes : scores + profils bruts
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

Candidats :

{json.dumps(candidats_info, ensure_ascii=False, indent=2)}

Pour chaque candidat, vérifie :
1. Les incohérences entre le profil brut et le score attribué
2. Les dates suspectes (expérience irréaliste, chevauchements)
3. Les CV gonflés (trop de compétences sans preuves, titres vagues)
4. Les profils qui ne sont PAS des candidats (offres d'emploi, pages d'entreprise, agrégateurs)

Invalide les profils qui ne sont clairement pas des candidats individuels.
Marque comme "douteux" ceux avec des incohérences.
Ajuste le score_final si nécessaire."""

    messages = [
        SystemMessage(content=VERIFICATEUR_SYSTEM),
        HumanMessage(content=verif_msg)
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # Extraire le JSON
    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        validations = json.loads(content)
        if not isinstance(validations, list):
            validations = [validations]
    except json.JSONDecodeError:
        # Fallback : valider tous les candidats avec leur score original
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
    for v in validations:
        candidats_valides.append(CandidatValide(
            candidat_id=v.get("candidat_id", ""),
            nom=v.get("nom", ""),
            score_final=float(v.get("score_final", 0)),
            statut=v.get("statut", "douteux"),
            remarques=v.get("remarques", "")
        ))

    n_valides = sum(1 for c in candidats_valides if c["statut"] == "valide")
    n_invalides = sum(1 for c in candidats_valides if c["statut"] == "invalide")
    n_douteux = sum(1 for c in candidats_valides if c["statut"] == "douteux")
    print(f"[A5 Vérificateur] Résultat : {n_valides} valides, {n_douteux} douteux, {n_invalides} invalides.", flush=True)
    for c in sorted(candidats_valides, key=lambda x: x["score_final"], reverse=True):
        print(f"[A5 Vérificateur]   - {c['nom']} | {c['score_final']}/100 | {c['statut']}", flush=True)

    return {
        "candidats_valides": candidats_valides,
        "messages": [response]
    }
