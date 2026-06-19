#!/usr/bin/env bash
# test_extract_annotate_cli.sh — smoke test des 3 modes CLI (Phase 3, v2.0)
#
# Vérifie :
#   - le sous-commande annotate reproduit le comportement v1.0 (inchangé)
#   - le sous-commande extract fonctionne via loterre_cli.py (pas seulement en standalone)
#   - le sous-commande extract_annotate croise correctement par (doc_id, span exact) —
#     un candidat composé (ex. "controlled memory assessment") ne doit jamais
#     être faussement attribué au pref d'un sous-terme qu'il contient (ex. "memory")
#
# Usage : bash tests/smoke/test_extract_annotate_cli.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI="$PROJECT_DIR/src/loterre_cli.py"
TEXT="$PROJECT_DIR/data/jsonl/P66_en.jsonl"

echo "== sous-commande annotate : comportement v1.0 inchangé =="
OUT_ANNOTATE="$(mktemp /tmp/test_annotate.XXXXXX.json)"
# --silent (mode full) imprime toujours sur stdout, ignore --out (voir
# loterre_engine_v9_cli.py : "No file outputs; print JSON to stdout") —
# redirection shell, pas --out.
python3 "$CLI" annotate --dict-id P66_en --profile term_recall --text "$TEXT" --silent > "$OUT_ANNOTATE"
python3 - "$OUT_ANNOTATE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
matches = sum(len(r.get("matches", [])) for r in d.get("results", []))
assert matches > 0, "aucun match — comportement v1.0 cassé"
print(f"OK {matches} matches")
PY
rm -f "$OUT_ANNOTATE"

echo
echo "== sous-commande extract =="
OUT_EXTRACT="$(mktemp /tmp/test_extract.XXXXXX.json)"
python3 "$CLI" extract --text "$TEXT" --lang en --min-freq 2 --silent --out "$OUT_EXTRACT"
python3 - "$OUT_EXTRACT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["mode"] == "extract"
assert len(d["candidates"]) > 0
print(f"OK {len(d['candidates'])} candidats")
PY
rm -f "$OUT_EXTRACT"

echo
echo "== sous-commande extract_annotate : pas de faux croisement =="
OUT_EA="$(mktemp /tmp/test_extract_annotate.XXXXXX.json)"
python3 "$CLI" extract_annotate --dict-id P66_en --profile term_recall --text "$TEXT" --min-freq 2 --silent --out "$OUT_EA"
python3 - "$OUT_EA" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert d["mode"] == "extract_annotate"
candidates = d["candidates"]
assert candidates, "aucun candidat"

in_vocab = [c for c in candidates if c["in_vocabulary"]]
assert in_vocab, "aucun candidat reconnu dans le vocabulaire — dictionnaire vide ?"

# Un candidat reconnu doit toujours avoir pref == term (à la casse près) :
# si pref diffère franchement du candidat, c'est un faux croisement entre
# documents différents (bug doc_id) ou entre un terme et l'un de ses sous-termes.
mismatches = [c for c in in_vocab if c["term"].strip().lower() != (c["pref"] or "").strip().lower()]
assert not mismatches, f"faux croisement détecté : {[(c['term'], c['pref']) for c in mismatches]}"

not_in_vocab = [c for c in candidates if not c["in_vocabulary"]]
for c in not_in_vocab:
    assert c["uri"] is None and c["pref"] is None, f"{c['term']} : uri/pref devraient être None si non reconnu"

print(f"OK {len(in_vocab)} reconnus (term==pref), {len(not_in_vocab)} absents, 0 faux croisement")
PY
rm -f "$OUT_EA"

echo
echo "SUCCESS test_extract_annotate_cli"
