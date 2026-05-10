#!/usr/bin/env python3
import argparse, html, json, subprocess, sys
from pathlib import Path

def concept_url(m, base_url):
    for key in ("uri", "id", "ark"):
        value = str(m.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value

    cid = str(m.get("id") or m.get("ark") or m.get("uri") or "").strip()
    if not cid:
        return "#"
    if cid.startswith("ark:/"):
        return "https://www.loterre.fr/" + cid
    return base_url.rstrip("/") + "/" + cid.lstrip("/")

def ann_key(m):
    start = "" if m.get("start") is None else str(m.get("start"))
    end = "" if m.get("end") is None else str(m.get("end"))
    concept = str(m.get("id") or m.get("ark") or m.get("uri") or m.get("pref") or "").strip().lower()
    found = str(m.get("found") or m.get("label") or "").strip().lower()
    pref = str(m.get("pref") or m.get("label") or "").strip().lower()
    if start and end:
        return ("span", start, end, concept or pref or found)
    return ("surface", found, pref, concept)

def ann_span(m, text):
    try:
        s, e = int(m["start"]), int(m["end"])
    except Exception:
        s, e = None, None
    if s is not None and e is not None and 0 <= s < e <= len(text):
        return (s, e)

    # Fallback when gold/predicted rows do not carry character offsets:
    # try to locate surface form in source text.
    needle = str(m.get("found") or m.get("label") or m.get("pref") or "").strip()
    if not needle:
        return None
    # Known limitation: when the same surface appears multiple times without offsets,
    # we keep the first occurrence found in the source text.

    lo_text = text.lower()
    lo_needle = needle.lower()
    idx = lo_text.find(lo_needle)
    if idx < 0:
        return None
    return (idx, idx + len(needle))

def read_json_or_jsonl(path):
    p = Path(path)
    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return {"results": []}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"results": obj}
    except Exception:
        pass
    rows = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return {"results": rows}

def classify(text, predicted, expected):
    pkeys = {ann_key(m) for m in predicted}
    ekeys = {ann_key(m) for m in expected}
    anns = []
    for m in expected:
        sp = ann_span(m, text)
        if sp:
            anns.append({"start": sp[0], "end": sp[1], "status": "both" if ann_key(m) in pkeys else "expected_only", "source": "expected", "match": m})
    for m in predicted:
        sp = ann_span(m, text)
        if sp and ann_key(m) not in ekeys:
            anns.append({"start": sp[0], "end": sp[1], "status": "predicted_only", "source": "predicted", "match": m})
    pr = {"both": 0, "expected_only": 1, "predicted_only": 2}
    anns.sort(key=lambda a: (a["start"], pr[a["status"]], -(a["end"] - a["start"])))
    kept, occupied = [], []
    for a in anns:
        s, e = a["start"], a["end"]
        if any(not (e <= os_ or s >= oe) for os_, oe in occupied):
            continue
        kept.append(a); occupied.append((s, e))
    return sorted(kept, key=lambda a: a["start"])

def render_mark(text, ann, base_url):
    m = ann["match"]; s, e = ann["start"], ann["end"]
    surf = html.escape(text[s:e])
    pref = html.escape(str(m.get("pref") or m.get("label") or m.get("found") or ""))
    cid = html.escape(str(m.get("id") or m.get("ark") or m.get("uri") or ""))
    rule = html.escape(str(m.get("rule") or ""))
    score = html.escape(str(m.get("score") if m.get("score") is not None else ""))
    url = html.escape(concept_url(m, base_url), quote=True)
    tip = " | ".join(x for x in ["statut=" + ann["status"], "source=" + ann["source"], pref, cid, ("rule=" + rule) if rule else "", ("score=" + score) if score else ""] if x)
    return '<a class="term {cls}" href="{url}" target="_blank" rel="noopener noreferrer" title="{tip}">{surf}</a>'.format(cls=ann["status"], url=url, tip=html.escape(tip, quote=True), surf=surf)

def render_text(text, predicted, expected, base_url):
    parts, cur = [], 0
    for a in classify(text, predicted, expected):
        parts.append(html.escape(text[cur:a["start"]]))
        parts.append(render_mark(text, a, base_url))
        cur = a["end"]
    parts.append(html.escape(text[cur:]))
    return "".join(parts)

def table_row(m, base_url, kind):
    found = html.escape(str(m.get("found", "")))
    pref = html.escape(str(m.get("pref") or m.get("label") or ""))
    cid = html.escape(str(m.get("id") or m.get("ark") or m.get("uri") or ""))
    start = html.escape(str(m.get("start") if m.get("start") is not None else ""))
    end = html.escape(str(m.get("end") if m.get("end") is not None else ""))
    rule = html.escape(str(m.get("rule") or ""))
    score = html.escape(str(m.get("score") if m.get("score") is not None else ""))
    url = html.escape(concept_url(m, base_url), quote=True)
    return '<tr><td>{}</td><td>{}</td><td>{}</td><td><a href="{}" target="_blank">{}</a></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(kind, found, pref, url, cid, start, end, rule, score)

