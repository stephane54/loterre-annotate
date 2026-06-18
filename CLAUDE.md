# CLAUDE.md — loterre-annotate

Contexte et décisions architecturales pour les sessions de développement.

---

## Ce que fait ce projet

Moteur d'annotation terminologique sur les vocabulaires Loterre (INIST/CNRS).  
Étant donné un texte, il détecte les termes présents dans un vocabulaire Loterre et retourne leurs URIs.

**Version actuelle : v1.0.0** — annotateur par dictionnaire uniquement.  
**Version cible : v2.0** — ajout d'un module d'extraction terminologique.

---

## Trois modes cibles (v2.0)

| Mode CLI | Description |
|----------|-------------|
| `--mode annotate` | Comportement v1.0 — lookup dans un vocabulaire Loterre (inchangé) |
| `--mode extract` | Extraction de candidats termes depuis le texte (sans vocabulaire) |
| `--mode extract+annotate` | Extraction puis croisement avec Loterre (présent/absent + URI) |

---

## Contraintes non négociables

- **Langues** : français (FR) et anglais (EN) obligatoirement
- **Matériel** : CPU uniquement — pas de GPU disponible, pas d'accès cloud
- **Rapidité** : le mode extract ne doit pas être significativement plus lent que le mode annotate
- **Pas de modèle de langue massif** : pas de fine-tuning, pas de mBERT lourd en inférence

---

## Stack technique décidée

### Pipeline NLP
- **spaCy 3.8**
- Runtime annotateur : `en_core_web_sm` / `fr_core_news_sm` — ordre de préférence dans `resources/spacy_models.yaml`
- **scispaCy / `en_core_sci_sm` abandonné** : testé et non retenu (voir ci-dessous)

### Génération des dictionnaires — pipeline natif, mêmes modèles que l'ancien script

`scripts/build_dictionaries/build_dictionaries.py` génère les dictionnaires JSONL directement depuis les CSV vocab Loterre (`~/data/voc_loterre/<VOC>/<VOC>.csv`). Il **remplace l'orchestration** de l'ancien `~/app/terms_tools/script/extract_dico_lot.sh` (dépôt externe séparé, `csv_convert.py` + `terms_toolsCLI.py`) mais réutilise **les mêmes modèles spaCy transformers** que lui : `en_core_web_trf` (EN) / `fr_dep_news_trf` (FR), déclarés dans `GENERATION_MODELS` en tête du script — **volontairement différents** du runtime annotateur ci-dessus.

