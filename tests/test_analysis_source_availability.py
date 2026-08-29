from pathlib import Path
from types import SimpleNamespace
import unittest

from sequential_production_analysis import _analysis_availability


STAGES = ["intraday_short", "intraday_wide", "short_swing"]


def rule_trace(rule_id: str, *, status: str = "evaluated_shadow") -> dict:
    return {
        "rule_id": rule_id,
        "status": status,
        "outputs": {"measured": 1.0} if status != "blocked" else {},
        "probability_effect": "none_observation_only",
    }


def evaluated_run() -> dict:
    traces = {
        horizon: [
            rule_trace("LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"),
            rule_trace("LIB-CAND-FIBONACCI-DISTANCE-001"),
        ]
        for horizon in STAGES
    }
    return {
        "stage_contexts": {horizon: {"context_sigma": 0.02} for horizon in STAGES},
        "stage_rule_traces": traces,
    }


class AnalysisSourceAvailabilityTests(unittest.TestCase):
    def test_summary_is_derived_from_successful_stage_evidence(self):
        availability = _analysis_availability(
            evaluated_run(),
            SimpleNamespace(entry=2_433.56),
            STAGES,
            liquidation_available=True,
            order_book_available=True,
        )

        self.assertTrue(availability["futures_price"])
        self.assertTrue(availability["futures_klines"])
        self.assertTrue(availability["multiscale_5m"])
        self.assertTrue(availability["multiscale_1h"])
        self.assertTrue(availability["multiscale_6h"])
        self.assertTrue(availability["fibonacci"])
        self.assertTrue(availability["structural_levels"])
        self.assertTrue(availability["liquidation_heatmap"])
        self.assertTrue(availability["order_book_dynamics"])

    def test_rule_is_not_claimed_available_if_one_executed_stage_is_blocked(self):
        run = evaluated_run()
        run["stage_rule_traces"]["intraday_wide"][1] = rule_trace(
            "LIB-CAND-FIBONACCI-DISTANCE-001",
            status="blocked",
        )

        availability = _analysis_availability(
            run,
            SimpleNamespace(entry=100.0),
            STAGES,
            liquidation_available=False,
            order_book_available=False,
        )

        self.assertFalse(availability["fibonacci"])
        self.assertTrue(availability["structural_levels"])
        self.assertFalse(availability["liquidation_heatmap"])
        self.assertFalse(availability["order_book_dynamics"])

    def test_frontend_renders_only_sources_declared_by_current_contract(self):
        project_dir = Path(__file__).resolve().parents[1]
        javascript = (project_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn("Object.entries(availability)", javascript)
        self.assertNotIn("const chips = Object.entries(labels)", javascript)
        self.assertIn('structural_levels: "Niveles estructurales"', javascript)
        self.assertIn('order_book_dynamics: "Dinámica del libro"', javascript)
        self.assertIn('multiscale_6h: "Tramo 24 h-7 d · 6h"', javascript)


if __name__ == "__main__":
    unittest.main()
