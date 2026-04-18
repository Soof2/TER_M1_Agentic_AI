# Backlog — SMA de Recrutement Automatise

## Historique du probleme initial

Le pipeline fonctionnait structurellement mais echouait operationnellement : 0 candidat contacte sur 15 profils collectes. Cause identifiee : les donnees entrant dans le pipeline etaient mauvaises.

```
A3 ramenait du bruit (offres d'emploi, repos etudiants, pages d'agregateurs)
  → A4 evaluait du bruit (×15 appels LLM) → scores faibles justifies
    → A5 invalidait tout → aucun contact → 7 minutes et des tokens gaspilles
```

---

## Chantier 1 — Sourcing (A3)

### 1a. Scraper les pages trouvees ✅ FAIT (12/04/2026)
- [x] A3 scrape les pages via BeautifulSoup (3000 chars au lieu des snippets DDG)
- [x] Fallback sur snippet DDG si scraping echoue

### 1b. Filtrer le bruit avant evaluation ✅ FAIT (12/04/2026)
- [x] Pre-filtre par domaine URL (19 domaines d'agregateurs bloques)
- [x] Pre-filtre par mots-cles (24 mots-cles offres d'emploi)
- [x] Post-filtre apres scraping (contenu complet revele plus de bruit)

### 1c. Ameliorer les requetes ✅ FAIT (12/04/2026)
- [x] Exclusions DDG (-"offre d'emploi", -"postuler", etc.)
- [x] Prompt A3 cible des personnes (CV, portfolios, profils publics)
- [x] Categorie queries_cv_sites (malt.fr, doyoubuzz.com)

### 1d. APIs directes ✅ FAIT (18/04/2026)
- [x] **GitHub API** (gratuite) : recherche utilisateurs par competences/localisation
      Sans token : 60 req/h | Avec token gratuit : 5000 req/h
      src/tools/github_api.py
- [x] **Stack Overflow API** (gratuite) : recherche par tags techniques
      Sans cle : 300 req/jour | Avec cle gratuite : 10 000 req/jour
      src/tools/stackoverflow_api.py
- [x] LinkedIn : DDG site:linkedin.com/in (pas d'API publique disponible)

### 1e. Division A3 en sous-agents ✅ FAIT (18/04/2026)
- [x] **A3a Stratege** (chercheur_stratege.py) : LLM genere les requetes par source
- [x] **A3b Collecteur** (chercheur_collecteur.py) : DDG + GitHub API + SO API
- [x] **A3c Filtre** (chercheur_filtre.py) : filtre bruit algorithmique + scraping
- [x] Nouveau champ d'etat : requetes_recherche (A3a→A3b) et resultats_bruts (A3b→A3c)

---

## Chantier 2 — Scoring (A4) ✅ FAIT (18/04/2026)

- [x] Bareme explicite dans le prompt (85/70/50/30/0)
- [x] Distinction requises vs souhaitees (poids double hard skills)
- [x] Notion de potentiel (70% skills + bonne experience = score >= 60)
- [x] Retry avec backoff exponentiel si rate limit (5 tentatives)

---

## Chantier 3 — Routage conditionnel ✅ FAIT (18/04/2026)

- [x] Routage absolu : score >= 75 → A7 contacte
- [x] Routage relatif : si aucun >= 75, propose top-3 des >= 40 au recruteur quand meme
- [x] Seuils configurables via variables d'environnement (SCORE_SEUIL_CONTACT, etc.)

---

## Chantier 4 — Observabilite ✅ FAIT (18/04/2026)

- [x] src/observabilite.py : PipelineMetrics (timing par noeud, metriques metier)
- [x] Export JSON automatique dans logs/metriques_YYYYMMDD_HHMMSS.json
- [x] Resume inclus dans le rapport final
- [x] Metriques : taux de bruit A3c, n_candidats a chaque etape, routage

---

## Chantier 5 — Docker / Deploiement ✅ FAIT (18/04/2026)

- [x] Dockerfile optimise (couches separees, variables d'env)
- [x] docker-compose.yml avec volume logs/ pour export metriques
- [x] .env.example avec documentation des variables
- [x] .gitignore (venv, .env, logs, __pycache__)
- [x] config.py entierement pilote par env vars (OLLAMA_MODEL, GITHUB_TOKEN, etc.)

---

## Recap global

| Chantier | Statut | Impact mesure |
|----------|--------|---------------|
| 1a. Scraping pages | ✅ Fait 12/04 | Profils enrichis (3000 chars) |
| 1b. Filtre bruit | ✅ Fait 12/04 | 67% → 10% de bruit |
| 1c. Requetes ameliorees | ✅ Fait 12/04 | Prompt cible personnes |
| 1d. APIs directes | ✅ Fait 18/04 | GitHub API + Stack Overflow API |
| 1e. Division A3 | ✅ Fait 18/04 | 3 agents specialises A3a/b/c |
| 2. Scoring moins strict | ✅ Fait 18/04 | Bareme 85/70/50/30, poids requis |
| 3. Routage relatif | ✅ Fait 18/04 | Top-3 si aucun >= 75 |
| 4. Observabilite | ✅ Fait 18/04 | Metriques JSON par run |
| 5. Docker | ✅ Fait 18/04 | Env vars, volume logs |

**Resultat e2e** : test 12/04 → passe de 0 contact a 1 contact (Sri Ram 80/100).
Pipeline complet, toutes les ameliorations implementees.
