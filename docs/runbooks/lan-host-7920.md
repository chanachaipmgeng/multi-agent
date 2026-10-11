# Runbook — LAN host (Precision 7920 / `/opt/emaw`)

Operator checklist for **LAN + local LLM** (`make up-lan`, `CONSOLE_BIND=0.0.0.0`).
Covers remaining host work from [roadmap-next.md](../roadmap-next.md) W0–W5.
Does **not** replace [operator-handbook.md](../operator-handbook.md).

## 0. Assumptions

| Item | Value |
|---|---|
| Install path | `/opt/emaw` |
| Compose project | `COMPOSE_PROJECT_NAME=emaw` (match existing volumes) |
| Console | `http://<host-ip>:8088` |
| Backup root (preferred) | `/srv/emaw-backups` (outside the git tree) |

```bash
cd /opt/emaw
set -a && source .env && set +a
```

---

## 1. Pull + redeploy (W0 / W3 / W4)

```bash
cd /opt/emaw
git pull   # or deploy the branch that has W0–W5

# Console login secrets (DECISION-21) — never commit real values
# Copy shape from config/rbac.example.yaml → config/rbac.yaml
# Set per-user console_secret; rotate off example strings
$EDITOR config/rbac.yaml

make secrets-dev   # if .env / SECRET_* changed
make up-lan
# Pick up worker pause/heartbeat + session auth + System page:
docker compose -f docker-compose.yml -f docker-compose.local-free.yml \
  --profile agents --profile onprem-llm up -d --build --force-recreate \
  webhook-gateway router \
  adapter-dev-frontend adapter-dev-backend adapter-reviewer adapter-qa adapter-devops
docker compose --profile console build operator-console
docker compose --profile console up -d --force-recreate operator-console
```

Prove:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8088/
# Login in browser: user id + console_secret (not Hermes API key)
# Open Console → System (heartbeats / queues / DLQ)
```

---

## 2. Firewall (W0)

Publish only Console / Grafana / Hermes dashboard on the LAN. Keep Redis, Postgres,
MinIO, Hermes API, Prometheus, gateway `:8700` on loopback.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
# Adjust CIDR to the real LAN
sudo ufw allow from 10.50.0.0/16 to any port 8088,3030,9119 proto tcp
sudo ufw enable
sudo ufw status verbose
```

From a LAN laptop:

```bash
# Expect 404 (nginx allowlist) — not gateway metrics/webhooks
curl -s -o /dev/null -w '%{http_code}\n' http://<host-ip>:8088/api/metrics
curl -s -o /dev/null -w '%{http_code}\n' http://<host-ip>:8088/api/webhook/gitlab
# Expect 200
curl -s -o /dev/null -w '%{http_code}\n' http://<host-ip>:8088/
curl -s -o /dev/null -w '%{http_code}\n' http://<host-ip>:8088/api/healthz
```

---

## 3. Rotate compose defaults (W0)

If `.env` still uses example passwords, rotate at least:

- `GRAFANA_ADMIN_PASSWORD`
- `MINIO_ROOT_PASSWORD` / `SECRET_MINIO_ROOT_PASSWORD`
- `SECRET_DASHBOARD_PASSWORD`
- `SECRET_HERMES_API_KEY` (long random ≥ 32 chars)

Then `make secrets-dev` and recreate affected services. See
[token-rotation.md](token-rotation.md). **Never commit** the new values.
Also rotate the host SSH password used for install if it was shared.

---

## 4. systemd: stack + backup timers (W5)

Units live in `deploy/systemd/`. Scripts: `scripts/host-backup-timed.sh`,
`scripts/host-restore-drill-timed.sh`.

```bash
sudo mkdir -p /srv/emaw-backups
sudo chown "$USER:" /srv/emaw-backups   # or a dedicated backup user

cd /opt/emaw
sudo make install-host-units
# or: sudo scripts/install-host-units.sh

sudo systemctl enable --now emaw.service
sudo systemctl enable --now emaw-backup.timer emaw-restore-drill.timer
systemctl status emaw.service --no-pager
systemctl list-timers 'emaw-*'
```

Manual smoke (optional):

```bash
sudo systemctl start emaw-backup.service
journalctl -u emaw-backup.service -n 50 --no-pager
sudo systemctl start emaw-restore-drill.service
journalctl -u emaw-restore-drill.service -n 50 --no-pager
```

| Unit | Role |
|---|---|
| `emaw.service` | `make up-lan` after boot; `make down` on stop |
| `emaw-backup.timer` | daily ~03:15 → backup + prune > 7 days under `BACKUP_ROOT` |
| `emaw-restore-drill.timer` | weekly Sun ~04:30 → drill on newest backup |

Override `BACKUP_ROOT` / `BACKUP_KEEP_DAYS` with a drop-in:

```bash
sudo systemctl edit emaw-backup.service
# [Service]
# Environment=BACKUP_ROOT=/srv/emaw-backups
# Environment=BACKUP_KEEP_DAYS=7
```

Policy details: [restore.md](restore.md).

---

## 5. Ollama tuning (W2) — measure on this host only

`docker-compose.local-free.yml` currently sets `OLLAMA_CONTEXT_LENGTH` only.
On dual 16 GB GPUs with `qwen2.5-coder:14b`, try **one variable at a time**, then:

```bash
# edit inference-ollama.environment in docker-compose.local-free.yml (or compose override)
make up-lan   # or recreate inference-ollama only
make local-free-check
```

Suggested order (do not batch):

1. `OLLAMA_KEEP_ALIVE=-1`
2. `OLLAMA_MAX_LOADED_MODELS=1`
3. `OLLAMA_NUM_PARALLEL=2`
4. `OLLAMA_FLASH_ATTENTION=1`
5. `OLLAMA_KV_CACHE_TYPE=q8_0`

Keep only settings that still pass `local-free-check` under real Dispatch load.
Do **not** commit a guessed set for every host until measured here; open a separate PR
with the proven values.

---

## 6. Proof commands (after bring-up)

```bash
cd /opt/emaw
set -a && source .env && set +a
make local-free-check
make offline-acceptance
curl -fsS -o /dev/null -w '%{http_code}\n' http://10.50.0.117:8088/
```

From a laptop with the repo:

```bash
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive operator-console
bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline
```

## Explicit non-goals on this host

- No Cloudflare tunnel / OpenRouter / `make up-prod`
- No publishing Redis/Postgres/MinIO/Hermes API/Prometheus on the LAN
- No web UI for `make restore` (destructive) or secrets rotation
