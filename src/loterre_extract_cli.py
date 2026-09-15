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
import re
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

# Ponctuation tolérée à l'intérieur d'un span (jamais en bordure, déjà retirée
# par clean_chunk_span) : spaCy tokenise souvent le tiret/slash d'un composé
# scientifique comme un token PUNCT/SYM séparé du reste ("renin-angiotensin-
# aldosterone" -> 5 tokens, "ISO/IEC 27001" -> tiret/slash isolés) au lieu de
# le garder collé au mot comme un tokenizer type TreeTagger (voir TermSuite,
# resources/en(fr)/*-allowed-chars.txt : le tiret fait partie de l'alphabet
# d'un mot, jamais un motif de rejet). Sans cette liste blanche, is_valid_
# candidate rejetait la totalité du span dès qu'un seul de ces séparateurs
# apparaissait au milieu — mesuré sur le gold ACTER EN : rappel candidat sur
# le sous-ensemble à tiret/slash 0.021 -> 0.412 avec cette liste blanche,
# contre 0.385 pour une variante "graduée" façon CharacterFootprintTermFilter
# de TermSuite (tolère un seul token "sale" avant rejet) — moins bonne ici
# car un composé à 2 tirets ("renin-angiotensin-aldosterone") reste rejeté
# (2 tokens PUNCT > 1), alors que chez TermSuite ce cas ne se pose jamais
# (le tiret n'y crée pas de token séparé). Voir planification/
# analyse_benchmarks_extraction.md pour le détail des chiffres.
_CONNECTOR_PUNCT = frozenset({"-", "‐", "‑", "‒", "–", "—", "/"})

# Motifs N-préposition-N, adaptés de TermSuite (CNRS/TTC, Apache 2.0,
# termsuite-resources/en/english-multi-word-rule-system.regex) : vérifié
# empiriquement (EN et FR) que spaCy `doc.noun_chunks` ne produit JAMAIS
# "N of/with N" comme span unique ("quality of service" -> chunks séparés
# "quality"/"service", "la qualité de service" -> "La qualité"/"service" en
# FR aussi — la préposition attache une 2e NP au lieu d'être incluse dans le
# chunk) — un candidat composé de cette forme (ex. "rate of change", "taux de
# change") n'est donc jamais généré par noun_chunks seul, quel que soit
# l'extracteur en aval. Sous-ensemble volontairement restreint aux motifs à
# préposition (le vrai trou de couverture, confirmé empiriquement) — la
# grammaire TermSuite complète (~40 règles) inclut aussi des chaînes ADJ/NOUN
# longues que TermSuite annote elle-même "# noisy" ; pas reprises ici.
# Opt-in (--prep-patterns) tant que non validé par benchmark sur le gold
# ACTER — même prudence que --detect-variants (Phase 4).
_PREP_LEMMAS_BY_LANG = {"en": ("of", "with"), "fr": ("de", "avec")}
# Liste d'adjectifs génériques calibrée par TermSuite pour l'anglais (exclut
# "the same product", "many countries"...) — pas d'équivalent validé pour le
# français, donc les motifs avec ADJ (npan/anpn) ne sont ajoutés qu'en EN ;
# le français ne reçoit que npn/npnn (pas besoin de liste d'exclusion ADJ).
_GENERIC_ADJ_EN = frozenset({"same", "many", "other", "much", "several", "new"})
_GENERIC_ADV_EN = frozenset({"very", "so", "much", "where", "otherwise", "most", "how", "mostly",
                              "best", "therefore", "more", "less", "yet", "only", "when", "well"})


