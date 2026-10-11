import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

const POLL_MS = 20_000;

type Health = Awaited<ReturnType<typeof api.opsHealth>>;
type Queues = Awaited<ReturnType<typeof api.opsQueues>>;
type Dlq = Awaited<ReturnType<typeof api.opsDeadLetter>>;

export function SystemPage() {
  const { session } = useAuth();
  const isAdmin = Boolean(session?.roles?.includes("admin"));
  const [health, setHealth] = useState<Health | null>(null);
  const [queues, setQueues] = useState<Queues | null>(null);
  const [dlq, setDlq] = useState<Dlq | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [at, setAt] = useState("");

  const load = useCallback(async () => {
    if (!session) return;
    try {
      const [h, q, d] = await Promise.all([
        api.opsHealth(session),
        api.opsQueues(session),
        api.opsDeadLetter(session, 50),
      ]);
      setHealth(h);
      setQueues(q);
      setDlq(d);
      setError(null);
      setAt(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    void (async () => {
      if (!cancelled) await load();
    })();
    const id = window.setInterval(() => {
      if (!cancelled) void load();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [session, load]);

  async function onRetry(id: string) {
    if (!session || !isAdmin) return;
    setBusyId(id);
    setError(null);
    try {
      await api.dlqRetry(session, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function onDiscard(id: string) {
    if (!session || !isAdmin) return;
    if (!window.confirm(`Discard dead-letter ${id}? This cannot be undone.`)) return;
    setBusyId(id);
    setError(null);
    try {
      await api.dlqDiscard(session, id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <h1>System</h1>
      <p className="sub">
        Heartbeats · queue depth · dead-letter
        {at ? ` · อัปเดต ${at}` : ""} · poll {POLL_MS / 1000}s
      </p>
      <div className="row" style={{ marginBottom: "0.75rem" }}>
        <button type="button" onClick={() => void load()}>
          Refresh
        </button>
        <span className={`badge ${health?.ok ? "ok" : "warn"}`}>
          health {health?.ok ? "ok" : "degraded"}
        </span>
        <span className={`badge ${health?.redis_ok ? "ok" : "warn"}`}>
          redis {health?.redis_ok ? "ok" : "down"}
        </span>
        <span className={`badge ${health?.store_ok ? "ok" : "warn"}`}>
          store {health?.store_ok ? "ok" : "down"}
        </span>
        {health?.gateway?.version && (
          <span className="badge">gateway {health.gateway.version}</span>
        )}
      </div>
      {error && <p className="err">{error}</p>}

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h2 className="card-title">Heartbeats</h2>
        <p className="sub" style={{ marginTop: 0 }}>
          stale ถ้าไม่มี key หรืออายุ &gt; {health?.heartbeat_stale_after_seconds ?? 180}s
        </p>
        <table>
          <thead>
            <tr>
              <th>Component</th>
              <th>Age</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(health?.heartbeats || []).map((h) => (
              <tr key={h.key}>
                <td>
                  {h.name}
                  {h.extra ? " (extra)" : ""}
                </td>
                <td>
                  {h.missing
                    ? "—"
                    : h.age_seconds != null
                      ? `${h.age_seconds}s`
                      : "—"}
                </td>
                <td>
                  <span className={`badge ${h.stale ? "warn" : "ok"}`}>
                    {h.missing ? "missing" : h.stale ? "stale" : "ok"}
                  </span>
                </td>
              </tr>
            ))}
            {!health?.heartbeats?.length && (
              <tr>
                <td colSpan={3}>No heartbeat data</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <h2 className="card-title">Queues</h2>
        <table>
          <thead>
            <tr>
              <th>Stream</th>
              <th>Length</th>
              <th>Pending</th>
              <th>Group</th>
            </tr>
          </thead>
          <tbody>
            {(queues?.streams || []).map((s) => (
              <tr key={s.stream}>
                <td>
                  <code>{s.stream}</code>
                </td>
                <td>{s.length}</td>
                <td>{s.pending == null ? "—" : s.pending}</td>
                <td>{s.consumer_group || "—"}</td>
              </tr>
            ))}
            {!queues?.streams?.length && (
              <tr>
                <td colSpan={4}>No streams</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="card-title">Dead letter</h2>
        <p className="sub" style={{ marginTop: 0 }}>
          {dlq?.count ?? 0} shown · Retry ส่งกลับ{" "}
          <code>stream:tasks</code>
          {!isAdmin && " · admin เท่านั้นที่ retry/discard ได้"}
        </p>
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Reason</th>
              <th>Project / worker</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(dlq?.entries || []).map((e) => (
              <tr key={e.id}>
                <td>
                  {e.task_id ? (
                    <Link to={`/tasks/${encodeURIComponent(e.task_id)}`}>{e.task_id}</Link>
                  ) : (
                    "—"
                  )}
                  <div className="sub" style={{ fontSize: "0.75rem" }}>
                    {e.id}
                  </div>
                </td>
                <td style={{ maxWidth: "18rem" }}>{e.reason || "—"}</td>
                <td>
                  {e.project || "—"}
                  {e.assigned_to ? ` · ${e.assigned_to}` : ""}
                </td>
                <td>
                  {isAdmin && (
                    <div className="row">
                      <button
                        type="button"
                        className="primary"
                        disabled={busyId === e.id}
                        onClick={() => void onRetry(e.id)}
                      >
                        Retry
                      </button>
                      <button
                        type="button"
                        disabled={busyId === e.id}
                        onClick={() => void onDiscard(e.id)}
                      >
                        Discard
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {!dlq?.entries?.length && (
              <tr>
                <td colSpan={4}>Dead-letter queue empty</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
