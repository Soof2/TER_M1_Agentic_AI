"""
Tests — Memoire RAG (ChromaDB).

Verifie le stockage et la recherche vectorielle sans LLM.
Utilise un dossier temporaire pour ne pas polluer la base de production.
"""

import pytest
import tempfile
import shutil
from src.tools.rag import MemoireRAG


@pytest.fixture
def memoire(tmp_path):
    """Instance RAG isolee dans un dossier temporaire."""
    m = MemoireRAG(persist_dir=str(tmp_path / "chromadb_test"))
    yield m
    shutil.rmtree(str(tmp_path), ignore_errors=True)


class TestMemoireRAG:
    def test_base_vide_au_demarrage(self, memoire):
        assert memoire.compter() == 0

    def test_ajouter_candidat(self, memoire):
        memoire.ajouter_candidat(
            candidat_id="c1",
            nom="Alice Dupont",
            profil_brut="Développeuse Python 7 ans, ML, NLP, Paris",
            score=85.0,
            source="linkedin",
        )
        assert memoire.compter() == 1

    def test_ajouter_plusieurs_candidats(self, memoire):
        for i in range(3):
            memoire.ajouter_candidat(
                candidat_id=f"c{i}",
                nom=f"Candidat {i}",
                profil_brut=f"Profil développeur Python {i}",
                score=float(60 + i * 10),
                source="web",
            )
        assert memoire.compter() == 3

    def test_upsert_meme_id(self, memoire):
        """Ajouter deux fois le meme ID ne cree pas de doublon."""
        memoire.ajouter_candidat("c1", "Alice", "Python dev", 70.0, "github")
        memoire.ajouter_candidat("c1", "Alice", "Python dev senior", 82.0, "github")
        assert memoire.compter() == 1

    def test_recherche_similaire(self, memoire):
        memoire.ajouter_candidat(
            "c1", "Alice Dupont",
            "Développeuse Python senior, machine learning, NLP, 7 ans",
            85.0, "linkedin",
        )
        resultats = memoire.rechercher_similaires(
            "Python developer machine learning experience", n_results=1
        )
        assert len(resultats) == 1
        assert resultats[0]["nom"] == "Alice Dupont"
        assert resultats[0]["score"] == 85.0
        assert 0.0 <= resultats[0]["similarite"] <= 1.0

    def test_recherche_base_vide(self, memoire):
        """Recherche dans base vide retourne liste vide sans erreur."""
        resultats = memoire.rechercher_similaires("Python developer", n_results=3)
        assert resultats == []

    def test_recherche_n_results_respecte(self, memoire):
        for i in range(5):
            memoire.ajouter_candidat(f"c{i}", f"Dev {i}", f"Python developer {i}", 60.0 + i, "web")
        resultats = memoire.rechercher_similaires("Python developer", n_results=2)
        assert len(resultats) <= 2

    def test_similarite_coherente(self, memoire):
        """Un profil identique doit avoir une similarite proche de 1."""
        profil = "Expert Python machine learning deep learning PyTorch Paris"
        memoire.ajouter_candidat("c1", "Alice", profil, 90.0, "github")
        resultats = memoire.rechercher_similaires(profil, n_results=1)
        assert resultats[0]["similarite"] > 0.9
