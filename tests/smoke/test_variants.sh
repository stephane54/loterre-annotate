#!/usr/bin/env bash
# test_variants.sh — smoke test de la détection de variantes (Phase 4, v2.0)
#
# Deux parties :
#  1) Test unitaire de loterre_variants.group_variants() sur des candidats
#     construits à la main, un par catégorie (morph_inflection, graphical,
#     morph_prefix, syn_expansion x2, syn_permutation, morph_derivation).
#  2) Test de bout en bout via la CLI : --detect-variants ajoute les champs
#     canonical_form/variant_type ; sans le flag, sortie strictement
#     inchangée (zéro régression, l'option est explicite par défaut).
#
# Usage : bash tests/smoke/test_variants.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLI="$PROJECT_DIR/src/loterre_extract_cli.py"
TEXT="$PROJECT_DIR/data/jsonl/P66_en.jsonl"

echo "== unitaire : group_variants() par catégorie =="
PYTHONPATH="$PROJECT_DIR/src" python3 - <<'PY'
from loterre_extraction_base import CandidateTerm
from loterre_variants import group_variants


def cand(term, lemma, pattern, freq):
    return CandidateTerm(term=term, lemma=lemma, pattern=pattern, frequency=freq,
                          score=float(freq), rule="noun_chunk")


def tok(lemma, pos):
    return {"pos": pos, "lemma": lemma}


def check(candidates, lang, expect):
    # expect: {term: (canonical_term_ou_None, variant_type_ou_None)}
    group_variants(candidates, lang)
    by_term = {c.term: c for c in candidates}
    for term, (expected_canon, expected_type) in expect.items():
        c = by_term[term]
        assert c.canonical_form == expected_canon, (
            f"{term!r}: canonical_form={c.canonical_form!r} attendu {expected_canon!r}")
        assert c.variant_type == expected_type, (
            f"{term!r}: variant_type={c.variant_type!r} attendu {expected_type!r}")


# 1) morph_inflection : même lemme, fréquence différente -> canonique = plus fréquent
candidates = [
    cand("résultats", "résultat", [tok("résultat", "NOUN")], 10),
    cand("résultat", "résultat", [tok("résultat", "NOUN")], 4),
]
check(candidates, "fr", {
    "résultats": (None, None),
    "résultat": ("résultats", "morph_inflection"),
})
print("OK morph_inflection : résultat -> résultats")

# 2) graphical : tiret/accent, lemmes différents mais clé normalisée identique
candidates = [
    cand("macroéconomie", "macroéconomie", [tok("macroéconomie", "NOUN")], 7),
    cand("macro-économie", "macro-économie", [tok("macro-économie", "NOUN")], 3),
]
check(candidates, "fr", {
    "macroéconomie": (None, None),
    "macro-économie": ("macroéconomie", "graphical"),
})
print("OK graphical : macro-économie -> macroéconomie")

# 3) morph_prefix : un seul token diffère, lié par un préfixe privatif (a-)
candidates = [
    cand("machine synchrone", "machine synchrone",
         [tok("machine", "NOUN"), tok("synchrone", "ADJ")], 8),
    cand("machine asynchrone", "machine asynchrone",
         [tok("machine", "NOUN"), tok("asynchrone", "ADJ")], 4),
]
check(candidates, "fr", {
    "machine synchrone": (None, None),
    "machine asynchrone": ("machine synchrone", "morph_prefix"),
})
print("OK morph_prefix : machine asynchrone -> machine synchrone")

# 4a) syn_expansion (insertion de contenu) : squelette de contenu = sous-séquence
candidates = [
    cand("chauffage électrique", "chauffage électrique",
         [tok("chauffage", "NOUN"), tok("électrique", "ADJ")], 15),
    cand("chauffage électrique solaire", "chauffage électrique solaire",
         [tok("chauffage", "NOUN"), tok("électrique", "ADJ"), tok("solaire", "ADJ")], 6),
]
check(candidates, "fr", {
    "chauffage électrique": (None, None),
    "chauffage électrique solaire": ("chauffage électrique", "syn_expansion"),
})
print("OK syn_expansion (insertion) : chauffage électrique solaire -> chauffage électrique")

