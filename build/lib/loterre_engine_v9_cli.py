#!/usr/bin/env python3
"""
Loterre Engine v9

Features
--------
- single configurable engine
- 3 generic profiles
- YAML config support
- stdin support
- silent/api JSON stdout
- markdown annotation in JSON results
- optional multiprocessing for document batches
- optional streaming mode
- structured logging
- optional input validation
- no cache
- proper config/CLI precedence:
  * without --config: required values must come from CLI
  * with --config: values can come from YAML
  * CLI overrides YAML when both are provided
"""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import spacy

try:
    import yaml
except Exception:
    yaml = None

SEP_RE = re.compile(r"[-‐‑‒–—−/⁄_]+")
MULTISPACE_RE = re.compile(r"\s+")
_PUNCT_KEEP_APOS_RE = re.compile(r"[^\w\s'()]")
_PUNCT_RE = re.compile(r"[^\w\s()]")

_RESOURCES_DIR = Path(os.environ["LOTERRE_RESOURCES_DIR"]) if "LOTERRE_RESOURCES_DIR" in os.environ \
    else Path(__file__).parent.parent / "resources"


def _load_word_set(path: Path, fallback: frozenset) -> frozenset:
    """Load a frozenset of words from a text file (one word per line, # comments).
    Returns fallback if the file is missing or unreadable."""
    try:
        words = {
            w for line in path.read_text(encoding="utf-8").splitlines()
            for w in [line.strip()]
            if w and not w.startswith("#")
        }
        return frozenset(words) if words else fallback
    except Exception:
        return fallback


def _load_spacy_models(path: Path, fallback: dict) -> dict:
    """Load spaCy model candidates from a YAML file. Returns fallback on error."""
    try:
        if yaml and path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {lang: list(models) for lang, models in data.items() if isinstance(models, list)}
    except Exception:
        pass
    return fallback


# ── Constantes POS/lexicales — définies ici pour éviter leur reconstruction
# à chaque appel de score_match_quality (fonction dans le hot path). ─────────
_STOP_POS = frozenset({"CCONJ", "SCONJ", "DET", "PRON", "AUX", "PART", "ADP", "INTJ"})
_CONTENT_POS = frozenset({"NOUN", "PROPN", "ADJ"})

_WEAK_WORDS_EN = _load_word_set(
    _RESOURCES_DIR / "en" / "weak_words.txt",
    frozenset({"and", "or", "it", "well", "can", "may", "like"}),
)
_WEAK_WORDS_FR = _load_word_set(
    _RESOURCES_DIR / "fr" / "weak_words.txt",
    frozenset({"et", "ou", "ni", "mais", "il", "elle", "on", "bien", "ainsi", "comme"}),
)
_WEAK_WORDS = _WEAK_WORDS_EN  # alias rétrocompatible

_SPACY_MODELS = _load_spacy_models(
    _RESOURCES_DIR / "spacy_models.yaml",
    {"en": ["en_core_web_sm", "en_core_web_md"], "fr": ["fr_core_news_sm", "fr_core_news_md"]},
)
_SYNTACTIC_GENERIC_DEFAULT = frozenset({
    "process", "quality", "thing", "matter", "way",         # EN
    "processus", "qualite", "chose", "fait", "maniere",     # FR (sans accent)
})
_RELATIVE_PRONOUNS_DEFAULT = frozenset({
    "that", "which", "who", "whom", "whose",                # EN
    "que", "qui", "dont", "lequel", "laquelle",             # FR
    "lesquels", "lesquelles", "duquel", "auquel",
})
_PROFILE_MIN_SCORES: Dict[str, float] = {
    "entity_strict": 0.80,
    "term_balanced": 0.75,
    "term_recall": 0.70,
}

DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    "entity_strict": {
        "use_pattern": True, "use_surface": True, "use_lemma": False,
        "pattern_priority": True, "allow_surface_fallback": True,
        "allow_single_token_fallback": False, "single_token_uppercase_exact": True,
        "propn_can_match_noun": True, "normalize_separators": True,
        "normalize_apostrophes": True, "normalize_parentheses": True,
        "batch_size": 64,
    },
    "term_balanced": {
        "use_pattern": True, "use_surface": True, "use_lemma": True,
        "pattern_priority": False, "allow_surface_fallback": True,
        "allow_single_token_fallback": True, "single_token_uppercase_exact": False,
        "propn_can_match_noun": True, "normalize_separators": True,
        "normalize_apostrophes": True, "normalize_parentheses": True,
        "batch_size": 64,
    },
    "term_recall": {
        "use_pattern": True, "use_surface": True, "use_lemma": True,
        "pattern_priority": False, "allow_surface_fallback": True,
        "allow_single_token_fallback": True, "single_token_uppercase_exact": False,
        "propn_can_match_noun": True, "normalize_separators": True,
        "normalize_apostrophes": True, "normalize_parentheses": True,
        "batch_size": 64,
    },
}

QUALITY_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "strict_stopwords": True,
    "require_pos_match": True,
    "penalize_single_token": True,
    "single_token_penalty": 0.15,
    "adaptive_single_token_penalty": True,
    "multi_token_bonus": 0.03,
    "case_sensitive_entities": True,
    "context_guard": True,
    "contextual_scoring": True,
    "context_window": 2,
    "discourse_pattern_guard": True,
    "syntactic_context_guard": False,
    "syntactic_adp_head_penalty": 0.15,
    "function_context_penalty": 0.20,
    "lexical_context_bonus": 0.05,
    "exact_pos_bonus": 0.05,
    "single_token_min_score": 0.75,
}

@dataclass
class ResourceProfile:
    """Configuration wrapper for a selected profile."""
    name: str
    params: Dict[str, Any]

@dataclass
class FlatView:
    """Flattened token view used for sequence matching."""
    tokens: List[str]
    flat_to_spacy: List[int]

class TrieNode:
    """A node in a token trie."""
    __slots__ = ("children", "payloads")
    def __init__(self):
        self.children = {}
        self.payloads = []

class SeqTrie:
    """Trie for longest sequence matching."""
    def __init__(self):
        self.root = TrieNode()

    def add(self, seq: Tuple[str, ...], payload: Dict[str, Any]) -> None:
        """Insert one token sequence into the trie."""
        node = self.root
        for tok in seq:
            node = node.children.setdefault(tok, TrieNode())
        node.payloads.append(payload)

    def iter_longest(self, tokens: List[str], start: int):
        """Return the longest matching sequence starting at `start`."""
        node = self.root
        longest = None
        i = start
        while i < len(tokens):
            nxt = node.children.get(tokens[i])
            if nxt is None:
                break
            node = nxt
            if node.payloads:
                longest = (i + 1, node.payloads)
            i += 1
        return longest

