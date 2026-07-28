from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_resilience_verification as m7  # noqa: E402


class M76ResilienceVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = m7.build_verification()

    def test_all_fault_injections_are_controlled(self) -> None:
        cases = self.verification["fault_injection_cases"]
        self.assertEqual(len(cases), 12)
        self.assertTrue(all(item["passed"] for item in cases))
        self.assertTrue(
            all(item["unhandled_exception"] is None for item in cases)
        )

    def test_extreme_finite_predictor_remains_evaluated(self) -> None:
        case = next(
            item
            for item in self.verification["fault_injection_cases"]
            if item["name"] == "finite_extreme_predictor"
        )
        self.assertEqual(case["observed_status"], "evaluated_internal_only")

    def test_invalid_or_oversized_counts_block(self) -> None:
        selected = {
            item["name"]: item
            for item in self.verification["fault_injection_cases"]
            if "interval" in item["name"]
        }
        self.assertEqual(len(selected), 4)
        self.assertTrue(
            all(item["observed_status"] == "blocked" for item in selected.values())
        )

    def test_resource_contract_is_explicit(self) -> None:
        contract = self.verification["resource_contract"]
        self.assertEqual(contract["minimum_interval_count"], 1)
        self.assertEqual(
            contract["maximum_interval_count"],
            m7.MAX_INTERVAL_COUNT,
        )
        self.assertTrue(contract["boolean_is_not_integer_count"])
        self.assertTrue(contract["oversized_count_fails_before_iteration"])

    def test_all_performance_buckets_pass(self) -> None:
        benchmarks = self.verification["performance_buckets"]
        self.assertTrue(benchmarks["solver"]["within_budget"])
        self.assertTrue(benchmarks["engine"]["within_budget"])
        self.assertTrue(benchmarks["interval_stress"]["within_budget"])

    def test_defects_are_recorded_and_closed(self) -> None:
        self.assertEqual(
            self.verification["corrected_defects"],
            ["M7-DEFECT-NUMERIC-002", "M7-DEFECT-RESOURCE-003"],
        )
        summary = self.verification["summary"]
        self.assertEqual(summary["critical_defects_open"], 0)
        self.assertEqual(summary["high_defects_open"], 0)

    def test_boundaries_do_not_claim_exchange_sla_or_calibration(self) -> None:
        self.assertIn(
            "Latency budgets are internal engineering limits, not exchange SLA.",
            self.verification["limitations"],
        )
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
                str(ROOT / "build_m7_resilience_verification.py"),
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
