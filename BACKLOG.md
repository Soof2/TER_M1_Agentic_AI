# Backlog — SMA de Recrutement Automatise

## Probleme

Le pipeline fonctionne structurellement mais echoue operationnellement. Le rapport final du test reel conclut "echec total, reboot necessaire" : 0 candidat contacte sur 15 profils collectes. La cause est identifiee : les donnees qui entrent dans le pipeline sont mauvaises.

```
A3 ramene du bruit (offres d'emploi, repos etudiants, pages d'agregateurs)
  → A4 evalue du bruit (×15 appels LLM) → scores faibles justifies
    → A5 invalide tout → aucun contact → 7 minutes et des tokens gaspilles
```

---

## Chantier 1 — Sourcing (A3) — priorite absolue

C'est le goulot. Tout le reste du pipeline est pret, il attend de bonnes donnees.

**Statut global** : 1a/1b/1c faits cette semaine (12 avril 2026). Test e2e : 0 → 1 candidat contacte, bruit 67% → 10%. 1d et 1e restent a faire.

### 1a. Scraper les pages trouvees ✅ FAIT (12/04/2026)

`extraire_page_web` existe dans `src/tools/scraping.py` mais n'est jamais appele. A3 utilise les snippets DuckDuckGo (2-3 lignes) comme "profil brut" — c'est insuffisant pour evaluer un candidat.

- [x] Apres chaque recherche DuckDuckGo, appeler `extraire_page_web` sur chaque URL
- [x] Le profil brut devient le contenu scrape (jusqu'a 3000 chars) au lieu du snippet
- [x] Extraction d'une fonction `extraire_page_web_raw()` non-tool pour appel direct depuis A3 (evite `bind_tools` incompatible avec le cloud model)

### 1b. Filtrer le bruit avant evaluation ✅ FAIT (12/04/2026)

Sur 15 resultats, 10+ sont des offres d'emploi ou des pages d'agregateurs. On les envoie quand meme a A4 (15 appels LLM inutiles).

- [x] Pre-filtre algorithmique (sans LLM) : detecter les offres d'emploi par mots-cles dans le profil brut ("nous recherchons", "postuler", "rejoignez-nous", "CDI a pourvoir", "candidature")
- [x] Exclure avant d'envoyer a A4 — economie directe de tokens et de temps
- [x] **Bonus** : ajout d'un filtre par **domaine d'URL** (`_is_noise_url`) avec 19 domaines d'agregateurs bloques (Indeed, Glassdoor, Jooble, Monster, Cadremploi, etc.). Plus fiable que le filtre textuel car les agregateurs ont des titres anodins ("Python - Paris : 2024 emplois").
- [x] **Bonus** : post-filtre apres scraping — le contenu complet d'une page revele parfois des offres non detectables depuis le snippet DDG.

### 1c. Ameliorer les requetes ✅ PARTIELLEMENT FAIT (12/04/2026)

- [x] Ajouter des exclusions dans les requetes DuckDuckGo (`-"offre d'emploi"`, `-"postuler"`, `-"nous recrutons"`, `-"rejoignez-nous"`, `-"CDI a pourvoir"`, `-"candidature"`) — constante `DDG_EXCLUSIONS` dans `src/tools/search.py`
- [x] Prompt A3 ameliore pour cibler des **personnes** (CV, portfolios, profils publics) et pas des offres ou des repos
- [x] Ajout d'une 4eme categorie de requetes `queries_cv_sites` ciblant doyoubuzz, malt, viadeo, about.me, behance, dribbble, stackoverflow/users
- [ ] Pre-filtre geographique (`Paris OR Ile-de-France`) — non fait

### 1d. A terme — APIs directes ❌ NON FAIT

DuckDuckGo est un pis-aller. Le vrai sourcing passe par des APIs/MCPs :

- [ ] **MCP Indeed** : a trouve 73 offres en un appel cote demandeur d'emploi — la meme infra peut chercher des CVs/profils cote recruteur
- [ ] **LinkedIn API** : filtres avances (experience, localisation, competences, secteur)
- [ ] **GitHub API** : recherche d'utilisateurs par langage, localisation, contributions (distinguer senior vs etudiant)
- [ ] S'inspirer de **career-ops** (skill Claude Code) qui fait du scraping d'offres — meme patterns, sens inverse

**Motivation renforcee** : apres le refactor, les resultats post-filtrage sont quasi exclusivement LinkedIn. Les autres sources (web general, GitHub via DDG) sont soit bloquees par le filtre bruit soit inutilisables (repos au lieu de personnes). Les APIs directes sont la vraie solution pour diversifier.

### 1e. Diviser A3 ❌ NON FAIT

A3 fait trop de choses (genere requetes + execute recherches + parse resultats). Avec le scraping + filtrage ca devient ingerable.

- [ ] **A3a Stratege** : recoit le profil de competences, genere les requetes optimisees par source
- [ ] **A3b Collecteur** : execute les recherches, scrape les pages, produit les profils bruts enrichis
- [ ] **A3c Filtre** : classe chaque resultat (candidat reel vs bruit) avant deduplication

**Note** : avec l'ajout des 6 etapes de pipeline dans `chercheur.py` (collecte → dedup → pre-filtre URL → pre-filtre texte → scraping → post-filtre), le fichier atteint ~270 lignes. La division devient pertinente.

---

## Chantier 2 — Scoring (A4) — trop strict ❌ NON FAIT

Un senior Python+ML sans Kubernetes tombe a 15/100. Le prompt demande "rigueur" et "adequation parfaite" pour 100 — le LLM penalise chaque competence manquante comme si c'etait eliminatoire.

- [ ] Distinguer competences **requises** vs **souhaitees** dans le prompt (avec poids differents)
- [ ] Bareme explicite dans le prompt : 80-100 excellent match, 60-80 bon match partiel, 40-60 interessant avec lacunes, < 40 hors sujet
- [ ] Notion de **potentiel** : un candidat qui coche 70% des hard skills avec une bonne experience ne devrait pas scorer en dessous de 60

---

## Chantier 3 — Routage — trop binaire ❌ NON FAIT

Seuil absolu de 75. Si le meilleur du lot est a 68, personne n'est contacte.

- [ ] **Seuil relatif** : si aucun >= 75, proposer les top 3 candidats valides au recruteur humain quand meme
- [ ] Distinguer "aucun viable" (tous < 40) de "interessants mais imparfaits" (40-75)
- [ ] Seuil configurable en CLI (`--seuil 60`)

---

## Recap semaine du 7-12 avril 2026

| Chantier | Statut | Impact |
|----------|--------|--------|
| 1a. Scraping des pages | ✅ Fait | Profils enrichis (3000 chars au lieu de 2-3 lignes) |
| 1b. Filtre bruit mots-cles + domaines | ✅ Fait (+ bonus URL filter) | 67% → 10% de bruit |
| 1c. Exclusions DDG + prompt + queries_cv_sites | ✅ Partiellement fait | Prompt cible des personnes, pas des offres |
| 1d. APIs directes | ❌ Non fait | Principale limitation restante (resultats LinkedIn-centric) |
| 1e. Division A3 en sous-agents | ❌ Non fait | A3 commence a etre gros (~270 lignes) |
| 2. Scoring moins strict | ❌ Non fait | Prochaine priorite |
| 3. Routage relatif | ❌ Non fait | Prochaine priorite |

**Resultat concret du refactor** : test e2e passe de 0 contact a 1 contact (Sri Ram 80/100), avec detection d'un CV gonfle (DeShawn Smith 81 → 55 par A5).
