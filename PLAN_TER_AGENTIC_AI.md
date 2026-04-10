# Projet TER : Système Multi-Agents (SMA) basé LLM pour la Comparaison de Prix Dynamique

Ce document sert de Master Plan pour la conception, l'ingénierie et la justification scientifique de notre architecture Agentic AI avec LangGraph et des LLMs locaux. Il est structuré pour répondre aux exigences académiques d'un Master IA & Data.

---

## 1. Objectifs Académiques (Ce que les examinateurs évaluent)

*   **La pensée système (Systems Thinking) :** Interaction des composants et gestion d'état.
*   **La maîtrise de l'incertitude :** Fiabilité des extractions via des contraintes formelles.
*   **L'optimisation sous contraintes (LLM Local) :** Gestion du contexte et de l'inférence.
*   **L'évaluation scientifique :** Métriques de précision (Precision/Recall) et qualité du raisonnement.

---

## 2. État de l'Art & Apports Scientifiques (MAS & Agentic AI)

1.  **ReAct (Yao et al., 2022) :** Raisonnement avant l'action.
2.  **Reflexion (Shinn et al., 2023) :** Auto-correction verbale.
3.  **Plan-and-Solve :** Séparation planification / exécution.
4.  **Multi-Agent Collaboration :** Division des tâches par personas spécialisés.

---

## 3. Crash Course : LangGraph pour l'Ingénierie Agentique

*   **State Machine :** Graphes cycliques pour l'autonomie.
*   **State & Reducers :** Mémoire partagée et mise à jour atomique.
*   **Conditional Edges :** Routage logique basé sur l'état.
*   **Checkpointers :** Persistance et Human-in-the-loop.

---

## 4. Architecture du Système : La Boucle Agentique (ReAct)

Cycle : **Pensée -> Action -> Observation -> Synthèse**.

### Composants (Nœuds) :
1.  **Planner :** Stratégie initiale.
2.  **Search Tool :** Recherche web.
3.  **Scraper :** Extraction du texte brut (Markdown).
4.  **Information Extractor :** Structuration JSON.
5.  **Validator :** Vérification de la cohérence.
6.  **Synthesizer :** Rapport final.

---

## 5. Design Patterns Agentiques Implémentés

*   **Map-Reduce :** Parallélisation du scraping.
*   **Fallback Strategies :** Sécurité via méthodes classiques (Regex).
*   **Stateful Tooling :** Outils conscients de l'historique.

---

## 6. Features du Logiciel

*   [ ] Mode Chat Interactif.
*   [ ] Exécution Locale (Ollama).
*   [ ] Human-in-the-loop (Validation URLs).
*   [ ] Observabilité du graphe en temps réel.

---

## 7. Roadmap & Plan de Développement

| Phase | Focus | Livrable |
| :--- | :--- | :--- |
| **1. Fondation** | Setup env & State definition | Squelette LangGraph fonctionnel |
| **2. Perception** | Tooling (Search & Scrape) | Agent capable de lire le web |
| **3. Cognition** | Extraction JSON & Reflexion | Données structurées fiables |
| **4. Interface** | UI & Observabilité | Logiciel complet & Démo |

---

## 8. Méthodologie : "Agent-to-Agent Engineering"

Collaboration entre l'Assistant IA (Généraliste) et l'étudiant pour construire l'Agent Projet (Spécialiste).

---

## 9. Guide d'Implémentation Détaillé (Step-by-Step)

### Étape 0 : Setup de l'Environnement
*   **Action :** Installer Ollama, Python 3.10+, et créer un `venv`.
*   **Dépendances :** `langgraph`, `langchain-ollama`, `beautifulsoup4`, `duckduckgo-search`.
*   **Principe :** Isolation des dépendances pour la reproductibilité scientifique.

### Étape 1 : Définition de l'Ontologie (Le "State")
*   **Action :** Créer un `TypedDict` contenant `messages`, `products_found` (liste de dicts), et `current_step`.
*   **Concept :** **Shared Memory Pattern**. L'état est la "vérité unique" du système.
*   **Ingénierie :** Utiliser des `Annotated` avec des fonctions de réduction (`add_messages`).

### Étape 2 : Le Cerveau (Nœud Agent)
*   **Action :** Connecter Ollama au graphe. Créer le premier nœud qui reçoit la requête et décide d'utiliser un outil.
*   **Pattern :** **ReAct Controller**. Le LLM ne répond pas, il "appelle des fonctions".
*   **Design :** Utiliser `.bind_tools()` pour exposer les capacités au modèle.

### Étape 3 : Les Instruments (Tools & Search)
*   **Action :** Implémenter l'outil de recherche DuckDuckGo et le nœud de scraping (BeautifulSoup).
*   **Pattern :** **Strategy Pattern**. Chaque site peut avoir une stratégie d'extraction différente.
*   **Concept :** **Grounding**. Ancrer les réponses du LLM dans des données réelles et actuelles.

### Étape 4 : Le Contrôle Qualité (Reflexion & Validation)
*   **Action :** Créer un nœud `Validator` qui vérifie si le JSON extrait par l'étape précédente est valide et complet.
*   **Concept :** **Computational Reflexion**. Si le prix est aberrant ou le format incorrect, le graphe boucle vers l'extracteur avec un message d'erreur.
*   **Science :** Réduction du taux d'hallucination par vérification croisée.

### Étape 5 : Optimisation de Masse (Map-Reduce)
*   **Action :** Si l'agent trouve 5 URLs, lancer 5 instances d'extraction en parallèle.
*   **Pattern :** **Fan-out / Fan-in**.
*   **Performance :** Crucial pour les LLMs locaux qui peuvent être lents ; l'extraction parallèle gagne un temps précieux.

### Étape 6 : UI & Human-in-the-loop
*   **Action :** Ajouter un `interrupt_before` sur le nœud de scraping. Utiliser Streamlit pour l'interface.
*   **Concept :** **Human-Centered AI**. L'humain garde le contrôle sur les actions coûteuses ou sensibles.
*   **Observabilité :** Afficher les logs du "Reasoning" pour que l'utilisateur comprenne *pourquoi* l'agent a choisi tel produit.

### Étape 7 : Évaluation & Benchmark
*   **Action :** Créer un petit dataset de test (10 produits dont on connaît le prix). Faire tourner l'agent et calculer le score de précision.
*   **Science :** Validation empirique des résultats pour le rapport final.
