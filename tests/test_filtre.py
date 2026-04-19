"""
Tests — A3c Filtre anti-bruit.

Verifie les fonctions de detection de bruit sans LLM ni reseau.
"""

import pytest
from src.agents.chercheur_filtre import _is_noise_url, _is_noise_text, filtre_node


class TestIsNoiseUrl:
    def test_indeed_bloque(self):
        assert _is_noise_url("https://fr.indeed.com/jobs?q=python") is True

    def test_glassdoor_bloque(self):
        assert _is_noise_url("https://www.glassdoor.fr/Emploi/python.htm") is True

    def test_welcometothejungle_bloque(self):
        assert _is_noise_url("https://www.welcometothejungle.com/fr/jobs/python") is True

    def test_linkedin_autorise(self):
        assert _is_noise_url("https://www.linkedin.com/in/alice-dupont") is False

    def test_github_autorise(self):
        assert _is_noise_url("https://github.com/alice-dev") is False

    def test_malt_autorise(self):
        assert _is_noise_url("https://www.malt.fr/profile/alicedupont") is False

    def test_url_vide(self):
        assert _is_noise_url("") is False

    def test_url_none_like(self):
        assert _is_noise_url(None) is False  # type: ignore


class TestIsNoiseText:
    def test_offre_emploi_detectee(self):
        assert _is_noise_text("Nous recherchons un développeur Python pour rejoindre notre équipe") is True

    def test_postuler_detecte(self):
        assert _is_noise_text("Cliquez ici pour postuler à cette offre") is True

    def test_cdi_a_pourvoir_detecte(self):
        assert _is_noise_text("CDI à pourvoir immédiatement, télétravail partiel") is True

    def test_profil_candidat_autorise(self):
        assert _is_noise_text("Alice Dupont, développeuse Python 7 ans, spécialiste ML") is False

    def test_github_profile_autorise(self):
        assert _is_noise_text("Bio: Python developer | Location: Paris | Followers: 120") is False

    def test_texte_vide(self):
        assert _is_noise_text("") is False

    def test_insensible_casse(self):
        assert _is_noise_text("NOUS RECRUTONS un expert data") is True


class TestFiltreNode:
    def test_filtre_vide(self):
        """Filtre sans hits retourne liste vide."""
        resultat = filtre_node({"resultats_bruts": []})
        assert resultat["profils_bruts"] == []

    def test_filtre_eliMine_indeed(self):
        """Les URLs Indeed sont eliminées avant scraping."""
        hits = [
            {"title": "Python dev", "url": "https://fr.indeed.com/job", "body": "offre", "source": "indeed"},
            {"title": "Alice Dev",  "url": "https://github.com/alice", "body": "Python developer", "source": "github"},
        ]
        # On mocke extraire_page_web_raw pour eviter le reseau
        import unittest.mock as mock
        with mock.patch("src.agents.chercheur_filtre.extraire_page_web_raw",
                        return_value="Alice Dupont, Python developer, 5 years experience"):
            resultat = filtre_node({"resultats_bruts": hits})

        profils = resultat["profils_bruts"]
        urls = [p["url"] for p in profils]
        assert "https://fr.indeed.com/job" not in urls
        assert "https://github.com/alice" in urls

    def test_filtre_eliMine_bruit_texte(self):
        """Les pages contenant des mots-cles d'offres sont eliminées."""
        hits = [
            {
                "title": "Offre emploi",
                "url": "https://example.com/job",
                "body": "nous recrutons un developpeur",
                "source": "web",
            }
        ]
        resultat = filtre_node({"resultats_bruts": hits})
        assert len(resultat["profils_bruts"]) == 0
