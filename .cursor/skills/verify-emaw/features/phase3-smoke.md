# Phase 3 smoke

Operators confirm router, five role adapters, six Hermes agents, gateway, and MinIO are running together.

## Sub-features

- `containers` — named containers for router/adapters/agents are running.
- `deps` — gateway healthz and MinIO live.
- `compose` — compose files still validate.

## How to get to it (user POV)

- Run `make phase3-check` from the repo root after `make up-local-free` (or equivalent).

## Driving it with verify-emaw

Preconditions:

- Agents profile is up (`emaw-router`, `emaw-adapter-*`, `emaw-*` agents).

- **Smoke.** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive phase3-smoke`.
- **Proof.** `evidence/<RUN_ID>/phase3-check.txt` contains `phase3-check: PASSED`.

## Gotchas

- On Windows use Git Bash for the helper; `make phase3-check` also works if Make is available.
- A single stopped agent fails the whole check — fix that container before declaring Phase 3 green.
