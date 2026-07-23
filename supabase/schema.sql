CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    starting_balance DOUBLE PRECISION NOT NULL DEFAULT 1000,
    cash_balance DOUBLE PRECISION NOT NULL DEFAULT 1000,
    avatar_path TEXT,
    avatar_mime_type TEXT,
    avatar_data BYTEA,
    avatar_updated_at TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    entry DOUBLE PRECISION NOT NULL,
    margin DOUBLE PRECISION NOT NULL,
    leverage DOUBLE PRECISION NOT NULL,
    time_horizon TEXT NOT NULL DEFAULT 'intraday_short',
    stop_loss DOUBLE PRECISION NOT NULL,
    take_profit DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING_ANALYSIS',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    closed_at TEXT,
    close_price DOUBLE PRECISION,
    close_reason TEXT,
    final_pnl DOUBLE PRECISION,
    observation_until TEXT,
    observation_status TEXT,
    post_emotion TEXT,
    plan_followed TEXT,
    closing_note TEXT,
    observation_result TEXT,
    observation_result_at TEXT,
    observation_summary TEXT,
    learning_outcome TEXT,
    learning_summary TEXT,
    exit_evidence_json TEXT,
    mode TEXT NOT NULL DEFAULT 'training',
    contest_season_id BIGINT
);

CREATE TABLE IF NOT EXISTS recommendations (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analysis_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    tp_probability DOUBLE PRECISION NOT NULL,
    sl_probability DOUBLE PRECISION NOT NULL,
    range_probability DOUBLE PRECISION NOT NULL,
    risk_level TEXT NOT NULL,
    setup_grade TEXT NOT NULL,
    confidence TEXT NOT NULL,
    training_decision TEXT NOT NULL,
    time_horizon TEXT NOT NULL DEFAULT 'intraday_short',
    parameter_advice_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    alerts_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    analysis_json TEXT,
    engine_version TEXT NOT NULL,
    app_version TEXT,
    scoring_version TEXT,
    learning_schema_version TEXT,
    data_source_version TEXT,
    data_contract_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_ticks (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT REFERENCES operations(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contest_seasons (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    starting_balance DOUBLE PRECISION NOT NULL DEFAULT 1000,
    finalized_at TEXT,
    winner_user_id BIGINT,
    winner_username TEXT,
    winner_equity DOUBLE PRECISION,
    winner_pnl DOUBLE PRECISION,
    final_leaderboard_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contest_entries (
    id BIGSERIAL PRIMARY KEY,
    season_id BIGINT NOT NULL REFERENCES contest_seasons(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starting_balance DOUBLE PRECISION NOT NULL DEFAULT 1000,
    cash_balance DOUBLE PRECISION NOT NULL DEFAULT 1000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(season_id, user_id)
);

CREATE TABLE IF NOT EXISTS wallet_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    event_type TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    balance_after DOUBLE PRECISION,
    operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
    contest_season_id BIGINT REFERENCES contest_seasons(id) ON DELETE SET NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_evaluations (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL UNIQUE REFERENCES operations(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recommendation_id BIGINT REFERENCES recommendations(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    time_horizon TEXT NOT NULL,
    mode TEXT NOT NULL,
    close_reason TEXT,
    final_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    plan_result TEXT NOT NULL,
    analysis_verdict TEXT NOT NULL,
    primary_lesson TEXT NOT NULL,
    failure_type TEXT,
    user_decision_quality TEXT,
    max_favorable_pct DOUBLE PRECISION,
    max_adverse_pct DOUBLE PRECISION,
    max_favorable_pnl DOUBLE PRECISION,
    max_adverse_pnl DOUBLE PRECISION,
    time_to_close_minutes DOUBLE PRECISION,
    would_hit_tp_after_manual INTEGER NOT NULL DEFAULT 0,
    would_hit_sl_after_manual INTEGER NOT NULL DEFAULT 0,
    setup_grade TEXT,
    risk_level TEXT,
    confidence TEXT,
    training_decision TEXT,
    tp_probability DOUBLE PRECISION,
    sl_probability DOUBLE PRECISION,
    range_probability DOUBLE PRECISION,
    technical_label TEXT,
    technical_score DOUBLE PRECISION,
    market_regime TEXT,
    direction_score DOUBLE PRECISION,
    confidence_score DOUBLE PRECISION,
    risk_reward_ratio DOUBLE PRECISION,
    risk_margin_pct DOUBLE PRECISION,
    reward_margin_pct DOUBLE PRECISION,
    leverage_bucket TEXT,
    app_version TEXT,
    scoring_version TEXT,
    learning_evaluator_version TEXT,
    learning_schema_version TEXT,
    data_source_version TEXT,
    data_contract_version TEXT,
    evidence_version TEXT,
    evidence_source TEXT,
    evidence_quality TEXT,
    evidence_status TEXT,
    evidence_path_resolution TEXT,
    evidence_start_at TEXT,
    evidence_end_at TEXT,
    evidence_candle_count INTEGER,
    evidence_expected_candles INTEGER,
    evidence_coverage_ratio DOUBLE PRECISION,
    first_plan_touch TEXT,
    first_plan_touch_at TEXT,
    first_post_close_touch TEXT,
    first_post_close_touch_at TEXT,
    reconstructed_plan_result TEXT,
    plan_result_consistency TEXT,
    evidence_reconstructed_at TIMESTAMPTZ,
    evidence_json TEXT,
    structured_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_evidence_reconstructions (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    evaluation_id BIGINT NOT NULL REFERENCES learning_evaluations(id) ON DELETE CASCADE,
    reconstruction_version TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_source TEXT NOT NULL,
    evidence_quality TEXT NOT NULL,
    path_resolution TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation_id, reconstruction_version)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'operations_contest_season_fk'
    ) THEN
        ALTER TABLE operations
            ADD CONSTRAINT operations_contest_season_fk
            FOREIGN KEY (contest_season_id) REFERENCES contest_seasons(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_operations_user_mode_status ON operations(user_id, mode, status);
CREATE INDEX IF NOT EXISTS idx_operations_contest ON operations(contest_season_id, user_id);
CREATE INDEX IF NOT EXISTS idx_price_ticks_operation_time ON price_ticks(operation_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_recommendations_user_operation ON recommendations(user_id, operation_id);
CREATE INDEX IF NOT EXISTS idx_wallet_events_user_mode ON wallet_events(user_id, mode, created_at);
CREATE INDEX IF NOT EXISTS idx_contest_entries_season ON contest_entries(season_id, user_id);
CREATE INDEX IF NOT EXISTS idx_learning_evaluations_user_horizon ON learning_evaluations(user_id, time_horizon, side);
CREATE INDEX IF NOT EXISTS idx_learning_evaluations_pattern ON learning_evaluations(symbol, side, time_horizon, plan_result);
CREATE INDEX IF NOT EXISTS idx_learning_evidence_status ON learning_evidence_reconstructions(status, evidence_quality);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contest_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_ticks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contest_seasons ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.users FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.recommendations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.wallet_events FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.contest_entries FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.learning_evaluations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.price_ticks FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.contest_seasons FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM anon, authenticated;

GRANT USAGE ON SCHEMA public TO postgres, service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres, service_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres, service_role;
