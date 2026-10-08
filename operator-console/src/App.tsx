import type { ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { LoginPage } from "./pages/LoginPage";
import { TasksPage } from "./pages/TasksPage";
import { TaskDetailPage } from "./pages/TaskDetailPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ControlPage } from "./pages/ControlPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { LinksPage } from "./pages/LinksPage";

function Shell({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth();
  return (
    <div className="shell">
      <nav className="side">
        <div className="brand">EMAW Console</div>
        <NavLink to="/tasks" className={({ isActive }) => (isActive ? "active" : "")}>
          Tasks
        </NavLink>
        <NavLink to="/approvals" className={({ isActive }) => (isActive ? "active" : "")}>
          Approvals
        </NavLink>
        <NavLink to="/control" className={({ isActive }) => (isActive ? "active" : "")}>
          Control
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
        <button type="button" onClick={logout}>
          Logout
        </button>
      </nav>
      <main>{children}</main>
    </div>
  );
}

export function App() {
  const { session } = useAuth();
  if (!session) return <LoginPage />;

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to="/tasks" replace />} />
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/control" element={<ControlPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/links" element={<LinksPage />} />
        <Route path="*" element={<Navigate to="/tasks" replace />} />
      </Routes>
    </Shell>
  );
}
