---
name: switch-context
description: Phase 1–2 single-agent helper — map [Frontend]/[Backend]/[Ops] tags to projects.yaml cwd + rulebook.
version: 0.1.0
metadata:
  hermes:
    tags: [emaw, routing]
    category: emaw
    owner: coordinator
    phase: 2
    status: placeholder
    note: >
      With one Hermes profile per role (Phase 3), routing is done by the coordinator + queue
      streams; this skill remains useful only for a single-agent Phase 1–2 install.
---

# Skill: switch-context (Phase 2)

Placeholder — `[Frontend]` / `[Backend]` tag → change cwd to the project in `projects.yaml`, read its `project-standards.md`, confirm with the project name and one rule just read.

**Phase 3 note:** Prefer separate Hermes profiles / compose services instead of switch-context.
