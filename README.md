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
                                                └─► Reduce scores
                                                      └─► [Send × N] A5 Vérificateur (parallèle)
                                                            └─► Reduce validations
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
| Send / Map-Reduce | A4 évalue N candidats en parallèle, A5 vérifie N scores en parallèle (`Send()`) |
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

### Persistance des runs
- Les runs API sont persistés dans SQLite (`./data/runs.sqlite` par défaut)
- L'historique reste disponible après redémarrage de l'API
- Un run interrompu par redémarrage est marqué en erreur pour éviter un faux blocage

### API Gateway (FastAPI)
Expose le SMA comme un service REST :

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/recruter` | Lance un pipeline avec une fiche de poste |
| `GET` | `/rapport/{run_id}` | Récupère le rapport d'un run |
| `GET` | `/runs` | Liste tous les runs |
| `GET` | `/runs/{run_id}/stream` | Flux SSE live du pipeline |
| `POST` | `/runs/{run_id}/hitl` | Décision human-in-the-loop |
| `GET` | `/metrics` | Métriques courantes et exports JSON |
| `GET` | `/rag` | État de la mémoire RAG |
| `GET` | `/health` | Health check |

Documentation interactive : `http://localhost:8000/docs`

### Interface graphique (NiceGUI)
Une UI web permet de lancer un run, suivre la timeline live, visualiser le graphe Mermaid, gérer le HITL, consulter les rapports, la mémoire RAG et les métriques.

Interface : `http://localhost:8080`

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
| Interface graphique | NiceGUI |
| Conteneurisation | Docker + docker-compose |

---

## Installation

