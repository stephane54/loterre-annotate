#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
import sys
import time
from pathlib import Path
from typing import Optional


def load_jsonl(path: str | Path):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def normalize(s: str, case_sensitive: bool = False) -> str:
    # Collapse internal whitespace so "long  term" == "long term" in the index.
    s = " ".join(str(s or "").split())
    return s if case_sensitive else s.lower()


def fingerprint(path: str | Path) -> str:
    # mtime_ns + size is faster than hashing file content (dicts can be 100 MB+)
    # and good enough: same path + same modification time + same size → same content.
    p = Path(path)
    st = p.stat()
    raw = f"{p.resolve()}::{st.st_mtime_ns}::{st.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_dictionary_entries(dict_path: str | Path):
    entries = []
    for obj in load_jsonl(dict_path):
        label = obj.get("label") or obj.get("pref") or obj.get("prefLabel") or ""
        pref = obj.get("pref") or obj.get("prefLabel") or label
        concept_id = obj.get("id") or obj.get("uri") or obj.get("ark") or ""

        variants = [label]
        for key in ("variants", "altLabels", "altLabel", "synonyms"):
            value = obj.get(key)
            if isinstance(value, list):
                variants.extend(str(x) for x in value if x)
            elif isinstance(value, str):
                variants.append(value)

        variants = [x for x in variants if x]
        if variants:
            entries.append({
                "label": label,
                "pref": pref,
                "id": concept_id,
                "variants": variants,
            })
    return entries


def build_index(entries, case_sensitive: bool = False):
    index = {}
    for entry in entries:
        for form in entry["variants"]:
            key = normalize(form, case_sensitive=case_sensitive)
            if not key:
                continue
            index.setdefault(key, []).append({
                "label": entry["label"],
                "pref": entry["pref"],
                "id": entry["id"],
                "surface": form,
            })
    return index


def load_or_build_index(
    dict_path: str | Path,
    cache_dir: str | Path = ".loterre_cache",
    case_sensitive: bool = False,
):
    # Building the index (normalize + expand variants) is O(E×V) and can take
    # several seconds on large dictionaries (50k+ entries). The pickle cache
    # avoids this cost on repeated runs. The fingerprint encodes the file state
    # AND the case mode so that changing case_sensitive invalidates the cache.
    dict_path = Path(dict_path)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    fp = fingerprint(dict_path)
    cs_suffix = "cs" if case_sensitive else "ci"
    cache_path = cache_dir / f"{dict_path.stem}.{fp}.{cs_suffix}.fastindex.pkl"

    if cache_path.exists():
        try:
            return pickle.loads(cache_path.read_bytes())
        except Exception:
            # Corrupt or truncated cache (e.g. interrupted write) — rebuild silently.
            cache_path.unlink(missing_ok=True)

    index = build_index(load_dictionary_entries(dict_path), case_sensitive=case_sensitive)
    cache_path.write_bytes(pickle.dumps(index))

    # Remove stale caches for the same dict (different fingerprint or case mode).
    for old in cache_dir.glob(f"{dict_path.stem}.*.*.fastindex.pkl"):
        if old != cache_path:
            old.unlink(missing_ok=True)

    return index


def compile_regex(index, max_terms: Optional[int] = None, case_sensitive: bool = False):
    # Sort longest-first so the regex engine prefers "long-term memory" over "memory"
    # when both are in the alternation (re alternation is ordered, not greedy by length).
    terms = sorted(index.keys(), key=len, reverse=True)
    if max_terms:
        terms = terms[:max_terms]
    terms = [re.escape(t) for t in terms if t]

    if not terms:
        # Unsatisfiable pattern — finditer will yield nothing without raising.
        return re.compile(r"$^")

    # Word-boundary lookarounds prevent matching substrings inside words
    # (e.g. "or" inside "memory"). \w covers [a-zA-Z0-9_] which is sufficient
    # for the Latin-script terms in Loterre dictionaries.
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<!\w)(" + "|".join(terms) + r")(?!\w)", flags)


def read_docs(text_path: str | Path | None):
    rows = []
    if text_path:
        iterator = load_jsonl(text_path)
    else:
        iterator = (json.loads(line) for line in sys.stdin if line.strip())

    for i, obj in enumerate(iterator, 1):
        rows.append({
            "id": obj.get("id", f"doc_{i}"),
            "value": obj.get("value", obj.get("text", "")),
        })
    return rows


def fast_match(text: str, index, regex, case_sensitive: bool = False):
    # Run the regex on the normalized form so offsets stay aligned with the
    # original text; recover the original surface string via text[start:end].
    search = text if case_sensitive else text.lower()
    matches = []

    for match in regex.finditer(search):
        key = normalize(match.group(0), case_sensitive=case_sensitive)
        candidates = index.get(key, [])

        for candidate in candidates:
            matches.append({
                "start": match.start(),
                "end": match.end(),
                "found": text[match.start():match.end()],
                "label": candidate["label"],
                "pref": candidate["pref"],
                "id": candidate["id"],
                "rule": "fast_exact",
                # Score 0.85 (not 1.0) when the surface form maps to multiple
                # concepts — signals that the hybrid engine should refine this doc.
                "score": 1.0 if len(candidates) == 1 else 0.85,
                "ambiguous": len(candidates) > 1,
            })

    return matches


def dedupe(matches):
    # Sort: earliest start first; for ties prefer the longest span, then highest
    # score. The greedy left-to-right sweep then keeps only non-overlapping matches.
    matches = sorted(
        matches,
        key=lambda m: (m["start"], -(m["end"] - m["start"]), -float(m.get("score", 0))),
    )
    out = []
    last_end = -1
    for match in matches:
        if match["start"] >= last_end:
            out.append(match)
            last_end = match["end"]
    return out


def annotate_docs_fast(docs, index, regex, case_sensitive: bool = False):
    results = []
    for doc in docs:
        text = doc.get("value", "")
        matches = dedupe(fast_match(text, index, regex, case_sensitive=case_sensitive))
        results.append({
            "id": doc.get("id"),
            "value": text,
            "matches": matches,
        })
    return results


def run_fast_path(
    text_path: str | Path | None,
    dict_path: str | Path,
    cache_dir: str | Path = ".loterre_cache",
    case_sensitive: bool = False,
    max_regex_terms: Optional[int] = None,
):
    t0 = time.perf_counter()
    index = load_or_build_index(dict_path, cache_dir, case_sensitive)
    regex = compile_regex(index, max_terms=max_regex_terms, case_sensitive=case_sensitive)
    docs = read_docs(text_path)
    results = annotate_docs_fast(docs, index, regex, case_sensitive)

    return {
        "mode": "fast_exact",
        "docs": len(results),
        "matches": sum(len(row.get("matches", [])) for row in results),
        "timings": {"fast_total_s": round(time.perf_counter() - t0, 4)},
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Loterre fast exact path")
    parser.add_argument("--text")
    parser.add_argument("--dict", required=True)
    parser.add_argument("--out")
    parser.add_argument("--cache-dir", default=".loterre_cache")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--max-regex-terms", type=int)
    args = parser.parse_args()

    payload = run_fast_path(
        text_path=args.text,
        dict_path=args.dict,
        cache_dir=args.cache_dir,
        case_sensitive=args.case_sensitive,
        max_regex_terms=args.max_regex_terms,
    )
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
