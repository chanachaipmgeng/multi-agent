import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type OpsSummary } from "../api";
import { useAuth } from "../auth";
import {
  grafanaBaseUrl,
  hermesDashboardUrl,
  isRemoteConsole,
  loopbackUrl,
  sshTunnelHint,
} from "../opsLinks";

const POLL_MS = 20_000;

export function HomePage() {
  const { session } = useAuth();
  const [data, setData] = useState<OpsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [at, setAt] = useState<string>("");

  useEffect(() => {
    if (!session) return;
    let cancelled = false;

    async function load() {
      try {
        const s = await api.opsSummary(session!);
        if (cancelled) return;
        setData(s);
        setError(null);
        setAt(new Date().toLocaleTimeString());
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }

    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [session]);

  const host =
    typeof window !== "undefined" ? window.location.hostname || "127.0.0.1" : "127.0.0.1";
  const remote = isRemoteConsole();
  const grafana = grafanaBaseUrl();
  const hermes = hermesDashboardUrl();

  return (
    <>
      <h1>Home</h1>
      <p className="sub">
        สถานะแพลตฟอร์ม + สิ่งที่ต้องทำตอนนี้
        {at ? ` · อัปเดต ${at}` : ""} · poll {POLL_MS / 1000}s
      </p>
      {error && <p className="err">{error}</p>}

      <div className="status-strip">
        <span className={`badge ${data?.gateway.status === "ok" ? "ok" : "warn"}`}>
          gateway {data?.gateway.status ?? "…"}
        </span>
        <span className={`badge ${data?.redis_ok ? "ok" : "warn"}`}>
          redis {data?.redis_ok ? "ok" : "down"}
        </span>
        <span className={`badge ${data?.store_enabled ? "ok" : "warn"}`}>
          store {data?.store_enabled ? "on" : "off"}
        </span>
        <span className={`badge ${data?.control.safe_mode ? "warn" : "ok"}`}>
          safe-mode {data?.control.safe_mode ? "ON" : "off"}
        </span>
        <span className={`badge ${data?.control.pause_all ? "warn" : "ok"}`}>
          pause-all {data?.control.pause_all ? "ON" : "off"}
        </span>
        {(data?.control.paused_agents?.length ?? 0) > 0 && (
          <span className="badge warn">
            paused: {data!.control.paused_agents.join(", ")}
          </span>
        )}
      </div>

      <div className="home-grid">
        <div className="card">
          <h2 className="card-title">ต้องทำตอนนี้</h2>
          <p>
            <Link to="/approvals" className="stat-link">
              <span className="stat-num">{data?.approvals_pending ?? "—"}</span>
              <span className="sub"> pending approvals</span>
            </Link>
          </p>
          <div className="row" style={{ marginTop: "0.75rem" }}>
            <Link to="/dispatch">
              <button type="button" className="primary">
                Dispatch task
              </button>
            </Link>
            <Link to="/control">
              <button type="button">Control</button>
            </Link>
            <Link to="/tasks">
              <button type="button">All tasks</button>
            </Link>
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">Tasks by state</h2>
          <div className="state-chips">
            {Object.keys(data?.tasks_by_state || {}).length === 0 && (
              <span className="sub">ยังไม่มี task</span>
            )}
            {Object.entries(data?.tasks_by_state || {})
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([st, n]) => (
                <Link
                  key={st}
                  to={`/tasks?state=${encodeURIComponent(st)}`}
                  className="badge"
                >
                  {st} · {n}
                </Link>
              ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">Recent tasks</h2>
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Project</th>
              <th>State</th>
              <th>Worker</th>
            </tr>
          </thead>
          <tbody>
            {(data?.tasks_recent || []).map((t) => (
              <tr key={t.task_id}>
                <td>
                  <Link className="mono" to={`/tasks/${encodeURIComponent(t.task_id)}`}>
                    {t.task_id}
                  </Link>
                </td>
                <td>{t.project || "—"}</td>
                <td>
                  <span className="badge">{t.state || "—"}</span>
                </td>
                <td className="mono">{t.assigned_to || "—"}</td>
              </tr>
            ))}
            {(data?.tasks_recent || []).length === 0 && (
              <tr>
                <td colSpan={4} className="sub">
                  ไม่มีงานล่าสุด — เริ่มที่ Dispatch
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="card-title">Ops shortcuts</h2>
        <div className="links">
          <a href={grafana} target="_blank" rel="noreferrer">
            Grafana
          </a>
          <a href={`${grafana}/explore`} target="_blank" rel="noreferrer">
            Explore (Loki)
          </a>
          <a href={hermes} target="_blank" rel="noreferrer">
            Hermes dashboard
          </a>
          <a href={loopbackUrl("9001")} target="_blank" rel="noreferrer">
            MinIO (loopback)
          </a>
          <Link to="/links">All links + handbook</Link>
        </div>
        {remote && (
          <p className="sub" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
            MinIO/Prometheus อยู่บนเซิร์ฟเวอร์ loopback — tunnel:{" "}
            <span className="mono">{sshTunnelHint(host)}</span>
          </p>
        )}
      </div>
    </>
  );
}
