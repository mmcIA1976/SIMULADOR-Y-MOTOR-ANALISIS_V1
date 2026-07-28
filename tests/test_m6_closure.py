from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m6_closure as m6  # noqa: E402


class M66ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = m6.build_package(m6.DEFAULT_COEFFICIENT_PATH)

    def test_owner_order_completes_m6_without_starting_m7(self) -> None:
        approval = self.package["owner_authorization"]
        self.assertTrue(approval["methodology_approved"])
        self.assertTrue(approval["m6_completion_authorized"])
        self.assertFalse(approval["production_authorized"])
        self.assertFalse(approval["m7_start_authorized"])
        self.assertTrue(self.package["scope"]["m6_closed"])
        self.assertFalse(self.package["scope"]["m7_started"])

    def test_complete_probability_architecture_is_registered(self) -> None:
        scope = self.package["scope"]
        self.assertEqual(scope["outcomes"], 3)
        self.assertEqual(scope["formulas_registered"], 8)
        self.assertEqual(scope["m5_rules_partitioned"], 27)
        self.assertEqual(scope["baseline_inputs"], 5)
        self.assertEqual(scope["candidate_covariates"], 12)
        self.assertEqual(scope["active_evidence_coefficients"], 0)

    def test_formula_registry_is_unique_and_layered(self) -> None:
        formulas = self.package["formula_registry"]
        self.assertEqual(len({item["id"] for item in formulas}), 8)
        self.assertEqual(
            {item["layer"] for item in formulas},
            {"first_passage_baseline", "competing_risks"},
        )
        self.assertTrue(all(item["expression"] for item in formulas))

    def test_coefficient_artifact_is_locked_and_has_no_values(self) -> None:
        coefficients = m6.read_json(m6.DEFAULT_COEFFICIENT_PATH)
        self.assertEqual(
            coefficients["status"],
            "locked_no_estimated_coefficients",
        )
        self.assertIsNone(coefficients["coefficients"])
        self.assertFalse(coefficients["manual_coefficients_authorized"])
        self.assertFalse(coefficients["probability_adjustment_active"])
        self.assertFalse(coefficients["production_authorized"])
        self.assertEqual(len(coefficients["candidate_rule_ids"]), 12)

    def test_trace_contract_exposes_every_probability_step(self) -> None:
        trace = self.package["trace_contract"]
        self.assertEqual(trace["production_effect"], "none")
        expected = {
            "source M5 trace hashes",
            "formula IDs",
            "baseline probabilities",
            "interval hazards and cumulative incidence",
            "coefficient artifact status",
            "uncertainty status or scenario envelope",
            "assumptions and limitations",
            "probability mass error",
        }
        self.assertEqual(set(trace["exposes"]), expected)

    def test_case_872_873_is_corrected_without_retrospective_claim(self) -> None:
        historical = self.package["historical_872_873"]
        self.assertEqual(
            historical["legacy_ordering"],
            "P_TP_872_lt_P_TP_873",
        )
        self.assertEqual(
            historical["m6_ordering"],
            "P_TP_872_gt_P_TP_873_for_every_sigma_scenario",
        )
        self.assertFalse(historical["historical_probability_claimed"])

    def test_all_internal_verification_gates_pass_but_m7_remains(self) -> None:
        verification = self.package["verification_summary"]
        for key, value in verification.items():
            self.assertTrue(value, key)
        self.assertTrue(
            verification["m7_independent_verification_still_required"]
        )

    def test_boundaries_make_no_calibration_or_profit_claim(self) -> None:
        boundaries = self.package["boundaries"]
        self.assertEqual(boundaries["manual_points_bonus_penalties"], "none")
        self.assertEqual(boundaries["manual_coefficients"], "none")
        self.assertFalse(boundaries["production_probability_changed"])
        self.assertFalse(boundaries["probabilities_calibrated"])
        self.assertFalse(boundaries["predictive_validity_established"])
        self.assertFalse(boundaries["profitability_established"])
        self.assertFalse(boundaries["m7_replaced"])
        self.assertFalse(boundaries["m8_replaced"])

    def test_m6_modules_are_isolated_from_production_engine(self) -> None:
        for item in self.package["import_isolation_audit"]:
            self.assertEqual(item["forbidden_imports"], [])
            self.assertTrue(item["internal_only"])

    def test_production_hashes_match_m5_close(self) -> None:
        m5 = m6.read_json(m6.M5_CLOSURE_PATH)
        expected = {
            item["path"]: item["sha256"]
            for item in m5["production_source_hashes_at_close"]
        }
        observed = {
            item["path"]: item["sha256"]
            for item in self.package["production_source_hashes_at_close"]
        }
        self.assertEqual(observed, expected)

    def test_manifest_is_unique_complete_and_current(self) -> None:
        manifest = self.package["artifact_manifest"]
        self.assertEqual(len({item["path"] for item in manifest}), len(manifest))
        for item in manifest:
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(item["sha256"], m6.file_sha256(path))
            self.assertEqual(item["bytes"], path.stat().st_size)

    def test_m7_requires_separate_owner_order(self) -> None:
        next_phase = self.package["next_phase"]
        self.assertEqual(next_phase["id"], "M7")
        self.assertFalse(next_phase["started"])
        self.assertTrue(next_phase["requires_separate_owner_order"])
        verification = self.package["verification_commands"]
        self.assertEqual(verification["status"], "passed_2026_07_28")
        self.assertEqual(verification["m6_specific_tests_passed"], 62)
        self.assertEqual(verification["full_suite_tests_passed"], 478)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "build_m6_closure.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_package_matches_builder(self) -> None:
        written = json.loads(
            m6.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.package)


if __name__ == "__main__":
    unittest.main()
