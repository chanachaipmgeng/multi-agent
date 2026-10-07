---
name: deploy-prod
description: Production deploy proposal — always requires approver HITL; never auto-deploy.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, devops, deploy]
    category: emaw
    owner: devops
    phase: 3
    hitl: approver only (DECISION-8)
    inputs: [task_id, project, target, change_summary]
---

# Skill: deploy-prod

เสนอ deploy ไป production — **ห้ามรัน deploy จริงก่อนได้ `approved` จาก role `approver`**

## ขั้นตอน

1. อ่าน `project-standards.md` / runbook deploy ของโปรเจกต์
2. สรุปสิ่งที่จะ deploy: image/tag, migration?, rollback plan, blast radius
3. สร้างคำขอ approval:
   `action: deploy_prod`, `required_role: approver`, timeout 30 นาที
   ผ่าน coordinator `human-approval-gate` (API `/internal/approvals`)
4. รอ — `rejected` / `expired` → จบโดยไม่แตะ prod
5. เมื่อ `approved` — รันขั้นตอน deploy ตาม runbook ใน sandbox/CI trigger ที่อนุญาต
6. รายงานผล + **HANDOFF** `reason: done` (หรือ `needs_human` ถ้าพัง)

## ห้าม

- deploy โดยไม่มี approval จาก approver
- ข้าม migration / ข้าม rollback plan
- ใช้สิทธิ์ developer อนุมัติเอง (DECISION-8)
