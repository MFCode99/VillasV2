#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/home/nunogouveia/villas-v2
PENDING_DIR="$APP_DIR/updates/pending"
ARCHIVE="$PENDING_DIR/payload.tar.gz"
MANIFEST="$PENDING_DIR/manifest.json"
WORK_DIR=$(mktemp -d /tmp/villas-v2-update.XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

test -f "$ARCHIVE"
test -f "$MANIFEST"
if tar -tzf "$ARCHIVE" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then
  echo 'Pacote com caminhos inválidos.' >&2
  exit 1
fi
tar -xzf "$ARCHIVE" -C "$WORK_DIR"
test -d "$WORK_DIR/app"
test -d "$WORK_DIR/frontend/dist"

cp -a "$WORK_DIR/app/." "$APP_DIR/app/"
if test -d "$WORK_DIR/migrations"; then cp -a "$WORK_DIR/migrations/." "$APP_DIR/migrations/"; fi
if test -f "$WORK_DIR/alembic.ini"; then cp "$WORK_DIR/alembic.ini" "$APP_DIR/alembic.ini"; fi
rm -rf "$APP_DIR/frontend/dist"
mkdir -p "$APP_DIR/frontend/dist"
cp -a "$WORK_DIR/frontend/dist/." "$APP_DIR/frontend/dist/"

cd "$APP_DIR"
if test -x .venv/bin/alembic; then .venv/bin/alembic upgrade head; fi
mkdir -p updates
mkdir -p updates/history
if test -f updates/current.json; then
  CURRENT_VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("version", "previous"))' updates/current.json 2>/dev/null || echo previous)
  cp updates/current.json "updates/history/${CURRENT_VERSION}.json"
fi
python3 - "$MANIFEST" "$WORK_DIR/applied-manifest.json" <<'PY'
import json, sys
from datetime import datetime, timezone
source, target = sys.argv[1:]
with open(source, encoding='utf-8') as handle:
    value = json.load(handle)
value['installedAt'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
with open(target, 'w', encoding='utf-8') as handle:
    json.dump(value, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
PY
cp "$WORK_DIR/applied-manifest.json" updates/current.json
cp "$WORK_DIR/applied-manifest.json" "updates/history/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$WORK_DIR/applied-manifest.json").json"
rm -rf "$PENDING_DIR"
systemctl restart villas-v2
