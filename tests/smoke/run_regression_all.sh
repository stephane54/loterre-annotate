#!/usr/bin/env bash
# Lance la suite de smoke tests v2.0 (extraction) en une fois, avec un résumé final.
# Usage : source venv (sentence-transformers requis pour test_embed) puis bash tests/smoke/run_regression_all.sh

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FAILS=()
for t in test_extract_cli test_cvalue test_positionrank test_extract_annotate_cli test_embed test_variants; do
  echo "=== $t ==="
  if bash "$SCRIPT_DIR/$t.sh"; then
    echo "--- PASS $t ---"
  else
    echo "--- FAIL $t ---"
    FAILS+=("$t")
  fi
  echo
done

echo "===================="
if [ ${#FAILS[@]} -eq 0 ]; then
  echo "SUCCESS: tous les tests sont passés"
else
  echo "ECHEC: ${FAILS[*]}"
  exit 1
fi
