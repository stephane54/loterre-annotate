#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CLI="${1:-$REPO_ROOT/src/loterre_cli.py}"
OUTDIR="${2:-$REPO_ROOT/eval_outputs}"
EVAL_PY="$REPO_ROOT/scripts/evaluation/evaluate_json.py"

mkdir -p "$OUTDIR"

cd "$REPO_ROOT"

echo "== P66 evaluation =="
python3 "$CLI" --text ./examples/texts/P66_en.jsonl --dict-id P66_en --silent > "$OUTDIR/p66_pred.json"
python3 "$EVAL_PY" --gold ./gold_cleaned/gold_P66_en.jsonl --pred "$OUTDIR/p66_pred.json" --out-json "$OUTDIR/p66_eval.json"

echo
echo "== 9SD evaluation =="
python3 "$CLI" --text ./examples/texts/9SD_en.jsonl --dict-id 9SD_en --silent > "$OUTDIR/9sd_pred.json"
python3 "$EVAL_PY" --gold ./gold_cleaned/gold_9SD_en.jsonl --pred "$OUTDIR/9sd_pred.json" --out-json "$OUTDIR/9sd_eval.json"

echo
echo "Evaluation outputs written to $OUTDIR"
