#!/usr/bin/env python3
"""Évalue des sorties TermSuite sur le gold ACTER, avec le protocole exact
d'acter_eval.py (token-level, sans entités nommées, coupure top-N = nombre de
termes gold uniques du domaine), pour comparer TermSuite à ncvalue/graph.

Entrée : un export JSON TermSuite par domaine/langue (`--json`, occurrences
incluses — défaut de TerminologyExtractorCLI), nommé acter_<domaine>_<langue>.json,
produit sur les textes annotated/texts d'ACTER (mêmes fichiers qu'acter_eval).
Les offsets begin/end des occurrences TermSuite sont des offsets caractères dans
ces fichiers, utilisés tels quels. Classement : propriété `rank` de TermSuite
(spécificité décroissante, son classement par défaut).

Avec --compare acter_results.json (sortie d'acter_eval.py), ajoute ncvalue et
graph au tableau.

Usage :
    python3 scripts/evaluation/termsuite_acter_eval.py \
        --termsuite-dir benchmark_results/termsuite/outputs_v2 \
        --compare benchmark_results/termsuite/acter_cold/acter_results.json \
        --out benchmark_results/termsuite/termsuite_acter_results

    # protocole semi-supervisé (embed, listes de production) :
    python3 scripts/evaluation/acter_eval.py --min-freq 1 --skip-cold \
        --out-dir benchmark_results/termsuite/acter_embed
    python3 scripts/evaluation/termsuite_acter_eval.py \
        --termsuite-dir benchmark_results/termsuite/outputs_v2 \
        --seeded-compare benchmark_results/termsuite/acter_embed \
        --out benchmark_results/termsuite/termsuite_vs_embed
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from acter_eval import (DOMAINS, LANGS, gold_term_spans, load_domain_gold,  # noqa: E402
                        predicted_spans_by_doc, read_unique_terms, split_seed_holdout,
                        token_level_prf)


def termsuite_candidates(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    doc_of = {int(k): Path(v).stem for k, v in data["input_sources"].items()}
    occ_by_term: dict[str, list[dict]] = defaultdict(list)
    for o in data.get("occurrences", []):
        occ_by_term[o["tid"]].append({"doc_id": doc_of[o["file"]], "start": o["begin"], "end": o["end"]})
    terms = sorted(data["terms"], key=lambda t: t["props"]["rank"])
    return [{"term": t["props"]["pilot"], "occurrences": occ_by_term[t["props"]["key"]]} for t in terms]


def micro(rows: list[dict]) -> dict:
    tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def fmt(v: dict) -> str:
    return f"{v['precision']:.3f} / {v['recall']:.3f} / **{v['f1']:.3f}**"


def seeded_comparison(args) -> None:
    """Protocole semi-supervisé d'acter_eval.py (même split seed/holdout,
    seed=42, fraction 0.5 ; tokens des termes seed exclus de la notation).
    TermSuite n'utilise pas le vocabulaire seed : on le note (A) avec la même
    coupure oracle que embed (top-N = nb de termes holdout), (B) à budget égal
    aux listes de production — mêmes nombres de suggestions que la liste 1
    (embed seul) et que les listes 1+2, candidats déjà dans le seed retirés
    comme en production."""
    d = Path(args.seeded_compare)
    emb = {(r["domain"], r["lang"]): r for r in json.loads((d / "acter_results_embed_seeded.json").read_text())}
    struct = {(r["domain"], r["lang"]): r
              for r in json.loads((d / "acter_results_structural_signal.json").read_text())}
    rows, acc = [], defaultdict(list)
    for domain in DOMAINS:
        for lang in LANGS:
            domain_dir = Path(args.corpus_root) / lang / domain
            texts, gold, _ = load_domain_gold(domain_dir)
            terms = read_unique_terms(domain_dir / "annotated" / "annotations" / "unique_annotation_lists"
                                      / f"{domain}_{lang}_terms.tsv")
            seed, holdout = split_seed_holdout(terms, fraction=0.5)
            cands = termsuite_candidates(Path(args.termsuite_dir) / f"acter_{domain}_{lang}.json")
            unseen = [c for c in cands if c["term"].lower() not in seed]
            s = struct[(domain, lang)]
            k1, k12 = s["embed_only"]["n_flagged"], s["combined"]["n_flagged"]

            def score(selected):
                return token_level_prf(gold, predicted_spans_by_doc({"candidates": selected}),
                                       texts=texts, exclude_terms=seed)

            row = {"domain": domain, "lang": lang, "n_holdout": len(holdout), "k_list1": k1, "k_list12": k12,
                   "embed_topn": emb[(domain, lang)]["embed_seeded"], "termsuite_topn": score(cands[:len(holdout)]),
                   "list1": s["embed_only"], "termsuite_k1": score(unseen[:k1]),
                   "list12": s["combined"], "termsuite_k12": score(unseen[:k12])}
            for key in ("embed_topn", "termsuite_topn", "list1", "termsuite_k1", "list12", "termsuite_k12"):
                acc[key].append(row[key])
            rows.append(row)
            print(domain, lang, {k: row[k]["f1"] for k in ("embed_topn", "termsuite_topn", "list1",
                                                          "termsuite_k1", "list12", "termsuite_k12")}, flush=True)
    totals = {k: micro(v) for k, v in acc.items()}
    out = Path(args.out)
    out.with_suffix(".json").write_text(json.dumps({"results": rows, "totals": totals}, ensure_ascii=False,
                                                   indent=2), encoding="utf-8")
    lines = ["| Domaine | Lang | holdout | embed top-N | TermSuite top-N | K liste 1 | liste 1 (embed) | "
             "TermSuite top-K1 | K listes 1+2 | listes 1+2 | TermSuite top-K12 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['domain']} | {r['lang']} | {r['n_holdout']} | {fmt(r['embed_topn'])} | "
                     f"{fmt(r['termsuite_topn'])} | {r['k_list1']} | {fmt(r['list1'])} | {fmt(r['termsuite_k1'])} | "
                     f"{r['k_list12']} | {fmt(r['list12'])} | {fmt(r['termsuite_k12'])} |")
    t = totals
    lines.append(f"| **TOTAL** | | | {fmt(t['embed_topn'])} | {fmt(t['termsuite_topn'])} | | {fmt(t['list1'])} | "
                 f"{fmt(t['termsuite_k1'])} | | {fmt(t['list12'])} | {fmt(t['termsuite_k12'])} |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--termsuite-dir", required=True)
    pa.add_argument("--corpus-root", default="corpus_acter")
    pa.add_argument("--compare", help="acter_results.json d'acter_eval.py (ncvalue/graph)")
    pa.add_argument("--seeded-compare", metavar="DIR",
                    help="Dossier d'acter_eval.py --skip-cold (embed seed/holdout + listes de production) : "
                         "note TermSuite selon ce protocole")
    pa.add_argument("--out", required=True, help="Préfixe de sortie (.json et .md)")
    args = pa.parse_args()
    if args.seeded_compare:
        seeded_comparison(args)
        return

    compare = {}
    if args.compare:
        for r in json.loads(Path(args.compare).read_text(encoding="utf-8")):
            compare[(r["domain"], r["lang"])] = r["extractors"]

    systems = ["termsuite"] + (["ncvalue", "graph"] if compare else [])
    results, per_system = [], defaultdict(list)
    for domain in DOMAINS:
        for lang in LANGS:
            ts_path = Path(args.termsuite_dir) / f"acter_{domain}_{lang}.json"
            texts, gold, _ = load_domain_gold(Path(args.corpus_root) / lang / domain)
            n_gold = len({texts[d][s:e].lower() for d, toks in gold.items() for s, e in gold_term_spans(toks)})
            cands = termsuite_candidates(ts_path)
            top = cands[:n_gold]
            prf = token_level_prf(gold, predicted_spans_by_doc({"candidates": top}))
            prf.update(n_candidates_total=len(cands), n_candidates_kept=len(top))
            row = {"domain": domain, "lang": lang, "n_gold_terms": n_gold, "systems": {"termsuite": prf}}
            for name in systems[1:]:
                row["systems"][name] = compare[(domain, lang)][name]
            for name, v in row["systems"].items():
                per_system[name].append(v)
            results.append(row)
            print(domain, lang, {k: v["f1"] for k, v in row["systems"].items()},
                  f"termsuite {len(top)}/{len(cands)} candidats", flush=True)

    totals = {name: micro(rows) for name, rows in per_system.items()}
    by_lang = {(name, lang): micro([r["systems"][name] for r in results if r["lang"] == lang])
               for name in systems for lang in LANGS}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(
        {"results": results, "totals": totals,
         "by_lang": {f"{n}_{l}": v for (n, l), v in by_lang.items()}}, ensure_ascii=False, indent=2), encoding="utf-8")

    head = "| Domaine | Lang | Gold termes | TermSuite cand. | " + " | ".join(f"{s} P / R / F1" for s in systems) + " |"
    lines = [head, "|" + "---|" * 2 + "---:|" * (2 + len(systems))]
    for r in results:
        ts = r["systems"]["termsuite"]
        cells = [f"{v['precision']:.3f} / {v['recall']:.3f} / **{v['f1']:.3f}**" for v in r["systems"].values()]
        lines.append(f"| {r['domain']} | {r['lang']} | {r['n_gold_terms']} | {ts['n_candidates_total']} | "
                     + " | ".join(cells) + " |")
    for lang in LANGS:
        lines.append(f"| **{lang.upper()}** | | | | " + " | ".join(
            f"{by_lang[(s, lang)]['precision']:.3f} / {by_lang[(s, lang)]['recall']:.3f} / **{by_lang[(s, lang)]['f1']:.3f}**"
            for s in systems) + " |")
    lines.append("| **TOTAL** | | | | " + " | ".join(
        f"{totals[s]['precision']:.3f} / {totals[s]['recall']:.3f} / **{totals[s]['f1']:.3f}**" for s in systems) + " |")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
