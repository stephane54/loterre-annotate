#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs_autoprofile_quality}"

mkdir -p "$OUTDIR"

for code in P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR; do
  echo "== Auto-profile en ${code} =="
  python3 "$CLI" \
    --text data/texts/${code}_en.jsonl \
    --dict-id  ${code}_en \
    --auto-profile \
    --yaml-out "$OUTDIR/${code}_en_auto_profile.yaml" \
    > "$OUTDIR/${code}_en.json"
done
echo

for code in P66 9SD 8HQ B9M 27X BVM QX8; do
  echo "== Auto-profile fr ${code} =="
  python3 "$CLI" \
    --text data/texts/${code}_fr.jsonl \
    --dict-id  ${code}_fr \
    --auto-profile \
    --yaml-out "$OUTDIR/${code}_fr_auto_profile.yaml" \
    > "$OUTDIR/${code}_fr.json"
done