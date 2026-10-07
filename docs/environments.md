# Environments (D2.6)

| | **dev (local-free)** | **staging** | **prod** |
|---|---|---|---|
| Host | Windows / Docker Desktop | Linux VM or same host with cloud LLM | Linux VM Ubuntu 24.04 (DECISION-2) |
| Compose | `docker-compose.yml` + `docker-compose.local-free.yml` | base compose + cloud LLM keys | base + `docker-compose.prod.yml` + profile `ingress` |
| LLM | `inference-ollama` / `qwen2.5-coder:7b` @ **64K ctx** | OpenRouter (or hybrid per `projects.yaml`) | OpenRouter + optional `onprem-llm` |
| Agents | all 6 | all 6 | all 6 |
| Adapters | router + 5 workers (`ADAPTER_DISPATCHER=hermes_api`) | same | same |
| Ingress | loopback only | Cloudflare tunnel (staging hostname) | Cloudflare tunnel (DECISION-5) |
| Secrets | `make secrets-dev` | SOPS `.env.enc` | SOPS / future Vault |
| Pilot repos | `sandbox-smoke` + placeholders | DECISION-11 pilot | DECISION-11 |
| RBAC | `config/rbac.yaml` (from example) | real Telegram ids (DECISION-8) | same |
| MinIO | local compose + SigV4 via root password | local or external | compose MinIO + offsite restic (Phase 4) |
| Verified | API Flow A + E11 pause/RBAC (see `phase3-exit-criteria.md`) | — | — |

## Promote checklist

1. Fill DECISION-8 / 11 / 5 / 2 in `config/org.yaml`
2. `cp config/rbac.example.yaml config/rbac.yaml` and set real user ids
3. Staging: cloud LLM keys + tunnel + GitLab webhook to staging hostname
4. Prod: `make up-prod` on the VM after `docs/deploy-linux-vm.md`
