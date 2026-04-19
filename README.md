# SMA de Recrutement Automatise — LangGraph

Systeme Multi-Agents (SMA) de recrutement automatise. A partir d'une fiche de poste, le systeme pilote de facon autonome la recherche, l'evaluation et le premier contact avec les candidats.

Projet realise dans le cadre d'un TER (Travail d'Etude et de Recherche) de Master IA & Data.

---

## Table des matieres

1. [Architecture generale](#1-architecture-generale)
2. [Les agents](#2-les-agents)
3. [Patterns SMA implementes](#3-patterns-sma-implementes)
4. [Structure du projet](#4-structure-du-projet)
5. [GraphState — Le tableau noir](#5-graphstate--le-tableau-noir)
6. [Flux de donnees detaille](#6-flux-de-donnees-detaille)
7. [Sources de candidats](#7-sources-de-candidats)
8. [Memoire RAG](#8-memoire-rag)
9. [Observabilite](#9-observabilite)
10. [Installation](#10-installation)
11. [Utilisation](#11-utilisation)
12. [Configuration](#12-configuration)
13. [Docker](#13-docker)
14. [Tests](#14-tests)
15. [Gitflow](#15-gitflow)

---

## 1. Architecture generale

```
Fiche de poste (input)
        |
      START
        |
   A1 Orchestrateur          <- Superviseur, coordonne le flux
        |
   A2 Analyste               <- Extrait hard/soft skills, contraintes
        |
   A3a Stratege              <- LLM genere les requetes par source
        |
   A3b Collecteur            <- DDG + GitHub API + Stack Overflow API
        |
   A3c Filtre                <- Anti-bruit algorithmique + scraping
        |
   A6 Deduplicateur          <- Fusionne les profils identiques
        |
   +----+----+
   A4  A4  A4  ... (xN)      <- Evaluateurs paralleles via Send()
                                 + contexte RAG (profils similaires)
   +----+----+
        |
   reduce_scores              <- Fan-in, synchronisation
        |
   A5 Verificateur            <- Validation pair-a-pair, CV gonfles
        |
   +----+--------+
   |             |
  >=75        <75 viable    <40
   |             |            |
  A7          A7 (top-3)   Rapport
  Contact      relatif
   |             |
   +------+------+
          |
       Rapport               <- Stats, classement, recommandations
          |
   A8 Persistance            <- Stocke les candidats en base RAG
          |
         END -> rapport_final
```

Le graphe est construit avec `langgraph.graph.StateGraph`. Chaque agent est un noeud, chaque flux de donnees est une arete. Les decisions de routage sont des aretes conditionnelles explicites.

---

## 2. Les agents

| Agent | Fichier | Role | Pattern SMA |
|-------|---------|------|-------------|
| **A1 Orchestrateur** | `orchestrateur.py` | Initialise le pipeline, produit le rapport final | Superviseur |
| **A2 Analyste** | `analyste.py` | Extrait hard skills, soft skills, contraintes, mots-cles | Publie sur blackboard |
| **A3a Stratege** | `chercheur_stratege.py` | LLM genere les requetes optimisees par source | Cognitif (LLM) |
| **A3b Collecteur** | `chercheur_collecteur.py` | Collecte DDG + GitHub API + Stack Overflow API | Operationnel (APIs) |
| **A3c Filtre** | `chercheur_filtre.py` | Filtre bruit algorithmique + scraping BeautifulSoup | Algorithmique |
| **A4 Evaluateur (xN)** | `evaluateur.py` | Score multicriteres 0-100 + contexte RAG | Map-Reduce via Send() |
| **A5 Verificateur** | `verificateur.py` | Verifie coherence, detecte CV gonfles, invalide faux profils | Validation pair-a-pair |
| **A6 Deduplicateur** | `deduplicateur.py` | Fusionne les doublons par nom (>0.85) et URL | Utilitaire transversal |
| **A7 Recruteur** | `recruteur.py` | Redige les messages de contact personnalises | Reactif evenementiel |
| **A8 Persistance** | `persistance.py` | Stocke les candidats valides dans ChromaDB | Memoire inter-runs |

---

## 3. Patterns SMA implementes

### 3.1 Blackboard (Tableau noir)

Le `GraphState` est l'implementation du tableau noir SMA. Chaque agent a ses champs dedies en ecriture. Zero couplage direct entre agents.

| Champ | Ecrit par | Lu par |
|-------|-----------|--------|
| `fiche_poste` | Input | A1, A2 |
| `profil_competences` | A2 | A3a, A4 |
| `requetes_recherche` | A3a | A3b |
| `resultats_bruts` | A3b | A3c |
| `profils_bruts` | A3c | A6 |
| `profils_dedupliques` | A6 | A4(xN) |
| `candidats_scores` | A4 | A5 |
| `candidats_valides` | A5 | A1, A7, A8 |
| `messages_envoyes` | A7 | A1 |
| `rapport_final` | A1 | Recruteur humain |

### 3.2 Superviseur

A1 coordonne le flux via le graphe lui-meme (topologie etoile). Il initie le pipeline et produit le rapport final.

### 3.3 Send() / Map-Reduce

Apres la deduplication, `Send()` cree N instances paralleles d'A4. Chaque instance traite un seul candidat. Le reducer `operator.add` sur `candidats_scores` fusionne les resultats sans conflit.

```python
def route_to_evaluateurs(state):
    return [
        Send("evaluateur", {"candidat": c, "profil_competences": state["profil_competences"]})
        for c in state["profils_dedupliques"][:MAX_PROFILS_PARALLELES]
    ]
```

### 3.4 Validation pair-a-pair

A4 produit, A5 controle independamment. A5 recoit les scores + les profils bruts originaux pour croisement.

### 3.5 Routage conditionnel (absolu + relatif)

```
score >= SCORE_SEUIL_CONTACT (75)    -> A7 contacte directement
score >= SCORE_SEUIL_VIABLE (40)     -> A7 contacte en mode "relatif" (top-3)
score < SCORE_SEUIL_VIABLE           -> rapport sans contact
```

Evite le cas "tous les candidats sont a 68 → personne contacte".

### 3.6 Human-in-the-loop

`interrupt_before=["recruteur"]` arrete le graphe avant A7. Le recruteur humain valide (ou refuse) avant l'envoi des messages.

### 3.7 Memoire contextuelle (RAG)

A4 interroge ChromaDB avant de scorer pour calibrer par rapport aux evaluations passees. A8 persiste les resultats apres chaque run. Le systeme s'ameliore avec le temps.

---

## 4. Structure du projet

```
TER_M1_Agentic_AI/
|-- README.md
|-- BACKLOG.md
|-- requirements.txt
|-- Dockerfile
|-- docker-compose.yml
|-- .env.example
|-- .gitignore
|-- src/
|   |-- __init__.py
|   |-- config.py              # Configuration via env vars
|   |-- state.py               # GraphState = blackboard SMA
|   |-- prompts.py             # Prompts systeme des agents LLM
|   |-- graph.py               # Construction du StateGraph
|   |-- main.py                # Point d'entree CLI
|   |-- logger.py              # Logging structure
|   |-- observabilite.py       # Metriques timing/counts par noeud
|   |-- agents/
|   |   |-- orchestrateur.py   # A1 — Superviseur + rapport + reduce
|   |   |-- analyste.py        # A2 — Analyse fiche de poste
|   |   |-- chercheur_stratege.py   # A3a — LLM genere les requetes
|   |   |-- chercheur_collecteur.py # A3b — DDG + GitHub API + SO API
|   |   |-- chercheur_filtre.py     # A3c — Anti-bruit + scraping
|   |   |-- deduplicateur.py   # A6 — Fusion des doublons
|   |   |-- evaluateur.py      # A4 — Scoring (xN via Send) + RAG
|   |   |-- verificateur.py    # A5 — Validation pair-a-pair
|   |   |-- recruteur.py       # A7 — Contact candidats
|   |   `-- persistance.py     # A8 — Persistance RAG
|   `-- tools/
|       |-- search.py          # DuckDuckGo (web, LinkedIn, CV sites)
|       |-- scraping.py        # Extraction HTML BeautifulSoup
|       |-- github_api.py      # GitHub Search Users API (gratuit)
|       |-- stackoverflow_api.py # Stack Overflow API (gratuit)
|       `-- rag.py             # ChromaDB wrapper (memoire vectorielle)
|-- tests/
|   |-- test_filtre.py         # Tests A3c filtrage anti-bruit
|   |-- test_deduplicateur.py  # Tests A6 deduplication
|   |-- test_rag.py            # Tests memoire RAG
|   `-- test_graph.py          # Tests structure graphe + routage
`-- data/
    `-- chromadb/              # Base vectorielle persistante (auto-cree)
```

---

## 5. GraphState — Le tableau noir

```python
class GraphState(TypedDict):
    fiche_poste: str
    profil_competences: dict
    requetes_recherche: dict          # A3a -> A3b
    resultats_bruts: list[dict]       # A3b -> A3c (hits bruts)
    profils_bruts: Annotated[list[Candidat], operator.add]
    profils_dedupliques: list[Candidat]
    candidats_scores: Annotated[list[CandidatScore], operator.add]
    candidats_valides: list[CandidatValide]
    messages_envoyes: Annotated[list[dict], operator.add]
    rapport_final: str
    messages: Annotated[list, add_messages]
```

Les champs `Annotated[list, operator.add]` sont des reducers : N instances d'A4 ecrivent en parallele sans conflit.

---

## 6. Flux de donnees detaille

```
1. Input : fiche_poste (texte libre)
2. A1    : log la fiche, demarre le pipeline
3. A2    : fiche_poste -> LLM -> profil_competences {hard_skills, soft_skills, ...}
4. A3a   : profil_competences -> LLM -> requetes_recherche {generales, linkedin, github, cv_sites, tags_so}
5. A3b   : requetes_recherche -> DDG + GitHub API + SO API -> resultats_bruts (hits dedupliques par URL)
6. A3c   : resultats_bruts -> pre-filtre URL + mots-cles -> scraping -> post-filtre -> profils_bruts
7. A6    : profils_bruts -> SequenceMatcher (seuil 0.85) -> profils_dedupliques
8. A4xN  : Send() -> pour chaque profil : RAG context + LLM -> CandidatScore (0-100)
9. reduce: fan-in, synchronisation des N scores
10. A5   : candidats_scores + profils_bruts -> LLM -> candidats_valides {valide/invalide/douteux}
11. Route: score >= 75 -> A7 | score 40-75 -> A7 top-3 | score < 40 -> rapport
12. A7   : candidats_valides + fiche_poste -> LLM -> messages_envoyes
13. A1   : toutes donnees -> LLM -> rapport_final (stats + classement)
14. A8   : candidats_valides -> ChromaDB (persistance pour runs futurs)
```

---

## 7. Sources de candidats

Toutes gratuites, sans abonnement.

| Source | Outil | Quota | Token optionnel |
|--------|-------|-------|-----------------|
| Web general | DuckDuckGo | Illimite | Non |
| LinkedIn | DuckDuckGo site:linkedin.com/in | Illimite | Non |
| Sites CV (malt.fr, doyoubuzz.com) | DuckDuckGo site: | Illimite | Non |
| GitHub | API officielle Search Users | 60 req/h (5000 avec token gratuit) | `GITHUB_TOKEN` |
| Stack Overflow | API officielle | 300 req/jour (10000 avec cle gratuite) | `STACKOVERFLOW_KEY` |

**Obtenir les tokens gratuits :**
- GitHub : github.com/settings/tokens → "Generate new token (classic)" → aucun scope requis
- Stack Overflow : stackapps.com/apps/oauth/register → gratuit

---

## 8. Memoire RAG

Le systeme maintient une memoire vectorielle persistante entre les runs.

**Technologie :** ChromaDB (local) + SentenceTransformers `all-MiniLM-L6-v2` (~80 MB, telecharge une fois)

**Fonctionnement :**
- **A4 (lecture)** : avant de scorer un candidat, recupere les 2 profils les plus similaires
  des runs precedents pour calibrer l'evaluation
- **A8 (ecriture)** : apres chaque run, stocke les candidats valides (non invalides) en base

**Persistance :** `./data/chromadb/` (cree automatiquement, monte comme volume Docker)

Le premier run s'effectue sans contexte. A partir du second run sur des postes similaires,
A4 beneficie de references calibrees.

---

## 9. Observabilite

Chaque noeud enregistre son timing et ses metriques metier via `src/observabilite.py`.

**Export automatique** apres chaque run : `logs/metriques_YYYYMMDD_HHMMSS.json`

```json
{
  "run_id": "20260419_143022",
  "duree_totale_s": 187.4,
  "etapes": {
    "A2_analyste":    {"duree_s": 3.2, "n_hard_skills": 8, "n_soft_skills": 3},
    "A3a_stratege":   {"duree_s": 4.1, "n_requetes": 9},
    "A3b_collecteur": {"duree_s": 12.3, "n_bruts": 42, "n_apres_dedup": 31},
    "A3c_filtre":     {"duree_s": 38.7, "n_entree": 31, "n_sortie": 8, "taux_bruit": 0.74},
    "A6_deduplicateur": {"duree_s": 0.1, "n_entree": 8, "n_sortie": 7, "n_doublons": 1},
    "A4_xxxx":        {"duree_s": 9.2, "nom": "Alice Dupont", "score": 82.0},
    "A5_verificateur":{"duree_s": 11.4, "n_valides": 2, "n_douteux": 3, "n_invalides": 2},
    "A7_recruteur":   {"duree_s": 6.8, "n_messages": 2, "mode": "absolu"},
    "A8_persistance": {"duree_s": 0.3, "n_persistes": 2, "total_base": 5},
    "routage":        {"decision": "recruteur", "mode": "absolu", "meilleur_score": 82.0}
  }
}
```

---

## 10. Installation

### Prerequis

- Python 3.11+
- [Ollama](https://ollama.ai/) installe et en cours d'execution
- Modele LLM disponible : `ollama pull kimi-k2.5:cloud`

### Etapes

```bash
git clone <url-du-repo>
cd TER_M1_Agentic_AI

python -m venv venv
source venv/bin/activate    # Windows : venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env        # puis editer .env avec vos tokens
```

### Dependances principales

| Package | Role |
|---------|------|
| `langgraph` | Framework graphe multi-agents |
| `langchain-classic` | `init_chat_model`, outils LangChain |
| `langchain-ollama` | Integration LLM Ollama |
| `ddgs` | Recherche DuckDuckGo |
| `beautifulsoup4` | Extraction HTML |
| `requests` | Appels APIs (GitHub, Stack Overflow) |
| `chromadb` | Base vectorielle locale (RAG) |
| `sentence-transformers` | Embeddings (all-MiniLM-L6-v2) |

---

## 11. Utilisation

```bash
source venv/bin/activate

# Avec human-in-the-loop (pause avant envoi des messages)
python -m src.main "Developpeur Python senior, 5 ans, Machine Learning, Paris"

# Mode automatique
python -m src.main --no-interrupt "Data Scientist ML, 3 ans, teletravail"

# Depuis un fichier
python -m src.main --fichier fiche_poste.txt
```

### Exemple de fiche de poste

```
Developpeur Python Senior – Machine Learning & NLP

Entreprise : DataFlow Solutions, startup IA, 45 collaborateurs.

Missions :
- Developper des modeles ML (NLP, detection de fraude)
- Concevoir des pipelines de donnees temps reel
- Industrialiser via APIs REST et microservices

Competences requises :
- Python (5 ans minimum), PyTorch ou TensorFlow, scikit-learn
- NLP : transformers, spaCy, NLTK
- Docker, Git, CI/CD

Conditions : CDI, Paris ou full-remote, 55-70K euros
```

---

## 12. Configuration

Toutes les valeurs sont surchargeables via variables d'environnement (fichier `.env`).

| Variable | Defaut | Description |
|----------|--------|-------------|
| `OLLAMA_MODEL` | `kimi-k2.5:cloud` | Modele LLM |
| `OLLAMA_PROVIDER` | `ollama` | Provider LangChain |
| `OLLAMA_HOST` | `http://localhost:11434` | URL serveur Ollama |
| `GITHUB_TOKEN` | _(vide)_ | Token GitHub (optionnel, augmente quota) |
| `STACKOVERFLOW_KEY` | _(vide)_ | Cle SO (optionnel, augmente quota) |
| `CHROMADB_DIR` | `./data/chromadb` | Dossier persistance RAG |
| `SCORE_SEUIL_CONTACT` | `75` | Score minimum pour contact direct |
| `SCORE_SEUIL_VIABLE` | `40` | Score minimum pour contact relatif |
| `TOP_N_RELATIF` | `3` | Nb candidats en mode relatif |
| `MAX_PROFILS_RECHERCHE` | `15` | Limite de profils collectes par A3c |
| `MAX_PROFILS_PARALLELES` | `10` | Limite d'evaluateurs paralleles (A4) |

---

## 13. Docker

```bash
# Copier la config
cp .env.example .env

# Lancer Ollama + SMA
docker-compose up --build

# Dans un autre terminal, executer un run
docker-compose exec sma python -m src.main "Dev Python senior, Paris"
```

Les metriques sont exportees dans `./logs/` et la base RAG dans `./data/`.

---

## 14. Tests

```bash
source venv/bin/activate
pip install pytest
pytest tests/ -v
```

Les tests couvrent (sans LLM, sans Ollama) :
- Filtrage anti-bruit A3c (`test_filtre.py`)
- Deduplication A6 (`test_deduplicateur.py`)
- Memoire RAG ChromaDB (`test_rag.py`)
- Structure du graphe et routage conditionnel (`test_graph.py`)

---

## 15. Gitflow

```
main                     <- stable, merge par PR uniquement
  |
  +-- feat/sourcing      <- A3a/b/c, APIs, filtrage
  +-- feat/scoring       <- A4 bareme, A5 verification
  +-- feat/rag           <- ChromaDB, persistance
  `-- feat/...
```

**Regles :**
- Jamais de push direct sur `main`
- Chaque feature = une branche `feat/xxx`
- Integration dans main par Pull Request avec review
