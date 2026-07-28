from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_math_verification as m7  # noqa: E402
from m7_independent_oracle import (  # noqa: E402
    IndependentOracleInputError,
    finite_difference_first_passage,
)


class M72IndependentOracleTests(unittest.TestCase):
    def test_oracle_has_no_m6_import(self) -> None:
        path = ROOT / "m7_independent_oracle.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse([name for name in imported if name.startswith("m6")])

    def test_oracle_preserves_probability_mass(self) -> None:
        result = finite_difference_first_passage(
            tp_log_distance=0.03,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
            spatial_intervals=120,
            time_steps=300,
        )
        self.assertAlmostEqual(
            result.p_tp + result.p_sl + result.p_expiry,
            1.0,
            places=12,
        )
        self.assertTrue(
            all(
                0 <= value <= 1
                for value in (result.p_tp, result.p_sl, result.p_expiry)
            )
        )

    def test_oracle_reflection_swaps_tp_and_sl(self) -> None:
        first = finite_difference_first_passage(
            tp_log_distance=0.02,
            sl_log_distance=0.06,
            sigma_horizon=0.04,
            spatial_intervals=120,
            time_steps=300,
        )
        swapped = finite_difference_first_passage(
            tp_log_distance=0.06,
            sl_log_distance=0.02,
            sigma_horizon=0.04,
            spatial_intervals=120,
            time_steps=300,
        )
        self.assertAlmostEqual(first.p_tp, swapped.p_sl, places=11)
        self.assertAlmostEqual(first.p_sl, swapped.p_tp, places=11)
        self.assertAlmostEqual(first.p_expiry, swapped.p_expiry, places=11)

    def test_oracle_rejects_invalid_inputs(self) -> None:
        with self.assertRaises(IndependentOracleInputError):
            finite_difference_first_passage(
                tp_log_distance=0,
                sl_log_distance=0.05,
                sigma_horizon=0.04,
            )
        with self.assertRaises(IndependentOracleInputError):
            finite_difference_first_passage(
                tp_log_distance=0.03,
                sl_log_distance=0.05,
                sigma_horizon=0.04,
                spatial_intervals=2,
            )


class M72VerificationArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = m7.build_verification()

    def test_all_checks_pass_without_critical_defects(self) -> None:
        summary = self.verification["summary"]
        self.assertEqual(
            summary["checks_passed"],
            summary["checks_total"],
        )
        self.assertEqual(summary["critical_defects_open"], 0)
        self.assertEqual(self.verification["defects"], [])
        self.assertEqual(
            self.verification["corrected_defects"],
            [
                {
                    "id": "M7-DEFECT-CONVERGENCE-001",
                    "status": "corrected_and_retested",
                    "pre_correction_record": m7.artifact_record(
                        m7.PRE_CORRECTION_DEFECT_PATH
                    ),
                    "correction_record": m7.artifact_record(
                        m7.CORRECTION_RECORD_PATH
                    ),
                }
            ],
        )

    def test_independent_oracle_agrees_with_m6_within_tolerance(self) -> None:
        summary = self.verification["summary"]
        self.assertLessEqual(
            summary["max_independent_oracle_error"],
            m7.ORACLE_TOLERANCE,
        )
        self.assertEqual(
            len(self.verification["oracle_comparisons"]),
            len(m7.ORACLE_CASES),
        )

    def test_adversarial_grid_covers_extreme_scales(self) -> None:
        summary = self.verification["summary"]
        self.assertEqual(summary["adversarial_grid_cases"], 175)
        self.assertLessEqual(summary["max_probability_mass_error"], 1e-12)

    def test_no_empirical_or_production_claim_is_made(self) -> None:
        boundaries = self.verification["boundaries"]
        self.assertFalse(boundaries["probability_calibration_performed"])
        self.assertFalse(boundaries["empirical_performance_measured"])
        self.assertEqual(boundaries["production_effect"], "none")
        self.assertFalse(boundaries["m8_started"])
        commands = self.verification["verification_commands"]
        self.assertEqual(commands["status"], "passed_2026_07_28")
        self.assertEqual(commands["m7_tests_passed"], 22)
        self.assertEqual(commands["full_suite_tests_passed"], 501)

    def test_written_artifact_matches_builder(self) -> None:
        written = json.loads(
            m7.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.verification)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m7_math_verification.py"),
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