def _build_prep_matcher(vocab, lang: str):
    prep_lemmas = _PREP_LEMMAS_BY_LANG.get(lang)
    if not prep_lemmas:
        return None
    from spacy.matcher import Matcher

    n = {"POS": {"IN": ["NOUN", "PROPN"]}}
    prep = {"POS": "ADP", "LEMMA": {"IN": list(prep_lemmas)}}
    det_opt = {"POS": "DET", "OP": "?"}
    matcher = Matcher(vocab)
    matcher.add("npn", [[n, prep, det_opt, n]])
    matcher.add("npnn", [[n, prep, det_opt, n, n]])
    if lang == "en":
        a = {"POS": "ADJ", "LEMMA": {"NOT_IN": list(_GENERIC_ADJ_EN)}}
        matcher.add("npan", [[n, prep, det_opt, a, n]])
        matcher.add("anpn", [[a, n, prep, det_opt, n]])
    return matcher


def _matcher_spans(doc, matcher):
    matches = matcher(doc)
    return [doc[start:end] for _, start, end in matches]


# ── Grammaire complète TermSuite (règles non "noisy"), --all-candidate-patterns ──
# Transcription directe des fichiers TermSuite (CNRS/TTC, Apache 2.0) :
#   EN : termsuite-resources/en/english-multi-word-rule-system.regex
#   FR : termsuite-resources/fr/french-multi-word-rule-system.regex
# Règles explicitement annotées "# noisy" par TermSuite (EN uniquement, le
# fichier FR n'en annote aucune) ou déjà désactivées dans leur propre fichier
# (commentées) exclues : aannn, annnn, nann, nan, nnnnn, anann, la règle
# "apn" (commentée dans les deux fichiers), "vpp n" (commentée en EN).
#
# Simplifications assumées faute de moteur Ruta pour vérifier la sémantique
# exacte de certains opérateurs :
#   - "~D"/"~D?" (Ruta — un token qui n'est PAS un déterminant, optionnel ou
#     non) traité uniformément comme un déterminant optionnel à sauter
#     (OP "?") — lecture NLP la plus proche du sens réel de la règle, déjà
#     validée empiriquement sur --prep-patterns (motifs "npn").
#   - "~Og"/"~Fg" (guillemets ouvrant/fermant, règle FR "npnqnq" seulement,
#     très marginale) traités comme des tokens de ponctuation requis
#     (littéral), pas la négation Ruta exacte.
#   - A2 (FR) simplifié à ADJ seul, sans branche "participe passé verbal"
#     séparée : vérifié empiriquement que fr_core_news_sm étiquette déjà la
#     plupart des participes passés adjectivaux directement en ADJ (ex.
#     "produit fini" -> "fini"/ADJ, pas VERB) — la branche Vpp de TermSuite
#     serait largement redondante avec ce tagger, et l'exprimer littéralement
#     (ADJ OU (VERB ET participe passé)) demanderait un OR inter-attributs
#     que le Matcher spaCy n'exprime pas nativement sur un seul token.
#
# Opt-in (--all-candidate-patterns), bien plus large que --prep-patterns (qui
# reste un sous-ensemble ciblé N-prep-N, inchangé, distinct) — voir
# planification/analyse_benchmarks_extraction.md, entrée 2026-09-10, pour le
# bench qui a motivé la prudence (jamais actif par défaut).

def _en_grammar_atoms() -> dict[str, dict]:
    generic_adj = list(_GENERIC_ADJ_EN)
    generic_adv = list(_GENERIC_ADV_EN)
    return {
        "N": {"POS": {"IN": ["NOUN", "PROPN"]}},
        "N1": {"POS": {"IN": ["NOUN", "PROPN"]}, "LEMMA": {"NOT_IN": ["number"]}},
        "A": {"POS": "ADJ", "LEMMA": {"NOT_IN": generic_adj}},
        "A2": {"TAG": {"IN": ["JJ", "JJR", "JJS", "VBN", "VBG"]}, "LEMMA": {"NOT_IN": generic_adj}},
        "R": {"POS": "ADV", "LEMMA": {"NOT_IN": generic_adv}},
        "P": {"POS": "ADP", "LEMMA": {"IN": ["of", "with"]}},
        "C": {"POS": "CCONJ"},
        "Vbe": {"POS": {"IN": ["AUX", "VERB"]}, "LEMMA": "be"},
        "D": {"POS": "DET"},
    }


