#!/usr/bin/env bash
set -euo pipefail

# Render HTML annotations for all JSON/JSONL files in a corpus directory.
#
# English vocabularies:
#   P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR
#
# French vocabularies:
#   P66 9SD 8HQ B9M 27X BVM QX8
#
# Usage:
#   bash tests/smoke/render_html_annotation.sh [CLI] [TEXT_ROOT] [OUTDIR] [RENDERER]
#
# Arguments:
#   CLI       path to loterre_cli.py
#   TEXT_ROOT directory containing input JSON/JSONL corpus files
#   OUTDIR    output directory
#   RENDERER  path to loterre_html_renderer.py
#
# Example:
#   bash tests/smoke/render_html_annotation.sh \
#     ./src/loterre_cli.py \
#     data/jsonl \
#     ./html_outputs \
#     ./src/loterre_html_renderer.py

CLI="${1:-./src/loterre_cli.py}"
TEXT_ROOT="${2:-data/jsonl}"
OUTDIR="${3:-./html_outputs}"
RENDERER="${4:-./src/loterre_html_renderer.py}"

BASE_URL="${BASE_URL:-https://www.loterre.fr/ark:/}"

mkdir -p "$OUTDIR/json" "$OUTDIR/html"

SUMMARY="$OUTDIR/html_generation_summary.tsv"
echo -e "dict_id\tstatus\ttext_file\tjson_file\thtml_file" > "$SUMMARY"

run_one() {
  local text_file="$1"
  local file_name stem dict_id
  file_name="$(basename "$text_file")"
  stem="${file_name%.*}"
  dict_id="$stem"

  echo
  echo "== ${dict_id} =="

  local json_file="$OUTDIR/json/${dict_id}.json"
  local html_file="$OUTDIR/html/${dict_id}.html"

  if python3 "$CLI" annotate \
      --dict-id "$dict_id" \
      --text "$text_file" \
      --silent > "$json_file"; then

    python3 "$RENDERER" render \
      --input "$json_file" \
      --gold "$text_file" \
      --out "$html_file" \
      --title "Annotation Loterre — ${dict_id}" \
      --base-url "$BASE_URL"

    echo "OK"
    echo "  text: $text_file"
    echo "  json: $json_file"
    echo "  html: $html_file"

    echo -e "${dict_id}\tok\t${text_file}\t${json_file}\t${html_file}" >> "$SUMMARY"
  else
    echo "ERROR: engine failed for ${dict_id}" >&2
    echo -e "${dict_id}\terror\t${text_file}\t${json_file}\t${html_file}" >> "$SUMMARY"
  fi
}

echo "HTML annotation generation"
echo "CLI:       $CLI"
echo "TEXT_ROOT: $TEXT_ROOT"
echo "OUTDIR:    $OUTDIR"
echo "RENDERER:  $RENDERER"
echo "BASE_URL:  $BASE_URL"

mapfile -t corpus_files < <(find "$TEXT_ROOT" -maxdepth 1 -type f \( -name '*.jsonl' -o -name '*.json' \) | sort)
if [[ ${#corpus_files[@]} -eq 0 ]]; then
  echo "WARNING: aucun fichier .json/.jsonl trouvé dans $TEXT_ROOT" >&2
fi
for text_file in "${corpus_files[@]}"; do
  run_one "$text_file"
done

echo
echo "Summary:"
echo "  $SUMMARY"
echo
echo "Generated HTML files:"
echo "  $OUTDIR/html/"
