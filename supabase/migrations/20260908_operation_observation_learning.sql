-- Seguimiento observacional de una operacion real.
-- Cada control exacto enlaza una recomendacion completa del mismo motor de
-- produccion; las reconstrucciones parciales quedan expresamente fuera de las
-- metricas formales. No se guardan velas ni libros de ordenes sin procesar.

CREATE TABLE IF NOT EXISTS public.operation_observation_sessions (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL UNIQUE
        REFERENCES public.operations(id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    opening_recommendation_id BIGINT
        REFERENCES public.recommendations(id) ON DELETE RESTRICT,
    session_code TEXT NOT NULL UNIQUE CHECK(session_code ~ '^[0-9]+o$'),
    status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'cancelled')),
    capture_mode TEXT NOT NULL CHECK(capture_mode IN ('live', 'reconstructed')),
    contract_version TEXT NOT NULL,
    planned_interval_minutes INTEGER CHECK(
        planned_interval_minutes IS NULL
        OR planned_interval_minutes BETWEEN 1 AND 1440
    ),
    reported_checkpoint_count INTEGER NOT NULL DEFAULT 0
        CHECK(reported_checkpoint_count >= 0),
    stored_checkpoint_count INTEGER NOT NULL DEFAULT 0
        CHECK(stored_checkpoint_count >= 0),
    next_checkpoint_number INTEGER NOT NULL DEFAULT 1
        CHECK(next_checkpoint_number > 0),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    evidence_source TEXT NOT NULL,
    evidence_quality TEXT NOT NULL
        CHECK(evidence_quality IN ('exact', 'reconstructed_partial')),
    summary_json TEXT NOT NULL
        CHECK(jsonb_typeof(summary_json::jsonb) = 'object'),
    summary_bytes INTEGER NOT NULL CHECK(
        summary_bytes > 0 AND summary_bytes <= 16384
        AND summary_bytes = octet_length(convert_to(summary_json, 'UTF8'))
    ),
    summary_sha256 TEXT NOT NULL CHECK(summary_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id, operation_id),
    CHECK(
        (status = 'active' AND ended_at IS NULL)
        OR (status <> 'active' AND ended_at IS NOT NULL)
    ),
    CHECK(
        (capture_mode = 'live' AND evidence_quality = 'exact')
        OR (capture_mode = 'reconstructed'
            AND evidence_quality = 'reconstructed_partial')
    )
);

CREATE TABLE IF NOT EXISTS public.operation_observation_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    operation_id BIGINT NOT NULL,
    recommendation_id BIGINT UNIQUE
        REFERENCES public.recommendations(id) ON DELETE RESTRICT,
    checkpoint_number INTEGER NOT NULL CHECK(checkpoint_number > 0),
    checkpoint_code TEXT NOT NULL UNIQUE
        CHECK(checkpoint_code ~ '^[0-9]+o[0-9]+$'),
    observed_at TIMESTAMPTZ NOT NULL,
    source_turn_id TEXT,
    market_price DOUBLE PRECISION NOT NULL CHECK(market_price > 0),
    unrealized_pnl DOUBLE PRECISION NOT NULL,
    remaining_seconds INTEGER CHECK(remaining_seconds >= 0),
    tp_probability DOUBLE PRECISION CHECK(tp_probability BETWEEN 0 AND 1),
    sl_probability DOUBLE PRECISION CHECK(sl_probability BETWEEN 0 AND 1),
    range_probability DOUBLE PRECISION CHECK(range_probability BETWEEN 0 AND 1),
    decision TEXT NOT NULL CHECK(
        decision IN ('unreviewed', 'hold', 'watch', 'protect', 'close', 'final')
    ),
    decision_candidate BOOLEAN NOT NULL DEFAULT FALSE,
    contract_quality TEXT NOT NULL
        CHECK(contract_quality IN ('exact', 'reconstructed_partial')),
    formal_learning_eligible BOOLEAN NOT NULL,
    evidence_source TEXT NOT NULL,
    context_json TEXT NOT NULL
        CHECK(jsonb_typeof(context_json::jsonb) = 'object'),
    context_bytes INTEGER NOT NULL CHECK(
        context_bytes > 0 AND context_bytes <= 16384
        AND context_bytes = octet_length(convert_to(context_json, 'UTF8'))
    ),
    context_sha256 TEXT NOT NULL CHECK(context_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, checkpoint_number),
    UNIQUE(id, operation_id),
    FOREIGN KEY(session_id, operation_id)
        REFERENCES public.operation_observation_sessions(id, operation_id)
        ON DELETE RESTRICT,
    CHECK(
        (contract_quality = 'exact'
            AND formal_learning_eligible
            AND recommendation_id IS NOT NULL)
        OR (contract_quality = 'reconstructed_partial'
            AND NOT formal_learning_eligible
            AND recommendation_id IS NULL)
    ),
    CHECK(
        (tp_probability IS NULL AND sl_probability IS NULL
            AND range_probability IS NULL)
        OR (
            tp_probability IS NOT NULL
            AND sl_probability IS NOT NULL
            AND range_probability IS NOT NULL
            AND abs(tp_probability + sl_probability + range_probability - 1.0)
                <= 0.0000011
        )
    )
);

