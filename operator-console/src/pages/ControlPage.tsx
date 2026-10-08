import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

const AGENTS = [
  "all",
  "coordinator",
  "dev-frontend",
  "dev-backend",
  "reviewer",
  "devops",
  "qa",
];

export function ControlPage() {
  const { session } = useAuth();
  const [safeMode, setSafeMode] = useState(false);
  const [paused, setPaused] = useState<string[]>([]);
  const [agent, setAgent] = useState("all");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!session) return;
    setError(null);
    try {
      const s = await api.controlStatus(session);
      setSafeMode(s.safe_mode);
      setPaused(s.paused_agents || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, [session]);

  async function run(op: "pause" | "resume" | "safe-on" | "safe-off") {
    if (!session) return;
    setError(null);
    try {
      if (op === "pause") await api.pause(session, agent);
      if (op === "resume") await api.resume(session, agent);
      if (op === "safe-on") await api.safeMode(session, true);
      if (op === "safe-off") await api.safeMode(session, false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <h1>Control</h1>
      <p className="sub">pause / resume / safe-mode (admin RBAC)</p>
      {error && <p className="err">{error}</p>}
      <div className="card">
        <p>
          Safe mode:{" "}
          <span className={`badge ${safeMode ? "warn" : "ok"}`}>
            {safeMode ? "ON" : "OFF"}
          </span>
        </p>
        <p>
          Paused agents:{" "}
          {paused.length ? paused.map((a) => (
            <span key={a} className="badge warn" style={{ marginRight: 4 }}>
              {a}
            </span>
          )) : (
            <span className="sub">none</span>
          )}
        </p>
        <div className="row">
          <button type="button" className="danger" onClick={() => void run("safe-on")}>
            Enable safe-mode
          </button>
          <button type="button" onClick={() => void run("safe-off")}>
            Disable safe-mode
          </button>
        </div>
      </div>
      <div className="card">
        <div className="row">
          <select value={agent} onChange={(e) => setAgent(e.target.value)}>
            {AGENTS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => void run("pause")}>
            Pause
          </button>
          <button type="button" className="primary" onClick={() => void run("resume")}>
            Resume
          </button>
          <button type="button" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>
    </>
  );
}
