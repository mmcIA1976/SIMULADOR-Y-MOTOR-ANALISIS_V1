from __future__ import annotations

import json
import math
import unittest

from build_m4_structure_regime import (
    DEFAULT_OUTPUT_PATH,
    MTF_WINDOW_MULTIPLIERS,
    SYMBOLS,
    VOLATILITY_REFERENCE_WINDOWS,
    build_catalog,
    continuous_regime_vector,
    empirical_volatility_percentile,
    exponential_smoother,
    multi_timeframe_state,
    path_structure,
    prior_horizon_extrema,
)


class M4StructureRegimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_catalog()
        cls.rules = {
            rule["id"]: rule
            for rule in cls.catalog["rules"]
        }

    def test_exponential_smoother_has_explicit_recursion(self):
        result = exponential_smoother([100, 110, 90], 0.25)
        self.assertEqual(result[0], 100)
        self.assertAlmostEqual(result[1], 102.5)
        self.assertAlmostEqual(result[2], 99.375)
        self.assertEqual(exponential_smoother([7, 7, 7], 0.4), [7, 7, 7])

    def test_exponential_smoother_rejects_implicit_or_invalid_inputs(self):
        for alpha in (0, -0.1, 1.1, float("nan")):
            with self.subTest(alpha=alpha):
                with self.assertRaisesRegex(ValueError, "invalid_alpha"):
                    exponential_smoother([100, 101], alpha)
        with self.assertRaisesRegex(ValueError, "empty_price_series"):
            exponential_smoother([], 0.5)
        with self.assertRaisesRegex(ValueError, "invalid_price"):
            exponential_smoother([100, 0], 0.5)

    def test_path_structure_is_exact_bounded_and_scale_invariant(self):
        closes = [100, 105, 102, 108]
        result = path_structure(closes)
        scaled = path_structure([value * 100 for value in closes])
        self.assertAlmostEqual(
            result["log_displacement"],
            math.log(closes[-1] / closes[0]),
        )
        self.assertGreaterEqual(result["path_efficiency"], 0)
        self.assertLessEqual(result["path_efficiency"], 1)
        self.assertGreaterEqual(result["signed_path_efficiency"], -1)
        self.assertLessEqual(result["signed_path_efficiency"], 1)
        self.assertAlmostEqual(
            result["signed_path_efficiency"],
            scaled["signed_path_efficiency"],
        )
        self.assertIsNone(result["prediction"])

    def test_flat_path_is_an_observation_not_missing_data(self):
        result = path_structure([100, 100, 100])
        self.assertEqual(result["log_displacement"], 0)
        self.assertEqual(result["total_log_variation"], 0)
        self.assertEqual(result["path_efficiency"], 0)
        self.assertEqual(result["signed_path_efficiency"], 0)
        self.assertEqual(result["path_status"], "flat_observed_path")

    def test_prior_extrema_are_mirrored_and_never_labelled_barriers(self):
        long = prior_horizon_extrema(
            side="long",
            entry=100,
            take_profit=110,
            highs=[98, 105, 107],
            lows=[94, 96, 101],
        )
        short = prior_horizon_extrema(
            side="short",
            entry=100,
            take_profit=90,
            highs=[99, 104, 102],
            lows=[97, 95, 92],
        )
        self.assertEqual(long["target_side_extreme"], 107)
        self.assertEqual(short["target_side_extreme"], 92)
        self.assertTrue(long["target_extreme_between_entry_and_tp"])
        self.assertTrue(short["target_extreme_between_entry_and_tp"])
        for result in (long, short):
            self.assertIsNone(result["support_resistance_label"])
            self.assertIsNone(result["barrier_effect"])

    def test_prior_extrema_reject_invalid_plan_or_bar_data(self):
        with self.assertRaisesRegex(ValueError, "invalid_target_geometry"):
            prior_horizon_extrema(
                side="long",
                entry=100,
                take_profit=99,
                highs=[101],
                lows=[98],
            )
        with self.assertRaisesRegex(ValueError, "invalid_high_low_bar"):
            prior_horizon_extrema(
                side="short",
                entry=100,
                take_profit=95,
                highs=[97],
                lows=[98],
            )

    def test_volatility_percentile_uses_60_prior_windows_and_midrank(self):
        reference = [float(value) for value in range(60)]
        result = empirical_volatility_percentile(30, reference)
        self.assertEqual(
            result["reference_window_count"],
            VOLATILITY_REFERENCE_WINDOWS,
        )
        self.assertAlmostEqual(
            result["volatility_percentile"],
            (30 + 0.5) / 60,
        )
        self.assertEqual(result["ranking_method"], "empirical_midrank")
        self.assertIsNone(result["regime_label"])
        self.assertIsNone(result["directional_effect"])

    def test_volatility_percentile_blocks_insufficient_history(self):
        with self.assertRaisesRegex(
            ValueError,
            "insufficient_volatility_reference_windows",
        ):
            empirical_volatility_percentile(1, [1] * 59)
        with self.assertRaisesRegex(
            ValueError,
            "invalid_current_realized_variance",
        ):
            empirical_volatility_percentile(-1, [1] * 60)

    def test_mtf_preserves_order_and_has_no_vote_or_score(self):
        structures = {
            "H": {"signed_path_efficiency": 0.8},
            "2H": {"signed_path_efficiency": 0.2},
            "4H": {"signed_path_efficiency": 0.1},
        }
        result = multi_timeframe_state(structures)
        self.assertEqual(
            result["window_multipliers"],
            list(MTF_WINDOW_MULTIPLIERS),
        )
        self.assertEqual(result["agreement_descriptor"], "all_positive")
        self.assertIsNone(result["aggregate_score"])
        self.assertIsNone(result["probability_effect"])

    def test_mtf_mixed_and_flat_states_are_descriptors_not_penalties(self):
        mixed = multi_timeframe_state(
            {
                "H": {"signed_path_efficiency": 0.2},
                "2H": {"signed_path_efficiency": -0.3},
                "4H": {"signed_path_efficiency": 0.4},
            }
        )
        flat = multi_timeframe_state(
            {
                "H": {"signed_path_efficiency": 0.2},
                "2H": {"signed_path_efficiency": 0},
                "4H": {"signed_path_efficiency": 0.4},
            }
        )
        self.assertEqual(mixed["agreement_descriptor"], "mixed")
        self.assertEqual(flat["agreement_descriptor"], "flat_present")
        with self.assertRaisesRegex(ValueError, "mtf_windows_mismatch"):
            multi_timeframe_state(
                {"H": {"signed_path_efficiency": 0.2}}
            )

    def test_continuous_regime_vector_has_no_categorical_or_directional_output(self):
        result = continuous_regime_vector(0.75, -0.4)
        self.assertEqual(result["volatility_percentile"], 0.75)
        self.assertEqual(result["signed_path_efficiency"], -0.4)
        self.assertIsNone(result["regime_label"])
        self.assertIsNone(result["directional_score"])
        self.assertIsNone(result["probability_effect"])

    def test_continuous_regime_vector_enforces_unit_bounds(self):
        for values in ((-0.1, 0), (1.1, 0), (0.5, -1.1), (0.5, 1.1)):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    continuous_regime_vector(*values)

    def test_six_rule_cards_are_complete_and_non_operational(self):
        self.assertEqual(len(self.rules), 6)
        required_fields = {
            "id",
            "version",
            "concrete_objective",
            "raw_data_and_provider",
            "exact_transformation_and_formula",
            "source_and_exact_supported_claim",
            "claims_not_supported_by_source",
            "double_counting_control",
            "missing_data_behavior",
            "trace_output",
            "refutation_suspension_or_withdrawal",
            "lifecycle_status",
        }
        for rule in self.rules.values():
            self.assertTrue(required_fields.issubset(rule))
            self.assertFalse(rule["direct_probability_effect_authorized"])
            self.assertFalse(rule["numeric_weight_authorized"])
            self.assertFalse(rule["production_authorized"])

    def test_all_pairs_horizons_and_no_ema_period_are_approved(self):
        scope = self.catalog["scope"]
        self.assertEqual(set(scope["symbols"]), set(SYMBOLS))
        self.assertEqual(
            set(scope["horizons"]),
            {"intraday_short", "intraday_wide", "short_swing"},
        )
        policies = self.catalog["operational_policies"]
        self.assertEqual(policies["ema_periods_approved"], [])
        self.assertFalse(policies["categorical_regime_labels_allowed"])
        self.assertFalse(policies["mtf_numeric_weights_allowed"])
        self.assertEqual(self.catalog["summary"]["p0_rule_cards"], 5)
        self.assertEqual(
            self.catalog["summary"]["auxiliary_operator_cards"],
            1,
        )
        self.assertEqual(
            {
                item["id"]
                for item in self.catalog["policy_decision_records"]
            },
            {
                "M4-POLICY-VOLATILITY-REFERENCE-WINDOWS-001",
                "M4-POLICY-MTF-WINDOW-MULTIPLIERS-001",
            },
        )

    def test_sources_state_claims_and_transfer_limits_separately(self):
        sources = {
            source["id"]: source
            for source in self.catalog["sources"]
        }
        for source in sources.values():
            self.assertTrue(source["supported_claim"])
            self.assertTrue(source["does_not_support"])
        self.assertIn("crypto", sources["MOSKOWITZ-OOI-PEDERSEN-2012"][
            "does_not_support"
        ].lower())
        osler_limit = sources["OSLER-2000-SUPPORT-RESISTANCE"][
            "does_not_support"
        ].lower()
        self.assertIn("rolling extrema", osler_limit)
        self.assertIn("crypto", osler_limit)
        self.assertIn("9/21/50/200", sources[
            "NIST-SINGLE-EXPONENTIAL-SMOOTHING"
        ]["does_not_support"])

    def test_evidence_families_cannot_be_added_as_independent_signals(self):
        families = self.catalog["evidence_families"]
        self.assertEqual(len(families), 3)
        self.assertTrue(
            all(
                not family["additive_members_allowed"]
                for family in families
            )
        )

    def test_opaque_legacy_scores_are_explicitly_superseded(self):
        superseded = self.catalog["supersedes_current_elements"]
        expected = {
            "IND-EMA-STACK",
            "SCORE-TREND_BIAS",
            "SCORE-TECHNICAL_DIRECTION_BIAS",
            "SCORE-MARKET_REGIME_BIAS",
            "SCORE-OVEREXTENSION_PENALTY",
            "SCORE-HIGHER_TIMEFRAME_PENALTY",
        }
        self.assertTrue(expected.issubset(superseded))

    def test_m4_3_closes_without_starting_m5_or_modifying_engines(self):
        scope = self.catalog["scope"]
        self.assertEqual(self.catalog["subphase"], "M4.3")
        self.assertEqual(scope["m4_next_subphase"], "M4.4")
        self.assertFalse(scope["production_modified"])
        self.assertFalse(scope["analysis_engine_modified"])
        self.assertFalse(scope["learning_engine_used"])
        self.assertFalse(scope["m5_started"])

    def test_generated_artifact_matches_builder(self):
        committed = json.loads(
            DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(committed, self.catalog)


if __name__ == "__main__":
    unittest.main()
