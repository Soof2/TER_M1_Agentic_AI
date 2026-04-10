"""
A6 — Déduplicateur.

Identifie et fusionne les profils identiques collectés par A3
via différentes sources. Maintient un identifiant unique par candidat.
Agent utilitaire transversal — garantit l'intégrité des données
en entrée du pipeline d'évaluation.
"""

from difflib import SequenceMatcher

from src.state import GraphState, Candidat


def deduplicateur_node(state: GraphState) -> dict:
    """Déduplique les profils bruts par similarité de noms et URLs."""
    profils = state.get("profils_bruts", [])
    print(f"\n[A6 Déduplicateur] Analyse de {len(profils)} profils bruts...", flush=True)

    if not profils:
        print("[A6 Déduplicateur] Aucun profil à dédupliquer.", flush=True)
        return {"profils_dedupliques": []}

    dedupliques: list[Candidat] = []
    used = set()

    for i, p1 in enumerate(profils):
        if i in used:
            continue

        # Chercher les doublons de p1
        merged = dict(p1)
        sources = [p1["source"]]

        for j, p2 in enumerate(profils[i + 1:], start=i + 1):
            if j in used:
                continue

            if _are_duplicates(p1, p2):
                used.add(j)
                sources.append(p2["source"])
                # Fusionner les profils bruts
                merged["profil_brut"] = (
                    merged["profil_brut"] + "\n\n--- Source: "
                    + p2["source"] + " ---\n" + p2["profil_brut"]
                )
                # Garder l'URL la plus informative
                if not merged.get("url") and p2.get("url"):
                    merged["url"] = p2["url"]

        merged["source"] = ", ".join(set(sources))
        dedupliques.append(Candidat(**{k: merged[k] for k in Candidat.__annotations__}))
        used.add(i)

    n_removed = len(profils) - len(dedupliques)
    print(f"[A6 Déduplicateur] {len(dedupliques)} profils uniques conservés "
          f"({n_removed} doublons fusionnés).", flush=True)

    return {"profils_dedupliques": dedupliques}


def _are_duplicates(p1: Candidat, p2: Candidat) -> bool:
    """Détecte si deux profils représentent la même personne."""
    # Même URL = même personne
    if p1.get("url") and p2.get("url") and p1["url"] == p2["url"]:
        return True

    # Similarité de nom élevée
    ratio = SequenceMatcher(
        None,
        p1["nom"].lower().strip(),
        p2["nom"].lower().strip()
    ).ratio()

    return ratio > 0.85
