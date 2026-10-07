# hermes-data/ — one profile per agent

Each sub-directory is the Hermes **data dir** (`HERMES_HOME` / `/opt/data`) for one role
(design §4.1). Layout matches Hermes Agent **v0.21.5** (see `docs/hermes-capability-check.md`).

| Path | In git? | Purpose |
|---|---|---|
| `SOUL.md` | yes | Primary agent identity (slot #1 in Hermes system prompt) |
| `AGENT.md` | yes | Role policy — layer 2 of the rule hierarchy (do / never-do) |
| `config.yaml` | yes | Real Hermes config: `model`, `terminal`, `approvals`, `worktree`, `skills.auto_load`, `database`, optional `mcp_servers` |
| `.env` | **no** | Runtime secrets (`TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`, `GITLAB_TOKEN`, `API_SERVER_KEY`, …) — materialised from `./secrets/*` at container start |
| `skills/emaw/<skill>/SKILL.md` | generated | Promoted from `skills/` by `make skills-sync` (E13 — never edit here) |
| `memory/` / `sessions/` / `logs/` | no | Runtime state |

## Terminal backend (DECISION-14)

- **Compose agents profile:** `terminal.backend: local` — the Hermes container *is* the sandbox (`cap_drop: ALL`, no `docker.sock`).
- **Host / WSL2 Ubuntu Phase 0:** `hermes config set terminal.backend docker` and use `nousresearch/hermes-sandbox:desktop`.

## Secrets

Do not put API keys in `config.yaml`. Use UPPER_SNAKE in `.env` (Hermes routes `hermes config set OPENROUTER_API_KEY …` there automatically). Compose injects them from Docker secrets — see `scripts/hermes-configure.sh` and `docker-compose.yml`.

## Phase 0 vs Phase 3

Phase 0–2 could run a single agent; **Phase 3** runs all six profiles as separate compose
services, each with an `adapter-<role>` sidecar reading `stream:<role>`.

Local-free: mount `config.local-free.yaml` (all six agents → shared `inference-ollama`).
Each local-free config sets `model.ollama_num_ctx: 65536` (Hermes ≥0.21 minimum);
compose also sets `OLLAMA_CONTEXT_LENGTH=65536` on `inference-ollama` (DECISION-15).
