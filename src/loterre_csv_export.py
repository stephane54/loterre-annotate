#!/usr/bin/env python3
"""Export CSV des candidats d'extraction (term/lemma/postag + champs essentiels).

Module volontairement sans dépendance lourde (stdlib uniquement) : importé à la
fois par loterre_extract_cli.py (subprocess dédié) et loterre_cli.py (process
principal, qui ne doit pas charger spaCy — voir le commentaire sur
_add_extraction_args dans loterre_cli.py). Opère sur les dicts déjà sérialisés
(CandidateTerm.to_dict() ou JSON rechargé), pas sur les objets CandidateTerm.
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, Iterable

CSV_FIELDS = [
    "term",
    "lemma",
    "postag",
    "frequency",
    "score",
    "rule",
    "in_vocabulary",
    "uri",
    "pref",
    "enrichment_suggestion_embed",
    "enrichment_suggestion_structural",
    "enrichment_suggestion_specificity",
    "canonical_form",
    "variant_type",
    "structural_score",
    "structural_rank",
    "specificity_score",
    "specificity_rank",
]


def _postag(candidate: Dict[str, Any]) -> str:
    """Séquence POS du candidat, un tag par token du pattern (ex: "ADJ NOUN")."""
    return " ".join(tok.get("pos", "") for tok in candidate.get("pattern") or [])


def candidates_to_csv(candidates: Iterable[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for candidate in candidates:
        row = {field: candidate.get(field) for field in CSV_FIELDS}
        row["postag"] = _postag(candidate)
        writer.writerow(row)
    return buf.getvalue()
