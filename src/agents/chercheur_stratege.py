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

Produis un JSON avec exactement ces clés :
- "queries_generales": liste de 2-3 requêtes web ciblant des CV ou portfolios.
  Utilise les compétences exactes avec des opérateurs comme intitle:CV ou les termes "portfolio" "profil" "expérience".
  EXEMPLE pour Python/ML/Paris : intitle:CV "Python" "machine learning" Paris
- "queries_linkedin": liste de 2 requêtes pour profils LinkedIn (personnes uniquement).
  Inclure hard skills principaux + localisation + site:linkedin.com/in
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
        requetes = {
            "queries_generales": [f'intitle:CV "{mots[0]}" {mots[1] if len(mots) > 1 else ""}'],
            "queries_linkedin": [f'site:linkedin.com/in {base}'],
            "queries_github": [f'{base} followers:>5'],
            "queries_cv_sites": [f'site:malt.fr {base}', f'site:doyoubuzz.com {base}'],
            "tags_stackoverflow": [t.lower().replace(" ", "-") for t in mots[:3]],
        }
        _log.warning("JSON non parsable depuis le stratège — fallback requêtes génériques.")

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
