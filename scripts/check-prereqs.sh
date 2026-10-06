#!/usr/bin/env bash
# D0.1 — verify the WSL2 / Linux host has everything Phase 0 needs.
# Usage: scripts/check-prereqs.sh      (exit 0 = ready, 1 = something missing)
set -uo pipefail

ok=0; missing=0
pass() { printf '  \033[32m✔\033[0m %s\n' "$1"; ok=$((ok+1)); }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; missing=$((missing+1)); }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

echo "== Core tooling =="
command -v git     >/dev/null && pass "git $(git --version | awk '{print $3}')"          || fail "git not found"
command -v docker  >/dev/null && pass "docker $(docker --version | awk '{print $3}' | tr -d ,)" || fail "docker not found (install Docker Desktop + WSL integration)"
docker compose version >/dev/null 2>&1 && pass "docker compose $(docker compose version --short)" || fail "docker compose v2 not available"
command -v python3 >/dev/null && pass "python3 $(python3 --version | awk '{print $2}')"   || fail "python3 not found"
command -v node    >/dev/null && pass "node $(node --version)"                             || fail "node not found (need v20+)"
command -v jq      >/dev/null && pass "jq"                                                 || warn "jq missing (used by scripts/send-test-webhook.sh)"
command -v curl    >/dev/null && pass "curl"                                               || fail "curl not found"

if command -v node >/dev/null; then
  major=$(node --version | sed 's/^v//' | cut -d. -f1)
  [ "$major" -ge 20 ] || fail "node >= 20 required (found v$major)"
fi

echo "== Secrets tooling (D0.6) =="
command -v sops       >/dev/null && pass "sops $(sops --version 2>/dev/null | head -1 | awk '{print $2}')" || fail "sops not found  → https://github.com/getsops/sops/releases"
command -v age        >/dev/null && pass "age"                                             || fail "age not found   → apt install age"
command -v age-keygen >/dev/null && pass "age-keygen"                                      || fail "age-keygen not found"
command -v gitleaks   >/dev/null && pass "gitleaks $(gitleaks version 2>/dev/null)"        || warn "gitleaks missing (pre-commit will install it; CI runs it anyway)"

echo "== Hermes Agent (D0.2) =="
if command -v hermes >/dev/null; then
  pass "hermes $(hermes --version 2>/dev/null | head -1)"
  backend=$(hermes config get terminal.backend 2>/dev/null || true)
  if [ "$backend" = "docker" ]; then pass "terminal.backend = docker (checklist #1)"; else fail "terminal.backend is '${backend:-unset}' — run: scripts/hermes-configure.sh"; fi
else
  warn "hermes CLI not installed on host (ok if you only run the compose stack) → https://github.com/NousResearch/hermes-agent"
fi

echo "== WSL2 specifics (skip on bare Linux) =="
if grep -qi microsoft /proc/version 2>/dev/null; then
  if grep -qs 'systemd=true' /etc/wsl.conf; then pass "systemd enabled in /etc/wsl.conf"; else warn "systemd=true missing in /etc/wsl.conf (needed for cloudflared service in Phase 1)"; fi
  docker info >/dev/null 2>&1 && pass "docker daemon reachable from WSL" || fail "docker daemon not reachable — enable WSL integration in Docker Desktop"
else
  pass "not WSL2 — nothing to check"
fi

echo
echo "$ok checks passed, $missing missing."
[ "$missing" -eq 0 ]
