import copy
import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import autonomous_confirmation as confirmation
import autonomous_contest as contest
import swing_trade_planner as planner
from multiscale_feature_runtime import _closed_material
from tests.test_autonomous_contest import candidate, OperationInsertDb


def material():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(61 * 28 + 1):
        close = 100 * math.exp(.0002 * index + .004 * math.sin(index * .7))
        stamp = int((start + timedelta(hours=6 * index)).timestamp() * 1000)
        rows.append(dict(open_time_ms=stamp, close_time_ms=stamp + 21599999,
                         open=close, close=close, high=close * 1.003, low=close * .997,
                         volume=100., quote_volume=100.*close,
                         taker_buy_base_volume=55., taker_buy_quote_volume=55.*close))
    at = start + timedelta(hours=6 * len(rows))
    return _closed_material(dict(time_horizon="short_swing", analysis_at=at.isoformat()), rows), at


def forecast(proposal, **kwargs):
    return dict(tp_probability=.55, sl_probability=.30, range_probability=.15,
                snapshot={}, model_trace={"artifact_id": "same-engine",
                "stage_traces": [{"selected_analogs": 100}]})


class SwingPlannerTests(unittest.TestCase):
    def test_three_direction_neutral_proposals_keep_seven_day_forecast(self):
        data, _ = material()
        long = planner.proposals(data, side="long", entry=100.)
        short = planner.proposals(data, side="short", entry=100.)
        self.assertEqual([p["proposal_hours"] for p in long], [24, 48, 72])
        self.assertEqual([p["radius_fraction"] for p in long], [p["radius_fraction"] for p in short])
        for left, right in zip(long, short):
            self.assertEqual(left["take_profit"], right["stop_loss"])
            self.assertEqual(left["stop_loss"], right["take_profit"])
            self.assertEqual(left["horizon_seconds"], 604800)
            self.assertEqual(left["reference_windows"], 60)
            self.assertLess(left["reference_last_end_at_ms"], left["current_window_start_at_ms"])
            self.assertAlmostEqual(left["radius_fraction"], left["current_sigma"] * left["normalized_reach_quantile"])

    def test_latest_72_hours_cannot_enter_reference_catalogue(self):
        data, _ = material()
        before = planner.proposals(data, side="long", entry=100.)[-1]
        changed = copy.deepcopy(data)
        for index, row in enumerate(changed["selected"][-12:]):
            row["close"] *= 1 + .001 * (index + 1)
            row["high"] = row["close"] * 1.003
            row["low"] = row["close"] * .997
        after = planner.proposals(changed, side="long", entry=100.)[-1]
        self.assertEqual(before["normalized_reach_quantile"], after["normalized_reach_quantile"])
        self.assertNotEqual(before["current_sigma"], after["current_sigma"])

    def test_unclosed_future_candle_cannot_change_proposals(self):
        data, at = material()
        future = dict(data["selected"][-1])
        future.update(open_time_ms=int(at.timestamp()*1000), close_time_ms=int(at.timestamp()*1000)+21599999,
                      open=1e6, close=1e6, high=1e6+1, low=1e6-1)
        filtered = _closed_material(dict(time_horizon="short_swing", analysis_at=at.isoformat()),
                                    data["selected"] + [future])
        self.assertEqual(planner.proposals(data, side="short", entry=100.),
                         planner.proposals(filtered, side="short", entry=100.))

    def test_bad_context_blocks_instead_of_falling_back_to_seven_day_sigma(self):
        data, _ = material()
        for mutation in ({"interval_seconds": 3600}, {"selected": data["selected"][-100:]},
                         {"data_cutoff_at_ms": 0}):
            with self.assertRaises(planner.PlanRejected):
                planner.proposals({**data, **mutation}, side="long", entry=100.)
        data["selected"][-2]["open_time_ms"] -= 1
        with self.assertRaisesRegex(planner.PlanRejected, "history_gap"):
            planner.proposals(data, side="long", entry=100.)

    def test_flat_market_and_duplicate_radii_are_bounded(self):
        data, _ = material()
        for row in data["selected"]:
            row.update(close=100., high=100., low=100.)
        with self.assertRaises(planner.PlanRejected):
            planner.proposals(data, side="long", entry=100.)
        data, _ = material()
        with patch.object(planner, "PROPOSAL_HOURS", (24, 24, 24)):
            self.assertEqual(len(planner.proposals(data, side="long", entry=100.)), 1)

    def test_scanner_audits_all_alternatives_and_loads_candles_once(self):
        data, at = material()
        calls, records = [], []
        def analyze(proposal, **kwargs):
            calls.append(proposal)
            return forecast(proposal)
        with patch.object(contest, "load_horizon_material", return_value=data) as load:
            rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[2], {"BTCUSDT": 100.}, at,
                analysis_runner=analyze, symbols=("BTCUSDT",), audit_records=records)
        load.assert_called_once()
        self.assertEqual(len(calls), 6)
        self.assertEqual(len(records), 6)
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["proposal_hours"] for r in records}, {24, 48, 72})
        self.assertTrue(all(r["proposal_source_sha256"] == data["data_sha256"] for r in records))
        self.assertTrue(all(p.time_horizon == "short_swing" for p in calls))
        self.assertTrue(all(row.eligible_for(contest.PARTICIPANT_POLICIES[2]) for row in rows))
        self.assertTrue(all(row.trade_plan["alternatives_evaluated"] == 3 for row in rows))

    def test_final_reanalysis_freezes_radius_and_checks_same_forecast_gates(self):
        data, at = material()
        selected = candidate(edge=.25, tp=.55, unresolved=.15)
        selected.time_horizon = "short_swing"
        selected.trade_plan = planner.proposals(data, side="long", entry=100.)[1]
        calls = []
        def analyze(proposal, **kwargs):
            calls.append(proposal)
            return dict(forecast(proposal), tp_probability=.43, sl_probability=.42)
        with patch.object(contest, "load_horizon_material", return_value=data):
            rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[2], {"BTCUSDT": 100.1}, at,
                analysis_runner=analyze, symbols=("BTCUSDT",), sides=("long",), fixed_candidate=selected)
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0].trade_plan["lineage_key"], selected.trade_plan["lineage_key"])
        radius = selected.trade_plan["radius_fraction"]
        self.assertAlmostEqual(calls[0].take_profit, 100.1 * (1 + radius))
        self.assertAlmostEqual(calls[0].stop_loss, 100.1 * (1 - radius))
        self.assertFalse(rows[0].eligible_for(contest.PARTICIPANT_POLICIES[2]))
        with self.assertRaises(planner.PlanRejected):
            planner.validate_requote({**selected.trade_plan, "version": "old"}, data, side="long", entry=100.)

    def test_alternative_selection_never_prefers_a_forecast_that_fails_gates(self):
        data, at = material()
        plans = planner.proposals(data, side="long", entry=100.)
        records = []
        def analyze(proposal, **kwargs):
            if abs(proposal.take_profit - plans[0]["take_profit"]) < 1e-9:
                return dict(forecast(proposal), tp_probability=.65, sl_probability=.10, range_probability=.25)
            if abs(proposal.take_profit - plans[1]["take_profit"]) < 1e-9:
                return dict(forecast(proposal), tp_probability=.46, sl_probability=.44, range_probability=.10)
            return forecast(proposal)
        with patch.object(contest, "load_horizon_material", return_value=data):
            rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[2], {"BTCUSDT": 100.}, at,
                analysis_runner=analyze, symbols=("BTCUSDT",), sides=("long",), audit_records=records)
        self.assertEqual([r["eligible"] for r in records], [False, False, True])
        self.assertEqual(rows[0].trade_plan["proposal_hours"], 72)

    def test_swing_keeps_edge_priority_in_panel_and_confirmation(self):
        stronger = candidate(edge=.30, tp=.55, unresolved=.20)
        higher_tp = candidate(edge=.28, tp=.60, unresolved=.08, symbol="ETHUSDT")
        for row in (stronger, higher_tp):
            row.time_horizon = "short_swing"
            row.trade_plan = {"version": planner.PLAN_VERSION}
        policy = contest.PARTICIPANT_POLICIES[2]
        self.assertIs(contest.select_candidate([stronger, higher_tp], policy), stronger)
        self.assertIs(confirmation.select([stronger, higher_tp], policy), stronger)

    def test_insert_keeps_swing_version_symmetric_levels_and_minimum_profit(self):
        data, at = material()
        selected = candidate(edge=.25, tp=.55, unresolved=.15)
        selected.time_horizon, selected.analyzed_at = "short_swing", at
        selected.sigma = math.sqrt(data["current_variance"])
        selected.trade_plan = planner.proposals(data, side="long", entry=100.)[1]
        selected.take_profit = selected.trade_plan["take_profit"]
        selected.stop_loss = selected.trade_plan["stop_loss"]
        selected.analysis_result = dict(forecast(None), analysis_type="pre_trade",
            risk_level="risk", setup_grade="n/a", confidence="empirical",
            parameter_advice={}, reasons=[], alerts=[])
        db = OperationInsertDb()
        contest._open_selected_operation(db, participant={"id": 3, "user_id": 29}, season_id=7,
            candidate=selected, policy=contest.PARTICIPANT_POLICIES[2], execution_entry=100.01, executed_at=at)
        stored = json.loads(next(p for q, p in db.calls if "INSERT INTO recommendations" in q)[17])
        self.assertEqual(stored["version_contract"]["autonomous_trade_plan_version"], planner.PLAN_VERSION)
        self.assertEqual(stored["entry_order_context"]["proposal_plan_version"], planner.PLAN_VERSION)
        geometry = stored["snapshot"]["execution_geometry"]
        self.assertAlmostEqual(geometry["take_profit"] - 100.01, 100.01 - geometry["stop_loss"])
        self.assertGreaterEqual(stored["position_sizing"]["estimated_tp_pnl"], 25.)
