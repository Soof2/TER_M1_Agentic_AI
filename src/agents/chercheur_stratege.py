"""
A3a — Stratège de Recherche.

Reçoit le profil de compétences extrait par A2 et produit un plan
de recherche structuré : requêtes optimisées par source (web général,
LinkedIn, GitHub, sites CV).

Responsabilité unique : décision cognitive (LLM) sur QUOI chercher.
La collecte (COMMENT) est déléguée à A3b, le filtrage (QUOI garder) à A3c.

Output :
    requetes_recherche : dict avec les clés :
        - queries_generales  : list[str]  — requêtes web générales (CV, portfolios)
        - queries_linkedin   : list[str]  — requêtes LinkedIn (site:linkedin.com/in)
        - queries_github     : list[str]  — requêtes GitHub Search API (operators natifs)
        - queries_cv_sites   : list[str]  — requêtes sur malt.fr, doyoubuzz.com, etc.
"""

import json

from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A3a_stratege")

_STRATEGE_PROMPT = """Tu es un expert en sourcing de talents. À partir du profil de compétences ci-dessous, génère des requêtes de recherche pour trouver des PERSONNES (candidats), PAS des offres d'emploi ni des dépôts de code.

RÈGLE ABSOLUE : Utilise UNIQUEMENT les compétences, la localisation et l'expérience du profil fourni. N'invente PAS de compétences ou de localisations absentes du profil.

RÈGLE DE NIVEAU : Respecte strictement le niveau attendu.
- Si niveau_experience vaut "alternant" ou "stagiaire", cherche des profils étudiants, apprentis, juniors, école, master, Bac+2/Bac+5, et évite les requêtes qui attirent des profils senior/lead/confirmés.
- Si niveau_experience vaut "junior", cherche des profils junior/débutant avec 0 à 2 ans d'expérience.
- Si niveau_experience vaut "senior", cherche des profils senior avec 5 ans d'expérience minimum.
- Si niveau_experience vaut "indifferent", n'ajoute aucun critère d'expérience.

Produis un JSON avec exactement ces clés :
- "queries_generales": liste de 2-3 requêtes web ciblant des CV ou portfolios.
  Utilise les compétences exactes avec des opérateurs comme intitle:CV, inurl:cv ou les termes "portfolio" "profil" "expérience".
  EXEMPLE pour Python/ML/Paris : intitle:CV "Python" "machine learning" Paris
- "queries_linkedin": liste de 2 requêtes pour profils LinkedIn (personnes uniquement).
  Inclure hard skills principaux + localisation + site:linkedin.com/in ou site:fr.linkedin.com/in
- "queries_github": liste de 2 requêtes pour l'API GitHub Search Users (PAS des repos).
  Utiliser les opérateurs natifs GitHub : location:Ville language:Python followers:>5
  EXEMPLE : python machine learning location:Paris followers:>5
- "queries_cv_sites": liste de 2 requêtes sur malt.fr ou doyoubuzz.com.
  Format : site:malt.fr "competence1" "competence2" localisation
- "tags_stackoverflow": liste de 3-5 tags Stack Overflow correspondant aux hard skills.
  Ce sont les tags exacts du site (tirets, minuscules) : ["python", "machine-learning", "scikit-learn"]
  Utilise UNIQUEMENT les tags qui correspondent aux compétences du profil.

Chaque requête doit utiliser les vraies compétences du profil fourni.
Réponds UNIQUEMENT avec le JSON, sans texte avant ou après. Pas de markdown, pas de backticks."""


_LANGUAGE_ALIASES = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "java": "Java",
    "angular": "TypeScript",
    "react": "JavaScript",
    "vue": "JavaScript",
    "node": "JavaScript",
    "php": "PHP",
    "symfony": "PHP",
    "laravel": "PHP",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "ruby": "Ruby",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "c#": "C#",
    "c++": "C++",
}


def _dedup_liste(items: list[str], limite: int) -> list[str]:
    vus: set[str] = set()
    resultat: list[str] = []
    for item in items:
        item = " ".join(str(item).split())
        if not item or item in vus:
            continue
        vus.add(item)
        resultat.append(item)
        if len(resultat) >= limite:
            break
    return resultat


