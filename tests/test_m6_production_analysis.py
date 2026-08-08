from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from m6_production_analysis import (
    ENGINE_VERSION,
    NewEngineAnalysisError,
    _probability_label,
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
            "traces": [
                {
                    "rule_id": "M4-RULE-QUOTED-SPREAD-001",
                    "status": "evaluated",
                    "outputs": {
                        "mid": 100.0,
                        "spread_fraction_mid": 0.0002,
                    },
                },
                {
                    "rule_id": "M4-RULE-DEPTH-SWEEP-001",
                    "status": "evaluated",
                    "outputs": {
                        "fill_ratio": 1.0,
                        "availability_status": "available",
                        "complete_vwap": 100.02,
                    },
                },
            ],
        },
        "m5_pre_probability_analysis": {
            "analysis_trace_sha256": "m5-pre-sha",
            "traces": [],
        },
        "m5_rule_effects": {},
        "observational_rule_traces": {
            "traces": [
                {
                    "rule_id": (
                        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
                    ),
                    "status": "evaluated_shadow",
                },
                {
                    "rule_id": "LIB-CAND-FIBONACCI-DISTANCE-001",
                    "status": "evaluated_shadow",
                },
                {
                    "rule_id": "LIB-CAND-FUNDING-PERCENTILE-001",
                    "status": "evaluated_shadow",
                },
                {
                    "rule_id": "LIB-CAND-CROWDING-PERCENTILE-001",
                    "status": "evaluated_shadow",
                },
                {
                    "rule_id": "LIB-CAND-BREADTH-001",
                    "status": "evaluated_shadow",
                },
                {
                    "rule_id": "LIB-CAND-SENTIMENT-PERCENTILE-001",
                    "status": "evaluated_shadow",
                },
                {
                    "rule_id": "LIB-CAND-LIQUIDATION-ZONE-001",
                    "status": "evaluated_shadow",
                },
            ]
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
            "decision_probabilities": {
                "resolution_within_horizon": 0.90,
                "tp_given_resolution": 0.55 / 0.90,
            },
            "calibration": {
                "version": "M6-global-frozen-champion-v0.1",
                "time_horizon": "intraday_short",
                "horizon_label": "Intradía corto · hasta 4 h",
                "confidence": "referencia congelada",
                "calibration_records": 35,
                "temperature": 1.5,
                "common_model_all_horizons": True,
            },
            "shadow_challenger": {
                "version": "M6-horizon-overlay-shadow-v0.1",
                "production_effect": "none",
            },
            "stability_policy": {
                "version": "engine-stability-policy-v0.1",
            },
            "result_sha256": "m6-sha",
        },
        "source_data_sha256": "source-sha",
        "data_cutoff_at": "2026-07-28T12:00:00+00:00",
    }


class M6ProductionAnalysisTests(unittest.TestCase):
    def test_tiny_nonzero_probabilities_are_not_labeled_zero(self):
        self.assertEqual(_probability_label(9.5e-11), "<0.1%")
        self.assertEqual(_probability_label(0.9999999998), ">99.9%")

    @patch(
        "m6_production_analysis.build_prospective_probability_run",
        return_value=evaluated_run(),
    )
    def test_new_engine_is_the_visible_result(self, build_run):
        result = analyze_trade(
            proposal(),
            context_loader=lambda **kwargs: {},
        )

        self.assertEqual(result["engine_version"], ENGINE_VERSION)
        self.assertTrue(result["snapshot"]["new_engine_only"])
        self.assertFalse(result["legacy_engine_executed"])
        self.assertEqual(result["production_effect"], "served")
        self.assertTrue(result["snapshot"]["availability"]["fibonacci"])
        self.assertTrue(
            result["snapshot"]["availability"]["structural_levels"]
        )
        self.assertTrue(
            result["snapshot"]["availability"]["funding_relative"]
        )
        self.assertTrue(
            result["snapshot"]["availability"]["long_short_ratio"]
        )
        self.assertTrue(
            result["snapshot"]["availability"]["market_breadth"]
        )
        self.assertTrue(result["snapshot"]["availability"]["fear_greed"])
        self.assertTrue(
            result["snapshot"]["availability"]["liquidation_heatmap"]
        )
        self.assertTrue(result["snapshot"]["availability"]["entry_depth"])
        economics = result["snapshot"]["execution_economics"]
        self.assertEqual(
            economics["probability_effect"],
            "none_separate_economic_layer",
        )
        self.assertEqual(
            economics["quoted_spread"]["spread_fraction_mid"],
            0.0002,
        )
        self.assertEqual(
            economics["entry_depth_sweep"]["fill_ratio"],
            1.0,
        )
        self.assertAlmostEqual(result["tp_probability"], 0.55)
        self.assertAlmostEqual(result["sl_probability"], 0.35)
        self.assertAlmostEqual(result["range_probability"], 0.10)
        self.assertAlmostEqual(
            result["tp_before_sl_within_horizon_probability"],
            0.55,
        )
        self.assertEqual(result["confidence"], "referencia congelada")
        self.assertEqual(
            result["horizon_calibration"]["time_horizon"],
            "intraday_short",
        )
        self.assertEqual(
            result["model_trace"]["coefficient_artifact_id"],
            "M6-CANDIDATE-NO-H-RIDGE-10-v0.2",
        )
        self.assertEqual(
            result["model_trace"]["shadow_challenger"][
                "production_effect"
            ],
            "none",
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
            analyze_trade(
                proposal(entry_type="pending"),
                context_loader=lambda **kwargs: {},
            )

    @patch(
        "m6_production_analysis.build_prospective_probability_run",
        return_value=evaluated_run(),
    )
    def test_historical_reanalysis_uses_explicit_activation_cutoff(self, build_run):
        activation_at = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)

        result = analyze_trade(
            proposal(),
            context_loader=lambda **kwargs: {},
            effective_analysis_at=activation_at,
        )

        snapshot = build_run.call_args.args[1]
        self.assertEqual(snapshot["analysis_at"], activation_at.isoformat())
        self.assertEqual(
            result["snapshot"]["analysis_at"],
            activation_at.isoformat(),
        )

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
            analyze_trade(
                proposal(),
                context_loader=lambda **kwargs: {},
            )

    def test_app_has_no_live_shadow_execution_path(self):
        app_source = Path("app.py").read_text(encoding="utf-8")
        self.assertNotIn("execute_live_shadow_run", app_source)
        self.assertNotIn("persist_live_shadow_safely", app_source)


if __name__ == "__main__":
    unittest.main()
