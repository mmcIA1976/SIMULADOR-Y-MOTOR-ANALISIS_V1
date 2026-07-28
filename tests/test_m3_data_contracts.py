from __future__ import annotations

import unittest

from build_m3_data_contracts import (
    HORIZONS,
    P0_BLOCK_DATA,
    REQUEST_MAX_LATENCY_MS,
    SNAPSHOT_MAX_SPAN_MS,
    SYMBOLS,
    build_catalog,
    build_current_audit,
    build_matrix,
    closed_klines_before_analysis,
    read_live_audit,
    validate_observation_time,
    validate_snapshot_capture,
)


def kline(open_time: int, close_time: int) -> list:
    return [
        open_time,
        "100",
        "102",
        "99",
        "101",
        "10",
        close_time,
        "1005",
        25,
        "6",
        "603",
    ]


class M3DataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_catalog()
        cls.matrix = build_matrix(cls.catalog)
        cls.audit = build_current_audit()
        cls.live = read_live_audit()

    def test_catalog_defines_18_unique_p0_contracts(self):
        contracts = self.catalog["contracts"]
        contract_ids = {item["id"] for item in contracts}
        self.assertEqual(len(contracts), 18)
        self.assertEqual(len(contract_ids), 18)
        self.assertTrue(all(item["priority"] == "P0" for item in contracts))
        self.assertEqual(
            set(self.catalog["universe"]["symbols"]),
            set(SYMBOLS),
        )
        self.assertEqual(
            set(self.catalog["universe"]["horizons"]),
            set(HORIZONS),
        )

    def test_every_contract_declares_fields_time_units_and_absence(self):
        for contract in self.catalog["contracts"]:
            self.assertTrue(contract["fields"], contract["id"])
            self.assertTrue(
                all(item["unit"] for item in contract["fields"]),
                contract["id"],
            )
            time_contract = contract["time_contract"]
            self.assertTrue(time_contract["requested_at_required"])
            self.assertTrue(time_contract["received_at_required"])
            self.assertIn("analysis_at", time_contract["analysis_rule"])
            missing_effect = contract["missing_effect"].lower()
            self.assertTrue(
                "never_neutral" in missing_effect
                or "blocked" in missing_effect,
                contract["id"],
            )

    def test_sources_are_official_free_or_explicitly_conditional(self):
        by_id = {
            item["id"]: item for item in self.catalog["contracts"]
        }
        public = [
            item
            for item in by_id.values()
            if item["authentication"] == "public"
        ]
        self.assertTrue(public)
        self.assertTrue(
            all(
                item["documentation_url"].startswith(
                    "https://developers.binance.com/"
                )
                for item in public
            )
        )
        commission = by_id["M3-DATA-018"]
        self.assertEqual(commission["authentication"], "signed_user_data")
        self.assertEqual(
            commission["source_status"],
            "approved_conditional_auth_source",
        )
        self.assertEqual(
            commission["current_implementation"]["status"],
            "not_implemented",
        )

    def test_liquidations_and_learning_are_outside_m3(self):
        serialized = str(self.catalog).lower()
        self.assertFalse(
            self.catalog["scope"]["p1_liquidations_included"]
        )
        self.assertFalse(self.catalog["scope"]["learning_engine_used"])
        self.assertNotIn("hyperperps", serialized)
        self.assertNotIn("hyperliquid", serialized)

    def test_matrix_covers_every_p0_block_pair_and_horizon(self):
        rows = self.matrix["rows"]
        self.assertEqual(len(P0_BLOCK_DATA), 12)
        self.assertEqual(
            len(rows),
            len(P0_BLOCK_DATA) * len(SYMBOLS) * len(HORIZONS),
        )
        combinations = {
            (row["block_id"], row["symbol"], row["time_horizon"])
            for row in rows
        }
        self.assertEqual(len(combinations), len(rows))
        self.assertEqual(
            {row["block_id"] for row in rows},
            set(P0_BLOCK_DATA),
        )

    def test_matrix_does_not_invent_m4_rules_or_claim_readiness(self):
        rows = self.matrix["rows"]
        self.assertTrue(
            all(
                row["rule_contract_status"] == "not_defined_until_M4"
                for row in rows
            )
        )
        self.assertTrue(
            all(not row["rigorous_candidate_ready"] for row in rows)
        )
        self.assertEqual(
            self.matrix["summary"]["current_ready_rows"],
            0,
        )

    def test_m3_is_owner_approved_without_starting_m4(self):
        self.assertEqual(
            self.catalog["status"],
            "completed_owner_approved",
        )
        self.assertEqual(self.catalog["approved_at"], "2026-07-27")
        self.assertEqual(
            self.matrix["status"],
            "completed_owner_approved",
        )
        self.assertEqual(self.matrix["approved_at"], "2026-07-27")
        self.assertFalse(self.catalog["scope"]["m4_started"])

    def test_pending_trigger_post_closure_clarification_is_explicit(self):
        plan_contract = next(
            item
            for item in self.catalog["contracts"]
            if item["id"] == "M3-DATA-001"
        )
        fields = {item["field"] for item in plan_contract["fields"]}
        self.assertIn("trigger_condition", fields)
        clarifications = self.catalog["post_closure_clarifications"]
        self.assertEqual(len(clarifications), 2)
        clarification = next(
            item
            for item in clarifications
            if item["id"] == "M3-CLARIFICATION-001"
        )
        self.assertEqual(
            clarification["id"],
            "M3-CLARIFICATION-001",
        )
        self.assertEqual(
            clarification["field_added"],
            "trigger_condition",
        )
        self.assertFalse(clarification["source_or_endpoint_changed"])
        self.assertFalse(clarification["production_modified"])
        self.assertFalse(clarification["m3_conclusions_changed"])

    def test_exposure_post_closure_clarification_is_explicit(self):
        plan_contract = next(
            item
            for item in self.catalog["contracts"]
            if item["id"] == "M3-DATA-001"
        )
        fields = {
            item["field"]: item["unit"]
            for item in plan_contract["fields"]
        }
        self.assertEqual(fields["margin"], "quote_asset")
        self.assertEqual(fields["leverage"], "multiple")
        clarification = next(
            item
            for item in self.catalog["post_closure_clarifications"]
            if item["id"] == "M3-CLARIFICATION-002"
        )
        self.assertEqual(clarification["identified_in_phase"], "M4.5")
        self.assertEqual(
            clarification["fields_added"],
            ["margin", "leverage"],
        )
        self.assertFalse(clarification["source_or_endpoint_changed"])
        self.assertFalse(clarification["production_modified"])
        self.assertFalse(clarification["m3_conclusions_changed"])

    def test_live_public_source_audit_passed_76_checks(self):
        summary = self.live["summary"]
        self.assertEqual(self.live["status"], "pass")
        self.assertEqual(summary["checks"], 76)
        self.assertEqual(summary["passed"], 76)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["per_symbol_endpoint_checks"], 72)
        self.assertEqual(summary["global_endpoint_checks"], 4)
        self.assertEqual(summary["authenticated_checks_skipped"], 1)
        self.assertTrue(all(item["ok"] for item in self.live["checks"]))

    def test_signed_commission_was_not_falsely_tested_as_public(self):
        self.assertEqual(
            self.live["authenticated_checks"],
            [
                {
                    "contract_id": "M3-DATA-018",
                    "endpoint": "/fapi/v1/commissionRate",
                    "status": "not_executed_authentication_required",
                }
            ],
        )

    def test_valid_observation_uses_provider_time_when_available(self):
        result = validate_observation_time(
            provider_time_ms=99_000,
            requested_at_ms=99_500,
            received_at_ms=100_000,
            analysis_at_ms=101_000,
            max_age_ms=5_000,
        )
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["timestamp_quality"], "provider_time")
        self.assertEqual(result["age_ms"], 2_000)

    def test_receive_time_fallback_is_labelled_not_hidden(self):
        result = validate_observation_time(
            provider_time_ms=None,
            requested_at_ms=99_500,
            received_at_ms=100_000,
            analysis_at_ms=101_000,
            max_age_ms=5_000,
        )
        self.assertEqual(result["timestamp_quality"], "receive_time_only")
        self.assertEqual(result["evidence_time_ms"], 100_000)

    def test_future_stale_slow_and_misordered_observations_are_rejected(self):
        cases = (
            (
                "future_data",
                dict(
                    provider_time_ms=101_001,
                    requested_at_ms=99_500,
                    received_at_ms=100_000,
                    analysis_at_ms=101_000,
                    max_age_ms=5_000,
                ),
            ),
            (
                "stale_data",
                dict(
                    provider_time_ms=90_000,
                    requested_at_ms=99_500,
                    received_at_ms=100_000,
                    analysis_at_ms=101_000,
                    max_age_ms=5_000,
                ),
            ),
            (
                "request_latency_exceeded",
                dict(
                    provider_time_ms=100_000,
                    requested_at_ms=80_000,
                    received_at_ms=80_000 + REQUEST_MAX_LATENCY_MS + 1,
                    analysis_at_ms=101_000,
                    max_age_ms=5_000,
                ),
            ),
            (
                "invalid_capture_order",
                dict(
                    provider_time_ms=100_000,
                    requested_at_ms=100_500,
                    received_at_ms=100_000,
                    analysis_at_ms=101_000,
                    max_age_ms=5_000,
                ),
            ),
        )
        for expected, arguments in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    validate_observation_time(**arguments)

    def test_only_closed_recent_klines_survive(self):
        raw = [
            kline(0, 59_999),
            kline(60_000, 119_999),
            kline(120_000, 179_999),
        ]
        result = closed_klines_before_analysis(
            raw,
            analysis_at_ms=125_000,
            interval_ms=60_000,
        )
        self.assertEqual(result, raw[:2])

    def test_open_stale_or_disordered_klines_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no_closed_klines"):
            closed_klines_before_analysis(
                [kline(120_000, 179_999)],
                analysis_at_ms=125_000,
                interval_ms=60_000,
            )
        with self.assertRaisesRegex(ValueError, "closed_klines_stale"):
            closed_klines_before_analysis(
                [kline(0, 59_999)],
                analysis_at_ms=181_000,
                interval_ms=60_000,
            )
        with self.assertRaisesRegex(
            ValueError, "klines_not_strictly_ordered"
        ):
            closed_klines_before_analysis(
                [kline(60_000, 119_999), kline(0, 59_999)],
                analysis_at_ms=125_000,
                interval_ms=60_000,
            )

    def test_snapshot_capture_has_a_bounded_span(self):
        observations = [
            {
                "provider_time_ms": 99_000,
                "requested_at_ms": 99_000,
                "received_at_ms": 100_000,
                "max_age_ms": 30_000,
            },
            {
                "provider_time_ms": None,
                "requested_at_ms": 100_000,
                "received_at_ms": 101_000,
                "max_age_ms": 30_000,
            },
        ]
        result = validate_snapshot_capture(
            observations,
            analysis_at_ms=102_000,
        )
        self.assertEqual(result["capture_span_ms"], 1_000)
        self.assertEqual(result["provider_timestamp_count"], 1)
        self.assertEqual(result["receive_time_only_count"], 1)

        observations[1]["received_at_ms"] = (
            observations[0]["received_at_ms"]
            + SNAPSHOT_MAX_SPAN_MS
            + 1
        )
        observations[1]["requested_at_ms"] = observations[1][
            "received_at_ms"
        ]
        with self.assertRaisesRegex(
            ValueError, "snapshot_capture_span_exceeded"
        ):
            validate_snapshot_capture(
                observations,
                analysis_at_ms=observations[1]["received_at_ms"] + 1,
            )

    def test_current_pipeline_failure_is_explicit_and_nonfunctional(self):
        summary = self.audit["summary"]
        self.assertEqual(summary["findings"], 15)
        self.assertEqual(summary["critical"], 10)
        self.assertEqual(summary["high"], 5)
        self.assertFalse(summary["production_modified"])
        self.assertFalse(self.catalog["scope"]["production_modified"])
        self.assertFalse(self.catalog["scope"]["analysis_engine_modified"])
        self.assertFalse(self.catalog["scope"]["m4_started"])
        self.assertFalse(self.catalog["scope"]["predictive_rules_defined"])


if __name__ == "__main__":
    unittest.main()
