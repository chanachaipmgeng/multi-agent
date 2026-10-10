import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type TaskRow } from "../api";
import { useAuth } from "../auth";

type View = "table" | "board";

const BOARD_COLUMNS: { key: string; states: string[] }[] = [
  { key: "QUEUED", states: ["QUEUED"] },
  { key: "IN_PROGRESS", states: ["IN_PROGRESS"] },
  { key: "AWAITING_APPROVAL", states: ["AWAITING_APPROVAL"] },
  { key: "REVIEW", states: ["REVIEW"] },
  { key: "DONE", states: ["DONE", "APPROVED"] },
  { key: "FAILED", states: ["FAILED", "CANCELLED", "EXPIRED", "NEEDS_HUMAN"] },
];

export function TasksPage() {
  const { session } = useAuth();
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [project, setProject] = useState("");
  const [state, setState] = useState("");
  const [view, setView] = useState<View>("table");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!session) return;
    setError(null);
    try {
      const data = await api.listTasks(session, {
        project: project || undefined,
        // Board loads all states; table respects filter
        state: view === "board" ? undefined : state || undefined,
      });
      setTasks(data.tasks);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, [session, view]);

  const columns = useMemo(() => {
    const map = new Map<string, TaskRow[]>();
    for (const col of BOARD_COLUMNS) map.set(col.key, []);
    for (const t of tasks) {
      const col = BOARD_COLUMNS.find((c) => c.states.includes(t.state));
      const key = col?.key || "FAILED";
      map.get(key)?.push(t);
    }
    return BOARD_COLUMNS.map((c) => ({ ...c, tasks: map.get(c.key) || [] }));
  }, [tasks]);

  return (
    <>
      <h1>Tasks</h1>
      <p className="sub">กรองจาก gateway task store · Table หรือ Kanban board</p>
      <div className="row">
        <button
          type="button"
          className={view === "table" ? "primary" : undefined}
          onClick={() => setView("table")}
        >
          Table
        </button>
        <button
          type="button"
          className={view === "board" ? "primary" : undefined}
          onClick={() => setView("board")}
        >
          Board
        </button>
        <input
          placeholder="project key"
          value={project}
          onChange={(e) => setProject(e.target.value)}
        />
        {view === "table" && (
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">any state</option>
            {[
              "QUEUED",
              "IN_PROGRESS",
              "AWAITING_APPROVAL",
              "REVIEW",
              "DONE",
              "FAILED",
              "NEEDS_HUMAN",
            ].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
        <button type="button" className="primary" onClick={() => void load()}>
          Refresh
        </button>
      </div>
      {error && <p className="err">{error}</p>}

      {view === "table" ? (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Project</th>
                <th>Type</th>
                <th>State</th>
                <th>Worker</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.task_id}>
                  <td className="mono">
                    <Link to={`/tasks/${t.task_id}`}>{t.task_id}</Link>
                  </td>
                  <td>{t.project || t.project_key}</td>
                  <td>{t.type}</td>
                  <td>
                    <span className="badge">{t.state}</span>
                  </td>
                  <td>{t.assigned_to || "—"}</td>
                </tr>
              ))}
              {tasks.length === 0 && (
                <tr>
                  <td colSpan={5} className="sub">
                    ไม่มีงานตามตัวกรอง
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="board">
          {columns.map((col) => (
            <section className="board-col" key={col.key}>
              <header>
                <span>{col.key}</span>
                <span className="badge">{col.tasks.length}</span>
              </header>
              <div className="board-cards">
                {col.tasks.map((t) => (
                  <Link
                    key={t.task_id}
                    className="board-card"
                    to={`/tasks/${t.task_id}`}
                  >
                    <div className="mono">{t.task_id}</div>
                    <div className="sub" style={{ margin: 0 }}>
                      {t.project || t.project_key} · {t.type}
                    </div>
                    <div className="badge">{t.assigned_to || "—"}</div>
                  </Link>
                ))}
                {col.tasks.length === 0 && <p className="sub">ว่าง</p>}
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
