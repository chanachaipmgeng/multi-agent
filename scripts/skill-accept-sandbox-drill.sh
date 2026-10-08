#!/usr/bin/env bash
# Procedure drill for skill-acceptance on sandbox-smoke (≥3 rounds).
# Simulates the *mechanical* gates of dev-flow when LLM tool-calling is unreliable:
# work branch → code + test → ./test.sh green → commit → never push.
# Run inside emaw-dev-backend or any shell with /workspace/sandbox-smoke.
set -euo pipefail

ROOT="${SANDBOX_ROOT:-/workspace/sandbox-smoke}"
cd "$ROOT"
test -d .git || { echo "missing git repo in $ROOT"; exit 1; }

# Keep evidence JSON/logs out of commits
grep -q 'skill-accept' .gitignore 2>/dev/null || cat >> .gitignore <<'EOF'
.skill-accept-*.json
.skill-accept-drill-*.log
EOF

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="/tmp/skill-accept-drill-${stamp}.log"
: >"$log_file"
pass=0

run_round() {
  local n="$1" name="$2" impl="$3" test_src="$4"
  local branch="skill-accept/${stamp}-r${n}-${name}"
  echo "=== round $n ($name) ===" | tee -a "$log_file"
  git checkout -f main >/dev/null 2>&1
  git clean -fd >/dev/null 2>&1 || true
  git checkout -B "$branch" main
  # apply impl
  eval "$impl"
  eval "$test_src"
  if ! ./test.sh; then
    echo "FAIL round $n: test.sh not green" | tee -a "$log_file"
    git checkout -f main >/dev/null 2>&1
    return 1
  fi
  git add smoke/__init__.py tests/test_smoke.py
  git commit -m "feat: add ${name} (skill-accept drill r${n})"
  # ensure we did not push
  if git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
    echo "FAIL round $n: upstream set unexpectedly" | tee -a "$log_file"
    return 1
  fi
  echo "PASS round $n branch=$branch sha=$(git rev-parse --short HEAD)" | tee -a "$log_file"
  pass=$((pass + 1))
  git checkout -f main >/dev/null 2>&1
}

# Round 1 — subtract
run_round 1 subtract \
  'python3 - <<"PY"
from pathlib import Path
p = Path("smoke/__init__.py")
t = p.read_text(encoding="utf-8")
if "def subtract" not in t:
    p.write_text(t.rstrip() + "\n\n\ndef subtract(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8")
PY' \
  'python3 - <<"PY"
from pathlib import Path
p = Path("tests/test_smoke.py")
t = p.read_text(encoding="utf-8")
if "test_subtract" not in t:
    p.write_text(t.rstrip() + "\n\n    def test_subtract(self) -> None:\n        from smoke import subtract\n        self.assertEqual(subtract(5, 2), 3)\n", encoding="utf-8")
PY'

# Round 2 — multiply after merging r1 into main
git checkout -f main
git merge --ff-only "skill-accept/${stamp}-r1-subtract" || true

run_round 2 multiply \
  'python3 - <<"PY"
from pathlib import Path
p = Path("smoke/__init__.py")
t = p.read_text(encoding="utf-8")
if "def multiply" not in t:
    p.write_text(t.rstrip() + "\n\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n", encoding="utf-8")
PY' \
  'python3 - <<"PY"
from pathlib import Path
p = Path("tests/test_smoke.py")
t = p.read_text(encoding="utf-8")
if "test_multiply" not in t:
    p.write_text(t.rstrip() + "\n\n    def test_multiply(self) -> None:\n        from smoke import multiply\n        self.assertEqual(multiply(3, 4), 12)\n", encoding="utf-8")
PY'

git checkout -f main
git merge --ff-only "skill-accept/${stamp}-r2-multiply" || true

# Round 3 — review-code style gate: forced-fail rehearsal + restore green (self-heal stop condition)
echo "=== round 3 (review-code / self-heal gate) ===" | tee -a "$log_file"
branch="skill-accept/${stamp}-r3-review"
git checkout -B "$branch" main
set +e
SMOKE_FORCE_FAIL=1 ./test.sh
rc=$?
set -e
if [ "$rc" -ne 1 ]; then
  echo "FAIL round 3: expected exit 1 got $rc" | tee -a "$log_file"
else
  ./test.sh
  git commit --allow-empty -m "chore: review-code drill — forced-fail gate verified (skill-accept r3)"
  echo "PASS round 3 branch=$branch sha=$(git rev-parse --short HEAD) forced_fail=exit1 green=ok" | tee -a "$log_file"
  pass=$((pass + 1))
fi
git checkout -f main >/dev/null 2>&1
git merge --ff-only "$branch" || true

# Persist a copy of the log next to evidence JSON (gitignored)
cp -f "$log_file" "$ROOT/.skill-accept-drill-${stamp}.log" 2>/dev/null || true
echo "summary passes=${pass}/3 log=$log_file" | tee -a "$log_file"
[ "$pass" -ge 3 ]
