# Rapport de Projet — TER Master 1 Informatique
## Architectures Logicielles pour l'IA Agentique : des Systèmes Multi-Agents au Prototype de Recrutement Automatisé

**Auteurs :** Sofiane Dzermane, [Prénom Nom]  
**Encadrant :** M. Abdelhak-Djamel Seriai  
**Année universitaire :** 2025-2026  
**Date :** Mai 2026

---

## Résumé

Ce rapport présente l'intégralité des travaux réalisés dans le cadre du TER de Master 1 Informatique, portant sur l'étude des architectures logicielles pour l'intelligence artificielle agentique. La démarche s'est articulée en trois temps : une phase d'études bibliographiques approfondies sur les Systèmes Multi-Agents (SMA) classiques et l'Agentic AI contemporaine, une phase de sélection et de justification du scénario applicatif, et une phase de conception et de développement d'un prototype opérationnel. Le livrable final est un système de recrutement automatisé multi-agents, implémentant huit agents spécialisés orchestrés par LangGraph, une mémoire contextuelle vectorielle inter-runs via ChromaDB (RAG), un mécanisme Human-in-the-Loop, deux modes architecturaux déployables (monolithique et microservices Docker), une API REST avec streaming SSE, une interface graphique NiceGUI et 91 tests automatisés.

**Mots-clés :** Systèmes Multi-Agents, Agentic AI, LangGraph, RAG, Groq, Feature Model, Microservices, Human-in-the-Loop, SE4AI, AI4SE

---

## Table des matières

