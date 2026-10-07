---
name: review-with-socraticode
description: Diff-scoped SocratiCode MCP review; hand proposed patches to the owning dev agent — never apply them.
version: 1.1.0
metadata:
  hermes:
    tags: [emaw, review, socraticode]
    category: emaw
    owner: reviewer
    phase: 2
    hitl: none for read-only review; handoff only — never push
    inputs: [task_id, project, branch, workspace_path, base_ref]
    requires: make up-socraticode (Ollama embeddings + Qdrant)
---

# Skill: review-with-socraticode

รีวิวเฉพาะไฟล์ใน git diff ด้วย **SocratiCode MCP tools** แล้วส่งข้อเสนอ/unified diff กลับไปยัง **dev agent เจ้าของ repo** — **ห้าม apply / commit / push เอง**

SocratiCode is AGPL local-first (DECISION-6): no API key. Tools live under `mcp_servers.socraticode`.

## Preconditions

1. `mcp_servers.socraticode` enabled in `hermes-data/reviewer/config.yaml`
2. Infra up: `make up-socraticode` (or `make up-local-free`) — compose DNS
   `OLLAMA_URL=http://socraticode-ollama:11434`, `QDRANT_URL=http://socraticode-qdrant:6333`
3. Project has `.socraticodeignore` at root (from `workspace/_templates/`)

ถ้า precondition ไม่ครบ → `NEEDS_HUMAN` พร้อมรายการที่ขาด แล้วจบ (อย่า fallback เป็นรีวิวเต็ม repo ด้วยมือ)

## ขั้นตอน

1. **กำหนดขอบเขต diff** — ใน worktree ของ task:
   ```bash
   BASE="${base_ref:-origin/main}"
   git diff --name-only "$BASE"...HEAD
   ```
   เก็บรายชื่อเป็น `CHANGED`. ว่าง → จบด้วย "ไม่มี diff ให้รีวิว"
2. **กรอง ignore** — ตัดไฟล์ที่ตรง `.agentignore` / `.socraticodeignore` ออกจาก `CHANGED`
3. **Index โปรเจกต์ (ครั้งแรก / หลัง diff ใหญ่)** — MCP:
   - ตั้ง `SOCRATICODE_PROJECT_ID=<projects.yaml key>` ใน env ของเซสชันถ้าทำได้
   - เรียก `codebase_index` บน `workspace_path` ของโปรเจกต์
   - ถ้า index มีอยู่แล้ว → `codebase_update` หรือ `codebase_status` ตรวจสุขภาพก่อน
4. **ค้นหาบริบทเฉพาะ diff** — สำหรับแต่ละไฟล์/สัญลักษณ์ใน `CHANGED`:
   - `codebase_search` ด้วย query จากชื่อไฟล์ / ฟังก์ชันที่เปลี่ยน
   - `codebase_symbol` / `codebase_symbols` สำหรับสัญลักษณ์ที่แก้
   ห้ามสแกนทั้ง monorepo นอกขอบเขต `CHANGED` + callers ที่ tool คืนมา
5. **สรุปผลเป็นภาษาไทย 3 กลุ่ม** (แต่ละข้อระบุ `ไฟล์:บรรทัด` + หลักฐานจาก SocratiCode):
   - 🛑 **บั๊กร้ายแรง / ช่องโหว่ / contract พัง**
   - ⚠️ **ควรแก้ก่อน merge**
   - 💡 **ข้อเสนอแนะ**
6. **เสนอ patch (ถ้าจำเป็น)** — เขียน unified diff เองจากบริบทที่ดึงได้ (SocratiCode ไม่มี `--fix` CLI):
   ```
   handoff → <default_worker จาก projects.yaml>
   action: apply_reviewer_patches
   patches: <unified diff หรือ path ภายใต้ artifact>
   do_not_apply: true   # reviewer ห้าม apply
   ```
   แจ้ง coordinator: "มี patch จากรีวิว — ส่งให้ dev agent แล้ว รอ human/dev ตัดสินใจ"
7. **จบ task** — `DONE` พร้อมสรุปรีวิว; ไม่มี git write จาก reviewer
8. **HANDOFF block (บังคับ)** — ตาม `skills/_shared/README.md`:
   - มี patch / 🛑 → `to_agent: <default_worker>`, `reason: review`
   - ผ่าน / มีแต่ 💡 → `to_agent:` (ว่าง), `reason: done`

## ห้าม

- `git apply` / commit ใน worktree ของ reviewer (mount `/workspace` เป็น read-only อยู่แล้ว)
- อ่านหรือรีวิวไฟล์นอก `CHANGED` (ยกเว้น `project-standards.md` และ ignore files ที่ root)
- push, เปิด MR, หรือเรียก `human-approval-gate` เพื่อ push ในนาม reviewer
- คัดลอก secret จากโค้ด/config ลงรายงาน

## Stop conditions

| สภาพ | ผล |
|---|---|
| MCP ปิด / infra down | `NEEDS_HUMAN` |
| `codebase_index` / search crash หรือ timeout > 10 นาที | `NEEDS_HUMAN` + log สั้น ๆ |
| พบ 🛑 ≥ 1 | รายงานครบแล้ว `DONE` — ไม่แก้เอง; ให้ dev agent รับ handoff |
| มีแต่ 💡 | `DONE` — ไม่บังคับ handoff patch |