def setup_logging(level: str) -> None:
    """Configure structured stderr logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

def load_model(lang: str):
    """Load a spaCy model for the requested language."""
    candidates = _SPACY_MODELS.get(lang)
    if not candidates:
        raise RuntimeError(f"No spaCy model configured for language '{lang}'. Add it to resources/spacy_models.yaml")
    for name in candidates:
        try:
            return spacy.load(name, disable=["parser", "ner"])
        except Exception:
            pass
    raise RuntimeError(f"No spaCy model installed for {lang}. Install one of: {candidates}")

def merge_profile(profile_name: str, overrides: Optional[Dict[str, Any]] = None) -> ResourceProfile:
    """Merge a default profile with optional overrides."""
    params = dict(DEFAULT_PROFILES[profile_name])
    if overrides:
        params.update(overrides)
    return ResourceProfile(name=profile_name, params=params)

def merge_quality(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge default quality settings with optional overrides."""
    params = dict(QUALITY_DEFAULTS)
    if overrides:
        params.update(overrides)
    return params

@lru_cache(maxsize=16384)
def normalize_text(
    s: str,
    normalize_separators: bool = True,
    normalize_apostrophes: bool = True,
    keep_apostrophe: bool = False,
) -> str:
    """Normalize typography and punctuation for matching."""
    if normalize_apostrophes:
        s = s.replace("’", "'").replace("‘", "'")
    s = s.lower()
    if normalize_separators:
        s = SEP_RE.sub(" ", s)
    if keep_apostrophe:
        s = _PUNCT_KEEP_APOS_RE.sub(" ", s)
    else:
        s = _PUNCT_RE.sub(" ", s)
        s = s.replace("'", "")
    return MULTISPACE_RE.sub(" ", s).strip()

def normalize_token_list(s: str, profile: ResourceProfile) -> List[str]:
    """Normalize a string and split it into matching tokens."""
    return [t for t in normalize_text(
        s,
        normalize_separators=profile.params["normalize_separators"],
        normalize_apostrophes=profile.params["normalize_apostrophes"],
        keep_apostrophe=False,
    ).split() if t]

def load_entries(path: str) -> List[Dict[str, Any]]:
    """Load a terminology dictionary from a JSONL file."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def validate_row(obj: Dict[str, Any], line_no: int) -> None:
    """Validate one JSONL input row."""
    if not isinstance(obj, dict):
        raise ValueError(f"Line {line_no}: JSON object expected")
    if "value" not in obj:
        raise ValueError(f"Line {line_no}: missing 'value'")
    if not isinstance(obj["value"], str):
        raise ValueError(f"Line {line_no}: 'value' must be a string")

def read_text_rows(text_path: Optional[str], validate: bool = False) -> List[Dict[str, Any]]:
    """Read JSONL texts from a file or from stdin."""
    if text_path:
        raw = Path(text_path).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    rows = []
    for i, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if validate:
            validate_row(obj, i)
        rows.append(obj)
    return rows


def profile_dictionary(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute richer statistics used for profile suggestion, quality suggestion and reporting."""
    n = len(entries)
    mono = with_pattern = upper_single = puncty = 0
    short_single = alpha_single = title_single = 0
    risky_single = 0
    risky_forms = {"well", "and", "or", "it", "can", "may", "like", "kind", "spring", "left", "right"}
    label_lengths = []
    pattern_pos = Counter()

    for e in entries:
        label = str(e.get("label", "")).strip()
        toks = label.split()
        label_lengths.append(len(toks))

        if len(toks) <= 1:
            mono += 1
            lab_low = label.lower()
            if len(lab_low) <= 4:
                short_single += 1
            if lab_low.isalpha():
                alpha_single += 1
            if label[:1].isupper() and label[1:].islower():
                title_single += 1
            if lab_low in risky_forms:
                risky_single += 1

        if e.get("pattern"):
            with_pattern += 1
            for spec in e["pattern"]:
                if "pos" in spec:
                    pattern_pos[spec["pos"]] += 1

        if label.isupper() and len(toks) == 1:
            upper_single += 1
        if any(ch in label for ch in "-/()'’"):
            puncty += 1

    mono_safe = mono if mono else 1
    return {
        "entries": n,
        "avg_label_len": round(sum(label_lengths) / n, 3) if n else 0.0,
        "ratio_pattern": round(with_pattern / n, 3) if n else 0.0,
        "ratio_mono": round(mono / n, 3) if n else 0.0,
        "ratio_upper_single": round(upper_single / n, 3) if n else 0.0,
        "ratio_puncty": round(puncty / n, 3) if n else 0.0,
        "ratio_short_single": round(short_single / mono_safe, 3),
        "ratio_alpha_single": round(alpha_single / mono_safe, 3),
        "ratio_title_single": round(title_single / mono_safe, 3),
        "ratio_risky_single": round(risky_single / mono_safe, 3),
        "pattern_pos_top": pattern_pos.most_common(10),
    }

def suggest_profile(stats: Dict[str, Any]) -> str:
    """Suggest one of the 3 generic profiles from dictionary statistics."""
    if (
        stats["ratio_pattern"] >= 0.45
        and stats["ratio_mono"] >= 0.4
        and (stats["ratio_upper_single"] >= 0.05 or stats["ratio_title_single"] >= 0.25)
    ):
        return "entity_strict"
    if stats["ratio_puncty"] >= 0.15 or stats["avg_label_len"] >= 2.2:
        return "term_recall"
    return "term_balanced"


def suggest_quality(stats: Dict[str, Any], profile_name: str) -> Dict[str, Any]:
    """Suggest a quality configuration from dictionary statistics."""
    quality = dict(QUALITY_DEFAULTS)

    if profile_name == "entity_strict":
        quality["single_token_penalty"] = 0.20
        quality["single_token_min_score"] = 0.80
    elif profile_name == "term_recall":
        quality["require_pos_match"] = False
        quality["single_token_penalty"] = 0.12
        quality["single_token_min_score"] = 0.70
    # term_balanced: QUALITY_DEFAULTS values already match this profile

    if stats["ratio_mono"] >= 0.45:
        quality["single_token_penalty"] = max(float(quality["single_token_penalty"]), 0.18)

    if stats["ratio_short_single"] >= 0.35 or stats["ratio_risky_single"] >= 0.05:
        quality["require_pos_match"] = True
        quality["single_token_penalty"] = max(float(quality["single_token_penalty"]), 0.20)

    if stats["ratio_pattern"] >= 0.35:
        quality["require_pos_match"] = True

    if stats["avg_label_len"] >= 2.2 and stats["ratio_mono"] <= 0.25:
        quality["single_token_penalty"] = min(float(quality["single_token_penalty"]), 0.14)

    return quality

