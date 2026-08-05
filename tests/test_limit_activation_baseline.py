from __future__ import annotations

import math
import unittest

from limit_activation_baseline import (
    LIMIT_ACTIVATION_MODEL_VERSION,
    LimitActivationBaselineError,
    activation_log_distance,
    build_limit_activation_baseline,
)
from limit_order_contract import build_limit_order_contract
from limit_activation_first_passage import (
    FirstPassageInputError,
    SINGLE_BARRIER_SOLVER_VERSION,
    single_barrier_first_passage,
)


class LimitActivationBaselineTests(unittest.TestCase):
    def contract(self, **overrides):
        values = {
            "analysis_id": "limit-activation-test",
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

    def test_single_barrier_matches_reflection_principle_reference(self):
        result = single_barrier_first_passage(
            log_distance=0.04,
            sigma_horizon=0.04,
        )
        expected = math.erfc(1 / math.sqrt(2))

        self.assertAlmostEqual(result.p_hit, expected, places=15)
        self.assertAlmostEqual(result.p_hit + result.p_no_hit, 1.0)
        self.assertEqual(
            result.solver_version,
            SINGLE_BARRIER_SOLVER_VERSION,
        )
        self.assertEqual(
            result.numerical_method,
            "reflection_principle_erfc",
        )

    def test_time_zero_has_no_activation(self):
        result = single_barrier_first_passage(
            log_distance=0.02,
            sigma_horizon=0.04,
            time_fraction=0,
        )

        self.assertEqual(result.p_hit, 0.0)
        self.assertEqual(result.p_no_hit, 1.0)
        self.assertEqual(result.numerical_method, "exact_time_zero")

    def test_activation_probability_is_monotone_in_time(self):
        values = [
            single_barrier_first_passage(
                log_distance=0.03,
                sigma_horizon=0.05,
                time_fraction=fraction,
            ).p_hit
            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]

        self.assertEqual(values, sorted(values))
        self.assertGreater(values[-1], values[1])

    def test_nearer_entry_has_higher_activation_probability(self):
        near = single_barrier_first_passage(
            log_distance=0.01,
            sigma_horizon=0.04,
        )
        far = single_barrier_first_passage(
            log_distance=0.05,
            sigma_horizon=0.04,
        )

        self.assertGreater(near.p_hit, far.p_hit)

    def test_more_volatility_has_higher_activation_probability(self):
        low = single_barrier_first_passage(
            log_distance=0.04,
            sigma_horizon=0.02,
        )
        high = single_barrier_first_passage(
            log_distance=0.04,
            sigma_horizon=0.08,
        )

        self.assertGreater(high.p_hit, low.p_hit)

    def test_long_and_short_mirror_have_same_distance_and_probability(self):
        long_distance = activation_log_distance(
            side="long",
            current_price=100,
            requested_entry=100 / 1.02,
        )
        short_distance = activation_log_distance(
            side="short",
            current_price=100,
            requested_entry=102,
        )
        long_result = build_limit_activation_baseline(
            self.contract(requested_entry=100 / 1.02, stop_loss=95),
            sigma_horizon=0.04,
        )
        short_result = build_limit_activation_baseline(
            self.contract(
                side="short",
                requested_entry=102,
                stop_loss=105,
                take_profit=97,
                trigger_condition="price_gte",
            ),
            sigma_horizon=0.04,
        )

        self.assertAlmostEqual(long_distance, short_distance, places=15)
        self.assertAlmostEqual(
            long_result["probabilities"]["activated_by_expiry"],
            short_result["probabilities"]["activated_by_expiry"],
            places=15,
        )

    def test_baseline_output_is_explicitly_shadow_and_uncalibrated(self):
        result = build_limit_activation_baseline(
            self.contract(),
            sigma_horizon=0.04,
        )

        self.assertEqual(result["model_version"], LIMIT_ACTIVATION_MODEL_VERSION)
        self.assertEqual(result["production_effect"], "shadow_only")
        self.assertEqual(result["status"], "evaluated_shadow_baseline")
        self.assertEqual(result["inputs"]["time_horizon"], "intraday_short")
        self.assertEqual(
            result["inputs"]["activation_horizon_seconds"],
            4 * 60 * 60,
        )
        self.assertEqual(
            result["calibration_status"],
            "not_empirically_calibrated_for_limit_orders",
        )
        self.assertFalse(
            result["interpretation"]["is_calibrated_user_probability"]
        )
        self.assertFalse(
            result["interpretation"]["may_change_operation_or_market_scoring"]
        )
        self.assertIn("liquidation_map", result["excluded_effects"])
        self.assertAlmostEqual(result["probability_mass"], 1.0)

    def test_cdf_is_monotone_and_finishes_at_expiry_probability(self):
        result = build_limit_activation_baseline(
            self.contract(),
            sigma_horizon=0.04,
        )
        cdf = result["activation_cdf"]
        activation_values = [item["activated_by_time"] for item in cdf]

        self.assertEqual(
            [item["time_fraction"] for item in cdf],
            [0.0, 0.25, 0.5, 0.75, 1.0],
        )
        self.assertEqual(activation_values, sorted(activation_values))
        self.assertAlmostEqual(
            activation_values[-1],
            result["probabilities"]["activated_by_expiry"],
        )

    def test_custom_checkpoints_must_be_sorted_unique_and_include_expiry(self):
        for checkpoints in (
            (),
            (0.5, 0.25, 1.0),
            (0.5, 0.5, 1.0),
            (0.0, 0.5),
            (0.0, 1.1),
        ):
            with self.subTest(checkpoints=checkpoints):
                with self.assertRaises(LimitActivationBaselineError):
                    build_limit_activation_baseline(
                        self.contract(),
                        sigma_horizon=0.04,
                        time_checkpoints=checkpoints,
                    )

    def test_invalid_solver_inputs_are_rejected(self):
        for kwargs in (
            {"log_distance": 0, "sigma_horizon": 0.04},
            {"log_distance": 0.02, "sigma_horizon": 0},
            {
                "log_distance": 0.02,
                "sigma_horizon": 0.04,
                "time_fraction": 1.01,
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(FirstPassageInputError):
                    single_barrier_first_passage(**kwargs)

    def test_wrong_contract_or_market_side_is_rejected(self):
        contract = self.contract()
        contract["contract_version"] = "old-version"
        with self.assertRaisesRegex(
            LimitActivationBaselineError,
            "limit_contract_version_mismatch",
        ):
            build_limit_activation_baseline(contract, sigma_horizon=0.04)

        with self.assertRaisesRegex(
            LimitActivationBaselineError,
            "long_limit_entry_must_be_below_market",
        ):
            activation_log_distance(
                side="long",
                current_price=100,
                requested_entry=100,
            )


if __name__ == "__main__":
    unittest.main()
