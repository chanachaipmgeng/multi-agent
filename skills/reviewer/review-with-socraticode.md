---
name: review-with-socraticode
description: Deep review via SocratiCode CLI/MCP on git-diff files only; hand patches to the owning dev agent.
version: 0.1.0
metadata:
  hermes:
    tags: [emaw, review, socraticode]
    category: emaw
    owner: reviewer
    phase: 2
    status: placeholder
    blocked_on: DECISION-6 SocratiCode license + SECRET_SOCRATICODE_KEY
---

# Skill: review-with-socraticode (Phase 2)

Placeholder — `socraticode review $(git diff --name-only origin/main...HEAD)`; proposed `--fix` patches are handed back to the dev agent, never applied by the reviewer.

Enable `mcp_servers.socraticode` in `hermes-data/reviewer/config.yaml` after license confirmation.
