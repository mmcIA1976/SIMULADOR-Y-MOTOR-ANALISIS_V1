from __future__ import annotations

import unittest

from m6_first_passage import double_barrier_first_passage
from m6_remediated_competing_risks import (
    LAYER_VERSION,
    apply_competing_risk_evidence,
)


HISTORICAL_DEFECT_CASES = (
    (0.015231510609612215, 0.015923657170183337, 0.09515392652002724),
    (0.004107928847568161, 0.0002604685516201984, 0.01793895495337509),
    (0.02117499713645878, 0.00903878146003792, 0.10656745600051167),
    (0.004047192920598725, 0.0017885619577991075, 0.01759061220346723),
    (0.005108644701296925, 0.002873393177225414, 0.022646357007875654),
)


class M6R1CompetingRiskTests(unittest.TestCase):
    def test_version_is_separate_from_historical_m6(self) -> None:
        self.assertEqual(
            LAYER_VERSION,
            "M6-R1-discrete-competing-risks-v0.1",
        )

    def test_historical_machine_precision_cases_are_resolved(self) -> None:
        for tp_distance, sl_distance, sigma in HISTORICAL_DEFECT_CASES:
            with self.subTest(
                tp_distance=tp_distance,
                sl_distance=sl_distance,
                sigma=sigma,
            ):
                result = apply_competing_risk_evidence(
                    tp_log_distance=tp_distance,
                    sl_log_distance=sl_distance,
                    sigma_horizon=sigma,
                    interval_count=24,
                )
                baseline = double_barrier_first_passage(
                    tp_log_distance=tp_distance,
                    sl_log_distance=sl_distance,
                    sigma_horizon=sigma,
                )
                self.assertAlmostEqual(result.p_tp, baseline.p_tp, places=12)
                self.assertAlmostEqual(result.p_sl, baseline.p_sl, places=12)
                self.assertAlmostEqual(
                    result.p_expiry,
                    baseline.p_expiry,
                    places=12,
                )
                self.assertAlmostEqual(
                    result.p_tp + result.p_sl + result.p_expiry,
                    1.0,
                    places=13,
                )
                self.assertTrue(
                    any(
                        interval["terminal_reconciliation"]
                        == "machine_precision_absorption"
                        for interval in result.intervals
                    )
                )

    def test_regular_geometry_does_not_need_reconciliation(self) -> None:
        result = apply_competing_risk_evidence(
            tp_log_distance=0.04,
            sl_log_distance=0.03,
            sigma_horizon=0.05,
        )
        self.assertTrue(
            all(
                interval["terminal_reconciliation"] is None
                for interval in result.intervals
            )
        )


if __name__ == "__main__":
    unittest.main()
