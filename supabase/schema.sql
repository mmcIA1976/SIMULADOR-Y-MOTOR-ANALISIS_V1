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

CREATE TABLE IF NOT EXISTS m6_prospective_runs (
    id BIGSERIAL PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    recommendation_id BIGINT NOT NULL REFERENCES recommendations(id) ON DELETE RESTRICT,
    runtime_version TEXT NOT NULL,
    m5_engine_version TEXT NOT NULL,
    m6_engine_version TEXT NOT NULL,
    run_status TEXT NOT NULL CHECK(run_status IN ('evaluated', 'blocked')),
    block_code TEXT,
    analysis_at TIMESTAMPTZ NOT NULL,
    data_cutoff_at TIMESTAMPTZ,
    evaluation_expires_at TIMESTAMPTZ NOT NULL,
    horizon_seconds INTEGER NOT NULL,
    plan_contract_json TEXT NOT NULL,
    feature_snapshot_json TEXT NOT NULL,
    m5_trace_json TEXT NOT NULL,
    probability_result_json TEXT NOT NULL,
    source_data_sha256 TEXT NOT NULL,
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    app_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recommendation_counterfactual_evaluations (
    id BIGSERIAL PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE,
    recommendation_id BIGINT NOT NULL
        REFERENCES recommendations(id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    evaluator_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    contract_quality TEXT NOT NULL DEFAULT 'exact'
        CHECK(contract_quality IN ('exact', 'legacy_upper_bound_proxy')),
    formal_learning_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    analysis_at_source TEXT NOT NULL DEFAULT 'snapshot.analysis_at',
    data_cutoff_source TEXT NOT NULL DEFAULT 'snapshot.data_cutoff_at',
    plan_source TEXT NOT NULL DEFAULT 'snapshot.explicit_levels',
    horizon_source TEXT NOT NULL
        DEFAULT 'snapshot.evaluation_horizon_seconds',
    source_engine_version TEXT NOT NULL,
    source_scoring_version TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    time_horizon TEXT NOT NULL,
    analysis_at TIMESTAMPTZ NOT NULL,
    data_cutoff_at TIMESTAMPTZ NOT NULL,
    evaluation_expires_at TIMESTAMPTZ NOT NULL,
    horizon_seconds INTEGER NOT NULL CHECK(horizon_seconds > 0),
    entry DOUBLE PRECISION NOT NULL CHECK(entry > 0),
    take_profit DOUBLE PRECISION NOT NULL CHECK(take_profit > 0),
    stop_loss DOUBLE PRECISION NOT NULL CHECK(stop_loss > 0),
    tp_probability DOUBLE PRECISION NOT NULL
        CHECK(tp_probability BETWEEN 0 AND 1),
    sl_probability DOUBLE PRECISION NOT NULL
        CHECK(sl_probability BETWEEN 0 AND 1),
    range_probability DOUBLE PRECISION NOT NULL
        CHECK(range_probability BETWEEN 0 AND 1),
    evaluation_status TEXT NOT NULL
        CHECK(evaluation_status IN ('evaluated', 'excluded')),
    exclusion_code TEXT,
    pretrade_status TEXT NOT NULL,
    pretrade_interval TEXT,
    feature_values_json TEXT NOT NULL
        CHECK(jsonb_typeof(feature_values_json::jsonb) = 'object'),
    feature_payload_bytes INTEGER NOT NULL
        CHECK(feature_payload_bytes > 0 AND feature_payload_bytes <= 4096),
    outcome_status TEXT NOT NULL,
    outcome_label TEXT CHECK(
        outcome_label IS NULL OR outcome_label IN (
            'tp_first_within_horizon',
            'sl_first_within_horizon',
            'neither_barrier_before_expiry'
        )
    ),
    first_touch_at TIMESTAMPTZ,
    coverage_ratio DOUBLE PRECISION,
    candle_count INTEGER,
    expected_candle_count INTEGER,
    market_sha256 TEXT,
    source_snapshot_sha256 TEXT NOT NULL
        CHECK(source_snapshot_sha256 ~ '^[0-9a-f]{64}$'),
    result_sha256 TEXT NOT NULL CHECK(result_sha256 ~ '^[0-9a-f]{64}$'),
    evidence_source TEXT NOT NULL,
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(recommendation_id, evaluator_version),
    CHECK(
        feature_payload_bytes = octet_length(
            convert_to(feature_values_json, 'UTF8')
        )
    ),
    CONSTRAINT counterfactual_probability_mass_valid CHECK(
        abs(tp_probability + sl_probability + range_probability - 1.0)
        <= 0.0000011
    ),
    CONSTRAINT counterfactual_contract_quality_valid CHECK(
        (contract_quality = 'exact' AND formal_learning_eligible = TRUE)
        OR
        (contract_quality = 'legacy_upper_bound_proxy'
            AND formal_learning_eligible = FALSE)
    ),
    CONSTRAINT counterfactual_data_cutoff_valid CHECK(
        data_cutoff_at <= analysis_at
    ),
    CONSTRAINT counterfactual_expiry_valid CHECK(
        evaluation_expires_at = analysis_at
            + make_interval(secs => horizon_seconds)
    ),
    CHECK(
        (evaluation_status = 'evaluated'
            AND exclusion_code IS NULL
            AND outcome_label IS NOT NULL)
        OR
        (evaluation_status = 'excluded'
            AND exclusion_code IS NOT NULL
            AND outcome_label IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS counterfactual_episode_grouping_runs (
    id BIGSERIAL PRIMARY KEY,
    run_key TEXT NOT NULL UNIQUE CHECK(run_key ~ '^[0-9a-f]{64}$'),
    grouping_version TEXT NOT NULL,
    source_dataset_sha256 TEXT NOT NULL
        CHECK(source_dataset_sha256 ~ '^[0-9a-f]{64}$'),
    source_row_count INTEGER NOT NULL CHECK(source_row_count > 0),
    evaluated_row_count INTEGER NOT NULL
        CHECK(evaluated_row_count BETWEEN 0 AND source_row_count),
    formal_evaluated_row_count INTEGER NOT NULL CHECK(
        formal_evaluated_row_count BETWEEN 0 AND evaluated_row_count
    ),
    market_episode_count INTEGER NOT NULL CHECK(market_episode_count > 0),
    horizon_episode_count INTEGER NOT NULL CHECK(horizon_episode_count > 0),
    calendar_block_count INTEGER NOT NULL CHECK(calendar_block_count > 0),
    summary_json TEXT NOT NULL
        CHECK(jsonb_typeof(summary_json::jsonb) = 'object'),
    summary_bytes INTEGER NOT NULL CHECK(
        summary_bytes > 0 AND summary_bytes <= 16384
        AND summary_bytes = octet_length(convert_to(summary_json, 'UTF8'))
    ),
    result_sha256 TEXT NOT NULL CHECK(result_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS counterfactual_episode_memberships (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES counterfactual_episode_grouping_runs(id)
        ON DELETE RESTRICT,
    evaluation_id BIGINT NOT NULL
        REFERENCES recommendation_counterfactual_evaluations(id)
        ON DELETE RESTRICT,
    symbol TEXT NOT NULL,
    time_horizon TEXT NOT NULL,
    contract_quality TEXT NOT NULL
        CHECK(contract_quality IN ('exact', 'legacy_upper_bound_proxy')),
    evaluation_status TEXT NOT NULL
        CHECK(evaluation_status IN ('evaluated', 'excluded')),
    formal_learning_eligible BOOLEAN NOT NULL,
    eligible_for_metrics BOOLEAN NOT NULL,
    formal_metric_eligible BOOLEAN NOT NULL,
    calendar_block_utc DATE NOT NULL,
    market_episode_key TEXT NOT NULL
        CHECK(market_episode_key ~ '^[0-9a-f]{64}$'),
    horizon_episode_key TEXT NOT NULL
        CHECK(horizon_episode_key ~ '^[0-9a-f]{64}$'),
    formal_market_episode_key TEXT CHECK(
        formal_market_episode_key IS NULL
        OR formal_market_episode_key ~ '^[0-9a-f]{64}$'
    ),
    formal_horizon_episode_key TEXT CHECK(
        formal_horizon_episode_key IS NULL
        OR formal_horizon_episode_key ~ '^[0-9a-f]{64}$'
    ),
    market_episode_size INTEGER NOT NULL CHECK(market_episode_size > 0),
    market_episode_evaluated_size INTEGER NOT NULL CHECK(
        market_episode_evaluated_size BETWEEN 0 AND market_episode_size
    ),
    market_episode_formal_size INTEGER NOT NULL CHECK(
        market_episode_formal_size BETWEEN 0
            AND market_episode_evaluated_size
    ),
    horizon_episode_size INTEGER NOT NULL CHECK(horizon_episode_size > 0),
    horizon_episode_evaluated_size INTEGER NOT NULL CHECK(
        horizon_episode_evaluated_size BETWEEN 0 AND horizon_episode_size
    ),
    horizon_episode_formal_size INTEGER NOT NULL CHECK(
        horizon_episode_formal_size BETWEEN 0
            AND horizon_episode_evaluated_size
    ),
    market_weight DOUBLE PRECISION NOT NULL
        CHECK(market_weight BETWEEN 0 AND 1),
    horizon_weight DOUBLE PRECISION NOT NULL
        CHECK(horizon_weight BETWEEN 0 AND 1),
    formal_market_weight DOUBLE PRECISION NOT NULL
        CHECK(formal_market_weight BETWEEN 0 AND 1),
    formal_horizon_weight DOUBLE PRECISION NOT NULL
        CHECK(formal_horizon_weight BETWEEN 0 AND 1),
    membership_sha256 TEXT NOT NULL
        CHECK(membership_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, evaluation_id),
    CHECK(formal_learning_eligible = (contract_quality = 'exact')),
    CHECK(eligible_for_metrics = (evaluation_status = 'evaluated')),
    CHECK(
        formal_metric_eligible = (
            eligible_for_metrics AND formal_learning_eligible
        )
    ),
    CHECK(
        (formal_metric_eligible
            AND formal_market_episode_key IS NOT NULL
            AND formal_horizon_episode_key IS NOT NULL)
        OR
        (NOT formal_metric_eligible
            AND formal_market_episode_key IS NULL
            AND formal_horizon_episode_key IS NULL)
    ),
    CHECK(
        (eligible_for_metrics AND market_weight > 0 AND horizon_weight > 0)
        OR
        (NOT eligible_for_metrics
            AND market_weight = 0 AND horizon_weight = 0)
    ),
    CHECK(
        (formal_metric_eligible
            AND formal_market_weight > 0 AND formal_horizon_weight > 0)
        OR
        (NOT formal_metric_eligible
            AND formal_market_weight = 0 AND formal_horizon_weight = 0)
    )
);

CREATE TABLE IF NOT EXISTS operation_observation_sessions (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL UNIQUE
        REFERENCES operations(id) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opening_recommendation_id BIGINT
        REFERENCES recommendations(id) ON DELETE RESTRICT,
    session_code TEXT NOT NULL UNIQUE CHECK(session_code ~ '^[0-9]+o$'),
    status TEXT NOT NULL CHECK(status IN ('active', 'paused', 'completed', 'cancelled')),
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
    paused_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    evidence_source TEXT NOT NULL,
    evidence_quality TEXT NOT NULL
        CHECK(evidence_quality IN ('exact', 'reconstructed_partial')),
    summary_json TEXT NOT NULL CHECK(jsonb_typeof(summary_json::jsonb) = 'object'),
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
        (status IN ('active', 'paused') AND ended_at IS NULL)
        OR (status IN ('completed', 'cancelled') AND ended_at IS NOT NULL)
    ),
    CHECK(
        (status = 'paused' AND paused_at IS NOT NULL)
        OR status <> 'paused'
    ),
    CHECK(
        (capture_mode = 'live' AND evidence_quality = 'exact')
        OR (capture_mode = 'reconstructed'
            AND evidence_quality = 'reconstructed_partial')
    )
);

CREATE TABLE IF NOT EXISTS operation_observation_session_events (
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
    details_json TEXT NOT NULL CHECK(jsonb_typeof(details_json::jsonb) = 'object'),
    details_bytes INTEGER NOT NULL CHECK(
        details_bytes > 0 AND details_bytes <= 4096
        AND details_bytes = octet_length(convert_to(details_json, 'UTF8'))
    ),
    details_sha256 TEXT NOT NULL CHECK(details_sha256 ~ '^[0-9a-f]{64}$'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id, operation_id)
        REFERENCES operation_observation_sessions(id, operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS operation_observation_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    operation_id BIGINT NOT NULL,
    recommendation_id BIGINT UNIQUE
        REFERENCES recommendations(id) ON DELETE RESTRICT,
    checkpoint_number INTEGER NOT NULL CHECK(checkpoint_number > 0),
    checkpoint_code TEXT NOT NULL UNIQUE CHECK(checkpoint_code ~ '^[0-9]+o[0-9]+$'),
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
    context_json TEXT NOT NULL CHECK(jsonb_typeof(context_json::jsonb) = 'object'),
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
        REFERENCES operation_observation_sessions(id, operation_id)
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

CREATE TABLE IF NOT EXISTS operation_exit_counterfactuals (
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
        REFERENCES operation_observation_checkpoints(id, operation_id)
        ON DELETE RESTRICT,
    CHECK(formal_learning_eligible = (contract_quality = 'exact'))
);

CREATE TABLE IF NOT EXISTS limit_learning_snapshots (
    id BIGSERIAL PRIMARY KEY,
    operation_id BIGINT NOT NULL REFERENCES operations(id) ON DELETE RESTRICT,
    recommendation_id BIGINT REFERENCES recommendations(id) ON DELETE RESTRICT,
    analysis_id TEXT NOT NULL,
    snapshot_type TEXT NOT NULL
        CHECK(snapshot_type IN ('placement', 'activation', 'closure')),
    snapshot_schema_version TEXT NOT NULL
        CHECK(snapshot_schema_version = 'limit-learning-snapshot-v0.1'),
    event_at TIMESTAMPTZ NOT NULL,
    selected_case_day DATE,
    daily_slot SMALLINT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
    time_horizon TEXT NOT NULL,
    learning_label TEXT,
    payload_sha256 TEXT NOT NULL CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
    payload_bytes INTEGER NOT NULL,
    payload_json TEXT NOT NULL
        CHECK(jsonb_typeof(payload_json::jsonb) = 'object'),
    production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(operation_id, snapshot_type),
    CHECK(payload_bytes = octet_length(convert_to(payload_json, 'UTF8'))),
    CHECK(
        payload_bytes > 0 AND payload_bytes <= CASE snapshot_type
            WHEN 'placement' THEN 3584
            WHEN 'activation' THEN 1280
            WHEN 'closure' THEN 1024
        END
    ),
    CHECK(
        (
            snapshot_type = 'placement'
            AND selected_case_day IS NOT NULL
            AND daily_slot IS NOT NULL
            AND selected_case_day = (event_at AT TIME ZONE 'UTC')::date
            AND daily_slot BETWEEN 1 AND 50
        ) OR (
            snapshot_type <> 'placement'
            AND selected_case_day IS NULL
            AND daily_slot IS NULL
        )
    ),
    CHECK(
        (snapshot_type = 'closure' AND learning_label IS NOT NULL)
        OR (snapshot_type <> 'closure' AND learning_label IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS operation_worker_state (
    worker_name TEXT PRIMARY KEY,
    lifecycle_status TEXT NOT NULL
        CHECK(lifecycle_status IN ('starting', 'running', 'degraded', 'stopped')),
    app_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    persist_exit_window BOOLEAN NOT NULL DEFAULT FALSE,
    poll_seconds DOUBLE PRECISION NOT NULL,
    reconcile_seconds DOUBLE PRECISION NOT NULL,
    heartbeat_seconds DOUBLE PRECISION NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    last_heartbeat_at TIMESTAMPTZ NOT NULL,
    last_cycle_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_reconcile_at TIMESTAMPTZ,
    cycle_count BIGINT NOT NULL DEFAULT 0,
    active_symbols INTEGER NOT NULL DEFAULT 0,
    market_symbols INTEGER NOT NULL DEFAULT 0,
    last_cycle_activated INTEGER NOT NULL DEFAULT 0,
    last_cycle_closed INTEGER NOT NULL DEFAULT 0,
    last_cycle_finalized INTEGER NOT NULL DEFAULT 0,
    last_cycle_failures INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_price_state (
    symbol TEXT PRIMARY KEY CHECK(symbol ~ '^[A-Z0-9]{5,20}$'),
    price DOUBLE PRECISION CHECK(price IS NULL OR price > 0),
    source TEXT,
    publisher TEXT NOT NULL DEFAULT 'operation_worker'
        CHECK(publisher = 'operation_worker'),
    captured_at TIMESTAMPTZ,
    watch_until TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK(
        (price IS NULL AND captured_at IS NULL AND source IS NULL)
        OR
        (price IS NOT NULL AND captured_at IS NOT NULL AND source IS NOT NULL)
    )
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
CREATE INDEX IF NOT EXISTS idx_m6_prospective_recommendation ON m6_prospective_runs(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_m6_prospective_status ON m6_prospective_runs(run_status, block_code, created_at);
CREATE INDEX IF NOT EXISTS idx_m6_prospective_expiry ON m6_prospective_runs(evaluation_expires_at, run_status);
CREATE INDEX IF NOT EXISTS idx_counterfactual_learning_slice ON recommendation_counterfactual_evaluations(evaluation_status, time_horizon, side, analysis_at);
CREATE INDEX IF NOT EXISTS idx_counterfactual_engine ON recommendation_counterfactual_evaluations(source_engine_version, evaluation_status);
CREATE INDEX IF NOT EXISTS idx_counterfactual_user ON recommendation_counterfactual_evaluations(user_id);
CREATE INDEX IF NOT EXISTS idx_counterfactual_episode_evaluation ON counterfactual_episode_memberships(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_counterfactual_episode_market ON counterfactual_episode_memberships(run_id, market_episode_key);
CREATE INDEX IF NOT EXISTS idx_counterfactual_episode_horizon ON counterfactual_episode_memberships(run_id, formal_metric_eligible, time_horizon, formal_horizon_episode_key);
CREATE INDEX IF NOT EXISTS idx_observation_sessions_user_status ON operation_observation_sessions(user_id, status, started_at);
CREATE INDEX IF NOT EXISTS idx_observation_session_events_timeline ON operation_observation_session_events(operation_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_observation_session_events_session ON operation_observation_session_events(session_id, operation_id);
CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_episode_time ON operation_observation_checkpoints(operation_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_learning ON operation_observation_checkpoints(formal_learning_eligible, contract_quality, observed_at);
CREATE INDEX IF NOT EXISTS idx_exit_counterfactual_operation ON operation_exit_counterfactuals(operation_id, evaluated_at);
CREATE INDEX IF NOT EXISTS idx_limit_learning_study ON limit_learning_snapshots(snapshot_type, symbol, side, time_horizon, event_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_limit_learning_daily_slot ON limit_learning_snapshots(selected_case_day, daily_slot) WHERE snapshot_type = 'placement';
CREATE INDEX IF NOT EXISTS idx_limit_learning_recommendation ON limit_learning_snapshots(recommendation_id) WHERE recommendation_id IS NOT NULL;

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
ALTER TABLE public.m6_prospective_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recommendation_counterfactual_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.counterfactual_episode_grouping_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.counterfactual_episode_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_observation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_observation_session_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_observation_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_exit_counterfactuals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.limit_learning_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operation_worker_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_price_state ENABLE ROW LEVEL SECURITY;

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
REVOKE ALL PRIVILEGES ON TABLE public.m6_prospective_runs FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.recommendation_counterfactual_evaluations FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.counterfactual_episode_grouping_runs FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.counterfactual_episode_memberships FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_observation_sessions FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_observation_session_events FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_observation_checkpoints FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_exit_counterfactuals FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.limit_learning_snapshots FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.operation_worker_state FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.market_price_state FROM anon, authenticated;
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
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.m6_prospective_runs FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.recommendation_counterfactual_evaluations FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.counterfactual_episode_grouping_runs FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.counterfactual_episode_memberships FROM service_role;
REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_observation_sessions FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_observation_session_events FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_observation_checkpoints FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.operation_exit_counterfactuals FROM service_role;
REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.limit_learning_snapshots FROM service_role;
GRANT SELECT, INSERT
    ON TABLE public.challenger_model_artifacts TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.challenger_shadow_config_events TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.challenger_shadow_runs TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.m6_prospective_runs TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.recommendation_counterfactual_evaluations TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.counterfactual_episode_grouping_runs TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.counterfactual_episode_memberships TO service_role;
GRANT SELECT, INSERT, UPDATE
    ON TABLE public.operation_observation_sessions TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.operation_observation_session_events TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.operation_observation_checkpoints TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.operation_exit_counterfactuals TO service_role;
GRANT SELECT, INSERT
    ON TABLE public.limit_learning_snapshots TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.challenger_model_artifacts_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.challenger_shadow_config_events_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.challenger_shadow_runs_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.m6_prospective_runs_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.recommendation_counterfactual_evaluations_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.counterfactual_episode_grouping_runs_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.counterfactual_episode_memberships_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.operation_observation_sessions_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.operation_observation_session_events_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.operation_observation_checkpoints_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.operation_exit_counterfactuals_id_seq TO service_role;
GRANT USAGE, SELECT
    ON SEQUENCE public.limit_learning_snapshots_id_seq TO service_role;

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

DROP RULE IF EXISTS recommendation_counterfactual_evaluations_no_update
    ON public.recommendation_counterfactual_evaluations;
DROP RULE IF EXISTS recommendation_counterfactual_evaluations_no_delete
    ON public.recommendation_counterfactual_evaluations;

CREATE OR REPLACE FUNCTION public.prevent_counterfactual_evaluation_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RETURN NULL;
END;
$$;

REVOKE ALL
    ON FUNCTION public.prevent_counterfactual_evaluation_mutation()
    FROM PUBLIC, anon, authenticated, service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid =
            'public.recommendation_counterfactual_evaluations'::regclass
          AND tgname =
            'recommendation_counterfactual_evaluations_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER recommendation_counterfactual_evaluations_append_only
        BEFORE UPDATE OR DELETE
        ON public.recommendation_counterfactual_evaluations
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_counterfactual_evaluation_mutation();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.prevent_counterfactual_episode_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RETURN NULL;
END;
$$;

REVOKE ALL
    ON FUNCTION public.prevent_counterfactual_episode_mutation()
    FROM PUBLIC, anon, authenticated, service_role;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid =
            'public.counterfactual_episode_grouping_runs'::regclass
          AND tgname = 'counterfactual_episode_grouping_runs_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER counterfactual_episode_grouping_runs_append_only
        BEFORE UPDATE OR DELETE
        ON public.counterfactual_episode_grouping_runs
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_counterfactual_episode_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid =
            'public.counterfactual_episode_memberships'::regclass
          AND tgname = 'counterfactual_episode_memberships_append_only'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER counterfactual_episode_memberships_append_only
        BEFORE UPDATE OR DELETE
        ON public.counterfactual_episode_memberships
        FOR EACH ROW
        EXECUTE FUNCTION public.prevent_counterfactual_episode_mutation();
    END IF;
END $$;

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
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid =
            'public.operation_observation_checkpoints'::regclass
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
        SELECT 1
        FROM pg_trigger
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

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'm6_prospective_runs'
          AND rulename = 'm6_prospective_runs_no_update'
    ) THEN
        CREATE RULE m6_prospective_runs_no_update AS
        ON UPDATE TO public.m6_prospective_runs
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'm6_prospective_runs'
          AND rulename = 'm6_prospective_runs_no_delete'
    ) THEN
        CREATE RULE m6_prospective_runs_no_delete AS
        ON DELETE TO public.m6_prospective_runs
        DO INSTEAD NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'limit_learning_snapshots'
          AND rulename = 'limit_learning_snapshots_no_update'
    ) THEN
        CREATE RULE limit_learning_snapshots_no_update AS
        ON UPDATE TO public.limit_learning_snapshots
        DO INSTEAD NOTHING;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_rules
        WHERE schemaname = 'public'
          AND tablename = 'limit_learning_snapshots'
          AND rulename = 'limit_learning_snapshots_no_delete'
    ) THEN
        CREATE RULE limit_learning_snapshots_no_delete AS
        ON DELETE TO public.limit_learning_snapshots
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

-- Compact baseline for observational-rule learning.  Historical raw payloads
-- are not copied: only formula-compatible signals, outcomes and episode weight.
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
