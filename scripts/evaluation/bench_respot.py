#!/usr/bin/env python3
"""Test de l'hypothèse « occurrences » (comparaison TermSuite, 2026-10-09).

Nos candidats ne portent que les occurrences où spaCy a produit exactement ce
groupe nominal (`_register_span` dans loterre_extract_cli.py) : un terme inclus
dans un groupe plus long, ou écrit avec une autre casse, n'y est pas compté.
TermSuite, lui, repère toutes les occurrences de chaque terme.

Ce script garde EXACTEMENT les mêmes candidats et le même classement (même
coupure qu'acter_eval.py), et compare deux notations token-level :
  - "actuel" : occurrences telles qu'extraites ;
  - "repéré" : toutes les occurrences du texte du candidat dans le document
    (insensible à la casse, bornes de mot).
Pour ncvalue/graph à froid, et pour les listes embed 1 et 1+2 (protocole
seed/holdout et seuils de production d'acter_eval.py).

Usage :
    python3 scripts/evaluation/bench_respot.py --out benchmark_results/respot/respot_results.json
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from acter_eval import (DOMAINS, LANGS, gold_term_spans, load_domain_gold,  # noqa: E402
                        predicted_spans_by_doc, read_unique_terms, run_extraction,
                        split_seed_holdout, token_level_prf)


def respot(candidates: list[dict], texts: dict[str, str]) -> list[dict]:
    out = []
    for c in candidates:
        pat = re.compile(r"(?<!\w)" + re.escape(c["term"]) + r"(?!\w)", re.IGNORECASE)
        occs = [{"doc_id": d, "start": m.start(), "end": m.end()}
                for d, t in texts.items() for m in pat.finditer(t)]
        out.append({"term": c["term"], "occurrences": occs or c.get("occurrences", [])})
    return out


def micro(rows: list[dict]) -> dict:
    tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--corpus-root", default="corpus_acter")
    pa.add_argument("--extract-cli", default="src/loterre_extract_cli.py")
    pa.add_argument("--min-freq", type=int, default=1)
    pa.add_argument("--enrichment-threshold", type=float, default=0.95)
    pa.add_argument("--structural-top-pct", type=float, default=2.0)
    pa.add_argument("--out", required=True)
    args = pa.parse_args()

    acc = defaultdict(list)
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="respot_"))
    for domain in DOMAINS:
        for lang in LANGS:
            ddir = Path(args.corpus_root) / lang / domain
            texts, gold, _ = load_domain_gold(ddir)
            n_gold = len({texts[d][s:e].lower() for d, toks in gold.items() for s, e in gold_term_spans(toks)})
            jsonl = tmp / f"{domain}_{lang}.jsonl"
            jsonl.write_text("".join(json.dumps({"id": d, "value": t}, ensure_ascii=False) + "\n"
                                     for d, t in texts.items()), encoding="utf-8")
            row = {"domain": domain, "lang": lang}

            # À froid : ncvalue / graph, coupure top-N = termes gold uniques
            for ext in ("ncvalue", "graph"):
                top = run_extraction(Path(args.extract_cli), jsonl, lang, ext, args.min_freq)["candidates"][:n_gold]
                for mode, cands in (("actuel", top), ("repéré", respot(top, texts))):
                    prf = token_level_prf(gold, predicted_spans_by_doc({"candidates": cands}))
                    row[f"{ext}_{mode}"] = prf
                    acc[f"{ext}_{mode}"].append(prf)

            # Avec vocabulaire : embed, listes de production (seed/holdout)
            terms = read_unique_terms(ddir / "annotated" / "annotations" / "unique_annotation_lists"
                                      / f"{domain}_{lang}_terms.tsv")
            seed, _ = split_seed_holdout(terms, fraction=0.5)
            seed_dict = tmp / f"{domain}_{lang}_seed.jsonl"
            seed_dict.write_text("".join(json.dumps({"id": t, "pref": t}, ensure_ascii=False) + "\n" for t in seed),
                                 encoding="utf-8")
            cands = run_extraction(Path(args.extract_cli), jsonl, lang, "embed", args.min_freq,
                                   dict_path=seed_dict)["candidates"]
            top_struct = max(1, round(len(cands) * args.structural_top_pct / 100))
            l1, l12 = [], []
            for c in cands:
                if c["term"].lower() in seed:
                    continue
                if c.get("score", 0.0) >= args.enrichment_threshold:
                    l1.append(c)
                    l12.append(c)
                elif c.get("structural_rank") is not None and c["structural_rank"] <= top_struct:
                    l12.append(c)
            for name, lst in (("liste1", l1), ("listes12", l12)):
                for mode, cs in (("actuel", lst), ("repéré", respot(lst, texts))):
                    prf = token_level_prf(gold, predicted_spans_by_doc({"candidates": cs}), texts=texts,
                                          exclude_terms=seed)
                    row[f"{name}_{mode}"] = prf
                    acc[f"{name}_{mode}"].append(prf)
            rows.append(row)
            print(domain, lang, {k: v["f1"] for k, v in row.items() if isinstance(v, dict)}, flush=True)

    totals = {k: micro(v) for k, v in acc.items()}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"results": rows, "totals": totals}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("\nTOTAL (P / R / F1)")
    for base in ("ncvalue", "graph", "liste1", "listes12"):
        a, b = totals[f"{base}_actuel"], totals[f"{base}_repéré"]
        print(f"{base:9} actuel {a['precision']:.3f} / {a['recall']:.3f} / {a['f1']:.3f}   "
              f"repéré {b['precision']:.3f} / {b['recall']:.3f} / {b['f1']:.3f}")


if __name__ == "__main__":
    main()
