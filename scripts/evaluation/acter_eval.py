#!/usr/bin/env python3
"""Benchmark des extracteurs v2.0 (ncvalue/graph) contre le gold standard ACTER
(Phase 6, planification/planif_extraction_terminologique.md).

ACTER (https://github.com/AylaRT/ACTER, CC BY-NC-SA 4.0) annote des termes au
niveau token (IOB) sur une tokenisation différente de la nôtre (LeTs Preprocess
vs spaCy) — on réaligne donc les tokens gold sur des offsets caractères dans le
texte brut, puis on compare au niveau caractère (aucune dépendance à un
tokeniseur commun).

L'extracteur `embed` (Phase 5) ne peut pas être comparé "à froid" comme
ncvalue/graph : il a besoin d'un vocabulaire cible (comparé par plus proche
voisin), qu'ACTER n'a pas (aucun vocabulaire Loterre ne couvre ses 4 domaines). Une
variante EXPÉRIMENTALE semi-supervisée est incluse en plus (section séparée) :
la moitié des termes gold d'un domaine sert de vocabulaire de référence
("seed"), l'autre moitié ("held-out") est l'objectif à retrouver — ce n'est PAS
comparable aux chiffres ncvalue/graph/D-Terminer (le système voit une partie
de la réponse), seulement informatif sur la capacité d'enrichissement.

Usage:
    make corpus-acter        # clone le corpus dans corpus_acter/
    python3 scripts/evaluation/acter_eval.py --corpus-root corpus_acter --out-dir benchmark_results/acter
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corpus"))
from txt_to_jsonl import iter_documents  # noqa: E402

DOMAINS = ["corp", "equi", "htfl", "wind"]
LANGS = ["en", "fr"]
EXTRACTORS = ["ncvalue", "graph"]


# ── alignement gold (tokens IOB -> offsets caractères) ─────────────────────────

def read_iob_file(path: Path) -> list[tuple[str, str]]:
    tokens = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        tokens.append((parts[0], parts[1]))
    return tokens


def align_gold_tokens(raw_text: str, gold_tokens: list[tuple[str, str]]) -> tuple[list[tuple[int, int, str]], int]:
    """Réaligne chaque token gold sur ses offsets caractères dans *raw_text*,
    par marche séquentielle (recherche du token à partir de la position
    courante, en sautant les espaces). Retourne (tokens_alignés, n_échecs)."""
    aligned = []
    pos = 0
    n = len(raw_text)
    failures = 0
    for tok_text, label in gold_tokens:
        while pos < n and raw_text[pos].isspace():
            pos += 1
        if raw_text[pos:pos + len(tok_text)] == tok_text:
            start, end = pos, pos + len(tok_text)
        else:
            idx = raw_text.find(tok_text, pos, pos + 500)
            if idx == -1:
                failures += 1
                continue
            start, end = idx, idx + len(tok_text)
        aligned.append((start, end, label))
        pos = end
    return aligned, failures


def gold_term_spans(aligned_tokens: list[tuple[int, int, str]]) -> list[tuple[int, int]]:
    """Fusionne les tokens B/I consécutifs en spans de termes (offsets
    caractères) ; un "I" sans "B" préalable (jamais observé en pratique mais
    possible en théorie) démarre aussi un span, par robustesse."""
    spans = []
    cur_start = cur_end = None
    for start, end, label in aligned_tokens:
        if label in ("B", "I") and cur_start is None:
            cur_start, cur_end = start, end
        elif label in ("B", "I") and label == "B":
            spans.append((cur_start, cur_end))
            cur_start, cur_end = start, end
        elif label == "I":
            cur_end = end
        else:  # "O"
            if cur_start is not None:
                spans.append((cur_start, cur_end))
            cur_start = cur_end = None
    if cur_start is not None:
        spans.append((cur_start, cur_end))
    return spans


# ── extraction + comparaison token-level ───────────────────────────────────────

def run_extraction(extract_cli: Path, jsonl_path: Path, lang: str, extractor: str, min_freq: int,
                    dict_path: Path | None = None) -> dict:
    cmd = [
        sys.executable, str(extract_cli),
        "--text", str(jsonl_path), "--lang", lang,
        "--extractor", extractor, "--min-freq", str(min_freq),
        "--silent",
    ]
    if dict_path is not None:
        cmd.extend(["--dict", str(dict_path)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"extraction failed ({' '.join(cmd)}):\n{proc.stderr}")
    return json.loads(proc.stdout)


def predicted_spans_by_doc(extraction_payload: dict) -> dict[str, list[tuple[int, int]]]:
    spans_by_doc: dict[str, list[tuple[int, int]]] = {}
    for c in extraction_payload.get("candidates", []):
        for occ in c.get("occurrences", []):
            spans_by_doc.setdefault(occ["doc_id"], []).append((occ["start"], occ["end"]))
    return spans_by_doc


def overlaps_any(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s < end and e > start for s, e in spans)


def token_level_prf(
    gold_tokens_by_doc: dict[str, list[tuple[int, int, str]]],
    pred_spans_by_doc: dict[str, list[tuple[int, int]]],
    texts: dict[str, str] | None = None,
    exclude_terms: set[str] | None = None,
) -> dict:
    """P/R/F1 token-level. Si *exclude_terms* est fourni (variante semi-
    supervisée), les tokens appartenant à un span gold dont le texte est dans
    *exclude_terms* (les termes "seed", déjà donnés au système) sont
    entièrement exclus du calcul — ni TP/FN (déjà connus, pas intéressants à
    "retrouver") ni FP/TN (le reste du texte n'est pas affecté)."""
    tp = fp = fn = tn = 0
    for doc_id, tokens in gold_tokens_by_doc.items():
        pred_spans = pred_spans_by_doc.get(doc_id, [])
        seed_ranges: list[tuple[int, int]] = []
        if exclude_terms and texts is not None:
            raw_text = texts[doc_id]
            for s, e in gold_term_spans(tokens):
                if raw_text[s:e].lower() in exclude_terms:
                    seed_ranges.append((s, e))
        for start, end, label in tokens:
            if seed_ranges and any(s <= start and end <= e for s, e in seed_ranges):
                continue
            is_gold_term = label in ("B", "I")
            is_pred_term = overlaps_any(start, end, pred_spans)
            if is_gold_term and is_pred_term:
                tp += 1
            elif is_pred_term and not is_gold_term:
                fp += 1
            elif is_gold_term and not is_pred_term:
                fn += 1
            else:
                tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


# ── variante expérimentale : embed semi-supervisé (seed/held-out) ─────────────

def read_unique_terms(path: Path) -> list[str]:
    """Lit unique_annotation_lists/{domain}_{lang}_terms.tsv (terme<TAB>label)."""
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts and parts[0]:
            terms.append(parts[0])
    return terms


def split_seed_holdout(terms: list[str], fraction: float = 0.5, seed: int = 42) -> tuple[set[str], set[str]]:
    shuffled = sorted(set(t.lower() for t in terms))
    random.Random(seed).shuffle(shuffled)
    cut = int(len(shuffled) * fraction)
    return set(shuffled[:cut]), set(shuffled[cut:])


# ── orchestration par domaine/langue ───────────────────────────────────────────

def load_domain_gold(domain_dir: Path) -> tuple[dict[str, str], dict[str, list[tuple[int, int, str]]], int]:
    """Charge textes bruts + tokens gold alignés pour un domaine/langue.
    Retourne (textes_par_doc, tokens_alignés_par_doc, total_échecs_alignement)."""
    texts_dir = domain_dir / "annotated" / "texts"
    iob_dir = (domain_dir / "annotated" / "annotations" / "sequential_annotations"
               / "iob_annotations" / "without_named_entities")

    texts = dict(iter_documents(texts_dir))
    gold_tokens_by_doc = {}
    total_failures = 0
    for stem, raw_text in texts.items():
        iob_path = iob_dir / f"{stem}_seq_terms.tsv"
        if not iob_path.exists():
            continue
        gold_tokens = read_iob_file(iob_path)
        aligned, failures = align_gold_tokens(raw_text, gold_tokens)
        gold_tokens_by_doc[stem] = aligned
        total_failures += failures
    return texts, gold_tokens_by_doc, total_failures


def evaluate_domain_lang(corpus_root: Path, domain: str, lang: str, extract_cli: Path,
                          min_freq: int, tmp_dir: Path) -> dict:
    domain_dir = corpus_root / lang / domain
    texts, gold_tokens_by_doc, align_failures = load_domain_gold(domain_dir)
    n_gold_tokens = sum(len(t) for t in gold_tokens_by_doc.values())

    # Nombre de termes gold uniques (texte, en minuscule) — utilisé comme
    # coupure top-N : ncvalue/graph produisent un classement, pas une
    # décision binaire, donc comparer le classement (pas l'ensemble brut,
    # identique entre extracteurs car même étape d'extraction noun-chunk en
    # amont) nécessite de couper au même N pour les deux.
    unique_gold_terms: set[str] = set()
    for doc_id, tokens in gold_tokens_by_doc.items():
        raw_text = texts[doc_id]
        for start, end in gold_term_spans(tokens):
            unique_gold_terms.add(raw_text[start:end].lower())
    n_gold_terms = len(unique_gold_terms)

    jsonl_path = tmp_dir / f"{domain}_{lang}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for doc_id, text in texts.items():
            f.write(json.dumps({"id": doc_id, "value": text}, ensure_ascii=False) + "\n")

    result = {"domain": domain, "lang": lang, "n_docs": len(texts),
              "n_gold_tokens": n_gold_tokens, "n_gold_terms": n_gold_terms,
              "align_failures": align_failures, "extractors": {}}

    for extractor in EXTRACTORS:
        payload = run_extraction(extract_cli, jsonl_path, lang, extractor, min_freq)
        candidates = payload.get("candidates", [])  # déjà trié par score décroissant
        top_n = candidates[:n_gold_terms]
        pred_spans = predicted_spans_by_doc({"candidates": top_n})
        prf = token_level_prf(gold_tokens_by_doc, pred_spans)
        prf["n_candidates_total"] = len(candidates)
        prf["n_candidates_kept"] = len(top_n)
        result["extractors"][extractor] = prf

    jsonl_path.unlink(missing_ok=True)
    return result


def evaluate_domain_lang_embed_seeded(corpus_root: Path, domain: str, lang: str, extract_cli: Path,
                                       min_freq: int, tmp_dir: Path, seed_fraction: float) -> dict:
    """Variante EXPÉRIMENTALE semi-supervisée : la moitié des termes gold du
    domaine sert de vocabulaire de référence (`--extractor embed`, comparé
    par plus proche voisin) ; l'objectif est de retrouver l'autre moitié
    ("held-out"), jamais montrée au système. Pas comparable aux chiffres
    ncvalue/graph "à froid"."""
    domain_dir = corpus_root / lang / domain
    texts, gold_tokens_by_doc, _ = load_domain_gold(domain_dir)

    terms_path = (domain_dir / "annotated" / "annotations" / "unique_annotation_lists"
                  / f"{domain}_{lang}_terms.tsv")
    if not terms_path.exists():
        return {"domain": domain, "lang": lang, "skipped": True, "reason": "unique_annotation_lists absent"}

    all_terms = read_unique_terms(terms_path)
    seed_terms, holdout_terms = split_seed_holdout(all_terms, fraction=seed_fraction)

    # Centroïde construit à partir du "vocabulaire" seed uniquement — un faux
    # dictionnaire Loterre minimal (pref/id) suffit, load_vocabulary_terms()
    # de loterre_embed.py ne lit que ces deux champs.
    seed_dict_path = tmp_dir / f"{domain}_{lang}_seed_dict.jsonl"
    with seed_dict_path.open("w", encoding="utf-8") as f:
        for term in seed_terms:
            f.write(json.dumps({"id": term, "pref": term}, ensure_ascii=False) + "\n")

    jsonl_path = tmp_dir / f"{domain}_{lang}_embed.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for doc_id, text in texts.items():
            f.write(json.dumps({"id": doc_id, "value": text}, ensure_ascii=False) + "\n")

    # N = nombre de termes held-out à retrouver, même logique de coupure top-N
    # que pour ncvalue/graph (comparer le classement, pas l'ensemble brut).
    payload = run_extraction(extract_cli, jsonl_path, lang, "embed", min_freq, dict_path=seed_dict_path)
    candidates = payload.get("candidates", [])
    top_n = candidates[:len(holdout_terms)]
    pred_spans = predicted_spans_by_doc({"candidates": top_n})
    prf = token_level_prf(gold_tokens_by_doc, pred_spans, texts=texts, exclude_terms=seed_terms)
    prf["n_candidates_total"] = len(candidates)
    prf["n_candidates_kept"] = len(top_n)

    jsonl_path.unlink(missing_ok=True)
    seed_dict_path.unlink(missing_ok=True)

    return {"domain": domain, "lang": lang, "n_seed_terms": len(seed_terms),
            "n_holdout_terms": len(holdout_terms), "embed_seeded": prf}


def print_table(results: list[dict]) -> None:
    hdr = f"{'Domaine':<8} {'Lang':<5} {'Docs':>5} {'TopN':>6}  {'ncvalue P/R/F1':<22} {'graph P/R/F1':<22}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        nc, gr = r["extractors"]["ncvalue"], r["extractors"]["graph"]
        nc_s = f"{nc['precision']:.2f}/{nc['recall']:.2f}/{nc['f1']:.2f}"
        gr_s = f"{gr['precision']:.2f}/{gr['recall']:.2f}/{gr['f1']:.2f}"
        print(f"{r['domain']:<8} {r['lang']:<5} {r['n_docs']:>5} {r['n_gold_terms']:>6}  {nc_s:<22} {gr_s:<22}")
    print("-" * len(hdr))

    for extractor in EXTRACTORS:
        tp = sum(r["extractors"][extractor]["tp"] for r in results)
        fp = sum(r["extractors"][extractor]["fp"] for r in results)
        fn = sum(r["extractors"][extractor]["fn"] for r in results)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        print(f"TOTAL {extractor:<10} P={p:.3f} R={rc:.3f} F1={f1:.3f}  (tp={tp} fp={fp} fn={fn})")


def print_table_embed_seeded(results: list[dict]) -> None:
    print()
    print("== EXPERIMENTAL — embed semi-supervise (PAS comparable a la table ci-dessus) ==")
    hdr = f"{'Domaine':<8} {'Lang':<5} {'Seed':>6} {'HeldOut':>8}  {'embed P/R/F1':<22}"
    print(hdr)
    print("-" * len(hdr))
    valid = [r for r in results if not r.get("skipped")]
    for r in valid:
        e = r["embed_seeded"]
        e_s = f"{e['precision']:.2f}/{e['recall']:.2f}/{e['f1']:.2f}"
        print(f"{r['domain']:<8} {r['lang']:<5} {r['n_seed_terms']:>6} {r['n_holdout_terms']:>8}  {e_s:<22}")
    print("-" * len(hdr))
    if valid:
        tp = sum(r["embed_seeded"]["tp"] for r in valid)
        fp = sum(r["embed_seeded"]["fp"] for r in valid)
        fn = sum(r["embed_seeded"]["fn"] for r in valid)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * p * rc / (p + rc) if (p + rc) else 0.0
        print(f"TOTAL embed (seeded) P={p:.3f} R={rc:.3f} F1={f1:.3f}  (tp={tp} fp={fp} fn={fn})")


def write_markdown(results: list[dict], path: Path, embed_results: list[dict] | None = None) -> None:
    lines = ["# Benchmark ACTER — C-value vs PositionRank", "",
              "Corpus : [AylaRT/ACTER](https://github.com/AylaRT/ACTER) (CC BY-NC-SA 4.0). "
              "Évaluation token-level (offsets caractères réalignés depuis l'annotation IOB), "
              "sans entités nommées, coupure top-N (N = nombre de termes gold uniques du domaine) "
              "pour comparer le classement, pas l'ensemble brut (identique entre extracteurs). "
              "`embed` non évalué ici (nécessite un vocabulaire cible) — voir section séparée plus bas.", "",
              "| Domaine | Lang | Docs | Gold termes | Gold tokens | Échecs align. | ncvalue P | ncvalue R | ncvalue F1 | graph P | graph R | graph F1 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        nc, gr = r["extractors"]["ncvalue"], r["extractors"]["graph"]
        lines.append(
            f"| {r['domain']} | {r['lang']} | {r['n_docs']} | {r['n_gold_terms']} | {r['n_gold_tokens']} | {r['align_failures']} | "
            f"{nc['precision']} | {nc['recall']} | {nc['f1']} | {gr['precision']} | {gr['recall']} | {gr['f1']} |"
        )

    if embed_results:
        valid = [r for r in embed_results if not r.get("skipped")]
        lines += ["", "## EXPÉRIMENTAL — embed semi-supervisé (PAS comparable au tableau ci-dessus)", "",
                   "La moitié des termes gold sert de vocabulaire de référence (comparé par plus proche "
                   "voisin), l'autre moitié (\"held-out\", jamais montrée) est l'objectif à retrouver. "
                   "Informatif sur la capacité d'enrichissement d'`embed` (Phase 5), pas une comparaison à froid.", "",
                   "| Domaine | Lang | Seed termes | Held-out termes | embed P | embed R | embed F1 |",
                   "|---|---|---:|---:|---:|---:|---:|"]
        for r in valid:
            e = r["embed_seeded"]
            lines.append(
                f"| {r['domain']} | {r['lang']} | {r['n_seed_terms']} | {r['n_holdout_terms']} | "
                f"{e['precision']} | {e['recall']} | {e['f1']} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--corpus-root", default="corpus_acter", help="Racine du corpus ACTER cloné (make corpus-acter)")
    pa.add_argument("--out-dir", default="benchmark_results/acter")
    pa.add_argument("--extract-cli", default="src/loterre_extract_cli.py")
    pa.add_argument("--domains", default=",".join(DOMAINS), help="Domaines à évaluer (séparés par virgule)")
    pa.add_argument("--langs", default=",".join(LANGS), help="Langues à évaluer (séparées par virgule)")
    pa.add_argument("--min-freq", type=int, default=2,
                     help="--min-freq transmis à l'extraction (défaut 2) ; recommandé : 1 sur ACTER "
                          "(corpus de domaine restreints, beaucoup de termes spécifiques à occurrence "
                          "unique — voir `make benchmark-acter`)")
    pa.add_argument("--skip-embed-seeded", action="store_true",
                     help="Ne pas lancer la variante expérimentale embed semi-supervisée (active par défaut)")
    pa.add_argument("--skip-cold", action="store_true",
                     help="Ne pas lancer la comparaison à froid ncvalue/graph (utile pour ne re-lancer "
                          "que la variante embed semi-supervisée après une modification de loterre_embed.py)")
    pa.add_argument("--seed-fraction", type=float, default=0.5,
                     help="[embed semi-supervisé] Fraction des termes gold utilisée comme vocabulaire "
                          "de référence, le reste étant l'objectif à retrouver (défaut 0.5)")
    args = pa.parse_args()

    corpus_root = Path(args.corpus_root)
    if not corpus_root.exists():
        sys.exit(f"ERROR: {corpus_root} introuvable — lancer `make corpus-acter` d'abord")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    extract_cli = Path(args.extract_cli)

    results = []
    if not args.skip_cold:
        for domain in args.domains.split(","):
            for lang in args.langs.split(","):
                domain_dir = corpus_root / lang / domain
                if not domain_dir.exists():
                    print(f"  [skip] {domain}/{lang} absent du corpus", file=sys.stderr)
                    continue
                print(f"== {domain} ({lang}) ==", file=sys.stderr)
                results.append(evaluate_domain_lang(corpus_root, domain, lang, extract_cli, args.min_freq, out_dir))

        print_table(results)

    embed_results: list[dict] = []
    if not args.skip_embed_seeded:
        for domain in args.domains.split(","):
            for lang in args.langs.split(","):
                domain_dir = corpus_root / lang / domain
                if not domain_dir.exists():
                    continue
                print(f"== embed semi-supervise {domain} ({lang}) ==", file=sys.stderr)
                embed_results.append(evaluate_domain_lang_embed_seeded(
                    corpus_root, domain, lang, extract_cli, args.min_freq, out_dir, args.seed_fraction
                ))
        print_table_embed_seeded(embed_results)

    if results:
        # Ne pas écraser un acter_results.json existant avec une liste vide
        # quand --skip-cold est utilisé pour ne relancer que la variante embed.
        (out_dir / "acter_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON -> {out_dir / 'acter_results.json'}")
    if embed_results:
        (out_dir / "acter_results_embed_seeded.json").write_text(
            json.dumps(embed_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON (embed seeded) -> {out_dir / 'acter_results_embed_seeded.json'}")
    if results or embed_results:
        write_markdown(results or json.loads((out_dir / "acter_results.json").read_text(encoding="utf-8")),
                       out_dir / "acter_results.md", embed_results=embed_results)
        print(f"Markdown -> {out_dir / 'acter_results.md'}")


if __name__ == "__main__":
    main()
