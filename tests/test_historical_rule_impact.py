import unittest

import audit_historical_rule_impact as impact


def sample_record() -> dict:
    return {
        "recommendation_id": 1,
        "symbol": "BTCUSDT",
        "side": "short",
        "time_horizon": "intraday_short",
        "engine_version": impact.TARGET_ENGINE_VERSION,
        "scoring_version": impact.TARGET_SCORING_VERSION,
        "original": {
            "tp_probability": 0.53,
            "sl_probability": 0.35,
            "range_probability": 0.12,
            "risk_level": "medio",
            "setup_grade": "B",
            "confidence": "media",
            "training_decision": "simular",
        },
        "score_components": {
            "trend_bias": 0.05,
            "technical_direction_bias": 0.0,
            "price_vs_entry_bias": 0.03,
            "volume_bias": 0.0,
            "order_book_bias": 0.0,
            "momentum_bias": 0.0,
            "market_regime_bias": 0.0,
            "fibonacci_probability_adjustment": 0.0,
            "zone_probability_adjustment": 0.0,
            "taker_flow_bias": 0.0,
            "cvd_bias": 0.0,
            "oi_trend_bias": 0.0,
            "breadth_bias": 0.0,
            "volatility_penalty": 0.0,
            "liquidity_penalty": 0.0,
            "overextension_penalty": 0.0,
            "funding_penalty": 0.0,
            "funding_relative_penalty": 0.0,
            "crowding_penalty": 0.0,
            "level_penalty": 0.025,
            "sentiment_penalty": 0.0,
            "higher_timeframe_penalty": 0.0,
            "technical_entry_timing_penalty": 0.0,
            "technical_barrier_penalty": 0.025,
            "oi_context_penalty": 0.0,
            "contradiction_penalty": 0.0,
            "risk_calibration_tp_adjustment": 0.0,
            "zone_range_probability_adjustment": 0.0,
            "risk_calibration_range_adjustment": 0.0,
            "zone_risk_score_addition": 0.0,
            "risk_calibration_score_addition": 0.0,
        },
        "context": {
            "recent_range_pct": 1.0,
            "atr_pct": 0.5,
            "risk_distance_pct": 1.0,
            "risk_reward_ratio": 2.0,
            "spread_pct": 0.02,
            "market_regime": "mixto",
            "fibonacci_risk_score_addition": 0.0,
            "confidence_score": 70,
            "expected_value": {
                "net_win_usdt": 3.0,
                "net_loss_usdt": 2.0,
                "estimated_cost_usdt": 0.2,
                "notional": 200.0,
                "expected_value_usdt": 0.866,
            },
            "risk_calibration": {
                "flags": [],
                "grade_cap": None,
                "force_observar": False,
                "expected_value_score_penalty": 0,
                "confidence_score_penalty": 0,
            },
        },
    }


class HistoricalRuleImpactTests(unittest.TestCase):
    def test_replays_preserved_probability_formula(self):
        replay = impact.replay_probabilities(sample_record())

        self.assertAlmostEqual(replay["tp_probability"], 0.53)
        self.assertAlmostEqual(replay["range_probability"], 0.12)
        self.assertAlmostEqual(replay["sl_probability"], 0.35)

    def test_direct_ablation_removes_only_recorded_component(self):
        record = sample_record()
        baseline = impact.replay_baseline(record)
        without_trend = impact.direct_ablation(record, "trend_bias")

        self.assertAlmostEqual(without_trend["tp_probability"], 0.48)
        self.assertAlmostEqual(without_trend["sl_probability"], 0.40)
        self.assertAlmostEqual(
            baseline["tp_probability"] - without_trend["tp_probability"],
            0.05,
        )

    def test_caps_are_reapplied_after_ablation(self):
        record = sample_record()
        record["score_components"]["trend_bias"] = 0.1
        record["score_components"]["technical_direction_bias"] = 0.035
        record["score_components"]["market_regime_bias"] = 0.024
        record["score_components"]["price_vs_entry_bias"] = 0.03
        record["score_components"]["volume_bias"] = 0.025
        record["score_components"]["order_book_bias"] = 0.016
        record["score_components"]["momentum_bias"] = 0.02
        record["score_components"]["taker_flow_bias"] = 0.02
        record["score_components"]["cvd_bias"] = 0.018
        record["score_components"]["oi_trend_bias"] = 0.02
        record["score_components"]["breadth_bias"] = 0.02
        record["score_components"]["level_penalty"] = 0.0
        record["score_components"]["technical_barrier_penalty"] = 0.0

        baseline = impact.replay_probabilities(record)
        ablated = impact.replay_probabilities(record, {"cvd_bias"})

        self.assertEqual(baseline["tp_probability"], 0.74)
        self.assertEqual(ablated["tp_probability"], 0.74)

    def test_risk_calibration_bundle_removes_aggregate_controls(self):
        record = sample_record()
        record["score_components"]["risk_calibration_tp_adjustment"] = -0.05
        record["score_components"]["risk_calibration_score_addition"] = 0.10
        record["context"]["risk_calibration"] = {
            "flags": ["sl_probability_gte_55"],
            "grade_cap": "D",
            "force_observar": True,
            "expected_value_score_penalty": 10,
            "confidence_score_penalty": 10,
        }
        record["original"]["tp_probability"] = 0.48
        record["original"]["sl_probability"] = 0.40
        record["original"]["setup_grade"] = "D"
        record["original"]["training_decision"] = "observar"

        baseline = impact.replay_baseline(record)
        ablated = impact.composite_ablation(record, "risk_calibration_bundle")

        self.assertEqual(baseline["training_decision"], "observar")
        self.assertAlmostEqual(ablated["tp_probability"], 0.53)
        self.assertLess(ablated["risk_score"], baseline["risk_score"])

    def test_audit_rejects_other_engine_versions(self):
        record = sample_record()
        record["engine_version"] = "rules-v0.9-pending-zone-adjusted"

        audit = impact.audit_records([record])

        self.assertEqual(audit["replay"]["cases"], 0)
        self.assertEqual(audit["excluded"]["different_engine_version"], 1)

    def test_partial_audits_merge_without_losing_maxima(self):
        first = impact.audit_records([sample_record()])
        second_record = sample_record()
        second_record["recommendation_id"] = 2
        second = impact.audit_records([second_record])

        merged = impact.finalize_audit(impact.merge_audits([first, second]))

        self.assertEqual(merged["replay"]["cases"], 2)
        self.assertEqual(merged["units"]["trend_bias"]["active_cases"], 2)
        self.assertEqual(merged["dimensions"]["symbol"]["BTCUSDT"], 2)


if __name__ == "__main__":
    unittest.main()
