"""
A5 — Vérificateur.

Vérifie la cohérence des profils scorés par A4. Validation pair-à-pair
formelle : A4 produit, A5 contrôle indépendamment. La séparation des
sous-champs (candidats_scores / candidats_valides) impose cette contrainte.
"""

import json
import re
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState, CandidatValide
from src.config import get_llm
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A5_verificateur")


_VERIFICATEUR_UNITAIRE_SYSTEM = """Tu es le vérificateur A5 d'un système de recrutement.
Tu contrôles UN seul candidat à la fois à partir du score A4, du profil brut et du profil requis.

Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans texte autour :
{
  "candidat_id": "...",
  "nom": "...",
  "score_final": <reprends le score_global_A4 fourni, ajuste seulement si tu as une raison forte>,
  "statut": "valide|douteux|invalide",
  "remarques": "..."
}

Règles strictes :
- "valide" uniquement si le profil décrit clairement une personne ET montre des compétences techniques liées au poste.
- "invalide" si c'est une page entreprise, formation, article, annuaire, offre, professeur/cours, profil hors métier (banquier, immobilier, juriste, retraité, commercial...) ou profil clairement non-technique.
- "douteux" si c'est une personne possible mais avec preuves insuffisantes ou incohérences.
- Ne remets JAMAIS score_final à 0 sauf si le profil est complètement hors sujet (score < 20).
- Garde le score_global_A4 comme base et ajuste de ±20 maximum."""


_SKILL_ALIASES = {
    "python": ("python",),
    "fastapi": ("fastapi", "fast api"),
    "langgraph": ("langgraph", "lang graph"),
    "docker": ("docker", "container", "conteneur"),
    "rag": (" rag ", "retrieval augmented generation", "retrieval-augmented generation"),
    "java": ("java",),
    "javascript": ("javascript", "js"),
    "typescript": ("typescript", "ts"),
    "react": ("react", "reactjs", "react.js"),
    "angular": ("angular",),
    "sql": ("sql",),
    "postgresql": ("postgresql", "postgres"),
    "mongodb": ("mongodb", "mongo"),
    "kubernetes": ("kubernetes", "k8s"),
    "git": (" git ", "github", "gitlab"),
}


def _texte_normalise(*parts: str) -> str:
    return f" {' '.join(str(p or '').lower() for p in parts)} "


def _skill_present(skill: str, texte: str) -> bool:
    key = skill.lower().strip()
    aliases = _SKILL_ALIASES.get(key, (key,))
    for alias in aliases:
        alias = alias.strip()
        if re.search(rf"(?<![a-z0-9+#]){re.escape(alias)}(?![a-z0-9+#])", texte):
            return True
    return False


def _preuves_competences(profil_requis: dict, nom: str, profil_brut: str) -> tuple[int, list[str], list[str]]:
    """Compte les hard skills réellement visibles dans le profil candidat."""
    hard_skills = [s for s in profil_requis.get("hard_skills", []) if s]
    texte = _texte_normalise(nom, profil_brut)
    presentes = [skill for skill in hard_skills if _skill_present(skill, texte)]
    absentes = [skill for skill in hard_skills if skill not in presentes]
    return len(presentes), presentes, absentes


def _role_tech_compatible(nom: str, profil_brut: str) -> bool:
    texte = _texte_normalise(nom, profil_brut)
    marqueurs = (
        "développeur", "developpeur", "developer", "software engineer",
        "backend", "fullstack", "full stack", "data engineer", "ml engineer",
        "architecte logiciel", "software architect", "lead developer",
        "tech lead", "ingénieur logiciel", "ingenieur logiciel",
        "étudiant", "etudiant", "student", "epitech", "projets",
    )
    return any(m in texte for m in marqueurs)


