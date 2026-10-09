import type { Session } from "./auth";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  session: Session,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${session.apiKey}`);
  headers.set("X-EMAW-User-Id", session.userId);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.reason || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type TaskRow = {
  task_id: string;
  trace_id: string;
  type: string;
  project: string;
  project_key?: string;
  state: string;
  assigned_to?: string | null;
  skill?: string | null;
  created_at?: string | null;
  source?: Record<string, unknown>;
  inputs?: Record<string, unknown>;
  handoffs?: Array<Record<string, unknown>>;
  links?: string[];
};

export type ApprovalRow = {
  nonce: string;
  task_id: string;
  action: string;
  payload_summary?: Record<string, unknown>;
  required_role?: string;
  timeout_at?: string;
  decision?: string | null;
};

export type ProjectRow = {
  key: string;
  scm: string;
  path_with_namespace: string;
  repo?: string | null;
  workspace_path: string;
  default_worker: string;
  allowed_workers: string[];
  opt_in_label: string;
  data_classification: string;
  llm_backend: string;
};

export const api = {
  listTasks: (s: Session, q: { project?: string; state?: string } = {}) => {
    const params = new URLSearchParams();
    if (q.project) params.set("project", q.project);
    if (q.state) params.set("state", q.state);
    const qs = params.toString();
    return request<{ tasks: TaskRow[]; count: number }>(
      s,
      `/internal/tasks${qs ? `?${qs}` : ""}`,
    );
  },
  getTask: (s: Session, id: string) =>
    request<TaskRow>(s, `/internal/tasks/${encodeURIComponent(id)}`),
  listApprovals: (s: Session, status = "pending") =>
    request<{ approvals: ApprovalRow[]; count: number }>(
      s,
      `/internal/approvals?status=${encodeURIComponent(status)}`,
    ),
  decideApproval: (s: Session, nonce: string, decision: "approved" | "rejected") =>
    request<{ status: string; task_id: string }>(
      s,
      `/internal/approvals/${encodeURIComponent(nonce)}/decide`,
      { method: "POST", body: JSON.stringify({ decision }) },
    ),
  controlStatus: (s: Session) =>
    request<{ safe_mode: boolean; pause_all: boolean; paused_agents: string[] }>(
      s,
      "/internal/control/status",
    ),
  pause: (s: Session, agent: string) =>
    request(s, "/internal/control/pause", {
      method: "POST",
      body: JSON.stringify({ agent }),
    }),
  resume: (s: Session, agent: string) =>
    request(s, "/internal/control/resume", {
      method: "POST",
      body: JSON.stringify({ agent }),
    }),
  safeMode: (s: Session, enabled: boolean) =>
    request(s, "/internal/control/safe-mode", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  listProjects: (s: Session) =>
    request<{ projects: ProjectRow[]; count: number }>(s, "/internal/projects"),
  listAudit: (
    s: Session,
    q: { taskId?: string; traceId?: string },
  ) => {
    const params = new URLSearchParams();
    if (q.taskId) params.set("task_id", q.taskId);
    if (q.traceId) params.set("trace_id", q.traceId);
    return request<{ events: Array<Record<string, unknown>>; count: number }>(
      s,
      `/internal/audit?${params.toString()}`,
    );
  },
  listUsers: (s: Session) =>
    request<{
      users: Array<{ user_id: number; name: string; roles: string[] }>;
      count: number;
    }>(s, "/internal/rbac/users"),
  healthz: () => fetch(`${BASE}/healthz`).then((r) => r.json()),
};
