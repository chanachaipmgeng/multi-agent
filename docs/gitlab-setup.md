# GitLab setup for Phase 1

Design §5.3, §7.3, checklist #2, #8, #9, E2.

## 1. Tokens (checklist #2)

Create **Project Access Tokens** (not personal tokens) per repo, role *Developer*, expiry ≤ 90 days:

| Secret file | Project | Scopes | Used by |
|---|---|---|---|
| `gitlab_token_readonly` | each pilot project (or a group token with `read_api`) | `read_api` | coordinator, reviewer, queue-adapter (job traces) |
| `gitlab_token_frontend` | frontend-app | `read_api`, `write_repository` | dev-frontend |
| `gitlab_token_backend` | backend-api | `read_api`, `write_repository` | dev-backend |
| `gitlab_token_ci` | both | `read_api`, `write_repository` | devops |
| `gitlab_token_qa` | both | `read_api`, `write_repository` | qa |

Phase 0–2 single agent: configure one writer token with `hermes config set gitlab.token` /
`gitlab.base_url` (`scripts/hermes-configure.sh` does it from `secrets/`). Verify with
`scripts/gitlab-token-check.sh` — it fails on scope `api`/admin and warns 14 days before expiry.

> The source guide used a PAT with scope `api`. The design lowers this to `read_api` +
> `write_repository` (checklist #2). Creating a MR through the REST API would need `api`, so the
> skills create the MR with GitLab **push options** instead, which only need push rights:
> `git push -u origin <branch> -o merge_request.create -o merge_request.target=main`
> `-o merge_request.remove_source_branch -o merge_request.title="…" -o merge_request.description="Closes #<iid> …"`.
> The MR URL is printed in the push output. (`resolve-issue` step 11 uses this.)

## 2. Protected branches (checklist #8)

Project → Settings → Repository → Protected branches: `main` and `release/*` →
*Allowed to push and merge: No one* (or Maintainers only), *Allowed to merge: Maintainers*,
require ≥ 1 approval (Settings → Merge requests → Approval rules). This is defense in depth
behind `platform-policy.yaml#git.never_push_branches`.

## 3. Webhook (checklist #9, E2)

```bash
export GITLAB_ADMIN_TOKEN=<maintainer PAT, scope api, used once from your shell>
scripts/gitlab-webhook-register.sh acme/frontend-app https://webhook.<org>.com
scripts/gitlab-webhook-register.sh acme/backend-api  https://webhook.<org>.com
```

Creates/updates the hook: URL `…/webhook/gitlab`, secret token = `secrets/gitlab_webhook_secret`,
events **Issues, Pipeline, Job** only, SSL verification on. Then *Test → Issues events* must
return **200** (the test payload has no `agent-ready` label → gateway answers `recorded`/`ignored`;
a `403` means the project id is not in `config/projects.yaml`, a `401` means the secret differs).

Labels to create in each project: `agent-ready` (opt-in), `area:frontend`, `area:backend`,
`area:ci`, `area:qa`.

## 4. Smoke test (exit criteria)

1. Open an issue with labels `agent-ready` + `area:frontend` → gateway `queued` → adapter dispatches
   `resolve-issue` → Telegram "รับงาน" → within 30 min a MR with `Closes #<iid>` and a Telegram summary.
2. Push a commit that breaks a job (e.g. `exit 1` in `.gitlab-ci.yml`) → Pipeline Hook `failed` →
   `incident-triage` → analysis message in Telegram within 2 min.
3. Send a webhook with a wrong secret (`scripts/send-test-webhook.sh issue --bad-token` against the
   public URL) → 401, `webhook_auth_fail_total` increments.
