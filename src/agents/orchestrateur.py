"""
A1 — Orchestrateur (Superviseur).

Reçoit la fiche de poste, coordonne tous les agents, et produit le
rapport final. Implémenté via le pattern Supervisor de LangGraph.
Topologie étoile, délégation formelle.

Ce module contient aussi le nœud de rapport final et le nœud de
réduction des scores (fan-in après Send).
"""

from langchain_core.messages import HumanMessage

from src.state import GraphState
from src.observabilite import get_metrics
from src.logger import get_logger

_log = get_logger("A1_orchestrateur")


def orchestrateur_node(state: GraphState) -> dict:
    """Point d'entrée : reçoit la fiche de poste et initialise le pipeline."""
    _log.info("Réception de la fiche de poste : %s...", state['fiche_poste'][:80])
    _log.info("Démarrage du pipeline multi-agents.")
    return {
        "messages": [
            HumanMessage(content=f"[Orchestrateur] Lancement du recrutement pour :\n{state['fiche_poste']}")
        ]
    }


def reduce_scores_node(state: GraphState) -> dict:
    """Nœud de réduction : agrège les scores des N évaluateurs parallèles.

    Les scores sont déjà agrégés par le reducer operator.add sur
    candidats_scores. Ce nœud sert de point de synchronisation (fan-in)
    avant de passer au vérificateur.
    """
    log = get_logger("reduce")
    n_scores = len(state.get("candidats_scores", []))
    log.info("Fan-in : %d scores agrégés depuis les évaluateurs parallèles.", n_scores)
    return {
        "messages": [
            HumanMessage(content=f"[Réduction] {n_scores} candidats évalués, passage à la vérification.")
        ]
    }


def reduce_validations_node(state: GraphState) -> dict:
    """Nœud de réduction : agrège les validations A5 parallèles."""
    log = get_logger("reduce")
    candidats = state.get("candidats_valides", [])
    n_valides = sum(1 for c in candidats if c.get("statut") == "valide")
    n_douteux = sum(1 for c in candidats if c.get("statut") == "douteux")
    n_invalides = sum(1 for c in candidats if c.get("statut") == "invalide")
    log.info(
        "Fan-in A5 : %d validations agrégées (%d valides, %d douteux, %d invalides).",
        len(candidats), n_valides, n_douteux, n_invalides,
    )
    return {
        "messages": [
            HumanMessage(
                content=(
                    f"[Réduction A5] {len(candidats)} validations : "
                    f"{n_valides} valides, {n_douteux} douteux, {n_invalides} invalides."
                )
            )
        ]
    }


def _valeur(value) -> str:
    if value in (None, "", []):
        return "Non renseigné"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "Non renseigné"
    return str(value)


def _ligne_table(cells: list[str]) -> str:
    return "| " + " | ".join(str(c).replace("\n", " ").replace("|", "/") for c in cells) + " |"


def _table_candidats(candidats: list[dict], profils_par_id: dict[str, dict]) -> str:
    if not candidats:
        return "Aucun."
    lignes = [
        _ligne_table(["Nom", "Lieu / source", "Lien", "Score", "Statut", "Remarques"]),
        _ligne_table(["---", "---", "---", "---:", "---", "---"]),
    ]
    for c in sorted(candidats, key=lambda x: x.get("score_final", 0), reverse=True):
        profil = profils_par_id.get(c.get("candidat_id"), {})
        lieu_source = _valeur(profil.get("source"))
        lien = profil.get("url") or "Non renseigné"
        lignes.append(_ligne_table([
            c.get("nom", "Non renseigné"),
            lieu_source,
            lien,
            f"{float(c.get('score_final', 0)):.1f}",
            c.get("statut", "douteux"),
            c.get("remarques", ""),
        ]))
    return "\n".join(lignes)


def _section_requetes(requetes: dict) -> str:
    """Formate les requêtes A3a pour audit dans le rapport final."""
    if not requetes:
        return "Aucune requête enregistrée."

    labels = {
        "queries_generales": "Web général / CV / portfolios",
        "queries_linkedin": "LinkedIn",
        "queries_github": "GitHub Users API",
        "queries_cv_sites": "Sites CV / freelances",
        "tags_stackoverflow": "Tags Stack Overflow",
    }
    lignes = [
        _ligne_table(["Source", "N°", "Requête"]),
        _ligne_table(["---", "---:", "---"]),
    ]
    for key, label in labels.items():
        valeurs = requetes.get(key, [])
        if not valeurs:
            continue
        for index, valeur in enumerate(valeurs, 1):
            lignes.append(_ligne_table([label, str(index), f"`{valeur}`"]))
    return "\n".join(lignes) if len(lignes) > 2 else "Aucune requête enregistrée."


