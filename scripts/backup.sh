#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$ROOT" == "/home/nunogouveia/villas" ]]; then
  echo "Refusing to back up V1" >&2
  exit 1
fi

OUT_DIR="$($ROOT/.venv/bin/python scripts/backup_database.py)"
if [[ -d media ]]; then
  tar -czf "$OUT_DIR/media.tar.gz" media
fi
printf 'Backup written to %s\n' "$OUT_DIR"
