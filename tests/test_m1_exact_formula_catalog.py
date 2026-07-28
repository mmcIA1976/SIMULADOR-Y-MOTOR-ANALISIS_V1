import unittest

from build_m1_exact_formula_catalog import (
    DATA_SPECS,
    GATE_DEFINITIONS,
    build_catalog,
    exact_specs,
)


class M1ExactFormulaCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_catalog()
        cls.entries = cls.payload["entries"]

    def test_catalog_reconciles_all_86_m1_entries(self):
        summary = self.payload["summary"]
        self.assertEqual(summary["entries"], 86)
        self.assertEqual(summary["unique_ids"], 86)
        self.assertEqual(summary["current_production_entries"], 82)
        self.assertEqual(summary["contract_infrastructure_entries"], 4)
        self.assertEqual(len(exact_specs()), 86)

    def test_every_current_definition_is_complete_and_anchored(self):
        for item in self.entries:
            with self.subTest(rule_id=item["id"]):
                self.assertTrue(
                    item["definition_complete_for_current_implementation"]
                )
                self.assertTrue(item["exact_definition"])
                self.assertTrue(all(item["exact_definition"]))
                self.assertTrue(item["source_anchors"])
                for anchor in item["source_anchors"]:
                    self.assertGreater(anchor["start_line"], 0)
                    self.assertGreaterEqual(
                        anchor["end_line"], anchor["start_line"]
                    )
                    self.assertEqual(len(anchor["function_sha256"]), 64)

    def test_data_contracts_do_not_claim_predictive_formulas(self):
        by_id = {item["id"]: item for item in self.entries}
        for rule_id in DATA_SPECS:
            with self.subTest(rule_id=rule_id):
                item = by_id[rule_id]
                self.assertEqual(
                    item["definition_type"], "exact_data_contract"
                )
                joined = " ".join(item["exact_definition"]).lower()
                self.assertIn("no direct", joined)

    def test_all_19_gates_include_every_effect_dimension(self):
        self.assertEqual(len(GATE_DEFINITIONS), 19)
        by_id = {item["id"]: item for item in self.entries}
        required = (
            "tp_delta=",
            "risk_delta=",
            "quality_penalty+=",
            "confidence_penalty+=",
            "EV_score_penalty+=",
            "execution_risk_addition+=",
            "grade_cap=",
            "force_observar=",
        )
        for rule_id in GATE_DEFINITIONS:
            with self.subTest(rule_id=rule_id):
                joined = " ".join(by_id[rule_id]["exact_definition"])
                for token in required:
                    self.assertIn(token, joined)

    def test_catalog_does_not_authorize_or_modify_production(self):
        self.assertEqual(
            self.payload["summary"]["direct_probability_authorized"], 0
        )
        scope = self.payload["scope"]
        self.assertTrue(scope["m1_closed"])
        self.assertTrue(scope["m1_a_closed"])
        self.assertFalse(scope["m1_reopened"])
        self.assertFalse(scope["m2_started"])
        self.assertFalse(scope["production_modified"])
        self.assertFalse(scope["learning_engine_used"])

    def test_catalog_hash_is_stable_shape(self):
        self.assertEqual(len(self.payload["catalog_sha256"]), 64)
        self.assertEqual(
            self.payload["source"]["m1_decisions_catalog_sha256"],
            "1a3a5248e1aaad816eab297e27e14e75b2386a62afdcd4dc7fc1e2f57e23c2ce",
        )


if __name__ == "__main__":
    unittest.main()
