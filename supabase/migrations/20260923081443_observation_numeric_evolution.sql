-- One bounded derived report per operation/version. No raw snapshots copied.
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE IF NOT EXISTS public.operation_observation_numeric_evaluations (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL REFERENCES public.operations(id) ON DELETE RESTRICT,
    evaluator_version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('long','short')),
    time_horizon TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL,
    checkpoint_count INTEGER NOT NULL CHECK (checkpoint_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('complete','blocked')),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    payload_json TEXT NOT NULL,
    payload_bytes INTEGER NOT NULL CHECK (
        payload_bytes > 0 AND payload_bytes <= 65536
        AND payload_bytes = octet_length(convert_to(payload_json,'UTF8'))
    ),
    production_effect TEXT NOT NULL DEFAULT 'none' CHECK (production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation_id,evaluator_version)
);
CREATE INDEX IF NOT EXISTS idx_observation_numeric_comparable
    ON public.operation_observation_numeric_evaluations
    (symbol,side,time_horizon,evaluator_version,closed_at DESC);
ALTER TABLE public.operation_observation_numeric_evaluations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.operation_observation_numeric_evaluations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT,INSERT ON public.operation_observation_numeric_evaluations TO service_role;
REVOKE ALL ON SEQUENCE public.operation_observation_numeric_evaluations_id_seq FROM PUBLIC,anon,authenticated;
GRANT USAGE,SELECT ON SEQUENCE public.operation_observation_numeric_evaluations_id_seq TO service_role;
COMMIT;
