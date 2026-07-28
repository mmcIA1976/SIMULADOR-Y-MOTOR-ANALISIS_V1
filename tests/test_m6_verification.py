from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m6_verification as m6  # noqa: E402


class M65VerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = m6.build_verification()

    def test_historical_case_preserves_exact_plan_and_legacy_values(self) -> None:
        cases = self.verification["historical_case_872_873"]["cases"]
        by_id = {item["recommendation_id"]: item for item in cases}
        self.assertEqual(by_id[872]["entry"], 63942.4)
        self.assertEqual(by_id[872]["take_profit"], 63200.0)
        self.assertEqual(by_id[872]["legacy_p_tp"], 0.5389)
        self.assertEqual(by_id[873]["entry"], 63920.2)
        self.assertEqual(by_id[873]["take_profit"], 63115.0)
        self.assertEqual(by_id[873]["legacy_p_tp"], 0.5889)
        self.assertLess(
            by_id[872]["tp_log_distance"],
            by_id[873]["tp_log_distance"],
        )

    def test_m6_corrects_872_873_ordering_across_sigma_grid(self) -> None:
        historical = self.verification["historical_case_872_873"]
        self.assertEqual(len(historical["m6_results"]), 6)
        for row in historical["m6_results"]:
            self.assertEqual(row["ordering"], "872_gt_873")
            self.assertGreater(
                row["probabilities"]["872"]["p_tp"],
                row["probabilities"]["873"]["p_tp"],
            )

    def test_historical_case_does_not_claim_reconstructed_probability(self) -> None:
        interpretation = self.verification[
            "historical_case_872_873"
        ]["interpretation"]
        self.assertIn("not reconstructed M5 volatility", interpretation)
        self.assertIn("not a historical probability claim", interpretation)

    def test_probability_grid_has_mass_and_bounds(self) -> None:
        properties = self.verification["property_results"]
        self.assertEqual(properties["mass_grid_cases"], 125)
        self.assertLessEqual(properties["max_mass_error"], 1e-12)
        self.assertTrue(properties["all_probabilities_in_unit_interval"])

    def test_farther_tp_is_monotone_and_continuity_passes(self) -> None:
        properties = self.verification["property_results"]
        rows = properties["farther_tp_monotonic_rows"]
        probabilities = [item["p_tp"] for item in rows]
        self.assertEqual(probabilities, sorted(probabilities, reverse=True))
        self.assertTrue(properties["farther_tp_never_increases_p_tp"])
        self.assertTrue(properties["continuity_passed"])
        self.assertLess(
            properties["continuity_max_probability_delta"],
            1e-5,
        )

    def test_verification_does_not_replace_m7_m8_or_calibration(self) -> None:
        claims = self.verification["claims"]
        self.assertTrue(
            claims["software_and_basic_mathematical_properties_verified"]
        )
        self.assertFalse(claims["brownian_model_empirically_validated"])
        self.assertFalse(claims["probabilities_calibrated"])
        self.assertFalse(claims["profitability_established"])
        self.assertFalse(claims["m7_replaced"])
        self.assertFalse(claims["m8_replaced"])
        self.assertFalse(claims["production_authorized"])

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m6_verification.py"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_verification_matches_builder(self) -> None:
        written = json.loads(
            m6.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.verification)


if __name__ == "__main__":
    unittest.main()
