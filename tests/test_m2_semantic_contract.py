from __future__ import annotations

import unittest

from build_m2_semantic_contract import (
    CONDITIONAL_OUTCOMES,
    OVERALL_OUTCOMES,
    VISIBLE_OUTCOMES,
    build_contract,
    build_current_engine_audit,
    compose_probability_tree,
    current_price_vs_entry_bias,
    current_residual_probabilities,
    derive_plan_geometry,
    normalize_geometry_by_volatility,
    validate_barrier_geometry,
    validate_horizon,
    validate_probability_distribution,
)


class M2SemanticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = build_contract()
        cls.audit = build_current_engine_audit()

    def test_long_and_short_mirror_have_same_log_geometry(self):
        long = derive_plan_geometry("long", 100, 103, 98, 7200)
        short = derive_plan_geometry(
            "short",
            100,
            10000 / 103,
            10000 / 98,
            7200,
        )
        self.assertAlmostEqual(
            long["tp_log_distance"], short["tp_log_distance"]
        )
        self.assertAlmostEqual(
            long["sl_log_distance"], short["sl_log_distance"]
        )
        self.assertAlmostEqual(
            long["log_horizon_seconds"],
            short["log_horizon_seconds"],
        )

    def test_invalid_barrier_geometry_blocks_both_sides(self):
        with self.assertRaisesRegex(
            ValueError, "invalid_barrier_geometry"
        ):
            validate_barrier_geometry("long", 100, 99, 98)
        with self.assertRaisesRegex(
            ValueError, "invalid_barrier_geometry"
        ):
            validate_barrier_geometry("short", 100, 101, 102)

    def test_geometry_requires_positive_horizon_volatility_scale(self):
        geometry = derive_plan_geometry("long", 100, 103, 98, 7200)
        normalized = normalize_geometry_by_volatility(geometry, 0.02)
        self.assertAlmostEqual(
            normalized["tp_volatility_units"],
            geometry["tp_log_distance"] / 0.02,
        )
        self.assertAlmostEqual(
            normalized["sl_volatility_units"],
            geometry["sl_log_distance"] / 0.02,
        )
        for invalid in (None, 0, -0.1, float("nan"), float("inf")):
            with self.assertRaisesRegex(
                ValueError, "invalid_horizon_volatility"
            ):
                normalize_geometry_by_volatility(geometry, invalid)

    def test_only_three_current_horizon_profiles_are_valid(self):
        validate_horizon("intraday_short", 1800)
        validate_horizon("intraday_wide", 24 * 60 * 60)
        validate_horizon("short_swing", 7 * 24 * 60 * 60)
        with self.assertRaisesRegex(ValueError, "invalid_time_horizon"):
            validate_horizon("3-60h", 10800)
        with self.assertRaisesRegex(
            ValueError, "horizon_seconds_out_of_profile"
        ):
            validate_horizon("intraday_short", 7 * 24 * 60 * 60)

    def test_market_entry_probability_tree_is_coherent(self):
        result = compose_probability_tree(
            1.0,
            {
                "tp_first": 0.45,
                "sl_first": 0.35,
                "expiry_after_entry": 0.20,
            },
        )
        self.assertEqual(result["overall"]["no_entry"], 0.0)
        self.assertAlmostEqual(result["conditional_mass"], 1.0)
        self.assertAlmostEqual(result["overall_mass"], 1.0)
        self.assertAlmostEqual(result["visible_mass"], 1.0)

    def test_pending_no_entry_is_not_mixed_with_expiry_after_entry(self):
        result = compose_probability_tree(
            0.60,
            {
                "tp_first": 0.50,
                "sl_first": 0.30,
                "expiry_after_entry": 0.20,
            },
        )
        self.assertAlmostEqual(result["overall"]["tp_first"], 0.30)
        self.assertAlmostEqual(result["overall"]["sl_first"], 0.18)
        self.assertAlmostEqual(
            result["overall"]["expiry_after_entry"], 0.12
        )
        self.assertAlmostEqual(result["overall"]["no_entry"], 0.40)
        self.assertAlmostEqual(result["visible"]["unresolved"], 0.52)

    def test_invalid_probability_mass_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "probability_mass_not_one"
        ):
            validate_probability_distribution(
                {
                    "tp_first": 0.60,
                    "sl_first": 0.40,
                    "expiry_after_entry": 0.10,
                },
                CONDITIONAL_OUTCOMES,
            )
        with self.assertRaisesRegex(
            ValueError, "probability_keys_mismatch"
        ):
            validate_probability_distribution(
                {"tp_first": 1.0},
                VISIBLE_OUTCOMES,
            )

    def test_case_872_873_current_rule_has_forbidden_jump(self):
        below = current_price_vs_entry_bias("short", 99.999999, 100)
        at_entry = current_price_vs_entry_bias("short", 100, 100)
        self.assertEqual(below, -0.02)
        self.assertEqual(at_entry, 0.03)
        self.assertAlmostEqual(at_entry - below, 0.05)

    def test_current_residual_floor_can_exceed_probability_mass(self):
        current = current_residual_probabilities(0.74, 0.22)
        self.assertAlmostEqual(sum(current.values()), 1.01)
        with self.assertRaisesRegex(
            ValueError, "probability_keys_mismatch"
        ):
            validate_probability_distribution(current, OVERALL_OUTCOMES)

    def test_contract_has_all_required_invariants_and_edge_cases(self):
        invariant_ids = {
            item["id"] for item in self.contract["invariants"]
        }
        self.assertEqual(len(invariant_ids), 19)
        self.assertEqual(len(self.contract["edge_cases"]), 15)
        for required in (
            "M2-INV-GEOMETRY-01",
            "M2-INV-SCALE-01",
            "M2-INV-ACTIVATION-01",
            "M2-INV-OUTCOME-02",
            "M2-INV-MONO-TP-01",
            "M2-INV-CONTINUITY-01",
            "M2-INV-DATA-01",
            "M2-INV-TRACE-01",
        ):
            self.assertIn(required, invariant_ids)

    def test_external_audit_cannot_redirect_the_roadmap(self):
        filter_result = self.contract["external_audit_filter"]
        discarded = " ".join(
            item["detail"]
            for item in filter_result["discarded_or_not_adopted"]
        )
        self.assertIn("3-60", discarded)
        self.assertIn("logistic/GBM", discarded)
        self.assertFalse(
            self.contract["scope"]["probabilistic_method_selected"]
        )
        self.assertFalse(self.contract["scope"]["m3_started"])
        self.assertEqual(
            self.contract["status"], "completed_owner_approved"
        )
        self.assertEqual(self.contract["approved_at"], "2026-07-27")

    def test_current_engine_failures_are_explicit_and_nonfunctional(self):
        summary = self.audit["summary"]
        self.assertEqual(summary["findings"], 9)
        self.assertEqual(summary["failures"], 9)
        self.assertGreaterEqual(summary["critical"], 5)
        self.assertFalse(summary["production_modified"])
        self.assertEqual(
            self.audit["status"],
            "current_engine_fails_m2_contract_as_expected",
        )


if __name__ == "__main__":
    unittest.main()
