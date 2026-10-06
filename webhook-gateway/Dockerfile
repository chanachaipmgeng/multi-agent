# syntax=docker/dockerfile:1.7
# TODO(E12, Phase 4): pin by digest, e.g. python:3.12-slim@sha256:<digest>
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 1000 emaw \
 && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin emaw

WORKDIR /srv/gateway

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

USER emaw
EXPOSE 8700

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8700/healthz || exit 1

CMD ["python", "-m", "app.main"]
