"""
Tests — Structure du graphe et routage conditionnel.

Verifie la topologie du graphe et la logique de routage sans LLM.
"""

import pytest
from src.graph import build_graph, route_apres_verification
from src.state import CandidatValide


def _valide(nom="Alice", score=80.0, statut="valide") -> CandidatValide:
    return CandidatValide(
        candidat_id="x1", nom=nom,
        score_final=score, statut=statut, remarques=""
    )


class TestStructureGraphe:
    @pytest.fixture(scope="class")
    def app(self):
        return build_graph(with_interrupt=False)

    def test_noeuds_presents(self, app):
        noeuds = set(app.get_graph().nodes.keys())
        attendus = {
            "orchestrateur", "analyste",
            "chercheur_stratege", "chercheur_collecteur", "chercheur_filtre",
            "deduplicateur", "evaluateur", "reduce_scores",
            "verificateur", "reduce_validations", "recruteur", "rapport", "persistance",
        }
        assert attendus.issubset(noeuds)

    def test_noeud_persistance_present(self, app):
        noeuds = set(app.get_graph().nodes.keys())
        assert "persistance" in noeuds

    def test_noeuds_au_total(self, app):
        # __start__ + 13 nœuds métier (dont injection_rag) + persistance + __end__ = 16
        assert len(app.get_graph().nodes) == 16

    def test_aretes_pipeline_a3(self, app):
        """A3a -> A3b -> A3c -> deduplicateur."""
        edges = {(e[0], e[1]) for e in app.get_graph().edges}
        assert ("chercheur_stratege", "chercheur_collecteur") in edges
        assert ("chercheur_collecteur", "chercheur_filtre") in edges
        assert ("chercheur_filtre", "deduplicateur") in edges

    def test_arete_rapport_persistance(self, app):
        edges = {(e[0], e[1]) for e in app.get_graph().edges}
        assert ("rapport", "persistance") in edges

    def test_arete_verificateur_reduce_validations(self, app):
        edges = {(e[0], e[1]) for e in app.get_graph().edges}
        assert ("verificateur", "reduce_validations") in edges

    def test_interrupt_before_recruteur(self):
        app_interrupt = build_graph(with_interrupt=True)
        # Pas d'assertion directe sur le config LangGraph, on verifie juste la compilation
        assert app_interrupt is not None


class TestRoutageConditionnel:
    def test_score_eleve_route_recruteur(self):
        state = {"candidats_valides": [_valide(score=80.0)]}
        assert route_apres_verification(state) == "recruteur"

    def test_score_exactement_75_route_recruteur(self):
        state = {"candidats_valides": [_valide(score=75.0)]}
        assert route_apres_verification(state) == "recruteur"

    def test_score_viable_route_recruteur_relatif(self):
        """Score entre 40 et 75 -> recruteur (mode relatif top-3)."""
        state = {"candidats_valides": [_valide(score=60.0)]}
        assert route_apres_verification(state) == "recruteur"

    def test_score_sous_viable_route_rapport(self):
        """Score < 40 -> rapport, aucun viable."""
        state = {"candidats_valides": [_valide(score=30.0)]}
        assert route_apres_verification(state) == "rapport"

    def test_aucun_candidat_route_rapport(self):
        state = {"candidats_valides": []}
        assert route_apres_verification(state) == "rapport"

    def test_meilleur_score_determine_route(self):
        """Avec plusieurs candidats, c'est le meilleur score qui compte."""
        state = {"candidats_valides": [
            _valide(score=30.0),
            _valide(score=80.0),   # celui-ci depasse le seuil
            _valide(score=45.0),
        ]}
        assert route_apres_verification(state) == "recruteur"

    def test_tous_sous_seuil_mais_viables(self):
        """Tous sous 75 mais au-dessus de 40 -> recruteur relatif."""
        state = {"candidats_valides": [
            _valide(score=68.0),
            _valide(score=55.0),
        ]}
        assert route_apres_verification(state) == "recruteur"

    def test_tous_invalides_score_zero(self):
        """Tous invalides avec score 0 -> rapport."""
        state = {"candidats_valides": [
            _valide(score=0.0, statut="invalide"),
            _valide(score=5.0, statut="invalide"),
        ]}
        assert route_apres_verification(state) == "rapport"

    def test_douteux_score_eleve_ne_route_pas_recruteur(self):
        """Un profil douteux ne doit jamais etre contacte automatiquement."""
        state = {"candidats_valides": [
            _valide(score=90.0, statut="douteux"),
        ]}
        assert route_apres_verification(state) == "rapport"

    def test_seuls_les_valides_comptent_pour_le_routage(self):
        state = {"candidats_valides": [
            _valide(score=95.0, statut="douteux"),
            _valide(score=60.0, statut="valide"),
        ]}
        assert route_apres_verification(state) == "recruteur"
