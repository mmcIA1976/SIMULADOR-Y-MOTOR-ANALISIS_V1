from __future__ import annotations

import json
import math
import unittest

from build_m4_reachability import (
    DEFAULT_OUTPUT_PATH,
    HORIZON_LIMITS_SECONDS,
    SOURCE_REGISTRY,
    build_catalog,
    closed_log_returns,
    derive_plan_geometry,
    horizon_realized_volatility,
    normalize_barrier_reachability,
    pending_activation_distance,
    select_sampling_interval,
)


class M4ReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_catalog()

    def test_sampling_policy_covers_profile_boundaries_exactly(self):
        expected = {
            ("intraday_short", 30 * 60): ("1m", 30),
            ("intraday_short", 4 * 60 * 60): ("5m", 48),
            ("intraday_wide", 4 * 60 * 60): ("5m", 48),
            ("intraday_wide", 24 * 60 * 60): ("1h", 24),
            ("short_swing", 24 * 60 * 60): ("1h", 24),
            ("short_swing", 7 * 24 * 60 * 60): ("6h", 28),
        }
        for arguments, result in expected.items():
            with self.subTest(arguments=arguments):
                selected = select_sampling_interval(*arguments)
                self.assertEqual(selected["interval"], result[0])
                self.assertEqual(
                    selected["returns_per_horizon"],
                    result[1],
                )
                self.assertEqual(
                    arguments[1] % selected["interval_seconds"],
                    0,
                )
        records = self.catalog["policy_decision_records"]
        self.assertEqual(
            [item["id"] for item in records],
            ["M4-POLICY-SAMPLING-MIN-RETURNS-001"],
        )
        self.assertEqual(records[0]["value"], 24)

    def test_horizon_is_never_rounded_or_moved_between_profiles(self):
        with self.assertRaisesRegex(
            ValueError, "horizon_seconds_out_of_profile"
        ):
            select_sampling_interval("intraday_short", 4 * 60 * 60 + 1)
        with self.assertRaisesRegex(
            ValueError, "horizon_not_aligned_to_supported_interval"
        ):
            select_sampling_interval("intraday_short", 30 * 60 + 1)
        with self.assertRaisesRegex(ValueError, "invalid_time_horizon"):
            select_sampling_interval("3-60h", 3 * 60 * 60)

    def test_geometry_is_long_short_symmetric_and_scale_invariant(self):
        long = derive_plan_geometry("long", 100, 103, 98, 14_400)
        short = derive_plan_geometry(
            "short",
            100,
            10_000 / 103,
            10_000 / 98,
            14_400,
        )
        scaled = derive_plan_geometry(
            "long",
            10_000,
            10_300,
            9_800,
            14_400,
        )
        self.assertAlmostEqual(
            long["tp_log_distance"],
            short["tp_log_distance"],
        )
        self.assertAlmostEqual(
            long["sl_log_distance"],
            short["sl_log_distance"],
        )
        self.assertAlmostEqual(
            long["tp_log_distance"],
            scaled["tp_log_distance"],
        )
        self.assertAlmostEqual(
            long["sl_log_distance"],
            scaled["sl_log_distance"],
        )

    def test_invalid_geometry_blocks_instead_of_returning_neutral_values(self):
        with self.assertRaisesRegex(
            ValueError, "invalid_barrier_geometry"
        ):
            derive_plan_geometry("long", 100, 99, 98, 14_400)
        with self.assertRaisesRegex(
            ValueError, "invalid_barrier_geometry"
        ):
            derive_plan_geometry("short", 100, 101, 102, 14_400)
        with self.assertRaisesRegex(ValueError, "invalid_price"):
            derive_plan_geometry("long", 0, 103, 98, 14_400)

    def test_log_returns_are_dimensionless_and_scale_invariant(self):
        first = closed_log_returns([100, 101, 99, 102])
        scaled = closed_log_returns([10_000, 10_100, 9_900, 10_200])
        self.assertEqual(len(first), 3)
        for left, right in zip(first, scaled):
            self.assertAlmostEqual(left, right)
        self.assertEqual(closed_log_returns([100, 100]), [0.0])

    def test_realized_volatility_uses_previous_exact_horizon(self):
        horizon_seconds = 30 * 60
        interval_seconds = 60
        return_count = 30
        closes = [
            100 * math.exp(0.01 * index)
            for index in range(return_count + 1)
        ]
        close_times = [
            index * interval_seconds * 1000
            for index in range(return_count + 1)
        ]
        result = horizon_realized_volatility(
            closes=closes,
            close_times_ms=close_times,
            analysis_at_ms=close_times[-1],
            time_horizon="intraday_short",
            horizon_seconds=horizon_seconds,
            interval_seconds=interval_seconds,
        )
        self.assertEqual(result["return_count"], return_count)
        self.assertAlmostEqual(
            result["realized_variance"],
            return_count * 0.01**2,
        )
        self.assertAlmostEqual(
            result["realized_volatility"],
            math.sqrt(return_count * 0.01**2),
        )
        self.assertEqual(result["forecast_status"], "not_a_forecast")

    def test_realized_volatility_rejects_wrong_grid_gap_future_and_stale(self):
        horizon_seconds = 30 * 60
        closes = [100 + index for index in range(31)]
        close_times = [index * 60_000 for index in range(31)]
        common = dict(
            closes=closes,
            close_times_ms=close_times,
            time_horizon="intraday_short",
            horizon_seconds=horizon_seconds,
        )
        with self.assertRaisesRegex(
            ValueError, "interval_does_not_match_policy"
        ):
            horizon_realized_volatility(
                **common,
                analysis_at_ms=close_times[-1],
                interval_seconds=180,
            )

        gapped = list(close_times)
        gapped[15] += 1
        with self.assertRaisesRegex(
            ValueError, "kline_gap_or_misalignment"
        ):
            horizon_realized_volatility(
                **{**common, "close_times_ms": gapped},
                analysis_at_ms=close_times[-1],
                interval_seconds=60,
            )

        with self.assertRaisesRegex(ValueError, "future_closed_bar"):
            horizon_realized_volatility(
                **common,
                analysis_at_ms=close_times[-1] - 1,
                interval_seconds=60,
            )

        with self.assertRaisesRegex(
            ValueError, "latest_closed_bar_stale"
        ):
            horizon_realized_volatility(
                **common,
                analysis_at_ms=close_times[-1] + 120_001,
                interval_seconds=60,
            )

    def test_reachability_is_continuous_monotonic_and_not_probability(self):
        base = derive_plan_geometry("long", 100, 103, 98, 14_400)
        farther = derive_plan_geometry("long", 100, 106, 98, 14_400)
        normalized = normalize_barrier_reachability(base, 0.04)
        farther_result = normalize_barrier_reachability(farther, 0.04)
        higher_volatility = normalize_barrier_reachability(base, 0.08)
        self.assertGreater(farther_result["z_tp"], normalized["z_tp"])
        self.assertLess(higher_volatility["z_tp"], normalized["z_tp"])
        self.assertLess(higher_volatility["z_sl"], normalized["z_sl"])
        self.assertIsNone(normalized["probability"])
        rule_ids = {rule["id"] for rule in self.catalog["rules"]}
        self.assertIn(
            "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            rule_ids,
        )
        self.assertNotIn("M4-RULE-BARRIER-REACHABILITY-001", rule_ids)

    def test_zero_or_invalid_volatility_blocks_reachability(self):
        geometry = derive_plan_geometry("long", 100, 103, 98, 14_400)
        for value in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError, "invalid_horizon_volatility"
                ):
                    normalize_barrier_reachability(geometry, value)

    def test_pending_activation_is_separate_from_tp_sl(self):
        market = pending_activation_distance(
            entry_type="market",
            side="long",
            trigger_condition=None,
            current_price=100,
            entry=100,
            horizon_volatility=0.04,
        )
        self.assertEqual(market["z_entry"], 0)
        self.assertIsNone(market["activation_probability"])

        pending = pending_activation_distance(
            entry_type="pending",
            side="long",
            trigger_condition="price_lte",
            current_price=100,
            entry=98,
            horizon_volatility=0.04,
        )
        self.assertGreater(pending["z_entry"], 0)
        self.assertEqual(pending["entry_order_type"], "limit_pullback")
        self.assertIsNone(pending["activation_probability"])

    def test_pending_trigger_must_be_valid_and_unsatisfied(self):
        with self.assertRaisesRegex(
            ValueError, "pending_trigger_required"
        ):
            pending_activation_distance(
                entry_type="pending",
                side="long",
                trigger_condition=None,
                current_price=100,
                entry=98,
                horizon_volatility=0.04,
            )
        with self.assertRaisesRegex(
            ValueError, "pending_trigger_already_satisfied"
        ):
            pending_activation_distance(
                entry_type="pending",
                side="long",
                trigger_condition="price_lte",
                current_price=97,
                entry=98,
                horizon_volatility=0.04,
            )

    def test_catalog_has_six_complete_rule_cards_and_no_weights(self):
        rules = self.catalog["rules"]
        self.assertEqual(len(rules), 6)
        self.assertEqual(
            self.catalog["summary"]["rules_with_probability_effect"],
            0,
        )
        self.assertEqual(
            self.catalog["summary"]["rules_with_numeric_weight"],
            0,
        )
        for rule in rules:
            self.assertEqual(
                rule["lifecycle_status"],
                "documented_candidate_no_predictive_weight",
            )
            self.assertFalse(rule["direct_probability_effect_authorized"])
            self.assertFalse(rule["numeric_weight_authorized"])
            self.assertFalse(rule["production_authorized"])
            self.assertTrue(rule["exact_transformation_and_formula"])
            self.assertTrue(rule["claims_not_supported_by_source"])
            self.assertTrue(rule["missing_data_behavior"])
            self.assertTrue(rule["trace_output"])

    def test_sources_state_both_support_and_transfer_limits(self):
        source_ids = {item["id"] for item in SOURCE_REGISTRY}
        self.assertIn(
            "ANDERSEN-BOLLERSLEV-DIEBOLD-LABYS-2003",
            source_ids,
        )
        self.assertIn("POETZELBERGER-WANG-2001", source_ids)
        for source in SOURCE_REGISTRY:
            self.assertTrue(source["supported_claim"])
            self.assertTrue(source["does_not_support"])

    def test_catalog_preserves_all_pairs_horizons_and_m3_clarification(self):
        scope = self.catalog["scope"]
        self.assertEqual(
            set(scope["symbols"]),
            {
                "BTCUSDT",
                "ETHUSDT",
                "SOLUSDT",
                "BNBUSDT",
                "XRPUSDT",
                "INJUSDT",
            },
        )
        self.assertEqual(
            set(scope["horizons"]),
            set(HORIZON_LIMITS_SECONDS),
        )
        m3_path = (
            DEFAULT_OUTPUT_PATH.parent
            / "catalogo_contratos_datos_m3_v0_1.json"
        )
        m3 = json.loads(m3_path.read_text(encoding="utf-8"))
        clarification_ids = {
            item["id"] for item in m3["post_closure_clarifications"]
        }
        self.assertIn("M3-CLARIFICATION-001", clarification_ids)

    def test_current_heuristic_bands_are_explicitly_superseded(self):
        superseded = self.catalog["supersedes_current_elements"]
        for current_id in (
            "IND-ATR14-CURRENT",
            "SCORE-PRICE_VS_ENTRY_BIAS",
            "SCORE-VOLATILITY_PENALTY",
            "SCORE-ZONE_PROBABILITY_ADJUSTMENT",
        ):
            self.assertIn(current_id, superseded)

    def test_m4_2_does_not_modify_production_or_start_m5(self):
        scope = self.catalog["scope"]
        self.assertFalse(scope["production_modified"])
        self.assertFalse(scope["analysis_engine_modified"])
        self.assertFalse(scope["learning_engine_used"])
        self.assertFalse(scope["m5_started"])
        self.assertEqual(scope["m4_next_subphase"], "M4.3")

    def test_generated_artifact_matches_builder(self):
        committed = json.loads(
            DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(committed, self.catalog)


if __name__ == "__main__":
    unittest.main()
