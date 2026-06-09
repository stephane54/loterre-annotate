#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <CLI_V8> <CLI_V81> <REPO_ROOT> [OUTDIR]" >&2
  exit 1
fi

CLI_V8="$1"
CLI_V81="$2"
REPO_ROOT="$3"
OUTDIR="${4:-benchmark_outputs}"

mkdir -p "$OUTDIR"

P66_TEXT="$REPO_ROOT/data/jsonl/P66_en.jsonl"
P66_GOLD="$REPO_ROOT/gold/gold_P66_en__en_annot_P66.jsonl"
SD9_TEXT="$REPO_ROOT/data/jsonl/9SD_en.jsonl"
SD9_GOLD="$REPO_ROOT/gold/gold_9SD_en__en_annot_9SD.jsonl"
EVAL_PY="$REPO_ROOT/scripts/evaluation/evaluate_json.py"

echo "== P66 v8 =="
python3 "$CLI_V8" --text "$P66_TEXT" --dict-id P66_en --silent > "$OUTDIR/p66_v8.json"
python3 "$EVAL_PY" --gold "$P66_GOLD" --pred "$OUTDIR/p66_v8.json" --out-json "$OUTDIR/p66_v8_eval.json"

echo "== P66 v8.1 =="
python3 "$CLI_V81" --text "$P66_TEXT" --dict-id P66_en --silent > "$OUTDIR/p66_v81.json"
python3 "$EVAL_PY" --gold "$P66_GOLD" --pred "$OUTDIR/p66_v81.json" --out-json "$OUTDIR/p66_v81_eval.json"

echo "== 9SD v8 =="
python3 "$CLI_V8" --text "$SD9_TEXT" --dict-id 9SD_en --silent > "$OUTDIR/9sd_v8.json"
python3 "$EVAL_PY" --gold "$SD9_GOLD" --pred "$OUTDIR/9sd_v8.json" --out-json "$OUTDIR/9sd_v8_eval.json"

echo "== 9SD v8.1 =="
python3 "$CLI_V81" --text "$SD9_TEXT" --dict-id 9SD_en --silent > "$OUTDIR/9sd_v81.json"
python3 "$EVAL_PY" --gold "$SD9_GOLD" --pred "$OUTDIR/9sd_v81.json" --out-json "$OUTDIR/9sd_v81_eval.json"

echo "== Done =="
