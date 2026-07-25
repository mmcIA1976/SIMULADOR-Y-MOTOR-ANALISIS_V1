-- E1.4 read-only export contract.
-- Replace :limit and :offset in the audit runner. This query never writes.
WITH source AS (
    SELECT
        id,
        symbol,
        side,
        time_horizon,
        engine_version,
        scoring_version,
        tp_probability,
        sl_probability,
        range_probability,
        risk_level,
        setup_grade,
        confidence,
        training_decision,
        snapshot_json::jsonb AS snapshot,
        analysis_json::jsonb AS analysis
    FROM public.recommendations
    WHERE engine_version = 'rules-v0.12.1-liquidations-readable'
    ORDER BY id
    LIMIT :limit
    OFFSET :offset
)
SELECT jsonb_agg(
    jsonb_build_object(
        'recommendation_id', id,
        'symbol', symbol,
        'side', side,
        'time_horizon', time_horizon,
        'engine_version', engine_version,
        'scoring_version', scoring_version,
        'original', jsonb_build_object(
            'tp_probability', tp_probability,
            'sl_probability', sl_probability,
            'range_probability', range_probability,
            'risk_level', risk_level,
            'setup_grade', setup_grade,
            'confidence', confidence,
            'training_decision', training_decision
        ),
        'score_components', snapshot->'score_components',
        'context', jsonb_build_object(
            'recent_range_pct', (snapshot->>'recent_range_pct')::double precision,
            'atr_pct', (snapshot->>'atr_pct')::double precision,
            'risk_distance_pct', (snapshot->>'risk_distance_pct')::double precision,
            'risk_reward_ratio', (snapshot->>'risk_reward_ratio')::double precision,
            'spread_pct', (snapshot#>>'{order_book,spread_pct}')::double precision,
            'market_regime', analysis#>>'{market_regime,name}',
            'fibonacci_risk_score_addition',
                COALESCE((analysis#>>'{fibonacci_context,risk_score_addition}')::double precision, 0),
            'confidence_score',
                (analysis#>>'{layered_scores,confidence_score}')::integer,
            'expected_value', jsonb_build_object(
                'net_win_usdt',
                    (analysis#>>'{expected_value,net_win_usdt}')::double precision,
                'net_loss_usdt',
                    (analysis#>>'{expected_value,net_loss_usdt}')::double precision,
                'estimated_cost_usdt',
                    (analysis#>>'{expected_value,estimated_cost_usdt}')::double precision,
                'notional',
                    (analysis#>>'{expected_value,notional}')::double precision,
                'expected_value_usdt',
                    (analysis#>>'{expected_value,expected_value_usdt}')::double precision
            ),
            'risk_calibration', jsonb_build_object(
                'flags', COALESCE(analysis#>'{risk_calibration_context,flags}', '[]'::jsonb),
                'grade_cap', analysis#>>'{risk_calibration_context,grade_cap}',
                'force_observar',
                    COALESCE((analysis#>>'{risk_calibration_context,force_observar}')::boolean, false),
                'expected_value_score_penalty',
                    COALESCE((analysis#>>'{risk_calibration_context,expected_value_score_penalty}')::integer, 0),
                'confidence_score_penalty',
                    COALESCE((analysis#>>'{risk_calibration_context,confidence_score_penalty}')::integer, 0)
            )
        )
    )
    ORDER BY id
) AS records
FROM source;
