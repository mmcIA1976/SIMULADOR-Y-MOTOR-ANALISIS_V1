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
    economic_normalization_version TEXT,
    economic_normalization_status TEXT,
    economic_exclusion_reason TEXT,
    economic_normalized_at TIMESTAMPTZ,
    closure_type TEXT,
    notional_amount DOUBLE PRECISION,
    initial_risk_pct DOUBLE PRECISION,
    initial_risk_amount DOUBLE PRECISION,
    unleveraged_return_pct DOUBLE PRECISION,
    margin_return_pct DOUBLE PRECISION,
    r_multiple DOUBLE PRECISION,
    economic_plan_outcome TEXT,
    economic_final_pnl DOUBLE PRECISION,
    economic_metrics_json TEXT,
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

CREATE TABLE IF NOT EXISTS learning_economic_normalizations (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    evaluation_id BIGINT NOT NULL REFERENCES learning_evaluations(id) ON DELETE CASCADE,
    normalization_version TEXT NOT NULL,
    status TEXT NOT NULL,
    exclusion_reason TEXT,
    before_json TEXT,
    after_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation_id, normalization_version)
);

CREATE TABLE IF NOT EXISTS learning_legacy_reevaluations (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    evaluation_id BIGINT NOT NULL REFERENCES learning_evaluations(id) ON DELETE CASCADE,
    reevaluation_version TEXT NOT NULL,
    review_schema_version TEXT NOT NULL,
    review_status TEXT NOT NULL,
    source_engine_version TEXT,
    source_learning_schema_version TEXT,
    source_data_contract_version TEXT,
    source_evaluation_created_at TIMESTAMPTZ,
    source_evaluation_updated_at TIMESTAMPTZ,
    source_bundle_sha256 TEXT NOT NULL,
    original_interpretation_json TEXT NOT NULL,
    reevaluated_contract_json TEXT NOT NULL,
    missing_fields_json TEXT NOT NULL,
    predictive_eligibility_json TEXT NOT NULL,
    outcome_class TEXT NOT NULL,
    outcome_status TEXT NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation_id, reevaluation_version)
);

