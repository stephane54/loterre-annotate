#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _find_registry() -> str:
    env = os.environ.get("LOTERRE_REGISTRY")
    if env:
        return env
    # Walk up from __file__ to find configs/registry.yaml or loterre-v9/configs/registry.yaml
    here = Path(__file__).resolve().parent
    for _ in range(10):
        for sub in ("", "loterre-v9"):
            candidate = (here / sub / "configs" / "registry.yaml") if sub else (here / "configs" / "registry.yaml")
            if candidate.exists():
                return str(candidate)
        here = here.parent
    return "configs/registry.yaml"


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError("PyYAML is required. Install with: pip install pyyaml") from exc
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_registry(path: Path) -> Dict[str, Any]:
    data = load_yaml(path)
    return data.get("dictionaries", {}) or {}


def resolve_config_value(config: Dict[str, Any], *keys, default=None):
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
    return default


def resolve_effective_params(args) -> Dict[str, Any]:
    config = load_yaml(Path(args.config).resolve()) if args.config else {}
    registry_path = Path(args.registry).resolve()
    registry = load_registry(registry_path)

    dict_id = args.dict_id or resolve_config_value(config, "dict_id")
    reg_entry = registry.get(dict_id, {}) if dict_id else {}

    dict_path = (
        args.dict
        or resolve_config_value(config, "dictionary", "dict")
        or reg_entry.get("path")
    )
    lang = args.lang or resolve_config_value(config, "lang", "language") or reg_entry.get("lang")
    profile = args.profile or resolve_config_value(config, "profile") or reg_entry.get("profile")
    text_path = args.text or resolve_config_value(config, "text", "input")

    if dict_path:
        raw = str(dict_path)
        dict_path = Path(dict_path)
        if not dict_path.is_absolute():
            # registry paths are relative to configs/
            if reg_entry.get("path") == raw:
                dict_path = (registry_path.parent / dict_path).resolve()
            else:
                dict_path = dict_path.resolve()

    return {
        "dict_id": dict_id,
        "dict": str(dict_path) if dict_path else None,
        "lang": lang,
        "profile": profile,
        "text": str(Path(text_path).resolve()) if text_path else None,
        "config": config,
        "registry": str(registry_path),
    }


def write_or_print_json(payload: Dict[str, Any], out: Optional[str]) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(data, encoding="utf-8")
    else:
        print(data)


def run_fast_mode(args, effective: Dict[str, Any]) -> None:
    if not effective.get("dict"):
        raise SystemExit("ERROR: --dict or --dict-id with registry path is required for fast mode")
    from loterre_fast_path import run_fast_path

    payload = run_fast_path(
        text_path=effective.get("text"),
        dict_path=effective["dict"],
        cache_dir=args.cache_dir,
        case_sensitive=args.case_sensitive,
        max_regex_terms=args.max_regex_terms,
    )
    payload.update({
        "execution_strategy": "fast",
        "dict_id": effective.get("dict_id"),
        "dict": effective.get("dict"),
        "lang": effective.get("lang"),
        "profile": effective.get("profile"),
    })
    write_or_print_json(payload, args.out)


def run_engine_full_json(effective: Dict[str, Any], text_path: str, unknown_args) -> Dict[str, Any]:
    engine = Path(__file__).with_name("loterre_engine_v9_cli.py")
    if not engine.exists():
        raise SystemExit(f"ERROR: engine not found: {engine}")

    cmd = [sys.executable, str(engine), "--text", text_path]
    if effective.get("dict"):
        cmd.extend(["--dict", effective["dict"]])
    if effective.get("lang"):
        cmd.extend(["--lang", effective["lang"]])
    if effective.get("profile"):
        cmd.extend(["--profile", effective["profile"]])
    cmd.append("--silent")
    cmd.extend(unknown_args)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "v9 engine failed during hybrid refinement\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDERR:\n{proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"v9 engine did not return valid JSON in --silent mode: {exc}") from exc


def result_has_ambiguity(result: Dict[str, Any], args) -> bool:
    matches = result.get("matches", [])
    if any(m.get("ambiguous") for m in matches):
        return True

    if len(matches) >= args.hybrid_max_fast_matches:
        return True

    if args.hybrid_refine_single_tokens:
        for m in matches:
            found = str(m.get("found", ""))
            if found and len(found.split()) == 1:
                return True

    if args.hybrid_refine_low_score is not None:
        for m in matches:
            try:
                score = float(m.get("score", 1.0))
            except Exception:
                score = 1.0
            if score < args.hybrid_refine_low_score:
                return True

    return False


def write_subset_jsonl(results, subset_ids, subset_path: Path) -> None:
    selected = set(subset_ids)
    with subset_path.open("w", encoding="utf-8") as f:
        for row in results:
            if row.get("id") in selected:
                f.write(json.dumps({
                    "id": row.get("id"),
                    "value": row.get("value", ""),
                }, ensure_ascii=False) + "\n")


