---
name: human-approval-gate
description: HITL gate for push/MR, deploy, migration, infra — silence or timeout means no action.
version: 1.1.0
metadata:
  hermes:
    tags: [emaw, hitl, approval]
    category: emaw
    owner: coordinator
    phase: 0
    hitl: this skill IS the gate
    inputs: [task_id, action, payload, requested_by]
    policy: /config/policies/platform-policy.yaml#human_in_the_loop
---

# Skill: human-approval-gate

ด่านอนุมัติก่อนทุก action ที่มีผลกระทบสูง (push/MR, deploy, migration, infra change, budget increase)
หลักการ: **ไม่ตอบ = ไม่อนุมัติ** และ **ห้าม push protected branch แม้จะได้รับอนุมัติ**

DECISION-17: ใช้ข้อความ `y <nonce>` / `n <nonce>` (ไม่พึ่ง Telegram inline keyboard callback)
เพราะ Hermes เป็นผู้ consume Telegram update เอง — Hermes native approval UI ใช้กับคำสั่ง terminal อันตราย

## Gateway

```
GATEWAY=${EMAW_GATEWAY_URL:-http://webhook-gateway:8700}
AUTH="Authorization: Bearer $API_SERVER_KEY"
USER="X-EMAW-User-Id: <telegram_user_id>"
```

## ขั้นตอน

1. **ตรวจ policy** — หา `action` ใน `platform-policy.yaml#human_in_the_loop`
   - `approval: forbidden` → ตอบ `rejected_by_policy` ทันที ไม่ถามใคร
   - `approval: none` → ปล่อยผ่าน บันทึก audit
   - `approval: required` → ไปข้อ 2
2. **ตรวจผู้มีสิทธิ์** — จาก `approver_role` + `rbac.yaml` (DECISION-8: approver ≠ developer)
3. **สรุปสิ่งที่จะทำ** 5–8 บรรทัด + `payload_hash`
4. **สร้าง approval ผ่าน API**:
   ```bash
   curl -fsS -X POST "$GATEWAY/internal/approvals" \
     -H "$AUTH" -H "$USER" -H "Content-Type: application/json" \
     -d "{
       \"task_id\": \"<task_id>\",
       \"action\": \"<action>\",
       \"payload\": {…},
       \"required_role\": \"developer|approver\",
       \"timeout_min\": 30,
       \"requested_by\": \"<agent>\"
     }"
   ```
   ได้ `nonce` + `timeout_at`
5. **ถามผ่าน Telegram** — สรุป + ข้อความ:
   `⚠️ ต้องการอนุมัติหรือไม่? พิมพ์ y <nonce> / n <nonce> (หมดเวลา 30 นาที)`
6. **หยุดรอ (PAUSE)** — ห้ามทำงานต่อหรือ "ถือว่าอนุมัติ"
7. **ตัดสิน** เมื่อได้คำตอบ:
   ```bash
   curl -fsS -X POST "$GATEWAY/internal/approvals/<nonce>/decide" \
     -H "$AUTH" -H "X-EMAW-User-Id: <approver_id>" \
     -H "Content-Type: application/json" \
     -d '{"decision":"approved"}'   # หรือ rejected
   ```
   - `approved` → แจ้ง worker ให้ทำ **เฉพาะ action ที่ hash ตรง**
   - `rejected` → task `CANCELLED`
   - timeout / 410 → `EXPIRED` ไม่มีการกระทำ
8. **รายงานผล** พร้อม `trace_id`

## ตัวอย่างข้อความ
```
⚠️ ขออนุมัติ: push branch + เปิด MR
Task t-20261006-a1b2c3 · frontend-app · fix/issue-89
3 commits · +84 −12 · check:all ✅ 42 passed (1m12s)
จะเกิดอะไร: push origin fix/issue-89 → MR "fix: mobile overflow (Closes #89)"
หมดเวลาใน 30 นาที · hash 9f3a…c2
พิมพ์: y <nonce>   หรือ   n <nonce>
```