def counts(predicted, expected):
    p, e = {ann_key(m) for m in predicted}, {ann_key(m) for m in expected}
    return {"both": len(p & e), "expected_only": len(e - p), "predicted_only": len(p - e)}

def render_doc(d, base_url):
    doc_id = html.escape(str(d.get("id", "")))
    text = d.get("text") or d.get("value") or ""
    predicted = d.get("matches", []) or []
    expected = d.get("expected_matches", []) or []
    c = counts(predicted, expected)
    annotated = render_text(text, predicted, expected, base_url)
    rows = "\n".join([table_row(m, base_url, "expected") for m in expected] + [table_row(m, base_url, "predicted") for m in predicted])
    if not rows:
        rows = '<tr><td colspan="8">Aucun terme attendu ou prédit</td></tr>'
    stats = "prédits: {} - attendus: {} - attendus+prédits: {} - attendus non prédits: {} - prédits non attendus: {}".format(len(predicted), len(expected), c["both"], c["expected_only"], c["predicted_only"])
    return '<section class="doc"><h2>Document {}</h2><div class="stats">{}</div><div class="legend"><span><span class="swatch both"></span> attendu + prédit</span><span><span class="swatch expected_only"></span> attendu mais non prédit</span><span><span class="swatch predicted_only"></span> prédit mais non attendu</span></div><div class="text">{}</div><details><summary>Voir le détail des termes</summary><table><thead><tr><th>Type</th><th>Terme</th><th>Concept</th><th>ID / ARK</th><th>Start</th><th>End</th><th>Règle</th><th>Score</th></tr></thead><tbody>{}</tbody></table></details></section>'.format(doc_id, stats, annotated, rows)

def load_results(payload):
    if "results" in payload:
        return payload.get("results") or []
    if "documents" in payload:
        return payload.get("documents") or []
    if "id" in payload:
        return [payload]
    return []

def merge_gold(results, gold_path):
    if not gold_path:
        return results
    gold_payload = read_json_or_jsonl(gold_path)
    gold_rows = load_results(gold_payload)
    gold = {str(d.get("id")): d for d in gold_rows}
    out = []
    for d in results:
        d2 = dict(d)
        g = gold.get(str(d.get("id")))
        if g:
            d2.setdefault("value", g.get("value", d.get("text", d.get("value", ""))))
            d2["expected_matches"] = g.get("expected_matches", [])
        out.append(d2)
    return out

def css():
    return "body{margin:0;padding:2rem;background:#f7f7f8;color:#1f2937;font-family:system-ui,sans-serif;line-height:1.6}.doc{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:1.25rem;margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.04)}.text{white-space:pre-wrap;background:#fafafa;padding:1rem;border-radius:10px;border:1px solid #e5e7eb}a.term{color:#111827;text-decoration:none;padding:0 .15rem;border-radius:4px}a.term.both{background:#d9fbe3;border-bottom:2px solid #22c55e}a.term.expected_only{background:#dbeafe;border-bottom:2px solid #60a5fa}a.term.predicted_only{background:#ffedd5;border-bottom:2px solid #fb923c}.legend{display:flex;gap:1rem;flex-wrap:wrap;margin:.75rem 0 1rem 0;font-size:.9rem}.swatch{width:1rem;height:1rem;display:inline-block;border-radius:4px;border:1px solid #d1d5db;margin-right:.25rem;vertical-align:middle}.swatch.both{background:#d9fbe3;border-color:#22c55e}.swatch.expected_only{background:#dbeafe;border-color:#60a5fa}.swatch.predicted_only{background:#ffedd5;border-color:#fb923c}table{width:100%;border-collapse:collapse;margin-top:.75rem;font-size:.9rem}th,td{border:1px solid #e5e7eb;padding:.45rem;vertical-align:top}th{background:#f3f4f6;text-align:left}.summary,.stats{color:#6b7280}"

def render_page(payload, base_url, title, gold_path=None):
    results = merge_gold(load_results(payload), gold_path)
    total_p = sum(len(d.get("matches", []) or []) for d in results)
    total_e = sum(len(d.get("expected_matches", []) or []) for d in results)
    docs = "\n".join(render_doc(d, base_url) for d in results)
    return '<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{}</title><style>{}</style></head><body><header><h1>{}</h1><div class="summary">{} document(s), {} terme(s) prédit(s), {} terme(s) attendu(s)</div></header>{}</body></html>'.format(html.escape(title), css(), html.escape(title), len(results), total_p, total_e, docs)

