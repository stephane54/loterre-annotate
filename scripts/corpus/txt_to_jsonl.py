#!/usr/bin/env python3
"""Convertit un ou plusieurs fichiers .txt en JSONL pour les modes extract /
extract_annotate / annotate de loterre-v9 (une ligne JSON par document, champs
"id" et "value").

Accepte en entrée : un fichier .txt, un répertoire de .txt, ou une archive
tar (.tar.gz/.tgz/.tar) contenant des .txt — extraits directement en mémoire,
sans rien écrire sur disque.

Usage:
    python3 scripts/corpus/txt_to_jsonl.py mon_texte.txt --out mon_texte.jsonl
    python3 scripts/corpus/txt_to_jsonl.py mes_textes/ --out corpus.jsonl
    python3 scripts/corpus/txt_to_jsonl.py mes_textes.tar.gz --out corpus.jsonl
    python3 scripts/corpus/txt_to_jsonl.py mon_texte.txt   # affiche sur stdout
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path

_TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar")


def _is_tar(path: Path) -> bool:
    return path.name.endswith(_TAR_SUFFIXES)


def iter_documents(path: Path) -> list[tuple[str, str]]:
    """Retourne une liste de (id, texte) depuis un fichier .txt, un répertoire
    de .txt, ou une archive tar(.gz) contenant des .txt."""
    if _is_tar(path):
        docs = []
        with tarfile.open(path, "r:*") as tar:
            for member in tar.getmembers():
                if not (member.isfile() and member.name.endswith(".txt")):
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                text = f.read().decode("utf-8", errors="ignore")
                docs.append((Path(member.name).stem, text))
        return docs

    if path.is_dir():
        return [(f.stem, f.read_text(encoding="utf-8")) for f in sorted(path.glob("*.txt"))]

    return [(path.stem, path.read_text(encoding="utf-8"))]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input", help="Fichier .txt, répertoire de .txt, ou archive .tar.gz/.tgz/.tar de .txt")
    p.add_argument("--out", help="Fichier JSONL de sortie (sinon stdout)")
    args = p.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"ERROR: {input_path} introuvable")

    documents = iter_documents(input_path)
    if not documents:
        sys.exit(f"ERROR: aucun fichier .txt trouvé dans {input_path}")

    lines = []
    for doc_id, text in documents:
        text = text.strip()
        if not text:
            continue
        lines.append(json.dumps({"id": doc_id, "value": text}, ensure_ascii=False))

    if not lines:
        sys.exit("ERROR: tous les fichiers .txt trouvés sont vides")

    output = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"{len(lines)} document(s) écrits dans {args.out}", file=sys.stderr)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
