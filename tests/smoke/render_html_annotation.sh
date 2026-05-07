#!/usr/bin/env bash
set -euo pipefail

# Render HTML annotations for a predefined list of Loterre vocabularies.
#
# English vocabularies:
#   P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR
#
# French vocabularies:
#   P66 9SD 8HQ B9M 27X BVM QX8
#
# Usage:
#   bash scripts/render_html_annotation.sh [CLI] [TEXT_ROOT] [OUTDIR] [RENDERER]
#
# Arguments:
#   CLI       path to loterre_cli.py
#   TEXT_ROOT directory containing input JSONL texts
#   OUTDIR    output directory
#   RENDERER  path to loterre_html_renderer.py
#
# Example:
#   bash scripts/render_html_annotation.sh \
#     ./src/loterre_cli.py \
#     examples/texts \
#     ./html_outputs \
#     ./src/loterre_html_renderer.py

CLI="${1:-./src/loterre_cli.py}"
TEXT_ROOT="${2:-examples/texts}"
OUTDIR="${3:-./html_outputs}"
RENDERER="${4:-./src/loterre_html_renderer.py}"

BASE_URL="${BASE_URL:-https://www.loterre.fr/ark:/}"

#EN_CODES=(P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR)
EN_CODES=(27X P66 9SD)
#FR_CODES=(P66 9SD 8HQ B9M 27X BVM QX8)

mkdir -p "$OUTDIR/json" "$OUTDIR/html"

SUMMARY="$OUTDIR/html_generation_summary.tsv"
echo -e "dict_id\tlang\tcode\tstatus\ttext_file\tjson_file\thtml_file" > "$SUMMARY"

find_text_file() {
  local code="$1"
  local lang="$2"
  local root="$3"

  local candidates=(
    "$root/${code}_${lang}.jsonl"
    "$root/${code}_${lang}.json"
    "$root/${code}.jsonl"
    "$root/${code}.json"
  )

  for c in "${candidates[@]}"; do
    if [[ -f "$c" ]]; then
      echo "$c"
      return 0
    fi
  done

  local found=""
  found=$(find "$root" -maxdepth 1 -type f \( \
      -name "*${code}*${lang}*.jsonl" -o \
      -name "*${code}*${lang}*.json" -o \
      -name "*${code}*.jsonl" -o \
      -name "*${code}*.json" \
    \) | sort | head -n 1 || true)

  if [[ -n "$found" ]]; then
    echo "$found"
    return 0
  fi

  return 1
}

run_one() {
  local code="$1"
  local lang="$2"
  local dict_id="${code}_${lang}"

  echo
  echo "== ${dict_id} =="

  local text_file=""
  if ! text_file=$(find_text_file "$code" "$lang" "$TEXT_ROOT"); then
    echo "WARNING: no text file found for ${dict_id} in ${TEXT_ROOT}" >&2
    echo -e "${dict_id}\t${lang}\t${code}\tmissing_text\t\t\t" >> "$SUMMARY"
    return 0
  fi

  local json_file="$OUTDIR/json/${dict_id}.json"
  local html_file="$OUTDIR/html/${dict_id}.html"

  if python "$CLI" \
      --dict-id "$dict_id" \
      --text "$text_file" \
      --silent > "$json_file"; then

    python "$RENDERER" render \
      --input "$json_file" \
      --out "$html_file" \
      --title "Annotation Loterre — ${dict_id}" \
      --base-url "$BASE_URL"

    echo "OK"
    echo "  text: $text_file"
    echo "  json: $json_file"
    echo "  html: $html_file"

    echo -e "${dict_id}\t${lang}\t${code}\tok\t${text_file}\t${json_file}\t${html_file}" >> "$SUMMARY"
  else
    echo "ERROR: engine failed for ${dict_id}" >&2
    echo -e "${dict_id}\t${lang}\t${code}\terror\t${text_file}\t${json_file}\t${html_file}" >> "$SUMMARY"
  fi
}

echo "HTML annotation generation"
echo "CLI:       $CLI"
echo "TEXT_ROOT: $TEXT_ROOT"
echo "OUTDIR:    $OUTDIR"
echo "RENDERER:  $RENDERER"
echo "BASE_URL:  $BASE_URL"

for code in "${EN_CODES[@]}"; do
  run_one "$code" "en"
done

for code in "${FR_CODES[@]}"; do
  run_one "$code" "fr"
done

echo
echo "Summary:"
echo "  $SUMMARY"
echo
echo "Generated HTML files:"
echo "  $OUTDIR/html/"
