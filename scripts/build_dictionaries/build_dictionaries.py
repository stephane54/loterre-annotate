#!/usr/bin/env python3
"""Génère les dictionnaires d'annotation JSONL à partir des fichiers CSV vocab Loterre.

Remplace l'ancien pipeline externe `~/app/terms_tools/script/extract_dico_lot.sh`
(dépôt séparé `terms_tools`) par un script natif intégré à loterre-v9, en
reproduisant exactement son comportement : mêmes modèles spaCy transformers
(en_core_web_trf / fr_dep_news_trf, voir GENERATION_MODELS), même phrase-cadre
("the X is correct." / "le X est correct."), mêmes corrections de pattern.

Ces modèles sont volontairement différents de ceux du runtime de l'annotateur
(resources/spacy_models.yaml, en_core_web_sm/fr_core_news_sm) : un test chiffré
sur 7 vocabulaires a montré que les faire coïncider dégrade la qualité du
matching (cf. planification/journal_versions.md). Ne pas réutiliser load_model()
ici.

Nécessite un environnement avec les modèles transformers installés (ex. venv
`~/app/terms_tools/venv`) :
    ~/app/terms_tools/venv/bin/python3 scripts/build_dictionaries/build_dictionaries.py ...

Format CSV source (par vocabulaire, dans --voc-dir/<VOC>/<VOC>.csv) :
    colonnes ID, prefLabel<lang>, altLabel<lang>, hiddenLabel<lang>
    (suffixe <lang> = "Eng"/"Fre" ou "_en"/"_fr")
    champs multivalués séparés par "§§" (format loterre) ou "|" (format MX) —
    détecté automatiquement par scan du fichier.

Usage:
    python3 scripts/build_dictionaries/build_dictionaries.py --voc P66 --lang en
    python3 scripts/build_dictionaries/build_dictionaries.py --all --lang en fr
    python3 scripts/build_dictionaries/build_dictionaries.py --voc P66 --lang en --voc-dir ~/data/voc_loterre
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Iterable, Iterator

import spacy

ROOT = Path(__file__).parent.parent.parent

# Modèles de génération — identiques à l'ancien pipeline terms_tools
# (~/app/terms_tools/terms_tools/nlptools/models/__init__.py), volontairement
# différents du runtime de l'annotateur.
GENERATION_MODELS = {
    "en": "en_core_web_trf",
    "fr": "fr_dep_news_trf",
}


def load_generation_model(lang: str):
    """Charge le modèle spaCy de génération (transformer), comme exec_spacy_pipe.py."""
    name = GENERATION_MODELS.get(lang)
    if not name:
        raise RuntimeError(f"Pas de modèle de génération configuré pour la langue '{lang}'")
    return spacy.load(name, disable=["ner"])


DIVE = {
    "en": ("the", "is correct."),
    "fr": ("le", "est correct."),
}

DEFAULT_VOC_DIR = Path.home() / "data" / "voc_loterre"
DEFAULT_OUT_DIR = ROOT / "dictionary"

_SINGLE_SPECIAL_CHAR = frozenset(list("-(){},/\"\\"))


# ── Lecture CSV ──────────────────────────────────────────────────────────────

def sniff_csv_delimiter(path: Path) -> str:
    """Devine le délimiteur de colonnes CSV (par défaut ';')."""
    with path.open(newline="", encoding="utf-8", errors="ignore") as f:
        sample = f.read(2048)
    try:
        return csv.Sniffer().sniff(sample).delimiter
    except csv.Error:
        return ";"


# Les deux formats CSV vocab Loterre couplent un style de suffixe de colonne
# à un délimiteur d'occurrence fixe — détecter l'un suffit à déduire l'autre :
#   format loterre : colonnes "prefLabel_fr"/"prefLabel_en" (underscore) -> occurrence "§§"
#   format MX      : colonnes "prefLabelFre"/"prefLabelEng" (camelCase)  -> occurrence "|"
_FORMAT_BY_SUFFIX = {
    "_fr": ("loterre", "§§"), "_en": ("loterre", "§§"),
    "Fre": ("MX", "|"), "Eng": ("MX", "|"),
}


def detect_label_format(fieldnames: list[str], lang: str) -> tuple[str, str, str]:
    """Détecte depuis les en-têtes CSV : (suffixe de colonne, format, délimiteur d'occurrence)."""
    joined = "".join(fieldnames)
    camel = "Eng" if lang == "en" else "Fre"
    underscore = "_en" if lang == "en" else "_fr"
    suffix = camel if camel in joined else underscore
    format_name, delimiter_occ = _FORMAT_BY_SUFFIX[suffix]
    return suffix, format_name, delimiter_occ


def extract_terms_from_csv(path: Path, lang: str) -> Iterator[tuple[str, str, str]]:
    """Extrait les triplets (id, terme, pref) d'un CSV vocab Loterre/MX.

    Réplique la logique de ~/app/tools/csv/csv_termino/csv_convert.py :
    chaque valeur de prefLabel/altLabel/hiddenLabel devient un terme candidat,
    tous rattachés au même id et à la même valeur pref (le prefLabel).
    Le format (loterre/MX) est détecté automatiquement depuis les en-têtes CSV.
    """
    col_delimiter = sniff_csv_delimiter(path)

    with path.open(newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(
            f, delimiter=col_delimiter, quotechar='"',
            quoting=csv.QUOTE_ALL, skipinitialspace=True,
        )
        if not reader.fieldnames:
            return
        suffix, _format_name, delimiter_occ = detect_label_format(list(reader.fieldnames), lang)
        categories = [f"prefLabel{suffix}", f"altLabel{suffix}", f"hiddenLabel{suffix}"]

        for row in reader:
            try:
                pref = row[f"prefLabel{suffix}"]
            except KeyError:
                continue
            if not pref:
                continue

            for category, value in row.items():
                if category not in categories or not value:
                    continue
                if delimiter_occ in value:
                    for piece in value.split(delimiter_occ):
                        piece = piece.strip()
                        if piece:
                            yield row["ID"], piece, pref
                else:
                    value = value.strip()
                    if value:
                        yield row["ID"], value, pref


# ── Tagging POS+lemme ────────────────────────────────────────────────────────

def dive_term(term: str, lang: str) -> str:
    """Encadre le terme d'un contexte minimal pour guider le tagging spaCy."""
    left, right = DIVE[lang]
    return f"{left} {term} {right}"


def build_patterns(nlp, terms: list[str], lang: str, batch_size: int = 256) -> list[list[dict]]:
    """Tag POS+lemme pour une liste de termes, en un seul passage batché nlp.pipe().

    Chaque terme est encadré ("the X is correct." / "le X est correct."),
    puis le contexte (1 token à gauche, 3 à droite) est retiré après tagging.
    """
    wrapped = [dive_term(t, lang) for t in terms]
    patterns = []
    for doc in nlp.pipe(wrapped, batch_size=batch_size):
        core = doc[1:-3]
        patterns.append([
            {"pos": tok.pos_, "lemma": tok.lemma_.lower()}
            for tok in core
        ])
    return patterns


def postprocess_pattern(pattern: list[dict]) -> list[dict]:
    """Applique les corrections historiques (anciennement faites en sed) :
    - lemme réduit à un seul caractère spécial -> marqué optionnel ("OP": "?")
    - PRON en tête de pattern -> PROPN (heuristique : pronom isolé = libellé)
    """
    fixed = []
    for i, spec in enumerate(pattern):
        spec = dict(spec)
        if i == 0 and spec.get("pos") == "PRON":
            spec["pos"] = "PROPN"
        if len(spec.get("lemma", "")) == 1 and spec["lemma"] in _SINGLE_SPECIAL_CHAR:
            spec["OP"] = "?"
        fixed.append(spec)
    return fixed


# ── Orchestration ────────────────────────────────────────────────────────────

def build_dictionary(voc_dir: Path, voc: str, lang: str, out_dir: Path, nlp) -> Path:
    csv_path = voc_dir / voc / f"{voc}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV introuvable : {csv_path}")

    rows = list(extract_terms_from_csv(csv_path, lang))
    if not rows:
        raise ValueError(f"Aucun terme extrait de {csv_path} (lang={lang})")

    terms = [r[1] for r in rows]
    patterns = build_patterns(nlp, terms, lang)

    out_path = out_dir / f"{lang}_annot_{voc}.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for (term_id, term, pref), pattern in zip(rows, patterns):
            entry = {
                "label": term,
                "pattern": postprocess_pattern(pattern),
                "id": term_id,
                "pref": pref,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return out_path


def discover_vocabs(voc_dir: Path) -> list[str]:
    return sorted(p.name for p in voc_dir.iterdir() if p.is_dir() and (p / f"{p.name}.csv").exists())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voc", action="append", help="Code vocabulaire (ex: P66). Répétable.")
    parser.add_argument("--all", action="store_true", help="Traite tous les vocabulaires trouvés dans --voc-dir")
    parser.add_argument("--lang", nargs="+", choices=["en", "fr"], required=True)
    parser.add_argument("--voc-dir", type=Path, default=DEFAULT_VOC_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    if not args.all and not args.voc:
        parser.error("préciser --voc <CODE> (répétable) ou --all")

    vocs = discover_vocabs(args.voc_dir) if args.all else args.voc

    for lang in args.lang:
        print(f"=== lang={lang} : {len(vocs)} vocabulaire(s) ===")
        nlp = load_generation_model(lang)  # un seul chargement du modèle transformer par langue
        for voc in vocs:
            try:
                out_path = build_dictionary(args.voc_dir, voc, lang, args.out_dir, nlp)
                print(f"  ✓ {voc} -> {out_path}")
            except (FileNotFoundError, ValueError) as exc:
                print(f"  ✗ {voc} : {exc}")


if __name__ == "__main__":
    main()
