from __future__ import annotations

import unittest

from m6_remediation_engine import (
    ENGINE_VERSION,
    run_internal_probability_analysis,
)
from tests.test_m6_engine import FIXED_TIME, m5_analysis


class M6R1EngineTests(unittest.TestCase):
    def test_remediated_engine_is_versioned_and_internal_only(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-r1",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(result["engine_version"], ENGINE_VERSION)
        self.assertEqual(result["status"], "evaluated_internal_only")
        self.assertEqual(result["production_effect"], "none")
        self.assertFalse(result["m9_started"])
        self.assertIn(
            "M6-R1-NUMERICAL-TERMINAL-RECONCILIATION-009",
            result["trace"]["formulas"],
        )

    def test_engine_resolves_a_historical_blocking_geometry(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-r1-historical",
            m5_analysis=m5_analysis(
                tp_distance=0.004107928847568161,
                sl_distance=0.0002604685516201984,
                sigma=0.01793895495337509,
            ),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(result["status"], "evaluated_internal_only")
        self.assertAlmostEqual(
            sum(result["probabilities"].values()),
            1.0,
            places=13,
        )
        self.assertTrue(
            any(
                interval["terminal_reconciliation"]
                == "machine_precision_absorption"
                for interval in result["trace"]["evidence"]["intervals"]
            )
        )

    def test_fixed_input_has_reproducible_hash(self) -> None:
        first = run_internal_probability_analysis(
            analysis_id="same-r1",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        second = run_internal_probability_analysis(
            analysis_id="same-r1",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(first["result_sha256"], second["result_sha256"])


if __name__ == "__main__":
    unittest.main()
