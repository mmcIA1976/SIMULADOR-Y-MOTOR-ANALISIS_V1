from __future__ import annotations

import unittest

from limit_activation_baseline import build_limit_activation_baseline
from limit_context_rule_runtime import (
    RULE_IDS,
    LimitContextRuleError,
    evaluate_limit_context_rule_family,
)
from limit_order_contract import build_limit_order_contract


def parent_trace(rule_id: str, outputs: dict, status: str = "evaluated") -> dict:
    return {
        "rule_id": rule_id,
        "status": status,
        "outputs": outputs,
        "trace_sha256": f"sha-{rule_id}",
    }


class LimitContextRuleRuntimeTests(unittest.TestCase):
    def contract(self, **overrides):
        values = {
            "analysis_id": "limit-context-test",
            "symbol": "BTCUSDT",
            "side": "long",
            "time_horizon": "intraday_short",
            "analysis_at": "2026-08-05T10:00:00+00:00",
            "current_price": 100.0,
            "requested_entry": 98.0,
            "stop_loss": 96.0,
            "take_profit": 103.0,
            "trigger_condition": "price_lte",
        }
        values.update(overrides)
        return build_limit_order_contract(**values)

    def baseline(self, contract: dict):
        return build_limit_activation_baseline(
            contract,
            sigma_horizon=0.04,
        )

    def m5_traces(self, *, path: float = -0.6, displacement: float = -0.02):
        return {
            "traces": [
                parent_trace(
                    "M4-RULE-PATH-STRUCTURE-001",
                    {
                        "signed_path_efficiency": path,
                        "log_displacement": displacement,
                    },
                ),
                parent_trace(
                    "M4-RULE-MTF-HIERARCHY-001",
                    {
                        "signed_path_efficiencies": {
                            "H": path,
                            "2H": path / 2,
                            "4H": -path / 4,
                        }
                    },
                ),
                parent_trace(
                    "M4-RULE-VOLATILITY-RANK-001",
                    {"volatility_percentile": 0.7},
                ),
                parent_trace(
                    "M4-RULE-AGGRESSOR-IMBALANCE-001",
                    {"ATI_H": -0.25},
                ),
                parent_trace(
                    "M4-RULE-OPEN-INTEREST-CHANGE-001",
                    {"dOI_H": 0.08},
                ),
                parent_trace(
                    "M4-RULE-FUNDING-STATE-001",
                    {"last_funding_rate": 0.0001},
                ),
            ]
        }

    def observations(self, *, side: str = "long"):
        desired_level = (
            {
                "type": "low",
                "price": 97.9,
                "prominence_atr": 1.4,
                "distance_sigma_horizon": -0.025,
            }
            if side == "long"
            else {
                "type": "high",
                "price": 102.1,
                "prominence_atr": 1.4,
                "distance_sigma_horizon": 0.025,
            }
        )
        return [
            parent_trace(
                "LIB-CAND-EMA-TREND-001",
                {"ema50_slope_6bars_atr": -0.3},
                "evaluated_shadow",
            ),
            parent_trace(
                "LIB-CAND-RSI-WILDER-001",
                {"centered_rsi": -0.2},
                "evaluated_shadow",
            ),
            parent_trace(
                "LIB-CAND-CVD-SLOPE-001",
                {
                    "normalized_cvd_slope": -0.15,
                    "terminal_taker_imbalance": -0.2,
                },
                "evaluated_shadow",
            ),
            parent_trace(
                "LIB-CAND-ORDERBOOK-IMBALANCE-001",
                {
                    "spread_fraction": 0.0002,
                    "measures": {"top_20": {"imbalance": -0.1}},
                },
                "evaluated_shadow",
            ),
            parent_trace(
                "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
                {
                    "confirmed_pivot_count": 8,
                    "nearest_support": desired_level if side == "long" else None,
                    "nearest_resistance": desired_level if side == "short" else None,
                    "target_path_level_count": 2,
                    "adverse_path_level_count": 1,
                    "strongest_target_path_prominence_atr": 1.8,
                    "strongest_adverse_path_prominence_atr": 1.1,
                },
                "evaluated_shadow",
            ),
            parent_trace(
                "LIB-CAND-FIBONACCI-DISTANCE-001",
                {
                    "nearest_to_entry": {
                        "set": "retracements",
                        "ratio": "0.618",
                        "price": 98.05 if side == "long" else 101.95,
                        "absolute_distance_sigma_horizon": 0.012,
                    },
                    "entry_retracement_fraction": 0.62,
                },
                "evaluated_shadow",
            ),
        ]

    def liquidation_context(self):
        return {
            "available": True,
            "status": "available",
            "provider": "hyperperps",
            "scope": "hyperliquid",
            "schema": "test-v1",
            "as_of": "2026-08-05T10:00:00+00:00",
            "age_seconds": 15,
            "clusters_below": [
                {
                    "position_side": "long",
                    "price": 99,
                    "notional_usd": 1000,
                    "wallet_count": 2,
                },
                {
                    "position_side": "long",
                    "price": 97,
                    "notional_usd": 2000,
                    "wallet_count": 3,
                },
                {
                    "position_side": "long",
                    "price": 95,
                    "notional_usd": 4000,
                    "wallet_count": 4,
                },
            ],
            "clusters_above": [
                {
                    "position_side": "short",
                    "price": 101,
                    "notional_usd": 3000,
                    "wallet_count": 5,
                },
                {
                    "position_side": "short",
                    "price": 102,
                    "notional_usd": 5000,
                    "wallet_count": 6,
                },
                {
                    "position_side": "short",
                    "price": 104,
                    "notional_usd": 7000,
                    "wallet_count": 7,
                },
            ],
        }

    def evaluate(self, contract: dict | None = None, **kwargs):
        contract = contract or self.contract()
        return evaluate_limit_context_rule_family(
            contract,
            self.baseline(contract),
            m5_analysis=kwargs.get("m5_analysis", self.m5_traces()),
            observational_traces=kwargs.get(
                "observational_traces", self.observations()
            ),
            liquidation_context=kwargs.get(
                "liquidation_context", self.liquidation_context()
            ),
        )

    def test_long_downtrend_helps_activation_but_opposes_reaction(self):
        result = self.evaluate()
        trajectory = result["traces"][0]["outputs"]

        self.assertGreater(
            trajectory["activation_adjusted_path_efficiency_h"], 0
        )
        self.assertLess(
            trajectory["reaction_adjusted_path_efficiency_h"], 0
        )
        self.assertEqual(
            trajectory["activation_path_relation"], "toward_direction"
        )

    def test_short_uptrend_is_the_mirror_activation_case(self):
        contract = self.contract(
            side="short",
            requested_entry=102,
            stop_loss=104,
            take_profit=97,
            trigger_condition="price_gte",
        )
        result = self.evaluate(
            contract,
            m5_analysis=self.m5_traces(path=0.6, displacement=0.02),
            observational_traces=self.observations(side="short"),
        )
        trajectory = result["traces"][0]["outputs"]

        self.assertGreater(
            trajectory["activation_adjusted_path_efficiency_h"], 0
        )
        self.assertLess(
            trajectory["reaction_adjusted_path_efficiency_h"], 0
        )

    def test_sell_flow_has_opposite_activation_and_reaction_roles_for_long(self):
        flow = self.evaluate()["traces"][1]["outputs"]
        ati = flow["directional_components"]["aggressor_imbalance_h"]

        self.assertGreater(ati["activation_adjusted"], 0)
        self.assertLess(ati["reaction_adjusted"], 0)
        self.assertEqual(
            flow["order_book_semantics"],
            "current_price_snapshot_not_future_entry_zone_liquidity",
        )
        self.assertEqual(
            flow["aggregation_policy"],
            "raw_components_reoriented_but_never_summed",
        )

    def test_zone_uses_support_for_long_and_preserves_components(self):
        zone = self.evaluate()["traces"][2]["outputs"]

        self.assertEqual(zone["desired_level_type"], "support")
        self.assertTrue(zone["zone_has_confirmed_desired_level"])
        self.assertEqual(zone["desired_level"]["price"], 97.9)
        self.assertEqual(zone["fibonacci_at_entry"]["ratio"], "0.618")
        self.assertNotIn("zone_score", zone)

    def test_missing_fibonacci_does_not_block_structural_zone(self):
        observations = [
            trace
            for trace in self.observations()
            if trace["rule_id"] != "LIB-CAND-FIBONACCI-DISTANCE-001"
        ]
        zone = self.evaluate(observational_traces=observations)["traces"][2]

        self.assertEqual(zone["status"], "evaluated_shadow")
        self.assertIsNone(zone["outputs"]["fibonacci_at_entry"])

    def test_long_liquidations_are_partitioned_by_path_without_raw_clusters(self):
        liquidation = self.evaluate()["traces"][3]["outputs"]

        self.assertEqual(
            liquidation["approach_path"]["visible_notional_usd"], 1000
        )
        self.assertEqual(
            liquidation["overshoot_path_entry_to_sl"]["visible_notional_usd"],
            2000,
        )
        self.assertEqual(
            liquidation["post_activation_target_path"]["visible_notional_usd"],
            8000,
        )
        self.assertNotIn("clusters", liquidation)
        self.assertEqual(
            liquidation["interpretation_policy"],
            "visible_mass_descriptor_not_causal_attraction_or_probability",
        )

    def test_short_liquidations_mirror_the_three_path_regions(self):
        contract = self.contract(
            side="short",
            requested_entry=102,
            stop_loss=104,
            take_profit=97,
            trigger_condition="price_gte",
        )
        liquidation = self.evaluate(
            contract,
            observational_traces=self.observations(side="short"),
        )["traces"][3]["outputs"]

        self.assertEqual(
            liquidation["approach_path"]["visible_notional_usd"], 8000
        )
        self.assertEqual(
            liquidation["overshoot_path_entry_to_sl"]["visible_notional_usd"],
            7000,
        )
        self.assertEqual(
            liquidation["post_activation_target_path"]["visible_notional_usd"],
            3000,
        )

    def test_unavailable_liquidations_block_only_optional_rule(self):
        result = self.evaluate(
            liquidation_context={
                "available": False,
                "status": "unsupported",
                "reason": "symbol_not_supported_by_provider",
            }
        )

        self.assertEqual(result["status"], "partially_evaluated_shadow")
        self.assertEqual(result["evaluated_rule_count"], 3)
        self.assertEqual(result["traces"][3]["status"], "blocked")

    def test_missing_trajectory_parents_do_not_block_zone_or_liquidations(self):
        result = self.evaluate(m5_analysis={"traces": []})

        self.assertEqual(result["traces"][0]["status"], "blocked")
        self.assertEqual(result["traces"][1]["status"], "evaluated_shadow")
        self.assertEqual(result["traces"][2]["status"], "evaluated_shadow")
        self.assertEqual(result["traces"][3]["status"], "evaluated_shadow")

    def test_all_rules_have_zero_probability_effect_and_no_coefficients(self):
        result = self.evaluate()

        self.assertEqual(result["rule_ids"], list(RULE_IDS))
        for trace in result["traces"]:
            self.assertEqual(
                trace["probability_effect"], "none_shadow_descriptor"
            )
            self.assertEqual(trace["coefficient_status"], "not_estimated")
        self.assertEqual(
            result["double_counting_policy"]["probability_effect"], "none"
        )

    def test_runtime_hash_is_deterministic(self):
        self.assertEqual(
            self.evaluate()["runtime_trace_sha256"],
            self.evaluate()["runtime_trace_sha256"],
        )

    def test_contract_and_baseline_must_match(self):
        contract = self.contract()
        baseline = self.baseline(contract)
        baseline["analysis_id"] = "different-analysis"

        with self.assertRaisesRegex(LimitContextRuleError, "analysis_id_mismatch"):
            evaluate_limit_context_rule_family(
                contract,
                baseline,
                m5_analysis=self.m5_traces(),
                observational_traces=self.observations(),
            )


if __name__ == "__main__":
    unittest.main()