def _adequation_minimale(
    profil_requis: dict,
    nom: str,
    profil_brut: str,
) -> tuple[bool, str]:
    """Verrou anti-faux positifs : score LLM élevé ne suffit pas."""
    # Si le profil_brut est très court, le scraping a échoué (snippet DDG uniquement).
    # Dans ce cas on ne peut pas prouver l'absence de compétences → on passe.
    if len((profil_brut or "").strip()) < 400:
        return True, ""

    n_presentes, presentes, absentes = _preuves_competences(profil_requis, nom, profil_brut)
    n_requises = len([s for s in profil_requis.get("hard_skills", []) if s])
    if n_requises == 0:
        return True, ""

    minimum = 2 if n_requises >= 3 else 1
    if n_presentes < minimum:
        return (
            False,
            f"Compétences insuffisamment prouvées dans le profil ({', '.join(presentes) or 'aucune'} ; manquantes : {', '.join(absentes[:4])}).",
        )
    if not _role_tech_compatible(nom, profil_brut):
        return False, "Profil personne détecté mais rôle technique compatible non prouvé."
    return True, ""


def _profil_non_candidat(nom: str, profil_brut: str, url: str = "") -> bool:
    """Détecte les pages qui ne décrivent pas une personne candidate."""
    texte = f"{nom} {profil_brut} {url}".lower()
    marqueurs = (
        "offre d'emploi", "offres d'emploi", "trouver un emploi",
        "recrutement en alternance", "raisons de tenter", "article",
        "blog", "école supérieure", "ecole supérieure", "école superieure",
        "groupe alternance", "formation en alternance", "campus",
        "adopte1alternant", "walt community", "annuaire", "job board",
        "trouvez un freelance", "sélectionnez", "selectionnez",
        "recevez gratuitement", "formation react", "les formations à",
        "les formations a", "angular vs react", "quel framework front-end choisir",
        "spécialiste du travail", "specialiste du travail", "prof de python",
        "€/h", "avis", "élèves accompagnés", "eleves accompagnés",
        "codeur.com/developpeur", "freelance-informatique.fr",
        "orsys.fr", "humancoders.com/formations", "aquilapp.fr/ressources",
        "superprof.fr",
    )
    return any(m in texte for m in marqueurs)


def _profil_personne_probable(nom: str, profil_brut: str, source: str, url: str) -> bool:
    """Heuristique conservatrice : page publique qui ressemble à une personne."""
    texte = f"{nom} {profil_brut}".lower()
    url_lower = (url or "").lower()
    if _profil_non_candidat(nom, profil_brut, url):
        return False
    if "linkedin" in source and "/in/" in url_lower:
        return not any(m in texte for m in ("spécialiste du travail", "specialiste du travail", "recrutement", "agence"))
    if "malt.fr/profile/" in url_lower:
        return True
    if "github.com/" in url_lower and not any(p in url_lower for p in ("/topics/", "/orgs/", "/marketplace/")):
        return True
    return bool(re.search(r"\b[A-ZÉÈÀÂÎÔÛÇ][a-zA-ZÀ-ÖØ-öø-ÿ'’-]+\s+[A-ZÉÈÀÂÎÔÛÇ][a-zA-ZÀ-ÖØ-öø-ÿ'’.]+\b", nom))


def _profil_senior(profil_brut: str) -> bool:
    texte = profil_brut.lower()
    marqueurs = (
        "senior", "lead", "manager", "architecte", "principal",
        "confirmé", "confirme", "head of", "cto", "directeur",
        "tech lead", "staff engineer", "principal engineer",
    )
    annees = re.search(r"\b([6-9]|1[0-9]|2[0-9])\s*\+?\s*ans\b", texte)
    return any(m in texte for m in marqueurs) or bool(annees)


def _profil_debutant(profil_brut: str) -> bool:
    texte = profil_brut.lower()
    marqueurs = (
        "alternant", "alternance", "stagiaire", "stage", "étudiant",
        "etudiant", "apprenti", "apprentissage", "junior", "débutant",
        "debutant", "bac+2", "bac+3", "master 1", "master 2",
    )
    return any(m in texte for m in marqueurs)


