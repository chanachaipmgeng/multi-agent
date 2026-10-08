const LINKS = [
  {
    name: "Hermes dashboard",
    url: import.meta.env.VITE_HERMES_URL || "http://127.0.0.1:9119",
    note: "agent sessions · basic auth",
  },
  {
    name: "Grafana",
    url: import.meta.env.VITE_GRAFANA_URL || "http://127.0.0.1:3000",
    note: "Operations / Agents / Cost / Security",
  },
  {
    name: "MinIO console",
    url: import.meta.env.VITE_MINIO_URL || "http://127.0.0.1:9001",
    note: "artifacts",
  },
  {
    name: "Prometheus",
    url: import.meta.env.VITE_PROM_URL || "http://127.0.0.1:9090",
    note: "raw metrics",
  },
  {
    name: "Gateway health",
    url: "/api/healthz",
    note: "proxied",
  },
];

export function LinksPage() {
  return (
    <>
      <h1>Links</h1>
      <p className="sub">พื้นผิว ops ที่มีอยู่แล้ว — ไม่สร้างซ้ำใน console</p>
      <div className="card">
        <ul className="timeline">
          {LINKS.map((l) => (
            <li key={l.name}>
              <a href={l.url} target="_blank" rel="noreferrer">
                {l.name}
              </a>
              <span className="sub"> — {l.note}</span>
              <div className="mono sub">{l.url}</div>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
