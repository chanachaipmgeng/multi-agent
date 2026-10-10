import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type ProjectRow } from "../api";
import { useAuth } from "../auth";

const TASK_TYPES = [
  "feature",
  "issue",
  "review",
  "deploy_request",
  "pipeline_failed",
  "job_failed",
] as const;

export function DispatchPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [project, setProject] = useState("sandbox-smoke");
  const [type, setType] = useState<string>("feature");
  const [assignedTo, setAssignedTo] = useState("");
  const [instruction, setInstruction] = useState("");
  const [labels, setLabels] = useState("area:backend");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [createdId, setCreatedId] = useState<string | null>(null);

  const selected = projects.find((p) => p.key === project);
  const workers = selected?.allowed_workers || [];

  useEffect(() => {
    if (!session) return;
    void (async () => {
      try {
        const data = await api.listProjects(session);
        setProjects(data.projects);
        if (data.projects.some((p) => p.key === "sandbox-smoke")) {
          setProject("sandbox-smoke");
        } else if (data.projects[0]) {
          setProject(data.projects[0].key);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [session]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    if (!project.trim() || !instruction.trim()) {
      setError("ต้องระบุ project และ instruction");
      return;
    }
    setBusy(true);
    setError(null);
    setCreatedId(null);
    try {
      const labelList = labels
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await api.createTask(session, {
        project: project.trim(),
        type,
        instruction: instruction.trim(),
        labels: labelList,
        ...(assignedTo ? { assigned_to: assignedTo } : {}),
        idempotency_key: `console-dispatch:${crypto.randomUUID()}`,
      });
      if (res.task_id) {
        setCreatedId(res.task_id);
        navigate(`/tasks/${res.task_id}`);
      } else {
        setError(`unexpected status: ${res.status}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Dispatch</h1>
      <p className="sub">สร้างงานด้วยมือผ่าน POST /internal/tasks (ไม่ต้องรอ SCM webhook)</p>
      <form className="card" onSubmit={(e) => void onSubmit(e)}>
        <label htmlFor="project">Project</label>
        <select
          id="project"
          value={project}
          onChange={(e) => {
            setProject(e.target.value);
            setAssignedTo("");
          }}
        >
          {projects.map((p) => (
            <option key={p.key} value={p.key}>
              {p.key} · {p.default_worker}
            </option>
          ))}
        </select>

        <label htmlFor="type">Type</label>
        <select id="type" value={type} onChange={(e) => setType(e.target.value)}>
          {TASK_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <label htmlFor="worker">Assigned to (optional)</label>
        <select id="worker" value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)}>
          <option value="">auto-route ({selected?.default_worker || "default"})</option>
          {workers.map((w) => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>

        <label htmlFor="labels">Labels (comma-separated)</label>
        <input
          id="labels"
          value={labels}
          onChange={(e) => setLabels(e.target.value)}
          placeholder="area:backend"
        />

        <label htmlFor="instruction">Instruction</label>
        <textarea
          id="instruction"
          rows={5}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="เช่น: add a no-op comment in README and run tests"
          required
        />

        {error && <p className="err">{error}</p>}
        {createdId && (
          <p className="sub">
            Created{" "}
            <Link className="mono" to={`/tasks/${createdId}`}>
              {createdId}
            </Link>
          </p>
        )}

        <div className="row" style={{ marginTop: "0.75rem" }}>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Creating…" : "Create task"}
          </button>
        </div>
      </form>
    </>
  );
}
