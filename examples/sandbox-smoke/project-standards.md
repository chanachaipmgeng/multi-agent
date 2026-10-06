# Project Rulebook — sandbox-smoke

## 1. Tech Stack
- Python 3.12 standard library only; no third-party dependencies.

## 2. Security & Quality
- No secrets, no network calls. Files matching `.agentignore` are off-limits.

## 3. Testing
- `./test.sh` — exit 0 when green, exit 1 when red. `SMOKE_FORCE_FAIL=1 ./test.sh` simulates a failure.
- Self-heal at most 3 rounds, then report NEEDS_HUMAN.

## 4. Git Workflow
- Never commit to `main`; branches `fix/issue-<iid>` / `feat/<slug>`; Conventional Commits.

## 5. Human-in-the-Loop
- Any push goes through the coordinator's `human-approval-gate`.
