#!/usr/bin/env bash
set -euo pipefail

# Convert all prediction JSON/JSONL files from an input directory
# into JSONL files with expected_matches in an output directory.
#
# Usage:
#   bash scripts/prediction/bulk_results_to_expected.sh <input_dir> <output_dir>

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <input_dir> <output_dir>" >&2
  exit 2
fi

INPUT_DIR="$1"
OUTPUT_DIR="$2"
CONVERTER="scripts/prediction/results_to_expected_jsonl.py"

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "ERROR: input directory not found: $INPUT_DIR" >&2
  exit 1
fi

if [[ ! -f "$CONVERTER" ]]; then
  echo "ERROR: converter script not found: $CONVERTER" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

count=0
while IFS= read -r -d '' file; do
  rel="${file#"$INPUT_DIR"/}"
  rel_no_ext="${rel%.*}"
  out_file="$OUTPUT_DIR/${rel_no_ext}.jsonl"
  mkdir -p "$(dirname "$out_file")"

  echo "Converting: $file -> $out_file"
  python3 "$CONVERTER" --input "$file" --out "$out_file"
  count=$((count + 1))
done < <(find "$INPUT_DIR" -type f \( -name '*.json' -o -name '*.jsonl' \) -print0 | sort -z)

echo "Done. Converted $count file(s) into: $OUTPUT_DIR"
