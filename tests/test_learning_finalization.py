import unittest
from unittest.mock import Mock, patch

from app import (
    finalize_due_observations,
    predictive_rule_learning_snapshot,
)


class LearningFinalizationTests(unittest.TestCase):
    def test_predictive_rule_snapshot_joins_pretrade_effect_and_outcome(self):
        snapshot = {
            "feature_snapshot": {
                "active_predictive_rule_ids": ["rule-a"],
            },
            "m5_rule_effects": {
                "rule-a": {
                    "rule_status": "evaluated",
                    "probability_effect": "provisional_rule_contribution",
                    "probability_effect_reason": "active",
                    "signal": 0.4,
                    "provisional_weight": 0.1,
                    "tp_probability_delta": 0.01,
                    "sl_probability_delta": -0.008,
                }
            },
        }

        result = predictive_rule_learning_snapshot(
            snapshot,
            plan_result="plan_success",
        )

        self.assertEqual(result["active_rule_count"], 1)
        self.assertEqual(
            result["observed_outcome"],
            "tp_first_within_horizon",
        )
        self.assertEqual(
            result["rules"]["rule-a"]["tp_probability_delta"],
            0.01,
        )

    def test_observational_rules_are_linked_without_probability_effect(self):
        snapshot = {
            "feature_snapshot": {
                "active_predictive_rule_ids": [],
                "observational_rule_traces": {
                    "status": "evaluated_shadow",
                    "traces": [
                        {
                            "rule_id": "LIB-CAND-RSI-WILDER-001",
                            "status": "evaluated_shadow",
                            "family_id": "FAMILY-MOMENTUM",
                            "role": "contextual",
                            "parent_rule_ids": [],
                            "formula_ids": ["RSI-FORMULA"],
                            "inputs": {"closed_candle_count": 260},
                            "outputs": {"rsi14": 61.2},
                            "source_data_sha256": "source-sha",
                            "trace_sha256": "trace-sha",
                            "probability_effect": "none_shadow_observation",
                        }
                    ],
                },
            },
            "m5_rule_effects": {},
        }

        result = predictive_rule_learning_snapshot(
            snapshot,
            plan_result="plan_failure",
        )

        self.assertEqual(
            result["observational_rule_ids"],
            ["LIB-CAND-RSI-WILDER-001"],
        )
        observation = result["observational_rules"][
            "LIB-CAND-RSI-WILDER-001"
        ]
        self.assertEqual(observation["outputs"]["rsi14"], 61.2)
        self.assertEqual(
            observation["probability_effect"],
            "none_shadow_observation",
        )

    @patch("app.refresh_learning_evaluations")
    @patch("app.refresh_learning_conclusions")
    @patch("app.finalize_due_observations_with_db")
    def test_finalized_observation_immediately_refreshes_learning(
        self,
        finalize_with_db,
        refresh_conclusions,
        refresh_evaluations,
    ):
        db = Mock()
        finalized = [{"id": 227, "result": "plan_would_succeed"}]
        finalize_with_db.return_value = finalized

        result = finalize_due_observations(db)

        self.assertEqual(result, finalized)
        refresh_conclusions.assert_called_once_with(db)
        refresh_evaluations.assert_called_once_with(db)

    @patch("app.refresh_learning_evaluations")
    @patch("app.refresh_learning_conclusions")
    @patch("app.finalize_due_observations_with_db", return_value=[])
    def test_no_learning_refresh_without_newly_finalized_observations(
        self,
        finalize_with_db,
        refresh_conclusions,
        refresh_evaluations,
    ):
        db = Mock()

        result = finalize_due_observations(db)

        self.assertEqual(result, [])
        finalize_with_db.assert_called_once_with(db)
        refresh_conclusions.assert_not_called()
        refresh_evaluations.assert_not_called()


if __name__ == "__main__":
    unittest.main()
