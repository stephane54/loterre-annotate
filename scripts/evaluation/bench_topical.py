#!/usr/bin/env python3
"""Benchmark de signaux de répartition intra-corpus (dispersion / concentration
thématique) contre le gold ACTER — question : un candidat concentré dans une
partie du corpus (un "thème") est-il plus probablement un terme qu'un candidat
réparti uniformément (bruit académique générique) ?

Aucun des trois signaux existants ne mesure ça : embed = proximité au
vocabulaire cible, structurel (C-value/PositionRank) = forme/fréquence,
spécificité = contraste vs langue générale.

Unité de répartition : segments de SEGMENT_CHARS caractères de chaque
document (et non les documents eux-mêmes — ACTER n'a que 2 à 12 documents
pour wind/corp, trop peu pour une dispersion). ~500-600 segments par
couple domaine/langue, homogène entre domaines. 600 caractères ≈ 100 tokens,
sous la fenêtre de 128 tokens de MiniLM (pas de troncature à l'encodage).

Signaux testés (plus haut = plus "terme") :
- `ridf`     : IDF résiduel (Church & Gale 1995) — IDF observé moins IDF
               attendu sous Poisson ; > 0 = candidat "en rafales".
- `dp`       : DP de Gries (2008), déviation des proportions — 0 = réparti
               comme le corpus, 1 = concentré dans un seul segment.
- `nmf`      : NMF (scikit-learn) sur la matrice segments × candidats
               (tf-idf) ; score = poids max du candidat dans un thème.
- `bertopic` : recette BERTopic — segments encodés avec MiniLM (même modèle
               que embed), regroupés en thèmes, candidats notés par c-TF-IDF
               (formule BERTopic), score = c-TF-IDF max sur les thèmes.
               Regroupement par KMeans (option cluster_model supportée par
               BERTopic) plutôt qu'UMAP+HDBSCAN par défaut : reproductible
               (graine fixe), pas de segments "hors thème" (-1), et pas de
               dépendance ajoutée (bertopic/umap-learn/numba non installés).

Trois modes, mêmes protocoles que bench_specificity.py :
- `standalone`   : classement autonome par signal vs ncvalue/graph, coupure
                   top-N = fraction × n_gold_terms.
- `filter-sweep` : retire les N% de candidats les plus faibles selon le signal
                   avant ncvalue (comme --specificity-filter-pctl).
- `embed`        : signal comme niveau de suggestion supplémentaire pour embed
                   (seed/holdout 50%), précision du niveau isolé (ni embed ni
                   structurel) et union avec structurel(2%) — spécificité
                   recalculée en référence.
- `indicator`    : signal exposé comme score par candidat (pas comme liste) —
                   à l'intérieur de chaque niveau de production (embed,
                   structurel 2%, spécificité 10%), précision du haut vs du
                   bas du classement par le signal.

Usage:
    python3 scripts/evaluation/bench_topical.py --mode standalone
    python3 scripts/evaluation/bench_topical.py --mode filter-sweep
    python3 scripts/evaluation/bench_topical.py --mode embed
    python3 scripts/evaluation/bench_topical.py --mode indicator
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import acter_eval as ae  # noqa: E402
from bench_specificity import DOMAINS, LANGS, _prf_totals_to_row, iter_domains, unique_gold_terms  # noqa: E402
from loterre_extract_cli import extract_candidates, score_extracted_candidates  # noqa: E402

SEGMENT_CHARS = 600
SEED = 42
DEFAULT_SIGNALS = ["ridf", "dp", "nmf", "bertopic"]
DEFAULT_FRACTIONS = [0.1, 0.5, 1.0, 1.5]
DEFAULT_PERCENTILES = [0, 10, 20, 30, 40, 50]
DEFAULT_TOP_PCTS = [2.0, 5.0, 10.0]
ENRICHMENT_THRESHOLD = 0.95


# ── segmentation et matrice candidats × segments ─────────────────────────────

def build_segments(texts: dict[str, str]) -> tuple[list[tuple[str, int]], list[str]]:
    """Découpe chaque document en segments de SEGMENT_CHARS caractères.
    Retourne les identifiants (doc_id, index) et les textes des segments."""
    seg_ids, seg_texts = [], []
    for doc_id, text in texts.items():
        for k in range(max(1, math.ceil(len(text) / SEGMENT_CHARS))):
            seg_ids.append((doc_id, k))
            seg_texts.append(text[k * SEGMENT_CHARS:(k + 1) * SEGMENT_CHARS])
    return seg_ids, seg_texts


def build_count_matrix(candidates, seg_ids) -> np.ndarray:
    """counts[c, s] = occurrences du candidat c dans le segment s (depuis
    CandidateTerm.occurrences, aucun second passage spaCy)."""
    seg_index = {sid: i for i, sid in enumerate(seg_ids)}
    counts = np.zeros((len(candidates), len(seg_ids)), dtype=np.float32)
    for ci, c in enumerate(candidates):
        for occ in c.occurrences:
            si = seg_index.get((occ.doc_id, occ.start // SEGMENT_CHARS))
            if si is not None:
                counts[ci, si] += 1
    return counts


# ── signaux ──────────────────────────────────────────────────────────────────

def signal_ridf(counts: np.ndarray, _seg_sizes, _ctx) -> np.ndarray:
    n_seg = counts.shape[1]
    cf = counts.sum(axis=1)
    df = (counts > 0).sum(axis=1)
    out = np.zeros(len(cf))
    ok = df > 0
    observed_idf = -np.log2(df[ok] / n_seg)
    expected_idf = -np.log2(1.0 - np.exp(-cf[ok] / n_seg))
    out[ok] = observed_idf - expected_idf
    return out


def signal_dp(counts: np.ndarray, seg_sizes: np.ndarray, _ctx) -> np.ndarray:
    expected = seg_sizes / seg_sizes.sum()
    cf = counts.sum(axis=1, keepdims=True)
    observed = np.divide(counts, cf, out=np.zeros_like(counts), where=cf > 0)
    dp = 0.5 * np.abs(observed - expected).sum(axis=1)
    return dp / (1.0 - expected.min())


def _n_topics(n_seg: int) -> int:
    return int(min(20, max(5, n_seg // 30)))


def signal_nmf(counts: np.ndarray, _seg_sizes, _ctx) -> np.ndarray:
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfTransformer

    x = TfidfTransformer().fit_transform(counts.T)  # segments × candidats
    model = NMF(n_components=_n_topics(counts.shape[1]), init="nndsvd", random_state=SEED, max_iter=400)
    model.fit(x)
    h = model.components_  # thèmes × candidats
    h = h / np.maximum(h.sum(axis=1, keepdims=True), 1e-12)  # poids relatif dans chaque thème
    return h.max(axis=0)


def signal_bertopic(counts: np.ndarray, _seg_sizes, ctx) -> np.ndarray:
    from sklearn.cluster import KMeans

    emb = ctx["model"].encode(ctx["seg_texts"], batch_size=64, show_progress_bar=False,
                              normalize_embeddings=True)
    k = _n_topics(counts.shape[1])
    labels = KMeans(n_clusters=k, random_state=SEED, n_init=10).fit_predict(emb)
    ctx["topic_labels"] = labels
    # c-TF-IDF (BERTopic) : tf = fréquence du candidat dans la classe normalisée
    # par la taille de la classe ; idf = log(1 + A / f), A = nb moyen
    # d'occurrences par classe, f = fréquence totale du candidat.
    class_counts = np.stack([counts[:, labels == t].sum(axis=1) for t in range(k)], axis=0)  # k × cand
    class_totals = np.maximum(class_counts.sum(axis=1, keepdims=True), 1e-12)
    tf = class_counts / class_totals
    avg_words = class_counts.sum() / k
    idf = np.log(1.0 + avg_words / np.maximum(class_counts.sum(axis=0), 1e-12))
    return (tf * idf).max(axis=0)


def signal_freq(counts: np.ndarray, _seg_sizes, _ctx) -> np.ndarray:
    """Témoin : fréquence brute du candidat. Un signal de répartition qui ne
    fait pas mieux que ça n'apporte rien de propre (voir entrée 2026-09-30)."""
    return counts.sum(axis=1)


