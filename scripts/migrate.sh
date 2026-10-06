#!/usr/bin/env bash
# Apply db/migrations/*.sql not yet recorded in schema_migrations.
# Usage: DATABASE_URL=postgresql://emaw:pw@localhost:5432/emaw scripts/migrate.sh
#    or: scripts/migrate.sh            (uses the compose postgres container via docker exec)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIGRATIONS="$ROOT/db/migrations"

if [ -n "${DATABASE_URL:-}" ]; then
  psql_cmd() { psql -v ON_ERROR_STOP=1 -qAt "$DATABASE_URL" "$@"; }
else
  psql_cmd() { docker compose -f "$ROOT/docker-compose.yml" exec -T postgres psql -v ON_ERROR_STOP=1 -qAt -U emaw -d emaw "$@"; }
fi

psql_cmd -c "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());"

applied=0
for f in $(ls "$MIGRATIONS"/*.sql | sort); do
  version="$(basename "$f" .sql)"
  if [ "$(psql_cmd -c "SELECT 1 FROM schema_migrations WHERE version='$version'")" = "1" ]; then
    echo "skip   $version (already applied)"
    continue
  fi
  echo "apply  $version"
  psql_cmd < "$f"
  applied=$((applied+1))
done
echo "done — $applied migration(s) applied"
