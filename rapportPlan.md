# Journal des décisions de conception

Ce fichier trace les choix d'architecture et de technologie effectués au cours
du TER, avec les arguments qui les justifient. Il alimente la section "Choix
techniques" du rapport final et explique pourquoi telle option a été retenue
contre telle autre.

---

## Interface graphique

### 1. Contexte et besoins réels

Le système à interfacer n'est ni un dashboard statique, ni une application
CRUD, ni un chatbot. C'est un **pipeline multi-agents long-running avec
validation humaine intermédiaire**. Les besoins concrets dictés par
l'architecture existante :

1. **Durée d'un run : 2 à 5 minutes** — la collecte multi-sources, le scraping
   et les N évaluations parallèles (pattern `Send/Reduce` de LangGraph) ne
   peuvent pas être synchrones côté UI. Un écran figé pendant plusieurs
   minutes est inacceptable pour une démo.

2. **Human-in-the-loop sur A7 Recruteur** — l'`interrupt_before` déjà
   configuré dans `src/graph.py` impose que l'UI puisse **pauser**, afficher
   les candidats présélectionnés, attendre une décision, puis **reprendre**
   le graphe avec `app.invoke(None, config)`. Le modèle d'exécution de
   l'UI doit gérer cette pause/reprise naturellement.

3. **Rendu markdown du rapport final** — A1 produit un rapport structuré
   qui doit être affiché lisiblement.

4. **Plusieurs vues distinctes** — formulaire de lancement, suivi d'un run,
   historique des runs, exploration de la mémoire RAG, métriques
   d'observabilité. Une application multi-pages est nécessaire.

5. **Contrainte d'équipe** — trois étudiants Python. Imposer un framework
   JavaScript réduirait la capacité de contribution à un seul membre.

6. **Contrainte pédagogique** — le jury évalue l'argumentaire architectural
   autant que le résultat. Chaque choix doit être défendable ; un modèle
   d'exécution forcé ou inadapté est un point faible.

### 2. Critères de sélection

| Critère | Importance | Justification |
|---|---|---|
| Cohérence Python pur | Élevée | Équipe 3 Python, déploiement Docker existant |
| Streaming live bidirectionnel | Élevée | Pipeline long, suivi temps réel indispensable |
| Modèle événementiel | Élevée | HITL naturel, pas de rerun global |
| Multi-pages propre | Moyenne | Plusieurs vues distinctes |
| Esthétique out-of-the-box | Moyenne | Démo jury |
| Intégration Mermaid / graphes | Moyenne | Visualiser le graphe des agents en direct |

### 3. Comparatif des technologies candidates

| Techno | Python | Streaming | HITL naturel | Multi-pages | Esthétique | Adéquation |
|---|---|---|---|---|---|---|
| **Streamlit** | oui | partiel | non, bricolé | moyen | correct | Inadéquat : modèle "rerun global" incompatible avec pipeline long + HITL |
| **Gradio** | oui | oui | non | non | correct | Inadéquat : paradigme chat/ML, pas pipeline |
| **NiceGUI** | oui | oui (WebSocket natif) | oui (callbacks) | oui | bon (Quasar/Material) | Adéquat |
| **Reflex** | oui | oui | oui | oui | bon | Adéquat mais build system plus lourd, moins stable |
| **Next.js + shadcn/ui** | non | oui (SSE ajouté) | oui | oui | excellent | Rejeté : double codebase, 2/3 de l'équipe bloquée |
| **Vite + React** | non | idem | oui | oui | bon | Rejeté : idem |

### 4. Décision : **NiceGUI**

#### Arguments retenus

1. **Modèle d'exécution adapté** — NiceGUI fonctionne comme une application
   web classique (événements, callbacks, état persistant côté serveur). Une
   action utilisateur déclenche une fonction Python, sans réexécuter le
   script entier. C'est le modèle attendu pour un pipeline asynchrone avec
   pauses.

2. **WebSocket intégré** — la progression du pipeline (nœud en cours,
   candidats scorés, métriques) est diffusée en push sans polling ni hack.

3. **Python pur** — les trois membres de l'équipe peuvent contribuer au
   frontend. Le déploiement reste couvert par le `docker-compose.yml`
   existant (un service supplémentaire).

4. **Composants adaptés au besoin** — `ui.table` (candidats triables),
   `ui.markdown` (rapport), `ui.mermaid` (graphe des agents),
   `ui.plotly` (métriques), `ui.timeline` (suivi du pipeline).

5. **Esthétique correcte sans effort** — base Quasar/Material, dark mode
   natif, cohérent sans CSS custom.

#### Arguments contre considérés

- Écosystème plus petit que Streamlit ou React : doc solide, communauté en
  croissance, mais moins de réponses Stack Overflow. Risque accepté car le
  cas d'usage reste dans ce que couvre la doc officielle.
- Rendu initial légèrement plus lourd qu'une page Streamlit simple : non
  bloquant pour une application interne de démonstration.

#### Pourquoi Streamlit a été rejeté malgré sa popularité

