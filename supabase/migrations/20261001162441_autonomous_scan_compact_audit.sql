-- All candidate decisions in the existing scan row. No candle/snapshot copies,
-- historical backfill, extra counterfactual jobs, grants or new tables.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
ALTER TABLE public.autonomous_scan_runs
    ADD COLUMN IF NOT EXISTS candidate_audit_json JSONB;
COMMENT ON COLUMN public.autonomous_scan_runs.candidate_audit_json IS
    'Versioned compact scalar results of every proposal/confirmation in this scan; NULL means legacy coverage is incomplete.';
COMMIT;
