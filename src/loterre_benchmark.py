#!/usr/bin/env python3
"""Benchmark loterre_cli.py (local) vs the terms-tools API and the Loterre
Resolvers API, against gold corpus.

Three engines are compared:
  - local     : loterre_cli.py annotate (local), config/registre de ce repo —
                labellé "cli" dans les colonnes de comparaison
  - api       : service terms-tools (production)
                (https://github.com/Inist-CNRS/web-services/tree/main/services/terms-tools),
                appelé en HTTP — réponse à indices de tokens, convertie en
                offsets caractères (voir api_doc_to_matches() / docs/README.md §13.1)
  - resolvers : Loterre Resolvers   (loterre-resolvers.services.istex.fr)

Usage
-----
    python3 src/loterre_benchmark.py \\
        --text-root data/jsonl \\
        --out-dir   benchmark_results \\
        [--cli      src/loterre_cli.py] \\
        [--renderer src/loterre_html_renderer.py] \\
        [--api-url  https://terms-tools.services.istex.fr/v1/{lang}/terms-matcher/json-standoff/annotate] \\
        [--resolvers-url https://loterre-resolvers.services.istex.fr/v1/annotate] \\
        [--vocabs   P66,27X,9SD]   # subset; default = all found in TEXT_ROOT, sauf --exclude-vocabs \\
        [--exclude-vocabs JVR]     # exclus du run par defaut (ignore si --vocabs est donne) ;
                                   # JVR est volumineux et ralentit fortement le benchmark \\
        [--skip-local]             # skip local engine \\
        [--skip-api]               # skip l'appel API terms-tools \\
        [--skip-resolvers]         # skip loterre-resolvers API \\
        [--batch-size 4]           # docs per API call (terms-tools et Resolvers) \\
        [--base-url https://www.loterre.fr/ark:/]

Output layout
-------------
    OUT_DIR/
      local/json/<vocab>_en.json
      local/html/<vocab>_en.html
      api/json/<vocab>_en.json
      api/html/<vocab>_en.html
      resolvers/json/<vocab>_en.json
      resolvers/html/<vocab>_en.html
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
RESOLVERS_DEFAULT = "https://loterre-resolvers.services.istex.fr/v1/annotate"

# Tokeniseur utilisé par l'API terms-tools pour ses indices idx.start/end
# (nombres décimaux comme un seul token, ponctuation isolée) — voir
# docs/README.md §13.1. Nécessaire pour convertir les indices de tokens
# renvoyés par l'API en offsets caractères comparables au gold/à loterre_cli.
_API_TOKEN_RE = re.compile(r"\d+\.\d+|\w+|[^\w\s]")


def _tokenize_for_api(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _API_TOKEN_RE.finditer(text)]

# ── helpers ───────────────────────────────────────────────────────────────────

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


# ── stats ──────────────────────────────────────────────────────────────────────

def ann_key(m: dict) -> str:
    return str(m.get("pref") or m.get("label") or m.get("found") or "").strip().lower()


def compute_counts(predicted: list, expected: list) -> dict:
    pc = Counter(ann_key(m) for m in predicted)
    ec = Counter(ann_key(m) for m in expected)
    both     = sum(min(pc[k], ec[k]) for k in ec)
    exp_only = sum(max(0, ec[k] - pc[k]) for k in ec)
    pred_only = sum(max(0, pc[k] - ec[k]) for k in pc)
    return {"both": both, "expected_only": exp_only, "predicted_only": pred_only}


def aggregate_stats(json_path: Path, gold_path: Path) -> dict:
    """Return {p, a, b, eo, po, recall, precision, f1} for one vocab."""
    payload   = read_json_payload(json_path)
    results   = payload.get("results") or payload.get("documents") or []
    gold_rows = read_jsonl(gold_path)
    gold_map  = {str(r["id"]): r for r in gold_rows}

    tot_p = tot_a = tot_b = tot_eo = tot_po = 0
    for d in results:
        g         = gold_map.get(str(d.get("id")), {})
        predicted = d.get("matches", []) or []
        expected  = g.get("expected_matches", []) or []
        c         = compute_counts(predicted, expected)
        tot_p  += len(predicted)
        tot_a  += len(expected)
        tot_b  += c["both"]
        tot_eo += c["expected_only"]
        tot_po += c["predicted_only"]

    recall = 100 * tot_b / tot_a if tot_a else 0.0
    prec   = 100 * tot_b / tot_p if tot_p else 0.0
    f1     = 2 * recall * prec / (recall + prec) if (recall + prec) else 0.0
    # available = False means the service returned no documents at all (not available
    # for this vocabulary), so this row must be excluded from global totals.
    available = len(results) > 0
    return dict(p=tot_p, a=tot_a, b=tot_b, eo=tot_eo, po=tot_po,
                recall=recall, precision=prec, f1=f1, available=available)


def _empty_stats() -> dict:
    return dict(p=0, a=0, b=0, eo=0, po=0, recall=0.0, precision=0.0, f1=0.0,
                available=False)


# ── moteur local (loterre_cli.py) ───────────────────────────────────────────────

def run_local(cli: Path, dict_id: str, text_file: Path, json_out: Path,
              label: str = "local") -> bool:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    cmd  = [sys.executable, str(cli), "annotate", "--dict-id", dict_id,
            "--text", str(text_file), "--silent"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  [{label}] ERROR for {dict_id}: {proc.stderr[:200]}", file=sys.stderr)
        return False
    json_out.write_text(proc.stdout, encoding="utf-8")
    return True


def _http_post(url: str, docs: list[dict], label: str,
               timeout: int = 90) -> list[dict] | None:
    body = json.dumps(docs).encode("utf-8")
    req  = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8").strip()
            if not raw:
                print(f"  [{label}] empty response", file=sys.stderr)
                return []
            return json.loads(raw)
    except HTTPError as e:
        print(f"  [{label}] HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
        return None
    except URLError as e:
        print(f"  [{label}] URL error: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [{label}] parse error: {e}", file=sys.stderr)
        return None


# ── terms-tools API ───────────────────────────────────────────────────────────

def api_doc_to_matches(api_doc: dict, text: str) -> list[dict]:
    """Convert one terms-tools response document into local match dicts.

    La réponse contient idx.start/idx.end en indices de TOKENS, pas en
    offsets caractères (voir docs/README.md §13.1) — on retokénise le texte
    source avec la même règle que l'API pour retrouver les offsets exacts.
    """
    tokens = _tokenize_for_api(text)
    n      = len(tokens)
    matches = []
    for segment in api_doc.get("value", []):
        for ann in segment.get("matches", []):
            idx = ann.get("idx", {})
            try:
                ti_start = int(idx.get("start"))
                ti_end   = int(idx.get("end"))
            except (TypeError, ValueError):
                continue
            if not (0 <= ti_start < ti_end <= n):
                continue
            match_info = ann.get("match", {}) or {}
            char_start = tokens[ti_start][0]
            char_end   = tokens[ti_end - 1][1]
            matches.append({
                "start": char_start,
                "end":   char_end,
                "found": match_info.get("text", text[char_start:char_end]),
                "pref":  match_info.get("term", ""),
                "uri":   match_info.get("id", ""),
            })
    return matches


def run_api(api_url: str, vocab: str, lang: str, gold_rows: list[dict],
            json_out: Path, batch_size: int = 4, delay: float = 0.5) -> bool:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    input_docs = [{"id": r["id"], "value": r.get("value", r.get("text", ""))}
                  for r in gold_rows]
    results = []
    for i in range(0, len(input_docs), batch_size):
        batch = input_docs[i:i + batch_size]
        url   = f"{api_url.format(lang=lang)}?loterreID={vocab}"
        print(f"  [api] batch {i//batch_size+1} ({len(batch)} docs)…", end=" ", flush=True)
        t0   = time.perf_counter()
        resp = _http_post(url, batch, "api")
        dt   = time.perf_counter() - t0
        if resp is None:
            print(f"FAILED ({dt:.1f}s)")
            continue
        print(f"OK ({dt:.1f}s)")
        for api_doc in resp:
            doc_id = str(api_doc.get("id", ""))
            text   = next((r.get("value", r.get("text", ""))
                           for r in gold_rows if str(r["id"]) == doc_id), "")
            results.append({"id": api_doc.get("id"),
                            "matches": api_doc_to_matches(api_doc, text)})
        if i + batch_size < len(input_docs):
            time.sleep(delay)

    json_out.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return len(results) > 0


# ── loterre-resolvers API ─────────────────────────────────────────────────────

def resolvers_doc_to_matches(resp_doc: dict, text: str) -> list[dict]:
    """Convert a loterre-resolvers /v1/annotate response doc to benchmark matches.

    The resolvers service returns concepts with recognised surface forms but no
    character offsets.  Positions are reconstructed by searching the source text
    for each cleaned surface form (case-insensitive, respecting the reported
    frequency so we don't over-count repeated terms).
    """
    matches    = []
    seen_spans: set[tuple[int, int]] = set()
    text_lower = text.lower()

    for concept in resp_doc.get("value", []):
        pref  = concept.get("prefLabel", "")
        uri   = concept.get("conceptUri", "")
        freq  = int(concept.get("frequence", 1))
        found_count = 0

        for surface in concept.get("termeReconnu", []):
            # Strip trailing punctuation included by the annotator
            clean = re.sub(r"[.,;:!?'\"\)\s]+$", "", surface).strip()
            if not clean:
                continue
            pattern = re.compile(re.escape(clean.lower()))
            for m in pattern.finditer(text_lower):
                if found_count >= freq:
                    break
                span = (m.start(), m.end())
                if span in seen_spans:
                    continue
                seen_spans.add(span)
                found_count += 1
                matches.append({
                    "start": m.start(),
                    "end":   m.end(),
                    "found": text[m.start():m.end()],
                    "pref":  pref,
                    "uri":   uri,
                })
            if found_count >= freq:
                break

    return matches


def run_resolvers(resolvers_url: str, vocab: str, lang: str, gold_rows: list[dict],
                  json_out: Path, batch_size: int = 4, delay: float = 0.5) -> bool:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    input_docs = [{"id": r["id"], "value": r.get("value", r.get("text", ""))}
                  for r in gold_rows]
    results = []
    for i in range(0, len(input_docs), batch_size):
        batch = input_docs[i:i + batch_size]
        url   = f"{resolvers_url}?loterreID={vocab}&lang={lang}"
        print(f"  [resolvers] batch {i//batch_size+1} ({len(batch)} docs)…",
              end=" ", flush=True)
        t0   = time.perf_counter()
        resp = _http_post(url, batch, "resolvers")
        dt   = time.perf_counter() - t0
        if resp is None:
            print(f"FAILED ({dt:.1f}s)")
            continue
        print(f"OK ({dt:.1f}s)")
        for res_doc in resp:
            doc_id = str(res_doc.get("id", ""))
            text   = next((r.get("value", r.get("text", ""))
                           for r in gold_rows if str(r["id"]) == doc_id), "")
            results.append({"id": res_doc.get("id"),
                            "matches": resolvers_doc_to_matches(res_doc, text)})
        if i + batch_size < len(input_docs):
            time.sleep(delay)

    json_out.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return len(results) > 0


# ── HTML rendering ─────────────────────────────────────────────────────────────

def render_html(renderer_path: Path, json_file: Path, gold_file: Path,
                html_out: Path, title: str, base_url: str) -> None:
    html_out.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(renderer_path.parent))
    from loterre_html_renderer import render_file
    render_file(str(json_file), str(html_out), base_url, title, str(gold_file))


# ── summary report ─────────────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v:.1f}%"


def _delta(a: float, b: float) -> str:
    d = b - a
    return ("+" if d >= 0 else "") + f"{d:.1f}"


def _fmt(s: dict, key: str) -> str:
    """Format a stat value as '0.0' or 'N/A' when service was unavailable."""
    if not s.get("available", True):
        return "N/A"
    return f"{s[key]:.1f}"


def _delta_or_na(a: dict, b: dict, key: str) -> str:
    """Delta between two stats, or 'N/A' if either is unavailable."""
    if not a.get("available", True) or not b.get("available", True):
        return "N/A"
    return _delta(a[key], b[key])


def write_summary_tsv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "vocab", "lang",
        "api_r",  "api_p",  "api_f1",  "api_both",
        "res_r",  "res_p",  "res_f1",  "res_both",
        "cli_r",  "cli_p",  "cli_f1",  "cli_both",
        "delta_cli_api_r", "delta_cli_api_p", "delta_cli_api_f1",
        "delta_cli_res_r", "delta_cli_res_p", "delta_cli_res_f1",
    ]
    lines = ["\t".join(header)]
    for r in rows:
        a, res, c = r["api"], r["resolvers"], r["cli"]
        stem = r.get("stem", r["vocab"])
        lang = stem.split("_")[1] if "_" in stem else "en"
        lines.append("\t".join([
            r["vocab"], lang,
            _fmt(a,   "recall"), _fmt(a,   "precision"), _fmt(a,   "f1"), str(a['b']  if a.get("available")   else "N/A"),
            _fmt(res, "recall"), _fmt(res, "precision"), _fmt(res, "f1"), str(res['b'] if res.get("available") else "N/A"),
            _fmt(c,   "recall"), _fmt(c,   "precision"), _fmt(c,   "f1"), str(c['b']  if c.get("available")   else "N/A"),
            _delta_or_na(a,   c, "recall"), _delta_or_na(a,   c, "precision"), _delta_or_na(a,   c, "f1"),
            _delta_or_na(res, c, "recall"), _delta_or_na(res, c, "precision"), _delta_or_na(res, c, "f1"),
        ]))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_html(rows: list[dict], path: Path, gold_root: Path,
                       local_html_dir: Path, api_html_dir: Path,
                       resolvers_html_dir: Path) -> None:
    css = """
body{font-family:system-ui,sans-serif;margin:0;padding:2rem;background:#f7f7f8;color:#1f2937}
h1{margin-bottom:.5rem}
.subtitle{color:#6b7280;margin-bottom:2rem}
table{width:100%;border-collapse:collapse;background:white;border-radius:12px;
      overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06);font-size:.85rem}
th{background:#1e3a5f;color:white;padding:.5rem .7rem;text-align:left}
th.grp{background:#2d4a73;font-size:.8rem;letter-spacing:.04em}
td{padding:.45rem .7rem;border-bottom:1px solid #e5e7eb;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f0f4ff}
.api{color:#b45309}.res{color:#7c3aed}.cli{color:#166534}.delta{font-weight:600}
.pos{color:#166534}.neg{color:#dc2626}.neu{color:#6b7280}
.bar-bg{background:#e5e7eb;border-radius:4px;height:7px;margin-top:2px}
.bar-fill-api{background:#f59e0b;border-radius:4px;height:7px}
.bar-fill-res{background:#7c3aed;border-radius:4px;height:7px}
.bar-fill-cli{background:#22c55e;border-radius:4px;height:7px}
a{color:#1d4ed8;text-decoration:none}a:hover{text-decoration:underline}
.legend{display:flex;gap:1.5rem;margin-bottom:1rem;font-size:.85rem}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:.3rem;vertical-align:middle}
"""

    def bar(pct: float, cls: str) -> str:
        w = round(max(0, min(pct, 100)))
        return f'<div class="bar-bg"><div class="{cls}" style="width:{w}%"></div></div>'

    def delta_html(a: float, b: float) -> str:
        d = b - a
        sign = "+" if d >= 0 else ""
        cls = "pos" if d > 0.5 else ("neg" if d < -0.5 else "neu")
        return f'<span class="delta {cls}">{sign}{d:.1f}</span>'

    NA_CELL = "<span style='color:#9ca3af;font-size:.8rem'>N/A</span>"

    def cell(s: dict, key: str, cls: str, bar_cls: str) -> str:
        if not s.get("available", True):
            return f"<td class='{cls}'>{NA_CELL}</td>"
        v = s[key]
        return f"<td class='{cls}'>{_pct(v)}{bar(v, bar_cls)}</td>"

    def dcell(a: dict, b: dict, key: str) -> str:
        if not a.get("available", True) or not b.get("available", True):
            return f"<td>{NA_CELL}</td>"
        return f"<td>{delta_html(a[key], b[key])}</td>"

    rows_html = ""
    for r in rows:
        v_code = r["vocab"]
        stem   = r.get("stem", v_code)
        lang   = stem.split("_")[1] if "_" in stem else "en"
        lang_badge = (
            f'<span style="font-size:.72rem;padding:1px 5px;border-radius:3px;'
            f'background:{"#dbeafe" if lang=="en" else "#fce7f3"};'
            f'color:{"#1e40af" if lang=="en" else "#9d174d"}">{lang}</span>'
        )
        a, res, c = r["api"], r["resolvers"], r["cli"]
        local_link = f'<a href="local/html/{stem}.html">cli</a>'
        api_link   = f'<a href="api/html/{stem}.html">api</a>'
        res_link   = f'<a href="resolvers/html/{stem}.html">res</a>'
        rows_html += (
            f"<tr>"
            f"<td><b>{v_code}</b> {lang_badge} {local_link} {api_link} {res_link}</td>"
            + cell(a,   "recall",    "api", "bar-fill-api")
            + cell(a,   "precision", "api", "bar-fill-api")
            + cell(a,   "f1",        "api", "bar-fill-api")
            + cell(res, "recall",    "res", "bar-fill-res")
            + cell(res, "precision", "res", "bar-fill-res")
            + cell(res, "f1",        "res", "bar-fill-res")
            + cell(c,   "recall",    "cli", "bar-fill-cli")
            + cell(c,   "precision", "cli", "bar-fill-cli")
            + cell(c,   "f1",        "cli", "bar-fill-cli")
            + dcell(a,   c, "recall") + dcell(a,   c, "f1")
            + dcell(res, c, "recall") + dcell(res, c, "f1")
            + "</tr>\n"
        )

    def tot(key: str, engine: str) -> float:
        # Only include vocabs where the engine was actually available.
        avail = [r for r in rows if r[engine].get("available", True)]
        num   = sum(r[engine]["b"] for r in avail)
        den_a = sum(r[engine]["a"] for r in avail)
        den_p = sum(r[engine]["p"] for r in avail)
        if key == "recall":
            return 100 * num / den_a if den_a else 0
        if key == "precision":
            return 100 * num / den_p if den_p else 0
        r_ = tot("recall", engine); p_ = tot("precision", engine)
        return 2 * r_ * p_ / (r_ + p_) if (r_ + p_) else 0

    def tot_n(engine: str) -> int:
        """Number of vocabs where the engine was available."""
        return sum(1 for r in rows if r[engine].get("available", True))

    ar = tot("recall","api");       ap = tot("precision","api");       af = tot("f1","api")
    rr = tot("recall","resolvers"); rp = tot("precision","resolvers"); rf = tot("f1","resolvers")
    cr = tot("recall","cli");       cp = tot("precision","cli");       cf = tot("f1","cli")
    an = tot_n("api"); rn = tot_n("resolvers"); cn = tot_n("cli")
    rows_html += (
        f"<tr style='background:#f3f4f6;font-weight:600'>"
        f"<td>TOTAL <span style='font-size:.75rem;color:#6b7280'>"
        f"api:{an} res:{rn} cli:{cn} vocabs</span></td>"
        f"<td class='api'>{_pct(ar)}{bar(ar,'bar-fill-api')}</td>"
        f"<td class='api'>{_pct(ap)}{bar(ap,'bar-fill-api')}</td>"
        f"<td class='api'>{_pct(af)}{bar(af,'bar-fill-api')}</td>"
        f"<td class='res'>{_pct(rr)}{bar(rr,'bar-fill-res')}</td>"
        f"<td class='res'>{_pct(rp)}{bar(rp,'bar-fill-res')}</td>"
        f"<td class='res'>{_pct(rf)}{bar(rf,'bar-fill-res')}</td>"
        f"<td class='cli'>{_pct(cr)}{bar(cr,'bar-fill-cli')}</td>"
        f"<td class='cli'>{_pct(cp)}{bar(cp,'bar-fill-cli')}</td>"
        f"<td class='cli'>{_pct(cf)}{bar(cf,'bar-fill-cli')}</td>"
        f"<td>{delta_html(ar, cr)}</td><td>{delta_html(af, cf)}</td>"
        f"<td>{delta_html(rr, cr)}</td><td>{delta_html(rf, cf)}</td>"
        f"</tr>\n"
    )

    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Benchmark Loterre — API / Resolvers / CLI</title>
<style>{css}</style></head><body>
<h1>Benchmark Loterre</h1>
<p class="subtitle">Comparaison : terms-tools (production) · Loterre Resolvers · loterre_cli (local)</p>
<div class="legend">
  <span><span class="dot" style="background:#f59e0b"></span>terms-tools (production)</span>
  <span><span class="dot" style="background:#7c3aed"></span>Loterre Resolvers (production)</span>
  <span><span class="dot" style="background:#22c55e"></span>loterre_cli (local)</span>
</div>
<table>
<thead>
<tr>
  <th rowspan="2">Vocabulaire</th>
  <th colspan="3" class="grp" style="background:#b45309">terms-tools</th>
  <th colspan="3" class="grp" style="background:#6d28d9">Resolvers</th>
  <th colspan="3" class="grp" style="background:#15803d">cli (local)</th>
  <th colspan="2" class="grp">Δ cli vs API</th>
  <th colspan="2" class="grp">Δ cli vs Res.</th>
</tr>
<tr>
  <th>R%</th><th>P%</th><th>F1%</th>
  <th>R%</th><th>P%</th><th>F1%</th>
  <th>R%</th><th>P%</th><th>F1%</th>
  <th>ΔR</th><th>ΔF1</th>
  <th>ΔR</th><th>ΔF1</th>
</tr>
</thead>
<tbody>{rows_html}</tbody>
</table>
<p style="color:#6b7280;font-size:.8rem;margin-top:1rem">
  Généré le {time.strftime('%Y-%m-%d %H:%M')} — gold: {gold_root}
</p>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def print_table(rows: list[dict]) -> None:
    NA = "  N/A "

    def fmt(s: dict, key: str, w: int) -> str:
        if not s.get("available", True):
            return "N/A".rjust(w + 1)
        return f"{s[key]:>{w}.1f}%"

    def dfmt(a: dict, b: dict, key: str, w: int) -> str:
        if not a.get("available", True) or not b.get("available", True):
            return "N/A".rjust(w)
        d = b[key] - a[key]
        return (("+" if d >= 0 else "") + f"{d:.1f}").rjust(w)

    hdr = (f"{'Vocab':<12}  "
           f"{'API R%':>7} {'API P%':>7} {'API F1%':>8}  "
           f"{'Res R%':>7} {'Res P%':>7} {'Res F1%':>8}  "
           f"{'cli R%':>6} {'cli P%':>7} {'cli F1%':>8}  "
           f"{'Δ(cli-API)F1':>12} {'Δ(cli-Res)F1':>12}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        a, res, c = r["api"], r["resolvers"], r["cli"]
        stem = r.get("stem", r["vocab"])
        print(
            f"{stem:<12}  "
            f"{fmt(a,'recall',6)} {fmt(a,'precision',6)} {fmt(a,'f1',7)}  "
            f"{fmt(res,'recall',6)} {fmt(res,'precision',6)} {fmt(res,'f1',7)}  "
            f"{fmt(c,'recall',5)} {fmt(c,'precision',6)} {fmt(c,'f1',7)}  "
            f"{dfmt(a,c,'f1',12)} {dfmt(res,c,'f1',12)}"
        )
    print("-" * len(hdr))

    def tot(key, engine):
        avail = [r for r in rows if r[engine].get("available", True)]
        num   = sum(r[engine]["b"] for r in avail)
        den   = sum(r[engine]["a"] if key == "recall" else r[engine]["p"] for r in avail)
        if key in ("recall", "precision"):
            return 100 * num / den if den else 0
        rr = tot("recall", engine); pp = tot("precision", engine)
        return 2 * rr * pp / (rr + pp) if (rr + pp) else 0

    an = sum(1 for r in rows if r["api"].get("available", True))
    rn = sum(1 for r in rows if r["resolvers"].get("available", True))
    cn = sum(1 for r in rows if r["cli"].get("available", True))

    def tot_fmt(engine: str, key: str, n: int, w: int) -> str:
        return "N/A".rjust(w + 1) if n == 0 else f"{tot(key, engine):>{w}.1f}%"

    def tot_delta(e1: str, e2: str, n1: int, n2: int, w: int) -> str:
        if n1 == 0 or n2 == 0:
            return "N/A".rjust(w)
        d = tot("f1", e2) - tot("f1", e1)
        return (("+" if d >= 0 else "") + f"{d:.1f}").rjust(w)

    print(
        f"{'TOTAL':<12}  "
        f"{tot_fmt('api','recall',an,6)} {tot_fmt('api','precision',an,6)} {tot_fmt('api','f1',an,7)}  "
        f"{tot_fmt('resolvers','recall',rn,6)} {tot_fmt('resolvers','precision',rn,6)} {tot_fmt('resolvers','f1',rn,7)}  "
        f"{tot_fmt('cli','recall',cn,5)} {tot_fmt('cli','precision',cn,6)} {tot_fmt('cli','f1',cn,7)}  "
        f"{tot_delta('api','cli',an,cn,12)} {tot_delta('resolvers','cli',rn,cn,12)}"
    )
    print(f"  (totals on: api={an}, resolvers={rn}, cli={cn} vocabs with available results)")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    pa = argparse.ArgumentParser(
        description="Benchmark loterre_cli.py (local) vs the terms-tools API and Loterre Resolvers API against gold corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    pa.add_argument("--text-root",       default="data/jsonl")
    pa.add_argument("--out-dir",         default="benchmark_results")
    pa.add_argument("--cli",             default="src/loterre_cli.py")
    pa.add_argument("--renderer",        default="src/loterre_html_renderer.py")
    pa.add_argument("--api-url",         default=API_DEFAULT,
                    help="terms-tools base URL (default: terms-tools.services.istex.fr)")
    pa.add_argument("--resolvers-url",   default=RESOLVERS_DEFAULT,
                    help="Loterre Resolvers base URL (default: loterre-resolvers.services.istex.fr)")
    pa.add_argument("--vocabs",          help="Comma-separated vocab codes (default: all)")
    pa.add_argument("--exclude-vocabs",  default="JVR",
                    help="Comma-separated vocab codes excluded from the default run "
                         "(ignored if --vocabs is given) ; defaut: JVR (vocabulaire "
                         "volumineux, ralentit fortement le benchmark)")
    pa.add_argument("--skip-local",      action="store_true")
    pa.add_argument("--skip-api",        action="store_true",
                    help="Skip the terms-tools API")
    pa.add_argument("--skip-resolvers",  action="store_true")
    pa.add_argument("--batch-size",      type=int, default=4)
    pa.add_argument("--base-url",        default="https://www.loterre.fr/ark:/")
    args = pa.parse_args()

    text_root      = Path(args.text_root)
    out_dir        = Path(args.out_dir)
    cli            = Path(args.cli)
    renderer       = Path(args.renderer)
    local_dir      = out_dir / "local"
    api_dir        = out_dir / "api"
    resolvers_dir  = out_dir / "resolvers"

    gold_files = sorted(text_root.glob("*.jsonl"))
    if not gold_files:
        sys.exit(f"No .jsonl files found in {text_root}")

    if args.vocabs:
        wanted     = {v.strip() for v in args.vocabs.split(",")}
        gold_files = [
            g for g in gold_files
            if g.stem in wanted or g.stem.split("_")[0] in wanted
        ]
    elif args.exclude_vocabs:
        excluded = {v.strip() for v in args.exclude_vocabs.split(",") if v.strip()}
        gold_files = [
            g for g in gold_files
            if g.stem not in excluded and g.stem.split("_")[0] not in excluded
        ]

    sys.path.insert(0, str(renderer.parent))

    summary_rows = []

    for gold_file in gold_files:
        stem  = gold_file.stem
        vocab = stem.split("_")[0]
        lang  = stem.split("_")[1] if "_" in stem else "en"

        print(f"\n{'='*60}")
        print(f"  {vocab} ({lang})  —  gold: {gold_file.name}")
        print(f"{'='*60}")

        local_json     = local_dir     / "json" / f"{stem}.json"
        local_html     = local_dir     / "html" / f"{stem}.html"
        api_json       = api_dir       / "json" / f"{stem}.json"
        api_html       = api_dir       / "html" / f"{stem}.html"
        resolvers_json = resolvers_dir / "json" / f"{stem}.json"
        resolvers_html = resolvers_dir / "html" / f"{stem}.html"

        # ── local engine ──────────────────────────────────────────────────
        if not args.skip_local:
            print(f"[local] running {cli.name} …")
            ok = run_local(cli, stem, gold_file, local_json)
            if ok:
                render_html(renderer, local_json, gold_file, local_html,
                            f"Annotation loterre_cli (local) — {stem}", args.base_url)
                print(f"[local] → {local_html}")
        else:
            print("[local] skipped")

        # ── terms-tools API ────────────────────────────────────────────────
        gold_rows = read_jsonl(gold_file)
        if not args.skip_api:
            effective_url = args.api_url.format(lang=lang) + f"?loterreID={vocab}"
            print(f"[api]   calling {effective_url} …")
            ok = run_api(args.api_url, vocab, lang, gold_rows, api_json,
                         batch_size=args.batch_size)
            if ok:
                render_html(renderer, api_json, gold_file, api_html,
                            f"Annotation terms-tools — {stem}", args.base_url)
                print(f"[api]   → {api_html}")
        else:
            print("[api] skipped")

        # ── loterre-resolvers ──────────────────────────────────────────────
        if not args.skip_resolvers:
            res_url = f"{args.resolvers_url}?loterreID={vocab}&lang={lang}"
            print(f"[resolvers] calling {res_url} …")
            ok = run_resolvers(args.resolvers_url, vocab, lang, gold_rows,
                               resolvers_json, batch_size=args.batch_size)
            if ok:
                render_html(renderer, resolvers_json, gold_file, resolvers_html,
                            f"Annotation Loterre Resolvers — {stem}", args.base_url)
                print(f"[resolvers] → {resolvers_html}")
        else:
            print("[resolvers] skipped")

        # ── stats ──────────────────────────────────────────────────────────
        row = {"vocab": vocab, "stem": stem}
        row["cli"]       = aggregate_stats(local_json,     gold_file) if local_json.exists()     else _empty_stats()
        row["api"]       = aggregate_stats(api_json,       gold_file) if api_json.exists()       else _empty_stats()
        row["resolvers"] = aggregate_stats(resolvers_json, gold_file) if resolvers_json.exists() else _empty_stats()
        summary_rows.append(row)

        a, res, c = row["api"], row["resolvers"], row["cli"]
        print(f"  API:       R={a['recall']:.1f}%  P={a['precision']:.1f}%  F1={a['f1']:.1f}%  (both={a['b']})")
        print(f"  Resolvers: R={res['recall']:.1f}%  P={res['precision']:.1f}%  F1={res['f1']:.1f}%  (both={res['b']})")
        print(f"  cli:       R={c['recall']:.1f}%  P={c['precision']:.1f}%  F1={c['f1']:.1f}%  (both={c['b']})")

    # ── summary ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    if summary_rows:
        print_table(summary_rows)
        tsv_path  = out_dir / "summary.tsv"
        html_path = out_dir / "summary.html"
        write_summary_tsv(summary_rows, tsv_path)
        write_summary_html(summary_rows, html_path, text_root,
                           local_dir / "html", api_dir / "html",
                           resolvers_dir / "html")
        print(f"\n  TSV  → {tsv_path}")
        print(f"  HTML → {html_path}")


if __name__ == "__main__":
    main()