SIGNAL_FUNCS = {"ridf": signal_ridf, "dp": signal_dp, "nmf": signal_nmf, "bertopic": signal_bertopic,
                "freq": signal_freq}


def compute_signals(candidates, texts, signals, ctx) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    seg_ids, seg_texts = build_segments(texts)
    ctx["seg_texts"] = seg_texts
    seg_sizes = np.array([len(t) for t in seg_texts], dtype=np.float64)
    counts = build_count_matrix(candidates, seg_ids)
    out, timings = {}, {}
    for name in signals:
        t0 = time.perf_counter()
        out[name] = SIGNAL_FUNCS[name](counts, seg_sizes, ctx)
        timings[name] = time.perf_counter() - t0
    return out, timings


def rank_desc(scores: np.ndarray) -> np.ndarray:
    """rank[i] = rang 1-indexé du candidat i (1 = meilleur score)."""
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(len(scores), dtype=int)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


def _add(totals: dict, prf: dict) -> None:
    totals["tp"] += prf["tp"]; totals["fp"] += prf["fp"]; totals["fn"] += prf["fn"]


def _new_totals() -> dict:
    return {"tp": 0, "fp": 0, "fn": 0}


def _needs_model(signals) -> bool:
    return "bertopic" in signals


def _load_model_if_needed(signals, ctx) -> None:
    if _needs_model(signals) and "model" not in ctx:
        from loterre_embed import get_embed_model
        ctx["model"] = get_embed_model()


