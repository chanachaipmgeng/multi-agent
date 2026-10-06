---
name: human-approval-gate
owner: coordinator
phase: 0
hitl: this skill IS the gate
inputs: [task_id, action, payload, requested_by]
policy: /config/policies/platform-policy.yaml#human_in_the_loop
---

# Skill: human-approval-gate

ด่านอนุมัติก่อนทุก action ที่มีผลกระทบสูง (push/MR, deploy, migration, infra change, budget increase)
หลักการ: **ไม่ตอบ = ไม่อนุมัติ** และ **ห้าม push protected branch แม้จะได้รับอนุมัติ**

## ขั้นตอน

1. **ตรวจ policy** — หา `action` ใน `platform-policy.yaml#human_in_the_loop`
   - `approval: forbidden` (เช่น push ไป `main`) → ตอบ `rejected_by_policy` ทันที ไม่ถามใคร บันทึก audit
   - `approval: none` → ปล่อยผ่าน บันทึก audit
   - `approval: required` → ไปข้อ 2
2. **ตรวจผู้มีสิทธิ์** — จาก `approver_role` (developer ของ repo / approver / requester) และ `rbac.yaml`
   ผู้ขอ (agent) ไม่มีวันเป็นผู้อนุมัติ; ใน production `approver` ต้องไม่ใช่ developer คนเดียวกัน (DECISION-8)
3. **สรุปสิ่งที่จะทำ** ให้คนอ่านรู้เรื่องใน 5–8 บรรทัด: task, project, branch, จำนวน commit, diff stat, ผล test,
   สิ่งที่จะเกิดขึ้นเมื่อกด Approve, และ `payload_hash = sha256(payload)`
4. **สร้างคำขอ** — บันทึกแถวใน `approvals` (`task_id`, `action`, `payload_hash`, `nonce` สุ่ม, `timeout_at`)
   เปลี่ยน task เป็น `AWAITING_APPROVAL` และบันทึก audit `approval.requested`
5. **ถามผ่าน Telegram** — ส่งสรุป + ปุ่ม `[✅ Approve] [❌ Reject]` ที่ผูก `task_id` + `nonce`
   (ถ้า inline keyboard ใช้ไม่ได้ ให้ถาม `⚠️ ต้องการอนุมัติคำสั่งนี้หรือไม่? พิมพ์ y <nonce> / n <nonce>`)
6. **หยุดรอ (PAUSE)** — ห้ามทำงานต่อหรือ "ถือว่าอนุมัติ" ไม่ว่ากรณีใด
7. **ตัดสิน**
   - คำตอบจาก user id ที่มีสิทธิ์ + nonce ตรง → `approved`: บันทึก `decided_by`, `decided_at`, audit `approval.granted`
     → แจ้ง worker ให้ดำเนินการ **เฉพาะ action ที่ hash ตรงกับที่ขอ**
   - `Reject` → `rejected`: task → `CANCELLED` (หรือกลับ `IN_PROGRESS` ถ้าผู้ใช้ให้คำแนะนำเพิ่ม) audit `approval.rejected`
   - คำตอบจากคนไม่มีสิทธิ์ / nonce ไม่ตรง → เพิกเฉย + แจ้งว่า "ไม่มีสิทธิ์อนุมัติ" + audit `approval.unauthorized_attempt`
   - หมดเวลา (`timeout_minutes`) → `expired`: task → `EXPIRED` **ไม่มีการกระทำใด ๆ** audit `approval.expired` แจ้งผู้ขอ
8. **รายงานผล** กลับผู้ใช้และ worker พร้อม `trace_id`

## ตัวอย่างข้อความ
```
⚠️ ขออนุมัติ: push branch + เปิด MR
Task t-20261006-a1b2c3 · frontend-app · fix/issue-89
3 commits · +84 −12 · check:all ✅ 42 passed (1m12s)
จะเกิดอะไร: push origin fix/issue-89 → MR "fix: mobile overflow (Closes #89)" → ขอรีวิว
หมดเวลาใน 30 นาที · hash 9f3a…c2
[✅ Approve] [❌ Reject]
```
