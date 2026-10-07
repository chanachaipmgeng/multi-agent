# Enterprise Multi-Agent Workspace (`emaw-config`)

Platform code และ config ของ **Enterprise Multi-Agent Workspace** — ระบบ Multi-Agent บน
[Hermes Agent](https://github.com/NousResearch/hermes-agent) สำหรับงานพัฒนาซอฟต์แวร์อัตโนมัติและ
Incident Response: มนุษย์สั่งงานผ่าน Telegram, GitLab ยิง webhook ผ่าน Cloudflare Tunnel เข้า
Webhook Gateway, Coordinator มอบหมายงานให้ worker agents ที่ทำงานใน Docker sandbox และทุก action ที่มี
ผลกระทบสูงต้องผ่าน Human-in-the-Loop

สถานะ: **Phase 0 — Foundation ✅ · Phase 1 — Permanent Ingress & GitLab Integration (in progress)**
ดู [`docs/phase0-exit-criteria.md`](docs/phase0-exit-criteria.md) และ [`docs/phase1-exit-criteria.md`](docs/phase1-exit-criteria.md)
เอกสารออกแบบฉบับเต็ม: *Enterprise Multi-Agent Workspace — System Design Document v1.1*

## Architecture (ย่อ)

```text
Telegram ──▶ coordinator ──▶ Redis Streams ──▶ dev-frontend / dev-backend / reviewer / devops / qa
                 ▲                │                          │ (Docker sandbox, git worktree per task)
GitLab ─▶ Cloudflare Tunnel ─▶ Webhook Gateway (FastAPI) ─▶ stream:tasks ─▶ queue-adapter ─▶ Hermes
          POST /webhook/gitlab    verify · dedupe · normalize      │   enrich (job trace, redacted) · prompt · dispatch
                                                                   ▼
                                               PostgreSQL Task Store + audit (append-only)
```

Phase 1–2: `queue-adapter` ตัวเดียวส่งงานให้ Hermes ตัวเดียว (`CONSUMER_GROUP=hermes-single`);
Phase 3: adapter เป็น sidecar ต่อ role อ่าน `stream:<role>` และ coordinator เป็นผู้ route

หลักการ: Human-in-command · Sandbox by default · Least privilege · One role, one profile ·
Everything is auditable · Grow in phases

## Repository layout

| Path | What |
|---|---|
| `docker-compose.yml` | dev stack: `redis`, `postgres`, `webhook-gateway`; profiles `agents` (6 Hermes containers), `ingress` (cloudflared), `onprem-llm` (Ollama) |
| `webhook-gateway/` | FastAPI gateway — `X-Gitlab-Token` constant-time check, idempotency (`X-Gitlab-Event-UUID`), Task envelope, Redis Streams publisher, Postgres task store, `/metrics`; tests |
| `queue-adapter/` | Redis Streams consumer → Hermes dispatcher (`dryrun` / `http` / `hermes_cli`), GitLab job-trace enrichment with secret redaction, retry via `XAUTOCLAIM`, dead-letter, task state + audit, Telegram notice; tests |
| `db/migrations/` | Task Store schema: `tasks`, `handoffs`, `approvals`, `audit_events` (append-only), least-privilege roles |
| `config/projects.yaml` | project allowlist + routing (opt-in label `agent-ready`, `auto_push_branches: []`) |
| `config/policies/platform-policy.yaml` | platform policy layer 1: never push `main`, HITL matrix, limits, prompt-injection rule |
| `config/rbac.example.yaml` | coordinator RBAC (approver ≠ developer) — enforced Phase 3 |
| `hermes-data/<agent>/` | 6 profiles (`coordinator`, `dev-frontend`, `dev-backend`, `reviewer`, `devops`, `qa`): `AGENT.md`, `config.yaml`, `skills/`, `memory/` |
| `skills/` | version-controlled skills; Phase 0: `dev-flow`, `review-code`, `human-approval-gate` (+ placeholders) |
| `workspace/` | project clones (gitignored) + `_templates/` (`project-standards.md`, `.agentignore`, `.socraticodeignore`) + `.worktrees/` |
| `examples/sandbox-smoke/` | minimal pilot project whose `./test.sh` returns exit 0/1 correctly |
| `cloudflared/` | Named Tunnel config template + runbook (Phase 1, blocked on domain) |
| `scripts/`, `Makefile` | prereq check, SOPS secrets, migrate, Hermes configure, onboard repo, skill sync, test webhook, Phase 0 verifier, **tunnel setup/status, GitLab webhook register, token scope check** |
| `docs/` | `local-dev.md`, `secrets.md`, `gitlab-setup.md`, `phase0-exit-criteria.md`, `phase1-exit-criteria.md`, `runbooks/{tunnel,token-rotation}.md` |
| `.env.example`, `.sops.yaml`, `.gitleaks.toml`, `.agentignore`, `.pre-commit-config.yaml` | secrets & hygiene |

## Quick start (รันในเครื่อง / Run locally)

ต้องมี: Docker + Compose v2, Python 3.12, (sops + age สำหรับ secrets จริง) — ตรวจด้วย `make prereqs`

```bash
git clone https://github.com/chanachaipmgeng/multi-agent.git && cd multi-agent

# 1) secrets — dev shortcut (plaintext .env → ./secrets/*). Production path: make secrets-init / secrets-encrypt / secrets-decrypt
cp .env.example .env && make secrets-dev

# 2) platform stack
make up                                  # redis + postgres (+ schema) + webhook-gateway :8700 + queue-adapter (dryrun)
curl -s localhost:8700/readyz            # {"status":"ok","checks":{"redis":true,"task_store":true}}

# 3) fire a sample GitLab webhook and watch it flow
make webhook-test                        # Issue Hook (agent-ready, area:frontend) → {"status":"queued","assigned_to":"dev-frontend",...}
make webhook-test KIND=pipeline          # failed pipeline → devops
scripts/send-test-webhook.sh issue --bad-token    # → HTTP 401
make outbox                              # prompts the adapter built for Hermes (DISPATCHER=dryrun)
docker compose exec postgres psql -U emaw -c 'select task_id,type,state,assigned_to from tasks'

# 4) tests
make test                                # 37 gateway + 22 adapter unit tests
make test-integration                    # +3 against Postgres (TEST_DATABASE_URL=...)
make verify-phase0                       # Phase 0 exit-criteria self-check
```

Phase 1 (ต้องมีโดเมน Cloudflare + GitLab จริง): `make tunnel-setup HOST=webhook.<org>.com SERVICE=1` →
`make gitlab-webhook PROJECT=<group>/<repo> URL=https://webhook.<org>.com` → `make gitlab-token-check` →
`make tunnel-status URL=https://webhook.<org>.com` — ดู [`docs/gitlab-setup.md`](docs/gitlab-setup.md)

Hermes single agent (Phase 0, บน WSL2): ดู [`docs/local-dev.md`](docs/local-dev.md) §4 —
`hermes setup` → `TELEGRAM_ALLOWED_USERS=<id> make hermes-configure` → `make skills-sync` → `hermes gateway run`

## Gateway contract

`POST /webhook/gitlab` → `401` bad token · `403` project not in `projects.yaml` · `200 ignored`
(event not allowed / pipeline success / issue closed) · `200 duplicate` (same event UUID within 24 h) ·
`200 recorded` (issue without `agent-ready`) · `200 attached` (issue already has an active task) ·
`200 queued` (Task envelope written to `tasks` + `XADD stream:tasks`).

Task envelope (design §4.3): `task_id`, `trace_id`, `type`, `project`, `source`, `requester`,
`assigned_to`, `skill`, `inputs`, `constraints{token_budget,self_heal_limit,deadline_min}`,
`handoffs`, `state`, `created_at`.

## Decisions baked into this repo

| Decision | Where |
|---|---|
| Linux VM from Phase 3, WSL2 for dev now | `docs/local-dev.md`, compose is host-agnostic |
| Hybrid LLM (cloud + Ollama for sensitive repos) | `projects.yaml#data_classification/llm_backend`, `inference-ollama` profile, per-profile `local_endpoint` |
| GitLab webhooks via Cloudflare Named Tunnel | `cloudflared/`, compose `ingress` profile, single path `/webhook/gitlab` |
| SocratiCode via CLI + MCP | `hermes-data/reviewer/config.yaml#mcp_servers` (enabled Phase 2) |
| No auto-push for 2 months; approver ≠ developer; never push `main` | `projects.yaml#auto_push_branches: []`, `platform-policy.yaml`, `rbac.example.yaml`, every `AGENT.md` |
| Gateway built in-house: FastAPI + Redis Streams + PostgreSQL | `webhook-gateway/`, `queue-adapter/`, `db/` |
| Opt-in via label `agent-ready` | gateway `normalize()` → `recorded` without label |

## Security notes

ไม่มี secret จริงใน repo — ค่าทั้งหมดใน `.env.example` เป็น placeholder; `.env`, `secrets/*`, `*.age`
ถูก gitignore; gitleaks รันใน pre-commit และ CI; gateway ไม่ start ถ้าไม่มี webhook secret;
container ทุกตัว `read_only`, `cap_drop: ALL`, `no-new-privileges`, ไม่ mount `docker.sock`;
ทุก port bind `127.0.0.1` เท่านั้น

## License

MIT (platform code). Hermes Agent, SocratiCode and other third-party tools keep their own licenses.
