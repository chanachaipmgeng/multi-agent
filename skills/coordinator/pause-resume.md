---
name: pause-resume
description: Admin kill switch — pause/resume agent dispatch via /internal/control.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, coordinator, control]
    category: emaw
    owner: coordinator
    phase: 3
    hitl: admin only
    inputs: [agent|all]
---

# Skill: pause-resume

คำสั่ง admin: `/pause <agent|all>` · `/resume <agent|all>` หรือข้อความ `pause …` / `resume …`
(Hermes อาจไม่ map slash command → รองรับทั้งสองรูปแบบ — ดู `docs/hermes-capability-check.md`)

## ขั้นตอน

1. ตรวจว่าผู้ส่งเป็น admin (gateway จะคืน 403 ถ้าไม่ใช่)
2. Parse เป้า: `all` / `dev-frontend` / `dev-backend` / `reviewer` / `qa` / `devops`
3. Pause:
   ```bash
   curl -fsS -X POST "$GATEWAY/internal/control/pause" \
     -H "Authorization: Bearer $API_SERVER_KEY" \
     -H "X-EMAW-User-Id: <id>" -H "Content-Type: application/json" \
     -d '{"agent":"<agent|all>"}'
   ```
4. Resume: เหมือนกันที่ `/internal/control/resume`
5. ตอบ `⏸️ paused <agent>` หรือ `▶️ resumed <agent>`

Worker ที่ pause อยู่จะจบงานปัจจุบันแล้วไม่รับงานใหม่ (ไม่ XREADGROUP)
