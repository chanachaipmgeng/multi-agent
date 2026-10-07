# Decision records (implementation)

Source of truth for design-level decisions remains the System Design Document §13.
This file records **implementation confirmations** made while closing DECISION-1 and follow-ons.

## DECISION-1 — Hermes capability (confirmed 2026-10-07)

| Item | Decision |
|---|---|
| Version | Hermes Agent **v0.21.5** (`nousresearch/hermes-agent@sha256:d4da4a40…`) |
| Orchestration | Keep **one container per agent** (O3). Hermes native profiles are supported but not required for Phase 0–2 |
| Non-interactive API | `POST /v1/runs` on port **8642** (`DISPATCHER=hermes_api`) |
| Non-interactive CLI | `hermes -p <profile> chat --oneshot -Q --query-file … -s <skill>` |
| Secrets | UPPER_SNAKE in `/opt/data/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `GITLAB_TOKEN`, `API_SERVER_KEY`, provider keys) |
| Identity files | `SOUL.md` (identity) + `AGENT.md` (role policy) under each profile data dir |
| Evidence | [`docs/hermes-capability-check.md`](hermes-capability-check.md) |

ASSUMPTION A1/A2 updated: key names in early drafts (`telegram.token`, `gitlab.base_url` as Hermes config keys, `hermes run --file`) are **obsolete**. Port 8642 is the API server; Hermes webhook is 8644 and unused by EMAW.

## DECISION-14 — Sandbox strategy for Hermes-in-container (decided)

| Option | Description | When |
|---|---|---|
| **(B) Recommended for local compose** | Hermes runs **inside** the compose container with `terminal.backend: local`. Isolation = container itself (`cap_drop: ALL`, `no-new-privileges`, scoped mounts, no `docker.sock`) | Windows Docker Desktop / any host without a separate Docker-in-Docker plan |
| (A) Host / WSL2 Ubuntu | Hermes installed on host; `terminal.backend: docker` + `nousresearch/hermes-sandbox:desktop` | Phase 0 checklist path on real Ubuntu WSL2 |
| (C) DinD sidecar | Dedicated `docker:dind` on `workers` network; Hermes `terminal.backend: docker` pointed at DinD | Phase 3 Linux VM if nested Docker is required |

Rationale for (B) now: this machine only has WSL distro `docker-desktop` (no Ubuntu), mounting `docker.sock` into workers violates platform policy P2/T4, and named volumes already solve the Windows WAL issue for `/opt/data`.

Revisit (A)/(C) when moving production to a Linux VM (DECISION-2 / Phase 3).
