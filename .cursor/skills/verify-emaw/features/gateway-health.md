# Gateway health

Operators confirm the webhook gateway is alive and exporting Prometheus metrics before trusting webhooks or Grafana panels.

## Sub-features

- `healthz` returns a JSON health document on loopback `:8700`.
- `metrics` exposes Prometheus text including `webhook_received_total`.

## How to get to it (user POV)

- Open `http://127.0.0.1:8700/healthz` in a browser or curl.
- Open `http://127.0.0.1:8700/metrics` (scraped by Prometheus when observability is up).

## Driving it with verify-emaw

Preconditions:

- `verify-emaw.sh doctor` has run or gateway container is up.
- Port `8700` answers on `127.0.0.1`.

- **Health.** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive gateway-health`. Exit `0`. Evidence `gateway-healthz.json` exists and is non-empty JSON.
- **Metrics.** Same command writes `gateway-metrics.txt` containing `webhook_received_total`.
- **Proof.** Both files under `evidence/<RUN_ID>/` plus `run.log` line `PROOF gateway-health`.

## Gotchas

- Gateway must be the compose service `webhook-gateway`, not a random process on 8700.
- Empty metrics after a fresh start is OK as long as HELP/TYPE lines for webhook metrics exist.
