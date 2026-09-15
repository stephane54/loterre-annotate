#!/usr/bin/env python3
"""Benchmark du signal de spécificité (Weirdness Ratio vs langue générale,
src/loterre_specificity.py) contre le gold ACTER.

Consolidation des scripts ad hoc de la session 2026-09-11 (bench_specificity.py,
bench_specificity_filter.py, bench_specificity_threshold_sweep.py,
bench_specificity_embed.py) — trois modes, mêmes mesures que journalisées dans
planification/analyse_benchmarks_extraction.md :

- `standalone` : classement autonome (spécificité seule) vs ncvalue/graph —
  rejeté comme 4ᵉ --extractor (plus faible aux coupures serrées).
- `filter-sweep` : --specificity-filter-pctl (ncvalue), balayage de percentile
  — 40% est le point optimal mesuré (F1 top-N=1.5x : 0.455→0.518).
- `embed` : --specificity-top-pct comme troisième signal de suggestion pour
  embed (niveau 3), seul et combiné au signal structurel — nécessite
  sentence-transformers/torch. F1 embed+structurel+spécificité(10%) = 0.314
  contre 0.270 pour structurel seul, mais précision isolée du niveau 3 basse
  (~0.27-0.30) — d'où le choix de le garder opt-in (voir CLAUDE.md).

Usage:
    make corpus-acter   # si pas déjà fait
    python3 scripts/evaluation/bench_specificity.py --mode standalone
    python3 scripts/evaluation/bench_specificity.py --mode filter-sweep --percentiles 0,10,20,30,40,50,60,70
    python3 scripts/evaluation/bench_specificity.py --mode embed --top-pcts 2,5,10
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
from loterre_specificity import score_candidates_specificity  # noqa: E402

DOMAINS = ["corp", "equi", "htfl", "wind"]
LANGS = ["en", "fr"]
DEFAULT_FRACTIONS = [0.1, 0.5, 1.0, 1.5]
DEFAULT_PERCENTILES = [0, 10, 20, 30, 40, 50, 60, 70]
DEFAULT_TOP_PCTS = [2.0, 5.0, 10.0]
ENRICHMENT_THRESHOLD = 0.95


def unique_gold_terms(gold_tokens_by_doc: dict, texts: dict) -> set[str]:
    s = set()
    for doc_id, toks in gold_tokens_by_doc.items():
        raw = texts[doc_id]
        for start, end in ae.gold_term_spans(toks):
            s.add(raw[start:end].lower())
    return s


def iter_domains(corpus_root: Path, domains: list[str], langs: list[str]):
    for lang in langs:
        for domain in domains:
            domain_dir = corpus_root / lang / domain
            if not domain_dir.exists():
                print(f"  [skip] {domain}/{lang} absent du corpus", file=sys.stderr)
                continue
            print(f"== {domain} ({lang}) ==", file=sys.stderr)
            yield domain, lang, domain_dir


def _prf_totals_to_row(t: dict) -> dict:
    p = t["tp"] / (t["tp"] + t["fp"]) if (t["tp"] + t["fp"]) else 0.0
    r = t["tp"] / (t["tp"] + t["fn"]) if (t["tp"] + t["fn"]) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


# ── mode "standalone" : classement autonome spécificité vs ncvalue/graph ──────

def run_standalone(args) -> dict:
    corpus_root = Path(args.corpus_root)
    fractions = [float(f) for f in args.fractions.split(",")]
    methods = ["ncvalue", "graph", "specificity"]
    totals = {(m, f): {"tp": 0, "fp": 0, "fn": 0} for m in methods for f in fractions}

    for domain, lang, domain_dir in iter_domains(corpus_root, args.domains.split(","), args.langs.split(",")):
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        gold_terms = unique_gold_terms(gold_tokens_by_doc, texts)
        n_gold_terms = len(gold_terms)
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )
        for method in methods:
            if method == "specificity":
                scored = score_candidates_specificity(list(candidates), per_doc_tokens, lang)
                scored.sort(key=lambda c: -(c.specificity_score or 0.0))
            else:
                scored, _ = score_extracted_candidates(
                    list(candidates), per_doc_tokens, total_tokens, method,
                    auto_threshold=50000, lang=lang, dict_path=None,
                )
            for fraction in fractions:
                n = max(1, round(n_gold_terms * fraction))
                pred_spans = ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in scored[:n]]})
                prf = ae.token_level_prf(gold_tokens_by_doc, pred_spans)
                t = totals[(method, fraction)]
                t["tp"] += prf["tp"]; t["fp"] += prf["fp"]; t["fn"] += prf["fn"]

    print()
    print("== Classement autonome : specificite vs ncvalue/graph, micro-moyenne ==")
    rows_out = []
    for fraction in fractions:
        for method in methods:
            row = _prf_totals_to_row(totals[(method, fraction)])
            print(f"{method:<12} frac={fraction:>4.2f} P={row['precision']:.3f} R={row['recall']:.3f} F1={row['f1']:.3f}")
            rows_out.append({"method": method, "fraction": fraction, **row})
    return {"mode": "standalone", "min_freq": args.min_freq, "rows": rows_out}


# ── mode "filter-sweep" : --specificity-filter-pctl (ncvalue) ────────────────

def run_filter_sweep(args) -> dict:
    corpus_root = Path(args.corpus_root)
    fractions = [float(f) for f in args.fractions.split(",")]
    percentiles = [float(p) for p in args.percentiles.split(",")]
    totals = {(pctl, f): {"tp": 0, "fp": 0, "fn": 0} for pctl in percentiles for f in fractions}

    for domain, lang, domain_dir in iter_domains(corpus_root, args.domains.split(","), args.langs.split(",")):
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        gold_terms = unique_gold_terms(gold_tokens_by_doc, texts)
        n_gold_terms = len(gold_terms)
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )
        score_candidates_specificity(candidates, per_doc_tokens, lang)
        sorted_scores = sorted(c.specificity_score or 0.0 for c in candidates)
        n_cand = len(sorted_scores)

        for pctl in percentiles:
            if pctl <= 0:
                cand_set = candidates
            else:
                cutoff = sorted_scores[min(int(n_cand * pctl / 100), n_cand - 1)]
                cand_set = [c for c in candidates if (c.specificity_score or 0.0) >= cutoff]
            scored, _ = score_extracted_candidates(
                list(cand_set), per_doc_tokens, total_tokens, "ncvalue",
                auto_threshold=50000, lang=lang, dict_path=None,
            )
            for fraction in fractions:
                n = max(1, round(n_gold_terms * fraction))
                pred_spans = ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in scored[:n]]})
                prf = ae.token_level_prf(gold_tokens_by_doc, pred_spans)
                t = totals[(pctl, fraction)]
                t["tp"] += prf["tp"]; t["fp"] += prf["fp"]; t["fn"] += prf["fn"]

    print()
    print("== Balayage seuil filtre specificite (ncvalue seul), micro-moyenne ==")
    hdr = f"{'pctl_retire':>11}" + "".join(f"  F1@{f:.2f}".rjust(10) for f in fractions)
    print(hdr)
    rows_out = []
    for pctl in percentiles:
        row = f"{pctl:>10}%"
        f1s = {}
        for fraction in fractions:
            r = _prf_totals_to_row(totals[(pctl, fraction)])
            row += f"{r['f1']:>10.3f}"
            f1s[fraction] = r
        print(row)
        rows_out.append({"percentile_removed": pctl, "by_fraction": f1s})
    return {"mode": "filter-sweep", "min_freq": args.min_freq, "rows": rows_out}


# ── mode "embed" : troisième signal de suggestion (niveau 3) ─────────────────

def run_embed(args) -> dict:
    corpus_root = Path(args.corpus_root)
    top_pcts = [float(p) for p in args.top_pcts.split(",")]
    from loterre_embed import embed_vocabulary_terms, get_embed_model, load_vocabulary_terms, score_candidates_embed
    from loterre_extract_cli import _attach_structural_signal

    model = get_embed_model()
    embed_only_totals = {"tp": 0, "fp": 0, "fn": 0}
    structural_totals = {"tp": 0, "fp": 0, "fn": 0}
    specificity_totals = {p: {"tp": 0, "fp": 0, "fn": 0} for p in top_pcts}
    combo_totals = {p: {"tp": 0, "fp": 0, "fn": 0} for p in top_pcts}
    tier3_only_totals = {p: {"tp": 0, "fp": 0, "fn": 0} for p in top_pcts}

    for domain, lang, domain_dir in iter_domains(corpus_root, args.domains.split(","), args.langs.split(",")):
        terms_path = (domain_dir / "annotated" / "annotations" / "unique_annotation_lists"
                      / f"{domain}_{lang}_terms.tsv")
        if not terms_path.exists():
            continue
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        all_terms = ae.read_unique_terms(terms_path)
        seed_terms, holdout_terms = ae.split_seed_holdout(all_terms, fraction=0.5, seed=42)
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )

        seed_dict_path = Path(args.out_dir) / f"tmp_seed_embed_{domain}_{lang}.jsonl"
        seed_dict_path.parent.mkdir(parents=True, exist_ok=True)
        with seed_dict_path.open("w", encoding="utf-8") as f:
            for term in seed_terms:
                f.write(json.dumps({"id": term, "pref": term}, ensure_ascii=False) + "\n")
        vocab_terms = load_vocabulary_terms(str(seed_dict_path))
        vocab_embeddings = embed_vocabulary_terms(model, vocab_terms)
        score_candidates_embed(candidates, model, vocab_embeddings)
        seed_dict_path.unlink(missing_ok=True)

        _attach_structural_signal(candidates, per_doc_tokens, total_tokens, 50000)
        score_candidates_specificity(candidates, per_doc_tokens, lang)

        n_total = len(candidates)
        structural_top_n = max(1, round(n_total * 2.0 / 100))
        top_n_by_pct = {p: max(1, round(n_total * p / 100)) for p in top_pcts}

        embed_only, combined_structural = [], []
        combined_specificity = {p: [] for p in top_pcts}
        combined_both = {p: [] for p in top_pcts}
        tier3_only = {p: [] for p in top_pcts}

        for c in candidates:
            if c.term.lower() in seed_terms:
                continue
            is_embed = c.score >= ENRICHMENT_THRESHOLD
            is_structural = c.structural_rank is not None and c.structural_rank <= structural_top_n
            if is_embed:
                embed_only.append(c)
                combined_structural.append(c)
                for p in top_pcts:
                    combined_specificity[p].append(c)
                    combined_both[p].append(c)
                continue
            if is_structural:
                combined_structural.append(c)
            for p in top_pcts:
                is_specific = c.specificity_rank is not None and c.specificity_rank <= top_n_by_pct[p]
                if is_specific:
                    combined_specificity[p].append(c)
                if is_structural or is_specific:
                    combined_both[p].append(c)
                if is_specific and not is_structural:
                    tier3_only[p].append(c)

        def prf(cands):
            return ae.token_level_prf(
                gold_tokens_by_doc, ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in cands]}),
                texts=texts, exclude_terms=seed_terms,
            )

        for totals_dict, cands in ((embed_only_totals, embed_only), (structural_totals, combined_structural)):
            r = prf(cands)
            totals_dict["tp"] += r["tp"]; totals_dict["fp"] += r["fp"]; totals_dict["fn"] += r["fn"]
        for p in top_pcts:
            for totals_dict, cands in ((specificity_totals[p], combined_specificity[p]),
                                        (combo_totals[p], combined_both[p]),
                                        (tier3_only_totals[p], tier3_only[p])):
                r = prf(cands)
                totals_dict["tp"] += r["tp"]; totals_dict["fp"] += r["fp"]; totals_dict["fn"] += r["fn"]

    print()
    print("== Embed seul vs +structurel(2%) vs +specificite(X%) seul, micro-moyenne ==")
    rows_out = {"embed_only": _prf_totals_to_row(embed_only_totals),
                "structural_2pct": _prf_totals_to_row(structural_totals)}
    print(f"embed seul                     {rows_out['embed_only']}")
    print(f"embed + structurel (2%)        {rows_out['structural_2pct']}")
    rows_out["specificity_alone"] = {}
    for p in top_pcts:
        row = _prf_totals_to_row(specificity_totals[p])
        rows_out["specificity_alone"][p] = row
        print(f"embed + specificite ({p:.0f}%)      {row}")

    print()
    print("== Combinaison structurel(2%) OU specificite(X%), et niveau 3 isolé ==")
    rows_out["combined"] = {}
    rows_out["tier3_isolated"] = {}
    for p in top_pcts:
        combo_row = _prf_totals_to_row(combo_totals[p])
        tier3_row = _prf_totals_to_row(tier3_only_totals[p])
        rows_out["combined"][p] = combo_row
        rows_out["tier3_isolated"][p] = tier3_row
        print(f"structurel(2%) OU specificite({p:.0f}%)  combiné={combo_row}  niveau3_isolé={tier3_row}")

    return {"mode": "embed", "min_freq": args.min_freq, "top_pcts": top_pcts, "results": rows_out}


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--mode", choices=["standalone", "filter-sweep", "embed"], required=True)
    pa.add_argument("--corpus-root", default="corpus_acter")
    pa.add_argument("--out-dir", default="benchmark_results/specificity")
    pa.add_argument("--domains", default=",".join(DOMAINS))
    pa.add_argument("--langs", default=",".join(LANGS))
    pa.add_argument("--min-freq", type=int, default=1)
    pa.add_argument("--fractions", default=",".join(str(f) for f in DEFAULT_FRACTIONS),
                     help="[standalone/filter-sweep] Fractions de n_gold_terms pour la coupure top-N")
    pa.add_argument("--percentiles", default=",".join(str(p) for p in DEFAULT_PERCENTILES),
                     help="[filter-sweep] Percentiles de candidats retirés à tester")
    pa.add_argument("--top-pcts", default=",".join(str(p) for p in DEFAULT_TOP_PCTS),
                     help="[embed] --specificity-top-pct à tester")
    args = pa.parse_args()

    corpus_root = Path(args.corpus_root)
    if not corpus_root.exists():
        sys.exit(f"ERROR: {corpus_root} introuvable — lancer `make corpus-acter` d'abord")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "standalone":
        result = run_standalone(args)
    elif args.mode == "filter-sweep":
        result = run_filter_sweep(args)
    else:
        result = run_embed(args)

    out_path = out_dir / f"bench_specificity_{args.mode}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON -> {out_path}")


if __name__ == "__main__":
    main()