# Noms de règles fidèles à ceux du fichier TermSuite EN (identifiants entre
# guillemets dans le .regex), pour pouvoir comparer ligne à ligne.
_EN_GRAMMAR_RULES: dict[str, list] = {
    "n": ["N"],
    "a": ["A2"],
    "r": ["R"],
    "an": ["A2", "N"],
    "nnn": ["N", "N", "N"],
    "nn": ["N", "N"],
    "npn": ["N1", "P", ("D", "?"), "N"],
    "aan": ["A", "A", "N"],
    "ann": ["A", "N", "N"],
    "npan": ["N1", "P", ("D", "?"), "A", "N"],
    "npnn": ["N1", "P", ("D", "?"), "N", "N"],
    "anpn": ["A", "N", "P", ("D", "?"), "N"],
    "npncn": ["N1", "P", ("D", "?"), "N", "C", "N"],
    "acan": ["A", "C", "A", "N"],
    "aaann": ["A", "A", "A", "N", "N"],
    "aaan": ["A", "A", "A", "N"],
    "aann": ["A", "A", "N", "N"],
    "anan": ["A", "N", "A", "N"],
    "annn": ["A", "N", "N", "N"],
    "naan": ["N", "A", "A", "N"],
    "nnan": ["N", "N", "A", "N"],
    "nnnn": ["N", "N", "N", "N"],
    "raan": ["R", "A", "A", "N"],
    "rannn": ["R", "A", "N", "N", "N"],
    "rann": ["R", "A", "N", "N"],
    "ran": ["R", "A", "N"],
    "npnnn": ["N1", "P", ("D", "?"), "N", "N", "N"],
    "acann": ["A", "C", "A", "N", "N"],
    "npncnn": ["N1", "P", ("D", "?"), "N", "C", "N", "N"],
    "anpnn": ["A", "N", "P", ("D", "?"), "N", "N"],
    "ncnn": ["N", "C", "N", "N"],
    "ncan": ["N", "C", "A", "N"],
    "nnpn": ["N", "N", "P", ("D", "?"), "N"],
    "ncnpn": ["N", "C", "N", "P", ("D", "?"), "N"],
    "npnpn": ["N", "P", ("D", "?"), "N", "P", ("D", "?"), "N"],
    "npncpn": ["N1", "P", ("D", "?"), "N", "C", "P", ("D", "?"), "N"],
    "nva": [("D", "?"), "N", "Vbe", "A"],
}


def _fr_grammar_atoms() -> dict[str, dict]:
    l1 = ["axe", "calage", "chair", "couleur", "développement", "état", "face",
          "genre", "origine", "pas", "pâte", "phase", "type", "vitesse", "voie"]
    return {
        "N": {"POS": {"IN": ["NOUN", "PROPN"]}},
        "Nn": {"POS": {"IN": ["NOUN", "PROPN"]}},
        "Nnn": {"POS": {"IN": ["NOUN", "PROPN", "NUM"]}},
        "N1": {"POS": {"IN": ["NOUN", "PROPN"]}, "LEMMA": {"IN": l1}},
        "A": {"POS": "ADJ"},
        "A2": {"POS": "ADJ"},  # voir note A2(FR) ci-dessus
        "A3": {"POS": {"IN": ["ADJ", "NUM"]}},
        "R": {"POS": "ADV"},
        "P": {"POS": "ADP"},
        "Pde": {"POS": "ADP", "LEMMA": "de"},
        "Pa": {"POS": "ADP", "LEMMA": "à"},
        "C": {"LOWER": {"IN": ["et", "ou"]}},
        "Vbe": {"POS": {"IN": ["AUX", "VERB"]}, "LEMMA": "être"},
        "Vinf": {"POS": "VERB", "MORPH": {"IS_SUPERSET": ["VerbForm=Inf"]}},
        "D": {"POS": "DET"},
        "comma": {"ORTH": ","},
        "Og": {"ORTH": {"IN": ['"', "«"]}},
        "Fg": {"ORTH": {"IN": ['"', "»"]}},
    }


