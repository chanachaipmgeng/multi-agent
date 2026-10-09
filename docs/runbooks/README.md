# Runbooks index (E14 / D4.7)

Design checklist **E14** requires: tunnel down, agent stuck, token rotation, restore, incident from agent mistake (rollback MR).

| Runbook | E14 item | Path |
|---|---|---|
| Tunnel down / flap | tunnel down | [tunnel.md](tunnel.md) |
| Agent / adapter stuck | agent stuck | [agent-stuck.md](agent-stuck.md) |
| Rotate secrets | token rotation | [token-rotation.md](token-rotation.md) |
| Backup & restore | restore | [restore.md](restore.md) |
| Bad agent MR | incident / rollback | [rollback-mr.md](rollback-mr.md) |
| Alerts (ops) | (supporting) | [alerts.md](alerts.md) |
| Weekly log review | D4.7 go-live | [weekly-log-review.md](weekly-log-review.md) |
| Trace by event UUID | (supporting) | [trace-by-event.md](trace-by-event.md) |
| Audit export (object lock) | D4.4 prep | [audit-export.md](audit-export.md) |
| Ingress Access/WAF checklist | D4.3 prep | generated: `cloudflared/access-and-waf.md` via `make ingress-render` |
| Offline / air-gap pack (GPU host) | (supporting) | [../offline-airgap.md](../offline-airgap.md) — phases A–F, `preflight-offline` / `offline-acceptance` / `pack-offline` |

After production go-live, fill [weekly-log-review.md](weekly-log-review.md) for the first **two weeks** (one row per review meeting).

Operator proofs: `.cursor/skills/verify-emaw` — features include `local-free-offline` and `operator-console`.
