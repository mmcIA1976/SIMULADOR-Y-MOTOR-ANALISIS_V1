CREATE TABLE IF NOT EXISTS public.order_book_observation_state (
    symbol TEXT PRIMARY KEY
        CHECK(symbol ~ '^[A-Z0-9]{5,20}$'),
    summary_json JSONB NOT NULL,
    source TEXT NOT NULL,
    publisher TEXT NOT NULL DEFAULT 'operation_worker'
        CHECK(publisher = 'operation_worker'),
    captured_at TIMESTAMPTZ NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    sample_count INTEGER NOT NULL CHECK(sample_count >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.order_book_observation_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES
    ON TABLE public.order_book_observation_state
    FROM anon, authenticated;
GRANT ALL PRIVILEGES
    ON TABLE public.order_book_observation_state
    TO postgres, service_role;
