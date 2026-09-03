import json
import unittest
from datetime import datetime, timezone

import autonomous_contest


class Cursor:
    def __init__(self, row=None, lastrowid=None):
        self._row = row
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._row


class OperationInsertDb:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        normalized = " ".join(query.split())
        if "SELECT COUNT(*) AS count" in normalized:
            return Cursor({"count": 0})
        if "SELECT starting_balance FROM contest_entries" in normalized:
            return Cursor({"starting_balance": 1000.0})
        if "AS closed_pnl" in normalized and "AS active_margin" in normalized:
            return Cursor({"closed_pnl": 0.0, "active_margin": 0.0})
        if "INSERT INTO operations" in normalized:
            return Cursor(lastrowid=501)
        if "INSERT INTO recommendations" in normalized:
            return Cursor(lastrowid=601)
        return Cursor()


class CountDb:
    def __init__(self, count):
        self.count = count

    def execute(self, _query, _params=None):
        return Cursor({"count": self.count})


def candidate(*, edge, tp=0.45, unresolved=0.30, symbol="BTCUSDT"):
    sl = tp - edge
    return autonomous_contest.Candidate(
        symbol=symbol,
        side="long",
        time_horizon="intraday_short",
        analyzed_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        entry=100.0,
        take_profit=101.0,
        stop_loss=99.0,
        tp_probability=tp,
        sl_probability=sl,
        unresolved_probability=unresolved,
        edge=edge,
        selected_analogs_min=100,
        analysis_status="evaluated",
    )


