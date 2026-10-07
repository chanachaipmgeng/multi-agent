# Deploy on Linux VM (D3.8)

Target: Ubuntu 24.04 + Docker Engine (DECISION-2). WSL2 is for Phase 0–2 only.

## 1. Host prep

```bash
sudo apt update && sudo apt install -y git curl
# Install Docker Engine + Compose plugin (official docs)
sudo usermod -aG docker "$USER"   # re-login
```

## 2. Clone + secrets

```bash
git clone <repo> emaw && cd emaw
cp .env.example .env              # fill SECRET_* and MINIO_ROOT_PASSWORD
# Preferred: sops decrypt
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
make secrets-decrypt              # or: make secrets-dev
cp config/rbac.example.yaml config/rbac.yaml   # set real Telegram ids (DECISION-8)
```

## 3. Bring up

```bash
make hermes-seed
make skills-sync
make up-prod                      # compose.yml + compose.prod.yml + agents + ingress
scripts/minio-init.sh
```

Ensure `secrets/tunnel_token` is set before relying on cloudflared (DECISION-5).

## 4. Verify

```bash
make phase3-check
curl -fsS http://127.0.0.1:8700/healthz
# Public path only via tunnel — see docs/runbooks/tunnel.md
```

## 5. Ops notes

- Host ports remain on `127.0.0.1` in the base compose; do not publish them to the LAN.
- Rotate tokens with `docs/runbooks/token-rotation.md`.
- Backup/restore: `make backup` / `make restore-drill BACKUP=backups/<ts>` (D4.5); optional `RESTIC_REPOSITORY`.
