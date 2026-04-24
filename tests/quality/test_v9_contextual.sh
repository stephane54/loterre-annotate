#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs_v9_contextual}"

mkdir -p "$OUTDIR"

echo "== Test 1: discourse/context guard with well =="
printf '%s\n' '{"id":"ctx1","value":"The word Parthenon comes from the Greek parthénos as well as other forms."}' | python "$CLI" \
  --dict-id 9SD_en \
  --silent > "$OUTDIR/well_context.json"

echo
echo "== Test 2: weak function words =="
printf '%s\n' '{"id":"ctx2","value":"and or it are only function words here."}' | python "$CLI" \
  --dict-id 9SD_en \
  --silent > "$OUTDIR/function_words.json"

echo
echo "== Test 3: lexical entity context =="
printf '%s\n' '{"id":"ctx3","value":"Italy and Rome are mentioned here."}' | python "$CLI" \
  --dict-id 9SD_en \
  --silent > "$OUTDIR/entity_context.json"

echo
echo "Outputs in $OUTDIR"
