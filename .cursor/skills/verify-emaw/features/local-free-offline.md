# Local-free / air-gap / LAN-hybrid LLM (DECISION-15)

Prove the shared `inference-ollama` path, model presence, and (when brought up via
`up-offline` or `up-lan`) Console + observability as the operator surface.

Runbooks: [`docs/offline-airgap.md`](../../../../docs/offline-airgap.md),
[`docs/environments.md`](../../../../docs/environments.md) (LAN + local LLM),
[`docs/roadmap-next.md`](../../../../docs/roadmap-next.md).

## Sub-features

- `inference` — Ollama on loopback with `LOCAL_LLM_MODEL` present.
- `agents-local` — six Hermes agents use `model.provider=custom`.
- `socraticode` — embedding Ollama + Qdrant ready for reviewer MCP.
- `console-optional` — `:8088` returns 200 when `up-offline` / `up-lan` / `up-console` was used.
- `console-lan` — when `CONSOLE_BIND=0.0.0.0`, host LAN IP `:8088` returns 200.

## How to get to it (user POV)

```bash
make up-local-free && make local-llm-pull
# LAN hybrid (online host, local Ollama, Console on LAN IP):
#   CONSOLE_BIND=0.0.0.0 make up-lan && make local-llm-pull
# or after pack/load on GPU host:
# make load-offline && make up-offline
make local-free-check
```

## Driving it with verify-emaw

Preconditions:

- `make up-local-free` / `up-lan` / `up-offline` completed; model pulled or restored from pack.

Primary operator proof after migrate (Phase F) or LAN hybrid:

```bash
make offline-acceptance
```

- **Smoke (skill helper).** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline`.
- **Proof.** `make offline-acceptance` prints `PASSED`; or `evidence/<RUN_ID>/local-free-check.txt` exit 0 and optional `console-http.txt` shows `200`.

## Gotchas

- `LOCAL_LLM_MODEL` must match what was pulled/packed — sync with `make sync-local-llm` before checks.
- Bare profile `onprem-llm` has no NVIDIA devices; GPU hosts must use local-free compose override.
- Pack/load itself is not driven here (large tarballs); prove runtime after load with this feature.
- Air-gap / LAN hybrid before Telegram: skip Telegram/tunnel proofs; Console is primary HITL.
- `offline-acceptance` Grafana check uses `GRAFANA_PORT` (7920 may be `3030`).
