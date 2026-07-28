from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m4_final_integration as m4  # noqa: E402


class M47FinalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = m4.build_catalog()

    def test_dag_contains_exactly_27_unique_nodes(self) -> None:
        nodes = self.catalog["rule_dag"]["nodes"]
        self.assertEqual(len(nodes), 27)
        self.assertEqual(len({node["id"] for node in nodes}), 27)
        self.assertEqual(self.catalog["scope"]["p0_core_rules"], 26)
        self.assertEqual(self.catalog["scope"]["auxiliary_operators"], 1)

    def test_dag_is_acyclic_and_order_respects_every_edge(self) -> None:
        dag = self.catalog["rule_dag"]
        self.assertTrue(dag["acyclic"])
        order = {rule_id: index for index, rule_id in enumerate(
            dag["topological_order"]
        )}
        self.assertEqual(len(order), 27)
        for edge in dag["edges"]:
            self.assertLess(order[edge["from"]], order[edge["to"]])

    def test_every_core_rule_has_one_canonical_family(self) -> None:
        assignments = self.catalog["canonical_family_assignment"]
        self.assertEqual(len(assignments), 26)
        self.assertEqual(
            len({item["rule_id"] for item in assignments}),
            26,
        )
        self.assertTrue(all(item["assignment_count"] == 1 for item in assignments))
        self.assertTrue(
            all(
                not item["additive_duplicate_route_authorized"]
                for item in assignments
            )
        )

    def test_auxiliary_smoother_is_not_an_evidence_vote(self) -> None:
        node = next(
            node
            for node in self.catalog["rule_dag"]["nodes"]
            if node["id"] == "M4-RULE-EXPONENTIAL-SMOOTHER-001"
        )
        self.assertEqual(node["card_role"], "auxiliary_operator")
        self.assertIsNone(node["canonical_family"])
        self.assertFalse(node["additive_vote_authorized"])

    def test_basis_inputs_are_mutually_exclusive_alternatives(self) -> None:
        group = self.catalog["rule_dag"]["alternative_input_groups"][0]
        self.assertEqual(len(group["members"]), 2)
        self.assertFalse(group["simultaneous_additive_use_authorized"])
        basis_edges = [
            edge
            for edge in self.catalog["rule_dag"]["edges"]
            if edge["relation"] == "alternative_basis_input"
        ]
        self.assertEqual(len(basis_edges), 2)

    def test_every_declared_invariant_has_stable_future_test(self) -> None:
        matrix = self.catalog["invariant_matrix"]
        self.assertTrue(matrix)
        self.assertEqual(len({item["id"] for item in matrix}), len(matrix))
        self.assertEqual(
            len({item["m5_required_test_id"] for item in matrix}),
            len(matrix),
        )
        for item in matrix:
            self.assertTrue(item["statement"])
            self.assertTrue(item["m4_reference_test_module"])
            self.assertEqual(
                item["m5_production_gate_status"],
                "pending_m5_implementation",
            )

    def test_all_15_hypotheses_link_to_one_origin_rule(self) -> None:
        inventory = self.catalog["hypothesis_inventory"]
        self.assertEqual(len(inventory), 15)
        self.assertEqual(len({item["id"] for item in inventory}), 15)
        self.assertTrue(
            all(not item["production_weight_authorized"] for item in inventory)
        )

    def test_future_promotion_gate_has_no_invented_threshold(self) -> None:
        gate = self.catalog["future_promotion_gate"]
        self.assertEqual(gate["id"], "M8-GATE-RULE-PROMOTION-001")
        self.assertFalse(gate["empirical_thresholds_defined"])
        self.assertFalse(gate["production_promotion_authorized"])

    def test_operational_detours_are_explicitly_deferred(self) -> None:
        deferred = set(self.catalog["deferred_outside_current_scope"])
        self.assertEqual(
            deferred,
            {
                "pending_order_automation",
                "analysis_revalidation_policy",
                "automatic_time_expiry_execution",
                "production_first_passage_correction",
            },
        )

    def test_no_probability_weight_or_production_is_authorized(self) -> None:
        assertions = self.catalog["integration_assertions"]
        self.assertEqual(assertions["probability_weights_authorized"], 0)
        self.assertEqual(assertions["production_rules_authorized"], 0)
        self.assertFalse(self.catalog["scope"]["production_modified"])
        self.assertFalse(self.catalog["scope"]["m4_closed"])
        self.assertFalse(self.catalog["scope"]["m5_started"])

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m4_final_integration.py"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_catalog_matches_builder(self) -> None:
        written = json.loads(
            m4.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.catalog)


if __name__ == "__main__":
    unittest.main()
