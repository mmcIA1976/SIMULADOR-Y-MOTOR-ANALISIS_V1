from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m5_closure as m5  # noqa: E402


class M56ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = m5.build_package()

    def test_owner_order_completes_m5_without_starting_m6(self) -> None:
        approval = self.package["owner_authorization"]
        self.assertEqual(approval["statement"], "continua y completa M5")
        self.assertTrue(approval["authorized_completion"])
        self.assertFalse(approval["production_authorized"])
        self.assertFalse(approval["m6_start_authorized"])
        self.assertTrue(self.package["scope"]["m5_closed"])
        self.assertFalse(self.package["scope"]["m6_started"])

    def test_exact_rule_formula_and_dag_scope_is_complete(self) -> None:
        scope = self.package["scope"]
        self.assertEqual(scope["rules_implemented"], 27)
        self.assertEqual(scope["formulas_preserved"], 80)
        self.assertEqual(scope["dag_nodes"], 27)
        self.assertEqual(scope["dag_edges"], 32)
        self.assertEqual(scope["canonical_families"], 17)

    def test_every_formula_has_literal_parity_and_executable_test(self) -> None:
        parity = self.package["formula_parity"]
        self.assertEqual(len(parity), 27)
        self.assertEqual(len({item["rule_id"] for item in parity}), 27)
        for item in parity:
            self.assertTrue(item["formula_text_exact"])
            self.assertTrue(item["input_contract_preserved"])
            self.assertTrue(item["evaluator_registered"])
            self.assertTrue(item["test_module"])
            self.assertTrue(item["test_case"])
            self.assertEqual(item["status"], "implemented_and_tested")

    def test_all_108_invariants_have_unique_executable_coverage(self) -> None:
        coverage = self.package["invariant_coverage"]
        self.assertEqual(len(coverage), 108)
        self.assertEqual(len({item["m5_test_id"] for item in coverage}), 108)
        self.assertEqual(
            len({item["m4_invariant_id"] for item in coverage}),
            108,
        )
        self.assertTrue(
            all(
                item["status"] == "mapped_to_executable_tests"
                for item in coverage
            )
        )

    def test_internal_engine_has_no_import_from_production_engine(self) -> None:
        for item in self.package["import_isolation_audit"]:
            self.assertEqual(item["forbidden_production_imports"], [])
            self.assertTrue(item["internal_shadow_isolation"])

    def test_all_legacy_elements_have_zero_m5_effect(self) -> None:
        legacy = self.package["legacy_effect"]
        self.assertEqual(len(legacy), 30)
        self.assertTrue(
            all(item["m5_internal_effect"] == "none" for item in legacy)
        )

    def test_boundaries_make_no_predictive_or_profit_claim(self) -> None:
        boundaries = self.package["boundaries"]
        self.assertEqual(boundaries["production_output_effect"], "none")
        self.assertEqual(boundaries["probability_output_effect"], "none")
        self.assertEqual(boundaries["numeric_weights_or_scores"], "none")
        self.assertFalse(boundaries["predictive_validity_claimed"])
        self.assertFalse(boundaries["profitability_claimed"])
        self.assertFalse(boundaries["m7_verification_replaced"])
        self.assertFalse(boundaries["m8_empirical_validation_replaced"])

    def test_production_hashes_are_unchanged_from_m5_start(self) -> None:
        start = {
            item["path"]: item["sha256"]
            for item in m5.read_json(m5.M5_CONTRACT_PATH)[
                "production_source_hashes_at_start"
            ]
        }
        close = {
            item["path"]: item["sha256"]
            for item in self.package["production_source_hashes_at_close"]
        }
        self.assertEqual(close, start)

    def test_manifest_is_complete_unique_and_current(self) -> None:
        manifest = self.package["artifact_manifest"]
        self.assertTrue(m5.PRODUCTION_ACTIVATION_PATH.is_file())
        self.assertEqual(len({item["path"] for item in manifest}), len(manifest))
        for item in manifest:
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(len(item["sha256"]), 64)

    def test_m6_requires_separate_owner_order(self) -> None:
        next_phase = self.package["next_phase"]
        self.assertEqual(next_phase["id"], "M6")
        self.assertFalse(next_phase["started"])
        self.assertTrue(next_phase["requires_separate_owner_order"])
        verification = self.package["verification"]
        self.assertEqual(verification["status"], "passed_2026_07_27")
        self.assertEqual(verification["m5_specific_tests_passed"], 71)
        self.assertEqual(verification["full_suite_tests_passed"], 416)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "build_m5_closure.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_package_matches_builder(self) -> None:
        written = json.loads(
            m5.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.package)


if __name__ == "__main__":
    unittest.main()
