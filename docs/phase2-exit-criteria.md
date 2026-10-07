# Phase 2 — Multi-project + SocratiCode review: deliverables and exit criteria

Source: design §12 Phase 2, checklist §11.1 item **10** and §11.2 **E13** (skill acceptance).
Legend: ✅ in repo & verified · 🧪 in repo, needs real environment · ☐ manual / blocked on a decision.

## Deliverables

| ID | Deliverable | Where | Status |
|---|---|---|---|
| D2.1 | SocratiCode infra in compose (Ollama embeddings + Qdrant) | compose profile `socraticode`, `make up-socraticode`, `make socraticode-check`, `docs/local-dev.md` §3b | ✅ |
| D2.2 | Skill `review-with-socraticode` (diff-only, handoff patches, no apply) | `skills/reviewer/review-with-socraticode.md` → synced to reviewer profile | ✅ procedure · ☐ live ≥3 runs |
| D2.3 | Skill `deep-review` (`codebase_impact` + `codebase_graph_*`) | `skills/reviewer/deep-review.md` | ✅ procedure · ☐ live ≥3 runs |
| D2.4 | Skill `switch-context` for single-agent host | `skills/coordinator/switch-context.md` | ✅ procedure · ☐ optional rehearse |
| D2.5 | Reviewer MCP wiring (local AGPL, no API key) | `hermes-data/reviewer/config.yaml` `mcp_servers.socraticode` enabled | ✅ wired · 🧪 exercise on sandbox-smoke |
| D2.6 | Skill acceptance log (≥3 clean runs / skill before promote) | `docs/skill-acceptance.md` | ☐ fill after live drills |
| D2.7 | Local-free LLM path (optional) | `docker-compose.local-free.yml`, `make up-local-free` (DECISION-15) | ✅ |

## Checklist items in scope

| # | Item | Evidence | Remaining |
|---|---|---|---|
| 10 | SocratiCode on diff scope only | skills forbid full-repo scan; `.socraticodeignore` templates; tools `codebase_*` | ☐ live review on pilot MR diff |
| E13 | Skills versioned in git, synced one-way into profiles | `make skills-sync` / `skills-check`; CI sync step | ☐ ≥3 acceptance rows per Phase 2 skill |

## Exit criteria

> Reviewer รัน `review-with-socraticode` (+ `deep-review` เมื่อขอ) บน diff ของ pilot MR → ได้รายงาน 🛑/⚠️/💡 และ handoff patch ไป dev agent **โดย reviewer ไม่ apply/commit/push**;
> `make socraticode-check` เขียว; acceptance ≥ 3 รอบต่อ skill ใน `skill-acceptance.md`

| Test | Date | Result | Notes |
|---|---|---|---|
| `make socraticode-check` | | | no license needed |
| `make local-free-check` (optional) | | | DECISION-15 |
| `review-with-socraticode` on sandbox-smoke / pilot diff | | | MCP `codebase_index` + search |
| Handoff patch — reviewer worktree clean (no apply) | | | |
| `deep-review` via `codebase_impact` / graph | | | |
| MCP/infra down → `NEEDS_HUMAN` (no silent full-repo fallback) | | | |

## Still blocked / optional org inputs

| Decision | Fill in | Where |
|---|---|---|
| DECISION-6 | closed for **local AGPL**; commercial key only if you need a non-AGPL redistribute | `docs/decisions.md` |
| DECISION-11 | pilot paths (for real MR diffs) | `config/org.yaml`, `config/projects.yaml` |

## What Phase 2 does *not* include

- Permanent Cloudflare ingress (Phase 1 / DECISION-5)
- Playwright e2e / `write-e2e` (Phase 3)
- Commercial SocratiCode license (not required for local MCP)

## After this prep — Phase 0 live gate (ops)

**Before treating the platform as exited Phase 0**, run the ops gate in
[`phase0-runbook.md`](phase0-runbook.md) (Track B). For a free local LLM drill use
`make up-local-free` instead of OpenRouter keys (DECISION-15).
