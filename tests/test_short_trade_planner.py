import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import autonomous_confirmation as confirmation
import autonomous_contest as contest
import short_trade_planner as planner
from multiscale_feature_runtime import _closed_material
from tests.test_autonomous_contest import candidate, OperationInsertDb


def material(side="long", *, flat=False):
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(61 * 48 + 1):
        close = 100 + .015 * index + .15 * math.sin(index * math.pi / 10)
        if flat:
            close = 100.0
        if side == "short":
            close = 300 - close
        stamp = int((start + timedelta(minutes=5 * index)).timestamp() * 1000)
        rows.append(dict(open_time_ms=stamp, close_time_ms=stamp + 299999,
                         open=close, close=close, high=close + .10, low=close - .10,
                         volume=100., quote_volume=100.*close,
                         taker_buy_base_volume=55., taker_buy_quote_volume=55.*close))
    at = start + timedelta(minutes=5 * len(rows))
    return _closed_material(dict(time_horizon="intraday_short", analysis_at=at.isoformat()), rows), at


class PlannerTests(unittest.TestCase):
    def test_long_and_short_use_observed_four_hour_excursions_for_both_levels(self):
        for side in ("long", "short"):
            data, at = material(side)
            entry = data["selected"][-1]["close"]
            proposals = planner.proposals(data, side=side, entry=entry)
            self.assertTrue(proposals)
            self.assertLessEqual(len(proposals), 2)
            sign = 1 if side == "long" else -1
            for plan in proposals:
                self.assertGreater(sign * (entry - plan["stop_loss"]), 0)
                self.assertGreater(sign * (plan["take_profit"] - entry), 0)
                self.assertLessEqual(abs(plan["take_profit"] - entry), plan["four_hour_reach"])
                self.assertLessEqual(abs(plan["stop_loss"] - entry), plan["four_hour_adverse_reach"] + 1e-12)
                self.assertGreater(plan["reward_risk_ratio"], 0.)
                self.assertIn(plan["excursion_quantile"], (.25, .50))
                self.assertLessEqual(plan["data_cutoff_at_ms"], data["data_cutoff_at_ms"])
                self.assertEqual(plan["reference_windows"], 59)
                self.assertEqual(plan["horizon_seconds"], 14400)
                self.assertNotIn("candles", plan)

    def test_opposite_direction_and_flat_market_are_analyzed_not_pre_vetoed(self):
        for data, side in ((material()[0], "short"), (material(flat=True)[0], "long")):
            plans = planner.proposals(data, side=side, entry=data["selected"][-1]["close"])
            self.assertTrue(plans)
            self.assertLessEqual(len(plans), 2)

    def test_current_four_hour_excursions_are_not_in_reference_windows(self):
        data, _ = material()
        entry = data["selected"][-1]["close"]
        before = planner.context(data, side="long", entry=entry)
        # An outlier in the last hour changes current ATR, not the historical
        # normalized reach catalogue. Compare reach / current ATR.
        altered = {**data, "selected": [dict(r) for r in data["selected"]]}
        altered["selected"][-1]["high"] += 50
        after = planner.context(altered, side="long", entry=entry)
        self.assertAlmostEqual(before["four_hour_reach"] / before["atr_5m"],
                               after["four_hour_reach"] / after["atr_5m"])

    def test_requote_keeps_absolute_analyzed_barriers(self):
        data, _ = material()
        entry = data["selected"][-1]["close"]
        plan = planner.proposals(data, side="long", entry=entry)[-1]
        again = planner.validate_requote(plan, data, side="long", entry=entry)
        self.assertEqual(again["take_profit"], plan["take_profit"])
        self.assertEqual(again["stop_loss"], plan["stop_loss"])
        with self.assertRaises(planner.PlanRejected):
            planner.validate_requote(plan, data, side="long", entry=plan["take_profit"])

    def test_entry_is_not_vetoed_by_distance_to_an_arbitrary_pivot(self):
        data, _ = material()
        entry = data["selected"][-1]["close"] + 10
        self.assertTrue(planner.proposals(data, side="long", entry=entry))

    def test_forecast_filters_preserve_edge_and_add_resolution_requirements(self):
        policy = contest.PARTICIPANT_POLICIES[0]
        item = candidate(edge=.15, tp=.55, unresolved=.20)
        item.trade_plan = {"version": planner.PLAN_VERSION}
        self.assertTrue(item.eligible_for(policy))
        item.tp_probability = .49
        self.assertFalse(item.eligible_for(policy))
        item.tp_probability, item.unresolved_probability = .55, .26
        self.assertFalse(item.eligible_for(policy))
        item.unresolved_probability, item.edge = .20, .09
        self.assertFalse(item.eligible_for(policy))

    def test_ranking_prioritizes_tp_among_candidates_that_pass_all_gates(self):
        low = candidate(edge=.35, tp=.55, unresolved=.25)
        high = candidate(edge=.30, tp=.65, unresolved=0., symbol="ETHUSDT")
        for item in (low, high):
            item.trade_plan = {"version": planner.PLAN_VERSION}
        self.assertIs(contest.select_candidate([low, high], contest.PARTICIPANT_POLICIES[0]), high)

    def test_changed_invalidation_starts_new_confirmation_episode(self):
        at = datetime(2026, 9, 27, tzinfo=timezone.utc)
        previous = []
        for i, key in enumerate(("anchor-a", "anchor-a", "anchor-b")):
            item = candidate(edge=.15, tp=.55, unresolved=.20)
            item.trade_plan = {"lineage_key": key}
            item.analyzed_at = at + timedelta(minutes=15 * i)
            item.artifact_id = "same-artifact"
            confirmation.advance([item], contest.PARTICIPANT_POLICIES[0], previous,
                                 slot=item.analyzed_at, scan_run_id=i + 1,
                                 engine_version=contest.EMPIRICAL_ENGINE_VERSION)
            previous = [dict(symbol=item.symbol, side=item.side, analyzed_at=item.analyzed_at,
                             engine_version=contest.EMPIRICAL_ENGINE_VERSION,
                             artifact_id=item.artifact_id, confirmation=dict(item.confirmation))]
        self.assertEqual(item.confirmation["controls"], 1)
        self.assertIsNone(confirmation.select([item], contest.PARTICIPANT_POLICIES[0]))

    def test_structural_barriers_survive_actual_operation_insert(self):
        item = candidate(edge=.40, tp=.65, unresolved=.10)
        item.sigma, item.take_profit, item.stop_loss = .02, 102.0, 99.0
        item.trade_plan = {"version": planner.PLAN_VERSION, "lineage_key": "a"}
        item.analysis_result = dict(analysis_type="pre_trade", tp_probability=.65,
                                   sl_probability=.25, range_probability=.10,
                                   risk_level="risk", setup_grade="n/a", confidence="empirical",
                                   parameter_advice={}, reasons=[], alerts=[], snapshot={})
        db = OperationInsertDb()
        contest._open_selected_operation(
            db, participant={"id": 1, "user_id": 27}, season_id=1, candidate=item,
            policy=contest.PARTICIPANT_POLICIES[0], execution_entry=100.02,
            executed_at=item.analyzed_at,
        )
        params = next(p for q, p in db.calls if "INSERT INTO operations" in q)
        self.assertEqual(params[7:9], (99., 102.))
        stored = json.loads(next(p for q, p in db.calls if "INSERT INTO recommendations" in q)[17])
        self.assertEqual(stored["autonomous_trade_plan"]["version"], planner.PLAN_VERSION)
        self.assertEqual(stored["snapshot"]["take_profit"], 102.)
        self.assertEqual(stored["snapshot"]["stop_loss"], 99.)

    def test_scanner_uses_same_engine_with_at_most_two_proposals_per_side(self):
        data, at = material()
        calls = []
        def analyze(proposal, **kwargs):
            calls.append(proposal)
            return dict(tp_probability=.60, sl_probability=.25, range_probability=.15,
                        snapshot={}, model_trace={"artifact_id": "same-engine",
                        "stage_traces": [{"selected_analogs": 100}]})
        with patch.object(contest, "load_horizon_material", return_value=data):
            rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[0],
                {"BTCUSDT": data["selected"][-1]["close"]}, at,
                analysis_runner=analyze, symbols=("BTCUSDT",))
        self.assertLessEqual(len(calls), 4)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].eligible_for(contest.PARTICIPANT_POLICIES[0]))
        self.assertEqual(rows[1].analysis_status, "evaluated")
        self.assertEqual({p.side for p in calls}, {"long", "short"})

    def test_future_candles_do_not_change_the_plan(self):
        data, at = material()
        future = dict(data["selected"][-1])
        future.update(open_time_ms=int(at.timestamp()*1000),
                      close_time_ms=int(at.timestamp()*1000)+299999,
                      open=1e6, close=1e6, high=1e6+1, low=1e6-1)
        filtered = _closed_material(dict(time_horizon="intraday_short", analysis_at=at.isoformat()),
                                    data["selected"] + [future])
        entry = data["selected"][-1]["close"]
        self.assertEqual(planner.proposals(data, side="long", entry=entry),
                         planner.proposals(filtered, side="long", entry=entry))

    def test_final_reanalysis_evaluates_exact_same_absolute_levels(self):
        data, at = material()
        entry = data["selected"][-1]["close"]
        plan = planner.proposals(data, side="long", entry=entry)[-1]
        selected = candidate(edge=.35, tp=.60, unresolved=.15)
        selected.trade_plan = plan
        calls = []
        def analyze(proposal, **kwargs):
            calls.append(proposal)
            return dict(tp_probability=.60, sl_probability=.25, range_probability=.15,
                        snapshot={}, model_trace={"artifact_id": "same-engine",
                        "stage_traces": [{"selected_analogs": 100}]})
        with patch.object(contest, "load_horizon_material", return_value=data):
            rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[0],
                {"BTCUSDT": entry + .001}, at, analysis_runner=analyze,
                symbols=("BTCUSDT",), sides=("long",), fixed_candidate=selected)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].take_profit, plan["take_profit"])
        self.assertEqual(calls[0].stop_loss, plan["stop_loss"])
        self.assertEqual(rows[0].trade_plan["lineage_key"], plan["lineage_key"])

    def test_planned_control_with_real_rule_context_fits_existing_byte_budget(self):
        from multiscale_feature_runtime import build_stage_context
        from sequential_production_runtime import apply_target_rule_trace_scope
        from empirical_temporal_engine import load_production_artifact
        data, at = material()
        entry = data["selected"][-1]["close"]
        plan = planner.proposals(data, side="long", entry=entry)[-1]
        ctx = build_stage_context(dict(symbol="BTCUSDT", side="long", entry=entry,
            take_profit=plan["take_profit"], stop_loss=plan["stop_loss"],
            time_horizon="intraday_short", horizon_seconds=14400, analysis_at=at.isoformat()), data["selected"])
        apply_target_rule_trace_scope({"intraday_short": ctx}, "intraday_short", load_production_artifact())
        previous = []
        for index in range(3):
            item = candidate(edge=.35, tp=.60, unresolved=.15)
            item.trade_plan = plan
            item.analyzed_at = at + timedelta(minutes=15*index)
            item.analysis_result = {"snapshot": {"stage_rule_traces": {"intraday_short": ctx["rule_traces"]}}}
            confirmation.advance([item], contest.PARTICIPANT_POLICIES[0], previous,
                slot=item.analyzed_at, scan_run_id=index+1, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
            previous = [dict(symbol=item.symbol, side=item.side, analyzed_at=item.analyzed_at,
                artifact_id=item.artifact_id, engine_version=contest.EMPIRICAL_ENGINE_VERSION,
                confirmation=dict(item.confirmation))]
        payload = confirmation.compact_payload(item)
        self.assertIs(confirmation.select([item], contest.PARTICIPANT_POLICIES[0]), item)
        self.assertLessEqual(len(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()),
                             confirmation.CONTROL_JSON_BYTE_BUDGET)
        self.assertNotIn("selected", payload)
        self.assertTrue(payload["active_context"])

    def test_missing_data_pauses_planned_followup_but_invalid_plan_discards(self):
        data, at = material()
        plan = planner.proposals(data, side="long", entry=data["selected"][-1]["close"])[-1]
        previous = []
        for index in range(2):
            item = candidate(edge=.35, tp=.60, unresolved=.15)
            item.trade_plan, item.analyzed_at = plan, at + timedelta(minutes=15*index)
            confirmation.advance([item], contest.PARTICIPANT_POLICIES[0], previous,
                slot=item.analyzed_at, scan_run_id=index+1, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
            previous = [dict(symbol=item.symbol, side=item.side, analyzed_at=item.analyzed_at,
                artifact_id=item.artifact_id, engine_version=contest.EMPIRICAL_ENGINE_VERSION,
                confirmation=dict(item.confirmation))]
        for reason, expected in (("plan_data:provider_failed", "paused"),
                                 ("short_plan_barrier_already_crossed", "discarded")):
            failed = candidate(edge=.35, tp=.60, unresolved=.15)
            failed.analysis_status, failed.rejection_code = "blocked", reason
            failed.analyzed_at = at + timedelta(minutes=30)
            confirmation.advance([failed], contest.PARTICIPANT_POLICIES[0], previous,
                slot=failed.analyzed_at, scan_run_id=3, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
            self.assertEqual(failed.confirmation["state"], expected)
            self.assertEqual(failed.confirmation["controls"], 2)

    def test_rr_below_one_is_allowed_only_with_positive_forecast_payoff(self):
        item = candidate(edge=.40, tp=.65, unresolved=.10)
        item.trade_plan = {"version": planner.PLAN_VERSION}
        item.take_profit = 100.5
        self.assertTrue(item.eligible_for(contest.PARTICIPANT_POLICIES[0]))
        item.sigma = .02
        self.assertTrue(contest.execution_drift_is_acceptable(item, 100.))
        item.take_profit = 100.1
        self.assertFalse(item.eligible_for(contest.PARTICIPANT_POLICIES[0]))
        item.take_profit = 99.5
        self.assertFalse(planner.passes_forecast(item))

    def test_followup_preserves_levels_key_and_count_across_new_market_cutoffs(self):
        data, at = material()
        entry = data["selected"][-1]["close"]
        previous, levels, calls = [], None, []
        def analyze(proposal, **kwargs):
            calls.append(proposal)
            return dict(tp_probability=.60, sl_probability=.25, range_probability=.15,
                        snapshot={}, model_trace={"artifact_id": "same-engine",
                        "stage_traces": [{"selected_analogs": 100}]})
        for index in range(3):
            changed = {**data, "data_cutoff_at_ms": data["data_cutoff_at_ms"] + index * 900000,
                       "data_sha256": str(index)}
            with patch.object(contest, "load_horizon_material", return_value=changed):
                rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[0],
                    {"BTCUSDT": entry + index * .001}, at + timedelta(minutes=index*15),
                    analysis_runner=analyze, symbols=("BTCUSDT",), sides=("long",),
                    previous_confirmations=previous)
            item = rows[0]
            confirmation.advance(rows, contest.PARTICIPANT_POLICIES[0], previous,
                slot=item.analyzed_at, scan_run_id=index+1, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
            current = (item.take_profit, item.stop_loss, item.trade_plan["lineage_key"])
            if levels is None:
                levels = current
            self.assertEqual(current, levels)
            payload = confirmation.compact_payload(item)
            previous = [dict(symbol=item.symbol, side=item.side, analyzed_at=item.analyzed_at,
                artifact_id=item.artifact_id, engine_version=contest.EMPIRICAL_ENGINE_VERSION,
                take_profit=item.take_profit, stop_loss=item.stop_loss, **payload)]
        self.assertEqual(item.confirmation["controls"], 3)
        self.assertEqual(item.confirmation["state"], "ready")
        self.assertEqual(len(calls), 4)  # Two initial alternatives, then the exact chosen plan twice.
        for state in ("discarded", "consumed"):
            previous[0]["confirmation"]["state"] = state
            self.assertIsNone(confirmation.frozen_plan(previous[0], plan_version=planner.PLAN_VERSION))

    def test_missing_data_preserves_frozen_geometry_in_paused_storage(self):
        data, at = material()
        plan = planner.proposals(data, side="long", entry=data["selected"][-1]["close"])[-1]
        item = candidate(edge=.35, tp=.60, unresolved=.15)
        item.trade_plan, item.analyzed_at = plan, at
        item.entry = data["selected"][-1]["close"]
        item.take_profit, item.stop_loss = plan["take_profit"], plan["stop_loss"]
        confirmation.advance([item], contest.PARTICIPANT_POLICIES[0], [],
            slot=at, scan_run_id=1, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
        previous = dict(symbol=item.symbol, side=item.side, analyzed_at=at,
            artifact_id=item.artifact_id, engine_version=contest.EMPIRICAL_ENGINE_VERSION,
            take_profit=item.take_profit, stop_loss=item.stop_loss, **confirmation.compact_payload(item))
        failed = candidate(edge=.35, tp=.60, unresolved=.15)
        failed.analysis_status, failed.rejection_code = "failed", "sigma:provider_unavailable"
        failed.analyzed_at = at + timedelta(minutes=15)
        failed.take_profit = failed.stop_loss = None
        confirmation.advance([failed], contest.PARTICIPANT_POLICIES[0], [previous],
            slot=failed.analyzed_at, scan_run_id=2, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
        self.assertEqual(failed.confirmation["state"], "paused")
        self.assertEqual(failed.confirmation["controls"], 1)
        self.assertEqual((failed.take_profit, failed.stop_loss), (item.take_profit, item.stop_loss))
        self.assertEqual(confirmation.compact_payload(failed)["proposal_plan"], previous["proposal_plan"])

    def test_actual_production_engine_retains_support_guard_without_extra_downloads(self):
        from sequential_production_analysis import analyze_trade
        data, at = material()
        downloads = []
        def loader(symbol, interval, limit, start_time_ms, end_time_ms):
            downloads.append((symbol, interval, start_time_ms, end_time_ms))
            return [[r["open_time_ms"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["close_time_ms"],
                     r["quote_volume"], 100, r["taker_buy_base_volume"], r["taker_buy_quote_volume"]]
                    for r in data["selected"] if start_time_ms <= r["open_time_ms"] <= end_time_ms][:limit]
        with patch.object(contest.market_data, "collect_positioning_observation", return_value={"stages": {}}):
            rows = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[0],
                {"BTCUSDT": data["selected"][-1]["close"]}, at, analysis_runner=analyze_trade,
                kline_loader=loader, liquidation_contexts={"BTCUSDT": None},
                order_book_contexts={"BTCUSDT": None}, symbols=("BTCUSDT",), sides=("long",))
        self.assertIn(rows[0].analysis_status, {"evaluated", "blocked"}, rows[0].rejection_code)
        if rows[0].analysis_status == "evaluated":
            self.assertAlmostEqual(rows[0].tp_probability + rows[0].sl_probability + rows[0].unresolved_probability, 1.)
            self.assertEqual(rows[0].analysis_result["engine_version"], contest.EMPIRICAL_ENGINE_VERSION)
        else:
            self.assertTrue(rows[0].rejection_code.startswith("context_outside_historical_support:"), rows[0].rejection_code)
            self.assertIsNone(rows[0].tp_probability)
            self.assertIsNone(rows[0].analysis_result)
        self.assertEqual(rows[0].trade_plan["version"], planner.PLAN_VERSION)
        self.assertLessEqual(len(downloads), 3)
        self.assertEqual(len(downloads), len(set(downloads)))


if __name__ == "__main__":
    unittest.main()
