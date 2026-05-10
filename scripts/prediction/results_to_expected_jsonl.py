#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def read_payload(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {"results": []}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        rows: List[Dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return {"results": rows}

    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"results": data}
    raise ValueError(f"Unsupported JSON payload type: {type(data).__name__}")


def iter_results(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    if "results" in payload and isinstance(payload["results"], list):
        return payload["results"]
    if "documents" in payload and isinstance(payload["documents"], list):
        return payload["documents"]
    if "id" in payload:
        return [payload]
    return []


def to_expected_match(match: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "found": match.get("found", ""),
        "pref": match.get("pref", match.get("label", "")),
        "id": match.get("id", match.get("uri", match.get("ark", ""))),
        "start": match.get("start"),
        "end": match.get("end"),
        "rule": match.get("rule", ""),
        "score": match.get("score"),
    }


def build_gold_rows(results: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for doc in results:
        matches = doc.get("matches") or []
        rows.append(
            {
                "id": doc.get("id", ""),
                "value": doc.get("text", doc.get("value", "")),
                "expected_matches": [to_expected_match(m) for m in matches],
            }
        )
    return rows


def write_jsonl(rows: Iterable[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Transform a prediction JSON/JSONL file into an input JSONL with expected_matches."
    )
    p.add_argument("--input", required=True, help="Prediction JSON or JSONL path (with results[].matches).")
    p.add_argument("--out", required=True, help="Output JSONL path containing expected_matches.")
    args = p.parse_args()

    payload = read_payload(Path(args.input))
    rows = build_gold_rows(iter_results(payload))
    write_jsonl(rows, Path(args.out))
    print(json.dumps({"status": "ok", "documents": len(rows), "out": args.out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
