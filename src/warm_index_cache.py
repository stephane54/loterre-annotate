#!/usr/bin/env python3
"""
Pre-build the on-disk index cache (build_indexes_cached in loterre_engine_v9_cli)
for every dictionary registered in configs/registry.yaml.

Intended to be run once (locally or in CI, wherever DVC credentials are
available) whenever a dictionary or a profile in registry.yaml changes, so the
resulting .loterre_index_cache/ directory can be tracked with DVC and pulled
at Docker build time instead of being rebuilt from scratch on every image
build (~18-19 min sequential, dominated by JVR alone at ~12-13 min).

Usage:
    python3 src/warm_index_cache.py
    python3 src/warm_index_cache.py --registry configs/registry.yaml --cache-dir .loterre_index_cache

Then, to ship the result via DVC (from wherever your webdav credentials live):
    dvc add .loterre_index_cache
    dvc push
    git add .loterre_index_cache.dvc .gitignore
    git commit -m "Refresh pre-built annotation index cache"

Groups dict-ids by language and loads each spaCy model once per language
(instead of once per dict-id), running the languages in parallel processes —
build_indexes() is CPU-bound and effectively serial per process, so
cross-language parallelism is the simple, safe win here: JVR alone is ~70% of
total build time and already splits evenly across en/fr.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loterre_engine_v9_cli import (  # noqa: E402
    build_indexes_cached,
    load_entries,
    load_model,
    merge_profile,
)


def _load_registry(path: Path) -> dict:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("dictionaries", {}) or {}


def _warm_lang(lang: str, specs_by_dict_id: dict, registry_dir: Path, cache_dir: str) -> None:
    nlp = load_model(lang)
    for dict_id, spec in specs_by_dict_id.items():
        t0 = time.perf_counter()
        dict_path = str((registry_dir / spec["path"]).resolve())
        profile = merge_profile(spec.get("profile", "term_recall"))
        entries = load_entries(dict_path)
        build_indexes_cached(entries, nlp, profile, dict_path, lang,
                              cache_dir=cache_dir, use_cache=True)
        print(f"[{lang}] {dict_id}: {len(entries)} entries in {time.perf_counter() - t0:.1f}s", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_registry = Path(__file__).resolve().parent.parent / "configs" / "registry.yaml"
    p.add_argument("--registry", default=str(default_registry))
    p.add_argument("--cache-dir", default=None,
                    help="default: LOTERRE_INDEX_CACHE_DIR env var, or <repo>/.loterre_index_cache")
    args = p.parse_args()

    registry_path = Path(args.registry).resolve()
    registry = _load_registry(registry_path)
    if not registry:
        raise SystemExit(f"No dictionaries found in {registry_path}")

    by_lang: dict[str, dict] = {}
    for dict_id, spec in registry.items():
        by_lang.setdefault(spec["lang"], {})[dict_id] = spec

    counts = {lang: len(specs) for lang, specs in by_lang.items()}
    print(f"Warming {len(registry)} dict-id(s) across {len(by_lang)} language(s): {counts}", flush=True)

    t0 = time.perf_counter()
    procs = [
        mp.Process(target=_warm_lang, args=(lang, specs, registry_path.parent, args.cache_dir))
        for lang, specs in by_lang.items()
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join()

    failed = [proc for proc in procs if proc.exitcode != 0]
    if failed:
        raise SystemExit(f"{len(failed)} language worker(s) failed")

    print(f"Done: {len(registry)} dict-id(s) warmed in {time.perf_counter() - t0:.1f}s total", flush=True)


if __name__ == "__main__":
    main()
