# Org unblock checklist (`config/org.yaml`)

Fill real values in [`config/org.yaml`](../config/org.yaml) — **do not invent** domains, Telegram IDs, GitLab paths, or VM hosts. This file lists which fields unlock Phase 4 / Flow C work.

## Field → decision map

| `org.yaml` path | Decision | Unlocks | Next command |
|---|---|---|---|
| `org.domain` | DECISION-5 | D4.3 Access/WAF, Named Tunnel DNS | `make ingress-render` then tunnel DNS + Zero Trust |
| `org.cloudflare_account_owner` | DECISION-5 | Tunnel + Access policy ownership | apply `cloudflared/access-and-waf.md` |
| `org.webhook_hostname` | DECISION-5 | `WEBHOOK_PUBLIC_URL`, GitLab webhook | `make tunnel-status URL=https://…` |
| `org.agents_hostname` | DECISION-5 | Dashboard via Cloudflare Access | Access app in Zero Trust |
| `org.grafana_hostname` | DECISION-5 | Grafana Access policy | Access app in Zero Trust |
| `hosting.production_vm` | DECISION-2 | `make up-prod` on Linux VM | cron for `make audit-export` |
| `hosting.hermes_version` / `hermes_image_digest` | DECISION-1 | already set | change only with capability re-check |
| `pilot_repos.*.gitlab_path` | DECISION-11 | Flow C, skill acceptance on **real** pilots | `make onboard KEY=…` |
| `pilot_repos.*.gitlab_project_id` | DECISION-11 | webhook routing / labels | `make gitlab-webhook` |
| `roles.admin` / `approver` / `developer` | DECISION-8 | Telegram RBAC, Flow C approvals | copy into `hermes-data/coordinator/rbac.yaml` |

## Also required outside `org.yaml`

| Item | Decision | Where | Next command |
|---|---|---|---|
| OpenRouter (or vendor) API keys | ops | `SECRET_LLM_KEY_*` in `.env` | `make secrets-dev` → `make up-cloud` → `make dev-flow-live` |
| Compliance / data residency sign-off | DECISION-3 / 9 | legal — [compliance-review.md](compliance-review.md) | mark D4.8 after signatures |
| Vault (short-lived secrets) | infra DECISION | blocks full **D4.4** secrets path | audit export prep already: `make audit-export` |
| Live Telegram bot + allowlist | DECISION-8 | secrets (`TELEGRAM_*`) + `roles.*` | Flow C |
| Alertmanager Telegram chat | ops | `.env` `TELEGRAM_CHAT_ID` | recreate alertmanager |

## Suggested fill order

1. **LLM keys** → `make preflight` green for cloud → `make up-cloud` → `make dev-flow-live`
2. **DECISION-2** `hosting.production_vm` → Ubuntu 24.04 + Docker → `make up-prod`
3. **DECISION-5** domain + Cloudflare owner + hostnames → `make ingress-render` → tunnel DNS + Access/WAF (**D4.3**)
4. **DECISION-8** Telegram user ids in `roles.*` → sync rbac → Flow C HITL
5. **DECISION-11** pilot `gitlab_path` + `gitlab_project_id` → onboard + skill acceptance on pilots
6. **DECISION-3/9** legal → complete [compliance-review.md](compliance-review.md)

Until these are filled, keep placeholders as `"<to confirm>"` / `null` / `[]`. Sandbox drills use `examples/sandbox-smoke` and do **not** require DECISION-11.

## Local checks (no invent)

```bash
make preflight          # placeholders + dispatcher
make ingress-render     # fails until org.domain is real
make audit-export       # MinIO object-lock stand-in (Vault still pending)
```
