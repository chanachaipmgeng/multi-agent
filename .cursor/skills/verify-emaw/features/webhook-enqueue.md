# Webhook enqueue

Operators (or GitLab/GitHub) POST an issue event; the gateway authenticates, normalizes, and queues a task.
This feature recipe drives the **GitLab** fixture path; GitHub uses `POST /webhook/github` + HMAC (manual / future recipe).

## Sub-features

- `issue-hook` — sample Issue Hook fixture accepted with valid secret.
- `auth-reject` — bad token rejected (optional manual check with `--bad-token`).

## How to get to it (user POV)

- GitLab project webhook → `…/webhook/gitlab`, or GitHub → `…/webhook/github`, or
- `make webhook-test KIND=issue` / `scripts/send-test-webhook.sh issue`.

## Driving it with verify-emaw

Preconditions:

- Gateway up; `secrets/gitlab_webhook_secret` non-empty; project allowlisted in `config/projects.yaml` for the fixture project id.

- **Enqueue.** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive webhook-enqueue`.
- **Proof.** `webhook-response.txt` shows HTTP 200 and a body mentioning `queued`, `duplicate`, or `recorded`.

## Gotchas

- Duplicate UUID returns duplicate — still a successful proof of the path.
- Fixture project must match allowlist or you get 403 (not a harness bug).
