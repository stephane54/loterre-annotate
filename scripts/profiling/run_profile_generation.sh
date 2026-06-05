#!/usr/bin/env bash
# Génère un profil YAML pour chaque dictionnaire trouvé dans DICTS_DIR.
#
# Découverte automatique : tous les fichiers {lang}_annot_{CODE}.jsonl
# présents dans DICTS_DIR sont traités.
#
# Si un fichier texte correspondant existe dans TEXTS_DIR
# (data/texts/{CODE}_{lang}.jsonl), il est inclus dans le YAML généré.
# Sinon, le champ text est laissé vide (le profil reste utilisable).
#
# Usage:
#   bash scripts/profiling/run_profile_generation.sh [DICTS_DIR] [OUTDIR] [ENGINE]
#
# Defaults:
#   DICTS_DIR = ./dictionary
#   OUTDIR    = ./configs
#   ENGINE    = ./src/loterre_engine_v9_cli.py
#   TEXTS_DIR = ./data/texts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

DICTS_DIR="${1:-./dictionary}"
OUTDIR="${2:-./configs}"
ENGINE="${3:-./src/loterre_engine_v9_cli.py}"
TEXTS_DIR="${TEXTS_DIR:-./data/texts}"

mkdir -p "$OUTDIR"

ok=0
skipped=0
errors=0

for dict_file in "$DICTS_DIR"/*.jsonl; do
  fname="$(basename "$dict_file")"

  # Attend le format {lang}_annot_{CODE}.jsonl
  if [[ ! "$fname" =~ ^(en|fr)_annot_(.+)\.jsonl$ ]]; then
    continue
  fi

  lang="${BASH_REMATCH[1]}"
  code="${BASH_REMATCH[2]}"
  dict_id="${code}_${lang}"

  yaml_out="$OUTDIR/${dict_id}_auto_profile.yaml"
  json_out="$OUTDIR/${dict_id}_auto_profile.json"

  # Recherche d'un fichier texte correspondant (optionnel)
  text_arg=""
  text_file="$TEXTS_DIR/${dict_id}.jsonl"
  if [[ -f "$text_file" ]]; then
    text_arg="--text $text_file"
  fi

  echo "== $dict_id =="
  if python3 "$ENGINE" \
      --dict "$dict_file" \
      --lang "$lang" \
      $text_arg \
      --auto-profile \
      --yaml-out "$yaml_out" \
      > "$json_out" 2>/dev/null; then
    ok=$(( ok + 1 ))
  else
    echo "  ERREUR pour $dict_id" >&2
    errors=$(( errors + 1 ))
  fi
done

echo
echo "Terminé : $ok profils générés, $errors erreurs."
echo "Profils dans : $OUTDIR"
