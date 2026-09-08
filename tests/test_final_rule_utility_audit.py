from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import audit_final_rule_utility as audit


class FinalRuleUtilityAuditTests(unittest.TestCase):
    def test_fast_soft_auc_matches_binary_ordering_and_ties(self) -> None:
        self.assertEqual(audit.fast_soft_auc([0.1, 0.9], [0.0, 1.0]), 1.0)
        self.assertEqual(audit.fast_soft_auc([1.0, 1.0], [0.0, 1.0]), 0.5)

    def test_fast_soft_auc_matches_reference_for_fractional_episodes(self) -> None:
        signals = [0.1, 0.2, 0.8, 0.9]
        shares = [0.1, 0.25, 0.75, 0.9]
        numerator = 0.0
        denominator = 0.0
        for left, (left_signal, left_share) in enumerate(zip(signals, shares)):
            for right, (right_signal, right_share) in enumerate(zip(signals, shares)):
                if left == right:
                    continue
                weight = left_share * (1.0 - right_share)
                denominator += weight
                if left_signal > right_signal:
                    numerator += weight
                elif left_signal == right_signal:
                    numerator += 0.5 * weight
        self.assertAlmostEqual(
            audit.fast_soft_auc(signals, shares),
            numerator / denominator,
        )

    def test_episode_signal_rows_collapse_overlapping_cases(self) -> None:
        rows = [
            {
                "episode_key": "a",
                "analysis_at": "2026-08-01T00:00:00+00:00",
                "value": 0.2,
                "outcome_label": audit.CLASSES[0],
            },
            {
                "episode_key": "a",
                "analysis_at": "2026-08-01T00:01:00+00:00",
                "value": 0.8,
                "outcome_label": audit.CLASSES[1],
            },
            {
                "episode_key": "b",
                "analysis_at": "2026-08-02T00:00:00+00:00",
                "value": 1.0,
                "outcome_label": audit.CLASSES[0],
            },
        ]
        episodes = audit._episode_signal_rows(rows, "directional")
        self.assertEqual(len(episodes), 2)
        self.assertAlmostEqual(episodes[0]["signal"], 0.5)
        self.assertAlmostEqual(episodes[0]["positive_share"], 0.5)

    def test_association_inference_does_not_run_below_latest_minimum(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        episodes = [
            {
                "episode_key": str(index),
                "analysis_at": start + timedelta(days=index),
                "signal": float(index),
                "positive_share": float(index % 2),
                "raw_cases": 1,
            }
            for index in range(14)
        ]
        result = audit._association_inference(episodes, orientation=1, seed=1)
        self.assertIsNone(result["permutation_p"])
        self.assertIsNone(result["bootstrap_95ci"])

    def test_association_inference_runs_at_latest_minimum(self) -> None:
        start = datetime(2026, 8, 1, tzinfo=timezone.utc)
        episodes = [
            {
                "episode_key": str(index),
                "analysis_at": start + timedelta(days=index),
                "signal": float(index),
                "positive_share": 1.0 if index >= 8 else 0.0,
                "raw_cases": 1,
            }
            for index in range(16)
        ]
        with patch.object(audit, "BOOTSTRAP_SAMPLES", 40), patch.object(
            audit, "PERMUTATION_SAMPLES", 40
        ):
            result = audit._association_inference(episodes, orientation=1, seed=1)
        self.assertEqual(result["auc"], 1.0)
        self.assertIsNotNone(result["permutation_p"])
        self.assertIsNotNone(result["bootstrap_95ci"])

    def test_classification_always_covers_the_full_library(self) -> None:
        library = audit.load_rule_library()
        runtime = {
            "production_fitted_rule_ids": [],
            "shadow_challenger_rule_ids": [],
            "observational_rule_ids": [],
        }
        decisions = audit.classify_rule_library(
            library,
            {},
            [],
            [],
            [],
            runtime,
        )
        self.assertEqual(len(decisions), 38)
        self.assertEqual(len({item["rule_id"] for item in decisions}), 38)
        self.assertTrue(
            all(item["production_change_authorized"] is False for item in decisions)
        )


if __name__ == "__main__":
    unittest.main()
