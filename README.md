# Enterprise Multi-Agent Workspace (`emaw-config`)

Platform code และ config ของ **Enterprise Multi-Agent Workspace** — ระบบ Multi-Agent บน
[Hermes Agent](https://github.com/NousResearch/hermes-agent) สำหรับงานพัฒนาซอฟต์แวร์อัตโนมัติและ
Incident Response: มนุษย์สั่งงานผ่าน Telegram, GitLab ยิง webhook ผ่าน Cloudflare Tunnel เข้า
Webhook Gateway, Coordinator มอบหมายงานให้ worker agents ที่ทำงานใน Docker sandbox และทุก action ที่มี
ผลกระทบสูงต้องผ่าน Human-in-the-Loop

สถานะ: **Phase 3 closed** · **Phase 4** D4.1 observability + D4.2 redaction/gitleaks + D4.5/D4.6 ✅ · org-blocked: DECISION-2/5/8/11
Hermes Agent **v0.21.5** · decisions: [`docs/decisions.md`](docs/decisions.md) · design: [`docs/design/system-design-v1.1.md`](docs/design/system-design-v1.1.md) ([errata](docs/design/errata.md))
Exit criteria: [`phase0`](docs/phase0-exit-criteria.md) · [`phase1`](docs/phase1-exit-criteria.md) · [`phase2`](docs/phase2-exit-criteria.md) · [`phase3`](docs/phase3-exit-criteria.md) · [`phase4`](docs/phase4-exit-criteria.md)

## Architecture (ย่อ)

```text
Telegram ──▶ coordinator ──▶ POST /internal/tasks ──▶ stream:tasks ──▶ router ──▶ stream:<role>
GitLab ─▶ Tunnel ─▶ Webhook Gateway ─────────────────────────────────────┘         │
                                          verify · dedupe · normalize · RBAC         ▼
                                                                    adapter-<role> → Hermes :8642
                                                                         │
                                                                    stream:results → router → handoffs / state
                                                                         ▼
                                                         PostgreSQL + MinIO artifacts + audit
```

Phase 3 (DECISION-16): `router` fans out; one `adapter-<role>` per worker; coordinator skills handle Telegram tags / HITL / kill switch.

หลักการ: Human-in-command · Sandbox by default · Least privilege · One role, one profile ·
Everything is auditable · Grow in phases

## Repository layout

| Path | What |
|---|---|
| `docker-compose.yml` | platform + `router` + 5 role adapters + MinIO; profiles `agents`, `ingress`, `onprem-llm`, `socraticode`, `single` (legacy) |
| `docker-compose.local-free.yml` | all 6 agents → `inference-ollama` (`make up-local-free`, DECISION-15) |
| `docker-compose.prod.yml` | Linux VM override (`make up-prod`) |
| `webhook-gateway/` | GitLab webhook + `/internal/*` control plane (tasks, approvals, pause/safe-mode) + RBAC |
| `queue-adapter/` | `MODE=router\|worker` — fan-out, HANDOFF parse, breaker, MinIO upload, `/metrics` |
| `db/migrations/` | Task Store schema: `tasks`, `handoffs`, `approvals`, `audit_events` |
| `config/projects.yaml` | project allowlist + routing |
| `config/policies/platform-policy.yaml` | never push `main`, HITL matrix, limits |
| `config/rbac.example.yaml` | copy to `config/rbac.yaml` (gitignored) — enforced on `/internal/*` |
| `hermes-data/<agent>/` | 6 profiles + `config.local-free.yaml` |
| `skills/` | Phase 0–3 procedures (incl. `route-task`, `fix-pipeline`, `write-e2e`, …) |
| `workspace/` | project clones (gitignored) + `_templates/` (`project-standards.md`, `.agentignore`, `.socraticodeignore`) + `.worktrees/` |
| `examples/sandbox-smoke/` | minimal pilot project whose `./test.sh` returns exit 0/1 correctly |
| `cloudflared/` | Named Tunnel config template + runbook (Phase 1, blocked on domain) |
| `scripts/`, `Makefile` | prereq check, SOPS secrets, migrate, Hermes configure, onboard repo, skill sync, test webhook, Phase 0 verifier, **tunnel setup/status, GitLab webhook register, token scope check** |
| `docs/` | exit criteria, `secrets.md`, `environments.md`, `skill-acceptance.md`, `runbooks/{tunnel,token-rotation,restore,agent-stuck,rollback-mr}.md` |
| `.env.example`, `.sops.yaml`, `.gitleaks.toml`, `.agentignore`, `.pre-commit-config.yaml` | secrets & hygiene |

## Quick start (รันในเครื่อง / Run locally)

ต้องมี: Docker + Compose v2, Python 3.12, (sops + age สำหรับ secrets จริง) — ตรวจด้วย `make prereqs`

```bash
git clone https://github.com/chanachaipmgeng/multi-agent.git && cd multi-agent

# 1) secrets — dev shortcut (plaintext .env → ./secrets/*). Production path: make secrets-init / secrets-encrypt / secrets-decrypt
cp .env.example .env && make secrets-dev

# 2) platform stack (router + per-role adapters + MinIO)
cp config/rbac.example.yaml config/rbac.yaml
make up                                  # redis + postgres + gateway + router + adapters + minio
curl -s localhost:8700/readyz

# 3) sample webhook → router fans out to stream:<role>
make webhook-test                        # → queued → router → stream:dev-frontend
docker compose exec postgres psql -U emaw -c 'select task_id,type,state,assigned_to from tasks'

# 4) Hermes — cloud OR local-free (all 6 agents on Ollama)
make hermes-seed && make skills-sync
# make up-agents
# Local-free (stop any Phase 2 single-adapter stack first):
#   make down && make up-local-free && make local-llm-pull
#   make local-free-check && make phase3-check && make webhook-test
# Needs ≥64K Ollama context (DECISION-15); see docs/phase3-exit-criteria.md live-drill log.

# 5) tests
make test                                # gateway + adapter unit tests (incl. hermes_api dispatcher)
make test-integration                    # +3 against Postgres (TEST_DATABASE_URL=...)
make verify-phase0                       # Phase 0 exit-criteria self-check
```

Phase 1 (ต้องมีโดเมน Cloudflare + GitLab จริง): กรอก [`config/org.yaml`](config/org.yaml) →
`make tunnel-setup HOST=webhook.<org>.com SERVICE=1` →
`make gitlab-webhook PROJECT=<group>/<repo> URL=https://webhook.<org>.com` → `make gitlab-token-check` →
`make tunnel-status URL=https://webhook.<org>.com` — ดู [`docs/gitlab-setup.md`](docs/gitlab-setup.md)

Hermes (Phase 0): ดู [`docs/local-dev.md`](docs/local-dev.md) §4 และ [`docs/phase0-runbook.md`](docs/phase0-runbook.md)

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
| Local-free all 6 agents (DECISION-15) | `docker-compose.local-free.yml`, `OLLAMA_CONTEXT_LENGTH=65536`, `model.ollama_num_ctx: 65536` |
| Phase 3 router fan-out (DECISION-16) | `queue-adapter` `MODE=router|worker`, HANDOFF YAML, MinIO SigV4 artifacts |
| Dashboard basic auth (DECISION-18) | `secrets/dashboard_password` → `HERMES_DASHBOARD_BASIC_AUTH_*` · `:9119` |
| Metrics §8.2 | adapter gauges/histograms · gateway `approval_latency_seconds` |
| Backup / restore (D4.5) | `make backup` · `make restore-drill BACKUP=…` · `docs/runbooks/restore.md` |
| Supply chain (D4.6) | digest-pinned images · `scripts/pin-digests.sh` · CI Trivy |
| Observability (D4.1) | `make up-observability` · Grafana :3000 · 4 dashboards · Alertmanager → Telegram |
| Redaction + sandbox gitleaks (D4.2) | adapter notify/audit · Promtail/OTel · `tools/gitleaks` mount |
| GitLab webhooks via Cloudflare Named Tunnel | `cloudflared/`, compose `ingress` profile, single path `/webhook/gitlab` |
| SocratiCode MCP (local AGPL) | `hermes-data/reviewer/config.yaml#mcp_servers` + `make up-socraticode` / `make up-local-free` |
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
