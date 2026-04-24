#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs_autoprofile_quality}"

mkdir -p "$OUTDIR"

echo "== Auto-profile P66 =="
python "$CLI" \
  --text ../examples/texts/P66_en.jsonl \
  --dict-id P66_en \
  --auto-profile \
  --yaml-out "$OUTDIR/p66.yaml" \
  > "$OUTDIR/p66.json"

echo
echo "== Auto-profile 9SD =="
python "$CLI" \
  --text ../examples/texts/9SD_en.jsonl \
  --dict-id 9SD_en \
  --auto-profile \
  --yaml-out "$OUTDIR/9sd.yaml" \
  > "$OUTDIR/9sd.json"

echo
echo "Generated proposals in $OUTDIR"
