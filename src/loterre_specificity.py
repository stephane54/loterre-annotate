#!/usr/bin/env python3
"""Score de spécificité (Weirdness Ratio, TermSuite) — signal additionnel de
filtrage, planification/planif_extraction_terminologique.md §9.

Contraste de fréquence entre le corpus analysé et une référence de "langue
générale" (resources/termsuite_general_language/{lang}/general-language.txt,
vendorisé depuis termsuite-resources CNRS/TTC, Apache 2.0) : un mot beaucoup
plus fréquent dans le corpus analysé que dans la langue générale est
spécifique au domaine ; un mot aussi fréquent dans les deux est du
vocabulaire générique. CPU pur, aucun modèle.

Contrairement au signal structurel (`_attach_structural_signal`, réservé à
`--extractor embed`) ou au score embed lui-même, ne nécessite AUCUN
vocabulaire cible — calculable pour n'importe quel extracteur, y compris en
mode `extract` "à froid" sans dictionnaire.

Câblé en CLI via `--specificity-filter-pctl` (`loterre_extract_cli.py`,
dupliqué dans `loterre_cli.py`) — `filter_by_specificity()` retire les N%
de candidats les moins spécifiques avant scoring. Calibré sur ACTER le
2026-09-11 pour `--extractor ncvalue` uniquement (40% optimal) — code non
restreint à cet extracteur (aucun garde-fou), restriction documentée
seulement (voir planification/analyse_benchmarks_extraction.md).
specificity_score/specificity_rank exposés dans le schéma de sortie
(CandidateTerm.to_dict()) pour les candidats survivants après filtrage.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from loterre_extract_cli import _GENERIC_ADJ_EN, _GENERIC_ADV_EN
from loterre_extraction_base import CandidateTerm

_RESOURCE_DIR = Path(__file__).resolve().parent.parent / "resources" / "termsuite_general_language"

# spaCy POS (coarse) -> lettre TermSuite — même taxonomie que les motifs
# _EN_GRAMMAR_RULES/_FR_GRAMMAR_RULES de loterre_extract_cli.py (N/A/V/R).
_POS_TO_LETTER = {
    "NOUN": "N", "PROPN": "N",
    "ADJ": "A",
    "VERB": "V", "AUX": "V",
    "ADV": "R",
}

# Mots-outils adjectivaux/adverbiaux (déterminant-like : "other", "same"...)
# tagués ADJ/ADV par spaCy mais absents de general-language.txt (table
# limitée aux mots de contenu) — sans cette exclusion, leur absence de la
# table est lue à tort comme "jamais vu en langue générale" = très
# spécifique, un faux positif mesuré empiriquement sur "other hand" (score
# de spécificité aberrant, 74x plus haut que "one hand" sur un même texte).
# Même liste que _GENERIC_ADJ_EN/_GENERIC_ADV_EN (grammaire de motifs) —
# réutilisée ici pour la même raison : ces mots ne portent jamais de sens
# lexical de contenu à eux seuls.
_SKIP_LEMMAS = _GENERIC_ADJ_EN | _GENERIC_ADV_EN

# Fréquence de référence plancher pour un mot absent de la table de langue
# générale (jamais vu = très spécifique, pas une division par zéro).
_SMOOTHING = 0.5


def load_general_language(lang: str) -> tuple[dict[tuple[str, str], int], int]:
    """Charge general-language.txt -> {(lemme_minuscule, lettre_pos): fréquence}.

    Le fichier source contient aussi des entrées multi-mots (ex.
    "#10 note::A N::15") — ignorées ici, hors scope du score mot-à-mot de ce
    prototype. Retourne aussi la taille totale (en mots) du corpus de
    référence (ligne __NB_CORPUS_WORDS__)."""
    path = _RESOURCE_DIR / lang / "general-language.txt"
    freq: dict[tuple[str, str], int] = {}
    total_words = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("::")
        if len(parts) != 3:
            continue
        lemma, pos, count_str = parts
        if lemma == "__NB_CORPUS_WORDS__":
            total_words = int(count_str)
            continue
        if " " in pos or " " in lemma:
            continue
        try:
            freq[(lemma.lower(), pos)] = int(count_str)
        except ValueError:
            continue
    return freq, total_words


def build_corpus_lemma_freq(
    per_doc_tokens: list[list[tuple[int, str, str]]],
) -> tuple[dict[tuple[str, str], int], int]:
    """Fréquence (lemme, lettre_pos) sur le corpus analysé, à partir des
    per_doc_tokens déjà collectés par extract_candidates() — pas de second
    passage spaCy."""
    counts: Counter[tuple[str, str]] = Counter()
    total = 0
    for doc_tokens in per_doc_tokens:
        for _, lemma, pos in doc_tokens:
            letter = _POS_TO_LETTER.get(pos)
            if letter is None:
                continue
            counts[(lemma, letter)] += 1
            total += 1
    return dict(counts), total


def _word_weirdness(
    lemma: str, letter: str,
    corpus_freq: dict[tuple[str, str], int], corpus_total: int,
    ref_freq: dict[tuple[str, str], int], ref_total: int,
) -> float:
    my_count = corpus_freq.get((lemma, letter), 0)
    if my_count == 0 or corpus_total == 0:
        return 0.0
    my_rate = my_count / corpus_total
    ref_count = ref_freq.get((lemma, letter), _SMOOTHING)
    ref_rate = ref_count / ref_total if ref_total else _SMOOTHING
    return my_rate / ref_rate


def score_candidates_specificity(
    candidates: list[CandidateTerm],
    per_doc_tokens: list[list[tuple[int, str, str]]],
    lang: str,
) -> list[CandidateTerm]:
    """Ajoute specificity_score/specificity_rank à chaque candidat (moyenne
    géométrique du Weirdness Ratio sur ses mots de contenu) — champs du
    schéma CandidateTerm (loterre_extraction_base.py), ne touchent jamais
    score/rule."""
    ref_freq, ref_total = load_general_language(lang)
    corpus_freq, corpus_total = build_corpus_lemma_freq(per_doc_tokens)

    for c in candidates:
        words = [
            (tok["lemma"], _POS_TO_LETTER[tok["pos"]])
            for tok in c.pattern
            if tok["pos"] in _POS_TO_LETTER and tok["lemma"] not in _SKIP_LEMMAS
        ]
        ratios = [
            r for r in (
                _word_weirdness(lemma, letter, corpus_freq, corpus_total, ref_freq, ref_total)
                for lemma, letter in words
            )
            if r > 0
        ]
        if not ratios:
            c.specificity_score = 0.0
            continue
        product = 1.0
        for r in ratios:
            product *= r
        c.specificity_score = product ** (1.0 / len(ratios))

    ranked = sorted(candidates, key=lambda c: -(c.specificity_score or 0.0))
    for rank, c in enumerate(ranked, start=1):
        c.specificity_rank = rank
    return candidates


def filter_by_specificity(
    candidates: list[CandidateTerm],
    per_doc_tokens: list[list[tuple[int, str, str]]],
    lang: str,
    percentile: float,
) -> list[CandidateTerm]:
    """Retire les *percentile* % de candidats les moins spécifiques du corpus
    (Weirdness Ratio), avant scoring par --extractor.

    Calibré sur ACTER le 2026-09-11 (planification/analyse_benchmarks_extraction.md) :
    balayage 0/10/.../70% avec --extractor ncvalue — **40% est le point optimal**
    mesuré (F1 top-N=n_gold_terms 0.397->0.447, top-N=1.5x 0.455->0.518),
    au-delà (50%+) le F1 régresse (trop de candidats valides retirés). Testé
    uniquement avec ncvalue — avec `graph`/PositionRank, tout filtrage
    (même 50%, testé avant ce sweep) dégrade le F1 à toute profondeur : ne
    jamais combiner avec --extractor graph/auto sur corpus court."""
    if percentile <= 0:
        return candidates
    score_candidates_specificity(candidates, per_doc_tokens, lang)
    sorted_scores = sorted(c.specificity_score or 0.0 for c in candidates)
    if not sorted_scores:
        return candidates
    idx = min(int(len(sorted_scores) * percentile / 100), len(sorted_scores) - 1)
    cutoff = sorted_scores[idx]
    return [c for c in candidates if (c.specificity_score or 0.0) >= cutoff]