CREATE TABLE IF NOT EXISTS challenger_model_artifacts (
    id BIGSERIAL PRIMARY KEY,
    model_version TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    deployment_state TEXT NOT NULL CHECK(deployment_state = 'shadow'),
    artifact_sha256 TEXT NOT NULL UNIQUE,
    artifact_json TEXT NOT NULL,
    registration_reason TEXT NOT NULL,
    registered_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS challenger_shadow_config_events (
    id BIGSERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    selected_model_version TEXT REFERENCES challenger_model_artifacts(model_version) ON DELETE RESTRICT,
    previous_event_id BIGINT REFERENCES challenger_shadow_config_events(id) ON DELETE RESTRICT,
    previous_model_version TEXT,
    rollback_target_event_id BIGINT REFERENCES challenger_shadow_config_events(id) ON DELETE RESTRICT,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    app_version TEXT NOT NULL,
    code_commit_sha TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS challenger_shadow_runs (
    id BIGSERIAL PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    recommendation_id BIGINT NOT NULL REFERENCES recommendations(id) ON DELETE RESTRICT,
    config_event_id BIGINT REFERENCES challenger_shadow_config_events(id) ON DELETE RESTRICT,
    run_origin TEXT NOT NULL CHECK(run_origin IN ('live_analysis', 'offline_replay')),
    champion_engine_version TEXT NOT NULL,
    champion_scoring_version TEXT NOT NULL,
    champion_result_json TEXT NOT NULL,
    challenger_version TEXT NOT NULL,
    model_version TEXT REFERENCES challenger_model_artifacts(model_version) ON DELETE RESTRICT,
    challenger_status TEXT NOT NULL CHECK(challenger_status IN ('blocked', 'shadow_prediction')),
    block_code TEXT,
    challenger_result_json TEXT NOT NULL,
    comparison_json TEXT NOT NULL,
    plan_contract_json TEXT NOT NULL,
    feature_snapshot_json TEXT NOT NULL,
    source_snapshot_sha256 TEXT NOT NULL,
    admission_matrix_sha256 TEXT NOT NULL,
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    app_version TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_learning_evaluations_user_horizon ON learning_evaluations(user_id, time_horizon, side);
CREATE INDEX IF NOT EXISTS idx_learning_evaluations_pattern ON learning_evaluations(symbol, side, time_horizon, plan_result);
CREATE INDEX IF NOT EXISTS idx_learning_evidence_status ON learning_evidence_reconstructions(status, evidence_quality);
CREATE INDEX IF NOT EXISTS idx_learning_evidence_evaluation ON learning_evidence_reconstructions(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_learning_economic_status ON learning_economic_normalizations(status, exclusion_reason);
CREATE INDEX IF NOT EXISTS idx_learning_economic_evaluation ON learning_economic_normalizations(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_learning_evaluations_economics ON learning_evaluations(economic_normalization_status, closure_type);
CREATE INDEX IF NOT EXISTS idx_learning_legacy_review_status ON learning_legacy_reevaluations(review_status, outcome_class);
CREATE INDEX IF NOT EXISTS idx_learning_legacy_review_evaluation ON learning_legacy_reevaluations(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_challenger_artifacts_state ON challenger_model_artifacts(deployment_state, created_at);
CREATE INDEX IF NOT EXISTS idx_challenger_config_selected_model ON challenger_shadow_config_events(selected_model_version);
CREATE INDEX IF NOT EXISTS idx_challenger_config_previous_event ON challenger_shadow_config_events(previous_event_id);
CREATE INDEX IF NOT EXISTS idx_challenger_config_rollback_target ON challenger_shadow_config_events(rollback_target_event_id);
CREATE INDEX IF NOT EXISTS idx_challenger_shadow_recommendation ON challenger_shadow_runs(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_challenger_shadow_config ON challenger_shadow_runs(config_event_id);
CREATE INDEX IF NOT EXISTS idx_challenger_shadow_model ON challenger_shadow_runs(model_version);
CREATE INDEX IF NOT EXISTS idx_challenger_shadow_status ON challenger_shadow_runs(challenger_status, block_code, created_at);

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.wallet_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contest_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_ticks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contest_seasons ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_evidence_reconstructions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_economic_normalizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.learning_legacy_reevaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.challenger_model_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.challenger_shadow_config_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.challenger_shadow_runs ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE public.users FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.recommendations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.wallet_events FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.contest_entries FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.learning_evaluations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.price_ticks FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.contest_seasons FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.learning_evidence_reconstructions FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.learning_economic_normalizations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.learning_legacy_reevaluations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.challenger_model_artifacts FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.challenger_shadow_config_events FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.challenger_shadow_runs FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM anon, authenticated;

GRANT USAGE ON SCHEMA public TO postgres, service_role;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres, service_role;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres, service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.learning_legacy_reevaluations FROM service_role;
GRANT SELECT, INSERT
    ON TABLE public.learning_legacy_reevaluations TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.learning_legacy_reevaluations_id_seq TO service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.challenger_model_artifacts FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.challenger_shadow_config_events FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.challenger_shadow_runs FROM service_role;
GRANT SELECT, INSERT
    ON TABLE public.challenger_model_artifacts TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.challenger_shadow_config_events TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.challenger_shadow_runs TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.challenger_model_artifacts_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.challenger_shadow_config_events_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.challenger_shadow_runs_id_seq TO service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'learning_legacy_reevaluations'
          AND rulename = 'learning_legacy_reevaluations_no_update'
    ) THEN
        CREATE RULE learning_legacy_reevaluations_no_update AS
        ON UPDATE TO public.learning_legacy_reevaluations
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'learning_legacy_reevaluations'
          AND rulename = 'learning_legacy_reevaluations_no_delete'
    ) THEN
        CREATE RULE learning_legacy_reevaluations_no_delete AS
        ON DELETE TO public.learning_legacy_reevaluations
        DO INSTEAD NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'challenger_model_artifacts'
          AND rulename = 'challenger_model_artifacts_no_update'
    ) THEN
        CREATE RULE challenger_model_artifacts_no_update AS
        ON UPDATE TO public.challenger_model_artifacts
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'challenger_model_artifacts'
          AND rulename = 'challenger_model_artifacts_no_delete'
    ) THEN
        CREATE RULE challenger_model_artifacts_no_delete AS
        ON DELETE TO public.challenger_model_artifacts
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'challenger_shadow_config_events'
          AND rulename = 'challenger_shadow_config_events_no_update'
    ) THEN
        CREATE RULE challenger_shadow_config_events_no_update AS
        ON UPDATE TO public.challenger_shadow_config_events
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'challenger_shadow_config_events'
          AND rulename = 'challenger_shadow_config_events_no_delete'
    ) THEN
        CREATE RULE challenger_shadow_config_events_no_delete AS
        ON DELETE TO public.challenger_shadow_config_events
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'challenger_shadow_runs'
          AND rulename = 'challenger_shadow_runs_no_update'
    ) THEN
        CREATE RULE challenger_shadow_runs_no_update AS
        ON UPDATE TO public.challenger_shadow_runs
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'challenger_shadow_runs'
          AND rulename = 'challenger_shadow_runs_no_delete'
    ) THEN
        CREATE RULE challenger_shadow_runs_no_delete AS
        ON DELETE TO public.challenger_shadow_runs
        DO INSTEAD NOTHING;
    END IF;
END $$;

INSERT INTO public.challenger_shadow_config_events (
    action, enabled, selected_model_version, previous_event_id,
    previous_model_version, rollback_target_event_id, reason,
    requested_by, app_version, code_commit_sha
)
SELECT
    'initialize_disabled', FALSE, NULL, NULL, NULL, NULL,
    'Fase 6: estado seguro inicial sin artefacto aprobado',
    'system_migration', 'app-v0.17.0-challenger-shadow', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM public.challenger_shadow_config_events
);