def _competences_principales(profil: dict, limite: int = 3) -> list[str]:
    skills = [s for s in profil.get("hard_skills", []) if s]
    if not skills:
        skills = [s for s in profil.get("mots_cles", []) if s]
    return skills[:limite] or ["développeur"]


def _quote(term: str) -> str:
    term = str(term).strip()
    if not term:
        return ""
    if term.startswith('"') and term.endswith('"'):
        return term
    return f'"{term}"' if " " in term or len(term) > 2 else term


def _termes_competences(profil: dict) -> str:
    return " ".join(_quote(skill) for skill in _competences_principales(profil))


def _lieu_principal(profil: dict) -> str:
    lieux = [l for l in profil.get("localisations", []) if l]
    return lieux[0] if lieux else ""


def _github_language(profil: dict) -> str:
    for skill in _competences_principales(profil, limite=5):
        key = skill.lower().strip()
        if key in _LANGUAGE_ALIASES:
            return _LANGUAGE_ALIASES[key]
    return ""


def _followers_min(profil: dict) -> str:
    niveau = profil.get("niveau_experience", "indifferent")
    if niveau in ("alternant", "stagiaire", "junior"):
        return "followers:>0"
    return "followers:>5"


def _requetes_operateurs(profil: dict) -> dict:
    """Ajoute des requêtes opérateurs fiables en complément du LLM."""
    skills = _termes_competences(profil)
    lieu = _lieu_principal(profil)
    lieu_ddg = _quote(lieu) if lieu else ""
    lieu_github = f"location:{lieu}" if lieu else ""
    language = _github_language(profil)
    language_op = f"language:{language}" if language else ""
    github_base = " ".join(t for t in (skills.replace('"', ""), lieu_github, language_op, _followers_min(profil), "repos:>0") if t)

    return {
        "queries_generales": [
            f"intitle:CV {skills} {lieu_ddg}",
            f"inurl:cv {skills} {lieu_ddg}",
            f'"portfolio" {skills} {lieu_ddg}',
            f'"profil développeur" {skills} {lieu_ddg}',
        ],
        "queries_linkedin": [
            f"site:linkedin.com/in {skills} {lieu_ddg}",
            f"site:fr.linkedin.com/in {skills} {lieu_ddg}",
        ],
        "queries_github": [
            github_base,
            " ".join(t for t in (skills.replace('"', ""), lieu_github, language_op, "type:user") if t),
        ],
        "queries_cv_sites": [
            f"site:malt.fr {skills} {lieu_ddg}",
            f"site:doyoubuzz.com {skills} {lieu_ddg}",
            f"site:github.io {skills} {lieu_ddg}",
            f"site:about.me {skills} {lieu_ddg}",
        ],
    }


def _termes_experience(profil: dict) -> tuple[str, str]:
    """Retourne les termes à ajouter aux requêtes et les exclusions associées."""
    niveau = profil.get("niveau_experience", profil.get("niveau_seniorite", "indifferent"))
    contrat = profil.get("type_contrat", "indifferent")
    if niveau == "alternant":
        return f'"alternance" "alternant" apprenti étudiant junior', '-"senior" -"lead" -"confirmé" -"confirme" -"manager"'
    if niveau == "stagiaire":
        return f'"stage" stagiaire étudiant junior', '-"senior" -"lead" -"confirmé" -"confirme" -"manager"'
    if niveau == "junior":
        return '"junior" débutant "0 ans" "1 an" "2 ans"', '-"senior" -"lead" -"manager"'
    if niveau == "confirme":
        return '"confirmé" "3 ans" "4 ans" "5 ans"', ""
    if niveau == "senior":
        return '"senior" "5 ans" "6 ans" "7 ans"', ""
    if contrat in ("alternance", "stage"):
        return f'"{contrat}" étudiant junior', '-"senior" -"lead" -"manager"'
    return "", ""


def _termes_lieu(profil: dict) -> str:
    lieux = [l for l in profil.get("localisations", []) if l]
    termes = " ".join(f'"{lieu}" environs' for lieu in lieux)
    if profil.get("remote"):
        termes = f"{termes} télétravail remote hybride".strip()
    return termes


