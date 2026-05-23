# Système Multi-Agents de Recrutement Automatisé

Prototype développé dans le cadre du TER Master 1 Informatique — Université de Montpellier.

Sujet : **Architectures Logicielles pour l'IA Agentique — Systèmes Multi-Agents, Variabilité Architecturale et Prototype de Recrutement Automatisé**

Encadrant : M. Abdelhak-Djamel Seriai  
Auteurs : Sofiane Hammar, Anouar Soufyani, Souad Hadji

---

## Présentation

Le système prend une fiche de poste en entrée et exécute automatiquement :
1. Extraction du profil de compétences recherché (A2)
2. Recherche de candidats sur DuckDuckGo, GitHub et Stack Overflow (A3)
3. Déduplication et filtrage anti-bruit (A3c, A6)
4. Évaluation et scoring de chaque candidat par LLM (A4, parallèle)
5. Vérification indépendante des scores (A5, parallèle)
6. Injection de candidats connus depuis la mémoire RAG
7. Validation humaine obligatoire avant tout contact (HITL)
8. Rédaction de messages de contact (A7)
9. Persistance en mémoire vectorielle pour les runs suivants (A8)

---

## Lancement

### Prérequis

- Docker installé, ou Python 3.11+ avec `pip`
- Une clé API [Groq](https://console.groq.com) (gratuite, sans CB)

```bash
cp .env.example .env
# Renseigner GROQ_API_KEY=gsk_... dans .env
```

### Mode LangGraph monolithique (recommandé)

```bash
docker compose up --build
```

Ou sans Docker :

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./run_local.sh
```

### Mode microservices Docker

```bash
docker compose -f docker-compose.microservices.yml up --build
```

### Accès

| Service | URL |
|---|---|
| Interface web | http://localhost:8080 |
| API REST | http://localhost:8000 |
| Documentation API | http://localhost:8000/docs |

---

## Architecture

Le pipeline est un graphe LangGraph de 10 agents :

```
START → A1 → A2 → A3a → A3b → A3c → A6
                                      └─► [Send × N] A4 → reduce
                                                           └─► [Send × N] A5 → reduce
                                                                                └─► injection_rag
                                                                                      ├─► A7 → rapport → A8 → END
                                                                                      └─► rapport → A8 → END
```

**Deux modes d'exécution :**
- **LangGraph monolithique** : graphe d'état typé, HITL natif (`interrupt_before`), fan-out parallèle via `Send()`, checkpointing `MemorySaver`
- **Microservices Docker** : 6 services FastAPI indépendants orchestrés via HTTP, HITL via `asyncio.Event` + polling

---

## Fonctionnalités principales

### Mémoire RAG (ChromaDB)
- **Cache de score** : évite de réévaluer un candidat déjà scoré (A4)
- **Injection proactive** : réinjecte les candidats validés lors de runs précédents
- **Blacklist** : exclut les profils déjà rejetés de la collecte (A3c)

### Human-in-the-Loop (HITL)
Pause obligatoire avant A7 : l'opérateur peut approuver, rejeter ou modifier la liste des candidats retenus avant tout message de contact.

### Observabilité
- Métriques par nœud exportées en JSON (`logs/`)
- Historique des runs en SQLite (`data/runs.sqlite`)
- Interface web avec timeline live (SSE)

---

## Stack technique

| Composant | Technologie |
|---|---|
| Orchestration agents | LangGraph |
| LLM | Groq `llama-3.3-70b-versatile` |
| Recherche web | DuckDuckGo (ddgs) |
| Recherche profils | GitHub Search Users API + Stack Exchange API |
| Mémoire vectorielle | ChromaDB + SentenceTransformers |
| API REST | FastAPI + Uvicorn |
| Interface graphique | NiceGUI |
| Conteneurisation | Docker Compose |

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `GROQ_API_KEY` | *(obligatoire)* | Clé API Groq |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Modèle Groq |
| `SCORE_SEUIL_CONTACT` | `75` | Score minimum pour contacter un candidat |
| `SCORE_SEUIL_VIABLE` | `40` | Score minimum mode relatif |
| `TOP_N_RELATIF` | `3` | Nombre de candidats en mode relatif |
| `MAX_PROFILS_PARALLELES` | `10` | Évaluateurs parallèles max |
| `GITHUB_TOKEN` | *(optionnel)* | 5000 req/h au lieu de 60 |
| `STACKOVERFLOW_KEY` | *(optionnel)* | Clé Stack Exchange API |
| `CHROMADB_DIR` | `data/chromadb` | Base vectorielle RAG |
| `RUNS_DB_PATH` | `data/runs.sqlite` | Historique des runs |

---

## Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

97 tests automatisés couvrant : routage conditionnel, HITL, RAG, filtre anti-bruit, déduplication, API REST.

---

## Structure du projet

```
src/
├── agents/
│   ├── orchestrateur.py        # A1
│   ├── analyste.py             # A2
│   ├── chercheur_stratege.py   # A3a
│   ├── chercheur_collecteur.py # A3b
│   ├── chercheur_filtre.py     # A3c
│   ├── deduplicateur.py        # A6
│   ├── evaluateur.py           # A4
│   ├── verificateur.py         # A5
│   ├── recruteur.py            # A7
│   └── persistance.py          # A8
├── tools/
│   ├── search.py               # DuckDuckGo
│   ├── github_api.py           # GitHub Search API
│   ├── stackoverflow_api.py    # Stack Exchange API
│   └── rag.py                  # ChromaDB (MemoireRAG)
├── api.py                      # API Gateway FastAPI
├── graph.py                    # Graphe LangGraph
├── state.py                    # GraphState (blackboard)
└── config.py                   # Configuration
services/                       # Mode microservices
tests/                          # 97 tests automatisés
```
