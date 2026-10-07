# queue-adapter (Phase 3)

Redis Streams ↔ Hermes bridge with two modes (DECISION-16):

| `MODE` | Role | Consumes | Produces |
|---|---|---|---|
| `router` | fan-out + results state machine | `stream:tasks`, `stream:results` | `stream:<role>`, PG handoffs/state |
| `worker` | per-role sidecar | `stream:<role>` | Hermes `/v1/runs`, `stream:results` |

Also: pause/safe-mode control keys, circuit breaker, MinIO artifact upload (AWS SigV4),
Prometheus `/metrics` on `:9100`.

### Router notes (from Phase 3 live drill)

- Do **not** pass Redis `BLOCK 0` (means wait forever). Non-blocking reads omit `block`.
- Pause leaves messages in the PEL; resume drains via `XREADGROUP … 0` (pending) before `>`.
- Compose sets stable `CONSUMER_NAME=router` and `CLAIM_MIN_IDLE_MS=30000` so deferred work
  survives container recreate within ~30s.
- Artifacts: path-style `PUT` with SigV4 — no HTTP Basic, no `x-amz-acl` (MinIO rejects both).

Legacy Phase 1–2 single consumer: compose profile `single` (`queue-adapter` service).
Do not run `single` alongside the Phase 3 router — both claim `stream:tasks`.
