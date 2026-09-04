# Loterre-Annotator — Documentation

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Installation](#2-installation)
3. [Structure du projet](#3-structure-du-projet)
4. [Usage CLI](#4-usage-cli)
5. [Extraction terminologique (v2.0)](#5-extraction-terminologique-v20)
6. [Format du dictionnaire](#6-format-du-dictionnaire)
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

---

## 1. Vue d'ensemble

Loterre-Annotator est un moteur d'annotation et d'extraction terminologique. Il comprend trois fonctions (`annotate`/`extract`/`extract_annotate`) :
- **`annotate`** (v1.0) : détecte dans un texte les occurrences de termes définis dans un dictionnaire JSONL, en combinant matching exact, matching par lemme spaCy, et règles POS+lemme.
- **`extract`** (v2.0) : extrait des candidats termes d'un texte **sans** vocabulaire (noun chunks spaCy + scoring C-value, PositionRank, ou similarité aux embeddings d'un vocabulaire cible).
- **`extract_annotate`** (v2.0) : extraction puis croisement **avec** un vocabulaire Loterre — marque chaque candidat `in_vocabulary` (avec `uri`/`pref`) ou suggère son ajout (`enrichment_suggestion`).

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
- Benchmark avec le gold ACTER (extraction uniquement, comparable à D-Terminer)

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

> **`--extractor embed` ne nécessite pas d'accès réseau après le premier téléchargement** : `loterre_embed.py` force `HF_HUB_OFFLINE=1`, donc le modèle est chargé exclusivement depuis le cache local (`~/.cache/huggingface/hub/`) — cohérent avec la contrainte projet "pas d'accès cloud" (CPU uniquement, voir `CLAUDE.md`).

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
│   └── loterre_variants.py        # [Extraction] détection de variantes (graphiques/morpho/syntaxiques, TermSuite)
│
├── configs/
│   ├── registry.yaml              # index des dictionnaires disponibles
│   └── *_auto_profile.yaml        # profils générés automatiquement
│
├── resources/
│   ├── spacy_models.yaml          # ordre de préférence des modèles spaCy par langue (runtime)
│   └── termsuite_morphology/      # tables de dérivation vendorisées (termsuite-resources, Apache 2.0)
│       ├── fr/{suffix-derivation-bank,suppletives-bank}.txt
│       └── en/{suffix-derivation-bank,suppletives-bank}.txt
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
│   │   └── run_regression_all.sh               # lance les 6 tests d'extraction ci-dessus en une fois
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
│   │   └── acter_eval.py                  # benchmark token-level vs gold ACTER (Phase 6, extraction)
│   ├── corpus/
│   │   └── txt_to_jsonl.py                # convertit un répertoire/archive .txt en JSONL (extraction)
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
    └── README.md                  # ce fichier
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
| `--max-terms` | Garde les N meilleurs candidats triés par score décroissant |

> **Choisir un extracteur** : les trois algorithmes sont **exclusifs**, pas combinés ni auto-sélectionnés entre eux (sauf `auto` qui ne bascule qu'entre `ncvalue`/`graph`). `embed` donne le meilleur classement quand un vocabulaire cible pertinent et substantiel existe déjà (voir le diagnostic X64, `planification/planif_extraction_terminologique.md` §Phase 5) ; sinon `ncvalue`/`graph` selon le volume (ci-dessous).
>
> Chiffré sur X64 (vocabulaire Loterre de plusieurs milliers de termes) : taux de candidats pertinents (`in_vocabulary`) en top 20 — C-value ~4/20 (20 %), PositionRank 0/20 (FR) à 9/20 (EN), `embed` (plus proche voisin) **20/20 (100 %) dans les deux langues**. Mais ce gain suppose un vocabulaire cible riche : sur un domaine restreint sans cette richesse, `embed` perd au contraire (voir §5.7, variante semi-supervisée ACTER). Détail : `planification/analyse_benchmarks_extraction.md`.

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

Mesuré sur le gold ACTER (4 domaines, corpus de 50 000–65 000 tokens chacun, voir §5.7) : `graph` (F1=0.496) devance `ncvalue` (F1=0.391) sur les 8 combinaisons domaine/langue testées — au-dessus du seuil par défaut, `ncvalue` n'est donc pas automatiquement le meilleur choix en absolu, seulement le plus *fiable statistiquement* à grand volume ; comparer les deux extracteurs sur son propre corpus reste recommandé avant de figer un choix en production. Détail complet : `planification/analyse_benchmarks_extraction.md` §Dépendance au volume.

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
| `--enrichment-threshold` | `[--extractor embed]` Similarité cosinus minimale (plus proche voisin) pour marquer un candidat absent du vocabulaire comme suggestion d'enrichissement (défaut **0.95** — au plus proche voisin, du bruit courant/peu spécifique score encore 0.90-0.96, un seuil bas suggérerait massivement du bruit) |

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
      "score": 1.0,
      "rule": "embed",
      "in_vocabulary": true,
      "pref": "linguistics",
      "enrichment_suggestion": null,
      "canonical_form": null,
      "variant_type": null,
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
| `enrichment_suggestion` | `extract_annotate` + `--extractor embed` | `True` si absent du vocabulaire et score ≥ `--enrichment-threshold` |
| `canonical_form` / `variant_type` | `--detect-variants` | Voir §5.5 |
| `occurrences` | toujours | Offsets caractères par document (`doc_id` requis — les offsets sont locaux à un document) |

### 5.4 Scoring par embeddings — plus proche voisin

`--extractor embed` charge `paraphrase-multilingual-MiniLM-L12-v2` (118 Mo, CPU, FR+EN, `sentence-transformers`) et note chaque candidat par sa similarité cosinus au terme **le plus proche** du vocabulaire cible (max sur tous les termes, pas une moyenne/centroïde) — un vocabulaire Loterre mélange des sous-catégories sémantiquement très différentes (ex. X64, vocabulaire linguistique : 38-42% de concepts à un seul mot, des noms de langues, mais aussi des notions abstraites multi-mots), qu'un centroïde unique brouillerait. Aucun appel réseau : le modèle est chargé avec `HF_HUB_OFFLINE=1` depuis le cache local (`make models-embed` pour le pré-télécharger).

#### Évaluer si un vocabulaire cible est adapté à `embed`

Piste explorée et **abandonnée** : mesurer une densité interne du vocabulaire seul (scission seed/held-out, similarité au plus proche voisin), sans corpus de texte réel. Calibration testée sur 4 cas connus (X64 + 3 domaines ACTER, voir `planification/analyse_benchmarks_extraction.md`) : le vocabulaire ACTER `wind` est le **plus dense** de tous (médiane 0.874, au-dessus de X64 à 0.828) et donne pourtant le **pire** F1 réel (0.286, variante semi-supervisée) — ni la densité ni même la taille du vocabulaire (`corp`, 463 termes, F1=0.407 > `htfl`, 1180 termes, F1=0.345) ne discriminent les cas qui marchent des cas qui échouent. Cause probable : ces métriques ignorent le bruit des candidats non-termes extraits d'un texte réel, qui est le facteur dominant du rappel en production (précision correcte 0.55–0.85 partout, mais rappel bas 0.17–0.34 quel que soit le domaine — voir `benchmark_results/acter/acter_results_embed_seeded.json`). Aucun diagnostic sans corpus de texte réel n'est donc fiable ; seule la méthodologie d'`acter_eval.py` (seed/held-out sur un **corpus de texte réel** annoté) est validée pour évaluer `embed` avant de le choisir en production.

Ce détail précision/rappel donne toutefois un indice exploitable, indépendant du vocabulaire : `embed` **valide bien** un candidat qui ressemble à un terme déjà présent dans le vocabulaire cible (précision correcte), mais **rate la plupart des termes vraiment absents/nouveaux** qu'on lui demande de découvrir à partir de rien (rappel bas) — profil constant sur les 8 combinaisons domaine/langue testées. Ce n'est donc pas une propriété du vocabulaire qui doit guider le choix, mais la nature de la tâche :
- candidats attendus majoritairement proches de termes déjà connus du vocabulaire cible (variantes, synonymes, cas proches — matching/filtrage de bruit, cas réel X64 en `extract_annotate --extractor embed` pour `in_vocabulary`) → `embed` adapté ;
- objectif de découvrir des termes largement absents/nouveaux du vocabulaire cible (enrichissement pur, terminologie émergente) → ne pas compter sur `embed`, préférer `ncvalue`/`graph`.

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

# Convertit un répertoire (ou une archive .tar.gz) de .txt en JSONL pour extract/extract_annotate
python3 scripts/corpus/txt_to_jsonl.py mes_textes/ --out corpus.jsonl
```

### 5.7 Benchmark ACTER (extraction non supervisée)

```bash
make corpus-acter      # clone https://github.com/AylaRT/ACTER (CC BY-NC-SA 4.0) dans corpus_acter/
make benchmark-acter   # ncvalue vs PositionRank, P/R/F1 token-level vs le gold ACTER
```

Compare `ncvalue`/`graph` (sans vocabulaire, comme D-Terminer) sur 4 domaines × 2 langues. Résultat de référence : F1 PositionRank=0.496, C-value=0.391 (au sommet de la fourchette D-Terminer 0.32–0.50, mBERT+RNN+GPU). `--extractor embed` exclu de cette comparaison (nécessite un vocabulaire cible, qu'ACTER n'a pas) — voir `scripts/evaluation/acter_eval.py` pour la variante expérimentale semi-supervisée.

Cette variante (moitié du gold ACTER comme vocabulaire de référence, l'autre moitié à retrouver) donne F1=0.364 pour `embed` — **moins bon** que C-value (0.391) et PositionRank (0.496) évalués à froid sur le même gold, malgré la moitié des réponses fournies comme référence. À l'inverse du gain massif observé sur X64 (§5.1), un vocabulaire de référence restreint ne donne pas à `embed` un signal suffisant : préférer `ncvalue`/`graph` quand le vocabulaire cible est petit ou peu représentatif du domaine.

---

## 6. Format du dictionnaire

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

---

## 7. Profils de matching

Trois profils prédéfinis couvrent le spectre précision/rappel :

| Profil | Usage | Comportement |
|---|---|---|
| `entity_strict` | Entités nommées, acronymes | Priorité aux patterns, pas de fallback lemme, uppercase exact |
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

### 8.3 Variantes structurelles automatiques

Pour chaque entrée du dictionnaire, le moteur génère automatiquement :
- La forme canonique normalisée
- La forme sans parenthèses (`"hypermnesia (Pathology)"` → `"hypermnesia"`)
- La forme sans apostrophes (`"Alzheimer's disease"` → `"Alzheimers disease"`)

### 8.4 Index de premier token (optimisation)

Le matching par patterns utilise un index par premier token normalisé : pour chaque position du texte, seules les entrées dont le premier spec correspond sont testées.

### 8.5 Déduplication

Sélection gloutonne des meilleurs spans non-chevauchants, triés par : score décroissant → priorité de règle → longueur → position.

---

## 9. Filtrage qualité

### 9.1 Filtres durs (élimination)

- `strict_stopwords` : élimine les stopwords en position non-nominale
- `require_pos_match` : exige NOUN, PROPN ou ADJ
- `context_guard` : élimine un token entouré de deux mots fonctionnels
- `discourse_pattern_guard` : filtre les mots fonctionnels courants même pour les matches `rule="pattern"`, via des sets langue-spécifiques :
  - **EN** : `{"and", "or", "it", "well", "can", "may", "like"}`
  - **FR** : `{"et", "ou", "ni", "mais", "il", "elle", "on", "bien", "ainsi", "comme"}`
  - Le set est sélectionné automatiquement depuis `lang` et peut être surchargé par `quality.syntactic_generic_words`

### 9.2 Garde syntaxique (optionnel)

Activé par `syntactic_context_guard: true` :
1. **Attribut copulatif** : `"is the <mot_générique> that…"` → élimine `"process"`, etc.
2. **Mot-titre en position 0** : mot générique en majuscule au début du document

### 9.3 Pénalité adaptative des single-tokens

| Cas | Pénalité |
|---|---|
| Tout en majuscules ≥ 2 chars (`ERP`, `SAM`) | min(base, 0.05) — acronyme |
| CamelCase avec majuscule interne (`SenseCam`) | min(base, 0.05) — entité spécifique |
| Tout en minuscules ≤ 3 chars (`cue`, `or`) | max(base, 0.20) — risque élevé |
| Autres | base (valeur du profil) |

### 9.4 Scoring contextuel

Dans une fenêtre de ±2 tokens :
- Voisins lexicaux majoritaires → +0.05 (bonus)
- Voisins fonctionnels majoritaires → -0.20 (pénalité)
- Token en NOUN/PROPN/ADJ → +0.05 (bonus POS)

### 9.5 Seuil final

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

| Condition | Profil suggéré |
|---|---|
| `ratio_pattern ≥ 0.45` ET `ratio_mono ≥ 0.4` ET beaucoup d'uppercase | `entity_strict` |
| `ratio_puncty ≥ 0.15` OU `avg_label_len ≥ 2.2` | `term_recall` |
| Sinon | `term_balanced` |

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

### 12.4 Qualité des ARKs — corrections appliquées (corpus anglais)

Les gold ont été générés avec des versions antérieures des vocabulaires et contenaient des ARKs obsolètes (format numérique `P66-84482143`). Les corrections suivantes ont été appliquées :

**Corrections automatiques (correspondance par libellé préféré)** :
- **P66** : 289 ARKs numériques → alphanumériques courants
- **27X** : 294 ARKs numériques → alphanumériques courants
- 7 autres corpus (9SD, 8HQ, B9M, BVM, QX8, 3JP, JVR) : déjà corrects

**Corrections manuelles (termes absents du dictionnaire courant)** :

| Terme | Ancien ARK | ARK courant |
|---|---|---|
| `scientific discourse` (P66) | P66-24670690 | `P66-ZLDWBWS5-Z` |
| `speed cell` (P66) | P66-84416865 | `P66-FSHB2M05-B` |
| `scene construction theory` (P66) | P66-43657611 | `P66-GXCZ963J-Z` |
| `sleep-dependent memory triage` (P66) | P66-89130182 | `P66-SW8FNBND-B` |
| `scientific principle` (P66) | P66-24184462 | `P66-N7XGNQGG-J` |

**Termes supprimés** (absents des vocabulaires actuels) :
- `beetle` (27X) — 3 occurrences retirées
- `ceramic assemblage` (27X) — 3 occurrences retirées

### 12.5 Logique de comparaison gold/prédictions

Le renderer et le benchmark utilisent une comparaison **par libellé préféré** (`pref`), indépendante de la position exacte. Cette approche est nécessaire car les offsets de position du gold pour les documents 1+ sont systématiquement décalés par rapport au texte réel (conséquence de la génération avec une version différente du texte).

**Algorithme** (`loterre_html_renderer.py`) :
1. `ann_key(m)` retourne `pref.lower()` — clé de comparaison indépendante de la position et du format d'ARK
2. `ann_span(m, text)` valide `text[start:end] == found` avant d'utiliser la position ; si la position est incorrecte, recherche la surface form dans le texte
3. `classify()` groupe les matches par `pref` et apparie la i-ème occurrence attendue avec la i-ème occurrence prédite (trié par position) — gère correctement les occurrences multiples du même concept
4. `counts()` utilise `Counter` pour un comptage par occurrence (pas par concept unique)

**Conséquence** : un terme prédit au bon endroit mais avec un ARK plus récent (alphananumérique) est correctement reconnu comme correspondant au terme attendu avec l'ancien ARK.

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

Les `idx.start/end` sont des indices de **tokens** (non des offsets caractères). Le tokeniseur de l'API isole la ponctuation et traite les nombres décimaux comme un seul token (`1.1` → 1 token, non 3). Le convertisseur local (`api_doc_to_matches`) utilise la même règle `r"\d+\.\d+|\w+|[^\w\s]"` pour garantir l'alignement des indices.

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

> **BVM_en / B9M_fr légèrement sous la table 13.4** : cause identifiée — mismatch de tagging POS entre le dictionnaire (généré avec `en_core_web_trf`/`fr_dep_news_trf`) et le runtime (`en_core_web_sm`/`fr_core_news_sm`), confirmé indépendant des 3 correctifs ci-dessus (reproduit à l'identique avec l'ancien moteur via `git stash`).

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

### 15.2 Optimisations implémentées

| Optimisation | Gain mesuré |
|---|---|
| Pré-compilation de `_PUNCT_RE` | −8s sur P66_en |
| Pré-calcul de `spec._norm_lemma` | −5s |
| LRU cache sur `normalize_text` (99.9% hit rate) | −60% des appels |
| Index patterns par premier token normalisé | ×2 à ×73 selon le vocabulaire |

**Cumul** : P66_en 33s → 7s (×4.7), 9SD_en 117s → 1.6s (×73), 27X_en 16s → 1.2s (×13)

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
make extract-annotate VOCAB=P66 LOTLANG=en    # extraction + croisement vocabulaire

# ── Orchestrateurs (regroupent les commandes ci-dessus) ──────────────────
make test             # = test-smoke + test-profiling + test-quality + test-extraction
make test-extraction  # = test-extract + test-cvalue + test-positionrank + test-embed + test-variants + test-extract-annotate
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
