---
name: verify-emaw
description: Drive the EMAW platform (webhook-gateway, queue adapters, Hermes agents, observability) the way an operator would — HTTP + make smoke checks. Use when proving a change to compose, gateway, adapters, metrics, or Grafana; or when /poteto-mode needs a scripted green/red check.
---

# Verify EMAW (operator surface)

Primary surface: **HTTP services on loopback** + **Makefile smoke**. Secondary: Grafana UI (browser optional). This is not a single-page app — proofs are curl/make exit codes and JSON bodies, plus optional Grafana screenshot.

Never drive a stack you did not start for this run when isolation matters. The default compose project is shared on this host; prefer **doctor** before mutating, and use pause/resume only through documented internal API with a recorded RUN_ID.

## Launch

From repo root `d:\Project\myProject\multi-agent` (or `$EMAW_ROOT`):

```bash
# Platform + agents (local-free LLM path) — heavy; only if doctor fails on agents
make up-local-free

# Observability profile (Grafana/Prometheus/Alertmanager)
make up-observability
```

Ready when:

- `curl -fsS http://127.0.0.1:8700/healthz` returns JSON with ok status
- `scripts/phase3-check.sh` prints `phase3-check: PASSED` (agents path)
- `curl -fsS http://127.0.0.1:9090/-/healthy` and `http://127.0.0.1:9093/-/healthy` return OK (observability)

Teardown only what this RUN started. Prefer:

```bash
docker compose --profile observability stop grafana prometheus alertmanager loki tempo otel-collector promtail
# Do NOT `make down` unless the user asked — it stops the whole local stack.
```

## Doctor

```bash
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh doctor
```

Expect exit `0` and lines `OK ...`. Non-zero means do not drive mutations until fixed. Doctor is read-only (no pause, no webhook).

## Drive

Helper:

```bash
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive <feature-id>
# feature-id: gateway-health | phase3-smoke | observability | webhook-enqueue | pause-control
```

Or follow the matching file under `features/`. Prefer the helper — it writes evidence under `evidence/<RUN_ID>/`.

Harness = **curl + make + docker** (Windows: Git Bash). Grafana login defaults: `emaw` / `emaw-grafana-dev` (from `.env.example`).

## Evidence

Location: `.cursor/skills/verify-emaw/evidence/<RUN_ID>/` (gitignored).

Proof standards:

- Exercise the real operator path (`/healthz`, `/metrics`, `make phase3-check`, `/webhook/gitlab`, `/internal/control/*`).
- Capture **command + stdout + exit code** (and HTTP body for API calls).
- For mutations (webhook enqueue, pause): capture a **second read** (task list / redis key / metrics) showing the effect.
- Do not treat `dry-run` adapters as success for Hermes live dispatch unless the feature file says so.

## Cleanup

```bash
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh cleanup
```

Removes pause keys this run set and prints the evidence directory path. **Never deletes** `evidence/`. Does not kill shared platform containers unless `VERIFY_EMAW_STOP_OBS=1` (stops observability profile only).

## Helpers

| Command | Purpose |
|---|---|
| `verify-emaw.sh doctor` | Read-only health |
| `verify-emaw.sh drive <id>` | Run one feature recipe + evidence |
| `verify-emaw.sh cleanup` | Clear VERIFY_EMAW pause artifact; optional stop obs |

Feature map: [features/README.md](features/README.md).
