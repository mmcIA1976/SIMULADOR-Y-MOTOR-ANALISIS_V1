import unittest

import m8_evaluation as m8
from audit_real_closed_rule_evidence import (
    classify_real_rule_evidence,
    probability_metrics,
    stored_outcome,
)


class RealClosedRuleEvidenceTests(unittest.TestCase):
    def test_stored_touch_maps_to_three_class_contract(self) -> None:
        self.assertEqual(
            stored_outcome({"first_plan_touch": "take_profit"})["label"],
            m8.CLASSES[0],
        )
        self.assertEqual(
            stored_outcome({"first_plan_touch": "stop_loss"})["label"],
            m8.CLASSES[1],
        )
        self.assertEqual(
            stored_outcome({"first_plan_touch": "no_plan_touch"})["label"],
            m8.CLASSES[2],
        )

    def test_ambiguous_touch_is_not_a_training_label(self) -> None:
        result = stored_outcome({"first_plan_touch": "ambiguous_same_candle"})
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["label"])

    def test_probability_metrics_exclude_ambiguous_outcomes(self) -> None:
        records = [
            {
                "tp_probability": 0.8,
                "sl_probability": 0.1,
                "range_probability": 0.1,
                "outcome": {"label": m8.CLASSES[0]},
            },
            {
                "tp_probability": 0.2,
                "sl_probability": 0.4,
                "range_probability": 0.4,
                "outcome": {"label": None},
            },
        ]
        self.assertEqual(probability_metrics(records)["n"], 1)

    def test_supported_real_rule_is_shadow_only(self) -> None:
        library = {
            "rules": [
                {
                    "rule_id": "R1",
                    "name": "rule",
                    "lifecycle_status": "implemented_shadow",
                }
            ]
        }
        decisions = classify_real_rule_evidence(
            library,
            {"R1": {"exact_cases": 100}},
            [
                {
                    "rule_id": "R1",
                    "time_horizon": "intraday_wide",
                    "evidence_status": "supported_on_frozen_latest_segment",
                }
            ],
            [],
        )
        self.assertEqual(
            decisions[0]["decision"],
            "candidate_for_prospective_shadow_not_production",
        )

    def test_supported_ablation_requires_duration_recalibration(self) -> None:
        library = {
            "rules": [
                {
                    "rule_id": "R1",
                    "name": "rule",
                    "lifecycle_status": "active_provisional",
                }
            ]
        }
        decisions = classify_real_rule_evidence(
            library,
            {"R1": {"exact_cases": 100}},
            [],
            [
                {
                    "rule_id": "R1",
                    "time_horizon": "intraday_wide",
                    "evidence_status": "supported_material_stable_ablation",
                }
            ],
        )
        self.assertEqual(
            decisions[0]["decision"],
            "duration_recalibration_candidate_for_shadow_only",
        )
        self.assertEqual(
            decisions[0]["supported_ablation_horizons"], ["intraday_wide"]
        )


if __name__ == "__main__":
    unittest.main()
