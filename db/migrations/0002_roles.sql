-- 0002_roles.sql — least-privilege database roles (design §6.5, checklist E6)
--
-- Roles are NOLOGIN groups; the login users created at deploy time (Phase 3, Docker/Vault
-- secrets) are GRANTed membership:
--   emaw_gateway_rw  → webhook gateway: creates tasks, appends audit
--   emaw_coordinator → coordinator: full task/handoff/approval lifecycle, appends audit
--   emaw_worker_rw   → workers: read tasks, write handoffs, append audit
--   emaw_readonly    → dashboards / humans: SELECT only
-- Nobody gets UPDATE/DELETE on audit_events.

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emaw_gateway_rw') THEN
    CREATE ROLE emaw_gateway_rw NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emaw_coordinator') THEN
    CREATE ROLE emaw_coordinator NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emaw_worker_rw') THEN
    CREATE ROLE emaw_worker_rw NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emaw_readonly') THEN
    CREATE ROLE emaw_readonly NOLOGIN;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO emaw_gateway_rw, emaw_coordinator, emaw_worker_rw, emaw_readonly;

-- gateway
GRANT SELECT, INSERT          ON tasks         TO emaw_gateway_rw;
GRANT SELECT, INSERT          ON audit_events  TO emaw_gateway_rw;
GRANT USAGE                   ON SEQUENCE audit_events_id_seq TO emaw_gateway_rw;

-- coordinator
GRANT SELECT, INSERT, UPDATE  ON tasks         TO emaw_coordinator;
GRANT SELECT, INSERT          ON handoffs      TO emaw_coordinator;
GRANT SELECT, INSERT, UPDATE  ON approvals     TO emaw_coordinator;
GRANT SELECT, INSERT          ON audit_events  TO emaw_coordinator;
GRANT USAGE ON SEQUENCE handoffs_id_seq, approvals_id_seq, audit_events_id_seq TO emaw_coordinator;

-- workers
GRANT SELECT                  ON tasks         TO emaw_worker_rw;
GRANT SELECT, INSERT          ON handoffs      TO emaw_worker_rw;
GRANT SELECT, INSERT          ON audit_events  TO emaw_worker_rw;
GRANT USAGE ON SEQUENCE handoffs_id_seq, audit_events_id_seq TO emaw_worker_rw;

-- read-only
GRANT SELECT ON tasks, handoffs, approvals, audit_events, schema_migrations TO emaw_readonly;

REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM PUBLIC;

INSERT INTO schema_migrations (version) VALUES ('0002_roles') ON CONFLICT DO NOTHING;

COMMIT;