def _print_timings(timing_totals: dict) -> None:
    print("\nTemps cumulés par signal (tous couples domaine/langue) :")
    for name, secs in timing_totals.items():
        print(f"  {name:<10} {secs:7.1f} s")


# ── mode "standalone" ────────────────────────────────────────────────────────

def run_standalone(args) -> dict:
    fractions = [float(f) for f in args.fractions.split(",")]
    signals = args.signals.split(",")
    methods = ["ncvalue", "graph"] + signals
    totals = {(m, f): _new_totals() for m in methods for f in fractions}
    timing_totals = {s: 0.0 for s in signals}
    ctx: dict = {}
    _load_model_if_needed(signals, ctx)

    for domain, lang, domain_dir in iter_domains(Path(args.corpus_root), args.domains.split(","), args.langs.split(",")):
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        n_gold_terms = len(unique_gold_terms(gold_tokens_by_doc, texts))
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )
        sig, timings = compute_signals(candidates, texts, signals, ctx)
        for s, secs in timings.items():
            timing_totals[s] += secs

        for method in methods:
            if method in sig:
                order = np.argsort(-sig[method], kind="stable")
                scored = [candidates[i] for i in order]
            else:
                scored, _ = score_extracted_candidates(
                    list(candidates), per_doc_tokens, total_tokens, method,
                    auto_threshold=50000, lang=lang, dict_path=None,
                )
            for fraction in fractions:
                n = max(1, round(n_gold_terms * fraction))
                pred = ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in scored[:n]]})
                _add(totals[(method, fraction)], ae.token_level_prf(gold_tokens_by_doc, pred))

    print("\n== Classement autonome : signaux de répartition vs ncvalue/graph, micro-moyenne ==")
    print(f"{'methode':<10}" + "".join(f"F1@{f:.2f}".rjust(10) for f in fractions))
    rows_out = []
    for method in methods:
        line = f"{method:<10}"
        for fraction in fractions:
            row = _prf_totals_to_row(totals[(method, fraction)])
            line += f"{row['f1']:>10.3f}"
            rows_out.append({"method": method, "fraction": fraction, **row})
        print(line)
    _print_timings(timing_totals)
    return {"mode": "standalone", "min_freq": args.min_freq, "segment_chars": SEGMENT_CHARS,
            "rows": rows_out, "timings_s": timing_totals}


# ── mode "filter-sweep" (ncvalue) ────────────────────────────────────────────

