---
name: fix-pipeline
description: Diagnose a failed CI job, propose a CI/Docker hotfix branch, HITL before push.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, devops, ci]
    category: emaw
    owner: devops
    phase: 3
    hitl: push via human-approval-gate
    inputs: [task_id, project, pipeline_id, job_id]
---

# Skill: fix-pipeline

โฟกัสงาน `pipeline_failed` / `job_failed` — วิเคราะห์ job trace แล้วเสนอ hotfix บนไฟล์ CI/Docker เท่านั้น
(ขยายจาก `incident-triage`; ใช้ skill นี้เมื่อ task.skill = fix-pipeline)

## ขั้นตอน

1. อ่าน job trace จาก enrichment ใน prompt (หรือ GitLab API `read_api`)
2. จัดหมวด: `dependency` / `config` / `flaky` / `test_failure` / `secret_missing` / `infra`
3. `test_failure` → HANDOFF ไป `default_worker` แล้วจบ
4. `dependency` / `config` → worktree `hotfix/ci-<pipeline_id>` · แก้เฉพาะ CI/Docker · self-heal ≤ 2
5. Secret scan + commit `ci: …`
6. ขอ `human-approval-gate` ก่อน push + เปิด MR
7. ปิดท้ายด้วย **HANDOFF block** (`skills/_shared/README.md`)

## ห้าม

แก้ business logic · push โดยไม่มี approval · คัดลอก secret จาก log
