#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

CLI="${1:-./src/loterre_cli.py}"
OUTDIR="${2:-./outputs_predictions}"
TMP=`mktemp .XXXXXXXXXXX` 

O="$OUTDIR$TMP"
mkdir -p "$O"

function annotate_fr () {

  for code in P66 9SD 8HQ B9M 27X BVM QX8 ; do
    echo
    echo "== Annotation FR basée sur ${code} =="

    # pas de pipe stdin : le --config fournit déjà "text:", le moteur ne lit
    # jamais stdin ici (cat | ... causerait un SIGPIPE sous pipefail).
    python3 "$CLI" annotate \
      --config "configs/${code}_fr_auto_profile.yaml" \
      --out "$O/${code}_fr_annotation.md"
  done
}

function annotate_en () {

  for code in P66 9SD 8HQ B9M 27X BVM QX8 3JP JVR ; do
    echo
    echo "== Annotation EN basée sur ${code} =="

    # pas de pipe stdin : le --config fournit déjà "text:", le moteur ne lit
    # jamais stdin ici (cat | ... causerait un SIGPIPE sous pipefail).
    python3 "$CLI" annotate \
      --config "configs/${code}_en_auto_profile.yaml" \
      --out "$O/${code}_en_annotation.md"
  done
}

annotate_en
annotate_fr