#!/usr/bin/env python3
"""Nettoyage spécifique du corpus RevueESR (Environnement, Risques & Santé),
texte extrait de PDF — 2026-10-02.

Le texte source (data/RevueESR-textFR.json, JSONL {"id","value"}) porte des
défauts d'extraction PDF qui polluent les listes de suggestion d'extract_annotate
(voir planification/analyse_benchmarks_extraction.md, entrées 2026-09-29/30 et
2026-10-02). Ce script produit une copie nettoyée, mêmes identifiants de
documents, sans toucher au fichier d'origine.

Réparation du texte — **uniquement si la forme corrigée existe ailleurs dans
le corpus** (lexique construit sur le corpus lui-même, pas de dictionnaire
externe, pas de devinette) :
1. mots coupés en fin de ligne : "pré- sents" -> "présents" (sinon "a-b" si
   cette forme composée existe, sinon inchangé) ;
2. ligatures fi/fl/ff perdues : "signi catif" -> "significatif",
   "in uence" -> "influence", "pro l" -> "profil", " èvre" -> "fièvre" ;
3. accents perdus : "donn ees" -> "données", "r esultats" -> "résultats",
   "m emes" -> "mêmes", "franc ais" -> "français", "evolutions" -> "évolutions".

Suppression du paratexte de la revue (motifs propres à RevueESR) :
4. en-têtes/pieds de page "Environ Risque Sante Vol. 16, n 1, janvier-février 2017" ;
5. "Article reçu le …, accepté le …" ;
6. bloc "Pour citer cet article : …" (jusqu'à l'en-tête de revue qui le suit) ;
7. courriels (&lt;…&gt;, x@y) et "Tirés à part : B. Combes" ;
8. "Remerciements et autres mentions", "Financement : aucun", "Liens d'intérêts : …" ;
9. libellés "Mots clés :" / "Key words :" (les mots-clés eux-mêmes sont gardés) ;
10. brèves : signature de l'analyste ("Laurence Nicolle-Mir", …) et référence
    de l'article analysé ("*Meeker JD, Stapleton HM. … 2010 ; 118 : 318-23.").

Limites connues : un mot dont deux caractères ont été perdus ("d es" pour
"défavorisés") n'est pas réparé ; la ponctuation isolée ("-", "–") est un
problème du filtre de candidats, pas du texte.

Usage:
    python3 scripts/corpus/clean_revueesr.py \
        --input data/RevueESR-textFR.json \
        --output data/RevueESR-textFR.clean.json \
        --samples /tmp/revueesr_clean_samples.txt
"""
from __future__ import annotations

import argparse
import html
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

WORD = r"[A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]"
WORD_RE = re.compile(WORD + "+")
MIN_FREQ = 3            # fréquence minimale de la forme corrigée dans le corpus
INITIAL_ACCENT_RATIO = 20  # "evolutions" -> "évolutions" seulement si 20x plus fréquent
FRAGMENT_PAIR_RATIO = 0.25  # voir Repairer.join_pair
LIGATURES = ["fi", "fl", "ff", "ffi", "ffl"]
ACCENTS = {"e": "éèêë", "a": "àâ", "o": "ô", "u": "ûù", "i": "îï"}
COUNTRY_LIKE = {"États-Unis", "Etats-Unis", "Royaume-Uni", "Nouvelle-Zélande", "Pays-Bas"}

# En-tête des numéros anciens : "Environnement, Risques & Santé – Vol. 9, n° 3,
# mars-avril 2010", lettrines souvent perdues ("nvironnement, isques &").
_OLD_HEADER = r"[EÉ]?nvironnement,\s*R?isques\s*&(?:amp;)?\s*(?:S?ant[ée])?\s*[–-]?"
_VOL = r"Vol\.\s*\d+\s*,\s*n\s*°?\s*\d+\s*,\s*[^\d]{3,40}?\d{4}"

