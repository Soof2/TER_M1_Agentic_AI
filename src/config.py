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
# Groq est le provider par défaut pour que le projet soit portable via Docker :
# aucune dépendance à un serveur LLM local, seulement GROQ_API_KEY dans .env.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")
if "LLM_MODEL" in os.environ:
    LLM_MODEL = os.environ["LLM_MODEL"]
elif LLM_PROVIDER == "groq":
    LLM_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
else:
    LLM_MODEL = "mistral"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def get_llm(temperature: float = 0):
    """Retourne un LLM avec retry automatique sur rate limit (429)."""
    if LLM_PROVIDER == "groq" and not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY est requis pour utiliser Groq. "
            "Copiez .env.example vers .env puis renseignez GROQ_API_KEY."
        )
    from langchain_classic.chat_models import init_chat_model
    llm = init_chat_model(LLM_MODEL, model_provider=LLM_PROVIDER, temperature=temperature)
    return llm.with_retry(stop_after_attempt=6, wait_exponential_jitter=True)

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
