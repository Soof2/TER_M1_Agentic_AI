"""
A1 — Orchestrateur (Superviseur).

Reçoit la fiche de poste, coordonne tous les agents, et produit le
rapport final. Implémenté via le pattern Supervisor de LangGraph.
Topologie étoile, délégation formelle.

Ce module contient aussi le nœud de rapport final et le nœud de
réduction des scores (fan-in après Send).
"""

from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER
from src.prompts import ORCHESTRATEUR_RAPPORT_SYSTEM
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A1_orchestrateur")


def orchestrateur_node(state: GraphState) -> dict:
    """Point d'entrée : reçoit la fiche de poste et initialise le pipeline."""
    _log.info("Réception de la fiche de poste : %s...", state['fiche_poste'][:80])
    _log.info("Démarrage du pipeline multi-agents.")
    return {
        "messages": [
            HumanMessage(content=f"[Orchestrateur] Lancement du recrutement pour :\n{state['fiche_poste']}")
        ]
    }


def reduce_scores_node(state: GraphState) -> dict:
    """Nœud de réduction : agrège les scores des N évaluateurs parallèles.

    Les scores sont déjà agrégés par le reducer operator.add sur
    candidats_scores. Ce nœud sert de point de synchronisation (fan-in)
    avant de passer au vérificateur.
    """
    log = get_logger("reduce")
    n_scores = len(state.get("candidats_scores", []))
    log.info("Fan-in : %d scores agrégés depuis les évaluateurs parallèles.", n_scores)
    return {
        "messages": [
            HumanMessage(content=f"[Réduction] {n_scores} candidats évalués, passage à la vérification.")
        ]
    }


def rapport_node(state: GraphState) -> dict:
    """Produit le rapport final en agrégeant les résultats de tous les agents."""
    _log.info("Génération du rapport final...")
    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0.3)

    # Assembler les données pour le rapport
    profil = state.get("profil_competences", {})
    n_bruts = len(state.get("profils_bruts", []))
    n_dedup = len(state.get("profils_dedupliques", []))
    candidats_valides = state.get("candidats_valides", [])
    messages_envoyes = state.get("messages_envoyes", [])

    candidats_summary = ""
    for c in sorted(candidats_valides, key=lambda x: x["score_final"], reverse=True):
        candidats_summary += (
            f"- {c['nom']} | Score: {c['score_final']} | "
            f"Statut: {c['statut']} | {c['remarques']}\n"
        )

    # Exporter les métriques d'observabilité
    m = get_metrics()
    m.noter(
        "pipeline",
        n_profils_bruts=n_bruts,
        n_profils_dedup=n_dedup,
        n_scores=len(state.get("candidats_scores", [])),
        n_valides=len(candidats_valides),
        n_messages=len(messages_envoyes),
    )
    metriques_export = m.exporter()
    metriques_resume = m.resume_texte()

    rapport_msg = f"""Données du processus de recrutement :

FICHE DE POSTE :
{state.get('fiche_poste', 'N/A')}

PROFIL DE COMPÉTENCES EXTRAIT :
{profil}

STATISTIQUES :
- Profils trouvés : {n_bruts}
- Profils après déduplication : {n_dedup}
- Candidats évalués : {len(state.get('candidats_scores', []))}
- Candidats validés : {len(candidats_valides)}
- Messages envoyés : {len(messages_envoyes)}

CLASSEMENT DES CANDIDATS :
{candidats_summary if candidats_summary else 'Aucun candidat validé'}

MESSAGES ENVOYÉS :
{len(messages_envoyes)} message(s) de contact

MÉTRIQUES D'EXÉCUTION :
{metriques_resume}

Produis le rapport final structuré."""

    messages = [
        SystemMessage(content=ORCHESTRATEUR_RAPPORT_SYSTEM),
        HumanMessage(content=rapport_msg)
    ]

    response = llm.invoke(messages)
    _log.info("Rapport final généré.")

    return {
        "rapport_final": response.content,
        "messages": [response]
    }
