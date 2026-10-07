# syntax=docker/dockerfile:1.7
# TODO(E12, Phase 4): pin by digest
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 1000 emaw \
 && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin emaw \
 && mkdir -p /var/lib/queue-adapter/outbox && chown -R emaw:emaw /var/lib/queue-adapter

WORKDIR /srv/adapter
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

USER emaw
VOLUME ["/var/lib/queue-adapter"]

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD python -m app.health || exit 1

CMD ["python", "-m", "app.main"]
