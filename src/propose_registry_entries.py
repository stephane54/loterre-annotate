#!/usr/bin/env python3
"""
Compute --auto-profile for every dictionary/{en,fr}_annot_<CODE>.jsonl that has
no entry yet in configs/registry.yaml, and print ready-to-paste YAML entries in
the same style as the existing ones (profile + avg_len comment).

Read-only: does not modify registry.yaml itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml  # noqa: E402

from loterre_engine_v9_cli import load_entries, profile_dictionary, suggest_profile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DICT_DIR = ROOT / "dictionary"
REGISTRY_PATH = ROOT / "configs" / "registry.yaml"


def main() -> None:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))["dictionaries"]
    registered = set(registry.keys())

    proposals = []
    skipped_empty = []

    for jsonl_path in sorted(DICT_DIR.glob("*_annot_*.jsonl")):
        stem = jsonl_path.stem  # e.g. "en_annot_1WB"
        lang, _, code = stem.partition("_annot_")
        dict_id = f"{code}_{lang}"
        if dict_id in registered:
            continue

        entries = load_entries(str(jsonl_path))
        if not entries:
            skipped_empty.append(dict_id)
            continue

        stats = profile_dictionary(entries)
        profile = suggest_profile(stats)
        proposals.append({
            "dict_id": dict_id,
            "code": code,
            "lang": lang,
            "path": f"../dictionary/{jsonl_path.name}",
            "profile": profile,
            "n": len(entries),
            "avg_len": stats.get("avg_label_len"),
            "ratio_mono": stats.get("ratio_mono"),
        })

    proposals.sort(key=lambda p: (p["code"], p["lang"]))

    print(f"# {len(proposals)} new entries proposed, {len(skipped_empty)} skipped (empty): {skipped_empty}\n")
    for p in proposals:
        print(f"  {p['dict_id']}:")
        print(f"    path: {p['path']}")
        print(f"    lang: {p['lang']}")
        print(f"    profile: {p['profile']}"
              f"{' ' * max(1, 7 - len(p['profile']))}"
              f"# avg_len={p['avg_len']:.2f}, mono={p['ratio_mono']*100:.0f}%, "
              f"n={p['n']}, confirmé par --auto-profile (2026-09-17)")
        print()


if __name__ == "__main__":
    main()
