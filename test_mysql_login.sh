#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/nunogouveia/villas-v2
set -a
source ./.env
set +a
mysql -h127.0.0.1 -u"$DB_APP_USER" -p"$DB_APP_PASSWORD" -e "SELECT 1;" villas_v2