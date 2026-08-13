from __future__ import annotations

import math
import unittest

import nested_horizon_evaluation as nested
from phase1_controlled_replay import CLASSES


class NestedHorizonEvaluationTests(unittest.TestCase):
    def test_protocol_declares_one_engine_and_same_plan(self) -> None:
        result = nested.build_protocol()
        self.assertTrue(result["single_engine"])
        self.assertFalse(result["independent_engines_by_frame"])
        self.assertEqual(result["only_changed_plan_input"], "horizon_seconds")

    def test_nested_outcome_preserves_first_touch(self) -> None:
        future = [
            {
                "open_time_ms": index * 300_000,
                "high": 101.0,
                "low": 99.0,
            }
            for index in range(nested.MAX_HORIZON_SECONDS // 300)
        ]
        future[20]["high"] = 103.0
        future[100]["low"] = 97.0
        result = nested.nested_outcomes(
            future=future,
            side="long",
            take_profit=102.0,
            stop_loss=98.0,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(
            all(item["label"] == CLASSES[0] for item in result.values())
        )

    def test_nested_outcome_can_expire_then_resolve(self) -> None:
        future = [
            {
                "open_time_ms": index * 300_000,
                "high": 101.0,
                "low": 99.0,
            }
            for index in range(nested.MAX_HORIZON_SECONDS // 300)
        ]
        future[100]["high"] = 103.0
        result = nested.nested_outcomes(
            future=future,
            side="long",
            take_profit=102.0,
            stop_loss=98.0,
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["intraday_short"]["label"], CLASSES[2])
        self.assertEqual(result["intraday_wide"]["label"], CLASSES[0])
        self.assertEqual(result["short_swing"]["label"], CLASSES[0])

    def test_aware_sigma_scales_only_with_duration(self) -> None:
        reference = 0.02
        values = {
            name: reference
            * math.sqrt(profile["seconds"] / nested.REFERENCE_SECONDS)
            for name, profile in nested.HORIZONS.items()
        }
        self.assertLess(values["intraday_short"], reference)
        self.assertAlmostEqual(values["intraday_wide"], reference)
        self.assertGreater(values["short_swing"], reference)

    def test_canonical_rule_features_have_no_duplicates(self) -> None:
        keys = [nested.feature_key(*item) for item in nested.CANONICAL_RULE_FEATURES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_blind_model_has_no_duration_or_horizon_feature(self) -> None:
        row = {
            "horizon_seconds": nested.HORIZONS["short_swing"]["seconds"],
            "common_rule_features": {"rule::value": 0.2},
            "horizon_rule_features": {"rule::value": 0.8},
        }
        features = nested.raw_model_features(row, "horizon_blind_rules")
        self.assertEqual(features, {"intercept": 1.0, "rule::value": 0.2})

    def test_aware_interactions_use_continuous_duration(self) -> None:
        row = {
            "horizon_seconds": nested.HORIZONS["short_swing"]["seconds"],
            "common_rule_features": {"rule::value": 0.2},
            "horizon_rule_features": {"rule::value": 0.8},
        }
        features = nested.raw_model_features(
            row, "horizon_aware_interactions"
        )
        self.assertIn("log_duration_ratio", features)
        self.assertIn("rule::value::x_log_duration", features)
        self.assertGreater(features["log_duration_ratio"], 0)

    def test_final_gate_requires_no_horizon_degradation(self) -> None:
        comparison = {
            "log_loss_weekly_bootstrap_95ci": [0.01, 0.02],
            "brier_weekly_bootstrap_95ci": [0.01, 0.02],
            "by_horizon": {
                name: {
                    "mean_log_loss_improvement": 0.01,
                    "mean_brier_improvement": (
                        -0.001 if name == "short_swing" else 0.01
                    ),
                }
                for name in nested.HORIZONS
            },
        }
        self.assertFalse(nested.final_gate_passed(comparison))


if __name__ == "__main__":
    unittest.main()
