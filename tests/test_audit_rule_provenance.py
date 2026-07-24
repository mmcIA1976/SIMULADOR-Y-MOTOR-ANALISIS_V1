import json
import unittest
from pathlib import Path

import audit_rule_provenance


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "auditorias_motor" / "inventario_reglas_motor_v0_1.json"


def build_test_matrix() -> tuple[dict, dict]:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    return inventory, audit_rule_provenance.build_matrix(inventory)


class AuditRuleProvenanceTests(unittest.TestCase):
    def test_matrix_classifies_every_inventoried_function(self):
        inventory, matrix = build_test_matrix()
        expected = sum(len(module["functions"]) for module in inventory["modules"])

        self.assertEqual(matrix["summary"]["functions"], expected)
        self.assertEqual(matrix["summary"]["explicitly_classified_functions"], expected)
        self.assertEqual(len({item["stable_id"] for item in matrix["functions"]}), expected)
        self.assertTrue(
            all(item["status"] in audit_rule_provenance.VALID_STATUSES for item in matrix["functions"])
        )

    def test_matrix_preserves_all_literals_and_formula_fragments(self):
        inventory, matrix = build_test_matrix()
        expected_literals = sum(
            len(function["numeric_literals"])
            for module in inventory["modules"]
            for function in module["functions"]
        )
        expected_fragments = sum(
            len(function["formula_fragments"])
            for module in inventory["modules"]
            for function in module["functions"]
        )

        self.assertEqual(matrix["summary"]["numeric_literal_occurrences"], expected_literals)
        self.assertEqual(matrix["summary"]["formula_fragments"], expected_fragments)

    def test_critical_rules_are_not_misrepresented_as_externally_validated(self):
        _, matrix = build_test_matrix()
        by_id = {item["stable_id"]: item for item in matrix["functions"]}

        self.assertEqual(by_id["analysis_engine.py:analyze_trade"]["status"], "heuristica")
        self.assertEqual(
            by_id["analysis_engine.py:build_risk_calibration_context"]["status"],
            "empirica_provisional",
        )
        self.assertEqual(by_id["data_engine.py:rsi"]["status"], "heuristica")
        self.assertEqual(by_id["data_engine.py:atr"]["status"], "heuristica")
        self.assertEqual(by_id["liquidation_data.py:normalize_heatmap"]["status"], "heuristica")
        self.assertFalse(by_id["versioning.py:build_data_contract"]["rule_bearing"])

    def test_matrix_generation_is_deterministic(self):
        inventory, first = build_test_matrix()
        second = audit_rule_provenance.build_matrix(inventory)

        self.assertEqual(first["matrix_sha256"], second["matrix_sha256"])


if __name__ == "__main__":
    unittest.main()
