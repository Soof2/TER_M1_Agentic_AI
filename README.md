# SMA de Recrutement Automatise — LangGraph

Systeme Multi-Agents (SMA) de recrutement automatise. A partir d'une fiche de poste, le systeme pilote de facon autonome la recherche, l'evaluation et le premier contact avec les candidats.

Projet realise dans le cadre d'un TER (Travail d'Etude et de Recherche) de Master IA & Data.

---

## Table des matieres

1. [Architecture generale](#1-architecture-generale)
2. [Les 7 agents](#2-les-7-agents)
3. [Patterns SMA implementes](#3-patterns-sma-implementes)
4. [Structure du projet](#4-structure-du-projet)
5. [GraphState — Le tableau noir](#5-graphstate--le-tableau-noir)
6. [Flux de donnees detaille](#6-flux-de-donnees-detaille)
7. [Installation](#7-installation)
8. [Utilisation](#8-utilisation)
9. [Gitflow — Travail en equipe](#9-gitflow--travail-en-equipe)
10. [Configuration](#10-configuration)
11. [Fonctionnement detaille de chaque agent](#11-fonctionnement-detaille-de-chaque-agent)
12. [Outils (Tools)](#12-outils-tools)
13. [Filtrage anti-bruit](#13-filtrage-anti-bruit)
14. [Routage conditionnel](#14-routage-conditionnel)
15. [Human-in-the-loop](#15-human-in-the-loop)
16. [Logs et suivi en temps reel](#16-logs-et-suivi-en-temps-reel)
17. [Exemple d'execution complete](#17-exemple-dexecution-complete)
18. [Prompts systeme](#18-prompts-systeme)
19. [Limites et pistes d'amelioration](#19-limites-et-pistes-damelioration)

---

## 1. Architecture generale

```
Fiche de poste (input)
        |
      START
        |
   A1 Orchestrateur          ← Superviseur, coordonne le flux
        |
   A2 Analyste               ← Extrait hard/soft skills, contraintes
        |
   A3 Chercheur              ← DDG (web/LinkedIn/GitHub) + filtrage bruit + scraping
        |
   A6 Deduplicateur          ← Fusionne les profils identiques
        |
   ┌────┴────┐
   A4  A4  A4  ... (×N)      ← Evaluateurs paralleles via Send()
   └────┬────┘
        |
   reduce_scores              ← Fan-in, synchronisation
        |
   A5 Verificateur            ← Validation pair-a-pair, detection CV gonfles
        |
   ┌────┼────────┐
   |    |        |
  >=75  50-75   <50           ← Routage conditionnel sur le meilleur score
   |    |        |
  A7   Rapport  Rapport
Contact  (humain)  (fin)
   |
Rapport
   |
  END → rapport_final
```

Le graphe est construit avec `langgraph.graph.StateGraph`. Chaque agent est un noeud, chaque flux de donnees est une arete. Les decisions de routage sont des aretes conditionnelles explicites.

---

## 2. Les 7 agents

| Agent | Code | Role | Pattern SMA |
|-------|------|------|-------------|
| **A1 Orchestrateur** | `src/agents/orchestrateur.py` | Recoit la fiche de poste, coordonne les agents, produit le rapport final | Superviseur (topologie etoile) |
| **A2 Analyste** | `src/agents/analyste.py` | Analyse la fiche de poste, extrait hard skills, soft skills, contraintes, mots-cles | Publie sur le blackboard |
| **A3 Chercheur** | `src/agents/chercheur.py` | Recherche des profils sur LinkedIn, GitHub, web via DuckDuckGo | Communication evenementielle |
| **A4 Evaluateur (×N)** | `src/agents/evaluateur.py` | Score multicriteres pour chaque candidat (0-100) | Map-Reduce via Send() |
| **A5 Verificateur** | `src/agents/verificateur.py` | Verifie coherence des profils, detecte CV gonfles, invalide les faux profils | Validation pair-a-pair |
| **A6 Deduplicateur** | `src/agents/deduplicateur.py` | Fusionne les doublons par similarite de noms et URLs | Agent utilitaire transversal |
| **A7 Recruteur** | `src/agents/recruteur.py` | Redige des messages personnalises pour les meilleurs candidats | Reactivite evenementielle |

---

## 3. Patterns SMA implementes

### 3.1 Blackboard (Tableau noir)

Le `GraphState` (defini dans `src/state.py`) est l'implementation du tableau noir SMA. C'est un etat partage ou chaque agent a ses champs dedies en ecriture. Zero couplage direct entre agents : A2 publie le profil de competences, A3 le lit sans connaitre A2.

**Convention d'ecriture stricte :**

| Champ | Ecrit par | Lu par |
|-------|-----------|--------|
| `fiche_poste` | Input | A1, A2 |
| `profil_competences` | A2 | A3, A4 |
| `profils_bruts` | A3 | A6 |
| `profils_dedupliques` | A6 | A4(×N) |
| `candidats_scores` | A4 | A5 |
| `candidats_valides` | A5 | A1, A7 |
| `messages_envoyes` | A7 | A1 |
| `rapport_final` | A1 | Recruteur humain |

Le write croise est impossible car la contrainte SMA est imposee par l'architecture du graphe, pas par convention.

### 3.2 Superviseur (Coordination centralisee)

A1 est le superviseur. Il ne delegue pas dynamiquement (ce n'est pas un dispatcher) — le flux est formalise dans le graphe lui-meme. A1 initie le pipeline et produit le rapport final. La topologie est en etoile : tous les resultats convergent vers A1.

### 3.3 Send() / Map-Reduce (Parallelisme massif)

Apres la deduplication, le graphe utilise le pattern `Send()` de LangGraph pour creer N instances paralleles d'A4. Chaque instance recoit un state partiel contenant un seul candidat + le profil de competences.

```python
# Dans graph.py — fan-out
def route_to_evaluateurs(state):
    return [
        Send("evaluateur", {
            "candidat": candidat,
            "profil_competences": state["profil_competences"]
        })
        for candidat in state["profils_dedupliques"]
    ]
```

Les resultats sont agreges automatiquement par le reducer `operator.add` sur `candidats_scores`. Le noeud `reduce_scores` sert de point de synchronisation (fan-in).

### 3.4 Validation pair-a-pair

A4 produit les scores, A5 controle independamment. A5 recoit :
- Les scores et resumes d'A4
- Les profils bruts originaux (pour croiser les informations)

A5 peut :
- Ajuster les scores si A4 a surnote
- Invalider les faux profils (offres d'emploi deguisees en candidats)
- Detecter les CV gonfles (incoherences dates/competences)
- Marquer des profils comme "douteux"

La separation est garantie par l'architecture : A4 ecrit dans `candidats_scores`, A5 ecrit dans `candidats_valides`. Pas de write croise possible.

### 3.5 Routage conditionnel

Apres A5, le graphe route conditionnellement :
- Score >= 75 → A7 (contact des candidats)
- Score < 75 → Rapport (pas de contact, decision humaine ou fin)

La logique est declarative, lisible directement dans le graphe (fonction `route_apres_verification` dans `graph.py`).

### 3.6 Human-in-the-loop

Le parametre `interrupt_before=["recruteur"]` arrete le graphe avant que A7 envoie des messages. Le recruteur humain peut :
1. Consulter la liste des candidats valides avec leurs scores
2. Valider la poursuite (→ A7 contacte)
3. Refuser (→ rapport sans contact)

Implemente via le `MemorySaver` checkpointer de LangGraph qui sauvegarde l'etat a chaque etape.

---

## 4. Structure du projet

```
TER/
├── README.md                  # Ce fichier
├── requirements.txt           # Dependances Python
├── test.py                    # Script de demo initial (bind_tools)
├── venv/                      # Environnement virtuel Python
└── src/
    ├── __init__.py
    ├── config.py              # Configuration (modele, seuils, limites)
    ├── state.py               # GraphState = blackboard SMA (TypedDict)
    ├── prompts.py             # Prompts systeme des 7 agents
    ├── graph.py               # Construction du StateGraph LangGraph
    ├── main.py                # Point d'entree CLI
    ├── agents/
    │   ├── __init__.py
    │   ├── orchestrateur.py   # A1 — Superviseur + rapport + reduce
    │   ├── analyste.py        # A2 — Analyse fiche de poste
    │   ├── chercheur.py       # A3 — Recherche de profils web
    │   ├── deduplicateur.py   # A6 — Fusion des doublons
    │   ├── evaluateur.py      # A4 — Scoring (×N via Send)
    │   ├── verificateur.py    # A5 — Validation pair-a-pair
    │   └── recruteur.py       # A7 — Contact candidats
    └── tools/
        ├── __init__.py
        ├── search.py          # Recherche DuckDuckGo (web, LinkedIn, GitHub)
        └── scraping.py        # Extraction de texte depuis pages web
```

---

## 5. GraphState — Le tableau noir

Defini dans `src/state.py`. C'est un `TypedDict` Python avec des reducers `Annotated`.

### Types de donnees

```python
class Candidat(TypedDict):
    id: str              # UUID court (8 chars)
    nom: str             # Nom extrait du profil
    source: str          # "linkedin", "github", "indeed", "web"
    profil_brut: str     # Texte brut du profil
    url: Optional[str]   # URL du profil

class CandidatScore(TypedDict):
    candidat_id: str     # Reference vers Candidat.id
    nom: str
    score_global: float  # 0-100
    scores_detail: dict  # {hard_skills, soft_skills, experience, culture_fit}
    resume: str          # Explication textuelle

class CandidatValide(TypedDict):
    candidat_id: str
    nom: str
    score_final: float   # Score ajuste par A5
    statut: str          # "valide", "invalide", "douteux"
    remarques: str       # Explications, alertes
```

### Reducers

Les champs avec `Annotated[list[X], operator.add]` sont des reducers. Ils permettent a plusieurs instances d'un agent (ex: N evaluateurs paralleles) d'ecrire dans le meme champ sans conflit. Chaque ecriture est concatenee automatiquement.

Champs avec reducer :
- `profils_bruts` — A3 peut accumuler par lots
- `candidats_scores` — N instances d'A4 ecrivent en parallele
- `messages_envoyes` — A7 peut envoyer plusieurs messages
- `messages` — trace LLM (reducer `add_messages`)

---

## 6. Flux de donnees detaille

```
1. Input : fiche_poste (texte libre)
                |
2. A1 : Initialise le pipeline, log la fiche
                |
3. A2 : fiche_poste → LLM → profil_competences (JSON)
        {hard_skills, soft_skills, experience_min, formation, contraintes, mots_cles}
                |
4. A3 : profil_competences → LLM genere des requetes → DuckDuckGo (avec exclusions)
        → dedup URL → pre-filtre domaine + mots-cles → scraping pages → post-filtre
        → profils_bruts (contenu scrape, pas des snippets DDG)
                |
5. A6 : profils_bruts → algorithme de similarite (SequenceMatcher) → profils_dedupliques
        Fusion par nom (seuil 0.85) et URL identique
                |
6. A4 (×N) : Pour chaque profil_deduplique :
              Send({candidat, profil_competences}) → LLM → CandidatScore
              Scores : hard_skills, soft_skills, experience, culture_fit (0-100)
                |
7. reduce : Fan-in, synchronisation des N resultats
                |
8. A5 : candidats_scores + profils_bruts → LLM → candidats_valides
        Croise les profils bruts avec les scores pour detecter les incoherences
                |
9. Routage conditionnel :
        score >= 75 → A7 (contact)
        score < 75  → rapport (fin ou decision humaine)
                |
10. A7 : candidats_valides + fiche_poste → LLM → messages_envoyes
         Messages personnalises par candidat
                |
11. Rapport : Toutes les donnees → LLM → rapport_final
              Resume du poste, stats, classement, recommandations
```

---

## 7. Installation

### Prerequis

- Python 3.10+
- [Ollama](https://ollama.ai/) installe et en cours d'execution
- Un modele disponible dans Ollama (par defaut : `kimi-k2.5:cloud`)

### Etapes

```bash
# Cloner le projet
git clone <url-du-repo>
cd TER

# Creer l'environnement virtuel
python -m venv venv
source venv/bin/activate

# Installer les dependances
pip install -r requirements.txt

# Verifier qu'Ollama tourne et que le modele est disponible
ollama list
```

### Dependances

| Package | Version | Role |
|---------|---------|------|
| `langgraph` | >= 1.1.0 | Framework de graphe multi-agents |
| `langchain-ollama` | >= 1.0.0 | Integration LLM Ollama |
| `langchain-community` | >= 0.4.0 | Outils communautaires LangChain |
| `langchain-classic` | >= 1.0.0 | `init_chat_model`, `@tool` |
| `ddgs` | >= 9.0.0 | Recherche DuckDuckGo |
| `beautifulsoup4` | >= 4.12.0 | Extraction HTML |
| `pydantic` | >= 2.0.0 | Validation de donnees |
| `requests` | >= 2.31.0 | Requetes HTTP |

---

## 8. Utilisation

### Lancement basique (avec human-in-the-loop)

```bash
source venv/bin/activate
python -m src.main "Developpeur Python senior, 5 ans d'experience, Paris, CDI"
```

Le pipeline s'arrete avant A7 (contact) et demande une validation humaine.

### Mode automatique (sans interruption)

```bash
python -m src.main --no-interrupt "Data Scientist ML, 3 ans, teletravail"
```

### Depuis un fichier

```bash
python -m src.main --fichier fiche_poste.txt
python -m src.main -f fiche_poste.txt
```

### Arguments CLI

| Argument | Description |
|----------|-------------|
| `fiche_poste` | Texte de la fiche de poste (argument positionnel) |
| `--fichier`, `-f` | Chemin vers un fichier contenant la fiche de poste |
| `--no-interrupt` | Desactiver le human-in-the-loop |

### Exemple de fiche de poste

```
Developpeur Python Senior – Machine Learning & Data Engineering

Entreprise : DataFlow Solutions, startup IA, 45 collaborateurs.

Missions :
- Concevoir des pipelines de donnees temps reel
- Developper des modeles ML (detection de fraude, scoring credit)
- Industrialiser via APIs REST et microservices conteneurises

Competences requises :
- Python (5 ans minimum), TensorFlow ou PyTorch, Scikit-learn
- Apache Spark, Airflow, SQL avance (PostgreSQL)
- Docker, Kubernetes, CI/CD (GitLab CI)
- AWS (SageMaker, S3) ou GCP (Vertex AI, BigQuery)

Conditions : CDI, Paris, teletravail hybride 3j/2j, 55-70K euros
```

---

## 9. Gitflow — Travail en equipe

On est 3 sur le projet. Chacun travaille sur une branche separee, on merge dans `main` par Pull Request.

### Branches

```
main                          ← stable, toujours fonctionnel — personne ne push directement
  │
  ├── feat/sourcing           ← Chantier 1 : refonte A3 (scraping, filtrage, APIs)
  │
  ├── feat/scoring            ← Chantier 2 : prompt A4 + routage conditionnel
  │
  └── feat/...                ← toute autre feature
```

### Regles

- **Jamais de push direct sur `main`**
- Chaque chantier = une branche `feat/xxx`
- Pour integrer dans main = **Pull Request** avec review par au moins 1 coequipier
- Rebase sur main regulierement pour eviter les gros conflits

### Repartition par chantier

Les chantiers touchent des fichiers differents → peu de conflits :

| Personne | Branche | Fichiers principaux |
|----------|---------|-------------------|
| Personne 1 | `feat/sourcing` | `agents/chercheur.py`, `tools/search.py`, `tools/scraping.py`, `state.py` (nouveaux champs), `graph.py` (nouveaux noeuds) |
| Personne 2 | `feat/scoring` | `agents/evaluateur.py`, `prompts.py`, `graph.py` (routage), `config.py` (seuils), `main.py` (arg `--seuil`) |
| Personne 3 | Au choix | API/MCP, interface web, ou renfort sur un chantier |

**Zones de conflit potentielles** : `graph.py` et `state.py` — les personnes qui les touchent doivent se coordonner.

### Workflow quotidien

```bash
# Avant de travailler — se mettre a jour
git checkout feat/ma-branche
git fetch origin
git rebase origin/main

# Travailler, commit souvent
git add fichiers_modifies
git commit -m "description claire"

# Pousser
git push origin feat/ma-branche

# Quand c'est pret — PR vers main, review par un coequipier
```

---

## 10. Configuration

Fichier : `src/config.py`

```python
# Modele LLM (via Ollama)
OLLAMA_MODEL = "kimi-k2.5:cloud"   # Modele cloud rapide
OLLAMA_PROVIDER = "ollama"

# Seuils de decision apres verification (A5)
SCORE_SEUIL_CONTACT = 75   # score >= 75 → A7 contacte le candidat
SCORE_SEUIL_HUMAIN = 50    # score 50-75 → decision humaine requise
                            # score < 50  → candidat ecarte

# Limites
MAX_PROFILS_RECHERCHE = 15  # Nombre max de profils collectes par A3
MAX_PROFILS_PARALLELES = 10 # Nombre max d'instances paralleles d'A4
```

### Changer de modele

Pour utiliser un modele local :

```python
OLLAMA_MODEL = "qwen3.5:4b"    # ou tout autre modele Ollama local
```

Verifier les modeles disponibles avec `ollama list`.

---

## 11. Fonctionnement detaille de chaque agent

### A1 — Orchestrateur (`src/agents/orchestrateur.py`)

Contient 3 fonctions-noeuds :

- **`orchestrateur_node`** : Point d'entree du pipeline. Recoit la fiche de poste, initialise l'etat, log le demarrage. Pas d'appel LLM — c'est un superviseur qui gere le flux.

- **`reduce_scores_node`** : Noeud de synchronisation (fan-in). Apres que les N evaluateurs paralleles ont termine, ce noeud sert de point de convergence. Les scores sont deja agreges par le reducer `operator.add` — ce noeud log simplement le nombre de scores recus.

- **`rapport_node`** : Appelle le LLM pour generer le rapport final structure. Recoit toutes les donnees du pipeline (fiche de poste, profil de competences, statistiques, classement des candidats, messages envoyes) et produit un rapport en francais.

### A2 — Analyste (`src/agents/analyste.py`)

1. Recoit la fiche de poste depuis le blackboard
2. Envoie au LLM avec le prompt `ANALYSTE_SYSTEM`
3. Le LLM produit un JSON structure :
   ```json
   {
     "hard_skills": ["Python", "TensorFlow", "Docker"],
     "soft_skills": ["communication", "autonomie"],
     "experience_min": 5,
     "formation": "Bac+5",
     "contraintes": ["Paris", "teletravail partiel"],
     "mots_cles": ["ML", "data engineering", "pipeline"]
   }
   ```
4. Ecrit le resultat dans `profil_competences` sur le blackboard
5. Fallback : si le LLM ne produit pas de JSON valide, cree un profil vide avec la reponse brute

### A3 — Chercheur (`src/agents/chercheur.py`)

Pipeline interne en 6 etapes. C'est l'agent le plus complexe du systeme — il enchaine collecte, filtrage et enrichissement sans appel LLM supplementaire (sauf pour generer les requetes).

1. **Generation de requetes** : Le LLM recoit le profil de competences et genere des requetes de recherche optimisees (JSON avec `queries_generales`, `queries_linkedin`, `queries_github`). Les requetes sont formulees pour trouver des *personnes* (CV, portfolios, profils publics), pas des offres.

2. **Collecte structuree** : Les requetes sont executees via `_ddg_search_raw()` qui retourne des dicts structures `{title, url, body, source}` au lieu de texte brut. Chaque requete inclut automatiquement les exclusions DDG (`-"offre d'emploi"`, `-"postuler"`, etc.) pour filtrer le bruit a la source.

3. **Deduplication par URL** : Les resultats identiques provenant de differentes requetes sont elimines.

4. **Pre-filtre anti-bruit (sans LLM)** : Deux niveaux de filtrage algorithmique :
   - **Par domaine d'URL** (`_is_noise_url`) : elimine les pages d'agregateurs (Indeed, Glassdoor, Jooble, Monster, Cadremploi, etc. — 19 domaines bloques). C'est le filtre le plus fiable car les agregateurs ont des titres anodins ("Python - Paris : 2 024 emplois") que le filtre textuel ne detecte pas.
   - **Par mots-cles** (`_is_noise`) : elimine les offres d'emploi restantes par detection de mots-cles dans title+body ("nous recherchons", "postuler", "rejoignez-nous", etc. — 23 mots-cles).

5. **Scraping des pages restantes** : Chaque URL survivante est scrapee via `extraire_page_web_raw()` (BeautifulSoup, max 3000 chars). Le `profil_brut` du candidat devient le contenu scrape au lieu du snippet DDG de 2-3 lignes. En cas d'echec de scraping, le snippet DDG est utilise en fallback.

6. **Post-filtre** : Le contenu scrape complet est re-teste par `_is_noise()`. Le contenu complet d'une page peut reveler qu'on est sur une offre d'emploi alors que le snippet DDG ne le montrait pas.

**Resultat** : au lieu de passer ~15 profils bruts (dont 10+ offres d'emploi) a A4 pour evaluation LLM, A3 ne transmet que les candidats reels avec un profil_brut enrichi. Economie directe de tokens, de temps, et meilleure qualite d'evaluation.

### A4 — Evaluateur (`src/agents/evaluateur.py`)

- Recoit un state **partiel** via `Send()` : un seul candidat + le profil de competences
- N instances tournent en parallele (une par candidat)
- Produit un score multicriteres :
  - `hard_skills` (0-100) : adequation des competences techniques
  - `soft_skills` (0-100) : adequation comportementale
  - `experience` (0-100) : adequation du niveau d'experience
  - `culture_fit` (0-100) : adequation culturelle estimee
  - `score_global` (0-100) : score synthetique
  - `resume` : explication textuelle
- **Retry avec backoff exponentiel** : en cas de rate limiting (429), l'agent retry jusqu'a 5 fois avec un delai croissant (2^n + random). Protege contre les limites de requetes concurrentes du modele cloud.

### A5 — Verificateur (`src/agents/verificateur.py`)

Agent de controle independant. Recoit :
- Les scores d'A4 (`candidats_scores`)
- Les profils bruts originaux (`profils_dedupliques`) pour croisement

Verifications effectuees :
1. **Incoherences profil/score** : le score correspond-il au profil reel ?
2. **Dates suspectes** : experience irrealiste, chevauchements
3. **CV gonfles** : trop de competences sans preuves, titres vagues
4. **Faux profils** : offres d'emploi, pages d'entreprise, agregateurs deguises en candidats

Produit pour chaque candidat :
- `score_final` : score ajuste (peut etre different du score A4)
- `statut` : "valide", "invalide" ou "douteux"
- `remarques` : explications des ajustements

### A6 — Deduplicateur (`src/agents/deduplicateur.py`)

Agent algorithmique (pas d'appel LLM). Compare les profils par :
1. **URL identique** → meme personne
2. **Similarite de nom** > 0.85 (via `difflib.SequenceMatcher`) → meme personne

En cas de doublon :
- Les profils bruts sont fusionnes (concatenation avec indication de source)
- L'URL la plus informative est conservee
- Les sources sont listees (ex: "linkedin, github")

### A7 — Recruteur (`src/agents/recruteur.py`)

Declenche uniquement si un candidat valide a un score >= `SCORE_SEUIL_CONTACT` (75).

Pour chaque candidat eligible :
1. Le LLM genere un message personnalise (max 150 mots)
2. Le message mentionne specifiquement ce qui a retenu l'attention dans le profil
3. Propose un echange (appel, visio, cafe)
4. Suggere un canal de contact (linkedin, email)

---

## 12. Outils (Tools)

### `src/tools/search.py`

Deux niveaux d'API — un helper interne structure et des wrappers LangChain :

**Helper interne (utilise par A3)** :

| Fonction | Description |
|----------|-------------|
| `_ddg_search_raw(query, site_filter, max_results)` | Retourne `list[dict]` avec `{title, url, body, source}`. Ajoute automatiquement `DDG_EXCLUSIONS` a la requete. |
| `DDG_EXCLUSIONS` | Constante qui exclut les offres d'emploi a la source : `-"offre d'emploi"`, `-"postuler"`, `-"nous recrutons"`, `-"rejoignez-nous"`, `-"CDI a pourvoir"`, `-"candidature"`. |

**Wrappers `@tool` LangChain** (conserves pour compatibilite bind_tools) :

| Outil | Description | Strategie |
|-------|-------------|-----------|
| `recherche_profils` | Recherche web generale | Appelle `_ddg_search_raw(query)`, 5 resultats max |
| `recherche_linkedin` | Recherche LinkedIn | Appelle `_ddg_search_raw(query, site_filter="linkedin.com/in")`, 5 resultats max |
| `recherche_github` | Recherche GitHub | Appelle `_ddg_search_raw(query, site_filter="github.com")`, 5 resultats max |

### `src/tools/scraping.py`

Deux niveaux d'API egalement :

| Fonction / Outil | Type | Description |
|-----------------|------|-------------|
| `extraire_page_web_raw(url, max_chars)` | Fonction | Extrait le texte d'une page web avec BeautifulSoup. Supprime scripts/styles/nav/footer. Tronque a `max_chars` (defaut 3000). Utilisable depuis n'importe quel agent sans passer par LangChain. |
| `extraire_page_web` | `@tool` | Wrapper LangChain qui appelle `extraire_page_web_raw`. |

---

## 13. Filtrage anti-bruit

Implemente dans `src/agents/chercheur.py`. Filtre algorithmique (sans LLM) qui ecarte les offres d'emploi et pages d'agregateurs avant le scraping et l'evaluation. Objectif : ne pas gaspiller des appels LLM (A4) sur des pages qui ne sont pas des profils de candidats.

### Pipeline

```
Resultats bruts DDG (N hits)
        |
   Deduplication par URL
        |
   Filtre URL (_is_noise_url)       ← domaines bloques
        |
   Filtre texte (_is_noise)         ← mots-cles sur title + body
        |
   Scraping des pages restantes
        |
   Post-filtre (_is_noise)          ← mots-cles sur contenu scrape complet
        |
   Candidats finals → A6
```

Le filtre URL passe en premier car il est le plus fiable : les agregateurs ont souvent des titres generiques ("Python - Paris : 6 442 emplois") que le filtre textuel ne detecte pas.

### Domaines bloques (19)

**Generalistes (presence internationale)** :
`indeed.com`, `indeed.fr`, `glassdoor.com`, `glassdoor.fr`, `jooble.org`, `monster.fr`, `monster.com`, `talent.com`

**Specialises France** :
`welcometothejungle.com`, `hellowork.com`, `apec.fr`, `pole-emploi.fr`, `francetravail.fr`, `cadremploi.fr`, `keljob.com`, `regionsjob.com`, `meteojob.com`, `jobijoba.com`, `sagexa.com`

Stockes dans le tuple `_NOISE_DOMAINS`. Testes via `_is_noise_url(url)` qui fait un `any(domain in url.lower() ...)`.

### Categories de mots-cles detectes (24 mots-cles)

Stockes dans le tuple `_NOISE_KEYWORDS`. Testes via `_is_noise(text)` sur le texte en minuscules.

| Categorie | Exemples |
|-----------|----------|
| **Offres d'emploi** | "nous recherchons", "postuler", "offre d'emploi", "cdi a pourvoir", "description du poste", "profil recherche", "salaire", "temps plein", etc. |
| **Agregateurs / plateformes** | "welcometothejungle", "hellowork", "pole-emploi", "france travail" |

Le filtre est volontairement large : un faux positif (profil reel ecarte) est moins couteux qu'un faux negatif (offre d'emploi envoyee a A4 pour scoring LLM).

### Exemple concret

Resultat DDG :
- **title** : `machine learning - Paris : 6 442 emplois | Glassdoor`
- **url** : `https://www.glassdoor.fr/Emploi/paris-machine-learning-emplois-SRCH_...`

Verdict : **bloque par `_is_noise_url`** (domaine `glassdoor.fr`). Le filtre textuel `_is_noise` ne l'aurait pas detecte car aucun des 24 mots-cles n'apparait dans le titre. C'est precisement pour ce type de cas que le filtre URL existe en complement du filtre texte.

---

## 14. Routage conditionnel

Apres que A5 a verifie les candidats, le graphe route selon le meilleur score :

```python
def route_apres_verification(state):
    meilleur_score = max(c["score_final"] for c in state["candidats_valides"])
    if meilleur_score >= 75:
        return "recruteur"     # A7 contacte les meilleurs
    else:
        return "rapport"       # Rapport sans contact
```

```
                    A5 Verificateur
                         |
                   meilleur score?
                    /          \
              >= 75              < 75
                /                  \
        A7 Recruteur           Rapport final
        (contact)              (fin ou decision humaine)
              \                  /
               \                /
                Rapport final
                     |
                    END
```

---

## 15. Human-in-the-loop

Active par defaut (desactivable avec `--no-interrupt`).

Le graphe utilise `interrupt_before=["recruteur"]` avec le `MemorySaver` checkpointer. Quand le pipeline atteint A7 :

1. **Pause** : le graphe s'arrete et affiche les candidats valides
2. **Choix humain** :
   - `o/oui/y/yes` → le pipeline reprend, A7 redige et "envoie" les messages
   - `n/non` → le pipeline saute A7 et genere le rapport sans contact

```
============================================================
  PAUSE — Validation humaine requise avant contact
============================================================

Candidats a contacter :
  - Jean Dupont | Score: 82 | valide
  - Marie Martin | Score: 78 | valide

Continuer et envoyer les messages ? (o/n) :
```

Le checkpointer sauvegarde l'etat a chaque etape. La reprise apres interruption est transparente grace a `app.stream(None, config=config)`.

---

## 16. Logs et suivi en temps reel

Chaque agent affiche des logs avec `print(..., flush=True)` pour un suivi en temps reel :

```
[A1 Orchestrateur] Reception de la fiche de poste...
[A1 Orchestrateur] Demarrage du pipeline multi-agents.

[A2 Analyste] Analyse de la fiche de poste en cours...
[A2 Analyste] Profil extrait : 11 hard skills, 0 soft skills, 17 mots-cles.

[A3 Chercheur] Generation des requetes de recherche...
[A3 Chercheur] Lancement de 7 recherches (3 web, 2 LinkedIn, 2 GitHub)...
[A3 Chercheur]   Web 1/3 : intitle:CV OR intitle:Resume "Python" "FastAPI"...
[A3 Chercheur]   LinkedIn 1/2 : "Python" AND ("FastAPI" OR "Django")...
[A3 Chercheur]   GitHub 1/2 : "FastAPI" "LangChain" "Python"...
[A3 Chercheur] 19 resultats bruts DDG collectes.
[A3 Chercheur] 17 resultats apres deduplication par URL.
[A3 Chercheur] Pre-filtre : 6 offres/agregateurs ecartes, 11 candidats potentiels.
[A3 Chercheur]   Scraping 1/11 : https://www.linkedin.com/in/john-doe/
[A3 Chercheur]   Scraping 2/11 : https://github.com/jsmith
[A3 Chercheur] Post-filtre : 1 pages ecartees apres scraping.
[A3 Chercheur] 10 profils bruts collectes (avec contenu scrape).

[A6 Deduplicateur] Analyse de 10 profils bruts...
[A6 Deduplicateur] 10 profils uniques conserves (0 doublons fusionnes).

[Graph] Fan-out : envoi de 10 profils vers 10 evaluateurs paralleles (Send).
[A4 Evaluateur] Evaluation de : Sri Ram - Gen AI Engineer (source: linkedin)...
[A4 Evaluateur] Evaluation de : Pankaj Salunkhe - Backend/Gen AI (source: linkedin)...
[A4 Evaluateur] Rate limit pour Sri Ram, retry 1/5 dans 1.6s...
[A4 Evaluateur] Sri Ram -> score: 82/100
[A4 Evaluateur] DeShawn Smith -> score: 81/100

[Reduce] Fan-in : 10 scores agreges depuis les evaluateurs paralleles.

[A5 Verificateur] Verification de 10 candidats scores...
[A5 Verificateur] Resultat : 2 valides, 3 douteux, 5 invalides.
[A5 Verificateur]   - Sri Ram | 80/100 | valide
[A5 Verificateur]   - Hazz Saeed Haris | 60/100 | valide
[A5 Verificateur]   - DeShawn Smith | 55/100 | douteux (CV gonfle detecte)

[Graph] Routage : meilleur score 80 >= 75 -> A7 Recruteur.

[A7 Recruteur] 1 candidats au-dessus du seuil de 75/100.
[A7 Recruteur]   -> Sri Ram via linkedin

[A1 Rapport] Generation du rapport final...
[A1 Rapport] Rapport final genere.
```

---

## 17. Exemple d'execution complete

### Commande

```bash
python -m src.main --no-interrupt "Developpeur Python senior — 5+ ans d'experience en Python, FastAPI ou Django, PostgreSQL, Docker, AWS ou GCP. Bonus : experience ML/IA (LangChain, RAG, LLMs). Localisation : Paris ou full remote. Equipe produit, CDI."
```

### Resultat (test reel du 11 avril 2026 — apres refactor sourcing)

- **A2 Analyste** : extrait 11 hard skills, 17 mots-cles
- **A3 Chercheur** : 7 recherches → 19 bruts DDG → 17 apres dedup → **6 ecartes par pre-filtre** (Indeed, Glassdoor, Jooble) → 11 scrapes → 1 ecarte post-scraping → **10 profils bruts enrichis** (contenu scrape, pas snippets)
- **A6 Deduplicateur** : 10 profils conserves (0 doublons)
- **A4 Evaluateur** : 10 instances paralleles via Send(), scores de 20 a 82/100. Rate limiting gere par retry exponentiel.
- **A5 Verificateur** : 2 valides, 3 douteux, 5 invalides. Detection de CV gonfle sur DeShawn Smith (81→55, "keyword stuffing suspect"). Agregateurs restants invalides a 0/100.
- **Routage** : meilleur score 80 >= 75 → A7 Recruteur active
- **A7 Recruteur** : 1 message de contact redige (Sri Ram, via LinkedIn)
- **Rapport** : classement detaille, recommandations par candidat, analyse des risques (localisation, authenticite)

**Comparaison avant/apres refactor sourcing :**

| Metrique | Avant refactor | Apres refactor |
|----------|----------------|----------------|
| Profils collectes | 15 (snippets DDG) | 10 (contenu scrape) |
| Offres d'emploi dans le lot | ~10 (67%) | 5 (50%, ecartes par A5) |
| Candidats contactes | **0** | **1** |
| Temps total | ~7 min | ~5 min (moins d'appels A4) |

---

## 18. Prompts systeme

Tous les prompts sont centralises dans `src/prompts.py`. Chaque agent a un prompt systeme dedie.

### ANALYSTE_SYSTEM
Force la sortie JSON avec les cles : `hard_skills`, `soft_skills`, `experience_min`, `formation`, `contraintes`, `mots_cles`.

### CHERCHEUR_QUERIES_PROMPT
(Defini dans `chercheur.py`) Genere des requetes de recherche en JSON : `queries_generales`, `queries_linkedin`, `queries_github`.

### EVALUATEUR_SYSTEM
Produit un JSON avec `score_global` (0-100), `scores_detail` (4 sous-scores), et `resume`.

### VERIFICATEUR_SYSTEM
Verifie coherence des dates, competences, detecte les CV gonfles. Produit un JSON avec `score_final`, `statut` (valide/invalide/douteux), et `remarques`.

### RECRUTEUR_SYSTEM
Redige des messages personnalises (max 150 mots) avec `objet`, `message`, et `canal`.

### ORCHESTRATEUR_RAPPORT_SYSTEM
Produit un rapport structure : resume du poste, statistiques, classement, actions, recommandations.

---

## 19. Limites et pistes d'amelioration

### Limites actuelles

| Limite | Explication |
|--------|-------------|
| **Recherche web uniquement** | Pas d'API LinkedIn/GitHub directe — DuckDuckGo avec exclusions + filtre domaine + filtre mots-cles. Efficace mais certains agregateurs passent encore quand leurs titres sont generiques |
| **Rate limiting modele cloud** | Les N evaluateurs paralleles peuvent saturer le modele cloud (429). Le retry avec backoff gere ce cas mais ralentit l'execution |
| **Scoring trop strict** | Le seuil fixe de 75 fait passer des bons candidats (60-70) sans contact. Le prompt A4 penalise chaque competence manquante comme eliminatoire |
| **Qualite du parsing** | Le LLM ne produit pas toujours du JSON valide. Les fallbacks sont en place mais perdent de l'information |
| **Pas de persistance** | Le `MemorySaver` est en memoire. Redemarrer le process perd l'etat |
| **Messages non envoyes** | A7 redige les messages mais ne les envoie pas reellement (pas d'integration email/LinkedIn) |

### Pourquoi les resultats sont majoritairement LinkedIn

A3 lance 3 categories de recherches via DuckDuckGo (web general, LinkedIn, GitHub). Apres le pipeline de filtrage (filtre domaine + filtre mots-cles + scraping), les resultats qui survivent sont quasi exclusivement des profils LinkedIn. Trois raisons :

1. **Web general → agregateurs** : les recherches generiques ramenent surtout des pages Indeed, Glassdoor, Jooble, Monster, etc. Ces domaines sont bloques par le filtre domaine. Les rares pages qui passent sont des offres d'emploi, eliminees par le filtre texte ("nous recherchons", "postuler"...).

2. **GitHub via DDG → repos, pas des personnes** : DuckDuckGo renvoie des pages de repositories, pas des profils utilisateurs. Le titre contient un nom de projet, rarement un nom de candidat. Le filtre texte ne trouve ni competences ni parcours — le resultat est ecarte.

3. **LinkedIn → profils individuels** : c'est la seule source ou DDG renvoie des pages structurees avec nom + titre + resume de competences. Ces pages passent le filtre domaine (autorise), le filtre texte (contenu pertinent) et le scraping (structure HTML exploitable).

Ce biais n'est pas un bug du filtrage — c'est une consequence de la nature des resultats DuckDuckGo. Pour diversifier reellement les sources, il faut des APIs directes (cf. pistes ci-dessous).

### Pistes d'amelioration

- **Diversification des sources** : remplacer les recherches DDG par des APIs dediees. **GitHub API** pour rechercher des utilisateurs par langage, localisation et contributions (au lieu de repos). **Indeed API** cote recruteur pour acceder aux CVs — le MCP Indeed a trouve 73 offres en un seul appel cote demandeur d'emploi, la meme infrastructure pourrait chercher des profils cote recruteur. **LinkedIn API** avec filtres avances (experience, competences, secteur, localisation)
- **Division d'A3** : actuellement A3 fait trop (genere requetes + execute recherches + filtre + scrape). A terme, separer en 3 sous-agents : **A3a Stratege** (recoit le profil de competences, genere les requetes optimisees par source), **A3b Collecteur** (execute les recherches, scrape les pages, produit les profils bruts enrichis), **A3c Filtre** (classe chaque resultat en candidat reel vs bruit avant deduplication)
- **APIs directes** : Integration LinkedIn Recruiter, GitHub API, Indeed API pour un sourcing plus precis
- **Persistance** : Remplacer `MemorySaver` par `SqliteSaver` ou `PostgresSaver` pour garder l'etat entre les sessions
- **Analyse d'entretien** : Ajouter un agent A8 pour l'analyse de reponses d'entretien video/texte
- **Verification de references** : Agent dedie pour contacter les references
- **Interface web** : Dashboard pour le recruteur humain au lieu du CLI
- **Envoi reel** : Integration SMTP/API LinkedIn pour envoyer les messages d'A7
- **Metriques** : Tracking des taux de reponse pour ameliorer les prompts d'A7 au fil du temps
