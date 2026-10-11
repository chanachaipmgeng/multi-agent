import type { ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./auth";
import { LoginPage } from "./pages/LoginPage";
import { TasksPage } from "./pages/TasksPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ControlPage } from "./pages/ControlPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { LinksPage } from "./pages/LinksPage";
import { AuditPage } from "./pages/AuditPage";
import { DispatchPage } from "./pages/DispatchPage";
import { HomePage } from "./pages/HomePage";
import { SystemPage } from "./pages/SystemPage";

function Shell({ children }: { children: ReactNode }) {
  const { session, setSession } = useAuth();

  async function onLogout() {
    try {
      await api.logout();
    } catch {
      /* cookie may already be gone */
    }
    setSession(null);
  }

  return (
    <div className="shell">
      <nav className="side">
        <div className="brand">EMAW Console</div>
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          Home
        </NavLink>
        <NavLink to="/tasks" className={({ isActive }) => (isActive ? "active" : "")}>
          Tasks
        </NavLink>
        <NavLink to="/dispatch" className={({ isActive }) => (isActive ? "active" : "")}>
          Dispatch
        </NavLink>
        <NavLink to="/approvals" className={({ isActive }) => (isActive ? "active" : "")}>
          Approvals
        </NavLink>
        <NavLink to="/audit" className={({ isActive }) => (isActive ? "active" : "")}>
          Audit
        </NavLink>
        <NavLink to="/control" className={({ isActive }) => (isActive ? "active" : "")}>
          Control
        </NavLink>
        <NavLink to="/system" className={({ isActive }) => (isActive ? "active" : "")}>
          System
        </NavLink>
        <NavLink to="/projects" className={({ isActive }) => (isActive ? "active" : "")}>
          Projects
        </NavLink>
        <NavLink to="/links" className={({ isActive }) => (isActive ? "active" : "")}>
          Links
        </NavLink>
        <div style={{ flex: 1 }} />
        <div className="sub" style={{ fontSize: "0.8rem" }}>
          {session?.userName} · {session?.userId}
        </div>
        <button type="button" onClick={() => void onLogout()}>
          Logout
        </button>
      </nav>
      <main>{children}</main>
    </div>
  );
}

export function App() {
  const { session, ready } = useAuth();
  if (!ready) {
    return (
      <div className="login card">
        <p className="sub">Checking session…</p>
      </div>
    );
  }
  if (!session) return <LoginPage />;

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        <Route path="/dispatch" element={<DispatchPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/control" element={<ControlPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/links" element={<LinksPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
