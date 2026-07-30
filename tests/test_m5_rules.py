from __future__ import annotations

import math
import unittest

from m5_rules import EVALUATORS, execute_rule, rule_specs


FIXED_TIME = "2026-07-27T12:00:00+00:00"
BASE_MS = 1_800_000_000_000


def run_rule(rule_id, inputs, dependencies=None):
    return execute_rule(
        rule_id,
        analysis_id="m5-rule-test",
        inputs=inputs,
        dependencies=dependencies,
        executed_at=FIXED_TIME,
    )


def closed_prices(count=61, interval_seconds=60, growth=0.001):
    values = []
    price = 100.0
    for index in range(count):
        values.append(
            {
                "close": price,
                "close_time": BASE_MS + index * interval_seconds * 1000,
                "closed": True,
            }
        )
        price *= 1 + growth
    return values


class M53RuleImplementationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sampling = run_rule(
            "M4-RULE-HORIZON-SAMPLING-001",
            {
                "time_horizon": "intraday_short",
                "horizon_seconds": 3600,
                "profile_intervals_seconds": [60, 300, 900],
            },
        )
        cls.geometry = run_rule(
            "M4-RULE-PLAN-GEOMETRY-001",
            {
                "side": "long",
                "entry": 100,
                "take_profit": 110,
                "stop_loss": 95,
            },
        )
        cls.returns = run_rule(
            "M4-RULE-LOG-RETURNS-001",
            {
                "closes": closed_prices(),
                "interval_seconds": 60,
            },
            {"M4-RULE-HORIZON-SAMPLING-001": cls.sampling},
        )
        cls.volatility = run_rule(
            "M4-RULE-REALIZED-VOLATILITY-001",
            {},
            {
                "M4-RULE-HORIZON-SAMPLING-001": cls.sampling,
                "M4-RULE-LOG-RETURNS-001": cls.returns,
            },
        )
        cls.path = run_rule(
            "M4-RULE-PATH-STRUCTURE-001",
            {"window_seconds": 3600},
            {
                "M4-RULE-HORIZON-SAMPLING-001": cls.sampling,
                "M4-RULE-LOG-RETURNS-001": cls.returns,
            },
        )
        cls.oi = run_rule(
            "M4-RULE-OPEN-INTEREST-CHANGE-001",
            {
                "previous_timestamp_ms": BASE_MS,
                "current_timestamp_ms": BASE_MS + 3_600_000,
                "horizon_seconds": 3600,
                "previous_open_interest": 1000,
                "current_open_interest": 1100,
            },
        )

    def test_registry_implements_exactly_all_27_rules(self) -> None:
        self.assertEqual(set(EVALUATORS), set(rule_specs()))
        self.assertEqual(len(EVALUATORS), 27)

    def test_sampling_uses_largest_exact_valid_interval(self) -> None:
        self.assertEqual(self.sampling.status, "evaluated")
        self.assertEqual(self.sampling.outputs["interval_seconds"], 60)
        self.assertEqual(self.sampling.outputs["returns_per_horizon"], 60)
        blocked = run_rule(
            "M4-RULE-HORIZON-SAMPLING-001",
            {
                "horizon_seconds": 1000,
                "profile_intervals_seconds": [60, 300],
            },
        )
        self.assertEqual(blocked.status, "not_applicable")

    def test_plan_geometry_is_directionally_symmetric(self) -> None:
        long = self.geometry
        short = run_rule(
            "M4-RULE-PLAN-GEOMETRY-001",
            {
                "side": "short",
                "entry": 100,
                "take_profit": 10000 / 110,
                "stop_loss": 10000 / 95,
            },
        )
        self.assertAlmostEqual(
            long.outputs["tp_log_distance"],
            short.outputs["tp_log_distance"],
        )
        self.assertAlmostEqual(
            long.outputs["sl_log_distance"],
            short.outputs["sl_log_distance"],
        )

    def test_log_returns_and_realized_volatility_match_manual_formula(self) -> None:
        self.assertEqual(self.returns.status, "evaluated")
        self.assertEqual(self.returns.outputs["return_count"], 60)
        expected_return = math.log(1.001)
        self.assertAlmostEqual(
            self.returns.outputs["return_series"][0],
            expected_return,
        )
        self.assertAlmostEqual(
            self.volatility.outputs["realized_variance"],
            60 * expected_return**2,
        )
        self.assertAlmostEqual(
            self.volatility.outputs["realized_volatility"],
            math.sqrt(60) * expected_return,
        )

    def test_normalized_barrier_geometry_uses_plan_and_sigma(self) -> None:
        trace = run_rule(
            "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            {},
            {
                "M4-RULE-PLAN-GEOMETRY-001": self.geometry,
                "M4-RULE-REALIZED-VOLATILITY-001": self.volatility,
            },
        )
        self.assertEqual(trace.status, "evaluated")
        self.assertAlmostEqual(
            trace.outputs["z_tp"],
            self.geometry.outputs["tp_log_distance"]
            / self.volatility.outputs["realized_volatility"],
        )
        self.assertNotIn("probability", trace.outputs)

    def test_market_activation_is_zero_and_pending_is_deferred(self) -> None:
        market = run_rule(
            "M4-RULE-PENDING-ACTIVATION-001",
            {"entry_type": "market", "entry": 100, "current_price": 101},
            {
                "M4-RULE-PLAN-GEOMETRY-001": self.geometry,
                "M4-RULE-REALIZED-VOLATILITY-001": self.volatility,
            },
        )
        self.assertEqual(market.outputs["z_entry"], 0)
        pending = run_rule(
            "M4-RULE-PENDING-ACTIVATION-001",
            {"entry_type": "limit", "entry": 100, "current_price": 101},
            {
                "M4-RULE-PLAN-GEOMETRY-001": self.geometry,
                "M4-RULE-REALIZED-VOLATILITY-001": self.volatility,
            },
        )
        self.assertEqual(pending.status, "deferred")

    def test_smoother_and_path_structure_match_manual_calculation(self) -> None:
        smoother = run_rule(
            "M4-RULE-EXPONENTIAL-SMOOTHER-001",
            {"values": [1, 3, 5], "alpha": 0.5},
        )
        self.assertEqual(smoother.outputs["smoothed_value"], 3.5)
        self.assertAlmostEqual(self.path.outputs["path_efficiency"], 1.0)
        self.assertAlmostEqual(
            self.path.outputs["log_displacement"],
            sum(self.returns.outputs["return_series"]),
        )

    def test_prior_extrema_and_volatility_rank_are_continuous_outputs(self) -> None:
        extrema = run_rule(
            "M4-RULE-PRIOR-EXTREMA-001",
            {
                "bars": [
                    {"high": 105, "low": 97},
                    {"high": 108, "low": 98},
                ],
                "side": "long",
                "entry": 100,
                "take_profit": 110,
            },
            {"M4-RULE-PLAN-GEOMETRY-001": self.geometry},
        )
        self.assertEqual(extrema.outputs["prior_high"], 108)
        self.assertTrue(
            extrema.outputs["target_extreme_between_entry_and_tp"]
        )
        rank = run_rule(
            "M4-RULE-VOLATILITY-RANK-001",
            {
                "current_realized_variance": 30,
                "reference_variances": list(range(60)),
                "reference_cutoff": BASE_MS,
            },
            {"M4-RULE-REALIZED-VOLATILITY-001": self.volatility},
        )
        self.assertAlmostEqual(rank.outputs["volatility_percentile"], 30.5 / 60)
        self.assertNotIn("regime_label", rank.outputs)

    def test_mtf_and_continuous_regime_do_not_create_scores(self) -> None:
        mtf = run_rule(
            "M4-RULE-MTF-HIERARCHY-001",
            {
                "signed_path_efficiencies": {
                    "H": 0.2,
                    "2H": -0.1,
                    "4H": 0.0,
                }
            },
            {"M4-RULE-PATH-STRUCTURE-001": self.path},
        )
        self.assertEqual(mtf.outputs["agreement_descriptor"], "flat_present")
        rank = run_rule(
            "M4-RULE-VOLATILITY-RANK-001",
            {
                "current_realized_variance": 30,
                "reference_variances": list(range(60)),
            },
            {"M4-RULE-REALIZED-VOLATILITY-001": self.volatility},
        )
        regime = run_rule(
            "M4-RULE-CONTINUOUS-REGIME-001",
            {},
            {
                "M4-RULE-PATH-STRUCTURE-001": self.path,
                "M4-RULE-VOLATILITY-RANK-001": rank,
            },
        )
        self.assertEqual(
            set(regime.outputs),
            {"volatility_percentile", "signed_path_efficiency"},
        )

    def test_aggressor_and_open_interest_use_exact_observations(self) -> None:
        ati = run_rule(
            "M4-RULE-AGGRESSOR-IMBALANCE-001",
            {
                "ati_source": "trades",
                "trades": [
                    {
                        "price": 100,
                        "quantity": 2,
                        "buyer_is_maker": False,
                    },
                    {
                        "price": 100,
                        "quantity": 1,
                        "buyer_is_maker": True,
                    },
                ],
                "window_start_ms": BASE_MS,
                "window_end_ms": BASE_MS + 3_600_000,
                "coverage_start_ms": BASE_MS,
                "coverage_end_ms": BASE_MS + 3_600_000,
            },
        )
        self.assertAlmostEqual(ati.outputs["ATI_H"], 1 / 3)
        self.assertAlmostEqual(self.oi.outputs["dOI_H"], math.log(1.1))

    def test_price_oi_state_is_a_container_without_positioning_label(self) -> None:
        trace = run_rule(
            "M4-RULE-PRICE-OI-STATE-001",
            {},
            {
                "M4-RULE-PATH-STRUCTURE-001": self.path,
                "M4-RULE-OPEN-INTEREST-CHANGE-001": self.oi,
            },
        )
        self.assertEqual(trace.outputs["price_sign"], 1)
        self.assertEqual(trace.outputs["oi_sign"], 1)
        self.assertNotIn("positioning_label", trace.outputs)

    def test_basis_and_mark_index_keep_semantics_separate(self) -> None:
        basis = run_rule(
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            {
                "futures_bid": 101,
                "futures_ask": 102,
                "spot_bid": 99,
                "spot_ask": 100,
                "futures_received_at_ms": BASE_MS,
                "spot_received_at_ms": BASE_MS,
                "spot_symbol_status": "TRADING",
                "capture_limit_ms": 10,
            },
        )
        self.assertAlmostEqual(
            basis.outputs["b_mid"],
            math.log(101.5 / 99.5),
        )
        premium = run_rule(
            "M4-RULE-MARK-INDEX-PREMIUM-001",
            {
                "mark_price": 101,
                "index_price": 100,
                "provider_time": BASE_MS,
            },
        )
        self.assertFalse(premium.outputs["binance_spot_basis"])
        self.assertAlmostEqual(
            premium.outputs["mark_index_log_premium"],
            math.log(1.01),
        )

    def test_funding_state_uses_realized_load_without_future_cost(self) -> None:
        trace = run_rule(
            "M4-RULE-FUNDING-STATE-001",
            {
                "last_funding_rate": 0.0008,
                "funding_interval_hours": 8,
                "current_time_ms": BASE_MS,
                "horizon_seconds": 3600,
                "previous_events": [
                    {"time_ms": BASE_MS - 1_000_000, "rate": 0.0005}
                ],
                "scheduled_event_times_ms": [BASE_MS + 1_000_000],
            },
        )
        self.assertAlmostEqual(
            trace.outputs["linearized_last_funding_rate_per_hour"],
            0.0001,
        )
        self.assertIsNone(trace.outputs["projected_funding_cost"])

    def test_derivatives_context_selects_one_basis_source(self) -> None:
        ati = run_rule(
            "M4-RULE-AGGRESSOR-IMBALANCE-001",
            {
                "ati_source": "periodic",
                "periods": [{"buy_volume": 60, "sell_volume": 40}],
                "window_start_ms": BASE_MS,
                "window_end_ms": BASE_MS + 3_600_000,
                "coverage_start_ms": BASE_MS,
                "coverage_end_ms": BASE_MS + 3_600_000,
            },
        )
        basis = run_rule(
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            {
                "futures_bid": 101,
                "futures_ask": 102,
                "spot_bid": 99,
                "spot_ask": 100,
                "futures_received_at_ms": BASE_MS,
                "spot_received_at_ms": BASE_MS,
                "spot_symbol_status": "TRADING",
            },
        )
        premium = run_rule(
            "M4-RULE-MARK-INDEX-PREMIUM-001",
            {
                "mark_price": 101,
                "index_price": 100,
                "provider_time": BASE_MS,
            },
        )
        funding = run_rule(
            "M4-RULE-FUNDING-STATE-001",
            {
                "last_funding_rate": 0.0008,
                "funding_interval_hours": 8,
                "current_time_ms": BASE_MS,
                "horizon_seconds": 3600,
            },
        )
        trace = run_rule(
            "M4-RULE-DERIVATIVES-CONTEXT-001",
            {"basis_source": "spot_futures"},
            {
                "M4-RULE-AGGRESSOR-IMBALANCE-001": ati,
                "M4-RULE-OPEN-INTEREST-CHANGE-001": self.oi,
                "M4-RULE-SPOT-FUTURES-BASIS-001": basis,
                "M4-RULE-MARK-INDEX-PREMIUM-001": premium,
                "M4-RULE-FUNDING-STATE-001": funding,
            },
        )
        self.assertEqual(trace.outputs["basis_source"], "spot_futures")
        self.assertNotIn("aggregate_score", trace.outputs)

    def test_spread_depth_and_fee_formulas_match_manual_values(self) -> None:
        spread = run_rule(
            "M4-RULE-QUOTED-SPREAD-001",
            {"best_bid": 99, "best_ask": 101, "receive_time": BASE_MS},
        )
        self.assertEqual(spread.outputs["mid"], 100)
        self.assertEqual(spread.outputs["spread_fraction_mid"], 0.02)
        depth = run_rule(
            "M4-RULE-DEPTH-SWEEP-001",
            {
                "side": "buy",
                "base_quantity": 2,
                "arrival_mid": 100,
                "asks": [
                    {"price": 101, "quantity": 1},
                    {"price": 102, "quantity": 1},
                ],
            },
            {"M4-RULE-QUOTED-SPREAD-001": spread},
        )
        self.assertEqual(depth.outputs["vwap_filled"], 101.5)
        self.assertEqual(
            depth.outputs["implementation_shortfall_filled_quote"],
            3,
        )
        self.assertEqual(depth.outputs["fill_ratio"], 1.0)
        self.assertEqual(depth.outputs["availability_status"], "available")
        fee = run_rule(
            "M4-RULE-FEE-SCENARIOS-001",
            {
                "notional": 1000,
                "commission_rates": {"maker": 0.0002, "taker": 0.0005},
                "allowed_roles": ["maker", "taker"],
            },
        )
        self.assertEqual(fee.outputs["fee_lower"], 0.2)
        self.assertEqual(fee.outputs["fee_upper"], 0.5)

    def test_partial_visible_depth_is_traced_without_inventing_full_cost(
        self,
    ) -> None:
        spread = run_rule(
            "M4-RULE-QUOTED-SPREAD-001",
            {"best_bid": 99, "best_ask": 101, "receive_time": BASE_MS},
        )
        depth = run_rule(
            "M4-RULE-DEPTH-SWEEP-001",
            {
                "side": "buy",
                "base_quantity": 2,
                "asks": [{"price": 101, "quantity": 0.8}],
            },
            {"M4-RULE-QUOTED-SPREAD-001": spread},
        )

        self.assertEqual(depth.status, "evaluated")
        self.assertAlmostEqual(depth.outputs["fill_ratio"], 0.4)
        self.assertAlmostEqual(depth.outputs["unfilled_quantity"], 1.2)
        self.assertIsNone(depth.outputs["complete_vwap"])
        self.assertEqual(
            depth.outputs["availability_status"],
            "insufficient_visible_depth",
        )

    def test_stale_book_snapshot_blocks_economic_measurement(self) -> None:
        spread = run_rule(
            "M4-RULE-QUOTED-SPREAD-001",
            {
                "best_bid": 99,
                "best_ask": 101,
                "receive_time": BASE_MS,
                "capture_time": BASE_MS + 30_001,
                "max_age_ms": 30_000,
            },
        )

        self.assertEqual(spread.status, "blocked")
        self.assertEqual(spread.reason_codes, ("stale_quoted_book",))
        self.assertEqual(spread.outputs, {})

    def test_funding_cashflow_and_exposure_preserve_signs(self) -> None:
        funding = run_rule(
            "M4-RULE-FUNDING-CASHFLOW-001",
            {
                "side": "long",
                "base_quantity": 2,
                "events": [{"mark_price": 100, "funding_rate": 0.001}],
            },
        )
        self.assertEqual(funding.outputs["cashflow_total"], -0.2)
        exposure = run_rule(
            "M4-RULE-PLAN-EXPOSURE-001",
            {
                "side": "long",
                "entry": 100,
                "take_profit": 110,
                "stop_loss": 95,
                "margin": 100,
                "leverage": 2,
            },
            {"M4-RULE-PLAN-GEOMETRY-001": self.geometry},
        )
        self.assertEqual(exposure.outputs["notional"], 200)
        self.assertEqual(exposure.outputs["quantity"], 2)
        self.assertEqual(exposure.outputs["gross_reward"], 20)
        self.assertEqual(exposure.outputs["gross_risk"], 10)

    def test_net_payoff_identity_and_no_entry_constraint(self) -> None:
        trace = run_rule(
            "M4-RULE-NET-PAYOFFS-001",
            {
                "gross_price_pnl": {"tp": 20, "sl": -10, "no_entry": 0},
                "fee_cost": {"tp": 1, "sl": 1, "no_entry": 0},
                "execution_shortfall_cost": {
                    "tp": 0.5,
                    "sl": 0.5,
                    "no_entry": 0,
                },
                "funding_cashflow": {"tp": -0.2, "sl": -0.1, "no_entry": 0},
            },
        )
        self.assertAlmostEqual(
            trace.outputs["net_payoff_by_outcome"]["tp"],
            18.3,
        )
        self.assertEqual(
            trace.outputs["net_payoff_by_outcome"]["no_entry"],
            0,
        )

    def test_expected_value_is_implemented_but_blocked_until_m6(self) -> None:
        deferred = run_rule(
            "M4-RULE-EXPECTED-VALUE-001",
            {
                "probabilities": {"tp": 0.6, "sl": 0.4},
                "net_payoffs": {"tp": 10, "sl": -5},
            },
        )
        self.assertEqual(deferred.status, "deferred")
        evaluated = run_rule(
            "M4-RULE-EXPECTED-VALUE-001",
            {
                "m6_probabilities_authorized": True,
                "probabilities": {"tp": 0.6, "sl": 0.4},
                "net_payoffs": {"tp": 10, "sl": -5},
            },
        )
        self.assertEqual(evaluated.outputs["expected_value"], 4)

    def test_readiness_never_authorizes_decision(self) -> None:
        trace = run_rule(
            "M4-RULE-EVALUATION-READINESS-001",
            {
                "statuses": {
                    "market_probabilities": "blocked",
                    "entry_execution": "available",
                    "exit_execution": "available",
                    "fees": "available",
                    "funding": "available",
                    "payoffs": "available",
                    "account_risk": "blocked",
                }
            },
        )
        self.assertFalse(trace.outputs["economic_ready"])
        self.assertFalse(trace.outputs["account_risk_ready"])
        self.assertFalse(trace.outputs["decision_authorized"])

    def test_invalid_or_missing_data_blocks_without_numeric_output(self) -> None:
        trace = run_rule(
            "M4-RULE-QUOTED-SPREAD-001",
            {"best_bid": 101, "best_ask": 99, "receive_time": BASE_MS},
        )
        self.assertEqual(trace.status, "blocked")
        self.assertEqual(trace.outputs, {})


if __name__ == "__main__":
    unittest.main()
