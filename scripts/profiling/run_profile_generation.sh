#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CLI="${1:-$REPO_ROOT/src/loterre_cli.py}"
DICT_ID="${2:-P66_en}"
TEXT_PATH="${3:-../examples/texts/P66_en.jsonl}"
OUTDIR="${4:-$REPO_ROOT/profile_outputs}"

mkdir -p "$OUTDIR"

python "$CLI" \
  --dict-id "$DICT_ID" \
  --text "$TEXT_PATH" \
  --auto-profile \
  --yaml-out "$OUTDIR/${DICT_ID}.yaml" \
  > "$OUTDIR/${DICT_ID}.json"

echo "Generated:"
echo "  $OUTDIR/${DICT_ID}.yaml"
echo "  $OUTDIR/${DICT_ID}.json"
