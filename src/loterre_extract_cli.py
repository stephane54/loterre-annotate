#!/usr/bin/env python3
"""Mode extract — collecte de candidats termes par noun chunks (Phase 1, v2.0).

Étape de base de l'extraction : noun chunks spaCy + filtres POS/stopwords/ponctuation
+ comptage de fréquence sur le corpus. Le scoring NC-value (Phase 2) n'est pas encore
implémenté ici — le champ "score" vaut la fréquence brute en attendant.

Fichier séparé de loterre_engine_v9_cli.py par design (voir
planification/planif_extraction_terminologique.md §0.5) : ne touche pas au moteur
d'annotation testé.

Usage:
    python3 src/loterre_extract_cli.py --text data/jsonl/P66_en.jsonl --lang en --silent
    cat data/jsonl/P66_fr.jsonl | python3 src/loterre_extract_cli.py --lang fr
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from loterre_cvalue import filter_by_threshold, score_candidates
from loterre_extraction_base import CandidateTerm, Occurrence, get_nlp

# POS à retirer des bords d'un chunk (déterminants, ponctuation, etc.) pour ne
# garder que le contenu lexical : "the quick brown fox" -> "quick brown fox".
_EDGE_STRIP_POS = frozenset({"DET", "PRON", "ADP", "CCONJ", "SCONJ", "PUNCT", "PART", "AUX"})
_CONTENT_POS = frozenset({"NOUN", "PROPN", "ADJ"})


def clean_chunk_span(chunk):
    """Retire les tokens non lexicaux en tête/fin d'un noun chunk."""
    start, end = 0, len(chunk)
    while start < end and chunk[start].pos_ in _EDGE_STRIP_POS:
        start += 1
    while end > start and chunk[end - 1].pos_ in _EDGE_STRIP_POS:
        end -= 1
    return chunk[start:end]


def is_valid_candidate(span, min_tokens: int, max_tokens: int) -> bool:
    if len(span) == 0 or not (min_tokens <= len(span) <= max_tokens):
        return False
    if not any(t.pos_ in _CONTENT_POS for t in span):
        return False
    if all(t.is_stop for t in span):
        return False
    if any(t.is_punct or t.is_space for t in span):
        return False
    return True


def extract_candidates(
    rows: list[dict[str, Any]], lang: str, min_tokens: int, max_tokens: int, min_freq: int
) -> tuple[list[CandidateTerm], int, list[list[tuple[int, str, str]]]]:
    """Collecte les candidats noun-chunks sur un corpus, filtrés et comptés en
    fréquence — et capture en même passage spaCy les données nécessaires à
    PositionRank (per_doc_tokens) et à la décision auto ncvalue/graph
    (total_tokens), pour éviter de retraiter le corpus deux fois selon
    l'extracteur choisi ensuite (voir score_extracted_candidates())."""
    nlp = get_nlp(lang, parser=True)
    occurrences: dict[str, list[Occurrence]] = defaultdict(list)
    patterns: dict[str, list[dict[str, str]]] = {}
    lemmas: dict[str, str] = {}
    per_doc_tokens: list[list[tuple[int, str, str]]] = []
    total_tokens = 0

    for row, doc in zip(rows, nlp.pipe((r["value"] for r in rows), batch_size=64)):
        doc_id = row.get("id")
        total_tokens += len(doc)
        per_doc_tokens.append([(i, t.lemma_.lower(), t.pos_) for i, t in enumerate(doc)])
        for chunk in doc.noun_chunks:
            span = clean_chunk_span(chunk)
            if not is_valid_candidate(span, min_tokens, max_tokens):
                continue
            term = span.text
            occurrences[term].append(Occurrence(span.start_char, span.end_char, doc_id))
            if term not in patterns:
                patterns[term] = [{"pos": t.pos_, "lemma": t.lemma_.lower()} for t in span]
                lemmas[term] = " ".join(t.lemma_.lower() for t in span)

    candidates = []
    for term, occs in occurrences.items():
        freq = len(occs)
        if freq < min_freq:
            continue
        candidates.append(CandidateTerm(
            term=term,
            lemma=lemmas[term],
            pattern=patterns[term],
            frequency=freq,
            score=float(freq),  # placeholder — remplacé par score_extracted_candidates()
            rule="noun_chunk",
            occurrences=occs,
        ))
    candidates.sort(key=lambda c: -c.frequency)
    return candidates, total_tokens, per_doc_tokens


