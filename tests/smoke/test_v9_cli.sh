#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs_tests_v9_cli}"

mkdir -p "$OUTDIR"

echo "== Test 1: génération YAML auto-profile P66 =="
python "$CLI" \
  --text examples/gold_1/P66_en.jsonl \
  --dict-id P66_en \
  --auto-profile \
  --yaml-out "$OUTDIR/p66_auto_profile.yaml" \
  > "$OUTDIR/p66_auto_profile.json"

echo
echo "== Test 2: génération YAML auto-profile 9SD avec profil imposé =="
python "$CLI" \
  --text examples/gold_1/9SD_en.jsonl \
  --dict-id 9SD_en \
  --profile entity_strict \
  --auto-profile \
  --yaml-out "$OUTDIR/9sd_forced_profile.yaml" \
  > "$OUTDIR/9sd_forced_profile.json"

echo
echo "== Test 3: annotation P66 via stdin + --silent =="
cat examples/gold_1/P66_en.jsonl | python "$CLI" \
  --dict-id P66_en \
  --silent \
  > "$OUTDIR/p66_stdin_silent.json"

echo
echo "== Test 4: annotation P66 via fichier + --api =="
python "$CLI" \
  --text examples/gold_1/P66_en.jsonl \
  --dict-id P66_en \
  --api \
  > "$OUTDIR/p66_api.json"

echo
echo "== Test 5: annotation 9SD via fichier =="
python "$CLI" \
  --text examples/gold_1/9SD_en.jsonl \
  --dict-id 9SD_en \
  --out "$OUTDIR/annotation_9SD_en.md" \
  --report "$OUTDIR/report_9SD_en.md"

echo
echo "== Test 6: annotation 9SD via stdin + --silent =="
cat examples/gold_1/9SD_en.jsonl | python "$CLI" \
  --dict-id 9SD_en \
  --silent \
  > "$OUTDIR/9sd_stdin_silent.json"

echo
echo "== Test 7: annotation P66 avec config YAML rapide (1 seul document) =="
python "$CLI" \
  --config configs/example_p66_en_quick.yaml \
  --out "$OUTDIR/annotation_P66_en_quick.md" \
  --report "$OUTDIR/report_P66_en_quick.md"

echo
echo "== Test 8: test qualité anti-bruit (and/it) sur 9SD =="
printf '%s\n' '{"id":"bad1","value":"and is here"}' '{"id":"bad2","value":"it is here"}' | python "$CLI" \
  --dict-id 9SD_en \
  --silent \
  > "$OUTDIR/quality_false_positive_guard.json"

echo
echo "Tous les tests v8.1 CLI sont terminés."
echo "Résultats dans: $OUTDIR"
