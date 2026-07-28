from __future__ import annotations

import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_trace_verification as m7  # noqa: E402
from m6_engine import run_internal_probability_analysis  # noqa: E402
from m7_trace_audit import (  # noqa: E402
    explain_probability_result,
    verify_result_integrity,
)


class M75TraceVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = m7.build_verification()

    def test_sample_is_predeclared_and_complete(self) -> None:
        self.assertTrue(
            self.verification["sample_predeclared_before_execution"]
        )
        self.assertEqual(
            len(self.verification["samples"]),
            len(m7.PREDECLARED_CASES),
        )

    def test_every_sample_is_reproducible_and_explained(self) -> None:
        samples = self.verification["samples"]
        self.assertTrue(all(item["reproducible"] for item in samples))
        self.assertTrue(all(item["explained"] for item in samples))
        self.assertTrue(all(not item["integrity_issues"] for item in samples))

    def test_manual_oracle_comparison_stays_within_limit(self) -> None:
        self.assertLessEqual(
            self.verification["summary"]["max_independent_oracle_error"],
            m7.ORACLE_LIMIT,
        )

    def test_872_873_ordering_is_correct(self) -> None:
        comparison = self.verification["operation_872_873"]
        self.assertTrue(comparison["passed"])
        self.assertEqual(comparison["ordering"], "P_TP_872_gt_P_TP_873")

    def test_tampering_breaks_hash_mass_and_explanation(self) -> None:
        tamper = self.verification["tamper_test"]
        self.assertTrue(tamper["detected"])
        self.assertTrue(tamper["explanation_blocked"])
        self.assertIn("result_hash_mismatch", tamper["issues"])
        self.assertIn("probability_mass_invalid", tamper["issues"])

    def test_direct_trace_audit_detects_modified_limitations(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="direct-tamper",
            m5_analysis=m7.m5_analysis(m7.PREDECLARED_CASES[2]),
            executed_at=m7.FIXED_TIME,
        )
        modified = deepcopy(result)
        modified["trace"]["limitations"] = []
        self.assertIn("result_hash_mismatch", verify_result_integrity(modified))
        self.assertEqual(
            explain_probability_result(modified)["status"],
            "blocked",
        )

    def test_boundaries_do_not_claim_calibration(self) -> None:
        boundaries = self.verification["boundaries"]
        self.assertEqual(boundaries["production_effect"], "none")
        self.assertFalse(boundaries["calibration_performed"])
        self.assertFalse(boundaries["m8_started"])

    def test_written_artifact_matches_builder(self) -> None:
        written = json.loads(
            m7.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.verification)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m7_trace_verification.py"),
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
