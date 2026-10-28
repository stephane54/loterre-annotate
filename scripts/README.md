# Scripts

Outils de production pour annoter, évaluer et benchmarker.

## Structure

```
scripts/
├── corpus/
│   ├── txt_to_jsonl.py                # convertit .txt (fichier ou dossier) en JSONL pour extract/annotate
│   └── clean_revueesr.py              # nettoie le corpus RevueESR (texte PDF) : césures, ligatures, accents, paratexte
├── evaluation/
│   ├── evaluate_json.py               # calcul Précision / Rappel / F1
│   ├── run_eval.sh                    # évaluation batch EN + FR
│   ├── run_generated_eval.sh          # évaluation sur gold auto-générés
│   ├── clean_gold.py                 # nettoyage et correction des ARKs gold
│   ├── acter_eval.py                  # extraction : benchmark token-level vs gold ACTER (make benchmark-acter)
│   ├── bench_candidate_patterns.py    # extraction : grammaire de candidats étendue vs ACTER
│   ├── bench_specificity.py           # extraction : signal de spécificité vs ACTER
│   ├── bench_topical.py               # extraction : signaux de répartition vs témoin fréquence (rejetés)
│   ├── build_report.py                # rapport --report depuis des sorties existantes
│   ├── sweep_topics.py                # rapport : balayage du nombre de thèmes
│   ├── bench_respot.py                # extraction : effet du repérage de toutes les occurrences
│   └── termsuite_acter_eval.py        # extraction : sorties TermSuite notées avec le protocole d'acter_eval
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

## corpus/

### `txt_to_jsonl.py`

Convertit un fichier `.txt`, un répertoire de `.txt`, ou une archive
`.tar.gz`/`.tgz`/`.tar` contenant des `.txt`, en JSONL `{"id":..., "value":...}`
— le format attendu par les sous-commandes `annotate`/`extract`/`extract_annotate`
de `src/loterre_cli.py`. L'archive est lue directement en mémoire (rien n'est
extrait sur disque).

```bash
python3 scripts/corpus/txt_to_jsonl.py mon_texte.txt --out mon_texte.jsonl
python3 scripts/corpus/txt_to_jsonl.py mes_textes/ --out corpus.jsonl       # un doc par .txt du dossier
python3 scripts/corpus/txt_to_jsonl.py mes_textes.tar.gz --out corpus.jsonl # un doc par .txt de l'archive
python3 scripts/corpus/txt_to_jsonl.py mon_texte.txt                         # affiche sur stdout
```

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

### `acter_eval.py` (extraction)

Benchmark token-level contre le gold ACTER (`make corpus-acter` d'abord) : `ncvalue` et
`graph` à froid (coupure top-N = nombre de termes gold uniques), puis `embed` semi-supervisé
(la moitié des termes gold sert de vocabulaire) et les listes de production 1 et 1+2.
Résultats de référence : `docs/evaluation.md` §1.

```bash
make benchmark-acter                                    # tout, dans benchmark_results/acter/
python3 scripts/evaluation/acter_eval.py --min-freq 1 --skip-embed-seeded --skip-structural-signal \
  --out-dir benchmark_results/acter_cold                # à froid seulement
python3 scripts/evaluation/acter_eval.py --min-freq 1 --skip-cold \
  --out-dir benchmark_results/acter_embed               # embed seulement (Markdown omis sans résultats à froid)
python3 scripts/evaluation/acter_eval.py --min-freq 1 --respot-occurrences \
  --out-dir benchmark_results/respot/acter_respot       # tout, avec --respot-occurrences à chaque extraction
```

### `bench_respot.py` (extraction)

Test de l'hypothèse « occurrences » (2026-10-09) : garde exactement les candidats, le
classement et la coupure d'`acter_eval.py`, et compare la notation avec les occurrences
extraites et avec toutes les occurrences du texte du candidat (ncvalue/graph à froid,
listes embed 1 et 1+2). A montré que l'avance de TermSuite venait surtout de là ;
la correction est désormais l'option `--respot-occurrences` de l'extraction.

```bash
python3 scripts/evaluation/bench_respot.py --out benchmark_results/respot/respot_results.json
```

### `termsuite_acter_eval.py` (extraction)

Note des sorties TermSuite (`--json`, un fichier `acter_<domaine>_<langue>.json` par corpus,
produit sur `corpus_acter/<langue>/<domaine>/annotated/texts`) avec les fonctions
d'`acter_eval.py`. Les occurrences TermSuite sont prises à leurs positions exportées.
`--compare` ajoute ncvalue/graph (sortie d'`acter_eval.py` à froid) ; `--seeded-compare`
note TermSuite selon le protocole embed (même coupure, puis même nombre de suggestions
que les listes 1 et 1+2).

```bash
python3 scripts/evaluation/termsuite_acter_eval.py \
  --termsuite-dir benchmark_results/termsuite/outputs_v2 \
  --compare benchmark_results/termsuite/acter_cold/acter_results.json \
  --out benchmark_results/termsuite/termsuite_acter_results
python3 scripts/evaluation/termsuite_acter_eval.py \
  --termsuite-dir benchmark_results/termsuite/outputs_v2 \
  --seeded-compare benchmark_results/termsuite/acter_embed \
  --out benchmark_results/termsuite/termsuite_vs_embed
```

### `build_report.py` (rapport)

Produit le rapport `--report` (HTML + JSON, CSV enrichi en option) à partir d'une sortie
`extract_annotate` et des annotations du même corpus, sans relancer l'extraction ; ou
regénère seulement la page HTML depuis le JSON d'un rapport.

```bash
python3 scripts/evaluation/build_report.py \
  --input output_extract/RevueESR_clean3_extract_annotate.json \
  --annotations output_extract/RevueESR_clean3_annotate_SEN.json \
  --text data/RevueESR-textFR.clean.json \
  --output output_extract/RevueESR_clean3_report.html \
  --out-csv output_extract/RevueESR_clean3_candidats.csv
python3 scripts/evaluation/build_report.py --from-report output_extract/RevueESR_clean3_report.json \
  --output output_extract/RevueESR_clean3_report.html
```

### `sweep_topics.py` (rapport)

Fait varier le nombre de thèmes du rapport et mesure, pour chaque valeur, la cohérence
des étiquettes (NPMI), la stabilité (sous-échantillons de 80 % des segments), les thèmes
génériques et le classement de couverture. Même entrées que `build_report.py`.

```bash
python3 scripts/evaluation/sweep_topics.py "$PWD" \
  output_extract/RevueESR_clean3_extract_annotate.json \
  output_extract/RevueESR_clean3_annotate_SEN.json \
  benchmark_results/topical/RevueESR_sweep_n_topics.json 10,15,20,25,30,40,50
```

`bench_candidate_patterns.py`, `bench_specificity.py` et `bench_topical.py` sont les
scripts des benchmarks du même nom dans `planification/analyse_benchmarks_extraction.md`.

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
