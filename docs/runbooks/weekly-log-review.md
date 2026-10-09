# Weekly log review (D4.7)

**When:** first **two weeks after production go-live**, then monthly or as needed.  
**Who:** ops admin + one developer (optional).  
**Inputs:** Grafana EMAW dashboards, Loki queries, `audit_events`, Alertmanager history, Telegram ops chat.

## Agenda (30–45 min)

1. **Critical alerts** — any `AgentHeartbeatStale`, `TunnelDown`, auth-fail spikes? Root cause + follow-up owner.
2. **Queue / duration** — `queue_depth`, `task_duration_seconds` p95; stuck `NEEDS_HUMAN` / `AWAITING_APPROVAL`.
3. **Cost proxy** — token burn by agent (`llm_tokens_total` / `emaw_tokens_total`); compare to DECISION-7 budgets.
4. **Security / secrets** — webhook auth fails, accidental secret in logs (redaction gaps), rotations due.
5. **Agent mistakes** — bad MRs, rollbacks ([rollback-mr.md](rollback-mr.md)); rulebook/skill changes.
6. **Actions** — list tickets; update skills or `project-standards.md` if a pattern repeats.

## Log (copy a row per meeting)

| Week | Date | Attendees | Alerts reviewed | Findings | Actions | Owner |
|---|---|---|---|---|---|---|
| W1 | | | | | | |
| W2 | | | | | | |

## Suggested Loki / Prom queries

- Auth fails: `rate(webhook_auth_fail_total[1h])`
- Stale agents: `time() - agent_heartbeat_timestamp > 300`
- Failures: `rate(emaw_tasks_failed_total[1h])`
- Loki: `{compose_service=~"webhook-gateway|router|adapter-.*"} |= "error"` (after redaction)
- Trace one webhook: see [trace-by-event.md](trace-by-event.md) — LogQL `|= \`event_uuid=<UUID>\`` then follow `task_id` / `trace_id`

Do **not** paste raw secrets into this log even if redaction failed — fix the pipeline instead.
