#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError("PyYAML is required. Install with: pip install pyyaml") from exc

    if not path.exists():
        return {}

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_registry(path: Path) -> Dict[str, Any]:
    """Load registry dictionaries from YAML."""
    data = load_yaml(path)
    return data.get("dictionaries", {}) or {}


def resolve_registry_path(cli_path: Optional[str]) -> Path:
    """Resolve registry path."""
    if cli_path:
        return Path(cli_path).resolve()
    return Path("configs/registry.yaml").resolve()


def resolve_config_value(config: Dict[str, Any], *keys, default=None):
    """Return first existing value from config."""
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
    return default


def resolve_effective_params(args) -> Dict[str, Any]:
    """Resolve dict/lang/profile/text according to CLI > config > registry."""
    config = load_yaml(Path(args.config).resolve()) if args.config else {}

    registry_path = resolve_registry_path(args.registry)
    registry = load_registry(registry_path)

    dict_id = args.dict_id or resolve_config_value(config, "dict_id")
    reg_entry = registry.get(dict_id, {}) if dict_id else {}

    dict_path = (
        args.dict
        or resolve_config_value(config, "dictionary", "dict")
        or reg_entry.get("path")
    )

    lang = (
        args.lang
        or resolve_config_value(config, "lang", "language")
        or reg_entry.get("lang")
    )

    profile = (
        args.profile
        or resolve_config_value(config, "profile")
        or reg_entry.get("profile")
    )

    text_path = (
        args.text
        or resolve_config_value(config, "text", "input")
    )

    if dict_path:
        dict_path = Path(dict_path)
        if not dict_path.is_absolute():
            if reg_entry.get("path") == str(dict_path) or reg_entry.get("path") == args.dict:
                # Registry paths are relative to configs/
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
    """Write JSON to file or stdout."""
    data = json.dumps(payload, ensure_ascii=False, indent=2)

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(data, encoding="utf-8")
    else:
        print(data)


def run_fast_mode(args, effective: Dict[str, Any]) -> None:
    """Run fast mode by calling run_fast_path() directly."""
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

    payload["execution_strategy"] = "fast"
    payload["dict_id"] = effective.get("dict_id")
    payload["dict"] = effective.get("dict")
    payload["lang"] = effective.get("lang")
    payload["profile"] = effective.get("profile")

    write_or_print_json(payload, args.out)


def run_full_mode(args, effective: Dict[str, Any], unknown_args) -> None:
    """Delegate to the original v9 engine for full mode."""
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
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Loterre v9 CLI with clean fast execution strategy")

    parser.add_argument("--execution-strategy", choices=["full", "fast", "hybrid"], default="full")

    parser.add_argument("--dict-id", help="Dictionary id from configs/registry.yaml")
    parser.add_argument("--registry", default="configs/registry.yaml")
    parser.add_argument("--config")

    parser.add_argument("--text")
    parser.add_argument("--dict")
    parser.add_argument("--lang", choices=["en", "fr"])
    parser.add_argument("--profile", choices=["entity_strict", "term_balanced", "term_recall"])

    parser.add_argument("--out")
    parser.add_argument("--report")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--api", action="store_true")

    # Fast mode parameters
    parser.add_argument("--cache-dir", default=".loterre_cache")
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--max-regex-terms", type=int)

    return parser


def main() -> None:
    """Main CLI entrypoint."""
    parser = build_parser()
    args, unknown_args = parser.parse_known_args()

    effective = resolve_effective_params(args)

    if args.execution_strategy == "fast":
        run_fast_mode(args, effective)
        return

    if args.execution_strategy == "hybrid":
        raise SystemExit(
            "ERROR: --execution-strategy hybrid is not implemented yet. "
            "Use 'fast' for fast exact mode or 'full' for v9 mode."
        )

    run_full_mode(args, effective, unknown_args)


if __name__ == "__main__":
    main()
