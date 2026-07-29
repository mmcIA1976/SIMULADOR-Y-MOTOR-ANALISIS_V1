from __future__ import annotations

import unittest

from m6_predictive_rules import (
    ACTIVE_PREDICTIVE_RULE_IDS,
    PROVISIONAL_RULE_WEIGHTS,
    apply_provisional_rule_overlay,
    build_provisional_rule_signals,
)


def evaluated(rule_id: str, outputs: dict) -> dict:
    return {
        "rule_id": rule_id,
        "status": "evaluated",
        "outputs": outputs,
        "trace_sha256": f"sha-{rule_id}",
    }


class M6PredictiveRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m5_analysis = {
            "traces": [
                evaluated(
                    "M4-RULE-PATH-STRUCTURE-001",
                    {"signed_path_efficiency": 0.4},
                ),
                evaluated(
                    "M4-RULE-CONTINUOUS-REGIME-001",
                    {
                        "signed_path_efficiency": 0.4,
                        "volatility_percentile": 0.8,
                    },
                ),
                evaluated(
                    "M4-RULE-AGGRESSOR-IMBALANCE-001",
                    {"ATI_H": 0.3},
                ),
                evaluated(
                    "M4-RULE-OPEN-INTEREST-CHANGE-001",
                    {"dOI_H": 0.02},
                ),
                evaluated(
                    "M4-RULE-PRICE-OI-STATE-001",
                    {"D_H": 0.01, "dOI_H": 0.02},
                ),
                evaluated(
                    "M4-RULE-SPOT-FUTURES-BASIS-001",
                    {"b_mid": -0.002},
                ),
                evaluated(
                    "M4-RULE-MARK-INDEX-PREMIUM-001",
                    {"mark_index_log_premium": -0.001},
                ),
                evaluated(
                    "M4-RULE-FUNDING-STATE-001",
                    {"last_funding_rate": -0.0001},
                ),
            ]
        }

    def test_active_catalog_has_eleven_unique_predictive_rules(self):
        self.assertEqual(len(ACTIVE_PREDICTIVE_RULE_IDS), 11)
        self.assertEqual(
            len(set(ACTIVE_PREDICTIVE_RULE_IDS)),
            len(ACTIVE_PREDICTIVE_RULE_IDS),
        )

    def test_every_available_provisional_rule_gets_nonzero_effect(self):
        snapshot = build_provisional_rule_signals(
            self.m5_analysis,
            side="long",
        )

        self.assertEqual(
            set(snapshot["active"]),
            set(PROVISIONAL_RULE_WEIGHTS),
        )
        self.assertFalse(snapshot["unavailable"])
        for contribution in snapshot["active"].values():
            self.assertNotEqual(
                abs(contribution["tp_log_effect"])
                + abs(contribution["sl_log_effect"])
                + abs(contribution["expiry_log_effect"]),
                0.0,
            )

    def test_overlay_preserves_mass_and_traces_each_rule_delta(self):
        snapshot = build_provisional_rule_signals(
            self.m5_analysis,
            side="long",
        )
        result = apply_provisional_rule_overlay(
            {
                "tp_first_within_horizon": 0.4,
                "sl_first_within_horizon": 0.35,
                "neither_barrier_before_expiry": 0.25,
            },
            snapshot,
        )

        self.assertAlmostEqual(
            sum(result["probabilities_after"].values()),
            1.0,
        )
        self.assertLessEqual(result["probability_mass_error"], 1e-12)
        self.assertEqual(
            set(result["rule_contributions"]),
            set(PROVISIONAL_RULE_WEIGHTS),
        )
        for contribution in result["rule_contributions"].values():
            self.assertNotEqual(
                abs(contribution["tp_probability_delta"])
                + abs(contribution["sl_probability_delta"]),
                0.0,
            )
            self.assertIn(
                "ablation_probabilities_without_rule",
                contribution,
            )
            self.assertAlmostEqual(
                sum(
                    contribution[
                        "ablation_probabilities_without_rule"
                    ].values()
                ),
                1.0,
            )
            self.assertIn(
                "ablation_probability_delta",
                contribution,
            )

    def test_missing_rule_is_excluded_from_active_analysis(self):
        self.m5_analysis["traces"] = self.m5_analysis["traces"][:-1]
        snapshot = build_provisional_rule_signals(
            self.m5_analysis,
            side="long",
        )

        self.assertNotIn(
            "M4-RULE-FUNDING-STATE-001",
            snapshot["active"],
        )
        self.assertEqual(
            snapshot["unavailable"]["M4-RULE-FUNDING-STATE-001"][
                "status"
            ],
            "missing",
        )


if __name__ == "__main__":
    unittest.main()
