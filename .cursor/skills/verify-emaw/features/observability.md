# Observability

Operators confirm Prometheus scrapes platform metrics and Grafana shows the four EMAW dashboards.

## Sub-features

- `prometheus-ready` — `/-/healthy` on `:9090`.
- `alertmanager-ready` — `/-/healthy` on `:9093`.
- `targets` — `webhook-gateway` appears among active targets.
- `dashboards` — Grafana search lists EMAW Operations / Agents / Cost / Security.

## How to get to it (user POV)

- `make up-observability`
- Open Grafana at `http://127.0.0.1:3000` (default `emaw` / `emaw-grafana-dev`).
- Open Prometheus at `http://127.0.0.1:9090/targets`.

## Driving it with verify-emaw

Preconditions:

- Observability profile containers are up.

- **Drive.** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive observability`.
- **Proof.** Evidence includes `prometheus-targets.json` mentioning `webhook-gateway` and `grafana-search.json` containing `EMAW Operations` and `EMAW Security`.

## Gotchas

- `cloudflared` target is expected **down** without `--profile ingress`.
- Grafana password may be overridden in `.env` (`GRAFANA_ADMIN_PASSWORD`); update the helper env if login fails.
