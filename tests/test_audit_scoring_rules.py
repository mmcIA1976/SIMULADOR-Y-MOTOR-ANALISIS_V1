import hashlib
import unittest

from audit_scoring_rules import ROOT, build_inventory


class AuditScoringRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = build_inventory()
        cls.modules = {
            module["path"]: module
            for module in cls.inventory["modules"]
        }

    def test_inventory_covers_analysis_data_and_learning(self):
        self.assertEqual(self.inventory["inventory_schema"], "scoring-rule-inventory-v0.1")
        self.assertIn("analysis_engine.py", self.modules)
        self.assertIn("data_engine.py", self.modules)
        self.assertIn("market_data.py", self.modules)
        self.assertIn("liquidation_data.py", self.modules)
        self.assertIn("learning_evidence.py", self.modules)
        self.assertIn("economic_metrics.py", self.modules)
        self.assertIn("versioning.py", self.modules)
        self.assertIn("app.py", self.modules)

    def test_critical_rules_are_present(self):
        functions = {
            module_name: {
                function["name"]
                for function in module["functions"]
            }
            for module_name, module in self.modules.items()
        }
        self.assertIn("analyze_trade", functions["analysis_engine.py"])
        self.assertIn("calculate_expected_value", functions["analysis_engine.py"])
        self.assertIn("grade_from_scores", functions["analysis_engine.py"])
        self.assertIn("decision_from_context", functions["analysis_engine.py"])
        self.assertIn("build_market_snapshot", functions["data_engine.py"])
        self.assertIn("build_historical_evidence", functions["learning_evidence.py"])
        self.assertIn("classify_analysis_verdict", functions["app.py"])
        self.assertIn("build_learning_signal", functions["app.py"])

    def test_module_hashes_match_the_audited_source(self):
        for module_name, module in self.modules.items():
            source = (ROOT / module_name).read_bytes()
            self.assertEqual(
                module["sha256"],
                hashlib.sha256(source).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
