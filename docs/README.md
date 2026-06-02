# Loterre v9 — Documentation

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Installation](#2-installation)
3. [Structure du projet](#3-structure-du-projet)
4. [Usage CLI](#4-usage-cli)
5. [Format du dictionnaire](#5-format-du-dictionnaire)
6. [Profils de matching](#6-profils-de-matching)
7. [Stratégie de matching](#7-stratégie-de-matching)
8. [Filtrage qualité](#8-filtrage-qualité)
9. [Stratégies d'exécution](#9-stratégies-dexécution)
10. [Auto-profiling](#10-auto-profiling)
11. [Évaluation et gold standard](#11-évaluation-et-gold-standard)
12. [Sortie HTML](#12-sortie-html)
13. [Performance](#13-performance)
14. [Tests et workflow de développement](#14-tests-et-workflow-de-développement)

---

## 1. Vue d'ensemble

Loterre v9 est un moteur d'annotation terminologique. Il détecte dans un texte les occurrences de termes définis dans un dictionnaire JSONL, en combinant matching exact, matching par lemme spaCy, et règles POS+lemme.

**Capacités** :
- Trois profils précision/rappel prédéfinis
- Filtrage qualité contextuel configurable
- Auto-profiling depuis les statistiques du dictionnaire
- Modes d'exécution : complet, rapide (regex), hybride
- Sortie JSON annotée ou rendu HTML interactif
- Langues : anglais et français

---

## 2. Installation

```bash
pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
python3 -m spacy download fr_core_news_sm
```

`requirements.txt` : `spacy`, `pyyaml`

---

## 3. Structure du projet

```text
loterre-v9/
├── src/
│   ├── loterre_engine_v9_cli.py   # moteur principal
│   ├── loterre_cli.py             # lanceur avec --dict-id et stratégies
│   ├── loterre_fast_path.py       # matching rapide par regex
│   └── loterre_html_renderer.py   # rendu HTML interactif
│
├── configs/
│   ├── registry.yaml              # index des dictionnaires disponibles
│   └── *_auto_profile.yaml        # profils générés automatiquement
│
├── examples/
│   ├── dicts/                     # dictionnaires JSONL exemples
│   └── texts/                     # textes JSONL exemples
│
├── gold/                          # gold standards originaux (auto-générés)
├── gold_cleaned/                  # gold standards nettoyés (référence d'évaluation)
│
├── scripts/
│   ├── evaluation/
│   │   ├── evaluate_json.py       # calcul Précision / Rappel / F1
│   │   ├── run_eval.sh            # évaluation batch P66 + 9SD
│   │   └── clean_gold.py          # nettoyage des gold auto-générés
│   ├── prediction/
│   │   └── generate_gold_from_predictions.py
│   ├── profiling/
│   │   └── run_profile_generation.sh
│   └── benchmark/
│       └── run_benchmark.sh
│
├── tests/
│   ├── smoke/
│   │   ├── test_v9_cli.sh
│   │   ├── test_p66_non_regression.sh
│   │   └── render_html_annotation.sh
│   ├── quality/
│   │   └── test_v9_contextual.sh
│   └── profiling/
│       └── test_auto_profile_quality.sh
│
└── docs/
    └── README.md                  # ce fichier
```

---

## 4. Usage CLI

### Annotation via `loterre_cli.py` (recommandé)

```bash
# Via dict-id (résolu depuis registry.yaml)
python3 src/loterre_cli.py \
  --text examples/texts/P66_en.jsonl \
  --dict-id P66_en \
  --silent

# Via chemin explicite
python3 src/loterre_cli.py \
  --text examples/texts/P66_en.jsonl \
  --dict examples/dicts/en_annot_P66.jsonl \
  --lang en \
  --profile term_recall \
  --silent

# Via fichier de configuration YAML
python3 src/loterre_cli.py \
  --config configs/P66_en_auto_profile.yaml \
  --silent
```

### Annotation directe via le moteur

```bash
python3 src/loterre_engine_v9_cli.py \
  --text examples/texts/P66_en.jsonl \
  --dict examples/dicts/en_annot_P66.jsonl \
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

### Format de sortie (`--silent`)

```json
{
  "profile": "term_recall",
  "docs": 11,
  "timings": {"load_and_profile_s": 0.012, "process_s": 7.1, "total_s": 7.1},
  "results": [
    {
      "id": "doc_001",
      "text": "Texte à annoter...",
      "annotated_text": "**long-term memory**〔[long-term memory](http://...)〕",
      "matches": [
        {
          "start": 10, "end": 26,
          "found": "long-term memory",
          "pref": "long-term memory",
          "uri": "http://data.loterre.fr/ark:/67375/P66-...",
          "label": "long-term memory",
          "rule": "pattern",
          "score": 1.0
        }
      ]
    }
  ]
}
```

---

## 5. Format du dictionnaire

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
  "altLabels": ["LTM", "long term memory"],
  "variants": ["mémoire à long terme"]
}
```

| Champ | Requis | Description |
|---|---|---|
| `label` | oui | Forme de surface principale |
| `pref` | recommandé | Terme préféré (affiché dans la sortie) |
| `id` | recommandé | URI identifiant le concept |
| `pattern` | optionnel | Liste de specs `{pos, lemma}` pour matching POS+lemme |
| `altLabels` / `altLabel` | optionnel | Formes alternatives |
| `variants` | optionnel | Variantes supplémentaires |

**Note** : toutes les formes (label, altLabels, variants) sont indexées avec leurs variantes structurelles (sans parenthèses, sans apostrophes).

---

## 6. Profils de matching

Trois profils prédéfinis couvrent le spectre précision/rappel :

| Profil | Usage | Comportement |
|---|---|---|
| `entity_strict` | Entités nommées, acronymes | Priorité aux patterns, pas de fallback lemme, uppercase exact |
| `term_balanced` | Terminologie mixte | Équilibre surface+lemme, single-token modéré |
| `term_recall` | Multi-termes, rappel maximal | Tous les chemins activés, seuils plus bas |

### Personnalisation via YAML

Un fichier de configuration permet de surcharger n'importe quel paramètre :

```yaml
text: examples/texts/P66_en.jsonl
dictionary: examples/dicts/en_annot_P66.jsonl
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
  syntactic_context_guard: false   # garde syntaxique (désactivé par défaut)
```

---

## 7. Stratégie de matching

Le moteur applique jusqu'à cinq chemins de matching, dans l'ordre de priorité décroissante :

### 7.1 Normalisation préalable

Appliquée symétriquement au dictionnaire et au texte :
- Apostrophes typographiques → droites
- Tirets (`-`, `–`, `—`, `/`, `_`) → espace
- Mise en minuscule
- Suppression de la ponctuation résiduelle

### 7.2 Chemins de matching

| Règle | Mécanisme | Score multi | Score mono |
|---|---|---|---|
| `pattern` | POS+lemme spec par spec | 1.0 | 1.0 |
| `surface_upper_exact` | Token exactement en majuscules | 0.9 | 0.9 |
| `lemma_pattern_seq` | Séquence de lemmes depuis patterns | 0.9 | 0.9 |
| `surface_structural` | Forme normalisée exacte | 0.85 | 0.75 |
| `lemma_structural` | Lemme spaCy normalisé | 0.82 | 0.72 |

### 7.3 Variantes structurelles automatiques

Pour chaque entrée du dictionnaire, le moteur génère automatiquement :
- La forme canonique normalisée
- La forme sans parenthèses (`"hypermnesia (Pathology)"` → `"hypermnesia"`)
- La forme sans apostrophes (`"Alzheimer's disease"` → `"Alzheimers disease"`)

### 7.4 Index de premier token (optimisation)

Le matching par patterns utilise un index par premier token normalisé :
pour chaque position du texte, seules les entrées dont le premier spec correspond sont testées. Cela réduit la complexité de O(T × E) à O(T × avg_candidats).

### 7.5 Déduplication

Sélection gloutonne des meilleurs spans non-chevauchants, triés par :
score décroissant → priorité de règle → longueur → position.

---

## 8. Filtrage qualité

Le module `score_match_quality` applique des filtres et ajustements de score à chaque match single-token.

### 8.1 Filtres durs (élimination)

- `strict_stopwords` : élimine les stopwords en position non-nominale
- `require_pos_match` : exige NOUN, PROPN ou ADJ (désactivé en `term_recall`)
- `context_guard` : élimine un token entouré de deux mots fonctionnels (pour les règles non-pattern)
- `discourse_pattern_guard` : gère les mots pièges (`"well"`, `"and"`, `"or"`)

### 8.2 Garde syntaxique (optionnel)

Activé par `syntactic_context_guard: true`, il détecte sans parser deux patterns fréquents de faux positifs :

1. **Attribut copulatif** : `"is/est the/le <mot_générique> that/qui…"` → élimine `"process"`, `"processus"`, etc.
2. **Mot-titre en position 0** : mot générique en majuscule au début du document

Les listes de mots génériques (`syntactic_generic_words`) et de pronoms relatifs (`syntactic_relative_pronouns`) sont configurables dans le YAML et incluent par défaut des formes EN et FR.

### 8.3 Pénalité adaptative des single-tokens

La pénalité varie selon la morphologie du token au lieu d'être uniforme :

| Cas | Pénalité |
|---|---|
| Tout en majuscules ≥ 2 chars (`ERP`, `SAM`) | min(base, 0.05) — acronyme |
| CamelCase avec majuscule interne (`SenseCam`) | min(base, 0.05) — entité spécifique |
| Tout en minuscules ≤ 3 chars (`cue`, `or`) | max(base, 0.20) — risque élevé |
| Autres | base (valeur du profil) |

### 8.4 Scoring contextuel

Dans une fenêtre de ±2 tokens, le score est ajusté selon les voisins :
- Voisins lexicaux majoritaires → +0.05 (bonus)
- Voisins fonctionnels majoritaires → -0.20 (pénalité)
- Token en NOUN/PROPN/ADJ → +0.05 (bonus POS)

### 8.5 Seuil final

Les matches non-pattern dont le score final est inférieur au seuil du profil sont filtrés :

| Profil | Seuil |
|---|---|
| `entity_strict` | 0.80 |
| `term_balanced` | 0.75 |
| `term_recall` | 0.70 |

Les matches `rule="pattern"` ne sont **pas** filtrés par ce seuil.

### 8.6 Paramètres qualité complets

```yaml
quality:
  enabled: true
  strict_stopwords: true
  require_pos_match: true
  penalize_single_token: true
  single_token_penalty: 0.15         # base, modulée par la pénalité adaptative
  adaptive_single_token_penalty: true
  multi_token_bonus: 0.03
  case_sensitive_entities: true
  context_guard: true
  contextual_scoring: true
  context_window: 2
  discourse_pattern_guard: true
  syntactic_context_guard: false
  syntactic_adp_head_penalty: 0.15
  syntactic_generic_words: []        # surcharge les défauts EN+FR si renseigné
  syntactic_relative_pronouns: []
  function_context_penalty: 0.20
  lexical_context_bonus: 0.05
  exact_pos_bonus: 0.05
  single_token_min_score: 0.75
```

---

## 9. Stratégies d'exécution

### 9.1 Full (défaut)

Pipeline complet : spaCy + patterns + lemmes + filtrage qualité.

```bash
python3 src/loterre_cli.py --execution-strategy full --dict-id P66_en --text ...
```

### 9.2 Fast

Matching exact par regex compilées, sans spaCy. Très rapide, pas de filtrage contextuel.

```bash
python3 src/loterre_cli.py --execution-strategy fast --dict-id P66_en --text ...
```

Chaque match contient `"ambiguous": true` si plusieurs entrées du dictionnaire correspondent à la même forme.

### 9.3 Hybrid

Fast path sur tous les documents, puis moteur complet uniquement sur les documents ambigus.

```bash
python3 src/loterre_cli.py \
  --execution-strategy hybrid \
  --dict-id P66_en \
  --text examples/texts/P66_en.jsonl \
  --hybrid-refine-low-score 0.90 \
  --hybrid-max-fast-matches 50
```

**Pipeline** :
```
Tous les documents → fast path
        ↓
Documents ambigus → moteur complet v9
        ↓
Fusion : résultat v9 écrase fast pour les docs raffinés
```

**Critères de raffinement** (un seul suffit) :
- `ambiguous: true` dans un match
- score < `--hybrid-refine-low-score` (0.90 par défaut)
- nombre de matches > `--hybrid-max-fast-matches` (50)
- `--hybrid-refine-single-tokens` activé et un mono-token détecté

La sortie identifie la source de chaque document :
```json
"hybrid_source": "fast"       // ou "v9_refined"
"hybrid": {"refined_docs": 2, "fast_docs": 10}
```

### 9.4 Multiprocessing

```bash
python3 src/loterre_cli.py --dict-id P66_en --text ... --workers 4
```

Activé automatiquement quand `--workers > 1` et le corpus dépasse `--chunk-size` documents (200 par défaut).

---

## 10. Auto-profiling

Le moteur peut analyser un dictionnaire et suggérer automatiquement un profil et les paramètres qualité adaptés.

### Génération d'une configuration YAML

```bash
python3 src/loterre_cli.py \
  --text examples/texts/P66_en.jsonl \
  --dict-id P66_en \
  --auto-profile \
  --yaml-out configs/P66_en_auto_profile.yaml
```

### Statistiques calculées

| Statistique | Description |
|---|---|
| `ratio_pattern` | Part des entrées avec règles POS+lemme |
| `ratio_mono` | Part des entrées mono-token |
| `ratio_upper_single` | Part des mono-tokens tout en majuscules |
| `ratio_puncty` | Part des entrées avec tirets/parenthèses |
| `avg_label_len` | Longueur moyenne en tokens |
| `ratio_risky_single` | Part des mono-tokens dans une liste de mots ambigus |

### Règle de suggestion de profil

| Condition | Profil suggéré |
|---|---|
| `ratio_pattern ≥ 0.45` ET `ratio_mono ≥ 0.4` ET (beaucoup d'uppercase ou de title-case) | `entity_strict` |
| `ratio_puncty ≥ 0.15` OU `avg_label_len ≥ 2.2` | `term_recall` |
| Sinon | `term_balanced` |

### Génération batch

```bash
bash scripts/profiling/run_profile_generation.sh
```

Génère les fichiers `configs/*_auto_profile.yaml` pour tous les dictionnaires du registry.

---

## 11. Évaluation et gold standard

### 11.1 Évaluation d'un vocabulaire

```bash
# Générer les prédictions
python3 src/loterre_cli.py --dict-id P66_en --text examples/texts/P66_en.jsonl --silent > pred.json

# Évaluer contre le gold nettoyé
python3 scripts/evaluation/evaluate_json.py \
  --gold gold_cleaned/gold_P66_en.jsonl \
  --pred pred.json \
  --mode found_pref
```

**Modes de comparaison** (`--mode`) :
- `found_pref` : compare `(forme_trouvée, terme_préféré)` — mode standard
- `pref_only` : compare uniquement le terme préféré
- `span_pref` : compare `(début, fin, terme_préféré)` — mode strict

**Sortie** :
```json
{
  "tp": 352, "fp": 16, "fn": 0,
  "precision": 0.9565, "recall": 1.0, "f1": 0.9778,
  "top_errors": [...]
}
```

### 11.2 Évaluation batch (P66 + 9SD)

```bash
bash scripts/evaluation/run_eval.sh
```

Les résultats sont écrits dans `eval_outputs/`.

### 11.3 Gold standard — qualité et nettoyage

Les gold standards ont été **auto-générés à partir des prédictions** via `scripts/prediction/generate_gold_from_predictions.py`. Ils héritent donc des biais du moteur (faux positifs acceptés comme corrects).

**Nettoyage automatique** (`gold_cleaned/`) :
```bash
python3 scripts/evaluation/clean_gold.py \
  --gold-dir gold \
  --out-dir gold_cleaned \
  --report gold_cleaned/cleanup_report.json
```

Le script applique deux règles :
1. **Fragments** : supprime les annotations dont le texte trouvé se termine par `-`
2. **Mots génériques à faible score** : supprime les single-tokens score < 0.75 appartenant à la liste `{"quality"}` et analogues
3. **Corrections manuelles** : surcharges encodées dans `MANUAL_REMOVALS` pour des faux positifs identifiés par lecture du texte (ex : `"confidence"` en contexte économique dans P66_en doc 0)

**Référence d'évaluation** : utiliser `gold_cleaned/` plutôt que `gold/` pour des métriques plus fiables.

### 11.4 Interpréter les erreurs

| Symptôme | Cause probable | Action |
|---|---|---|
| FP élevés (bruit) | Seuils trop bas, mots génériques non filtrés | Augmenter `single_token_penalty`, activer `syntactic_context_guard` |
| FN élevés (manques) | Profil trop strict, variantes manquantes | Passer à `term_recall`, enrichir `altLabels` |
| FP sur mono-tokens | Lemme trop générique | Activer `require_pos_match`, ajouter un `pattern` au terme |
| FN sur formes fléchies | Lemmatisation spaCy insuffisante | Ajouter les formes dans `altLabels` |

---

## 12. Sortie HTML

`src/loterre_html_renderer.py` génère une visualisation interactive avec les termes surlignés et cliquables.

### Rendu depuis un JSON existant

```bash
python3 src/loterre_html_renderer.py render \
  --input predictions/P66_en.json \
  --out html_outputs/P66_en.html \
  --title "Annotation P66_en"
```

### Rendu avec comparaison gold/prédictions

```bash
python3 src/loterre_html_renderer.py render \
  --input predictions/P66_en.json \
  --gold gold_cleaned/gold_P66_en.jsonl \
  --out html_outputs/P66_en.html
```

### Batch complet EN + FR

```bash
python3 src/loterre_html_renderer.py batch \
  --cli ./src/loterre_cli.py \
  --text-root examples/texts \
  --outdir ./html_outputs

# Ou via le script shell :
bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py examples/texts ./html_outputs ./src/loterre_html_renderer.py
```

**Vocabulaires traités par défaut** :
- Anglais : P66, 9SD, 8HQ, B9M, 27X, BVM, QX8, 3JP, JVR
- Français : P66, 9SD, 8HQ, B9M, 27X, BVM, QX8

**Structure de sortie** :
```text
html_outputs/
  json/P66_en.json
  html/P66_en.html
  html_generation_summary.json
```

---

## 13. Performance

### 13.1 Throughput mesuré (machine de développement, WSL2)

Mesuré après les optimisations de la session courante :

| Vocabulaire | Profil | Temps | Docs | docs/s |
|---|---|---|---|---|
| B9M_en | term_recall | 1.9s | 10 | 3.0 |
| 27X_en | term_recall | 1.2s | 11 | 2.3 |
| P66_en | term_recall | 7.1s | 11 | 0.8 |
| 9SD_en | entity_strict | 1.6s | 10 | 0.3 |
| BVM_en | term_recall | 22.9s | 10 | 0.2 |

La variance s'explique par la taille et la proportion de patterns dans chaque dictionnaire.

### 13.2 Répartition du temps (cProfile, P66_en après optimisations)

| Fonction | % temps | Appels |
|---|---|---|
| `token_matches_spec` | ~50% | ~11M |
| `match_pattern_entry` / `match_patterns_indexed` | ~25% | ~42K |
| Reste (trie, quality, spaCy) | ~25% | — |

### 13.3 Optimisations implémentées

**Session 2025-06 :**

| Optimisation | Gain mesuré |
|---|---|
| Pré-compilation de `_PUNCT_RE` et `_PUNCT_KEEP_APOS_RE` | −8s sur P66_en (suppression de 22M appels `re._compile`) |
| Pré-calcul de `spec._norm_lemma` dans `build_indexes` | −5s (suppression de la renormalisation dans `token_matches_spec`) |
| LRU cache sur `normalize_text` (16 384 entrées, 99.9% hit rate) | −60% des appels totaux |
| Index patterns par premier token normalisé | ×2 à ×73 selon le vocabulaire |

**Cumul vs point de départ** :
- P66_en : 33s → 7s (×4.7)
- 9SD_en : 117s → 1.6s (×73)
- 27X_en : 16s → 1.2s (×13)

### 13.4 Améliorations à venir

| Amélioration | Gain estimé | Effort |
|---|---|---|
| Streaming ligne par ligne (I/O) | −5 à 20% mémoire | Faible |
| Aho-Corasick pour les tries surface/lemme | +15 à 70% selon dict | Élevé |
| Indexation par POS du premier token (en plus du lemme) | −20% supplémentaire | Moyen |

---

## 14. Tests et workflow de développement

### 14.1 Lancer les tests

```bash
# Smoke tests (fonctionnalité CLI de base)
bash tests/smoke/test_v9_cli.sh

# Non-régression P66 (CLI + conversion + HTML)
bash tests/smoke/test_p66_non_regression.sh

# Évaluation qualité P66 + 9SD
bash scripts/evaluation/run_eval.sh

# Tests contextuels (filtrage qualité)
bash tests/quality/test_v9_contextual.sh

# Tests auto-profiling
bash tests/profiling/test_auto_profile_quality.sh
```

Commande complète :
```bash
bash tests/smoke/test_v9_cli.sh && bash scripts/evaluation/run_eval.sh
```

### 14.2 Workflow de développement d'un nouveau vocabulaire

```
1. Préparer un dictionnaire JSONL + textes de test JSONL

2. Générer la configuration automatique :
   python3 src/loterre_cli.py --dict-id MON_VOCAB --auto-profile --yaml-out configs/mon_vocab.yaml

3. Lancer une première annotation :
   python3 src/loterre_cli.py --config configs/mon_vocab.yaml --silent > pred.json

4. Générer un gold bootstrap :
   python3 scripts/prediction/generate_gold_from_predictions.py --engine src/loterre_cli.py ...

5. Nettoyer le gold (supprimer les faux positifs évidents) :
   python3 scripts/evaluation/clean_gold.py --gold-dir gold --out-dir gold_cleaned

6. Évaluer :
   python3 scripts/evaluation/evaluate_json.py --gold gold_cleaned/gold_MON_VOCAB.jsonl --pred pred.json

7. Analyser les top_errors (FP = bruit, FN = manques) et ajuster le YAML

8. Reboucler jusqu'à satisfaction
```

### 14.3 Registry

`configs/registry.yaml` référence les dictionnaires disponibles pour `--dict-id` :

```yaml
dictionaries:
  P66_en:
    path: examples/dicts/en_annot_P66.jsonl
    lang: en
    profile: term_recall
  9SD_en:
    path: examples/dicts/en_annot_9SD.jsonl
    lang: en
    profile: entity_strict
```

### 14.4 Différence scripts / tests

- `scripts/` : outils de production pour annoter, évaluer, benchmarker
- `tests/` : vérifications automatiques de non-régression
