from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_closure as m7  # noqa: E402


class M77ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = m7.build_package()

    def test_owner_authorizes_m7_close_only(self) -> None:
        authorization = self.package["owner_authorization"]
        self.assertTrue(authorization["m7_completion_authorized"])
        self.assertFalse(authorization["m8_start_authorized"])
        self.assertFalse(authorization["production_authorized"])

    def test_all_12_workstreams_are_completed(self) -> None:
        self.assertEqual(
            self.package["scope"]["roadmap_workstreams_completed"],
            12,
        )
        self.assertTrue(self.package["scope"]["m7_closed"])
        self.assertFalse(self.package["scope"]["m8_started"])

    def test_coverage_is_complete(self) -> None:
        scope = self.package["scope"]
        self.assertEqual(scope["pairs_covered"], 6)
        self.assertEqual(scope["horizons_covered"], 3)
        self.assertEqual(scope["sides_covered"], 2)
        self.assertEqual(scope["rules_covered"], 27)
        self.assertEqual(scope["coverage_cells"], 972)
        self.assertEqual(scope["runtime_cells"], 36)

    def test_formula_registry_exactly_matches_runtime_trace(self) -> None:
        review = self.package["formula_review"]
        self.assertTrue(review["exact_match"])
        self.assertEqual(
            review["registered_formula_ids"],
            review["trace_formula_ids"],
        )
        self.assertEqual(len(review["registered_formula_ids"]), 8)
        self.assertTrue(
            all(item["sources_present"] for item in review["reviews"])
        )

    def test_project_specific_transform_is_not_misrepresented(self) -> None:
        project_specific = [
            item
            for item in self.package["formula_review"]["reviews"]
            if item["exact_project_specific_transform"]
        ]
        self.assertEqual(len(project_specific), 1)
        self.assertIn("limitation", project_specific[0])

    def test_reviewed_modules_are_isolated_and_deterministic(self) -> None:
        review = self.package["code_review"]
        self.assertTrue(review["all_passed"])
        for item in review["module_audits"]:
            self.assertEqual(item["forbidden_production_imports"], [])
            self.assertEqual(item["random_calls"], [])
            self.assertTrue(item["passed"])

    def test_all_discovered_defects_are_corrected(self) -> None:
        defects = self.package["defect_register"]
        self.assertEqual(
            defects["corrected"],
            [
                "M7-DEFECT-CONVERGENCE-001",
                "M7-DEFECT-NUMERIC-002",
                "M7-DEFECT-RESOURCE-003",
            ],
        )
        self.assertEqual(defects["critical_open"], 0)
        self.assertEqual(defects["high_open"], 0)

    def test_every_remaining_limitation_is_declared(self) -> None:
        limitations = self.package["declared_limitations"]
        self.assertEqual(len(limitations), 6)
        self.assertEqual(len({item["id"] for item in limitations}), 6)
        self.assertTrue(all(item["statement"] for item in limitations))

    def test_closure_gates_all_pass(self) -> None:
        gates = self.package["closure_gates"]
        self.assertTrue(gates["all_12_workstreams_completed"])
        self.assertEqual(gates["critical_defects_open"], 0)
        self.assertEqual(gates["high_defects_open"], 0)
        self.assertTrue(gates["all_remaining_limitations_declared"])
        self.assertTrue(gates["production_unchanged"])
        self.assertTrue(gates["owner_approval_present"])
        self.assertTrue(gates["passed"])

    def test_no_calibration_profit_or_production_claim(self) -> None:
        boundaries = self.package["boundaries"]
        self.assertFalse(boundaries["probabilities_calibrated"])
        self.assertFalse(boundaries["predictive_validity_established"])
        self.assertFalse(boundaries["profitability_established"])
        self.assertFalse(boundaries["coefficients_estimated"])
        self.assertEqual(boundaries["production_effect"], "none")
        self.assertFalse(boundaries["m8_started"])

    def test_production_hashes_match_m6_close(self) -> None:
        m6 = m7.read_json(m7.M6_CLOSURE_PATH)
        expected = {
            item["path"]: item["sha256"]
            for item in m6["production_source_hashes_at_close"]
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
            self.assertEqual(item["sha256"], m7.file_sha256(path))
            self.assertEqual(item["bytes"], path.stat().st_size)

    def test_m8_requires_separate_owner_order(self) -> None:
        next_phase = self.package["next_phase"]
        self.assertEqual(next_phase["id"], "M8")
        self.assertFalse(next_phase["started"])
        self.assertTrue(next_phase["requires_separate_owner_order"])
        verification = self.package["verification_commands"]
        self.assertEqual(verification["status"], "passed_2026_07_28")
        self.assertEqual(verification["m7_specific_tests_passed"], 71)
        self.assertEqual(verification["full_suite_tests_passed"], 552)

    def test_written_artifact_matches_builder(self) -> None:
        written = json.loads(
            m7.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.package)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "build_m7_closure.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
