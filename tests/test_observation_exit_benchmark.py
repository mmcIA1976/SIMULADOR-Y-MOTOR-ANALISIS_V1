from __future__ import annotations

import unittest

from observation_exit_benchmark import (
    OUTCOME_KEYS,
    _geometry_tp_probability,
    probability_metrics,
)
from operation_observation_learning import (
    OBSERVATION_CLOSURE_POLICY_VERSION,
    observation_closure_advisory,
)


class ObservationExitBenchmarkTests(unittest.TestCase):
    def test_geometry_probability_respects_long_and_short_barriers(self):
        self.assertAlmostEqual(
            _geometry_tp_probability(
                side="long",
                price=100.0,
                take_profit=110.0,
                stop_loss=95.0,
            ),
            1.0 / 3.0,
        )
        self.assertAlmostEqual(
            _geometry_tp_probability(
                side="short",
                price=100.0,
                take_profit=90.0,
                stop_loss=105.0,
            ),
            1.0 / 3.0,
        )

    def test_probability_metrics_exclude_reconstructed_diagnostics(self):
        exact = {
            "formal_learning_eligible": True,
            "terminal_outcome": OUTCOME_KEYS[0],
            "probabilities": {
                OUTCOME_KEYS[0]: 0.7,
                OUTCOME_KEYS[1]: 0.2,
                OUTCOME_KEYS[2]: 0.1,
            },
            "geometry_tp_probability": 0.6,
        }
        reconstructed = {
            **exact,
            "formal_learning_eligible": False,
            "probabilities": {
                OUTCOME_KEYS[0]: 0.0,
                OUTCOME_KEYS[1]: 1.0,
                OUTCOME_KEYS[2]: 0.0,
            },
        }
        metrics = probability_metrics([exact, reconstructed])
        self.assertEqual(metrics["cases"], 1)
        self.assertEqual(metrics["top_class_accuracy"], 1.0)

    def test_closure_policy_has_an_explicit_version(self):
        advisory = observation_closure_advisory([])
        self.assertEqual(
            advisory["policy_version"],
            OBSERVATION_CLOSURE_POLICY_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
