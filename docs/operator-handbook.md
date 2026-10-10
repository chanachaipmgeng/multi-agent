# คู่มือผู้ปฏิบัติการ EMAW (Operator handbook)

สำหรับโหมด **LAN + local LLM** บน host เช่น Precision 7920 (`/opt/emaw`, Console ที่ `http://<host-ip>:8088`).

หลักการ: **Console = HITL / สั่งงาน + สรุปสถานะ (Home)** · **Grafana = ดูสุขภาพระบบ** · **Hermes = ดูบทสนทนา agent** · **MinIO = ไฟล์ผลลัพธ์** · **Prometheus = metrics ดิบ**  
อย่าสร้าง UI ซ้ำสำหรับงานเดียวกัน (DECISION-20).

---

## เลือกใช้ตัวไหน (สั้นๆ)

| อยากทำอะไร | ไปที่ |
|---|---|
| เปิดเช้าดูสถานะ / รออนุมัติ / งานล่าสุด | **Console → Home** |
| สร้างงาน / อนุมัติ / pause / ดู task | **Operator Console** |
| ดูคิวพังไหม, error rate, dashboard ops | **Grafana** |
| ตาม log ของ task / trace | **Grafana Explore (Loki)** |
| ดูว่า agent พูดอะไรใน session | **Hermes dashboard** |
| ดาวน์โหลด test report / diff / artifact | **MinIO** |
| ดู metric ดิบ / debug PromQL | **Prometheus** |
| เช็ก gateway ยังหายใจอยู่ | **Gateway health** (`/api/healthz`) |

---

## 1) Operator Console — HITL หลัก (ตอนนี้)

| | |
|---|---|
| **ทำอะไร** | สั่งงานและควบคุมแพลตฟอร์มผ่าน gateway `/internal/*` เท่านั้น — ไม่แทน Grafana/Hermes |
| **เมื่อไหร่** | ทุกวัน: สร้าง task, ดูบอร์ด, อนุมัติ, pause/safe-mode, ค้น audit |
| **URL (LAN)** | `http://<host-ip>:8088` เช่น `http://10.50.0.117:8088` |
| **Login** | **API key** = ไฟล์ `secrets/hermes_api_key` · **User ID** = คีย์ใน `config/rbac.yaml` (เช่น `987654321`) |

```bash
cd /opt/emaw
cat secrets/hermes_api_key
grep -A5 '^users:' config/rbac.yaml
```

### หน้าใน Console

| หน้า | ใช้ทำ |
|---|---|
| **Home** (ค่าเริ่มหลัง login) | สรุป gateway/redis/pause · จำนวนรออนุมัติ · tasks by state · งานล่าสุด · ทางลัด Grafana/Hermes |
| **Tasks** (ตาราง / board) | ดูสถานะงาน, เปิดรายละเอียด, ลิงก์ SCM / Loki |
| **Dispatch** | สร้าง task ด้วยมือ (`POST /internal/tasks`) — เริ่ม drill จากที่นี่ |
| **Approvals** | กล่องอนุมัติ HITL (optional `comment`) |
| **Audit** | ค้นเหตุการณ์ตาม `task_id` / `trace_id` |
| **Control** | pause / resume / safe-mode |
| **Projects** | รายการจาก `projects.yaml` (อ่านอย่างเดียว) |
| **Links** | ทางลัด ops ครบ + อ้างคู่มือนี้ |

Task detail มีแถบ **Open in** (Loki / Hermes / artifact URL จาก handoff)

รายละเอียด API: [operator-console.md](operator-console.md)

---

## 2) Grafana — สุขภาพระบบ + กราฟ

| | |
|---|---|
| **ทำอะไร** | ดู metrics/logs/traces ที่จัดเป็นแดชบอร์ด (Operations / Agents / Cost / Security) |
| **เมื่อไหร่** | คิวค้าง, agent ช้า, หลัง deploy, weekly review |
| **URL (LAN)** | `http://<host-ip>:${GRAFANA_PORT}` — บน 7920 มักเป็น **`:3030`** (เพราะ `:3000` ถูกใช้แล้ว) |
| **Login** | ค่าเริ่มต้น compose: user **`emaw`** / password **`emaw-grafana-dev`** (หรือค่าใน `.env`: `GRAFANA_ADMIN_*`) |

**ไม่ใช้ Grafana เพื่อ** สร้าง task หรือกดอนุมัติ — นั้นอยู่ที่ Console

แดชบอร์ดที่มักใช้:

- **Operations** — คิว, สถานะ task, error
- **Agents** — ต่อ agent (งาน, self-heal, tokens)
- **Cost** — ต่อ agent/โปรเจกต์/วัน (cloud; local-free อาจว่าง/stub)
- **Security** — webhook auth fail, approvals, safe-mode

---

## 3) Grafana Explore (Loki) — ตาม log ราย task

| | |
|---|---|
| **ทำอะไร** | ค้น log ด้วย LogQL ตาม `task_id` / `trace_id` / `event_uuid` |
| **เมื่อไหร่** | งานค้าง, adapter error, ไล่หลัง webhook |
| **URL** | `http://<host-ip>:${GRAFANA_PORT}/explore` |
| **Login** | ชุดเดียวกับ Grafana |

คู่มือ query: [runbooks/trace-by-event.md](runbooks/trace-by-event.md)  
จาก Task detail ใน Console มักมีลิงก์ Explore พร้อม filter แล้ว

---

## 4) Hermes dashboard — session ของ agent

