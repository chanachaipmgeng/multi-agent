---
name: write-e2e
description: Write/adjust Playwright E2E for the MR feature; run on worktree at e2e_port; report coverage.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, qa, playwright]
    category: emaw
    owner: qa
    phase: 3
    hitl: none for tests; push via human-approval-gate
    inputs: [task_id, project, workspace_path, e2e_port, branch]
---

# Skill: write-e2e

เขียน/ปรับ Playwright E2E สำหรับฟีเจอร์ใน MR แล้วรันบน worktree ที่พอร์ต `e2e_port` จาก `projects.yaml`

## ขั้นตอน

1. อ่าน `project-standards.md` + diff ของ branch งาน
2. เขียน/แก้สเปกภายใต้ path ที่อนุญาตใน AGENT.md (`e2e/**`, `**/*.spec.ts`, …)
3. สตาร์ท preview บน `e2e_port` (เช่น 3001) ตามสคริปต์โปรเจกต์
4. รัน `npx playwright test` (หรือคำสั่งใน rulebook) · self-heal ≤ 3
5. Secret scan + commit `test: …`
6. ขอ approval ก่อน push (ถ้าต้องการ) ผ่าน coordinator
7. **HANDOFF block** — `reason: done` หรือส่งต่อ `default_worker` ถ้าพบบั๊กจริง

## ห้าม

แก้ business logic นอก test dirs · `.skip` เพื่อให้ผ่านโดยไม่ระบุใน handoff
