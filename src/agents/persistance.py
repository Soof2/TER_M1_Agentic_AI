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
    """Stocke la fiche de poste courante + les candidats validés,
    reliés via un fiche_id stable. Le lien fiche↔candidat permet à A4
    de filtrer les runs précédents par pertinence de contexte."""
    m = get_metrics()
    m.debut("A8_persistance")

    candidats_valides = state.get("candidats_valides", [])
    profils_dedupliques = state.get("profils_dedupliques", [])
    fiche_poste = state.get("fiche_poste", "")

    if not candidats_valides:
        _log.info("Aucun candidat validé à persister.")
        m.fin("A8_persistance", n_persistes=0)
        return {}

    try:
        memoire = get_memoire()
    except Exception as exc:  # noqa: BLE001
        _log.warning("Mémoire RAG indisponible, persistance ignorée : %s", exc)
        m.fin("A8_persistance", n_persistes=0, rag_error=str(exc)[:200])
        return {}

    # Upsert de la fiche courante — renvoie un hash stable
    try:
        fiche_id = memoire.ajouter_fiche_poste(fiche_poste)
        if fiche_id:
            _log.info("Fiche de poste persistée (fiche_id=%s).", fiche_id)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Erreur persistance fiche RAG, persistance ignorée : %s", exc)
        m.fin("A8_persistance", n_persistes=0, rag_error=str(exc)[:200])
        return {}

    # Index profils bruts par ID pour récupérer le texte
    profils_idx = {p["id"]: p for p in profils_dedupliques}

    n_persistes = 0

    for candidat in candidats_valides:
        # Ne pas persister les candidats invalides (bruit détecté par A5)
        if candidat.get("statut") == "invalide":
            continue

        profil = profils_idx.get(candidat["candidat_id"], {})
        profil_brut = profil.get("profil_brut", f"Profil de {candidat['nom']}")
        source = profil.get("source", "inconnu")

        try:
            memoire.ajouter_candidat(
                candidat_id=candidat["candidat_id"],
                nom=candidat["nom"],
                profil_brut=profil_brut,
                score=candidat["score_final"],
                source=source,
                remarques=candidat.get("remarques", ""),
                fiche_id=fiche_id,
            )
            n_persistes += 1
        except Exception as exc:  # noqa: BLE001
            _log.warning("Erreur persistance candidat %s : %s", candidat.get("nom", "?"), exc)

    _log.info(
        "%d candidats persistés en base RAG (total : %d candidats, %d fiches).",
        n_persistes, memoire.compter(), memoire.compter_fiches(),
    )
    m.fin(
        "A8_persistance",
        n_persistes=n_persistes,
        total_base=memoire.compter(),
        total_fiches=memoire.compter_fiches(),
    )

    return {}
