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

### 1. Générer une configuration

```bash
bash scripts/profiling/run_profile_generation.sh   ./src/loterre_cli.py   P66_en   ../examples/texts/P66_en.jsonl   ./profile_outputs
```

### 2. Générer les prédictions/golds avec un manifest

```bash
python scripts/prediction/generate_gold_from_predictions.py   --engine ./src/loterre_cli.py   --manifest manifest.json   --outdir .
```

### 3. Évaluer en batch

```bash
bash scripts/evaluation/run_generated_eval.sh   ./scripts/evaluation/evaluate_json.py   ./eval_outputs
```

### 4. Benchmarker deux versions

```bash
bash scripts/benchmark/run_benchmark.sh   /path/to/old/src/loterre_cli.py   ./src/loterre_cli.py   .
```

### 5. Lancer les tests

```bash
bash tests/smoke/test_v9_cli.sh
bash tests/profiling/test_auto_profile_quality.sh
bash tests/quality/test_v9_contextual.sh
```

## Différence scripts / tests

- `scripts/` : outils de travail pour produire, évaluer, benchmarker.
- `tests/` : vérifications automatiques de non-régression.
