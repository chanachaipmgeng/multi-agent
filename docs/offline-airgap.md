# Offline / air-gap pack (Precision 7920 class)

Run EMAW **local-free** (DECISION-15) on a Linux host with **no internet after install**:
local Ollama LLM, Operator Console HITL, optional observability. Do **not** use
`make up-prod` (that path expects OpenRouter + Cloudflare tunnel).

Reference host (example): Dell Precision 7920 Rack — Ubuntu 26.04, 2× Xeon Gold 6234,
~436 GiB RAM, 2× Quadro RTX 5000 (16 GB VRAM each), ~1.5 TiB disk, LAN e.g. `10.50.0.117/24`.

DECISION-2 documents Ubuntu **24.04**; 26.04 is fine if Docker Engine + NVIDIA Container
Toolkit install and `nvidia-smi` / a GPU container smoke test succeed.

## Who does what

| Step | Repo / packer (has network) | Operator on air-gap host |
|---|---|---|
| Clone EMAW, fill `.env` / secrets | yes | copy age key + `.env.enc` or run `secrets-dev` from transferred secrets |
| Install Docker + NVIDIA toolkit | — | **required on host** |
| `make pack-offline` (images + model volumes + npm cache) | yes | — |
| Move `offline-pack/<ts>/` (USB / LAN) | yes | receive tarball directory |
| `make load-offline PACK=…` | — | yes |
| `make up-offline` + smoke checks | — | yes |
| Telegram / Cloudflare / GitLab.com | — | needs network or LAN SCM; otherwise use Console / API only |

## Model sizing (dual RTX 5000, 16 GB ×2)

Hermes ≥0.21 needs **≥64K** context (`OLLAMA_CONTEXT_LENGTH` + `model.ollama_num_ctx`).
KV-cache at 64K uses extra VRAM on top of weights.

| Tier | `LOCAL_LLM_MODEL` | Approx. weights | Fit |
|---|---|---|---|
| Baseline | `qwen2.5-coder:7b` | ~4–5 GB | One GPU; shared queue for 6 agents |
| **Recommended on 7920** | `qwen2.5-coder:14b` | ~8–10 GB + KV | One GPU; second GPU free for headroom |
| High quality | `qwen2.5-coder:32b` (Q4) | ~18–20 GB | Both GPUs (Ollama layer split) and/or RAM offload |
| Experimental | ~70B Q3–Q4 | ~35–40 GB+ | Heavy RAM offload; high latency — not default |

On the server set in `.env` (dev laptops can keep 7b):

```bash
LLM_MODE=local
LOCAL_LLM_MODEL=qwen2.5-coder:14b
LOCAL_LLM_FALLBACK=qwen2.5-coder:7b   # optional; defaults to LOCAL_LLM_MODEL
```

`make hermes-seed` / `up-local-free` / `up-offline` run `scripts/sync-local-llm-model.sh` so
all six `hermes-data/*/config.local-free.yaml` match those env vars.

Also pull embeddings once while packing: `nomic-embed-text` into `socraticode-ollama`.

## GPU modes

- **A (default):** one `inference-ollama` with `deploy.resources…nvidia count: all` (already in
  [`docker-compose.local-free.yml`](../docker-compose.local-free.yml)).
- **B (later):** give `socraticode-ollama` its own GPU reservation if embedding load matters.
  Do not share the confidential LLM volume with the embedding store (DECISION-6).

Bare profile `onprem-llm` has **no** NVIDIA stanza — always use local-free / `up-offline`.

## Pack (machine with network)

Prerequisites: Docker, compose v2, enough disk for images + models (plan ~20–80 GB by tier).

```bash
cp -n .env.example .env
# set SECRET_HERMES_API_KEY, LOCAL_LLM_MODEL=…, LLM_MODE=local
make secrets-dev
make up-local-free
make local-llm-pull                          # LOCAL_LLM_MODEL
docker exec socraticode-ollama ollama pull nomic-embed-text
# Optional: warm SocratiCode npm cache (first reviewer MCP spawn), then:
make pack-offline
# → offline-pack/<UTC-ts>/{images.tar, volumes/*.tar.gz, manifest.json, …}
```

`pack-offline` builds/pulls compose images, `docker save`s them, and tars:

- `ollama-data` (chat models)
- `socraticode_ollama_data` / `socraticode_qdrant_data` (external volume names)
- `hermes-reviewer-data` (npm/`npx` SocratiCode cache when present)

Override output: `PACK_DIR=… make pack-offline`.

## Load + run (air-gap host)

### 1. Host prep (operator)

```bash
# Docker Engine + Compose plugin (official docs for your Ubuntu)
sudo usermod -aG docker "$USER"   # re-login

# NVIDIA driver + Container Toolkit — then:
nvidia-smi
# smoke: docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### 2. Transfer + load

```bash
# After copying offline-pack/<ts> onto the host (and cloning/copying the EMAW repo):
make load-offline PACK=offline-pack/<ts>
# or: PACK_DIR=/path/to/offline-pack/<ts> make load-offline
```

### 3. Secrets + bring-up

```bash
cp -n .env.example .env
# LLM_MODE=local, LOCAL_LLM_MODEL=qwen2.5-coder:14b (or whatever was packed)
make secrets-dev   # or secrets-decrypt with offline age key
cp -n config/rbac.example.yaml config/rbac.yaml
make up-offline    # local-free + Operator Console + observability
make local-free-check && make phase3-check
```

Console: http://127.0.0.1:8088 — HITL without Telegram.  
Grafana: http://127.0.0.1:3000 after observability profile is up.

Host ports stay on loopback by default. For LAN-only access, put a reverse proxy / VPN in
front; do not expose raw compose ports without auth.

## What “100% offline” covers

| Capability | Offline? |
|---|---|
| Platform + 6 agents + local LLM + SocratiCode infra | yes (after pack/load) |
| Operator Console approvals / control | yes |
| Observability (Grafana/Prometheus/Loki) | yes (Alertmanager Telegram needs chat + network) |
| Telegram bot HITL | no (needs internet) |
| Cloudflare tunnel | no — skip `ingress` |
| GitLab.com / GitHub.com webhooks & API | no unless SCM is on LAN |
| Image/model updates | re-pack on a networked machine; no auto-update |

Hybrid `llm_backend` in `projects.yaml` (DECISION-3) is **policy metadata** today — it does
not auto-switch providers per task. Offline mode is the blunt switch: all six agents → Ollama.

## Ops after go-live

```bash
make backup BACKUP_OLLAMA=1          # include ollama-data
make restore-drill BACKUP=backups/<ts>
```

Operator proof (Cursor skill):  
`bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline`  
— see [`.cursor/skills/verify-emaw/features/local-free-offline.md`](../.cursor/skills/verify-emaw/features/local-free-offline.md).

See [`deploy-linux-vm.md`](deploy-linux-vm.md) for the cloud+tunnel prod path (different from this doc).

Skills for Hermes agents still promote from `skills/` via `make skills-sync` (never edit `hermes-data/*/skills` as source of truth).