def run_filter_sweep(args) -> dict:
    fractions = [float(f) for f in args.fractions.split(",")]
    percentiles = [float(p) for p in args.percentiles.split(",")]
    signals = args.signals.split(",")
    totals = {(s, p, f): _new_totals() for s in signals for p in percentiles for f in fractions}
    ctx: dict = {}
    _load_model_if_needed(signals, ctx)

    for domain, lang, domain_dir in iter_domains(Path(args.corpus_root), args.domains.split(","), args.langs.split(",")):
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        n_gold_terms = len(unique_gold_terms(gold_tokens_by_doc, texts))
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )
        sig, _ = compute_signals(candidates, texts, signals, ctx)
        baseline_scored = None

        for s in signals:
            sorted_scores = np.sort(sig[s])
            for pctl in percentiles:
                if pctl <= 0:
                    if baseline_scored is None:
                        baseline_scored, _ = score_extracted_candidates(
                            list(candidates), per_doc_tokens, total_tokens, "ncvalue",
                            auto_threshold=50000, lang=lang, dict_path=None,
                        )
                    scored = baseline_scored
                else:
                    cutoff = sorted_scores[min(int(len(sorted_scores) * pctl / 100), len(sorted_scores) - 1)]
                    kept = [c for c, v in zip(candidates, sig[s]) if v >= cutoff]
                    scored, _ = score_extracted_candidates(
                        kept, per_doc_tokens, total_tokens, "ncvalue",
                        auto_threshold=50000, lang=lang, dict_path=None,
                    )
                for fraction in fractions:
                    n = max(1, round(n_gold_terms * fraction))
                    pred = ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in scored[:n]]})
                    _add(totals[(s, pctl, fraction)], ae.token_level_prf(gold_tokens_by_doc, pred))

    print("\n== Filtre avant ncvalue : % de candidats les plus faibles retirés, micro-moyenne ==")
    rows_out = []
    for s in signals:
        print(f"\n-- {s} --")
        print(f"{'pctl':>6}" + "".join(f"F1@{f:.2f}".rjust(10) for f in fractions))
        for pctl in percentiles:
            line = f"{pctl:>5.0f}%"
            by_fraction = {}
            for fraction in fractions:
                r = _prf_totals_to_row(totals[(s, pctl, fraction)])
                line += f"{r['f1']:>10.3f}"
                by_fraction[fraction] = r
            print(line)
            rows_out.append({"signal": s, "percentile_removed": pctl, "by_fraction": by_fraction})
    return {"mode": "filter-sweep", "min_freq": args.min_freq, "segment_chars": SEGMENT_CHARS, "rows": rows_out}


# ── mode "embed" : niveau de suggestion supplémentaire ───────────────────────