def build_surface_forms(entry: Dict[str, Any], profile: ResourceProfile) -> List[str]:
    """Collect all candidate surface forms for one dictionary entry."""
    forms = []
    for key in ("label", "pref"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            forms.append(val)
    for key in ("altLabel", "altLabels", "variants"):
        vals = entry.get(key, [])
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    forms.append(v)
    seen, out = set(), []
    for f in forms:
        nf = normalize_text(
            f,
            normalize_separators=profile.params["normalize_separators"],
            normalize_apostrophes=profile.params["normalize_apostrophes"],
            keep_apostrophe=False,
        )
        if nf and nf not in seen:
            seen.add(nf)
            out.append(f)
    return out

def expand_structural_forms(form: str, profile: ResourceProfile) -> List[str]:
    """Generate structure-based variants without using vocabulary-specific rules."""
    variants = set()
    base = normalize_text(form, profile.params["normalize_separators"], profile.params["normalize_apostrophes"], True)
    if base:
        variants.add(base)
    if profile.params["normalize_parentheses"]:
        no_par = MULTISPACE_RE.sub(" ", re.sub(r"\([^)]*\)", " ", base)).strip()
        if no_par:
            variants.add(no_par)
    if profile.params["normalize_apostrophes"]:
        no_apo = base.replace("'", "")
        if no_apo:
            variants.add(no_apo)
    seen, out = set(), []
    for v in variants:
        nv = normalize_text(v, profile.params["normalize_separators"], profile.params["normalize_apostrophes"], False)
        if nv and nv not in seen:
            seen.add(nv)
            out.append(v)
    return out

def form_to_surface_seqs(form: str, profile: ResourceProfile) -> List[Tuple[str, ...]]:
    """Convert a form into normalized surface token sequences."""
    seen, out = set(), []
    for part in expand_structural_forms(form, profile):
        seq = tuple(normalize_token_list(part, profile))
        if seq and seq not in seen:
            seen.add(seq)
            out.append(seq)
    return sorted(out, key=lambda x: (-len(x), x))

def form_to_lemma_seqs(form: str, nlp, profile: ResourceProfile) -> List[Tuple[str, ...]]:
    """Convert a form into normalized lemma token sequences."""
    seen, out = set(), []
    for part in expand_structural_forms(form, profile):
        doc = nlp(part)
        seq = []
        for tok in doc:
            seq.extend(normalize_token_list(tok.lemma_, profile))
        seq = tuple(seq)
        if seq and seq not in seen:
            seen.add(seq)
            out.append(seq)
    return sorted(out, key=lambda x: (-len(x), x))

def build_flat_view(doc, attr: str, profile: ResourceProfile) -> FlatView:
    """Flatten a spaCy doc into normalized tokens + reverse token mapping."""
    toks, mapping = [], []
    for i, tok in enumerate(doc):
        pieces = normalize_token_list(tok.text if attr == "text" else tok.lemma_, profile)
        toks.extend(pieces)
        mapping.extend([i] * len(pieces))
    return FlatView(tokens=toks, flat_to_spacy=mapping)

def spacy_span_from_flat(doc, flat_view: FlatView, start_flat: int, end_flat_excl: int):
    """Map a flat-token span back to the original spaCy span."""
    start_spacy = flat_view.flat_to_spacy[start_flat]
    end_spacy = flat_view.flat_to_spacy[end_flat_excl - 1] + 1
    return doc[start_spacy:end_spacy]

def token_matches_spec(tok, spec: Dict[str, Any], profile: ResourceProfile) -> bool:
    """Check whether a token satisfies a dictionary pattern specification."""
    wanted_lemma = spec.get("lemma")
    wanted_pos = spec.get("pos")
    if wanted_lemma:
        tok_lemma = normalize_text(tok.lemma_, profile.params["normalize_separators"], profile.params["normalize_apostrophes"], False)
        spec_lemma = spec.get("_norm_lemma") or normalize_text(
            wanted_lemma, profile.params["normalize_separators"], profile.params["normalize_apostrophes"], False,
        )
        if tok_lemma != spec_lemma:
            return False
    if wanted_pos:
        if tok.pos_ == wanted_pos:
            return True
        if profile.params["propn_can_match_noun"] and wanted_pos == "PROPN" and tok.pos_ == "NOUN":
            return True
        return False
    return True

def match_pattern_entry(doc, entry: Dict[str, Any], profile: ResourceProfile) -> List[Dict[str, Any]]:
    """Apply a dictionary `pattern` to a document."""
    out = []
    pattern = entry.get("pattern")
    if not pattern:
        return out
    plen = len(pattern)
    for i in range(len(doc) - plen + 1):
        ok = True
        for j, spec in enumerate(pattern):
            if not token_matches_spec(doc[i + j], spec, profile):
                ok = False
                break
        if ok:
            span = doc[i:i + plen]
            out.append({
                "start": span.start_char, "end": span.end_char, "found": span.text,
                "pref": entry.get("pref", entry.get("label", "")), "uri": entry.get("id", ""),
                "label": entry.get("label", ""), "rule": "pattern", "score": 1.0,
            })
    return out

def match_patterns_indexed(
    doc,
    pattern_first_idx: Dict[str, List[Dict[str, Any]]],
    pattern_wildcards: List[Dict[str, Any]],
    profile: ResourceProfile,
) -> List[Dict[str, Any]]:
    """Pattern matching using a first-token index.

    Complexity: O(T × avg_candidates) instead of O(T × E).
    For each token position, only entries whose first-spec normalized lemma
    matches are checked, plus the small wildcard bucket (no-lemma first specs).
    """
    matches = []
    norm_sep = profile.params["normalize_separators"]
    norm_apo = profile.params["normalize_apostrophes"]
    doc_len = len(doc)

    for i in range(doc_len):
        tok_lemma_norm = normalize_text(doc[i].lemma_, norm_sep, norm_apo, False)
        candidates = pattern_first_idx.get(tok_lemma_norm, [])
        if pattern_wildcards:
            candidates = candidates + pattern_wildcards

        for entry in candidates:
            pattern = entry["pattern"]
            plen = len(pattern)
            if i + plen > doc_len:
                continue
            ok = True
            for j, spec in enumerate(pattern):
                if not token_matches_spec(doc[i + j], spec, profile):
                    ok = False
                    break
            if ok:
                span = doc[i:i + plen]
                matches.append({
                    "start": span.start_char, "end": span.end_char, "found": span.text,
                    "pref": entry.get("pref", entry.get("label", "")),
                    "uri": entry.get("id", ""),
                    "label": entry.get("label", ""),
                    "rule": "pattern", "score": 1.0,
                })
    return matches


def pattern_to_lemma_seq(pattern: List[Dict[str, str]], profile: ResourceProfile) -> Tuple[str, ...]:
    """Project a dictionary pattern to one lemma sequence."""
    out = []
    for spec in pattern:
        lemma = spec.get("lemma")
        if not lemma:
            return tuple()
        out.extend(normalize_token_list(lemma, profile))
    return tuple(out)

def build_indexes(entries: List[Dict[str, Any]], nlp, profile: ResourceProfile):
    """Build tries and side structures used by the matcher."""
    pattern_entries = []
    surface_trie = SeqTrie()
    lemma_trie = SeqTrie()
    pattern_lemma_trie = SeqTrie()
    upper_single_entries = []
    seen_pattern_lemma = set()

    for idx, entry in enumerate(entries):
        label = entry.get("label", "")
        pref = entry.get("pref", label)
        uri = entry.get("id", "")

        if entry.get("pattern") and profile.params["use_pattern"]:
            # Pre-normalize spec lemmas once here to avoid redundant normalize_text
            # calls inside token_matches_spec (called millions of times per run).
            for spec in entry["pattern"]:
                if "lemma" in spec and "_norm_lemma" not in spec:
                    spec["_norm_lemma"] = normalize_text(
                        spec["lemma"],
                        profile.params["normalize_separators"],
                        profile.params["normalize_apostrophes"],
                        False,
                    )
            pattern_entries.append(entry)
            if profile.params["use_lemma"]:
                lemma_seq = pattern_to_lemma_seq(entry["pattern"], profile)
                if lemma_seq and lemma_seq not in seen_pattern_lemma:
                    seen_pattern_lemma.add(lemma_seq)
                    pattern_lemma_trie.add(lemma_seq, {
                        "seq": lemma_seq,
                        "label": label,
                        "pref": pref,
                        "uri": uri,
                    })

        seen_surface, seen_lemma = set(), set()
        for form in build_surface_forms(entry, profile):
            for seq in form_to_surface_seqs(form, profile):
                if len(seq) == 1 and form.isupper() and profile.params["single_token_uppercase_exact"]:
                    upper_single_entries.append({"form": form, "label": label, "pref": pref, "uri": uri})
                    continue
                if seq not in seen_surface:
                    seen_surface.add(seq)
                    surface_trie.add(seq, {"seq": seq, "entry_idx": idx, "label": label, "pref": pref, "uri": uri})
            if profile.params["use_lemma"]:
                for seq in form_to_lemma_seqs(form, nlp, profile):
                    if seq not in seen_lemma:
                        seen_lemma.add(seq)
                        lemma_trie.add(seq, {"seq": seq, "entry_idx": idx, "label": label, "pref": pref, "uri": uri})

    # Build first-token index for O(T × avg_candidates) pattern matching
    # instead of O(T × E).  Entries without a lemma on their first token go into
    # pattern_wildcards and are still checked at every position.
    pattern_first_idx: Dict[str, List[Dict[str, Any]]] = {}
    pattern_wildcards: List[Dict[str, Any]] = []
    for entry in pattern_entries:
        key = entry["pattern"][0].get("_norm_lemma")
        if key:
            pattern_first_idx.setdefault(key, []).append(entry)
        else:
            pattern_wildcards.append(entry)

    return pattern_entries, surface_trie, lemma_trie, upper_single_entries, pattern_lemma_trie, pattern_first_idx, pattern_wildcards

def match_trie(flat_view: FlatView, trie: SeqTrie, doc, rule_name: str, score_multi: float, score_single: float, allow_single: bool):
    """Match longest indexed sequences against a flattened document view."""
    out = []
    for i in range(len(flat_view.tokens)):
        longest = trie.iter_longest(flat_view.tokens, i)
        if longest is None:
            continue
        end_flat, payloads = longest
        for payload in payloads:
            L = len(payload["seq"])
            if L == 1 and not allow_single:
                continue
            span = spacy_span_from_flat(doc, flat_view, i, end_flat)
            out.append({
                "start": span.start_char, "end": span.end_char, "found": span.text,
                "pref": payload["pref"], "uri": payload["uri"], "label": payload["label"],
                "rule": rule_name, "score": score_multi if L > 1 else score_single,
            })
    return out

def match_surface_upper(doc, upper_single_entries):
    """Apply exact-case matching for uppercase single-token labels."""
    out = []
    if not upper_single_entries:
        return out
    by_form = defaultdict(list)
    for entry in upper_single_entries:
        by_form[entry["form"]].append(entry)
    for tok in doc:
        for entry in by_form.get(tok.text, []):
            out.append({
                "start": tok.idx, "end": tok.idx + len(tok), "found": tok.text,
                "pref": entry["pref"], "uri": entry["uri"], "label": entry["label"],
                "rule": "surface_upper_exact", "score": 0.9,
            })
    return out

def match_document(doc, profile: ResourceProfile, indexes):
    """Run the complete matching strategy on one document."""
    pattern_entries, surface_trie, lemma_trie, upper_single_entries, pattern_lemma_trie, pattern_first_idx, pattern_wildcards = indexes
    matches = []
    surface_view = None
    lemma_view = None

    if profile.params["use_pattern"]:
        matches.extend(match_patterns_indexed(doc, pattern_first_idx, pattern_wildcards, profile))

        if profile.params["use_lemma"] and pattern_lemma_trie is not None:
            if lemma_view is None:
                lemma_view = build_flat_view(doc, "lemma", profile)
            matches.extend(match_trie(lemma_view, pattern_lemma_trie, doc, "lemma_pattern_seq", 0.9, 0.9, True))

        if profile.params["pattern_priority"]:
            patt = [m for m in matches if m["rule"] == "pattern"]
            if patt:
                prioritized = list(patt)
                prioritized.extend(match_surface_upper(doc, upper_single_entries))
                pattern_spans = [(m["start"], m["end"]) for m in patt]

                def non_overlapping_with_pattern(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                    out = []
                    for cand in candidates:
                        overlaps_pattern = any(
                            not (cand["end"] <= ps or cand["start"] >= pe)
                            for ps, pe in pattern_spans
                        )
                        if not overlaps_pattern:
                            out.append(cand)
                    return out

                if profile.params["use_surface"] and profile.params["allow_surface_fallback"]:
                    if surface_view is None:
                        surface_view = build_flat_view(doc, "text", profile)
                    surface_matches = match_trie(
                        surface_view,
                        surface_trie,
                        doc,
                        "surface_structural",
                        0.85,
                        0.75,
                        profile.params["allow_single_token_fallback"],
                    )
                    prioritized.extend(non_overlapping_with_pattern(surface_matches))

                if profile.params["use_lemma"]:
                    if lemma_view is None:
                        lemma_view = build_flat_view(doc, "lemma", profile)
                    lemma_matches = match_trie(
                        lemma_view,
                        lemma_trie,
                        doc,
                        "lemma_structural",
                        0.82,
                        0.72,
                        profile.params["allow_single_token_fallback"],
                    )
                    prioritized.extend(non_overlapping_with_pattern(lemma_matches))
                return prioritized

    if profile.params["single_token_uppercase_exact"]:
        matches.extend(match_surface_upper(doc, upper_single_entries))
    if profile.params["use_surface"] and profile.params["allow_surface_fallback"]:
        surface_view = build_flat_view(doc, "text", profile)
        matches.extend(match_trie(surface_view, surface_trie, doc, "surface_structural", 0.85, 0.75, profile.params["allow_single_token_fallback"]))
    if profile.params["use_lemma"]:
        lemma_view = build_flat_view(doc, "lemma", profile)
        matches.extend(match_trie(lemma_view, lemma_trie, doc, "lemma_structural", 0.82, 0.72, profile.params["allow_single_token_fallback"]))
    return matches


def _strip_accents(s: str) -> str:
    """Return a lowercase, accent-stripped form for language-neutral comparison."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _adaptive_single_token_penalty(found: str, base: float) -> float:
    """Return a morphology-aware penalty instead of the flat base value.

    Applied in priority order:
    1. All-uppercase ≥ 2 cased chars  → acronym/symbol (ERP, SAM, mRNA) → min(base, 0.05)
    2. CamelCase with internal upper   → specific entity (SenseCam)       → min(base, 0.05)
    3. All-lowercase ≤ 3 chars         → short ambiguous word              → max(base, 0.20)
    4. Default                         → base (unchanged behaviour)
    """
    s = found.strip()
    if not s:
        return base
    # Acronyms / symbols: all cased chars are uppercase, at least 2 chars total
    if s.isupper() and len(s) >= 2:
        return min(base, 0.05)
    # CamelCase proper names: uppercase after position 0
    if s[0].isupper() and any(c.islower() for c in s) and any(c.isupper() for c in s[1:]):
        return min(base, 0.05)
    # Very short all-lowercase: higher ambiguity risk
    if s.islower() and len(s) <= 3:
        return max(base, 0.20)
    return base


def score_match_quality(match: Dict[str, Any], doc, quality: Dict[str, Any],
                        _sg_set=None, _rp_set=None) -> Optional[Dict[str, Any]]:
    """Apply score adjustments and hard filters to one match."""
    if not quality.get("enabled", True):
        return match

    span = doc.char_span(match["start"], match["end"], alignment_mode="expand")
    if span is None or len(span) == 0:
        return None

    tokens = list(span)
    token_count = len(tokens)
    first = tokens[0]
    found = match["found"]
    lowered = found.lower()
    rule = match.get("rule", "")

    stop_pos = _STOP_POS
    content_pos = _CONTENT_POS
    weak_words = quality.get("_weak_words_set", _WEAK_WORDS)

    if token_count == 1 and rule != "pattern":
        if quality.get("strict_stopwords", True):
            if lowered in weak_words and first.pos_ in (stop_pos | {"ADV"}):
                return None
            if first.is_stop and first.pos_ in stop_pos and not found.isupper():
                return None

        if quality.get("case_sensitive_entities", True):
            if found.islower() and first.pos_ in (stop_pos | {"ADV"}):
                return None

        if quality.get("require_pos_match", True) and first.pos_ not in content_pos:
            return None

    if token_count == 1 and quality.get("context_guard", True):
        left = doc[first.i - 1] if first.i > 0 else None
        right = doc[first.i + 1] if first.i + 1 < len(doc) else None
        left_pos = left.pos_ if left is not None else None
        right_pos = right.pos_ if right is not None else None
        local_functional = stop_pos | {"ADV", "PUNCT"}

        if rule != "pattern" and first.pos_ not in content_pos:
            if (left_pos in local_functional or left_pos is None) and (right_pos in local_functional or right_pos is None):
                return None

        if quality.get("discourse_pattern_guard", True):
            left_low = left.text.lower() if left is not None else None
            right_low = right.text.lower() if right is not None else None
            if lowered == "well":
                if (left_low == "as" and right_low == "as") or right_pos == "PUNCT":
                    return None
            if lowered in weak_words and first.pos_ in (stop_pos | {"ADV"}):
                return None

    # Syntactic context guard — approximates dependency-based filtering using a
    # linear window (no parser required, no POS side-effects from parser enabling).
    # Applies to ALL rules (including "pattern") for non-PROPN, non-uppercase tokens.
    #
    # Two hard-kill patterns detected from the linear window:
    #
    # 1. Copula-attribute pattern: "is/was/are the <generic_word> that/which/who…"
    #    Signature: AUX in the 2-token left window + relative pronoun on the right.
    #    e.g. "Working memory updating IS THE PROCESS THAT replaces…" → kills "process"
    #    NOT triggered for domain-specific words (only for _SYNTACTIC_GENERIC).
    #
    # 2. Document-initial title/label word: token at position 0, starts with uppercase,
    #    is a generic word (unlikely to be a genuine in-text term occurrence).
    #    e.g. "Quality For him, a gallery is never…" → kills "Quality"
    #
    # Both word lists are configurable via quality keys and default to EN+FR combined.
    _SYNTACTIC_GENERIC = _sg_set if _sg_set is not None else frozenset(
        quality.get("syntactic_generic_words", _SYNTACTIC_GENERIC_DEFAULT)
    )
    _relative_pronouns = _rp_set if _rp_set is not None else frozenset(
        quality.get("syntactic_relative_pronouns", _RELATIVE_PRONOUNS_DEFAULT)
    )

    if token_count == 1 and quality.get("syntactic_context_guard", False):
        if not found.isupper() and first.pos_ not in {"PROPN"}:
            left_window = [doc[i] for i in range(max(0, first.i - 2), first.i)]
            right1 = doc[first.i + 1] if first.i + 1 < len(doc) else None
            # Normalise found for accent-insensitive comparison (qualité → qualite)
            found_norm = _strip_accents(found.lower())

            # Pattern 1: copula predicate + relative clause
            # EN: "is the process that…"  / FR: "est le processus qui…"
            has_aux_left = any(t.pos_ == "AUX" for t in left_window)
            has_rel_right = (right1 is not None
                             and right1.pos_ in {"SCONJ", "PRON"}
                             and right1.text.lower() in _relative_pronouns)
            if has_aux_left and has_rel_right and found_norm in _SYNTACTIC_GENERIC:
                return None

            # Pattern 2: document-initial uppercase generic word (title/label)
            if first.i == 0 and found[0].isupper() and found_norm in _SYNTACTIC_GENERIC:
                return None

    scored = dict(match)

    if token_count == 1 and quality.get("penalize_single_token", True):
        base_penalty = float(quality.get("single_token_penalty", 0.15))
        if quality.get("adaptive_single_token_penalty", True):
            penalty = _adaptive_single_token_penalty(found, base_penalty)
        else:
            penalty = base_penalty
        scored["score"] = max(0.0, scored["score"] - penalty)
    elif token_count > 1:
        scored["score"] = min(1.0, scored["score"] + float(quality.get("multi_token_bonus", 0.03)))

    if quality.get("contextual_scoring", True) and token_count == 1:
        window = int(quality.get("context_window", 2))
        left_tokens = [doc[i] for i in range(max(0, first.i - window), first.i)]
        right_tokens = [doc[i] for i in range(first.i + 1, min(len(doc), first.i + 1 + window))]
        neigh = left_tokens + right_tokens

        lexical_neighbors = sum(1 for t in neigh if t.pos_ in {"NOUN", "PROPN", "ADJ", "VERB"})
        functional_neighbors = sum(1 for t in neigh if t.pos_ in (stop_pos | {"ADV", "PUNCT"}))

        if first.pos_ in content_pos:
            scored["score"] = min(1.0, scored["score"] + float(quality.get("exact_pos_bonus", 0.05)))

        if lexical_neighbors > functional_neighbors:
            scored["score"] = min(1.0, scored["score"] + float(quality.get("lexical_context_bonus", 0.05)))
        elif functional_neighbors > lexical_neighbors:
            scored["score"] = max(0.0, scored["score"] - float(quality.get("function_context_penalty", 0.20)))

    return scored


def apply_quality_filters(doc, matches: List[Dict[str, Any]], quality: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply quality-oriented filtering and rescoring to matches."""
    min_single = float(quality.get(
        "single_token_min_score",
        _PROFILE_MIN_SCORES.get(quality.get("profile_name"), 0.75),
    ))
    _sg_set = frozenset(quality.get("syntactic_generic_words", _SYNTACTIC_GENERIC_DEFAULT))
    _rp_set = frozenset(quality.get("syntactic_relative_pronouns", _RELATIVE_PRONOUNS_DEFAULT))
    out = []
    for match in matches:
        scored = score_match_quality(match, doc, quality, _sg_set, _rp_set)
        if scored is None:
            continue
        span = doc.char_span(scored["start"], scored["end"], alignment_mode="expand")
        if span is None:
            continue
        if len(span) == 1 and scored.get("rule") != "pattern" and scored["score"] < min_single:
            continue
        out.append(scored)
    return out


def dedupe(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the best-scoring non-overlapping matches."""
    rule_rank = {
        "pattern": 3,
        "surface_upper_exact": 2,
        "surface_structural": 1,
        "lemma_pattern_seq": 1,
        "lemma_structural": 0,
    }
    ordered = sorted(
        matches,
        key=lambda m: (
            -m["score"],
            -rule_rank.get(m.get("rule", ""), -1),
            -(m["end"] - m["start"]),
            m["start"],
        ),
    )
    final = []
    for m in ordered:
        overlaps = any(not (m["end"] <= f["start"] or m["start"] >= f["end"]) for f in final)
        if not overlaps:
            final.append(m)
    return sorted(final, key=lambda x: x["start"])

def annotate(text: str, matches: List[Dict[str, Any]]) -> str:
    """Render the annotated text as markdown."""
    out = text
    for m in sorted(matches, key=lambda x: x["start"], reverse=True):
        found = out[m["start"]:m["end"]]
        rep = f"**{found}**〔[{m['pref']}]({m['uri']})〕" if m["uri"] else f"**{found}**〔{m['pref']}〕"
        out = out[:m["start"]] + rep + out[m["end"]:]
    return out

def write_outputs(docs, out_md: str, report_md: str, lang: str, profile: ResourceProfile, stats: Dict[str, Any], timings: Dict[str, float]):
    """Write markdown annotation and detailed report files."""
    total = sum(len(matches) for _, _, matches in docs)
    chunks = []
    report = [
        f"# Rapport {lang} — profil {profile.name}",
        "",
        "## Temps",
        "",
        f"- load_and_profile_s: {timings['load_and_profile_s']:.3f}",
        f"- process_s: {timings['process_s']:.3f}",
        f"- total_s: {timings['total_s']:.3f}",
        "",
        "## Profil de dictionnaire",
        "",
        f"- entries: {stats['entries']}",
        f"- avg_label_len: {stats['avg_label_len']}",
        f"- ratio_pattern: {stats['ratio_pattern']}",
        f"- ratio_mono: {stats['ratio_mono']}",
        f"- ratio_upper_single: {stats['ratio_upper_single']}",
        f"- ratio_puncty: {stats['ratio_puncty']}",
        f"- pattern_pos_top: {stats['pattern_pos_top']}",
        "",
        "## Paramètres du profil",
        "",
    ]
    for k, v in profile.params.items():
        report.append(f"- {k}: {v}")
    report.extend(["", "## Résultat", "", f"- Documents traités: {len(docs)}", f"- Occurrences annotées: {total}", "", "## Détail", ""])
    for doc_id, text, matches in docs:
        chunks.append(f"# {doc_id} ({lang}, {profile.name})")
        chunks.append("")
        chunks.append(f"Occurrences annotées: {len(matches)}")
        chunks.append("")
        chunks.append("## Texte annoté")
        chunks.append("")
        chunks.append(annotate(text, matches))
        chunks.append("")
        chunks.append("## Termes trouvés")
        chunks.append("")
        for m in matches:
            if m["uri"]:
                chunks.append(f"- [{m['pref']}]({m['uri']}) — `{m['found']}` — {m['rule']} — {m['score']}")
            else:
                chunks.append(f"- {m['pref']} — `{m['found']}` — {m['rule']} — {m['score']}")
        chunks.append("")
        report.append(f"- {doc_id}: {len(matches)} occurrence(s)")
    Path(out_md).write_text("\n".join(chunks), encoding="utf-8")
    Path(report_md).write_text("\n".join(report), encoding="utf-8")

def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load an optional YAML configuration file."""
    if not config_path:
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML non installé. Fais: pip install pyyaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def resolve_effective_config(args, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge CLI and YAML with CLI taking precedence when explicitly provided."""
    effective = {
        "text": cfg.get("text"),
        "dictionary": cfg.get("dictionary"),
        "lang": cfg.get("lang"),
        "out": cfg.get("out", "annotation.md"),
        "report": cfg.get("report", "report.md"),
        "profile": cfg.get("profile"),
        "profile_overrides": cfg.get("profile_overrides", {}),
        "quality": cfg.get("quality", {}),
    }

    cli_values = {
        "text": args.text,
        "dictionary": args.dict,
        "lang": args.lang,
        "out": args.out,
        "report": args.report,
        "profile": args.profile,
    }

    for key, value in cli_values.items():
        if value is not None and value is not False:
            effective[key] = value

    return effective

def validate_effective_config(effective: Dict[str, Any], used_config: bool, require_text: bool = False) -> None:
    """Validate the merged config after YAML + CLI resolution."""
    missing = []
    if require_text and not effective.get("text"):
        missing.append("--text / text")
    if not effective.get("dictionary"):
        missing.append("--dict / dictionary")
    if not effective.get("lang"):
        missing.append("--lang / lang")

    if missing:
        prefix = "With --config, missing required value(s): " if used_config else "Missing required CLI value(s): "
        raise ValueError(prefix + ", ".join(missing))


def generate_yaml_proposal(text_path: str, dict_path: str, lang: str, stats: Dict[str, Any], requested_profile: Optional[str], out_path: Optional[str] = None) -> Dict[str, Any]:
    """Generate a valid YAML proposal instead of running annotation."""
    auto_suggested = suggest_profile(stats)
    chosen_profile = requested_profile or auto_suggested
    quality = suggest_quality(stats, chosen_profile)

    # All quality parameters explicitly listed so the YAML is self-contained.
    full_quality = {
        "enabled":                     quality.get("enabled", True),
        "strict_stopwords":            quality.get("strict_stopwords", True),
        "require_pos_match":           quality.get("require_pos_match", True),
        "penalize_single_token":       quality.get("penalize_single_token", True),
        "single_token_penalty":        quality.get("single_token_penalty", 0.15),
        "adaptive_single_token_penalty": quality.get("adaptive_single_token_penalty", True),
        "multi_token_bonus":           quality.get("multi_token_bonus", 0.03),
        "case_sensitive_entities":     quality.get("case_sensitive_entities", True),
        "context_guard":               quality.get("context_guard", True),
        "contextual_scoring":          quality.get("contextual_scoring", True),
        "context_window":              quality.get("context_window", 2),
        "discourse_pattern_guard":     quality.get("discourse_pattern_guard", True),
        "syntactic_context_guard":     quality.get("syntactic_context_guard", False),
        "syntactic_adp_head_penalty":  quality.get("syntactic_adp_head_penalty", 0.15),
        "function_context_penalty":    quality.get("function_context_penalty", 0.20),
        "lexical_context_bonus":       quality.get("lexical_context_bonus", 0.05),
        "exact_pos_bonus":             quality.get("exact_pos_bonus", 0.05),
        "single_token_min_score":      quality.get("single_token_min_score", 0.75),
    }

    proposal = {
        "text": text_path,
        "dictionary": dict_path,
        "lang": lang,
        "profile": chosen_profile,
        "out": "annotation.md",
        "report": "report.md",
        "profile_overrides": dict(DEFAULT_PROFILES[chosen_profile]),
        "quality": full_quality,
    }
    yaml_text = yaml.safe_dump(proposal, allow_unicode=True, sort_keys=False) if yaml else json.dumps(proposal, ensure_ascii=False, indent=2)
    if out_path:
        Path(out_path).write_text(yaml_text, encoding="utf-8")
    return {
        "proposal": proposal,
        "suggested_profile": auto_suggested,
        "suggested_quality": full_quality,
        "used_profile": chosen_profile,
        "yaml": yaml_text,
        "written_to": out_path,
    }

_WORKER_STATE = {}

def _worker_init(lang: str, profile_name: str, profile_overrides: Dict[str, Any], entries: List[Dict[str, Any]], quality: Dict[str, Any]) -> None:
    """Initialize one worker process with its own spaCy model and indexes."""
    profile = merge_profile(profile_name, profile_overrides)
    nlp = load_model(lang)
    indexes = build_indexes(entries, nlp, profile)
    _WORKER_STATE["profile"] = profile
    _WORKER_STATE["nlp"] = nlp
    _WORKER_STATE["indexes"] = indexes
    _WORKER_STATE["quality"] = quality

def _worker_process(rows: List[Dict[str, Any]]):
    """Process one chunk of rows in a worker process."""
    profile = _WORKER_STATE["profile"]
    nlp = _WORKER_STATE["nlp"]
    indexes = _WORKER_STATE["indexes"]
    quality = _WORKER_STATE["quality"]
    docs = []
    batch_size = int(profile.params.get("batch_size", 64))
    for row, doc in zip(rows, nlp.pipe((r["value"] for r in rows), batch_size=batch_size)):
        doc_id = row.get("id", "doc")
        raw_text = row["value"]
        matches = dedupe(apply_quality_filters(doc, match_document(doc, profile, indexes), quality))
        docs.append((doc_id, raw_text, matches))
    return docs

def chunked(items: List[Dict[str, Any]], size: int):
    """Yield fixed-size chunks from a list."""
    for i in range(0, len(items), size):
        yield items[i:i + size]

def parse_args():
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description="Loterre engine v9")
    p.add_argument("--text", help="Text JSONL path; if omitted, read from stdin")
    p.add_argument("--dict", dest="dict", help="Dictionary JSONL path")
    p.add_argument("--lang", choices=["en", "fr"])
    p.add_argument("--out", default=None)
    p.add_argument("--report", default=None)
    p.add_argument("--config")
    p.add_argument("--profile", choices=["entity_strict", "term_balanced", "term_recall"])
    p.add_argument("--auto-profile", action="store_true", help="Generate a valid YAML configuration proposal instead of annotating")
    p.add_argument("--yaml-out", help="Write the proposed YAML to this file when using --auto-profile")
    p.add_argument("--silent", action="store_true", help="No file outputs; print JSON to stdout")
    p.add_argument("--api", action="store_true", help="Compact JSON payload on stdout")
    p.add_argument("--stream", action="store_true", help="Process input in a single process")
    p.add_argument("--ezs", action="store_true", help="EZS streaming mode: one JSON per input line, value=[matches]")
    p.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    p.add_argument("--chunk-size", type=int, default=200, help="Chunk size for multiprocessing")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--validate-input", action="store_true")
    p.add_argument("--dump-effective-config", action="store_true", help="Print merged config to stderr")
    return p.parse_args()

def main():
    """Main entry point."""
    t0 = time.perf_counter()
    args = parse_args()
    # En mode JSON pur (--silent / --api), on supprime les traces INFO pour ne
    # pas polluer stderr quand la sortie est redirigée ou consommée par un autre programme.
    if args.silent or args.api or args.ezs:
        args.log_level = "WARNING"
    setup_logging(args.log_level)
    cfg = load_config(args.config)

    effective = resolve_effective_config(args, cfg)
    validate_effective_config(effective, used_config=bool(args.config), require_text=False)

    if args.dump_effective_config:
        logging.info("Effective config: %s", json.dumps(effective, ensure_ascii=False))

    text_path = effective.get("text")
    dict_path = effective.get("dictionary")
    lang = effective.get("lang")
    out_md = effective.get("out") or "annotation.md"
    report_md = effective.get("report") or "report.md"
    profile_overrides = effective.get("profile_overrides", {})
    quality = merge_quality(effective.get("quality", {}))
    if "_weak_words_set" not in quality:
        quality["_weak_words_set"] = _WEAK_WORDS_FR if lang == "fr" else _WEAK_WORDS_EN

    logging.info("Loading dictionary")
    entries = load_entries(dict_path)
    t1 = time.perf_counter()

    if args.auto_profile:
        stats = profile_dictionary(entries)
        stats_stdout = {k: v for k, v in stats.items() if k != "pattern_pos_top"}
        proposal_payload = generate_yaml_proposal(
            text_path=text_path,
            dict_path=dict_path,
            lang=lang,
            stats=stats,
            requested_profile=args.profile,
            out_path=args.yaml_out,
        )
        proposal_payload["stats"] = stats_stdout
        proposal_payload["timings"] = {
            "load_and_profile_s": t1 - t0,
            "total_s": t1 - t0,
        }
        print(json.dumps(proposal_payload, ensure_ascii=False, indent=2))
        return

    if not effective.get("profile"):
        raise ValueError("Missing profile for annotation run. Provide --profile or 'config' in config. Use --auto-profile only to generate a YAML proposal.")

    profile = merge_profile(effective["profile"], profile_overrides)
    quality["profile_name"] = profile.name
    logging.info("Using profile %s", profile.name)

    # ── Mode EZS : traitement en flux, une ligne JSON par document ───────────
    if args.ezs:
        nlp = load_model(lang)
        indexes = build_indexes(entries, nlp, profile)
        compteur = 0
        for json_line in sys.stdin:
            json_line = json_line.strip()
            if not json_line:
                continue
            compteur += 1
            try:
                data = json.loads(json_line)
            except json.JSONDecodeError:
                logging.error("Line %s: invalid JSON: %s", compteur, json_line)
                continue
            if not isinstance(data, dict):
                continue  # item parasite EZS (ex: index de concurrence, entier, etc.)
            text = data.get("value", "")
            spacy_doc = next(nlp.pipe([text]))
            matches = dedupe(apply_quality_filters(spacy_doc, match_document(spacy_doc, profile, indexes), quality))
            data["annotated"] = annotate(text, matches)
            data["value"] = [
                {
                    "start": m["start"],
                    "end": m["end"],
                    "found": m.get("found", ""),
                    "pref": m.get("pref", ""),
                    "uri": m.get("uri", ""),
                    "label": m.get("label", ""),
                    "rule": m.get("rule", ""),
                    "score": round(m.get("score", 1.0), 4),
                }
                for m in matches
            ]
            sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return

    rows = read_text_rows(text_path, validate=args.validate_input)
    logging.info("Loaded %s documents", len(rows))

    docs = []
    if args.workers and args.workers > 1 and len(rows) > args.chunk_size:
        logging.info("Multiprocessing with %s workers", args.workers)
        with mp.Pool(
            processes=args.workers,
            initializer=_worker_init,
            initargs=(lang, profile.name, profile_overrides, entries, quality),
        ) as pool:
            for chunk_docs in pool.imap(_worker_process, chunked(rows, args.chunk_size)):
                docs.extend(chunk_docs)
    else:
        logging.info("Single-process mode")
        nlp = load_model(lang)
        indexes = build_indexes(entries, nlp, profile)
        batch_size = int(profile.params.get("batch_size", 64))
        for row, doc in zip(rows, nlp.pipe((r["value"] for r in rows), batch_size=batch_size)):
            doc_id = row.get("id", "doc")
            raw_text = row["value"]
            matches = dedupe(apply_quality_filters(doc, match_document(doc, profile, indexes), quality))
            docs.append((doc_id, raw_text, matches))
    t2 = time.perf_counter()

    timings = {
        "load_and_profile_s": t1 - t0,
        "process_s": t2 - t1,
        "total_s": t2 - t0,
    }

    payload = {
        "profile": profile.name,
        "docs": len(docs),
        "timings": timings,
    }

    if args.silent or args.api:
        payload["results"] = [
            {
                "id": doc_id,
                "annotated_text": annotate(raw_text, matches),
                "matches": matches,
            }
            for doc_id, raw_text, matches in docs
        ]
    else:
        stats = profile_dictionary(entries)
        write_outputs(docs, out_md, report_md, lang, profile, stats, timings)
        payload["out"] = out_md
        payload["report"] = report_md

    if args.api:
        compact = {
            "profile": payload["profile"],
            "docs": payload["docs"],
            "results": payload["results"],
        }
        print(json.dumps(compact, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()