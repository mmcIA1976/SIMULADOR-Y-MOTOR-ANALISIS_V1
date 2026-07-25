from __future__ import annotations

import unittest

from challenger_engine import (
    CHALLENGER_VERSION,
    MODEL_SCHEMA_VERSION,
    compare_with_champion,
    derive_plan_features,
    evaluate_configured_shadow,
    evaluate_shadow,
    select_shadow_artifact,
    validate_plan,
)


MATRIX_SHA = "matrix-test-sha"
ANALYSIS_AT = "2026-07-25T12:00:00+00:00"


def valid_plan(**overrides) -> dict:
    plan = {
        "symbol": "ETHUSDT",
        "side": "long",
        "entry": 3000.0,
        "take_profit": 3060.0,
        "stop_loss": 2970.0,
        "time_horizon": "intraday_short",
        "horizon_seconds": 7200,
        "analysis_at": ANALYSIS_AT,
    }
    plan.update(overrides)
    return plan


def valid_artifact() -> dict:
    features = [
        {
            "feature_id": "PLAN-TP-LOG-DISTANCE",
            "rule_id": "PLAN-TP-LOG-DISTANCE",
            "plan_dependencies": ["PLAN-TP-LOG-DISTANCE"],
            "unit": "log_return",
            "center": 0.02,
            "scale": 0.01,
            "max_age_seconds": 0,
        },
        {
            "feature_id": "PLAN-SL-LOG-DISTANCE",
            "rule_id": "PLAN-SL-LOG-DISTANCE",
            "plan_dependencies": ["PLAN-SL-LOG-DISTANCE"],
            "unit": "log_return",
            "center": 0.01,
            "scale": 0.01,
            "max_age_seconds": 0,
        },
        {
            "feature_id": "PLAN-LOG-HORIZON-SECONDS",
            "rule_id": "PLAN-LOG-HORIZON-SECONDS",
            "plan_dependencies": ["PLAN-LOG-HORIZON-SECONDS"],
            "unit": "log_seconds",
            "center": 8.8,
            "scale": 0.5,
            "max_age_seconds": 0,
        },
        {
            "feature_id": "MARKET-TEST",
            "rule_id": "MARKET-TEST",
            "plan_dependencies": [],
            "unit": "ratio",
            "center": 1.0,
            "scale": 0.2,
            "max_age_seconds": 60,
        },
    ]
    coefficients = {
        "tp_first": {
            "PLAN-TP-LOG-DISTANCE": -1.0,
            "PLAN-SL-LOG-DISTANCE": 0.5,
            "PLAN-LOG-HORIZON-SECONDS": 0.4,
            "MARKET-TEST": 0.2,
        },
        "sl_first": {
            "PLAN-TP-LOG-DISTANCE": 0.5,
            "PLAN-SL-LOG-DISTANCE": -1.0,
            "PLAN-LOG-HORIZON-SECONDS": 0.3,
            "MARKET-TEST": -0.2,
        },
        "expiry_unresolved": {
            "PLAN-TP-LOG-DISTANCE": 0.3,
            "PLAN-SL-LOG-DISTANCE": 0.3,
            "PLAN-LOG-HORIZON-SECONDS": -0.5,
            "MARKET-TEST": 0.0,
        },
    }
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_version": "model-test-v1",
        "dataset_id": "dataset-test-v1",
        "code_sha256": "code-test-sha",
        "training_cutoff_at": "2026-07-24T00:00:00+00:00",
        "deployment_state": "shadow",
        "admission_matrix_sha256": MATRIX_SHA,
        "supported_horizons": ["intraday_short"],
        "supported_symbols": ["ETHUSDT"],
        "features": features,
        "intercepts": {
            "tp_first": 0.0,
            "sl_first": 0.0,
            "expiry_unresolved": 0.0,
        },
        "coefficients": coefficients,
        "calibration": {
            "method": "multinomial_temperature",
            "temperature": 1.1,
            "validation_report_id": "validation-test-v1",
        },
    }


def valid_snapshot() -> dict:
    return {
        "MARKET-TEST": {
            "value": 1.1,
            "source": "test_fixture",
            "observed_at": "2026-07-25T11:59:30+00:00",
            "quality": "ok",
        }
    }