def render_file(input_path, out_path, base_url, title, gold_path=None):
    payload = read_json_or_jsonl(input_path)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_page(payload, base_url, title, gold_path), encoding="utf-8")

def find_file(root, code, lang):
    root = Path(root)
    for c in [root/f"{code}_{lang}.jsonl", root/f"{code}_{lang}.json", root/f"{code}.jsonl", root/f"{code}.json"]:
        if c.exists(): return c
    for pat in [f"*{code}*{lang}*.jsonl", f"*{code}*{lang}*.json", f"*{code}*.jsonl", f"*{code}*.json"]:
        hits = sorted(root.glob(pat))
        if hits: return hits[0]
    return None

def find_gold(root, code, lang, dict_id):
    root = Path(root)
    if not root.exists(): return None
    for c in [root/f"gold_{dict_id}.jsonl", root/f"{dict_id}.jsonl", root/f"gold_{code}_{lang}.jsonl", root/f"gold_{code}.jsonl"]:
        if c.exists(): return c
    for pat in [f"*{dict_id}*.jsonl", f"*{code}*{lang}*.jsonl", f"*{code}*.jsonl"]:
        hits = sorted(root.glob(pat))
        if hits: return hits[0]
    return None

def run_engine(cli, dict_id, text_file, json_out, extra):
    Path(json_out).parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(cli), "--dict-id", dict_id, "--text", str(text_file), "--silent"] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("Engine failed for {}\n{}".format(dict_id, proc.stderr))
    Path(json_out).write_text(proc.stdout, encoding="utf-8")

def batch(args):
    en = args.en_codes.split(",") if args.en_codes else ["P66","9SD","8HQ","B9M","27X","BVM","QX8","3JP","JVR"]
    fr = args.fr_codes.split(",") if args.fr_codes else ["P66","9SD","8HQ","B9M","27X","BVM","QX8"]
    jobs = [(c,"en",f"{c}_en") for c in en] + [(c,"fr",f"{c}_fr") for c in fr]
    outdir = Path(args.outdir); summary = []
    for code, lang, dict_id in jobs:
        print("== {} ==".format(dict_id))
        text_file = find_file(args.text_root, code, lang)
        if not text_file:
            summary.append({"dict_id": dict_id, "status": "missing_text"}); continue
        gold = find_gold(args.gold_root, code, lang, dict_id) if args.gold_root else None
        json_out = outdir/"json"/f"{dict_id}.json"; html_out = outdir/"html"/f"{dict_id}.html"
        try:
            run_engine(Path(args.cli), dict_id, text_file, json_out, args.engine_arg or [])
            render_file(json_out, html_out, args.base_url, "Annotation Loterre - {}".format(dict_id), str(gold) if gold else None)
            summary.append({"dict_id": dict_id, "status": "ok", "text": str(text_file), "gold": str(gold) if gold else "", "json": str(json_out), "html": str(html_out)})
        except Exception as e:
            summary.append({"dict_id": dict_id, "status": "error", "message": str(e)})
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir/"html_generation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    p = argparse.ArgumentParser(description="Render predicted and expected Loterre matches as HTML")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("render")
    r.add_argument("--input", required=True); r.add_argument("--out", required=True); r.add_argument("--gold")
    r.add_argument("--title", default="Annotation Loterre"); r.add_argument("--base-url", default="https://www.loterre.fr/ark:/")
    b = sub.add_parser("batch")
    b.add_argument("--cli", default="./src/loterre_cli.py"); b.add_argument("--text-root", default="../examples/texts"); b.add_argument("--gold-root", default="./gold"); b.add_argument("--outdir", default="./html_outputs")
    b.add_argument("--base-url", default="https://www.loterre.fr/ark:/"); b.add_argument("--en-codes", default="P66,9SD,8HQ,B9M,27X,BVM,QX8,3JP,JVR"); b.add_argument("--fr-codes", default="P66,9SD,8HQ,B9M,27X,BVM,QX8"); b.add_argument("--engine-arg", action="append", default=[])
    p.add_argument("--input"); p.add_argument("--out"); p.add_argument("--gold"); p.add_argument("--title", default="Annotation Loterre"); p.add_argument("--base-url", default="https://www.loterre.fr/ark:/")
    args = p.parse_args()
    if args.cmd == "render":
        render_file(args.input, args.out, args.base_url, args.title, args.gold)
    elif args.cmd == "batch":
        batch(args)
    elif args.input and args.out:
        render_file(args.input, args.out, args.base_url, args.title, args.gold)
    else:
        p.print_help(); raise SystemExit(2)

if __name__ == "__main__":
    main()
