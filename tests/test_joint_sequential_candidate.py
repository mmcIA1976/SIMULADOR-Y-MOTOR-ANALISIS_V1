import unittest

from audit_empirical_active_rules import _load_numpy
from evaluate_joint_sequential_candidate import (
    _weight_score,
    cumulative_probabilities,
    volume_integration_gate,
)
from multiscale_feature_runtime import STAGE_ORDER


class JointSequentialCandidateTests(unittest.TestCase):
    @staticmethod
    def _integration_evaluation(swing_improvement=0.0):
        return {
            "partition": "test",
            "comparisons": {
                "candidate_vs_v0_10": {
                    "intraday_short": {
                        direction: {
                            "log_loss_improvement": 0.0,
                            "brier_improvement": 0.0,
                        }
                        for direction in ("long", "short")
                    },
                    "intraday_wide": {
                        direction: {
                            "log_loss_improvement": 0.01,
                            "brier_improvement": 0.005,
                        }
                        for direction in ("long", "short")
                    },
                    "short_swing": {
                        direction: {
                            "log_loss_improvement": swing_improvement,
                            "brier_improvement": swing_improvement,
                        }
                        for direction in ("long", "short")
                    },
                }
            },
        }

    def test_later_horizons_inherit_earlier_survival_mass(self):
        np = _load_numpy()
        stage_probabilities = {
            STAGE_ORDER[0]: np.asarray([[[0.2, 0.3, 0.5]]]),
            STAGE_ORDER[1]: np.asarray([[[0.4, 0.1, 0.5]]]),
            STAGE_ORDER[2]: np.asarray([[[0.1, 0.2, 0.7]]]),
        }
        result = cumulative_probabilities(np, stage_probabilities)
        np.testing.assert_allclose(result[STAGE_ORDER[0]][0, 0], [0.2, 0.3, 0.5])
        np.testing.assert_allclose(result[STAGE_ORDER[1]][0, 0], [0.4, 0.35, 0.25])
        np.testing.assert_allclose(
            result[STAGE_ORDER[2]][0, 0], [0.425, 0.4, 0.175]
        )

    def test_strict_all_horizon_improvement_beats_partial_improvement(self):
        reference = {
            horizon: {"log_loss": 1.0, "brier": 1.0}
            for horizon in STAGE_ORDER
        }
        strict = {
            horizon: {"log_loss": 0.999, "brier": 0.999}
            for horizon in STAGE_ORDER
        }
        partial = {
            horizon: {
                "log_loss": 0.9,
                "brier": 0.9 if horizon != STAGE_ORDER[-1] else 1.001,
            }
            for horizon in STAGE_ORDER
        }
        self.assertLess(
            _weight_score(strict, reference, (0.1, 0.1, 0.1)),
            _weight_score(partial, reference, (0.5, 0.5, 0.5)),
        )

    def test_integration_gate_allows_unchanged_boundaries(self):
        result = volume_integration_gate(self._integration_evaluation())
        self.assertTrue(result["passed"])

    def test_integration_gate_rejects_accumulated_swing_regression(self):
        result = volume_integration_gate(
            self._integration_evaluation(swing_improvement=-0.0001)
        )
        self.assertFalse(result["passed"])
        self.assertFalse(
            result["requirements"]["no_accumulated_swing_regression"]
        )


if __name__ == "__main__":
    unittest.main()
