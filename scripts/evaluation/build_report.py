#!/usr/bin/env python3
"""Génère le rapport d'analyse (src/loterre_report.py) à partir de sorties déjà
calculées, sans relancer extraction ni annotation — même rapport que
`extract_annotate --report`.

Entrées : la sortie JSON d'`extract_annotate` (candidates[] avec occurrences
et enrichment_suggestion_*) et la sortie JSON du moteur d'annotation sur le
même corpus avec le même vocabulaire (`loterre_engine_v9_cli.py --silent`,
results[].matches[]). Avec --text, ajoute aussi le champ `context` aux
candidats ; avec --out-csv, réécrit le CSV des candidats enrichi (n_docs,
nearest_vocab_term si présent, context, topic_id/topic_label/topic_coverage).

Avec --from-report RAPPORT.json, régénère seulement la page HTML à partir du
JSON d'un rapport déjà calculé (après une modification de la mise en page),
en quelques secondes et sans aucune autre entrée.

Usage:
    python3 scripts/evaluation/build_report.py \
        --from-report output_extract/RevueESR_clean2_report.json \
        --output output_extract/RevueESR_clean2_report.html

    python3 scripts/evaluation/build_report.py \
        --input output_extract/RevueESR_extract_annotate_2026-09-30.json \
        --annotations output_extract/RevueESR_annotate_SEN.json \
        --text data/RevueESR-textFR.json \
        --output output_extract/RevueESR_report.html \
        --out-csv output_extract/RevueESR_candidats.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from loterre_csv_export import attach_contexts, candidates_to_csv  # noqa: E402
from loterre_report import render_html, write_report  # noqa: E402


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--input", help="Sortie JSON d'extract_annotate")
    pa.add_argument("--annotations", help="Sortie JSON du moteur d'annotation (même corpus)")
    pa.add_argument("--from-report", help="JSON d'un rapport déjà calculé : régénère seulement la page HTML")
    pa.add_argument("--output", required=True, help="Rapport HTML (un .json est écrit à côté)")
    pa.add_argument("--text", help="Corpus JSONL source, pour le champ context")
    pa.add_argument("--out-csv", help="Réécrit le CSV des candidats enrichi")
    pa.add_argument("--topics", type=int, default=0, help="Nombre de thèmes (0 = automatique)")
    args = pa.parse_args()

    if args.from_report:
        rep = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
        Path(args.output).write_text(render_html(rep["summary"], rep["topics"], rep["meta"]), encoding="utf-8")
        print(f"page régénérée depuis {args.from_report} -> {args.output}")
        return
    if not (args.input and args.annotations):
        pa.error("--input et --annotations sont requis (sauf avec --from-report)")

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    annotations = json.loads(Path(args.annotations).read_text(encoding="utf-8"))
    candidates = data["candidates"]
    for c in candidates:  # sorties antérieures au champ n_docs
        c.setdefault("n_docs", len({o.get("doc_id") for o in c.get("occurrences", [])}))
    attach_contexts(candidates, args.text)
    meta = {
        "corpus": Path(args.text or args.input).name,
        "dict_name": data.get("dict_id") or Path(data.get("dict") or "").stem,
        "extractor": data.get("extractor"),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    report = write_report(args.output, candidates, annotations.get("results", []), data, meta,
                          dict_path=data.get("dict"), n_topics=args.topics)
    if args.out_csv:
        Path(args.out_csv).write_text(candidates_to_csv(candidates), encoding="utf-8", newline="")
    s, t = report["summary"], report["topics"]
    print(f"{s['docs']} documents, {s['n_candidates']} candidats, {s['concepts_found']}/{s['vocabulary_size']} "
          f"concepts du vocabulaire retrouvés, {t['n_topics'] if t else 0} thèmes -> {args.output}")


if __name__ == "__main__":
    main()
