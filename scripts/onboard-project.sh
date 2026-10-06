#!/usr/bin/env bash
# D0.4 — onboard a pilot repository into the workspace.
#
#   scripts/onboard-project.sh <project-key> <git-url> [test-command]
#   e.g. scripts/onboard-project.sh backend-api git@gitlab.com:acme/backend-api.git "pytest -q"
#
# Clones into workspace/<key>, copies the rulebook/ignore templates when missing, then verifies
# the test command returns a usable exit code (checklist #7). Add the project to config/projects.yaml
# afterwards (the gateway refuses webhooks for unknown projects).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="${1:-}"; URL="${2:-}"; TEST_CMD="${3:-}"
[ -n "$KEY" ] && [ -n "$URL" ] || { sed -n '2,9p' "$0"; exit 1; }

DEST="$ROOT/workspace/$KEY"
TPL="$ROOT/workspace/_templates"

if [ -d "$DEST/.git" ]; then
  echo "workspace/$KEY already cloned — pulling"
  git -C "$DEST" pull --ff-only
else
  git clone "$URL" "$DEST"
fi

for f in .agentignore .socraticodeignore; do
  if [ ! -f "$DEST/$f" ]; then cp "$TPL/$f" "$DEST/$f"; echo "added $f"; else echo "kept existing $f"; fi
done
if [ ! -f "$DEST/project-standards.md" ]; then
  sed "s/<project-name>/$KEY/g" "$TPL/project-standards.md" > "$DEST/project-standards.md"
  echo "added project-standards.md (edit it — it is the rulebook every agent reads first)"
fi

# secrets must never be readable by agents
for pattern in '.env' '.env.*' '*.pem' '*.key' 'secrets.*' 'credentials.json'; do
  grep -qxF "$pattern" "$DEST/.agentignore" || echo "warning: .agentignore lacks '$pattern'"
done

if [ -n "$TEST_CMD" ]; then
  echo "→ verifying test command exit codes: $TEST_CMD"
  set +e
  (cd "$DEST" && bash -lc "$TEST_CMD" >/tmp/emaw-onboard-test.log 2>&1)
  rc=$?
  set -e
  case $rc in
    0) echo "  tests pass (exit 0) ✔";;
    1) echo "  tests FAIL (exit 1) — acceptable signal for self-heal, fix before go-live";;
    *) echo "  exit code $rc — command probably misconfigured (see /tmp/emaw-onboard-test.log)"; exit 1;;
  esac
fi

cat <<EOF

Next: add to config/projects.yaml
  - key: $KEY
    gitlab_project_id: <id>
    path_with_namespace: "<group>/$KEY"
    workspace_path: /workspace/$KEY
    default_worker: dev-backend | dev-frontend
    allowed_workers: [...]
    test_command: "${TEST_CMD:-<test command>}"
    opt_in_label: agent-ready
    auto_push_branches: []
    data_classification: internal | confidential | restricted
EOF
