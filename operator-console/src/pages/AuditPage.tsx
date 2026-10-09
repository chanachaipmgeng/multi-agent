import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { lokiByTaskId, lokiByTraceId } from "../loki";

export function AuditPage() {
  const { session } = useAuth();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<"task_id" | "trace_id">(
    params.get("trace_id") ? "trace_id" : "task_id",
  );
  const [query, setQuery] = useState(
    () => params.get("task_id") || params.get("trace_id") || "",
  );
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function search(override?: { mode: "task_id" | "trace_id"; q: string }) {
    if (!session) return;
    const m = override?.mode ?? mode;
    const q = (override?.q ?? query).trim();
    if (!q) {
      setError("ใส่ task_id หรือ trace_id");
      return;
    }
    setError(null);
    setSearched(true);
    try {
      const data =
        m === "task_id"
          ? await api.listAudit(session, { taskId: q })
          : await api.listAudit(session, { traceId: q });
      setEvents(data.events);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setEvents([]);
    }
  }

  useEffect(() => {
    const tid = params.get("task_id");
    const tr = params.get("trace_id");
    if (!session || (!tid && !tr)) return;
    if (tid) {
      setMode("task_id");
      setQuery(tid);
      void search({ mode: "task_id", q: tid });
    } else if (tr) {
      setMode("trace_id");
      setQuery(tr);
      void search({ mode: "trace_id", q: tr });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hydrate once from URL
  }, [session, params]);

  return (
    <>
      <h1>Audit</h1>
      <p className="sub">
        ค้น audit_events ด้วย task_id หรือ trace_id — ไม่ต้อง psql · logs ดูผ่าน Grafana/Loki
      </p>
      <div className="row">
        <select
          value={mode}
          onChange={(e) => setMode(e.target.value as "task_id" | "trace_id")}
        >
          <option value="task_id">task_id</option>
          <option value="trace_id">trace_id</option>
        </select>
        <input
          className="mono"
          style={{ flex: 1, minWidth: "12rem" }}
          placeholder={mode === "task_id" ? "tsk_…" : "trace…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void search();
          }}
        />
        <button type="button" className="primary" onClick={() => void search()}>
          Search
        </button>
        {query.trim() && (
          <a
            href={
              mode === "task_id"
                ? lokiByTaskId(query.trim())
                : lokiByTraceId(query.trim())
            }
            target="_blank"
            rel="noreferrer"
          >
            Loki Explore
          </a>
        )}
      </div>
      {error && <p className="err">{error}</p>}
      {searched && !error && (
        <p className="sub">
          {events.length} event{events.length === 1 ? "" : "s"}
        </p>
      )}
      <ul className="timeline">
        {events.map((ev, i) => (
          <li key={i}>
            <span className="mono">{String(ev.ts)}</span> ·{" "}
            {ev.task_id ? (
              <Link className="mono" to={`/tasks/${String(ev.task_id)}`}>
                {String(ev.task_id)}
              </Link>
            ) : (
              "—"
            )}{" "}
            · {String(ev.actor)} · <strong>{String(ev.event)}</strong>
            {ev.attrs != null && (
              <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: "0.25rem 0 0" }}>
                {JSON.stringify(ev.attrs, null, 2)}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
