import unittest

from build_m1_rule_decisions import BLOCKS, CONTRACT_ONLY_IDS, build_matrix


class M1RuleDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_matrix()
        cls.decisions = cls.payload["decisions"]

    def test_reconciles_productive_and_contractual_universe(self):
        reconciliation = self.payload["reconciliation"]
        self.assertEqual(reconciliation["source_elements"], 86)
        self.assertEqual(reconciliation["current_production_elements"], 82)
        self.assertEqual(reconciliation["contract_infrastructure_elements"], 4)
        self.assertEqual(reconciliation["decided_elements"], 86)
        self.assertEqual(reconciliation["unique_ids"], 86)

    def test_contract_only_ids_are_exact_and_not_productive(self):
        actual = {
            item["id"]
            for item in self.decisions
            if item["origin"] == "contract_infrastructure_only"
        }
        self.assertEqual(actual, CONTRACT_ONLY_IDS)

    def test_every_rule_has_blocks_decision_action_and_route(self):
        for item in self.decisions:
            with self.subTest(rule_id=item["id"]):
                self.assertTrue(item["block_ids"])
                self.assertTrue(item["m1_decision"])
                self.assertTrue(item["required_action"])
                self.assertTrue(item["current_route"])
                self.assertTrue(item["implementation_refs"])
                self.assertTrue(item["initial_action_phase"])
                self.assertTrue(item["replacement_phase"])
                self.assertFalse(item["direct_probability_authorized"])
                self.assertFalse(item["production_modified_in_m1"])

    def test_all_34_blocks_are_explicit(self):
        coverage = self.payload["block_coverage"]
        self.assertEqual(len(coverage), 34)
        self.assertEqual({item["id"] for item in coverage}, set(BLOCKS))
        for item in coverage:
            with self.subTest(block_id=item["id"]):
                self.assertIn(
                    item["m1_status"],
                    {
                        "existing_elements_decided",
                        "no_current_element_explicitly_recorded",
                    },
                )

    def test_no_current_predictive_rule_is_authorized(self):
        self.assertEqual(
            self.payload["summary"]["direct_probability_authorized"],
            0,
        )
        for item in self.decisions:
            self.assertFalse(item["direct_probability_authorized"])

    def test_current_adjustments_are_removed_before_replacement(self):
        for item in self.decisions:
            if item["current_kind"] in {
                "active_predictive_adjustment",
                "internal_empirical_gate",
            }:
                with self.subTest(rule_id=item["id"]):
                    self.assertEqual(item["initial_action_phase"], "M5")

    def test_m4_contains_only_rules_with_a_p0_block(self):
        for item in self.decisions:
            if item["replacement_phase"] == "M4":
                with self.subTest(rule_id=item["id"]):
                    self.assertIn("P0", {block["priority"] for block in item["blocks"]})

    def test_exact_current_probability_path_counts(self):
        kinds = self.payload["summary"]["current_kind_counts"]
        actions = self.payload["summary"]["probability_action_counts"]
        self.assertEqual(kinds["active_predictive_adjustment"], 29)
        self.assertEqual(kinds["internal_empirical_gate"], 19)
        self.assertEqual(
            actions["debe_salir_de_la_ruta_probabilistica_actual"],
            48,
        )
        self.assertEqual(
            actions["debe_reemplazarse_en_la_ruta_probabilistica"],
            5,
        )

    def test_intermarket_and_seasonality_are_not_falsely_claimed(self):
        coverage = {
            item["id"]: item for item in self.payload["block_coverage"]
        }
        self.assertEqual(coverage[20]["existing_element_count"], 0)
        self.assertEqual(coverage[25]["existing_element_count"], 0)

    def test_m1_does_not_modify_production_or_use_learning(self):
        summary = self.payload["summary"]
        self.assertFalse(summary["production_modified"])
        self.assertFalse(summary["learning_engine_used"])
        self.assertFalse(summary["next_phase_started"])


if __name__ == "__main__":
    unittest.main()
