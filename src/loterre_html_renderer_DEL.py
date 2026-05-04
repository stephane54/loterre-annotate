#!/usr/bin/env python3
from __future__ import annotations
import argparse, html, json, subprocess, sys
from pathlib import Path

DEFAULT_EN_CODES = ["P66","9SD","8HQ","B9M","27X","BVM","QX8","3JP","JVR"]
DEFAULT_FR_CODES = ["P66","9SD","8HQ","B9M","27X","BVM","QX8"]

def concept_url(m, base_url):
    uri = str(m.get("uri") or "")
    if uri.startswith(("http://","https://")):
        return uri
    cid = str(m.get("id") or m.get("ark") or m.get("uri") or "").strip()
    return "#" if not cid else base_url.rstrip("/") + "/" + cid

def render_text(text, matches, base_url):
    spans = []
    for m in matches:
        try:
            s, e = int(m["start"]), int(m["end"])
        except Exception:
            continue
        if 0 <= s < e <= len(text):
            spans.append((s,e,m))
    spans.sort(key=lambda x: (x[0], -(x[1]-x[0])))
    keep, last = [], -1
    for s,e,m in spans:
        if s >= last:
            keep.append((s,e,m))
            last = e
    parts, cur = [], 0
    for s,e,m in keep:
        parts.append(html.escape(text[cur:s]))
        surf = html.escape(text[s:e])
        pref = html.escape(str(m.get("pref") or m.get("label") or m.get("found") or ""))
        cid = html.escape(str(m.get("id") or m.get("ark") or m.get("uri") or ""))
        rule = html.escape(str(m.get("rule") or ""))
        score = html.escape(str(m.get("score") if m.get("score") is not None else ""))
        url = html.escape(concept_url(m, base_url), quote=True)
        tip = " | ".join(x for x in [pref,cid,f"rule={rule}" if rule else "",f"score={score}" if score else ""] if x)
        parts.append(f'<a class="term" href="{url}" target="_blank" rel="noopener noreferrer" title="{html.escape(tip, quote=True)}">{surf}</a>')
        cur = e
    parts.append(html.escape(text[cur:]))
    return "".join(parts)

def render_doc(d, base_url):
    doc_id = html.escape(str(d.get("id","")))
    text = d.get("text") or d.get("value") or ""
    matches = d.get("matches", [])
    annotated = render_text(text, matches, base_url)
    rows = []
    for m in matches:
        found = html.escape(str(m.get("found","")))
        pref = html.escape(str(m.get("pref") or m.get("label") or ""))
        cid = html.escape(str(m.get("id") or m.get("ark") or m.get("uri") or ""))
        rule = html.escape(str(m.get("rule") or ""))
        score = html.escape(str(m.get("score") if m.get("score") is not None else ""))
        url = html.escape(concept_url(m, base_url), quote=True)
        rows.append(f'<tr><td>{found}</td><td>{pref}</td><td><a href="{url}" target="_blank">{cid}</a></td><td>{rule}</td><td>{score}</td></tr>')
    table = "\\n".join(rows) if rows else '<tr><td colspan="5">Aucun terme retrouvé</td></tr>'
    return f'''<section class="doc">
<h2>Document {doc_id}</h2><div class="stats">{len(matches)} match(es)</div>
<div class="text">{annotated}</div>
<details><summary>Voir les termes retrouvés</summary><table>
<thead><tr><th>Terme trouvé</th><th>Concept</th><th>ID / ARK</th><th>Règle</th><th>Score</th></tr></thead>
<tbody>{table}</tbody></table></details></section>'''

