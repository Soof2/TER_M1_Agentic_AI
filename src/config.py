"""Configuration du système multi-agents de recrutement."""

# Modèle LLM (Ollama cloud)
OLLAMA_MODEL = "kimi-k2.5:cloud"
OLLAMA_PROVIDER = "ollama"

# Seuils de décision après vérification (A5)
SCORE_SEUIL_CONTACT = 75    # score >= 75 → A7 contacte le candidat
SCORE_SEUIL_HUMAIN = 50     # score 50-75 → décision humaine requise
                             # score < 50  → candidat écarté

# Limites
MAX_PROFILS_RECHERCHE = 15   # nombre max de profils bruts collectés par A3
MAX_PROFILS_PARALLELES = 10  # nombre max d'instances parallèles d'A4
