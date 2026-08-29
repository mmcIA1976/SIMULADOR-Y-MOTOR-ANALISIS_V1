from pathlib import Path
import unittest


class EmpiricalAnalysisPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_dir = Path(__file__).resolve().parents[1]
        cls.javascript = (project_dir / "app.js").read_text(encoding="utf-8")
        cls.styles = (project_dir / "styles.css").read_text(encoding="utf-8")
        cls.index_html = (project_dir / "index.html").read_text(encoding="utf-8")

    def test_empirical_engine_uses_dedicated_interpretation(self) -> None:
        self.assertIn("function isEmpiricalStageAnalysis", self.javascript)
        self.assertIn('historical_analog_exact_first_touch', self.javascript)
        self.assertIn('metric.bias || "").toLowerCase() === "tramo_condicional"', self.javascript)
        self.assertIn("renderEmpiricalAnalysisInterpretation(analysis, metrics)", self.javascript)
        self.assertIn('"TP antes que SL"', self.javascript)
        self.assertIn('"SL antes que TP"', self.javascript)
        self.assertIn('"Sin resolver"', self.javascript)

    def test_real_alerts_are_counted_in_empirical_summary(self) -> None:
        self.assertIn("const alerts = (analysis.alerts || []).filter(Boolean)", self.javascript)
        self.assertIn("<strong>${alerts.length}</strong>", self.javascript)
        self.assertIn("Alertas metodologicas", self.javascript)

    def test_conditional_stages_render_tp_sl_and_survival(self) -> None:
        self.assertIn("conditional.tp_first_in_stage", self.javascript)
        self.assertIn("conditional.sl_first_in_stage", self.javascript)
        self.assertIn("conditional.survive_stage", self.javascript)
        self.assertIn("stage-probability-bar", self.javascript)
        self.assertIn("stage-probability-legend", self.styles)
        self.assertIn('tramo_condicional: "Tramo condicional"', self.javascript)

    def test_missing_score_or_source_does_not_render_empty_placeholders(self) -> None:
        self.assertIn("metric.score !== null && metric.score !== undefined", self.javascript)
        self.assertIn('String(metric.source || "").trim()', self.javascript)
        self.assertIn('${source ? `<span class="explain-source">', self.javascript)

    def test_assets_are_cache_busted_for_new_panel(self) -> None:
        self.assertIn("/static/app.js?v=20260829-analysis-source-availability-v2", self.index_html)
        self.assertIn("/static/styles.css?v=20260829-analysis-source-availability-v2", self.index_html)


if __name__ == "__main__":
    unittest.main()
