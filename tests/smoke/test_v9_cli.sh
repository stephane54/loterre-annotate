#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs_tests_v9_cli}"

mkdir -p "$OUTDIR"

echo "== Test 1: génération YAML auto-profile P66 =="
python3 "$CLI" annotate \
  --text data/jsonl/P66_en.jsonl \
  --dict-id P66_en \
  --auto-profile \
  --yaml-out "$OUTDIR/p66_auto_profile.yaml" \
  > "$OUTDIR/p66_auto_profile.json"

echo
echo "== Test 2: génération YAML auto-profile 9SD avec profil imposé =="
python3 "$CLI" annotate \
  --text data/jsonl/9SD_en.jsonl \
  --dict-id 9SD_en \
  --profile entity_strict \
  --auto-profile \
  --yaml-out "$OUTDIR/9sd_forced_profile.yaml" \
  > "$OUTDIR/9sd_forced_profile.json"

echo
echo "== Test 3: annotation P66 via stdin + --silent =="
cat data/jsonl/P66_en.jsonl | python3 "$CLI" annotate \
  --dict-id P66_en \
  --silent \
  > "$OUTDIR/p66_stdin_silent.json"

echo
echo "== Test 4: annotation P66 via fichier + --api =="
python3 "$CLI" annotate \
  --text data/jsonl/P66_en.jsonl \
  --dict-id P66_en \
  --api \
  > "$OUTDIR/p66_api.json"

echo
echo "== Test 5: annotation 9SD via fichier =="
python3 "$CLI" annotate \
  --text data/jsonl/9SD_en.jsonl \
  --dict-id 9SD_en \
  --out "$OUTDIR/annotation_9SD_en.md" \
  --report "$OUTDIR/report_9SD_en.md"

echo
echo "== Test 6: annotation 9SD via stdin + --silent =="
cat data/jsonl/9SD_en.jsonl | python3 "$CLI" annotate \
  --dict-id 9SD_en \
  --silent \
  > "$OUTDIR/9sd_stdin_silent.json"

echo
echo "== Test 7: annotation P66 avec config YAML rapide (1 seul document) =="
python3 "$CLI" annotate \
  --config configs/example_p66_en_quick.yaml \
  --out "$OUTDIR/annotation_P66_en_quick.md" \
  --report "$OUTDIR/report_P66_en_quick.md"

echo
echo "== Test 8: test qualité anti-bruit (and/it) sur 9SD =="
printf '%s\n' '{"id":"bad1","value":"and is here"}' '{"id":"bad2","value":"it is here"}' | python3 "$CLI" annotate \
  --dict-id 9SD_en \
  --silent \
  > "$OUTDIR/quality_false_positive_guard.json"

# ── Tests français ────────────────────────────────────────────────────────────

echo
echo "== Test 9: auto-profile P66_fr (français) =="
python3 "$CLI" annotate \
  --text data/jsonl/P66_fr.jsonl \
  --dict-id P66_fr \
  --auto-profile \
  --yaml-out "$OUTDIR/P66_fr_auto_profile.yaml" \
  > "$OUTDIR/P66_fr_auto_profile.json"

echo
echo "== Test 10: annotation P66_fr --silent (variants flexionnels) =="
python3 "$CLI" annotate \
  --text data/jsonl/P66_fr.jsonl \
  --dict-id P66_fr \
  --silent \
  > "$OUTDIR/P66_fr_silent.json"
python3 - <<'PY' "$OUTDIR/P66_fr_silent.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
results = data.get("results", [])
assert results, "aucun résultat"
# Vérifier que des variants flexionnels sont reconnus (found != pref)
variants = [
    m for d in results for m in d.get("matches", [])
    if m.get("found","") != m.get("pref","")
]
print(f"OK {len(results)} docs, {sum(len(d.get('matches',[])) for d in results)} matches, {len(variants)} variants flexionnels reconnus")
PY

echo
echo "== Test 11: annotation B9M_fr --silent (biologie FR) =="
python3 "$CLI" annotate \
  --text data/jsonl/B9M_fr.jsonl \
  --dict-id B9M_fr \
  --silent \
  > "$OUTDIR/B9M_fr_silent.json"

echo
echo "== Test 12: test qualité anti-bruit FR (et/ou) sur P66_fr =="
printf '%s\n' '{"id":"bruit1","value":"et ou ni mais"}' '{"id":"bruit2","value":"il elle on bien"}' | python3 "$CLI" annotate \
  --dict-id P66_fr \
  --silent \
  > "$OUTDIR/quality_fr_false_positive_guard.json"
python3 - <<'PY' "$OUTDIR/quality_fr_false_positive_guard.json"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
matches = [m for d in data.get("results",[]) for m in d.get("matches",[])]
weak = [m for m in matches if m.get("found","").lower() in {"et","ou","ni","mais","il","elle","on","bien"}]
assert not weak, f"FAIL: mots faibles FR non filtrés: {weak}"
print(f"OK aucun mot faible FR non filtré ({len(matches)} matches au total)")
PY

echo
echo "== Test 13: annotation QX8_fr --silent (géosciences FR) =="
python3 "$CLI" annotate \
  --text data/jsonl/QX8_fr.jsonl \
  --dict-id QX8_fr \
  --silent \
  > "$OUTDIR/QX8_fr_silent.json"

echo
echo "Tous les tests CLI sont terminés (EN + FR)."
echo "Résultats dans: $OUTDIR"
