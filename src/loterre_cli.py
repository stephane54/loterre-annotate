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
    # When the package is installed (pip install), __file__ ends up several
    # levels deep inside site-packages. Walk up until we find configs/ so
    # the CLI works both from the source tree and from an installed wheel.
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
    # getattr() partout ici : selon la sous-commande (annotate/extract/
    # extract_annotate), certains attributs (dict_id/dict/profile/config)
    # n'existent pas sur le namespace args — extract n'a pas de vocabulaire.
    config_path = getattr(args, "config", None)
    config = load_yaml(Path(config_path).resolve()) if config_path else {}
    registry_path = Path(args.registry).resolve()
    registry = load_registry(registry_path)

    dict_id = getattr(args, "dict_id", None) or resolve_config_value(config, "dict_id")
    reg_entry = registry.get(dict_id, {}) if dict_id else {}

    dict_path = (
        getattr(args, "dict", None)
        or resolve_config_value(config, "dictionary", "dict")
        or reg_entry.get("path")
    )
    lang = args.lang or resolve_config_value(config, "lang", "language") or reg_entry.get("lang")
    profile = getattr(args, "profile", None) or resolve_config_value(config, "profile") or reg_entry.get("profile")
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
    # The engine is invoked as a subprocess rather than imported because it
    # loads a spaCy model into memory that we don't want to share with the
    # fast-path process. The subprocess boundary also isolates any engine
    # crashes from the caller and lets unknown_args pass through verbatim.
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


