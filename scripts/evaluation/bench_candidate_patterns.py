#!/usr/bin/env python3
"""Benchmark de la grammaire de motifs de candidats TermSuite
(--prep-patterns / --all-candidate-patterns, planification/
planif_extraction_terminologique.md §9) contre le gold ACTER.

Consolidation des scripts ad hoc de la session 2026-09-10 (bench_prep_patterns.py,
bench_prep_patterns_f1.py, bench_prep_patterns_topn_sweep.py,
bench_all_candidate_patterns.py) — mêmes mesures, un seul outil réutilisable :

1. Rappel candidat oracle (avant tout scoring) : baseline (noun_chunks seul)
   vs le motif choisi (--prep-patterns ou --all-candidate-patterns).
2. Sweep top-N (fraction de n_gold_terms) sur ncvalue ET graph, pour voir si
   le gain/la perte de F1 dépend de la profondeur de coupure.

Résultats de référence déjà mesurés et journalisés dans
planification/analyse_benchmarks_extraction.md (entrées 2026-09-10) :
--all-candidate-patterns donne un gain net avec ncvalue (+0.08 à +0.13 selon
coupure) mais une régression nette avec graph/PositionRank (jusqu'à -0.12),
et un coût O(n²) prohibitif sur gros corpus (build_containment_map) — les
deux flags restent opt-in, jamais par défaut.

Usage:
    make corpus-acter   # si pas déjà fait
    python3 scripts/evaluation/bench_candidate_patterns.py --patterns all-candidate-patterns
    python3 scripts/evaluation/bench_candidate_patterns.py --patterns prep-patterns --domains htfl --langs en
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import acter_eval as ae  # noqa: E402
from loterre_extract_cli import extract_candidates, score_extracted_candidates  # noqa: E402

DOMAINS = ["corp", "equi", "htfl", "wind"]
LANGS = ["en", "fr"]
EXTRACTORS = ["ncvalue", "graph"]
DEFAULT_FRACTIONS = [0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]


def unique_gold_terms(gold_tokens_by_doc: dict, texts: dict) -> set[str]:
    s = set()
    for doc_id, toks in gold_tokens_by_doc.items():
        raw = texts[doc_id]
        for start, end in ae.gold_term_spans(toks):
            s.add(raw[start:end].lower())
    return s


def extract_with_patterns(rows, lang, min_freq, patterns: str):
    kwargs = {"prep_patterns": False, "all_candidate_patterns": False}
    if patterns == "prep-patterns":
        kwargs["prep_patterns"] = True
    elif patterns == "all-candidate-patterns":
        kwargs["all_candidate_patterns"] = True
    return extract_candidates(rows, lang, min_tokens=1, max_tokens=6, min_freq=min_freq, **kwargs)


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--corpus-root", default="corpus_acter")
    pa.add_argument("--out-dir", default="benchmark_results/candidate_patterns")
    pa.add_argument("--patterns", choices=["prep-patterns", "all-candidate-patterns"], required=True,
                     help="Quelle grammaire étendue comparer à la baseline (noun_chunks seul)")
    pa.add_argument("--domains", default=",".join(DOMAINS))
    pa.add_argument("--langs", default=",".join(LANGS))
    pa.add_argument("--min-freq", type=int, default=1,
                     help="Recommandé 1 sur ACTER (corpus de domaine restreint, voir CLAUDE.md)")
    pa.add_argument("--fractions", default=",".join(str(f) for f in DEFAULT_FRACTIONS),
                     help="Fractions de n_gold_terms pour le sweep top-N, séparées par des virgules")
    args = pa.parse_args()

    corpus_root = Path(args.corpus_root)
    if not corpus_root.exists():
        sys.exit(f"ERROR: {corpus_root} introuvable — lancer `make corpus-acter` d'abord")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fractions = [float(f) for f in args.fractions.split(",")]
    domains = args.domains.split(",")
    langs = args.langs.split(",")

    cand_summary = {False: {"tp": 0, "gold": 0, "n_cand": 0}, True: {"tp": 0, "gold": 0, "n_cand": 0}}
    totals = {(e, pat, f): {"tp": 0, "fp": 0, "fn": 0}
              for e in EXTRACTORS for pat in (False, True) for f in fractions}
    per_combo: list[dict] = []

    for lang in langs:
        for domain in domains:
            domain_dir = corpus_root / lang / domain
            if not domain_dir.exists():
                print(f"  [skip] {domain}/{lang} absent du corpus", file=sys.stderr)
                continue
            print(f"== {domain} ({lang}) ==", file=sys.stderr)
            texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
            gold_terms = unique_gold_terms(gold_tokens_by_doc, texts)
            n_gold_terms = len(gold_terms)
            rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]

            combo_result = {"domain": domain, "lang": lang, "n_gold_terms": n_gold_terms}

            for use_patterns in (False, True):
                candidates, total_tokens, per_doc_tokens = extract_with_patterns(
                    rows, lang, args.min_freq, args.patterns if use_patterns else "none"
                )
                cand_terms = {c.term.lower() for c in candidates}
                tp = len(gold_terms & cand_terms)
                cand_summary[use_patterns]["tp"] += tp
                cand_summary[use_patterns]["gold"] += n_gold_terms
                cand_summary[use_patterns]["n_cand"] += len(candidates)
                combo_result[f"n_candidates_{use_patterns}"] = len(candidates)
                combo_result[f"candidate_recall_{use_patterns}"] = round(tp / n_gold_terms, 4) if n_gold_terms else None

                for extractor in EXTRACTORS:
                    scored, _ = score_extracted_candidates(
                        list(candidates), per_doc_tokens, total_tokens, extractor,
                        auto_threshold=50000, lang=lang, dict_path=None,
                    )
                    for fraction in fractions:
                        n = max(1, round(n_gold_terms * fraction))
                        top_n = scored[:n]
                        pred_spans = ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in top_n]})
                        prf = ae.token_level_prf(gold_tokens_by_doc, pred_spans)
                        t = totals[(extractor, use_patterns, fraction)]
                        t["tp"] += prf["tp"]
                        t["fp"] += prf["fp"]
                        t["fn"] += prf["fn"]

            per_combo.append(combo_result)

    print()
    print(f"== 1) Rappel candidat oracle + volume (micro-moyenne, motif={args.patterns}) ==")
    for use_patterns in (False, True):
        c = cand_summary[use_patterns]
        r = c["tp"] / c["gold"] if c["gold"] else 0.0
        label = args.patterns if use_patterns else "baseline (noun_chunks seul)"
        print(f"{label:<32} n_candidats={c['n_cand']:>7}  rappel_global={r:.4f}")

    print()
    print("== 2) Sweep top-N (fraction de n_gold_terms), micro-moyenne ==")
    sweep_rows = []
    for extractor in EXTRACTORS:
        for fraction in fractions:
            vals = {}
            for use_patterns in (False, True):
                t = totals[(extractor, use_patterns, fraction)]
                p = t["tp"] / (t["tp"] + t["fp"]) if (t["tp"] + t["fp"]) else 0.0
                r = t["tp"] / (t["tp"] + t["fn"]) if (t["tp"] + t["fn"]) else 0.0
                f1 = 2 * p * r / (p + r) if (p + r) else 0.0
                vals[use_patterns] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}
            delta = vals[True]["f1"] - vals[False]["f1"]
            print(f"{extractor:<8} frac={fraction:>4.2f} F1(baseline)={vals[False]['f1']:.3f} "
                  f"F1({args.patterns})={vals[True]['f1']:.3f} Delta={delta:+.3f}")
            sweep_rows.append({"extractor": extractor, "fraction": fraction,
                                "baseline": vals[False], args.patterns.replace("-", "_"): vals[True],
                                "delta_f1": round(delta, 4)})

    result = {
        "patterns": args.patterns, "min_freq": args.min_freq, "fractions": fractions,
        "candidate_recall": {
            "baseline": {"n_candidates": cand_summary[False]["n_cand"],
                         "recall": round(cand_summary[False]["tp"] / cand_summary[False]["gold"], 4) if cand_summary[False]["gold"] else None},
            args.patterns.replace("-", "_"): {"n_candidates": cand_summary[True]["n_cand"],
                                               "recall": round(cand_summary[True]["tp"] / cand_summary[True]["gold"], 4) if cand_summary[True]["gold"] else None},
        },
        "topn_sweep": sweep_rows,
        "per_domain_lang": per_combo,
    }
    out_path = out_dir / f"bench_{args.patterns.replace('-', '_')}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON -> {out_path}")


if __name__ == "__main__":
    main()
