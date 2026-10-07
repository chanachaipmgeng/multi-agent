---
name: switch-context
description: Map [Frontend]/[Backend]/[Ops]/[QA] tags to projects.yaml cwd, load project-standards.md, confirm context.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, routing, single-agent]
    category: emaw
    owner: coordinator
    phase: 2
    hitl: confirm project name + one rule before continuing work
    inputs: [user_message, tag]
    note: >
      For multi-profile compose (one container per role), prefer coordinator routing
      + Redis streams. Keep this skill for a single-agent Phase 1–2 host install.
---

# Skill: switch-context

สลับบริบทโปรเจกต์บน **single-agent host install** ตามแท็กในข้อความผู้ใช้ — อ่าน `config/projects.yaml` เป็นแหล่งความจริง

## แท็กที่รองรับ

| แท็กในข้อความ | routing hint | เลือกโปรเจกต์จาก |
|---|---|---|
| `[Frontend]` / `[FE]` | `area:frontend` | `routing.label_to_worker.frontend` → โปรเจกต์ที่ `default_worker` หรือ `allowed_workers` รวม worker นั้น |
| `[Backend]` / `[BE]` | `area:backend` | เช่นเดียวกันกับ backend |
| `[Ops]` / `[CI]` | `area:ci` | โปรเจกต์ที่ devops อยู่ใน `allowed_workers` หรือ key ที่เกี่ยวกับ CI |
| `[QA]` | `area:qa` | โปรเจกต์ที่ qa อยู่ใน `allowed_workers` |
| ไม่มีแท็ก | — | ถามผู้ใช้ หรือใช้โปรเจกต์ปัจจุบันถ้ามี session context |

ถ้ามีหลายโปรเจกต์เข้าเงื่อนไข → ถามให้เลือก `key` จากรายชื่อสั้น ๆ แล้วรอคำตอบ

## ขั้นตอน

1. **parse แท็ก** — ดึงแท็กแรกจากข้อความผู้ใช้; ไม่มี → ถาม
   `"โปรเจกต์ไหน? ใส่ [Frontend] / [Backend] / [Ops] / [QA] หรือระบุ key จาก projects.yaml"`
2. **โหลด registry** — อ่าน `/config/projects.yaml` (compose) หรือ `config/projects.yaml` บน host
3. **resolve `key`**
   - map แท็ก → worker ผ่าน `routing.label_to_worker`
   - เลือกโปรเจกต์ที่ `default_worker == worker` หรือ worker ∈ `allowed_workers`
   - ถ้าไม่พบ → `NEEDS_HUMAN` พร้อมรายการ `projects[].key` ทั้งหมด
4. **เปลี่ยน cwd** — `cd <workspace_path>` ของโปรเจกต์นั้น
   ตรวจว่ามี directory จริง; ไม่มี → แนะนำ `make onboard KEY=…` แล้วจบ
5. **โหลด rulebook** — อ่าน `project-standards.md` ที่ root ของโปรเจกต์
   (ถ้าไม่มี ให้ใช้ template จาก `workspace/_templates/project-standards.md` และเตือนว่ายังไม่ onboard)
6. **ยืนยันกับผู้ใช้ก่อนทำงานต่อ** — ส่งข้อความรูปแบบคงที่ แล้ว**รอ** `y` / `n`:
   ```
   Context → <key> (<path_with_namespace>)
   cwd: <workspace_path>
   worker ปกติ: <default_worker>
   test: <test_command>
   กฎที่เพิ่งอ่าน: <หนึ่งบรรทัดจาก project-standards.md>
   ใช้บริบทนี้ต่อไหม? (y/n)
   ```
7. **หลัง `y`** — จำ session context (`project_key`, `workspace_path`, `default_worker`) สำหรับข้อความถัดไปจนกว่าจะมีแท็กใหม่หรือคำสั่ง `switch-context` อีกครั้ง
8. **หลัง `n` / timeout 5 นาที** — ไม่เปลี่ยน context เดิม; ถามแท็กใหม่

## ห้าม

- เดา `workspace_path` นอก `projects.yaml`
- เริ่ม `dev-flow` / แก้โค้ด ก่อนได้ `y` ในข้อ 6
- สลับไปโปรเจกต์ที่ `data_classification: confidential` โดยไม่เตือนว่าต้องใช้ `llm_backend` ตาม registry

## Phase 3 note

เมื่อรันแบบหนึ่ง container ต่อ role แล้ว การเลือก worker ทำที่ coordinator + `stream:<role>` — **อย่าพึ่ง skill นี้เป็นตัว routing หลัก**; คงไว้สำหรับโฮสต์ single-agent เท่านั้น
