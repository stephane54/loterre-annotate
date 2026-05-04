#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs}"
TMP=`mktemp .XXXXXXXXXXX` 

O="$OUTDIR$TMP"
mkdir -p "$O"

for code in P66 9SD 8HQ B9M 27X BVM QX8 ; do
  echo
  echo "== Annotation FR basée sur ${code} =="

  cat ../examples/texts/${code}_fr.jsonl | python "$CLI" \
    --config "configs/${code}_fr_auto_profile.yaml" \
    --out "$O/${code}_fr_annotation.md"
  python ./src/loterre_html_renderer.py --input "$JSON_OUT" --out "$HTML_OUT" --title "Annotation Loterre — ${DICT_ID}"

done

for code in P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR ; do
  echo
  echo "== Annotation EN basée sur ${code} =="

  cat ../examples/texts/${code}_en.jsonl | python "$CLI" \
    --config "configs/${code}_en_auto_profile.yaml" \
    --out "$O/${code}_en_annotation.md"
done