def run_extraction_subprocess(args, effective: Dict[str, Any]) -> Dict[str, Any]:
    # Subprocess boundary for the same reason as run_engine_full_json: the
    # extraction module loads its own spaCy model (parser enabled, see
    # loterre_extraction_base.get_nlp) and must not share state with this process.
    # Les paramètres d'extraction sont désormais explicitement définis sur les
    # sous-commandes extract/extract_annotate (add_extraction_args) plutôt que
    # transmis via unknown_args — on les reconstruit ici en flags explicites.
    script = Path(__file__).with_name("loterre_extract_cli.py")
    if not script.exists():
        raise SystemExit(f"ERROR: extraction module not found: {script}")

    cmd = [sys.executable, str(script), "--silent"]
    if effective.get("text"):
        cmd.extend(["--text", effective["text"]])
    if effective.get("lang"):
        cmd.extend(["--lang", effective["lang"]])
    cmd.extend(["--min-tokens", str(args.min_tokens)])
    cmd.extend(["--max-tokens", str(args.max_tokens)])
    cmd.extend(["--min-freq", str(args.min_freq)])
    cmd.extend(["--cvalue-threshold", str(args.cvalue_threshold)])
    cmd.extend(["--extractor", args.extractor])
    cmd.extend(["--extractor-auto-threshold", str(args.extractor_auto_threshold)])
    if args.max_terms:
        cmd.extend(["--max-terms", str(args.max_terms)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "extraction module failed\n"
            f"Command: {' '.join(cmd)}\n"
            f"STDERR:\n{proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"extraction module did not return valid JSON: {exc}") from exc


def run_extract_mode(args, effective: Dict[str, Any]) -> None:
    if not effective.get("lang"):
        raise SystemExit("ERROR: --lang is required for extract")
    payload = run_extraction_subprocess(args, effective)
    write_or_print_json(payload, args.out)


def run_extract_annotate_mode(args, effective: Dict[str, Any]) -> None:
    if not effective.get("lang"):
        raise SystemExit("ERROR: --lang is required for extract_annotate")
    if not effective.get("dict"):
        raise SystemExit("ERROR: --dict or --dict-id with registry path is required for extract_annotate")

    from loterre_extract_cli import cross_reference_candidates

    extraction_payload = run_extraction_subprocess(args, effective)
    annotation_payload = run_engine_full_json(effective, effective["text"], [])

    candidates = extraction_payload.get("candidates", [])
    cross_reference_candidates(candidates, annotation_payload.get("results", []))

    payload = {
        **extraction_payload,
        "mode": "extract_annotate",
        "dict_id": effective.get("dict_id"),
        "dict": effective.get("dict"),
    }
    write_or_print_json(payload, args.out)


def result_has_ambiguity(result: Dict[str, Any], args) -> bool:
    # Decide whether a fast-path result should be sent to the v9 engine for
    # refinement. Four independent signals trigger refinement:
    #   1. A surface form maps to multiple concepts (score=0.85, ambiguous=True).
    #   2. Unusually many matches — likely a noisy / over-general dictionary hit.
    #   3. Single-token matches, which have higher false-positive rates than
    #      multi-token terms (opt-in via --hybrid-refine-single-tokens).
    #   4. Any match below the low-score threshold (default 0.90 — catches the
    #      0.85 ambiguous matches without re-examining clean 1.0 matches).
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
    # Hybrid strategy: run the fast exact-match path on the full corpus first,
    # then send only the ambiguous/uncertain documents through the v9 spaCy engine.
    # Typical split: ~80 % of docs come back from fast-path, ~20 % need refinement.
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
        # Write the subset to a temp JSONL file because the engine only accepts
        # a file path as input (no stdin streaming in subprocess mode).
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


def _add_extraction_args(parser: argparse.ArgumentParser) -> None:
    """Paramètres d'extraction pour les sous-commandes extract/extract_annotate.

    Dupliqué (volontairement, pas importé) depuis loterre_extract_cli.add_extraction_args :
    importer ce module depuis loterre_cli.py chargerait spacy au niveau module
    (mesuré : ~1.3s) à chaque invocation de la CLI, y compris --execution-strategy
    fast qui doit justement rester libre de tout coût spaCy dans ce process — la
    frontière subprocess existe précisément pour ça (voir run_engine_full_json).
    """
    parser.add_argument("--min-tokens", type=int, default=1,
                         help="Longueur minimale d'un candidat, en tokens (défaut 1)")
    parser.add_argument("--max-tokens", type=int, default=6,
                         help="Longueur maximale d'un candidat (défaut 6)")
    parser.add_argument("--min-freq", type=int, default=2,
                         help="Fréquence minimale dans le corpus pour retenir un candidat (défaut 2)")
    parser.add_argument("--cvalue-threshold", type=float, default=0.0,
                         help="Score C-value minimal (ou fréquence normalisée pour les mono-tokens) ; "
                              "0 = pas de filtre (défaut 0.0)")
    parser.add_argument("--extractor", choices=["ncvalue", "graph", "auto"], default="auto",
                         help="Algorithme de scoring (défaut auto) : ncvalue=C-value (corpus volumineux), "
                              "graph=PositionRank (corpus court), auto=bascule selon --extractor-auto-threshold")
    parser.add_argument("--extractor-auto-threshold", type=int, default=50000,
                         help="Nombre de tokens du corpus en dessous duquel --extractor auto bascule "
                              "vers PositionRank (défaut 50000)")
    parser.add_argument("--max-terms", type=int, default=None,
                         help="Garde les N meilleurs candidats, triés par score décroissant (défaut illimité)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Loterre v9 CLI — annotation par dictionnaire (v1.0) et extraction terminologique (v2.0)",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # ── annotate ──────────────────────────────────────────────────────────
    p_annotate = subparsers.add_parser(
        "annotate",
        help="Annoter un texte avec un vocabulaire Loterre (comportement v1.0, inchangé)",
        description="Annote un texte avec un vocabulaire Loterre (comportement v1.0, inchangé).",
    )
    p_annotate.add_argument("--dict-id", help="Identifiant du vocabulaire dans le registre (ex: P66_en) — ou --dict, ou via --config")
    p_annotate.add_argument("--dict", help="Chemin direct vers un dictionnaire JSONL (alternative à --dict-id)")
    p_annotate.add_argument("--profile", choices=["entity_strict", "term_balanced", "term_recall"],
                             help="Profil de qualité (requis, sauf si fourni via --config)")
    p_annotate.add_argument("--registry", default=_find_registry(), help="Chemin du registre des vocabulaires (configs/registry.yaml)")
    p_annotate.add_argument("--config", help="Fichier de config YAML optionnel (peut fournir dict-id/lang/profile)")
    p_annotate.add_argument("--text", help="Fichier JSONL source ({\"id\":..., \"value\":...} par ligne) ; lit stdin si omis")
    p_annotate.add_argument("--lang", choices=["en", "fr"], help="Langue (optionnel, déduite du dict sinon)")
    p_annotate.add_argument("--execution-strategy", choices=["full", "fast", "hybrid"], default="full",
                             help="full=spaCy complet (défaut), fast=regex sans spaCy, hybrid=fast puis ré-examen spaCy des cas ambigus")
    p_annotate.add_argument("--out", help="Fichier de sortie (sinon stdout)")
    p_annotate.add_argument("--report", help="Fichier de rapport Markdown additionnel")
    p_annotate.add_argument("--silent", action="store_true", help="Sortie JSON compacte (sans fichiers intermédiaires)")
    p_annotate.add_argument("--api", action="store_true", help="Payload JSON compact pour API")
    p_annotate.add_argument("--cache-dir", default=".loterre_cache", help="[fast/hybrid] Répertoire de cache regex")
    p_annotate.add_argument("--case-sensitive", action="store_true", help="[fast/hybrid] Matching sensible à la casse")
    p_annotate.add_argument("--max-regex-terms", type=int, help="[fast/hybrid] Limite de termes compilés en regex")
    p_annotate.add_argument("--hybrid-refine-single-tokens", action="store_true",
                             help="[hybrid] Ré-examine aussi les matches à un seul token")
    p_annotate.add_argument("--hybrid-refine-low-score", type=float, default=0.90,
                             help="[hybrid] Seuil de score sous lequel un match est ré-examiné (défaut 0.90)")
    p_annotate.add_argument("--hybrid-max-fast-matches", type=int, default=50,
                             help="[hybrid] Au-delà de ce nombre de matches, ré-examen complet du document (défaut 50)")

    # ── extract ───────────────────────────────────────────────────────────
    p_extract = subparsers.add_parser(
        "extract",
        help="Extraire des candidats termes d'un texte (sans vocabulaire)",
        description="Extrait des candidats termes d'un texte, sans vocabulaire.",
    )
    p_extract.add_argument("--lang", choices=["en", "fr"], help="Langue (requis)")
    p_extract.add_argument("--text", help="Fichier JSONL source ({\"id\":..., \"value\":...} par ligne) ; lit stdin si omis")
    p_extract.add_argument("--registry", default=_find_registry(), help=argparse.SUPPRESS)
    p_extract.add_argument("--out", help="Fichier de sortie (sinon stdout)")
    p_extract.add_argument("--silent", action="store_true", help="Sortie JSON compacte")
    _add_extraction_args(p_extract)

    # ── extract_annotate ─────────────────────────────────────────────────
    p_ea = subparsers.add_parser(
        "extract_annotate",
        help="Extraire des candidats termes puis les croiser avec un vocabulaire Loterre",
        description="Extrait des candidats termes puis les croise avec un vocabulaire Loterre.",
    )
    p_ea.add_argument("--lang", choices=["en", "fr"], help="Langue (requis)")
    p_ea.add_argument("--dict-id", help="Identifiant du vocabulaire dans le registre — ou --dict (requis)")
    p_ea.add_argument("--dict", help="Chemin direct vers un dictionnaire JSONL")
    p_ea.add_argument("--profile", choices=["entity_strict", "term_balanced", "term_recall"], help="Profil de qualité (requis)")
    p_ea.add_argument("--registry", default=_find_registry(), help="Chemin du registre des vocabulaires (configs/registry.yaml)")
    p_ea.add_argument("--config", help="Fichier de config YAML optionnel")
    p_ea.add_argument("--text", help="Fichier JSONL source ({\"id\":..., \"value\":...} par ligne) ; lit stdin si omis")
    p_ea.add_argument("--out", help="Fichier de sortie (sinon stdout)")
    p_ea.add_argument("--silent", action="store_true", help="Sortie JSON compacte")
    _add_extraction_args(p_ea)

    return parser


def main() -> None:
    parser = build_parser()
    args, unknown_args = parser.parse_known_args()

    effective = resolve_effective_params(args)

    if args.mode == "extract":
        run_extract_mode(args, effective)
        return
    if args.mode == "extract_annotate":
        run_extract_annotate_mode(args, effective)
        return

    # args.mode == "annotate" à partir d'ici — seul ce sous-parser définit
    # hybrid_refine_low_score / execution_strategy / etc.
    if args.hybrid_refine_low_score is not None and args.hybrid_refine_low_score < 0:
        args.hybrid_refine_low_score = None

    if args.execution_strategy == "fast":
        run_fast_mode(args, effective)
    elif args.execution_strategy == "hybrid":
        run_hybrid_mode(args, effective, unknown_args)
    else:
        run_full_mode(args, effective, unknown_args)


if __name__ == "__main__":
    main()
