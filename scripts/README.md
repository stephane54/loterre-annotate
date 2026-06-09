# Scripts

Outils de production pour annoter, évaluer et benchmarker.

## Structure

```
scripts/
├── evaluation/
│   ├── evaluate_json.py               # calcul Précision / Rappel / F1
│   ├── run_eval.sh                    # évaluation batch EN + FR
│   ├── run_generated_eval.sh          # évaluation sur gold auto-générés
│   └── clean_gold.py                 # nettoyage et correction des ARKs gold
├── prediction/
│   ├── generate_gold_from_predictions.py   # bootstrap gold depuis prédictions moteur
│   ├── results_to_expected_jsonl.py         # convertit pred JSON → expected JSONL
│   └── bulk_results_to_expected.sh          # conversion batch d'un répertoire
├── profiling/
│   └── run_profile_generation.sh      # génère tous les auto-profiles YAML
├── benchmark/
│   ├── run_benchmark.sh               # benchmark rapide local vs API
│   └── benchmark_fast_path.sh         # benchmark du fast path (regex) uniquement
└── generate_fr_corpus.py              # génération des corpus FR avec variants flexionnels
```

> **Note** : le benchmark principal (moteur local vs API production, EN + FR) est dans
> `tests/smoke/compare_engines.sh` → `src/loterre_benchmark.py`.
> Voir `tests/README.md` pour les détails.

---

## evaluation/

### `evaluate_json.py`

Calcule Précision, Rappel et F1 en comparant un fichier de prédictions à un gold.

```bash
python3 scripts/evaluation/evaluate_json.py \
  --gold gold_cleaned/gold_P66_en.jsonl \
  --pred eval_outputs/P66_en_pred.json \
  --out-json eval_outputs/P66_en_eval.json
```

### `run_eval.sh`

Évaluation batch sur tous les vocabulaires EN (P66, 9SD) et FR (P66_fr … QX8_fr).
Produit les fichiers `*_pred.json` et `*_eval.json` dans `eval_outputs/`.

```bash
bash scripts/evaluation/run_eval.sh
# ou avec CLI et répertoire personnalisés :
bash scripts/evaluation/run_eval.sh src/loterre_cli.py eval_outputs/
```

### `clean_gold.py`

Nettoie les gold auto-générés : corrige les ARKs obsolètes (format numérique → alphanumérique)
par correspondance sur le libellé préféré, et supprime les termes absents du vocabulaire courant.

---

## prediction/

### `generate_gold_from_predictions.py`

Bootstrap d'un gold standard depuis les prédictions du moteur.
Lit le registry, annote tous les corpus disponibles, et génère des fichiers JSONL
avec `expected_matches` prêts à la révision manuelle.

```bash
python3 scripts/prediction/generate_gold_from_predictions.py \
  --engine src/loterre_cli.py \
  --text-root data/jsonl \
  --out-dir predictions
```

### `results_to_expected_jsonl.py`

Convertit un fichier de prédictions JSON (`matches`) en fichier JSONL avec `expected_matches`.
Utilisé notamment par `test_p66_non_regression.sh`.

```bash
python3 scripts/prediction/results_to_expected_jsonl.py \
  --input predictions/P66_en.pred.json \
  --out   predictions/P66_en.expected.jsonl
```

### `bulk_results_to_expected.sh`

Applique `results_to_expected_jsonl.py` à tous les fichiers JSON d'un répertoire.

```bash
bash scripts/prediction/bulk_results_to_expected.sh predictions/ gold_bootstrap/
```

---

## profiling/

### `run_profile_generation.sh`

Génère les fichiers YAML auto-profile pour tous les vocabulaires EN et FR
et les écrit dans `configs/`.

```bash
bash scripts/profiling/run_profile_generation.sh
```

---

## benchmark/

### `run_benchmark.sh`

Benchmark rapide : annote les corpus EN et FR avec le moteur local et stocke
les prédictions dans `predictions/`.

### `benchmark_fast_path.sh`

Benchmark dédié au fast path (regex sans spaCy) — mesure la vitesse et
compare les résultats avec le moteur complet.

---

## `generate_fr_corpus.py`

Génère les corpus de test français `data/jsonl/*_fr.jsonl` avec des variants flexionnels
(pluriels, féminins, formes en -aux) calculés depuis les dictionnaires FR.

```bash
python3 scripts/generate_fr_corpus.py
# Produit : data/jsonl/{P66,27X,9SD,8HQ,B9M,BVM,QX8}_fr.jsonl
```
