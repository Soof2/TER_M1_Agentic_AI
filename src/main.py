"""
Point d'entrée CLI du SMA de recrutement automatisé.

Usage :
    python -m src.main "Développeur Python senior, 5 ans d'expérience, Paris"
    python -m src.main --fichier fiche_poste.txt
    python -m src.main --no-interrupt "Data Scientist ML, remote"
"""

import argparse
import sys
import uuid

from src.graph import build_graph
from src.observabilite import reset_metrics


def main():
    parser = argparse.ArgumentParser(
        description="SMA de recrutement automatisé — LangGraph"
    )
    parser.add_argument(
        "fiche_poste",
        nargs="?",
        help="Fiche de poste (texte direct)"
    )
    parser.add_argument(
        "--fichier", "-f",
        help="Chemin vers un fichier contenant la fiche de poste"
    )
    parser.add_argument(
        "--no-interrupt",
        action="store_true",
        help="Désactiver le human-in-the-loop (pas d'arrêt avant A7)"
    )
    args = parser.parse_args()

    # Lire la fiche de poste
    if args.fichier:
        with open(args.fichier) as f:
            fiche_poste = f.read().strip()
    elif args.fiche_poste:
        fiche_poste = args.fiche_poste
    else:
        print("Erreur : fournir une fiche de poste (texte ou --fichier)")
        sys.exit(1)

    print("=" * 60)
    print("  SMA DE RECRUTEMENT AUTOMATISÉ")
    print("=" * 60)
    print(f"\nFiche de poste :\n{fiche_poste}\n")
    print("-" * 60)

    # Initialiser les métriques d'observabilité pour ce run
    reset_metrics()

    # Construire le graphe
    with_interrupt = not args.no_interrupt
    app = build_graph(with_interrupt=with_interrupt)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Lancer le pipeline
    print("\n[Lancement du pipeline multi-agents...]\n")

    if with_interrupt:
        # Mode avec human-in-the-loop : le graphe s'arrête avant A7
        result = None
        for event in app.stream(
            {"fiche_poste": fiche_poste},
            config=config,
            stream_mode="updates"
        ):
            for node_name, node_output in event.items():
                print(f"  [{node_name}] terminé")
                result = node_output

        # Vérifier si on est en pause (interrupt_before recruteur)
        state = app.get_state(config)
        if state.next and "recruteur" in state.next:
            print("\n" + "=" * 60)
            print("  PAUSE — Validation humaine requise avant contact")
            print("=" * 60)

            candidats = state.values.get("candidats_valides", [])
            if candidats:
                print("\nCandidats à contacter :")
                for c in sorted(candidats, key=lambda x: x["score_final"], reverse=True):
                    print(f"  - {c['nom']} | Score: {c['score_final']} | {c['statut']}")

            reponse = input("\nContinuer et envoyer les messages ? (o/n) : ").strip().lower()

            if reponse in ("o", "oui", "y", "yes"):
                print("\n[Reprise du pipeline — envoi des messages...]\n")
                for event in app.stream(None, config=config, stream_mode="updates"):
                    for node_name, node_output in event.items():
                        print(f"  [{node_name}] terminé")
            else:
                print("\n[Pipeline arrêté par l'utilisateur — génération du rapport...]\n")
                # Mettre à jour l'état pour passer directement au rapport
                app.update_state(config, {}, as_node="recruteur")
                for event in app.stream(None, config=config, stream_mode="updates"):
                    for node_name, node_output in event.items():
                        print(f"  [{node_name}] terminé")
    else:
        # Mode sans interrupt : exécution complète
        for event in app.stream(
            {"fiche_poste": fiche_poste},
            config=config,
            stream_mode="updates"
        ):
            for node_name, node_output in event.items():
                print(f"  [{node_name}] terminé")

    # Afficher le rapport final
    final_state = app.get_state(config)
    rapport = final_state.values.get("rapport_final", "")

    print("\n" + "=" * 60)
    print("  RAPPORT FINAL")
    print("=" * 60)
    print(rapport)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