def _experience_incompatible(profil_brut: str, niveau_requis: str) -> tuple[bool, str]:
    """Applique le filtrage d'expérience demandé par la fiche de poste."""
    if niveau_requis in ("alternant", "stagiaire", "junior") and _profil_senior(profil_brut):
        return True, f"Profil trop expérimenté pour un niveau {niveau_requis}."
    if niveau_requis == "senior" and _profil_debutant(profil_brut) and not _profil_senior(profil_brut):
        return True, "Profil trop junior pour un niveau senior."
    return False, ""


def _profil_court(profil_brut: str, max_chars: int = 1600) -> str:
    texte = " ".join(str(profil_brut or "").split())
    if len(texte) <= max_chars:
        return texte
    return texte[:max_chars] + " [...]"


def _parse_validation_json(content: str) -> dict:
    """Parse une réponse A5 même si le modèle ajoute des fences ou du texte."""
    cleaned = (content or "").strip()
    if "```" in cleaned:
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.strip().startswith("json"):
            cleaned = cleaned.strip()[4:]
    cleaned = cleaned.strip()

    for candidate in (
        cleaned,
        re.search(r"\{.*\}", cleaned, re.DOTALL).group(0) if re.search(r"\{.*\}", cleaned, re.DOTALL) else "",
        re.search(r"\[.*\]", cleaned, re.DOTALL).group(0) if re.search(r"\[.*\]", cleaned, re.DOTALL) else "",
    ):
        if not candidate:
            continue
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            if not parsed:
                raise ValueError("Liste JSON vide")
            parsed = parsed[0]
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Aucun objet JSON valide trouvé")


def _verifier_candidat_llm(llm, profil_requis: dict, cs: dict, profil_source: dict) -> tuple[dict, object | None]:
    candidat_info = {
        "candidat_id": cs["candidat_id"],
        "nom": cs["nom"],
        "score_global_A4": cs["score_global"],
        "scores_detail_A4": cs.get("scores_detail", {}),
        "resume_A4": cs.get("resume", ""),
        "source": profil_source.get("source", ""),
        "url": profil_source.get("url", ""),
        "profil_brut": _profil_court(profil_source.get("profil_brut", "")),
    }
    verif_msg = f"""Profil requis :
{json.dumps(profil_requis, ensure_ascii=False, indent=2)}

Candidat à vérifier :
{json.dumps(candidat_info, ensure_ascii=False, indent=2)}

Contrôle l'adéquation réelle du candidat et renvoie l'objet JSON demandé."""
    last_error: Exception | None = None
    response = None
    for attempt in range(3):
        response = llm.invoke([
            SystemMessage(content=_VERIFICATEUR_UNITAIRE_SYSTEM),
            HumanMessage(content=verif_msg),
        ])
        try:
            validation = _parse_validation_json(response.content)
            break
        except Exception as exc:
            last_error = exc
            _log.warning(
                "A5 JSON invalide pour %s tentative %d/3 : %s",
                cs.get("nom", "?"),
                attempt + 1,
                str(exc)[:160],
            )
    else:
        raise ValueError(
            f"A5 n'a pas produit de JSON valide pour {cs.get('nom', '?')} après 3 tentatives : {last_error}"
        )

    validation.setdefault("candidat_id", cs["candidat_id"])
    validation.setdefault("nom", cs["nom"])
    validation.setdefault("score_final", cs["score_global"])
    validation.setdefault("statut", "douteux")
    validation.setdefault("remarques", "Vérification A5 sans remarque.")
    return validation, response


