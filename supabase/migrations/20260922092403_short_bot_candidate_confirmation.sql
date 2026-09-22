-- Add a compact checkpoint kind. No new tables, columns, historical rewrites,
-- privileges or RLS changes. Apply before deploying the short-bot selector.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
ALTER TABLE public.autonomous_candidate_observations
    DROP CONSTRAINT IF EXISTS autonomous_candidate_observations_storage_reason_check;
ALTER TABLE public.autonomous_candidate_observations
    ADD CONSTRAINT autonomous_candidate_observations_storage_reason_check
    CHECK (storage_reason IN ('panel', 'selected', 'boundary', 'confirmation'));
COMMIT;
