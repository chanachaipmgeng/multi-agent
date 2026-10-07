---
name: safe-mode
description: Toggle platform safe-mode — every write requires approval.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, coordinator, control]
    category: emaw
    owner: coordinator
    phase: 3
    hitl: admin only
    inputs: [on|off]
---

# Skill: safe-mode

`/safe-mode on|off` หรือข้อความ `safe-mode on|off` (admin)

## ขั้นตอน

```bash
curl -fsS -X POST "$GATEWAY/internal/control/safe-mode" \
  -H "Authorization: Bearer $API_SERVER_KEY" \
  -H "X-EMAW-User-Id: <id>" -H "Content-Type: application/json" \
  -d '{"enabled": true}'   # หรือ false
```

เมื่อเปิด: router/worker ใส่ `constraints.require_approval=true` ในทุก task
และ prompt เตือน SAFE MODE — action ที่เขียน repo ต้องรอ approval

Circuit breaker อัตโนมัติ (`tasks_failed > 3 / 15m` หรือ token budget/ชม.)
ก็เปิด safe-mode ให้เช่นกัน และแจ้ง admin ทาง Telegram
