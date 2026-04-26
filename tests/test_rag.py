"""
Tests — Memoire RAG (ChromaDB).

Verifie le stockage et la recherche vectorielle sans LLM.
Utilise un dossier temporaire pour ne pas polluer la base de production.
"""

import pytest
import tempfile
import shutil
from src.tools.rag import MemoireRAG, hash_fiche


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


class TestCalibrationParFiche:
    """Vérifie le filtrage du RAG par similarité fiche↔fiche."""

    def test_hash_fiche_stable(self):
        h1 = hash_fiche("Développeur Python senior, 5 ans, Paris")
        h2 = hash_fiche("  Développeur  Python  senior,  5 ans,   Paris  ")
        assert h1 == h2, "Le hash doit ignorer les espaces multiples"

    def test_hash_fiche_differentes(self):
        h1 = hash_fiche("Dev Python senior Paris")
        h2 = hash_fiche("Dev Java junior Lyon")
        assert h1 != h2

    def test_ajouter_fiche_retourne_id(self, memoire):
        fiche_id = memoire.ajouter_fiche_poste("Dev Python senior Paris")
        assert fiche_id
        assert memoire.compter_fiches() == 1

    def test_fiche_vide_retourne_id_vide(self, memoire):
        assert memoire.ajouter_fiche_poste("") == ""
        assert memoire.compter_fiches() == 0

    def test_rag_vide_si_aucune_fiche_comparable(self, memoire):
        """Si aucune fiche stockée n'est proche de la fiche courante, on
        ne doit rien renvoyer plutôt que d'injecter un contexte biaisé."""
        fid = memoire.ajouter_fiche_poste("Dev Python senior 5 ans Paris ML")
        memoire.ajouter_candidat(
            "c1", "Alice", "Python ML Paris", 85.0, "github", fiche_id=fid,
        )
        # Fiche courante totalement différente
        resultats = memoire.rechercher_similaires(
            "Python ML",
            fiche_poste="Chef de projet marketing digital Lyon B2B",
            n_results=3,
            seuil_fiche=0.5,
        )
        assert resultats == []

    def test_rag_renvoie_candidats_pour_fiche_similaire(self, memoire):
        """Fiche courante quasi-identique → les candidats rattachés remontent."""
        fiche = "Développeur Python senior machine learning Paris 5 ans"
        fid = memoire.ajouter_fiche_poste(fiche)
        memoire.ajouter_candidat(
            "c1", "Alice",
            "Développeuse Python 7 ans ML NLP Paris",
            82.0, "github", fiche_id=fid,
        )
        # Fiche courante très similaire (même compétences, même ville)
        resultats = memoire.rechercher_similaires(
            "Python ML Paris",
            fiche_poste="Recherche développeur Python senior ML Paris",
            n_results=3,
            seuil_fiche=0.4,
        )
        assert len(resultats) == 1
        assert resultats[0]["nom"] == "Alice"

    def test_rag_isole_par_fiche(self, memoire):
        """Deux fiches très différentes en base : une fiche courante proche
        de la première ne doit PAS remonter les candidats de la seconde."""
        fid_py = memoire.ajouter_fiche_poste("Dev Python ML Paris senior")
        fid_mk = memoire.ajouter_fiche_poste("Chef projet marketing digital B2B Lyon")
        memoire.ajouter_candidat(
            "c_py", "Alice", "Python ML Paris", 85.0, "github", fiche_id=fid_py,
        )
        memoire.ajouter_candidat(
            "c_mk", "Bob", "Marketing digital B2B Lyon", 80.0, "linkedin", fiche_id=fid_mk,
        )
        resultats = memoire.rechercher_similaires(
            "Python ML",
            fiche_poste="Développeur Python senior Paris data science",
            n_results=5,
            seuil_fiche=0.4,
        )
        noms = [r["nom"] for r in resultats]
        assert "Alice" in noms
        assert "Bob" not in noms

    def test_legacy_sans_fiche(self, memoire):
        """Appel sans fiche_poste : comportement global historique (aucun filtrage)."""
        fid = memoire.ajouter_fiche_poste("Dev Python Paris")
        memoire.ajouter_candidat(
            "c1", "Alice", "Python dev Paris", 85.0, "github", fiche_id=fid,
        )
        resultats = memoire.rechercher_similaires("Python developer", n_results=3)
        assert len(resultats) == 1
