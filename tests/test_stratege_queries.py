from src.agents.chercheur_stratege import _enrichir_requetes


def test_requetes_operateurs_linkedin_et_cv():
    profil = {
        "hard_skills": ["Angular", "TypeScript"],
        "niveau_experience": "alternant",
        "type_contrat": "alternance",
        "localisations": ["Montpellier"],
        "remote": False,
    }

    requetes = _enrichir_requetes(
        {
            "queries_generales": [],
            "queries_linkedin": [],
            "queries_github": [],
            "queries_cv_sites": [],
            "tags_stackoverflow": [],
        },
        profil,
    )

    assert any("intitle:CV" in q for q in requetes["queries_generales"])
    assert any("inurl:cv" in q for q in requetes["queries_generales"])
    assert any("site:linkedin.com/in" in q for q in requetes["queries_linkedin"])
    assert any("site:fr.linkedin.com/in" in q for q in requetes["queries_linkedin"])
    assert all('-"senior"' in q for q in requetes["queries_linkedin"])


def test_requetes_github_utilisent_operateurs_natifs():
    profil = {
        "hard_skills": ["Angular", "TypeScript"],
        "niveau_experience": "senior",
        "type_contrat": "indifferent",
        "localisations": ["Montpellier"],
        "remote": False,
    }

    requetes = _enrichir_requetes(
        {
            "queries_generales": [],
            "queries_linkedin": [],
            "queries_github": [],
            "queries_cv_sites": [],
            "tags_stackoverflow": [],
        },
        profil,
    )

    github_query = " ".join(requetes["queries_github"])
    assert "location:Montpellier" in github_query
    assert "language:TypeScript" in github_query
    assert "followers:>5" in github_query
