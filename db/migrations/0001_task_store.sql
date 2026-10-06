-- 0001_task_store.sql — Task Store schema (design §A.7, §3.6, §4.5, §6.5)
-- Applied automatically on first `docker compose up` (postgres initdb) or via scripts/migrate.sh.

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     TEXT PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- tasks
CREATE TABLE IF NOT EXISTS tasks (
  task_id            TEXT PRIMARY KEY,
  trace_id           TEXT NOT NULL,
  type               TEXT NOT NULL
                     CHECK (type IN ('issue','feature','pipeline_failed','job_failed','review','deploy_request')),
  project_key        TEXT NOT NULL,
  issue_iid          INT,
  state              TEXT NOT NULL
                     CHECK (state IN ('RECEIVED','REJECTED','QUEUED','ASSIGNED','IN_PROGRESS','REVIEW',
                                      'AWAITING_APPROVAL','APPROVED','NEEDS_HUMAN','DONE','FAILED',
                                      'CANCELLED','EXPIRED')),
  assigned_to        TEXT,
  requester_user_id  BIGINT,
  skill              TEXT,
  source             JSONB NOT NULL DEFAULT '{}'::jsonb,
  inputs             JSONB NOT NULL DEFAULT '{}'::jsonb,
  constraints        JSONB NOT NULL DEFAULT '{}'::jsonb,
  result             JSONB,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "1 Issue = 1 active task" (§4.5). A partial unique index (instead of a plain UNIQUE
-- constraint) lets a closed/failed task be followed by a new one when the issue is reopened.
CREATE UNIQUE INDEX IF NOT EXISTS tasks_one_active_per_issue
  ON tasks (project_key, issue_iid)
  WHERE issue_iid IS NOT NULL
    AND state NOT IN ('DONE','FAILED','CANCELLED','EXPIRED','REJECTED');

CREATE INDEX IF NOT EXISTS tasks_trace_id_idx ON tasks (trace_id);
CREATE INDEX IF NOT EXISTS tasks_state_idx    ON tasks (state);
CREATE INDEX IF NOT EXISTS tasks_project_idx  ON tasks (project_key, created_at DESC);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tasks_set_updated_at ON tasks;
CREATE TRIGGER tasks_set_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ------------------------------------------------------------- handoffs
CREATE TABLE IF NOT EXISTS handoffs (
  id             BIGSERIAL PRIMARY KEY,
  task_id        TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE RESTRICT,
  from_agent     TEXT NOT NULL,
  to_agent       TEXT NOT NULL,
  reason         TEXT,
  worktree_path  TEXT,
  branch         TEXT,
  summary        TEXT,
  open_questions TEXT,
  artifacts      JSONB NOT NULL DEFAULT '[]'::jsonb,
  token_spent    INT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS handoffs_task_idx ON handoffs (task_id, created_at);

-- ------------------------------------------------------------ approvals
CREATE TABLE IF NOT EXISTS approvals (
  id            BIGSERIAL PRIMARY KEY,
  task_id       TEXT NOT NULL REFERENCES tasks (task_id) ON DELETE RESTRICT,
  action        TEXT NOT NULL,              -- push_branch | create_mr | deploy_prod | migration | infra_change | budget_increase
  payload_hash  TEXT NOT NULL,              -- sha256 of the exact action payload shown to the approver
  nonce         TEXT NOT NULL UNIQUE,       -- bound to the Telegram inline keyboard callback
  requested_by  TEXT NOT NULL,              -- agent that asked
  required_role TEXT NOT NULL DEFAULT 'developer',  -- developer | approver (DECISION-8)
  timeout_at    TIMESTAMPTZ NOT NULL,
  requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_by    BIGINT,                     -- Telegram user id
  decision      TEXT CHECK (decision IN ('approved','rejected','expired')),
  decided_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS approvals_task_idx    ON approvals (task_id);
CREATE INDEX IF NOT EXISTS approvals_pending_idx ON approvals (timeout_at) WHERE decision IS NULL;

-- --------------------------------------------------------- audit_events
-- Append-only. UPDATE/DELETE are blocked by trigger for *every* role (defense in depth on
-- top of the GRANT model in 0002_roles.sql).
CREATE TABLE IF NOT EXISTS audit_events (
  id        BIGSERIAL PRIMARY KEY,
  ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
  trace_id  TEXT,
  task_id   TEXT,
  actor     TEXT NOT NULL,                  -- webhook-gateway | coordinator | dev-frontend | … | human:<user_id>
  event     TEXT NOT NULL,                  -- task.received | task.queued | tool.exec | approval.granted | …
  attrs     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_events_trace_idx ON audit_events (trace_id, ts);
CREATE INDEX IF NOT EXISTS audit_events_task_idx  ON audit_events (task_id, ts);
CREATE INDEX IF NOT EXISTS audit_events_ts_idx    ON audit_events (ts);

CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only (% not allowed)', TG_OP
    USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events;
CREATE TRIGGER audit_events_no_update_delete
  BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();

INSERT INTO schema_migrations (version) VALUES ('0001_task_store') ON CONFLICT DO NOTHING;

COMMIT;
