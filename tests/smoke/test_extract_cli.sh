#!/usr/bin/env bash
# test_extract_cli.sh — smoke test du mode extract (Phase 1, v2.0)
#
# Vérifie le module d'extraction noun-chunks (src/loterre_extract_cli.py) sur
# un corpus de référence anglais et français : sortie JSON valide, candidats
# non vides, schéma de champs correct, respect du seuil --min-freq.
#
# Usage : bash tests/smoke/test_extract_cli.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI="$PROJECT_DIR/src/loterre_extract_cli.py"

VALIDATOR="$(mktemp /tmp/extract_validate.XXXXXX.py)"
trap 'rm -f "$VALIDATOR"' EXIT

cat > "$VALIDATOR" <<'PY'
import json, sys
payload_path, min_freq = sys.argv[1], int(sys.argv[2])
payload = json.load(open(payload_path, encoding="utf-8"))

assert payload.get("mode") == "extract", "champ mode incorrect"
assert payload.get("docs", 0) > 0, "aucun document traité"
candidates = payload.get("candidates")
assert candidates, "aucun candidat extrait"

required_keys = {"term", "lemma", "pattern", "frequency", "score", "rule",
                  "occurrences", "in_vocabulary", "uri", "pref"}
for c in candidates:
    assert required_keys <= set(c.keys()), f"champs manquants sur {c.get('term')}"
    assert c["frequency"] >= min_freq, f"{c['term']} sous le seuil min-freq"
    assert len(c["occurrences"]) == c["frequency"], f"{c['term']} : occurrences != frequency"
    assert c["pattern"], f"{c['term']} : pattern vide"
    assert c["rule"] in ("cvalue", "freq_single_token", "positionrank"), f"règle inattendue : {c['rule']}"

print(f"OK {len(candidates)} candidats, docs={payload['docs']}, extractor={payload.get('extractor')}")
PY

run_check() {
  local lang="$1" text_file="$2" min_freq="$3"
  echo "== extract --lang $lang ($text_file, --min-freq $min_freq) =="
  local out_json="$(mktemp /tmp/extract_out.XXXXXX.json)"
  python3 "$CLI" --text "$text_file" --lang "$lang" --min-freq "$min_freq" --silent --out "$out_json"
  python3 "$VALIDATOR" "$out_json" "$min_freq"
  rm -f "$out_json"
}

run_check en "$PROJECT_DIR/data/jsonl/P66_en.jsonl" 2
run_check fr "$PROJECT_DIR/data/jsonl/P66_fr.jsonl" 2

echo
echo "SUCCESS test_extract_cli"