# Noms de règles fidèles au fichier TermSuite FR, sauf deux renommages pour
# rester des identifiants Python-friendly ("naca+" -> "naca_virgule",
# "npn,pncpn" -> "npn_virgule_pncpn" — la virgule dans le nom d'origine
# n'a aucun sens sémantique, c'est juste l'identifiant de règle).
_FR_GRAMMAR_RULES: dict[str, list] = {
    "n": ["N"],
    "a": ["A"],
    "r": ["R"],
    "nn": ["N", "Nn"],
    "na": ["N", "A2"],
    "nra": ["N", ("R", "+"), "A2"],
    "naa": ["N", "A2", "A"],
    "naaa": ["N", "A2", "A2", "A"],
    "npn": ["N", "P", ("D", "?"), "N"],
    "nnpn": ["N", "N", "P", ("D", "?"), "N"],
    "npnn": ["N", "P", "N1", "Nnn"],
    "npnqnq": ["N", "P", "N1", "Og", "Nnn", "Fg"],
    "naca": ["N", "A2", "C", "A"],
    "naca_virgule": ["N", "A", "comma", "A", "C", "A"],
    "npna": ["N", "P", "N", "A"],
    "npnaa": ["N", "P", "N", "A", "A"],
    "npan": ["N", "P", "A3", "N"],
    "napn1": ["N", "A2", "P", "N"],
    "napan": ["N", "A", "P", "A3", "N"],
    "napacan": ["N", "A", "P", "A3", "C", "A3", "N"],
    "napna": ["N", "A", "P", "N", "A3"],
    "dncdna": [("D", "?"), "N", "C", ("D", "?"), "N", "A"],
    "dncdnpn": [("D", "?"), "N", "C", ("D", "?"), "N", "P", "N"],
    "npncpn": ["N", "P", "N", "C", "P", "N"],
    "npdncpdn": ["N", "P", ("D", "?"), "N", "C", "P", ("D", "?"), "N"],
    "npn_virgule_pncpn": ["N", "P", "N", "comma", "P", "N", "C", "P", "N"],
    "npnpn": ["N", "P", "N", "Pde", "Nn"],
    "npnpna": ["N", "P", "N", "P", "N", "A3"],
    "npnpan": ["N", "P", "N", "P", "A3", "N"],
    "npnpacan": ["N", "P", "N", "P", "A3", "C", "A3", "N"],
    "nnca": ["N", "N", "C", "A"],
    "nva": [("D", "?"), "N", "Vbe", "A"],
    "nvra": [("D", "?"), "N", "Vbe", "R", "A"],
    "npvinf": ["N", "Pa", "Vinf"],
}


def _compile_grammar_pattern(atoms: list, atom_dict: dict) -> list:
    pattern = []
    for atom in atoms:
        if isinstance(atom, tuple):
            name, op = atom
            token = dict(atom_dict[name])
            token["OP"] = op
            pattern.append(token)
        else:
            pattern.append(dict(atom_dict[atom]))
    return pattern


def _build_all_candidate_patterns_matcher(vocab, lang: str):
    if lang == "en":
        atom_dict, rules = _en_grammar_atoms(), _EN_GRAMMAR_RULES
    elif lang == "fr":
        atom_dict, rules = _fr_grammar_atoms(), _FR_GRAMMAR_RULES
    else:
        return None
    from spacy.matcher import Matcher

    matcher = Matcher(vocab)
    for name, atoms in rules.items():
        matcher.add(name, [_compile_grammar_pattern(atoms, atom_dict)])
    return matcher


# Élisions FR ("l'", "d'", "qu'", "jusqu'", ...) : fr_core_news_sm les
# mistague souvent en NOUN au lieu de DET (vu avec l'apostrophe typographique
# "’"), ce qui casse aussi l'analyse de dépendances en aval. On les détecte
# par motif textuel, indépendamment du POS, pour pouvoir quand même les
# retirer des bords d'un chunk.
_ELISION_RE = re.compile(
    r"^(l|d|n|m|t|s|c|j|qu|jusqu|lorsqu|puisqu|quoiqu|presqu)['’]$", re.IGNORECASE
)


