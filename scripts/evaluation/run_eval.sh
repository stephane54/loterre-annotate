#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CLI="${1:-$REPO_ROOT/src/loterre_cli.py}"
OUTDIR="${2:-$REPO_ROOT/eval_outputs}"
EVAL_PY="$REPO_ROOT/scripts/evaluation/evaluate_json.py"

mkdir -p "$OUTDIR"

cd "$REPO_ROOT"

# ── Anglais — gold nettoyé (gold_cleaned/) ────────────────────────────────────

echo "== P66_en evaluation =="
python3 "$CLI" --text ./data/jsonl/P66_en.jsonl --dict-id P66_en --silent > "$OUTDIR/P66_en_pred.json"
python3 "$EVAL_PY" --gold ./gold_cleaned/gold_P66_en.jsonl --pred "$OUTDIR/P66_en_pred.json" --out-json "$OUTDIR/P66_en_eval.json"

echo
echo "== 9SD_en evaluation =="
python3 "$CLI" --text ./data/jsonl/9SD_en.jsonl --dict-id 9SD_en --silent > "$OUTDIR/9SD_en_pred.json"
python3 "$EVAL_PY" --gold ./gold_cleaned/gold_9SD_en.jsonl --pred "$OUTDIR/9SD_en_pred.json" --out-json "$OUTDIR/9SD_en_eval.json"

# ── Français — gold inline (data/jsonl/*_fr.jsonl) ───────────────────────
# Le gold est inclus directement dans les fichiers JSONL via expected_matches.

for vocab in P66_fr 27X_fr 9SD_fr 8HQ_fr B9M_fr BVM_fr QX8_fr; do
  echo
  echo "== ${vocab} evaluation =="
  GOLD="./data/jsonl/${vocab}.jsonl"
  PRED="$OUTDIR/${vocab}_pred.json"
  EVAL_OUT="$OUTDIR/${vocab}_eval.json"

  if [[ ! -f "$GOLD" ]]; then
    echo "  SKIP: gold file not found: $GOLD" >&2
    continue
  fi

  python3 "$CLI" --text "$GOLD" --dict-id "$vocab" --silent > "$PRED"
  # gold = même fichier JSONL (expected_matches inline)
  python3 "$EVAL_PY" --gold "$GOLD" --pred "$PRED" --out-json "$EVAL_OUT"
done

echo
echo "Evaluation outputs written to $OUTDIR"
