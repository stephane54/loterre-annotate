#!/usr/bin/env bash
# test_specificity.sh — smoke test de la grammaire de motifs TermSuite
# (--prep-patterns/--all-candidate-patterns) et du signal de spécificité
# (--specificity-filter-pctl/--specificity-top-pct), 2026-09-10/11.
#
# Vérifie :
#   - --prep-patterns produit un composé N-prep-N ("quality of service") que
#     noun_chunks seul ne produit jamais comme span unique
#   - --all-candidate-patterns produit strictement plus de candidats que
#     --prep-patterns (grammaire plus large), sans doublon exact de span
#   - --specificity-filter-pctl (--extractor ncvalue) retire des candidats et
#     peuple specificity_score/specificity_rank ; désactivé (défaut), les deux
#     champs restent null
#   - --specificity-top-pct (--extractor embed, extract_annotate) peuple
#     enrichment_suggestion_specificity, mutuellement exclusif des niveaux 1/2 ;
#     désactivé (défaut), jamais True
#
# Usage : bash tests/smoke/test_specificity.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXTRACT_CLI="$PROJECT_DIR/src/loterre_extract_cli.py"
CLI="$PROJECT_DIR/src/loterre_cli.py"
TEXT_P66="$PROJECT_DIR/data/jsonl/P66_en.jsonl"
DICT_P66="$PROJECT_DIR/dictionary/en_annot_P66.jsonl"

TMP_TEXT="$(mktemp /tmp/test_specificity_text.XXXXXX.jsonl)"
cat > "$TMP_TEXT" <<'EOF'
{"id": "d1", "value": "The rate of change in quality of service depends on the abuse of power. Fast and reliable machine learning systems are widely used. Three chemical products were tested. The study of semiotics and linguistics reveals that the author, on the one hand, discusses philology, and on the other hand, the general reader can easily follow the argument."}
EOF
trap 'rm -f "$TMP_TEXT"' EXIT

echo "== --prep-patterns : produit un composé N-prep-N que noun_chunks seul ne produit jamais =="
OUT_BASE="$(mktemp /tmp/test_spec_base.XXXXXX.json)"
OUT_PREP="$(mktemp /tmp/test_spec_prep.XXXXXX.json)"
python3 "$EXTRACT_CLI" --text "$TMP_TEXT" --lang en --min-freq 1 --silent --out "$OUT_BASE"
python3 "$EXTRACT_CLI" --text "$TMP_TEXT" --lang en --min-freq 1 --prep-patterns --silent --out "$OUT_PREP"
python3 - "$OUT_BASE" "$OUT_PREP" <<'PY'
import json, sys
base = json.load(open(sys.argv[1], encoding="utf-8"))
prep = json.load(open(sys.argv[2], encoding="utf-8"))
base_terms = {c["term"] for c in base["candidates"]}
prep_terms = {c["term"] for c in prep["candidates"]}
assert "quality of service" not in base_terms, "noun_chunks seul n'aurait jamais dû produire ce composé"
assert "quality of service" in prep_terms, "--prep-patterns aurait dû produire 'quality of service'"
assert "rate of change" in prep_terms
assert "abuse of power" in prep_terms
print(f"OK noun_chunks seul: {len(base_terms)} candidats, +--prep-patterns: {len(prep_terms)} (composés N-prep-N ajoutés)")
PY
rm -f "$OUT_BASE" "$OUT_PREP"

echo
echo "== --all-candidate-patterns : strictement plus de candidats que --prep-patterns, pas de doublon de span =="
OUT_PREP="$(mktemp /tmp/test_spec_prep2.XXXXXX.json)"
OUT_ALL="$(mktemp /tmp/test_spec_all.XXXXXX.json)"
python3 "$EXTRACT_CLI" --text "$TMP_TEXT" --lang en --min-freq 1 --prep-patterns --silent --out "$OUT_PREP"
python3 "$EXTRACT_CLI" --text "$TMP_TEXT" --lang en --min-freq 1 --all-candidate-patterns --silent --out "$OUT_ALL"
python3 - "$OUT_PREP" "$OUT_ALL" <<'PY'
import json, sys
prep = json.load(open(sys.argv[1], encoding="utf-8"))
allp = json.load(open(sys.argv[2], encoding="utf-8"))
assert len(allp["candidates"]) > len(prep["candidates"]), "--all-candidate-patterns devrait produire plus de candidats"
# Pas de doublon exact de (terme, occurrence) -- verifie la dedup par bornes.
seen = set()
for c in allp["candidates"]:
    for occ in c["occurrences"]:
        key = (occ["doc_id"], occ["start"], occ["end"])
        assert key not in seen, f"span dupliqué détecté : {key} (terme {c['term']!r})"
        seen.add(key)
