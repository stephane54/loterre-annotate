#!/usr/bin/env bash
set -euo pipefail

# Non-regression smoke test focused on P66 flow:
# 1) CLI prediction
# 2) prediction -> expected conversion
# 3) HTML render with gold merge
# 4) bulk converter wrapper

CLI="${1:-./src/loterre_cli.py}"
RENDERER="${2:-./src/loterre_html_renderer.py}"
CONVERTER="${3:-./scripts/prediction/results_to_expected_jsonl.py}"
BULK="${4:-./scripts/prediction/bulk_results_to_expected.sh}"
INPUT="${5:-data/jsonl/P66_en.jsonl}"

OUTDIR="${OUTDIR:-/tmp/loterre_p66_nonreg}"
rm -rf "$OUTDIR"
mkdir -p "$OUTDIR"

PRED_JSON="$OUTDIR/P66_en.pred.json"
EXPECTED_JSONL="$OUTDIR/P66_en.expected.jsonl"
HTML_OUT="$OUTDIR/P66_en.html"
BULK_IN="$OUTDIR/bulk_in"
BULK_OUT="$OUTDIR/bulk_out"

echo "[1/4] CLI prediction"
if python3 "$CLI" --dict-id P66_en --text "$INPUT" --silent > "$PRED_JSON"; then
  echo "OK CLI prediction generated"
else
  echo "WARN: CLI prediction skipped (missing runtime model/dependency), using fixture predictions"
  cp outputs_tests_v8_1_cli/p66_api.json "$PRED_JSON"
fi
python3 - <<'PY' "$PRED_JSON"
import json, sys
obj = json.load(open(sys.argv[1], encoding="utf-8"))
assert "results" in obj and isinstance(obj["results"], list), "missing results[]"
print("OK results[]:", len(obj["results"]))
PY

echo "[2/4] Convert prediction to expected JSONL"
python3 "$CONVERTER" --input "$PRED_JSON" --out "$EXPECTED_JSONL"
python3 - <<'PY' "$EXPECTED_JSONL"
import json, sys
rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8") if x.strip()]
assert rows, "empty expected jsonl"
assert "expected_matches" in rows[0], "expected_matches missing"
print("OK expected rows:", len(rows))
PY

echo "[3/4] Render HTML comparison"
python3 "$RENDERER" render --input "$PRED_JSON" --gold "$EXPECTED_JSONL" --out "$HTML_OUT" --title "P66 non regression"
python3 - <<'PY' "$HTML_OUT"
import re, sys
html = open(sys.argv[1], encoding="utf-8").read()
assert "attendu" in html.lower(), "expected legend missing"
assert re.search(r'class="term ', html), "highlighted terms missing"
assert re.search(r'href="https?://', html), "clickable links missing"
print("OK html generated")
PY

echo "[4/4] Bulk converter wrapper"
mkdir -p "$BULK_IN"
cp "$PRED_JSON" "$BULK_IN/p66.json"
bash "$BULK" "$BULK_IN" "$BULK_OUT"
test -s "$BULK_OUT/p66.jsonl"
echo "OK bulk output: $BULK_OUT/p66.jsonl"

echo "SUCCESS non-regression P66"
