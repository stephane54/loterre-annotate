#!/usr/bin/env bash
set -euo pipefail

CLI="${1:-./src/loterre_cli.py}"
FAST="${2:-./src/loterre_fast_path.py}"
TEXT="${3:-data/texts/P66_en.jsonl}"
DICT="${4:-data/dicts/en_annot_P66.jsonl}"
DICT_ID="${5:-P66_en}"
OUTDIR="${6:-./bench_outputs}"

mkdir -p "$OUTDIR"

echo "== Standard v9 =="
time python "$CLI" --dict-id "$DICT_ID" --text "$TEXT" --silent > "$OUTDIR/${DICT_ID}.v9.json"

echo
echo "== Fast path =="
time python "$FAST" --text "$TEXT" --dict "$DICT" --out "$OUTDIR/${DICT_ID}.fast.json" --cache-dir "$OUTDIR/cache"

echo
echo "Outputs:"
echo "  $OUTDIR/${DICT_ID}.v9.json"
echo "  $OUTDIR/${DICT_ID}.fast.json"
