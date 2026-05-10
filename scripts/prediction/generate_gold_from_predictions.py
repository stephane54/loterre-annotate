#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


def load_registry(path: Path) -> Dict[str, dict]:
    """Load configs/registry.yaml and return the dictionaries mapping."""
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError("PyYAML is required to read registry.yaml. Install with: pip install pyyaml") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("dictionaries", {}) or {}


def code_from_dict_id(dict_id: str) -> str:
    """Extract resource code from dict-id: P66_en -> P66."""
    return dict_id.rsplit("_", 1)[0] if "_" in dict_id else dict_id


def find_text_file(dict_id: str, text_root: Path) -> Optional[Path]:
    """Find a text file matching a dictionary id."""
    code = code_from_dict_id(dict_id)

    candidates = [
        text_root / f"{dict_id}.jsonl",
        text_root / f"{code}.jsonl",
        text_root / f"{dict_id}.json",
        text_root / f"{code}.json",
    ]
    for path in candidates:
        if path.exists():
            return path

    for pattern in [f"*{dict_id}*.jsonl", f"*{code}*.jsonl", f"*{dict_id}*.json", f"*{code}*.json"]:
        matches = sorted(text_root.glob(pattern))
        if matches:
            return matches[0]

    return None


def make_jobs_from_registry(registry: Dict[str, dict], registry_path: Path, text_root: Path, only_dict_id: Optional[str] = None) -> List[dict]:
    """Build execution jobs directly from registry.yaml."""
    jobs = []
    registry_dir = registry_path.parent

    for dict_id, spec in registry.items():
        if only_dict_id and dict_id != only_dict_id:
            continue

        dict_path_raw = spec.get("path")
        if not dict_path_raw:
            jobs.append({"dict_id": dict_id, "status": "error", "error": "missing path in registry"})
            continue

        dict_path = Path(dict_path_raw)
        if not dict_path.is_absolute():
            dict_path = Path(os.path.normpath(str(registry_dir / ".." / dict_path)))

        lang = spec.get("lang", "en")
        profile = spec.get("profile", "term_recall")
        text_path = find_text_file(dict_id, text_root)

        if text_path is None:
            jobs.append({
                "dict_id": dict_id,
                "status": "missing_text",
                "dict": str(dict_path),
                "lang": lang,
                "profile": profile,
                "error": f"no text file found for {dict_id} in {text_root}",
            })
            continue

        jobs.append({
            "dict_id": dict_id,
            "status": "ready",
            "text": str(text_path),
            "dict": str(dict_path),
            "lang": lang,
            "profile": profile,
        })

    return jobs


def safe_name(path: str) -> str:
    """Return a filesystem-friendly stem."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(path).stem)


def create_gold_from_prediction(prediction: dict, gold_path: Path) -> None:
    """Create a gold JSONL file from a Loterre prediction payload."""
    with gold_path.open("w", encoding="utf-8") as f:
        for item in prediction.get("results", []):
            expected = []
            for m in item.get("matches", []):
                expected.append({
                    "found": m.get("found", ""),
                    "pref": m.get("pref", ""),
                    "id": m.get("uri", m.get("id", "")),
                    "start": m.get("start"),
                    "end": m.get("end"),
                    "rule": m.get("rule", ""),
                    "score": m.get("score"),
                })
            f.write(json.dumps({
                "id": item.get("id", ""),
                "value": item.get("text", item.get("value", "")),
                "expected_matches": expected,
            }, ensure_ascii=False) + "\n")


def run_job(engine: Path, job: dict, outdir: Path, timeout: int) -> dict:
    """Run one prediction job and generate the corresponding gold."""
    pred_dir = outdir / "predictions"
    gold_dir = outdir / "gold"
    pred_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)

    dict_id = job["dict_id"]
    pred_path = pred_dir / f"{dict_id}__{safe_name(job['text'])}__{safe_name(job['dict'])}.pred.json"
    gold_path = gold_dir / f"gold_{dict_id}__{safe_name(job['text'])}__{safe_name(job['dict'])}.jsonl"

    cmd = [
        sys.executable, str(engine),
        "--text", job["text"],
        "--dict", job["dict"],
        "--lang", job["lang"],
        "--profile", job["profile"],
        "--silent",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if proc.returncode != 0:
        return {**job, "status": "error", "command": cmd, "stderr": proc.stderr[-4000:]}

    pred_path.write_text(proc.stdout, encoding="utf-8")

    try:
        prediction = json.loads(proc.stdout)
    except Exception as exc:
        return {**job, "status": "error", "command": cmd, "prediction": str(pred_path), "error": f"invalid JSON prediction: {exc}"}

    create_gold_from_prediction(prediction, gold_path)

    return {**job, "status": "ok", "prediction": str(pred_path), "gold": str(gold_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate predictions and bootstrap gold files from configs/registry.yaml")
    # This script runs the engine and then generates gold JSONL.
    # If you already have prediction files and only need conversion,
    # use scripts/prediction/results_to_expected_jsonl.py.
    parser.add_argument("--engine", required=True, help="Path to loterre_cli.py or loterre_engine_v9_cli.py")
    parser.add_argument("--registry", default="configs/registry.yaml", help="Path to registry.yaml")
    parser.add_argument("--text-root", default="texts", help="Directory containing text JSONL files")
    parser.add_argument("--outdir", default=".", help="Output root directory")
    parser.add_argument("--dict-id", help="Optional single dictionary id to process")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--jobs-out", default="generated_jobs.json")
    parser.add_argument("--summary-out", default="generation_summary.json")
    parser.add_argument("--dry-run", action="store_true", help="Only generate the job list, do not run the engine")
    args = parser.parse_args()

    registry_path = Path(args.registry)
    text_root = Path(args.text_root)
    outdir = Path(args.outdir)
    engine = Path(args.engine)
    outdir.mkdir(parents=True, exist_ok=True)

    jobs = make_jobs_from_registry(
        registry=load_registry(registry_path),
        registry_path=registry_path,
        text_root=text_root,
        only_dict_id=args.dict_id,
    )

    jobs_path = outdir / args.jobs_out
    jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.dry_run:
        print(json.dumps({"status": "dry_run", "jobs": jobs, "jobs_out": str(jobs_path)}, ensure_ascii=False, indent=2))
        return

    summary = []
    for job in jobs:
        if job.get("status") != "ready":
            summary.append(job)
            continue
        summary.append(run_job(engine=engine, job=job, outdir=outdir, timeout=args.timeout))

    summary_path = outdir / args.summary_out
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"jobs_out": str(jobs_path), "summary_out": str(summary_path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
