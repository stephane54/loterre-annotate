#!/usr/bin/env python3
"""Evaluate the production ISTEX terms-matcher API against local gold files.

Usage:
    python3 src/loterre_api_eval.py --vocab P66 --lang en \
        --gold data/texts/P66_en.jsonl \
        --out html_api/html/P66_en.html [--json-out html_api/json/P66_en.json]

    python3 src/loterre_api_eval.py --vocab P66 --lang fr \
        --gold data/texts/P66_fr.jsonl \
        --out html_api/html/P66_fr.html

The API endpoint is language-specific:
    https://terms-tools.services.istex.fr/v1/{lang}/terms-matcher/json-standoff/annotate
where {lang} is "en" or "fr".
"""
from __future__ import annotations
import argparse, json, re, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_BASE = "https://terms-tools.services.istex.fr/v1/{lang}/terms-matcher/json-standoff/annotate"


# ---------------------------------------------------------------------------
# Tokeniser (mirrors the API's whitespace+punctuation split)
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[dict]:
    """Split text into word/punctuation tokens, returning char offsets.

    Decimal numbers like "1.1" or "3.14" are kept as a single token to match
    the API's internal tokenisation (which does not split on embedded dots).
    """
    return [
        {"text": m.group(), "start": m.start(), "end": m.end()}
        for m in re.finditer(r"\d+\.\d+|\w+|[^\w\s]", text)
    ]


def token_span_to_char(tokens: list[dict], start_tok: int, end_tok: int) -> tuple[int, int] | None:
    """Convert exclusive token [start_tok, end_tok) to character (start, end)."""
    if not tokens or start_tok >= len(tokens) or end_tok > len(tokens) or start_tok >= end_tok:
        return None
    return tokens[start_tok]["start"], tokens[end_tok - 1]["end"]


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_api(vocab: str, lang: str, docs: list[dict], timeout: int = 60) -> list[dict] | None:
    """POST docs as JSON array to the API and return parsed response."""
    url = f"{API_BASE.format(lang=lang)}?loterreID={vocab}"
    body = json.dumps(docs).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8").strip()
            if not raw:
                print(f"[API] empty response for {vocab}/{lang}", file=sys.stderr)
                return []
            return json.loads(raw)
    except HTTPError as e:
        print(f"[API] HTTP {e.code} for vocab={vocab}: {e.read().decode()[:200]}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"[API] URL error for vocab={vocab}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[API] parse error for {vocab}/{lang}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Response → local match format
# ---------------------------------------------------------------------------

def api_doc_to_matches(api_doc: dict, text: str) -> list[dict]:
    """Convert one API response document into a list of local match dicts."""
    tokens = tokenize(text)
    matches = []
    for value_item in api_doc.get("value", []):
        for ann in value_item.get("matches", []):
            start_tok = int(ann["idx"]["start"])
            end_tok = int(ann["idx"]["end"])
            span = token_span_to_char(tokens, start_tok, end_tok)
            if span is None:
                continue
            matches.append({
                "start": span[0],
                "end": span[1],
                "found": ann["match"].get("text", ""),
                "pref": ann["match"].get("term", ""),
                "uri": ann["match"].get("id", ""),
            })
    return matches


# ---------------------------------------------------------------------------
# Read gold
# ---------------------------------------------------------------------------

def read_gold(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Evaluate production API against gold corpus")
    p.add_argument("--vocab", required=True, help="Vocabulary code, e.g. P66")
    p.add_argument("--lang", default=None,
                   help="Language: en or fr (default: inferred from gold filename)")
    p.add_argument("--gold", required=True, help="Gold JSONL file")
    p.add_argument("--out", required=True, help="Output HTML file")
    p.add_argument("--json-out", help="Optional: save API results as JSON")
    p.add_argument("--base-url", default="https://www.loterre.fr/ark:/")
    p.add_argument("--batch-size", type=int, default=5,
                   help="Number of documents per API call (default 5)")
    p.add_argument("--delay", type=float, default=0.5,
                   help="Seconds between batches (default 0.5)")
    args = p.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from loterre_html_renderer import render_page

    # Infer language from gold filename if not provided (e.g. P66_fr.jsonl → fr)
    lang = args.lang
    if not lang:
        stem = Path(args.gold).stem          # e.g. "P66_fr"
        parts = stem.split("_")
        lang = parts[-1] if parts[-1] in ("en", "fr") else "en"

    gold_rows = read_gold(args.gold)
    print(f"[eval] {len(gold_rows)} documents in gold, vocab={args.vocab}, lang={lang}")

    # Prepare input docs (strip expected_matches to send to API)
    input_docs = [{"id": row["id"], "value": row.get("value", row.get("text", ""))} for row in gold_rows]

    # Call API in batches
    api_results_by_id: dict[str, list[dict]] = {}
    for i in range(0, len(input_docs), args.batch_size):
        batch = input_docs[i:i + args.batch_size]
        print(f"[api] batch {i//args.batch_size + 1}: docs {i}..{i+len(batch)-1}", end=" ", flush=True)
        t0 = time.perf_counter()
        resp = call_api(args.vocab, lang, batch)
        elapsed = time.perf_counter() - t0
        if resp is None:
            print(f"FAILED ({elapsed:.1f}s)")
            continue
        print(f"OK ({elapsed:.1f}s, {len(resp)} docs returned)")
        for api_doc in resp:
            doc_id = str(api_doc.get("id", ""))
            text = next((r.get("value", r.get("text", "")) for r in gold_rows if str(r["id"]) == doc_id), "")
            api_results_by_id[doc_id] = api_doc_to_matches(api_doc, text)
        if i + args.batch_size < len(input_docs):
            time.sleep(args.delay)

    # Build merged results: gold doc + API matches
    results = []
    total_pred, total_exp, total_both, total_exp_only, total_pred_only = 0, 0, 0, 0, 0
    for row in gold_rows:
        doc_id = str(row["id"])
        text = row.get("value", row.get("text", ""))
        expected = row.get("expected_matches", [])
        predicted = api_results_by_id.get(doc_id, [])
        results.append({
            "id": row["id"],
            "text": text,
            "matches": predicted,
            "expected_matches": expected,
        })

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[eval] JSON saved to {args.json_out}")

    payload = {"results": results}
    title = f"API production vs gold — {args.vocab}"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        render_page(payload, args.base_url, title), encoding="utf-8"
    )
    print(f"[eval] HTML saved to {args.out}")


if __name__ == "__main__":
    main()
