#!/usr/bin/env bash
# test_cvalue.sh — smoke test du scoring C-value (Phase 2, v2.0)
#
# Vérifie sur un corpus de référence anglais : le score C-value est calculé
# correctement pour un terme emboîté connu (formule Frantzi et al. 1998), les
# termes à un seul token utilisent le score de repli (jamais C-value, qui est
# toujours nul par log2(1)=0), et --cvalue-threshold filtre bien les candidats.
#
# Usage : bash tests/smoke/test_cvalue.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI="$PROJECT_DIR/src/loterre_extract_cli.py"
TEXT="$PROJECT_DIR/data/jsonl/P66_en.jsonl"

OUT_JSON="$(mktemp /tmp/cvalue_test.XXXXXX.json)"
trap 'rm -f "$OUT_JSON"' EXIT

echo "== extraction + scoring C-value sur P66_en =="
python3 "$CLI" --text "$TEXT" --lang en --min-freq 1 --extractor ncvalue --silent --out "$OUT_JSON"

python3 - "$OUT_JSON" <<'PY'
import json, math, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
by_term = {c["term"]: c for c in payload["candidates"]}

# 1) Terme emboîté connu : "controlled memories" (freq 48) est une sous-séquence
#    de lemmes de "controlled memory assessment" (freq 52, P(a)=1).
#    C-value attendu = log2(2) * (48 - 52/1) = -4.0
nested = by_term.get("controlled memories")
assert nested is not None, "candidat de référence absent — corpus changé ?"
expected = math.log2(2) * (48 - 52 / 1)
assert abs(nested["score"] - expected) < 0.01, f"C-value incorrect: {nested['score']} != {expected}"
assert nested["rule"] == "cvalue"
print(f"OK terme emboîté 'controlled memories' : score={nested['score']:.2f} (attendu {expected:.2f})")

# 2) Un terme à un seul token ne doit jamais utiliser la règle "cvalue" (toujours
#    nulle par construction) mais le repli fréquence.
single = by_term.get("study")
assert single is not None
assert single["rule"] == "freq_single_token", f"règle inattendue pour mono-token: {single['rule']}"
print(f"OK mono-token 'study' utilise le repli fréquence (score={single['score']:.3f})")

# 3) Le terme composé dominant doit avoir un score largement positif et être en tête.
top = payload["candidates"][0]
assert top["term"] == "controlled memory assessment", f"tête de classement inattendue: {top['term']}"
assert top["score"] > 50
print(f"OK tête de classement : {top['term']!r} score={top['score']:.2f}")
PY

echo
echo "== test --cvalue-threshold =="
OUT_FILTERED="$(mktemp /tmp/cvalue_filtered.XXXXXX.json)"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 1 --extractor ncvalue --cvalue-threshold 5.0 --silent --out "$OUT_FILTERED"
python3 - "$OUT_FILTERED" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert all(c["score"] >= 5.0 for c in payload["candidates"]), "seuil --cvalue-threshold non respecté"
print(f"OK {len(payload['candidates'])} candidats >= seuil 5.0")
PY
rm -f "$OUT_FILTERED"

echo
echo "SUCCESS test_cvalue"
