from __future__ import annotations

import math
import unittest

from m5_rules import EVALUATORS, execute_rule


FIXED_TIME = "2026-07-27T12:00:00+00:00"
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = (
    ("intraday_short", 3600),
    ("intraday_wide", 14_400),
    ("short_swing", 86_400),
)


def run(rule_id, inputs):
    return execute_rule(
        rule_id,
        analysis_id="property-test",
        inputs=inputs,
        executed_at=FIXED_TIME,
    )


class M55PropertyTests(unittest.TestCase):
    def test_plan_geometry_is_scale_invariant_for_all_pairs_and_horizons(self) -> None:
        reference = None
        for symbol in SYMBOLS:
            for horizon, seconds in HORIZONS:
                for scale in (0.01, 1, 1000):
                    trace = run(
                        "M4-RULE-PLAN-GEOMETRY-001",
                        {
                            "symbol": symbol,
                            "time_horizon": horizon,
                            "horizon_seconds": seconds,
                            "side": "long",
                            "entry": 100 * scale,
                            "take_profit": 110 * scale,
                            "stop_loss": 95 * scale,
                        },
                    )
                    self.assertEqual(trace.status, "evaluated")
                    observed = (
                        trace.outputs["tp_log_distance"],
                        trace.outputs["sl_log_distance"],
                    )
                    reference = reference or observed
                    self.assertAlmostEqual(observed[0], reference[0])
                    self.assertAlmostEqual(observed[1], reference[1])

    def test_long_short_reciprocal_symmetry_holds_across_scales(self) -> None:
        for scale in (0.1, 1, 10_000):
            long = run(
                "M4-RULE-PLAN-GEOMETRY-001",
                {
                    "side": "long",
                    "entry": 100 * scale,
                    "take_profit": 110 * scale,
                    "stop_loss": 95 * scale,
                },
            )
            short = run(
                "M4-RULE-PLAN-GEOMETRY-001",
                {
                    "side": "short",
                    "entry": 100 * scale,
                    "take_profit": (10000 / 110) * scale,
                    "stop_loss": (10000 / 95) * scale,
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

    def test_target_distance_is_monotone_with_farther_valid_target(self) -> None:
        distances = []
        for target in (101, 105, 110, 120):
            trace = run(
                "M4-RULE-PLAN-GEOMETRY-001",
                {
                    "side": "long",
                    "entry": 100,
                    "take_profit": target,
                    "stop_loss": 95,
                },
            )
            distances.append(trace.outputs["tp_log_distance"])
        self.assertEqual(distances, sorted(distances))
        self.assertEqual(len(distances), len(set(distances)))

    def test_path_efficiency_bounds_follow_from_definition(self) -> None:
        for returns in (
            [0.1, 0.1, 0.1],
            [0.1, -0.1, 0.1],
            [-0.2, -0.1, 0.05],
            [0.0, 0.0, 0.0],
        ):
            displacement = sum(returns)
            variation = sum(abs(value) for value in returns)
            efficiency = abs(displacement) / variation if variation else 0
            signed = displacement / variation if variation else 0
            self.assertGreaterEqual(efficiency, 0)
            self.assertLessEqual(efficiency, 1)
            self.assertGreaterEqual(signed, -1)
            self.assertLessEqual(signed, 1)

    def test_aggressor_imbalance_is_bounded_and_antisymmetric(self) -> None:
        for buy, sell in ((100, 0), (75, 25), (50, 50), (0, 100)):
            total = buy + sell
            ati = (buy - sell) / total
            swapped = (sell - buy) / total
            self.assertGreaterEqual(ati, -1)
            self.assertLessEqual(ati, 1)
            self.assertAlmostEqual(ati, -swapped)

    def test_volatility_midrank_is_always_in_unit_interval(self) -> None:
        reference = list(range(60))
        for current in (0, 10, 30, 59, 100):
            below = sum(value < current for value in reference)
            equal = sum(value == current for value in reference)
            rank = (below + 0.5 * equal) / 60
            self.assertGreaterEqual(rank, 0)
            self.assertLessEqual(rank, 1)

    def test_fee_and_funding_cashflow_scale_linearly(self) -> None:
        for multiplier in (0.5, 2, 10):
            fee = run(
                "M4-RULE-FEE-SCENARIOS-001",
                {
                    "notional": 1000 * multiplier,
                    "commission_rates": {"taker": 0.0005},
                    "allowed_roles": ["taker"],
                },
            )
            self.assertAlmostEqual(
                fee.outputs["fee_lower"],
                0.5 * multiplier,
            )
            funding = run(
                "M4-RULE-FUNDING-CASHFLOW-001",
                {
                    "side": "long",
                    "base_quantity": 2 * multiplier,
                    "events": [
                        {"mark_price": 100, "funding_rate": 0.001}
                    ],
                },
            )
            self.assertAlmostEqual(
                funding.outputs["cashflow_total"],
                -0.2 * multiplier,
            )

    def test_no_evaluator_name_or_output_contract_contains_score_weight(self) -> None:
        forbidden = {"score", "bonus", "penalty", "weight", "probability_effect"}
        for rule_id in EVALUATORS:
            self.assertFalse(any(token in rule_id.lower() for token in forbidden))
        expected = run(
            "M4-RULE-EXPECTED-VALUE-001",
            {
                "probabilities": {"tp": 0.5, "sl": 0.5},
                "net_payoffs": {"tp": 1, "sl": -1},
            },
        )
        self.assertEqual(expected.status, "deferred")
        self.assertEqual(expected.outputs, {})

    def test_invalid_numeric_inputs_never_produce_evaluated_output(self) -> None:
        invalid_values = (None, 0, -1, float("nan"), float("inf"))
        for value in invalid_values:
            trace = run(
                "M4-RULE-QUOTED-SPREAD-001",
                {
                    "best_bid": value,
                    "best_ask": 101,
                    "receive_time": 1_800_000_000_000,
                },
            )
            self.assertNotEqual(trace.status, "evaluated")
            self.assertEqual(trace.outputs, {})

    def test_expected_value_identity_is_linear_when_m6_is_explicitly_enabled(self) -> None:
        first = run(
            "M4-RULE-EXPECTED-VALUE-001",
            {
                "m6_probabilities_authorized": True,
                "probabilities": {"a": 0.25, "b": 0.75},
                "net_payoffs": {"a": 4, "b": -2},
            },
        )
        second = run(
            "M4-RULE-EXPECTED-VALUE-001",
            {
                "m6_probabilities_authorized": True,
                "probabilities": {"a": 0.25, "b": 0.75},
                "net_payoffs": {"a": 8, "b": -4},
            },
        )
        self.assertAlmostEqual(
            second.outputs["expected_value"],
            2 * first.outputs["expected_value"],
        )
        self.assertTrue(
            math.isclose(first.outputs["probability_mass"], 1.0)
        )


if __name__ == "__main__":
    unittest.main()
