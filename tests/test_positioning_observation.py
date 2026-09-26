from __future__ import annotations

import copy
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import positioning_observation as positioning
from observational_measurement_scores import absorption_proxy
from current_engine_rule_direction import score_current_trace_case, score_compact_measurements
from operation_observation_learning import _compact_stage_rule_traces, observation_rule_signals
from observational_learning_base import current_snapshot_rule_values


END = 1789200000000
H = 4*3600000
CUTOFF = END+600000


def context():
    return {"interval": "5m", "interval_seconds": 300, "horizon_seconds": H//1000,
            "positioning_price_pair": {"end_ms": END, "start_ms": END-H,
                                       "price_current": 110, "price_previous": 100}}


def payload():
    return {"stages": {"intraday_short": {"oi_rows": [
        {"timestamp": END-H, "sumOpenInterest": "100", "sumOpenInterestValue": "999999"},
        {"timestamp": END, "sumOpenInterest": "120", "sumOpenInterestValue": "1"}]}},
        "funding_rows": [{"fundingTime": END-8*3600000, "fundingRate": "0.0001"},
                         {"fundingTime": END, "fundingRate": "0.0002"}]}


def evaluate(data=None, ctx=None):
    return positioning.evaluate_positioning_stage(ctx or context(), data or payload(),
        stage="intraday_short", cutoff_ms=CUTOFF)


