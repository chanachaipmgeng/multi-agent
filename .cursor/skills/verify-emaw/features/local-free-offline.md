# Local-free / air-gap LLM (DECISION-15)

Prove the shared `inference-ollama` path, model presence, and (when brought up via `up-offline`) Console + observability as the air-gap operator surface.

Runbook: [`docs/offline-airgap.md`](../../../../docs/offline-airgap.md).

## Sub-features

- `inference` — Ollama on loopback with `LOCAL_LLM_MODEL` present.
- `agents-local` — six Hermes agents use `model.provider=custom`.
- `socraticode` — embedding Ollama + Qdrant ready for reviewer MCP.
- `console-optional` — `:8088` returns 200 when `up-offline` / `up-console` was used.

## How to get to it (user POV)

```bash
make up-local-free && make local-llm-pull
# or after pack/load on GPU host:
# make load-offline && make up-offline
make local-free-check
```

## Driving it with verify-emaw

Preconditions:

- `make up-local-free` (or `up-offline`) completed; model pulled or restored from pack.

- **Smoke.** Run `bash .cursor/skills/verify-emaw/bin/verify-emaw.sh drive local-free-offline`.
- **Proof.** `evidence/<RUN_ID>/local-free-check.txt` ends with success (script exit 0); optional `console-http.txt` shows `200`.

## Gotchas

- `LOCAL_LLM_MODEL` must match what was pulled/packed — sync with `make sync-local-llm` before checks.
- Bare profile `onprem-llm` has no NVIDIA devices; GPU hosts must use local-free compose override.
- Pack/load itself is not driven here (large tarballs); prove runtime after load with this feature.
- Air-gap: skip Telegram/tunnel proofs; Console is primary HITL.
