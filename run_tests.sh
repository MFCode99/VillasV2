#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/nunogouveia/villas-v2
. .venv/bin/activate
set -a
source .env
set +a
DATABASE_URL="$DATABASE_URL_TEST" alembic upgrade head
pytest