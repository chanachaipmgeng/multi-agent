# queue-adapter (Phase 3)

Redis Streams ↔ Hermes bridge with two modes (DECISION-16):

| `MODE` | Role | Consumes | Produces |
|---|---|---|---|
| `router` | fan-out + results state machine | `stream:tasks`, `stream:results` | `stream:<role>`, PG handoffs/state |
| `worker` | per-role sidecar | `stream:<role>` | Hermes `/v1/runs`, `stream:results` |

Also: pause/safe-mode control keys, circuit breaker, MinIO artifact upload, Prometheus `/metrics` on `:9100`.

Legacy Phase 1–2 single consumer: compose profile `single` (`queue-adapter` service).