def _is_edge_strippable(token) -> bool:
    if token.pos_ in _EDGE_STRIP_POS:
        return True
    # "fixed" = composant d'une locution figée (ex. "à travers", "à partir
    # de") — jamais du contenu à lui seul, même si son POS individuel (ex.
    # NOUN pour "travers") suggère le contraire.
    if token.dep_ == "fixed":
        return True
    if _ELISION_RE.match(token.text):
        return True
    return False


def clean_chunk_span(chunk):
    """Retire les tokens non lexicaux en tête/fin d'un noun chunk."""
    start, end = 0, len(chunk)
    while start < end and _is_edge_strippable(chunk[start]):
        start += 1
    while end > start and _is_edge_strippable(chunk[end - 1]):
        end -= 1
    return chunk[start:end]


def is_valid_candidate(span, min_tokens: int, max_tokens: int) -> bool:
    if len(span) == 0 or not (min_tokens <= len(span) <= max_tokens):
        return False
    if not any(t.pos_ in _CONTENT_POS for t in span):
        return False
    if all(t.is_stop for t in span):
        return False
    if any(t.is_space for t in span):
        return False
    if any(t.is_punct and t.text not in _CONNECTOR_PUNCT for t in span):
        return False
    return True


def _register_span(span, doc_id, occurrences, patterns, lemmas) -> None:
    term = span.text
    occurrences[term].append(Occurrence(span.start_char, span.end_char, doc_id))
    if term not in patterns:
        patterns[term] = [{"pos": t.pos_, "lemma": t.lemma_.lower()} for t in span]
        lemmas[term] = " ".join(t.lemma_.lower() for t in span)


def extract_candidates(
    rows: list[dict[str, Any]], lang: str, min_tokens: int, max_tokens: int, min_freq: int,
    prep_patterns: bool = False, all_candidate_patterns: bool = False,
) -> tuple[list[CandidateTerm], int, list[list[tuple[int, str, str]]]]:
    """Collecte les candidats noun-chunks sur un corpus, filtrés et comptés en
    fréquence — et capture en même passage spaCy les données nécessaires à
    PositionRank (per_doc_tokens) et à la décision auto ncvalue/graph
    (total_tokens), pour éviter de retraiter le corpus deux fois selon
    l'extracteur choisi ensuite (voir score_extracted_candidates()).

    prep_patterns : ajoute les motifs N-prep-N (voir _build_prep_matcher).
    all_candidate_patterns : grammaire complète TermSuite non-"noisy" (voir
    _build_all_candidate_patterns_matcher) — prioritaire sur prep_patterns
    (sous-ensemble strict de cette grammaire, inutile de construire les deux
    matchers). Les deux tournent sur le même doc déjà parsé, pas de second
    passage spaCy.

    Un span matcher chevauche souvent un noun_chunk sans lui être identique
    (ex. "quality" (noun_chunk) et "quality of service" (motif "npn") au même
    point de départ, bornes différentes) : c'est voulu, pas un doublon — c'est
    exactement ce que `loterre_cvalue.build_containment_map()` attend pour
    calculer l'absorption du terme court par le terme composé (C-value
    classique, Frantzi et al. 1998 : la fréquence brute du candidat court
    inclut ses occurrences imbriquées, la formule soustrait l'absorption,
    l'étape d'extraction ne doit pas le faire elle-même). Seul un span aux
    bornes EXACTEMENT identiques à un span déjà retenu (même texte, ex.
    "machine learning" produit à la fois par noun_chunks et par le motif
    "nn") est un vrai doublon de comptage — dédupliqué ci-dessous par
    (start_char, end_char)."""
    nlp = get_nlp(lang, parser=True)
    if all_candidate_patterns:
        matcher = _build_all_candidate_patterns_matcher(nlp.vocab, lang)
    elif prep_patterns:
        matcher = _build_prep_matcher(nlp.vocab, lang)
    else:
        matcher = None
    occurrences: dict[str, list[Occurrence]] = defaultdict(list)
    patterns: dict[str, list[dict[str, str]]] = {}
    lemmas: dict[str, str] = {}
    per_doc_tokens: list[list[tuple[int, str, str]]] = []
    total_tokens = 0

    for row, doc in zip(rows, nlp.pipe((r["value"] for r in rows), batch_size=64)):
        doc_id = row.get("id")
        total_tokens += len(doc)
        per_doc_tokens.append([(i, t.lemma_.lower(), t.pos_) for i, t in enumerate(doc)])

        cleaned_chunks = [c for c in (clean_chunk_span(ch) for ch in doc.noun_chunks) if len(c) > 0]
        combined = cleaned_chunks + _matcher_spans(doc, matcher) if matcher is not None else cleaned_chunks
        seen_bounds: set[tuple[int, int]] = set()
        spans = []
        for span in combined:
            bounds = (span.start_char, span.end_char)
            if bounds in seen_bounds:
                continue
            seen_bounds.add(bounds)
            spans.append(span)

        for span in spans:
            if not is_valid_candidate(span, min_tokens, max_tokens):
                continue
            _register_span(span, doc_id, occurrences, patterns, lemmas)

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