### Prérequis
- Python 3.11+
- [Ollama](https://ollama.com) installé
- Un modèle Ollama disponible localement ou accessible via Ollama Cloud

```bash
ollama pull mistral
# ou un autre modèle compatible :
# ollama pull llama3.1
# ollama pull qwen2.5
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

## Lancement rapide

### 1. Démarrer Ollama

Dans un terminal séparé, si Ollama n'est pas déjà lancé :

```bash
ollama serve
```

Vérifier que le serveur répond :

```bash
curl http://localhost:11434/api/tags
```

### 2. Choisir le modèle

Dans `.env`, modifier :

```env
OLLAMA_MODEL=mistral
OLLAMA_PROVIDER=ollama
```

Le modèle doit exister dans Ollama :

```bash
ollama list
ollama pull mistral
```

### 3. Lancer API + UI en une commande

```bash
./run_local.sh
```

Puis ouvrir :

- UI : `http://localhost:8080`
- API docs : `http://localhost:8000/docs`

Arrêt propre : `Ctrl+C` dans le terminal qui a lancé `./run_local.sh`.

Les logs sont dans :

```bash
tail -f logs/api_local.log
tail -f logs/ui_local.log
```

---

## Modes d'utilisation

### Mode CLI

```bash
ollama serve

OLLAMA_MODEL=mistral python3 -m src.main --no-interrupt "Développeur Python senior, 5 ans, Paris"

# Avec human-in-the-loop
OLLAMA_MODEL=mistral python3 -m src.main "Développeur Python senior, 5 ans, Paris"

# Depuis un fichier
OLLAMA_MODEL=mistral python3 -m src.main --fichier fiche_poste.txt
```

Le mode CLI est utile pour tester rapidement le graphe sans interface. Pour la démo, utiliser plutôt l'UI.

### Mode API REST

```bash
source venv/bin/activate
uvicorn src.api:app --reload --port 8000

curl -X POST http://localhost:8000/recruter \
  -H "Content-Type: application/json" \
  -d '{"fiche_poste": "Développeur Python senior, 5 ans, Paris"}'

curl http://localhost:8000/rapport/<run_id>
```

Si `OLLAMA_HOST` n'est pas défini, le projet utilise `http://localhost:11434` par défaut.

### Mode UI local manuel

Normalement, utiliser `./run_local.sh`. Si besoin de lancer manuellement :

Terminal 1 :

```bash
source venv/bin/activate
uvicorn src.api:app --reload --port 8000
```

Terminal 2 :

```bash
source venv/bin/activate
API_URL=http://localhost:8000 python3 -m src.ui.app
```

L'UI sera disponible sur `http://localhost:8080`.

### Mode UI local en une commande

```bash
./run_local.sh
```

Le script lance l'API sur `http://localhost:8000` et l'UI sur `http://localhost:8080`.

Ports personnalisés si besoin :

```bash
API_PORT=8001 UI_PORT=8081 ./run_local.sh
```

### Via Docker

```bash
cp .env.example .env
# modifier OLLAMA_MODEL dans .env si besoin
docker compose up --build
```

L'API est accessible sur `http://localhost:8000` et l'UI sur `http://localhost:8080`.

Si les ports locaux sont déjà utilisés par un lancement manuel :

```bash
API_PORT=8001 UI_PORT_HOST=8081 docker compose up --build
```

L'API Docker sera alors sur `http://localhost:8001` et l'UI Docker sur `http://localhost:8081`.

Commandes Docker utiles :

```bash
docker compose ps
docker compose logs -f sma-api
docker compose logs -f sma-ui
docker compose down
```

Le service Docker `ollama` monte `~/.ollama` dans le conteneur. Les modèles déjà téléchargés sur la machine hôte sont donc réutilisés.

### Mode CLI via Docker

```bash
docker compose --profile cli run --rm sma-cli python -m src.main --no-interrupt "Développeur Python senior, Paris"
```

---

## Changer de modèle LLM

Le modèle est choisi avec `OLLAMA_MODEL`.

### En local

1. Télécharger le modèle :

```bash
ollama pull mistral
```

2. Modifier `.env` :

```env
OLLAMA_MODEL=mistral
OLLAMA_PROVIDER=ollama
```

3. Relancer le projet :

```bash
./run_local.sh
```

### Pour une seule commande

```bash
OLLAMA_MODEL=mistral ./run_local.sh
OLLAMA_MODEL=mistral python3 -m src.main --no-interrupt "Développeur Python senior Paris"
```

### Avec Docker

Modifier `.env`, puis relancer :

```bash
docker compose up --build
```

### Modèles conseillés

| Modèle | Usage |
|---|---|
| `mistral` | Léger, rapide, correct pour tester |
| `llama3.1` | Meilleure qualité générale si disponible |
| `qwen2.5` | Bon respect du JSON selon les versions |
| `kimi-k2.5:cloud` | Qualité plus élevée si Ollama Cloud est configuré |

Important : A4 et A5 exigent des réponses JSON. Si un modèle ne respecte pas le JSON, le run peut échouer explicitement, surtout sur A5. Dans ce cas, essayer un modèle plus fiable en sortie structurée.

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
| `RUNS_DB_PATH` | `data/runs.sqlite` | Base SQLite des runs API |
| `CHROMADB_DIR` | `data/chromadb` | Base vectorielle RAG |
| `API_URL` | `http://localhost:8000` | URL API utilisée par l'UI |
| `API_PORT` | `8000` | Port API pour `run_local.sh` |
| `UI_PORT` | `8080` | Port UI pour `run_local.sh` |
| `UI_PORT_HOST` | `8080` | Port UI exposé par Docker |

---

## Dépannage

### `Connection refused` vers Ollama

Vérifier qu'Ollama tourne :

```bash
ollama serve
curl http://localhost:11434/api/tags
```

En Docker, l'API doit utiliser `OLLAMA_HOST=http://ollama:11434`, déjà défini dans `docker-compose.yml`.

### Le modèle n'existe pas

```bash
ollama list
ollama pull mistral
```

Puis mettre le même nom dans `.env`.

### Ports déjà utilisés

Local :

```bash
API_PORT=8001 UI_PORT=8081 ./run_local.sh
```

Docker :

```bash
API_PORT=8001 UI_PORT_HOST=8081 docker compose up --build
```

### Voir pourquoi un run a échoué

```bash
tail -f logs/api_local.log
tail -f logs/ui_local.log
```

Depuis l'UI, consulter aussi la timeline du run et le statut `run_error`.

### Réinitialiser les données locales

Supprimer l'historique des runs et la mémoire RAG :

```bash
rm -rf data/runs.sqlite data/chromadb
```

Ne pas le faire si vous voulez conserver l'historique ou la mémoire de calibration.

---

## Tests

```bash
source venv/bin/activate
python3 -m pytest tests/ -v
```

Tests rapides utiles pendant le développement :

```bash
python3 -m pytest tests/test_graph.py tests/test_stratege_queries.py tests/test_verificateur_rules.py -q
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
