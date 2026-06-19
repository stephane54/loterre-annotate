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

CLI en sous-commandes positionnelles (`loterre_cli.py <sous-commande> ...`, pas de flag `--mode`) :

| Sous-commande | Description |
|----------|-------------|
| `annotate` | Comportement v1.0 — lookup dans un vocabulaire Loterre (inchangé) |
| `extract` | Extraction de candidats termes depuis le texte (sans vocabulaire) |
| `extract_annotate` | Extraction puis croisement avec Loterre (présent/absent + URI) |

---

## Contraintes non négociables

- **Langues** : français (FR) et anglais (EN) obligatoirement
- **Matériel** : CPU uniquement — pas de GPU disponible, pas d'accès cloud
- **Rapidité** : le mode extract ne doit pas être significativement plus lent que le mode annotate
- **Pas de modèle de langue massif** : pas de fine-tuning, pas de mBERT lourd en inférence

---

## Stack technique décidée

### Pipeline NLP — deux modèles différents selon l'usage

| Usage | Modèle EN | Modèle FR | Où | Statut |
|-------|-----------|-----------|-----|--------|
| **Reconnaissance (runtime annotateur)** | `en_core_web_sm` (3.7.1) | `fr_core_news_sm` (3.7.0) | `resources/spacy_models.yaml`, lu par `load_model()` dans `loterre_engine_v9_cli.py` | **Actif** — restauré au défaut v1.0.0 après régression scispaCy (voir journal) |
| **Génération des dictionnaires actuels (`dictionary/*.jsonl` sur disque)** | `en_core_web_trf` | `fr_dep_news_trf` | Ancien pipeline externe `~/app/terms_tools` (déprécié) | **Historique** — ces dictionnaires n'ont pas été régénérés, ils datent du 8 juin 2026 |
| **Génération via le nouveau script natif** | *celui de `load_model('en')`, donc `en_core_web_sm` actuellement* | *celui de `load_model('fr')`* | `scripts/build_dictionaries/build_dictionaries.py` | Disponible mais **pas encore exécuté** en production |

**Point important** : `scripts/build_dictionaries/build_dictionaries.py` ne déclare pas de modèle de génération séparé — il appelle `load_model()`, donc **le même modèle que le runtime**. Si on l'exécute aujourd'hui, génération et reconnaissance utiliseraient toutes les deux `en_core_web_sm`/`fr_core_news_sm`, ce qui **élimine** l'écart structurel actuel (~18 % de désaccords lemme/POS sur P66_en, mesuré et documenté) entre les dictionnaires `_trf` existants et le runtime `_sm`. Ce n'est pas encore fait — les dictionnaires sur disque restent ceux générés par l'ancien pipeline `_trf`.

scispaCy (`en_core_sci_sm`) a été testé comme modèle de reconnaissance EN par défaut et **abandonné** : -8 points de F1 sur P66 (vocabulaire multidisciplinaire, pas biomédical) — voir le journal des versions pour les chiffres.

Usage du script de génération :
```bash
python3 scripts/build_dictionaries/build_dictionaries.py --voc P66 --lang en
python3 scripts/build_dictionaries/build_dictionaries.py --all --lang en fr
```
Détection automatique des deux formats CSV vocab depuis les en-têtes :
- format **loterre** : colonnes `prefLabel_fr`/`prefLabel_en` (underscore) → délimiteur d'occurrence `§§`
- format **MX** : colonnes `prefLabelFre`/`prefLabelEng` (camelCase) → délimiteur d'occurrence `|`

Batché via `nlp.pipe()` — un seul chargement de modèle par langue. Validé caractère pour caractère contre un dictionnaire de production existant (`long-term memory` → pattern identique avec `OP:"?"` sur le tiret).

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
| 0 | Conception + génération native dictionnaires (transformers) — spaCy reste 3.7.x, scispaCy testé/rejeté | Quasi terminée |
| 0.5 | Préparation architecturale (CandidateTerm, chargement spaCy centralisé) | **Terminée** |
| 1 | Module extraction noun chunks + filtres POS | **Terminée** |
| 2 | C-value scoring (termes emboîtés, seuil configurable) | **Cœur terminé** — extension contexte NC-value différée |
| 3 | Intégration 3 sous-commandes CLI (`annotate\|extract\|extract_annotate`) | **Terminée** |
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
| `src/loterre_cli.py` | CLI principale — résolution registre + dispatch, sous-commandes `annotate\|extract\|extract_annotate` |
| `src/loterre_fast_path.py` | Fast path regex (mode hybride) |
| `src/loterre_benchmark.py` | Benchmark local vs API ISTEX |
| `src/loterre_extraction_base.py` | v2.0 — `CandidateTerm`, `get_nlp()` (chargement spaCy cache, parser optionnel) |
| `src/loterre_extract_cli.py` | v2.0 — extraction noun chunks (Phase 1) + scoring C-value (Phase 2) + `cross_reference_candidates()` (Phase 3) |
| `src/loterre_cvalue.py` | v2.0 — algorithme C-value (Frantzi 1998), termes emboîtés, cas limite mono-token |
| `tests/baselines/annotation_baseline_v1.0.0.json` | Baseline non-régression mode annotate (F1 par vocab/langue) |
| `scripts/build_dictionaries/build_dictionaries.py` | Génération native des dictionnaires JSONL depuis CSV vocab Loterre |
| `configs/registry.yaml` | Registre des 30+ vocabulaires Loterre |
| `resources/spacy_models.yaml` | Ordre de préférence des modèles spaCy par langue |
| `VERSION` | Version courante du package |
| `production/release.sh` | Script de release complet (4 étapes) |
