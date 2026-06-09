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
11. [Gold standard — corpus d'évaluation](#11-gold-standard--corpus-dévaluation)
12. [Rendu HTML — visualisation et comparaison](#12-rendu-html--visualisation-et-comparaison)
13. [Benchmark : moteur local vs API production](#13-benchmark--moteur-local-vs-api-production)
14. [Performance](#14-performance)
15. [Tests et workflow de développement](#15-tests-et-workflow-de-développement)
16. [Build et déploiement du package](#16-build-et-déploiement-du-package)

---

## 1. Vue d'ensemble

Loterre v9 est un moteur d'annotation terminologique. Il détecte dans un texte les occurrences de termes définis dans un dictionnaire JSONL, en combinant matching exact, matching par lemme spaCy, et règles POS+lemme.

**Capacités** :
- Trois profils précision/rappel prédéfinis
- Filtrage qualité contextuel configurable
- Auto-profiling depuis les statistiques du dictionnaire
- Modes d'exécution : complet, rapide (regex), hybride
- Sortie JSON annotée ou rendu HTML interactif avec comparaison gold
- Benchmark intégré contre l'API production ISTEX
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
│   ├── loterre_html_renderer.py   # rendu HTML interactif + comparaison gold
│   ├── loterre_api_eval.py        # évaluation de l'API production ISTEX
│   └── loterre_benchmark.py       # benchmark local v9 vs API production
│
├── configs/
│   ├── registry.yaml              # index des dictionnaires disponibles
│   └── *_auto_profile.yaml        # profils générés automatiquement
│
├── data/
│   ├── dicts/                     # dictionnaires JSONL (ARKs courants)
│   └── texts/                     # gold JSONL — textes + expected_matches
│
├── tests/
│   ├── smoke/
│   │   ├── test_v9_cli.sh
│   │   ├── test_p66_non_regression.sh
│   │   ├── render_html_annotation.sh  # génère les HTML locaux
│   │   └── compare_engines.sh         # benchmark local v9 vs API
│   ├── quality/
│   │   └── test_v9_contextual.sh
│   └── profiling/
│       └── test_auto_profile_quality.sh
│
├── scripts/
│   ├── evaluation/
│   │   ├── evaluate_json.py               # calcul Précision / Rappel / F1
│   │   ├── run_eval.sh                    # évaluation batch EN + FR
│   │   ├── run_generated_eval.sh          # évaluation sur gold auto-générés
│   │   └── clean_gold.py                 # nettoyage et correction des ARKs
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
html_outputs/        # HTML du moteur local v9 vs gold (render_html_annotation.sh)
html_api/            # HTML de l'API production vs gold (loterre_api_eval.py)
benchmark_results/   # résultats complets du benchmark (compare_engines.sh)
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

### Annotation via `loterre_cli.py` (recommandé)

```bash
# Via dict-id (résolu depuis registry.yaml)
python3 src/loterre_cli.py \
  --text data/jsonl/P66_en.jsonl \
  --dict-id P66_en \
  --silent

# Via chemin explicite
python3 src/loterre_cli.py \
  --text data/jsonl/P66_en.jsonl \
  --dict dictionary/en_annot_P66.jsonl \
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
      "idx": {"start": 10, "end": 26},
      "match": {
        "id": "http://data.loterre.fr/ark:/67375/P66-J8FC45M1-6",
        "ul": "long-term memory",
        "term": "long-term memory"
      }
    }
  ]
}
```

| Champ | Description |
|---|---|
| `id` | Identifiant du document (passé en entrée, inchangé) |
| `annotated` | Texte original avec les termes balisés en markdown |
| `value[]` | Liste des matches |
| `value[].idx.start/end` | Offsets caractères dans le texte original |
| `value[].match.id` | URI du concept |
| `value[].match.ul` | Forme préférentielle du concept |
| `value[].match.term` | Texte exact trouvé dans le document |

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

## 6. Profils de matching

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

Le matching par patterns utilise un index par premier token normalisé : pour chaque position du texte, seules les entrées dont le premier spec correspond sont testées.

### 7.5 Déduplication

Sélection gloutonne des meilleurs spans non-chevauchants, triés par : score décroissant → priorité de règle → longueur → position.

---

## 8. Filtrage qualité

### 8.1 Filtres durs (élimination)

- `strict_stopwords` : élimine les stopwords en position non-nominale
- `require_pos_match` : exige NOUN, PROPN ou ADJ
- `context_guard` : élimine un token entouré de deux mots fonctionnels
- `discourse_pattern_guard` : filtre les mots fonctionnels courants même pour les matches `rule="pattern"`, via des sets langue-spécifiques :
  - **EN** : `{"and", "or", "it", "well", "can", "may", "like"}`
  - **FR** : `{"et", "ou", "ni", "mais", "il", "elle", "on", "bien", "ainsi", "comme"}`
  - Le set est sélectionné automatiquement depuis `lang` et peut être surchargé par `quality.syntactic_generic_words`

### 8.2 Garde syntaxique (optionnel)

Activé par `syntactic_context_guard: true` :
1. **Attribut copulatif** : `"is the <mot_générique> that…"` → élimine `"process"`, etc.
2. **Mot-titre en position 0** : mot générique en majuscule au début du document

### 8.3 Pénalité adaptative des single-tokens

| Cas | Pénalité |
|---|---|
| Tout en majuscules ≥ 2 chars (`ERP`, `SAM`) | min(base, 0.05) — acronyme |
| CamelCase avec majuscule interne (`SenseCam`) | min(base, 0.05) — entité spécifique |
| Tout en minuscules ≤ 3 chars (`cue`, `or`) | max(base, 0.20) — risque élevé |
| Autres | base (valeur du profil) |

### 8.4 Scoring contextuel

Dans une fenêtre de ±2 tokens :
- Voisins lexicaux majoritaires → +0.05 (bonus)
- Voisins fonctionnels majoritaires → -0.20 (pénalité)
- Token en NOUN/PROPN/ADJ → +0.05 (bonus POS)

### 8.5 Seuil final

| Profil | Seuil |
|---|---|
| `entity_strict` | 0.80 |
| `term_balanced` | 0.75 |
| `term_recall` | 0.70 |

---

## 9. Stratégies d'exécution

### 9.1 Full (défaut)

Pipeline complet : spaCy + patterns + lemmes + filtrage qualité.

### 9.2 Fast

Matching exact par regex compilées, sans spaCy. Chaque match peut contenir `"ambiguous": true`.

```bash
python3 src/loterre_cli.py --execution-strategy fast --dict-id P66_en --text ...
```

### 9.3 Hybrid

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

### 9.4 Multiprocessing

```bash
python3 src/loterre_cli.py --dict-id P66_en --text ... --workers 4
```

---

## 10. Auto-profiling

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

## 11. Gold standard — corpus d'évaluation

### 11.1 Structure des fichiers gold

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

### 11.2 Vocabulaires disponibles (anglais)

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

### 11.3 Vocabulaires disponibles (français)

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

### 11.4 Qualité des ARKs — corrections appliquées (corpus anglais)

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

### 11.5 Logique de comparaison gold/prédictions

Le renderer et le benchmark utilisent une comparaison **par libellé préféré** (`pref`), indépendante de la position exacte. Cette approche est nécessaire car les offsets de position du gold pour les documents 1+ sont systématiquement décalés par rapport au texte réel (conséquence de la génération avec une version différente du texte).

**Algorithme** (`loterre_html_renderer.py`) :
1. `ann_key(m)` retourne `pref.lower()` — clé de comparaison indépendante de la position et du format d'ARK
2. `ann_span(m, text)` valide `text[start:end] == found` avant d'utiliser la position ; si la position est incorrecte, recherche la surface form dans le texte
3. `classify()` groupe les matches par `pref` et apparie la i-ème occurrence attendue avec la i-ème occurrence prédite (trié par position) — gère correctement les occurrences multiples du même concept
4. `counts()` utilise `Counter` pour un comptage par occurrence (pas par concept unique)

**Conséquence** : un terme prédit au bon endroit mais avec un ARK plus récent (alphananumérique) est correctement reconnu comme correspondant au terme attendu avec l'ancien ARK.

---

## 12. Rendu HTML — visualisation et comparaison

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

## 13. Benchmark : moteur local vs API production

### 13.1 API production ISTEX

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

### 13.2 Évaluation de l'API seule

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

### 13.3 Benchmark complet (recommandé)

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
  local/json/P66_en.json     ← prédictions moteur local v9
  local/html/P66_en.html     ← HTML local v9 vs gold
  api/json/P66_en.json       ← prédictions API production
  api/html/P66_en.html       ← HTML API vs gold
  summary.tsv                ← tableau comparatif (tabulation)
  summary.html               ← tableau comparatif interactif
```

### 13.4 Résultats de référence (juin 2026)

Évaluation sur le corpus gold complet (9 vocabulaires anglais) :

| Vocab | API R% | API F1% | v9 R% | v9 F1% | ΔF1 |
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

---

## 14. Performance

### 14.1 Throughput mesuré (WSL2, développement)

| Vocabulaire | Profil | Temps | Docs | docs/s |
|---|---|---|---|---|
| B9M_en | term_recall | 1.9s | 10 | 3.0 |
| 27X_en | term_recall | 1.2s | 11 | 2.3 |
| P66_en | term_recall | 7.1s | 11 | 0.8 |
| 9SD_en | entity_strict | 1.6s | 10 | 0.3 |
| BVM_en | term_recall | 22.9s | 10 | 0.2 |

### 14.2 Optimisations implémentées

| Optimisation | Gain mesuré |
|---|---|
| Pré-compilation de `_PUNCT_RE` | −8s sur P66_en |
| Pré-calcul de `spec._norm_lemma` | −5s |
| LRU cache sur `normalize_text` (99.9% hit rate) | −60% des appels |
| Index patterns par premier token normalisé | ×2 à ×73 selon le vocabulaire |

**Cumul** : P66_en 33s → 7s (×4.7), 9SD_en 117s → 1.6s (×73), 27X_en 16s → 1.2s (×13)

---

## 15. Tests et workflow de développement

### 15.1 Commandes Makefile

```bash
make install          # pip install -r requirements.txt
make models           # télécharge en_core_web_sm + fr_core_news_sm

make test             # smoke + profiling + quality (les 3 suites)
make test-smoke       # 13 smoke tests CLI (EN + FR)
make test-non-regression  # non-régression P66_en complète
make test-profiling   # auto-profiling sur tous les vocabulaires EN + FR
make test-quality     # filtrage contextuel (discourse guard, stopwords)
make test-api         # appel API production ISTEX (nécessite réseau)

make benchmark                           # benchmark local v9 vs API, tous vocabs
make benchmark BENCHMARK_ARGS="--skip-api"         # local uniquement
make benchmark BENCHMARK_ARGS="--vocabs P66_en,9SD_en"  # sous-ensemble

make html             # génère les HTML annotés pour tous les corpus

make clean            # supprime tous les répertoires de sortie générés
make tree             # affiche l'arborescence du projet (profondeur 4)
```

### 15.2 Lancer les tests directement

```bash
# Smoke tests EN + FR (13 tests au total)
bash tests/smoke/test_v9_cli.sh

# Non-régression P66_en
bash tests/smoke/test_p66_non_regression.sh

# HTML local v9 vs gold (tous vocabulaires EN + FR auto-découverts)
bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py data/jsonl ./html_outputs ./src/loterre_html_renderer.py

# Benchmark local v9 vs API production (EN + FR)
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

### 15.3 Options du benchmark

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

### 15.4 Workflow de développement d'un nouveau vocabulaire

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

### 15.5 Registry

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

### 15.6 Différence scripts / tests

- `scripts/` : outils de production pour annoter, évaluer, benchmarker
- `tests/` : vérifications automatiques de non-régression et de qualité

---

## 16. Build et déploiement du package

Le répertoire `production/` (gitignored, non versionné) contient les outils de packaging et de release. Il n'est **jamais poussé** dans le dépôt Git du projet.

### 16.1 Contenu de `production/`

| Fichier | Rôle |
|---|---|
| `version.txt` | Numéro de version sémantique (`MAJOR.MINOR.PATCH`) — à incrémenter avant chaque release |
| `setup.py` | Configuration du package Python (`loterre-annotate`) |
| `build_push_package.sh` | Script de build, publication Git, DVC optionnel |

### 16.2 Prérequis

**Toujours requis :**
```bash
# Clé SSH pour GitHub
ssh-add ~/.ssh/id_rsa
ssh -T git@github.com   # doit afficher "Hi stephane54!"
```

**Requis uniquement avec `--dvc` :**
```bash
pip install dvc

# Configurer un remote DVC (S3, SSH, Google Drive, NFS…)
dvc remote add -d myremote s3://mon-bucket/loterre-dvc
# ou via SSH :
dvc remote add -d myremote ssh://serveur/chemin/dvc-store
```

### 16.3 Workflow de release

```
1. Mettre à jour production/version.txt  (ex: 0.9.1)
2. Valider le code (tests + benchmark)
3. Lancer le script :

   bash production/build_push_package.sh                    # build + push Git
   bash production/build_push_package.sh --dvc              # + push dictionnaires DVC
   bash production/build_push_package.sh --deploy           # + install local
   bash production/build_push_package.sh --dvc --deploy     # tout
```

### 16.4 Ce que fait le script

**Étape 0 — Tests smoke pré-build** *(toujours)*

```bash
make test-smoke
```
Le build est interrompu si un test échoue.

**Étape 1 — DVC : push des dictionnaires** *(avec `--dvc` seulement)*

```bash
# Initialise DVC si c'est la première fois
dvc init && git commit -m "chore: init DVC"

# Ajoute dictionary/ sous contrôle DVC (crée dictionary.dvc)
dvc add dictionary/
git add dictionary.dvc .gitignore
git commit -m "chore: add dictionary/ to DVC"

# Pousse les données vers le remote DVC configuré
dvc commit -f && dvc push
```

Le répertoire `dictionary/` est ainsi stocké séparément du code (stockage DVC) mais la référence `dictionary.dvc` est versionnée dans Git. Sans `--dvc`, cette étape est ignorée — utile pour un release purement code sans modifier les dictionnaires.

**Étape 2 — Build wheel + push Git** *(toujours)*

```bash
# Construit la distribution binaire
python3 production/setup.py bdist_wheel
# → dist/loterre_annotate-{version}-py3-none-any.whl

# Commit, tag et push
git commit -m "release: loterre-annotate v{version}"
git tag v{version}
git push origin HEAD
git push origin v{version} --force
```

**Étape 3 — Installation locale** *(avec `--deploy` seulement)*

```bash
pip install --force-reinstall dist/loterre_annotate-{version}-*.whl
```

Commandes installées après `--deploy` :

| Commande | Module | Description |
|---|---|---|
| `loterre-annotate` | `loterre_cli` | Lanceur principal (avec registry) |
| `loterre-engine` | `loterre_engine_v9_cli` | Moteur v9 direct |
| `loterre-benchmark` | `loterre_benchmark` | Benchmark 3 moteurs |
| `loterre-render` | `loterre_html_renderer` | Rendu HTML |

### 16.5 Package `loterre-annotate` — structure

Le `setup.py` installe les modules depuis `src/` via `package_dir={"": "src"}`.

**Inclus dans la distribution :**
- Modules Python : `loterre_cli`, `loterre_engine_v9_cli`, `loterre_fast_path`, `loterre_html_renderer`, `loterre_api_eval`, `loterre_benchmark`
- Données : `resources/en/weak_words.txt`, `resources/fr/weak_words.txt`, `resources/spacy_models.yaml`, `configs/registry.yaml`

**Exclus de la distribution :**
- `dictionary/` — trop volumineux, géré par DVC ; à récupérer séparément via `dvc pull`
- `data/jsonl/` — corpus de test, non requis à l'exécution

### 16.6 Récupérer les dictionnaires (après clone ou install)

```bash
# Après git clone du projet :
dvc pull          # télécharge dictionary/ depuis le remote DVC

# Ou pour un vocabulaire précis :
dvc pull dictionary/en_annot_P66.jsonl
```
