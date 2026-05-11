from src.agents.verificateur import (
    _adequation_minimale,
    _parse_validation_json,
    _profil_non_candidat,
    _profil_personne_probable,
)


def test_pages_non_candidats_detectees_depuis_titre_et_url():
    assert _profil_non_candidat(
        "Angular vs React : Quel framework front-end choisir ?",
        "",
        "https://www.aquilapp.fr/ressources/projet-web/angular-vs-react",
    )
    assert _profil_non_candidat(
        "CV PYTHON : recevez gratuitement les...",
        "",
        "https://www.freelance-informatique.fr/cv-python-622",
    )


def test_profils_personnes_probables_conserves():
    assert _profil_personne_probable(
        "Erwann B. - Epitech Student at Epitech Montpellier | LinkedIn",
        "Étudiant à Epitech Montpellier, projets Java et React.",
        "linkedin",
        "https://fr.linkedin.com/in/erwann-b-874054197/en",
    )
    assert _profil_personne_probable(
        "Charalambos Anastassopoulos, Développeur JAVA Angular / freelance",
        "Développeur Java Angular freelance.",
        "web",
        "https://www.malt.fr/profile/charalambosanastassopoulos",
    )


def test_adequation_minimale_accepte_profil_tech_avec_competences():
    profil_requis = {"hard_skills": ["Java", "React"], "niveau_experience": "junior"}
    ok, _ = _adequation_minimale(
        profil_requis,
        "Erwann B. - Epitech Student at Epitech Montpellier | LinkedIn",
        "Étudiant à Epitech Montpellier, projets Java et React.",
    )
    assert ok

    ok, _ = _adequation_minimale(
        profil_requis,
        "Angular vs React : Quel framework front-end choisir ?",
        "",
    )
    assert not ok


def test_adequation_minimale_rejette_personne_hors_poste():
    profil_requis = {
        "hard_skills": ["Python", "FastAPI", "Docker", "RAG"],
        "niveau_experience": "senior",
    }

    ok, remarque = _adequation_minimale(
        profil_requis,
        "Fabienne Brandsma - Senior Banker - Retail",
        "Senior banker retail construction finance communication.",
    )
    assert not ok
    assert "Compétences insuffisamment prouvées" in remarque

    ok, _ = _adequation_minimale(
        profil_requis,
        "Nicolas Bigot - Lead developer, architect - DoYouBuzz",
        "Lead developer Python FastAPI Docker. Architecte logiciel backend.",
    )
    assert ok


def test_parse_validation_json_accepte_markdown_et_texte():
    parsed = _parse_validation_json(
        'Voici le résultat:\n```json\n{"candidat_id":"x","nom":"Alice","score_final":80,"statut":"valide","remarques":"ok"}\n```'
    )
    assert parsed["statut"] == "valide"
