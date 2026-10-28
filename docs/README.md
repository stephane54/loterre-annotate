# Loterre-Annotator — Documentation

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Installation](#2-installation)
3. [Structure du projet](#3-structure-du-projet)
4. [Usage CLI](#4-usage-cli)
5. [Extraction terminologique (v2.0)](#5-extraction-terminologique-v20)
6. [Ressources terminologiques](#6-ressources-terminologiques)
7. [Profils de matching](#7-profils-de-matching)
8. [Stratégie de matching](#8-stratégie-de-matching)
9. [Filtrage qualité](#9-filtrage-qualité)
10. [Stratégies d'exécution](#10-stratégies-dexécution)
11. [Auto-profiling](#11-auto-profiling)
12. [Gold standard — corpus d'évaluation](#12-gold-standard--corpus-dévaluation)
13. [Rendu HTML — visualisation et comparaison](#13-rendu-html--visualisation-et-comparaison)
14. [Benchmark : moteur local vs API production](#14-benchmark--moteur-local-vs-api-production)
15. [Performance](#15-performance)
16. [Tests et workflow de développement](#16-tests-et-workflow-de-développement)
17. [Build et déploiement du package](#17-build-et-déploiement-du-package)

### Autres documents

- [Guide de curation](curation_guide.md) : quelle méthode choisir, et comment relire les listes de suggestion
- [Les 3 méthodes d'extraction](methodes.md) : explication de C-value, PositionRank et embed, avec un exemple travaillé pour chacune
- [Under the hood](underthehood.md) : fonctionnement interne de l'extraction, du rapport et de l'annotation (index, caches, matching)
- [Évaluation](evaluation.md) : résultats mesurés, protocoles d'évaluation, comparaison avec TermSuite
- Présentations : [Extraction terminologique v2](Extraction_terminologique_v2.pptx), [version ReLM](Extraction_terminologique_v2_ReLM.pptx), [ReLM Revue #07](ReLM_Revue%2307.pptx), [TermSuite sur ACTER](slide_termsuite_acter.pptx)

---

## 1. Vue d'ensemble

Loterre-Annotator est un moteur d'annotation et d'extraction terminologique. Il comprend trois fonctions (`annotate`/`extract`/`extract_annotate`) :
- **`annotate`** (v1.0) : détecte dans un texte les occurrences de termes définis dans un dictionnaire JSONL, en combinant matching exact, matching par lemme spaCy, et règles POS+lemme.
- **`extract`** (v2.0) : extrait des candidats termes d'un texte **sans** vocabulaire (noun chunks spaCy + scoring C-value, PositionRank, ou similarité aux embeddings d'un vocabulaire cible).
- **`extract_annotate`** (v2.0) : extraction puis croisement **avec** un vocabulaire Loterre — marque chaque candidat `in_vocabulary` (avec `uri`/`pref`) ou suggère son ajout, sur trois niveaux de confiance (`enrichment_suggestion_embed` / `enrichment_suggestion_structural` / `enrichment_suggestion_specificity`, ce dernier désactivé par défaut, `--extractor embed` uniquement — voir §5.3/§5.4 et `docs/curation_guide.md`).

**Capacités (annotation)** :
- Trois profils précision/rappel prédéfinis
- Filtrage qualité contextuel configurable
- Auto-profiling depuis les statistiques du dictionnaire
- Modes d'exécution : complet, rapide (regex), hybride
- Sortie JSON annotée ou rendu HTML interactif avec comparaison gold
- Benchmark intégré contre l'API production ISTEX

**Capacités (extraction, v2.0)** :
- Scoring : C-value (corpus volumineux), PositionRank (corpus court), similarité aux embeddings d'un vocabulaire cible (plus proche voisin)
- Détection de variantes (graphiques/morphologiques/syntaxiques), inspirée de TermSuite (CNRS/TTC)
- Benchmark avec le gold ACTER (extraction uniquement), comparé à D-Terminer et à TermSuite (§5.7)

**Langues** : anglais et français.

---

## 2. Installation

```bash
make install   # ou : pip install -r requirements.txt
make models    # télécharge en_core_web_sm + fr_core_news_sm

# Optionnel — uniquement pour --extractor embed (Phase 5, v2.0) :
make models-embed   # télécharge paraphrase-multilingual-MiniLM-L12-v2 (~118 Mo)
```

`requirements.txt` : `spacy`, `pyyaml`, `click`, `sentence-transformers` (ce dernier uniquement utilisé par `--extractor embed`, chargement paresseux — aucun coût pour `annotate`/`extract --extractor ncvalue|graph`).

> **`--extractor embed` ne nécessite pas d'accès réseau après `make models-embed`** : le modèle est ensuite lu depuis le cache local (`~/.cache/huggingface/hub/`).

---

## 3. Structure du projet

```text
loterre-v9/
├── src/
│   ├── loterre_engine_v9_cli.py   # [Annotation] moteur principal (v1.0)
│   ├── loterre_cli.py             # [Les deux] lanceur, sous-commandes annotate|extract|extract_annotate
│   ├── loterre_fast_path.py       # [Annotation] matching rapide par regex
│   ├── loterre_html_renderer.py   # [Annotation] rendu HTML interactif + comparaison gold
│   ├── loterre_api_eval.py        # [Annotation] évaluation de l'API production ISTEX
│   ├── loterre_benchmark.py       # [Annotation] benchmark loterre_cli (local) vs API terms-tools + Resolvers
│   │
│   │   # ── Extraction terminologique (v2.0) — voir §5 ──
│   ├── loterre_extraction_base.py # [Extraction] CandidateTerm (dataclass), get_nlp() (cache spaCy, parser optionnel)
│   ├── loterre_extract_cli.py     # [Les deux] extraction noun chunks + scoring + cross_reference_candidates() (croisement vocabulaire de extract_annotate)
│   ├── loterre_cvalue.py          # [Extraction] scoring C-value (Frantzi 1998) — corpus volumineux
│   ├── loterre_positionrank.py    # [Extraction] scoring PositionRank (Florescu & Caragea 2017) — corpus court
│   ├── loterre_embed.py           # [Extraction] scoring par embeddings (plus proche voisin du vocabulaire cible)
│   ├── loterre_variants.py        # [Extraction] détection de variantes (graphiques/morpho/syntaxiques, TermSuite)
│   ├── loterre_specificity.py     # [Extraction] Weirdness Ratio vs langue générale — filtre ncvalue + niveau 3 embed
│   ├── loterre_report.py          # [Extraction] rapport d'analyse HTML (--report) : chiffres, graphiques, thèmes
│   └── loterre_csv_export.py      # [Les deux] export CSV additionnel des candidats (--out-csv)
│
├── configs/
│   ├── registry.yaml              # index des dictionnaires disponibles
│   └── *_auto_profile.yaml        # profils générés automatiquement
│
├── resources/
│   ├── spacy_models.yaml          # ordre de préférence des modèles spaCy par langue (runtime)
│   ├── termsuite_morphology/      # tables de dérivation vendorisées (termsuite-resources, Apache 2.0)
│   │   ├── fr/{suffix-derivation-bank,suppletives-bank}.txt
│   │   └── en/{suffix-derivation-bank,suppletives-bank}.txt
│   └── termsuite_general_language/  # tables de fréquence "langue générale" (termsuite-resources, Apache 2.0)
│       ├── en/general-language.txt
│       ├── fr/general-language.txt
│       └── SOURCE.md              # provenance (pas d'en-tête inline, données contiennent des tokens "#...")
│
├── data/
│   ├── dicts/                     # dictionnaires JSONL (ARKs courants)
│   ├── texts/                     # gold JSONL — textes + expected_matches
│   └── X64_{en,fr}.jsonl          # corpus d'extraction (sans gold, sans vocabulaire requis)
│
├── tests/
│   ├── smoke/
│   │   ├── test_v9_cli.sh                      # [Annotation]
│   │   ├── test_p66_non_regression.sh          # [Annotation]
│   │   ├── render_html_annotation.sh           # [Annotation] génère les HTML locaux
│   │   ├── compare_engines.sh                  # [Annotation] benchmark loterre_cli (local) vs API
│   │   │
│   │   │   # ── Extraction terminologique (v2.0) — voir §5 ──
│   │   ├── test_extract_cli.sh                 # [Extraction] noun chunks de base (Phase 1)
│   │   ├── test_cvalue.sh                      # [Extraction] scoring C-value (Phase 2)
│   │   ├── test_positionrank.sh                # [Extraction] scoring PositionRank + bascule auto
│   │   ├── test_embed.sh                       # [Extraction] scoring par embeddings (Phase 5)
│   │   ├── test_variants.sh                    # [Extraction] détection de variantes (Phase 4)
│   │   ├── test_extract_annotate_cli.sh        # [Les deux] annotate + extract + extract_annotate
│   │   ├── test_specificity.sh                 # [Les deux] motifs TermSuite + spécificité (2026-09-10/11)
│   │   └── run_regression_all.sh               # lance les 7 tests d'extraction ci-dessus en une fois
│   ├── quality/
│   │   └── test_v9_contextual.sh               # [Annotation]
│   └── profiling/
│       └── test_auto_profile_quality.sh        # [Annotation]
│
├── scripts/
│   ├── evaluation/
│   │   ├── evaluate_json.py               # calcul Précision / Rappel / F1 (annotation)
│   │   ├── run_eval.sh                    # évaluation batch EN + FR
│   │   ├── run_generated_eval.sh          # évaluation sur gold auto-générés
│   │   ├── clean_gold.py                 # nettoyage et correction des ARKs
│   │   ├── acter_eval.py                  # benchmark token-level vs gold ACTER (Phase 6, extraction)
│   │   ├── bench_candidate_patterns.py    # --prep-patterns/--all-candidate-patterns vs gold ACTER (2026-09-10)
│   │   ├── bench_specificity.py           # --specificity-filter-pctl/--specificity-top-pct vs gold ACTER (2026-09-11)
│   │   ├── bench_topical.py               # signaux de répartition (NMF, BERTopic…) vs témoin fréquence, rejetés (2026-09-30)
│   │   ├── build_report.py                # rapport --report depuis des sorties existantes, ou depuis son JSON
│   │   ├── sweep_topics.py                # nombre de thèmes du rapport : cohérence, stabilité, couverture (2026-10-08)
│   │   ├── termsuite_acter_eval.py        # sorties TermSuite notées avec le protocole d'acter_eval (2026-10-09)
│   │   └── bench_respot.py                # hypothèse « occurrences » : mêmes candidats, occurrences re-repérées (2026-10-09)
│   ├── corpus/
│   │   ├── txt_to_jsonl.py                # convertit un répertoire/archive .txt en JSONL (extraction)
│   │   └── clean_revueesr.py              # nettoyage du corpus RevueESR (texte PDF)
│   ├── build_dictionaries/
│   │   └── build_dictionaries.py          # génération native des dictionnaires JSONL depuis CSV vocab
│   ├── prediction/
│   │   ├── generate_gold_from_predictions.py   # bootstrap gold depuis prédictions
│   │   ├── results_to_expected_jsonl.py         # convertit pred JSON → expected JSONL
│   │   └── bulk_results_to_expected.sh          # conversion batch d'un répertoire
│   ├── profiling/
│   │   └── run_profile_generation.sh      # génère tous les auto-profiles YAML
│   ├── benchmark/
│   │   ├── run_benchmark.sh               # benchmark rapide local vs API
│   │   └── benchmark_fast_path.sh         # benchmark du fast path uniquement
│   └── generate_fr_corpus.py              # génération des corpus FR avec variants flexionnels
│
└── docs/
    ├── README.md                  # ce fichier — manuel d'utilisation
    ├── curation_guide.md          # consigne de travail du curateur
    ├── underthehood.md            # fonctionnement interne (extraction, annotation, caches)
    └── evaluation.md              # résultats mesurés et protocoles d'évaluation
```

**Répertoires de sortie** (non versionnés) :
```text
html_outputs/         # HTML de loterre_cli (local) vs gold (render_html_annotation.sh)
html_api/             # HTML de l'API production vs gold (loterre_api_eval.py)
benchmark_results/    # résultats complets du benchmark (compare_engines.sh, acter_eval.py)
output_extract/       # sorties JSON des sous-commandes extract/extract_annotate (usage ad-hoc)
corpus_acter/         # corpus ACTER cloné (make corpus-acter, CC BY-NC-SA 4.0, non versionné)
```

**Répertoire de production** (non versionné — gitignore) :
```text
production/
  version.txt                 # numéro de version à incrémenter avant chaque release
  setup.py                    # configuration du package Python
  build_push_package.sh       # script de build, DVC push et publication Git
```

**Données DVC** (non versionnées dans Git) :
```text
dictionary/          # dictionnaires JSONL — géré par DVC (dictionary.dvc versionné)
```

---

## 4. Usage CLI

`loterre_cli.py` utilise une sous-commande positionnelle obligatoire :

| Sous-commande | Annotation (matching vs vocabulaire) | Extraction (candidats sans vocabulaire) | Section |
|---|:---:|:---:|---|
| `annotate` | ✅ | — | ce paragraphe (§4) |
| `extract` | — | ✅ | §5 |
| `extract_annotate` | ✅ | ✅ — extraction puis croisement avec le vocabulaire | §5 |

### Annotation via `loterre_cli.py` (recommandé)

```bash
# Via dict-id (résolu depuis registry.yaml)
python3 src/loterre_cli.py annotate \
  --text data/jsonl/P66_en.jsonl \
  --dict-id P66_en \
  --profile term_recall \
  --silent

# Via chemin explicite
python3 src/loterre_cli.py annotate \
  --text data/jsonl/P66_en.jsonl \
  --dict dictionary/en_annot_P66.jsonl \
  --lang en \
  --profile term_recall \
  --silent

# Via fichier de configuration YAML
python3 src/loterre_cli.py annotate \
  --config configs/P66_en_auto_profile.yaml \
  --silent
```

### Annotation directe via le moteur

```bash
python3 src/loterre_engine_v9_cli.py \
  --text data/jsonl/P66_en.jsonl \
  --dict dictionary/en_annot_P66.jsonl \
  --lang en \
  --profile term_recall \
  --silent
```

### Options principales

| Option | Description |
|---|---|
| `--text` | Chemin vers le fichier JSONL d'entrée (ou stdin si omis) |
| `--dict` | Chemin vers le dictionnaire JSONL |
| `--dict-id` | Identifiant dans registry.yaml (ex: `P66_en`) |
| `--lang` | Langue : `en` ou `fr` |
| `--profile` | Profil : `entity_strict`, `term_balanced`, `term_recall` |
| `--config` | Fichier YAML de configuration (remplace les autres options) |
| `--silent` | Sortie JSON sur stdout, pas de fichiers |
| `--api` | Sortie JSON compacte |
| `--workers N` | Multiprocessing (N processus parallèles) |
| `--execution-strategy` | `full` (défaut), `fast`, `hybrid` |

### Format d'entrée

Chaque ligne du fichier texte est un objet JSON :

```json
{"id": "doc_001", "value": "Texte à annoter..."}
```

Les fichiers gold (`data/jsonl/`) incluent en plus un champ `expected_matches` utilisé par le renderer et le benchmark pour la comparaison.

### Format de sortie (`--silent`)

```json
{
  "profile": "term_recall",
  "docs": 11,
  "timings": {"load_and_profile_s": 0.012, "process_s": 7.1, "total_s": 7.1},
  "results": [
    {
      "id": "doc_001",
      "annotated_text": "**long-term memory**〔[long-term memory](http://...)〕...",
      "matches": [
        {
          "start": 10, "end": 26,
          "found": "long-term memory",
          "pref": "long-term memory",
          "uri": "http://data.loterre.fr/ark:/67375/P66-J8FC45M1-6",
          "label": "long-term memory",
          "rule": "pattern",
          "score": 1.0
        }
      ]
    }
  ]
}
```

> Le champ `text` (texte brut du document) n'est **pas** inclus dans la sortie — le rendu HTML recharge le texte depuis le fichier gold passé en argument. Seul `annotated_text` (markdown pré-rendu) et `matches` sont présents.

### Format de sortie (`--ezs`)

Mode streaming utilisé par le pipeline EZS. Entrée : une ligne JSON `{id, value}` par document. Sortie : une ligne JSON par document, `value` remplacé par la liste des matches, `annotated` ajouté.

```json
{
  "id": "doc_001",
  "annotated": "**long-term memory**〔[long-term memory](http://data.loterre.fr/ark:/67375/P66-J8FC45M1-6)〕...",
  "value": [
    {
      "start": 10,
      "end": 26,
      "found": "long-term memory",
      "pref": "long-term memory",
      "uri": "http://data.loterre.fr/ark:/67375/P66-J8FC45M1-6",
      "label": "long-term memory",
      "rule": "surface_upper_exact",
      "score": 0.9
    }
  ]
}
```

| Champ | Description |
|---|---|
| `id` | Identifiant du document (passé en entrée, inchangé) |
| `annotated` | Texte original avec les termes balisés en markdown `**terme**〔[préférentiel](uri)〕` |
| `value[]` | Liste des matches |
| `value[].start` / `.end` | Offsets caractères dans le texte original |
| `value[].found` | Texte exact trouvé dans le document |
| `value[].pref` | Forme préférentielle du concept |
| `value[].uri` | URI du concept Loterre |
| `value[].label` | Libellé brut du concept |
| `value[].rule` | Règle de matching : `pattern`, `surface_upper_exact`, `surface_structural`, `lemma_structural`, `lemma_pattern_seq` |
| `value[].score` | Score de confiance [0.0–1.0] — seuil recommandé : 0.80 pour les mono-tokens |

---

## 5. Extraction terminologique (v2.0)

Deux sous-commandes supplémentaires de `loterre_cli.py`, ajoutées à `annotate` sans le modifier (extraction de candidats termes, avec ou sans croisement vocabulaire).

### 5.1 `extract` — candidats sans vocabulaire

```bash
python3 src/loterre_cli.py extract \
  --text data/X64_en.jsonl \
  --lang en \
  --extractor auto \
  --silent --out output_extract/x64.json
```

| Option | Description |
|---|---|
| `--lang` | Langue : `en` ou `fr` (requis) |
| `--text` | Fichier JSONL source (lit stdin si omis) |
| `--min-tokens` / `--max-tokens` | Longueur d'un candidat en tokens (défaut 1 / 6) |
| `--min-freq` | Fréquence minimale dans le corpus (défaut **3**) |
| `--extractor` | `ncvalue` (C-value, corpus volumineux), `graph` (PositionRank, corpus court), `embed` (similarité au vocabulaire cible, nécessite `--dict`), `auto` (bascule ncvalue/graph selon `--extractor-auto-threshold`, défaut 50000 tokens — **ne bascule jamais vers `embed`**) |
| `--cvalue-threshold` | Score C-value minimal (`--extractor ncvalue` uniquement ; 0 = pas de filtre) |
| `--dict` | `[--extractor embed]` Dictionnaire JSONL cible, comparé par **plus proche voisin** (pas un centroïde — voir §5.4) |
| `--embed-threshold` | `[--extractor embed]` Similarité cosinus minimale (0 = pas de filtre) |
| `--detect-variants` | Regroupe les variantes (§5.5) — option explicite, défaut désactivé |
| `--prep-patterns` | Ajoute les candidats de forme nom + préposition + nom ("rate of change"), que l'extraction de base ne produit pas. Défaut désactivé |
| `--all-candidate-patterns` | Ajoute toutes les formes de candidats de la grammaire TermSuite (bien plus large que `--prep-patterns`). Utile seulement avec `--extractor ncvalue` sur un document ou un petit lot : dégrade `graph`/`auto` et devient très lent sur un gros corpus. Défaut désactivé |
| `--respot-occurrences` | Compte toutes les occurrences de chaque candidat, y compris à l'intérieur de groupes nominaux plus longs, et fusionne ses variantes de casse. Fréquences plus justes, mais pas plus de suggestions justes pour le curateur (part de suggestions justes de la liste 1 : 0.51 contre 0.53 sans l'option) ; plus lent (RevueESR : 39 min au lieu de 28). Défaut désactivé. Mesures : `docs/evaluation.md` §1.1 |
| `--specificity-filter-pctl` | Retire les N% de candidats les moins spécifiques du domaine (comparés à la langue générale) avant le classement — défaut **0** (désactivé) ; valeur conseillée **40**, avec `--extractor ncvalue` uniquement |
| `--max-terms` | Garde les N meilleurs candidats triés par score décroissant |

> **Choisir un extracteur** : les trois algorithmes sont **exclusifs**, pas combinés ni auto-sélectionnés entre eux (sauf `auto` qui ne bascule qu'entre `ncvalue`/`graph`). `embed` donne le meilleur classement quand un vocabulaire cible pertinent et substantiel existe déjà (voir le diagnostic X64, `planification/planif_extraction_terminologique.md` §Phase 5) ; sinon `ncvalue`/`graph` selon le volume (ci-dessous).
>
> Chiffré sur X64 (vocabulaire Loterre de plusieurs milliers de termes) : taux de candidats pertinents (`in_vocabulary`) en top 20 — C-value ~4/20 (20 %), PositionRank 0/20 (FR) à 9/20 (EN), `embed` (plus proche voisin) **20/20 (100 %) dans les deux langues**. Mais ce gain suppose un vocabulaire cible riche : sur un domaine restreint sans cette richesse, `embed` perd au contraire (variante semi-supervisée ACTER, `docs/evaluation.md` §1).

#### Choix selon le volume du corpus

`ncvalue` (C-value) a besoin de fréquences fiables — celle de chaque candidat, et celle de ses occurrences comme sous-chaîne de termes plus longs — pour pénaliser correctement les termes emboîtés. En dessous d'un certain volume, ces fréquences sont trop rares pour être significatives, et `graph` (PositionRank, qui ne dépend pas des fréquences de termes emboîtés) donne un meilleur classement.

| Volume du corpus | Extracteur recommandé | Pourquoi |
|---|---|---|
| Texte unique, abstract, petit lot (< ~10 000 tokens) | `graph` | Pas assez d'occurrences répétées pour que C-value soit significatif ; PositionRank reste pertinent dès un seul document |
| Corpus moyen (~10 000–50 000 tokens) | `graph` ou `ncvalue` selon le cas | Zone intermédiaire — comparer les deux si le temps le permet |
| Corpus volumineux, mode batch (> 50 000 tokens, ~6–10 articles complets) | `ncvalue` | C-value redevient fiable et dépasse PositionRank en pratique sur corpus académique |

`--extractor auto` (défaut) applique cette règle automatiquement : bascule vers `graph` si `total_tokens < --extractor-auto-threshold` (défaut **50000**), sinon `ncvalue`. Ajuster le seuil :

```bash
python3 src/loterre_cli.py extract --lang en --text mon_corpus.jsonl \
  --extractor auto --extractor-auto-threshold 20000
```

Sur le corpus de référence ACTER (4 domaines de 50 000–65 000 tokens), `graph` devance pourtant `ncvalue` partout (`docs/evaluation.md` §1) : au-dessus du seuil, `ncvalue` n'est pas automatiquement le meilleur choix. Comparer les deux extracteurs sur son propre corpus avant de figer un choix en production.

`embed` est **indépendant du volume** : son choix dépend uniquement de l'existence d'un vocabulaire cible pertinent (`--dict`), jamais sélectionné par `auto`.

### 5.2 `extract_annotate` — extraction + croisement vocabulaire

```bash
python3 src/loterre_cli.py extract_annotate \
  --dict-id X64_en --profile term_recall \
  --text data/X64_en.jsonl \
  --extractor embed --min-freq 3 \
  --silent --out output_extract/x64_embed_en.json
```

Mêmes options que `extract`, plus celles de l'annotation (`--dict-id`/`--dict`/`--profile`/`--config`, requis comme pour `annotate`) et :

| Option | Description |
|---|---|
| `--enrichment-threshold` | `[--extractor embed]` Similarité minimale au terme le plus proche du vocabulaire pour qu'un candidat absent soit proposé en liste 1 (`enrichment_suggestion_embed`) — défaut **0.95** ; un seuil plus bas fait entrer beaucoup de bruit |
| `--structural-top-pct` | `[--extractor embed]` Part des candidats les mieux classés par C-value/PositionRank proposés en liste 2 (`enrichment_suggestion_structural`, voir §5.4) — défaut **2%** |
| `--specificity-top-pct` | `[--extractor embed]` Part des candidats les plus spécifiques du domaine proposés en liste 3 (`enrichment_suggestion_specificity`, voir §5.4) — défaut **0.0 = désactivé** ; valeur conseillée **10** si on l'active, en sachant que cette liste est nettement plus bruitée |
| `--report RAPPORT.html` | Rapport d'analyse HTML autonome (alias `--topic-report`) : chiffres clés (part du vocabulaire retrouvée dans le corpus, documents annotés, suggestions par liste), graphiques de l'annotation et de l'extraction, suggestions les plus fréquentes de chaque liste, et **couverture du vocabulaire par thème (expérimental)**, qui repère les zones du corpus où la ressource manque de termes et les thèmes de bruit. Écrit aussi `RAPPORT.json` et ajoute `topic_id`/`topic_label`/`topic_coverage` aux candidats. Coût faible (~15 s sur 1 500 articles). La partie thèmes est omise sur un corpus trop court. Lecture du rapport : `docs/curation_guide.md` ; mécanisme : `docs/underthehood.md` |
| `--report-topics N` | Nombre de thèmes du rapport (alias `--topic-report-topics`) — défaut 0 = automatique, entre 5 et 30 selon la taille du corpus |

### 5.3 Schéma de sortie (`candidates[]`)

```json
{
  "mode": "extract_annotate",
  "lang": "en",
  "docs": 773,
  "total_tokens": 113042,
  "extractor": "embed",
  "candidates": [
    {
      "uri": "http://data.loterre.fr/ark:/67375/X64-...",
      "term": "linguistics",
      "lemma": "linguistics",
      "pattern": [{"pos": "NOUN", "lemma": "linguistics"}],
      "frequency": 80,
      "n_docs": 41,
      "score": 1.0,
      "rule": "embed",
      "in_vocabulary": true,
      "pref": "linguistics",
      "enrichment_suggestion_embed": null,
      "enrichment_suggestion_structural": null,
      "enrichment_suggestion_specificity": null,
      "canonical_form": null,
      "variant_type": null,
      "structural_score": 0.141,
      "structural_rule": "positionrank",
      "structural_rank": 3,
      "specificity_score": 84335.6,
      "specificity_rank": 12,
      "nearest_vocab_term": "linguistics",
      "context": "… approaches in applied [linguistics] have shown that …",
      "topic_id": 4,
      "topic_label": "language, linguistics, grammar, syntax, corpus",
      "topic_coverage": 0.62,
      "occurrences": [{"start": 120, "end": 131, "doc_id": "doc_042"}]
    }
  ]
}
```

| Champ | Présent si | Description |
|---|---|---|
| `term` / `lemma` / `pattern` | toujours | Surface, lemme(s), détail POS+lemme par token |
| `frequency` / `score` / `rule` | toujours | `rule` = `cvalue`, `positionrank`, `embed`, ou `freq_single_token` (repli mono-token) |
| `in_vocabulary` / `uri` / `pref` | `extract_annotate` | Croisement avec le vocabulaire (span exact, pas simple chevauchement) |
| `enrichment_suggestion_embed` | `extract_annotate` + `--extractor embed` | Niveau 1 : `True` si absent du vocabulaire et `score` (similarité embed) ≥ `--enrichment-threshold` |
| `enrichment_suggestion_structural` | `extract_annotate` + `--extractor embed` | Niveau 2 : `True` si absent du vocabulaire, niveau 1 `False`, et `structural_rank` dans le top `--structural-top-pct` — jamais `True` en même temps que les niveaux 1 et 3. Voir §5.4 et `docs/curation_guide.md` |
| `enrichment_suggestion_specificity` | `extract_annotate` + `--extractor embed` + `--specificity-top-pct` > 0 | Niveau 3 : `True` si absent du vocabulaire, niveaux 1 et 2 `False`, et `specificity_rank` dans le top `--specificity-top-pct` — **désactivé par défaut** (0.0), contrairement aux niveaux 1/2 : liste nettement plus bruitée. Voir §5.4 et `docs/curation_guide.md` |
| `structural_score` / `structural_rule` / `structural_rank` | `extract_annotate` + `--extractor embed` | Signal C-value/PositionRank calculé en parallèle du score embed, indépendant du vocabulaire cible (`structural_rule` = `cvalue` ou `positionrank`, `structural_rank` = 1 pour le plus fort). Jamais utilisé comme score comparable entre corpus — échelle non bornée |
| `specificity_score` / `specificity_rank` | `--specificity-filter-pctl` > 0 (`ncvalue`) OU `--extractor embed` (toujours) | Spécificité du candidat : sa fréquence dans le corpus comparée à sa fréquence en langue générale (mécanisme : `docs/underthehood.md`). Sert au niveau 3 ci-dessus. `specificity_rank` = 1 pour le plus spécifique. `null` si ni l'un ni l'autre n'est actif. Échelle non bornée, pas comparable entre corpus |
| `canonical_form` / `variant_type` | `--detect-variants` | Voir §5.5 |
| `n_docs` | toujours | Nombre de documents distincts contenant le candidat |
| `nearest_vocab_term` | `--extractor embed` | Libellé du terme du vocabulaire le plus proche (celui qui a donné `score`) — aide à juger la suggestion et à la placer dans la ressource |
| `context` | `--text` fourni (pas stdin) | Extrait de texte (±70 caractères) autour de la première occurrence, terme entre crochets |
| `topic_id` / `topic_label` / `topic_coverage` / `topic_generic` | `extract_annotate` + `--report` | Thème principal du candidat (NMF), 5 mots de son étiquette, et couverture de ce thème par le vocabulaire (part des passages du thème contenant un terme propre du vocabulaire). `topic_generic` = `True` si le thème est un fourre-tout de discours général (poids ≥ 2,5 × la moyenne), affiché hors classement dans le rapport. Information de rangement, pas un score — `null` pour les hapax (hors modèle de thèmes) |
| `occurrences` | toujours | Offsets caractères par document (`doc_id` requis — les offsets sont locaux à un document) |

### 5.4 Scoring par embeddings — plus proche voisin

`--extractor embed` utilise le modèle `paraphrase-multilingual-MiniLM-L12-v2` (118 Mo, CPU, FR+EN, à installer par `make models-embed`) et note chaque candidat par sa ressemblance avec le terme **le plus proche** du vocabulaire cible (`nearest_vocab_term` dans la sortie).

**Quand l'utiliser** : `embed` reconnaît bien les candidats qui ressemblent à des termes déjà présents dans le vocabulaire (variantes, voisins proches), mais trouve peu de termes vraiment nouveaux. Il suppose un vocabulaire cible riche et représentatif du domaine. Il n'existe pas de moyen fiable de juger un vocabulaire à l'avance, sans corpus : en cas de doute, comparer `embed` à `ncvalue`/`graph` sur un échantillon de son propre corpus (`docs/evaluation.md` §3).

**Trois listes de suggestion, jamais fusionnées** — chaque candidat absent du vocabulaire peut entrer dans une seule d'entre elles :

| Liste | Champ | Origine | Réglage | Part de suggestions justes (ACTER) |
|---|---|---|---|---:|
| 1 | `enrichment_suggestion_embed` | Très proche d'un terme du vocabulaire | `--enrichment-threshold` (défaut 0.95) | 0.53 |
| 2 | `enrichment_suggestion_structural` | Bien classé par C-value/PositionRank, sans regarder le vocabulaire : capte des termes éloignés de la ressource | `--structural-top-pct` (défaut 2%) | 0.23 |
| 3 | `enrichment_suggestion_specificity` | Très spécifique du domaine par rapport à la langue générale | `--specificity-top-pct` (défaut 0 = désactivée ; 10 conseillé si activée) | 0.14 |

Les listes sont gardées séparées pour que le curateur leur accorde une confiance différente. Dans chaque liste, trier par `frequency` décroissante : les candidats les plus fréquents sont les plus souvent justes. Consigne de relecture : `docs/curation_guide.md` ; mécanisme : `docs/underthehood.md` ; mesures détaillées : `docs/evaluation.md` §2.

### 5.5 Détection de variantes (Phase 4)

`--detect-variants` regroupe les candidats variantes d'une même forme, par 6 mécanismes inspirés des règles par langue de TermSuite (CNRS/TTC) :

| `variant_type` | Mécanisme | Exemple |
|---|---|---|
| `morph_inflection` | Même séquence de lemmes | *"résultats"* → *"résultat"* |
| `graphical` | Clé normalisée accents/casse/tirets/espaces | *"macro-économie"* → *"macroéconomie"* |
| `morph_prefix` | Lemmes identiques sauf un token lié par un préfixe connu | *"machine asynchrone"* → *"machine synchrone"* |
| `syn_expansion` | Squelette de contenu sous-séquence contiguë (couvre aussi N N ↔ N de/of N) | *"panne"* ↔ *"panne de réseau"* |
| `syn_permutation` | Même multiset de lemmes de contenu, ordre différent | *"vitesse annuelle moyenne"* → *"vitesse moyenne annuelle"* |
| `morph_derivation` | Alternance N+Adj ↔ N+Prep+N via les tables de dérivation TermSuite vendorisées (`resources/termsuite_morphology/`) | *"atteinte du poumon"* → *"atteinte pulmonaire"* |

Un candidat n'est jamais le canonique de son propre groupe : `canonical_form` pointe vers le `term` du candidat retenu comme forme canonique (fréquence la plus haute) du cluster ; reste `null` pour un candidat canonique ou non groupé. La synonymie est explicitement hors scope (relation différente d'une variante de forme). Limite connue, documentée : `morph_prefix` garde un faux positif occasionnel sur des mots latins à préfixe historique non séparable synchroniquement (ex. *"information"*/*"formation"*).

Détail des mécanismes et des bugs corrigés en validation : `planification/planif_extraction_terminologique.md` §Phase 4.

### 5.6 Génération de dictionnaires et conversion de corpus

```bash
# Génère un dictionnaire JSONL natif depuis un CSV vocab Loterre
python3 scripts/build_dictionaries/build_dictionaries.py --voc P66 --lang en fr

# Convertit un répertoire (ou une archive .tar.gz/.tgz/.tar/.zip) de .txt en JSONL pour extract/extract_annotate
python3 scripts/corpus/txt_to_jsonl.py mes_textes/ --out corpus.jsonl
python3 scripts/corpus/txt_to_jsonl.py mes_textes.zip --out corpus.jsonl
```

### 5.7 Benchmark ACTER (extraction non supervisée)

```bash
make corpus-acter      # clone https://github.com/AylaRT/ACTER (CC BY-NC-SA 4.0) dans corpus_acter/
make benchmark-acter   # ncvalue vs PositionRank, P/R/F1 token-level vs le gold ACTER
```

Mesure la qualité de l'extraction sur un corpus annoté de référence (4 domaines × 2 langues). Résultats de référence : F1 PositionRank 0.499, C-value 0.398 (token-level). Avec vocabulaire, la liste 1 d'`embed` donne 53 % de suggestions justes, contre 39 % pour TermSuite avec le même nombre de suggestions. Résultats complets, variantes du protocole, comparaison avec D-Terminer et TermSuite : `docs/evaluation.md` §1.

---

## 6. Ressources terminologiques

### 6.1 Ressources exploitées

Le moteur s'appuie sur une ressource principale, les **vocabulaires Loterre** (INIST-CNRS), et sur quelques ressources linguistiques secondaires. Chaque vocabulaire Loterre est exporté en CSV (`prefLabel`/`altLabel` FR et EN, URI ARK du concept) puis converti par `scripts/build_dictionaries/build_dictionaries.py` en un **dictionnaire d'annotation JSONL par vocabulaire et par langue** (`dictionary/{en,fr}_annot_{CODE}.jsonl`, 64 vocabulaires × 2 langues, ~230 Mo, versionnés par DVC). Cette conversion analyse chaque libellé avec un modèle spaCy transformer (`en_core_web_trf`/`fr_dep_news_trf`) pour produire son motif POS+lemme (§6.2) ; elle est faite hors ligne, une fois par mise à jour du vocabulaire, et n'est jamais relancée à l'exécution. Les dictionnaires sont référencés par un code court dans `configs/registry.yaml` (`--dict-id P66_en` → chemin, langue, profil de matching). Le même fichier sert aux trois sous-commandes : `annotate` y cherche les occurrences des termes, `extract_annotate` l'utilise pour marquer les candidats déjà présents (`in_vocabulary`, `uri`, `pref`) et, avec `--extractor embed`, en extrait les libellés préférés (un par concept, dédupliqués par URI) pour calculer la similarité au plus proche voisin (§5.4). Les ressources secondaires sont des fichiers texte du dossier `resources/` : listes de mots faibles par langue (`{en,fr}/weak_words.txt`, filtrage qualité §9), tables de dérivation morphologique (`termsuite_morphology/`, détection de variantes §5.5) et tables de fréquence en langue générale (`termsuite_general_language/`, signal de spécificité), ces deux dernières reprises de `termsuite-resources` (CNRS/TTC, Apache 2.0) ; s'y ajoutent les modèles spaCy de reconnaissance (`resources/spacy_models.yaml`) et le modèle d'embeddings `paraphrase-multilingual-MiniLM-L12-v2`, utilisé hors ligne depuis le cache Hugging Face local.

### 6.2 Format du dictionnaire

Fichier JSONL, une entrée par ligne :

```json
{
  "label": "long-term memory",
  "pref": "long-term memory",
  "id": "http://data.loterre.fr/ark:/67375/P66-J8FC45M1-6",
  "pattern": [
    {"pos": "ADJ", "lemma": "long-term"},
    {"pos": "NOUN", "lemma": "memory"}
  ],
  "altLabels": ["LTM", "long term memory"]
}
```

| Champ | Requis | Description |
|---|---|---|
| `label` | oui | Forme de surface principale |
| `pref` | recommandé | Terme préféré (affiché dans la sortie) |
| `id` | recommandé | URI ARK identifiant le concept (format `http://data.loterre.fr/ark:/67375/XXX-XXXXXXXX-Y`) |
| `pattern` | optionnel | Liste de specs `{pos, lemma}` pour matching POS+lemme |
| `altLabels` / `altLabel` | optionnel | Formes alternatives |
| `variants` | optionnel | Variantes supplémentaires |

**Format ARK** : les identifiants de concept suivent la forme `http://data.loterre.fr/ark:/67375/{CODE}-{XXXXXXXX}-{Y}` où `Y` est une lettre majuscule (ex: `P66-ZLDWBWS5-Z`). Les anciens identifiants numériques (ex: `P66-24670690`) sont obsolètes.

### 6.3 Cache des index

Avant d'annoter, le moteur prépare le dictionnaire en index de recherche. Cette préparation prend quelques secondes pour un petit vocabulaire, plusieurs minutes pour les plus gros (MeSH). Elle est donc mise en cache sur disque, et l'appel suivant avec le même dictionnaire, le même profil et le même modèle spaCy démarre immédiatement. Le cache se met à jour tout seul quand l'un des trois change ; il n'y a rien à vider à la main.

| Besoin | Comment |
|---|---|
| Récupérer le cache déjà calculé pour tous les vocabulaires | `dvc pull` (livré avec les dictionnaires dans `dictionary/.loterre_index_cache/`, ~1,2 Go) |
| Le calculer soi-même | `python3 src/warm_index_cache.py` |
| Choisir son emplacement | variable d'environnement `LOTERRE_INDEX_CACHE_DIR` (défaut : `.loterre_index_cache/` à la racine du dépôt) ; avec le moteur appelé directement, aussi `--index-cache-dir` |
| Forcer la reconstruction | `--no-index-cache` (moteur appelé directement, `src/loterre_engine_v9_cli.py`) |

Les modes `fast`/`hybrid` (§10) ont leur propre cache, dans `.loterre_cache/` (`--cache-dir`). Fonctionnement détaillé des index et des caches : `docs/underthehood.md`, partie « Annotation ».

---

## 7. Profils de matching

Trois profils prédéfinis couvrent le spectre précision/rappel :

| Profil | Usage | Comportement |
|---|---|---|
| `entity_strict` | Entités nommées, acronymes | Priorité aux patterns, pas de passe lemme séquence complète (`use_lemma: false`), uppercase exact |
| `term_balanced` | Terminologie mixte | Équilibre surface+lemme, single-token modéré |
| `term_recall` | Multi-termes, rappel maximal | Tous les chemins activés, seuils plus bas |

### Personnalisation via YAML

```yaml
text: data/jsonl/P66_en.jsonl
dictionary: dictionary/en_annot_P66.jsonl
lang: en
profile: term_recall

profile_overrides:
  use_pattern: true
  use_surface: true
  use_lemma: true
  pattern_priority: false
  allow_single_token_fallback: true
  normalize_separators: true
  normalize_apostrophes: true
  normalize_parentheses: true

quality:
  enabled: true
  single_token_penalty: 0.12
  single_token_min_score: 0.70
  context_guard: true
  contextual_scoring: true
  syntactic_context_guard: false
```

---

## 8. Stratégie de matching

Le moteur applique jusqu'à cinq chemins de matching, dans l'ordre de priorité décroissante :

### 8.1 Normalisation préalable

Appliquée symétriquement au dictionnaire et au texte :
- Apostrophes typographiques → droites
- Tirets (`-`, `–`, `—`, `/`, `_`) → espace
- Mise en minuscule
- Suppression de la ponctuation résiduelle

### 8.2 Chemins de matching

| Règle | Mécanisme | Score multi | Score mono |
|---|---|---|---|
| `pattern` | POS+lemme spec par spec | 1.0 | 1.0 |
| `surface_upper_exact` | Token exactement en majuscules | 0.9 | 0.9 |
| `lemma_pattern_seq` | Séquence de lemmes depuis patterns | 0.9 | 0.9 |
| `surface_structural` | Forme normalisée exacte | 0.85 | 0.75 |
| `lemma_structural` | Lemme spaCy normalisé | 0.82 | 0.72 |

Options correspondantes (`profile_overrides`, §7) :

| Option | Chemins activés | À savoir |
|---|---|---|
| `use_pattern` | `pattern` | Compare toujours les lemmes : un terme au singulier dans le dictionnaire retrouve déjà ses formes fléchies (pluriel, accord), même avec `use_lemma: false` |
| `use_lemma` | `lemma_pattern_seq`, `lemma_structural` | Filet de secours pour les entrées sans motif exploitable |
| `use_surface` | `surface_structural`, `surface_upper_exact` | Forme écrite normalisée, sans lemmatisation |

Quand plusieurs termes se chevauchent, le moteur garde le meilleur score, puis la règle la plus sûre, puis le terme le plus long. Fonctionnement détaillé : `docs/underthehood.md`, partie « Annotation ».

### 8.3 Variantes structurelles automatiques

Pour chaque entrée du dictionnaire, le moteur génère automatiquement :
- La forme canonique normalisée
- La forme sans parenthèses (`"hypermnesia (Pathology)"` → `"hypermnesia"`)
- La forme sans apostrophes (`"Alzheimer's disease"` → `"Alzheimers disease"`)

---

## 9. Filtrage qualité

Le moteur écarte ou pénalise les correspondances douteuses, surtout les termes d'un seul mot. Ces filtres se règlent dans la partie `quality` du YAML (§7) :

| Clé `quality.*` | Défaut | Effet |
|---|---|---|
| `enabled` | `true` | Active l'ensemble du filtrage qualité |
| `strict_stopwords` | `true` | Écarte les mots vides hors position nominale |
| `require_pos_match` | `true` | Exige un nom, un nom propre ou un adjectif |
| `context_guard` | `true` | Écarte un mot isolé entre deux mots outils |
| `discourse_pattern_guard` | `true` | Écarte les mots de discours courants (« and », « bien », « comme »…), même trouvés par `pattern` ; liste remplaçable par `syntactic_generic_words` |
| `syntactic_context_guard` | `false` | Garde syntaxique supplémentaire contre les mots génériques (« is the process that… ») |
| `penalize_single_token` / `single_token_penalty` | `true` / selon le profil | Pénalité de score des termes d'un seul mot, allégée pour les sigles et les noms propres |
| `single_token_min_score` | selon le profil | Score minimal d'un terme d'un seul mot |
| `contextual_scoring` | `true` | Ajuste le score selon les mots voisins |

Valeurs internes des pénalités et bonus : `docs/underthehood.md`, partie « Annotation ».

### Seuil final

| Profil | Seuil |
|---|---|
| `entity_strict` | 0.80 |
| `term_balanced` | 0.75 |
| `term_recall` | 0.70 |

---

## 10. Stratégies d'exécution

### 10.1 Full (défaut)

Pipeline complet : spaCy + patterns + lemmes + filtrage qualité.

### 10.2 Fast

Matching exact par regex compilées, sans spaCy. Chaque match peut contenir `"ambiguous": true`.

```bash
python3 src/loterre_cli.py --execution-strategy fast --dict-id P66_en --text ...
```

### 10.3 Hybrid

Fast path sur tous les documents, puis moteur complet uniquement sur les documents ambigus.

```bash
python3 src/loterre_cli.py \
  --execution-strategy hybrid \
  --dict-id P66_en \
  --text data/jsonl/P66_en.jsonl \
  --hybrid-refine-low-score 0.90 \
  --hybrid-max-fast-matches 50
```

**Critères de raffinement** : `ambiguous: true`, score < seuil, nb matches > max, ou mono-token détecté.

### 10.4 Multiprocessing

```bash
python3 src/loterre_cli.py --dict-id P66_en --text ... --workers 4
```

---

## 11. Auto-profiling

```bash
python3 src/loterre_cli.py \
  --text data/jsonl/P66_en.jsonl \
  --dict-id P66_en \
  --auto-profile \
  --yaml-out configs/P66_en_auto_profile.yaml
```

Choisit le profil (§7) d'après la composition du dictionnaire : beaucoup de sigles et de termes d'un mot → `entity_strict` ; termes longs ou riches en ponctuation → `term_recall` ; sinon `term_balanced`. Le YAML produit peut être relu et ajusté avant usage. Règle exacte : `docs/underthehood.md`, partie « Annotation ».

---

## 12. Gold standard — corpus d'évaluation

### 12.1 Structure des fichiers gold

Les fichiers gold se trouvent dans `data/jsonl/`. Chaque ligne JSONL contient :

```json
{
  "id": 1,
  "value": "Texte du document...",
  "expected_matches": [
    {
      "found": "selective attention",
      "pref": "selective attention",
      "id": "http://data.loterre.fr/ark:/67375/P66-V1086TZP-C",
      "start": 37, "end": 56,
      "rule": "pattern"
    }
  ]
}
```

### 12.2 Vocabulaires disponibles (anglais)

| Fichier | Vocabulaire | Domaine | Docs | Terms attendus |
|---|---|---|---|---|
| `P66_en.jsonl` | P66 | Psychologie de la mémoire | 11 | 346 |
| `27X_en.jsonl` | 27X | Archéologie | 11 | 330 |
| `9SD_en.jsonl` | 9SD | Sciences de la mer | 10 | 300 |
| `8HQ_en.jsonl` | 8HQ | Chimie / Matériaux | 10 | 300 |
| `B9M_en.jsonl` | B9M | Biologie marine | 10 | 300 |
| `BVM_en.jsonl` | BVM | Sciences végétales | 10 | 300 |
| `QX8_en.jsonl` | QX8 | Environnement | 10 | 300 |
| `3JP_en.jsonl` | 3JP | Droit | 10 | 300 |
| `JVR_en.jsonl` | JVR | Musicologie | 10 | 300 |

### 12.3 Vocabulaires disponibles (français)

| Fichier | Vocabulaire | Domaine | Docs | Terms attendus | Variants flexionnels |
|---|---|---|---|---|---|
| `P66_fr.jsonl` | P66 | Psychologie cognitive | 11 | 42 | 18 |
| `27X_fr.jsonl` | 27X | Archéologie | 11 | 30 | 11 |
| `9SD_fr.jsonl` | 9SD | Géographie mondiale | 11 | 32 | 3 |
| `8HQ_fr.jsonl` | 8HQ | Chimie / Éléments périodiques | 11 | 43 | 0 |
| `B9M_fr.jsonl` | B9M | Biologie / Éthologie | 11 | 36 | 12 |
| `BVM_fr.jsonl` | BVM | Géographie française | 11 | 33 | 0 |
| `QX8_fr.jsonl` | QX8 | Géosciences | 11 | 41 | 21 |

**Structure** : document 0 = texte réaliste thématique ; documents 1–10 = textes structurés (1 terme par phrase, 3 termes par document). Les variants flexionnels testent la lemmatisation FR : pluriels (`mémoires à long terme`), pluriels en -aux (`temporaux`), féminins en -ive/-euse (`évolutive`), etc.

**Génération / régénération** :

```bash
python3 scripts/generate_fr_corpus.py
# Produit data/jsonl/{P66,27X,9SD,8HQ,B9M,BVM,QX8}_fr.jsonl
```

Le script `scripts/generate_fr_corpus.py` lit les dictionnaires FR dans `dictionary/`, sélectionne des termes avec variation flexionnelle, calcule les offsets caractère exacts et écrit les fichiers JSONL prêts à l'emploi.

### 12.4 Corrections du gold et logique de comparaison

Les ARK obsolètes des gold anglais ont été corrigés, et la comparaison gold/prédictions se fait par libellé préféré (`pref`), pas par position. Détail : `docs/evaluation.md` §4.

---

## 13. Rendu HTML — visualisation et comparaison

`src/loterre_html_renderer.py` génère une visualisation interactive avec les termes surlignés et cliquables, et un tableau comparatif prédit/attendu par document.

### Code couleur

| Couleur | Signification |
|---|---|
| 🟢 Vert | Terme attendu **et** prédit (both) |
| 🔵 Bleu | Terme attendu mais **non** prédit (expected_only) |
| 🟠 Orange | Terme prédit mais **non** attendu (predicted_only) |

### Génération pour tous les vocabulaires

```bash
# Via le script smoke
bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py data/jsonl ./html_outputs ./src/loterre_html_renderer.py

# Ou via la sous-commande batch du renderer
python3 src/loterre_html_renderer.py batch \
  --cli ./src/loterre_cli.py \
  --text-root data/jsonl \
  --outdir ./html_outputs
```

**Sortie** :
```text
html_outputs/
  json/P66_en.json        ← prédictions brutes du moteur
  html/P66_en.html        ← visualisation annotée vs gold
  html_generation_summary.tsv
```

### Rendu depuis un JSON existant

```bash
python3 src/loterre_html_renderer.py render \
  --input predictions/P66_en.json \
  --gold data/jsonl/P66_en.jsonl \
  --out html_outputs/P66_en.html \
  --title "Annotation P66_en" \
  --base-url "https://www.loterre.fr/ark:/"
```

### Comportement des ARKs dans le HTML

Pour les termes classifiés `both`, le lien pointe vers l'ARK du **match prédit** (vocabulaire courant), même si le gold contient un ancien ARK numérique. Pour les termes `expected_only` (attendus mais non trouvés), l'ARK du gold est utilisé tel quel.

---

## 14. Benchmark : moteur local vs API production

### 14.1 API production ISTEX

L'API de production est accessible en anglais et en français :
```
https://terms-tools.services.istex.fr/v1/en/terms-matcher/json-standoff/annotate?loterreID={VOCAB}
https://terms-tools.services.istex.fr/v1/fr/terms-matcher/json-standoff/annotate?loterreID={VOCAB}
```
où `{VOCAB}` est le code du vocabulaire (ex : `P66`, `27X`).

**Format de requête** : `POST` avec `Content-Type: application/json`, corps = tableau JSON de documents :
```json
[{"id": 1, "value": "Texte à annoter..."}]
```

**Format de réponse** : tableau JSON avec annotations par token :
```json
[{
  "id": 1,
  "value": [{
    "doc": "Texte annoté en [Markdown](http://ark...)",
    "matches": [{
      "idx": {"start": "0", "end": "2"},
      "match": {"id": "http://data.loterre.fr/ark:/67375/P66-...", "text": "spatial memory", "term": "spatial memory"}
    }]
  }]
}]
```

Les positions renvoyées par l'API sont des numéros de tokens, convertis automatiquement en positions de caractères par les scripts d'évaluation (`docs/evaluation.md` §5).

### 14.2 Évaluation de l'API seule

La langue est inférée automatiquement depuis le nom du fichier gold. Elle peut aussi être passée explicitement avec `--lang`.

```bash
# Évaluation EN (langue inférée depuis P66_en.jsonl)
python3 src/loterre_api_eval.py \
  --vocab P66 \
  --gold data/jsonl/P66_en.jsonl \
  --out html_api/html/P66_en.html \
  --json-out html_api/json/P66_en.json

# Évaluation FR (langue inférée depuis P66_fr.jsonl → /v1/fr/...)
python3 src/loterre_api_eval.py \
  --vocab P66 \
  --gold data/jsonl/P66_fr.jsonl \
  --out html_api/html/P66_fr.html \
  --json-out html_api/json/P66_fr.json
```

### 14.3 Benchmark complet (recommandé)

```bash
# Tous les vocabulaires
bash tests/smoke/compare_engines.sh

# Sous-ensemble de vocabulaires
bash tests/smoke/compare_engines.sh --vocabs P66,9SD,27X

# Avec répertoire de sortie daté
bash tests/smoke/compare_engines.sh --out-dir results/$(date +%Y%m%d)

# Sans appels API (local uniquement)
bash tests/smoke/compare_engines.sh --skip-api

# Sans moteur local (API uniquement)
bash tests/smoke/compare_engines.sh --skip-local
```

**Sortie** :
```text
benchmark_results/
  local/json/P66_en.json     ← prédictions loterre_cli (local)
  local/html/P66_en.html     ← HTML loterre_cli (local) vs gold
  api/json/P66_en.json       ← prédictions API production
  api/html/P66_en.html       ← HTML API vs gold
  summary.tsv                ← tableau comparatif (tabulation)
  summary.html               ← tableau comparatif interactif
```

### 14.4 Résultats de référence (juin 2026)

Évaluation sur le corpus gold complet (9 vocabulaires anglais) :

| Vocab | API R% | API F1% | cli R% | cli F1% | ΔF1 |
|---|---|---|---|---|---|
| QX8 | 90.0 | 93.4 | 98.3 | 99.2 | +5.7 |
| B9M | 90.7 | 91.1 | 94.3 | 97.1 | +6.0 |
| 27X | 81.8 | 64.4 | 87.3 | 67.4 | +3.0 |
| P66 | 76.0 | 67.7 | 93.9 | 81.3 | +13.6 |
| BVM | 65.7 | 64.5 | 91.3 | 88.1 | +23.6 |
| 9SD | 65.0 | 66.0 | 90.7 | 92.0 | +26.1 |
| 3JP | 66.3 | 50.4 | 96.7 | 72.3 | +21.9 |
| 8HQ | 34.7 | 37.5 | 80.7 | 89.3 | +51.8 |
| **JVR** | **0.7** | **0.9** | 68.3 | 57.7 | +56.7 |
| **TOTAL** | **63.8** | **61.5** | **89.1** | **81.1** | **+19.6** |

> **Note JVR** : l'API production retourne quasi aucun résultat pour ce vocabulaire (temps de réponse ~40s/batch vs 4s pour les autres) — le vocabulaire semble non chargé côté serveur.

### 14.5 Baseline de non-régression — loterre_cli (local), (juin 2026, EN+FR)

Capturée après correction de 3 bugs (régression scispaCy, priorité aux segments longs dans `dedupe()`, champ `text` manquant en sortie `--silent`). Fichier source : `tests/baselines/annotation_baseline_v1.0.0.json`.

| Vocab | EN F1% | FR F1% |
|---|---|---|
| 27X | 74.7 | 34.1 |
| 3JP | 74.7 | — |
| 8HQ | 89.5 | 44.1 |
| 9SD | 94.4 | 87.3 |
| B9M | 96.0 | 59.8 |
| BVM | 85.0 | 81.0 |
| JVR | 93.5 | — |
| P66 | 83.8 | 66.1 |
| QX8 | 99.2 | 78.7 |
| **TOTAL (16 combinaisons)** | **83.9** (R=93.5%, P=76.1%) | |

> **BVM_en / B9M_fr légèrement sous le §14.4** : écart connu et accepté, dû à la différence entre le modèle spaCy qui a produit le dictionnaire et celui utilisé à l'exécution — détail : `docs/evaluation.md` §5.

Reproduire : `bash tests/smoke/compare_engines.sh --skip-api --skip-resolvers --out-dir <répertoire>`

---

## 15. Performance

### 15.1 Throughput mesuré (WSL2, développement)

| Vocabulaire | Profil | Temps | Docs | docs/s |
|---|---|---|---|---|
| B9M_en | term_recall | 1.9s | 10 | 3.0 |
| 27X_en | term_recall | 1.2s | 11 | 2.3 |
| P66_en | term_recall | 7.1s | 11 | 0.8 |
| 9SD_en | entity_strict | 1.6s | 10 | 0.3 |
| BVM_en | term_recall | 22.9s | 10 | 0.2 |

Optimisations du moteur et gains mesurés : `docs/underthehood.md`, partie « Annotation ».

---

## 16. Tests et workflow de développement

### 16.1 Commandes Makefile

Chaque commande est étiquetée **[Annotation]** (v1.0, sous-commande `annotate`), **[Extraction]** (v2.0, `extract`, sans vocabulaire), **[Les deux]** (`extract_annotate`, extraction puis croisement avec un vocabulaire) ou **[Commun]** (installation, ménage — utile aux deux).

```bash
# ── Commun ──────────────────────────────────────────────────────────────
make install          # pip install -r requirements.txt
make models           # télécharge en_core_web_sm + fr_core_news_sm — requis par annotate ET extract
make clean            # supprime tous les répertoires de sortie générés
make tree             # affiche l'arborescence du projet (profondeur 4)

# ── Annotation (v1.0) ────────────────────────────────────────────────────
make test-smoke       # 13 smoke tests CLI (EN + FR)
make test-non-regression  # non-régression P66_en complète
make test-profiling   # auto-profiling sur tous les vocabulaires EN + FR
make test-quality     # filtrage contextuel (discourse guard, stopwords)
make benchmark                           # benchmark loterre_cli (local) vs API, tous vocabs
make benchmark BENCHMARK_ARGS="--skip-api"         # local uniquement
make benchmark BENCHMARK_ARGS="--vocabs P66_en,9SD_en"  # sous-ensemble
make html             # génère les HTML annotés pour tous les corpus

# ── Extraction (v2.0, sans vocabulaire) ─────────────────────────────────
make models-embed     # télécharge paraphrase-multilingual-MiniLM-L12-v2 (--extractor embed, ~118 Mo)
make test-extract     # extraction noun chunks de base (Phase 1)
make test-cvalue      # scoring C-value (Phase 2)
make test-positionrank  # scoring PositionRank + bascule auto
make test-embed       # scoring par embeddings (Phase 5)
make test-variants    # détection de variantes (Phase 4)
make corpus-acter      # clone le corpus ACTER (gold extraction non supervisée, CC BY-NC-SA 4.0)
make benchmark-acter   # ncvalue vs PositionRank, P/R/F1 token-level vs le gold ACTER
make extract VOCAB=P66 LOTLANG=en             # extraction ad-hoc, sans vocabulaire

# ── Les deux (extraction + croisement vocabulaire) ──────────────────────
make test-extract-annotate  # 3 sous-commandes via loterre_cli.py (annotate/extract/extract_annotate)
make test-specificity  # motifs TermSuite + spécificité (--prep-patterns/--all-candidate-patterns/--specificity-*)
make extract-annotate VOCAB=P66 LOTLANG=en    # extraction + croisement vocabulaire

# ── Orchestrateurs (regroupent les commandes ci-dessus) ──────────────────
make test             # = test-smoke + test-profiling + test-quality + test-extraction
make test-extraction  # = test-extract + test-cvalue + test-positionrank + test-embed + test-variants + test-extract-annotate + test-specificity
```

### 16.2 Lancer les tests directement

```bash
# Smoke tests EN + FR (13 tests au total)
bash tests/smoke/test_v9_cli.sh

# Non-régression P66_en
bash tests/smoke/test_p66_non_regression.sh

# HTML loterre_cli (local) vs gold (tous vocabulaires EN + FR auto-découverts)
bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py data/jsonl ./html_outputs ./src/loterre_html_renderer.py

# Benchmark loterre_cli (local) vs API production (EN + FR)
bash tests/smoke/compare_engines.sh

# Benchmark FR uniquement, sans API
bash tests/smoke/compare_engines.sh \
  --vocabs P66_fr,27X_fr,9SD_fr,8HQ_fr,B9M_fr,BVM_fr,QX8_fr \
  --skip-api --out-dir benchmark_fr

# Évaluation EN (P66_en, 9SD_en) + FR (P66_fr…QX8_fr)
bash scripts/evaluation/run_eval.sh

# Tests contextuels (filtrage qualité)
bash tests/quality/test_v9_contextual.sh

# Tests auto-profiling
bash tests/profiling/test_auto_profile_quality.sh
```

> **Prérequis FR** : le modèle spaCy français doit être installé :
> ```bash
> python3 -m spacy download fr_core_news_sm
> ```

### 16.3 Options du benchmark

```bash
# Toutes options disponibles
bash tests/smoke/compare_engines.sh \
  --text-root  data/jsonl \        # répertoire des gold (EN + FR auto-découverts)
  --out-dir    benchmark_results \     # répertoire de sortie
  --cli        src/loterre_cli.py \    # chemin vers le CLI local
  --renderer   src/loterre_html_renderer.py \
  --vocabs     P66_en,P66_fr \         # sous-ensemble (défaut: tous)
  --skip-local \                       # ignorer le moteur local
  --skip-api \                         # ignorer l'API
  --batch-size 2 \                     # docs/appel API (défaut: 4)
  --api-url    https://.../{lang}/...  # template (défaut: ISTEX /v1/{lang}/...)
```

> L'API ISTEX supporte `en` et `fr` : `/v1/en/...` et `/v1/fr/...`. La langue est inférée automatiquement depuis le nom du fichier gold (`P66_fr.jsonl` → `/v1/fr/...`, `P66_en.jsonl` → `/v1/en/...`). L'option `--api-url` accepte le placeholder `{lang}`.

### 16.4 Workflow de développement d'un nouveau vocabulaire

```
1. Préparer un dictionnaire JSONL + textes de test JSONL
   → ARKs au format http://data.loterre.fr/ark:/67375/{CODE}-{XXXXXXXX}-{Y}

2. Ajouter l'entrée dans configs/registry.yaml

3. Générer la configuration automatique :
   python3 src/loterre_cli.py --dict-id MON_VOCAB --auto-profile --yaml-out configs/mon_vocab.yaml

4. Lancer une première annotation :
   python3 src/loterre_cli.py --config configs/mon_vocab.yaml --silent > pred.json

5. Générer un gold bootstrap :
   python3 scripts/prediction/generate_gold_from_predictions.py --engine src/loterre_cli.py ...

6. Vérifier les ARKs du gold contre le dictionnaire (corriger si nécessaire)

7. Évaluer avec le benchmark :
   bash tests/smoke/compare_engines.sh --vocabs MON_VOCAB

8. Analyser les HTML dans benchmark_results/local/html/ et benchmark_results/api/html/
   → termes bleus : manques du moteur
   → termes orange : faux positifs

9. Ajuster le profil YAML et reboucler
```

### 16.5 Registry

`configs/registry.yaml` référence les dictionnaires disponibles pour `--dict-id` :

```yaml
dictionaries:
  P66_en:
    path: dictionary/en_annot_P66.jsonl
    lang: en
    profile: term_recall
  9SD_en:
    path: dictionary/en_annot_9SD.jsonl
    lang: en
    profile: entity_strict
```

### 16.6 Différence scripts / tests

- `scripts/` : outils de production pour annoter, évaluer, benchmarker
- `tests/` : vérifications automatiques de non-régression et de qualité

---

## 17. Build et déploiement du package

Les scripts de packaging et de déploiement sont dans `production/` (non versionné, non poussé). Voir `production/README.md`.
