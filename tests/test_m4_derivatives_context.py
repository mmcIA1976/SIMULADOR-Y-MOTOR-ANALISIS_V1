from __future__ import annotations

import json
import math
import unittest

from build_m4_derivatives_context import (
    CROSS_VENUE_MAX_SKEW_MS,
    DEFAULT_OUTPUT_PATH,
    SYMBOLS,
    aggressor_trade_imbalance,
    build_catalog,
    derivatives_context_vector,
    funding_state,
    mark_index_premium,
    open_interest_change,
    periodic_taker_imbalance,
    price_open_interest_state,
    reconcile_aggressor_measures,
    spot_futures_basis,
)


class M4DerivativesContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_catalog()
        cls.rules = {
            rule["id"]: rule
            for rule in cls.catalog["rules"]
        }

    def test_aggressor_trade_imbalance_uses_actual_taker_side(self):
        result = aggressor_trade_imbalance(
            [
                {
                    "aggregate_trade_id": 1,
                    "price": 100,
                    "quantity": 2,
                    "time_ms": 1_001,
                    "buyer_is_maker": False,
                },
                {
                    "aggregate_trade_id": 2,
                    "price": 100,
                    "quantity": 1,
                    "time_ms": 1_500,
                    "buyer_is_maker": True,
                },
            ],
            window_start_ms=1_000,
            window_end_ms=2_000,
            coverage_complete=True,
        )
        self.assertEqual(result["buy_taker_quote"], 200)
        self.assertEqual(result["sell_taker_quote"], 100)
        self.assertAlmostEqual(result["aggressor_trade_imbalance"], 1 / 3)
        self.assertEqual(result["direction_descriptor"], "positive")
        self.assertEqual(result["ati_source"], "binance_usdm_aggTrades")
        self.assertEqual(result["activity_unit"], "quote_asset")
        self.assertEqual(result["coverage_start_ms"], 1_000)
        self.assertEqual(result["coverage_end_ms"], 2_000)
        self.assertIsNone(result["full_order_flow_imbalance"])
        self.assertIsNone(result["prediction"])

    def test_event_window_is_left_open_right_closed(self):
        common = {
            "aggregate_trade_id": 1,
            "price": 100,
            "quantity": 1,
            "buyer_is_maker": False,
        }
        with self.assertRaisesRegex(
            ValueError,
            "trade_outside_exact_window",
        ):
            aggressor_trade_imbalance(
                [{**common, "time_ms": 1_000}],
                window_start_ms=1_000,
                window_end_ms=2_000,
                coverage_complete=True,
            )
        result = aggressor_trade_imbalance(
            [{**common, "time_ms": 2_000}],
            window_start_ms=1_000,
            window_end_ms=2_000,
            coverage_complete=True,
        )
        self.assertEqual(result["trade_count"], 1)

    def test_aggressor_measure_blocks_incomplete_or_disordered_events(self):
        trade = {
            "aggregate_trade_id": 2,
            "price": 100,
            "quantity": 1,
            "time_ms": 1_500,
            "buyer_is_maker": False,
        }
        with self.assertRaisesRegex(ValueError, "incomplete_event_window"):
            aggressor_trade_imbalance(
                [trade],
                window_start_ms=1_000,
                window_end_ms=2_000,
                coverage_complete=False,
            )
        with self.assertRaisesRegex(
            ValueError,
            "trade_ids_not_strictly_increasing",
        ):
            aggressor_trade_imbalance(
                [
                    trade,
                    {
                        **trade,
                        "aggregate_trade_id": 1,
                        "time_ms": 1_600,
                    },
                ],
                window_start_ms=1_000,
                window_end_ms=2_000,
                coverage_complete=True,
            )

    def test_periodic_taker_imbalance_requires_an_exact_grid(self):
        result = periodic_taker_imbalance(
            [
                {
                    "timestamp_ms": 1_500,
                    "buy_volume": 4,
                    "sell_volume": 2,
                },
                {
                    "timestamp_ms": 2_000,
                    "buy_volume": 0,
                    "sell_volume": 2,
                },
            ],
            window_start_ms=1_000,
            window_end_ms=2_000,
            period_ms=500,
        )
        self.assertEqual(result["period_count"], 2)
        self.assertAlmostEqual(result["aggressor_trade_imbalance"], 0)
        self.assertEqual(result["direction_descriptor"], "flat")
        self.assertEqual(
            result["ati_source"],
            "binance_usdm_periodic_taker_volume",
        )
        self.assertEqual(result["activity_unit"], "base_asset")
        self.assertIsNone(result["full_order_flow_imbalance"])

    def test_periodic_taker_imbalance_blocks_gaps_and_zero_activity(self):
        with self.assertRaisesRegex(ValueError, "period_gap_or_misalignment"):
            periodic_taker_imbalance(
                [
                    {
                        "timestamp_ms": 1_499,
                        "buy_volume": 1,
                        "sell_volume": 1,
                    },
                    {
                        "timestamp_ms": 2_000,
                        "buy_volume": 1,
                        "sell_volume": 1,
                    },
                ],
                window_start_ms=1_000,
                window_end_ms=2_000,
                period_ms=500,
            )
        with self.assertRaisesRegex(ValueError, "zero_taker_activity"):
            periodic_taker_imbalance(
                [
                    {
                        "timestamp_ms": 2_000,
                        "buy_volume": 0,
                        "sell_volume": 0,
                    }
                ],
                window_start_ms=1_000,
                window_end_ms=2_000,
                period_ms=1_000,
            )

    def test_aggressor_sources_are_reconciled_without_averaging(self):
        event = {"aggressor_trade_imbalance": 0.4}
        periodic = {"aggressor_trade_imbalance": -0.2}
        result = reconcile_aggressor_measures(event, periodic)
        self.assertEqual(result["consistency_descriptor"], "opposite_sign")
        self.assertAlmostEqual(result["signed_difference"], 0.6)
        self.assertEqual(set(result["source_metadata"]), {
            "event_trade",
            "periodic_taker",
        })
        self.assertIsNone(result["combined_value"])
        self.assertIsNone(result["probability_effect"])
        single = reconcile_aggressor_measures(event, None)
        self.assertEqual(single["consistency_descriptor"], "single_source_only")
        self.assertIsNone(single["signed_difference"])

    def test_open_interest_change_is_logarithmic_and_scale_invariant(self):
        timing = {
            "previous_timestamp_ms": 1_000,
            "current_timestamp_ms": 61_000,
            "horizon_seconds": 60,
        }
        result = open_interest_change(100, 125, **timing)
        scaled = open_interest_change(10_000, 12_500, **timing)
        self.assertAlmostEqual(
            result["log_open_interest_change"],
            math.log(1.25),
        )
        self.assertAlmostEqual(
            result["log_open_interest_change"],
            scaled["log_open_interest_change"],
        )
        self.assertIsNone(result["long_short_direction"])
        self.assertIsNone(result["prediction"])
        self.assertEqual(result["actual_separation_seconds"], 60)
        self.assertEqual(result["alignment_error_seconds"], 0)

    def test_open_interest_change_rejects_zero_or_invalid_values(self):
        with self.assertRaisesRegex(
            ValueError,
            "invalid_previous_open_interest",
        ):
            open_interest_change(
                0,
                10,
                previous_timestamp_ms=1_000,
                current_timestamp_ms=61_000,
                horizon_seconds=60,
            )
        with self.assertRaisesRegex(
            ValueError,
            "invalid_current_open_interest",
        ):
            open_interest_change(
                10,
                float("nan"),
                previous_timestamp_ms=1_000,
                current_timestamp_ms=61_000,
                horizon_seconds=60,
            )

    def test_open_interest_change_blocks_endpoint_misalignment(self):
        with self.assertRaisesRegex(
            ValueError,
            "open_interest_endpoint_misalignment",
        ):
            open_interest_change(
                100,
                101,
                previous_timestamp_ms=1_000,
                current_timestamp_ms=60_999,
                horizon_seconds=60,
            )

    def test_price_oi_state_preserves_components_without_narrative(self):
        result = price_open_interest_state(0.03, -0.02)
        self.assertEqual(
            result["state_descriptor"],
            "price_positive__oi_negative",
        )
        self.assertIsNone(result["positioning_label"])
        self.assertIsNone(result["aggregate_score"])
        self.assertIsNone(result["probability_effect"])

    def test_spot_futures_basis_is_scale_invariant_and_bounded_by_quotes(self):
        result = spot_futures_basis(
            futures_bid=101,
            futures_ask=102,
            spot_bid=99,
            spot_ask=100,
            futures_received_at_ms=10_000,
            spot_received_at_ms=11_000,
        )
        scaled = spot_futures_basis(
            futures_bid=10_100,
            futures_ask=10_200,
            spot_bid=9_900,
            spot_ask=10_000,
            futures_received_at_ms=10_000,
            spot_received_at_ms=11_000,
        )
        self.assertAlmostEqual(
            result["mid_log_basis"],
            scaled["mid_log_basis"],
        )
        self.assertLessEqual(
            result["sell_futures_buy_spot_log_basis"],
            result["mid_log_basis"],
        )
        self.assertLessEqual(
            result["mid_log_basis"],
            result["buy_futures_sell_spot_log_basis"],
        )
        self.assertFalse(result["fees_included"])
        self.assertEqual(result["capture_time_basis"], "local_receive_time")
        self.assertFalse(result["market_timestamp_synchronized"])
        self.assertEqual(
            result["basis_capture_uncertainty_status"],
            "receive_time_bounded_not_market_synchronized",
        )
        self.assertIsNone(result["price_leadership"])

    def test_spot_futures_basis_blocks_stale_skew_and_crossed_books(self):
        common = {
            "futures_bid": 101,
            "futures_ask": 102,
            "spot_bid": 99,
            "spot_ask": 100,
            "futures_received_at_ms": 10_000,
            "spot_received_at_ms": 10_000,
        }
        with self.assertRaisesRegex(
            ValueError,
            "cross_venue_capture_skew",
        ):
            spot_futures_basis(
                **{
                    **common,
                    "spot_received_at_ms": (
                        10_000 + CROSS_VENUE_MAX_SKEW_MS + 1
                    ),
                }
            )
        with self.assertRaisesRegex(ValueError, "crossed_futures_book"):
            spot_futures_basis(
                **{**common, "futures_bid": 103}
            )

    def test_mark_index_premium_is_not_mislabelled_as_spot_basis(self):
        result = mark_index_premium(101, 100)
        self.assertAlmostEqual(
            result["mark_index_log_premium"],
            math.log(1.01),
        )
        self.assertIsNone(result["binance_spot_basis"])
        self.assertIsNone(result["prediction"])

    def test_funding_state_normalizes_interval_and_never_projects_rate(self):
        analysis_at_ms = 100 * 86_400_000
        result = funding_state(
            last_funding_rate=0.0008,
            funding_interval_hours=8,
            next_funding_time_ms=analysis_at_ms + 8 * 3_600_000,
            analysis_at_ms=analysis_at_ms,
            horizon_seconds=24 * 3_600,
            historical_events=[
                {
                    "funding_time_ms": analysis_at_ms - 16 * 3_600_000,
                    "funding_rate": 0.0001,
                },
                {
                    "funding_time_ms": analysis_at_ms - 8 * 3_600_000,
                    "funding_rate": -0.0002,
                },
                {
                    "funding_time_ms": analysis_at_ms,
                    "funding_rate": 0.0003,
                },
            ],
        )
        self.assertAlmostEqual(
            result["linearized_last_funding_rate_per_hour"],
            0.0001,
        )
        self.assertNotIn("last_rate_per_hour", result)
        self.assertEqual(result["scheduled_events_under_current_config"], 3)
        self.assertEqual(result["historical_event_count"], 3)
        self.assertAlmostEqual(
            result["previous_horizon_funding_load"],
            0.0002,
        )
        self.assertIsNone(result["future_funding_rate_assumption"])
        self.assertIsNone(result["projected_funding_cost"])
        self.assertIsNone(result["directional_prediction"])

    def test_funding_history_is_left_open_and_strictly_ordered(self):
        analysis_at_ms = 100 * 86_400_000
        common = {
            "last_funding_rate": 0.0001,
            "funding_interval_hours": 8,
            "next_funding_time_ms": analysis_at_ms + 8 * 3_600_000,
            "analysis_at_ms": analysis_at_ms,
            "horizon_seconds": 24 * 3_600,
        }
        with self.assertRaisesRegex(
            ValueError,
            "invalid_historical_funding_time",
        ):
            funding_state(
                **common,
                historical_events=[
                    {
                        "funding_time_ms": (
                            analysis_at_ms - 24 * 3_600_000
                        ),
                        "funding_rate": 0.0001,
                    }
                ],
            )
        with self.assertRaisesRegex(
            ValueError,
            "invalid_historical_funding_time",
        ):
            funding_state(
                **common,
                historical_events=[
                    {
                        "funding_time_ms": (
                            analysis_at_ms - 8 * 3_600_000
                        ),
                        "funding_rate": 0.0001,
                    },
                    {
                        "funding_time_ms": (
                            analysis_at_ms - 16 * 3_600_000
                        ),
                        "funding_rate": 0.0002,
                    },
                ],
            )

    def test_derivatives_vector_has_no_crowding_label_or_score(self):
        result = derivatives_context_vector(
            aggressor_imbalance=0.25,
            log_open_interest_change=0.03,
            mid_log_basis=-0.001,
            linearized_last_funding_rate_per_hour=0.00001,
        )
        self.assertEqual(result["aggressor_imbalance"], 0.25)
        self.assertIsNone(result["crowding_label"])
        self.assertIsNone(result["aggregate_score"])
        self.assertIsNone(result["probability_effect"])
        with self.assertRaisesRegex(
            ValueError,
            "invalid_aggressor_imbalance",
        ):
            derivatives_context_vector(
                aggressor_imbalance=1.01,
                log_open_interest_change=0,
                mid_log_basis=0,
                linearized_last_funding_rate_per_hour=0,
            )

    def test_catalog_has_seven_complete_non_operational_rule_cards(self):
        self.assertEqual(len(self.rules), 7)
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
        }
        for rule in self.rules.values():
            self.assertTrue(required_fields.issubset(rule))
            self.assertFalse(rule["direct_probability_effect_authorized"])
            self.assertFalse(rule["numeric_weight_authorized"])
            self.assertFalse(rule["production_authorized"])

    def test_scope_covers_six_pairs_three_horizons_and_four_p0_blocks(self):
        scope = self.catalog["scope"]
        self.assertEqual(set(scope["symbols"]), set(SYMBOLS))
        self.assertEqual(
            set(scope["horizons"]),
            {"intraday_short", "intraday_wide", "short_swing"},
        )
        self.assertEqual(set(scope["p0_blocks"]), {7, 9, 10, 15})

    def test_operational_policy_forbids_legacy_semantic_shortcuts(self):
        policies = self.catalog["operational_policies"]
        self.assertFalse(policies["funding_projection_allowed"])
        self.assertFalse(policies["market_leadership_label_allowed"])
        self.assertFalse(policies["oi_positioning_label_allowed"])
        self.assertFalse(policies["full_ofi_label_allowed"])
        self.assertEqual(
            policies["cross_venue_max_skew_ms"],
            CROSS_VENUE_MAX_SKEW_MS,
        )
        policy = self.catalog["policy_decision_records"][0]
        self.assertEqual(
            policy["id"],
            "M4-POLICY-CROSS-VENUE-MAX-RECEIVE-SKEW-001",
        )
        self.assertEqual(policy["value"], CROSS_VENUE_MAX_SKEW_MS)

    def test_rule_provider_metadata_matches_each_market(self):
        spot_basis = self.rules["M4-RULE-SPOT-FUTURES-BASIS-001"]
        mark_index = self.rules["M4-RULE-MARK-INDEX-PREMIUM-001"]
        self.assertEqual(
            spot_basis["raw_data_and_provider"]["provider"],
            "Binance USD-M and Binance Spot",
        )
        self.assertEqual(
            mark_index["raw_data_and_provider"]["provider"],
            "Binance USD-M",
        )
        self.assertEqual(
            mark_index["market_symbol_timestamp_unit_freshness"]["markets"],
            ["Binance USD-M perpetual"],
        )

    def test_sources_separate_supported_claims_from_transfer_limits(self):
        sources = {
            source["id"]: source
            for source in self.catalog["sources"]
        }
        for source in sources.values():
            self.assertTrue(source["supported_claim"])
            self.assertTrue(source["does_not_support"])
        self.assertIn(
            "full order-book",
            sources["CONT-KUKANOV-STOIKOV-2014"][
                "supported_claim"
            ],
        )
        self.assertIn(
            "Crypto perpetual intraday",
            sources["HONG-YOGO-2012"]["does_not_support"],
        )
        self.assertIn(
            "fixed leader",
            sources["FRINO-ET-AL-2025"]["does_not_support"],
        )

    def test_all_evidence_families_forbid_additive_double_counting(self):
        families = self.catalog["evidence_families"]
        self.assertEqual(len(families), 5)
        self.assertTrue(
            all(
                not family["additive_members_allowed"]
                for family in families
            )
        )
        flow = next(
            family
            for family in families
            if family["id"] == "M4-EVIDENCE-EXECUTED-AGGRESSOR-FLOW"
        )
        self.assertEqual(len(flow["alternative_sources"]), 3)

    def test_legacy_cvd_oi_and_funding_scores_are_superseded(self):
        superseded = self.catalog["supersedes_current_elements"]
        expected = {
            "IND-CVD-PROXY",
            "SCORE-TAKER_FLOW_BIAS",
            "SCORE-CVD_BIAS",
            "SCORE-OI_TREND_BIAS",
            "SCORE-OI_CONTEXT_PENALTY",
            "SCORE-FUNDING_PENALTY",
            "SCORE-FUNDING_RELATIVE_PENALTY",
            "P0-BLOCK-SPOT-FUTURES",
        }
        self.assertEqual(set(superseded), expected)

    def test_m4_4_closes_without_starting_m5_or_modifying_engines(self):
        scope = self.catalog["scope"]
        self.assertEqual(self.catalog["subphase"], "M4.4")
        self.assertEqual(scope["m4_next_subphase"], "M4.5")
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
