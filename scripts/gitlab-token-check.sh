#!/usr/bin/env bash
# D1.2 / checklist #2 — verify every GitLab token in ./secrets has the minimum scopes and is not expiring.
#   scripts/gitlab-token-check.sh            (reads secrets/gitlab_token_*)
# Env: GITLAB_BASE_URL (default https://gitlab.com), MAX_DAYS_LEFT (default 14 → warn)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${GITLAB_BASE_URL:-https://gitlab.com}"
WARN_DAYS="${MAX_DAYS_LEFT:-14}"
command -v jq >/dev/null || { echo "jq required"; exit 1; }
rc=0

declare -A EXPECT=(
  [gitlab_token_readonly]="read_api"
  [gitlab_token_frontend]="read_api write_repository"
  [gitlab_token_backend]="read_api write_repository"
  [gitlab_token_ci]="read_api write_repository"
  [gitlab_token_qa]="read_api write_repository"
)

for name in "${!EXPECT[@]}"; do
  f="$ROOT/secrets/$name"
  if [ ! -s "$f" ]; then echo "  - $name: (empty) skip"; continue; fi
  token="$(cat "$f")"
  info="$(curl -fsS -H "PRIVATE-TOKEN: $token" "$BASE/api/v4/personal_access_tokens/self" 2>/dev/null)" || { echo "  ✘ $name: token rejected by $BASE"; rc=1; continue; }
  scopes="$(echo "$info" | jq -r '.scopes | join(" ")')"
  expires="$(echo "$info" | jq -r '.expires_at // "never"')"
  active="$(echo "$info" | jq -r '.active')"
  line="  $name: scopes=[$scopes] expires=$expires"
  # forbidden: full `api` / admin scopes (checklist #2)
  if echo " $scopes " | grep -qE ' (api|admin_mode|sudo) '; then echo "  ✘ $line → over-privileged (scope api/admin); use read_api + write_repository"; rc=1; continue; fi
  for want in ${EXPECT[$name]}; do
    echo " $scopes " | grep -q " $want " || { echo "  ✘ $line → missing scope $want"; rc=1; continue 2; }
  done
  [ "$active" = "true" ] || { echo "  ✘ $line → inactive/revoked"; rc=1; continue; }
  if [ "$expires" = "never" ]; then
    echo "  ! $line → no expiry; policy is 90-day rotation (set an expiry)"
  else
    days=$(( ( $(date -d "$expires" +%s) - $(date +%s) ) / 86400 ))
    if [ "$days" -lt 0 ]; then echo "  ✘ $line → EXPIRED"; rc=1
    elif [ "$days" -le "$WARN_DAYS" ]; then echo "  ! $line → expires in $days days — rotate (docs/runbooks/token-rotation.md)"
    else echo "  ✔ $line ($days days left)"; fi
  fi
done
exit $rc
