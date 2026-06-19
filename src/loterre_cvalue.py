"""Scoring C-value (Frantzi et al. 1998) — Phase 2, v2.0.

C-value pénalise un candidat selon sa fréquence en tant que sous-séquence de
termes plus longs (termes emboîtés) : un terme composé fréquent fait baisser
le score de ses propres fragments. Le score de contexte nominal de NC-value
(mots adjacents pondérés, Frantzi et al. 2000) n'est pas encore implémenté ici
— nécessite le suivi des positions de tokens (CandidateTerm n'a que des offsets
caractères) ; prochaine étape documentée dans planification/.

Fichier séparé de loterre_engine_v9_cli.py (règle Phase 0.5) : ne dépend pas du
moteur d'annotation, uniquement de loterre_extraction_base.CandidateTerm.
"""
from __future__ import annotations

import math
from typing import Sequence

from loterre_extraction_base import CandidateTerm


def lemma_tokens(candidate: CandidateTerm) -> tuple[str, ...]:
    return tuple(candidate.lemma.split())


def build_containment_map(candidates: Sequence[CandidateTerm]) -> dict[str, list[CandidateTerm]]:
    """Pour chaque candidat, liste les candidats plus longs qui le contiennent
    comme sous-séquence contiguë de lemmes (ex. "memory" dans "controlled memory
    assessment")."""
    tokenized = {c.term: lemma_tokens(c) for c in candidates}
    containment: dict[str, list[CandidateTerm]] = {c.term: [] for c in candidates}

    for a in candidates:
        a_tokens = tokenized[a.term]
        for b in candidates:
            if a.term == b.term:
                continue
            b_tokens = tokenized[b.term]
            if len(b_tokens) <= len(a_tokens):
                continue
            for i in range(len(b_tokens) - len(a_tokens) + 1):
                if b_tokens[i:i + len(a_tokens)] == a_tokens:
                    containment[a.term].append(b)
                    break
    return containment


def c_value(candidate: CandidateTerm, containment: dict[str, list[CandidateTerm]]) -> float:
    """C-value (Frantzi et al. 1998).

    Toujours 0 pour un terme à un seul token (log2(1) = 0 par construction de la
    formule) — voir single_token_score() pour le score de repli sur ce cas limite.
    """
    length = len(lemma_tokens(candidate))
    if length <= 1:
        return 0.0
    longer_terms = containment.get(candidate.term, [])
    if not longer_terms:
        return math.log2(length) * candidate.frequency
    nested_freq_sum = sum(t.frequency for t in longer_terms)
    p_a = len(longer_terms)
    return math.log2(length) * (candidate.frequency - nested_freq_sum / p_a)


def single_token_score(candidate: CandidateTerm, max_frequency: int) -> float:
    """Score de repli pour les termes à un seul token (cas limite documenté en
    Phase 0) : fréquence normalisée par la fréquence max du corpus, sur la même
    échelle [0, max C-value observé] que les candidats multi-tokens n'est pas
    garanti — uniquement comparable entre candidats mono-tokens entre eux."""
    if max_frequency <= 0:
        return 0.0
    return candidate.frequency / max_frequency


def score_candidates(candidates: Sequence[CandidateTerm]) -> list[CandidateTerm]:
    """Calcule le score C-value (ou le repli mono-token) pour chaque candidat,
    in place, et retourne la liste triée par score décroissant."""
    if not candidates:
        return []
    containment = build_containment_map(candidates)
    max_freq = max(c.frequency for c in candidates)

    for c in candidates:
        if len(lemma_tokens(c)) <= 1:
            c.score = single_token_score(c, max_freq)
            c.rule = "freq_single_token"
        else:
            c.score = c_value(c, containment)
            c.rule = "cvalue"

    return sorted(candidates, key=lambda c: -c.score)


def filter_by_threshold(candidates: Sequence[CandidateTerm], threshold: float) -> list[CandidateTerm]:
    return [c for c in candidates if c.score >= threshold]
