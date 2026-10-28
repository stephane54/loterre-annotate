#!/usr/bin/env python3
"""Rapport d'analyse d'un run `extract_annotate` — option `--report rapport.html`
(alias `--topic-report`, 2026-10-02).

Page HTML autonome (aucune ressource externe), en trois parties :

1. **Synthèse chiffrée** : documents, candidats, part du vocabulaire retrouvée
   dans le corpus, documents annotés, suggestions par liste.
2. **Annotation et extraction** : termes du vocabulaire les plus annotés,
   annotations par document, entonnoir candidats → suggestions, candidats par
   longueur, suggestions les plus fréquentes de chaque liste. Comptages directs,
   sans incertitude de méthode.
3. **Thèmes (expérimental)** : le corpus découpé en thèmes (NMF sur les
   candidats) et la couverture du vocabulaire par thème — où la ressource
   manque-t-elle de termes ? Mécanisme : docs/underthehood.md ; usage :
   docs/curation_guide.md.

Partie 3, mécanisme résumé :
- Segments : tranches de SEGMENT_CHARS caractères de chaque document,
  déduites des offsets des occurrences de candidats.
- Thèmes : NMF (scikit-learn) sur la matrice creuse segments × candidats
  (tf-idf, candidats de fréquence >= MIN_TOPIC_FREQ). Thème dominant d'un
  segment = argmax de sa ligne W ; thème principal d'un candidat = argmax de
  sa colonne H.
- Couverture : part des segments du thème contenant au moins une annotation
  d'un **terme propre** du vocabulaire — surreprésenté dans le thème (part de
  ses annotations dans le thème >= SPECIFIC_LIFT × part des segments du thème,
  >= SPECIFIC_MIN_COUNT annotations). Mesurée par les annotations de
  l'annotateur, pas par in_vocabulary (qui sous-estime). Neutralise les termes
  transversaux ("risque sanitaire" sur RevueESR/SEN).
- Chaque candidat reçoit topic_id / topic_label / topic_coverage : des
  informations de **rangement** (filtrer par thème dans le CSV), jamais un
  score de pertinence — NMF comme signal de pertinence a été mesuré et ne fait
  pas mieux que la fréquence (planification/analyse_benchmarks_extraction.md,
  entrée 2026-09-29).

CPU pur, aucun modèle. RevueESR (1 539 documents, 38 838 candidats) : ~15 s.
"""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from typing import Any, Optional

SEGMENT_CHARS = 600
MIN_SEGMENTS = 50          # en dessous, pas assez de matière pour des thèmes
MIN_TOPIC_FREQ = 2         # les hapax n'aident pas à former des thèmes
SPECIFIC_LIFT = 2.0
SPECIFIC_MIN_COUNT = 3
# Thème "générique" : NMF range le discours général ("compte, exemple, mise,
# place, prise, gestion") dans un grand thème fourre-tout, dont la couverture
# est mécaniquement basse — il apparaîtrait à tort en tête des zones "mal
# couvertes". Repéré par son poids : >= GENERIC_SHARE_FACTOR fois le poids
# moyen d'un thème (RevueESR/SEN, 30 thèmes : 13,2% contre 3,3% de moyenne et
# 5,1% pour le thème suivant ; la spécificité des mots de l'étiquette, elle,
# ne le distingue pas).
GENERIC_SHARE_FACTOR = 2.5


def is_generic_topic(segment_share: float, n_topics: int) -> bool:
    return n_topics > 0 and segment_share >= GENERIC_SHARE_FACTOR / n_topics
_SEED = 42
LEVELS = [("enrichment_suggestion_embed", "Liste 1 — embed"),
          ("enrichment_suggestion_structural", "Liste 2 — structurel"),
          ("enrichment_suggestion_specificity", "Liste 3 — spécificité")]


