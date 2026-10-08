# Org unblock checklist (`config/org.yaml`)

Fill real values in [`config/org.yaml`](../config/org.yaml) — **do not invent** domains, Telegram IDs, GitLab paths, or VM hosts. This file lists which fields unlock Phase 4 / Flow C work.

## Field → decision map

| `org.yaml` path | Decision | Unlocks | Notes (examples only — replace with yours) |
|---|---|---|---|
| `org.domain` | DECISION-5 | D4.3 Access/WAF, Named Tunnel DNS, public URLs | e.g. your company apex domain |
| `org.cloudflare_account_owner` | DECISION-5 | Tunnel + Access policy ownership | Cloudflare account email / team |
| `org.webhook_hostname` | DECISION-5 | `WEBHOOK_PUBLIC_URL`, GitLab webhook target | usually `webhook.<domain>` |
| `org.agents_hostname` | DECISION-5 | Dashboard via Cloudflare Access | usually `agents.<domain>` |
| `org.grafana_hostname` | DECISION-5 | Grafana Access policy | usually `grafana.<domain>` |
| `hosting.production_vm` | DECISION-2 | `make up-prod` on Linux VM | on-prem hostname or cloud instance id/region |
| `hosting.hermes_version` / `hermes_image_digest` | DECISION-1 | already set | change only with capability re-check |
| `pilot_repos.*.gitlab_path` | DECISION-11 | Flow C, skill acceptance on **real** pilots | e.g. `group/frontend-app` |
| `pilot_repos.*.gitlab_project_id` | DECISION-11 | webhook routing / labels | numeric GitLab project id |
| `roles.admin` / `approver` / `developer` | DECISION-8 | Telegram RBAC, Flow C approvals | list of Telegram user ids → copy into `hermes-data/coordinator/rbac.yaml` |

## Also required outside `org.yaml`

| Item | Decision | Where |
|---|---|---|
| Compliance / data residency sign-off | DECISION-3 / 9 | legal — blocks **D4.8** |
| Vault + immutable audit export | infra DECISION | blocks **D4.4** (not a field in org.yaml today) |
| Live Telegram bot + allowlist | DECISION-8 | secrets (`TELEGRAM_*`) + `roles.*` above |
| Alertmanager Telegram chat | ops | `.env` `TELEGRAM_CHAT_ID` (bot token already seeded) |

## Suggested fill order

1. **DECISION-2** `hosting.production_vm` → provision Ubuntu 24.04 + Docker → `make up-prod`
2. **DECISION-5** domain + Cloudflare owner + hostnames → tunnel DNS + Access/WAF (**D4.3**)
3. **DECISION-8** Telegram user ids in `roles.*` → sync rbac → Flow C HITL
4. **DECISION-11** pilot `gitlab_path` + `gitlab_project_id` → onboard + skill acceptance on pilots

Until these are filled, keep placeholders as `"<to confirm>"` / `null` / `[]`. Sandbox skill-acceptance uses `examples/sandbox-smoke` and does **not** require DECISION-11.
