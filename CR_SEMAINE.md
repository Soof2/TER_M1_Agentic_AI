# Compte rendu — Semaine du 7 au 12 avril 2026

**Projet** : SMA de Recrutement Automatisé avec LangGraph  
**Cadre** : TER Master IA & Data  
**Équipe** : 3 personnes  

---

## Résumé

Cette semaine, le pipeline complet à 7 agents a été implémenté et testé de bout en bout pour la première fois. Le premier test a échoué (0 candidat contacté sur 15 profils collectés) à cause du bruit massif ramené par l'agent Chercheur (A3). Un refactoring majeur d'A3 a permis de réduire le bruit de ~67 % à ~10 %, et le deuxième test a abouti à 1 candidat effectivement contacté — premier succès du système.

---

## Travail réalisé

### 1. Implémentation du pipeline complet (7 agents)

Les 7 agents du SMA sont opérationnels et connectés dans le graphe LangGraph :

| Agent | Rôle | Fichier |
|-------|------|---------|
| A1 Orchestrateur | Superviseur, coordonne le flux, produit le rapport final | `src/agents/orchestrateur.py` |
| A2 Analyste | Extrait hard/soft skills, contraintes, mots-clés depuis la fiche de poste | `src/agents/analyste.py` |
| A3 Chercheur | Recherche de profils web (DDG + scraping + filtrage) | `src/agents/chercheur.py` |
| A4 Évaluateur (×N) | Scoring multicritères par candidat (0-100), parallélisé via Send() | `src/agents/evaluateur.py` |
| A5 Vérificateur | Validation pair-à-pair, détection de CV gonflés | `src/agents/verificateur.py` |
| A6 Dédupliqueur | Fusion des doublons par similarité de noms et URLs | `src/agents/deduplicateur.py` |
| A7 Recruteur | Rédaction de messages personnalisés pour les candidats retenus | `src/agents/recruteur.py` |

L'architecture du graphe (`src/graph.py`) implémente plusieurs patterns SMA : blackboard (état partagé via `GraphState`), superviseur (A1), fan-out/fan-in via `Send()` pour les évaluateurs parallèles, validation pair-à-pair (A4 produit → A5 contrôle), routage conditionnel sur le score, et human-in-the-loop (`interrupt_before` sur A7).

### 2. Passage au modèle cloud

Les modèles locaux (type `qwen3.5:4b`) étaient trop lents pour un pipeline à 7 agents avec potentiellement 15+ appels LLM. Le projet utilise maintenant `kimi-k2.5:cloud` via Ollama, ce qui permet des temps de réponse acceptables sur l'ensemble du pipeline.

### 3. Premier test end-to-end — échec

**Fiche de poste testée** : Développeur Python Senior, Machine Learning & Data Engineering, CDI Paris.

**Résultat** : échec total. 0 candidat contacté sur 15 profils collectés. Le diagnostic est clair : A3 ramenait essentiellement des offres d'emploi et des pages d'agrégateurs (Indeed, Glassdoor, Welcome to the Jungle...). Le pipeline en aval fonctionnait correctement mais recevait du bruit en entrée — A4 évaluait du bruit (15 appels LLM inutiles), les scores étaient faibles à juste titre, A5 invalidait tout, aucun candidat n'arrivait jusqu'à A7.

### 4. Refactoring majeur d'A3 — pipeline de filtrage en 6 étapes

Le fichier `src/agents/chercheur.py` a été entièrement restructuré. Ancien fonctionnement : A3 utilisait les snippets DuckDuckGo (2-3 lignes) comme "profil brut" et les transmettait tous à A4 sans filtrage. Nouveau pipeline :

1. **Génération de requêtes par le LLM** — requêtes optimisées pour trouver des personnes (CV, portfolios, profils publics), pas des offres
2. **Collecte structurée** via `_ddg_search_raw()` qui retourne des dicts typés `{title, url, body, source}` au lieu de texte brut
3. **Déduplication par URL** — élimine les doublons entre requêtes
4. **Pré-filtre algorithmique (sans LLM)** :
   - Par domaine d'URL (`_is_noise_url`) : 19 domaines d'agrégateurs bloqués (Indeed, Glassdoor, Jooble, Monster, Cadremploi, Welcome to the Jungle, Apec, France Travail, etc.)
   - Par mots-clés (`_is_noise`) : 24 mots-clés de détection d'offres dans title+body ("nous recherchons", "postuler", "CDI à pourvoir", "rejoignez-nous", etc.)
