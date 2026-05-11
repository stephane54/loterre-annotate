# Loterre v9 — Repo organisé

## Organisation proposée

```text
loterre-v9/
├── src/
│   ├── loterre_engine_v9_cli.py
│   └── loterre_cli.py
│
├── configs/
│   ├── registry.yaml
│   └── examples/
│
├── scripts/
│   ├── profiling/
│   │   └── run_profile_generation.sh
│   ├── prediction/
│   │   └── generate_gold_from_predictions.py
│   ├── evaluation/
│   │   ├── evaluate_json.py
│   │   ├── run_eval.sh
│   │   └── run_generated_eval.sh
│   └── benchmark/
│       └── run_benchmark.sh
│
├── tests/
│   ├── smoke/
│   │   ├── test_annotate_cli.sh
│   │   └── test_v9_cli.sh
│   ├── profiling/
│   │   └── test_auto_profile_quality.sh
│   └── quality/
│       └── test_v9_contextual.sh
│
├── gold/
├── predictions/
├── eval_outputs/
└── README.md
```

## Rôle de chaque dossier

### `src/`
Code principal :
- `loterre_engine_v9_cli.py` : moteur
- `loterre_cli.py` : lanceur CLI avec `--dict-id`

### `configs/`
Configuration :
- `registry.yaml` : dictionnaires disponibles
- `examples/` : exemples de YAML

### `scripts/profiling/`
Génération automatique de profils/YAML.

### `scripts/prediction/`
Génération des prédictions et des golds bootstrap.

### `scripts/evaluation/`
Évaluation qualité :
- TP / FP / FN
- précision
- rappel
- F1

### `scripts/benchmark/`
Comparaison entre deux versions du moteur.

### `tests/smoke/`
Tests rapides du CLI.

### `tests/profiling/`
Tests de génération automatique des profils.

### `tests/quality/`
Tests qualité/contextuels.

## Workflow recommandé

NB : A lancer depuis REPO_ROOT

Prérequis runtime :
- Python 3 (`python3`)
- Dépendances installées (`pip install -r requirements.txt`)
- Modèles spaCy pour EN/FR si vous lancez le moteur complet
  - ex: `python3 -m spacy download en_core_web_sm`
  - ex: `python3 -m spacy download fr_core_news_sm`

### 1. Générer les configurations (auto-profile)

```bash
bash scripts/profiling/run_profile_generation.sh ./src/loterre_cli.py P66_en examples/texts/P66_en.jsonl ./profile_outputs
```


Toutes les configs :
```bash
./scripts/profiling/run_profile_generation.sh
```
Résultat : génération des fichiers `*_auto_profile.json` dans `configs/`.

### 2. Générer les prédictions/golds

Avec manifest :
 ```bash
python3 scripts/prediction/generate_gold_from_predictions_v0.py --engine ./src/loterre_cli.py
```
avec registry.yaml : 

```bash
python3 scripts/prediction/generate_gold_from_predictions.py --engine ./src/loterre_cli.py --text-root examples/texts
```

Résultat : génération de fichiers de prédiction et de gold bootstrap.

Conversion simple de résultats déjà produits vers `expected_matches` :
```bash
python3 scripts/prediction/results_to_expected_jsonl.py --input outputs_tests_v8_1_cli/p66_api.json --out /tmp/p66_expected.jsonl
```
Batch sur un dossier :
```bash
bash scripts/prediction/bulk_results_to_expected.sh outputs_tests_v8_1_cli /tmp/expected_bulk
```


### 3. Évaluer en batch

```bash
./scripts/evaluation/run_generated_eval.sh ./scripts/evaluation/evaluate_json.py ./outputs_eval
```

### 4. Benchmarker deux versions [NON TESTE]

```bash
./scripts/benchmark/run_benchmark.sh   /path/to/old/src/loterre_cli.py   ./src/loterre_cli.py   .
```

### 5. Lancer les tests

```bash
./tests/smoke/test_v9_cli.sh
./tests/smoke/test_annotate_cli.sh
./tests/profiling/test_auto_profile_quality.sh
./tests/quality/test_v9_contextual.sh
./tests/smoke/test_p66_non_regression.sh
```

## Différence scripts / tests

- `scripts/` : outils de travail pour produire, évaluer, benchmarker.
- `tests/` : vérifications automatiques de non-régression.



# TODO

## BUG


## EVOL/MODIF

Pb de tepps sur gros dico : : ex :JVR
