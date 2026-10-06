#!/usr/bin/env bash
# Phase 0 exit-criteria self-check (design §12 Phase 0 + checklist #1, #3, #4, #5, #7).
# Automates what can be automated; prints the manual steps that remain.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; failed=1; }
manual() { printf '  \033[33m☐\033[0m %s\n' "$1"; }
failed=0

echo "== Checklist #1 — Docker sandbox =="
if command -v hermes >/dev/null; then
  [ "$(hermes config get terminal.backend 2>/dev/null)" = "docker" ] && pass "terminal.backend=docker" || fail "terminal.backend != docker"
else
  manual "install hermes and run scripts/hermes-configure.sh, then: hermes run \"id\" → must show sandbox uid"
fi
grep -q 'docker.sock' docker-compose.yml && fail "docker.sock is mounted in compose" || pass "no docker.sock mounted into any agent container"

echo "== Checklist #3 — .agentignore =="
for f in .agentignore workspace/_templates/.agentignore workspace/_templates/.socraticodeignore; do
  for p in '.env' '*.pem' 'secrets.*' 'credentials.json' 'node_modules/'; do
    grep -qxF "$p" "$f" || grep -qF "$p" "$f" || fail "$f lacks $p"
  done
done
pass ".agentignore / .socraticodeignore templates cover secrets + build output"
if command -v gitleaks >/dev/null; then
  gitleaks detect --no-banner --redact --config .gitleaks.toml --source . >/dev/null 2>&1 && pass "gitleaks: no secrets in repo" || fail "gitleaks found something"
else
  manual "gitleaks not installed locally (CI runs it)"
fi

echo "== Checklist #4 — Human-in-the-Loop =="
grep -q 'human-approval-gate' skills/_dev-common/dev-flow.md && pass "dev-flow routes push through human-approval-gate" || fail "dev-flow missing gate"
grep -q 'never_push_branches' config/policies/platform-policy.yaml && pass "platform policy forbids push to protected branches" || fail "platform policy missing"
manual "run dev-flow via Telegram, answer 'n' and let one request time out → verify nothing was pushed (git log origin)"

echo "== Checklist #5 — Project rulebook =="
for dir in workspace/*/; do
  key="$(basename "$dir")"
  [ "$key" = "_templates" ] && continue
  [ -f "workspace/$key/project-standards.md" ] && pass "workspace/$key/project-standards.md" || fail "workspace/$key has no project-standards.md"
done
[ -f workspace/_templates/project-standards.md ] && pass "rulebook template present"

echo "== Checklist #7 — tests return proper exit codes =="
(cd examples/sandbox-smoke && ./test.sh >/dev/null 2>&1); rc=$?
[ "$rc" -eq 0 ] && pass "examples/sandbox-smoke ./test.sh → exit 0" || fail "sandbox-smoke test exited $rc"
(cd examples/sandbox-smoke && SMOKE_FORCE_FAIL=1 ./test.sh >/dev/null 2>&1); rc=$?
[ "$rc" -eq 1 ] && pass "examples/sandbox-smoke ./test.sh (forced failure) → exit 1" || fail "forced failure exited $rc (expected 1)"

echo "== Gateway =="
if [ -x webhook-gateway/.venv/bin/pytest ]; then
  (cd webhook-gateway && .venv/bin/pytest -q >/tmp/emaw-gw-tests.log 2>&1) && pass "webhook-gateway unit tests" || fail "gateway tests failed (see /tmp/emaw-gw-tests.log)"
else
  manual "make test (gateway unit tests)"
fi

echo "== D0.6 — secrets =="
[ -f .env ] && pass ".env present (gitignored)" || manual "cp .env.example .env"
[ -f .env.enc ] && pass ".env.enc present" || manual "make secrets-encrypt"
git check-ignore -q .env && pass ".env is gitignored" || fail ".env NOT gitignored"
grep -q 'age1placeholder' .sops.yaml && manual ".sops.yaml still has placeholder recipient (scripts/secrets-init.sh)" || pass ".sops.yaml has a real recipient"

echo "== Exit criterion — 3 dev-flow runs =="
manual "run 3 dev-flow tasks through Telegram → each ends with a commit on a work branch, tests green, and a HITL prompt before any push (record in docs/phase0-exit-criteria.md)"

echo
[ "$failed" -eq 0 ] && echo "automated checks passed — complete the ☐ items manually" || { echo "some automated checks FAILED"; exit 1; }