def rapport_node(state: GraphState) -> dict:
    """Produit le rapport final en agrégeant les résultats de tous les agents."""
    _log.info("Génération du rapport final...")

    profil = state.get("profil_competences", {})
    n_bruts = len(state.get("profils_bruts", []))
    n_hits_bruts = len(state.get("resultats_bruts", []))
    n_dedup = len(state.get("profils_dedupliques", []))
    candidats_verifies = state.get("candidats_valides", [])
    candidats_valides = [c for c in candidats_verifies if c.get("statut") == "valide"]
    candidats_douteux = [c for c in candidats_verifies if c.get("statut") == "douteux"]
    candidats_invalides = [c for c in candidats_verifies if c.get("statut") == "invalide"]
    messages_envoyes = state.get("messages_envoyes", [])
    profils_par_id = {p.get("id"): p for p in state.get("profils_dedupliques", [])}
    requetes_section = _section_requetes(state.get("requetes_recherche", {}))

    # Exporter les métriques d'observabilité
    m = get_metrics()
    m.noter(
        "pipeline",
        n_profils_bruts=n_bruts,
        n_profils_dedup=n_dedup,
        n_scores=len(state.get("candidats_scores", [])),
        n_valides=len(candidats_valides),
        n_douteux=len(candidats_douteux),
        n_invalides=len(candidats_invalides),
        n_messages=len(messages_envoyes),
    )
    metriques_resume = f"```text\n{m.resume_texte()}\n```"

    messages_section = "Aucun message généré."
    if messages_envoyes:
        messages_section = "\n".join(
            f"- {msg.get('nom', 'Candidat')} ({msg.get('canal', 'canal non précisé')}) : {msg.get('objet', 'Sans objet')}"
            for msg in messages_envoyes
        )

    rapport = f"""# Rapport final de recrutement

## Résumé du poste
- Fiche de poste : {state.get('fiche_poste', 'Non renseignée')}
- Hard skills : {_valeur(profil.get('hard_skills'))}
- Soft skills : {_valeur(profil.get('soft_skills'))}
- Niveau d'expérience attendu : {_valeur(profil.get('niveau_experience', profil.get('niveau_seniorite')))}
- Expérience attendue : min {_valeur(profil.get('experience_min'))} an(s), max {_valeur(profil.get('experience_max'))}
- Type de contrat : {_valeur(profil.get('type_contrat'))}
- Localisation(s) : {_valeur(profil.get('localisations'))}
- Contraintes : {_valeur(profil.get('contraintes'))}

## Statistiques de recherche
- Résultats bruts collectés : {n_hits_bruts}
- Profils trouvés : {n_bruts}
- Profils après déduplication : {n_dedup}
- Candidats évalués : {len(state.get('candidats_scores', []))}
- Candidats valides : {len(candidats_valides)}
- Candidats douteux : {len(candidats_douteux)}
- Profils invalides / non-candidats : {len(candidats_invalides)}
- Messages générés : {len(messages_envoyes)}

## Recherches effectuées
{requetes_section}

## Candidats valides à contacter
{_table_candidats(candidats_valides, profils_par_id)}

## Candidats douteux à vérifier manuellement
{_table_candidats(candidats_douteux, profils_par_id)}

## Profils invalides ou non-candidats
{_table_candidats(candidats_invalides, profils_par_id)}

## Messages générés
{messages_section}

## Recommandations
- Contacter uniquement les candidats au statut `valide`.
- Vérifier manuellement les candidats `douteux` avant toute prise de contact.
- Ignorer les profils `invalides`, les pages d'école, les articles, les offres d'emploi et les agrégateurs.

## Métriques d'exécution
{metriques_resume}
"""
    _log.info("Rapport final généré.")

    return {
        "rapport_final": rapport,
        "messages": [HumanMessage(content="[Rapport] Rapport final déterministe généré.")]
    }
