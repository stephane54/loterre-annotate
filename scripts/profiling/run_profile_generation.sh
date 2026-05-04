#!/usr/bin/env bash
set -euo pipefail

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./configs}"


for code in P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR; do
  echo "== Génération auto-profile pour $code (en) =="
  python "$CLI" \
    --text examples/texts/${code}_en.jsonl \
    --dict-id ${code}_en \
    --auto-profile \
    --lang en \
    --yaml-out "$OUTDIR/${code}_en_auto_profile.yaml" \
    > "$OUTDIR/${code}_en_auto_profile.json"
done

for code in P66 9SD 8HQ B9M 27X BVM QX8; do
  echo "== Génération auto-profile pour $code (fr) =="
  python "$CLI" \
    --text examples/texts/${code}_fr.jsonl \
    --dict-id ${code}_fr \
    --auto-profile \
    --lang fr \
    --yaml-out "$OUTDIR/${code}_fr_auto_profile.yaml" \
    > "$OUTDIR/${code}_fr_auto_profile.json"
done