import unittest
from unittest.mock import Mock, patch

from app import (
    finalize_due_observations,
    predictive_rule_learning_snapshot,
    refresh_learning_evaluations_with_db,
)


class LearningFinalizationTests(unittest.TestCase):
    @patch("app.save_learning_economic_audit")
    @patch("app.save_learning_evidence_audit")
    @patch("app.save_learning_evaluation")
    @patch("app.build_structured_learning_evaluation")
    @patch("app.reconstruct_operation_historical_evidence")
    @patch("app.upgrade_stored_historical_evidence")
    def test_outdated_v09_evaluation_reuses_stored_evidence_without_download(
        self,
        upgrade_evidence,
        reconstruct_evidence,
        build_evaluation,
        save_evaluation,
        save_evidence,
        save_economics,
    ):
        operation = {
            "id": 328,
            "existing_learning_evidence_json": '{"version":"old"}',
        }
        upgraded = {"version": "new"}
        evaluation = {
            "max_favorable_pct": 1.0,
            "max_adverse_pct": -0.5,
            "max_favorable_pnl": 10.0,
            "max_adverse_pnl": -5.0,
            "plan_result": "plan_success",
            "analysis_verdict": "analysis_supported",
            "failure_type": None,
            "economic_metrics": {},
            "r_multiple": 2.0,
            "unleveraged_return_pct": 1.0,
            "margin_return_pct": 2.0,
            "initial_risk_amount": 5.0,
            "economic_plan_outcome": "tp",
        }
        upgrade_evidence.return_value = upgraded
        build_evaluation.return_value = evaluation
        first_cursor = Mock()
        first_cursor.fetchall.return_value = [operation]
        tick_cursor = Mock()
        tick_cursor.fetchall.return_value = []
        db = Mock()
        db.execute.side_effect = [first_cursor, tick_cursor]

        result = refresh_learning_evaluations_with_db(db)

        self.assertEqual(result, [evaluation])
        upgrade_evidence.assert_called_once_with(operation, {"version": "old"})
        reconstruct_evidence.assert_not_called()
        build_evaluation.assert_called_once_with(
            operation,
            [],
            historical_evidence=upgraded,
        )
        save_evaluation.assert_called_once_with(db, evaluation)
        save_evidence.assert_called_once()
        save_economics.assert_called_once()

    def test_v09_snapshot_links_active_inputs_and_observational_traces(self):
        snapshot = {
            "probability_trace": {
                "stage_traces": [
                    {
                        "time_horizon": "intraday_short",
                        "active_rule_groups": ["price_path", "volatility_regime"],
                        "current_feature_values": {
                            "intraday_short::M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h": 0.4,
                            "intraday_short::LIB-CAND-COMPRESSION-001::compression_vector.atr_rank": 0.7,
                            "intraday_short::log_context_sigma": -3.2,
                        },
                    }
                ],
            },
            "stage_rule_traces": {
                "intraday_short": [
                    {
                        "rule_id": "M4-RULE-PATH-STRUCTURE-001",
                        "status": "evaluated",
                        "outputs": {"directional_path_efficiency_h": 0.4},
                    },
                    {
                        "rule_id": "LIB-CAND-FIBONACCI-DISTANCE-001",
                        "status": "evaluated_shadow",
                        "outputs": {"distance": 1.2},
                    },
                ]
            },
            "stage_contexts": {
                "intraday_short": {
                    "source_data_sha256": "stage-sha",
                    "feature_values": {
                        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001::target_path_level_count": 2.0,
                    },
                }
            },
        }

        result = predictive_rule_learning_snapshot(
            snapshot,
            plan_result="plan_success",
        )

        self.assertEqual(result["trace_contract"], "empirical_multiscale_v0.9")
        self.assertEqual(result["active_rule_count"], 2)
        self.assertIn("M4-RULE-PATH-STRUCTURE-001", result["rules"])
        self.assertIn("LIB-CAND-COMPRESSION-001", result["rules"])
        self.assertEqual(result["observational_rule_count"], 2)
        self.assertIn(
            "LIB-CAND-FIBONACCI-DISTANCE-001",
            result["observational_rules"],
        )
        structural = result["observational_rules"][
            "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
        ]["stage_traces"][0]
        self.assertEqual(
            structural["trace_origin"],
            "reconstructed_from_stage_context",
        )
        self.assertEqual(structural["outputs"]["target_path_level_count"], 2.0)
        self.assertEqual(
            result["observed_outcome"],
            "tp_first_within_horizon",
        )

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
