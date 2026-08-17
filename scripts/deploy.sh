#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$ROOT" == "/home/nunogouveia/villas" ]]; then
  echo "Refusing to deploy from V1 path" >&2
  exit 1
fi

source .venv/bin/activate
alembic upgrade head
sudo systemctl restart villas-v2
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8001/ready >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8001/ready >/dev/null
printf 'Deploy complete\n'
