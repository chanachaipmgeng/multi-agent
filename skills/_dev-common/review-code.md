---
name: review-code
description: Self-review staged/diff against project-standards.md before handoff; ask before auto-fixing.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, review]
    category: emaw
    owner: [dev-frontend, dev-backend]
    phase: 0
    hitl: ask before auto-fixing
    inputs: [task_id, project]
---

# Skill: review-code

Self-review ก่อนส่งงาน เทียบ diff กับ `project-standards.md` และหาช่องโหว่ความปลอดภัย

## ขั้นตอน

1. `git diff --staged` (ถ้าว่าง ใช้ `git diff origin/main...HEAD`) ใน worktree ของ task — รีวิวเฉพาะไฟล์ใน diff
2. อ่าน `project-standards.md` แล้วตรวจทีละหัวข้อ:
   - **สถาปัตยกรรม**: ตรงตาม stack rules (เช่น Signals ไม่ใช่ BehaviorSubject, routers/services/models แยกชั้น)
   - **ความปลอดภัย**: ไม่มี secret hardcode, ทุก endpoint ตรวจ JWT/RBAC, ไม่มี raw SQL ต่อ string, ไม่ส่ง stack trace ให้ client
   - **คุณภาพ**: ไม่มี `any`, ฟังก์ชันซับซ้อนเกิน 10 ต้องแยก, ไม่มีโค้ดซ้ำ
   - **Test**: โค้ดใหม่มี test คลุม, ไม่มี `.skip` / `--passWithNoTests` ที่ไม่ตั้งใจ
3. สรุปผลเป็นภาษาไทย 3 กลุ่ม:
   - 🛑 **บั๊กร้ายแรง / ช่องโหว่** (ต้องแก้ก่อน commit)
   - ⚠️ **สิ่งที่ควรปรับปรุง**
   - 💡 **ข้อเสนอแนะ**
   แต่ละข้อระบุ `ไฟล์:บรรทัด` และวิธีแก้สั้น ๆ
4. ถ้ามีข้อ 🛑 หรือ ⚠️ ให้ถามผ่าน coordinator: "ต้องการให้แก้ไขตามข้อเสนอแนะอัตโนมัติหรือไม่ (y/n)?" — **รอคำตอบ**
5. ถ้า `y`: แก้ → รัน `<test_command>` ซ้ำ (self-heal ≤ 3) → `gitleaks protect --staged` → commit `refactor:`/`fix:`
   ถ้า `n` หรือไม่ตอบ: จบที่รายงาน ไม่แก้ไข
6. แนบสรุปรีวิวใน handoff ไป reviewer (Phase 3) หรือใน MR description (Phase 1)

## ห้าม
- แก้โค้ดก่อนได้รับ `y`
- รีวิว/อ่านไฟล์ที่ตรงกับ `.agentignore`
- "ผ่าน" งานที่ยังมีข้อ 🛑 ค้างอยู่
