from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m8_evaluation_protocol as m8  # noqa: E402


class M81EvaluationProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = m8.build_protocol()

    def test_owner_starts_m8_without_m9_or_production(self) -> None:
        authorization = self.protocol["owner_authorization"]
        self.assertTrue(authorization["m8_started"])
        self.assertFalse(authorization["m9_started"])
        self.assertFalse(authorization["production_authorized"])

    def test_closed_operation_results_remain_embargoed(self) -> None:
        embargo = self.protocol["historical_outcome_embargo"]
        self.assertEqual(embargo["status"], "active_during_M8_1_and_M8_2")
        self.assertFalse(
            embargo["closed_operations_performance_inspected_in_M8_1"]
        )
        self.assertFalse(embargo["database_queried_in_M8_1"])
        self.assertFalse(
            embargo["legacy_probabilities_allowed_as_label_or_training_target"]
        )
        self.assertTrue(
            embargo["legacy_probabilities_allowed_as_final_comparator_only"]
        )

    def test_model_files_and_zero_coefficients_are_frozen(self) -> None:
        frozen = self.protocol["frozen_model"]
        self.assertEqual(len(frozen["files"]), len(m8.FROZEN_MODEL_FILES))
        self.assertEqual(frozen["active_evidence_coefficients"], 0)
        self.assertEqual(frozen["manual_weights"], 0)
        for item in frozen["files"]:
            path = ROOT / item["path"]
            self.assertEqual(item["sha256"], m8.file_sha256(path))

    def test_outcomes_are_exhaustive_without_forced_ambiguity(self) -> None:
        outcomes = self.protocol["outcome_contract"]
        self.assertEqual(len(outcomes["classes"]), 3)
        self.assertFalse(outcomes["forced_tp_or_sl_label"])
        self.assertEqual(
            outcomes["manual_close_before_resolved_barrier"],
            "right_censored_not_a_class",
        )
        self.assertIn("ambiguous", outcomes["same_bar_ambiguity"])

    def test_three_chronological_partitions_have_separate_uses(self) -> None:
        policy = self.protocol["chronological_partition_policy"]
        self.assertEqual(
            [item["id"] for item in policy["partitions"]],
            ["development", "calibration", "final_test"],
        )
        self.assertTrue(policy["final_test_is_latest_period"])
        self.assertFalse(policy["final_test_reuse_after_failure"])
        self.assertEqual(policy["minimum_50_rule"], "rejected")
        self.assertIn("never outcomes", policy["cut_selection"].lower())
        self.assertIn("pnl", policy["cut_selection"].lower())

    def test_primary_metrics_have_exact_formulas(self) -> None:
        metrics = {item["id"]: item for item in self.protocol["metrics"]}
        self.assertIn("M8-METRIC-BRIER-3C", metrics)
        self.assertIn("M8-METRIC-LOGLOSS-3C", metrics)
        self.assertIn("M8-METRIC-CALIBRATION", metrics)
        self.assertIn("sum_i sum_c", metrics["M8-METRIC-BRIER-3C"]["formula"])
        self.assertIn("1e-15", metrics["M8-METRIC-LOGLOSS-3C"]["formula"])

    def test_uncertainty_is_temporally_blocked_and_reproducible(self) -> None:
        uncertainty = self.protocol["uncertainty_protocol"]
        self.assertEqual(
            uncertainty["method"],
            "paired_UTC_day_block_bootstrap",
        )
        self.assertEqual(uncertainty["resamples"], 2000)
        self.assertEqual(uncertainty["seed"], 20260728)
        self.assertEqual(uncertainty["confidence_level"], 0.95)

    def test_legacy_engine_is_comparator_not_truth(self) -> None:
        models = {item["id"]: item for item in self.protocol["models_to_compare"]}
        legacy = models["M8-COMPARATOR-LEGACY"]
        self.assertFalse(legacy["fit_allowed"])
        self.assertEqual(
            legacy["role"],
            "final_comparator_only_not_ground_truth",
        )

    def test_rules_cannot_receive_manual_coefficients(self) -> None:
        rules = self.protocol["rule_evaluation"]
        self.assertEqual(
            rules["coefficient_source"],
            "development_partition_only",
        )
        self.assertFalse(rules["manual_coefficients_allowed"])
        self.assertTrue(rules["double_counting_check_required"])

    def test_decision_can_explicitly_report_insufficient_evidence(self) -> None:
        states = {
            item["state"] for item in self.protocol["final_decision_states"]
        }
        self.assertEqual(
            states,
            {
                "approved_for_M9_consideration",
                "rejected",
                "return_to_earlier_phase",
                "insufficient_evidence",
            },
        )

    def test_prohibited_actions_prevent_test_peeking(self) -> None:
        prohibited = self.protocol["prohibited_actions"]
        self.assertIn("tune any rule after opening final_test", prohibited)
        self.assertIn(
            "choose chronological cuts from outcomes or PnL",
            prohibited,
        )
        self.assertIn(
            "use legacy score or probability as an outcome label",
            prohibited,
        )

    def test_m9_remains_blocked(self) -> None:
        boundaries = self.protocol["boundaries"]
        self.assertTrue(boundaries["m8_started"])
        self.assertFalse(boundaries["m8_closed"])
        self.assertFalse(boundaries["m9_started"])
        self.assertEqual(boundaries["production_effect"], "none")

    def test_written_artifact_matches_builder(self) -> None:
        written = json.loads(
            m8.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.protocol)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m8_evaluation_protocol.py"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
