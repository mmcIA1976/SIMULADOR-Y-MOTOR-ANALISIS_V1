from __future__ import annotations

import unittest

import app
from analysis_engine import TradeProposal
from liquidation_rule_runtime import RULE_ID
from sequential_production_analysis import attach_liquidation_observation
from tests.test_liquidation_rule_runtime import available_context


class LiquidationObservationIntegrationTests(unittest.TestCase):
    def proposal(self, horizon: str = "intraday_wide") -> TradeProposal:
        return TradeProposal(
            symbol="BTCUSDT",
            side="long",
            time_horizon=horizon,
            entry=100.0,
            margin=200.0,
            leverage=10.0,
            stop_loss=97.0,
            take_profit=103.0,
        )

    def build_run(self) -> dict:
        probability_result = {"immutable": "served-probability"}
        return {
            "stage_contexts": {
                "intraday_short": {"context_sigma": 0.02},
                "intraday_wide": {"context_sigma": 0.04},
                "short_swing": {"context_sigma": 0.08},
            },
            "stage_rule_traces": {
                "intraday_short": [{"rule_id": "existing-short"}],
                "intraday_wide": [{"rule_id": "existing-wide"}],
                "short_swing": [{"rule_id": "existing-swing"}],
            },
            "probability_result": probability_result,
            "details": {
                "stage_order": [
                    "intraday_short",
                    "intraday_wide",
                    "short_swing",
                ],
            },
        }

    def test_provider_is_loaded_once_and_compact_trace_is_added_per_stage(self):
        run = self.build_run()
        original_probability = run["probability_result"]
        calls = []

        def loader(symbol, market_price):
            calls.append((symbol, market_price))
            return available_context()["liquidation_context"]

        live_context, summary = attach_liquidation_observation(
            run,
            self.proposal(),
            context_loader=loader,
            context_market_price=101.0,
            analysis_at="2026-08-29T12:00:00+00:00",
        )

        self.assertEqual(calls, [("BTCUSDT", 101.0)])
        self.assertIs(run["probability_result"], original_probability)
        self.assertTrue(summary["available"])
        self.assertEqual(summary["probability_effect"], "none_observation_only")
        self.assertEqual(summary["provider_query_count"], 1)
        self.assertEqual(
            live_context["liquidation_context"]["provider"],
            "hyperperps",
        )
        for horizon in ("intraday_short", "intraday_wide", "short_swing"):
            trace = run["stage_rule_traces"][horizon][-1]
            self.assertEqual(trace["rule_id"], RULE_ID)
            self.assertEqual(trace["status"], "evaluated_shadow")
            self.assertEqual(
                trace["probability_effect"],
                "none_shadow_observation",
            )
            self.assertNotIn("target_path_clusters", trace["outputs"])
            self.assertNotIn("adverse_path_clusters", trace["outputs"])

    def test_missing_provider_is_recorded_without_changing_probability(self):
        run = self.build_run()
        original_probability = run["probability_result"]

        _live_context, summary = attach_liquidation_observation(
            run,
            self.proposal(),
            context_loader=None,
            context_market_price=None,
            analysis_at="2026-08-29T12:00:00+00:00",
        )

        self.assertIs(run["probability_result"], original_probability)
        self.assertFalse(summary["available"])
        self.assertEqual(summary["provider_query_count"], 0)
        self.assertFalse(summary["queried_once"])
        self.assertEqual(
            summary["provider_reason"],
            "liquidation_context_loader_not_configured",
        )
        for horizon in ("intraday_short", "intraday_wide", "short_swing"):
            trace = run["stage_rule_traces"][horizon][-1]
            self.assertEqual(trace["rule_id"], RULE_ID)
            self.assertEqual(trace["status"], "blocked")
            self.assertEqual(trace["outputs"], {})

    def test_learning_bridge_keeps_heatmap_observational(self):
        snapshot = {
            "probability_trace": {
                "stage_traces": [
                    {
                        "time_horizon": "intraday_short",
                        "active_rule_groups": ["price_path"],
                        "current_feature_values": {
                            "intraday_short::directional_path_efficiency_h": 0.4,
                        },
                    }
                ]
            },
            "stage_rule_traces": {
                "intraday_short": [
                    {
                        "rule_id": RULE_ID,
                        "status": "evaluated_shadow",
                        "outputs": {
                            "target_visible_path_mass_fraction": 0.7,
                            "adverse_path_visible_notional_usd": 3_000_000,
                        },
                        "probability_effect": "none_shadow_observation",
                    }
                ]
            },
        }

        result = app.predictive_rule_learning_snapshot(
            snapshot,
            plan_result="plan_success",
        )

        self.assertIn(RULE_ID, result["observational_rule_ids"])
        observation = result["observational_rules"][RULE_ID]
        self.assertEqual(
            observation["probability_effect"],
            "none_observation_only",
        )
        self.assertEqual(
            observation["stage_traces"][0]["outputs"][
                "target_visible_path_mass_fraction"
            ],
            0.7,
        )


if __name__ == "__main__":
    unittest.main()
