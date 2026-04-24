#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

EVAL="${1:-$REPO_ROOT/scripts/evaluation/evaluate_json.py}"
OUTDIR="${2:-$REPO_ROOT/eval_outputs}"

mkdir -p "$OUTDIR"

cd "$REPO_ROOT"

for gold in ./gold/*.jsonl; do
  [[ -e "$gold" ]] || continue
  name=$(basename "$gold" .jsonl)
  pred_name="${name#gold_}.pred.json"
  pred="./predictions/$pred_name"

  if [[ -f "$pred" ]]; then
    echo "== Evaluating $name =="
    python "$EVAL" \
      --gold "$gold" \
      --pred "$pred" \
      --out-json "$OUTDIR/$name.eval.json" \
      --out-csv "$OUTDIR/$name.eval.csv" \
      --out-md "$OUTDIR/$name.eval.md" \
      > "$OUTDIR/$name.stdout.json"
  else
    echo "No prediction found for $gold"
  fi
done
