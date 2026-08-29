from pathlib import Path
import unittest


class ObservationalRulesPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project_dir = Path(__file__).resolve().parents[1]
        cls.javascript = (project_dir / "app.js").read_text(encoding="utf-8")
        cls.html = (project_dir / "index.html").read_text(encoding="utf-8")
        cls.styles = (project_dir / "styles.css").read_text(encoding="utf-8")

    def test_extended_analysis_has_observational_rule_panel(self):
        self.assertIn('id="observationalRulesPanel"', self.html)
        self.assertIn("renderObservationalRules(analysis)", self.javascript)
        self.assertIn(".observational-rule-card", self.styles)

    def test_panel_declares_probability_neutrality(self):
        self.assertIn("No intervienen en los porcentajes mostrados", self.javascript)
        self.assertIn("Sin peso probabilístico", self.javascript)

    def test_known_dynamic_rules_have_human_readable_views(self):
        for rule_id in (
            "LIB-CAND-EMA-TREND-001",
            "LIB-CAND-RSI-WILDER-001",
            "LIB-CAND-CVD-SLOPE-001",
            "LIB-CAND-LIQUIDATION-ZONE-001",
            "LIB-CAND-ORDERBOOK-IMBALANCE-001",
        ):
            self.assertIn(rule_id, self.javascript)

    def test_static_assets_are_cache_busted(self):
        self.assertIn(
            "/static/app.js?v=20260829-analysis-source-availability-v2",
            self.html,
        )
        self.assertIn(
            "/static/styles.css?v=20260829-analysis-source-availability-v2",
            self.html,
        )


if __name__ == "__main__":
    unittest.main()
