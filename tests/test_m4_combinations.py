from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m4_combinations as m4  # noqa: E402


class M46CombinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = m4.build_catalog()

    def test_reconciles_exact_upstream_universe(self) -> None:
        summary = self.catalog["summary"]
        self.assertEqual(summary["rules_reconciled"], 27)
        self.assertEqual(summary["hypotheses_reconciled"], 15)
        self.assertEqual(summary["legacy_reconciled"], 30)
        self.assertEqual(summary["seed_families_reconciled"], 17)
        self.assertEqual(summary["p0_blocks_reconciled"], 12)
        self.assertEqual(summary["unresolved_legacy_elements"], 0)

    def test_all_upstream_rule_ids_are_unique(self) -> None:
        ids = [item["id"] for item in self.catalog["upstream_rules"]]
        self.assertEqual(len(ids), 27)
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_upstream_hypothesis_ids_are_unique(self) -> None:
        ids = [item["id"] for item in self.catalog["upstream_hypotheses"]]
        self.assertEqual(len(ids), 15)
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_legacy_element_has_one_final_disposition(self) -> None:
        rows = self.catalog["legacy_reconciliation"]
        ids = [row["current_rule_id"] for row in rows]
        self.assertEqual(len(ids), 30)
        self.assertEqual(len(ids), len(set(ids)))
        allowed = {
            "reconciled_to_formal_cards_without_legacy_effect",
            "retired_without_replacement",
            "deferred_to_m10",
            "replaced_by_preregistered_combinations",
        }
        self.assertTrue(all(row["final_status"] in allowed for row in rows))

    def test_contradiction_penalty_is_replaced_not_renamed(self) -> None:
        row = next(
            row
            for row in self.catalog["legacy_reconciliation"]
            if row["current_rule_id"] == "SCORE-CONTRADICTION_PENALTY"
        )
        self.assertEqual(
            row["final_status"],
            "replaced_by_preregistered_combinations",
        )
        self.assertEqual(row["formal_rule_ids"], [])
        self.assertFalse(row["legacy_points_or_weights_authorized"])

    def test_learning_adjustments_remain_retired(self) -> None:
        rows = {
            row["current_rule_id"]: row
            for row in self.catalog["legacy_reconciliation"]
        }
        for rule_id in (
            "SCORE-RISK_CALIBRATION_TP_ADJUSTMENT",
            "SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT",
        ):
            self.assertEqual(
                rows[rule_id]["final_status"],
                "retired_without_replacement",
            )

    def test_feature_slots_have_one_canonical_representation(self) -> None:
        slots = self.catalog["feature_slots"]
        self.assertEqual(len(slots), 15)
        self.assertEqual(len({slot["id"] for slot in slots}), 15)
        for slot in slots:
            self.assertTrue(slot["canonical_values"])
            self.assertTrue(slot["excluded_as_extra_votes"])
            self.assertTrue(slot["reason"])

    def test_exact_path_redundancies_are_excluded(self) -> None:
        slot = next(
            slot
            for slot in self.catalog["feature_slots"]
            if slot["id"] == "M4-SLOT-PATH-STRUCTURE"
        )
        self.assertIn("E_H=abs(SE_H)", slot["excluded_as_extra_votes"])
        self.assertIn("MTF agreement label", slot["excluded_as_extra_votes"])
        self.assertNotIn("E_H", slot["canonical_values"])

    def test_relation_matrix_covers_core_double_counts(self) -> None:
        relations = {
            item["id"]: item for item in self.catalog["relation_matrix"]
        }
        self.assertEqual(len(relations), 16)
        self.assertEqual(
            relations["M4-REL-002"]["relation"],
            "exact_redundancy",
        )
        self.assertEqual(
            relations["M4-REL-008"]["relation"],
            "container_redundancy",
        )
        self.assertEqual(
            relations["M4-REL-009"]["relation"],
            "overlapping_execution_cost",
        )
        self.assertEqual(
            relations["M4-REL-012"]["relation"],
            "separate_layers",
        )
        self.assertEqual(
            relations["M4-REL-015"]["relation"],
            "shared_raw_history_different_roles",
        )
        self.assertEqual(
            relations["M4-REL-016"]["relation"],
            "exact_redundancy",
        )

    def test_basis_modes_are_mutually_exclusive(self) -> None:
        slot = next(
            slot
            for slot in self.catalog["feature_slots"]
            if slot["id"] == "M4-SLOT-BASIS"
        )
        self.assertEqual(len(slot["canonical_values"]), 2)
        combination = next(
            item
            for item in self.catalog["preregistered_combinations"]
            if item["id"] == "M4-COMB-DERIVATIVES-001"
        )
        self.assertIn(
            "exactly one basis_mode",
            combination["mutually_exclusive_or_duplicate_inputs"],
        )

    def test_combinations_are_complete_and_not_authorized(self) -> None:
        combinations = self.catalog["preregistered_combinations"]
        self.assertEqual(len(combinations), 8)
        for item in combinations:
            self.assertTrue(item["operator_and_order"])
            self.assertTrue(item["activation_and_block_conditions"])
            self.assertTrue(item["null_or_refutation_statement"])
            self.assertFalse(item["direct_probability_effect_authorized"])
            self.assertFalse(item["numeric_weight_authorized"])
            self.assertFalse(item["production_authorized"])
            self.assertFalse(item["m6_model_authorized"])

    def test_combinations_have_sources_trace_and_refutation(self) -> None:
        required = (
            "source_and_exact_supported_claim",
            "claims_not_supported_by_source",
            "double_counting_control",
            "missing_data_behavior",
            "trace_output",
            "null_or_refutation_statement",
            "refutation_suspension_or_withdrawal",
            "lifecycle_status",
        )
        for item in self.catalog["preregistered_combinations"]:
            for field in required:
                self.assertTrue(item[field], f"{item['id']}:{field}")

    def test_all_pairs_and_horizons_are_preserved(self) -> None:
        for item in self.catalog["preregistered_combinations"]:
            self.assertEqual(tuple(item["symbols"]), m4.SYMBOLS)
            self.assertEqual(tuple(item["horizons"]), m4.HORIZONS)

    def test_interactions_follow_strong_hierarchy(self) -> None:
        combinations = {
            item["id"]: item
            for item in self.catalog["preregistered_combinations"]
        }
        structure = " ".join(
            combinations["M4-COMB-STRUCTURE-001"]["operator_and_order"]
        )
        self.assertIn("q_RV", structure)
        self.assertIn("SE_H", structure)
        self.assertIn("q_RV*SE_H", structure)
        flow = " ".join(
            combinations["M4-COMB-FLOW-001"]["operator_and_order"]
        )
        self.assertIn("ATI_H", flow)
        self.assertIn("ATI_H*SE_H", flow)
        self.assertIn("ATI_H*q_RV", flow)
        for combination_id in (
            "M4-COMB-STRUCTURE-001",
            "M4-COMB-FLOW-001",
            "M4-COMB-PRICE-OI-001",
            "M4-COMB-DERIVATIVES-001",
        ):
            self.assertTrue(
                any(
                    "strong hierarchy" in condition
                    for condition in combinations[combination_id][
                        "activation_and_block_conditions"
                    ]
                )
            )

    def test_pending_tree_separates_activation_from_outcomes(self) -> None:
        item = next(
            item
            for item in self.catalog["preregistered_combinations"]
            if item["id"] == "M4-COMB-PENDING-TREE-001"
        )
        formula = " ".join(item["operator_and_order"])
        self.assertIn("P(no_entry)=1-P(activate)", formula)
        self.assertIn("P(k)=P(activate)*P(k|activate)", formula)
        self.assertNotIn("P(TP)+P(activate)", formula)

    def test_execution_and_exposure_are_absent_from_market_combination(self) -> None:
        full = next(
            item
            for item in self.catalog["preregistered_combinations"]
            if item["id"] == "M4-COMB-FULL-MARKET-001"
        )
        forbidden = {
            "M4-SLOT-CURRENT-EXECUTION",
            "M4-SLOT-FEES",
            "M4-SLOT-FUNDING-CASHFLOW",
            "M4-SLOT-EXPOSURE",
            "M4-SLOT-ECONOMIC-EVALUATION",
        }
        self.assertTrue(forbidden.isdisjoint(full["parent_slots"]))
        operator = " ".join(full["operator_and_order"])
        self.assertIn("ordered_unique", operator)
        self.assertIn("main or interaction", operator)

    def test_economic_combination_occurs_after_probability(self) -> None:
        item = next(
            item
            for item in self.catalog["preregistered_combinations"]
            if item["id"] == "M4-COMB-ECONOMIC-EVALUATION-001"
        )
        self.assertEqual(item["layer"], "economic_evaluation")
        self.assertIn(
            "M6 coherent probabilities",
            item["activation_and_block_conditions"],
        )
        self.assertIn(
            "execution and leverage cannot enter market probability",
            item["mutually_exclusive_or_duplicate_inputs"],
        )

    def test_all_12_p0_blocks_are_covered_exactly(self) -> None:
        coverage = self.catalog["p0_block_coverage"]
        self.assertEqual(
            {item["block"] for item in coverage},
            set(m4.P0_BLOCKS),
        )
        known = {item["id"] for item in self.catalog["upstream_rules"]}
        for block in coverage:
            self.assertTrue(block["rules"])
            self.assertTrue(set(block["rules"]).issubset(known))

    def test_probability_and_decision_work_remains_assigned_later(self) -> None:
        unresolved = {
            item["item"]: item["phase"]
            for item in self.catalog["unresolved_for_later_phases"]
        }
        self.assertEqual(unresolved["software_implementation"], "M5")
        self.assertEqual(unresolved["probability_link_and_calibration"], "M6")
        self.assertEqual(
            unresolved["independent_empirical_validation"],
            "M8",
        )
        self.assertEqual(
            unresolved["grade_and_decision_policy"],
            "after_M8",
        )

    def test_governance_forbids_post_result_combination_search(self) -> None:
        governance = self.catalog["governance_contract"]
        self.assertFalse(governance["combination_search_after_results_allowed"])
        self.assertFalse(governance["probability_model_defined"])
        self.assertFalse(governance["weights_defined"])
        self.assertFalse(governance["promotion_threshold_defined"])

    def test_m46_does_not_modify_production_or_start_m5(self) -> None:
        scope = self.catalog["scope"]
        self.assertFalse(scope["production_modified"])
        self.assertFalse(scope["analysis_engine_modified"])
        self.assertFalse(scope["learning_engine_used"])
        self.assertFalse(scope["m5_started"])
        self.assertEqual(scope["m4_next_subphase"], "M4.7")

    def test_sources_separate_support_from_transfer_limits(self) -> None:
        for source in self.catalog["sources"]:
            self.assertTrue(source["supported_claim"])
            self.assertTrue(source["does_not_support"])

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "build_m4_combinations.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_catalog_matches_builder(self) -> None:
        path = (
            ROOT
            / "auditorias_motor"
            / "catalogo_combinaciones_reconciliacion_m4_6_v0_2.json"
        )
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written, self.catalog)


if __name__ == "__main__":
    unittest.main()
