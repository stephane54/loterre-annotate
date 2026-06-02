#!/usr/bin/env python3
"""
Clean gold standard files by removing annotations that are likely false positives.

This script applies two complementary strategies:

1. AUTOMATIC (applied to all gold files):
   - Remove fragment annotations (found text ends with '-' or starts with '-').
   - Remove single-token, low-confidence (score < SCORE_THRESHOLD) annotations
     where the token is a generic upper-ontology word unlikely to be a genuine
     terminology match in isolation: {"process", "quality"}.
     These words exist in the P66 ontology but are so generic that a score of
     0.7 in an unchecked context almost certainly indicates a false positive.

2. MANUAL OVERRIDES (per-file explicit corrections, encoded below):
   - Remove specific annotations identified by (doc_id, found, start) that are
     confirmed false positives after reading the text in context.
   - Used for P66_en doc 0 where cross-domain text (economics) triggered matches.

Output is written to gold_cleaned/  (originals in gold/ are never modified).
A JSON report summarises what was removed from each file.

Usage:
    python scripts/evaluation/clean_gold.py [--gold-dir gold] [--out-dir gold_cleaned]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# ── Automatic cleanup ────────────────────────────────────────────────────────

SCORE_THRESHOLD = 0.75

# Single-token generic words that are very likely FP when score < SCORE_THRESHOLD,
# evaluated ACROSS ALL DOMAIN CONTEXTS.
# Deliberately very narrow: a word belongs here only if it is generic enough that
# a score-0.7 match is almost always a false positive in every domain.
#
# "quality" → in isolation at 0.7 it typically annotates a title/label word
#             (e.g. "Quality For him…"), not a genuine ontological concept.
#
# NOT included: "process" — in synthetic corpus texts it appears explicitly as a
# named term ("the entry compares X, process, and Y"), making it a TP.
# "process" false positives in P66_en doc 0 are handled via MANUAL_REMOVALS below.
#
# NOT included: "interference", "cue", "recognition", "theory", "script", "schema",
# "ERP", "sensitization", "semantization" — all are genuine domain terms at 0.7.
GENERIC_SINGLE_TOKEN_BLOCKLIST: frozenset[str] = frozenset({"quality"})


def _is_fragment(found: str) -> bool:
    """True if the annotated surface looks like a tokenisation artefact."""
    s = found.strip()
    return s.endswith("-") or s.startswith("-")


def _is_low_score_generic(match: dict) -> bool:
    """True if this single-token annotation is a known generic word at low confidence."""
    found: str = match.get("found", "")
    score: float = match.get("score", 1.0)
    tokens = found.split()
    if len(tokens) != 1:
        return False
    if score >= SCORE_THRESHOLD:
        return False
    return found.lower() in GENERIC_SINGLE_TOKEN_BLOCKLIST


# ── Manual overrides (confirmed FPs after reading context) ───────────────────
# Structure: {gold_filename_stem: {doc_id: [(found, start)]}}
# A match is removed if (doc_id, found, start) matches exactly.
# Using the filename stem (without extension) so this works for any directory.

MANUAL_REMOVALS: dict[str, dict[str | int, list[tuple[str, int]]]] = {
    "gold_P66_en": {
        # Doc 0 — natural language text with mixed scientific / economics passages.
        "0": [
            # "event-" is a hyphenated fragment annotation caused by "event-based"
            # being split. The correct annotation "event-based prospective memory"
            # already appears later in the same document.
            ("event-", 391),
            # "developments" → "developmental process": matched in the sentence
            # "…an indication of future developments of households' consumption
            # and saving." This is economics language, not cognitive science.
            # The word is correctly a P66 concept but the usage is off-domain.
            ("developments", 1256),
            # "confidence" → "confidence judgment": in the same economics sentence
            # "standardised confidence indicator providing an indication of future
            # developments of households' consumption…". Economics sense, not memory.
            ("confidence", 1201),
            # "process" → "process": in "Working memory updating is the process
            # that replaces…". Used as a generic English connector, not as the
            # cognitive-science concept "process". Score 0.7 confirms low confidence.
            ("process", 1858),
        ],
    },
}


# ── Core logic ───────────────────────────────────────────────────────────────

def _build_removal_key(match: dict) -> tuple[str, int]:
    return (match.get("found", ""), match.get("start", -1))


def clean_matches(
    matches: list[dict],
    doc_id: str,
    file_stem: str,
) -> tuple[list[dict], list[dict]]:
    """Return (kept, removed) for one document's match list."""
    manual_keys: set[tuple[str, int]] = set()
    if file_stem in MANUAL_REMOVALS:
        for key in (doc_id, str(doc_id)):
            manual_keys.update(MANUAL_REMOVALS[file_stem].get(key, []))

    kept: list[dict] = []
    removed: list[dict] = []

    for m in matches:
        reason: str | None = None

        if _is_fragment(m.get("found", "")):
            reason = "fragment"
        elif _is_low_score_generic(m):
            reason = f"low_score_generic (score={m.get('score')}, found={m.get('found')})"
        elif _build_removal_key(m) in manual_keys:
            reason = "manual_override"

        if reason:
            removed.append({**m, "_removal_reason": reason})
        else:
            kept.append(m)

    return kept, removed