| | |
|---|---|
| **ทำอะไร** | ดูบทสนทนา / session ระดับ Hermes agent (coordinator เป็นต้น) |
| **เมื่อไหร่** | สงสัยว่าโมเดลตอบเพี้ยน, ไล่ tool call, ดูบริบทใน session |
| **URL (LAN)** | `http://<host-ip>:9119` |
| **Login** | Basic auth — user **`emaw`** · password จาก `secrets/dashboard_password` |

```bash
cat /opt/emaw/secrets/dashboard_password
# ค่า dev บ่อยครั้ง: emaw-dashboard-dev
```

**หมายเหตุ:** Hermes **API** (`:8642`) ยังอยู่บน loopback เท่านั้น — ไม่เปิด LAN (adapter พูดใน docker network)

---

## 5) MinIO console — คลัง artifact

| | |
|---|---|
| **ทำอะไร** | เก็บ/ดูไฟล์ผลรัน: test report, sandbox log, diff, SocratiCode report, audit export |
| **เมื่อไหร่** | เปิดหลักฐานหลังรัน task, ตรวจว่า adapter อัปโหลดสำเร็จ |
| **URL** | **`http://127.0.0.1:9001` บนเซิร์ฟเวอร์** (ไม่เปิด LAN โดยดีฟอลต์) |
| **Login** | root จาก compose secrets (`minio_root_*` / ค่าใน `.env`) — ดู [secrets.md](secrets.md) |

เข้าจากแล็ปท็อป: SSH tunnel แล้วเปิด `127.0.0.1:9001`

```bash
ssh -L 9001:127.0.0.1:9001 myhr@10.50.0.117
```

Bucket ที่พบบ่อย: `emaw-artifacts` (ต่อโปรเจกต์/task), `emaw-audit` (export)

---

## 6) Prometheus — metrics ดิบ

| | |
|---|---|
| **ทำอะไร** | query PromQL โดยตรง, ดู target up/down |
| **เมื่อไหร่** | debug เมื่อ Grafana ไม่พอ; ตรวจว่า scraper เห็น gateway/adapters |
| **URL** | **`http://127.0.0.1:9090` บนเซิร์ฟเวอร์** (loopback) |
| **Login** | ไม่มี (จึงไม่เปิด LAN) |

วันปกติใช้ **Grafana** พอ — Prometheus เป็นชั้นดิบ

```bash
ssh -L 9090:127.0.0.1:9090 myhr@10.50.0.117
```

---

## 7) Gateway health — สัญญาณชีพ

| | |
|---|---|
| **ทำอะไร** | `GET /healthz` ของ webhook-gateway (ผ่าน proxy ของ Console เป็น `/api/healthz`) |
| **เมื่อไหร่** | smoke เร็วๆ ว่า gateway ขึ้น |
| **URL** | ใน Console Links → `/api/healthz` หรือ `http://127.0.0.1:8700/healthz` บนโฮสต์ |

คาดหวัง JSON ประมาณ `{"status":"ok",...}`

---

## แผนที่พอร์ต (7920 LAN hybrid)

| พื้นผิว | พอร์ต | Bind เมื่อ `CONSOLE_BIND=0.0.0.0` |
|---|---|---|
| Operator Console | **8088** | LAN |
| Grafana | **3030** (หรือ `GRAFANA_PORT`) | LAN |
| Hermes dashboard | **9119** | LAN |
| MinIO console | 9001 | loopback เท่านั้น |
| Prometheus | 9090 | loopback เท่านั้น |
| Gateway | 8700 | loopback (Console proxy `/api`) |
| Hermes API | 8642 | loopback |

Firewall แนะนำ: อนุญาต LAN เฉพาะพอร์ตที่ต้องใช้จริง (อย่างน้อย `8088`; เพิ่ม `3030`/`9119` ถ้าต้องการเข้าจากแล็ปโดยตรง)

SSH tunnel รวม (MinIO + Prometheus + สำรอง):

```bash
ssh -L 3030:127.0.0.1:3030 \
    -L 9119:127.0.0.1:9119 \
    -L 9001:127.0.0.1:9001 \
    -L 9090:127.0.0.1:9090 \
    myhr@10.50.0.117
```

(เมื่อ Grafana/Hermes เปิด LAN อยู่แล้ว ไม่จำเป็นต้อง `-L` คู่ 3030/9119)

---

## ทริปทำงานรายวัน (แนะนำ)

1. เปิด **Console** → login → ตกที่ **Home**  
2. ดู strip สุขภาพ + จำนวน pending approvals  
3. **Dispatch** สร้าง task บนโปรเจกต์ที่ onboard แล้ว (เช่น `sandbox-smoke`)  
4. ตามสถานะใน Home (recent) หรือ **Tasks** / board  
5. มี HITL → **Approvals** (หรือคลิกจาก Home)  
6. งานผิดปกติ → Task detail → **Open in Loki** / Grafana · หรือ **Hermes**  
7. อยากได้ไฟล์ผลรัน → ลิงก์ artifact / **MinIO** (tunnel ถ้าอยู่คนละเครื่อง)

พิสูจน์ stack: `cd /opt/emaw && set -a && source .env && set +a && make local-free-check`  
แผนงานถัดไปของโฮสต์: [roadmap-next.md](roadmap-next.md)

---

## อ่านต่อ

| เอกสาร | เนื้อหา |
|---|---|
| [operator-console.md](operator-console.md) | DECISION-20, หน้าจอ, Telegram checklist |
| [environments.md](environments.md) | โหมด LAN / air-gap / prod |
| [offline-airgap.md](offline-airgap.md) | pack/load, acceptance |
| [secrets.md](secrets.md) | รายการ secret |
| [runbooks/](runbooks/README.md) | เหตุการณ์ (agent stuck, restore, …) |
| [runbooks/trace-by-event.md](runbooks/trace-by-event.md) | ตาม log ด้วย task/trace id |