class AutonomousContestPolicyTests(unittest.TestCase):
    def test_scanner_kline_cache_reuses_exact_pages_without_shared_mutation(self):
        calls = []

        def loader(symbol, interval, limit, start_time_ms=None, end_time_ms=None):
            calls.append((symbol, interval, limit, start_time_ms, end_time_ms))
            return [[1000, "1", "2", "0.5", "1.5", "10", 1999]]

        cached = autonomous_contest.MemoizedKlineLoader(loader)
        first = cached("btcusdt", "5m", 1500, 1000, 2000)
        first[0][1] = "mutated"
        second = cached("BTCUSDT", "5m", 1500, 1000, 2000)

        self.assertEqual(len(calls), 1)
        self.assertEqual(second[0][1], "1")
        self.assertEqual(
            cached.stats(),
            {"provider_requests": 1, "cache_hits": 1, "cached_pages": 1},
        )

    def test_three_horizon_policies_have_the_agreed_cadence_and_quotas(self):
        policies = {
            policy.time_horizon: policy
            for policy in autonomous_contest.PARTICIPANT_POLICIES
        }

        self.assertEqual(len(policies), 3)
        self.assertEqual(policies["intraday_short"].cadence_minutes, 15)
        self.assertEqual(policies["intraday_short"].daily_operation_limit, 3)
        self.assertEqual(policies["intraday_wide"].cadence_minutes, 60)
        self.assertEqual(policies["intraday_wide"].daily_operation_limit, 2)
        self.assertEqual(policies["short_swing"].cadence_minutes, 360)
        self.assertEqual(policies["short_swing"].daily_operation_limit, 1)
        self.assertEqual(
            {symbol for policy in policies.values() for symbol in policy.symbols},
            set(autonomous_contest.SYMBOLS),
        )

    def test_release_delay_never_uses_the_slot_before_worker_data_is_ready(self):
        policy = autonomous_contest.PARTICIPANT_POLICIES[0]

        before_release = autonomous_contest.scan_slot(
            policy,
            datetime(2026, 8, 30, 12, 1, 14, tzinfo=timezone.utc),
        )
        at_release = autonomous_contest.scan_slot(
            policy,
            datetime(2026, 8, 30, 12, 1, 15, tzinfo=timezone.utc),
        )

        self.assertEqual(before_release.hour, 11)
        self.assertEqual(before_release.minute, 45)
        self.assertEqual(at_release.hour, 12)
        self.assertEqual(at_release.minute, 0)

    def test_canonical_storage_panels_match_the_compact_daily_budget(self):
        short, wide, swing = autonomous_contest.PARTICIPANT_POLICIES
        day = datetime(2026, 8, 30, tzinfo=timezone.utc)
        short_slots = [
            day.replace(hour=minute // 60, minute=minute % 60)
            for minute in range(0, 24 * 60, 15)
        ]
        wide_slots = [day.replace(hour=hour) for hour in range(24)]
        swing_slots = [day.replace(hour=hour) for hour in range(0, 24, 6)]

        self.assertEqual(
            sum(autonomous_contest.is_canonical_panel(short, slot) for slot in short_slots),
            6,
        )
        self.assertEqual(
            sum(autonomous_contest.is_canonical_panel(wide, slot) for slot in wide_slots),
            1,
        )
        self.assertEqual(
            sum(autonomous_contest.is_canonical_panel(swing, slot) for slot in swing_slots),
            1,
        )
        self.assertEqual((6 + 1 + 1) * 12, 96)

    def test_non_panel_candidate_storage_has_one_global_daily_cap(self):
        policy = autonomous_contest.PARTICIPANT_POLICIES[0]
        slot = datetime(2026, 8, 30, 0, 15, tzinfo=timezone.utc)
        winner = candidate(edge=0.15)
        runner_up = candidate(edge=0.09, symbol="ETHUSDT")

        last_slot = autonomous_contest._candidate_storage_selection(
            CountDb(11),
            policy,
            slot,
            [winner, runner_up],
            winner,
        )
        full = autonomous_contest._candidate_storage_selection(
            CountDb(12),
            policy,
            slot,
            [winner, runner_up],
            winner,
        )

        self.assertEqual(last_slot, {(winner.symbol, winner.side): "selected"})
        self.assertEqual(full, {})

    def test_horizon_thresholds_are_not_replaced_by_one_universal_rule(self):
        short, wide, swing = autonomous_contest.PARTICIPANT_POLICIES
        viable_only_for_swing = candidate(edge=0.05)

        self.assertIsNone(autonomous_contest.select_candidate([viable_only_for_swing], short))
        self.assertIsNone(autonomous_contest.select_candidate([viable_only_for_swing], wide))
        self.assertIs(
            autonomous_contest.select_candidate([viable_only_for_swing], swing),
            viable_only_for_swing,
        )

    def test_position_sizing_replaces_fixed_100_x1_with_probability_based_capital(self):
        selected = candidate(
            edge=0.495320077120577 - 0.317254342473678,
            tp=0.495320077120577,
            unresolved=0.187425580405745,
        )
        selected.entry = 686.87
        selected.take_profit = 677.251276028439
        selected.stop_loss = 696.488723971561
        selected.side = "short"

        sizing = autonomous_contest.determine_position_sizing(selected, 1000.0)

        self.assertEqual(sizing.leverage, 4)
        self.assertGreater(sizing.margin, 500.0)
        self.assertGreater(sizing.estimated_tp_pnl, 2.0)
        self.assertGreater(sizing.expected_pnl, 0.0)
        self.assertEqual(
            sizing.as_dict()["probability_effect"],
            "none_post_selection_only",
        )

    def test_stronger_advantage_allocates_more_capital_but_not_blind_leverage(self):
        weak = candidate(edge=0.10, tp=0.40, unresolved=0.30)
        strong = candidate(edge=0.25, tp=0.55, unresolved=0.15)

        weak_sizing = autonomous_contest.determine_position_sizing(weak, 1000.0)
        strong_sizing = autonomous_contest.determine_position_sizing(strong, 1000.0)

        self.assertGreater(strong_sizing.margin, weak_sizing.margin)
        self.assertGreater(
            strong_sizing.estimated_tp_pnl,
            weak_sizing.estimated_tp_pnl,
        )
        self.assertLessEqual(
            strong_sizing.leverage,
            autonomous_contest.MAX_AUTONOMOUS_LEVERAGE,
        )

    def test_wide_stop_reduces_margin_to_respect_the_sl_budget(self):
        selected = candidate(edge=0.10, tp=0.40, unresolved=0.30)
        selected.take_profit = 112.0
        selected.stop_loss = 88.0

        sizing = autonomous_contest.determine_position_sizing(selected, 1000.0)

        self.assertEqual(sizing.leverage, 1)
        self.assertAlmostEqual(sizing.margin, 250.0, places=4)
        self.assertAlmostEqual(sizing.estimated_sl_pnl, -30.0, places=4)

    def test_tight_stop_can_use_x10_and_still_guarantees_two_dollar_tp(self):
        selected = candidate(edge=0.10, tp=0.40, unresolved=0.30)
        selected.take_profit = 100.025
        selected.stop_loss = 99.975

        sizing = autonomous_contest.determine_position_sizing(selected, 1000.0)

        self.assertEqual(sizing.leverage, 10)
        self.assertAlmostEqual(sizing.margin, 800.0, places=4)
        self.assertGreaterEqual(
            sizing.estimated_tp_pnl,
            autonomous_contest.MIN_TARGET_PROFIT_USDT,
        )

    def test_position_size_scales_with_balance_without_a_nominal_stake_cap(self):
        selected = candidate(edge=0.10, tp=0.40, unresolved=0.30)

        small = autonomous_contest.determine_position_sizing(selected, 1000.0)
        large = autonomous_contest.determine_position_sizing(selected, 10_000.0)

        self.assertAlmostEqual(large.margin, small.margin * 10, places=4)
        self.assertEqual(large.leverage, small.leverage)

    def test_gates_reject_low_tp_high_unresolved_and_low_support(self):
        policy = autonomous_contest.PARTICIPANT_POLICIES[0]
        low_tp = candidate(edge=0.15, tp=0.29, unresolved=0.20)
        high_unresolved = candidate(edge=0.15, tp=0.60, unresolved=0.56)
        low_support = candidate(edge=0.15)
        low_support.selected_analogs_min = 79

        self.assertIsNone(
            autonomous_contest.select_candidate(
                [low_tp, high_unresolved, low_support],
                policy,
            )
        )

    def test_symmetric_geometry_preserves_direction(self):
        self.assertEqual(
            autonomous_contest.symmetric_geometry(100.0, 0.02, "long"),
            (102.0, 98.0),
        )
        self.assertEqual(
            autonomous_contest.symmetric_geometry(100.0, 0.02, "short"),
            (98.0, 102.0),
        )

    def test_execution_rejects_a_stale_analysis_price_after_material_drift(self):
        selected = candidate(edge=0.15)
        selected.sigma = 0.01

        self.assertTrue(
            autonomous_contest.execution_drift_is_acceptable(selected, 100.05)
        )
        self.assertFalse(
            autonomous_contest.execution_drift_is_acceptable(selected, 100.20)
        )

    def test_selected_analysis_contract_uses_actual_worker_execution_price(self):
        selected = candidate(edge=0.15)
        selected.sigma = 0.01
        selected.analysis_result = {
            "snapshot": {"entry": 100.0, "take_profit": 101.0, "stop_loss": 99.0},
        }
        executed_at = selected.analyzed_at.replace(minute=1)

        result = autonomous_contest._prepare_selected_analysis(
            selected,
            execution_entry=100.05,
            execution_take_profit=101.0505,
            execution_stop_loss=99.0495,
            executed_at=executed_at,
        )

        self.assertEqual(result["snapshot"]["entry"], 100.05)
        self.assertEqual(result["snapshot"]["take_profit"], 101.0505)
        self.assertEqual(
            result["entry_order_context"]["execution_price_authority"],
            "operation_worker",
        )
        self.assertEqual(result["data_contract"]["pre_trade_features"]["entry"], 100.05)

    def test_operation_and_recommendation_are_linked_to_fresh_execution_price(self):
        policy = autonomous_contest.PARTICIPANT_POLICIES[0]
        selected = candidate(edge=0.15)
        selected.sigma = 0.01
        selected.take_profit = 101.0
        selected.stop_loss = 99.0
        selected.analysis_result = {
            "analysis_type": "pre_trade",
            "tp_probability": 0.45,
            "sl_probability": 0.30,
            "range_probability": 0.25,
            "risk_level": "30.0% SL",
            "setup_grade": "no aplicable",
            "confidence": "empirica",
            "training_decision": "decision del usuario",
            "parameter_advice": {},
            "reasons": [],
            "alerts": [],
            "snapshot": {
                "entry": 100.0,
                "take_profit": 101.0,
                "stop_loss": 99.0,
            },
            "engine_version": "TP-SL-EMPIRICAL-ANALOG-v0.9",
        }
        db = OperationInsertDb()
        executed_at = selected.analyzed_at.replace(minute=1)

        operation_id, recommendation_id = autonomous_contest._open_selected_operation(
            db,
            participant={"id": 9, "user_id": 7},
            season_id=3,
            candidate=selected,
            policy=policy,
            execution_entry=100.05,
            executed_at=executed_at,
        )

        self.assertEqual((operation_id, recommendation_id), (501, 601))
        operation_params = next(
            params for query, params in db.calls if "INSERT INTO operations" in query
        )
        recommendation_params = next(
            params for query, params in db.calls if "INSERT INTO recommendations" in query
        )
        tick_params = next(
            params for query, params in db.calls if "INSERT INTO price_ticks" in query
        )
        self.assertEqual(operation_params[4], 100.05)
        self.assertEqual(operation_params[5], 500.0)
        self.assertEqual(operation_params[6], 7)
        self.assertEqual(operation_params[9], executed_at.isoformat())
        self.assertEqual(operation_params[11], 100.05)
        self.assertEqual(recommendation_params[0], 501)
        self.assertEqual(tick_params[2], 100.05)
        self.assertFalse(
            any(
                "SELECT COUNT(*) AS count" in " ".join(query.split())
                and "status IN ('OPEN', 'PENDING_ENTRY')" in " ".join(query.split())
                for query, _params in db.calls
            ),
            "Existing open positions must never block today's operation target.",
        )
        stored_analysis = json.loads(recommendation_params[17])
        self.assertEqual(stored_analysis["position_sizing"]["margin"], 500.0)
        self.assertEqual(stored_analysis["position_sizing"]["leverage"], 7)
        self.assertNotIn("position_sizing", stored_analysis["snapshot"])

    def test_observational_payload_is_bounded_and_contains_no_raw_market_data(self):
        result = {
            "snapshot": {
                "stage_rule_traces": {
                    "intraday_short": [
                        {
                            "rule_id": "OBS-1",
                            "status": "evaluated_shadow",
                            "probability_effect": "none_observation_only",
                            "outputs": {"oversized": "x" * 50_000},
                        }
                    ]
                },
                "liquidation_observation": {"status": "evaluated_observation"},
                "order_book_observation": {"status": "evaluated_observation"},
            }
        }

        compact = autonomous_contest._compact_observations(result)

        self.assertLessEqual(
            len(json.dumps(compact, separators=(",", ":")).encode("utf-8")),
            autonomous_contest.OBSERVATIONAL_JSON_BYTE_BUDGET,
        )
        self.assertFalse(compact["raw_market_payloads_stored"])

    def test_counterfactual_outcome_uses_first_touch_order(self):
        candles = [
            {
                "open_time_ms": 1_777_593_600_000,
                "high": 100.5,
                "low": 99.5,
                "close": 100.2,
            },
            {
                "open_time_ms": 1_777_593_660_000,
                "high": 101.1,
                "low": 100.0,
                "close": 100.9,
            },
            {
                "open_time_ms": 1_777_593_720_000,
                "high": 101.0,
                "low": 98.9,
                "close": 99.0,
            },
        ]

        outcome = autonomous_contest._evaluate_path(
            candles,
            side="long",
            entry=100.0,
            take_profit=101.0,
            stop_loss=99.0,
        )

        self.assertEqual(outcome["first_touch"], "tp")
        self.assertEqual(outcome["r_multiple"], 1.0)


if __name__ == "__main__":
    unittest.main()