# 4b) syn_expansion (mot-outil seul, squelette de contenu identique) : N N <-> N de N
candidates = [
    cand("panne réseau", "panne réseau",
         [tok("panne", "NOUN"), tok("réseau", "NOUN")], 9),
    cand("panne de réseau", "panne de réseau",
         [tok("panne", "NOUN"), tok("de", "ADP"), tok("réseau", "NOUN")], 20),
]
check(candidates, "fr", {
    "panne de réseau": (None, None),
    "panne réseau": ("panne de réseau", "syn_expansion"),
})
print("OK syn_expansion (mot-outil) : panne réseau <-> panne de réseau")

# 5) syn_permutation : même multiset de lemmes de contenu, ordre différent
candidates = [
    cand("vitesse moyenne annuelle", "vitesse moyen annuel",
         [tok("vitesse", "NOUN"), tok("moyen", "ADJ"), tok("annuel", "ADJ")], 12),
    cand("vitesse annuelle moyenne", "vitesse annuel moyen",
         [tok("vitesse", "NOUN"), tok("annuel", "ADJ"), tok("moyen", "ADJ")], 5),
]
check(candidates, "fr", {
    "vitesse moyenne annuelle": (None, None),
    "vitesse annuelle moyenne": ("vitesse moyenne annuelle", "syn_permutation"),
})
print("OK syn_permutation : vitesse annuelle moyenne <-> vitesse moyenne annuelle")

# 6) morph_derivation : N+Adj <-> N+Prep+N, lié par la table de suffixes TermSuite
#    (règle vendée "A N -ulmonaire -oumon" -> pulmonaire/poumon)
candidates = [
    cand("atteinte pulmonaire", "atteinte pulmonaire",
         [tok("atteinte", "NOUN"), tok("pulmonaire", "ADJ")], 11),
    cand("atteinte du poumon", "atteinte de poumon",
         [tok("atteinte", "NOUN"), tok("de", "ADP"), tok("poumon", "NOUN")], 3),
]
check(candidates, "fr", {
    "atteinte pulmonaire": (None, None),
    "atteinte du poumon": ("atteinte pulmonaire", "morph_derivation"),
})
print("OK morph_derivation : atteinte du poumon -> atteinte pulmonaire (table TermSuite)")

# Non-régression : candidats sans aucune relation ne sont jamais groupés
candidates = [
    cand("linguistique", "linguistique", [tok("linguistique", "NOUN")], 50),
    cand("traduction automatique", "traduction automatique",
         [tok("traduction", "NOUN"), tok("automatique", "ADJ")], 30),
]
group_variants(candidates, "fr")
assert all(c.canonical_form is None and c.variant_type is None for c in candidates), \
    "faux regroupement entre candidats non reliés"
print("OK non-régression : candidats non reliés jamais groupés")
PY

echo
echo "== bout en bout : --detect-variants additif, pas de régression sans le flag =="

OUT_WITHOUT="$(mktemp /tmp/variants_without.XXXXXX.json)"
OUT_WITH="$(mktemp /tmp/variants_with.XXXXXX.json)"
trap 'rm -f "$OUT_WITHOUT" "$OUT_WITH"' EXIT

python3 "$CLI" --text "$TEXT" --lang en --min-freq 2 --silent --out "$OUT_WITHOUT"
python3 "$CLI" --text "$TEXT" --lang en --min-freq 2 --detect-variants --silent --out "$OUT_WITH"

python3 - "$OUT_WITHOUT" "$OUT_WITH" <<'PY'
import json, sys

without = json.load(open(sys.argv[1], encoding="utf-8"))
with_ = json.load(open(sys.argv[2], encoding="utf-8"))

# Sans --detect-variants : les champs existent (schéma stable) mais restent None partout.
assert all(c.get("canonical_form") is None and c.get("variant_type") is None
           for c in without["candidates"]), "régression : champs renseignés sans --detect-variants"
print(f"OK {len(without['candidates'])} candidats, canonical_form/variant_type=None sans --detect-variants")

# Même candidats (même extraction), seuls canonical_form/variant_type peuvent différer.
terms_without = {c["term"] for c in without["candidates"]}
terms_with = {c["term"] for c in with_["candidates"]}
assert terms_without == terms_with, "--detect-variants a changé l'ensemble des candidats"
print(f"OK même ensemble de {len(terms_with)} candidats avec --detect-variants")

grouped = [c for c in with_["candidates"] if c.get("canonical_form")]
print(f"OK {len(grouped)} candidats groupés en variantes sur ce corpus")
PY

echo
echo "SUCCESS test_variants"
