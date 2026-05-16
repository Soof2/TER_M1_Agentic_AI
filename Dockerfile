FROM python:3.11-slim

WORKDIR /app

# Dépendances système pour BeautifulSoup / lxml / sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python en couche séparée (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code source
COPY src/ ./src/
COPY services/ ./services/

# Répertoires pour métriques et persistance RAG
RUN mkdir -p logs data/chromadb

# Variables d'environnement par défaut (surchargeables via docker-compose ou CLI)
ENV LLM_PROVIDER=groq
ENV LLM_MODEL=llama-3.3-70b-versatile
ENV SCORE_SEUIL_CONTACT=75
ENV MAX_PROFILS_RECHERCHE=15

# Par défaut : API REST (peut être surchargé dans docker-compose pour le mode CLI)
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
