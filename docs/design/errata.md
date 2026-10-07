# System Design v1.1 — implementation errata

Canonical design text: [`system-design-v1.1.md`](system-design-v1.1.md) (copied from the desktop design doc).

| Topic | Design said | Implementation |
|---|---|---|
| SocratiCode tools (A5) | `analyze_blast_radius`, `get_dependencies`, `socraticode review --fix` | Real MCP tools: `codebase_*` (index/search/symbol/impact/graph_*); no `--fix` CLI — reviewer proposes unified diff via handoff |
| DECISION-6 | Commercial key | Local AGPL + external Ollama/Qdrant (see `docs/decisions.md`) |
| D3.4 inline keyboard | Telegram inline Approve/Reject | DECISION-17: `y <nonce>` / `n <nonce>` + Hermes native terminal approvals |
| Routing ownership | Coordinator LLM routes everything | DECISION-16: Python `MODE=router` for rules 1/2/4; coordinator skill for rules 3/5 |
| Flow A reviewer apply | Reviewer may `--fix` then hand back | Reviewer never applies; handoff patch to owning dev agent |
| Phase 3 local-free | (not specified) | All 6 agents on shared `inference-ollama` (DECISION-15 updated) |
| Local Ollama context | (not specified) | Hermes ≥0.21 needs ≥64K — `OLLAMA_CONTEXT_LENGTH` + `model.ollama_num_ctx: 65536` |
| MinIO root password | Docker secret file | MinIO has no `*_FILE` support — root password via env; adapters SigV4 with root key locally |
| Redis `BLOCK 0` | (implied non-blocking) | Redis treats `BLOCK 0` as wait forever — router omits `block` for non-blocking reads |
| Claim idle (§10.3) | `CLAIM_MIN_IDLE` = 10 minutes for all | Workers keep **10 min**; **router** uses `CLAIM_MIN_IDLE_MS=30000` so pause-deferred PEL resumes quickly |
| Dashboard `:9119` | Bind + Cloudflare Access (Phase 4) | Hermes 0.21 refuses `0.0.0.0` without auth — **DECISION-18** basic auth via `HERMES_DASHBOARD_BASIC_AUTH_*` from `secrets/dashboard_password` |
| Image pins (E12) | Digest-pin base + service images | Dockerfiles + compose `${*_IMAGE:-…@sha256:…}`; `scripts/pin-digests.sh`; CI Trivy job |
| Observability logs | OTel Collector only | Promtail scrapes docker logs (redacted) → Loki; OTel Collector handles OTLP → Tempo + transform redaction |
| Gitleaks in sandbox | pre-commit in every worktree | Linux `tools/gitleaks` mounted into Hermes; template `.pre-commit-config.yaml` via onboard |
