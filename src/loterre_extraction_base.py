"""Building blocks shared by the v2.0 extraction modules (NC-value, PositionRank, embeddings).

Kept in a separate file from loterre_engine_v9_cli.py on purpose — the annotation
engine (match_document, dedupe, 5-pass strategy) is tested and stable and must not
be touched by the extraction work. See planification/planif_extraction_terminologique.md
section 0.5 for the rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional

from loterre_engine_v9_cli import load_model


@lru_cache(maxsize=8)
def get_nlp(lang: str, parser: bool = False):
    """Load and cache the spaCy model for *lang*.

    Wraps load_model() with an LRU cache so repeated calls in the same process
    share one model instance instead of reloading it.

    parser=False (default) matches the annotation runtime exactly (disable=
    parser+ner) — use this when only POS+lemma are needed (NC-value scoring,
    dictionary lookup).
    parser=True keeps the dependency parse enabled, required by doc.noun_chunks
    (candidate generation). This loads a second, separate model instance from
    the parser=False one — they are never the same object, so enabling the
    parser here can't slow down or otherwise affect the annotation runtime.
    """
    disable = ("ner",) if parser else ("parser", "ner")
    return load_model(lang, disable=disable)


@dataclass
class Occurrence:
    start: int
    end: int
    doc_id: Any = None  # offsets caractères sont locaux à un document — sans
    # doc_id, deux occurrences de documents différents peuvent partager le même
    # (start, end) par coïncidence (corpus multi-documents).


@dataclass
class CandidateTerm:
    """A term candidate produced by an extraction module.

    Field names mirror the JSONL `candidate` schema decided in Phase 0
    (planif_extraction_terminologique.md), so to_dict() is a direct serialization.
    Vocabulary fields (in_vocabulary/uri/pref) stay None for the extract
    subcommand and are filled in by the dictionary lookup in extract_annotate.
    enrichment_suggestion stays None unless --extractor embed is used in
    extract_annotate (Phase 5) — True means a high-similarity candidate not
    already in the vocabulary, a candidate suggestion for Loterre.
    canonical_form/variant_type stay None unless --detect-variants is passed
    (Phase 4, see loterre_variants.group_variants) — None means this candidate
    is itself canonical (or wasn't grouped); otherwise canonical_form holds
    the term of the candidate it was grouped under.
    """
    term: str
    lemma: str
    pattern: list[dict[str, str]]
    frequency: int
    score: float
    rule: str
    occurrences: list[Occurrence] = field(default_factory=list)
    in_vocabulary: Optional[bool] = None
    uri: Optional[str] = None
    pref: Optional[str] = None
    enrichment_suggestion: Optional[bool] = None
    canonical_form: Optional[str] = None
    variant_type: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "term": self.term,
            "lemma": self.lemma,
            "pattern": self.pattern,
            "frequency": self.frequency,
            "score": self.score,
            "rule": self.rule,
            "in_vocabulary": self.in_vocabulary,
            "pref": self.pref,
            "enrichment_suggestion": self.enrichment_suggestion,
            "canonical_form": self.canonical_form,
            "variant_type": self.variant_type,
            "occurrences": [{"start": o.start, "end": o.end, "doc_id": o.doc_id} for o in self.occurrences],
        }