def run_embed(args) -> dict:
    top_pcts = [float(p) for p in args.top_pcts.split(",")]
    signals = args.signals.split(",") + ["specificity"]
    from loterre_embed import embed_vocabulary_terms, get_embed_model, load_vocabulary_terms, score_candidates_embed
    from loterre_extract_cli import _attach_structural_signal
    from loterre_specificity import score_candidates_specificity

    ctx: dict = {"model": get_embed_model()}
    structural_totals = _new_totals()
    union_totals = {(s, p): _new_totals() for s in signals for p in top_pcts}
    isolated_totals = {(s, p): _new_totals() for s in signals for p in top_pcts}
    isolated_counts = {(s, p): 0 for s in signals for p in top_pcts}

    for domain, lang, domain_dir in iter_domains(Path(args.corpus_root), args.domains.split(","), args.langs.split(",")):
        terms_path = (domain_dir / "annotated" / "annotations" / "unique_annotation_lists"
                      / f"{domain}_{lang}_terms.tsv")
        if not terms_path.exists():
            continue
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        seed_terms, _ = ae.split_seed_holdout(ae.read_unique_terms(terms_path), fraction=0.5, seed=SEED)
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )

        seed_dict_path = Path(args.out_dir) / f"tmp_seed_topical_{domain}_{lang}.jsonl"
        seed_dict_path.parent.mkdir(parents=True, exist_ok=True)
        with seed_dict_path.open("w", encoding="utf-8") as f:
            for term in seed_terms:
                f.write(json.dumps({"id": term, "pref": term}, ensure_ascii=False) + "\n")
        vocab_embeddings = embed_vocabulary_terms(ctx["model"], load_vocabulary_terms(str(seed_dict_path)))
        score_candidates_embed(candidates, ctx["model"], vocab_embeddings)
        seed_dict_path.unlink(missing_ok=True)

        _attach_structural_signal(candidates, per_doc_tokens, total_tokens, 50000)
        score_candidates_specificity(candidates, per_doc_tokens, lang)
        sig, _ = compute_signals(candidates, texts, args.signals.split(","), ctx)
        ranks = {s: rank_desc(v) for s, v in sig.items()}
        ranks["specificity"] = np.array([c.specificity_rank or len(candidates) + 1 for c in candidates])

        n_total = len(candidates)
        structural_top_n = max(1, round(n_total * 2.0 / 100))
        top_n = {p: max(1, round(n_total * p / 100)) for p in top_pcts}

        structural_set = []
        union_sets = {(s, p): [] for s in signals for p in top_pcts}
        isolated_sets = {(s, p): [] for s in signals for p in top_pcts}
        for i, c in enumerate(candidates):
            if c.term.lower() in seed_terms:
                continue
            is_embed = c.score >= ENRICHMENT_THRESHOLD
            is_structural = c.structural_rank is not None and c.structural_rank <= structural_top_n
            if is_embed or is_structural:
                structural_set.append(c)
            for s in signals:
                for p in top_pcts:
                    hit = ranks[s][i] <= top_n[p]
                    if is_embed or is_structural or hit:
                        union_sets[(s, p)].append(c)
                    if hit and not is_embed and not is_structural:
                        isolated_sets[(s, p)].append(c)

        def prf(cands):
            return ae.token_level_prf(
                gold_tokens_by_doc, ae.predicted_spans_by_doc({"candidates": [c.to_dict() for c in cands]}),
                texts=texts, exclude_terms=seed_terms,
            )

        _add(structural_totals, prf(structural_set))
        for key in union_sets:
            _add(union_totals[key], prf(union_sets[key]))
            _add(isolated_totals[key], prf(isolated_sets[key]))
            isolated_counts[key] += len(isolated_sets[key])

    base = _prf_totals_to_row(structural_totals)
    print("\n== embed + structurel(2%) + signal(X%), micro-moyenne ==")
    print(f"référence embed + structurel(2%) : {base}")
    rows_out = []
    for s in signals:
        for p in top_pcts:
            u = _prf_totals_to_row(union_totals[(s, p)])
            iso = _prf_totals_to_row(isolated_totals[(s, p)])
            n_iso = isolated_counts[(s, p)]
            print(f"{s:<12} {p:>4.0f}%  union F1={u['f1']:.3f} (P={u['precision']:.3f} R={u['recall']:.3f})"
                  f"  | niveau isolé P={iso['precision']:.3f} R={iso['recall']:.3f} n={n_iso}")
            rows_out.append({"signal": s, "top_pct": p, "union": u, "isolated": iso, "isolated_n": n_iso})
    return {"mode": "embed", "min_freq": args.min_freq, "segment_chars": SEGMENT_CHARS,
            "reference_structural_2pct": base, "rows": rows_out}


# ── mode "indicator" : le signal ordonne-t-il bien l'intérieur des niveaux ? ──

INDICATOR_SPECIFICITY_TOP_PCT = 10.0  # niveau 3 à sa valeur calibrée (opt-in)


