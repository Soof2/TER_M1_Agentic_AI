"""
GraphState — Tableau noir (blackboard) du système multi-agents.

Chaque agent a ses champs dédiés en écriture. La séparation stricte
des droits d'écriture est ce qui donne au système ses propriétés SMA formelles.

Champs avec Annotated[..., operator.add] : reducers permettant l'écriture
parallèle par N instances (ex: A4 via Send()) sans conflit de merge.

Division A3 (depuis refactor) :
    requetes_recherche  → A3a (Stratège)    : requêtes LLM par source
    resultats_bruts     → A3b (Collecteur)  : hits DDG/GitHub avant filtrage
    profils_bruts       → A3c (Filtre)      : profils après scraping + filtrage
"""

from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages
import operator


class Candidat(TypedDict):
    """Profil brut d'un candidat collecté par A3c."""
    id: str
    nom: str
    source: str                # linkedin, github, indeed, web, malt
    profil_brut: str           # texte extrait du profil (scraping)
    url: Optional[str]


class CandidatScore(TypedDict):
    """Résultat d'évaluation d'un candidat par A4."""
    candidat_id: str
    nom: str
    score_global: float        # 0-100
    scores_detail: dict        # {hard_skills, soft_skills, experience, culture_fit}
    resume: str                # explication textuelle du score


class CandidatValide(TypedDict):
    """Candidat vérifié par A5."""
    candidat_id: str
    nom: str
    score_final: float
    statut: str                # "valide", "invalide", "douteux"
    remarques: str


class GraphState(TypedDict):
    """
    État partagé du graphe = blackboard SMA.

    Convention d'écriture (pipeline complet) :
        fiche_poste         → input entreprise
        profil_competences  → A2  (Analyste)
        requetes_recherche  → A3a (Stratège)         : dict de listes de requêtes
        resultats_bruts     → A3b (Collecteur)       : hits bruts DDG/GitHub API
        profils_bruts       → A3c (Filtre)           [reducer: append]
        profils_dedupliques → A6  (Déduplicateur)
        candidats_scores    → A4  (Évaluateur ×N)    [reducer: append]
        candidats_valides   → A5  (Vérificateur)
        messages_envoyes    → A7  (Recruteur)         [reducer: append]
        rapport_final       → A1  (Orchestrateur)
    """
    # Input — écrit par l'entreprise, lu par A1, A2
    fiche_poste: str

    # A2 écrit, lu par A3a, A4
    profil_competences: dict

    # A3a écrit, lu par A3b
    requetes_recherche: dict

    # A3b écrit, lu par A3c
    resultats_bruts: list[dict]

    # A3c écrit (reducer: append pour accumulation par lots)
    profils_bruts: Annotated[list[Candidat], operator.add]

    # A6 écrit, lu par A4(×N)
    profils_dedupliques: list[Candidat]

    # A4 écrit (reducer: append — N instances parallèles via Send)
    candidats_scores: Annotated[list[CandidatScore], operator.add]

    # A5 écrit, lu par A1, A7
    candidats_valides: list[CandidatValide]

    # A7 écrit (reducer: append)
    messages_envoyes: Annotated[list[dict], operator.add]

    # A1 écrit, lu par le recruteur humain
    rapport_final: str

    # Messages LLM pour trace/debug
    messages: Annotated[list, add_messages]
