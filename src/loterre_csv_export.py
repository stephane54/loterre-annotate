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
import json
from typing import Any, Dict, Iterable, Optional

CONTEXT_CHARS = 70  # caractères gardés de part et d'autre du terme dans `context`

CSV_FIELDS = [
    "term",
    "lemma",
    "postag",
    "frequency",
    "n_docs",
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
    "nearest_vocab_term",
    "context",
    "topic_id",
    "topic_label",
    "topic_coverage",
    "topic_generic",
]


def attach_contexts(candidates: Iterable[Dict[str, Any]], text_path: Optional[str]) -> None:
    """Ajoute à chaque candidat (dict sérialisé) un champ `context` : extrait
    du texte autour de sa première occurrence, terme entre crochets
    ("… la prise en charge des [maladies professionnelles] chez les …") —
    pour juger un candidat sans rouvrir le corpus. Relit le fichier source
    JSONL ({"id":..., "value":...} par ligne) ; sans fichier (lecture depuis
    stdin), ne fait rien."""
    if not text_path:
        return
    texts: Dict[Any, str] = {}
    with open(text_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                texts[row.get("id")] = row.get("value") or ""
    for c in candidates:
        occs = c.get("occurrences") or []
        if not occs:
            continue
        occ = occs[0]
        text = texts.get(occ.get("doc_id"))
        if not text:
            continue
        start, end = occ["start"], occ["end"]
        before = text[max(0, start - CONTEXT_CHARS):start]
        after = text[end:end + CONTEXT_CHARS]
        snippet = f"{'…' if start > CONTEXT_CHARS else ''}{before}[{text[start:end]}]{after}" \
                  f"{'…' if end + CONTEXT_CHARS < len(text) else ''}"
        c["context"] = " ".join(snippet.split())


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
