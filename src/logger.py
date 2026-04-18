"""
Logging structuré pour le SMA de recrutement.

Remplace les print() dispersés par des logs formatés avec :
- timestamp ISO
- niveau (INFO / WARNING / ERROR)
- nom de l'agent (ex: "A3_chercheur")
- message

Usage :
    from src.logger import get_logger
    log = get_logger("A3_chercheur")
    log.info("15 profils collectés")
    log.warning("JSON non parsable, fallback activé")
    log.error("Scraping échoué : %s", url)
"""

import logging
import sys


_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)-20s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_FORMATTER)

# Racine du SMA — tous les sous-loggers héritent du niveau et du handler
_root = logging.getLogger("sma")
_root.setLevel(logging.INFO)
if not _root.handlers:
    _root.addHandler(_handler)
_root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger préfixé 'sma.<name>'.

    Args:
        name: Identifiant court de l'agent ou du composant
              (ex: "A3_chercheur", "A4_evaluateur", "graph").

    Returns:
        Logger configuré, prêt à l'emploi.
    """
    return logging.getLogger(f"sma.{name}")
