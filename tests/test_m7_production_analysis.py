from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from m7_production_analysis import (
    ENGINE_VERSION,
    NewEngineAnalysisError,
    _probability_label,
    analyze_trade,
)
from m7_joint_temporal_engine import load_production_artifact


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
    artifact = load_production_artifact()
    standardized = {
        "intercept": 1.0,
        **{
            name: (
                FEATURE_VALUES[name]
                - artifact["feature_standardization"][name]["mean"]
            )
            / artifact["feature_standardization"][name]["scale"]
            for name in FEATURE_VALUES
        },
    }
    probabilities = {
        "tp_first_within_horizon": 0.25,
        "sl_first_within_horizon": 0.35,
        "neither_barrier_before_expiry": 0.40,
    }
    curve = {
        "intraday_short": probabilities,
        "intraday_wide": {
            "tp_first_within_horizon": 0.35,
            "sl_first_within_horizon": 0.45,
            "neither_barrier_before_expiry": 0.20,
        },
        "short_swing": {
            "tp_first_within_horizon": 0.42,
            "sl_first_within_horizon": 0.53,
            "neither_barrier_before_expiry": 0.05,
        },
    }
    return {
        "status": "evaluated",
        "block_code": None,
        "analysis_engine_execution_count": 1,
        "executed_analysis_engines": [ENGINE_VERSION],
        "feature_snapshot": {
            "values": FEATURE_VALUES,
            "standardized_values": standardized,
        },
        "probability_result": {
            "probabilities": probabilities,
            "probability_curve": curve,
            "decision_probabilities": {
                "resolution_within_horizon": 0.60,
                "tp_given_resolution": 0.25 / 0.60,
            },
            "plan": {
                "tp_log_distance": 0.0198,
                "sl_log_distance": 0.0101,
            },
            "result_sha256": "m7-result-sha",
        },
        "reference_sigma_24h": 0.02,
        "source_data_sha256": "source-sha",
        "data_cutoff_at": "2026-08-13T12:00:00+00:00",
    }


class M7ProductionAnalysisTests(unittest.TestCase):
    def test_tiny_nonzero_probabilities_are_not_labeled_zero(self):
        self.assertEqual(_probability_label(9.5e-11), "<0.1%")
        self.assertEqual(_probability_label(0.9999999998), ">99.9%")

    @patch(
        "m7_production_analysis.build_production_probability_run",
        return_value=evaluated_run(),
    )
    def test_v07_is_the_only_visible_and_executed_engine(self, build_run):
        result = analyze_trade(proposal())

        self.assertEqual(result["engine_version"], ENGINE_VERSION)
        self.assertEqual(result["analysis_engine_execution_count"], 1)
        self.assertEqual(result["executed_analysis_engines"], [ENGINE_VERSION])
        self.assertTrue(result["snapshot"]["new_engine_only"])
        self.assertFalse(result["legacy_engine_executed"])
        self.assertEqual(result["production_effect"], "served")
        self.assertAlmostEqual(result["tp_probability"], 0.25)
        self.assertAlmostEqual(result["sl_probability"], 0.35)
        self.assertAlmostEqual(result["range_probability"], 0.40)
        self.assertTrue(result["model_trace"]["single_engine"])
        self.assertEqual(
            result["model_trace"]["parallel_probability_engines_executed"],
            0,
        )
        self.assertNotIn("shadow_challenger", result["model_trace"])
        self.assertNotIn("raw_probabilities", result["model_trace"])
        self.assertFalse(result["snapshot"]["availability"]["fibonacci"])
        self.assertFalse(
            result["snapshot"]["availability"]["liquidation_heatmap"]
        )
        build_run.assert_called_once()

    def test_pending_entry_is_rejected_without_fallback(self):
        with self.assertRaisesRegex(NewEngineAnalysisError, "market_entry_required"):
            analyze_trade(proposal(entry_type="pending"))

    @patch(
        "m7_production_analysis.build_production_probability_run",
        return_value=evaluated_run(),
    )
    def test_historical_reanalysis_uses_explicit_cutoff(self, build_run):
        activation_at = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)

        result = analyze_trade(
            proposal(),
            effective_analysis_at=activation_at,
        )

        snapshot = build_run.call_args.args[1]
        self.assertEqual(snapshot["analysis_at"], activation_at.isoformat())
        self.assertEqual(result["snapshot"]["analysis_at"], activation_at.isoformat())

    @patch(
        "m7_production_analysis.build_production_probability_run",
        return_value={
            "status": "blocked",
            "block_code": "insufficient_pretrade_history",
            "details": {},
        },
    )
    def test_blocked_v07_does_not_return_an_old_result(self, _build_run):
        with self.assertRaisesRegex(
            NewEngineAnalysisError,
            "insufficient_pretrade_history",
        ):
            analyze_trade(proposal())

    def test_app_has_no_shadow_or_challenger_routes(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertNotIn("execute_live_shadow_run", app_source)
        self.assertNotIn("champion-shadow-audit", app_source)
        self.assertNotIn("challenger-audit", app_source)


if __name__ == "__main__":
    unittest.main()
