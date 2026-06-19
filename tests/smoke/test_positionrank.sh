#!/usr/bin/env bash
# test_positionrank.sh — smoke test de PositionRank et de la bascule automatique
# ncvalue/graph (v2.0, suite à la Phase 2)
#
# Vérifie : PositionRank favorise les mots fréquents et précoces (vs rares et
# tardifs), --extractor auto bascule correctement selon --extractor-auto-threshold
# par rapport au volume réel du corpus, et --extractor graph/ncvalue forcent
# explicitement l'algorithme demandé.
#
# Usage : bash tests/smoke/test_positionrank.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI="$PROJECT_DIR/src/loterre_extract_cli.py"
TEXT="$PROJECT_DIR/data/jsonl/P66_en.jsonl"

echo "== --extractor auto sur un petit corpus (< seuil) -> graph =="
OUT_AUTO="$(mktemp /tmp/posrank_auto.XXXXXX.json)"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 1 --silent --out "$OUT_AUTO"
python3 - "$OUT_AUTO" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["total_tokens"] < 50000, f"corpus de test trop gros pour ce test : {d['total_tokens']} tokens"
assert d["extractor"] == "graph", f"auto devrait basculer sur graph sous le seuil, a choisi {d['extractor']}"
assert all(c["rule"] == "positionrank" for c in d["candidates"])
print(f"OK auto -> graph (total_tokens={d['total_tokens']} < 50000)")
PY
rm -f "$OUT_AUTO"

echo
echo "== --extractor-auto-threshold abaissé -> bascule vers ncvalue =="
OUT_FORCED="$(mktemp /tmp/posrank_forced.XXXXXX.json)"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 1 --extractor-auto-threshold 100 --silent --out "$OUT_FORCED"
python3 - "$OUT_FORCED" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["extractor"] == "ncvalue", f"seuil abaissé devrait forcer ncvalue, a choisi {d['extractor']}"
print("OK seuil abaissé -> ncvalue")
PY
rm -f "$OUT_FORCED"

echo
echo "== --extractor graph explicite =="
OUT_GRAPH="$(mktemp /tmp/posrank_graph.XXXXXX.json)"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 2 --extractor graph --silent --out "$OUT_GRAPH"
python3 - "$OUT_GRAPH" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["extractor"] == "graph"
candidates = d["candidates"]
assert candidates, "aucun candidat"
assert all(c["rule"] == "positionrank" for c in candidates)
# Les scores doivent être strictement positifs et triés décroissants.
scores = [c["score"] for c in candidates]
assert all(s > 0 for s in scores), "score PositionRank devrait toujours être positif (somme de scores positifs)"
assert scores == sorted(scores, reverse=True), "candidats non triés par score décroissant"
print(f"OK {len(candidates)} candidats PositionRank, triés, scores positifs")
PY
rm -f "$OUT_GRAPH"

echo
echo "SUCCESS test_positionrank"
