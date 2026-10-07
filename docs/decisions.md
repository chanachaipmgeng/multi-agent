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

## DECISION-6 — SocratiCode mode (decided 2026-10-07)

| Item | Decision |
|---|---|
| License for local EMAW | **AGPL-3.0 local-first** — no `SOCRATICODE_API_KEY` / commercial key required |
| Runtime | MCP via `npx -y socraticode` inside the reviewer container |
| Infra | Compose profile `socraticode`: `socraticode-ollama` (embeddings) + `socraticode-qdrant` |
| Env | `OLLAMA_MODE=external`, `QDRANT_MODE=external`, `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_MODEL=nomic-embed-text` |
| Tools used by skills | `codebase_index`, `codebase_search`, `codebase_symbol`, `codebase_impact`, `codebase_graph_*` |

AGPL note: fine for private/internal use of unmodified upstream. If you **modify** SocratiCode and offer it as a network service to others, comply with AGPL or obtain a commercial license.

Obsolete assumption: early drafts treated DECISION-6 as “blocked until SECRET_SOCRATICODE_KEY”.

## DECISION-15 — Local-free LLM mode (updated Phase 3)

| Item | Decision |
|---|---|
| Scope | **all 6 agents** (coordinator, dev-frontend, dev-backend, reviewer, qa, devops) |
| Provider | Hermes `model.provider: custom` → `http://inference-ollama:11434/v1` |
| Default model | `qwen2.5-coder:7b` (GPU 8–12 GB VRAM); override with `LOCAL_LLM_MODEL` |
| Context | Hermes ≥0.21 requires **≥64K** window — `OLLAMA_CONTEXT_LENGTH=65536` on `inference-ollama` + `model.ollama_num_ctx: 65536` in every `config.local-free.yaml` |
| Compose | `docker-compose.local-free.yml` + `make up-local-free` / `local-llm-pull` / `local-free-check` |
| Seed | `LLM_MODE=local` → `CUSTOM_API_KEY=ollama` in every agent `.env` |
| Trade-off | Shared inference queue on one GPU (no extra VRAM); quality/latency below cloud Sonnet; 64K ctx uses more RAM on CPU hosts (~2–3 GiB model residency observed) |

## DECISION-16 — Deterministic routing in Python router (Phase 3)

| Item | Decision |
|---|---|
| Router | `queue-adapter` with `MODE=router` consumes `stream:tasks`, fans out to `stream:<role>` |
| Workers | One `queue-adapter` sidecar per role (`MODE=worker`, `ROLE=<agent>`) → Hermes `:8642` |
| Rules 1/2/4 | Implemented in `queue-adapter/app/projects.py` (same semantics as gateway) |
| Rules 3/5 | Coordinator skill `route-task` (Telegram tags / ask user) → `POST /internal/tasks` |
| Handoff | Agents emit `HANDOFF:` YAML; router writes `handoffs` + re-enqueues; missing block from a dev worker → auto `reviewer` if allowed |

## DECISION-17 — HITL via y/n + nonce (deviation from D3.4 inline keyboard)

| Item | Decision |
|---|---|
| Telegram UX | Text `y <nonce>` / `n <nonce>` (and Hermes native terminal approvals) |
| Why | Hermes owns the Telegram update loop; gateway cannot reliably own callback queries |
| Persistence | `POST /internal/approvals` + `/internal/approvals/{nonce}/decide` + `approvals` table |
