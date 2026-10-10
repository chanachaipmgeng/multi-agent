import { Link } from "react-router-dom";
import {
  grafanaBaseUrl,
  hermesDashboardUrl,
  isRemoteConsole,
  loopbackUrl,
  sshTunnelHint,
} from "../opsLinks";

function host(): string {
  return typeof window !== "undefined" ? window.location.hostname || "127.0.0.1" : "127.0.0.1";
}

type LinkItem = {
  name: string;
  url: string;
  note: string;
  /** When true, service stays on host loopback even if Console is on LAN. */
  loopbackOnly?: boolean;
};

function buildLinks(): LinkItem[] {
  const grafana = grafanaBaseUrl();
  return [
    {
      name: "Hermes dashboard",
      url: hermesDashboardUrl(),
      note: "agent sessions · basic auth",
    },
    {
      name: "Grafana",
      url: grafana,
      note: "Operations / Agents / Cost / Security",
    },
    {
      name: "Grafana Explore (Loki)",
      url: `${grafana}/explore`,
      note: "search logs by task_id / trace_id / event_uuid — docs/runbooks/trace-by-event.md",
    },
    {
      name: "MinIO console",
      url: import.meta.env.VITE_MINIO_URL || loopbackUrl("9001"),
      note: "artifacts · host loopback only",
      loopbackOnly: true,
    },
    {
      name: "Prometheus",
      url: import.meta.env.VITE_PROM_URL || loopbackUrl("9090"),
      note: "raw metrics · host loopback only",
      loopbackOnly: true,
    },
    {
      name: "Gateway health",
      url: "/api/healthz",
      note: "proxied",
    },
  ];
}

export function LinksPage() {
  const remote = isRemoteConsole();
  const links = buildLinks();
  const h = host();

  return (
    <>
      <h1>Links</h1>
      <p className="sub">
        พื้นผิว ops ที่มีอยู่แล้ว — ไม่สร้างซ้ำใน console · คู่มือ:{" "}
        <span className="mono">docs/operator-handbook.md</span> · สรุปรายวันเริ่มที่{" "}
        <Link to="/">Home</Link>
      </p>
      {remote && (
        <p className="sub card" style={{ marginBottom: "1rem" }}>
          Console เปิดผ่าน <span className="mono">{h}</span> — Grafana / Hermes ใช้ IP
          เดียวกัน (เมื่อ <span className="mono">CONSOLE_BIND=0.0.0.0</span>). MinIO /
          Prometheus ยังอยู่ที่ <span className="mono">127.0.0.1</span> บนเซิร์ฟเวอร์ —
          ใช้ SSH tunnel แล้วเปิดลิงก์ loopback:
          <br />
          <span className="mono">{sshTunnelHint(h)}</span>
        </p>
      )}
      <div className="card">
        <ul className="timeline">
          {links.map((l) => (
            <li key={l.name}>
              <a href={l.url} target="_blank" rel="noreferrer">
                {l.name}
              </a>
              <span className="sub"> — {l.note}</span>
              <div className="mono sub">{l.url}</div>
              {remote && l.loopbackOnly && (
                <div className="sub">เปิดได้หลัง SSH -L หรือบนเครื่องเซิร์ฟเวอร์โดยตรง</div>
              )}
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
