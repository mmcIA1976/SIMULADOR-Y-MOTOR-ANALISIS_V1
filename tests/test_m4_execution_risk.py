from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m4_execution_risk as m4  # noqa: E402


class M45ExecutionRiskTests(unittest.TestCase):
    def test_quoted_spread(self) -> None:
        value = m4.quoted_spread(99.0, 101.0)
        self.assertEqual(value["midpoint"], 100.0)
        self.assertEqual(value["spread_quote"], 2.0)
        self.assertEqual(value["spread_fraction_mid"], 0.02)

    def test_quoted_spread_rejects_crossed_book(self) -> None:
        with self.assertRaisesRegex(ValueError, "crossed_book"):
            m4.quoted_spread(101.0, 100.0)

    def test_buy_sweep_consumes_asks_and_includes_spread(self) -> None:
        value = m4.depth_sweep(
            side="buy",
            requested_quantity=3.0,
            bids=[[99.0, 10.0]],
            asks=[[101.0, 1.0], [102.0, 2.0]],
        )
        self.assertEqual(value["status"], "complete_visible_sweep")
        self.assertAlmostEqual(value["vwap_filled"], 305.0 / 3.0)
        self.assertAlmostEqual(value["vwap"], 305.0 / 3.0)
        self.assertAlmostEqual(
            value["implementation_shortfall_fraction_mid"],
            ((305.0 / 3.0) - 100.0) / 100.0,
        )
        self.assertFalse(value["future_exit_estimate_authorized"])

    def test_sell_sweep_sign_is_positive_cost(self) -> None:
        value = m4.depth_sweep(
            side="sell",
            requested_quantity=2.0,
            bids=[[99.0, 1.0], [98.0, 1.0]],
            asks=[[101.0, 5.0]],
        )
        self.assertAlmostEqual(value["vwap"], 98.5)
        self.assertAlmostEqual(
            value["implementation_shortfall_fraction_mid"],
            0.015,
        )

    def test_incomplete_visible_depth_blocks_complete_vwap(self) -> None:
        value = m4.depth_sweep(
            side="buy",
            requested_quantity=5.0,
            bids=[[99.0, 5.0]],
            asks=[[101.0, 2.0]],
        )
        self.assertEqual(value["status"], "insufficient_visible_depth")
        self.assertEqual(value["fill_ratio"], 0.4)
        self.assertEqual(value["filled_quantity"], 2.0)
        self.assertEqual(value["unfilled_quantity"], 3.0)
        self.assertEqual(value["vwap_filled"], 101.0)
        self.assertAlmostEqual(
            value["filled_implementation_shortfall_fraction_mid"],
            0.01,
        )
        self.assertIsNone(value["vwap"])
        self.assertIsNone(value["implementation_shortfall_fraction_mid"])
        self.assertNotIn("partial_vwap", value)

    def test_depth_order_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "asks_not_ascending"):
            m4.depth_sweep(
                side="buy",
                requested_quantity=1.0,
                bids=[[99.0, 1.0]],
                asks=[[102.0, 1.0], [101.0, 1.0]],
            )

    def test_fee_known_role_is_pretrade_scenario_until_observed(self) -> None:
        value = m4.fee_cost_bounds(
            notional=10_000.0,
            allowed_roles=["taker"],
            rates={"maker": 0.0002, "taker": 0.0005, "rpi": 0.0001},
        )
        self.assertFalse(value["exact"])
        self.assertEqual(value["status"], "single_role_pretrade_scenario")
        self.assertEqual(
            value["value_quality"]["lower_cost"],
            "scenario_point",
        )
        self.assertEqual(value["lower_cost"], 5.0)
        self.assertEqual(value["upper_cost"], 5.0)

    def test_fee_is_exact_only_for_observed_execution(self) -> None:
        value = m4.fee_cost_bounds(
            notional=10_000.0,
            allowed_roles=["taker"],
            rates={"taker": 0.0005},
            observed_execution=True,
            fee_asset="USDT",
        )
        self.assertTrue(value["exact"])
        self.assertEqual(
            value["status"],
            "observed_exact_from_executed_notional_and_rate",
        )
        self.assertEqual(
            value["value_quality"]["lower_cost"],
            "observed_exact",
        )
        self.assertEqual(value["notional_basis"], "executed_notional")
        self.assertEqual(value["fee_asset"], "USDT")

    def test_observed_fee_requires_unique_role_and_fee_asset(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "observed_execution_requires_one_role",
        ):
            m4.fee_cost_bounds(
                notional=10_000.0,
                allowed_roles=["maker", "taker"],
                rates={"maker": 0.0002, "taker": 0.0005},
                observed_execution=True,
                fee_asset="USDT",
            )
        with self.assertRaisesRegex(
            ValueError,
            "observed_execution_requires_fee_asset",
        ):
            m4.fee_cost_bounds(
                notional=10_000.0,
                allowed_roles=["taker"],
                rates={"taker": 0.0005},
                observed_execution=True,
            )

    def test_fee_bounds_for_unknown_maker_or_taker_role(self) -> None:
        value = m4.fee_cost_bounds(
            notional=10_000.0,
            allowed_roles=["maker", "taker"],
            rates={"maker": 0.0002, "taker": 0.0005},
        )
        self.assertEqual(value["status"], "bounded_role_scenario")
        self.assertEqual(value["lower_cost"], 2.0)
        self.assertEqual(value["upper_cost"], 5.0)

    def test_fee_blocks_when_authenticated_rate_is_missing(self) -> None:
        value = m4.fee_cost_bounds(
            notional=10_000.0,
            allowed_roles=["maker", "taker"],
            rates={"maker": 0.0002, "taker": None},
        )
        self.assertEqual(
            value["status"],
            "blocked_missing_authenticated_rate",
        )
        self.assertIsNone(value["lower_cost"])

    def test_funding_cashflow_preserves_side_and_rate_sign(self) -> None:
        events = [{"mark_price": 100.0, "funding_rate": 0.001}]
        long_value = m4.funding_cashflow(
            side="long",
            quantity=2.0,
            events=events,
        )
        short_value = m4.funding_cashflow(
            side="short",
            quantity=2.0,
            events=events,
        )
        self.assertEqual(long_value["cashflow_quote"], -0.2)
        self.assertEqual(short_value["cashflow_quote"], 0.2)
        self.assertFalse(long_value["future_rate_forecast_authorized"])

    def test_plan_exposure_long(self) -> None:
        value = m4.plan_exposure(
            side="long",
            entry=100.0,
            take_profit=110.0,
            stop_loss=95.0,
            margin=100.0,
            leverage=2.0,
        )
        self.assertEqual(value["notional_quote"], 200.0)
        self.assertEqual(value["quantity_base"], 2.0)
        self.assertEqual(value["gross_reward_quote"], 20.0)
        self.assertEqual(value["gross_risk_quote"], 10.0)
        self.assertEqual(value["gross_reward_to_risk"], 2.0)
        self.assertEqual(value["gross_risk_fraction_margin"], 0.1)
        self.assertFalse(value["market_probability_effect_authorized"])

    def test_plan_exposure_short_is_direction_symmetric(self) -> None:
        value = m4.plan_exposure(
            side="short",
            entry=100.0,
            take_profit=90.0,
            stop_loss=105.0,
            margin=100.0,
            leverage=2.0,
        )
        self.assertEqual(value["gross_reward_quote"], 20.0)
        self.assertEqual(value["gross_risk_quote"], 10.0)

    def test_plan_exposure_rejects_invalid_geometry(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_long_geometry"):
            m4.plan_exposure(
                side="long",
                entry=100.0,
                take_profit=90.0,
                stop_loss=105.0,
                margin=100.0,
                leverage=2.0,
            )

    def test_net_payoff_uses_signed_funding(self) -> None:
        value = m4.net_outcome_payoffs(
            {
                "tp": {
                    "entered": True,
                    "gross_price_pnl": 20.0,
                    "fee_cost": 2.0,
                    "execution_shortfall_cost": 1.0,
                    "funding_cashflow": -0.5,
                },
                "no_entry": {"entered": False},
            }
        )
        self.assertEqual(value["status"], "complete")
        self.assertEqual(
            value["outcomes"]["tp"]["net_payoff_quote"],
            16.5,
        )
        self.assertEqual(
            value["outcomes"]["no_entry"]["net_payoff_quote"],
            0.0,
        )
        self.assertFalse(
            value["outcomes"]["no_entry"]["opportunity_cost_included"]
        )

    def test_missing_outcome_cost_blocks_payoff_vector(self) -> None:
        value = m4.net_outcome_payoffs(
            {
                "sl": {
                    "entered": True,
                    "gross_price_pnl": -10.0,
                    "fee_cost": 2.0,
                    "execution_shortfall_cost": None,
                    "funding_cashflow": 0.0,
                }
            }
        )
        self.assertEqual(value["status"], "incomplete")
        self.assertIsNone(
            value["outcomes"]["sl"]["net_payoff_quote"]
        )

    def test_expected_value_identity(self) -> None:
        value = m4.expected_value(
            probabilities={"tp": 0.4, "sl": 0.6},
            payoffs={"tp": 20.0, "sl": -10.0},
        )
        self.assertEqual(value, 2.0)

    def test_expected_value_rejects_incoherent_probabilities(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "probabilities_do_not_sum_to_one",
        ):
            m4.expected_value(
                probabilities={"tp": 0.6, "sl": 0.6},
                payoffs={"tp": 20.0, "sl": -10.0},
            )

    def test_readiness_never_authorizes_decision_or_grade(self) -> None:
        value = m4.evaluation_readiness(
            {
                "market_probabilities": "available",
                "entry_execution": "available",
                "exit_execution": "scenario_only",
                "fees": "available",
                "funding": "scenario_only",
                "payoffs": "unavailable",
                "account_risk": "unavailable",
            }
        )
        self.assertFalse(value["economic_evaluation_ready"])
        self.assertFalse(value["account_risk_ready"])
        self.assertFalse(value["decision_authorized"])
        self.assertIsNone(value["numeric_quality_score"])
        self.assertIsNone(value["grade"])

    def test_catalog_has_no_predictive_or_productive_effects(self) -> None:
        catalog = m4.build_catalog()
        self.assertEqual(catalog["scope"]["rules"], 8)
        self.assertEqual(catalog["summary"]["predictive_hypotheses"], 0)
        self.assertFalse(catalog["summary"]["current_ev_authorized"])
        self.assertFalse(catalog["summary"]["grade_authorized"])
        self.assertFalse(catalog["summary"]["decision_authorized"])
        self.assertEqual(catalog["scope"]["m4_next_subphase"], "M4.6")
        for rule in catalog["rules"]:
            self.assertFalse(rule["direct_probability_effect_authorized"])
            self.assertFalse(rule["numeric_weight_authorized"])
            self.assertFalse(rule["production_authorized"])
            self.assertIsNone(rule["separate_predictive_hypothesis"])

    def test_every_rule_uses_the_complete_m4_documentation_contract(self) -> None:
        required = {
            "analytical_blocks",
            "concrete_objective",
            "rule_type",
            "raw_data_and_provider",
            "market_symbol_timestamp_unit_freshness",
            "exact_transformation_and_formula",
            "cross_pair_normalization",
            "applicable_horizons",
            "activation_conditions",
            "non_application_conditions",
            "source_and_exact_supported_claim",
            "claims_not_supported_by_source",
            "expected_relation_to_tp_sl_or_expiry",
            "related_rules",
            "double_counting_control",
            "missing_data_behavior",
            "unit_tests_limits_and_invariants",
            "trace_output",
            "refutation_suspension_or_withdrawal",
            "lifecycle_status",
        }
        for rule in m4.build_catalog()["rules"]:
            self.assertTrue(required.issubset(rule), rule["id"])
            self.assertEqual(rule["version"], m4.RULE_VERSION)
            for field in required:
                self.assertTrue(rule[field], f"{rule['id']}:{field}")

    def test_all_pairs_and_horizons_are_preserved(self) -> None:
        catalog = m4.build_catalog()
        for rule in catalog["rules"]:
            self.assertEqual(tuple(rule["symbols"]), m4.SYMBOLS)
            self.assertEqual(tuple(rule["horizons"]), m4.HORIZONS)

    def test_current_heuristic_costs_and_scores_are_superseded(self) -> None:
        superseded = m4.build_catalog()["supersedes_current_elements"]
        required = {
            "SCORE-LIQUIDITY_PENALTY",
            "OUT-FEE",
            "OUT-SLIPPAGE",
            "OUT-FUNDING-COST",
            "OUT-RISK-SCORE",
            "OUT-EV-COST",
            "OUT-GRADE",
            "OUT-CONFIDENCE",
            "OUT-DECISION",
            "OUT-LAYERED-SCORES",
            "GATE-RR_RATIO_GTE_3",
        }
        self.assertTrue(required.issubset(superseded))

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "build_m4_execution_risk.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_catalog_matches_builder(self) -> None:
        path = (
            ROOT
            / "auditorias_motor"
            / "catalogo_ejecucion_riesgo_m4_5_v0_2.json"
        )
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written, m4.build_catalog())


if __name__ == "__main__":
    unittest.main()
