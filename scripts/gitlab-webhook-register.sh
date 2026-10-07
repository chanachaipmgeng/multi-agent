#!/usr/bin/env bash
# D1.3 — create or update the GitLab project webhook pointing at the gateway.
#
#   scripts/gitlab-webhook-register.sh <project-id-or-path> <public-url>
#   e.g. scripts/gitlab-webhook-register.sh acme/backend-api https://webhook.example.com
#
# Env: GITLAB_BASE_URL (default https://gitlab.com), GITLAB_ADMIN_TOKEN (a *maintainer* PAT with scope `api`,
#      used once from the operator's shell — never stored in the repo or given to agents),
#      WEBHOOK_SECRET (default: ./secrets/gitlab_webhook_secret)
# Events: Issues, Pipeline, Job. SSL verification enabled. Idempotent: updates the hook if the URL exists.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${1:-}"; PUBLIC_URL="${2:-}"
[ -n "$PROJECT" ] && [ -n "$PUBLIC_URL" ] || { sed -n '2,10p' "$0"; exit 1; }
BASE="${GITLAB_BASE_URL:-https://gitlab.com}"
TOKEN="${GITLAB_ADMIN_TOKEN:-}"; [ -n "$TOKEN" ] || { echo "set GITLAB_ADMIN_TOKEN (maintainer PAT, scope api)"; exit 1; }
SECRET="${WEBHOOK_SECRET:-$(cat "$ROOT/secrets/gitlab_webhook_secret" 2>/dev/null || true)}"
[ -n "$SECRET" ] || { echo "no webhook secret (WEBHOOK_SECRET or secrets/gitlab_webhook_secret)"; exit 1; }
command -v jq >/dev/null || { echo "jq required"; exit 1; }

# URL-encode path_with_namespace for the API
ENC="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$PROJECT")"
HOOK_URL="${PUBLIC_URL%/}/webhook/gitlab"
API="$BASE/api/v4/projects/$ENC/hooks"

existing_id="$(curl -fsS -H "PRIVATE-TOKEN: $TOKEN" "$API" | jq -r --arg u "$HOOK_URL" '.[] | select(.url==$u) | .id' | head -1)"

payload=$(jq -n --arg url "$HOOK_URL" --arg token "$SECRET" '{
  url: $url, token: $token, enable_ssl_verification: true,
  issues_events: true, pipeline_events: true, job_events: true,
  push_events: false, merge_requests_events: false, note_events: false, tag_push_events: false,
  wiki_page_events: false, deployment_events: false, releases_events: false
}')

if [ -n "$existing_id" ]; then
  echo "updating hook $existing_id on $PROJECT → $HOOK_URL"
  curl -fsS -X PUT -H "PRIVATE-TOKEN: $TOKEN" -H 'Content-Type: application/json' -d "$payload" "$API/$existing_id" | jq '{id,url,issues_events,pipeline_events,job_events,enable_ssl_verification}'
else
  echo "creating hook on $PROJECT → $HOOK_URL"
  curl -fsS -X POST -H "PRIVATE-TOKEN: $TOKEN" -H 'Content-Type: application/json' -d "$payload" "$API" | jq '{id,url,issues_events,pipeline_events,job_events,enable_ssl_verification}'
fi

echo
echo "Next: GitLab → Settings → Webhooks → Test → 'Issues events' must return HTTP 200 (status 'ignored' or 'recorded' is fine for the test payload)."
echo "      Make sure the project is listed in config/projects.yaml with the real gitlab_project_id, otherwise the gateway answers 403."
