-- Tres participantes autonomos del concurso y evidencia compacta de candidatos.
-- El backend accede mediante la conexion Postgres; estas tablas no se exponen
-- al cliente web ni almacenan velas, profundidad o transacciones sin procesar.

CREATE TABLE IF NOT EXISTS autonomous_contest_participants (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    time_horizon TEXT NOT NULL UNIQUE
        CHECK(time_horizon IN ('intraday_short', 'intraday_wide', 'short_swing')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'paused')),
    policy_version TEXT NOT NULL,
    cadence_minutes INTEGER NOT NULL CHECK(cadence_minutes > 0),
    daily_operation_limit INTEGER NOT NULL CHECK(daily_operation_limit > 0),
    max_open_positions INTEGER NOT NULL CHECK(max_open_positions > 0),
    edge_threshold DOUBLE PRECISION NOT NULL CHECK(edge_threshold BETWEEN -1 AND 1),
    min_tp_probability DOUBLE PRECISION NOT NULL CHECK(min_tp_probability BETWEEN 0 AND 1),
    max_unresolved_probability DOUBLE PRECISION NOT NULL CHECK(max_unresolved_probability BETWEEN 0 AND 1),
    min_analogs_per_stage INTEGER NOT NULL CHECK(min_analogs_per_stage > 0),
    margin DOUBLE PRECISION NOT NULL CHECK(margin > 0),
    leverage DOUBLE PRECISION NOT NULL CHECK(leverage > 0),
    symbols_json JSONB NOT NULL CHECK(jsonb_typeof(symbols_json) = 'array'),
    last_scan_slot_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS autonomous_scan_runs (
    id BIGSERIAL PRIMARY KEY,
    participant_id BIGINT NOT NULL
        REFERENCES autonomous_contest_participants(id) ON DELETE CASCADE,
    contest_season_id BIGINT NOT NULL
        REFERENCES contest_seasons(id) ON DELETE CASCADE,
    scan_slot_at TIMESTAMPTZ NOT NULL,
    analyzed_at TIMESTAMPTZ,
    status TEXT NOT NULL
        CHECK(status IN (
            'running', 'no_trade', 'would_open', 'opened',
            'failed', 'no_cash', 'quota_reached', 'capacity_reached'
        )),
    reason_code TEXT,
    candidates_evaluated INTEGER NOT NULL DEFAULT 0,
    candidates_blocked INTEGER NOT NULL DEFAULT 0,
    candidates_eligible INTEGER NOT NULL DEFAULT 0,
    selected_symbol TEXT,
    selected_side TEXT CHECK(selected_side IS NULL OR selected_side IN ('long', 'short')),
    selected_tp_probability DOUBLE PRECISION,
    selected_sl_probability DOUBLE PRECISION,
    selected_unresolved_probability DOUBLE PRECISION,
    selected_edge DOUBLE PRECISION,
    recommendation_id BIGINT REFERENCES recommendations(id) ON DELETE SET NULL,
    operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
    engine_version TEXT NOT NULL,
    artifact_id TEXT,
    policy_version TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(participant_id, scan_slot_at)
);

CREATE TABLE IF NOT EXISTS autonomous_candidate_observations (
    id BIGSERIAL PRIMARY KEY,
    scan_run_id BIGINT NOT NULL
        REFERENCES autonomous_scan_runs(id) ON DELETE CASCADE,
    participant_id BIGINT NOT NULL
        REFERENCES autonomous_contest_participants(id) ON DELETE CASCADE,
    contest_season_id BIGINT NOT NULL
        REFERENCES contest_seasons(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    time_horizon TEXT NOT NULL,
    analyzed_at TIMESTAMPTZ NOT NULL,
    evaluation_due_at TIMESTAMPTZ NOT NULL,
    entry DOUBLE PRECISION,
    take_profit DOUBLE PRECISION,
    stop_loss DOUBLE PRECISION,
    context_sigma DOUBLE PRECISION,
    tp_probability DOUBLE PRECISION,
    sl_probability DOUBLE PRECISION,
    unresolved_probability DOUBLE PRECISION,
    edge DOUBLE PRECISION,
    selected_analogs_min INTEGER,
    max_context_distance_ratio DOUBLE PRECISION,
    analysis_status TEXT NOT NULL CHECK(analysis_status IN ('evaluated', 'blocked', 'failed')),
    rejection_code TEXT,
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    storage_reason TEXT NOT NULL CHECK(storage_reason IN ('panel', 'selected', 'boundary')),
    observational_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_version TEXT NOT NULL,
    artifact_id TEXT,
    outcome_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(outcome_status IN ('pending', 'evaluated', 'excluded')),
    first_touch TEXT CHECK(first_touch IS NULL OR first_touch IN ('tp', 'sl', 'ambiguous', 'unresolved')),
    first_touch_at TIMESTAMPTZ,
    terminal_price DOUBLE PRECISION,
    r_multiple DOUBLE PRECISION,
    evaluated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(scan_run_id, symbol, side)
);

CREATE INDEX IF NOT EXISTS idx_autonomous_participant_status
    ON autonomous_contest_participants(status, time_horizon);
CREATE INDEX IF NOT EXISTS idx_autonomous_scan_due
    ON autonomous_scan_runs(participant_id, scan_slot_at DESC);
CREATE INDEX IF NOT EXISTS idx_autonomous_scan_season
    ON autonomous_scan_runs(contest_season_id, status, scan_slot_at DESC);
CREATE INDEX IF NOT EXISTS idx_autonomous_candidate_due
    ON autonomous_candidate_observations(outcome_status, evaluation_due_at)
    WHERE outcome_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_autonomous_candidate_learning
    ON autonomous_candidate_observations(
        time_horizon, symbol, side, outcome_status, analyzed_at
    );

ALTER TABLE autonomous_contest_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE autonomous_scan_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE autonomous_candidate_observations ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE autonomous_contest_participants FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE autonomous_scan_runs FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE autonomous_candidate_observations FROM anon, authenticated;
