from __future__ import annotations

import unittest

from m5_engine import engine_contract, run_internal_analysis


FIXED_TIME = "2026-07-27T12:00:00+00:00"
BASE_MS = 1_800_000_000_000


def minimal_inputs() -> dict[str, dict]:
    return {
        "M4-RULE-HORIZON-SAMPLING-001": {
            "horizon_seconds": 3600,
            "profile_intervals_seconds": [60],
        },
        "M4-RULE-PLAN-GEOMETRY-001": {
            "side": "long",
            "entry": 100,
            "take_profit": 110,
            "stop_loss": 95,
        },
        "M4-RULE-EXPONENTIAL-SMOOTHER-001": {
            "values": [1, 2, 3],
            "alpha": 0.5,
        },
        "M4-RULE-FEE-SCENARIOS-001": {
            "notional": 1000,
            "commission_rates": {"taker": 0.0005},
            "allowed_roles": ["taker"],
        },
        "M4-RULE-FUNDING-STATE-001": {
            "last_funding_rate": 0.0008,
            "funding_interval_hours": 8,
            "current_time_ms": BASE_MS,
            "horizon_seconds": 3600,
        },
        "M4-RULE-MARK-INDEX-PREMIUM-001": {
            "mark_price": 101,
            "index_price": 100,
            "provider_time": BASE_MS,
        },
        "M4-RULE-QUOTED-SPREAD-001": {
            "best_bid": 99,
            "best_ask": 101,
            "receive_time": BASE_MS,
        },
        "M4-RULE-SPOT-FUTURES-BASIS-001": {
            "futures_bid": 101,
            "futures_ask": 102,
            "spot_bid": 99,
            "spot_ask": 100,
            "futures_received_at_ms": BASE_MS,
            "spot_received_at_ms": BASE_MS,
        },
        "M4-RULE-AGGRESSOR-IMBALANCE-001": {
            "ati_source": "periodic",
            "periods": [{"buy_volume": 60, "sell_volume": 40}],
            "window_start_ms": BASE_MS,
            "window_end_ms": BASE_MS + 3_600_000,
            "coverage_start_ms": BASE_MS,
            "coverage_end_ms": BASE_MS + 3_600_000,
        },
        "M4-RULE-OPEN-INTEREST-CHANGE-001": {
            "previous_timestamp_ms": BASE_MS,
            "current_timestamp_ms": BASE_MS + 3_600_000,
            "horizon_seconds": 3600,
            "previous_open_interest": 1000,
            "current_open_interest": 1100,
        },
        "M4-RULE-DERIVATIVES-CONTEXT-001": {
            "basis_source": "spot_futures",
        },
    }


class M54DagEngineTests(unittest.TestCase):
    def test_empty_input_still_produces_one_trace_per_rule(self) -> None:
        result = run_internal_analysis(
            analysis_id="empty",
            rule_inputs={},
            executed_at=FIXED_TIME,
        )
        self.assertEqual(result["rule_count"], 27)
        self.assertEqual(len(result["traces"]), 27)
        self.assertEqual(
            {trace["rule_id"] for trace in result["traces"]},
            set(engine_contract()["dag"]["topological_order"]),
        )
        self.assertEqual(result["production_effect"], "none")

    def test_trace_order_is_exact_approved_topological_order(self) -> None:
        result = run_internal_analysis(
            analysis_id="order",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(
            [trace["rule_id"] for trace in result["traces"]],
            engine_contract()["dag"]["topological_order"],
        )

    def test_selected_basis_is_the_only_alternative_dependency(self) -> None:
        result = run_internal_analysis(
            analysis_id="basis",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        context = next(
            trace
            for trace in result["traces"]
            if trace["rule_id"] == "M4-RULE-DERIVATIVES-CONTEXT-001"
        )
        parent_ids = {item["rule_id"] for item in context["dependencies"]}
        self.assertIn("M4-RULE-SPOT-FUTURES-BASIS-001", parent_ids)
        self.assertNotIn("M4-RULE-MARK-INDEX-PREMIUM-001", parent_ids)

    def test_failed_parent_blocks_child_without_running_formula(self) -> None:
        result = run_internal_analysis(
            analysis_id="blocked",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        price_oi = next(
            trace
            for trace in result["traces"]
            if trace["rule_id"] == "M4-RULE-PRICE-OI-STATE-001"
        )
        self.assertEqual(price_oi["status"], "blocked")
        self.assertEqual(price_oi["outputs"], {})
        self.assertEqual(
            price_oi["reason_codes"],
            ("dependency_not_evaluated",),
        )

    def test_no_family_is_aggregated_into_a_score(self) -> None:
        result = run_internal_analysis(
            analysis_id="families",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(len(result["canonical_families"]), 17)
        self.assertTrue(
            all(
                not item["additive_aggregation_performed"]
                for item in result["canonical_families"]
            )
        )
        self.assertIsNone(result["numeric_score_output"])
        self.assertIsNone(result["probability_output"])

    def test_fixed_inputs_and_time_have_reproducible_trace_hash(self) -> None:
        first = run_internal_analysis(
            analysis_id="same",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        second = run_internal_analysis(
            analysis_id="same",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(
            first["analysis_trace_sha256"],
            second["analysis_trace_sha256"],
        )

    def test_every_trace_declares_no_production_effect(self) -> None:
        result = run_internal_analysis(
            analysis_id="production",
            rule_inputs=minimal_inputs(),
            executed_at=FIXED_TIME,
        )
        self.assertTrue(
            all(
                trace["production_effect"] == "none"
                for trace in result["traces"]
            )
        )
        self.assertFalse(result["m6_started"])


if __name__ == "__main__":
    unittest.main()
