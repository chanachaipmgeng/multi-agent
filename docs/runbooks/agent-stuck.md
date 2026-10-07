# Runbook — Agent / adapter stuck

## Symptoms

- Task stays `IN_PROGRESS` / `ASSIGNED` > 45 min
- Adapter log shows repeated Hermes poll / connection errors
- `agent_heartbeat_timestamp` stale (> 5 min) on `/metrics`
- Coordinator unresponsive on Telegram

## Checks

```bash
docker compose --profile agents ps
docker logs emaw-adapter-<role> --since 30m
docker logs emaw-<role> --since 30m
curl -fsS http://127.0.0.1:8700/metrics | grep task_state_total
docker exec multi-agent-redis-1 redis-cli XPENDING stream:<role> adapter-<role>
```

## Actions

1. **Pause** the role: `POST /internal/control/pause {"agent":"<role>"}` (admin Bearer).
2. If Hermes API hung: `docker compose restart <role>` (API `:8642`).
3. If adapter PEL stuck: after fix, wait `CLAIM_MIN_IDLE_MS` (workers 10 min; router 30 s) or `XCLAIM` to the stable consumer.
4. Dead-letter after 3 deliveries → inspect `stream:dead-letter`, open incident, set task `FAILED` if needed.
5. **Resume** when healthy; confirm heartbeat gauges move.
