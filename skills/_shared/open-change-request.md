---
name: open-change-request
description: After HITL approval, push the work branch and open a GitLab MR or GitHub PR based on inputs.scm.
version: 1.0.0
metadata:
  hermes:
    tags: [emaw, scm, mr, pr]
    category: emaw
    owner: [dev-frontend, dev-backend, devops]
    phase: 1
    hitl: requires prior human-approval-gate approval for push_work_branch_and_open_mr
    inputs: [scm, repo, branch, mr_title, mr_description]
---

# Skill: open-change-request

ใช้หลังได้รับ `approved` จาก `human-approval-gate` สำหรับ action `push_work_branch_and_open_mr`
(ชื่อ action คงเดิมทั้ง GitLab และ GitHub — ไม่แตก action ใหม่)

อ่าน `inputs.scm` (ค่าเริ่มต้น `gitlab` ถ้าไม่มี) และ `inputs.repo` / `source.path_with_namespace`

## scm=gitlab (default)

Push พร้อม GitLab push options (scope `write_repository` พอ ไม่ต้องมี `api`):

```bash
git push -u origin <branch> \
  -o merge_request.create \
  -o merge_request.target=main \
  -o merge_request.remove_source_branch \
  -o merge_request.title="<mr_title>" \
  -o merge_request.description="<mr_description>"
```

อ่าน URL ของ MR จาก output ของ push

## scm=github

1. Push ปกติ (ไม่มี push options แบบ GitLab):

```bash
git push -u origin <branch>
```

2. เปิด PR — ถ้ามี `gh` ใน PATH (และ `GH_TOKEN` / `GITHUB_TOKEN` ใน env):

```bash
gh pr create --base main --title "<mr_title>" --body "<mr_description>"
```

3. ถ้าไม่มี `gh` ใช้ GitHub REST API:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "${GITHUB_API_URL:-https://api.github.com}/repos/<owner>/<name>/pulls" \
  -d "{\"title\":\"<mr_title>\",\"head\":\"<branch>\",\"base\":\"main\",\"body\":\"<mr_description>\"}"
```

`<owner>/<name>` = `inputs.repo` หรือ `source.repo`

หมายเหตุ: image Hermes ไม่บังคับติดตั้ง `gh` — host/agent ต้องมี `gh` ใน PATH หรือใช้ API;
optional mount `tools/gh` แบบเดียวกับ gitleaks ถ้าต้องการ

## ห้าม

- เรียก skill นี้ก่อนได้ `approved` จาก gate
- push ไป `main` / `release/*`
- merge / approve MR/PR เอง
