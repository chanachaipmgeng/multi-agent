---
name: deep-review
description: Blast-radius and dependency review via SocratiCode MCP on git-diff symbols only; report only — never modify code.
version: 1.1.0
metadata:
  hermes:
    tags: [emaw, review, socraticode, blast-radius]
    category: emaw
    owner: reviewer
    phase: 2
    hitl: none — read-only analysis
    inputs: [task_id, project, branch, workspace_path, base_ref, focus_symbols]
    requires: make up-socraticode (Ollama embeddings + Qdrant)
    companion_skill: review-with-socraticode
---

# Skill: deep-review

วิเคราะห์ **blast radius** และ **dependency graph** ของการเปลี่ยนแปลงใน diff ด้วย SocratiCode MCP — รายงานอย่างเดียว ไม่แก้โค้ด

ใช้เมื่อ coordinator/dev ขอ "รีวิวลึก" หรือหลัง `review-with-socraticode` พบ 🛑 ที่เกี่ยวกับสัญญาข้ามโมดูล

## Preconditions

เหมือน `review-with-socraticode`: MCP เปิด, infra `socraticode-ollama` + `socraticode-qdrant` สุขภาพดี, มี `.socraticodeignore`

## ขั้นตอน

1. **ขอบเขต** — สร้าง `CHANGED` จาก `git diff --name-only ${base_ref:-origin/main}...HEAD` แล้วกรอง ignore
2. **ระบุสัญลักษณ์** — จาก diff hunks (ฟังก์ชัน/คลาส/export ที่เพิ่มหรือแก้) หรือใช้ `focus_symbols` ถ้า task ส่งมา
   จำกัด ≤ 20 สัญลักษณ์ต่อรอบ; เกิน → จัดอันดับตามจำนวนบรรทัดที่เปลี่ยนแล้วตัดท้าย
3. **Ensure graph** — `codebase_graph_status`; ถ้ายังไม่มี → `codebase_graph_build` บน `workspace_path`
4. **MCP `codebase_impact`** — ทีละสัญลักษณ์ (หรือ batch ตามที่ tool รองรับ):
   - ผู้เรียกภายในโปรเจกต์
   - ผู้ถูกเรียก / ของที่พึ่งพา
   - ขอบเขตแพ็กเกจที่อาจพัง (test, API, UI)
5. **MCP graph query** — สำหรับไฟล์ใน `CHANGED` ที่เป็น entrypoint (router, service, public API):
   - `codebase_graph_query` (inbound / outbound)
   - `codebase_graph_circular` ตรวจวงจร
   - เทียบ layer กับ `project-standards.md`
6. **สรุปรายงานภาษาไทย**
   ```
   ## Deep review · <project> · <branch>
   ### Blast radius (codebase_impact)
   - <symbol> → กระทบ <N> callers · ความเสี่ยง: สูง|กลาง|ต่ำ · เหตุผลสั้น ๆ
   ### Dependencies (graph)
   - <file>: inbound … / outbound … · circular? · ปัญหา: …
   ### แนะนำก่อน merge
   - 🛑 / ⚠️ / 💡 (อ้างไฟล์:บรรทัด หรือ symbol)
   ### นอกขอบเขต
   - รายการที่ไม่ได้วิเคราะห์ (ตัดเพราะ limit / ignore)
   ```
7. **Handoff (ถ้ามีความเสี่ยงสูง)** — ส่งสรุปไป `default_worker` ของโปรเจกต์พร้อม
   `แนะนำเพิ่ม test หรือแยก MR` — **ไม่สร้าง patch เอง** (patch อยู่ใน `review-with-socraticode`)
8. **จบ** — `DONE` พร้อมรายงาน; ไม่มี git write

## ห้าม

- แก้ไฟล์, apply patch, push
- เรียก MCP กับ path นอก `CHANGED` หรือทั้ง repo โดยไม่มีเหตุจาก diff
- เปิดเผย secret / credential ที่พบบน graph

## Stop conditions

| สภาพ | ผล |
|---|---|
| MCP/infra ไม่พร้อม | `NEEDS_HUMAN` |
| `CHANGED` ว่าง | `DONE` — "ไม่มี diff" |
| tool error ต่อเนื่อง 2 ครั้ง | `NEEDS_HUMAN` |
| เสร็จครบใน limit | `DONE` |