Streamlit réexécute l'intégralité du script à chaque interaction. Pour un
pipeline de 3 minutes avec HITL, cela impose :

- des threads Python détachés pour maintenir le run vivant pendant les
  interactions utilisateur ;
- un usage intensif de `st.session_state` pour mémoriser l'état de
  progression, l'index du dernier événement streamé, le statut HITL en
  attente ;
- des appels manuels à `st.rerun()` pour rafraîchir l'interface.

Devant un jury orienté architecture logicielle, ce contournement systématique
du modèle d'exécution est difficile à défendre : on lutte contre l'outil.
NiceGUI résout cela par construction.

### 5. Architecture retenue : **Option A — découplée via SSE**

```
┌───────────────────────┐   HTTP + SSE   ┌──────────────────────────┐
│  NiceGUI (port 8080)  │ ─────────────► │  FastAPI (port 8000)     │
│  - /                  │                │  - POST /recruter        │
│  - /runs              │ ◄───────────── │  - GET  /rapport/{id}    │
│  - /runs/{id}         │     events     │  - GET  /runs            │
│  - /rag               │                │  - GET  /runs/{id}/stream│  (nouveau, SSE)
│  - /metriques         │                │  - POST /runs/{id}/hitl  │  (nouveau)
└───────────────────────┘                └────────────┬─────────────┘
                                                       │
                                                LangGraph app
                                          (astream_events + checkpoint)
```

Deux endpoints sont ajoutés à l'API existante :

- `GET /runs/{id}/stream` — Server-Sent Events relayant
  `app.astream_events()` de LangGraph (début/fin de nœud, scores produits
  par A4, métriques `observabilite`).
- `POST /runs/{id}/hitl` — corps `{action, candidats_retenus}` qui reprend
  le graphe interrompu via `app.invoke(None, config)`.

#### Alternative considérée et rejetée

**Option B — NiceGUI importe directement `build_graph()`**. Plus simple (un
seul processus, pas de SSE). Rejetée car elle couple la couche présentation
à la logique d'orchestration, ce qui contredit l'argument d'architecture
"API Gateway" mis en avant dans le rapport. L'option A **renforce** au
contraire cet argument : l'API reste l'unique point d'entrée du SMA, et
l'UI est un client comme un autre (démontrable en montrant que `curl`
fonctionne en parallèle).

### 6. Pages de l'application

| Route | Rôle |
|---|---|
| `/` | Formulaire fiche de poste, paramètres (seuils, max profils), bouton lancer, vignettes des 3 derniers runs |
| `/runs` | Historique complet avec filtres (statut, score moyen, durée) |
| `/runs/{id}` | Suivi temps réel : timeline des agents, graphe Mermaid avec nœud courant surligné, log d'événements, cartes candidats qui apparaissent au fil de A4, écran HITL avec tableau et boutons approuver/refuser |
| `/runs/{id}/rapport` | Rendu markdown du rapport final, bouton export |
| `/rag` | Explorateur de la base ChromaDB : fiches stockées, candidats par fiche, distribution des scores, vérification concrète du calibrage par fiche |
| `/metriques` | Visualisations Plotly sur les exports JSON de `observabilite.py` (durée par nœud, taux de bruit A3c, N candidats collectés par source) |

### 7. Points valorisables pour la démo et le rapport

- **Graphe Mermaid avec nœud courant surligné en direct** : démonstration
  visible du flux SMA, directement liée au schéma du rapport.
- **Cartes candidats apparaissant une par une pendant A4** : illustration
  concrète du pattern Map/Reduce via le reducer `Annotated[..., operator.add]`.
- **Comparaison visuelle score A4 / score A5** : rend tangible le pattern
  de validation pair-à-pair.
- **Explorateur RAG montrant le lien fiche↔candidats** : illustre la
  décision architecturale du RAG calibré par fiche.

### 8. Plan de réalisation

1. Ajouter les endpoints SSE et HITL à FastAPI.
2. Squelette NiceGUI (routing, layout, menu latéral).
3. Page `/` — formulaire et lancement.
4. Page `/runs/{id}` — timeline live + Mermaid dynamique.
5. Flow HITL complet (pause, tableau, reprise).
6. Pages rapport, RAG, métriques.
7. Docker : ajouter le service `ui` dans `docker-compose.yml`.

---

## Mémoire RAG calibrée par fiche de poste

### 1. Problème identifié dans la version initiale

La première version du RAG (`src/tools/rag.py`) stockait chaque candidat
évalué avec son `profil_brut`, son `score`, sa `source` et les `remarques`
produites par A5. À l'évaluation d'un nouveau candidat, A4 interrogeait
cette base avec le profil brut du candidat courant et injectait les deux
plus similaires dans le prompt, sous la forme :

```
Profils similaires évalués lors de runs précédents (à titre de référence) :
  - Alice Dupont | score=85/100 | ...
```

Cette conception présente un **défaut structurel** : la fiche de poste pour
laquelle chaque candidat a été évalué n'était pas stockée. Illustration
concrète du biais introduit :

