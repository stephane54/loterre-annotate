#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    rows.append({"id": f"line_{i}", "value": line.strip()})
    return rows

def main():
    p = argparse.ArgumentParser(description="Generate predictions and gold files from manifest")
    p.add_argument("--engine", required=True, help="Path to loterre_cli.py or loterre_engine_v9_cli.py")
    p.add_argument("--manifest", default="manifest.json")
    p.add_argument("--outdir", default=".")
    p.add_argument("--timeout", type=int, default=180)
    args = p.parse_args()

    root = Path(args.outdir)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    pred_dir = root / "predictions"
    gold_dir = root / "gold"
    pred_dir.mkdir(exist_ok=True)
    gold_dir.mkdir(exist_ok=True)

    summary = []
    for pair in manifest["pairs"]:
        text_path = root / pair["text_file"]
        dict_path = root / pair["dict_file"]

        pred_path = pred_dir / f"{Path(pair['text_file']).stem}__{Path(pair['dict_file']).stem}.pred.json"
        gold_path = gold_dir / f"gold_{Path(pair['text_file']).stem}__{Path(pair['dict_file']).stem}.jsonl"

        cmd = [
            sys.executable, args.engine,
            "--text", str(text_path),
            "--dict", str(dict_path),
            "--lang", pair["lang"],
            "--profile", pair["profile"],
            "--silent",
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
        if proc.returncode != 0:
            summary.append({"pair": pair, "status": "error", "stderr": proc.stderr[-2000:]})
            continue

        pred_path.write_text(proc.stdout, encoding="utf-8")
        pred = json.loads(proc.stdout)

        with open(gold_path, "w", encoding="utf-8") as f:
            for item in pred.get("results", []):
                expected = []
                for m in item.get("matches", []):
                    expected.append({
                        "found": m.get("found", ""),
                        "pref": m.get("pref", ""),
                        "id": m.get("uri", m.get("id", "")),
                        "start": m.get("start"),
                        "end": m.get("end"),
                        "rule": m.get("rule", ""),
                    })
                row = {
                    "id": item.get("id", ""),
                    "value": item.get("text", ""),
                    "expected_matches": expected,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        summary.append({
            "pair": pair,
            "status": "ok",
            "prediction": str(pred_path),
            "gold": str(gold_path),
        })

    (root / "generation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