def score_extracted_candidates(
    candidates: list[CandidateTerm],
    per_doc_tokens: list[list[tuple[int, str, str]]],
    total_tokens: int,
    extractor: str,
    auto_threshold: int,
) -> tuple[list[CandidateTerm], str]:
    """Choisit l'algorithme de scoring et l'applique.

    extractor="auto" bascule sur le volume du corpus (voir
    planification/analyse_benchmarks_extraction.md, §Dépendance au volume) :
    C-value a besoin d'au moins ~50 000 tokens pour que ses statistiques de
    fréquence soient fiables ; en dessous, PositionRank (qui ne dépend pas des
    fréquences de termes emboîtés) est plus adapté.
    """
    if extractor == "auto":
        extractor = "graph" if total_tokens < auto_threshold else "ncvalue"

    if extractor == "graph":
        from loterre_positionrank import build_cooccurrence_graph, position_rank, score_candidates_positionrank
        graph, position_weight = build_cooccurrence_graph(per_doc_tokens)
        word_scores = position_rank(graph, position_weight)
        return score_candidates_positionrank(candidates, word_scores), extractor

    return score_candidates(candidates), extractor


def cross_reference_candidates(candidates: list[dict[str, Any]], annotation_results: list[dict[str, Any]]) -> None:
    """Mode extract_annotate (Phase 3) : enrichit en place les dicts candidats
    (déjà désérialisés depuis le JSON d'extraction) avec in_vocabulary/uri/pref,
    en croisant par (doc_id, span exact) avec les matches du moteur d'annotation
    existant sur le même corpus — pas de réimplémentation du lookup Trie, on
    réutilise le moteur tel quel (règle Phase 0.5).

    annotation_results : la liste payload["results"] de l'annotateur, telle
    quelle (chaque élément a "id" et "matches") — surtout NE PAS aplatir les
    matches sans le doc_id : les offsets caractères sont locaux à un document,
    donc deux occurrences de documents différents peuvent partager le même
    (start, end) par coïncidence.

    Span exact (pas simple chevauchement) : un candidat composé qui contient un
    terme plus court reconnu séparément par l'annotateur (ex. "controlled memory
    assessment" contenant "memory") ne doit pas être faussement attribué à ce
    sous-terme — seule une correspondance de span identique compte.
    """
    matches_by_doc_span: dict[tuple[Any, int, int], dict[str, Any]] = {}
    for result in annotation_results:
        doc_id = result.get("id")
        for m in result.get("matches", []):
            matches_by_doc_span.setdefault((doc_id, m["start"], m["end"]), m)

    for c in candidates:
        found = None
        for occ in c.get("occurrences", []):
            found = matches_by_doc_span.get((occ.get("doc_id"), occ["start"], occ["end"]))
            if found:
                break
        c["in_vocabulary"] = found is not None
        if found:
            c["uri"] = found.get("uri", "")
            c["pref"] = found.get("pref", "")


def read_rows(text_path: str | None) -> list[dict[str, Any]]:
    raw = Path(text_path).read_text(encoding="utf-8") if text_path else sys.stdin.read()
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def add_extraction_args(parser: argparse.ArgumentParser) -> None:
    """Ajoute les paramètres d'extraction à *parser*.

    Factorisé ici et réutilisé par les sous-commandes extract/extract_annotate
    de loterre_cli.py (au lieu d'une 2ᵉ définition qui dériverait avec le temps).
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
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--text", help="Chemin JSONL ; lit stdin si omis")
    p.add_argument("--lang", choices=["en", "fr"], required=True)
    add_extraction_args(p)
    p.add_argument("--out", default=None)
    p.add_argument("--silent", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    rows = read_rows(args.text)
    candidates, total_tokens, per_doc_tokens = extract_candidates(
        rows, args.lang, args.min_tokens, args.max_tokens, args.min_freq
    )
    candidates, extractor_used = score_extracted_candidates(
        candidates, per_doc_tokens, total_tokens, args.extractor, args.extractor_auto_threshold
    )
    if args.cvalue_threshold > 0 and extractor_used == "ncvalue":
        candidates = filter_by_threshold(candidates, args.cvalue_threshold)
    if args.max_terms:
        candidates = candidates[: args.max_terms]

    payload = {
        "mode": "extract",
        "lang": args.lang,
        "docs": len(rows),
        "total_tokens": total_tokens,
        "extractor": extractor_used,
        "candidates": [c.to_dict() for c in candidates],
    }
    data = json.dumps(payload, ensure_ascii=False, indent=None if args.silent else 2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(data, encoding="utf-8")
    else:
        print(data)


if __name__ == "__main__":
    main()
