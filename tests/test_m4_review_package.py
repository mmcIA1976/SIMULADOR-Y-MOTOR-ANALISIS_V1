from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m4_review_package as m4  # noqa: E402


class M47ReviewPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = m4.build_catalog()

    def test_status_records_owner_approved_m4_closure(self) -> None:
        self.assertEqual(
            self.package["status"],
            "completed_owner_approved",
        )
        scope = self.package["scope"]
        self.assertTrue(scope["m4_closed"])
        self.assertFalse(scope["m5_started"])
        self.assertFalse(scope["production_modified"])
        self.assertFalse(scope["analysis_engine_modified"])

    def test_exact_review_universe_is_preserved(self) -> None:
        scope = self.package["scope"]
        self.assertEqual(scope["rules_reviewed"], 27)
        self.assertEqual(scope["p0_core_rules_reviewed"], 26)
        self.assertEqual(scope["auxiliary_operators_reviewed"], 1)
        self.assertEqual(scope["hypotheses_reviewed"], 15)
        self.assertEqual(scope["combinations_reviewed"], 8)
        self.assertEqual(scope["legacy_elements_reviewed"], 30)
        self.assertEqual(scope["feature_slots_reviewed"], 15)
        self.assertEqual(scope["relations_reviewed"], 16)
        self.assertEqual(scope["dag_nodes_reviewed"], 27)
        self.assertEqual(scope["dag_edges_reviewed"], 32)
        self.assertEqual(scope["invariants_reviewed"], 108)
        self.assertEqual(scope["canonical_families_reviewed"], 17)
        self.assertEqual(tuple(scope["symbols"]), m4.SYMBOLS)
        self.assertEqual(tuple(scope["horizons"]), m4.HORIZONS)
        self.assertEqual(tuple(scope["p0_blocks"]), m4.P0_BLOCKS)

    def test_all_27_rules_pass_complete_contract_audit(self) -> None:
        audit = self.package["rule_audit"]
        self.assertEqual(len(audit), 27)
        self.assertEqual(len({rule["id"] for rule in audit}), 27)
        for rule in audit:
            self.assertGreater(rule["formula_count"], 0)
            self.assertTrue(rule["source_ids"])
            self.assertTrue(rule["has_trace_contract"])
            self.assertTrue(rule["has_refutation_contract"])
            self.assertFalse(rule["probability_effect_authorized"])
            self.assertFalse(rule["production_authorized"])

    def test_all_15_hypotheses_are_linked_once_to_rule_universe(self) -> None:
        hypothesis_ids = {
            item["id"] for item in self.package["hypotheses"]
        }
        linked = {
            rule["predictive_hypothesis_id"]
            for rule in self.package["rule_audit"]
            if rule["predictive_hypothesis_id"]
        }
        self.assertEqual(len(hypothesis_ids), 15)
        self.assertEqual(linked, hypothesis_ids)

    def test_all_combinations_have_operator_source_trace_and_refutation(self) -> None:
        combinations = self.package["combinations"]
        self.assertEqual(len(combinations), 8)
        for item in combinations:
            self.assertTrue(item["has_operator"])
            self.assertTrue(item["has_sources"])
            self.assertTrue(item["has_trace_contract"])
            self.assertTrue(item["has_refutation_contract"])
            self.assertFalse(item["probability_effect_authorized"])
            self.assertFalse(item["production_authorized"])

    def test_technical_and_owner_review_pass(self) -> None:
        review = self.package["technical_review"]
        for key, value in review.items():
            self.assertTrue(value, key)

    def test_owner_approval_record_is_narrow_and_explicit(self) -> None:
        approval = self.package["owner_approval_record"]
        self.assertTrue(approval["approved"])
        self.assertEqual(approval["approved_at"], "2026-07-27")
        self.assertEqual(approval["owner_statement"], "cierra M4")
        self.assertEqual(
            approval["scope"],
            "documentary_and_technical_m4_only",
        )
        self.assertFalse(approval["predictive_validation_claimed"])
        self.assertFalse(approval["profitability_claimed"])
        self.assertFalse(approval["production_authorized"])
        self.assertFalse(approval["m5_start_authorized"])
        self.assertTrue(approval["deferred_work_preserved"])

    def test_owner_approval_meaning_is_not_empirical_validation(self) -> None:
        meaning = self.package["meaning_of_owner_approval"]
        self.assertIn(
            "accept amendment waves 1 and 2 plus final technical integration",
            meaning["does_mean"],
        )
        self.assertIn(
            "rules are empirically validated",
            meaning["does_not_mean"],
        )
        self.assertIn(
            "profitability is established",
            meaning["does_not_mean"],
        )
        self.assertIn(
            "production deployment or automatic trading is authorized",
            meaning["does_not_mean"],
        )

    def test_final_integration_is_embedded_without_production_effect(self) -> None:
        integration = self.package["final_integration"]
        self.assertTrue(integration["dag_acyclic"])
        self.assertEqual(integration["dag_nodes"], 27)
        self.assertEqual(integration["dag_edges"], 32)
        self.assertEqual(integration["invariants"], 108)
        self.assertFalse(
            integration["future_promotion_gate"][
                "production_promotion_authorized"
            ]
        )
    def test_owner_decisions_close_m4_and_preserve_deferred_p2_p4(self) -> None:
        decisions = self.package["owner_decisions"]
        self.assertEqual(len(decisions), 10)
        self.assertEqual(len({item["id"] for item in decisions}), 10)
        self.assertTrue(
            all(
                item["status"] in {
                    "resolved_owner_approved_2026_07_27",
                    "deferred_outside_current_m4_scope_owner_direction",
                }
                for item in decisions
            )
        )
        for decision_id in (
            "M4-OWNER-DECISION-001",
            "M4-OWNER-DECISION-002",
            "M4-OWNER-DECISION-003",
            "M4-OWNER-DECISION-004",
            "M4-OWNER-DECISION-005",
            "M4-OWNER-DECISION-006",
        ):
            self.assertEqual(
                next(
                    item["status"]
                    for item in decisions
                    if item["id"] == decision_id
                ),
                "resolved_owner_approved_2026_07_27",
            )
        self.assertEqual(
            next(
                item["status"]
                for item in decisions
                if item["id"] == "M4-OWNER-P1-ORDER-TYPES"
            ),
            "resolved_owner_approved_2026_07_27",
        )
        for decision_id in (
            "M4-OWNER-P2-PRICE-REFERENCES",
            "M4-OWNER-P3-LIQUIDATION-SEMANTICS",
            "M4-OWNER-P4-EXPIRY-PAYOFF",
        ):
            self.assertEqual(
                next(
                    item["status"]
                    for item in decisions
                    if item["id"] == decision_id
                ),
                "deferred_outside_current_m4_scope_owner_direction",
            )
        self.assertEqual(
            {
                item["id"]
                for item in decisions
                if item["id"].startswith("M4-OWNER-P")
            },
            {
                "M4-OWNER-P1-ORDER-TYPES",
                "M4-OWNER-P2-PRICE-REFERENCES",
                "M4-OWNER-P3-LIQUIDATION-SEMANTICS",
                "M4-OWNER-P4-EXPIRY-PAYOFF",
            },
        )
        self.assertTrue(all(item["acceptance_means"] for item in decisions))

    def test_closure_gate_closes_m4_without_starting_m5(self) -> None:
        gate = self.package["closure_gate"]
        self.assertEqual(
            gate["technical_gate"],
            "passed",
        )
        self.assertEqual(gate["owner_gate"], "passed")
        self.assertTrue(gate["m4_close_authorized"])
        self.assertFalse(gate["m5_start_authorized"])
        self.assertEqual(
            gate["required_final_action"],
            "none_for_m4_closure",
        )
        self.assertEqual(
            gate["next_required_action"],
            "explicit owner authorization to start M5",
        )

    def test_legacy_dispositions_sum_to_30(self) -> None:
        summary = self.package["legacy_disposition_summary"]
        self.assertEqual(sum(summary.values()), 30)
        self.assertEqual(summary["deferred_to_m10"], 1)
        self.assertEqual(
            summary["replaced_by_preregistered_combinations"],
            1,
        )

    def test_known_limits_remain_assigned_to_later_phases(self) -> None:
        limits = {
            item["item"]: item["phase"]
            for item in self.package["known_limits_preserved"]
        }
        self.assertEqual(limits["software_implementation"], "M5")
        self.assertEqual(limits["probability_link_and_calibration"], "M6")
        self.assertEqual(
            limits["mathematical_and_software_verification"],
            "M7",
        )
        self.assertEqual(
            limits["independent_empirical_validation"],
            "M8",
        )
        self.assertEqual(
            limits["grade_and_decision_policy"],
            "after_M8",
        )

    def test_manifest_has_unique_existing_hashed_artifacts(self) -> None:
        manifest = self.package["artifact_manifest"]
        self.assertEqual(
            len(manifest),
            len(m4.GENERATORS)
            + len(m4.M4_CATALOG_PATHS)
            + len(m4.REPORTS)
            + len(m4.OWNER_AUDIT_ARTIFACTS)
            + len(m4.TESTS),
        )
        self.assertEqual(
            len({item["path"] for item in manifest}),
            len(manifest),
        )
        for item in manifest:
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(item["sha256"], m4.file_sha256(path))
            self.assertEqual(item["bytes"], path.stat().st_size)

    def test_production_source_hashes_are_complete(self) -> None:
        records = self.package["production_source_hashes_at_review"]
        self.assertEqual(
            {item["path"] for item in records},
            set(m4.PRODUCTION_FILES),
        )
        for item in records:
            self.assertEqual(
                item["sha256"],
                m4.file_sha256(ROOT / item["path"]),
            )

    def test_reproduction_commands_cover_all_generators_and_tests(self) -> None:
        reproduction = self.package["reproduction"]
        self.assertEqual(
            len(reproduction["generate_in_order"]),
            len(m4.GENERATORS),
        )
        self.assertEqual(
            len(reproduction["check_in_order"]),
            len(m4.GENERATORS),
        )
        for script in m4.GENERATORS:
            self.assertTrue(
                any(script in command for command in reproduction["generate_in_order"])
            )
            self.assertTrue(
                any(script in command for command in reproduction["check_in_order"])
            )
        self.assertIn(
            "tests.test_m4_rule_audit_report",
            reproduction["m4_tests"],
        )
        self.assertIn(
            "tests.test_m4_review_package",
            reproduction["m4_tests"],
        )
        self.assertIn("unittest discover", reproduction["full_tests"])

    def test_owner_has_human_and_structured_rule_audit_surfaces(self) -> None:
        surfaces = self.package["owner_audit_surfaces"]
        self.assertEqual(
            set(surfaces),
            {
                "human_readable_rule_catalog",
                "structured_rule_catalog",
                "integrity_manifest",
                "amendment_result",
                "dag_and_invariant_integration",
                "review_decisions",
                "owner_closure_record",
            },
        )
        for path in surfaces.values():
            self.assertTrue((ROOT / path).is_file(), path)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "build_m4_review_package.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_package_matches_builder(self) -> None:
        path = ROOT / "auditorias_motor" / "paquete_revision_m4_7_v0_3.json"
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written, self.package)


if __name__ == "__main__":
    unittest.main()