- **Pourquoi garder des modèles différents générateur/runtime** : une tentative antérieure faisait coïncider les deux (modèle léger des deux côtés). Testé sur 7 vocabs (P66, 9SD, 8HQ, B9M, 27X, BVM, QX8) × 2 langues contre les gold standards : régression systématique du F1 (ex. 8HQ_fr 100%→76.5%, BVM_en 86.7%→68.8%), causée par la phrase-cadre artificielle (`dive_term`, "the X is correct.") qui ne reproduit pas fiablement le tag obtenu en contexte réel — un défaut indépendant du choix de modèle, qui touche surtout les labels courts/symboles (ex. "La" pour lanthane matchant tous les "la/le/l'" du texte FR) et les participes/adjectifs ambigus.
- **Environnement requis** : torch + modèles transformers installés (lourd, absent de l'environnement par défaut) — utiliser le venv `~/app/terms_tools/venv` tant que loterre-v9 n'a pas le sien :
  ```bash
  ~/app/terms_tools/venv/bin/python3 scripts/build_dictionaries/build_dictionaries.py --voc P66 --lang en
  ```
- Détection automatique des deux formats CSV vocab depuis les en-têtes :
  - format **loterre** : colonnes `prefLabel_fr`/`prefLabel_en` (underscore) → délimiteur d'occurrence `§§`
  - format **MX** : colonnes `prefLabelFre`/`prefLabelEng` (camelCase) → délimiteur d'occurrence `|`
- Batché via `nlp.pipe()` — un seul chargement de modèle par langue, pas de rechargement par terme (contrairement à l'ancien `terms_toolsCLI.py`)
- **Validation** : sortie comparée champ à champ (pattern+pref) aux dictionnaires de production actuels sur les 7 vocabs ci-dessus — 13/14 combinaisons strictement identiques à 100 %, 1/14 (9SD_en) avec une seule entrée différente sur 13784 (ambiguïté CCONJ/PROPN sur l'acronyme "AND"/Andorre, micro-variation du modèle). Tests de non-régression (precision/recall/F1) identiques à l'ancien dictionnaire sur les 14 combinaisons.

Usage :
```bash
~/app/terms_tools/venv/bin/python3 scripts/build_dictionaries/build_dictionaries.py --voc P66 --lang en
~/app/terms_tools/venv/bin/python3 scripts/build_dictionaries/build_dictionaries.py --all --lang en fr
```

### Extracteur terminologique
- **NC-value** (Frantzi et al. 2000) comme moteur principal sur corpus (> 50 000 tokens / ~6–10 articles)
- **PositionRank** pour textes courts (< 10 000 tokens / document unique)
- Sélection automatique selon volume, ou `--extractor ncvalue|graph|embed`

### Scoring et filtrage (sans GPU)
- **`paraphrase-multilingual-MiniLM-L12-v2`** (118 Mo, CPU, FR+EN) via `sentence-transformers`
- Similarité cosinus entre candidats et centroïde des termes Loterre du vocabulaire cible
- Deux objectifs : filtrage du bruit + identification de candidats d'enrichissement du vocabulaire

---

## Objectifs de qualité et mesure

### Annotation (mode actuel)
- Gold standards existants dans `data/jsonl/` (P66_en, P66_fr, etc.)
- Pipeline benchmark : `loterre_benchmark.py`

### Extraction (mode v2.0)
- Gold standard : **corpus ACTER** — [AylaRT/ACTER](https://github.com/AylaRT/ACTER) (CC BY-NC-SA 4.0)
  - FR + EN, 4 domaines (insuffisance cardiaque, énergie éolienne, équitation, corruption)
  - ~18 900 termes annotés manuellement, format IOB
- Baseline de comparaison : **D-Terminer** (mBERT + RNN, GPU) — F1 référence : 0.32–0.50 sur ACTER
- Métriques : Precision / Recall / F1 (token-level, protocole ACTER)

---

## Plan de développement

Voir `planification/planif_extraction_terminologique.md` pour le détail des phases.  
Voir `planification/analyse_benchmarks_extraction.md` pour les benchmarks de référence.

### Résumé des phases
| Phase | Contenu | Priorité |
|-------|---------|----------|
| 0 | Conception + upgrade spaCy 3.8 + génération native dictionnaires (transformers) | Obligatoire |
| 0.5 | Préparation architecturale ciblée (CandidateTerm, chargement spaCy centralisé) | Obligatoire |
| 1 | Module extraction noun chunks + filtres POS | Obligatoire |
| 2 | NC-value scoring (termes emboîtés, seuil configurable) | Obligatoire |
| 3 | Intégration 3 modes CLI + format JSONL unifié | Obligatoire |
| 4 | Détection de variantes (graphiques, morpho, syntaxiques) | Recommandée |
| 5 | Scoring embeddings Loterre (MiniLM) — filtrage + enrichissement | Recommandée |
| 6 | Benchmark ACTER + comparaison D-Terminer + TermSuite | Recommandée |

**Estimation totale : 90–120 h de travail effectif.**

---

## Gestion des versions

- **Source unique de version** : fichier `VERSION` à la racine (tracké par git)
- Tous les scripts lisent depuis `VERSION` : `setup.py`, `production/setup.py`, `production/build_push_package.sh`
- Pour changer la version lors d'une release : `bash production/release.sh --version X.Y.Z`

---

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `src/loterre_engine_v9_cli.py` | Moteur d'annotation — stratégie 5 passes + Trie |
| `src/loterre_cli.py` | CLI principale — résolution registre + dispatch |
| `src/loterre_fast_path.py` | Fast path regex (mode hybride) |
| `src/loterre_benchmark.py` | Benchmark local vs API ISTEX |
| `scripts/build_dictionaries/build_dictionaries.py` | Génération native des dictionnaires JSONL depuis CSV vocab Loterre |
| `configs/registry.yaml` | Registre des 30+ vocabulaires Loterre |
| `resources/spacy_models.yaml` | Ordre de préférence des modèles spaCy par langue |
| `VERSION` | Version courante du package |
| `production/release.sh` | Script de release complet (4 étapes) |
