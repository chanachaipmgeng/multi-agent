# Environments (D2.6)

| | **dev (local-free)** | **LAN + local LLM** | **air-gap / offline** | **staging** | **prod** |
|---|---|---|---|---|---|
| Host | Windows / Docker Desktop | Linux GPU host with outbound net (e.g. 7920) | Linux GPU host (no outbound) | Linux VM or same host with cloud LLM | Linux VM Ubuntu 24.04 (DECISION-2) |
| Compose | `docker-compose.yml` + `docker-compose.local-free.yml` | same + `make up-lan` (console + observability) | same + `make up-offline` | base compose + cloud LLM keys | base + `docker-compose.prod.yml` + profile `ingress` |
| LLM | `inference-ollama` / `LOCAL_LLM_MODEL` (default 7b) @ **64K ctx** | Ollama **14b** (online pull OK); **no** OpenRouter | packed Ollama; recommend **14b** | OpenRouter (or hybrid per `projects.yaml`) | OpenRouter + optional `onprem-llm` |
| Agents | all 6 | all 6 | all 6 | all 6 | all 6 |
| Adapters | router + 5 workers (`ADAPTER_DISPATCHER=hermes_api`) | same | same | same | same |
| Ingress | loopback only | Console on LAN (`CONSOLE_BIND=0.0.0.0`); **no** cloudflared | loopback only (**no** cloudflared) | Cloudflare tunnel (staging hostname) | Cloudflare tunnel (DECISION-5) |
| SCM | GitLab + optional GitHub (`scm` in `projects.yaml`) | optional; Console/API OK | optional LAN SCM; else Console/API only | same | same |
| Operator Console | `make up-console` → `:8088` (optional) | **primary HITL** now; Telegram later | **primary HITL** (`up-offline`) | optional | optional (DECISION-20) |
| Secrets | `make secrets-dev` | `secrets-dev` on host | transfer age key / `secrets-dev` | SOPS `.env.enc` | SOPS / future Vault |
| Pilot repos | `sandbox-smoke` + placeholders | same | same | DECISION-11 pilot | DECISION-11 |
| RBAC | `config/rbac.yaml` (from example) | same → real Telegram ids when enabling bot | same | real Telegram ids (DECISION-8) | same |
| MinIO | local compose + SigV4 via root password | same | same | local or external | compose MinIO + offsite restic (Phase 4) |
| Pack/load | — | not required (host can pull) | `make pack-offline` / `load-offline` — [`offline-airgap.md`](offline-airgap.md) | — | — |
| Verified | API Flow A + E11 pause/RBAC (see `phase3-exit-criteria.md`) | Console via LAN IP + local 14b | operator acceptance on GPU host | — | — |

### LAN + local LLM (hybrid)

Online host that still runs **local Ollama** (not `up-prod` / OpenRouter):

```bash
# .env: LLM_MODE=local, LOCAL_LLM_MODEL=qwen2.5-coder:14b, CONSOLE_BIND=0.0.0.0
make up-lan
# → http://<host-lan-ip>:8088
# Prefer: ufw allow from <LAN_CIDR> to any port 8088
```

Telegram 24/7 is optional later (outbound long-poll to `api.telegram.org`); keep `LLM_MODE=local`.
See [operator-console.md](operator-console.md) § Telegram checklist.

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
