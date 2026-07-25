import json
import unittest
from pathlib import Path

import audit_historical_rule_impact as impact


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "auditorias_motor"


class HistoricalRuleImpactArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(
            (AUDIT_DIR / "impacto_historico_reglas_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.coverage = json.loads(
            (AUDIT_DIR / "cobertura_historica_e1_4_v0_1.json").read_text(
                encoding="utf-8"
            )
        )

    def test_historical_replay_is_exact_before_ablation(self):
        replay = self.result["replay"]

        self.assertEqual(replay["cases"], 86)
        self.assertEqual(replay["probability_exact_cases"], 86)
        self.assertEqual(replay["grade_exact_cases"], 86)
        self.assertEqual(replay["risk_level_exact_cases"], 86)
        self.assertEqual(replay["decision_exact_cases"], 86)

    def test_every_declared_ablation_unit_is_present(self):
        expected = set(impact.DIRECT_ABLATION_UNITS) | set(impact.COMPOSITE_UNITS)

        self.assertEqual(set(self.result["units"]), expected)
        self.assertTrue(
            all(item["cases"] == 86 for item in self.result["units"].values())
        )

    def test_coverage_reconciles_all_recommendations(self):
        recommendations = self.coverage["recommendations"]

        self.assertEqual(
            recommendations["target_engine_version"]
            + recommendations["older_engine_versions_excluded"],
            recommendations["total"],
        )
        self.assertEqual(
            sum(self.coverage["engine_cohorts"].values()),
            recommendations["total"],
        )
        self.assertEqual(self.coverage["production_rows_modified"], 0)

    def test_read_only_query_contains_no_write_statement(self):
        query = (AUDIT_DIR / "e1_4_export_query.sql").read_text(
            encoding="utf-8"
        ).lower()

        for statement in ("insert ", "update ", "delete ", "create ", "alter ", "drop "):
            self.assertNotIn(statement, query)
        self.assertIn("from public.recommendations", query)

    def test_report_preserves_limits_and_next_phase(self):
        report = (AUDIT_DIR / "informe_impacto_historico_reglas.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("no autoriza a aumentar, reducir o retirar pesos", report)
        self.assertIn("Solo 20 casos tienen", report)
        self.assertIn("E1.5", report)


if __name__ == "__main__":
    unittest.main()