def _attach_structural_signal(
    candidates: list[CandidateTerm],
    per_doc_tokens: list[list[tuple[int, str, str]]],
    total_tokens: int,
    auto_threshold: int,
) -> None:
    """Option 3 (planification/planif_extraction_terminologique.md §8) : calcule
    un second signal pour les candidats scorés par `embed`, indépendant du
    vocabulaire cible — C-value ou PositionRank (même bascule "auto" que le
    choix normal d'extracteur), qui juge un candidat sur sa propre forme/
    fréquence dans le corpus plutôt que sur sa proximité à un terme connu.

    Un candidat loin de tout terme du vocabulaire (score embed bas, jamais
    proposé en enrichissement) mais fort sur ce second signal est un angle
    mort connu d'embed seul (voir analyse_benchmarks_extraction.md, entrée
    2026-09-07 : corriger le rappel candidat brut sur les composés à tiret/
    slash n'a presque pas bougé le F1 embed, ces candidats étant trop rares
    pour être bien classés par la similarité cosinus).

    Écrit dans des champs séparés (structural_score/structural_rule/
    structural_rank) — ne touche jamais score/rule, qui restent le signal
    embed utilisé pour le tri principal et --embed-threshold."""
    if not candidates:
        return
    saved_embed = [(c.score, c.rule) for c in candidates]

    if total_tokens < auto_threshold:
        from loterre_positionrank import build_cooccurrence_graph, position_rank, score_candidates_positionrank
        graph, position_weight = build_cooccurrence_graph(per_doc_tokens)
        word_scores = position_rank(graph, position_weight)
        score_candidates_positionrank(candidates, word_scores)
    else:
        score_candidates(candidates)  # C-value, déjà importé en tête de module

    for c, (embed_score, embed_rule) in zip(candidates, saved_embed):
        c.structural_score = c.score
        c.structural_rule = c.rule
        c.score, c.rule = embed_score, embed_rule

    ranked = sorted(candidates, key=lambda c: -(c.structural_score or 0.0))
    for rank, c in enumerate(ranked, start=1):
        c.structural_rank = rank


