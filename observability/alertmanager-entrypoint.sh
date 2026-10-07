#!/bin/sh
# Render Alertmanager config with Telegram credentials (D4.1).
set -eu
TOKEN_FILE="${TELEGRAM_TOKEN_FILE:-/run/secrets/telegram_token}"
CHAT_ID="${TELEGRAM_CHAT_ID:-}"
TOKEN=""
if [ -s "$TOKEN_FILE" ]; then
  TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
fi

OUT=/tmp/alertmanager.yml
if [ -n "$TOKEN" ] && [ -n "$CHAT_ID" ]; then
  cat > "$OUT" <<EOF
global:
  resolve_timeout: 5m
route:
  receiver: telegram
  group_by: ["alertname", "severity"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 15m
  routes:
    - matchers:
        - severity="critical"
      receiver: telegram
      repeat_interval: 15m
receivers:
  - name: telegram
    telegram_configs:
      - bot_token: "$TOKEN"
        chat_id: $CHAT_ID
        parse_mode: HTML
        message: |
          <b>{{ .Status | toUpper }}</b> {{ .CommonLabels.alertname }}
          {{ range .Alerts }}{{ .Annotations.summary }}
          {{ end }}
inhibit_rules: []
EOF
  echo "alertmanager: telegram receiver enabled (chat_id=$CHAT_ID)"
else
  cat > "$OUT" <<'EOF'
global:
  resolve_timeout: 5m
route:
  receiver: noop
  group_by: ["alertname"]
receivers:
  - name: noop
inhibit_rules: []
EOF
  echo "alertmanager: TELEGRAM_CHAT_ID or token empty — noop receiver (alerts visible in UI only)"
fi
exec /bin/alertmanager --config.file="$OUT" --storage.path=/alertmanager "$@"
