# Pause control

Admins pause all agents via the internal control API, then resume — kill-switch path (E11).

## Sub-features

- `pause-all` — `POST /internal/control/pause` with Bearer + admin user id.
- `resume-all` — matching resume clears the pause.

## How to get to it (user POV)

- Call the internal API (coordinator / ops tooling) with `Authorization: Bearer <hermes_api_key>` and `X-EMAW-User-Id` of an admin in `config/rbac.yaml`.

## Driving it with verify-emaw

Preconditions:

- Gateway up; `secrets/hermes_api_key` set; `VERIFY_EMAW_USER_ID` is admin (default `987654321` matches example rbac).

- **Pause/resume.** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive pause-control`.
- **Proof.** `pause.json` and `resume.json` show HTTP success bodies; no leftover `pause.flag` after the drive.

## Gotchas

- Viewer users get 403 — not a product failure if you used the wrong user id.
- Always resume if a run crashes mid-pause (`verify-emaw.sh cleanup`).
