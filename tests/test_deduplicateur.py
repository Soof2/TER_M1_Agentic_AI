"""
Tests — A6 Deduplicateur.

Verifie la logique de deduplication sans LLM ni reseau.
"""

from src.agents.deduplicateur import _are_duplicates, deduplicateur_node
from src.state import Candidat


def _candidat(id="a1", nom="Alice Dupont", source="linkedin",
               profil_brut="dev python", url=None) -> Candidat:
    return Candidat(id=id, nom=nom, source=source, profil_brut=profil_brut, url=url)


class TestAreDuplicates:
    def test_meme_url(self):
        p1 = _candidat(url="https://linkedin.com/in/alice")
        p2 = _candidat(nom="Alice D.", url="https://linkedin.com/in/alice")
        assert _are_duplicates(p1, p2) is True

    def test_meme_nom_exact(self):
        p1 = _candidat(nom="Alice Dupont")
        p2 = _candidat(nom="Alice Dupont")
        assert _are_duplicates(p1, p2) is True

    def test_nom_similaire(self):
        p1 = _candidat(nom="Alice Dupont")
        p2 = _candidat(nom="Alice Dupon")   # typo, ratio ~0.96
        assert _are_duplicates(p1, p2) is True

    def test_noms_differents(self):
        p1 = _candidat(nom="Alice Dupont")
        p2 = _candidat(nom="Bob Martin")
        assert _are_duplicates(p1, p2) is False

    def test_urls_differentes_noms_differents(self):
        """Noms differents + URLs differentes -> pas doublons."""
        p1 = _candidat(nom="Alice Dupont", url="https://linkedin.com/in/alice")
        p2 = _candidat(nom="Bob Martin",   url="https://linkedin.com/in/bob")
        assert _are_duplicates(p1, p2) is False

    def test_url_none_pas_doublon_par_url(self):
        p1 = _candidat(nom="Alice Dupont", url=None)
        p2 = _candidat(nom="Bob Martin", url=None)
        assert _are_duplicates(p1, p2) is False


class TestDeduplicateurNode:
    def test_aucun_profil(self):
        result = deduplicateur_node({"profils_bruts": []})
        assert result["profils_dedupliques"] == []

    def test_un_seul_profil(self):
        profils = [_candidat()]
        result = deduplicateur_node({"profils_bruts": profils})
        assert len(result["profils_dedupliques"]) == 1

    def test_deux_profils_differents(self):
        profils = [
            _candidat(id="a1", nom="Alice Dupont"),
            _candidat(id="b1", nom="Bob Martin"),
        ]
        result = deduplicateur_node({"profils_bruts": profils})
        assert len(result["profils_dedupliques"]) == 2

    def test_doublon_fusionne(self):
        profils = [
            _candidat(id="a1", nom="Alice Dupont", source="linkedin", url="https://linkedin.com/in/alice"),
            _candidat(id="a2", nom="Alice Dupont", source="github",   url="https://linkedin.com/in/alice"),
        ]
        result = deduplicateur_node({"profils_bruts": profils})
        assert len(result["profils_dedupliques"]) == 1
        # Les deux sources sont fusionnees
        merged = result["profils_dedupliques"][0]
        assert "linkedin" in merged["source"]
        assert "github" in merged["source"]

    def test_trois_profils_un_doublon(self):
        profils = [
            _candidat(id="a1", nom="Alice Dupont"),
            _candidat(id="a2", nom="Alice Dupont"),  # doublon
            _candidat(id="b1", nom="Bob Martin"),
        ]
        result = deduplicateur_node({"profils_bruts": profils})
        assert len(result["profils_dedupliques"]) == 2
