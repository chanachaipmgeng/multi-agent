#!/usr/bin/env bash
# Refresh image digests for Dockerfiles + compose defaults (D4.6 / E12).
#
# Usage:
#   scripts/pin-digests.sh           # dry-run (print digests)
#   scripts/pin-digests.sh --apply   # rewrite Dockerfiles + docker-compose.yml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

digest_of() {
  local ref="$1"
  local d
  d="$(docker image inspect "$ref" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
  if [ -z "$d" ] || [ "$d" = "<no value>" ]; then
    docker pull -q "$ref" >/dev/null
    d="$(docker image inspect "$ref" --format '{{index .RepoDigests 0}}')"
  fi
  echo "$d"
}

echo "resolving digests…"
PY_D="$(digest_of python:3.12-slim)"
REDIS_D="$(digest_of redis:7-alpine)"
PG_D="$(digest_of postgres:16-alpine)"
MINIO_D="$(digest_of minio/minio:latest)"
OLLAMA_D="$(digest_of ollama/ollama:latest)"
QDRANT_D="$(digest_of qdrant/qdrant:v1.17.0)"
CF_D="$(digest_of cloudflare/cloudflared:latest)"
LOKI_D="$(digest_of grafana/loki:3.3.2)"
TEMPO_D="$(digest_of grafana/tempo:2.6.1)"
OTEL_D="$(digest_of otel/opentelemetry-collector-contrib:0.114.0)"
PROMTAIL_D="$(digest_of grafana/promtail:3.3.2)"
PROM_D="$(digest_of prom/prometheus:v2.55.1)"
AM_D="$(digest_of prom/alertmanager:v0.27.0)"
GRAF_D="$(digest_of grafana/grafana:11.3.1)"

py_sha="${PY_D#*@}"
redis_sha="${REDIS_D#*@}"
pg_sha="${PG_D#*@}"
minio_sha="${MINIO_D#*@}"
ollama_sha="${OLLAMA_D#*@}"
qdrant_sha="${QDRANT_D#*@}"
cf_sha="${CF_D#*@}"
loki_sha="${LOKI_D#*@}"
tempo_sha="${TEMPO_D#*@}"
otel_sha="${OTEL_D#*@}"
promtail_sha="${PROMTAIL_D#*@}"
prom_sha="${PROM_D#*@}"
am_sha="${AM_D#*@}"
graf_sha="${GRAF_D#*@}"

printf '  python        %s\n' "$PY_D"
printf '  redis         %s\n' "$REDIS_D"
printf '  postgres      %s\n' "$PG_D"
printf '  minio         %s\n' "$MINIO_D"
printf '  ollama        %s\n' "$OLLAMA_D"
printf '  qdrant        %s\n' "$QDRANT_D"
printf '  cloudflared   %s\n' "$CF_D"
printf '  loki          %s\n' "$LOKI_D"
printf '  tempo         %s\n' "$TEMPO_D"
printf '  otel          %s\n' "$OTEL_D"
printf '  promtail      %s\n' "$PROMTAIL_D"
printf '  prometheus    %s\n' "$PROM_D"
printf '  alertmanager  %s\n' "$AM_D"
printf '  grafana       %s\n' "$GRAF_D"

if [ "$APPLY" -ne 1 ]; then
  echo "(dry-run — pass --apply to rewrite)"
  exit 0
fi

for df in queue-adapter/Dockerfile webhook-gateway/Dockerfile; do
  sed -i.bak -E "s#FROM python:3.12-slim(@sha256:[a-f0-9]+)?#FROM python:3.12-slim@${py_sha}#" "$df"
  rm -f "${df}.bak"
  echo "updated $df"
done

sed -i.bak \
  -e "s|\${REDIS_IMAGE:-[^}]*}|\${REDIS_IMAGE:-redis:7-alpine@${redis_sha}}|g" \
  -e "s|\${POSTGRES_IMAGE:-[^}]*}|\${POSTGRES_IMAGE:-postgres:16-alpine@${pg_sha}}|g" \
  -e "s|\${MINIO_IMAGE:-[^}]*}|\${MINIO_IMAGE:-minio/minio@${minio_sha}}|g" \
  -e "s|\${OLLAMA_IMAGE:-[^}]*}|\${OLLAMA_IMAGE:-ollama/ollama@${ollama_sha}}|g" \
  -e "s|\${QDRANT_IMAGE:-[^}]*}|\${QDRANT_IMAGE:-qdrant/qdrant:v1.17.0@${qdrant_sha}}|g" \
  -e "s|\${CLOUDFLARED_IMAGE:-[^}]*}|\${CLOUDFLARED_IMAGE:-cloudflare/cloudflared@${cf_sha}}|g" \
  -e "s|\${LOKI_IMAGE:-[^}]*}|\${LOKI_IMAGE:-grafana/loki:3.3.2@${loki_sha}}|g" \
  -e "s|\${TEMPO_IMAGE:-[^}]*}|\${TEMPO_IMAGE:-grafana/tempo:2.6.1@${tempo_sha}}|g" \
  -e "s|\${OTEL_COLLECTOR_IMAGE:-[^}]*}|\${OTEL_COLLECTOR_IMAGE:-otel/opentelemetry-collector-contrib:0.114.0@${otel_sha}}|g" \
  -e "s|\${PROMTAIL_IMAGE:-[^}]*}|\${PROMTAIL_IMAGE:-grafana/promtail:3.3.2@${promtail_sha}}|g" \
  -e "s|\${PROMETHEUS_IMAGE:-[^}]*}|\${PROMETHEUS_IMAGE:-prom/prometheus:v2.55.1@${prom_sha}}|g" \
  -e "s|\${ALERTMANAGER_IMAGE:-[^}]*}|\${ALERTMANAGER_IMAGE:-prom/alertmanager:v0.27.0@${am_sha}}|g" \
  -e "s|\${GRAFANA_IMAGE:-[^}]*}|\${GRAFANA_IMAGE:-grafana/grafana:11.3.1@${graf_sha}}|g" \
  docker-compose.yml
rm -f docker-compose.yml.bak
echo "updated docker-compose.yml"
echo "done"
