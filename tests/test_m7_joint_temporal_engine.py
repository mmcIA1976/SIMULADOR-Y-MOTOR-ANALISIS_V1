from __future__ import annotations

import copy
import unittest

from m7_joint_temporal_engine import (
    CLASSES,
    ENGINE_VERSION,
    HORIZON_SECONDS,
    JointTemporalEngineError,
    canonical_sha256,
    joint_temporal_probabilities,
    load_production_artifact,
    select_horizon,
    validate_artifact,
)


FEATURES = {
    "directional_path_efficiency_h": 0.15,
    "directional_path_efficiency_2h": 0.05,
    "directional_path_efficiency_4h": -0.10,
    "volatility_percentile_60": 0.65,
    "target_extreme_between_entry_and_tp": 1.0,
}


class JointTemporalEngineTests(unittest.TestCase):
    def test_frozen_artifact_has_no_parallel_engine_or_auto_updates(self):
        artifact = load_production_artifact()

        self.assertEqual(artifact["engine_version"], ENGINE_VERSION)
        self.assertTrue(artifact["single_engine"])
        self.assertEqual(artifact["parallel_probability_engines"], 0)
        self.assertFalse(artifact["automatic_weight_updates"])
        self.assertEqual(
            artifact["selection"]["weights_decision"],
            "rule_weights_rejected_baseline_curve_served",
        )

    def test_one_curve_is_monotone_and_absorbing_at_all_reads(self):
        result = joint_temporal_probabilities(
            side="long",
            entry=100.0,
            take_profit=103.0,
            stop_loss=98.0,
            reference_sigma_24h=0.025,
            feature_values=FEATURES,
        )

        ordered = sorted(HORIZON_SECONDS, key=HORIZON_SECONDS.get)
        curve = result["probability_curve"]
        for horizon in ordered:
            self.assertAlmostEqual(sum(curve[horizon].values()), 1.0, places=12)
        for left, right in zip(ordered, ordered[1:]):
            self.assertLessEqual(curve[left][CLASSES[0]], curve[right][CLASSES[0]])
            self.assertLessEqual(curve[left][CLASSES[1]], curve[right][CLASSES[1]])
            self.assertGreaterEqual(curve[left][CLASSES[2]], curve[right][CLASSES[2]])
        self.assertEqual(result["parallel_probability_engines_executed"], 0)
        self.assertEqual(
            select_horizon(result, "intraday_wide"),
            curve["intraday_wide"],
        )

    def test_same_plan_uses_same_curve_regardless_of_selected_read(self):
        first = joint_temporal_probabilities(
            side="short",
            entry=100.0,
            take_profit=97.0,
            stop_loss=102.0,
            reference_sigma_24h=0.02,
            feature_values=FEATURES,
        )
        second = joint_temporal_probabilities(
            side="short",
            entry=100.0,
            take_profit=97.0,
            stop_loss=102.0,
            reference_sigma_24h=0.02,
            feature_values=FEATURES,
        )

        self.assertEqual(first["probability_curve"], second["probability_curve"])
        self.assertEqual(first["result_sha256"], second["result_sha256"])

    def test_artifact_rejects_asymmetric_volatility_direction(self):
        artifact = copy.deepcopy(load_production_artifact())
        artifact["coefficients"]["tp"]["volatility_percentile_60"] = 0.1
        artifact["artifact_sha256"] = canonical_sha256(
            {key: value for key, value in artifact.items() if key != "artifact_sha256"}
        )

        with self.assertRaisesRegex(
            JointTemporalEngineError,
            "volatility_effect_not_shared",
        ):
            validate_artifact(artifact)


if __name__ == "__main__":
    unittest.main()
