#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, pickle, re, sys, time
from pathlib import Path

def load_jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def norm(s, case_sensitive=False):
    s = " ".join(str(s or "").split())
    return s if case_sensitive else s.lower()

def fingerprint(path):
    p = Path(path)
    st = p.stat()
    raw = f"{p.resolve()}::{st.st_mtime_ns}::{st.st_size}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def load_dict_entries(path):
    entries = []
    for obj in load_jsonl(path):
        label = obj.get("label") or obj.get("pref") or obj.get("prefLabel") or ""
        pref = obj.get("pref") or obj.get("prefLabel") or label
        cid = obj.get("id") or obj.get("uri") or obj.get("ark") or ""
        variants = [label]
        for key in ["variants", "altLabels", "altLabel", "synonyms"]:
            v = obj.get(key)
            if isinstance(v, list):
                variants.extend(str(x) for x in v if x)
            elif isinstance(v, str):
                variants.append(v)
        entries.append({"label": label, "pref": pref, "id": cid, "variants": [x for x in variants if x]})
    return entries

def build_index(entries, case_sensitive=False):
    idx = {}
    for e in entries:
        for form in e["variants"]:
            k = norm(form, case_sensitive)
            if not k:
                continue
            idx.setdefault(k, []).append({"label": e["label"], "pref": e["pref"], "id": e["id"], "surface": form})
    return idx

def load_or_build_index(dict_path, cache_dir, case_sensitive=False):
    dict_path = Path(dict_path)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fp = fingerprint(dict_path)
    cache = cache_dir / f"{dict_path.stem}.{fp}.fastindex.pkl"
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    idx = build_index(load_dict_entries(dict_path), case_sensitive)
    cache.write_bytes(pickle.dumps(idx))
    for old in cache_dir.glob(f"{dict_path.stem}.*.fastindex.pkl"):
        if old != cache:
            old.unlink(missing_ok=True)
    return idx

def compile_regex(index, max_terms=None):
    terms = sorted(index.keys(), key=len, reverse=True)
    if max_terms:
        terms = terms[:max_terms]
    terms = [re.escape(t) for t in terms if t]
    if not terms:
        return re.compile(r"$^")
    return re.compile(r"(?<!\\w)(" + "|".join(terms) + r")(?!\\w)", re.IGNORECASE)

def fast_match(text, index, regex, case_sensitive=False):
    search = text if case_sensitive else text.lower()
    out = []
    for m in regex.finditer(search):
        k = norm(m.group(0), case_sensitive)
        cands = index.get(k, [])
        for c in cands:
            out.append({
                "start": m.start(),
                "end": m.end(),
                "found": text[m.start():m.end()],
                "label": c["label"],
                "pref": c["pref"],
                "id": c["id"],
                "rule": "fast_exact",
                "score": 1.0 if len(cands) == 1 else 0.85,
                "ambiguous": len(cands) > 1
            })
    return out

def dedupe(matches):
    matches = sorted(matches, key=lambda m: (m["start"], -(m["end"]-m["start"]), -float(m.get("score",0))))
    out, last = [], -1
    for m in matches:
        if m["start"] >= last:
            out.append(m)
            last = m["end"]
    return out

def read_docs(path):
    rows = []
    if path:
        it = load_jsonl(path)
    else:
        it = (json.loads(line) for line in sys.stdin if line.strip())
    for i, obj in enumerate(it, 1):
        rows.append({"id": obj.get("id", f"doc_{i}"), "value": obj.get("value", obj.get("text", ""))})
    return rows

def annotate(docs, index, regex, case_sensitive=False):
    results = []
    for d in docs:
        text = d.get("value", "")
        results.append({"id": d.get("id"), "text": text, "matches": dedupe(fast_match(text, index, regex, case_sensitive))})
    return results

def main():
    p = argparse.ArgumentParser(description="Loterre v10 fast exact path")
    p.add_argument("--text")
    p.add_argument("--dict", required=True)
    p.add_argument("--out")
    p.add_argument("--cache-dir", default=".loterre_cache")
    p.add_argument("--case-sensitive", action="store_true")
    p.add_argument("--max-regex-terms", type=int)
    args = p.parse_args()
    t0 = time.perf_counter()
    idx = load_or_build_index(args.dict, args.cache_dir, args.case_sensitive)
    rx = compile_regex(idx, args.max_regex_terms)
    results = annotate(read_docs(args.text), idx, rx, args.case_sensitive)
    payload = {
        "mode": "fast_exact",
        "docs": len(results),
        "matches": sum(len(r["matches"]) for r in results),
        "timings": {"total_s": round(time.perf_counter() - t0, 4)},
        "results": results
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(data, encoding="utf-8")
    else:
        print(data)

if __name__ == "__main__":
    main()
