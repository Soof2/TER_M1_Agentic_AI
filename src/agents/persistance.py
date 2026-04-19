"""
A8 — Persistance RAG.

Nœud terminal du pipeline : stocke les candidats validés par A5
dans la base vectorielle ChromaDB pour enrichir les runs futurs.

Responsabilité unique : écriture en base, pas de LLM, pas de filtrage.
Ce nœud est transparent (ne modifie pas l'état du graphe).

Pattern : mémoire contextuelle persistante entre sessions.
Les runs suivants bénéficient du contexte des évaluations passées
via le RAG intégré dans A4 (Évaluateur).
"""

from src.state import GraphState
from src.tools.rag import get_memoire
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A8_persistance")


def persistance_node(state: GraphState) -> dict:
    """Stocke les candidats validés dans la mémoire vectorielle."""
    m = get_metrics()
    m.debut("A8_persistance")

    candidats_valides = state.get("candidats_valides", [])
    profils_dedupliques = state.get("profils_dedupliques", [])

    if not candidats_valides:
        _log.info("Aucun candidat validé à persister.")
        m.fin("A8_persistance", n_persistes=0)
        return {}

    # Index profils bruts par ID pour récupérer le texte
    profils_idx = {p["id"]: p for p in profils_dedupliques}

    memoire = get_memoire()
    n_persistes = 0

    for candidat in candidats_valides:
        # Ne pas persister les candidats invalides (bruit détecté par A5)
        if candidat.get("statut") == "invalide":
            continue

        profil = profils_idx.get(candidat["candidat_id"], {})
        profil_brut = profil.get("profil_brut", f"Profil de {candidat['nom']}")
        source = profil.get("source", "inconnu")

        memoire.ajouter_candidat(
            candidat_id=candidat["candidat_id"],
            nom=candidat["nom"],
            profil_brut=profil_brut,
            score=candidat["score_final"],
            source=source,
            remarques=candidat.get("remarques", ""),
        )
        n_persistes += 1

    _log.info(
        "%d candidats persistés en base RAG (total base : %d).",
        n_persistes, memoire.compter(),
    )
    m.fin("A8_persistance", n_persistes=n_persistes, total_base=memoire.compter())

    return {}
