from __future__ import annotations

import unittest

import audit_full_rule_library_closed_operations as audit


class FullRuleLibraryAuditTests(unittest.TestCase):
    def test_auc_supports_ties_and_perfect_ordering(self):
        self.assertEqual(audit.auc_score([1, 2, 3, 4], [0, 0, 1, 1]), 1.0)
        self.assertEqual(audit.auc_score([1, 1, 1, 1], [0, 1, 0, 1]), 0.5)

    def test_probability_metrics_keeps_zero_mass_classes(self):
        case = {
            "entry_type": "market",
            "outcome": {
                "status": "resolved",
                "label": "tp_first_within_horizon",
            },
            "probabilities": {
                "tp_first_within_horizon": 0.75,
                "sl_first_within_horizon": 0.25,
                "neither_barrier_before_expiry": 0.0,
            },
        }
        result = audit.probability_metrics([case], "probabilities")
        self.assertEqual(result["n"], 1)
        self.assertAlmostEqual(result["log_loss"], -__import__("math").log(0.75))

    def test_relative_volume_is_an_eligible_dimensionless_signal(self):
        eligible, reason = audit.variable_eligibility(
            "log_relative_horizon_volume",
            {"lifecycle_status": "implemented_shadow"},
        )
        self.assertTrue(eligible)
        self.assertEqual(reason, "dimensionless_relative_volume_signal")

    def test_legacy_proxy_is_not_promoted_to_exact_synthetic_signal(self):
        case = {
            "side": "long",
            "rules": {
                "M4-RULE-OPEN-INTEREST-CHANGE-001": {
                    "state": audit.STATE_PROXY,
                    "outputs": {"dOI_H_proxy": 0.02},
                }
            },
        }
        self.assertEqual(audit.synthetic_rule_signals(case), {})


if __name__ == "__main__":
    unittest.main()
