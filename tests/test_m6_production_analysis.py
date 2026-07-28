from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from m6_production_analysis import (
    ENGINE_VERSION,
    NewEngineAnalysisError,
    analyze_trade,
)


FEATURE_VALUES = {
    "directional_path_efficiency_h": 0.1,
    "directional_path_efficiency_2h": 0.2,
    "directional_path_efficiency_4h": 0.3,
    "volatility_percentile_60": 0.4,
    "target_extreme_between_entry_and_tp": 1.0,
}


def proposal(entry_type: str = "market"):
    return SimpleNamespace(
        symbol="BTCUSDT",
        side="long",
        time_horizon="intraday_short",
        entry=100.0,
        margin=100.0,
        leverage=2.0,
        stop_loss=99.0,
        take_profit=102.0,
        entry_type=entry_type,
    )


def evaluated_run() -> dict:
    return {
        "status": "evaluated",
        "block_code": None,
        "feature_snapshot": {
            "values": FEATURE_VALUES,
            "standardized_candidate_values": {
                "intercept": 1.0,
                **FEATURE_VALUES,
            },
        },
        "m5_analysis": {
            "analysis_trace_sha256": "m5-sha",
            "traces": [],
        },
        "m6_result": {
            "probabilities": {
                "tp_first_within_horizon": 0.55,
                "sl_first_within_horizon": 0.35,
                "neither_barrier_before_expiry": 0.10,
            },
            "raw_probabilities": {
                "tp_first_within_horizon": 0.52,
                "sl_first_within_horizon": 0.38,
                "neither_barrier_before_expiry": 0.10,
            },
            "result_sha256": "m6-sha",
        },
        "source_data_sha256": "source-sha",
        "data_cutoff_at": "2026-07-28T12:00:00+00:00",
    }


class M6ProductionAnalysisTests(unittest.TestCase):
    @patch(
        "m6_production_analysis.build_prospective_probability_run",
        return_value=evaluated_run(),
    )
    def test_new_engine_is_the_visible_result(self, build_run):
        result = analyze_trade(proposal())

        self.assertEqual(result["engine_version"], ENGINE_VERSION)
        self.assertTrue(result["snapshot"]["new_engine_only"])
        self.assertFalse(result["legacy_engine_executed"])
        self.assertEqual(result["production_effect"], "served")
        self.assertAlmostEqual(result["tp_probability"], 0.55)
        self.assertAlmostEqual(result["sl_probability"], 0.35)
        self.assertAlmostEqual(result["range_probability"], 0.10)
        self.assertEqual(
            result["model_trace"]["coefficient_artifact_id"],
            ENGINE_VERSION,
        )
        self.assertIn(
            "volatility_percentile_60",
            result["model_trace"]["feature_contributions"],
        )
        build_run.assert_called_once()

    def test_pending_entry_is_rejected_without_legacy_fallback(self):
        with self.assertRaisesRegex(
            NewEngineAnalysisError,
            "market_entry_required",
        ):
            analyze_trade(proposal(entry_type="pending"))

    @patch(
        "m6_production_analysis.build_prospective_probability_run",
        return_value={
            "status": "blocked",
            "block_code": "insufficient_pretrade_history",
            "details": {},
        },
    )
    def test_blocked_new_engine_does_not_return_an_old_result(self, _build_run):
        with self.assertRaisesRegex(
            NewEngineAnalysisError,
            "insufficient_pretrade_history",
        ):
            analyze_trade(proposal())

    def test_app_has_no_live_shadow_execution_path(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertNotIn("execute_live_shadow_run", app_source)
        self.assertNotIn("persist_live_shadow_safely", app_source)


if __name__ == "__main__":
    unittest.main()