def render_page(payload, base_url, title):
    results = payload.get("results") or payload.get("documents") or []
    total = sum(len(d.get("matches", [])) for d in results)
    docs = "\\n".join(render_doc(d, base_url) for d in results)
    css = '''
body{margin:0;padding:2rem;background:#f7f7f8;color:#1f2937;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6}
.doc{background:white;border:1px solid #e5e7eb;border-radius:14px;padding:1.25rem;margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.text{white-space:pre-wrap;background:#fafafa;padding:1rem;border-radius:10px;border:1px solid #e5e7eb}
a.term{background:#fff3a3;border-bottom:2px solid #f59e0b;color:#111827;text-decoration:none;padding:0 .15rem;border-radius:4px}
a.term:hover{background:#fde68a}
table{width:100%;border-collapse:collapse;margin-top:.75rem;font-size:.9rem}
th,td{border:1px solid #e5e7eb;padding:.45rem;vertical-align:top}
th{background:#f3f4f6;text-align:left}
.summary,.stats{color:#6b7280}
'''
    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{css}</style></head><body><header><h1>{html.escape(title)}</h1><div class="summary">{len(results)} document(s), {total} terme(s) retrouvé(s)</div></header>{docs}</body></html>'''

def render_json(input_path, out_path, base_url, title):
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_page(payload, base_url, title), encoding="utf-8")

def find_text(text_root, code, lang):
    root = Path(text_root)
    candidates = [root/f"{code}_{lang}.jsonl", root/f"{code}_{lang}.json", root/f"{code}.jsonl", root/f"{code}.json"]
    for c in candidates:
        if c.exists():
            return c
    for pat in [f"*{code}*{lang}*.jsonl", f"*{code}*{lang}*.json", f"*{code}*.jsonl", f"*{code}*.json"]:
        hits = sorted(root.glob(pat))
        if hits:
            return hits[0]
    return None

def run_engine(cli, dict_id, text_path, json_out, extra):
    Path(json_out).parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(cli), "--dict-id", dict_id, "--text", str(text_path), "--silent"] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Engine failed for {dict_id}\\nSTDERR:\\n{proc.stderr}")
    Path(json_out).write_text(proc.stdout, encoding="utf-8")

def batch(args):
    en_codes = args.en_codes.split(",") if args.en_codes else DEFAULT_EN_CODES
    fr_codes = args.fr_codes.split(",") if args.fr_codes else DEFAULT_FR_CODES
    jobs = [(c,"en",f"{c}_en") for c in en_codes] + [(c,"fr",f"{c}_fr") for c in fr_codes]
    outdir = Path(args.outdir)
    report = []
    for code, lang, dict_id in jobs:
        print(f"== {dict_id} ==")
        text_path = find_text(args.text_root, code, lang)
        if not text_path:
            print(f"WARNING: missing text for {dict_id}")
            report.append({"dict_id":dict_id,"code":code,"lang":lang,"status":"missing_text"})
            continue
        json_out = outdir/"json"/f"{dict_id}.json"
        html_out = outdir/"html"/f"{dict_id}.html"
        try:
            run_engine(Path(args.cli), dict_id, text_path, json_out, args.engine_arg or [])
            render_json(json_out, html_out, args.base_url, f"Annotation Loterre — {dict_id}")
            report.append({"dict_id":dict_id,"code":code,"lang":lang,"status":"ok","text":str(text_path),"json":str(json_out),"html":str(html_out)})
            print(f"HTML: {html_out}")
        except Exception as e:
            print(f"ERROR: {e}")
            report.append({"dict_id":dict_id,"code":code,"lang":lang,"status":"error","text":str(text_path),"message":str(e)})
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir/"html_generation_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary: {outdir/'html_generation_summary.json'}")

def main():
    p = argparse.ArgumentParser(description="Render Loterre JSON to clickable HTML, or run batch generation.")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("render")
    r.add_argument("--input", required=True); r.add_argument("--out", required=True); r.add_argument("--title", default="Annotation Loterre"); r.add_argument("--base-url", default="https://www.loterre.fr/ark:/")
    b = sub.add_parser("batch")
    b.add_argument("--cli", default="./src/loterre_cli.py"); b.add_argument("--text-root", default="examples/texts"); b.add_argument("--outdir", default="./html_outputs")
    b.add_argument("--base-url", default="https://www.loterre.fr/ark:/"); b.add_argument("--en-codes", default=",".join(DEFAULT_EN_CODES)); b.add_argument("--fr-codes", default=",".join(DEFAULT_FR_CODES))
    b.add_argument("--engine-arg", action="append", default=[])
    p.add_argument("--input"); p.add_argument("--out"); p.add_argument("--title", default="Annotation Loterre"); p.add_argument("--base-url", default="https://www.loterre.fr/ark:/")
    args = p.parse_args()
    if args.cmd == "render":
        render_json(args.input, args.out, args.base_url, args.title)
    elif args.cmd == "batch":
        batch(args)
    elif args.input and args.out:
        render_json(args.input, args.out, args.base_url, args.title)
    else:
        p.print_help(); raise SystemExit(2)

if __name__ == "__main__":
    main()
