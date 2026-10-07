# Runbook — Alerts (D4.1 / E8)

## Stack

```bash
make up-observability
# UI (loopback only):
#   Grafana      http://127.0.0.1:3000   (emaw / emaw-grafana-dev by default)
#   Prometheus   http://127.0.0.1:9090
#   Alertmanager http://127.0.0.1:9093
```

Set `TELEGRAM_CHAT_ID` in `.env` (numeric ops group/chat) so Alertmanager can post.
Uses `secrets/telegram_token` (same bot as coordinator). Empty chat id → null receiver (UI only).

## Critical alerts (§8.2)

| Alert | Meaning | First action |
|---|---|---|
| `AgentHeartbeatStale` | adapter/router silent > 5m | `docs/runbooks/agent-stuck.md` |
| `TunnelDown` | no cloudflared HA connection | `docs/runbooks/tunnel.md` (needs profile `ingress`) |
| `QueueDepthHigh` / `QueueOldestAgeHigh` | backlog | check pause flag, Hermes health, Ollama |
| `WebhookAuthFailRate` | secret mismatch or probe | rotate/compare `gitlab_webhook_secret` |
| `NeedsHumanBacklog` | HITL stuck | ping ops in Telegram |
| `ApprovalLatencyHigh` | humans slow | escalate in ops chat |
| `TaskDurationP95High` | agent too slow | check LLM / self-heal loops |

Critical alerts repeat every **15 minutes** until resolved (Alertmanager `repeat_interval`).

## Silence / ack

Use Alertmanager UI → Silence, or temporarily comment the rule in `observability/alerts.yml` and
`curl -X POST http://127.0.0.1:9090/-/reload`.
