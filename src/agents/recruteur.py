"""
A7 — Recruteur.

Rédige des messages personnalisés et les envoie aux meilleurs candidats.
Déclenché conditionnellement par A5 uniquement si le score dépasse le seuil.
Réactivité événementielle.
"""

import json
from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER, SCORE_SEUIL_CONTACT
from src.prompts import RECRUTEUR_SYSTEM


def recruteur_node(state: GraphState) -> dict:
    """Rédige des messages de contact pour les candidats validés au-dessus du seuil."""
    candidats_valides = state.get("candidats_valides", [])
    fiche_poste = state.get("fiche_poste", "")

    # Filtrer les candidats au-dessus du seuil de contact
    top_candidats = [
        c for c in candidats_valides
        if c["statut"] == "valide" and c["score_final"] >= SCORE_SEUIL_CONTACT
    ]

    print(f"\n[A7 Recruteur] {len(top_candidats)} candidats au-dessus du seuil de {SCORE_SEUIL_CONTACT}/100.", flush=True)

    if not top_candidats:
        print("[A7 Recruteur] Aucun candidat à contacter.", flush=True)
        return {"messages_envoyes": []}

    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0.7)

    candidats_info = json.dumps([
        {"candidat_id": c["candidat_id"], "nom": c["nom"],
         "score_final": c["score_final"], "remarques": c["remarques"]}
        for c in top_candidats
    ], ensure_ascii=False, indent=2)

    contact_msg = f"""Fiche de poste :
{fiche_poste}

Candidats validés à contacter :
{candidats_info}

Rédige un message de premier contact personnalisé pour chaque candidat."""

    messages = [
        SystemMessage(content=RECRUTEUR_SYSTEM),
        HumanMessage(content=contact_msg)
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # Extraire le JSON
    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        messages_contact = json.loads(content)
        if not isinstance(messages_contact, list):
            messages_contact = [messages_contact]
    except json.JSONDecodeError:
        messages_contact = [
            {
                "candidat_id": c["candidat_id"],
                "nom": c["nom"],
                "objet": f"Opportunité - {c['nom']}",
                "message": content[:500],
                "canal": "email"
            }
            for c in top_candidats
        ]

    print(f"[A7 Recruteur] {len(messages_contact)} messages de contact rédigés.", flush=True)
    for m in messages_contact:
        print(f"[A7 Recruteur]   -> {m.get('nom', '?')} via {m.get('canal', '?')}", flush=True)

    return {
        "messages_envoyes": messages_contact,
        "messages": [response]
    }