def verificateur_node(state: dict) -> dict:
    """Vérifie UN candidat scoré par A4.

    Ce nœud est appelé en parallèle via Send(), comme A4. Il n'existe pas de
    Si le LLM ne produit pas un JSON exploitable après retries, le run échoue
    explicitement.
    """
    m = get_metrics()
    candidat_score = state["candidat_score"]
    profil_source = state.get("profil_source", {})
    profil_requis = state.get("profil_competences", {})
    m.debut(f"A5_{candidat_score['candidat_id']}")
    _log.info("Vérification A5 de : %s", candidat_score.get("nom", "?"))

    llm = get_llm(temperature=0)
    validation, response = _verifier_candidat_llm(llm, profil_requis, candidat_score, profil_source)
    niveau_requis = profil_requis.get(
        "niveau_experience",
        profil_requis.get("niveau_seniorite", "indifferent"),
    )
    candidat_id = validation.get("candidat_id", candidat_score["candidat_id"])
    score_a4 = float(candidat_score["score_global"])
    score_final = float(validation.get("score_final") or score_a4)
    statut = validation.get("statut", "douteux")
    remarques = validation.get("remarques", "")
    nom = validation.get("nom", profil_source.get("nom", candidat_score["nom"]))
    profil_brut = profil_source.get("profil_brut", "")
    source = profil_source.get("source", "")
    url = profil_source.get("url", None)

    # Garde-fous déterministes : ils ne remplacent pas A5, ils empêchent A5 de
    # valider une page non-candidat ou hors compétences malgré un score A4 élevé.
    if _profil_non_candidat(nom, profil_brut, url or ""):
        score_final = min(score_final, 20.0)
        statut = "invalide"
        remarques = f"{remarques} Page non-candidat détectée.".strip()
    elif statut == "valide" and not _profil_personne_probable(nom, profil_brut, source, url or ""):
        score_final = min(score_final, 45.0)
        statut = "invalide"
        remarques = f"{remarques} Page ne décrivant pas clairement une personne.".strip()
    elif statut == "valide":
        ok, raison = _adequation_minimale(profil_requis, nom, profil_brut)
        if not ok:
            score_final = min(score_final, 45.0)
            statut = "invalide"
            remarques = f"{remarques} {raison}".strip()

    incompatible, raison = _experience_incompatible(profil_brut, niveau_requis)
    if incompatible:
        score_final = min(score_final, 45.0)
        statut = "invalide"
        remarques = f"{remarques} {raison}".strip()

    # Upgrade douteux → valide si score >= seuil contact et profil LinkedIn individuel.
    # LinkedIn bloque le scraping → A5 voit peu de contenu et bascule par défaut sur
    # "douteux" même pour de bons candidats. Si A4 a scoré >= 75 et que c'est un
    # vrai profil /in/ avec un titre tech compatible, on fait confiance au score.
    _TITRES_NON_TECH = (
        "banquier", "banker", "retraité", "retraite", "immobilier", "notaire",
        "avocat", "juriste", "commercial", "directeur commercial", "chasseur de têtes",
        "chasseur de tetes", "managing director", "conseil immobilier",
        "étudiant en droit", "etudiant en droit",
    )
    _titre_non_tech = any(t in nom.lower() for t in _TITRES_NON_TECH)
    from src.config import SCORE_SEUIL_CONTACT
    if (
        statut == "douteux"
        and score_a4 >= SCORE_SEUIL_CONTACT
        and url
        and "/in/" in url.lower()
        and not _profil_non_candidat(nom, profil_brut, url)
        and not _titre_non_tech
    ):
        statut = "valide"
        remarques = f"{remarques} Upgrade automatique : score >= {SCORE_SEUIL_CONTACT} sur profil LinkedIn individuel.".strip()

    candidat_valide = CandidatValide(
        candidat_id=candidat_id,
        nom=nom,
        score_final=score_final,
        statut=statut,
        remarques=remarques,
        source=source,
        url=url,
    )

    _log.info("%s -> %.1f/100 | %s", nom, score_final, statut)
    m.fin(
        f"A5_{candidat_id}",
        candidat_nom=nom,
        score=score_final,
        statut=statut,
        source=source,
    )

    return {
        "candidats_valides": [candidat_valide],
        "messages": [response],
    }
