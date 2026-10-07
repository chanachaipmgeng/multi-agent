# Runbook — credential rotation (first version, Phase 1)

Policy (design §6.3): GitLab tokens 90 days · webhook secret 180 days · Telegram / LLM / tunnel
on suspicion. Every token is a **separate** secret file (`secrets/<name>`) so one consumer can
be rotated without touching the others. Record each rotation as audit event `secret.rotated`
(coordinator does this in Phase 3; until then note it in the ops channel).

Pre-flight: `scripts/gitlab-token-check.sh` lists scopes and days left for all GitLab tokens.

## GitLab Project Access Token (`gitlab_token_<role>`)

1. GitLab → project → Settings → Access Tokens → **Add new token**: name `emaw-<role>-<YYYYMM>`,
   role *Developer*, scopes exactly `read_api` (+ `write_repository` for writers), expiry ≤ 90 days.
   Never `api`, never group/instance admin (checklist #2).
2. Put the value in `.env` (`SECRET_GITLAB_TOKEN_<ROLE>`), then `make secrets-encrypt && make secrets-decrypt`.
3. Restart only the consumer: `docker compose restart <service>` (or `hermes config set gitlab.token …` on the host in Phase 0–2).
4. Verify: `scripts/gitlab-token-check.sh`; trigger a test webhook / `hermes run "glab auth status"`.
5. Revoke the old token in GitLab. Update the inventory table below.

## Webhook secret (`gitlab_webhook_secret`)

Zero-downtime order matters — the gateway only knows one secret:

1. Generate: `openssl rand -hex 32`.
2. Update `.env` → encrypt → decrypt → `docker compose restart webhook-gateway` (gateway now rejects old secret with 401; GitLab will retry).
3. Immediately: `WEBHOOK_SECRET=<new> scripts/gitlab-webhook-register.sh <project> https://webhook.<org>.com` for every project.
4. GitLab → Webhooks → Test → Issues events → HTTP 200. Any 401s during the gap are retried by GitLab.

## Telegram bot token

`@BotFather` → `/revoke` → new token → `SECRET_TELEGRAM_TOKEN` → encrypt/decrypt → restart
coordinator (and `queue-adapter` if notifications are enabled). Allowlist (`telegram.allowed_users`) is unaffected.

## LLM provider key (`llm_key_<agent>`)

Create the new key at the provider **before** revoking; update the single agent's secret; restart
that agent; revoke old key; check the provider cost dashboard shows traffic under the new key.

## Cloudflare tunnel token

See `docs/runbooks/tunnel.md` → create a replacement tunnel, move DNS, swap `SECRET_TUNNEL_TOKEN`, delete old.

## Postgres password (`pg_password`)

`ALTER USER emaw PASSWORD '<new>'` inside the container → update secret → restart `webhook-gateway`,
`queue-adapter`, `coordinator`. Do not rotate during a running task burst (connections re-auth on restart).

## Inventory

| Secret | Owner | Created | Expires | Last rotated |
|---|---|---|---|---|
| gitlab_token_readonly | | | | |
| gitlab_token_frontend | | | | |
| gitlab_token_backend | | | | |
| gitlab_token_ci | | | | |
| gitlab_token_qa | | | | |
| gitlab_webhook_secret | | | | |
| telegram_token | | | | |
| tunnel_token | | | | |
| llm_key_* (6) | | | | |
