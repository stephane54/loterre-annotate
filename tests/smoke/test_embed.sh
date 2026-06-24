#!/usr/bin/env bash
# test_embed.sh — smoke test du scoring par embeddings Loterre (Phase 5, v2.0)
#
# Vérifie : --extractor embed nécessite --dict (erreur claire sinon), le score
# est une similarité cosinus dans [-1, 1], les candidats sont triés par score
# décroissant, et --embed-threshold filtre correctement.
#
# Usage : bash tests/smoke/test_embed.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI="$PROJECT_DIR/src/loterre_extract_cli.py"
TEXT="$PROJECT_DIR/data/jsonl/P66_en.jsonl"
DICT="$PROJECT_DIR/dictionary/en_annot_P66.jsonl"

echo "== --extractor embed sans --dict -> erreur claire =="
if python3 "$CLI" --text "$TEXT" --lang en --min-freq 2 --extractor embed --silent >/tmp/embed_no_dict.out 2>&1; then
  echo "FAIL: aurait dû échouer sans --dict"
  exit 1
fi
grep -qi "dict.*requis\|requires.*dict" /tmp/embed_no_dict.out || {
  echo "FAIL: message d'erreur peu clair :"; cat /tmp/embed_no_dict.out; exit 1
}
echo "OK erreur claire sans --dict"
rm -f /tmp/embed_no_dict.out

echo
echo "== --extractor embed avec --dict : scoring + tri =="
OUT="$(mktemp /tmp/embed_test.XXXXXX.json)"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 2 --extractor embed --dict "$DICT" --silent --out "$OUT"
python3 - "$OUT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["extractor"] == "embed"
candidates = d["candidates"]
assert candidates, "aucun candidat"
assert all(c["rule"] == "embed" for c in candidates)
scores = [c["score"] for c in candidates]
assert all(-1.0 <= s <= 1.0 for s in scores), "score embed hors de [-1, 1] (similarité cosinus)"
assert scores == sorted(scores, reverse=True), "candidats non triés par score décroissant"
print(f"OK {len(candidates)} candidats embed, scores dans [-1,1], triés ({scores[0]:.3f} -> {scores[-1]:.3f})")
PY
rm -f "$OUT"

echo
echo "== --embed-threshold filtre les candidats =="
# Seuil 0.8 (pas 0.5) : la similarité au plus proche voisin (max sur tout le
# vocabulaire) donne des scores plus hauts en moyenne que l'ancien centroïde
# (moyenne) — un seuil bas ne filtrerait plus rien sur ce corpus.
OUT_FILTERED="$(mktemp /tmp/embed_filtered.XXXXXX.json)"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 2 --extractor embed --dict "$DICT" --embed-threshold 0.8 --silent --out "$OUT_FILTERED"
python3 - "$OUT_FILTERED" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert all(c["score"] >= 0.8 for c in d["candidates"]), "candidat sous le seuil 0.8 non filtré"
print(f"OK {len(d['candidates'])} candidats >= seuil 0.8")
PY
rm -f "$OUT_FILTERED"

echo
echo "SUCCESS test_embed"