def run_indicator(args) -> dict:
    """Signal exposé comme score par candidat (pas comme liste) : à l'intérieur
    de chaque niveau de suggestion de production (mutuellement exclusifs,
    comme run_extract_annotate_mode), compare la précision du quart/de la
    moitié le mieux noté par le signal à celle du quart/de la moitié le moins
    bien noté. Un signal utile au curateur sépare nettement les deux.

    Deux précisions : token-level (protocole ACTER, pondère chaque candidat
    par ses occurrences — favorise mécaniquement les candidats fréquents) et
    par candidat (chaque candidat compte une fois : son terme est-il un terme
    gold held-out ? — ce que voit réellement le curateur en relisant une
    liste). `frequency` est ajouté comme témoin : un signal qui ne fait pas
    mieux que la fréquence brute n'apporte rien de propre."""
    signals = args.signals.split(",") + ["specificity", "frequency"]
    from loterre_embed import embed_vocabulary_terms, get_embed_model, load_vocabulary_terms, score_candidates_embed
    from loterre_extract_cli import _attach_structural_signal
    from loterre_specificity import score_candidates_specificity

    ctx: dict = {"model": get_embed_model()}
    tiers = ["embed", "structural", "specificity_tier"]
    slices = ["top25", "top50", "bottom50", "bottom25"]
    totals = {(t, s, sl): _new_totals() for t in tiers for s in signals for sl in slices}
    type_hits = {(t, s, sl): [0, 0] for t in tiers for s in signals for sl in slices}  # [gold, total]
    tier_totals = {t: _new_totals() for t in tiers}
    tier_type_hits = {t: [0, 0] for t in tiers}
    tier_sizes = {t: 0 for t in tiers}

    for domain, lang, domain_dir in iter_domains(Path(args.corpus_root), args.domains.split(","), args.langs.split(",")):
        terms_path = (domain_dir / "annotated" / "annotations" / "unique_annotation_lists"
                      / f"{domain}_{lang}_terms.tsv")
        if not terms_path.exists():
            continue
        texts, gold_tokens_by_doc, _ = ae.load_domain_gold(domain_dir)
        seed_terms, holdout_terms = ae.split_seed_holdout(ae.read_unique_terms(terms_path), fraction=0.5, seed=SEED)
        holdout_lower = {t.lower() for t in holdout_terms}
        rows = [{"id": doc_id, "value": text} for doc_id, text in texts.items()]
        candidates, total_tokens, per_doc_tokens = extract_candidates(
            rows, lang, min_tokens=1, max_tokens=6, min_freq=args.min_freq,
        )

        seed_dict_path = Path(args.out_dir) / f"tmp_seed_indicator_{domain}_{lang}.jsonl"
        seed_dict_path.parent.mkdir(parents=True, exist_ok=True)
        with seed_dict_path.open("w", encoding="utf-8") as f:
            for term in seed_terms:
                f.write(json.dumps({"id": term, "pref": term}, ensure_ascii=False) + "\n")
        vocab_embeddings = embed_vocabulary_terms(ctx["model"], load_vocabulary_terms(str(seed_dict_path)))
        score_candidates_embed(candidates, ctx["model"], vocab_embeddings)
        seed_dict_path.unlink(missing_ok=True)

        _attach_structural_signal(candidates, per_doc_tokens, total_tokens, 50000)
        score_candidates_specificity(candidates, per_doc_tokens, lang)
        sig, _ = compute_signals(candidates, texts, args.signals.split(","), ctx)
        sig["specificity"] = np.array([c.specificity_score or 0.0 for c in candidates])
        sig["frequency"] = np.array([float(c.frequency) for c in candidates])
        is_gold = [c.term.lower() in holdout_lower for c in candidates]

        n_total = len(candidates)
        structural_top_n = max(1, round(n_total * 2.0 / 100))
        specificity_top_n = max(1, round(n_total * INDICATOR_SPECIFICITY_TOP_PCT / 100))
        members = {t: [] for t in tiers}  # indices de candidats
        for i, c in enumerate(candidates):
            if c.term.lower() in seed_terms:
                continue
            if c.score >= ENRICHMENT_THRESHOLD:
                members["embed"].append(i)
            elif c.structural_rank is not None and c.structural_rank <= structural_top_n:
                members["structural"].append(i)
            elif c.specificity_rank is not None and c.specificity_rank <= specificity_top_n:
                members["specificity_tier"].append(i)

        def prf(idx):
            return ae.token_level_prf(
                gold_tokens_by_doc,
                ae.predicted_spans_by_doc({"candidates": [candidates[i].to_dict() for i in idx]}),
                texts=texts, exclude_terms=seed_terms,
            )

        for t in tiers:
            idx = members[t]
            tier_sizes[t] += len(idx)
            _add(tier_totals[t], prf(idx))
            tier_type_hits[t][0] += sum(is_gold[i] for i in idx)
            tier_type_hits[t][1] += len(idx)
            if len(idx) < 4:
                continue
            for s in signals:
                ordered = sorted(idx, key=lambda i: -sig[s][i])
                q, h = len(ordered) // 4, len(ordered) // 2
                parts = {"top25": ordered[:q], "top50": ordered[:h],
                         "bottom50": ordered[h:], "bottom25": ordered[len(ordered) - q:]}
                for sl, part in parts.items():
                    _add(totals[(t, s, sl)], prf(part))
                    type_hits[(t, s, sl)][0] += sum(is_gold[i] for i in part)
                    type_hits[(t, s, sl)][1] += len(part)

    def type_p(hits):
        return hits[0] / hits[1] if hits[1] else 0.0

    hdr = f"{'signal':<12}{'P top25%':>10}{'P top50%':>10}{'P bas50%':>10}{'P bas25%':>10}{'écart50':>9}"
    print("\n== Précision à l'intérieur de chaque niveau, selon le signal (micro-moyenne) ==")
    rows_out = []
    for t in tiers:
        base = _prf_totals_to_row(tier_totals[t])
        print(f"\n-- niveau {t} : n={tier_sizes[t]}  P token={base['precision']:.3f}"
              f"  P candidat={type_p(tier_type_hits[t]):.3f} --")
        for label in ("token", "candidat"):
            print(f"[précision par {label}]")
            print(hdr)
            for s in signals:
                if label == "token":
                    p = {sl: _prf_totals_to_row(totals[(t, s, sl)])["precision"] for sl in slices}
                else:
                    p = {sl: type_p(type_hits[(t, s, sl)]) for sl in slices}
                print(f"{s:<12}{p['top25']:>10.3f}{p['top50']:>10.3f}{p['bottom50']:>10.3f}{p['bottom25']:>10.3f}"
                      f"{p['top50'] - p['bottom50']:>+9.3f}")
                rows_out.append({"tier": t, "signal": s, "level": label, "precision": p,
                                 "tier_precision_token": base["precision"],
                                 "tier_precision_candidate": type_p(tier_type_hits[t]),
                                 "tier_size": tier_sizes[t]})
    return {"mode": "indicator", "min_freq": args.min_freq, "segment_chars": SEGMENT_CHARS,
            "specificity_top_pct": INDICATOR_SPECIFICITY_TOP_PCT, "rows": rows_out}


