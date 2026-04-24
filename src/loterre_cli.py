#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

def load_registry(path: str) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data.get("dictionaries", {})

def main() -> None:
    p = argparse.ArgumentParser(description="Loterre v9 CLI launcher with registry support")
    p.add_argument("--engine", default=str(Path(__file__).resolve().parent / "loterre_engine_v9_cli.py"))
    p.add_argument("--registry", default=str(Path(__file__).resolve().parent.parent / "configs" / "registry.yaml"))
    p.add_argument("--dict-id", help="Dictionary identifier from registry, e.g. P66_en")
    p.add_argument("--text")
    p.add_argument("--dict")
    p.add_argument("--lang")
    p.add_argument("--profile")
    p.add_argument("--config")
    p.add_argument("--auto-profile", action="store_true")
    p.add_argument("--yaml-out")
    p.add_argument("--out")
    p.add_argument("--report")
    p.add_argument("--silent", action="store_true")
    p.add_argument("--api", action="store_true")
    p.add_argument("--stream", action="store_true")
    p.add_argument("--workers", type=int)
    p.add_argument("--chunk-size", type=int)
    p.add_argument("--log-level")
    p.add_argument("--validate-input", action="store_true")
    p.add_argument("--dump-effective-config", action="store_true")
    args = p.parse_args()

    reg = load_registry(args.registry) if Path(args.registry).exists() else {}

    dict_path = args.dict
    lang = args.lang
    profile = args.profile

    if args.dict_id:
        if args.dict_id not in reg:
            raise SystemExit(f"Unknown --dict-id: {args.dict_id}")
        item = reg[args.dict_id]
        dict_path = dict_path or item.get("path")
        lang = lang or item.get("lang")
        profile = profile or item.get("profile")

    cmd = [sys.executable, args.engine]

    if args.text is not None:
        cmd += ["--text", args.text]
    if dict_path is not None:
        cmd += ["--dict", dict_path]
    if lang is not None:
        cmd += ["--lang", lang]
    if profile is not None:
        cmd += ["--profile", profile]
    if args.config is not None:
        cmd += ["--config", args.config]
    if args.yaml_out is not None:
        cmd += ["--yaml-out", args.yaml_out]
    if args.out is not None:
        cmd += ["--out", args.out]
    if args.report is not None:
        cmd += ["--report", args.report]
    if args.auto_profile:
        cmd += ["--auto-profile"]
    if args.silent:
        cmd += ["--silent"]
    if args.api:
        cmd += ["--api"]
    if args.stream:
        cmd += ["--stream"]
    if args.workers is not None:
        cmd += ["--workers", str(args.workers)]
    if args.chunk_size is not None:
        cmd += ["--chunk-size", str(args.chunk_size)]
    if args.log_level is not None:
        cmd += ["--log-level", args.log_level]
    if args.validate_input:
        cmd += ["--validate-input"]
    if args.dump_effective_config:
        cmd += ["--dump-effective-config"]

    # Read stdin only when neither --text nor --config is provided.
    # If --config is present, the engine may resolve `text:` from YAML, so the launcher
    # must not block waiting for stdin.
    if args.text is None and args.config is None:
        payload = sys.stdin.buffer.read()
        result = subprocess.run(cmd, input=payload)
    else:
        result = subprocess.run(cmd)

    raise SystemExit(result.returncode)

if __name__ == "__main__":
    main()
