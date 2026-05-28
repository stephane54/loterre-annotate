import json
from pathlib import Path
from src.loterre_engine_v9_cli import build_surface_forms, form_to_lemma_seqs, merge_profile, load_model

path = Path("examples/dicts/en_annot_P66.jsonl")
lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
entries = [json.loads(line) for line in lines]
print("entries", len(entries))
print("pattern_entries", sum(1 for e in entries if e.get("pattern")))
profile = merge_profile("term_recall", {})
print("use_lemma", profile.params["use_lemma"])
print("use_pattern", profile.params["use_pattern"])
print("allow_surface_fallback", profile.params["allow_surface_fallback"])
print("allow_single_token_fallback", profile.params["allow_single_token_fallback"])

nlp = load_model("en")
forms = 0
lemma_forms = 0
for e in entries[:100]:
    fs = list(build_surface_forms(e, profile))
    forms += len(fs)
    for f in fs:
        lemma_forms += len(list(form_to_lemma_seqs(f, nlp, profile)))
print("surface_forms_first100", forms, "lemma_forms_first100", lemma_forms)
print("avg_surface_forms", forms / 100, "avg_lemma_forms", lemma_forms / 100)
