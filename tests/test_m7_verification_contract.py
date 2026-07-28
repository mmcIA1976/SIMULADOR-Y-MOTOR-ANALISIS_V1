from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m7_verification_contract as m7  # noqa: E402


class M71VerificationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = m7.build_contract()

    def test_owner_order_starts_only_m7(self) -> None:
        authorization = self.contract["owner_authorization"]
        self.assertTrue(authorization["m7_started"])
        self.assertFalse(authorization["m8_started"])
        self.assertFalse(authorization["production_authorized"])

    def test_every_roadmap_workstream_has_one_gate(self) -> None:
        workstreams = self.contract["workstreams"]
        self.assertEqual(len(workstreams), 12)
        self.assertEqual(
            {item["roadmap_item"] for item in workstreams},
            set(range(1, 13)),
        )
        self.assertEqual(len({item["id"] for item in workstreams}), 12)

    def test_all_m7_subphases_are_covered(self) -> None:
        self.assertEqual(
            {item["subphase"] for item in self.contract["workstreams"]},
            {"M7.2", "M7.3", "M7.4", "M7.5", "M7.6", "M7.7"},
        )

    def test_independence_contract_forbids_self_confirmation(self) -> None:
        independence = self.contract["independence_contract"]
        self.assertTrue(independence["oracles_must_not_call_M6_solver"])
        self.assertTrue(
            independence["manual_cases_must_be_recalculated_outside_M6"]
        )
        self.assertTrue(
            independence["property_tests_must_not_copy_expected_M6_outputs"]
        )
        self.assertTrue(
            independence["formula_review_must_map_expression_to_primary_source"]
        )
        self.assertTrue(independence["failures_must_be_recorded_before_correction"])

    def test_coverage_contains_six_pairs_three_horizons_and_two_sides(self) -> None:
        coverage = self.contract["coverage_contract"]
        self.assertEqual(coverage["pairs"], list(m7.SUPPORTED_PAIRS))
        self.assertEqual(coverage["horizons"], list(m7.SUPPORTED_HORIZONS))
        self.assertEqual(coverage["sides"], list(m7.SIDES))
        self.assertEqual(coverage["pair_horizon_side_cells"], 36)
        self.assertEqual(coverage["rule_coverage_cells"], 972)
        self.assertEqual(coverage["frozen_rules"], 27)

    def test_severity_policy_blocks_critical_defects(self) -> None:
        severities = {
            item["severity"]: item
            for item in self.contract["severity_policy"]
        }
        self.assertEqual(
            set(severities),
            {"critical", "high", "medium", "low"},
        )
        self.assertEqual(
            severities["critical"]["closure_policy"],
            "must_be_fixed_and_retested_before_M7_closure",
        )
        self.assertEqual(
            self.contract["closure_gates"]["critical_defects_open"],
            0,
        )

    def test_m6_is_frozen_and_m8_remains_blocked(self) -> None:
        boundaries = self.contract["phase_boundaries"]
        self.assertTrue(boundaries["m6_frozen"])
        self.assertTrue(boundaries["m7_started"])
        self.assertFalse(boundaries["m7_closed"])
        self.assertTrue(boundaries["m8_blocked"])
        self.assertEqual(boundaries["production_effect"], "none")

    def test_no_calibration_or_profitability_claim_enters_m7(self) -> None:
        exclusions = set(self.contract["explicit_exclusions"])
        self.assertIn("no probability calibration", exclusions)
        self.assertIn("no coefficient estimation", exclusions)
        self.assertIn("no profitability claim", exclusions)
        self.assertIn("no use of legacy scores as truth", exclusions)
        self.assertIn("no production activation", exclusions)

    def test_production_hashes_are_inherited_from_m6_close(self) -> None:
        m6 = m7.read_json(m7.M6_CLOSURE_PATH)
        self.assertEqual(
            self.contract["production_source_hashes_frozen"],
            m6["production_source_hashes_at_close"],
        )

    def test_inputs_are_current_and_hashed(self) -> None:
        for item in self.contract["inputs"]:
            path = m7.ROOT / item["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(item["sha256"], m7.file_sha256(path))
            self.assertEqual(item["bytes"], path.stat().st_size)

    def test_written_artifact_matches_builder(self) -> None:
        written = json.loads(
            m7.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.contract)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m7_verification_contract.py"),
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
