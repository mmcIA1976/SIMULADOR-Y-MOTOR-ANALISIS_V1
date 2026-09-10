-- Compact, version-independent observational learning baseline.
-- It preserves formula-compatible signals and outcomes without retaining raw
-- candles, books, snapshots or narrative analysis payloads.

CREATE TABLE IF NOT EXISTS public.observational_learning_cohorts (
    id BIGSERIAL PRIMARY KEY,
    cohort_key TEXT NOT NULL UNIQUE,
    contract_version TEXT NOT NULL,
    historical_cutoff_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('building', 'verified', 'sealed')),
    audit_version TEXT NOT NULL,
    audit_sha256 TEXT NOT NULL CHECK(audit_sha256 ~ '^[0-9a-f]{64}$'),
    rule_catalog_sha256 TEXT NOT NULL CHECK(rule_catalog_sha256 ~ '^[0-9a-f]{64}$'),
    source_dataset_sha256 TEXT NOT NULL CHECK(source_dataset_sha256 ~ '^[0-9a-f]{64}$'),
    compact_dataset_sha256 TEXT CHECK(
        compact_dataset_sha256 IS NULL OR compact_dataset_sha256 ~ '^[0-9a-f]{64}$'
    ),
    historical_case_count INTEGER NOT NULL DEFAULT 0 CHECK(historical_case_count >= 0),
    historical_episode_count INTEGER NOT NULL DEFAULT 0 CHECK(historical_episode_count >= 0),
    protocol_json TEXT NOT NULL CHECK(jsonb_typeof(protocol_json::jsonb) = 'object'),
    summary_json TEXT NOT NULL CHECK(jsonb_typeof(summary_json::jsonb) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMPTZ,
    CHECK(status = 'building' OR (compact_dataset_sha256 IS NOT NULL AND verified_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS public.observational_rule_baselines (
    id BIGSERIAL PRIMARY KEY,
    cohort_id BIGINT NOT NULL REFERENCES public.observational_learning_cohorts(id) ON DELETE RESTRICT,
    rule_id TEXT NOT NULL,
    time_horizon TEXT NOT NULL CHECK(time_horizon IN ('intraday_short', 'intraday_wide', 'short_swing')),
    target TEXT NOT NULL CHECK(target IN ('directional', 'movement')),
    selected_variable TEXT NOT NULL,
    orientation TEXT NOT NULL CHECK(orientation IN ('direct', 'inverse')),
    lifecycle_status TEXT NOT NULL CHECK(lifecycle_status = 'observational'),
    probability_weight DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK(probability_weight = 0),
    formula_contract_json TEXT NOT NULL CHECK(jsonb_typeof(formula_contract_json::jsonb) = 'object'),
    formula_contract_sha256 TEXT NOT NULL CHECK(formula_contract_sha256 ~ '^[0-9a-f]{64}$'),
    historical_metrics_json TEXT NOT NULL CHECK(jsonb_typeof(historical_metrics_json::jsonb) = 'object'),
    continuation_json TEXT NOT NULL CHECK(jsonb_typeof(continuation_json::jsonb) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cohort_id, rule_id, time_horizon)
);

CREATE TABLE IF NOT EXISTS public.observational_learning_cases (
    id BIGSERIAL PRIMARY KEY,
    cohort_id BIGINT NOT NULL REFERENCES public.observational_learning_cohorts(id) ON DELETE RESTRICT,
    case_key TEXT NOT NULL UNIQUE CHECK(case_key ~ '^[0-9a-f]{64}$'),
    cohort_partition TEXT NOT NULL CHECK(cohort_partition IN ('historical', 'prospective')),
    source_kind TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    time_horizon TEXT NOT NULL CHECK(time_horizon IN ('intraday_short', 'intraday_wide', 'short_swing')),
    analysis_at TIMESTAMPTZ NOT NULL,
    evaluation_expires_at TIMESTAMPTZ NOT NULL,
    outcome_label TEXT NOT NULL CHECK(outcome_label IN (
        'tp_first_within_horizon', 'sl_first_within_horizon',
        'neither_barrier_before_expiry'
    )),
    episode_key TEXT CHECK(episode_key IS NULL OR episode_key ~ '^[0-9a-f]{64}$'),
    episode_weight DOUBLE PRECISION CHECK(episode_weight IS NULL OR (episode_weight > 0 AND episode_weight <= 1)),
    probabilities_json TEXT NOT NULL CHECK(jsonb_typeof(probabilities_json::jsonb) = 'object'),
    signals_json TEXT NOT NULL CHECK(jsonb_typeof(signals_json::jsonb) = 'object'),
    signal_count INTEGER NOT NULL CHECK(signal_count >= 0),
    missing_rule_ids_json TEXT NOT NULL CHECK(jsonb_typeof(missing_rule_ids_json::jsonb) = 'array'),
    contract_version TEXT NOT NULL,
    source_identity_sha256 TEXT NOT NULL CHECK(source_identity_sha256 ~ '^[0-9a-f]{64}$'),
    payload_sha256 TEXT NOT NULL UNIQUE CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(
        (cohort_partition = 'historical' AND episode_key IS NOT NULL AND episode_weight IS NOT NULL)
        OR cohort_partition = 'prospective'
    )
);

CREATE INDEX IF NOT EXISTS idx_observational_cases_cohort_time
    ON public.observational_learning_cases(cohort_id, cohort_partition, analysis_at);
CREATE INDEX IF NOT EXISTS idx_observational_cases_learning_slice
    ON public.observational_learning_cases(cohort_id, time_horizon, outcome_label, analysis_at);
CREATE INDEX IF NOT EXISTS idx_observational_baselines_rule
    ON public.observational_rule_baselines(cohort_id, rule_id, time_horizon);

ALTER TABLE public.observational_learning_cohorts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observational_rule_baselines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.observational_learning_cases ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.observational_learning_cohorts FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.observational_rule_baselines FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.observational_learning_cases FROM anon, authenticated;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.observational_learning_cohorts FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.observational_rule_baselines FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.observational_learning_cases FROM service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.observational_learning_cohorts TO service_role;
GRANT SELECT, INSERT ON TABLE public.observational_rule_baselines TO service_role;
GRANT SELECT, INSERT ON TABLE public.observational_learning_cases TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.observational_learning_cohorts_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.observational_rule_baselines_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.observational_learning_cases_id_seq TO service_role;

CREATE OR REPLACE FUNCTION public.prevent_observational_learning_fact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'observational_learning_fact_is_append_only';
END;
$$;

REVOKE ALL ON FUNCTION public.prevent_observational_learning_fact_mutation()
    FROM PUBLIC, anon, authenticated, service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.observational_rule_baselines'::regclass
          AND tgname = 'observational_rule_baselines_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER observational_rule_baselines_append_only
        BEFORE UPDATE OR DELETE ON public.observational_rule_baselines
        FOR EACH ROW EXECUTE FUNCTION public.prevent_observational_learning_fact_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.observational_learning_cases'::regclass
          AND tgname = 'observational_learning_cases_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER observational_learning_cases_append_only
        BEFORE UPDATE OR DELETE ON public.observational_learning_cases
        FOR EACH ROW EXECUTE FUNCTION public.prevent_observational_learning_fact_mutation();
    END IF;
END $$;
