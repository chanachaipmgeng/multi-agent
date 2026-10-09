import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type TaskRow } from "../api";
import { useAuth } from "../auth";
import { lokiByTaskId, lokiByTraceId } from "../loki";

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const { session } = useAuth();
  const [task, setTask] = useState<TaskRow | null>(null);
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session || !taskId) return;
    void (async () => {
      setError(null);
      try {
        const [t, a] = await Promise.all([
          api.getTask(session, taskId),
          api.listAudit(session, { taskId }),
        ]);
        setTask(t);
        setEvents(a.events);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [session, taskId]);

  if (error) return <p className="err">{error}</p>;
  if (!task) return <p className="sub">Loading…</p>;

  const project = task.project || task.project_key || "";
  const links = task.links || [];
  const inputs = task.inputs || {};
  const source = task.source || {};

  return (
    <>
      <p>
        <Link to="/tasks">← Tasks</Link>
      </p>
      <h1 className="mono">{task.task_id}</h1>
      <p className="sub">
        {project} · {task.type} · <span className="badge">{task.state}</span> · worker{" "}
        {task.assigned_to || "—"}
        {task.trace_id && (
          <>
            {" "}
            · trace <span className="mono">{task.trace_id}</span>
          </>
        )}
      </p>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>SCM / artifacts</h2>
        <div className="links">
          {typeof source.url === "string" && (
            <a href={String(source.url)} target="_blank" rel="noreferrer">
              Source issue / URL
            </a>
          )}
          {typeof inputs.repo === "string" && (
            <span className="badge">repo {String(inputs.repo)}</span>
          )}
          {typeof inputs.scm === "string" && (
            <span className="badge">{String(inputs.scm)}</span>
          )}
          {links.map((u) => (
            <a key={u} href={u} target="_blank" rel="noreferrer">
              {u.includes("merge_requests") || u.includes("/pull/")
                ? "Open MR/PR"
                : u.includes("issues")
                  ? "Open issue"
                  : "Open link"}
            </a>
          ))}
          <a href={lokiByTaskId(task.task_id)} target="_blank" rel="noreferrer">
            Loki · task_id
          </a>
          {task.trace_id && (
            <a href={lokiByTraceId(task.trace_id)} target="_blank" rel="noreferrer">
              Loki · trace_id
            </a>
          )}
          <Link to={`/audit?task_id=${encodeURIComponent(task.task_id)}`}>Audit search</Link>
        </div>
        {links.length === 0 && !source.url && (
          <p className="sub">ยังไม่มี URL ใน source/inputs/handoffs</p>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Inputs</h2>
        <pre className="mono" style={{ whiteSpace: "pre-wrap", margin: 0 }}>
          {JSON.stringify(inputs, null, 2)}
        </pre>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Handoffs</h2>
        {(task.handoffs || []).length === 0 && <p className="sub">ไม่มี handoff</p>}
        <ul className="timeline">
          {(task.handoffs || []).map((h, i) => (
            <li key={i}>
              <span className="mono">
                {String(h.from_agent)} → {String(h.to_agent)}
              </span>{" "}
              · {String(h.reason || "")} · {String(h.summary || "")}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Audit timeline</h2>
        <ul className="timeline">
          {events.map((ev, i) => (
            <li key={i}>
              <span className="mono">{String(ev.ts)}</span> · {String(ev.actor)} ·{" "}
              <strong>{String(ev.event)}</strong>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