print(f"OK --prep-patterns: {len(prep['candidates'])} candidats, --all-candidate-patterns: {len(allp['candidates'])}, aucun span dupliqué")
PY
rm -f "$OUT_PREP" "$OUT_ALL"

echo
echo "== --specificity-filter-pctl (--extractor ncvalue) : retire des candidats, peuple specificity_score =="
OUT_NOFILTER="$(mktemp /tmp/test_spec_nofilter.XXXXXX.json)"
OUT_FILTER="$(mktemp /tmp/test_spec_filter.XXXXXX.json)"
python3 "$EXTRACT_CLI" --text "$TEXT_P66" --lang en --min-freq 1 --extractor ncvalue --silent --out "$OUT_NOFILTER"
python3 "$EXTRACT_CLI" --text "$TEXT_P66" --lang en --min-freq 1 --extractor ncvalue --specificity-filter-pctl 40 --silent --out "$OUT_FILTER"
python3 - "$OUT_NOFILTER" "$OUT_FILTER" <<'PY'
import json, sys
nofilter = json.load(open(sys.argv[1], encoding="utf-8"))
filtered = json.load(open(sys.argv[2], encoding="utf-8"))
assert all(c["specificity_score"] is None for c in nofilter["candidates"]), \
    "specificity_score devrait rester null sans --specificity-filter-pctl"
assert len(filtered["candidates"]) < len(nofilter["candidates"]), \
    "--specificity-filter-pctl 40 devrait retirer des candidats"
assert all(c["specificity_score"] is not None for c in filtered["candidates"]), \
    "specificity_score devrait être peuplé pour les candidats survivants"
print(f"OK sans filtre: {len(nofilter['candidates'])} candidats (specificity_score=null), "
      f"avec filtre 40%: {len(filtered['candidates'])} (specificity_score peuplé)")
PY
rm -f "$OUT_NOFILTER" "$OUT_FILTER"

echo
echo "== --specificity-top-pct (--extractor embed, extract_annotate) : niveau 3, mutuellement exclusif =="
OUT_L3_OFF="$(mktemp /tmp/test_spec_l3off.XXXXXX.json)"
OUT_L3_ON="$(mktemp /tmp/test_spec_l3on.XXXXXX.json)"
python3 "$CLI" extract_annotate --text "$TEXT_P66" --lang en --dict "$DICT_P66" --profile term_recall \
  --extractor embed --min-freq 1 --silent --out "$OUT_L3_OFF"
python3 "$CLI" extract_annotate --text "$TEXT_P66" --lang en --dict "$DICT_P66" --profile term_recall \
  --extractor embed --min-freq 1 --specificity-top-pct 30 --silent --out "$OUT_L3_ON"
python3 - "$OUT_L3_OFF" "$OUT_L3_ON" <<'PY'
import json, sys
off = json.load(open(sys.argv[1], encoding="utf-8"))
on = json.load(open(sys.argv[2], encoding="utf-8"))

assert not any(c.get("enrichment_suggestion_specificity") for c in off["candidates"]), \
    "enrichment_suggestion_specificity ne devrait jamais être True avec --specificity-top-pct 0 (défaut)"

absent_on = [c for c in on["candidates"] if c["in_vocabulary"] is False]
assert absent_on, "aucun candidat absent du vocabulaire — test non concluant"
flagged_l3 = [c for c in absent_on if c["enrichment_suggestion_specificity"]]
assert flagged_l3, "--specificity-top-pct 30 devrait marquer au moins un candidat niveau 3 sur ce corpus"
for c in flagged_l3:
    assert not c["enrichment_suggestion_embed"] and not c["enrichment_suggestion_structural"], \
        f"{c['term']} : niveau 3 devrait être mutuellement exclusif des niveaux 1/2"
    assert c["specificity_score"] is not None and c["specificity_rank"] is not None

# Exclusivité mutuelle générale (les 3 champs, tous candidats).
for c in on["candidates"]:
    flags = [c["enrichment_suggestion_embed"], c["enrichment_suggestion_structural"], c["enrichment_suggestion_specificity"]]
    assert sum(bool(f) for f in flags) <= 1, f"{c['term']} : plus d'un niveau de suggestion actif à la fois"

print(f"OK --specificity-top-pct 0 (défaut) : jamais True. "
      f"--specificity-top-pct 30 : {len(flagged_l3)}/{len(absent_on)} candidats absents marqués niveau 3, "
      f"exclusivité mutuelle vérifiée sur {len(on['candidates'])} candidats")
PY
rm -f "$OUT_L3_OFF" "$OUT_L3_ON"

echo
echo "SUCCESS test_specificity"