def auto_n_topics(n_segments: int) -> int:
    return int(min(30, max(5, n_segments // 30)))


def count_vocabulary_concepts(dict_path: Optional[str]) -> Optional[int]:
    """Nombre de concepts distincts (champ id) du dictionnaire cible."""
    if not dict_path:
        return None
    ids = set()
    try:
        with open(dict_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    ids.add(json.loads(line).get("id"))
    except OSError:
        return None
    return len(ids)


# ── Parties 1 et 2 : synthèse, annotation, extraction ───────────────────────

def compute_summary(candidates: list[dict[str, Any]], annotation_results: list[dict[str, Any]],
                    payload: dict[str, Any], vocab_size: Optional[int]) -> dict[str, Any]:
    n_docs = payload.get("docs") or len(annotation_results)
    per_doc = [len(r.get("matches", [])) for r in annotation_results]
    concepts: Counter = Counter()
    concept_docs: dict[str, set] = defaultdict(set)
    label_of: dict[str, str] = {}
    for r in annotation_results:
        for m in r.get("matches", []):
            key = m.get("uri") or m.get("pref") or m.get("found") or ""
            concepts[key] += 1
            concept_docs[key].add(r.get("id"))
            label_of.setdefault(key, m.get("pref") or m.get("found") or key)

    hist_bins = [(0, 0, "0"), (1, 2, "1–2"), (3, 5, "3–5"), (6, 10, "6–10"), (11, 20, "11–20"), (21, None, "> 20")]
    hist = [{"label": lab, "count": sum(1 for n in per_doc if n >= lo and (hi is None or n <= hi))}
            for lo, hi, lab in hist_bins]

    in_voc = sum(1 for c in candidates if c.get("in_vocabulary"))
    absent = sum(1 for c in candidates if c.get("in_vocabulary") is False)
    levels = {}
    for field, name in LEVELS:
        sel = sorted((c for c in candidates if c.get(field)), key=lambda c: -(c.get("frequency") or 0))
        levels[name] = {
            "count": len(sel),
            "top": [{"term": c["term"], "frequency": c.get("frequency"), "n_docs": c.get("n_docs"),
                     "nearest_vocab_term": c.get("nearest_vocab_term")} for c in sel[:10]],
        }
    length_bins = Counter()
    for c in candidates:
        n = len(c.get("pattern") or c["term"].split())
        length_bins["4 mots et plus" if n >= 4 else f"{n} mot{'s' if n > 1 else ''}"] += 1

    return {
        "docs": n_docs,
        "total_tokens": payload.get("total_tokens"),
        "n_candidates": len(candidates),
        "in_vocabulary": in_voc,
        "absent": absent,
        "annotations_total": sum(per_doc),
        "concepts_found": len(concepts),
        "vocabulary_size": vocab_size,
        "docs_with_annotation": sum(1 for n in per_doc if n > 0),
        "annotations_per_doc_histogram": hist,
        "top_concepts": [{"pref": label_of[k], "count": n, "n_docs": len(concept_docs[k])}
                         for k, n in concepts.most_common(15)],
        "levels": levels,
        "candidates_by_length": [{"label": lab, "count": length_bins.get(lab, 0)}
                                 for lab in ("1 mot", "2 mots", "3 mots", "4 mots et plus")],
    }


# ── Partie 3 : thèmes ────────────────────────────────────────────────────────

def compute_topic_report(candidates: list[dict[str, Any]], annotation_results: list[dict[str, Any]],
                         n_topics: int = 0) -> Optional[dict[str, Any]]:
    """Calcule les thèmes et leur couverture ; ajoute topic_id / topic_label /
    topic_coverage aux candidats (dicts) qui entrent dans le modèle. Retourne
    None si le corpus a moins de MIN_SEGMENTS segments."""
    import numpy as np
    from scipy.sparse import csr_matrix
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfTransformer

    kept = [c for c in candidates if (c.get("frequency") or 0) >= MIN_TOPIC_FREQ]
    seg_index: dict[tuple, int] = {}
    rows, cols = [], []
    for col, c in enumerate(kept):
        for occ in c.get("occurrences", []):
            si = seg_index.setdefault((occ.get("doc_id"), occ["start"] // SEGMENT_CHARS), len(seg_index))
            rows.append(si)
            cols.append(col)
    n_seg = len(seg_index)
    if n_seg < MIN_SEGMENTS or not kept:
        return None
    k = min(n_topics or auto_n_topics(n_seg), len(kept))

    counts = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(n_seg, len(kept)))
    counts.sum_duplicates()
    model = NMF(n_components=k, init="nndsvd", random_state=_SEED, max_iter=400)
    w = model.fit_transform(TfidfTransformer().fit_transform(counts))
    h = model.components_
    seg_topic = w.argmax(axis=1)
    cand_topic = h.argmax(axis=0)
    topic_share = np.bincount(seg_topic, minlength=k) / n_seg

    per_seg: list[list[str]] = [[] for _ in range(n_seg)]
    for result in annotation_results:
        doc_id = result.get("id")
        for m in result.get("matches", []):
            si = seg_index.get((doc_id, m["start"] // SEGMENT_CHARS))
            if si is not None:
                per_seg[si].append(m.get("pref") or m.get("found") or "")

    term_total: Counter = Counter()
    term_by_topic: dict[int, Counter] = defaultdict(Counter)
    for si, prefs in enumerate(per_seg):
        for p in prefs:
            term_total[p] += 1
            term_by_topic[int(seg_topic[si])][p] += 1
    specific = {
        t: {p for p, n in term_by_topic[t].items()
            if n >= SPECIFIC_MIN_COUNT and topic_share[t] > 0
            and (n / term_total[p]) / topic_share[t] >= SPECIFIC_LIFT}
        for t in range(k)
    }
    transversal = [p for p, _ in term_total.most_common()
                   if sum(1 for t in range(k) if term_by_topic[t][p] > 0) >= k / 2][:10]

    labels = {t: [kept[j]["term"] for j in np.argsort(-h[t])[:10]] for t in range(k)}
    freq = np.array([c.get("frequency") or 0 for c in kept], dtype=float)
    topics, coverage_of = [], {}
    for t in range(k):
        segs = np.where(seg_topic == t)[0]
        if len(segs) == 0:
            continue
        members = np.where(cand_topic == t)[0]
        cov = sum(1 for s in segs if any(p in specific[t] for p in per_seg[s])) / len(segs)
        coverage_of[t] = cov
        suggestions = {}
        for field, name in LEVELS:
            sel = sorted((j for j in members if kept[j].get(field)), key=lambda j: -freq[j])
            suggestions[name] = [{"term": kept[j]["term"], "frequency": int(freq[j])} for j in sel]
        topics.append({
            "topic": t,
            "label": labels[t],
            "generic": is_generic_topic(float(topic_share[t]), k),
            "segment_share": float(topic_share[t]),
            "coverage": cov,
            "coverage_all_terms": sum(1 for s in segs if per_seg[s]) / len(segs),
            "specific_terms": [{"pref": p, "count": term_by_topic[t][p]}
                               for p in sorted(specific[t], key=lambda p: -term_by_topic[t][p])],
            "suggestions": suggestions,
        })
    topics.sort(key=lambda b: (b["generic"], b["coverage"], -b["segment_share"]))
    generic_ids = {b["topic"] for b in topics if b["generic"]}

    for j, c in enumerate(kept):
        t = int(cand_topic[j])
        if t in coverage_of:
            c["topic_id"] = t
            c["topic_label"] = ", ".join(labels[t][:5])
            c["topic_coverage"] = round(coverage_of[t], 4)
            c["topic_generic"] = t in generic_ids

    return {
        "segment_chars": SEGMENT_CHARS, "n_segments": n_seg, "n_topics": k,
        "specific_lift": SPECIFIC_LIFT, "specific_min_count": SPECIFIC_MIN_COUNT,
        "transversal_terms": [{"pref": p, "count": term_total[p]} for p in transversal],
        "topics": topics,
    }


# ── Rendu HTML ───────────────────────────────────────────────────────────────

_CSS = """
:root {
  color-scheme: light;
  --surface: #fcfcfb; --surface-2: #f3f2ef; --grid: #e4e3df;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7974;
  --accent: #2a78d6;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface: #1a1a19; --surface-2: #242423; --grid: #383835;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #94938b;
    --accent: #3987e5;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface: #1a1a19; --surface-2: #242423; --grid: #383835;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #94938b;
  --accent: #3987e5;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 40px 0 4px; }
h3 { font-size: 14px; margin: 0 0 8px; color: var(--text-secondary); font-weight: 600; }
.note { background: var(--surface-2); border-radius: 8px; padding: 12px 16px; margin-top: 16px; font-size: 14px; }
.note ul { margin: 6px 0; padding-left: 20px; color: var(--text-secondary); }
.note p { font-size: 14px; margin: 6px 0 0; }
p { color: var(--text-secondary); margin: 4px 0 12px; }
.meta { color: var(--text-muted); font-size: 13px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 20px 0 8px; }
.tile { background: var(--surface-2); border-radius: 8px; padding: 12px 14px; }
.tile .k { font-size: 13px; color: var(--text-secondary); }
.tile .v { font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; }
.tile .s { font-size: 12px; color: var(--text-muted); }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 28px; margin-top: 12px; }
.hbar { display: grid; grid-template-columns: minmax(0, 11em) minmax(0, 1fr); column-gap: 10px; align-items: center; }
.hbar .lab { font-size: 13px; color: var(--text-secondary); padding: 3px 0; overflow-wrap: anywhere; }
.track { display: flex; align-items: center; gap: 6px; min-height: 22px; }
.bar { height: 16px; min-width: 2px; border-radius: 0 4px 4px 0; background: var(--accent); flex: 0 0 auto; }
.val { font-size: 12px; color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.cols { display: flex; align-items: flex-end; gap: 2px; height: 140px; border-bottom: 1px solid var(--grid); }
.col { flex: 1 1 0; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; height: 100%; }
.col .bar { width: 70%; max-width: 24px; border-radius: 4px 4px 0 0; min-height: 2px; }
.col .val { margin-bottom: 2px; }
.collabs { display: flex; gap: 2px; }
.collabs span { flex: 1 1 0; text-align: center; font-size: 12px; color: var(--text-muted); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { text-align: left; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--grid); padding: 4px 6px; }
td { border-bottom: 1px solid var(--grid); padding: 4px 6px; color: var(--text-secondary); }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.topics { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) 6em; column-gap: 12px; align-items: center; }
.topics .head { font-size: 12px; color: var(--text-muted); border-bottom: 1px solid var(--grid); padding-bottom: 4px; }
.topics .lab { font-size: 13px; color: var(--text-secondary); padding: 4px 0; overflow-wrap: anywhere; }
.topics .n { font-size: 13px; text-align: right; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.guide { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 28px;
  background: var(--surface-2); border-radius: 8px; padding: 16px 20px; margin-top: 12px; }
.guide ol { margin: 0; padding-left: 20px; }
.guide li { font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.guide li b, .guide dt { color: var(--text-primary); }
.guide dl { margin: 0; font-size: 14px; }
.guide dt { font-weight: 600; margin-top: 8px; }
.guide dt:first-child { margin-top: 0; }
.guide dd { margin: 2px 0 0; color: var(--text-secondary); }
.guide code { font-size: 13px; }
details { border-top: 1px solid var(--grid); padding: 8px 0; }
summary { cursor: pointer; font-weight: 600; font-size: 14px; }
details p { font-size: 14px; }
details p b { color: var(--text-primary); }
#tip { position: fixed; pointer-events: none; background: var(--text-primary); color: var(--surface);
  font-size: 12px; padding: 6px 8px; border-radius: 6px; max-width: 320px; display: none; z-index: 10; }
@media (max-width: 640px) {
  .topics { grid-template-columns: minmax(0, 1fr) 5em; }
  .topics .head:nth-child(2), .topics .track { grid-column: 1 / -1; }
  .topics .head:nth-child(2) { display: none; }
  .hbar { grid-template-columns: minmax(0, 8em) minmax(0, 1fr); }
}
"""

_JS = """
const tip = document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('mousemove', e => {
    tip.textContent = el.dataset.tip; tip.style.display = 'block';
    const x = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
    tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px';
  });
  el.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
});
"""


# Rappel des consignes et du sens des indicateurs — version courte de
# docs/curation_guide.md ; précisions mesurées sur ACTER (2026-09-30), chaque
# liste prise seule. Le chiffre affiché est la précision PAR CANDIDAT (part de
# suggestions justes, ce que voit le curateur) ; la précision par token, pondérée
# par les occurrences, sert aux benchmarks et n'est pas montrée ici.
_GUIDE = """
<div class="guide">
<div><h3>Consignes de relecture</h3>
<ol>
<li><b>Une liste après l'autre</b> : 1, puis 2, puis 3. Ne jamais les mélanger : leur fiabilité est très différente.</li>
<li><b>Dans chaque liste, des plus fréquents aux moins fréquents</b> (colonne <code>frequency</code> du CSV) : le haut de
liste est nettement plus fiable que le bas.</li>
<li><b>Écarter d'abord le bruit évident</b> (en-têtes, ponctuation, fragments de mots coupés) : sur un corpus issu de PDF,
il remonte en tête justement parce qu'il est fréquent.</li>
<li><b>Juger chaque candidat dans son contexte</b> (colonne <code>context</code>) ; liste 1 en revue rapide, listes 2 et 3
une par une, jamais en lot.</li>
<li><b>Un candidat peu fréquent n'est pas rejeté d'office</b> : il demande seulement plus de vérification.</li>
<li><b>Les thèmes peu couverts</b> (en haut du graphique de la section « Couverture par thème ») indiquent où chercher
en priorité — si la zone entre dans le périmètre de la ressource.</li>
</ol>
<p>Consigne complète : <code>docs/curation_guide.md</code>.</p></div>
<div><h3>Ce que signifient les indicateurs</h3>
<dl>
<dt>Liste 1 — embed</dt>
<dd>Ressemble à un terme déjà dans le vocabulaire (similarité ≥ 0,95). La plus fiable : environ une suggestion sur deux
est un bon terme (53 %), quatre sur cinq dans le quart le plus fréquent.</dd>
<dt>Liste 2 — structurel</dt>
<dd>Loin du vocabulaire mais statistiquement fort dans le corpus (forme et fréquence d'un terme). Moins fiable : environ
une suggestion sur quatre (23 %).</dd>
<dt>Liste 3 — spécificité</dt>
<dd>Plus fréquent ici qu'en langue générale. Exploratoire, la plus bruitée : environ une suggestion sur sept (14 %) ;
désactivée par défaut.</dd>
<dt>Ressemble à (<code>nearest_vocab_term</code>)</dt>
<dd>Le terme du vocabulaire le plus proche : aide à juger la suggestion et à la placer dans la hiérarchie.</dd>
<dt>Fréquence, documents (<code>frequency</code>, <code>n_docs</code>)</dt>
<dd>Nombre d'occurrences et de documents. Un terme présent dans un seul document est souvent propre à un auteur.</dd>
<dt>Couverture d'un thème</dt>
<dd>Part des passages du thème contenant un terme propre du vocabulaire. Compare les thèmes entre eux, ce n'est pas un
taux absolu.</dd>
<dt>Scores bruts (<code>score</code>, <code>structural_score</code>, <code>specificity_score</code>)</dt>
<dd>À ne pas lire directement : échelles différentes, non comparables entre elles ni d'un corpus à l'autre.</dd>
</dl></div>
</div>"""


def _e(s: Any) -> str:
    return html.escape(str(s))


def _n(x: Any) -> str:
    return f"{x:,}".replace(",", " ") if isinstance(x, int) else _e(x)


def _hbars(items: list[tuple[str, int, str]]) -> str:
    """Barres horizontales, une seule série : (libellé, valeur, info-bulle)."""
    vmax = max((v for _, v, _ in items), default=1) or 1
    out = []
    for lab, v, tip in items:
        out.append(f'<div class="lab">{_e(lab)}</div><div class="track" data-tip="{_e(tip)}">'
                   f'<div class="bar" style="width:{v / vmax * 85:.2f}%"></div><span class="val">{_n(v)}</span></div>')
    return f'<div class="hbar">{"".join(out)}</div>'


def _columns(items: list[tuple[str, int, str]]) -> str:
    vmax = max((v for _, v, _ in items), default=1) or 1
    cols = "".join(f'<div class="col" data-tip="{_e(tip)}"><span class="val">{_n(v)}</span>'
                   f'<div class="bar" style="height:{v / vmax * 80:.2f}%"></div></div>' for _, v, tip in items)
    labs = "".join(f"<span>{_e(lab)}</span>" for lab, _, _ in items)
    return f'<div class="cols">{cols}</div><div class="collabs">{labs}</div>'


def _tile(key: str, value: str, sub: str = "") -> str:
    return f'<div class="tile"><div class="k">{_e(key)}</div><div class="v">{value}</div><div class="s">{_e(sub)}</div></div>'


def _pct(a: Optional[int], b: Optional[int]) -> str:
    return f"{a / b:.0%}" if a is not None and b else "—"


def render_html(summary: dict[str, Any], topics: Optional[dict[str, Any]], meta: dict[str, Any]) -> str:
    s = summary
    lv = s["levels"]
    l1, l2, l3 = (lv[name]["count"] for _, name in LEVELS)
    vocab = s["vocabulary_size"]
    tiles = "".join([
        _tile("Documents", _n(s["docs"]), f"{_n(s['total_tokens'])} tokens" if s.get("total_tokens") else ""),
        _tile("Candidats extraits", _n(s["n_candidates"]),
              f"{_n(s['in_vocabulary'])} déjà dans le vocabulaire"),
        _tile("Vocabulaire retrouvé", _pct(s["concepts_found"], vocab),
              f"{_n(s['concepts_found'])} concepts sur {_n(vocab) if vocab else '?'}"),
        _tile("Documents annotés", _pct(s["docs_with_annotation"], s["docs"]),
              f"{_n(s['annotations_total'])} annotations du vocabulaire"),
        _tile("Suggestions", _n(l1 + l2 + l3), f"listes 1 / 2 / 3 : {_n(l1)} / {_n(l2)} / {_n(l3)}"),
    ])

    # Partie 2 — annotation
    top_concepts = _hbars([(c["pref"], c["count"], f"{c['pref']} : {c['count']} annotations dans {c['n_docs']} documents")
                           for c in s["top_concepts"]])
    hist = _columns([(h["label"], h["count"], f"{h['count']} documents avec {h['label']} annotation(s)")
                     for h in s["annotations_per_doc_histogram"]])
    never = (f"{1 - s['concepts_found'] / vocab:.0%} des concepts du vocabulaire n'apparaissent jamais dans ce corpus."
             if vocab else "")

    # Partie 2 — extraction
    funnel = _hbars([
        ("Candidats extraits", s["n_candidates"], "Groupes nominaux retenus par l'extraction"),
        ("Absents du vocabulaire", s["absent"], "Candidats que l'annotateur ne reconnaît pas"),
        ("Suggestions (listes 1+2+3)", l1 + l2 + l3, "Candidats proposés au curateur"),
        ("Liste 1 — embed", l1, "Proches d'un terme du vocabulaire — à relire en premier"),
        ("Liste 2 — structurel", l2, "Statistiquement forts dans le corpus"),
        ("Liste 3 — spécificité", l3, "Rares en langue générale — exploratoire"),
    ])
    lengths = _hbars([(b["label"], b["count"], f"{b['count']} candidats de {b['label']}")
                      for b in s["candidates_by_length"]])
    tables = []
    for _, name in LEVELS:
        top = lv[name]["top"]
        if not top:
            continue
        near = name.startswith("Liste 1")
        head = "<tr><th>Terme</th><th class='n'>Fréq.</th><th class='n'>Docs</th>" + \
               ("<th>Ressemble à</th>" if near else "") + "</tr>"
        rows = "".join(
            f"<tr><td>{_e(t['term'])}</td><td class='n'>{_n(t['frequency'])}</td><td class='n'>{_n(t['n_docs'])}</td>"
            + (f"<td>{_e(t['nearest_vocab_term'] or '')}</td>" if near else "") + "</tr>" for t in top)
        tables.append(f"<div><h3>{_e(name)} — {_n(lv[name]['count'])} suggestions</h3><table>{head}{rows}</table></div>")

    # Partie 3 — thèmes
    if topics is None:
        topic_html = ("<p>Corpus trop court pour former des thèmes (moins de "
                      f"{MIN_SEGMENTS} passages de {SEGMENT_CHARS} caractères).</p>")
    else:
        all_topics = topics["topics"]
        for t in all_topics:  # rapports calculés avant le champ "generic"
            t.setdefault("generic", is_generic_topic(t["segment_share"], topics["n_topics"]))
        ranked = [t for t in all_topics if not t["generic"]]
        generic = [t for t in all_topics if t["generic"]]
        cmax = max((t["coverage"] for t in ranked), default=0.0)
        scale = max(0.05, -(-round(cmax * 100, 6) // 5) * 5 / 100)
        rows = []
        for t in ranked:
            n_sugg = sum(len(v) for v in t["suggestions"].values())
            rows.append(
                f'<div class="lab">{_e(", ".join(t["label"][:5]))}</div>'
                f'<div class="track" data-tip="{t["coverage"]:.0%} des passages de ce thème contiennent un terme '
                f'propre du vocabulaire · {t["segment_share"]:.1%} du corpus">'
                f'<div class="bar" style="width:{min(t["coverage"] / scale, 1) * 85:.2f}%"></div>'
                f'<span class="val">{t["coverage"]:.0%}</span></div>'
                f'<div class="n">{_n(n_sugg)}</div>')
        details = []
        for t in all_topics:
            spec = ", ".join(f'{_e(x["pref"])} ({x["count"]})' for x in t["specific_terms"][:12]) or "aucun"
            sugg = "".join(f'<p><b>{_e(name)}</b> ({len(items)}) : '
                           + (", ".join(f'{_e(i["term"])} ({i["frequency"]})' for i in items[:15]) or "—") + "</p>"
                           for name, items in t["suggestions"].items())
            tag = " — thème générique" if t["generic"] else ""
            details.append(f'<details><summary>{_e(", ".join(t["label"][:5]))} — {t["coverage"]:.0%}{tag}</summary>'
                           f'<p><b>Étiquette complète</b> : {_e(", ".join(t["label"]))}</p>'
                           f'<p><b>Termes propres du vocabulaire</b> : {spec}</p>{sugg}</details>')
        transversal = ", ".join(f'{_e(x["pref"])} ({x["count"]})' for x in topics["transversal_terms"]) or "aucun"
        generic_html = ""
        if generic:
            items = "".join(
                f'<li><b>{_e(", ".join(t["label"][:6]))}</b> — {t["segment_share"]:.0%} du corpus, '
                f'{_n(sum(len(v) for v in t["suggestions"].values()))} suggestions</li>' for t in generic)
            generic_html = f"""
<div class="note"><b>Thème{'s' if len(generic) > 1 else ''} générique{'s' if len(generic) > 1 else ''}, hors classement</b>
<ul>{items}</ul>
<p>Un thème qui pèse beaucoup plus que la moyenne ({1 / topics['n_topics']:.1%} du corpus par thème) regroupe le
discours général des articles (« compte », « exemple », « mise en place »…) plutôt qu'un sujet. Sa couverture est
basse par construction : ce n'est pas une zone où chercher des termes manquants. Ses suggestions restent à relire,
comme celles des autres listes.</p></div>"""
        topic_html = f"""
<p>Le corpus est découpé automatiquement en {topics['n_topics']} thèmes. Les thèmes du haut sont les moins
couverts par le vocabulaire : zones où chercher des termes à ajouter, ou thèmes de bruit à écarter.</p>
<div class="topics">
<div class="head">Thème (5 candidats les plus représentatifs)</div>
<div class="head">Passages avec un terme propre du vocabulaire · échelle 0–{scale:.0%}</div>
<div class="head" style="text-align:right">Suggestions</div>
{''.join(rows)}
</div>
{generic_html}
<details><summary>Comment lire ce graphique</summary>
<p>Un <b>terme propre</b> est un terme du vocabulaire surreprésenté dans le thème (au moins
{topics['specific_lift']:g} fois sa part attendue). Les termes présents partout ne comptent que là où ils sont
surreprésentés : {transversal}.</p>
<p>Ce n'est pas un taux de couverture absolu : comparez les thèmes entre eux. Le découpage varie d'un run à
l'autre et les étiquettes mêlent souvent des mots génériques. Les thèmes de bruit (en-têtes de revue,
remerciements, adresses, noms d'auteurs, texte mal extrait) se reconnaissent à leur étiquette.
Consigne complète : docs/curation_guide.md.</p>
</details>
<details><summary>Détail par thème ({len(topics['topics'])})</summary>{''.join(details)}</details>"""

    title = f"Rapport d'analyse — {meta.get('dict_name', 'vocabulaire')}"
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title><style>{_CSS}</style></head>
<body><main>
<h1>{_e(title)}</h1>
<div class="meta">Corpus {_e(meta.get('corpus', ''))} · extracteur {_e(meta.get('extractor', ''))}</div>
<div class="tiles">{tiles}</div>

<h2>Mode d'emploi</h2>
{_GUIDE}

<h2>Ce que le vocabulaire couvre déjà</h2>
<p>{never}</p>
<div class="grid2">
<div><h3>Termes du vocabulaire les plus annotés</h3>{top_concepts}</div>
<div><h3>Documents selon leur nombre d'annotations</h3>{hist}</div>
</div>

<h2>Ce qui pourrait manquer</h2>
<p>Des candidats extraits du corpus aux suggestions proposées au curateur. Dans chaque liste, commencer par
les plus fréquents.</p>
<div class="grid2">
<div><h3>Des candidats aux suggestions</h3>{funnel}</div>
<div><h3>Candidats par longueur</h3>{lengths}</div>
</div>
<div class="grid2">{''.join(tables)}</div>

<h2>Couverture par thème <span class="meta">(expérimental)</span></h2>
{topic_html}
</main><div id="tip"></div><script>{_JS}</script></body></html>
"""


def write_report(path: str, candidates: list[dict[str, Any]], annotation_results: list[dict[str, Any]],
                 payload: dict[str, Any], meta: dict[str, Any], dict_path: Optional[str] = None,
                 n_topics: int = 0) -> dict[str, Any]:
    """Calcule et écrit le rapport (HTML + JSON à côté). Ajoute aux candidats
    les champs topic_id / topic_label / topic_coverage — à appeler AVANT
    d'écrire la sortie JSON/CSV des candidats pour qu'ils y figurent."""
    summary = compute_summary(candidates, annotation_results, payload, count_vocabulary_concepts(dict_path))
    topics = compute_topic_report(candidates, annotation_results, n_topics)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(summary, topics, meta))
    json_path = path.rsplit(".", 1)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "topics": topics}, f, ensure_ascii=False, indent=2)
    return {"summary": summary, "topics": topics}
