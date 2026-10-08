-- 0003_approvals_payload_summary.sql — Operator Console (DECISION-20)
-- Safe summary of HITL payload for inbox UI (never store secrets).

BEGIN;

ALTER TABLE approvals
  ADD COLUMN IF NOT EXISTS payload_summary JSONB NOT NULL DEFAULT '{}'::jsonb;

INSERT INTO schema_migrations (version) VALUES ('0003_approvals_payload_summary')
  ON CONFLICT DO NOTHING;

COMMIT;