def clean_file(
    gold_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Clean one gold JSONL file. Returns a per-file summary dict."""
    file_stem = gold_path.stem
    total_docs = 0
    total_kept = 0
    total_removed = 0
    removal_log: list[dict] = []

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with gold_path.open(encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            doc_id = str(doc.get("id", total_docs))
            matches = doc.get("expected_matches", [])

            kept, removed = clean_matches(matches, doc_id, file_stem)

            doc["expected_matches"] = kept
            fout.write(json.dumps(doc, ensure_ascii=False) + "\n")

            total_docs += 1
            total_kept += len(kept)
            total_removed += len(removed)
            for r in removed:
                removal_log.append({
                    "doc_id": doc_id,
                    "found": r.get("found"),
                    "pref": r.get("pref"),
                    "score": r.get("score"),
                    "rule": r.get("rule"),
                    "start": r.get("start"),
                    "reason": r.get("_removal_reason"),
                })

    return {
        "file": str(gold_path),
        "out": str(out_path),
        "docs": total_docs,
        "kept": total_kept,
        "removed": total_removed,
        "removals": removal_log,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean gold standard JSONL files (remove likely false positives)."
    )
    parser.add_argument(
        "--gold-dir", default="gold",
        help="Directory containing gold_*.jsonl files (default: gold/)",
    )
    parser.add_argument(
        "--out-dir", default="gold_cleaned",
        help="Output directory for cleaned files (default: gold_cleaned/)",
    )
    parser.add_argument(
        "--report", default="gold_cleaned/cleanup_report.json",
        help="Path for the JSON cleanup report",
    )
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir)
    out_dir = Path(args.out_dir)
    report_path = Path(args.report)

    gold_files = sorted(gold_dir.glob("gold_*.jsonl"))
    if not gold_files:
        print(f"No gold_*.jsonl files found in {gold_dir}")
        return

    summaries: list[dict] = []
    grand_kept = 0
    grand_removed = 0

    for gf in gold_files:
        out_path = out_dir / gf.name
        summary = clean_file(gf, out_path)
        summaries.append(summary)
        grand_kept += summary["kept"]
        grand_removed += summary["removed"]
        removed_count = summary["removed"]
        flag = " ← cleaned" if removed_count else ""
        print(f"  {gf.name}: {summary['kept']} kept, {removed_count} removed{flag}")

    report = {
        "total_kept": grand_kept,
        "total_removed": grand_removed,
        "removal_rate_pct": round(100 * grand_removed / max(1, grand_kept + grand_removed), 2),
        "files": summaries,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nTotal: {grand_kept} kept, {grand_removed} removed "
          f"({report['removal_rate_pct']}% removal rate)")
    print(f"Report: {report_path}")
    print(f"Cleaned files: {out_dir}/")


if __name__ == "__main__":
    main()