- Run #1 — fiche "Développeur Python senior Paris" → Alice (Python 7 ans,
  ML) est évaluée **85/100**.
- Run #2 — fiche "Chef de projet marketing B2B Lyon". On collecte un
  candidat "Martin, data analyst Python, 3 ans". Sa similarité cosine
  avec le profil d'Alice est élevée (mots "Python", "data" en commun).
  Le RAG remonte Alice et son score de 85 dans le prompt.
- Conséquence : le LLM reçoit un signal de calibration *"un profil
  similaire a obtenu 85"* alors qu'Alice n'a **aucun rapport avec la fiche
  marketing** en cours d'évaluation. Le scoring de Martin est biaisé vers
  le haut.

Le RAG, censé améliorer la calibration, dégradait donc potentiellement la
qualité des évaluations inter-fiches.

### 2. Solution retenue : deux collections reliées par `fiche_id`

La base ChromaDB comporte désormais **deux collections** :

| Collection | Clé | Document | Métadonnées |
|---|---|---|---|
| `fiches_poste` | `fiche_id` (hash SHA1 du texte normalisé) | texte de la fiche (3 000 chars max) | longueur |
| `candidats_evalues` | `candidat_id` | `profil_brut` (2 000 chars max) | nom, score, source, remarques, **fiche_id** |

La procédure de lecture dans A4 devient :

1. Embedder la fiche courante.
2. Interroger la collection `fiches_poste`, récupérer les fiches dont la
   similarité cosine dépasse un seuil `seuil_fiche` (0,5 par défaut).
3. **Si aucune fiche ne dépasse le seuil** → retourner une liste vide.
   Aucun contexte RAG n'est injecté dans le prompt de A4.
4. Sinon → interroger `candidats_evalues` avec filtre
   `where={"fiche_id": {"$in": [fiches_retenues]}}` pour ne remonter que
   les candidats évalués dans un contexte de poste comparable.

### 3. Arguments et tradeoffs

#### Arguments pour cette approche

- **Élimine le biais inter-fiches** : un candidat n'est proposé comme
  référence que si la fiche courante ressemble à celle pour laquelle il
  avait été évalué.
- **Silence explicite quand inapplicable** : au premier run ou face à une
  fiche inédite, le RAG se tait plutôt que d'injecter du bruit. Le prompt
  reste propre.
- **Coût acceptable** : la requête supplémentaire sur `fiches_poste` est
  exécutée en mémoire locale par ChromaDB, pour un nombre de fiches qui
  reste petit (au plus quelques dizaines sur la durée d'un TER).
- **Idempotence** : le `fiche_id` est un hash déterministe du texte
  normalisé (espaces compressés, casse unifiée). Relancer le même run ne
  crée pas de doublon de fiche.

#### Tradeoffs assumés

- **Valeur ajoutée nulle au premier run** sur une fiche inédite. C'est
  une propriété correcte : le RAG ne fabrique pas de signal là où il n'y
  en a pas.
- **Choix du seuil** : 0,5 est retenu comme compromis entre sensibilité
  (trop bas → on retombe dans le biais inter-fiches) et utilité (trop
  haut → le RAG ne se déclenche presque jamais). Valeur ajustable via
  paramètre de `rechercher_similaires()`, donc testable empiriquement.
- **Similarité sémantique, pas taxonomique** : deux fiches "Dev Python
  senior Paris" et "Dev Python junior Lyon" sont jugées proches par
  l'embedding. C'est souhaitable dans la majorité des cas, mais un
  filtrage explicite par seniorité reste une amélioration possible si le
  besoin émerge.

### 4. Garanties formelles

Trois garanties testées unitairement (voir `tests/test_rag.py`,
classe `TestCalibrationParFiche`) :

1. **Hash stable** — deux textes identiques au whitespace et à la casse
   près produisent le même `fiche_id` → upsert idempotent.
2. **Isolation inter-fiches** — deux fiches très différentes en base,
   fiche courante proche de la première : seuls les candidats rattachés
   à la fiche similaire remontent.
3. **Fallback silencieux** — si aucune fiche stockée n'atteint le seuil,
   la recherche retourne `[]` sans exception et sans contexte injecté.

### 5. Rétrocompatibilité

La signature de `rechercher_similaires(profil_brut, fiche_poste=None, ...)`
conserve le comportement historique (recherche globale sans filtre) quand
`fiche_poste` est omis. Cela permet de garder les tests existants et
facilite la migration progressive si d'autres consommateurs du RAG étaient
ajoutés.

### 6. Impact sur les autres agents

- **A8 Persistance** — upserte désormais la fiche courante dans
  `fiches_poste` puis passe le `fiche_id` lors de chaque
  `ajouter_candidat()`.
- **A4 Évaluateur** — reçoit `fiche_poste` via le payload du `Send()`
  du graphe (modification mineure dans `src/graph.py`), puis le transmet
  à `rechercher_similaires()`.

Les autres agents (A1, A2, A3, A5, A6, A7) sont **inchangés**. La
modification est confinée à la couche persistance et à un paramètre
supplémentaire en lecture.
