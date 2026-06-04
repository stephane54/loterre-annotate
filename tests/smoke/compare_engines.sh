#!/usr/bin/env bash
# compare_engines.sh — benchmark local Dev v9 vs API production on gold corpus
#
# Découvre automatiquement tous les fichiers JSONL dans TEXT_ROOT,
# y compris les corpus français (*_fr.jsonl).
#
# Usage:
#   bash tests/smoke/compare_engines.sh [OPTIONS]
#
# Options (all optional, defaults shown):
#   --text-root  DIR    Gold JSONL directory     (default: data/texts)
#   --out-dir    DIR    Output directory          (default: benchmark_results)
#   --cli        FILE   loterre_cli.py path       (default: src/loterre_cli.py)
#   --renderer   FILE   loterre_html_renderer.py  (default: src/loterre_html_renderer.py)
#   --vocabs     LIST   Comma-separated codes     (default: all)
#   --skip-local        Skip local v9 engine
#   --skip-api          Skip API calls
#   --batch-size N      Docs per API call         (default: 4)
#   --api-url    URL    API endpoint URL
#
# Examples:
#   # Benchmark complet (EN + FR)
#   bash tests/smoke/compare_engines.sh
#
#   # Uniquement les corpus français, sans API
#   bash tests/smoke/compare_engines.sh --vocabs P66_fr,27X_fr,B9M_fr,QX8_fr --skip-api
#
#   # Benchmark EN seulement
#   bash tests/smoke/compare_engines.sh --vocabs P66_en,9SD_en,27X_en,8HQ_en,B9M_en,BVM_en,QX8_en,3JP_en,JVR_en
#
#   # Benchmark FR seulement, moteur local uniquement
#   bash tests/smoke/compare_engines.sh \
#     --vocabs P66_fr,27X_fr,9SD_fr,8HQ_fr,B9M_fr,BVM_fr,QX8_fr \
#     --skip-api \
#     --out-dir benchmark_fr
#
#   # Custom output dir daté
#   bash tests/smoke/compare_engines.sh --out-dir results/$(date +%Y%m%d)
#
# Note API FR :
#   L'API production ISTEX (endpoint /v1/en/...) peut ne pas supporter les
#   vocabulaires FR. Utilisez --skip-api pour les runs FR locaux uniquement.
#   Pour un endpoint FR hypothétique, surcharger --api-url si nécessaire.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 "$PROJECT_DIR/src/loterre_benchmark.py" \
    --text-root  "${TEXT_ROOT:-$PROJECT_DIR/data/texts}" \
    --out-dir    "${OUT_DIR:-$PROJECT_DIR/benchmark_results}" \
    --cli        "${CLI:-$PROJECT_DIR/src/loterre_cli.py}" \
    --renderer   "${RENDERER:-$PROJECT_DIR/src/loterre_html_renderer.py}" \
    "$@"