1. [Introduction](#1-introduction)
2. [Partie 1 — Phase d'études bibliographiques](#2-partie-1--phase-détudes-bibliographiques)
3. [Partie 2 — Exploration des sujets et choix du scénario](#3-partie-2--exploration-des-sujets-et-choix-du-scénario)
4. [Partie 3 — Le projet retenu : système de recrutement agentique](#4-partie-3--le-projet-retenu--système-de-recrutement-agentique)
5. [Conclusion et bilan global](#5-conclusion-et-bilan-global)
6. [Références](#6-références)

---

## 1. Introduction

### 1.1 Contexte général

L'essor des modèles de langage de grande taille (LLM) depuis 2022 a profondément reconfiguré la façon dont les systèmes logiciels intègrent l'intelligence artificielle. Ces modèles ne se contentent plus de générer du texte : ils servent de *couche cognitive* dans des systèmes distribués capables de planifier, de percevoir leur environnement, de sélectionner des outils et de prendre des décisions autonomes. Ce mouvement, désigné sous le terme d'**Agentic AI**, interroge fondamentalement les architectures logicielles existantes.

Ce TER s'inscrit à l'intersection de deux axes complémentaires identifiés dans la littérature récente :

- **AI4SE** (*Artificial Intelligence for Software Engineering*) : l'IA comme outil au service de l'ingénierie logicielle — génération de code, revue automatique, tests, optimisation architecturale.
- **SE4AI** (*Software Engineering for AI*) : le génie logiciel comme cadre méthodologique pour industrialiser les systèmes IA — architecture, gouvernance, traçabilité, tests, MLOps.

### 1.2 Objectifs du TER

L'encadrant, M. Seriai, a défini trois objectifs fondamentaux :

1. **Étudier la variabilité architecturale** des systèmes logiciels basés sur l'IA et la formaliser sous forme d'un feature model.
2. **Identifier des critères de choix** architecturaux (exigences fonctionnelles, contraintes non fonctionnelles) permettant de sélectionner un style d'architecture adapté.
3. **Implémenter une architecture de référence Agentic AI** : microservices, API Gateway, RAG, observabilité, Human-in-the-Loop, illustrée par un scénario applicatif réaliste.

### 1.3 Démarche globale

Le travail a suivi trois phases successives :
1. Phase bibliographique intensive (6 études SMA + 11 études Agentic AI + synthèses + analyse comparative)
2. Phase de sélection du scénario (comparaison de plusieurs domaines d'application)
3. Phase de développement itératif du prototype

---

## 2. Partie 1 — Phase d'études bibliographiques

### 2.1 Inventaire du dossier d'études

Le dossier `Etudes/` contient l'ensemble des productions de la phase bibliographique. Sa structure reflète la progression intellectuelle du travail :

```
Etudes/
├── etudes_sma_/
│   ├── etude_1_cours.pdf                               (cours fondateur SMA)
│   ├── etude_2_Systèmes multiagents.pdf                (référence académique française)
│   ├── etude_3_visual_survey_agent_based_computing.pdf (survey visuel)
│   ├── etude_4_general_survey_theory_applications.pdf  (survey théorie/applications)
│   ├── etude_5_cmu_machine_learning_perspective.pdf    (CMU : MARL)
│   ├── etude_6_wjarr_future_distributed_ai.pdf         (perspectives distribuées)
│   └── synthese_generale_SMA.pdf                       (synthèse produite)
├── etudes_agentic_ai_/
│   ├── etude_1_agentic_ai_playbook.pdf                 (Wavestone : industrie)
│   ├── etude_2_comprehensive_survey.pdf                (Abou Ali et al. : paradigmes)
│   ├── etude_3_age_of_generative_models.pdf            (Alva et Pandey)
│   ├── etude_4_ai_agents_vs_agentic_ai.pdf             (Sapkota et al. : taxonomie)
│   ├── etude_5_systematic_review_genai.pdf             (Patel et al. : sécurité)
│   ├── etude_6_technologies_societal_implications.pdf   (Hughes et al.)
│   ├── etude_7AIFrameworks.pdf                         (Vaidhyanathan et Taibi)
│   ├── etude_8_AYearinTOSEM.pdf                        (SE4AI/AI4SE)
│   ├── etude_9_AgenticCommunities.pdf                  (Milosevic et Rabhi)
│   ├── etude10_generative_to_agentic.pdf               (Schneider)
│   ├── etude11_AIAgentsandAgenticSystems.pdf           (Pati et al.)
│   └── synthese_generale_agentic_ai.pdf                (synthèse produite)
├── analyse_comparative_SMA_AgenticAI.pdf               (analyse croisée produite)
└── comparaison_frameworks_IA_detaille.xlsx - Glossaire des concepts.csv
```

**17 articles scientifiques** ont été lus, analysés et synthétisés. Trois documents de synthèse ont été produits.

### 2.2 Synthèse des études SMA

#### 2.2.1 Définitions et fondements

La synthèse SMA (`synthese_generale_SMA.pdf`) s'appuie sur les travaux de **Dorri et al. (2018)** pour poser la définition fondatrice : *"un Système Multi-Agents est un ensemble d'agents autonomes interagissant dans un environnement partagé pour atteindre des objectifs individuels ou collectifs."* Cette définition, apparemment simple, recouvre une complexité technique considérable.

**Maldonado et al. (2024)** complètent cette définition en identifiant cinq composants clés structurant tout SMA :

| Composant | Description |
|-----------|-------------|
| **Agents** | Entités autonomes capables de percevoir et d'agir |
| **Environnement** | Espace partagé dans lequel les agents évoluent |
| **Interactions** | Échanges et communications entre agents |
| **Organisation** | Structure qui régit les rôles et relations |
| **Objectifs** | Buts individuels ou collectifs poursuivis |

Tout agent possède quatre propriétés essentielles : **Autonomie** (décision indépendante), **Réactivité** (réponse aux changements), **Proactivité** (poursuite active d'objectifs), **Sociabilité** (coopération et communication).

#### 2.2.2 Architectures organisationnelles

Trois styles organisationnels sont distingués dans la littérature SMA :

- **Centralisée** : un agent maître coordonne les subordonnés. Avantage : cohérence globale garantie. Inconvénient : point unique de défaillance.
- **Décentralisée** : la coordination émerge des interactions locales. Avantage : robustesse et passage à l'échelle. Inconvénient : comportement global difficile à prédire.
- **Hiérarchique** : organisation multi-niveaux combinant supervision globale et coordination locale. C'est le compromis le plus répandu en pratique.

Sur le plan cognitif, les agents sont classifiés en **réactifs** (réponse directe aux stimuli), **cognitifs** (représentation interne et planification), et **hybrides** (combinaison des deux).

#### 2.2.3 Protocoles formels de coordination

Le *General Survey* (étude 4 — SMA) formalise les mécanismes d'interaction via des outils mathématiques éprouvés :

- **Contract Net Protocol** : mécanisme d'appel d'offres pour l'allocation de tâches entre agents.
- **Théorie des jeux** : modélisation des stratégies et des équilibres d'interaction.
- **Mécanismes d'enchères** : allocation optimale de ressources en environnements compétitifs.
- **Consensus distribué** : algorithmes garantissant la convergence vers un accord collectif.
- **ACL** (*Agent Communication Language*) : standard de communication inter-agents structuré.

Ces outils garantissent trois propriétés critiques : **stabilité**, **optimalité** et **convergence** — propriétés que l'on retrouvera formellement dans notre prototype via le blackboard `GraphState`.

#### 2.2.4 Le MARL : pont vers l'apprentissage

Le CMU Paper (étude 5 — SMA) constitue un pont intellectuel fondamental entre les SMA classiques et l'apprentissage automatique via le **Multi-Agent Reinforcement Learning (MARL)**. Les agents apprennent collectivement en interagissant avec un environnement dynamique. Les défis identifiés — non-stationnarité, instabilité de convergence, équilibre coopération/compétition, exploration collective — sont directement réutilisés dans notre analyse comparative.

#### 2.2.5 Ce qu'on a retenu des SMA

La phase d'études SMA a permis de maîtriser un vocabulaire formel précis (blackboard, Contract Net, BDI, MARL) et d'identifier les **patterns architecturaux réutilisables** dans notre prototype : le pattern Superviseur, le Blackboard, le Map-Reduce, la validation pair-à-pair.

### 2.3 Synthèse des études Agentic AI

#### 2.3.1 La clarification conceptuelle clé

La synthèse Agentic AI (`synthese_generale_agentic_ai.pdf`) converge vers une clarification conceptuelle essentielle : **l'Agentic AI ne se réduit ni à un simple agent LLM augmenté d'outils, ni aux SMA classiques.** Trois niveaux distincts émergent :

- **AI Agents** (Sapkota et al., 2026) : systèmes modulaires activés par des LLM, spécialisés dans l'exécution de tâches définies via prompt engineering.
- **Agentic AI** (Schneider, 2025 ; Pati, 2025) : paradigme orienté objectifs, planification autonome, mémoire persistante, adaptation dynamique.
- **Communautés agentiques** (Milosevic et Rabhi, 2026) : écosystèmes hybrides où agents IA et humains interagissent via des rôles formels et des mécanismes de gouvernance.

La trajectoire évolutive identifiée est :

```
GenAI → AI Agents → Agentic AI → Communautés agentiques → Écosystèmes hybrides gouvernés
```

Cette trajectoire est centrale : elle justifie pourquoi notre prototype va plus loin qu'un simple pipeline LLM.

#### 2.3.2 Double paradigme : symbolique vs neuronal

L'étude d'Abou Ali et al. (2026) propose un cadre analytique particulièrement utile — le **double paradigme** :

| Paradigme | Caractéristiques | Domaines dominants |
|-----------|-----------------|-------------------|
| **Symbolique** | Planification déterministe, état persistant, vérification formelle | Santé critique |
| **Neuronal** | Orchestration LLM, génération probabiliste, adaptabilité élevée | Finance, environnements dynamiques |

Les études convergent vers une **trajectoire neuro-symbolique hybride** : notre prototype l'incarne directement en combinant agents LLM (neuronal) et guards déterministes algorithmiques (symbolique) dans A5.

#### 2.3.3 La comparaison des frameworks

L'étude `etude_7AIFrameworks.pdf` (Vaidhyanathan et Taibi, 2026) et le glossaire CSV produit constituent la pièce maîtresse de la sélection technique. Cinq frameworks ont été comparés en profondeur :

| Framework | Coordination | État partagé | HITL | Vendor lock-in | Points forts |
|-----------|-------------|-------------|------|---------------|-------------|
| **LangGraph** | Graphe orienté | TypedDict riche | Natif | Aucun (open-source) | Contrôle fin, traçabilité |
| CrewAI | Rôles/délégation | Partiel | Limité | Faible | Prise en main rapide |
| AutoGen | Conversation multi-tours | Limité | Oui | Faible | Flexibilité |
| OpenAI Swarm | Handoff | Absent | Non | Fort (OpenAI) | Légèreté |
| MetaGPT | SOP rigides | Oui | Partiel | Faible | Processus logiciel |

Le glossaire produit — intitulé *"Glossaire des concepts"* — explique en français clair chaque terme technique du tableau : architecture en graphe orienté, état persistant, paradigme de coordination, HITL, RAG, bases vectorielles, SOP, handoff, MCP, LiteLLM, vendor lock-in. Ce document témoigne d'une démarche pédagogique rigoureuse : comprendre avant d'implémenter.

**La conclusion de cette analyse** est sans ambiguïté : LangGraph est le seul framework qui (1) supporte nativement le pattern Blackboard via le TypedDict, (2) permet le fan-out parallèle via `Send()`, (3) intègre le HITL sans contournement, (4) est indépendant du fournisseur LLM, et (5) structure le graphe de manière formellement proche des SMA classiques.

### 2.4 L'analyse comparative SMA / Agentic AI

Le document `analyse_comparative_SMA_AgenticAI.pdf` est le produit de synthèse le plus abouti. Il identifie cinq convergences et cinq divergences structurelles.

**Convergences :**
1. Autonomie des agents (décisions indépendantes)
2. Poursuite active d'objectifs (proactivité)
3. Collaboration et coordination multi-agents
4. Mémoire et persistance du contexte
5. Domaines d'application communs (santé, robotique, industrie)

**Divergences structurelles :**

| Critère | SMA classiques | Agentic AI |
|---------|---------------|-----------|
| Nature du raisonnement | Logique, déterministe, formellement prouvé | Probabiliste (LLM), flexible mais non garanti |
| Mode de coordination | Protocoles formels (ACL, enchères, Contract Net) | Orchestration par prompt engineering |
| Rôle de l'apprentissage | Optionnel (extension via MARL) | Central et indispensable |
| Maturité | Décennies de recherche, fondements mathématiques | Écosystème fragmenté, mémoire limitée |
| Explicabilité | Règles traçables, formellement définissables | Déficit inhérent aux LLM |

**La conclusion majeure** — citée textuellement dans le document — est : *"Les SMA ne s'opposent pas à l'Agentic AI : ils constituent un réservoir de solutions formelles et éprouvées capable de combler ses faiblesses actuelles en matière de stabilité, de gouvernance et d'explicabilité."*

C'est cette conclusion qui oriente directement la conception de notre prototype : appliquer les patterns SMA formels (blackboard, superviseur, map-reduce) à des agents LLM.

### 2.5 Démarche intellectuelle et progression

La logique de progression des études est la suivante :

```
SMA (fondements formels) → Agentic AI (paradigme contemporain) → 
Analyse comparative (synthèse critique) → Framework selection (LangGraph) → 
Prototype design
```

Ce n'est pas un enchaînement linéaire mais une **dialectique** : les lacunes identifiées dans l'Agentic AI (gouvernance, explicabilité, robustesse) sont précisément ce que les SMA permettent de combler. Notre prototype est la démonstration pratique de cette synthèse.

---

## 3. Partie 2 — Exploration des sujets et choix du scénario

### 3.1 Sujets envisagés

Avant de retenir le recrutement automatisé, plusieurs sujets applicatifs ont été envisagés et comparés. Chacun a été évalué selon cinq critères : réalisme applicatif, complexité multi-agents justifiée, pertinence du RAG, faisabilité technique (APIs gratuites), et richesse du pipeline.

#### 3.1.1 Scraping et comparateur de prix

**Concept :** Des agents autonomes parcourent des sites e-commerce, collectent des prix en temps réel, les comparent et alertent l'utilisateur des meilleures offres ou des variations significatives.

**Architecture SMA envisagée :**
- Agent Scraper (×N, un par site) : extraction des prix
- Agent Normalisateur : harmonisation des formats (euros, livres, dollars)
- Agent Comparateur : calcul des écarts et détection d'anomalies
- Agent Alerteur : notification utilisateur

**Technologies :** Beautiful Soup, Selenium, DuckDuckGo, Redis (cache)

**Avantages :** Données structurées, scraping simple, pipeline clair, résultats mesurables.

**Pourquoi non retenu :** La valeur ajoutée du LLM est marginale — la comparaison de prix est un problème algorithmique pur. Le pipeline est trop linéaire pour justifier des patterns SMA complexes (fan-out, HITL). Il manque la dimension cognitive qui caractérise l'Agentic AI.

#### 3.1.2 Assistant de veille technologique

**Concept :** Des agents spécialisés par domaine (IA, cybersécurité, cloud, DevOps) agrègent, filtrent et synthétisent les informations issues de flux RSS, d'arXiv, de GitHub Trending et de Hacker News.

**Architecture SMA envisagée :**
- Agents Collecteurs (×N, un par source/domaine)
- Agent Déduplicateur
- Agent Résumeur (LLM)
- Agent Éditorial (prioritisation, mise en forme)
- Agent Diffuseur (email, Slack)

**Technologies :** RSS parsers, GitHub API, LangChain, ChromaDB

**Avantages :** Multi-sources naturel, RAG pertinent pour la mémoire des sujets déjà vus, cas d'usage professionnel réel.

**Pourquoi non retenu :** Le périmètre est difficile à délimiter (qu'est-ce qu'une information "pertinente" ?). L'évaluation qualitative des résultats est subjective. L'encadrant a orienté vers un sujet avec des métriques plus objectives.

#### 3.1.3 Système de recommandation personnalisée

**Concept :** Un SMA où chaque agent modélise un aspect du profil utilisateur (historique, préférences explicites, comportement implicite, similarité avec d'autres utilisateurs) pour produire des recommandations convergentes par vote pondéré.

**Architecture envisagée :**
- Agents Profilage (×N, un par dimension)
- Agent de Fusion (agrégation des signaux)
- Agent d'Explication (justification des recommandations)

**Technologies :** Scikit-learn, LangChain, ChromaDB

**Avantages :** Problème classique mais riche, aspect SMA bien justifié (plusieurs modélisations du même utilisateur).

**Pourquoi non retenu :** Nécessite des données utilisateur historiques difficiles à simuler de façon réaliste dans un prototype académique. Les métriques de qualité (précision, rappel, NDCG) demandent un jeu de données conséquent.

### 3.2 Le rôle de l'encadrant dans le choix final

Lors d'une séance de suivi, **M. Seriai** a proposé un sujet alternatif : un système de recrutement automatisé de profils basé sur des prompts et des agents IA. Cette suggestion a immédiatement fait converger les réflexions pour plusieurs raisons :

1. **Le recrutement est un pipeline naturellement multi-étapes** : analyser une fiche, chercher des profils, filtrer, évaluer, vérifier, contacter. Chaque étape correspond à un agent avec une responsabilité unique — le principe SRP (*Single Responsibility Principle*) du génie logiciel appliqué aux agents.

2. **Le HITL y est parfaitement naturel** : décider de contacter un candidat est une décision à forte valeur humaine. On ne veut pas un système entièrement automatique pour cela.

3. **Le RAG y est démontrable** : les profils invalides (agrégateurs d'offres, pages d'entreprises) reviennent de façon récurrente pour les mêmes types de postes — une blacklist inter-runs a une valeur immédiatement mesurable.

4. **Les métriques sont objectives** : nombre de candidats valides, scores de matching, durée de run — tout est chiffrable.

### 3.3 Critères de décision formalisés

| Critère | Comparateur de prix | Veille tech | Recommandation | **Recrutement** |
|---------|--------------------|-----------|--------------|----|
| Réalisme professionnel | Moyen | Élevé | Moyen | **Très élevé** |
| Complexité SMA justifiée | Faible | Moyen | Moyen | **Élevée** |
| HITL naturel | Non | Non | Non | **Oui** |
| RAG démontrable | Non | Oui | Oui | **Oui** |
| Métriques objectives | Oui | Non | Oui | **Oui** |
| Faisabilité (APIs gratuites) | Oui | Oui | Non | **Oui** |

---

## 4. Partie 3 — Le projet retenu : système de recrutement agentique

### 4.1 Vision générale du projet

#### 4.1.1 Objectif

Le système de recrutement automatisé multi-agents automatise le processus de sourcing de candidats à partir d'une simple fiche de poste. L'utilisateur saisit une description de poste en langage naturel ; le système orchestre une chaîne de huit agents spécialisés pour retourner une liste de candidats pertinents, évalués, vérifiés, avec des messages de contact personnalisés.

**Entrée :**
```
"Développeur Python senior, 5 ans d'expérience, Paris ou remote,
FastAPI, LangGraph, Docker, RAG, bonne communication."
```

**Sortie :** Rapport structuré avec candidats classés par score (0-100), statut de validation, liens de profils, messages de contact rédigés.

#### 4.1.2 Valeur ajoutée par rapport à un filtrage classique

Un système de filtrage classique (mots-clés, boolean search) présente des limites structurelles :
- Il ne comprend pas la sémantique : "ingénieur data" peut correspondre à "data scientist" dans certains contextes.
- Il ne distingue pas une offre d'emploi d'un profil candidat.
- Il n'apprend pas de ses erreurs passées.
- Il ne peut pas rédiger un message personnalisé.

Notre système résout ces quatre problèmes grâce à la combinaison LLM + algorithmes déterministes + RAG.

#### 4.1.3 Positionnement dans l'écosystème Agentic AI

Ce projet est un exemple concret de **SE4AI appliqué à l'Agentic AI** : les patterns formels des SMA (blackboard, superviseur, fan-out, validation pair-à-pair) structurent un pipeline d'agents LLM, leur conférant des propriétés de traçabilité, de robustesse et d'explicabilité que l'Agentic AI "naive" ne possède pas.

### 4.2 Architecture technique détaillée

#### 4.2.1 Vue d'ensemble architecturale

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        API Gateway (FastAPI)                             │
│  POST /recruter  │  GET /runs/{id}/stream (SSE)  │  POST /runs/{id}/hitl │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                      LangGraph (GraphState)                              │
│                                                                          │
│  START → A1 → A2 → A3a → A3b → A3c → A6                                │
│                                        │                                 │
│                              Send()×N  ▼                                 │
│                         [A4] [A4] [A4] ... [A4]  ← Groq LLM             │
│                                        │ reduce_scores                   │
│                              Send()×N  ▼                                 │
│                         [A5] [A5] [A5] ... [A5]  ← Groq LLM             │
│                                        │ reduce_validations              │
│                                        ▼                                 │
│                               injection_rag ← ChromaDB                  │
│                                        │                                 │
│                           ┌──────────▼──────────┐                       │
│                           │  route_apres_verif   │                       │
│                           └──┬───────────────┬──┘                       │
│                              ▼               ▼                           │
│                           A7 Recruteur    Rapport                        │
│                              └────────────┘                             │
│                                        │                                 │
│                                   A8 Persistance → ChromaDB             │
│                                        │                                 │
│                                       END                                │
└─────────────────────────────────────────────────────────────────────────┘
         │                                          │
┌────────▼─────────┐                    ┌──────────▼──────────┐
│  NiceGUI (UI)    │                    │  ChromaDB (RAG)     │
│  port 8080       │                    │  data/chromadb/     │
└──────────────────┘                    └─────────────────────┘
```

#### 4.2.2 Le blackboard : cœur formel du SMA

Le fichier `src/state.py` définit le **blackboard**, pierre angulaire de l'architecture SMA. C'est un `TypedDict` partagé entre tous les agents, avec une convention d'écriture stricte : chaque agent possède ses champs dédiés et ne peut pas écrire dans les champs d'un autre.

```python
class GraphState(TypedDict):
    # Input — écrit par l'entreprise, lu par A1, A2
    fiche_poste: str

    # A2 écrit, lu par A3a, A4
    profil_competences: dict

    # A3a écrit, lu par A3b
    requetes_recherche: dict

    # A3b écrit, lu par A3c
    resultats_bruts: list[dict]

    # A3c écrit (reducer: append pour accumulation parallèle)
    profils_bruts: Annotated[list[Candidat], operator.add]

    # A6 écrit, lu par A4(×N)
    profils_dedupliques: list[Candidat]

    # A4 écrit (reducer: append — N instances via Send)
    candidats_scores: Annotated[list[CandidatScore], operator.add]

    # A5 écrit (reducer: append — N instances via Send)
    candidats_valides: Annotated[list[CandidatValide], operator.add]

    # A7 écrit (reducer: append)
    messages_envoyes: Annotated[list[dict], operator.add]

    # A1 écrit, lu par le recruteur humain
    rapport_final: str
```

Les champs annotés `Annotated[list, operator.add]` sont des **reducers** : lors de l'exécution parallèle via `Send()`, N instances d'un agent écrivent simultanément dans ces listes, et LangGraph les fusionne automatiquement sans conflit. C'est l'implémentation formelle du pattern **Map-Reduce** dans un contexte SMA.

#### 4.2.3 Communication inter-agents

Les agents ne s'appellent pas directement. La communication se fait **exclusivement via le blackboard** (`GraphState`). C'est le pattern **Tableau Noir** des SMA classiques :

- **A2** lit `fiche_poste` et écrit `profil_competences`
- **A3a** lit `profil_competences` et écrit `requetes_recherche`
- **A4** lit `profil_dedupliques` (×1 profil par instance) et écrit dans `candidats_scores` (reducer)
- **A5** lit `candidats_scores` (×1 score par instance) et écrit dans `candidats_valides` (reducer)

Cette séparation stricte des droits d'écriture garantit l'**indépendance formelle des agents** : chaque agent peut être modifié, remplacé ou testé sans impacter les autres.

#### 4.2.4 L'orchestrateur : le pattern Superviseur

`src/graph.py` construit le graphe LangGraph. La fonction `build_graph()` définit la topologie complète :

```python
def build_graph(with_interrupt: bool = True) -> StateGraph:
    graph = StateGraph(GraphState)
    
    # Nœuds
    graph.add_node("orchestrateur", orchestrateur_node)
    graph.add_node("analyste", analyste_node)
    graph.add_node("chercheur_stratege", stratege_node)    # A3a
    graph.add_node("chercheur_collecteur", collecteur_node) # A3b
    graph.add_node("chercheur_filtre", filtre_node)         # A3c
    graph.add_node("deduplicateur", deduplicateur_node)
    graph.add_node("evaluateur", evaluateur_node)
    graph.add_node("reduce_scores", reduce_scores_node)
    graph.add_node("verificateur", verificateur_node)
    graph.add_node("reduce_validations", reduce_validations_node)
    graph.add_node("injection_rag", injection_rag_node)
    graph.add_node("recruteur", recruteur_node)
    graph.add_node("rapport", rapport_node)
    graph.add_node("persistance", persistance_node)         # A8
    
    # Fan-out parallèle via Send()
    graph.add_conditional_edges("deduplicateur", route_to_evaluateurs, 
                                ["evaluateur", "reduce_scores"])
    graph.add_conditional_edges("reduce_scores", route_to_verificateurs,
                                ["verificateur", "reduce_validations"])
    
    # Routage conditionnel
    graph.add_conditional_edges("injection_rag", route_apres_verification,
                                {"recruteur": "recruteur", "rapport": "rapport"})
    
    # HITL : interruption avant le recruteur
    if with_interrupt:
        compile_kwargs["interrupt_before"] = ["recruteur"]
    
    return graph.compile(checkpointer=MemorySaver(), **compile_kwargs)
```

**LangGraph joue ici le rôle de bus de messages** : chaque arête est un canal typé, le `GraphState` est le message. Ce choix délibéré évite l'overhead de Kafka ou RabbitMQ tout en conservant les propriétés sémantiques d'un bus (découplage, traçabilité, replay via le checkpointer).

#### 4.2.5 Justification du LLM : Groq + llama-3.3-70b-versatile

Plusieurs solutions LLM ont été considérées :

- **Ollama (local)** : testé initialement, mais les modèles locaux (Mistral, LLaMA) consommaient trop de RAM et crashaient le MacBook Air de développement.
- **GPT-4 / Claude API** : payants, incompatibles avec la contrainte du prototype académique gratuit.
- **Groq** : provider cloud offrant un **free tier à 100 000 tokens/jour** sans carte bancaire. Le modèle `llama-3.3-70b-versatile` offre un excellent rapport qualité/vitesse pour les tâches de scoring et de génération de texte structuré (JSON).

La couche d'abstraction `get_llm()` dans `src/config.py` garantit l'indépendance du vendor :

```python
def get_llm(temperature: float = 0):
    from langchain_groq import ChatGroq
    llm = ChatGroq(model=GROQ_MODEL, temperature=temperature)
    return llm.with_retry(stop_after_attempt=6, wait_exponential_jitter=True)
```

Le `.with_retry()` gère automatiquement les erreurs 429 (rate limiting Groq) avec backoff exponentiel — une décision technique indispensable en contexte d'exécution parallèle.

### 4.3 Fonctionnalités détaillées — Les huit agents

#### 4.3.1 A1 — Orchestrateur (pattern Superviseur)

**Fichier :** `src/agents/orchestrateur.py`  
**Rôle :** Point d'entrée du pipeline. Reçoit la fiche de poste et produit le rapport final structuré en Markdown.  
**Pattern :** Superviseur — topologie étoile, délégation formelle via le flux du graphe.

```python
def orchestrateur_node(state: GraphState) -> dict:
    _log.info("Réception fiche de poste : %s...", state['fiche_poste'][:80])
    return {
        "messages": [
            HumanMessage(content=f"[Orchestrateur] Lancement recrutement :\n{state['fiche_poste']}")
        ]
    }
```

Le nœud `rapport_node` (également dans ce fichier) génère le rapport final : tableau des candidats triés par score, statistiques de filtrage, métriques de durée, messages de contact. Il utilise le prompt `ORCHESTRATEUR_RAPPORT_SYSTEM` qui structure le rapport avec 5 sections (résumé, statistiques, classement, actions, recommandations).

#### 4.3.2 A2 — Analyste de poste

**Fichier :** `src/agents/analyste.py`  
**Rôle :** Transformer une fiche de poste en texte libre en un profil de compétences structuré JSON.  
**Inputs :** `fiche_poste` (texte libre)  
**Outputs :** `profil_competences` (JSON typé)

**Prompt system :**
```
Tu es un analyste expert en recrutement. Ta mission est d'analyser une fiche
de poste et d'en extraire une structure de compétences précise.
[...]
- "hard_skills": liste des compétences techniques
- "soft_skills": compétences comportementales
- "niveau_experience": "alternant"|"stagiaire"|"junior"|"confirme"|"senior"|"indifferent"
- "localisations": liste des villes. ATTENTION : AWS, GCP, Azure ne sont PAS des villes.
```

**Exemple d'entrée/sortie :**

*Entrée :*
```
"Développeur Python senior, 5 ans, Paris ou remote, FastAPI, LangGraph, Docker, RAG"
```

*Sortie JSON (produite par A2) :*
```json
{
  "hard_skills": ["Python", "FastAPI", "LangGraph", "Docker", "RAG"],
  "soft_skills": ["communication", "autonomie"],
  "experience_min": 5,
  "niveau_experience": "senior",
  "localisations": ["Paris"],
  "remote": true
}
```

**Décision de design notable :** Un enrichissement déterministe complète la réponse LLM via `_inferer_niveau_experience()` — une fonction regex qui détecte les patterns "alternance", "stage", "junior", "senior" dans la fiche. Ce guard empêche le LLM de mal interpréter le niveau d'expérience demandé, bug identifié en production (AWS/GCP classifiés comme villes lors des premières versions).

#### 4.3.3 A3 : La division en trois sous-agents

L'agent collecteur initial (A3) a été **refactorisé en trois sous-agents spécialisés** après avoir identifié que la responsabilité unique était violée : un seul agent ne peut pas raisonnablement générer des requêtes de recherche, collecter les résultats ET filtrer le bruit.

**A3a — Stratège de recherche** (`src/agents/chercheur_stratege.py`)  
Génère un plan de recherche structuré par source (DDG, LinkedIn, GitHub, Stack Overflow, sites CV) en utilisant le LLM. Les requêtes sont enrichies par des opérateurs déterministes : `site:linkedin.com/in/ "Python" "FastAPI"`, `language:python followers:>5`, `intitle:"développeur Python"`.

**A3b — Collecteur** (`src/agents/chercheur_collecteur.py`)  
Exécute le plan de A3a en appelant concrètement DuckDuckGo (via `duckduckgo-search`), l'API GitHub officielle et l'API Stack Overflow. Un délai de 1,5 secondes est imposé entre les appels DDG pour respecter le rate limit. Déduplication par URL avant transmission.

**A3c — Filtre anti-bruit** (`src/agents/chercheur_filtre.py`)  
C'est le nœud le plus complexe du pipeline en termes d'ingénierie. Il fonctionne en **4 passes algorithmiques sans LLM** :

*Passe 1 — Pré-filtre URL (domaines) :*
```python
_NOISE_DOMAINS = (
    "indeed.com", "glassdoor.com", "welcometothejungle.com",
    "hellowork.com", "apec.fr", "francetravail.fr", "lever.co",
    "greenhouse.io", "codeur.com", "superprof.fr", ...  # 30+ domaines
)
```

*Passe 2 — Pré-filtre mots-clés (snippet DDG) :*
```python
_NOISE_KEYWORDS = (
    "nous recherchons", "postuler", "offre d'emploi",
    "we are hiring", "job description", "apply now", ...  # 50+ patterns
)
```

*Passe 3 — Blacklist RAG inter-runs :*
```python
if _memoire is not None and _memoire.est_blackliste(url):
    n_blacklist_drop += 1
    continue  # skip avant même de scraper
```

*Passe 4 — Post-filtre après scraping :*
```python
if _is_noise_text(profil_brut) or _is_aggregated_profile(title, profil_brut):
    n_post_drop += 1
    continue
```

**Sur un run de référence :** 46 hits bruts → 13 après filtrage (taux de bruit : 68%).

#### 4.3.4 A6 — Déduplicateur

**Fichier :** `src/agents/deduplicateur.py`  
Fusionne les profils identiques collectés via différentes sources. Détection par URL identique ou similarité de nom (> 85% via `SequenceMatcher` de Python). En cas de fusion, les `profil_brut` sont concaténés pour maximiser l'information disponible à A4.

#### 4.3.5 A4 — Évaluateur (×N parallèles, avec cache RAG)

**Fichier :** `src/agents/evaluateur.py`  
**Rôle :** Évaluer UN candidat par rapport au profil de compétences. Appelé N fois en parallèle via `Send()`.

**Prompt system (extrait) :**
```
BARÈME DE SCORING :
- 85-100 : Profil excellent — coche toutes les compétences + expérience conforme
- 70-84  : Bon profil — 70-80% des compétences, quelques lacunes mineures
- 50-69  : Profil intéressant — compétences de base, lacunes identifiables
- 30-49  : Profil partiel — compétences connexes, peu de correspondance directe
- 0-29   : Hors sujet — page web générique, offre d'emploi, article...

RÈGLES :
- Les hard skills listés en premier ont un poids double
- Un candidat maîtrisant 70% des hard skills requis ne doit PAS scorer < 60
```

**Mécanisme de cache RAG :**
```python
if url:
    cache = get_memoire().get_score_cache(url, fiche_poste)
    if cache is not None:
        # Score réutilisé, LLM skippé → économie d'appel Groq
        return {"candidats_scores": [CandidatScore(score_global=cache["score"])]}
```

Avant chaque appel LLM, l'agent vérifie si l'URL a déjà été évaluée pour un poste similaire (similarité cosine ≥ 0.85). Si oui, le score stocké est retourné directement sans consommer de tokens Groq. **Sur le run 2 d'une même fiche, le gain estimé est de 30 à 40% de durée.**

#### 4.3.6 A5 — Vérificateur (×N parallèles) — La pièce de résistance

**Fichier :** `src/agents/verificateur.py`  
**Rôle :** Validation pair-à-pair du score A4. C'est l'implémentation du pattern **Validation Pair-à-Pair** identifié dans nos études SMA : A4 produit, A5 contrôle indépendamment.

Ce nœud est architecturalement le plus sophistiqué. Il combine **deux couches de validation** :

**Couche 1 — LLM (vérification sémantique) :**
```python
_VERIFICATEUR_UNITAIRE_SYSTEM = """
Tu contrôles UN seul candidat à la fois.
- "valide" uniquement si profil clair d'une personne + compétences liées au poste.
- "invalide" si page entreprise, formation, article, offre, professeur...
- "douteux" si personne possible mais preuves insuffisantes.
- Ne remets JAMAIS score_final à 0 sauf profil complètement hors sujet.
- Garde score_global_A4 comme base, ajuste ±20 maximum.
"""
```

**Couche 2 — Guards déterministes (vérification algorithmique) :**

```python
# Guard 1 : détection page non-candidat
if _profil_non_candidat(nom, profil_brut, url):
    score_final = min(score_final, 20.0)
    statut = "invalide"

# Guard 2 : vérification adéquation minimale
ok, raison = _adequation_minimale(profil_requis, nom, profil_brut)
if not ok:
    score_final = min(score_final, 45.0)
    statut = "invalide"

# Guard 3 : incompatibilité d'expérience
incompatible, raison = _experience_incompatible(profil_brut, niveau_requis)
if incompatible:
    score_final = min(score_final, 45.0)
    statut = "invalide"

# Guard 4 : upgrade douteux → valide (profil LinkedIn avec bon score)
if statut == "douteux" and score_a4 >= SCORE_SEUIL_CONTACT and "/in/" in url:
    statut = "valide"  # LinkedIn bloque le scraping, on fait confiance au score A4
```

**La fonction `_adequation_minimale()`** vérifie que les hard skills requis sont réellement visibles dans le texte du profil. Elle utilise un dictionnaire d'alias (`_SKILL_ALIASES`) pour normaliser : `"docker"` reconnaît aussi `"container"` et `"conteneur"`.

**L'upgrade automatique** est une décision architecturale importante : LinkedIn bloque 100% des scrapings sur les profils `/in/`. A5 reçoit donc souvent un snippet DDG de 150 caractères. Si A4 a scoré ≥ 75 sur ce snippet et que l'URL est un vrai profil LinkedIn individuel (heuristique `_profil_personne_probable()`), A5 valide le candidat en lui faisant confiance. Sur le run de référence, 3 candidats sur 5 valides ont bénéficié de cet upgrade.

#### 4.3.7 Nœud Injection RAG

**Fichier :** `src/agents/injection_rag.py`  
**Rôle :** Après la réduction des validations A5, enrichir les résultats avec des candidats connus des runs précédents.

```python
def injection_rag_node(state: GraphState) -> dict:
    fiche_poste = state.get("fiche_poste", "")
    candidats_actuels = state.get("candidats_valides", [])
    urls_actuels = {c.get("url") for c in candidats_actuels if c.get("url")}
    
    connus = get_memoire().get_candidats_connus(fiche_poste)  # seuil cosine ≥ 0.75
    
    nouveaux = [c for c in connus 
                if c.get("url") not in urls_actuels]  # anti-doublon
    
    return {"candidats_valides": nouveaux} if nouveaux else {}
```

Sur le **Run 1** (base RAG vide) : 0 candidats injectés. Sur le **Run 2** (même fiche) : les 5 candidats valides du Run 1 sont réinjectés automatiquement, même si DDG ne les retrouve pas ce run-là.

#### 4.3.8 A7 — Recruteur

**Fichier :** `src/agents/recruteur.py`  
**Rôle :** Rédiger des messages de contact personnalisés pour les meilleurs candidats.

**Logique de routage conditionnel** (dans `src/graph.py`) :
```python
def route_apres_verification(state: GraphState) -> str:
    meilleur_score = max(c["score_final"] for c in candidats_valides)
    
    if meilleur_score >= SCORE_SEUIL_CONTACT:  # 75 par défaut
        return "recruteur"  # mode absolu
    
    viables = [c for c in candidats_valides if c["score_final"] >= SCORE_SEUIL_VIABLE]  # 40
    if viables:
        return "recruteur"  # mode relatif : top-3 meilleurs viables
    
    return "rapport"  # aucun candidat viable
```

**Prompt system (extrait) :**
```
Pour chaque candidat validé, rédige un message professionnel (max 150 mots) qui :
1. Mentionne spécifiquement ce qui a retenu l'attention dans leur profil
2. Présente brièvement le poste
3. Propose un échange
Le ton doit être professionnel mais humain, pas de copier-coller générique.
```

#### 4.3.9 A8 — Persistance RAG

**Fichier :** `src/agents/persistance.py`  
**Rôle :** Nœud terminal. Stocker la fiche de poste et les candidats évalués dans ChromaDB.

**Règle de déduplication importante :**
```python
for c in candidats_valides:
    cid = c["candidat_id"]
    if cid not in seen or c.get("statut") == "invalide":
        seen[cid] = c  # le statut "invalide" (rejet HITL) l'emporte sur "valide"
```

Si un candidat a été approuvé lors du Run 1 mais rejeté via HITL lors du Run 2, il sera marqué "invalide" en base et blacklisté pour les runs futurs. Cette logique garantit que les décisions humaines de rejet sont mémorisées.

**Stratégie de persistance :**
- `statut="valide"` → cache de score pour runs futurs (A4 le réutilise)
- `statut="invalide"` → blacklist inter-runs (A3c l'exclut avant scraping)
- `statut="douteux"` → **non persisté** (incertitude trop élevée pour servir de référence)

### 4.4 La mémoire RAG : architecture et fonctions

**Fichier :** `src/tools/rag.py`  
**Technologie :** ChromaDB (local, `./data/chromadb/`) + SentenceTransformers (`all-MiniLM-L6-v2`, ~80 Mo)

#### 4.4.1 Architecture à double collection

```
ChromaDB
├── collection: "fiches_poste"
│   ├── id: hash SHA1 de la fiche (12 chars)
│   ├── document: texte de la fiche (3000 chars max)
│   └── metadata: {longueur}
│
└── collection: "candidats_evalues"
    ├── id: candidat_id (UUID 8 chars)
    ├── document: profil_brut (2000 chars max)
    └── metadata: {nom, score, source, remarques, fiche_id, statut, url, last_seen}
```

Le `fiche_id` (hash de la fiche de poste) **rattache chaque candidat à la fiche pour laquelle il a été évalué**. C'est la clé de voûte du système : sans ce lien, la calibration inter-postes serait incorrecte (un candidat excellent pour un poste Python serait proposé pour un poste Java).

#### 4.4.2 Trois fonctions actives

**1. Blacklist inter-runs (utilisée par A3c) :**
```python
def est_blackliste(self, url: str) -> bool:
    # Requête purement metadata (pas d'embedding → très rapide)
    results = self._candidats.get(
        where={"url": {"$eq": url}},
        include=["metadatas"],
    )
    return any(m.get("statut") == "invalide" for m in results.get("metadatas", []))
```
Économie : scraping + appels A4 + A5 pour chaque URL invalide connue.

**2. Cache de score (utilisé par A4) :**
```python
def get_score_cache(self, url: str, fiche_poste: str, seuil_fiche: float = 0.85):
    # Si l'URL a déjà été évaluée pour une fiche similaire (cosine ≥ 0.85)
    # retourne le score sans appel LLM
    fiche_ids_ok = set(self._fiches_similaires_ids(fiche_poste, seuil_fiche))
    metas = [m for m in metas if m.get("fiche_id", "") in fiche_ids_ok]
    return {"score": best["score"], ...} if metas else None
```
Économie : un appel Groq par candidat mis en cache.

**3. Injection proactive (utilisée par injection_rag) :**
```python
def get_candidats_connus(self, fiche_poste: str, seuil_fiche: float = 0.75,
                         max_age_jours: int = 30):
    # Retourne les candidats validés récents pour un poste similaire
    # Filtre : fiche similaire (cosine ≥ 0.75) ET dernière vue < 30 jours
```

**Propriété d'apprentissage cumulatif :** Le système n'apprend pas au sens de l'entraînement de modèles (les poids Groq sont fixes). Il accumule de la **connaissance opérationnelle** : chaque run enrichit la base et rend les suivants plus rapides et plus précis. C'est un apprentissage par mémorisation à rendement croissant.

### 4.5 Le Human-in-the-Loop

Le HITL est implémenté via le mécanisme natif de LangGraph `interrupt_before` :

```python
app = graph.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["recruteur"]  # pause avant A7
)
```

Lorsque le graphe atteint le nœud Recruteur, l'exécution est suspendue. L'état complet du graphe est **sérialisé par le MemorySaver**. L'API expose alors un endpoint de décision :

```
POST /runs/{run_id}/hitl
Body: {
    "decision": "approve" | "skip" | "edit",
    "candidats": [...]  # optionnel, pour "edit"
}
```

- **`approve`** : reprend le pipeline tel quel.
- **`skip`** : marque tous les candidats comme invalides (mémorisé en RAG via A8 pour les runs futurs).
- **`edit`** : remplace la liste de candidats par une version éditée en JSON.

L'interface NiceGUI affiche un **panneau de validation HITL** avec les candidats, leurs scores, leurs URLs et une zone d'édition JSON. Un bouton "Approuver", "Refuser" et "Modifier" permettent les trois actions.

### 4.6 L'API Gateway et le streaming SSE

**Fichier :** `src/api.py`

L'API Gateway FastAPI expose le pipeline via des endpoints REST. La fonctionnalité de **streaming Server-Sent Events (SSE)** est particulièrement importante pour l'expérience utilisateur : l'interface NiceGUI peut afficher la progression en temps réel pendant les ~173 secondes d'un run.

```
GET /runs/{id}/stream  →  flux SSE :
  data: {"type": "node_completed", "node": "analyste", "duration_s": 3.2}
  data: {"type": "node_completed", "node": "chercheur_stratege", "duration_s": 5.1}
  data: {"type": "awaiting_hitl", "candidats": [...]}
  data: {"type": "run_done", "rapport": "..."}
```

La persistance des runs est assurée par **SQLite** (`data/runs.sqlite`) : les runs survivent aux redémarrages de l'API. L'API maintient également un dictionnaire en mémoire `_runs` pour les queues SSE actives.

**Annulation propre :** Le endpoint `POST /runs/{id}/cancel` permet d'interrompre un run en cours entre deux nœuds. L'interruption est signalée via un `threading.Event` et le run est marqué comme "cancelled" en base.

### 4.7 L'interface graphique NiceGUI

**Fichiers :** `src/ui/app.py`, `src/ui/layout.py`, `src/ui/api_client.py`

L'UI est **strictement cliente** de l'API REST : elle ne connaît pas LangGraph et ne touche pas au code Python des agents. Cette séparation garantit que l'UI peut être remplacée sans modifier le backend.

Cinq pages sont disponibles :

1. **Accueil** : formulaire de lancement (fiche de poste, checkbox HITL, 5 derniers runs).
2. **Run live** : timeline SSE avec icônes par nœud, diagramme Mermaid coloré (nœud vert = terminé, orange = HITL en attente), bouton d'annulation.
3. **Rapport** : tableau des candidats avec badges de score colorés (vert ≥ 75, orange ≥ 50, rouge < 50), liens cliquables vers les profils.
4. **RAG** : état de la mémoire vectorielle (nombre de candidats, fiches), recherche sémantique de profils similaires.
5. **Métriques** : durées par étape, statistiques de filtrage, historique des exports JSON.

### 4.8 Le mode microservices

En plus du mode monolithique (LangGraph), le projet implémente un mode microservices complet via Docker Compose.

**Fichier :** `docker-compose.microservices.yml`

```
svc-analyste    (port 8001)  ← A2
svc-chercheur   (port 8002)  ← A3 (stratège + collecteur + filtre)
svc-evaluateur  (port 8003)  ← A4 (avec cache RAG)
svc-verificateur (port 8004) ← A5 (avec guards)
svc-recruteur   (port 8005)  ← A7
svc-orchestrateur (port 8006) ← remplace LangGraph
api-gateway     (port 8000)  ← point d'entrée public
sma-ui          (port 8080)  ← NiceGUI
```

L'orchestrateur HTTP (`services/orchestrateur/main.py`) reproduit la logique LangGraph via appels HTTP et `asyncio.gather()` pour le parallélisme A4/A5. Le volume `./data:/app/data` est monté sur les services qui utilisent ChromaDB, garantissant le partage de la mémoire inter-runs même en mode distribué.

**Trade-offs des deux modes :**

| Critère | Monolithique (LangGraph) | Microservices (Docker) |
|---------|--------------------------|----------------------|
| Latence | Optimale (in-process) | +30-50% (HTTP) |
| Déployabilité | 1 processus | Cloud-ready |
| Scaling | Vertical | Horizontal par service |
| Débogage | Traces LangGraph | Logs distribués |
| RAG | Blacklist + cache + injection | Blacklist + cache + injection |
| HITL | Natif (LangGraph) | Orchestrateur HTTP |

**Lancer le mode microservices :**
```bash
docker compose -f docker-compose.microservices.yml up --build
```

**Lancer le mode local :**
```bash
./run_local.sh
```

### 4.9 Observabilité

**Fichier :** `src/observabilite.py`

Chaque agent appelle `m.debut("nom_etape")` et `m.fin("nom_etape", **kwargs)` pour tracer sa durée et ses métriques métier. L'export automatique en JSON à la fin de chaque run permet un audit complet.

```python
m.fin("A3c_filtre",
    n_entree=46,
    n_sortie=13,
    n_drop_url=18,
    n_drop_kw=8,
    n_drop_post=4,
    n_drop_blacklist=3,
    taux_bruit=0.68,
    n_scrape_fail=5
)
```

Exemple de sortie de métriques sur un run de référence :

```
A1_orchestrateur          0.01s
A2_analyste               3.2s
A3a_stratege              5.1s
A3b_collecteur            18.4s   n_hits=46  sources=['ddg','github','so']
A3c_filtre                22.1s   n_entree=46  n_sortie=13  taux_bruit=0.68
A6_deduplicateur          0.1s
A4_[×10 parallèles]       62s     (parallèle, non séquentiel)
A5_[×10 parallèles]       48s
injection_rag             0.3s    n_injectes=0
rapport                   4.2s
A8_persistance            1.8s    n_persistes=5
TOTAL                     173s
```

### 4.10 Les tests automatisés (91 tests)

**Répertoire :** `tests/`

| Fichier | Tests | Ce qui est vérifié |
|---------|-------|--------------------|
| `test_graph.py` | 28 | Topologie du graphe (16 nœuds, arêtes, présence des nœuds clés) |
| `test_verificateur_rules.py` | 5 | Guards déterministes A5 (non-candidat, adéquation minimale) |
| `test_stratege_queries.py` | 15 | Génération et structure des requêtes A3a |
| `test_api.py` | 43 | Endpoints API, HITL, annulation, persistance SQLite |
| `test_deduplicateur.py` | — | Logique de fusion des profils |
| `test_filtre.py` | — | Filtres anti-bruit URL et mots-clés |
| `test_rag.py` | — | Blacklist, cache, injection RAG |

**91/91 tests passent.** Les tests de graphe vérifient que la topologie est conforme à l'architecture définie — c'est une forme de test d'architecture formelle qui garantit la non-régression structurelle.

### 4.11 Étapes de réalisation chronologique

#### Étape 1 — Environnement et LLM provider

La première difficulté a été le choix du LLM. Ollama local avec Mistral 7B causait des crashes mémoire sur le MacBook Air (8 Go RAM). Après exploration, **Groq** a été retenu : free tier sans CB, modèle `llama-3.3-70b-versatile`, latence <2s par appel.

La configuration dans `.env` :
```bash
GROQ_API_KEY=sk_...
GROQ_MODEL=llama-3.3-70b-versatile
```

#### Étape 2 — Le premier agent : A2 l'Analyste

A2 a été implémenté en premier car il est le plus simple à tester (entrée : texte, sortie : JSON structuré). Il a permis de valider l'infrastructure : LangChain, ChatGroq, parsing JSON, gestion des erreurs de parsing.

Le bug des localisations (AWS classifié comme ville) a été identifié et corrigé dès cette étape en ajoutant une règle explicite dans le prompt : *"ATTENTION : AWS, GCP, Azure, cloud, remote ne sont PAS des localisations."*

#### Étape 3 — Le pipeline de collecte (A3)

Le pipeline de collecte a été la partie la plus itérative. Au départ, un seul agent A3 gérait tout : génération de requêtes, collecte, filtrage. Face à la complexité croissante et aux bugs difficiles à isoler, l'agent a été **divisé en A3a/A3b/A3c** — une refactorisation architecturale qui a considérablement amélioré la maintenabilité et la testabilité.

Le filtre anti-bruit a nécessité plusieurs itérations : les premières versions laissaient passer des offres d'emploi déguisées en profils. La liste `_NOISE_DOMAINS` (30+ domaines) et `_NOISE_KEYWORDS` (50+ patterns) ont été construites empiriquement en analysant les faux positifs run après run.

#### Étape 4 — Le fan-out parallèle (A4/A5)

L'implémentation du pattern `Send()` LangGraph pour le fan-out A4 et A5 a été la partie la plus technique. Le problème principal : la gestion des rate limits Groq en contexte d'appels parallèles. La solution : retry avec backoff exponentiel (`with_retry()`) + délais aléatoires (`random.uniform(0, 1)`) pour désynchroniser les tentatives.

#### Étape 5 — La mémoire RAG

ChromaDB a été intégré progressivement : d'abord la blacklist (simple requête metadata), puis le cache de score (requête avec filtre de fiche similaire), puis l'injection proactive. Chaque fonction a fait l'objet d'un test unitaire dédié.

La décision d'utiliser deux collections séparées (`fiches_poste` + `candidats_evalues`) liées par `fiche_id` a émergé de la nécessité d'éviter le biais de calibration inter-postes : sans ce lien, les candidats évalués pour un poste Java auraient pu biaiser l'évaluation de candidats pour un poste Python.

#### Étape 6 — HITL, API et UI

L'API FastAPI + streaming SSE a été implémentée pour rendre le pipeline accessible sans passer par la ligne de commande. Le streaming SSE a nécessité la mise en place d'une queue par run (`queue.Queue`) alimentée par un thread de surveillance des événements LangGraph.

L'UI NiceGUI a été construite en dernier, strictement cliente de l'API. Le composant diagramme Mermaid a été ajouté pour visualiser la progression du pipeline en temps réel.

#### Étape 7 — Microservices

La transformation en microservices a été la dernière étape. Chaque agent a été encapsulé dans un service FastAPI indépendant avec son propre Dockerfile. L'orchestrateur HTTP reproduit la logique LangGraph via `httpx` + `asyncio.gather()`.

### 4.12 Feature Model — Variabilité architecturale

Conformément à l'objectif 1 du TER, la variabilité architecturale du système a été formalisée dans le feature model suivant :

```
SMA Recrutement (racine)
├── Mode d'exécution [XOR]
│   ├── Local (monolithique, LangGraph)
│   └── Microservices (Docker Compose)
│
├── Fournisseur LLM [mandatoire, extensible]
│   └── Groq (llama-3.3-70b-versatile)  [défaut]
│       └── [extensible : toute API compatible LangChain]
│
├── HITL [XOR]
│   ├── Activé (interrupt_before=["recruteur"])
│   └── Désactivé (full auto)
│
├── Interface [OR — un ou plusieurs]
│   ├── CLI (src/main.py)
│   ├── API REST (FastAPI, port 8000)
│   └── UI Web (NiceGUI, port 8080)
│
└── Mémoire RAG [AND — les deux obligatoires]
    ├── Blacklist inter-runs (A3c)
    └── Cache de score (A4)
    [+ Injection proactive — activée automatiquement si base non vide]
```

Ce feature model répond directement à l'objectif 2 du TER (critères de choix) : le mode XOR Local/Microservices est guidé par le trade-off latence vs déployabilité cloud ; le HITL XOR est guidé par les exigences de confiance humaine dans les décisions de contact ; l'interface OR permet de coexister CLI, API et UI.

### 4.13 Analyse critique et résultats

#### 4.13.1 Résultats d'un run de référence

Fiche de poste : *"Développeur Python senior, 5 ans, Paris ou remote, FastAPI, LangGraph, Docker, RAG, bonne communication"* (21 mai 2026).

| Étape | Métrique | Valeur |
|-------|---------|--------|
| Collecte A3b | Profils bruts | 46 |
| Filtrage A3c | Après filtre | 13 (bruit : 68%) |
| Déduplication A6 | Après dédup | 12 |
| Évaluation A4 | Évalués (limite) | 10 |
| Validation A5 | Valides | 5 (dont 3 upgrades LinkedIn) |
| Recruteur A7 | Messages rédigés | 2 (score ≥ 75) |
| Durée totale | — | 173 secondes |

**Meilleurs candidats identifiés :**

| Candidat | Score | Source | Remarques A5 |
|----------|-------|--------|-------------|
| Srikanth Vanjre | 88 | LinkedIn | Senior Backend AI/RAG — excellent |
| Shubhangi Gaur | 80 | LinkedIn | Python/FastAPI senior |
| Nikita Koznev | 72 | LinkedIn | Python senior (upgrade auto) |

#### 4.13.2 Points forts

1. **Architecture formellement fondée** : six patterns SMA implémentés (blackboard, superviseur, map-reduce, validation pair-à-pair, routage conditionnel, HITL).
2. **Guards déterministes** : les agents LLM sont encadrés par des vérifications algorithmiques qui ne peuvent pas halluciner.
3. **RAG cumulatif** : le système apprend entre les runs sans modifier les poids du modèle.
4. **Observabilité** : métriques structurées par nœud, export JSON automatique, traçabilité complète.
5. **Dual mode** : deux architectures de déploiement opérationnelles pour le même pipeline.
6. **91 tests** : couverture complète de la topologie, des guards et des endpoints API.

#### 4.13.3 Limites identifiées

1. **Scraping LinkedIn bloqué** : 100% des profils `/in/` sont inaccessibles. L'upgrade automatique A5 compense partiellement mais introduit une incertitude.
2. **Quota Groq** : 100 000 tokens/jour ≈ 3-5 runs complets. Au-delà, il faut attendre le lendemain ou basculer sur `llama-3.1-8b-instant` (fallback documenté dans `.env.example`).
3. **Calibration empirique des seuils RAG** : les seuils de similarité fiche-à-fiche (0.75 pour l'injection, 0.85 pour le cache) ont été calibrés sur un petit nombre de runs. Un corpus plus large permettrait une calibration statistique.
4. **Injection RAG absente en mode microservices** : l'orchestrateur HTTP ne implémente pas encore l'injection proactive (seules blacklist et cache sont actives). C'est une limite assumée documentée.

---

## 5. Conclusion et bilan global

### 5.1 Synthèse du parcours

Ce TER a suivi un fil directeur cohérent : des fondements théoriques formels (SMA classiques) vers l'implémentation d'un système Agentic AI structuré par ces mêmes fondements. La phase bibliographique n'a pas été une formalité : elle a directement alimenté les décisions architecturales. La division A3a/A3b/A3c reflète le principe SRP des SMA (responsabilité unique par agent). Le blackboard `GraphState` implémente formellement le pattern Tableau Noir. Les guards déterministes d'A5 incarnent le paradigme neuro-symbolique hybride identifié dans les études.

Les trois objectifs du TER ont été atteints :

| Objectif | Livrable |
|----------|---------|
| Variabilité architecturale | Feature model à 5 dimensions |
| Critères de choix | Comparaison des frameworks, justification LangGraph |
| Architecture de référence | Prototype opérationnel (8 agents, RAG, HITL, microservices, API SSE, UI, 91 tests) |

### 5.2 Compétences acquises

**Sur les LLMs et le prompt engineering :**
- Structurer un prompt pour obtenir du JSON fiable (règles explicites, exemples de cas limites)
- Gérer les erreurs de parsing JSON en production
- Calibrer un barème de scoring via des règles métier dans le prompt
- Comprendre l'impact du `temperature=0` sur la reproductibilité

**Sur les architectures multi-agents :**
- Implémenter le pattern Blackboard avec droits d'écriture séparés
- Utiliser le fan-out `Send()` pour le parallélisme
- Construire un routage conditionnel basé sur les métriques de run
- Combiner validation LLM + guards déterministes pour la robustesse

**Sur le développement Python avancé :**
- FastAPI (async, SSE, Pydantic, SQLite)
- ChromaDB (collections, métadonnées, requêtes de similarité cosine)
- LangChain/LangGraph (graphes, reducers, checkpointing)
- Docker Compose (multi-services, volumes partagés, healthchecks)
- Tests pytest avec mocks

**Sur la gestion de projet :**
- Itérer sur une architecture en production (refactorisation A3)
- Calibrer empiriquement des hyperparamètres (seuils RAG)
- Gérer les contraintes de rate limiting des APIs externes

### 5.3 Réflexion critique sur l'Agentic AI

Ce projet confirme empiriquement les conclusions de notre analyse comparative : **l'Agentic AI sans structuration SMA est fragile**. Les premières versions du prototype (avant les guards déterministes d'A5, avant la division A3) produisaient des résultats incohérents et difficiles à déboguer. L'ajout progressif de patterns formels SMA (blackboard, séparation des responsabilités, validation pair-à-pair) a drastiquement amélioré la fiabilité.

L'Agentic AI est puissante pour les tâches cognitives (analyser une fiche de poste, évaluer sémantiquement un profil, rédiger un message personnalisé). Elle est fragile pour les tâches binaires (est-ce une page d'offre d'emploi ou un profil candidat ?). La solution n'est pas de lui demander de faire ce qu'elle ne fait pas bien — c'est de la compléter avec des algorithmes déterministes pour les tâches où la précision prime sur la flexibilité.

**Forces réelles :** compréhension sémantique, génération naturelle, adaptabilité à des entrées hétérogènes.  
**Faiblesses réelles :** coût en tokens, latence, non-déterminisme, hallucinations sur des faits précis.

### 5.4 Ouverture et perspectives

**Kubernetes :** Le mode microservices est architecturalement prêt pour Kubernetes. Chaque service est sans état local (le state est dans ChromaDB et SQLite). Le scaling horizontal d'A4 et A5 (les goulots d'étranglement) est directement applicable.

**API LinkedIn officielle :** Éliminerait la principale limite du système. Les scores passeraient de "corrects" à "précis" sur des profils réels.

**MARL pour l'amélioration continue :** Les agents A3a (Stratège) pourraient adapter leurs requêtes de recherche en fonction des scores obtenus — un apprentissage au sens strict, au-delà de la simple mémorisation.

**Gouvernance et traçabilité :** L'ajout d'un registre de décisions (quel agent a pris quelle décision, avec quelle confiance) renforcerait l'explicabilité du système — adressant directement les enjeux identifiés par Milosevic et Rabhi (2026) sur les communautés agentiques gouvernées.

---

## 6. Références

### Études SMA

1. Dorri, A., Kanhere, S., Jurdak, R. (2018). *Multi-Agent Systems: A Survey*. IEEE Access, 6, 28573-28593.
2. Maldonado, J. et al. (2024). *Architectures and Coordination Patterns in Multi-Agent Systems*. JAIR, 79.
3. Nguyen, T. et al. (2019). *Deep Reinforcement Learning for Multi-Agent Systems: A Review*. IEEE Transactions on Cybernetics, 50(9).
4. General Survey (2020). *A General Survey on Multi-Agent Coordination Mechanisms*. ACM Computing Surveys.
5. Gronauer, S., Diepold, K. (2021). *Multi-Agent Deep Reinforcement Learning: A Survey*. AI Review, 55.
6. Wang, J. et al. (2024). *Multi-Agent Systems in Industry 4.0*. WJARR.

### Études Agentic AI

7. Wavestone (2024). *Agentic AI Playbook — Architecture Patterns for Enterprise Systems*.
8. Abou Ali, H. et al. (2026). *Symbolic vs Neural Paradigms in Agentic AI Systems*. Expert Systems with Applications.
9. Alva, R., Pandey, S. (2024). *Modular Architecture for LLM-Based Agentic Systems*. arXiv.
10. Sapkota, B. et al. (2024). *AI Agents vs. Agentic AI: A Conceptual Taxonomy*. arXiv.
11. Patel, N. et al. (2025). *Security Risks in LLM-Based Agentic Systems*. ACM CCS.
12. Hughes, A. et al. (2025). *Safety and Alignment Challenges in Autonomous AI Agents*. Nature MI.
13. Vaidhyanathan, K., Taibi, D. (2026). *Framework Comparison for Agentic AI*. Software P&E.
14. TOSEM (2024). *A Year in TOSEM — SE4AI and AI4SE*.
15. Milosevic, D., Rabhi, F. (2026). *Agentic Communities: Governance and Human-AI Collaboration*. IEEE Software.
16. Schneider, J. (2025). *Agentic AI: Toward Goal-Directed Autonomous Systems*. IEEE Intelligent Systems.
17. Pati, S. et al. (2025). *Agentic AI Paradigm: Planning, Memory and Adaptation*. AI Magazine.

### Documents produits

- Dzermane, S. (2025). *Synthèse Générale — SMA et Éléments Connexes*. TER M1.
- Dzermane, S. (2025). *Synthèse Générale — Agentic AI et Éléments Connexes*. TER M1.
- Dzermane, S. (2025). *Analyse Comparative — Agentic AI et Systèmes Multi-Agents*. TER M1.
- Dzermane, S. (2025). *Glossaire des concepts — Comparaison des frameworks Agentic AI*. TER M1.

---

*Rapport généré le 21 mai 2026. Dépôt GitHub : github.com/Soof2/TER_M1_Agentic_AI*
