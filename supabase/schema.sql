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
