-- Monitor visual y control de ciclo de las observaciones de operaciones.
-- Los eventos son compactos, internos, append-only y no afectan al motor.

ALTER TABLE public.operation_observation_sessions
    ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ;

ALTER TABLE public.operation_observation_sessions
    DROP CONSTRAINT IF EXISTS operation_observation_sessions_status_check,
    DROP CONSTRAINT IF EXISTS operation_observation_sessions_check1,
    DROP CONSTRAINT IF EXISTS operation_observation_sessions_lifecycle_check,
    DROP CONSTRAINT IF EXISTS operation_observation_sessions_paused_check;

ALTER TABLE public.operation_observation_sessions
    ADD CONSTRAINT operation_observation_sessions_status_check
        CHECK(status IN ('active', 'paused', 'completed', 'cancelled')),
    ADD CONSTRAINT operation_observation_sessions_lifecycle_check
        CHECK(
            (status IN ('active', 'paused') AND ended_at IS NULL)
            OR (
                status IN ('completed', 'cancelled')
                AND ended_at IS NOT NULL
            )
        ),
    ADD CONSTRAINT operation_observation_sessions_paused_check
        CHECK(
            (status = 'paused' AND paused_at IS NOT NULL)
            OR status <> 'paused'
        );

CREATE TABLE IF NOT EXISTS public.operation_observation_session_events (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    operation_id BIGINT NOT NULL,
    event_type TEXT NOT NULL CHECK(
        event_type IN (
            'started', 'interval_changed', 'paused', 'resumed',
            'stopped', 'operation_closed'
        )
    ),
    occurred_at TIMESTAMPTZ NOT NULL,
    from_status TEXT CHECK(
        from_status IS NULL OR from_status IN (
            'active', 'paused', 'completed', 'cancelled'
        )
    ),
    to_status TEXT CHECK(
        to_status IS NULL OR to_status IN (
            'active', 'paused', 'completed', 'cancelled'
        )
    ),
    interval_minutes INTEGER CHECK(
        interval_minutes IS NULL OR interval_minutes BETWEEN 1 AND 1440
    ),
    details_json TEXT NOT NULL
        CHECK(jsonb_typeof(details_json::jsonb) = 'object'),
    details_bytes INTEGER NOT NULL CHECK(
        details_bytes > 0 AND details_bytes <= 4096
        AND details_bytes = octet_length(convert_to(details_json, 'UTF8'))
    ),
    details_sha256 TEXT NOT NULL CHECK(details_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id, operation_id)
        REFERENCES public.operation_observation_sessions(id, operation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_observation_session_events_timeline
    ON public.operation_observation_session_events(
        operation_id, occurred_at, id
    );

CREATE INDEX IF NOT EXISTS idx_observation_session_events_session
    ON public.operation_observation_session_events(session_id, operation_id);

ALTER TABLE public.operation_observation_session_events
    ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES
    ON TABLE public.operation_observation_session_events
    FROM anon, authenticated;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_observation_session_events
    FROM service_role;
GRANT SELECT, INSERT
    ON TABLE public.operation_observation_session_events
    TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.operation_observation_session_events_id_seq
    TO service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid =
            'public.operation_observation_session_events'::regclass
          AND tgname = 'operation_observation_session_events_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER operation_observation_session_events_append_only
        BEFORE UPDATE OR DELETE
        ON public.operation_observation_session_events
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_operation_observation_fact_mutation();
    END IF;
END $$;
