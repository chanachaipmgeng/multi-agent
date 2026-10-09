# Environments (D2.6)

| | **dev (local-free)** | **air-gap / offline** | **staging** | **prod** |
|---|---|---|---|---|
| Host | Windows / Docker Desktop | Linux GPU host (e.g. Precision 7920) | Linux VM or same host with cloud LLM | Linux VM Ubuntu 24.04 (DECISION-2) |
| Compose | `docker-compose.yml` + `docker-compose.local-free.yml` | same + `make up-offline` (console + observability) | base compose + cloud LLM keys | base + `docker-compose.prod.yml` + profile `ingress` |
| LLM | `inference-ollama` / `LOCAL_LLM_MODEL` (default 7b) @ **64K ctx** | packed Ollama; recommend **14b** on 2×16 GB VRAM | OpenRouter (or hybrid per `projects.yaml`) | OpenRouter + optional `onprem-llm` |
| Agents | all 6 | all 6 | all 6 | all 6 |
| Adapters | router + 5 workers (`ADAPTER_DISPATCHER=hermes_api`) | same | same | same |
| Ingress | loopback only | loopback / LAN only (**no** cloudflared) | Cloudflare tunnel (staging hostname) | Cloudflare tunnel (DECISION-5) |
| SCM | GitLab + optional GitHub (`scm` in `projects.yaml`) | optional LAN SCM; else Console/API only | same | same |
| Operator Console | `make up-console` → `:8088` (optional) | **primary HITL** (`up-offline`) | optional | optional (DECISION-20) |
| Secrets | `make secrets-dev` | transfer age key / `secrets-dev` | SOPS `.env.enc` | SOPS / future Vault |
| Pilot repos | `sandbox-smoke` + placeholders | same | DECISION-11 pilot | DECISION-11 |
| RBAC | `config/rbac.yaml` (from example) | same | real Telegram ids (DECISION-8) | same |
| MinIO | local compose + SigV4 via root password | same | local or external | compose MinIO + offsite restic (Phase 4) |
| Pack/load | — | `make pack-offline` / `load-offline` — [`offline-airgap.md`](offline-airgap.md) | — | — |
| Verified | API Flow A + E11 pause/RBAC (see `phase3-exit-criteria.md`) | operator acceptance on GPU host | — | — |

## Observability (D4.1)

```bash
make up-observability
# Grafana http://127.0.0.1:3000 · Prometheus :9090 · Alertmanager :9093
# Adapter metrics on host: router :9101 · FE :9102 · BE :9103 · reviewer :9104 · qa :9105 · devops :9106
curl -fsS http://127.0.0.1:9101/metrics | head
```

Compose profile `observability`: Loki, Tempo, OTel Collector, Promtail (docker log redaction),
Prometheus, Alertmanager (Telegram when `TELEGRAM_CHAT_ID` set), Grafana (4 EMAW dashboards).
Prometheus still scrapes adapters at `*:9100` on the Docker network; host ports are for local debug.
Optional `LLM_USD_PER_1K_TOKENS` (default `0`) feeds `llm_cost_usd_total` — do not invent a vendor price.
See `docs/runbooks/alerts.md`.

## Supply chain (D4.6 / E12)

* Base images and compose services are **digest-pinned** (`python:3.12-slim@sha256:…`,
  `REDIS_IMAGE`, `POSTGRES_IMAGE`, …). Defaults live in `docker-compose.yml` / Dockerfiles;
  override via `.env`.
* Refresh pins: `scripts/pin-digests.sh` (dry-run) or `--apply`.
* CI job `supply-chain` builds gateway + adapter images and runs Trivy
  (`severity: HIGH,CRITICAL`, `ignore-unfixed: true`) plus `trivy config` on compose/Dockerfiles.
* Ignore list: `.trivyignore` (empty by default — document every CVE there).

## Promote checklist

1. Fill DECISION-8 / 11 / 5 / 2 in `config/org.yaml` (see [`org-unblock.md`](org-unblock.md) — do not invent values)
2. `cp config/rbac.example.yaml config/rbac.yaml` and set real user ids
3. Staging: cloud LLM keys + tunnel + GitLab/GitHub webhooks to staging hostname
4. Prod: `make up-prod` on the VM after `docs/deploy-linux-vm.md`
5. Optional: `make up-console` behind the same tunnel / reverse proxy (loopback only by default)
