# Offline / air-gap pack (Precision 7920 class)

Run EMAW **local-free** (DECISION-15) on a Linux host with **no internet after install**:
local Ollama LLM, Operator Console HITL, observability. Do **not** use `make up-prod`
(that path expects OpenRouter + Cloudflare tunnel).

Reference host: Dell Precision 7920 Rack — Ubuntu 26.04, 2× Xeon Gold 6234,
~436 GiB RAM, 2× Quadro RTX 5000 (16 GB VRAM each), ~1.5 TiB disk, LAN e.g. `10.50.0.117/24`.

DECISION-2 documents Ubuntu **24.04**; 26.04 is fine after Docker Engine + NVIDIA Container
Toolkit install and the GPU smokes in Phase E pass.

**Server defaults:** copy knobs from [`config/env.offline-server.example`](../config/env.offline-server.example)
(`LOCAL_LLM_MODEL=qwen2.5-coder:14b`, fallback `7b`).

---

## Migration phases (green before you move)

| Phase | Where | Must have (green) |
|---|---|---|
| **A — Prep** | pack host (has network) | `.env` from server example, `secrets-dev`, `rbac.yaml`, ≥80 GiB free disk |
| **B — Prove** | pack host | `up-local-free` + pull **14b** (or note exception) + embed + `warm-socraticode-npm` → `make offline-acceptance` **PASS** |
| **C — Pack** | pack host | `make pack-offline` → `PACK=… make preflight-offline` **PASS** |
| **D — Transfer kit** | USB / LAN | repo tree + `offline-pack/<ts>/` + age key (separate channel) |
| **E — Host prep** | Precision 7920 | Docker + NVIDIA toolkit; `nvidia-smi` + GPU container smoke |
| **F — Load & accept** | 7920 | `load-offline` → `up-offline` → `make offline-acceptance` **PASS** |

Do **not** start Phase D until A–C are green. Production pack for this server **must** include
`qwen2.5-coder:14b` (dev laptops may prove with 7b only if GPU-limited — rebuild pack on a
host that can pull 14b before transfer).

### Who does what

| Work | Pack host (repo / network) | Operator on 7920 |
|---|---|---|
| Clone / fill secrets | yes | receive age key + kit; `secrets-dev` or decrypt |
| Install Docker + NVIDIA | — | **required (sudo)** |
| Prove + pack | `offline-acceptance` then `pack-offline` | — |
| Transfer kit | create / ship | receive |
| Load + `up-offline` | — | yes |
| Telegram / Cloudflare / SaaS SCM | — | needs network or LAN SCM; else Console/API only |

---

## Model sizing (dual RTX 5000, 16 GB ×2)

Hermes ≥0.21 needs **≥64K** context (`OLLAMA_CONTEXT_LENGTH` + `model.ollama_num_ctx`).

| Tier | `LOCAL_LLM_MODEL` | Approx. weights | Fit |
|---|---|---|---|
| Baseline | `qwen2.5-coder:7b` | ~4–5 GB | Dev prove / fallback |
| **7920 default** | `qwen2.5-coder:14b` | ~8–10 GB + KV | One GPU |
| High quality | `qwen2.5-coder:32b` (Q4) | ~18–20 GB | Both GPUs / RAM offload |
| Experimental | ~70B Q3–Q4 | ~35–40 GB+ | Heavy RAM offload — not default |

`make hermes-seed` / `up-local-free` / `up-offline` run `scripts/sync-local-llm-model.sh`.

GPU: local-free compose already sets NVIDIA `count: all`. Bare `onprem-llm` has **no** GPU
stanza — always use local-free / `up-offline`.

---

## Phase A — Prep (pack host)

```bash
cp -n config/env.offline-server.example .env   # or merge into existing .env
# Ensure: LLM_MODE=local, LOCAL_LLM_MODEL=qwen2.5-coder:14b, SECRET_HERMES_API_KEY=…
make secrets-dev
cp -n config/rbac.example.yaml config/rbac.yaml
df -h .   # aim ≥80 GiB free for 14b pack
make preflight-offline          # stack may still be down — checks secrets/env/disk/docker
```

---

## Phase B — Prove (pack host)

```bash
make up-local-free
make local-llm-pull                           # pulls LOCAL_LLM_MODEL (14b)
docker exec socraticode-ollama ollama pull nomic-embed-text
make warm-socraticode-npm                     # required before air-gap pack
make up-console && make up-observability      # or: make up-offline
make offline-acceptance                       # MUST pass (REQUIRE_CONSOLE=1)
# optional: bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline
```

If the pack host cannot pull/run 14b, prove with 7b for tooling only, then rebuild Phase B–C
on a GPU host that holds 14b before shipping to 7920.

---

## Phase C — Pack

```bash
make pack-offline
# → offline-pack/<UTC-ts>/{images.tar, volumes/*.tar.gz, manifest.json, …}
PACK=offline-pack/<ts> make preflight-offline   # MUST pass
```

Pack contents: chat models (`ollama-data`), SocratiCode ollama/qdrant volumes, reviewer npm
cache (`hermes-reviewer-data`), digest-pinned images.

---

## Phase D — Transfer kit

Ship **all** of:

| Item | Notes |
|---|---|
| EMAW git tree | `git clone` / `rsync` / `git archive` — same commit as pack |
| `offline-pack/<ts>/` | entire directory (`images.tar` is large) |
| Age private key | **separate channel** from the pack (USB + encrypted share, etc.) |
| Notes | packed `LOCAL_LLM_MODEL`, pack path, commit SHA |

Do not commit secrets or `offline-pack/` (gitignored).

---

## Phase E — Host prep (Precision 7920 — operator)

Requires sudo. Outline (follow current Ubuntu NVIDIA / Docker docs for your release):

