from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_data_verification as m7  # noqa: E402
from m7_data_gate import validate_pretrade_snapshot  # noqa: E402


class M73DataVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = m7.build_verification()

    def test_valid_snapshot_is_accepted(self) -> None:
        valid = self.verification["valid_case"]
        self.assertEqual(valid["status"], "accepted")
        self.assertEqual(valid["reason_codes"], [])

    def test_every_invalid_case_is_blocked_with_expected_reason(self) -> None:
        cases = self.verification["invalid_cases"]
        self.assertEqual(len(cases), 14)
        self.assertTrue(all(item["passed"] for item in cases))
        self.assertTrue(all(item["status"] == "blocked" for item in cases))

    def test_invalid_data_never_emits_probability_or_neutral_fallback(self) -> None:
        summary = self.verification["summary"]
        self.assertEqual(summary["neutral_fallbacks"], 0)
        self.assertEqual(summary["probabilities_emitted_for_invalid_data"], 0)
        self.assertTrue(
            all(
                not item["probabilities_emitted"]
                for item in self.verification["invalid_cases"]
            )
        )

    def test_invalid_analysis_identity_fails_closed(self) -> None:
        result = validate_pretrade_snapshot(
            analysis_at_ms=None,
            symbol="",
            required_contract_ids=[],
            observations=[],
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("invalid_analysis_at", result.reason_codes)
        self.assertIn("invalid_symbol", result.reason_codes)
        self.assertIn("required_contracts_empty", result.reason_codes)

    def test_unsupported_contract_fails_closed(self) -> None:
        result = validate_pretrade_snapshot(
            analysis_at_ms=m7.ANALYSIS_AT,
            symbol="BTCUSDT",
            required_contract_ids=["M3-DATA-999"],
            observations=[],
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("unsupported_required_contract_id", result.reason_codes)

    def test_production_and_m8_boundaries_remain_closed(self) -> None:
        boundaries = self.verification["boundaries"]
        self.assertTrue(boundaries["gate_is_internal_only"])
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
                str(ROOT / "build_m7_data_verification.py"),
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
