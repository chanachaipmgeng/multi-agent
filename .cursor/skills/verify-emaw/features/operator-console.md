# Feature: Operator Console (DECISION-20)

Prove the thin console APIs and optional compose profile without requiring a browser.

## Preconditions

- Gateway up with `HERMES_API_KEY` and `config/rbac.yaml` (admin user `987654321` or `VERIFY_EMAW_USER_ID`).
- Optional: `make up-console` for HTTP `:8088` (build needs Docker).

## Steps

1. Health: `curl -fsS "$GATEWAY_URL/healthz"`
2. List projects:

```bash
curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
  "$GATEWAY_URL/internal/projects" | tee evidence/projects.json
```

Expect `"count"` ≥ 1 and keys include known projects.

3. Control status includes `paused_agents`:

```bash
curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
  "$GATEWAY_URL/internal/control/status" | tee evidence/control-status.json
```

4. If console profile is up: `curl -fsS -o /dev/null -w "%{http_code}" http://127.0.0.1:${CONSOLE_PORT:-8088}/` → `200`.

## Pass

- Steps 1–3 succeed; step 4 only when `operator-console` is running.
