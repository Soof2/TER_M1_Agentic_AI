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

### 1a. Scraper les pages trouvees

`extraire_page_web` existe dans `src/tools/scraping.py` mais n'est jamais appele. A3 utilise les snippets DuckDuckGo (2-3 lignes) comme "profil brut" — c'est insuffisant pour evaluer un candidat.

- [ ] Apres chaque recherche DuckDuckGo, appeler `extraire_page_web` sur chaque URL
- [ ] Le profil brut devient le contenu scrape (jusqu'a 3000 chars) au lieu du snippet

### 1b. Filtrer le bruit avant evaluation

Sur 15 resultats, 10+ sont des offres d'emploi ou des pages d'agregateurs. On les envoie quand meme a A4 (15 appels LLM inutiles).

- [ ] Pre-filtre algorithmique (sans LLM) : detecter les offres d'emploi par mots-cles dans le profil brut ("nous recherchons", "postuler", "rejoignez-nous", "CDI a pourvoir", "candidature")
- [ ] Exclure avant d'envoyer a A4 — economie directe de tokens et de temps

### 1c. Ameliorer les requetes

- [ ] Ajouter des exclusions dans les requetes DuckDuckGo (`-"offre d'emploi"`, `-"postuler"`, `-"nous recrutons"`)
- [ ] Pre-filtre geographique (`Paris OR Ile-de-France`)

### 1d. A terme — APIs directes

DuckDuckGo est un pis-aller. Le vrai sourcing passe par des APIs/MCPs :

- [ ] **MCP Indeed** : a trouve 73 offres en un appel cote demandeur d'emploi — la meme infra peut chercher des CVs/profils cote recruteur
- [ ] **LinkedIn API** : filtres avances (experience, localisation, competences, secteur)
- [ ] **GitHub API** : recherche d'utilisateurs par langage, localisation, contributions (distinguer senior vs etudiant)
- [ ] S'inspirer de **career-ops** (skill Claude Code) qui fait du scraping d'offres — meme patterns, sens inverse

### 1e. Diviser A3

A3 fait trop de choses (genere requetes + execute recherches + parse resultats). Avec le scraping + filtrage ca devient ingerable.

- [ ] **A3a Stratege** : recoit le profil de competences, genere les requetes optimisees par source
- [ ] **A3b Collecteur** : execute les recherches, scrape les pages, produit les profils bruts enrichis
- [ ] **A3c Filtre** : classe chaque resultat (candidat reel vs bruit) avant deduplication

---

## Chantier 2 — Scoring (A4) — trop strict

Un senior Python+ML sans Kubernetes tombe a 15/100. Le prompt demande "rigueur" et "adequation parfaite" pour 100 — le LLM penalise chaque competence manquante comme si c'etait eliminatoire.

- [ ] Distinguer competences **requises** vs **souhaitees** dans le prompt (avec poids differents)
- [ ] Bareme explicite dans le prompt : 80-100 excellent match, 60-80 bon match partiel, 40-60 interessant avec lacunes, < 40 hors sujet
- [ ] Notion de **potentiel** : un candidat qui coche 70% des hard skills avec une bonne experience ne devrait pas scorer en dessous de 60

---

## Chantier 3 — Routage — trop binaire

Seuil absolu de 75. Si le meilleur du lot est a 68, personne n'est contacte.

- [ ] **Seuil relatif** : si aucun >= 75, proposer les top 3 candidats valides au recruteur humain quand meme
- [ ] Distinguer "aucun viable" (tous < 40) de "interessants mais imparfaits" (40-75)
- [ ] Seuil configurable en CLI (`--seuil 60`)