PARATEXT = [
    ("pour_citer", re.compile(
        rf"Pour citer cet article\s*:.{{0,700}}?(?=Environ Risque Sant[eé]|{_OLD_HEADER}|Vol\.\s*\d)", re.S)),
    ("article_recu", re.compile(r"Article reçu le [^,]{3,40}, accepté le \d{1,2}\s*\w+\s*\d{4}")),
    ("entete_revue", re.compile(rf"Environ Risque Sant[eé](?:\s*{_VOL})?")),
    ("entete_revue_ancien", re.compile(rf"(?:{_OLD_HEADER}\s*)?[–-]?\s*{_VOL}")),
    ("courriel", re.compile(r"&lt;[^&]{0,150}?&gt;|&lt;\s*\S+@\S+|\S+@\S+\.\w+")),
    ("tires_a_part", re.compile(
        r"Tirés à part\s*:\s*(?:[A-ZÉ][\w]*\.(?:-[A-ZÉ]\.)?\s*)+[A-ZÉ][\w\-’']+(?:\s+[A-ZÉ][\w\-’']+)?")),
    ("tires_a_part_label", re.compile(r"Tirés à part\s*:")),
    ("rubrique", re.compile(r"\bArticle original\b")),
    ("remerciements", re.compile(r"Remerciements et autres mentions")),
    ("financement", re.compile(r"Financement\s*:\s*aucun\s*;?")),
    ("liens_interets", re.compile(
        r"(?:Liens? d.int[ée]r[êe]ts?\s*:\s*)?(?:les\s+)?auteurs?\s+d[ée]clarent?\s+ne pas avoir de\s+liens?\s+"
        r"d(?:.|\s)?(?:int[ée]r[êe]ts?\.?)?", re.I)),
    ("liens_interets_label", re.compile(r"Liens? d.int[ée]r[êe]ts?\s*:", re.I)),
    ("mots_cles_label", re.compile(r"Mots[ -]cl[ée]s\s*:|Key ?words\s*:", re.I)),
    ("ref_breve", re.compile(r"\*\s?[A-Z][^*]{0,500}?\d{4}\s*;\s*\d+\s*(?:\(\d+\))?\s*:\s*[\w\-–]+\.")),
]


def build_lexicon(texts: list[str]) -> tuple[Counter, Counter]:
    """Fréquence des mots, et des paires de mots séparés par une seule espace."""
    lex: Counter = Counter()
    pairs: Counter = Counter()
    for t in texts:
        tokens = list(WORD_RE.finditer(t))
        lex.update(m.group(0).lower() for m in tokens)
        pairs.update((m1.group(0).lower(), m2.group(0).lower())
                     for m1, m2 in zip(tokens, tokens[1:]) if t[m1.end():m2.start()] == " ")
    return lex, pairs


def reviewer_signatures(texts: list[str]) -> list[str]:
    """Noms qui précèdent une référence d'article analysé ("Nom Prénom *Auteur")
    au moins 3 fois — signatures des brèves."""
    c: Counter = Counter()
    rx = re.compile(r"([A-ZÉ][a-zéèëï]+(?:[- ][A-ZÉ][a-zéèëï]+)+)\s*\*\s?[A-Z]")
    for t in texts:
        c.update(m.group(1) for m in rx.finditer(t))
    return sorted((n for n, k in c.items() if k >= 3 and n not in COUNTRY_LIKE), key=len, reverse=True)


