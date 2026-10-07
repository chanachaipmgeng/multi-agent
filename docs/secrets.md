# Secrets management (Phase 0–2: SOPS + age)

Design reference: §6.3, checklist E7. Rule zero: **no plaintext secret is ever committed or
placed under `/workspace`**. Agents can only see secrets as `/run/secrets/<name>` files that are
mounted into their own container, and `.agentignore` hides `.env*`, `secrets/`, `*.pem`, `*.key`.

## Flow

```text
.env.example ──cp──▶ .env (plaintext, gitignored)
                       │  make secrets-encrypt   (sops --encrypt, age recipient from .sops.yaml)
                       ▼
                    .env.enc (committed)
                       │  make secrets-decrypt   (sops --decrypt → one file per SECRET_*)
                       ▼
                    secrets/<name>  (0600, gitignored)  ──▶ docker compose `secrets:` ──▶ /run/secrets/<name>
```

1. `make secrets-init` — generates an age key pair (`~/.config/sops/age/keys.txt`) and writes the
   public key into `.sops.yaml`. Back the private key up offline; add a second recipient
   (break-glass key) before production.
2. `cp .env.example .env` and fill the `SECRET_*` values.
3. `make secrets-encrypt` → `.env.enc`. Commit it.
4. On any host that runs the stack: `export SOPS_AGE_KEY_FILE=…`, then `make secrets-decrypt`.
   For a throw-away dev box without SOPS you may use `make secrets-dev` (plaintext `.env` → files).

`sops exec-env .env.enc 'docker compose up -d'` is an alternative that never writes files to
disk; the file-based variant is used because Hermes reads `token_file:` paths.

## Inventory and rotation

| Secret file | Consumer | Scope | Rotate |
|---|---|---|---|
| `gitlab_webhook_secret` | webhook-gateway | GitLab webhook "Secret token" | 180 days |
| `pg_password` | postgres, gateway, coordinator | DB user `emaw` | 180 days |
| `tunnel_token` | cloudflared | one Named Tunnel | on suspicion |
| `telegram_token` | coordinator **only** | bot | on suspicion |
| `llm_key_<agent>` ×6 | that agent only | provider key, per-agent for cost + revocation | 90 days |
| `gitlab_token_readonly` | coordinator, reviewer | Project Access Token `read_api` | 90 days |
| `gitlab_token_frontend` / `_backend` / `_ci` / `_qa` | that worker only | PAT `read_api` + `write_repository`, one repo | 90 days |
| `socraticode_key` | reviewer | SocratiCode | 90 days |
| `hermes_api_key` | adapters, gateway internal, Hermes API | Bearer | 90 days |
| `dashboard_password` | coordinator dashboard `:9119` | basic auth (DECISION-18) | 90 days |
| `dashboard_session_secret` | coordinator dashboard sessions | HMAC (optional; falls back to `hermes_api_key`) | 90 days |
| `minio_*` | MinIO | root / agent | 180 days |

Rotation runbook (first version, Phase 1 will extend it): edit `.env` → `make secrets-encrypt`
→ `make secrets-decrypt` → `docker compose up -d <service>` for the consumer(s) only → revoke the
old credential at the provider → record `secret.rotated` in the audit log.

## Guard rails in this repo

* `.gitignore` excludes `.env`, `.env.*` (except `.env.example`), `secrets/*`, `*.age`, `*.pem`, `*.key`.
* `.gitleaks.toml` + pre-commit hook + CI job scan every commit (GitLab PAT, Telegram, tunnel token, age key patterns added).
* `webhook-gateway` refuses to start without `GITLAB_WEBHOOK_SECRET(_FILE)`; it never logs the token.
* Phase 3: Docker secrets per agent are already wired in compose (incl. `minio_agent_secret`).
  Phase 4 adds Vault/Infisical short-lived tokens (E7).