CREATE TABLE IF NOT EXISTS public.operation_exit_counterfactuals (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL,
    checkpoint_id BIGINT NOT NULL,
    evaluator_version TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    actual_final_pnl DOUBLE PRECISION NOT NULL,
    pnl_if_closed DOUBLE PRECISION NOT NULL,
    missed_profit DOUBLE PRECISION NOT NULL,
    protected_drawdown DOUBLE PRECISION,
    tp_reached_after BOOLEAN NOT NULL,
    sl_reached_after BOOLEAN NOT NULL,
    time_to_terminal_minutes DOUBLE PRECISION
        CHECK(time_to_terminal_minutes IS NULL OR time_to_terminal_minutes >= 0),
    absolute_profit_verdict TEXT NOT NULL,
    risk_adjusted_verdict TEXT NOT NULL,
    contract_quality TEXT NOT NULL
        CHECK(contract_quality IN ('exact', 'reconstructed_partial')),
    formal_learning_eligible BOOLEAN NOT NULL,
    evaluation_json TEXT NOT NULL
        CHECK(jsonb_typeof(evaluation_json::jsonb) = 'object'),
    evaluation_bytes INTEGER NOT NULL CHECK(
        evaluation_bytes > 0 AND evaluation_bytes <= 8192
        AND evaluation_bytes = octet_length(convert_to(evaluation_json, 'UTF8'))
    ),
    evaluation_sha256 TEXT NOT NULL
        CHECK(evaluation_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(checkpoint_id, evaluator_version),
    FOREIGN KEY(checkpoint_id, operation_id)
        REFERENCES public.operation_observation_checkpoints(id, operation_id)
        ON DELETE RESTRICT,
    CHECK(formal_learning_eligible = (contract_quality = 'exact'))
);

CREATE INDEX IF NOT EXISTS idx_observation_sessions_user_status
    ON public.operation_observation_sessions(user_id, status, started_at);
CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_episode_time
    ON public.operation_observation_checkpoints(operation_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_learning
    ON public.operation_observation_checkpoints(
        formal_learning_eligible, contract_quality, observed_at
    );
CREATE INDEX IF NOT EXISTS idx_exit_counterfactual_operation
    ON public.operation_exit_counterfactuals(operation_id, evaluated_at);

ALTER TABLE public.operation_observation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_observation_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_exit_counterfactuals ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.operation_observation_sessions
    FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_observation_checkpoints
    FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_exit_counterfactuals
    FROM anon, authenticated;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_observation_sessions FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_observation_checkpoints FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_exit_counterfactuals FROM service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.operation_observation_sessions
    TO service_role;
GRANT SELECT, INSERT ON TABLE public.operation_observation_checkpoints
    TO service_role;
GRANT SELECT, INSERT ON TABLE public.operation_exit_counterfactuals
    TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.operation_observation_sessions_id_seq
    TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.operation_observation_checkpoints_id_seq
    TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.operation_exit_counterfactuals_id_seq
    TO service_role;

CREATE OR REPLACE FUNCTION public.prevent_operation_observation_fact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'operation_observation_fact_is_append_only';
END;
$$;

REVOKE ALL
    ON FUNCTION public.prevent_operation_observation_fact_mutation()
    FROM PUBLIC, anon, authenticated, service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.operation_observation_checkpoints'::regclass
          AND tgname = 'operation_observation_checkpoints_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER operation_observation_checkpoints_append_only
        BEFORE UPDATE OR DELETE
        ON public.operation_observation_checkpoints
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_operation_observation_fact_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.operation_exit_counterfactuals'::regclass
          AND tgname = 'operation_exit_counterfactuals_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER operation_exit_counterfactuals_append_only
        BEFORE UPDATE OR DELETE
        ON public.operation_exit_counterfactuals
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_operation_observation_fact_mutation();
    END IF;
END $$;