class PositioningObservationTests(unittest.TestCase):
    def test_exact_alignment_base_quantity_and_settled_semantics(self):
        oi, price_oi, funding = evaluate()
        self.assertAlmostEqual(oi["outputs"]["dOI_H"], __import__("math").log(1.2))
        self.assertEqual(price_oi["outputs"]["start_ms"], oi["outputs"]["start_ms"])
        self.assertEqual(funding["outputs"]["observed_interval_hours"], 8)
        self.assertEqual(funding["outputs"]["settled_funding_rate_per_hour"],0.000025)
        self.assertNotIn("last_funding_rate", funding["outputs"])
        self.assertTrue(all(t["active_probability_outputs"] == [] for t in evaluate()))

    def test_missing_duplicate_future_and_lagged_endpoints(self):
        data = payload()
        data["stages"]["intraday_short"]["oi_rows"][1]["timestamp"] += 1
        self.assertEqual(evaluate(data)[0]["reason_codes"], ["exact_oi_endpoints_unavailable"])
        data = payload()
        data["stages"]["intraday_short"]["oi_rows"].append({"timestamp": END,"sumOpenInterest": 130})
        self.assertEqual(evaluate(data)[0]["reason_codes"], ["conflicting_oi_endpoint"])
        ctx = context()
        ctx["positioning_price_pair"]["end_ms"] = CUTOFF
        self.assertEqual(evaluate(ctx=ctx)[0]["reason_codes"], ["causal_price_pair_missing"])
        data = payload()
        data["funding_rows"].append({"fundingTime": CUTOFF+1, "fundingRate": "99"})
        self.assertEqual(evaluate(data)[2]["outputs"]["last_settled_funding_rate"], 0.0002)

    def test_missing_and_stale_are_not_neutral_funding(self):
        data = payload()
        data["funding_rows"] = [{"fundingTime": CUTOFF-86400001,"fundingRate": "0"}]
        funding = evaluate(data)[2]
        self.assertEqual(funding["reason_codes"], ["settled_funding_stale"])
        self.assertNotIn("last_settled_funding_rate", funding["outputs"])

    def test_single_payment_kept_but_not_assigned_a_comparable_score(self):
        data = payload()
        data["funding_rows"] = data["funding_rows"][-1:]
        traces = evaluate(data)
        self.assertNotIn("settled_funding_rate_per_hour",traces[2]["outputs"])
        scores = score_current_trace_case({"side":"long","time_horizon":"intraday_short","traces": traces})
        funding = next(r for r in scores if r["rule_id"] == positioning.FUNDING_RULE)
        self.assertIsNone(funding["directional_score"])

    def test_same_funding_payment_not_three_new_confirmations(self):
        from observation_numeric_evolution import build_evolution
        rows = []
        for index in range(3):
            data = payload()
            data["funding_observed_at_ms"] = CUTOFF+index*1200000
            trace = positioning.evaluate_positioning_stage(context(),data,stage="intraday_short",
                cutoff_ms=CUTOFF+index*1200000)[2]
            rows.append({"checkpoint_code": f"1o{index+1}",
                "observed_at": datetime.fromtimestamp((CUTOFF+index*1200000)/1000,timezone.utc).isoformat(),
                "market_price": 100+index,"snapshot_json": {"stage_rule_traces":{"intraday_short":[trace]}}})
        report = build_evolution({"id":1,"symbol":"BTCUSDT","side":"long","time_horizon":"intraday_short"},rows)
        metric = next(s for s in report["series"] if s["metric"] == "settled_funding_rate_per_hour")
        self.assertEqual(metric["distinct_evidence"],1)
        self.assertEqual(metric["same_source_controls"],2)
        self.assertFalse(metric["latest"]["three_distinct_readings_same_sign"])
        self.assertFalse(any(s["metric"] in {"observed_at_ms","age_seconds"} for s in report["series"]))

    def test_cache_reuses_both_sides_and_failure_has_cooldown(self):
        positioning._cache.clear()
        at = datetime.fromtimestamp(CUTOFF/1000, timezone.utc).isoformat()
        with patch.object(positioning.market_data,"get_open_interest_history",return_value=[]) as oi, \
             patch.object(positioning.market_data,"get_funding_history",return_value=[]) as funding, \
             patch.object(positioning.time,"time",return_value=CUTOFF/1000):
            positioning.collect_positioning_observation("BTCUSDT",{"intraday_short": context()},at)
            positioning.collect_positioning_observation("BTCUSDT",{"intraday_short": context()},at)
        self.assertEqual(oi.call_count,1)
        self.assertEqual(funding.call_count,1)
        self.assertEqual(oi.call_args.kwargs["limit"],51)
        positioning._cache.clear()

    def test_live_collector_does_not_invent_historical_availability(self):
        at = datetime.fromtimestamp(CUTOFF/1000,timezone.utc).isoformat()
        with patch.object(positioning.time,"time",return_value=CUTOFF/1000+7200), \
             patch.object(positioning.market_data,"get_open_interest_history") as oi:
            result = positioning.collect_positioning_observation("BTCUSDT",{"intraday_short": context()},at)
        self.assertIn("archived_provider",result["reason"])
        oi.assert_not_called()

    def test_unchanged_hourly_oi_does_not_refetch_each_fifteen_minutes(self):
        positioning._cache.clear()
        ctx = {"interval":"1h","interval_seconds":3600,"horizon_seconds":86400,
            "positioning_price_pair":{"end_ms":END-3600000,"start_ms":END-3600000-86400000,
                                      "price_current":110,"price_previous":100}}
        with patch.object(positioning.market_data,"get_open_interest_history",return_value=[{"timestamp":END}]) as oi, \
             patch.object(positioning.market_data,"get_funding_history",return_value=[]) as funding, \
             patch.object(positioning.time,"time",return_value=(CUTOFF+900000)/1000), \
             patch.object(positioning.time,"monotonic",side_effect=[0,0,901,901]):
            for delta in (0,900000):
                at=datetime.fromtimestamp((CUTOFF+delta)/1000,timezone.utc).isoformat()
                positioning.collect_positioning_observation("BTCUSDT",{"intraday_wide":ctx},at)
        self.assertEqual(oi.call_count,1)
        self.assertEqual(funding.call_count,2)
        positioning._cache.clear()

    def test_attachment_is_idempotent_compact_and_probability_invariant(self):
        run = {"stage_contexts": {"intraday_short": context()},"stage_rule_traces": {},
               "probability_result": {"probabilities": {"tp": 0.4,"sl": 0.3,"range": 0.3}},
               "feature_values": {"original": 42}}
        before = copy.deepcopy(run["probability_result"])
        at = datetime.fromtimestamp(CUTOFF/1000,timezone.utc).isoformat()
        for _ in range(2):
            positioning.attach_positioning_observation(run,SimpleNamespace(symbol="BTCUSDT"),
                observation_loader=lambda *a: payload(),analysis_at=at)
        self.assertEqual(run["probability_result"],before)
        self.assertEqual(len(run["stage_rule_traces"]["intraday_short"]),3)
        compact = _compact_stage_rule_traces(run["stage_rule_traces"])
        self.assertEqual(compact["intraday_short"][2]["rule_version"],"settled-funding-v1")
        text = json.dumps(compact)
        self.assertNotIn("oi_rows",text)
        self.assertNotIn("funding_rows",text)
        self.assertLess(len(text.encode()),5000)
        signals = observation_rule_signals({"side": "long","stage_rule_traces": compact})
        self.assertEqual(len(signals),3)
        self.assertTrue(all(s["score"] is None for s in signals))
        snapshot = {"stage_rule_traces": compact}
        values,_ = current_snapshot_rule_values(snapshot,side="long",time_horizon="intraday_short",
            baseline_specs=[{"rule_id": positioning.FUNDING_RULE,"selected_variable": "__current_formula_signal"}])
        self.assertIsNone(values[positioning.FUNDING_RULE]["value"])
        self.assertEqual(values[positioning.FUNDING_RULE]["measurement"]["numeric_inputs"]["last_settled_funding_rate"],0.0002)
        scores = score_compact_measurements({"side": "long","time_horizon": "intraday_short","signals_json": values})
        self.assertEqual(scores[0]["directional_score"],-2)
        self.assertIn("settled-funding-v1",scores[0]["formula_role"])

    def test_provider_exception_does_not_fail_analysis(self):
        run = {"stage_contexts": {"intraday_short": context()}}
        def fail(*args): raise TimeoutError()
        report = positioning.attach_positioning_observation(run,SimpleNamespace(symbol="BTCUSDT"),
            observation_loader=fail,analysis_at=datetime.fromtimestamp(CUTOFF/1000,timezone.utc).isoformat())
        self.assertEqual(report["provider_reason"],"provider_failed:TimeoutError")
        self.assertTrue(all(t["status"] == "blocked" for t in run["stage_rule_traces"]["intraday_short"]))
        values,_ = current_snapshot_rule_values({"stage_rule_traces": run["stage_rule_traces"]},
            side="long",time_horizon="intraday_short",baseline_specs=[])
        self.assertEqual(values[positioning.OI_RULE]["measurement"]["reason_codes"],
                         ["exact_oi_endpoints_unavailable"])
        self.assertIsNone(values[positioning.OI_RULE]["value"])

    def test_price_pair_covers_exact_horizon_on_each_stage(self):
        from tests.test_sequential_production_contract import synthetic_candles
        from multiscale_feature_runtime import build_stage_context, STAGE_PROFILES
        for horizon, profile in STAGE_PROFILES.items():
            candles, at = synthetic_candles(horizon)
            ctx = build_stage_context({"time_horizon": horizon,"horizon_seconds": profile["horizon_seconds"],
                "analysis_at": at.isoformat(),"side": "long","entry": 100,"stop_loss": 95,"take_profit": 105}, candles)
            pair = ctx["positioning_price_pair"]
            self.assertEqual(pair["end_ms"]-pair["start_ms"],profile["horizon_seconds"]*1000)
            self.assertLessEqual(pair["end_ms"], int(at.timestamp()*1000)-profile["interval_seconds"]*1000)

    def test_absorption_is_independent_proxy_not_aggressor_alias(self):
        vector = {"ATI_H": 0.3,"relative_horizon_volume": 2,
                  "horizon_displacement_atr": 0.1,"flow_opposing_wick_ratio": 0.9}
        a = absorption_proxy(vector,side="long")
        b = absorption_proxy({**vector,"horizon_displacement_atr": 2},side="long")
        self.assertEqual(a["directional_score"],-4)
        self.assertAlmostEqual(a["raw_directional_value"],-0.81)
        self.assertEqual(b["directional_score"],0)
        self.assertEqual(absorption_proxy(vector,side="short")["trade_side_score"],4)
        self.assertIsNone(absorption_proxy({"ATI_H": 0.3},side="long")["directional_score"])
        scores = score_current_trace_case({"side": "long","time_horizon": "intraday_short",
            "traces": [{"rule_id": "LIB-CAND-ABSORPTION-001","outputs": vector}]})
        self.assertEqual(scores[0]["directional_score"],-4)
        self.assertIn("proxy-v1",scores[0]["formula_role"])


if __name__ == "__main__":
    unittest.main()