def _enrichir_requetes(requetes: dict, profil: dict) -> dict:
    operateurs = _requetes_operateurs(profil)
    for key, generated in operateurs.items():
        requetes[key] = list(requetes.get(key, [])) + generated

    termes_exp, exclusions = _termes_experience(profil)
    termes_lieu = _termes_lieu(profil)
    suffixe = " ".join(t for t in (termes_exp, termes_lieu, exclusions) if t).strip()

    if suffixe:
        for key in ("queries_generales", "queries_linkedin", "queries_cv_sites"):
            requetes[key] = [f"{q} {suffixe}".strip() for q in requetes.get(key, [])]

        github_suffix = " ".join(t for t in (termes_exp.replace('"', ""), termes_lieu.replace('"', "")) if t).strip()
        if github_suffix:
            requetes["queries_github"] = [f"{q} {github_suffix}".strip() for q in requetes.get("queries_github", [])]

    requetes["queries_generales"] = _dedup_liste(requetes.get("queries_generales", []), 4)
    requetes["queries_linkedin"] = _dedup_liste(requetes.get("queries_linkedin", []), 4)
    requetes["queries_github"] = _dedup_liste(requetes.get("queries_github", []), 3)
    requetes["queries_cv_sites"] = _dedup_liste(requetes.get("queries_cv_sites", []), 4)
    requetes["tags_stackoverflow"] = _dedup_liste(requetes.get("tags_stackoverflow", []), 5)
    return requetes


def stratege_node(state: GraphState) -> dict:
    """Génère le plan de recherche (requêtes par source) à partir du profil de compétences."""
    m = get_metrics()
    m.debut("A3a_stratege")

    profil = state["profil_competences"]
    _log.info(
        "Génération des requêtes pour : %s",
        ", ".join(profil.get("hard_skills", [])[:5]),
    )

    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    recherche_msg = (
        f"Hard skills : {', '.join(profil.get('hard_skills', []))}\n"
        f"Soft skills : {', '.join(profil.get('soft_skills', []))}\n"
        f"Expérience minimum : {profil.get('experience_min', 0)} ans\n"
        f"Expérience maximum : {profil.get('experience_max', 'non contraint')}\n"
        f"Niveau attendu : {profil.get('niveau_experience', 'indifferent')}\n"
        f"Type de contrat : {profil.get('type_contrat', 'indifferent')}\n"
        f"Localisations : {', '.join(profil.get('localisations', []))}\n"
        f"Télétravail/hybride : {profil.get('remote', False)}\n"
        f"Formation : {profil.get('formation', 'Non spécifié')}\n"
        f"Contraintes : {', '.join(profil.get('contraintes', []))}\n"
        f"Mots-clés : {', '.join(profil.get('mots_cles', []))}"
    )

    response = llm.invoke([
        SystemMessage(content=_STRATEGE_PROMPT),
        HumanMessage(content=recherche_msg),
    ])
    content = response.content.strip()

    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        requetes = json.loads(content)
    except json.JSONDecodeError:
        # Fallback : requêtes génériques à partir des mots-clés
        mots = profil.get("mots_cles", profil.get("hard_skills", ["développeur"]))
        base = " ".join(mots[:5])
        lieux = _termes_lieu(profil)
        if lieux:
            base = f"{base} {lieux}"
        requetes = {
            "queries_generales": [f'intitle:CV "{mots[0]}" {mots[1] if len(mots) > 1 else ""}'],
            "queries_linkedin": [f'site:linkedin.com/in {base}'],
            "queries_github": [f'{base} followers:>5'],
            "queries_cv_sites": [f'site:malt.fr {base}', f'site:doyoubuzz.com {base}'],
            "tags_stackoverflow": [t.lower().replace(" ", "-") for t in mots[:3]],
        }
        _log.warning("JSON non parsable depuis le stratège — fallback requêtes génériques.")

    requetes = _enrichir_requetes(requetes, profil)

    n_requetes = sum(len(v) for v in requetes.values() if isinstance(v, list))
    _log.info(
        "%d requêtes générées (%d web, %d LinkedIn, %d GitHub, %d CV, %d tags SO)",
        n_requetes,
        len(requetes.get("queries_generales", [])),
        len(requetes.get("queries_linkedin", [])),
        len(requetes.get("queries_github", [])),
        len(requetes.get("queries_cv_sites", [])),
        len(requetes.get("tags_stackoverflow", [])),
    )

    m.fin("A3a_stratege", n_requetes=n_requetes)

    return {
        "requetes_recherche": requetes,
        "messages": [response],
    }
