#!/usr/bin/env bash
set -euo pipefail

CLI="${1:-../.../../../src/loterre_cli.py}"
OUTDIR="${2:-./eval_outputs}"

mkdir -p "$OUTDIR"

echo "== P66 evaluation =="
python "$CLI"   --text ./gold/texts_p66_en.jsonl   --dict-id P66_en   --silent   > "$OUTDIR/p66_pred.json"
python ../../scripts/evaluation/evaluate_json.py   --gold ./gold/gold_p66_en.jsonl   --pred "$OUTDIR/p66_pred.json"   --out-json "$OUTDIR/p66_eval.json"

echo
echo "== 9SD evaluation =="
python "$CLI"   --text ./gold/texts_9sd_en.jsonl   --dict-id 9SD_en   --silent   > "$OUTDIR/9sd_pred.json"
python ../../scripts/evaluation/evaluate_json.py   --gold ./gold/gold_9sd_en.jsonl   --pred "$OUTDIR/9sd_pred.json"   --out-json "$OUTDIR/9sd_eval.json"

echo
echo "Evaluation outputs written to $OUTDIR"