class Repairer:
    def __init__(self, lex: Counter, pairs: Counter):
        self.lex = lex
        self.pairs = pairs
        self.counts: Counter = Counter()
        self.samples: dict[str, list[str]] = defaultdict(list)

    def ok(self, w: str) -> bool:
        return self.lex[w.lower()] >= MIN_FREQ

    def _note(self, kind: str, before: str, after: str) -> None:
        self.counts[kind] += 1
        if len(self.samples[kind]) < 400:
            self.samples[kind].append(f"{before!r} -> {after!r}")

    def hyphen(self, m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        if self.ok(a + b):
            self._note("cesure", m.group(0), a + b)
            return a + b
        if self.ok(f"{a}-{b}"):
            self._note("cesure_compose", m.group(0), f"{a}-{b}")
            return f"{a}-{b}"
        return m.group(0)

    def join_pair(self, a: str, b: str) -> str | None:
        """Deux fragments séparés par une espace : ligature ou accent perdus.
        Retourne le mot réparé, ou None."""
        al, bl = a.lower(), b.lower()
        # Vrais mots ou fragments ? Un fragment ("donn", "ees", "uence") apparaît
        # surtout collé à son voisin : la paire représente une grande part de
        # ses occurrences. Deux vrais mots ("pour suivre") vivent aussi
        # séparément : la paire n'en représente qu'une petite part -> on ne
        # touche pas, même si leur concaténation est un mot ("poursuivre").
        # Seuil 0.25 calibré sur RevueESR : fragments 0.42 ("in uence", "uence"
        # suit aussi d'autres préfixes) à 0.86 ("m eme"), vrais mots 0.05
        # ("qu il") à 0.08 ("pour suivre").
        if self.pairs[(al, bl)] < FRAGMENT_PAIR_RATIO * min(self.lex[al], self.lex[bl]):
            return None
        whole = f"{a} {b}"
        for lig in LIGATURES:
            w = a + lig + b
            if self.ok(w):
                self._note("ligature", whole, w)
                return w
        variants = []
        if bl[0] in ACCENTS:
            variants += [a + acc + b[1:] for acc in ACCENTS[bl[0]]]
        if al[-1] == "c":
            variants.append(a[:-1] + "ç" + b)
        for w in variants:
            if self.ok(w):
                self._note("accent", whole, w)
                return w
        return None

    def initial(self, m: re.Match) -> str:
        """Mot entier sans son premier caractère : "èvre" (fi-), "evolutions" (é-)."""
        t = m.group(0)
        tl = t.lower()
        if self.lex[tl] >= 50:
            return t
        for lig in ("fi", "fl"):
            if self.ok(lig + t) and self.lex[(lig + tl)] >= INITIAL_ACCENT_RATIO * max(1, self.lex[tl]):
                self._note("ligature_initiale", t, lig + t)
                return lig + t
        if t[0] == "e":
            for acc in "éèê":
                w = acc + t[1:]
                if self.ok(w) and self.lex[w.lower()] >= INITIAL_ACCENT_RATIO * max(1, self.lex[tl]):
                    self._note("accent_initial", t, w)
                    return w
        return t


HYPHEN_RE = re.compile(rf"({WORD}+)- ({WORD}+)")
INITIAL_RE = re.compile(rf"\b[eè]{WORD}+")


def join_pairs(t: str, r: Repairer) -> str:
    """Parcourt les mots deux à deux (avec chevauchement : dans "the in uence",
    la paire "in uence" doit être testée même si "the in" ne l'a pas été) et
    recolle les fragments séparés par exactement une espace."""
    tokens = list(WORD_RE.finditer(t))
    out, last, i = [], 0, 0
    while i < len(tokens) - 1:
        m1, m2 = tokens[i], tokens[i + 1]
        if t[m1.end():m2.start()] == " ":
            fixed = r.join_pair(m1.group(0), m2.group(0))
            if fixed is not None:
                out.append(t[last:m1.start()])
                out.append(fixed)
                last = m2.end()
                i += 2
                continue
        i += 1
    out.append(t[last:])
    return "".join(out)


def repair_text(t: str, r: Repairer) -> str:
    t = HYPHEN_RE.sub(r.hyphen, t)
    # deux passes : un mot peut avoir perdu deux caractères séparés ("r esum e")
    for _ in range(2):
        t = join_pairs(t, r)
    return INITIAL_RE.sub(r.initial, t)


def strip_paratext(t: str, signatures_re: re.Pattern | None, counts: Counter) -> str:
    for name, rx in PARATEXT:
        t, n = rx.subn(" ", t)
        counts[name] += n
    if signatures_re is not None:
        t, n = signatures_re.subn(" ", t)
        counts["signature_breve"] += n
    t = html.unescape(t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--input", default="data/RevueESR-textFR.json")
    pa.add_argument("--output", default="data/RevueESR-textFR.clean.json")
    pa.add_argument("--samples", help="Fichier d'exemples de corrections, pour relecture")
    args = pa.parse_args()

    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = [r.get("value") or "" for r in rows]
    lex, pairs = build_lexicon(texts)
    sigs = reviewer_signatures(texts)
    sig_re = re.compile("|".join(re.escape(s) for s in sigs)) if sigs else None

    repairer = Repairer(lex, pairs)
    paratext_counts: Counter = Counter()
    chars_before = sum(len(t) for t in texts)
    out_rows = []
    for row, t in zip(rows, texts):
        t = repair_text(t, repairer)
        t = strip_paratext(t, sig_re, paratext_counts)
        out_rows.append({**row, "value": t})
    chars_after = sum(len(r["value"]) for r in out_rows)

    Path(args.output).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n", encoding="utf-8")

    print(f"{len(rows)} documents -> {args.output}")
    print(f"caractères : {chars_before} -> {chars_after} ({(chars_before - chars_after) / chars_before:.1%} retirés)")
    print("réparations :", dict(repairer.counts))
    print("paratexte retiré :", dict(paratext_counts))
    print("signatures de brèves :", sigs)
    if args.samples:
        random.seed(0)
        with open(args.samples, "w", encoding="utf-8") as f:
            for kind, items in repairer.samples.items():
                f.write(f"== {kind} ({repairer.counts[kind]}) — 40 exemples au hasard\n")
                for s in random.sample(items, min(40, len(items))):
                    f.write(f"  {s}\n")
        print(f"exemples -> {args.samples}")


if __name__ == "__main__":
    main()
