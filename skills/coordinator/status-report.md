---
name: status-report
description: Summarise open tasks / approvals via GET /internal/tasks.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, coordinator, status]
    category: emaw
    owner: coordinator
    phase: 3
    hitl: none
    inputs: [project?, state?]
---

# Skill: status-report

สรุปสถานะงานให้ผู้ใช้ Telegram (viewer ขึ้นไปผ่านได้)

## ขั้นตอน

1. เรียก:
   ```bash
   curl -fsS "$GATEWAY/internal/tasks?project=<optional>&state=<optional>&limit=50" \
     -H "Authorization: Bearer $API_SERVER_KEY" \
     -H "X-EMAW-User-Id: <telegram_user_id>"
   ```
2. จัดกลุ่มตาม `state` แล้วตาม `assigned_to`
3. ไฮไลต์งาน `AWAITING_APPROVAL` / `NEEDS_HUMAN` / `FAILED`
4. ตอบเป็นข้อความสั้น ๆ ภาษาไทย:

```
📊 สถานะ EMAW
IN_PROGRESS: n · REVIEW: n · AWAITING_APPROVAL: n · FAILED: n
- <task_id> [<state>] <project> → <assigned_to>
…
```

## Stop conditions

403 → แจ้งสิทธิ์ไม่พอ · ว่าง → "ไม่มีงานค้าง"
