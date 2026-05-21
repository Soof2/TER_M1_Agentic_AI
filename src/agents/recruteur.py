"""
A7 — Recruteur.

Rédige des messages personnalisés et les envoie aux meilleurs candidats.
Déclenché conditionnellement par A5 uniquement si le score dépasse le seuil.
Réactivité événementielle.
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState
from src.config import get_llm, SCORE_SEUIL_CONTACT, SCORE_SEUIL_VIABLE, TOP_N_RELATIF
from src.prompts import RECRUTEUR_SYSTEM
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A7_recruteur")


def recruteur_node(state: GraphState) -> dict:
    """Rédige des messages de contact pour les candidats validés.

    Mode absolu  : candidats avec score >= SCORE_SEUIL_CONTACT.
    Mode relatif : si aucun n'atteint le seuil, prend les TOP_N_RELATIF
                   meilleurs avec score >= SCORE_SEUIL_VIABLE.
    """
    m = get_metrics()
    m.debut("A7_recruteur")
    candidats_valides = [
        c for c in state.get("candidats_valides", [])
        if c.get("statut") == "valide"
    ]
    fiche_poste = state.get("fiche_poste", "")

    # Mode absolu : candidats clairement au-dessus du seuil
    top_candidats = [
        c for c in candidats_valides
        if c["score_final"] >= SCORE_SEUIL_CONTACT
    ]

    mode = "absolu"
    if not top_candidats:
        # Mode relatif : top-N parmi les viables
        viables = sorted(
            [c for c in candidats_valides if c["score_final"] >= SCORE_SEUIL_VIABLE],
            key=lambda x: x["score_final"],
            reverse=True
        )
        top_candidats = viables[:TOP_N_RELATIF]
        mode = "relatif"

    _log.info(
        "%d candidat(s) sélectionné(s) [mode %s, seuil %s].",
        len(top_candidats), mode,
        SCORE_SEUIL_CONTACT if mode == "absolu" else f">={SCORE_SEUIL_VIABLE} top-{TOP_N_RELATIF}"
    )

    if not top_candidats:
        _log.warning("Aucun candidat à contacter.")
        return {"messages_envoyes": []}

    llm = get_llm(temperature=0.7)

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

    _log.info("%d messages de contact rédigés.", len(messages_contact))
    for msg in messages_contact:
        _log.info("  -> %s via %s", msg.get('nom', '?'), msg.get('canal', '?'))
    m.fin("A7_recruteur", n_messages=len(messages_contact), mode=mode)

    return {
        "messages_envoyes": messages_contact,
        "messages": [response]
    }