def valid_admission_registry(market_state: str = "data_allowed_not_predictive") -> dict:
    return {
        "PLAN-TP-LOG-DISTANCE": "calculation_allowed_nonpredictive",
        "PLAN-SL-LOG-DISTANCE": "calculation_allowed_nonpredictive",
        "PLAN-LOG-HORIZON-SECONDS": "calculation_allowed_nonpredictive",
        "MARKET-TEST": market_state,
    }


class ChallengerEngineTests(unittest.TestCase):
    def test_no_model_means_no_probability(self):
        result = evaluate_shadow(
            valid_plan(),
            valid_snapshot(),
            None,
            {},
            MATRIX_SHA,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["block_code"], "model_artifact_absent")
        self.assertIsNone(result["probabilities"])

    def test_invalid_barrier_geometry_is_blocked(self):
        normalized, error = validate_plan(valid_plan(take_profit=2980.0))
        self.assertIsNone(normalized)
        self.assertEqual(error["block_code"], "invalid_barrier_geometry")

    def test_plan_distances_are_side_symmetric(self):
        long_plan, error = validate_plan(valid_plan())
        self.assertIsNone(error)
        long_features, error = derive_plan_features(long_plan)
        self.assertIsNone(error)

        short_plan, error = validate_plan(
            valid_plan(
                side="short",
                take_profit=3000.0 * 3000.0 / 3060.0,
                stop_loss=3000.0 * 3000.0 / 2970.0,
            )
        )
        self.assertIsNone(error)
        short_features, error = derive_plan_features(short_plan)
        self.assertIsNone(error)
        self.assertAlmostEqual(
            long_features["PLAN-TP-LOG-DISTANCE"],
            short_features["PLAN-TP-LOG-DISTANCE"],
        )
        self.assertAlmostEqual(
            long_features["PLAN-SL-LOG-DISTANCE"],
            short_features["PLAN-SL-LOG-DISTANCE"],
        )

    def test_unadmitted_feature_blocks_the_whole_prediction(self):
        result = evaluate_shadow(
            valid_plan(),
            valid_snapshot(),
            valid_artifact(),
            valid_admission_registry("research"),
            MATRIX_SHA,
        )
        self.assertEqual(result["block_code"], "feature_not_admitted")
        self.assertIsNone(result["probabilities"])

    def test_model_trained_after_analysis_is_blocked(self):
        artifact = valid_artifact()
        artifact["training_cutoff_at"] = "2026-07-26T00:00:00+00:00"
        result = evaluate_shadow(
            valid_plan(),
            valid_snapshot(),
            artifact,
            valid_admission_registry(),
            MATRIX_SHA,
        )
        self.assertEqual(result["block_code"], "model_temporal_leakage")
        self.assertIsNone(result["probabilities"])

    def test_stale_feature_is_not_replaced_with_neutral_value(self):
        snapshot = valid_snapshot()
        snapshot["MARKET-TEST"]["observed_at"] = "2026-07-25T11:00:00+00:00"
        result = evaluate_shadow(
            valid_plan(),
            snapshot,
            valid_artifact(),
            valid_admission_registry(),
            MATRIX_SHA,
        )
        self.assertEqual(result["block_code"], "feature_stale")
        self.assertIsNone(result["probabilities"])

    def test_feature_without_source_is_blocked(self):
        snapshot = valid_snapshot()
        snapshot["MARKET-TEST"]["source"] = ""
        result = evaluate_shadow(
            valid_plan(),
            snapshot,
            valid_artifact(),
            valid_admission_registry(),
            MATRIX_SHA,
        )
        self.assertEqual(result["block_code"], "feature_source_missing")
        self.assertIsNone(result["probabilities"])

    def test_shadow_probabilities_are_coherent_and_fully_traced(self):
        result = evaluate_shadow(
            valid_plan(),
            valid_snapshot(),
            valid_artifact(),
            valid_admission_registry(),
            MATRIX_SHA,
        )
        self.assertEqual(result["status"], "shadow_prediction")
        self.assertEqual(result["challenger_version"], CHALLENGER_VERSION)
        self.assertAlmostEqual(sum(result["probabilities"].values()), 1.0)
        self.assertAlmostEqual(result["trace"]["probability_mass"], 1.0)
        self.assertEqual(result["trace"]["production_effect"], "none")
        self.assertEqual(len(result["trace"]["features"]), 4)
        for outcome in ("tp_first", "sl_first", "expiry_unresolved"):
            self.assertEqual(len(result["trace"]["outcomes"][outcome]["features"]), 4)

    def test_non_monotonic_distance_model_is_blocked(self):
        artifact = valid_artifact()
        artifact["coefficients"]["tp_first"]["PLAN-TP-LOG-DISTANCE"] = 1.0
        result = evaluate_shadow(
            valid_plan(),
            valid_snapshot(),
            artifact,
            valid_admission_registry(),
            MATRIX_SHA,
        )
        self.assertEqual(result["block_code"], "monotonicity_constraint_failed")
        self.assertIsNone(result["probabilities"])

    def test_distance_and_horizon_monotonicity_hold_in_predictions(self):
        artifact = valid_artifact()
        registry = valid_admission_registry()
        base = evaluate_shadow(
            valid_plan(),
            valid_snapshot(),
            artifact,
            registry,
            MATRIX_SHA,
        )
        farther_tp = evaluate_shadow(
            valid_plan(take_profit=3090.0),
            valid_snapshot(),
            artifact,
            registry,
            MATRIX_SHA,
        )
        farther_sl = evaluate_shadow(
            valid_plan(stop_loss=2940.0),
            valid_snapshot(),
            artifact,
            registry,
            MATRIX_SHA,
        )
        longer_horizon = evaluate_shadow(
            valid_plan(horizon_seconds=10800),
            valid_snapshot(),
            artifact,
            registry,
            MATRIX_SHA,
        )
        self.assertLess(
            farther_tp["probabilities"]["tp_before_sl_within_horizon"],
            base["probabilities"]["tp_before_sl_within_horizon"],
        )
        self.assertLess(
            farther_sl["probabilities"]["sl_before_tp_within_horizon"],
            base["probabilities"]["sl_before_tp_within_horizon"],
        )
        self.assertLess(
            longer_horizon["probabilities"]["expiry_unresolved"],
            base["probabilities"]["expiry_unresolved"],
        )

    def test_comparison_cannot_modify_champion(self):
        champion = {
            "engine_version": "rules-frozen",
            "tp_probability": 0.61,
            "sl_probability": 0.29,
        }
        challenger = {
            "status": "blocked",
            "challenger_version": CHALLENGER_VERSION,
            "probabilities": None,
        }
        before = dict(champion)
        comparison = compare_with_champion(champion, challenger)
        self.assertEqual(champion, before)
        self.assertEqual(comparison["production_effect"], "none")

    def test_kill_switch_blocks_selection(self):
        artifact, error = select_shadow_artifact(
            {"model-test-v1": valid_artifact()},
            {"enabled": False, "selected_model_version": "model-test-v1"},
        )
        self.assertIsNone(artifact)
        self.assertEqual(error["block_code"], "shadow_disabled")

    def test_model_selection_is_versioned_and_reversible(self):
        first = valid_artifact()
        second = valid_artifact()
        second["model_version"] = "model-test-v2"
        registry = {"model-test-v1": first, "model-test-v2": second}
        selected, error = select_shadow_artifact(
            registry,
            {"enabled": True, "selected_model_version": "model-test-v2"},
        )
        self.assertIsNone(error)
        self.assertEqual(selected["model_version"], "model-test-v2")

        rolled_back, error = select_shadow_artifact(
            registry,
            {"enabled": True, "selected_model_version": "model-test-v1"},
        )
        self.assertIsNone(error)
        self.assertEqual(rolled_back["model_version"], "model-test-v1")

    def test_configured_shadow_uses_selected_artifact(self):
        result = evaluate_configured_shadow(
            valid_plan(),
            valid_snapshot(),
            {"model-test-v1": valid_artifact()},
            {"enabled": True, "selected_model_version": "model-test-v1"},
            valid_admission_registry(),
            MATRIX_SHA,
        )
        self.assertEqual(result["status"], "shadow_prediction")
        self.assertEqual(result["model_version"], "model-test-v1")


if __name__ == "__main__":
    unittest.main()
