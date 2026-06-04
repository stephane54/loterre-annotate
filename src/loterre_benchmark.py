#!/usr/bin/env python3
"""Benchmark local v9 engine vs production API against gold corpus.

Runs both engines on every gold JSONL file found in TEXT_ROOT, renders
per-vocabulary HTML annotations, and writes a side-by-side summary.

Usage
-----
    python3 src/loterre_benchmark.py \\
        --text-root data/texts \\
        --out-dir   benchmark_results \\
        [--cli      src/loterre_cli.py] \\
        [--renderer src/loterre_html_renderer.py] \\
        [--api-url  https://terms-tools.services.istex.fr/v1/{lang}/terms-matcher/json-standoff/annotate] \\
        [--vocabs   P66,27X,9SD]   # subset; default = all found in TEXT_ROOT \\
        [--skip-local]             # skip local engine \\
        [--skip-api]               # skip API calls \\
        [--batch-size 4]           # docs per API call \\
        [--base-url https://www.loterre.fr/ark:/]

Output layout
-------------
    OUT_DIR/
      local/json/<vocab>_en.json
      local/html/<vocab>_en.html
      api/json/<vocab>_en.json
      api/html/<vocab>_en.html
      summary.tsv
      summary.html
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, time
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_DEFAULT = (
    "https://terms-tools.services.istex.fr"
    "/v1/{lang}/terms-matcher/json-standoff/annotate"
)

# ── helpers ──────────────────────────────────────────────────────────────────

def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json_payload(path: str | Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8").strip()
    if not raw:
        return {"results": []}
    obj = json.loads(raw)
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return {"results": obj}
    return {"results": []}


# ── stats ─────────────────────────────────────────────────────────────────────

def ann_key(m: dict) -> str:
    return str(m.get("pref") or m.get("label") or m.get("found") or "").strip().lower()


def compute_counts(predicted: list, expected: list) -> dict:
    pc = Counter(ann_key(m) for m in predicted)
    ec = Counter(ann_key(m) for m in expected)
    both = sum(min(pc[k], ec[k]) for k in ec)
    exp_only = sum(max(0, ec[k] - pc[k]) for k in ec)
    pred_only = sum(max(0, pc[k] - ec[k]) for k in pc)
    return {"both": both, "expected_only": exp_only, "predicted_only": pred_only}


def aggregate_stats(json_path: Path, gold_path: Path) -> dict:
    """Return {p, a, b, eo, po, recall, precision, f1} for one vocab."""
    payload = read_json_payload(json_path)
    results = payload.get("results") or payload.get("documents") or []
    gold_rows = read_jsonl(gold_path)
    gold_map = {str(r["id"]): r for r in gold_rows}

    tot_p = tot_a = tot_b = tot_eo = tot_po = 0
    for d in results:
        g = gold_map.get(str(d.get("id")), {})
        predicted = d.get("matches", []) or []
        expected = g.get("expected_matches", []) or []
        c = compute_counts(predicted, expected)
        tot_p += len(predicted)
        tot_a += len(expected)
        tot_b += c["both"]
        tot_eo += c["expected_only"]
        tot_po += c["predicted_only"]

    recall = 100 * tot_b / tot_a if tot_a else 0.0
    prec   = 100 * tot_b / tot_p if tot_p else 0.0
    f1     = 2 * recall * prec / (recall + prec) if (recall + prec) else 0.0
    return dict(p=tot_p, a=tot_a, b=tot_b, eo=tot_eo, po=tot_po,
                recall=recall, precision=prec, f1=f1)


# ── local engine ──────────────────────────────────────────────────────────────

def run_local(cli: Path, dict_id: str, text_file: Path, json_out: Path) -> bool:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(cli), "--dict-id", dict_id,
           "--text", str(text_file), "--silent"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  [local] ERROR for {dict_id}: {proc.stderr[:200]}", file=sys.stderr)
        return False
    json_out.write_text(proc.stdout, encoding="utf-8")
    return True


# ── API engine ────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list[dict]:
    # Decimal numbers like "1.1" kept as one token to match the API's tokenisation.
    return [{"text": m.group(), "start": m.start(), "end": m.end()}
            for m in re.finditer(r"\d+\.\d+|\w+|[^\w\s]", text)]


def api_doc_to_matches(api_doc: dict, text: str) -> list[dict]:
    tokens = tokenize(text)
    matches = []
    for item in api_doc.get("value", []):
        for ann in item.get("matches", []):
            s = int(ann["idx"]["start"])
            e = int(ann["idx"]["end"])
            if s >= len(tokens) or e > len(tokens) or s >= e:
                continue
            matches.append({
                "start": tokens[s]["start"],
                "end":   tokens[e - 1]["end"],
                "found": ann["match"].get("text", ""),
                "pref":  ann["match"].get("term", ""),
                "uri":   ann["match"].get("id", ""),
            })
    return matches


def call_api(api_url: str, vocab: str, lang: str, docs: list[dict], timeout: int = 90) -> list[dict] | None:
    url = f"{api_url.format(lang=lang)}?loterreID={vocab}"
    body = json.dumps(docs).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8").strip()
            if not raw:
                print(f"  [api] empty response for {vocab}/{lang}", file=sys.stderr)
                return []
            return json.loads(raw)
    except HTTPError as e:
        print(f"  [api] HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"  [api] URL error: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [api] parse error for {vocab}/{lang}: {e}", file=sys.stderr)
        return None


def run_api(api_url: str, vocab: str, lang: str, gold_rows: list[dict],
            json_out: Path, batch_size: int = 4, delay: float = 0.5) -> bool:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    input_docs = [{"id": r["id"], "value": r.get("value", r.get("text", ""))}
                  for r in gold_rows]
    results = []
    for i in range(0, len(input_docs), batch_size):
        batch = input_docs[i:i + batch_size]
        print(f"  [api] batch {i//batch_size+1} ({len(batch)} docs)…", end=" ", flush=True)
        t0 = time.perf_counter()
        resp = call_api(api_url, vocab, lang, batch)
        dt = time.perf_counter() - t0
        if resp is None:
            print(f"FAILED ({dt:.1f}s)")
            continue
        print(f"OK ({dt:.1f}s)")
        for api_doc in resp:
            doc_id = str(api_doc.get("id", ""))
            text = next((r.get("value", r.get("text", ""))
                         for r in gold_rows if str(r["id"]) == doc_id), "")
            results.append({"id": api_doc.get("id"),
                            "matches": api_doc_to_matches(api_doc, text)})
        if i + batch_size < len(input_docs):
            time.sleep(delay)

    payload = {"results": results}
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(results) > 0


# ── HTML rendering ─────────────────────────────────────────────────────────────

def render_html(renderer_path: Path, json_file: Path, gold_file: Path,
                html_out: Path, title: str, base_url: str) -> None:
    html_out.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(renderer_path.parent))
    from loterre_html_renderer import render_file
    render_file(str(json_file), str(html_out), base_url, title, str(gold_file))


# ── summary report ────────────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v:.1f}%"

def _delta(a: float, b: float) -> str:
    d = b - a
    return ("+" if d >= 0 else "") + f"{d:.1f}"


def write_summary_tsv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["vocab", "api_r", "api_p", "api_f1", "api_both",
              "v9_r", "v9_p", "v9_f1", "v9_both",
              "delta_r", "delta_p", "delta_f1"]
    lines = ["\t".join(header)]
    for r in rows:
        lines.append("\t".join([
            r["vocab"],
            f"{r['api']['recall']:.1f}", f"{r['api']['precision']:.1f}", f"{r['api']['f1']:.1f}",
            str(r["api"]["b"]),
            f"{r['v9']['recall']:.1f}",  f"{r['v9']['precision']:.1f}",  f"{r['v9']['f1']:.1f}",
            str(r["v9"]["b"]),
            _delta(r["api"]["recall"],    r["v9"]["recall"]),
            _delta(r["api"]["precision"], r["v9"]["precision"]),
            _delta(r["api"]["f1"],        r["v9"]["f1"]),
        ]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bar(pct: float, width: int = 60) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def write_summary_html(rows: list[dict], path: Path, gold_root: Path,
                       local_html_dir: Path, api_html_dir: Path) -> None:
    css = """
