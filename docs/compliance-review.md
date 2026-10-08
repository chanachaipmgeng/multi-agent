# Compliance review pack (D4.8 / E15)

**Status:** prep complete — **blocked on legal sign-off** (DECISION-3, DECISION-9).  
Do **not** invent DPA parties, residency regions, or retention overrides. Fill blanks after review.

## 1. Data sent to external LLM providers

When `LLM_MODE=cloud` (OpenRouter / configured providers), agents may send:

| Category | Examples | Mitigation already in platform |
|---|---|---|
| Source code from workspace | feature diffs, test files | `project-standards.md`, `.agentignore`, gitleaks in sandbox (D4.2) |
| Issue / MR text | titles, bodies, labels | webhook redaction of tokens in attrs |
| Tool outputs / logs | test failures, shell snippets | Promtail + OTel redaction (`glpat-`, `sk-`, `Bearer `) |
| Never intentional | `.env`, API keys, private keys | ignore files + gitleaks; audit attrs redacted in adapter |

**Local path:** `make up-local-free` keeps inference on `inference-ollama` (no OpenRouter). Use for `confidential` / `restricted` once DECISION-3 routes by `data_classification`.

## 2. Data classification (DECISION-3)

| Class | Intended LLM path | Pilot assignment (fill) |
|---|---|---|
| `internal` | Cloud provider OK with DPA | _______________ |
| `confidential` | On-prem / local Ollama only | _______________ |
| `restricted` | On-prem only; no outbound code | _______________ |

OpenRouter / vendor **DPA signed?** ☐ yes · ☐ no · date: ________ · party: ________

## 3. Retention (DECISION-9 design defaults)

| Store | Design default | Enforced in compose? |
|---|---|---|
| `audit_events` DB | 1 year (append-only) | trigger + grants; export → MinIO object lock (`make audit-export`) |
| Audit object store | 1 year WORM | GOVERNANCE 365d on `emaw-audit` (prep) |
| Logs (Loki) | 30 days | `retention_period: 720h` in `observability/loki-config.yaml` |
| Metrics (Prometheus) | 90 days | `PROMETHEUS_RETENTION=90d` |
| Artifacts (MinIO `emaw-artifacts`) | 90 days | ILM in `scripts/minio-init.sh` |
| Episodic / session | 30–90 days, redacted | Hermes profile policy — confirm at go-live |

**PDPA / ISO override?** ☐ none · ☐ change to: ________ (update Loki/Prom env + re-export policy)

## 4. Redaction inventory (D4.2 — already shipped)

- Adapter: `queue-adapter/app/redaction.py` (Telegram notify, audit attrs, GitLab traces)
- Promtail pipeline + OTel transform (see `observability/`)
- Sandbox: gitleaks binary mount + template pre-commit

## 5. Legal checklist (sign here)

| Item | Owner | Done |
|---|---|---|
| DPA with LLM cloud vendor (or approve local-only) | Legal | ☐ |
| PDPA / residency statement for pilot data | Legal | ☐ |
| Confirm retention table above | Legal + Ops | ☐ |
| Approve Telegram ops chat logging | Security | ☐ |
| Approve public webhook hostname under Cloudflare WAF | Security | ☐ |

## 6. After sign-off

1. Record DECISION-3 / 9 outcomes in `docs/decisions.md` (no invented values).
2. If retention differs, set `PROMETHEUS_RETENTION` and Loki `retention_period`, recreate observability.
3. Mark D4.8 ✅ in `docs/phase4-exit-criteria.md`.
