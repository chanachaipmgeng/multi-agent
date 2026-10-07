# syntax=docker/dockerfile:1.7
# E12 / D4.6 — pin base by digest (refresh: scripts/pin-digests.sh)
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f AS base

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
