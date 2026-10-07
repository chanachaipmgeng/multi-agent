---
name: route-task
description: Parse Telegram tags, pick project/worker, POST /internal/tasks (RBAC-gated).
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, coordinator, routing]
    category: emaw
    owner: coordinator
    phase: 3
    hitl: none (creates task only)
    inputs: [message_text, telegram_user_id]
---

# Skill: route-task

สร้างงานจากข้อความ Telegram แล้วส่งเข้า `stream:tasks` ผ่าน gateway internal API
(DECISION-16 — deterministic routing อยู่ใน router; skill นี้จัดการกฎ 3/5: แท็ก + ถามผู้ใช้)

## Gateway

```
GATEWAY=${EMAW_GATEWAY_URL:-http://webhook-gateway:8700}
AUTH="Authorization: Bearer $API_SERVER_KEY"
USER="X-EMAW-User-Id: <telegram_user_id ของผู้ส่ง>"
```

## ขั้นตอน

1. **Parse แท็ก** จากข้อความ:
   | แท็ก | worker |
   |---|---|
   | `[Frontend]` / `[FE]` | `dev-frontend` |
   | `[Backend]` / `[BE]` | `dev-backend` |
   | `[CI]` / `[DevOps]` | `devops` |
   | `[QA]` | `qa` |
   | `[Review]` | `reviewer` |
   ไม่มีแท็ก → ถามผู้ใช้ให้เลือก (กฎ 5 / `unknown_intent: ask_user`) แล้วหยุด
2. **เลือกโปรเจกต์** — จาก `projects.yaml`:
   - ถ้าข้อความระบุชื่อโปรเจกต์ชัด → ใช้ค่านั้น
   - ถ้า worker มีโปรเจกต์เดียวใน `allowed_workers` → ใช้โปรเจกต์นั้น
   - ถ้ากำกวม → ถามผู้ใช้รายการโปรเจกต์ แล้วหยุด
3. **สร้าง task**:
   ```bash
   curl -fsS -X POST "$GATEWAY/internal/tasks" \
     -H "$AUTH" -H "$USER" -H "Content-Type: application/json" \
     -d "{
       \"type\": \"feature\",
       \"project\": \"<key>\",
       \"assigned_to\": \"<worker>\",
       \"skill\": \"dev-flow\",
       \"instruction\": \"<ข้อความหลังตัดแท็ก>\",
       \"labels\": [\"area:<frontend|backend|ci|qa>\"]
     }"
   ```
4. **ตอบผู้ใช้** — `🤖 รับงาน (trace <trace_id>) มอบหมาย <worker> · task <task_id>`
5. ถ้าได้ HTTP 403 → แจ้งว่า RBAC ปฏิเสธ (role/project) แล้วจบ

## ห้าม

- route ด้วยการเดาเมื่อไม่มีแท็ก / โปรเจกต์กำกวม
- เรียก Hermes worker โดยตรง — ต้องผ่าน gateway → router เท่านั้น

## Stop conditions

| สภาพ | ผล |
|---|---|
| ไม่มีแท็ก / โปรเจกต์กำกวม | ถามผู้ใช้ แล้วจบรอบนี้ |
| 403 / 401 จาก gateway | รายงาน RBAC/auth แล้วจบ |
| 200 queued | ตอบ trace แล้ว `DONE` |
