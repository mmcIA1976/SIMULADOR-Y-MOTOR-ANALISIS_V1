from __future__ import annotations

import unittest

from m6_active_engine import (
    ACTIVE_ENGINE_VERSION,
    ACTIVE_LAYER_VERSION,
    run_internal_probability_analysis,
)
from tests.test_m6_engine import FIXED_TIME, m5_analysis


class M6ActiveEngineTests(unittest.TestCase):
    def test_active_entrypoint_uses_the_repaired_implementation(self) -> None:
        self.assertEqual(
            ACTIVE_ENGINE_VERSION,
            "M6-R1-internal-probability-engine-v0.1",
        )
        self.assertEqual(
            ACTIVE_LAYER_VERSION,
            "M6-R1-discrete-competing-risks-v0.1",
        )
        result = run_internal_probability_analysis(
            analysis_id="active-historical-case",
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


if __name__ == "__main__":
    unittest.main()
