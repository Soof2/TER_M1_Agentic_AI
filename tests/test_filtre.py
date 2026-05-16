"""
Tests — A3c Filtre anti-bruit.

Verifie les fonctions de detection de bruit sans LLM ni reseau.
"""

import pytest
from src.agents.chercheur_filtre import (
    _is_aggregated_profile,
    _is_noise_url,
    _is_noise_text,
    _triage_priority,
    filtre_node,
)


class TestIsNoiseUrl:
    def test_indeed_pas_bloque_par_domaine(self):
        assert _is_noise_url("https://fr.indeed.com/viewjob?jk=123") is False

    def test_glassdoor_pas_bloque_par_domaine(self):
        assert _is_noise_url("https://www.glassdoor.fr/Profile/alice") is False

    def test_welcometothejungle_pas_bloque_par_domaine(self):
        assert _is_noise_url("https://www.welcometothejungle.com/fr/companies/acme") is False

    def test_search_page_bloquee_generiquement(self):
        assert _is_noise_url("https://www.simplyhired.fr/search?q=developpeur") is True

    def test_poste_pas_bloque_par_chemin(self):
        assert _is_noise_url("https://umontpellier.nous-recrutons.fr/poste/python") is False

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

    def test_recherche_emploi_detectee(self):
        assert _is_noise_text("les recherches suivantes : developpeur junior Montpellier") is True


class TestAggregatedProfile:
    def test_linkedin_resultat_agrege_detecte(self):
        title = (
            "Elias Ouissi - Développeur Web Full-Stack | LinkedIn"
            "Thaja-Laure KINKING - Diplômée ..."
            "Abdou Aziz Junior NIASSY - Montpellier ..."
        )
        assert _is_aggregated_profile(title, "") is True


class TestTriagePriority:
    def test_linkedin_profile_prioritaire(self):
        hit = {"url": "https://www.linkedin.com/in/alice", "title": "Alice", "body": ""}
        assert _triage_priority(hit, "Python developer") == 0

    def test_page_offre_depriorisee_mais_pas_bloquee(self):
        hit = {"url": "https://example.com/poste/python", "title": "Offre", "body": "Nous recrutons"}
        assert _triage_priority(hit, "description du poste") == 50


class TestFiltreNode:
    def test_filtre_vide(self):
        """Filtre sans hits retourne liste vide."""
        resultat = filtre_node({"resultats_bruts": []})
        assert resultat["profils_bruts"] == []

    def test_filtre_ne_jette_pas_job_board_par_domaine(self):
        """A3c laisse A4/A5 juger les job boards après analyse."""
        hits = [
            {"title": "Python dev", "url": "https://fr.indeed.com/viewjob?jk=1", "body": "offre", "source": "indeed"},
            {"title": "Alice Dev",  "url": "https://github.com/alice", "body": "Python developer", "source": "github"},
        ]
        # On mocke extraire_page_web_raw pour eviter le reseau
        import unittest.mock as mock
        with mock.patch("src.agents.chercheur_filtre.extraire_page_web_raw",
                        return_value="Alice Dupont, Python developer, 5 years experience"):
            resultat = filtre_node({"resultats_bruts": hits})

        profils = resultat["profils_bruts"]
        urls = [p["url"] for p in profils]
        assert "https://fr.indeed.com/viewjob?jk=1" in urls
        assert "https://github.com/alice" in urls

    def test_filtre_signale_bruit_texte_sans_jeter(self):
        """Les pages bruitées sont signalées à A4/A5, pas supprimées par blocklist."""
        hits = [
            {
                "title": "Offre emploi",
                "url": "https://example.com/poste",
                "body": "nous recrutons un developpeur",
                "source": "web",
            }
        ]
        import unittest.mock as mock
        with mock.patch("src.agents.chercheur_filtre.extraire_page_web_raw",
                        return_value="Nous recrutons un developpeur Python"):
            resultat = filtre_node({"resultats_bruts": hits})
        assert len(resultat["profils_bruts"]) == 1
        assert "[Signal A3c]" in resultat["profils_bruts"][0]["profil_brut"]
