#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 -f /migrations/001_schema.sql
# psql quotes these variables as SQL string literals; passwords never enter SQL source.
psql -v ON_ERROR_STOP=1 \
  -v app_password="$DB_APP_PASSWORD" \
  -v ingest_password="$DB_INGEST_PASSWORD" <<'SQL'
ALTER ROLE edip_app PASSWORD :'app_password';
ALTER ROLE edip_ingest PASSWORD :'ingest_password';
SQL
