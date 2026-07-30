from __future__ import annotations

import unittest

from liquidation_rule_runtime import evaluate_liquidation_rule_family


ANALYSIS_AT = "2026-07-30T12:00:00+00:00"


def available_context() -> dict:
    return {
        "liquidation_context": {
            "available": True,
            "status": "available",
            "reason": None,
            "provider": "hyperperps",
            "scope": "hyperliquid",
            "symbol": "BTC",
            "schema": "hyperperps.whale-heatmap.v4",
            "as_of": ANALYSIS_AT,
            "age_seconds": 120.0,
            "reference_price": 100.0,
            "market_price": 100.0,
            "reference_basis_pct": 0.0,
            "sample_size": 2500,
            "clusters_above": [
                {
                    "position_side": "short",
                    "price": 102.0,
                    "notional_usd": 4_000_000,
                    "wallet_count": 15,
                },
                {
                    "position_side": "short",
                    "price": 105.0,
                    "notional_usd": 1_000_000,
                    "wallet_count": 5,
                },
            ],
            "clusters_below": [
                {
                    "position_side": "long",
                    "price": 98.0,
                    "notional_usd": 3_000_000,
                    "wallet_count": 12,
                },
                {
                    "position_side": "long",
                    "price": 95.0,
                    "notional_usd": 2_000_000,
                    "wallet_count": 8,
                },
            ],
            "cascade_mass": {
                "long": {
                    "within_1pct": 1_000_000,
                    "within_2pct": 3_000_000,
                    "within_5pct": 5_000_000,
                },
                "short": {
                    "within_1pct": 2_000_000,
                    "within_2pct": 4_000_000,
                    "within_5pct": 5_000_000,
                },
            },
            "short_to_long_mass_ratio_2pct": 4 / 3,
            "net_oi_skew": 0.1,
            "crowd_leverage": {
                "long_avg": 18.0,
                "short_avg": 21.0,
            },
        }
    }


class LiquidationRuleRuntimeTests(unittest.TestCase):
    def test_long_plan_measures_path_mass_without_labels_or_points(
        self,
    ) -> None:
        result = evaluate_liquidation_rule_family(
            available_context(),
            side="long",
            entry=100,
            take_profit=103,
            stop_loss=97,
            sigma_horizon=0.02,
            analysis_at=ANALYSIS_AT,
        )

        self.assertEqual(result["status"], "evaluated_shadow")
        trace = result["traces"][0]
        outputs = trace["outputs"]
        self.assertEqual(outputs["target_position_side"], "short")
        self.assertEqual(outputs["adverse_position_side"], "long")
        self.assertEqual(outputs["target_path_cluster_count"], 1)
        self.assertEqual(outputs["adverse_path_cluster_count"], 1)
        self.assertEqual(
            outputs["target_path_visible_notional_usd"],
            4_000_000,
        )
        self.assertEqual(
            outputs["adverse_path_visible_notional_usd"],
            3_000_000,
        )
        self.assertAlmostEqual(
            outputs["target_visible_path_mass_fraction"],
            4 / 7,
        )
        self.assertNotIn("map_read", outputs)
        self.assertNotIn("score", outputs)
        self.assertEqual(
            trace["probability_effect"],
            "none_shadow_observation",
        )

    def test_short_plan_swaps_target_and_adverse_position_sides(
        self,
    ) -> None:
        result = evaluate_liquidation_rule_family(
            available_context(),
            side="short",
            entry=100,
            take_profit=97,
            stop_loss=103,
            sigma_horizon=0.02,
            analysis_at=ANALYSIS_AT,
        )
        outputs = result["traces"][0]["outputs"]

        self.assertEqual(outputs["target_position_side"], "long")
        self.assertEqual(outputs["adverse_position_side"], "short")
        self.assertEqual(
            outputs["target_path_visible_notional_usd"],
            3_000_000,
        )
        self.assertEqual(
            outputs["adverse_path_visible_notional_usd"],
            4_000_000,
        )

    def test_unavailable_provider_blocks_without_using_stale_clusters(
        self,
    ) -> None:
        context = available_context()
        context["liquidation_context"]["available"] = False
        context["liquidation_context"]["status"] = "stale"
        context["liquidation_context"]["reason"] = (
            "provider_data_too_old"
        )
        result = evaluate_liquidation_rule_family(
            context,
            side="long",
            entry=100,
            take_profit=103,
            stop_loss=97,
            sigma_horizon=0.02,
            analysis_at=ANALYSIS_AT,
        )

        trace = result["traces"][0]
        self.assertEqual(trace["status"], "blocked")
        self.assertEqual(trace["outputs"], {})
        self.assertIn(
            "provider_data_too_old",
            trace["reason_codes"],
        )

    def test_unsupported_or_missing_context_does_not_block_analysis_family(
        self,
    ) -> None:
        result = evaluate_liquidation_rule_family(
            {},
            side="long",
            entry=100,
            take_profit=103,
            stop_loss=97,
            sigma_horizon=0.02,
            analysis_at=ANALYSIS_AT,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["evaluated_rule_count"], 0)
        self.assertEqual(
            result["traces"][0]["reason_codes"],
            ["missing_liquidation_context"],
        )


if __name__ == "__main__":
    unittest.main()
