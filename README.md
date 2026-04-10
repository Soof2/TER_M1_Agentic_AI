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
9. [Configuration](#9-configuration)
10. [Fonctionnement detaille de chaque agent](#10-fonctionnement-detaille-de-chaque-agent)
11. [Outils (Tools)](#11-outils-tools)
12. [Routage conditionnel](#12-routage-conditionnel)
13. [Human-in-the-loop](#13-human-in-the-loop)
14. [Logs et suivi en temps reel](#14-logs-et-suivi-en-temps-reel)
15. [Exemple d'execution complete](#15-exemple-dexecution-complete)
16. [Prompts systeme](#16-prompts-systeme)
17. [Limites et pistes d'amelioration](#17-limites-et-pistes-damelioration)

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
   A3 Chercheur              ← Recherche web (DuckDuckGo, LinkedIn, GitHub)
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
4. A3 : profil_competences → LLM genere des requetes → DuckDuckGo → profils_bruts
        Le LLM produit des queries optimisees, les outils sont appeles directement
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

## 9. Configuration

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

## 10. Fonctionnement detaille de chaque agent

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

Fonctionne en 3 etapes :

1. **Generation de requetes** : Le LLM recoit le profil de competences et genere des requetes de recherche optimisees (JSON avec `queries_generales`, `queries_linkedin`, `queries_github`).

2. **Execution des recherches** : Les outils DuckDuckGo sont appeles directement (pas de `bind_tools`, compatible modeles cloud). Typiquement 5-7 recherches : 2-3 web generales, 2 LinkedIn, 1-2 GitHub.

3. **Parsing des resultats** : Les resultats bruts sont transformes en objets `Candidat` avec deduction automatique de la source (linkedin/github/indeed/web) a partir de l'URL. Deduplication par URL a ce stade.

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

## 11. Outils (Tools)

### `src/tools/search.py`

Trois outils de recherche bases sur DuckDuckGo (`ddgs`) :

| Outil | Description | Strategie |
|-------|-------------|-----------|
| `recherche_profils` | Recherche web generale | Requete directe, 5 resultats max |
| `recherche_linkedin` | Recherche LinkedIn | Prefixe `site:linkedin.com/in`, 5 resultats max |
| `recherche_github` | Recherche GitHub | Prefixe `site:github.com`, 5 resultats max |

Chaque outil est un `@tool` LangChain. Les resultats sont formates en texte structure (Titre/URL/Extrait separes par `---`).

### `src/tools/scraping.py`

| Outil | Description |
|-------|-------------|
| `extraire_page_web` | Extrait le texte principal d'une page web avec BeautifulSoup. Supprime scripts/styles/nav/footer. Tronque a 3000 caracteres. |

---

## 12. Routage conditionnel

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

## 13. Human-in-the-loop

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

## 14. Logs et suivi en temps reel

Chaque agent affiche des logs avec `print(..., flush=True)` pour un suivi en temps reel :

```
[A1 Orchestrateur] Reception de la fiche de poste...
[A1 Orchestrateur] Demarrage du pipeline multi-agents.

[A2 Analyste] Analyse de la fiche de poste en cours...
[A2 Analyste] Profil extrait : 6 hard skills, 3 soft skills, 8 mots-cles.

[A3 Chercheur] Generation des requetes de recherche...
[A3 Chercheur] Lancement de 7 recherches (3 web, 2 LinkedIn, 2 GitHub)...
[A3 Chercheur]   Web 1/3 : developpeur Python senior ML Paris...
[A3 Chercheur]   LinkedIn 1/2 : Python TensorFlow senior Paris...
[A3 Chercheur]   GitHub 1/2 : Python machine learning data pipeline...
[A3 Chercheur] 15 profils bruts collectes.

[A6 Deduplicateur] Analyse de 15 profils bruts...
[A6 Deduplicateur] 13 profils uniques conserves (2 doublons fusionnes).

[Graph] Fan-out : envoi de 13 profils vers 13 evaluateurs paralleles (Send).
[A4 Evaluateur] Evaluation de : Jean Dupont (source: linkedin)...
[A4 Evaluateur] Evaluation de : Marie Martin (source: github)...
[A4 Evaluateur] Rate limit pour X, retry 1/5 dans 1.3s...
[A4 Evaluateur] Jean Dupont -> score: 82/100
[A4 Evaluateur] Marie Martin -> score: 78/100

[Reduce] Fan-in : 13 scores agreges depuis les evaluateurs paralleles.

[A5 Verificateur] Verification de 13 candidats scores...
[A5 Verificateur] Resultat : 3 valides, 2 douteux, 8 invalides.
[A5 Verificateur]   - Jean Dupont | 82/100 | valide
[A5 Verificateur]   - Marie Martin | 78/100 | valide
[A5 Verificateur]   - Offre Emploi XYZ | 0/100 | invalide

[Graph] Routage : meilleur score 82 >= 75 -> A7 Recruteur.

[A7 Recruteur] 2 candidats au-dessus du seuil de 75/100.
[A7 Recruteur]   -> Jean Dupont via linkedin
[A7 Recruteur]   -> Marie Martin via email

[A1 Rapport] Generation du rapport final...
[A1 Rapport] Rapport final genere.
```

---

## 15. Exemple d'execution complete

### Commande

```bash
python -m src.main --no-interrupt "Developpeur Python senior, 5 ans d'experience minimum, specialise en Machine Learning et Data Engineering. Competences requises : Python, TensorFlow, PyTorch, SQL, Docker, Kubernetes. Poste base a Paris, teletravail partiel possible. CDI."
```

### Resultat (test reel effectue)

- **A2 Analyste** : extrait 6 hard skills, soft skills, formation Bac+5, contraintes Paris + teletravail
- **A3 Chercheur** : 7 recherches executees → 15 profils bruts collectes
- **A6 Deduplicateur** : 15 profils conserves (pas de doublons detectes)
- **A4 Evaluateur** : 15 instances paralleles via Send(), scores de 25 a 70/100
- **A5 Verificateur** : 5 vrais candidats identifies, 10 profils invalides (offres d'emploi, pages d'agregateurs)
- **Routage** : meilleur score 70 < 75 → pas de contact, direct au rapport
- **Rapport** : classement des 5 candidats, recommandations (elargir les sources, ajuster les criteres)

Duree totale : ~7 minutes (modele cloud avec rate limiting).

---

## 16. Prompts systeme

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

## 17. Limites et pistes d'amelioration

### Limites actuelles

| Limite | Explication |
|--------|-------------|
| **Recherche web uniquement** | Pas d'API LinkedIn/GitHub directe — les profils sont issus de DuckDuckGo, ce qui capte des offres d'emploi et des pages d'agregateurs en plus des vrais profils |
| **Rate limiting modele cloud** | Les N evaluateurs paralleles peuvent saturer le modele cloud (429). Le retry avec backoff gere ce cas mais ralentit l'execution |
| **Qualite du parsing** | Le LLM ne produit pas toujours du JSON valide. Les fallbacks sont en place mais perdent de l'information |
| **Pas de persistance** | Le `MemorySaver` est en memoire. Redemarrer le process perd l'etat |
| **Messages non envoyes** | A7 redige les messages mais ne les envoie pas reellement (pas d'integration email/LinkedIn) |

### Pistes d'amelioration

- **APIs directes** : Integration LinkedIn Recruiter, GitHub API, Indeed API pour un sourcing plus precis
- **Persistance** : Remplacer `MemorySaver` par `SqliteSaver` ou `PostgresSaver` pour garder l'etat entre les sessions
- **Analyse d'entretien** : Ajouter un agent A8 pour l'analyse de reponses d'entretien video/texte
- **Verification de references** : Agent dedie pour contacter les references
- **Interface web** : Dashboard pour le recruteur humain au lieu du CLI
- **Envoi reel** : Integration SMTP/API LinkedIn pour envoyer les messages d'A7
- **Metriques** : Tracking des taux de reponse pour ameliorer les prompts d'A7 au fil du temps
