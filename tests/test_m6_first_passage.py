from __future__ import annotations

import unittest

from m6_first_passage import (
    FirstPassageInputError,
    double_barrier_first_passage,
)


class M62FirstPassageTests(unittest.TestCase):
    def test_probabilities_are_collectively_exhaustive(self) -> None:
        result = double_barrier_first_passage(
            tp_log_distance=0.05,
            sl_log_distance=0.03,
            sigma_horizon=0.04,
        )
        self.assertAlmostEqual(
            result.p_tp + result.p_sl + result.p_expiry,
            1.0,
            places=14,
        )
        self.assertGreaterEqual(result.p_tp, 0)
        self.assertGreaterEqual(result.p_sl, 0)
        self.assertGreaterEqual(result.p_expiry, 0)

    def test_symmetric_barriers_have_symmetric_event_probabilities(self) -> None:
        result = double_barrier_first_passage(
            tp_log_distance=0.04,
            sl_log_distance=0.04,
            sigma_horizon=0.05,
        )
        self.assertAlmostEqual(result.p_tp, result.p_sl, places=13)

    def test_swapping_barriers_swaps_tp_and_sl(self) -> None:
        first = double_barrier_first_passage(
            tp_log_distance=0.02,
            sl_log_distance=0.06,
            sigma_horizon=0.04,
        )
        swapped = double_barrier_first_passage(
            tp_log_distance=0.06,
            sl_log_distance=0.02,
            sigma_horizon=0.04,
        )
        self.assertAlmostEqual(first.p_tp, swapped.p_sl, places=13)
        self.assertAlmostEqual(first.p_sl, swapped.p_tp, places=13)
        self.assertAlmostEqual(first.p_expiry, swapped.p_expiry, places=13)

    def test_nearer_tp_has_higher_tp_probability_all_else_equal(self) -> None:
        near = double_barrier_first_passage(
            tp_log_distance=0.02,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
        )
        far = double_barrier_first_passage(
            tp_log_distance=0.04,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
        )
        self.assertGreater(near.p_tp, far.p_tp)

    def test_more_volatility_reduces_expiry_probability(self) -> None:
        low = double_barrier_first_passage(
            tp_log_distance=0.05,
            sl_log_distance=0.05,
            sigma_horizon=0.02,
        )
        high = double_barrier_first_passage(
            tp_log_distance=0.05,
            sl_log_distance=0.05,
            sigma_horizon=0.08,
        )
        self.assertGreater(low.p_expiry, high.p_expiry)

    def test_common_scale_of_distances_and_sigma_is_invariant(self) -> None:
        reference = double_barrier_first_passage(
            tp_log_distance=0.03,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
        )
        scaled = double_barrier_first_passage(
            tp_log_distance=3.0,
            sl_log_distance=5.0,
            sigma_horizon=4.0,
        )
        self.assertAlmostEqual(reference.p_tp, scaled.p_tp, places=13)
        self.assertAlmostEqual(reference.p_sl, scaled.p_sl, places=13)
        self.assertAlmostEqual(
            reference.p_expiry,
            scaled.p_expiry,
            places=13,
        )

    def test_time_zero_is_certain_expiry(self) -> None:
        result = double_barrier_first_passage(
            tp_log_distance=0.03,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
            time_fraction=0,
        )
        self.assertEqual((result.p_tp, result.p_sl, result.p_expiry), (0, 0, 1))

    def test_event_probability_is_monotone_in_elapsed_fraction(self) -> None:
        early = double_barrier_first_passage(
            tp_log_distance=0.03,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
            time_fraction=0.25,
        )
        late = double_barrier_first_passage(
            tp_log_distance=0.03,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
            time_fraction=1,
        )
        self.assertLessEqual(early.p_tp, late.p_tp)
        self.assertLessEqual(early.p_sl, late.p_sl)
        self.assertGreaterEqual(early.p_expiry, late.p_expiry)

    def test_extreme_distance_uses_rigorous_tail_bound(self) -> None:
        result = double_barrier_first_passage(
            tp_log_distance=1.0,
            sl_log_distance=1.0,
            sigma_horizon=0.01,
        )
        self.assertEqual(
            result.numerical_method,
            "reflection_principle_tail_bound",
        )
        self.assertIsNotNone(result.absolute_error_bound)
        self.assertLessEqual(result.absolute_error_bound, 1e-12)

    def test_extreme_asymmetry_uses_bounded_reflection_branch(self) -> None:
        near_tp = double_barrier_first_passage(
            tp_log_distance=1e-12,
            sl_log_distance=5.0,
            sigma_horizon=1e-8,
        )
        near_sl = double_barrier_first_passage(
            tp_log_distance=5.0,
            sl_log_distance=1e-12,
            sigma_horizon=1e-8,
        )
        self.assertEqual(
            near_tp.numerical_method,
            "reflection_principle_separated_barriers",
        )
        self.assertEqual(
            near_sl.numerical_method,
            "reflection_principle_separated_barriers",
        )
        self.assertEqual(
            near_tp.solver_version,
            "M6-double-barrier-first-passage-v0.2",
        )
        self.assertLessEqual(near_tp.absolute_error_bound, 1e-12)
        self.assertLessEqual(near_sl.absolute_error_bound, 1e-12)
        self.assertAlmostEqual(near_tp.p_tp, near_sl.p_sl, places=14)
        self.assertAlmostEqual(near_tp.p_sl, near_sl.p_tp, places=14)
        self.assertAlmostEqual(
            near_tp.p_expiry,
            near_sl.p_expiry,
            places=14,
        )

    def test_invalid_geometry_or_sigma_is_rejected(self) -> None:
        for kwargs in (
            {
                "tp_log_distance": 0,
                "sl_log_distance": 0.03,
                "sigma_horizon": 0.04,
            },
            {
                "tp_log_distance": 0.03,
                "sl_log_distance": -1,
                "sigma_horizon": 0.04,
            },
            {
                "tp_log_distance": 0.03,
                "sl_log_distance": 0.03,
                "sigma_horizon": 0,
            },
        ):
            with self.assertRaises(FirstPassageInputError):
                double_barrier_first_passage(**kwargs)


if __name__ == "__main__":
    unittest.main()
