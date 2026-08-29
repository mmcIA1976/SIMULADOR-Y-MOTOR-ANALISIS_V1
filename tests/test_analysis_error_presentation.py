from pathlib import Path
import unittest

from app import NewEngineAnalysisError, new_engine_error_detail


class AnalysisErrorPresentationTests(unittest.TestCase):
    def test_outside_historical_support_is_explained_without_fake_result(self):
        detail = new_engine_error_detail(
            NewEngineAnalysisError(
                "context_outside_historical_support:short_swing:0.931368>0.766694"
            ),
            "ETHUSDT",
        )

        self.assertEqual(detail["code"], "context_outside_historical_support")
        self.assertIn("ETHUSDT", detail["message"])
        self.assertIn("hasta 7 días", detail["message"])
        self.assertIn("No se ha guardado ningún análisis", detail["message"])
        self.assertEqual(detail["details"]["nearest_context_distance"], 0.931368)
        self.assertEqual(
            detail["details"]["maximum_context_distance_allowed"],
            0.766694,
        )
        self.assertFalse(detail["details"]["analysis_saved"])

    def test_frontend_reads_structured_api_errors(self):
        javascript = Path("app.js").read_text(encoding="utf-8")
        html = Path("index.html").read_text(encoding="utf-8")

        self.assertIn("structuredDetail?.message", javascript)
        self.assertIn('error.code === "context_outside_historical_support"', javascript)
        self.assertIn("Análisis no disponible con fiabilidad", javascript)
        self.assertIn("No se han generado porcentajes", javascript)
        self.assertIn(
            "/static/app.js?v=20260829-observational-rule-readings",
            html,
        )


if __name__ == "__main__":
    unittest.main()
