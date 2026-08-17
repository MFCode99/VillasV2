#!/usr/bin/env bash
set -Eeuo pipefail
cd /home/nunogouveia/villas-v2
set -a
source ./.env
set +a
sudo mysql <<SQL
ALTER USER '${DB_APP_USER}'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '${DB_APP_PASSWORD}';
ALTER USER '${DB_APP_USER}'@'localhost' IDENTIFIED WITH mysql_native_password BY '${DB_APP_PASSWORD}';
ALTER USER '${DB_TEST_USER}'@'127.0.0.1' IDENTIFIED WITH mysql_native_password BY '${DB_TEST_PASSWORD}';
ALTER USER '${DB_TEST_USER}'@'localhost' IDENTIFIED WITH mysql_native_password BY '${DB_TEST_PASSWORD}';
SELECT user, host, plugin FROM mysql.user WHERE user LIKE 'villas_v2%';
SQL