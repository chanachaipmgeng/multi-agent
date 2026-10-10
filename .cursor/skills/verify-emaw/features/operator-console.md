# Feature: Operator Console (DECISION-20)

Prove the thin console APIs and optional compose profile without requiring a browser.
Includes Dispatch (`POST /internal/tasks`) used by the Console Dispatch page.

## Preconditions

- Gateway up with `HERMES_API_KEY` and `config/rbac.yaml` (admin user `987654321` or `VERIFY_EMAW_USER_ID`).
- Optional: `make up-console` or `make up-lan` for HTTP `:8088` (build needs Docker).
- LAN hybrid: `CONSOLE_BIND=0.0.0.0` — also prove `http://<host-ip>:8088/` → 200.

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

4. Audit + approvals list (status filters used by console Audit / History tabs):

```bash
curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
  "$GATEWAY_URL/internal/approvals?status=pending" | tee evidence/approvals-pending.json
curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
  "$GATEWAY_URL/internal/approvals?status=decided" | tee evidence/approvals-decided.json
# Audit requires task_id or trace_id — use a known id from list-tasks if available:
TASK_ID=$(curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
  "$GATEWAY_URL/internal/tasks?limit=1" | python3 -c "import sys,json; t=json.load(sys.stdin).get('tasks') or []; print(t[0]['task_id'] if t else '')")
if [ -n "$TASK_ID" ]; then
  curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
    -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
    "$GATEWAY_URL/internal/audit?task_id=$TASK_ID" | tee evidence/audit.json
fi
```

5. If console profile is up: `curl -fsS -o /dev/null -w "%{http_code}" http://127.0.0.1:${CONSOLE_PORT:-8088}/` → `200`.
   When `CONSOLE_BIND=0.0.0.0`, also hit `http://$(hostname -I | awk '{print $1}'):${CONSOLE_PORT:-8088}/` (or the known LAN IP) → `200`.

6. Dispatch path (Console Manual Task Dispatcher):

```bash
curl -fsS -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "X-EMAW-User-Id: ${VERIFY_EMAW_USER_ID:-987654321}" \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"feature\",\"project\":\"sandbox-smoke\",\"instruction\":\"verify-emaw dispatch prove\",\"labels\":[\"area:backend\"],\"idempotency_key\":\"verify-emaw:$(date +%s)\"}" \
  "$GATEWAY_URL/internal/tasks" | tee evidence/dispatch-create.json
```

Expect `"status":"queued"` and a `task_id`. Or: `make simulate-operator CMD=create-task`.

## Pass

- Steps 1–4 succeed (step 4 audit only when ≥1 task exists); step 5 when `operator-console` is running; step 6 when proving Dispatch.
