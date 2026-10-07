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
| MinIO root password | Docker secret file | MinIO has no `*_FILE` support — root password via env; agent key via Docker secret |