body{font-family:system-ui,sans-serif;margin:0;padding:2rem;background:#f7f7f8;color:#1f2937}
h1{margin-bottom:.5rem}
.subtitle{color:#6b7280;margin-bottom:2rem}
table{width:100%;border-collapse:collapse;background:white;border-radius:12px;
      overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06);font-size:.9rem}
th{background:#1e3a5f;color:white;padding:.6rem .8rem;text-align:left}
td{padding:.5rem .8rem;border-bottom:1px solid #e5e7eb;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f0f4ff}
.api{color:#b45309}.v9{color:#166534}.delta{font-weight:600}
.pos{color:#166534}.neg{color:#dc2626}.neu{color:#6b7280}
.bar-wrap{width:120px;display:inline-block;vertical-align:middle;margin-left:.4rem}
.bar-bg{background:#e5e7eb;border-radius:4px;height:8px}
.bar-fill-api{background:#f59e0b;border-radius:4px;height:8px}
.bar-fill-v9{background:#22c55e;border-radius:4px;height:8px}
a{color:#1d4ed8;text-decoration:none}a:hover{text-decoration:underline}
.legend{display:flex;gap:1.5rem;margin-bottom:1rem;font-size:.85rem}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:.3rem;vertical-align:middle}
"""
    def bar_html(pct: float, cls: str) -> str:
        w = round(max(0, min(pct, 100)))
        return (f'<div class="bar-bg"><div class="{cls}" style="width:{w}%"></div></div>')

    def delta_html(a: float, b: float) -> str:
        d = b - a
        sign = "+" if d >= 0 else ""
        cls = "pos" if d > 0.5 else ("neg" if d < -0.5 else "neu")
        return f'<span class="delta {cls}">{sign}{d:.1f}</span>'

    rows_html = ""
    for r in rows:
        v = r["vocab"]
        api, v9 = r["api"], r["v9"]
        local_link = f'<a href="local/html/{v}_en.html">v9</a>'
        api_link   = f'<a href="api/html/{v}_en.html">api</a>'
        rows_html += (
            f"<tr>"
            f"<td><b>{v}</b> {local_link} {api_link}</td>"
            f"<td class='api'>{_pct(api['recall'])}{bar_html(api['recall'],'bar-fill-api')}</td>"
            f"<td class='api'>{_pct(api['precision'])}{bar_html(api['precision'],'bar-fill-api')}</td>"
            f"<td class='api'>{_pct(api['f1'])}{bar_html(api['f1'],'bar-fill-api')}</td>"
            f"<td class='v9'>{_pct(v9['recall'])}{bar_html(v9['recall'],'bar-fill-v9')}</td>"
            f"<td class='v9'>{_pct(v9['precision'])}{bar_html(v9['precision'],'bar-fill-v9')}</td>"
            f"<td class='v9'>{_pct(v9['f1'])}{bar_html(v9['f1'],'bar-fill-v9')}</td>"
            f"<td>{delta_html(api['recall'],    v9['recall'])}</td>"
            f"<td>{delta_html(api['precision'], v9['precision'])}</td>"
            f"<td>{delta_html(api['f1'],        v9['f1'])}</td>"
            f"</tr>\n"
        )

    # totals row
    def tot(key: str, engine: str) -> float:
        num = sum(r[engine]["b"] for r in rows)
        den_a = sum(r[engine]["a"] for r in rows)
        den_p = sum(r[engine]["p"] for r in rows)
        if key == "recall":
            return 100 * num / den_a if den_a else 0
        if key == "precision":
            return 100 * num / den_p if den_p else 0
        r_ = tot("recall", engine); p_ = tot("precision", engine)
        return 2 * r_ * p_ / (r_ + p_) if (r_ + p_) else 0

    for engine, cls in [("api", "api"), ("v9", "v9")]:
        for key in ["recall", "precision", "f1"]:
            pass  # computed inline below

    api_r  = tot("recall",    "api"); api_p  = tot("precision", "api"); api_f1  = tot("f1", "api")
    v9_r   = tot("recall",    "v9");  v9_p   = tot("precision", "v9");  v9_f1   = tot("f1", "v9")
    rows_html += (
        f"<tr style='background:#f3f4f6;font-weight:600'>"
        f"<td>TOTAL</td>"
        f"<td class='api'>{_pct(api_r)}{bar_html(api_r,'bar-fill-api')}</td>"
        f"<td class='api'>{_pct(api_p)}{bar_html(api_p,'bar-fill-api')}</td>"
        f"<td class='api'>{_pct(api_f1)}{bar_html(api_f1,'bar-fill-api')}</td>"
        f"<td class='v9'>{_pct(v9_r)}{bar_html(v9_r,'bar-fill-v9')}</td>"
        f"<td class='v9'>{_pct(v9_p)}{bar_html(v9_p,'bar-fill-v9')}</td>"
        f"<td class='v9'>{_pct(v9_f1)}{bar_html(v9_f1,'bar-fill-v9')}</td>"
        f"<td>{delta_html(api_r, v9_r)}</td>"
        f"<td>{delta_html(api_p, v9_p)}</td>"
        f"<td>{delta_html(api_f1, v9_f1)}</td>"
        f"</tr>\n"
    )

    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Benchmark Loterre — API production vs Dev v9</title>
<style>{css}</style></head><body>
<h1>Benchmark Loterre</h1>
<p class="subtitle">API production vs moteur Dev v9 local — évaluation sur corpus gold</p>
<div class="legend">
  <span><span class="dot" style="background:#f59e0b"></span>API production</span>
  <span><span class="dot" style="background:#22c55e"></span>Dev v9 local</span>
</div>
<table>
<thead><tr>
  <th>Vocabulaire</th>
  <th>API Recall</th><th>API Précision</th><th>API F1</th>
  <th>v9 Recall</th><th>v9 Précision</th><th>v9 F1</th>
  <th>ΔRecall</th><th>ΔPrécision</th><th>ΔF1</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
<p style="color:#6b7280;font-size:.8rem;margin-top:1rem">
  Généré le {time.strftime('%Y-%m-%d %H:%M')} — gold: {gold_root}
</p>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def print_table(rows: list[dict]) -> None:
    hdr = (f"{'Vocab':<6}  {'API R%':>7} {'API P%':>7} {'API F1%':>8}"
           f"  {'v9 R%':>6} {'v9 P%':>7} {'v9 F1%':>8}"
           f"  {'ΔR':>6} {'ΔP':>6} {'ΔF1':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        a, v = r["api"], r["v9"]
        sign = lambda x: ("+" if x >= 0 else "") + f"{x:.1f}"
        print(f"{r['vocab']:<6}  {a['recall']:>6.1f}% {a['precision']:>6.1f}% {a['f1']:>7.1f}%"
              f"  {v['recall']:>5.1f}% {v['precision']:>6.1f}% {v['f1']:>7.1f}%"
              f"  {sign(v['recall']-a['recall']):>6}"
              f" {sign(v['precision']-a['precision']):>6}"
              f" {sign(v['f1']-a['f1']):>7}")
    print("-" * len(hdr))

    def tot(key, engine):
        num = sum(r[engine]["b"] for r in rows)
        den = sum(r[engine]["a"] if key == "recall" else r[engine]["p"] for r in rows)
        if key in ("recall", "precision"):
            return 100 * num / den if den else 0
        rr = tot("recall", engine); pp = tot("precision", engine)
        return 2 * rr * pp / (rr + pp) if (rr + pp) else 0

    ar=tot("recall","api"); ap=tot("precision","api"); af=tot("f1","api")
    vr=tot("recall","v9");  vp=tot("precision","v9");  vf=tot("f1","v9")
    sign = lambda x: ("+" if x >= 0 else "") + f"{x:.1f}"
    print(f"{'TOTAL':<6}  {ar:>6.1f}% {ap:>6.1f}% {af:>7.1f}%"
          f"  {vr:>5.1f}% {vp:>6.1f}% {vf:>7.1f}%"
          f"  {sign(vr-ar):>6} {sign(vp-ap):>6} {sign(vf-af):>7}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    pa = argparse.ArgumentParser(
        description="Benchmark local v9 engine vs production API against gold corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    pa.add_argument("--text-root",  default="data/texts",
                    help="Directory containing gold JSONL files (default: data/texts)")
    pa.add_argument("--out-dir",    default="benchmark_results",
                    help="Output directory (default: benchmark_results)")
    pa.add_argument("--cli",        default="src/loterre_cli.py",
                    help="Path to loterre_cli.py (default: src/loterre_cli.py)")
    pa.add_argument("--renderer",   default="src/loterre_html_renderer.py",
                    help="Path to loterre_html_renderer.py")
    pa.add_argument("--api-url",    default=API_DEFAULT, help="API base URL")
    pa.add_argument("--vocabs",     help="Comma-separated vocab codes (default: all)")
    pa.add_argument("--skip-local", action="store_true", help="Skip local engine")
    pa.add_argument("--skip-api",   action="store_true", help="Skip API calls")
    pa.add_argument("--batch-size", type=int, default=4,
                    help="Documents per API call (default: 4)")
    pa.add_argument("--base-url",   default="https://www.loterre.fr/ark:/")
    args = pa.parse_args()

    text_root  = Path(args.text_root)
    out_dir    = Path(args.out_dir)
    cli        = Path(args.cli)
    renderer   = Path(args.renderer)
    local_dir  = out_dir / "local"
    api_dir    = out_dir / "api"

    # discover gold files
    gold_files = sorted(text_root.glob("*.jsonl"))
    if not gold_files:
        sys.exit(f"No .jsonl files found in {text_root}")

    # filter by requested vocabs
    # Accepts both "P66" (matches P66_en + P66_fr) and "P66_fr" (exact stem match).
    if args.vocabs:
        wanted = {v.strip() for v in args.vocabs.split(",")}
        gold_files = [
            g for g in gold_files
            if g.stem in wanted or g.stem.split("_")[0] in wanted
        ]

    sys.path.insert(0, str(renderer.parent))

    summary_rows = []

    for gold_file in gold_files:
        stem   = gold_file.stem                    # e.g. P66_en
        vocab  = stem.split("_")[0]                # e.g. P66
        lang   = stem.split("_")[1] if "_" in stem else "en"

        print(f"\n{'='*60}")
        print(f"  {vocab} ({lang})  —  gold: {gold_file.name}")
        print(f"{'='*60}")

        local_json = local_dir / "json" / f"{stem}.json"
        local_html = local_dir / "html" / f"{stem}.html"
        api_json   = api_dir   / "json" / f"{stem}.json"
        api_html   = api_dir   / "html" / f"{stem}.html"

        # ── local engine ──────────────────────────────────────────────────
        if not args.skip_local:
            print(f"[local] running {cli.name} …")
            ok = run_local(cli, stem, gold_file, local_json)
            if ok:
                render_html(renderer, local_json, gold_file, local_html,
                            f"Annotation Loterre v9 — {stem}", args.base_url)
                print(f"[local] → {local_html}")
        else:
            print("[local] skipped")

        # ── API ────────────────────────────────────────────────────────────
        if not args.skip_api:
            effective_url = args.api_url.format(lang=lang) + f"?loterreID={vocab}"
            print(f"[api]   calling {effective_url} …")
            gold_rows = read_jsonl(gold_file)
            ok = run_api(args.api_url, vocab, lang, gold_rows, api_json,
                         batch_size=args.batch_size)
            if ok:
                render_html(renderer, api_json, gold_file, api_html,
                            f"Annotation API production — {stem}", args.base_url)
                print(f"[api]   → {api_html}")
        else:
            print("[api] skipped")

        # ── stats ─────────────────────────────────────────────────────────
        row = {"vocab": vocab}
        if local_json.exists():
            row["v9"]  = aggregate_stats(local_json, gold_file)
        else:
            row["v9"]  = dict(p=0, a=0, b=0, eo=0, po=0, recall=0, precision=0, f1=0)
        if api_json.exists():
            row["api"] = aggregate_stats(api_json, gold_file)
        else:
            row["api"] = dict(p=0, a=0, b=0, eo=0, po=0, recall=0, precision=0, f1=0)
        summary_rows.append(row)

        a, v = row["api"], row["v9"]
        print(f"  API: R={a['recall']:.1f}%  P={a['precision']:.1f}%  F1={a['f1']:.1f}%  (both={a['b']})")
        print(f"  v9:  R={v['recall']:.1f}%  P={v['precision']:.1f}%  F1={v['f1']:.1f}%  (both={v['b']})")

    # ── summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    if summary_rows:
        print_table(summary_rows)

        tsv_path  = out_dir / "summary.tsv"
        html_path = out_dir / "summary.html"
        write_summary_tsv(summary_rows, tsv_path)
        write_summary_html(summary_rows, html_path, text_root,
                           local_dir / "html", api_dir / "html")
        print(f"\n  TSV  → {tsv_path}")
        print(f"  HTML → {html_path}")


if __name__ == "__main__":
    main()
