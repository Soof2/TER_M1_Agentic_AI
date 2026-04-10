"""
A3 — Chercheur de Profils.

Recherche des profils sur le web selon les critères fournis par A2.
Communication événementielle par lots vers A6, s'appuie sur le
blackboard d'A2 sans couplage direct.

Le LLM génère les requêtes de recherche, puis les outils sont
appelés directement (compatible avec les modèles cloud sans bind_tools).
"""

import json
import uuid
from langchain_classic.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

from src.state import GraphState, Candidat
from src.config import OLLAMA_MODEL, OLLAMA_PROVIDER, MAX_PROFILS_RECHERCHE
from src.tools.search import recherche_profils, recherche_linkedin, recherche_github

CHERCHEUR_QUERIES_PROMPT = """Tu es un expert en sourcing de talents. À partir du profil de compétences ci-dessous, génère des requêtes de recherche pour trouver des candidats.

Produis un JSON avec exactement ces clés :
- "queries_generales": liste de 2-3 requêtes de recherche web générales
- "queries_linkedin": liste de 2 requêtes pour chercher des profils LinkedIn
- "queries_github": liste de 1-2 requêtes pour chercher des profils GitHub

Chaque requête doit combiner compétences techniques, expérience et localisation.
Réponds UNIQUEMENT avec le JSON, sans texte avant ou après. Pas de markdown, pas de backticks."""


def chercheur_node(state: GraphState) -> dict:
    """Recherche des profils candidats à partir du profil de compétences."""
    print("\n[A3 Chercheur] Génération des requêtes de recherche...", flush=True)
    llm = init_chat_model(OLLAMA_MODEL, model_provider=OLLAMA_PROVIDER, temperature=0)

    profil = state["profil_competences"]

    # Étape 1 : Le LLM génère les requêtes de recherche
    recherche_msg = f"""Profil de compétences :

Hard skills : {', '.join(profil.get('hard_skills', []))}
Soft skills : {', '.join(profil.get('soft_skills', []))}
Expérience minimum : {profil.get('experience_min', 0)} ans
Formation : {profil.get('formation', 'Non spécifié')}
Contraintes : {', '.join(profil.get('contraintes', []))}
Mots-clés : {', '.join(profil.get('mots_cles', []))}"""

    messages = [
        SystemMessage(content=CHERCHEUR_QUERIES_PROMPT),
        HumanMessage(content=recherche_msg)
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # Parser les requêtes générées
    try:
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        queries = json.loads(content)
    except json.JSONDecodeError:
        # Fallback : requêtes basiques à partir des mots-clés
        mots = profil.get("mots_cles", profil.get("hard_skills", ["développeur"]))
        base_query = " ".join(mots[:5])
        queries = {
            "queries_generales": [base_query + " recrutement profil"],
            "queries_linkedin": [base_query],
            "queries_github": [base_query]
        }

    # Étape 2 : Appeler les outils de recherche directement
    all_results = []

    n_gen = len(queries.get("queries_generales", []))
    n_li = len(queries.get("queries_linkedin", []))
    n_gh = len(queries.get("queries_github", []))
    print(f"[A3 Chercheur] Lancement de {n_gen + n_li + n_gh} recherches "
          f"({n_gen} web, {n_li} LinkedIn, {n_gh} GitHub)...", flush=True)

    for i, q in enumerate(queries.get("queries_generales", []), 1):
        print(f"[A3 Chercheur]   Web {i}/{n_gen} : {q[:60]}...", flush=True)
        result = recherche_profils.invoke({"query": q})
        all_results.append(result)

    for i, q in enumerate(queries.get("queries_linkedin", []), 1):
        print(f"[A3 Chercheur]   LinkedIn {i}/{n_li} : {q[:60]}...", flush=True)
        result = recherche_linkedin.invoke({"query": q})
        all_results.append(result)

    for i, q in enumerate(queries.get("queries_github", []), 1):
        print(f"[A3 Chercheur]   GitHub {i}/{n_gh} : {q[:60]}...", flush=True)
        result = recherche_github.invoke({"query": q})
        all_results.append(result)

    # Étape 3 : Parser les résultats en Candidats
    candidats = _parse_search_results(all_results)
    candidats = candidats[:MAX_PROFILS_RECHERCHE]
    print(f"[A3 Chercheur] {len(candidats)} profils bruts collectés.", flush=True)

    return {
        "profils_bruts": candidats,
        "messages": [response]
    }


def _parse_search_results(results: list[str]) -> list[Candidat]:
    """Parse les résultats de recherche en objets Candidat."""
    candidats = []
    seen_urls = set()

    for result_text in results:
        if not isinstance(result_text, str):
            result_text = str(result_text)

        entries = result_text.split("\n---\n")

        for entry in entries:
            lines = entry.strip().split("\n")
            if len(lines) < 2:
                continue

            nom = ""
            url = ""
            profil_brut = entry.strip()
            source = "web"

            for line in lines:
                if line.startswith(("Nom:", "Titre:", "Profil:")):
                    nom = line.split(":", 1)[1].strip()
                elif line.startswith("URL:"):
                    url = line.split(":", 1)[1].strip()

            if not nom:
                continue

            if "linkedin.com" in url:
                source = "linkedin"
            elif "github.com" in url:
                source = "github"
            elif "indeed" in url:
                source = "indeed"

            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            candidats.append(Candidat(
                id=str(uuid.uuid4())[:8],
                nom=nom,
                source=source,
                profil_brut=profil_brut,
                url=url or None
            ))

    return candidats
