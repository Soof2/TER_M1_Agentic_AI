# SMA de Recrutement Automatisé — Agentic AI

Système multi-agents de recrutement basé sur **LangGraph** et **LLM (Ollama)**.  
Prototype développé dans le cadre du TER M1 — *Étude des architectures des logiciels basés sur l'IA et de l'Agentic AI*.

---

## Architecture

Le pipeline est composé de **10 agents spécialisés** orchestrés via un graphe LangGraph :

```
START
  └─► A1 Orchestrateur
        └─► A2 Analyste          (extraction profil de compétences)
              └─► A3a Stratège   (génération de requêtes par LLM)
                    └─► A3b Collecteur  (DDG + GitHub API + Stack Overflow API)
                          └─► A3c Filtre  (anti-bruit algorithmique)
                                └─► A6 Déduplicateur
                                      └─► [Send × N] A4 Évaluateur  (parallèle)
                                                └─► Reduce
                                                      └─► A5 Vérificateur
                                                            ├─► A7 Recruteur
                                                            └─► Rapport
                                                                  └─► A8 Persistance RAG
                                                                        └─► END
```

### Patterns SMA implémentés
| Pattern | Implémentation |
|---|---|
| Superviseur | A1 coordonne via le flux du graphe |
| Blackboard | `GraphState` TypedDict partagé entre agents |
| Send / Map-Reduce | A4 évalue N candidats en parallèle (`Send()`) |
| Validation pair-à-pair | A4 produit → A5 contrôle |
| Routage conditionnel | Score > seuil → A7 / rapport |
| Human-in-the-loop | `interrupt_before` sur A7 |

---

## Fonctionnalités

### Division A3 — Recherche en 3 agents
L'agent Chercheur est divisé en trois agents spécialisés :
- **A3a Stratège** — le LLM génère des requêtes adaptées à chaque source
- **A3b Collecteur** — collecte sur DuckDuckGo, GitHub API et Stack Overflow API (APIs gratuites)
- **A3c Filtre anti-bruit** — élimine algorithmiquement les offres d'emploi (domaines bloqués, 50+ mots-clés, filtrage par chemin URL)

### Mémoire RAG (ChromaDB)
- Stockage vectoriel des candidats évalués (ChromaDB + SentenceTransformers `all-MiniLM-L6-v2`)
- Enrichissement de l'évaluation A4 avec les profils similaires des runs précédents
- Persistance dans `./data/chromadb/`

### Observabilité
- `PipelineMetrics` — mesure du temps d'exécution et métriques métier par nœud
- Export JSON automatique dans `logs/metriques_YYYYMMDD_HHMMSS.json`
- Résumé inclus dans le rapport final

### API Gateway (FastAPI)
Expose le SMA comme un service REST :

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/recruter` | Lance un pipeline avec une fiche de poste |
| `GET` | `/rapport/{run_id}` | Récupère le rapport d'un run |
| `GET` | `/runs` | Liste tous les runs |
| `GET` | `/health` | Health check |

Documentation interactive : `http://localhost:8000/docs`

---

## Stack technique

| Composant | Technologie |
|---|---|
| Orchestration agents | LangGraph |
| LLM | Ollama (kimi-k2.5:cloud, mistral, phi…) |
| Recherche web | DuckDuckGo (ddgs) |
| Recherche GitHub | GitHub Search Users API (gratuit) |
| Recherche Stack Overflow | Stack Exchange API (gratuit) |
| Mémoire vectorielle | ChromaDB + SentenceTransformers |
| API REST | FastAPI + Uvicorn |
| Conteneurisation | Docker + docker-compose |

---

## Installation

### Prérequis
- Python 3.11+
- [Ollama](https://ollama.com) installé et un modèle téléchargé

```bash
ollama pull mistral
```

### Setup

```bash
git clone <repo>
cd TER_M1_Agentic_AI

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

---

## Utilisation

### Mode CLI

```bash
ollama serve

OLLAMA_MODEL=mistral python3 -m src.main --no-interrupt "Développeur Python senior, 5 ans, Paris"

# Avec human-in-the-loop
OLLAMA_MODEL=mistral python3 -m src.main "Développeur Python senior, 5 ans, Paris"

# Depuis un fichier
OLLAMA_MODEL=mistral python3 -m src.main --fichier fiche_poste.txt
```

### Mode API REST

```bash
OLLAMA_HOST=http://localhost:11434 uvicorn src.api:app --reload --port 8000

curl -X POST http://localhost:8000/recruter \
  -H "Content-Type: application/json" \
  -d '{"fiche_poste": "Développeur Python senior, 5 ans, Paris"}'

curl http://localhost:8000/rapport/<run_id>
```

### Via Docker

```bash
echo "OLLAMA_MODEL=mistral" > .env
docker compose up --build
```

L'API est accessible sur `http://localhost:8000`.

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `OLLAMA_MODEL` | `kimi-k2.5:cloud` | Modèle LLM Ollama |
| `OLLAMA_HOST` | `http://localhost:11434` | URL du serveur Ollama |
| `GITHUB_TOKEN` | *(optionnel)* | Token GitHub (5000 req/h vs 60 sans) |
| `STACKOVERFLOW_KEY` | *(optionnel)* | Clé Stack Exchange API |
| `SCORE_SEUIL_CONTACT` | `75` | Score minimum pour contacter un candidat |
| `SCORE_SEUIL_VIABLE` | `40` | Score minimum pour mode relatif (top-N) |
| `TOP_N_RELATIF` | `3` | Nombre de candidats en mode relatif |
| `MAX_PROFILS_RECHERCHE` | `15` | Nombre max de profils collectés |
| `MAX_PROFILS_PARALLELES` | `10` | Nombre max d'évaluateurs parallèles |

---

## Tests

```bash
python3 -m pytest tests/ -v
```

Couverture : filtre anti-bruit, déduplication, structure du graphe, routage conditionnel, API REST (62 tests).

---

## Structure du projet

```
src/
├── agents/
│   ├── orchestrateur.py        # A1 — coordination + rapport
│   ├── analyste.py             # A2 — extraction compétences
│   ├── chercheur_stratege.py   # A3a — génération requêtes (LLM)
│   ├── chercheur_collecteur.py # A3b — collecte multi-sources
│   ├── chercheur_filtre.py     # A3c — filtre anti-bruit
│   ├── deduplicateur.py        # A6 — fusion doublons
│   ├── evaluateur.py           # A4 — scoring candidats
│   ├── verificateur.py         # A5 — validation scores
│   ├── recruteur.py            # A7 — messages de contact
│   └── persistance.py          # A8 — mémoire RAG
├── tools/
│   ├── search.py               # DuckDuckGo
│   ├── github_api.py           # GitHub Search API
│   ├── stackoverflow_api.py    # Stack Exchange API
│   ├── scraping.py             # Extraction contenu web
│   └── rag.py                  # ChromaDB (MemoireRAG)
├── api.py                      # API Gateway FastAPI
├── graph.py                    # Construction du graphe LangGraph
├── state.py                    # GraphState (blackboard)
├── config.py                   # Configuration centralisée
├── observabilite.py            # PipelineMetrics
├── prompts.py                  # Prompts système des agents
└── main.py                     # Point d'entrée CLI
tests/
├── test_filtre.py
├── test_deduplicateur.py
├── test_graph.py
├── test_rag.py
└── test_api.py
```

---

## Auteurs

Anouar SOUFYANI, Sofiane HAMMAR, Souad HADJI  
Master IA & Data — TER 2025-2026
