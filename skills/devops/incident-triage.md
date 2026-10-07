---
name: incident-triage
owner: devops
phase: 1
hitl: push hotfix branch + MR via human-approval-gate; deploy never without `approver`
inputs: [task_id, trace_id, project, pipeline_id, job_id, job_name, stage, ref, sha, failure_reason, failed_jobs, job_trace|job_traces, branch, workspace_path]
triggers: GitLab Pipeline Hook (status=failed) / Job Hook (build_status=failed, allow_failure=false)
sla: ข้อความวิเคราะห์สาเหตุถึงมนุษย์ภายใน 2 นาที
---

# Skill: incident-triage

วิเคราะห์ pipeline/job ที่พัง อธิบายสาเหตุเป็นภาษาคน เสนอวิธีแก้ และ (ถ้าแก้ได้ใน CI/Docker config) เตรียม hotfix branch — **ไม่ deploy เอง**

## ขั้นตอน

1. **อ่าน trace** — ใช้ `job_trace` / `job_traces` ที่ queue-adapter แนบมา (redacted, tail ≤ 64 KB);
   ถ้าไม่พอ ดึงเพิ่มผ่าน GitLab API `GET /projects/:id/jobs/:job_id/trace` (token `read_api`) — ห้ามพิมพ์ค่า secret/CI variable ใด ๆ ที่เห็นใน log
2. **จำแนกสาเหตุ** (เลือกหนึ่ง): `dependency` (เวอร์ชัน/registry) · `test_failure` (โค้ดพัง) · `infra` (runner, OOM, timeout, network) ·
   `config` (`.gitlab-ci.yml`, Dockerfile) · `flaky` (ผ่านเมื่อ retry) · `secret_missing` (CI variable ไม่มี) · `unknown`
3. **แจ้งผลวิเคราะห์ภายใน 2 นาที** ผ่าน coordinator/Telegram (ข้อความแรก ไม่ต้องรอแก้เสร็จ):
   ```
   ⚠️ Pipeline #<pipeline_id> fail · <project> · job <job_name> (<stage>) · ref <ref>
   สาเหตุ: <category> — <1–2 บรรทัดอธิบาย>
   บรรทัดสำคัญ: <error line>
   เสนอ: <retry | แก้ Dockerfile/CI บน hotfix branch | ส่งต่อ dev agent | ต้องการมนุษย์>
   trace <trace_id>
   ```
4. **ตัดสินใจเส้นทาง**
   - `test_failure` → ไม่ใช่งาน devops: เสนอ handoff ไปยัง dev agent เจ้าของ repo (`projects.yaml#default_worker`) พร้อม trace สรุป → จบ
   - `flaky` → เสนอ retry job ผ่าน API (`POST /jobs/:id/retry`) **หลังได้รับ approval** (นับเป็น infra action) → จบ
   - `secret_missing` / `infra` ที่ต้องแก้ runner → `NEEDS_HUMAN` พร้อมคำแนะนำ → จบ
   - `dependency` / `config` → ไปข้อ 5
5. **เตรียม hotfix** — `git worktree add /workspace/.worktrees/<task_id> -b hotfix/ci-<pipeline_id> origin/<ref>`;
   แก้เฉพาะไฟล์ CI/Docker (`.gitlab-ci.yml`, `Dockerfile*`, `docker-compose*.yml`, `deploy/`, `infra/`) — ห้ามแตะ business logic
6. **ทดสอบใน sandbox** — `docker build` / `gitlab-ci-lint` / คำสั่งของ job ที่พัง; **self-heal ≤ 2 รอบ**; ยังพัง → `NEEDS_HUMAN`
7. **Secret scan + commit** — `gitleaks protect --staged`; commit `ci: pin foo to 1.2.3 to fix docker-build (#pipeline <id>)`
8. **ขออนุมัติ** — `human-approval-gate` `{action: push_work_branch_and_open_mr, branch: hotfix/ci-<id>, diff_stat, build_result}`
   timeout 30 นาที → `EXPIRED` ไม่มีการ push
9. **เมื่อ approved** — push พร้อม push options `-o merge_request.create -o merge_request.target=<ref ที่พัง หรือ main ตาม rulebook>`
   และติดตาม pipeline ใหม่; รายงาน
   `✅ MR !<iid> พร้อมรีวิว · pipeline ใหม่ #<id> กำลังรัน` → task `DONE`

## ห้าม
- รัน deploy, `docker system prune`, แก้ runner/infra จริง — ต้อง `approver` อนุมัติผ่าน skill `deploy-prod` / infra_change เท่านั้น
- push ไป `main`/`release/*`; retry job หรือ cancel pipeline โดยไม่มี approval
- คัดลอกค่า secret/CI variable จาก log ลงข้อความ, commit, หรือ MR
- แก้ business logic ของแอป (ส่งต่อ dev agent)
