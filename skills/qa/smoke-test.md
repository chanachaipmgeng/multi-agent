---
name: smoke-test
description: Run a short smoke check against the worktree preview port (e2e_port).
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, qa, smoke]
    category: emaw
    owner: qa
    phase: 3
    hitl: none
    inputs: [task_id, project, workspace_path, e2e_port, base_url?]
---

# Skill: smoke-test

รันชุด smoke สั้น ๆ บน preview ของ worktree (`projects.yaml#e2e_port` เช่น 3001)

## ขั้นตอน

1. ยืนยันว่าแอป preview ฟังอยู่ที่ `http://127.0.0.1:<e2e_port>` (หรือ `base_url`)
2. รัน smoke ตามโปรเจกต์ เช่น `npm run smoke` / `pytest -q -m smoke` / `curl -fsS …/healthz`
3. ถ้าพัง → รายงานอาการ + HANDOFF ไป `default_worker` (`reason: review`)
4. ถ้าผ่าน → HANDOFF `reason: done`

## ห้าม

แก้ business logic · skip test เพื่อให้ผ่าน · เปิดพอร์ตนอกช่วงที่อนุญาต
