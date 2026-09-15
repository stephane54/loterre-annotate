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
    enrichment_suggestion_embed stays None unless --extractor embed is used in
    extract_annotate (Phase 5) — True means a high-similarity candidate not
    already in the vocabulary, a candidate suggestion for Loterre.
    canonical_form/variant_type stay None unless --detect-variants is passed
    (Phase 4, see loterre_variants.group_variants) — None means this candidate
    is itself canonical (or wasn't grouped); otherwise canonical_form holds
    the term of the candidate it was grouped under.
    structural_score/structural_rule/structural_rank stay None unless
    --extractor embed is used — second signal, independent of the target
    vocabulary (C-value or PositionRank, same auto choice as a normal
    extractor run), attached alongside the embed similarity score so a
    candidate far from any vocabulary term but statistically/structurally
    term-like isn't invisible (see loterre_extract_cli._attach_structural_signal
    and CLAUDE.md/planification/analyse_benchmarks_extraction.md, entrée
    2026-09-07). Never overwrites score/rule, which stay the embed similarity.
    specificity_score/specificity_rank (Weirdness Ratio against a
    general-language reference corpus, resources/termsuite_general_language/,
    loterre_specificity.score_candidates_specificity) are populated in two
    distinct situations: (1) --specificity-filter-pctl > 0 with --extractor
    ncvalue — pre-filter, calibrated 2026-09-11, for whichever candidates
    survive; (2) always for --extractor embed (like structural_score) — used
    to compute enrichment_suggestion_specificity below. Never validated with
    graph as a filter.
    enrichment_suggestion_specificity stays None/False unless --extractor
    embed AND --specificity-top-pct > 0 (disabled by default, unlike
    structural — measured isolated precision ~0.27-0.30 on ACTER, markedly
    noisier than structural's ~0.64, an explicit curator opt-in rather than a
    safe default). Mutually exclusive with enrichment_suggestion_embed and
    enrichment_suggestion_structural (set in loterre_cli.run_extract_annotate_mode,
    see planification/analyse_benchmarks_extraction.md, entrée 2026-09-11).
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
    enrichment_suggestion_embed: Optional[bool] = None
    enrichment_suggestion_structural: Optional[bool] = None
    enrichment_suggestion_specificity: Optional[bool] = None
    canonical_form: Optional[str] = None
    variant_type: Optional[str] = None
    structural_score: Optional[float] = None
    structural_rule: Optional[str] = None
    structural_rank: Optional[int] = None
    specificity_score: Optional[float] = None
    specificity_rank: Optional[int] = None

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
            "enrichment_suggestion_embed": self.enrichment_suggestion_embed,
            "enrichment_suggestion_structural": self.enrichment_suggestion_structural,
            "enrichment_suggestion_specificity": self.enrichment_suggestion_specificity,
            "canonical_form": self.canonical_form,
            "variant_type": self.variant_type,
            "structural_score": self.structural_score,
            "structural_rule": self.structural_rule,
            "structural_rank": self.structural_rank,
            "specificity_score": self.specificity_score,
            "specificity_rank": self.specificity_rank,
            "occurrences": [{"start": o.start, "end": o.end, "doc_id": o.doc_id} for o in self.occurrences],
        }
