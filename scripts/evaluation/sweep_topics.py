"""Balayage du nombre de thèmes du rapport (NMF) sur une sortie extract_annotate déjà calculée.

Pour chaque k : cohérence NPMI des étiquettes (top 10 candidats, co-occurrence
dans les segments), stabilité (sous-échantillons à 80 % des segments, appariement
des thèmes au modèle complet), poids du plus gros thème, thèmes génériques, et
classement de couverture (via compute_topic_report, identique au rapport).

Usage :
    python3 scripts/evaluation/sweep_topics.py <racine_repo> <extract_annotate.json> \
        <annotations.json> <sortie.json> [10,15,20,...]
"""
import copy
import json
import sys
import time

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.sparse import csr_matrix
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfTransformer

sys.path.insert(0, sys.argv[1] + "/src")
from loterre_report import MIN_TOPIC_FREQ, SEGMENT_CHARS, compute_topic_report  # noqa: E402

ea_path, ann_path, out_path = sys.argv[2], sys.argv[3], sys.argv[4]
KS = [int(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else [10, 15, 20, 25, 30, 40, 50]

cands = json.load(open(ea_path, encoding="utf-8"))["candidates"]
ann = json.load(open(ann_path, encoding="utf-8")).get("results", [])
# On ne garde que ce dont compute_topic_report a besoin (mémoire).
slim = [{k: c.get(k) for k in ("term", "frequency", "occurrences", "enrichment_suggestion_embed",
                                "enrichment_suggestion_structural", "enrichment_suggestion_specificity")}
        for c in cands]
del cands
for c in slim:
    c["occurrences"] = [{"doc_id": o.get("doc_id"), "start": o["start"]} for o in c["occurrences"] or []]

kept = [c for c in slim if (c.get("frequency") or 0) >= MIN_TOPIC_FREQ]
seg_index, rows, cols = {}, [], []
for col, c in enumerate(kept):
    for o in c["occurrences"]:
        rows.append(seg_index.setdefault((o["doc_id"], o["start"] // SEGMENT_CHARS), len(seg_index)))
        cols.append(col)
n_seg = len(seg_index)
counts = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(n_seg, len(kept)))
counts.sum_duplicates()
binary = (counts > 0).astype(np.float32).tocsc()
df = np.asarray(binary.sum(axis=0)).ravel()
x = TfidfTransformer().fit_transform(counts)
print(f"{n_seg} segments, {len(kept)} candidats", flush=True)


def npmi(idx):
    sub = binary[:, idx]
    co = (sub.T @ sub).toarray()
    vals = []
    for a in range(len(idx)):
        for b in range(a + 1, len(idx)):
            pij = co[a, b] / n_seg
            if pij == 0:
                vals.append(-1.0)
                continue
            pi, pj = df[idx[a]] / n_seg, df[idx[b]] / n_seg
            vals.append(np.log(pij / (pi * pj)) / -np.log(pij))
    return float(np.mean(vals))


def fit(mat, k):
    m = NMF(n_components=k, init="nndsvd", random_state=42, max_iter=400)
    w = m.fit_transform(mat)
    return w, m.components_


rng = np.random.default_rng(0)
results = []
for k in KS:
    t0 = time.time()
    w, h = fit(x, k)
    seg_topic = w.argmax(axis=1)
    share = np.bincount(seg_topic, minlength=k) / n_seg
    coh = [npmi(list(np.argsort(-h[t])[:10])) for t in range(k)]
    # Stabilité : 3 sous-échantillons de 80 % des segments, appariement hongrois
    # des vecteurs thème-candidats (cosinus) au modèle complet.
    hn = h / (np.linalg.norm(h, axis=1, keepdims=True) + 1e-12)
    stab = []
    for _ in range(3):
        sel = rng.choice(n_seg, int(0.8 * n_seg), replace=False)
        _, hs = fit(x[sel], k)
        hs = hs / (np.linalg.norm(hs, axis=1, keepdims=True) + 1e-12)
        sim = hn @ hs.T
        r, c = linear_sum_assignment(-sim)
        stab.append(float(sim[r, c].mean()))
    rep = compute_topic_report(copy.deepcopy(slim), ann, k)
    ranked = [t for t in rep["topics"] if not t["generic"]]
    travail = [(i + 1, t) for i, t in enumerate(ranked)
               if any(w_ in t["label"][:10] for w_ in ("travail", "travailleurs"))]
    res = {
        "k": k, "seconds": round(time.time() - t0),
        "npmi_mean": round(float(np.mean(coh)), 4), "npmi_median": round(float(np.median(coh)), 4),
        "stability": round(float(np.mean(stab)), 4), "stability_runs": [round(s, 4) for s in stab],
        "max_share": round(float(share.max()), 4), "mean_share": round(1 / k, 4),
        "n_generic": sum(t["generic"] for t in rep["topics"]),
        "generic_labels": [", ".join(t["label"][:6]) for t in rep["topics"] if t["generic"]],
        "least_covered": [(round(t["coverage"], 3), ", ".join(t["label"][:6])) for t in ranked[:5]],
        "most_covered": [(round(t["coverage"], 3), ", ".join(t["label"][:6])) for t in ranked[-5:]],
        "travail": [(rank, len(ranked), round(t["coverage"], 3), ", ".join(t["label"][:6])) for rank, t in travail],
    }
    results.append(res)
    print(json.dumps(res, ensure_ascii=False), flush=True)
    json.dump(results, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