```bash
# 1) Docker Engine + Compose plugin (official Docker docs for Ubuntu)
sudo usermod -aG docker "$USER"   # re-login

# 2) NVIDIA driver + nvidia-container-toolkit (NVIDIA docs)
nvidia-smi
# Expect both Quadro RTX 5000 visible

# 3) GPU in containers
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

If step 3 fails, fix toolkit/`nvidia-ctk runtime configure --runtime=docker` before Phase F.

---

## Phase F — Load & accept (7920)

**Preferred when the host can reach Hub/Ollama (LAN + local LLM hybrid):** clone the repo, set
`LOCAL_LLM_MODEL=qwen2.5-coder:14b`, `make secrets-dev`, then either:

- `make up-lan` with `CONSOLE_BIND=0.0.0.0` → Console at `http://<host-lan-ip>:8088`  
  (still **no** OpenRouter / cloudflared; see [environments.md](environments.md)), or
- `make up-offline` (loopback Console) if you prefer SSH tunnel only.

Then `make local-llm-pull`, pull `nomic-embed-text`, `make warm-socraticode-npm`, and
`make offline-acceptance`.

**Air-gap pack path** (no outbound pulls):

```bash
cd /path/to/emaw
# Place offline-pack/<ts> next to the repo (or set PACK= absolute path)
make load-offline PACK=offline-pack/<ts>
cp -n config/env.offline-server.example .env   # match packed LOCAL_LLM_MODEL
make secrets-dev                               # or: make secrets-decrypt
cp -n config/rbac.example.yaml config/rbac.yaml
make up-offline
make offline-acceptance                        # MUST pass before production use
```

- Console: http://127.0.0.1:8088 (default) or `http://<host-ip>:8088` when
  `CONSOLE_BIND=0.0.0.0` (`make up-lan`)
- Grafana: http://127.0.0.1:${GRAFANA_PORT:-3000} — if another stack owns `:3000`, set
  `GRAFANA_PORT=3030` in `.env` (`offline-acceptance` honors `GRAFANA_PORT`)
- MinIO: if Hub denies `minio/minio`, `docker save`/`load` the digest-pinned image from a
  pack host and set `MINIO_IMAGE=minio/minio:<local-tag>` (compose `--pull never` if needed)
- Hermes: `make secrets-dev` / `hermes-seed-env` writes `hermes-data/*/.env` mode `644` so the
  container UID can read the bind mount

Air-gap: keep ports on loopback (SSH tunnel). LAN hybrid: bind **Console only** via
`CONSOLE_BIND`; firewall to LAN CIDR — do not publish Redis/Postgres/MinIO/Hermes API.

### Operator-only checklist (cannot be done from the repo)

- [ ] sudo / install Docker + NVIDIA stack (Phase E)
- [ ] Physically transfer kit (USB/SCP)
- [ ] Age key delivered out-of-band
- [ ] `offline-acceptance` green on 7920
- [ ] Optional: LAN proxy for Console

---

## What “100% offline” covers

| Capability | Offline? |
|---|---|
| Platform + 6 agents + local LLM + SocratiCode | yes (after pack/load) |
| Operator Console / `simulate-operator` | yes |
| Observability (Grafana/Prometheus/Loki) | yes (Alertmanager→Telegram needs network) |
| Telegram / Cloudflare tunnel | no |
| GitLab.com / GitHub.com | no unless SCM on LAN |
| Image/model updates | re-pack on a networked host |

---

## Ops after go-live

```bash
make backup BACKUP_OLLAMA=1
make restore-drill BACKUP=backups/<ts>
```

Proofs: `make offline-acceptance` or  
`bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline`

Skills: promote from `skills/` via `make skills-sync` only.

Cloud+tunnel prod path: [`deploy-linux-vm.md`](deploy-linux-vm.md) (different from this doc).

---

## Pack-host prove notes (this repo)

| Date (UTC) | Host | Model packed | Result |
|---|---|---|---|
| 2026-10-09 | Windows pack host (Docker Desktop) | `qwen2.5-coder:7b` | `offline-acceptance` **PASSED**; pack `offline-pack/20261009T180801Z` + `preflight-offline PACK` **OK** (images ~5.3G + volumes). Disk ~40 GiB free — **did not pull 14b**. Rebuild Phase B–C with `LOCAL_LLM_MODEL=qwen2.5-coder:14b` on the 7920 (or any host with GPU + disk) before production transfer. Also fixed Operator Console nginx under `read_only` (`cap_add` CHOWN/SETUID/SETGID) so `:8088` stays up. |
| 2026-10-10 | Precision 7920 (`10.50.0.117`, Ubuntu, 2× RTX 5000) | `qwen2.5-coder:14b` (online pull) + `nomic-embed-text` | `offline-acceptance` **PASSED** on host (`up-offline` + console + observability). Notes: Docker Hub anonymous pull of `minio/minio` denied — loaded image via `docker save`/`load` from pack host and set `MINIO_IMAGE=minio/minio:emaw-offline`; host `:3000` taken by `open-webui` → `GRAFANA_PORT=3030`; Hermes bind-mount `.env` needed `chmod 644` (container UID). Console `127.0.0.1:8088`. |
| 2026-10-11 | Precision 7920 (same) | `qwen2.5-coder:14b` | **LAN hybrid:** `CONSOLE_BIND=0.0.0.0` + `make up-lan` → Console **http://10.50.0.117:8088** HTTP 200 from LAN. Still local LLM (no OpenRouter/cloudflared). Next work: [roadmap-next.md](roadmap-next.md). |

If GPU/VRAM/disk on the pack host is insufficient for 14b, prove with 7b as above, then rebuild
the pack on a capable host before Phase D.