def score_extracted_candidates(
    candidates: list[CandidateTerm],
    per_doc_tokens: list[list[tuple[int, str, str]]],
    total_tokens: int,
    extractor: str,
    auto_threshold: int,
    lang: str | None = None,
    dict_path: str | None = None,
) -> tuple[list[CandidateTerm], str]:
    """Choisit l'algorithme de scoring et l'applique.

    extractor="auto" bascule sur le volume du corpus (voir
    planification/analyse_benchmarks_extraction.md, §Dépendance au volume) :
    C-value a besoin d'au moins ~50 000 tokens pour que ses statistiques de
    fréquence soient fiables ; en dessous, PositionRank (qui ne dépend pas des
    fréquences de termes emboîtés) est plus adapté. "auto" ne bascule jamais
    vers "embed" (Phase 5) — il faut le demander explicitement, car il
    nécessite un dictionnaire cible (dict_path).
    """
    if extractor == "auto":
        extractor = "graph" if total_tokens < auto_threshold else "ncvalue"

    if extractor == "graph":
        from loterre_positionrank import build_cooccurrence_graph, position_rank, score_candidates_positionrank
        graph, position_weight = build_cooccurrence_graph(per_doc_tokens)
        word_scores = position_rank(graph, position_weight)
        return score_candidates_positionrank(candidates, word_scores), extractor

    if extractor == "embed":
        if not dict_path:
            raise SystemExit("ERROR: --dict est requis avec --extractor embed (vocabulaire cible de comparaison)")
        from loterre_embed import embed_vocabulary_terms, get_embed_model, load_vocabulary_terms, score_candidates_embed
        model = get_embed_model()
        vocab_terms = load_vocabulary_terms(dict_path)
        vocab_embeddings = embed_vocabulary_terms(model, vocab_terms)
        scored = score_candidates_embed(candidates, model, vocab_embeddings)
        _attach_structural_signal(scored, per_doc_tokens, total_tokens, auto_threshold)
        # Troisième signal (2026-09-11) : spécificité (Weirdness Ratio vs langue
        # générale) — toujours calculé pour embed (comme le signal structurel),
        # coût négligeable (pas de modèle, juste des ratios de fréquence). Le
        # booléen enrichment_suggestion_specificity (désactivé par défaut,
        # --specificity-top-pct 0) est calculé plus tard dans
        # run_extract_annotate_mode() (loterre_cli.py), sur ce score déjà présent.
        if lang:
            from loterre_specificity import score_candidates_specificity
            score_candidates_specificity(scored, per_doc_tokens, lang)
        return scored, extractor

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
    parser.add_argument("--min-freq", type=int, default=3,
                         help="Fréquence minimale dans le corpus pour retenir un candidat (défaut 3)")
    parser.add_argument("--cvalue-threshold", type=float, default=0.0,
                         help="Score C-value minimal (ou fréquence normalisée pour les mono-tokens) ; "
                              "0 = pas de filtre (défaut 0.0)")
    parser.add_argument("--extractor", choices=["ncvalue", "graph", "embed", "auto"], default="auto",
                         help="Algorithme de scoring (défaut auto) : ncvalue=C-value (corpus volumineux), "
                              "graph=PositionRank (corpus court), embed=similarité au vocabulaire cible "
                              "(Phase 5, nécessite --dict), auto=bascule entre ncvalue/graph selon "
                              "--extractor-auto-threshold (jamais embed automatiquement)")
    parser.add_argument("--extractor-auto-threshold", type=int, default=50000,
                         help="Nombre de tokens du corpus en dessous duquel --extractor auto bascule "
                              "vers PositionRank (défaut 50000)")
    parser.add_argument("--dict", default=None,
                         help="[--extractor embed] Chemin du dictionnaire JSONL cible, comparé par "
                              "plus proche voisin (requis si --extractor embed)")
    parser.add_argument("--embed-threshold", type=float, default=0.0,
                         help="[--extractor embed] Similarité cosinus minimale ; 0 = pas de filtre (défaut 0.0)")
    parser.add_argument("--max-terms", type=int, default=None,
                         help="Garde les N meilleurs candidats, triés par score décroissant (défaut illimité)")
    parser.add_argument("--specificity-filter-pctl", type=float, default=0.0,
                         help="Retire les N%% de candidats les moins spécifiques du corpus (Weirdness "
                              "Ratio vs langue générale, voir loterre_specificity.py), avant scoring — "
                              "0 = désactivé (défaut). Calibré sur ACTER le 2026-09-11 avec --extractor "
                              "ncvalue : 40 est le point optimal mesuré (F1 top-N=1.5x gold : 0.455->0.518), "
                              "au-delà (50+) le F1 régresse. À combiner UNIQUEMENT avec --extractor "
                              "ncvalue — dégrade le F1 à toute profondeur avec graph/auto sur corpus "
                              "court (planification/analyse_benchmarks_extraction.md).")
    parser.add_argument("--detect-variants", action="store_true",
                         help="Phase 4 : regroupe les variantes (graphiques/morphologiques/syntaxiques, "
                              "voir loterre_variants.py) et renseigne canonical_form/variant_type sur "
                              "chaque candidat groupé. Option explicite (défaut désactivé) — ne change "
                              "rien à la sortie existante tant qu'elle n'est pas demandée.")
    parser.add_argument("--prep-patterns", action="store_true",
                         help="Ajoute les motifs N-prep-N (\"rate of change\", \"abuse of power\" — "
                              "adaptés de TermSuite) que noun_chunks ne produit jamais comme span unique. "
                              "Option explicite (défaut désactivé) tant que non validée par benchmark sur "
                              "le gold ACTER — ne change rien à la sortie existante tant qu'elle n'est pas "
                              "demandée. Sous-ensemble de --all-candidate-patterns (ignoré si les deux sont "
                              "passés).")
    parser.add_argument("--all-candidate-patterns", action="store_true",
                         help="Grammaire complète TermSuite (règles non \"noisy\", voir "
                              "_build_all_candidate_patterns_matcher) en complément des noun_chunks — "
                              "bien plus large que --prep-patterns. Mesuré sur ACTER (2026-09-10, "
                              "planification/analyse_benchmarks_extraction.md) : gain net et large avec "
                              "--extractor ncvalue sur petit lot (+0.08 à +0.13 F1 selon coupure), "
                              "régression nette et systématique avec --extractor graph/auto sur corpus "
                              "court (jusqu'à -0.12 F1). ATTENTION performance : +154% de candidats mesuré "
                              "sur ACTER, et build_containment_map() (C-value) est O(n²) — sur un gros "
                              "corpus (>50k tokens, régime où ncvalue est auto-sélectionné), extract passe "
                              "de ~12s à ~66s (×5.4), soit ~6× plus lent qu'annotate sur le même corpus. "
                              "Sûr uniquement sur document unique/petit lot. Pas de garde-fou code. Option "
                              "explicite (défaut désactivé).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--text", help="Chemin JSONL ; lit stdin si omis")
    p.add_argument("--lang", choices=["en", "fr"], required=True)
    add_extraction_args(p)
    p.add_argument("--out", default=None)
    p.add_argument("--out-csv", default=None,
                    help="Export CSV additionnel des candidats (term, lemma, postag, "
                         "frequency, score, rule, uri, in_vocabulary, ...)")
    p.add_argument("--silent", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    rows = read_rows(args.text)
    candidates, total_tokens, per_doc_tokens = extract_candidates(
        rows, args.lang, args.min_tokens, args.max_tokens, args.min_freq,
        prep_patterns=args.prep_patterns, all_candidate_patterns=args.all_candidate_patterns,
    )
    if args.specificity_filter_pctl > 0:
        from loterre_specificity import filter_by_specificity
        candidates = filter_by_specificity(
            candidates, per_doc_tokens, args.lang, args.specificity_filter_pctl
        )
    candidates, extractor_used = score_extracted_candidates(
        candidates, per_doc_tokens, total_tokens, args.extractor, args.extractor_auto_threshold,
        lang=args.lang, dict_path=args.dict,
    )
    if args.detect_variants:
        from loterre_variants import group_variants
        group_variants(candidates, args.lang)
    if args.cvalue_threshold > 0 and extractor_used == "ncvalue":
        candidates = filter_by_threshold(candidates, args.cvalue_threshold)
    if args.embed_threshold > 0 and extractor_used == "embed":
        candidates = [c for c in candidates if c.score >= args.embed_threshold]
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

    if args.out_csv:
        from loterre_csv_export import candidates_to_csv
        Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_csv).write_text(
            candidates_to_csv(payload["candidates"]), encoding="utf-8", newline=""
        )


if __name__ == "__main__":
    main()