5. **Scraping des pages survivantes** via `extraire_page_web_raw()` (BeautifulSoup, max 3000 caractères) — le `profil_brut` devient le contenu réel de la page au lieu du snippet DDG
6. **Post-filtre** — re-test `_is_noise()` sur le contenu scrapé complet, qui révèle parfois des offres non détectables depuis le snippet

Côté outils de recherche (`src/tools/search.py`), des exclusions DDG ont été ajoutées directement dans les requêtes (`-"offre d'emploi" -"postuler" -"nous recrutons"`) pour filtrer le bruit à la source. Une liste de domaines cibles pour CV/portfolios (`CV_SITE_TARGETS`) a aussi été ajoutée pour référence.

### 5. Deuxième test end-to-end — succès

Même fiche de poste. Résultats :

- **1 candidat contacté** : Sri Ram, score 80/100 — A7 a rédigé un message personnalisé
- **2 candidats validés** au total
- **3 candidats marqués "douteux"** par A5
- A5 a correctement détecté un **CV gonflé** : DeShawn Smith, initialement scoré 81/100 par A4, rétrogradé à 55/100 par A5 pour incohérences

### 6. Documentation et organisation

- Rédaction complète du **README** (18+ sections) : architecture, patterns SMA, structure du projet, GraphState, flux de données, installation, utilisation, configuration, gitflow, fonctionnement détaillé de chaque agent, outils, filtrage, routage, human-in-the-loop, logs, exemple d'exécution, prompts système, limites
- Mise en place du **gitflow** pour le travail à 3 : branches `feat/sourcing`, `feat/scoring`, etc. avec PR obligatoires vers `main`
- Création du **backlog** avec 3 chantiers prioritaires identifiés

---

## Résultats concrets

### Avant / après refactoring d'A3

| Métrique | Avant (test 1) | Après (test 2) |
|----------|-----------------|-----------------|
| Profils collectés | 15 | ~10 |
| Bruit (offres / agrégateurs) | ~67 % (10+ sur 15) | ~10 % |
| Candidats évalués par A4 | 15 (dont 10+ inutiles) | ~5 (quasi tous pertinents) |
| Candidats validés par A5 | 0 | 2 |
| Candidats contactés par A7 | 0 | 1 |
| Détection CV gonflé | non testable (aucun candidat arrivé) | oui (DeShawn Smith, 81 → 55) |

---

## Difficultés rencontrées

- **Incompatibilité `bind_tools` avec le modèle cloud** : `kimi-k2.5:cloud` ne supporte pas `bind_tools` de LangChain. Contourné en appelant les outils directement depuis le code Python au lieu de laisser le LLM décider via le mécanisme de tool calling. Le fichier `test.py` conserve le prototype initial avec `bind_tools` pour référence.

- **Rate limiting sur les évaluateurs parallèles** : le fan-out de N instances d'A4 via `Send()` provoque des requêtes simultanées au modèle cloud. Résolu par retry avec backoff exponentiel.

- **DuckDuckGo ramène surtout des offres d'emploi** : une requête "développeur Python Paris" retourne en majorité des annonces (Indeed, Glassdoor, etc.) et non des profils de candidats. Le filtrage algorithmique implémenté dans A3 compense, mais c'est un pansement — le vrai fix serait d'utiliser des APIs directes.

- **Sources post-filtrage quasi exclusivement LinkedIn** : après le filtrage, les résultats utiles proviennent presque tous de LinkedIn. Les autres sources web sont trop bruitées. C'est une limite connue du sourcing via DDG.

---

## Prochaines étapes

1. **Chantier 2 — Scoring moins strict (A4)** : distinguer compétences requises vs souhaitées dans le prompt, ajouter un barème explicite, introduire la notion de potentiel. Actuellement un senior Python+ML sans Kubernetes tombe à 15/100, ce qui est trop pénalisant.

2. **Chantier 3 — Routage relatif** : si aucun candidat n'atteint le seuil de 75, proposer quand même le top 3 au recruteur humain. Distinguer "aucun viable" (tous < 40) de "intéressants mais imparfaits" (40-75). Rendre le seuil configurable en CLI (`--seuil`).

3. **Diversification des sources** : remplacer progressivement DuckDuckGo par des APIs directes (Indeed, LinkedIn, GitHub) pour du sourcing structuré au lieu de scraper des résultats de moteur de recherche.

4. **Division d'A3 en sous-agents** (si le temps le permet) : A3a Stratège (génère les requêtes), A3b Collecteur (exécute + scrape), A3c Filtre (classe candidat réel vs bruit). A3 fait actuellement trop de choses dans un seul nœud.