def merge_hybrid_results(fast_payload: Dict[str, Any], refined_payload: Dict[str, Any], refined_ids) -> Dict[str, Any]:
    refined_ids = set(refined_ids)
    refined_by_id = {row.get("id"): row for row in refined_payload.get("results", [])}

    merged_results = []
    for row in fast_payload.get("results", []):
        doc_id = row.get("id")
        if doc_id in refined_ids and doc_id in refined_by_id:
            refined = refined_by_id[doc_id]
            refined["hybrid_source"] = "v9_refined"
            merged_results.append(refined)
        else:
            row["hybrid_source"] = "fast"
            merged_results.append(row)

    return {
        **fast_payload,
        "mode": "hybrid_fast_then_v9",
        "execution_strategy": "hybrid",
        "docs": len(merged_results),
        "matches": sum(len(row.get("matches", [])) for row in merged_results),
        "hybrid": {
            "refined_docs": len(refined_ids),
            "fast_docs": len(merged_results) - len(refined_ids),
        },
        "results": merged_results,
    }


def run_hybrid_mode(args, effective: Dict[str, Any], unknown_args) -> None:
    if not effective.get("dict"):
        raise SystemExit("ERROR: --dict or --dict-id with registry path is required for hybrid mode")

    from loterre_fast_path import run_fast_path
    t0 = time.perf_counter()

    fast_payload = run_fast_path(
        text_path=effective.get("text"),
        dict_path=effective["dict"],
        cache_dir=args.cache_dir,
        case_sensitive=args.case_sensitive,
        max_regex_terms=args.max_regex_terms,
    )

    fast_results = fast_payload.get("results", [])
    refine_ids = [
        row.get("id")
        for row in fast_results
        if row.get("id") is not None and result_has_ambiguity(row, args)
    ]

    if refine_ids:
        with tempfile.TemporaryDirectory(prefix="loterre_hybrid_") as tmp:
            subset_path = Path(tmp) / "hybrid_subset.jsonl"
            write_subset_jsonl(fast_results, refine_ids, subset_path)
            refined_payload = run_engine_full_json(
                effective=effective,
                text_path=str(subset_path),
                unknown_args=unknown_args,
            )
        merged = merge_hybrid_results(fast_payload, refined_payload, refine_ids)
    else:
        merged = {
            **fast_payload,
            "mode": "hybrid_fast_only_no_refinement_needed",
            "execution_strategy": "hybrid",
            "hybrid": {"refined_docs": 0, "fast_docs": len(fast_results)},
        }
        for row in merged.get("results", []):
            row["hybrid_source"] = "fast"

    merged.update({
        "dict_id": effective.get("dict_id"),
        "dict": effective.get("dict"),
        "lang": effective.get("lang"),
        "profile": effective.get("profile"),
    })
    merged.setdefault("timings", {})
    merged["timings"]["hybrid_total_s"] = round(time.perf_counter() - t0, 4)
    write_or_print_json(merged, args.out)


def run_full_mode(args, effective: Dict[str, Any], unknown_args) -> None:
    engine = Path(__file__).with_name("loterre_engine_v9_cli.py")
    if not engine.exists():
        raise SystemExit(f"ERROR: engine not found: {engine}")

    cmd = [sys.executable, str(engine)]
    if effective.get("text"):
        cmd.extend(["--text", effective["text"]])
    if effective.get("dict"):
        cmd.extend(["--dict", effective["dict"]])
    if effective.get("lang"):
        cmd.extend(["--lang", effective["lang"]])
    if effective.get("profile"):
        cmd.extend(["--profile", effective["profile"]])
    if args.config:
        cmd.extend(["--config", args.config])
    if args.out:
        cmd.extend(["--out", args.out])
    if args.report:
        cmd.extend(["--report", args.report])
    if args.silent:
        cmd.append("--silent")
    if args.api:
        cmd.append("--api")
    cmd.extend(unknown_args)

    proc = subprocess.run(cmd)
    raise SystemExit(proc.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Loterre v9 CLI with full/fast/hybrid execution strategies")
    parser.add_argument("--execution-strategy", choices=["full", "fast", "hybrid"], default="full")
    parser.add_argument("--dict-id")
    parser.add_argument("--registry", default=_find_registry())
    parser.add_argument("--config")
    parser.add_argument("--text")
    parser.add_argument("--dict")
    parser.add_argument("--lang", choices=["en", "fr"])
    parser.add_argument("--profile", choices=["entity_strict", "term_balanced", "term_recall"])
    parser.add_argument("--out")
    parser.add_argument("--report")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--api", action="store_true")

    parser.add_argument("--cache-dir", default=".loterre_cache")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--max-regex-terms", type=int)

    parser.add_argument("--hybrid-refine-single-tokens", action="store_true")
    parser.add_argument("--hybrid-refine-low-score", type=float, default=0.90)
    parser.add_argument("--hybrid-max-fast-matches", type=int, default=50)
    return parser


def main() -> None:
    parser = build_parser()
    args, unknown_args = parser.parse_known_args()

    if args.hybrid_refine_low_score is not None and args.hybrid_refine_low_score < 0:
        args.hybrid_refine_low_score = None

    effective = resolve_effective_params(args)

    if args.execution_strategy == "fast":
        run_fast_mode(args, effective)
    elif args.execution_strategy == "hybrid":
        run_hybrid_mode(args, effective, unknown_args)
    else:
        run_full_mode(args, effective, unknown_args)


if __name__ == "__main__":
    main()
