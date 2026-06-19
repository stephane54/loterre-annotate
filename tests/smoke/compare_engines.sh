#!/usr/bin/env bash
# compare_engines.sh — benchmark local Dev v9 vs deux APIs de production
#
# Trois moteurs comparés :
#   - local      : moteur v9 local
#   - api        : Loterre Terms-Matcher (terms-tools.services.istex.fr)
#   - resolvers  : Loterre Resolvers    (loterre-resolvers.services.istex.fr)
#
# Usage:
#   bash tests/smoke/compare_engines.sh [OPTIONS]
#
# Options (all optional, defaults shown):
#   --text-root      DIR    Gold JSONL directory      (default: data/jsonl)
#   --out-dir        DIR    Output directory           (default: benchmark_results/<horodatage>_<moteurs>)
#   --cli            FILE   loterre_cli.py path        (default: src/loterre_cli.py)
#   --renderer       FILE   loterre_html_renderer.py   (default: src/loterre_html_renderer.py)
#   --vocabs         LIST   Comma-separated codes      (default: all)
#   --skip-local            Skip local v9 engine
#   --skip-api              Skip Terms-Matcher API
#   --skip-resolvers        Skip Loterre Resolvers API
#   --batch-size N          Docs per API call          (default: 4)
#   --api-url        URL    Terms-Matcher endpoint URL
#   --resolvers-url  URL    Resolvers endpoint URL
#
# Examples:
#   # Benchmark complet (EN + FR), 3 moteurs
#   bash tests/smoke/compare_engines.sh
#
#   # Local uniquement (pas d'appels réseau)
#   bash tests/smoke/compare_engines.sh --skip-api --skip-resolvers
#
#   # Benchmark EN seulement, sans resolvers
#   bash tests/smoke/compare_engines.sh \
#     --vocabs P66_en,9SD_en,27X_en,8HQ_en,B9M_en,BVM_en,QX8_en,3JP_en,JVR_en \
#     --skip-resolvers
#
#   # Corpus français, moteur local + resolvers uniquement
#   bash tests/smoke/compare_engines.sh \
#     --vocabs P66_fr,27X_fr,9SD_fr,8HQ_fr,B9M_fr,BVM_fr,QX8_fr \
#     --skip-api \
#     --out-dir benchmark_fr
#
#   # Custom output dir daté
#   bash tests/smoke/compare_engines.sh --out-dir results/$(date +%Y%m%d)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Détermine un suffixe selon les moteurs effectivement comparés, pour que le
# nom du répertoire indique ce qu'il contient (évite de confondre un run
# local-only avec un run complet local+api+resolvers).
ENGINES="local"
case " $* " in
  *" --skip-api "*)       : ;;
  *)                      ENGINES="${ENGINES}_api" ;;
esac
case " $* " in
  *" --skip-resolvers "*) : ;;
  *)                      ENGINES="${ENGINES}_resolvers" ;;
esac

DEFAULT_OUT_DIR="$PROJECT_DIR/benchmark_results/$(date +%Y%m%d_%H%M%S)_${ENGINES}"

# Chaque exécution écrit dans un répertoire neuf et horodaté par défaut —
# évite qu'un summary réutilise des fichiers api/resolvers d'un run précédent
# (loterre_benchmark.py agrège les stats dès que le fichier JSON existe sur
# disque, --skip-api/--skip-resolvers ne sautent que l'appel réseau).
# Surcharge possible via $OUT_DIR ou --out-dir explicite.
python3 "$PROJECT_DIR/src/loterre_benchmark.py" \
    --text-root  "${TEXT_ROOT:-$PROJECT_DIR/data/jsonl}" \
    --out-dir    "${OUT_DIR:-$DEFAULT_OUT_DIR}" \
    --cli        "${CLI:-$PROJECT_DIR/src/loterre_cli.py}" \
    --renderer   "${RENDERER:-$PROJECT_DIR/src/loterre_html_renderer.py}" \
    "$@"
