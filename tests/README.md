# Tests

Organisation des tests automatiques et scripts de validation.

## Structure

```text
tests/
├── smoke/
│   ├── test_v9_cli.sh              # smoke tests CLI (EN + FR)
│   ├── test_p66_non_regression.sh  # non-régression P66_en (4 étapes)
│   ├── test_annotate_cli.sh        # annotation batch via configs YAML
│   ├── render_html_annotation.sh   # HTML locaux v9 vs gold (EN + FR)
│   └── compare_engines.sh          # benchmark local v9 vs API (EN + FR)
├── quality/
│   └── test_v9_contextual.sh       # tests filtrage qualité contextuel
└── profiling/
    └── test_auto_profile_quality.sh # auto-profiling sur tous les vocabulaires
```

## Commandes rapides (Makefile)

```bash
make test                  # smoke + profiling + quality
make test-smoke            # smoke tests CLI (13 tests EN + FR)
make test-non-regression   # non-régression P66_en complète
make test-profiling        # auto-profiling EN + FR
make test-quality          # filtrage contextuel
make test-api              # appel API production ISTEX (réseau requis)
make benchmark             # benchmark local v9 vs API, tous vocabs
make benchmark BENCHMARK_ARGS="--skip-api"         # local uniquement
make benchmark BENCHMARK_ARGS="--vocabs P66_en,9SD_en"
make html                  # génère les HTML annotés pour tous les corpus
```

## Commandes directes

```bash
# Smoke tests complets EN + FR
bash tests/smoke/test_v9_cli.sh

# Non-régression P66_en (prédiction → conversion → HTML → bulk)
bash tests/smoke/test_p66_non_regression.sh

# HTML annotations locales (tous vocabulaires EN et FR)
bash tests/smoke/render_html_annotation.sh \
  ./src/loterre_cli.py data/jsonl ./html_outputs ./src/loterre_html_renderer.py

# Benchmark local v9 vs API production (tous vocabulaires EN + FR auto-découverts)
bash tests/smoke/compare_engines.sh

# Benchmark FR uniquement, local seulement
bash tests/smoke/compare_engines.sh \
  --vocabs P66_fr,27X_fr,9SD_fr,8HQ_fr,B9M_fr,BVM_fr,QX8_fr \
  --skip-api \
  --out-dir benchmark_fr
```

---

## test_v9_cli.sh — détail des 13 tests

| Test | Description | Langue |
|------|-------------|--------|
| 1 | Auto-profile P66_en — génère YAML | EN |
| 2 | Auto-profile 9SD_en avec profil forcé (`entity_strict`) | EN |
| 3 | Annotation P66_en via stdin + `--silent` | EN |
| 4 | Annotation P66_en via fichier + `--api` | EN |
| 5 | Annotation 9SD_en avec fichiers markdown de sortie | EN |
| 6 | Annotation 9SD_en via stdin + `--silent` | EN |
| 7 | Annotation P66_en via config YAML rapide | EN |
| 8 | Anti-bruit EN : `and`/`it` non annotés | EN |
| 9 | Auto-profile P66_fr | **FR** |
| 10 | Annotation P66_fr : variants flexionnels reconnus (found ≠ pref) | **FR** |
| 11 | Annotation B9M_fr (biologie/éthologie) | **FR** |
| 12 | Anti-bruit FR : `et`/`ou`/`il`/`elle` non annotés | **FR** |
| 13 | Annotation QX8_fr (géosciences) | **FR** |

## test_p66_non_regression.sh — 4 étapes

1. **CLI prediction** — génère `P66_en.pred.json` via `--dict-id P66_en --silent`
2. **Conversion** — `results_to_expected_jsonl.py` : pred JSON → expected JSONL
3. **Rendu HTML** — `loterre_html_renderer.py render` avec gold merge ; vérifie termes surlignés + liens
4. **Bulk** — `bulk_results_to_expected.sh` sur un répertoire de prédictions

## compare_engines.sh — options

| Option | Défaut | Description |
|--------|--------|-------------|
| `--text-root DIR` | `data/jsonl` | Répertoire des gold JSONL (EN + FR auto-découverts) |
| `--out-dir DIR` | `benchmark_results` | Répertoire de sortie |
| `--cli FILE` | `src/loterre_cli.py` | CLI du moteur local |
| `--renderer FILE` | `src/loterre_html_renderer.py` | Renderer HTML |
| `--vocabs LIST` | tous | Codes vocabulaires séparés par virgule (ex: `P66_en,P66_fr`) |
| `--skip-local` | — | Ignorer le moteur local |
| `--skip-api` | — | Ignorer l'API production (recommandé pour les runs FR purs) |
| `--batch-size N` | 4 | Documents par appel API |
| `--api-url URL` | ISTEX `/v1/{lang}/...` | Template d'URL (placeholder `{lang}` requis) |

> L'API ISTEX supporte `en` et `fr` via `/v1/en/...` et `/v1/fr/...`.
> La langue est inférée automatiquement depuis le nom du fichier gold
> (`P66_fr.jsonl` → `/v1/fr/...`, `P66_en.jsonl` → `/v1/en/...`).

## Sorties du benchmark

```text
benchmark_results/
  local/json/P66_en.json     ← prédictions moteur local v9
  local/html/P66_en.html     ← HTML local v9 vs gold
  api/json/P66_en.json       ← prédictions API production
  api/html/P66_en.html       ← HTML API vs gold
  summary.tsv                ← tableau comparatif (tabulation)
  summary.html               ← tableau comparatif interactif
```
