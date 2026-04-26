"""
Configuration du système multi-agents de recrutement.

Toutes les valeurs sont surchargeables via variables d'environnement.
Créer un fichier .env (voir .env.example) pour la configuration locale.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Modèle LLM
# ---------------------------------------------------------------------------
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "kimi-k2.5:cloud")
OLLAMA_PROVIDER = os.getenv("OLLAMA_PROVIDER", "ollama")

# URL du serveur Ollama (utile en Docker où il tourne dans un autre conteneur)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# ---------------------------------------------------------------------------
# APIs externes
# ---------------------------------------------------------------------------
# GitHub : sans token = 60 req/h, avec token gratuit = 5 000 req/h
# Créer sur https://github.com/settings/tokens (aucun scope requis)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Stack Overflow : sans clé = 300 req/jour, avec clé gratuite = 10 000 req/jour
# Créer sur https://stackapps.com/apps/oauth/register
STACKOVERFLOW_KEY = os.getenv("STACKOVERFLOW_KEY", "")

# ---------------------------------------------------------------------------
# Seuils de décision après vérification (A5)
# ---------------------------------------------------------------------------
SCORE_SEUIL_CONTACT = int(os.getenv("SCORE_SEUIL_CONTACT", "75"))
# score >= seuil  → A7 contacte le candidat directement
SCORE_SEUIL_HUMAIN = int(os.getenv("SCORE_SEUIL_HUMAIN", "50"))
# score 50-seuil  → décision humaine recommandée
# score < 50      → candidat écarté
SCORE_SEUIL_VIABLE = int(os.getenv("SCORE_SEUIL_VIABLE", "40"))
# score minimum pour être proposé en mode relatif (top-N)
TOP_N_RELATIF = int(os.getenv("TOP_N_RELATIF", "3"))
# si aucun >= SCORE_SEUIL_CONTACT, proposer les N meilleurs viables

# ---------------------------------------------------------------------------
# Limites pipeline
# ---------------------------------------------------------------------------
MAX_PROFILS_RECHERCHE = int(os.getenv("MAX_PROFILS_RECHERCHE", "15"))
# nombre max de profils bruts collectés par A3c
MAX_PROFILS_PARALLELES = int(os.getenv("MAX_PROFILS_PARALLELES", "10"))
# nombre max d'instances parallèles d'A4
