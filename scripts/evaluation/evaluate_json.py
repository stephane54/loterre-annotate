#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def load_jsonl(path: str) -> Dict[str, dict]:
    data = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                data[obj["id"]] = obj
    return data


def load_pred(path: str) -> Dict[str, dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {row["id"]: row for row in payload.get("results", [])}


def norm(s: str, case_sensitive: bool = False, strip_spaces: bool = True) -> str:
    if s is None:
        s = ""
    if strip_spaces:
        s = " ".join(str(s).split())
    return s if case_sensitive else s.lower()


def key_from_match(
    match: dict,
    mode: str,
    case_sensitive: bool,
    strip_spaces: bool,
    include_rule: bool = False
) -> Tuple:
    found = norm(match.get("found", ""), case_sensitive, strip_spaces)
    pref = norm(match.get("pref", ""), case_sensitive, strip_spaces)
    label = norm(match.get("label", ""), case_sensitive, strip_spaces)
    start = match.get("start")
    end = match.get("end")
    rule = match.get("rule", "")

    if mode == "found_pref":
        key = (found, pref)
    elif mode == "pref_only":
        key = (pref,)
    elif mode == "span_pref":
        key = (start, end, pref)
    elif mode == "found_only":
        key = (found,)
    elif mode == "label_pref":
        key = (label, pref)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    if include_rule:
        key = key + (rule,)
    return key


def build_set(matches: List[dict], mode: str, case_sensitive: bool, strip_spaces: bool, include_rule: bool) -> set:
    return {key_from_match(m, mode, case_sensitive, strip_spaces, include_rule) for m in matches}


def safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def evaluate(
    gold: Dict[str, dict],
    pred: Dict[str, dict],
    mode: str,
    case_sensitive: bool,
    strip_spaces: bool,
    include_rule: bool,
) -> dict:
    tp = fp = fn = 0
    per_doc = []
    error_counter = Counter()
    rule_counter = Counter()

    for doc_id, gold_doc in gold.items():
        gold_matches = gold_doc.get("expected_matches", [])
        pred_matches = pred.get(doc_id, {}).get("matches", [])

        gold_set = build_set(gold_matches, mode, case_sensitive, strip_spaces, include_rule)
        pred_set = build_set(pred_matches, mode, case_sensitive, strip_spaces, include_rule)

        doc_tp = gold_set & pred_set
        doc_fp = pred_set - gold_set
        doc_fn = gold_set - pred_set

        tp += len(doc_tp)
        fp += len(doc_fp)
        fn += len(doc_fn)

        for item in doc_fp:
            error_counter[("FP", item)] += 1
        for item in doc_fn:
            error_counter[("FN", item)] += 1

        for m in pred_matches:
            rule_counter[m.get("rule", "")] += 1

        per_doc.append({
            "id": doc_id,
            "tp": len(doc_tp),
            "fp": len(doc_fp),
            "fn": len(doc_fn),
            "missing": sorted(map(str, doc_fn)),
            "spurious": sorted(map(str, doc_fp)),
        })

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)

    return {
        "mode": mode,
        "case_sensitive": case_sensitive,
        "strip_spaces": strip_spaces,
        "include_rule": include_rule,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "top_errors": [{"type": t, "item": str(item), "count": c} for (t, item), c in error_counter.most_common(20)],
        "pred_rules": dict(rule_counter),
        "per_doc": per_doc,
    }


def write_csv(result: dict, path: str) -> None:
    rows = result.get("per_doc", [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["id", "tp", "fp", "fn", "missing", "spurious"])
        w.writeheader()
        for row in rows:
            row2 = dict(row)
            row2["missing"] = " | ".join(row2["missing"])
            row2["spurious"] = " | ".join(row2["spurious"])
            w.writerow(row2)


def write_markdown(result: dict, path: str) -> None:
    lines = [
        "# Evaluation report",
        "",
        f"- mode: `{result['mode']}`",
        f"- case_sensitive: `{result['case_sensitive']}`",
        f"- strip_spaces: `{result['strip_spaces']}`",
        f"- include_rule: `{result['include_rule']}`",
        "",
        "## Global metrics",
        "",
        f"- TP: {result['tp']}",
        f"- FP: {result['fp']}",
        f"- FN: {result['fn']}",
        f"- Precision: {result['precision']}",
        f"- Recall: {result['recall']}",
        f"- F1: {result['f1']}",
        "",
        "## Top errors",
        "",
    ]
    for err in result["top_errors"]:
        lines.append(f"- {err['type']} — `{err['item']}` — {err['count']}")
    lines.extend(["", "## Per-document results", ""])
    lines.append("| id | tp | fp | fn |")
    lines.append("|---|---:|---:|---:|")
    for row in result["per_doc"]:
        lines.append(f"| {row['id']} | {row['tp']} | {row['fp']} | {row['fn']} |")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="Advanced evaluator for Loterre outputs")
    p.add_argument("--gold", required=True, help="Gold JSONL file with expected_matches")
    p.add_argument("--pred", required=True, help="Prediction JSON file from --silent or --api")
    p.add_argument(
        "--mode",
        default="found_pref",
        choices=["found_pref", "pref_only", "span_pref", "found_only", "label_pref"],
        help="Comparison mode"
    )
    p.add_argument("--case-sensitive", action="store_true", help="Enable case-sensitive comparison")
    p.add_argument("--keep-spaces", action="store_true", help="Do not normalize repeated whitespace")
    p.add_argument("--include-rule", action="store_true", help="Include match rule in comparison key")
    p.add_argument("--out-json", help="Optional JSON output path")
    p.add_argument("--out-csv", help="Optional CSV output path")
    p.add_argument("--out-md", help="Optional Markdown report path")
    args = p.parse_args()

    gold = load_jsonl(args.gold)
    pred = load_pred(args.pred)

    result = evaluate(
        gold=gold,
        pred=pred,
        mode=args.mode,
        case_sensitive=args.case_sensitive,
        strip_spaces=not args.keep_spaces,
        include_rule=args.include_rule,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.out_json:
        Path(args.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out_csv:
        write_csv(result, args.out_csv)
    if args.out_md:
        write_markdown(result, args.out_md)


if __name__ == "__main__":
    main()
