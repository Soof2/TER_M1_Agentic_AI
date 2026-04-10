"""
Construction du graphe LangGraph — cœur du SMA de recrutement.

Architecture :
    START → orchestrateur → analyste → chercheur → deduplicateur
    → [Send() × N] evaluateur → reduce_scores → verificateur
    → (conditionnel) recruteur | rapport → END

Patterns SMA implémentés :
    - Superviseur (A1 coordonne via le flux du graphe)
    - Blackboard (GraphState partagé avec droits d'écriture séparés)
    - Send/Map-Reduce (A4 × N instances parallèles)
    - Validation pair-à-pair (A4 produit → A5 contrôle)
    - Routage conditionnel (score → A7 / rapport / fin)
    - Human-in-the-loop (interrupt_before sur A7)
"""

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver

from src.state import GraphState
from src.config import SCORE_SEUIL_CONTACT, SCORE_SEUIL_HUMAIN
from src.agents.orchestrateur import orchestrateur_node, reduce_scores_node, rapport_node
from src.agents.analyste import analyste_node
from src.agents.chercheur import chercheur_node
from src.agents.deduplicateur import deduplicateur_node
from src.agents.evaluateur import evaluateur_node
from src.agents.verificateur import verificateur_node
from src.agents.recruteur import recruteur_node


def route_to_evaluateurs(state: GraphState) -> list[Send]:
    """Fan-out : envoie chaque profil dédupliqué à une instance d'évaluateur.

    Utilise le pattern Send() de LangGraph pour créer N instances
    parallèles d'A4. Chaque instance reçoit un state partiel avec
    un seul candidat + le profil de compétences.
    """
    profils = state.get("profils_dedupliques", [])
    if not profils:
        print("\n[Graph] Aucun profil à évaluer, passage direct à la réduction.", flush=True)
        return [Send("reduce_scores", {})]

    print(f"\n[Graph] Fan-out : envoi de {len(profils)} profils vers {len(profils)} évaluateurs parallèles (Send).", flush=True)
    return [
        Send("evaluateur", {
            "candidat": candidat,
            "profil_competences": state["profil_competences"]
        })
        for candidat in profils
    ]


def route_apres_verification(state: GraphState) -> str:
    """Routage conditionnel après vérification par A5.

    - score >= 75 → recruteur (A7 contacte les candidats)
    - score 50-75 → rapport (décision humaine requise)
    - score < 50  → rapport (aucun candidat viable)
    """
    candidats_valides = state.get("candidats_valides", [])

    if not candidats_valides:
        print("\n[Graph] Routage : aucun candidat validé -> rapport.", flush=True)
        return "rapport"

    meilleur_score = max(c["score_final"] for c in candidats_valides)

    if meilleur_score >= SCORE_SEUIL_CONTACT:
        print(f"\n[Graph] Routage : meilleur score {meilleur_score} >= {SCORE_SEUIL_CONTACT} -> A7 Recruteur.", flush=True)
        return "recruteur"
    else:
        print(f"\n[Graph] Routage : meilleur score {meilleur_score} < {SCORE_SEUIL_CONTACT} -> rapport (pas de contact).", flush=True)
        return "rapport"


def build_graph(with_interrupt: bool = True) -> StateGraph:
    """Construit et compile le graphe du SMA de recrutement.

    Args:
        with_interrupt: Si True, ajoute interrupt_before sur le nœud
                       recruteur pour le human-in-the-loop.

    Returns:
        Le graphe compilé prêt à être invoqué.
    """
    graph = StateGraph(GraphState)

    # --- Ajout des nœuds ---
    graph.add_node("orchestrateur", orchestrateur_node)
    graph.add_node("analyste", analyste_node)
    graph.add_node("chercheur", chercheur_node)
    graph.add_node("deduplicateur", deduplicateur_node)
    graph.add_node("evaluateur", evaluateur_node)
    graph.add_node("reduce_scores", reduce_scores_node)
    graph.add_node("verificateur", verificateur_node)
    graph.add_node("recruteur", recruteur_node)
    graph.add_node("rapport", rapport_node)

    # --- Arêtes séquentielles (pipeline principal) ---
    graph.add_edge(START, "orchestrateur")
    graph.add_edge("orchestrateur", "analyste")
    graph.add_edge("analyste", "chercheur")
    graph.add_edge("chercheur", "deduplicateur")

    # --- Fan-out : déduplicateur → N × évaluateur via Send() ---
    graph.add_conditional_edges(
        "deduplicateur",
        route_to_evaluateurs,
        ["evaluateur", "reduce_scores"]
    )

    # --- Fan-in : évaluateur → reduce_scores (synchronisation) ---
    graph.add_edge("evaluateur", "reduce_scores")

    # --- Reduce → vérificateur ---
    graph.add_edge("reduce_scores", "verificateur")

    # --- Routage conditionnel après vérification ---
    graph.add_conditional_edges(
        "verificateur",
        route_apres_verification,
        {
            "recruteur": "recruteur",
            "rapport": "rapport"
        }
    )

    # --- Recruteur → rapport → fin ---
    graph.add_edge("recruteur", "rapport")
    graph.add_edge("rapport", END)

    # --- Compilation avec checkpointer ---
    memory = MemorySaver()

    compile_kwargs = {"checkpointer": memory}
    if with_interrupt:
        compile_kwargs["interrupt_before"] = ["recruteur"]

    app = graph.compile(**compile_kwargs)
    return app
