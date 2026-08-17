#!/usr/bin/env bash
set -Eeuo pipefail
if [[ ${1:-} != "--backup" || -z ${2:-} ]]; then
  echo "Usage: restore.sh --backup /path/to/backup-dir --confirm" >&2
  exit 1
fi
BACKUP_DIR="$2"
CONFIRM="${4:-}"
if [[ "$CONFIRM" != "--confirm" ]]; then
  echo "Add --confirm to continue" >&2
  exit 1
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$ROOT" == "/home/nunogouveia/villas" ]]; then
  echo "Refusing to restore onto V1" >&2
  exit 1
fi
if [[ ! -f "$BACKUP_DIR/database.sql" ]]; then
  echo "Missing database.sql" >&2
  exit 1
fi
printf 'Restore guardrails passed for %s\n' "$BACKUP_DIR"