def main() -> None:
    pa = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    pa.add_argument("--mode", choices=["standalone", "filter-sweep", "embed", "indicator"], required=True)
    pa.add_argument("--corpus-root", default="corpus_acter")
    pa.add_argument("--out-dir", default="benchmark_results/topical")
    pa.add_argument("--domains", default=",".join(DOMAINS))
    pa.add_argument("--langs", default=",".join(LANGS))
    pa.add_argument("--min-freq", type=int, default=1)
    pa.add_argument("--signals", default=",".join(DEFAULT_SIGNALS),
                    help="Signaux à tester parmi " + ",".join(SIGNAL_FUNCS))
    pa.add_argument("--fractions", default=",".join(str(f) for f in DEFAULT_FRACTIONS),
                    help="[standalone/filter-sweep] Fractions de n_gold_terms pour la coupure top-N")
    pa.add_argument("--percentiles", default=",".join(str(p) for p in DEFAULT_PERCENTILES),
                    help="[filter-sweep] Percentiles de candidats retirés à tester")
    pa.add_argument("--top-pcts", default=",".join(str(p) for p in DEFAULT_TOP_PCTS),
                    help="[embed] Part des candidats retenue par le signal")
    args = pa.parse_args()

    corpus_root = Path(args.corpus_root)
    if not corpus_root.exists():
        sys.exit(f"ERROR: {corpus_root} introuvable — lancer `make corpus-acter` d'abord")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    runner = {"standalone": run_standalone, "filter-sweep": run_filter_sweep, "embed": run_embed,
              "indicator": run_indicator}[args.mode]
    result = runner(args)
    out_path = out_dir / f"bench_topical_{args.mode}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"\nJSON -> {out_path}")


if __name__ == "__main__":
    main()
