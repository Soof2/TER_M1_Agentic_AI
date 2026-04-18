"""
Observabilité du pipeline SMA — métriques d'exécution.

Collecte par nœud :
    - Temps d'exécution (secondes)
    - Métriques métier (nombre de candidats, taux de filtrage, etc.)

Export automatique en JSON dans logs/ à chaque run.
Utilisé dans le rapport final pour la transparence du pipeline.

Usage dans un nœud :
    from src.observabilite import get_metrics
    m = get_metrics()
    t0 = m.debut("A3b_collecteur")
    ...
    m.fin("A3b_collecteur", n_hits=len(hits), sources=["ddg", "github"])
"""

import time
import json
import os
from datetime import datetime
from src.logger import get_logger

_log = get_logger("observabilite")


class PipelineMetrics:
    """Collecteur de métriques pour un run du pipeline multi-agents."""

    def __init__(self):
        self._run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._debut_run = time.time()
        self._etapes: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def debut(self, nom: str) -> float:
        """Démarre la mesure d'une étape. Retourne le timestamp de début."""
        t = time.time()
        self._etapes.setdefault(nom, {})["debut"] = t
        return t

    def fin(self, nom: str, **kwargs):
        """Termine la mesure d'une étape. kwargs = métriques métier.

        Exemple :
            m.fin("A3c_filtre", n_entree=30, n_sortie=8, taux_bruit=0.73)
        """
        t = time.time()
        etape = self._etapes.setdefault(nom, {})
        debut = etape.get("debut", t)
        etape["fin"] = t
        etape["duree_s"] = round(t - debut, 2)
        etape.update(kwargs)
        _log.info(
            "%-25s %.2fs  %s",
            nom,
            etape["duree_s"],
            "  ".join(f"{k}={v}" for k, v in kwargs.items()),
        )

    def noter(self, nom: str, **kwargs):
        """Enregistre des métriques ponctuelles sans timing."""
        self._etapes.setdefault(nom, {}).update(kwargs)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def exporter(self, chemin: str | None = None) -> dict:
        """Exporte les métriques dans un fichier JSON.

        Returns:
            Le dictionnaire de métriques exporté.
        """
        duree_totale = round(time.time() - self._debut_run, 2)
        rapport = {
            "run_id": self._run_id,
            "duree_totale_s": duree_totale,
            "etapes": self._etapes,
        }

        if chemin is None:
            os.makedirs("logs", exist_ok=True)
            chemin = f"logs/metriques_{self._run_id}.json"

        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)

        _log.info("Métriques exportées → %s (durée totale: %.1fs)", chemin, duree_totale)
        return rapport

    def resume_texte(self) -> str:
        """Retourne un résumé formaté pour inclusion dans le rapport final."""
        lignes = [f"Run ID : {self._run_id}"]
        lignes.append(f"Durée totale : {round(time.time() - self._debut_run, 1)}s")
        lignes.append("")
        lignes.append("Détail par étape :")
        for nom, data in self._etapes.items():
            duree = data.get("duree_s", "n/a")
            extras = {
                k: v
                for k, v in data.items()
                if k not in ("debut", "fin", "duree_s")
            }
            extra_str = "  |  ".join(f"{k}: {v}" for k, v in extras.items())
            lignes.append(f"  {nom:<25} {str(duree):>6}s   {extra_str}")
        return "\n".join(lignes)


# ---------------------------------------------------------------------------
# Singleton de run — réinitialisé à chaque appel de reset()
# ---------------------------------------------------------------------------
_instance: PipelineMetrics = PipelineMetrics()


def get_metrics() -> PipelineMetrics:
    """Retourne l'instance globale de métriques pour le run courant."""
    return _instance


def reset_metrics() -> PipelineMetrics:
    """Crée une nouvelle instance (à appeler au début de chaque run)."""
    global _instance
    _instance = PipelineMetrics()
    return _instance
