from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_coverage_verification as m7  # noqa: E402


class M74CoverageVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = m7.build_verification()

    def test_registry_is_exact_across_m4_m5_m6_and_code(self) -> None:
        self.assertTrue(self.verification["registry_exact"])

    def test_matrix_contains_exactly_972_unique_cells(self) -> None:
        matrix = self.verification["matrix"]
        keys = {
            (
                item["pair"],
                item["horizon"],
                item["side"],
                item["rule_id"],
            )
            for item in matrix
        }
        self.assertEqual(len(matrix), 972)
        self.assertEqual(len(keys), 972)
        self.assertTrue(
            all(item["coverage_status"] == "contract_covered" for item in matrix)
        )

    def test_all_36_runtime_cells_are_normalized_and_pass(self) -> None:
        cells = self.verification["runtime_cells"]
        self.assertEqual(len(cells), 36)
        self.assertTrue(all(item["passed"] for item in cells))
        self.assertTrue(
            all(
                abs(sum(item["probabilities"].values()) - 1.0) <= 1e-12
                for item in cells
            )
        )

    def test_cross_pair_and_side_normalization_is_exact(self) -> None:
        self.assertTrue(
            all(
                item["max_reference_error"] <= 1e-12
                for item in self.verification["runtime_cells"]
            )
        )

    def test_no_double_counting_or_manual_weight_is_active(self) -> None:
        interactions = self.verification["interactions"]
        self.assertFalse(interactions["duplicate_dag_edges"])
        self.assertTrue(interactions["candidate_ids_unique"])
        self.assertTrue(interactions["coefficient_artifact_candidate_match"])
        self.assertEqual(interactions["active_coefficients"], 0)
        self.assertEqual(interactions["manual_weights"], 0)
        self.assertFalse(interactions["double_counting_detected"])
        self.assertTrue(
            all(
                item["additive_probability_votes"] == 0
                for item in interactions["canonical_families"]
            )
        )

    def test_boundaries_do_not_claim_empirical_validation(self) -> None:
        boundaries = self.verification["boundaries"]
        self.assertEqual(boundaries["production_effect"], "none")
        self.assertFalse(boundaries["calibration_performed"])
        self.assertFalse(boundaries["m8_started"])
        self.assertIn(
            "Contract coverage is not empirical predictive validation.",
            self.verification["limitations"],
        )

    def test_written_artifact_matches_builder(self) -> None:
        written = json.loads(
            m7.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.verification)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m7_coverage_verification.py"),
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
