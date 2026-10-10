import { useEffect, useState } from "react";
import { api, type ProjectRow } from "../api";
import { useAuth } from "../auth";
import { grafanaBaseUrl } from "../opsLinks";

export function ProjectsPage() {
  const { session } = useAuth();
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session) return;
    void (async () => {
      try {
        const data = await api.listProjects(session);
        setProjects(data.projects);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [session]);

  return (
    <>
      <h1>Projects</h1>
      <p className="sub">อ่านจาก projects.yaml (read-only)</p>
      {error && <p className="err">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Key</th>
              <th>SCM</th>
              <th>Path / repo</th>
              <th>Worker</th>
              <th>Links</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.key}>
                <td className="mono">{p.key}</td>
                <td>
                  <span className="badge">{p.scm}</span>
                </td>
                <td className="mono">
                  {p.repo || p.path_with_namespace}
                  <div className="sub">{p.workspace_path}</div>
                </td>
                <td>{p.default_worker}</td>
                <td className="links">
                  <a
                    href={`${grafanaBaseUrl()}/d/emaw-operations?var-project=${encodeURIComponent(p.key)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Grafana
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
