from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone

from observation_numeric_evolution import (
    build_evolution, compare_episodes, pack, unpack, state, canonical, MAX_PAYLOAD_BYTES,
)
from observation_evolution_store import persist_evolution, source_identity, report_view


BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
OP = {"id": 1, "symbol": "BTCUSDT", "side": "long", "time_horizon": "intraday_short",
      "started_at": BASE.isoformat(), "closed_at": (BASE+timedelta(hours=5)).isoformat()}
RULE = "LIB-CAND-RSI-WILDER-001"


def checkpoints(values, prices=None, times=None, sources=None, catalog="fixed"):
    rows = []
    for i, value in enumerate(values):
        trace = {"rule_id": RULE, "rule_version": "1", "status": "evaluated_shadow",
                 "outputs": {"side_adjusted_centered_rsi": value},
                 "source_data_sha256": (sources or [str(j) for j in range(len(values))])[i]}
        rows.append({"checkpoint_code": f"1o{i+1}",
                     "observed_at": (BASE+timedelta(minutes=(times or [j*20 for j in range(len(values))])[i])).isoformat(),
                     "market_price": (prices or [100+i for i in range(len(values))])[i],
                     "snapshot_json": {"rule_catalog": {"catalog_sha256": catalog},
                         "stage_rule_traces": {"intraday_short": [trace]}}})
    return rows


class NumericEvolutionTests(unittest.TestCase):
    def test_positive_can_be_weakening_without_becoming_negative(self):
        report = build_evolution(OP, checkpoints([.7,.6,.5,.4]), include_points=True)
        last = report["series"][0]["latest"]
        self.assertTrue(last["three_distinct_readings_same_sign"])
        self.assertEqual(last["direction"], "falling")
        self.assertAlmostEqual(last["delta"], -.1)
        self.assertAlmostEqual(last["slope_per_hour"], -.3)
        self.assertAlmostEqual(last["three_reading_mean"], .5)

    def test_repeated_candle_is_not_three_confirmations(self):
        report = build_evolution(OP, checkpoints([.5,.5,.5],sources=["same"]*3))
        series = report["series"][0]
        self.assertEqual(series["distinct_evidence"],1)
        self.assertEqual(series["same_source_controls"],2)
        self.assertFalse(series["latest"]["three_distinct_readings_same_sign"])
        self.assertEqual(series["forward"]["20"]["n"],1)

    def test_new_candle_with_same_value_is_real_evidence_but_no_trend(self):
        s = build_evolution(OP,checkpoints([.5,.5,.5]))["series"][0]
        self.assertEqual(s["distinct_evidence"],3)
        self.assertEqual(s["latest"]["direction"],"flat")

    def test_missing_observation_resets_persistence(self):
        rows = checkpoints([.5,.6,.7,.8],times=[0,20,80,100])
        s = build_evolution(OP,rows)["series"][0]
        self.assertEqual(s["continuity_resets"],1)
        self.assertFalse(s["latest"]["three_distinct_readings_same_sign"])
        self.assertEqual(s["forward"]["60"]["n"],0)

    def test_gap_does_not_turn_an_old_candle_into_new_evidence(self):
        rows=checkpoints([.5,.5,.5],times=[0,20,80],sources=["same"]*3)
        s=build_evolution(OP,rows)["series"][0]
        self.assertEqual(s["distinct_evidence"],1)
        self.assertTrue(s["latest"]["repeated_evidence"])
        self.assertFalse(s["latest"]["three_distinct_readings_same_sign"])

    def test_future_values_do_not_change_past_descriptors(self):
        short = build_evolution(OP,checkpoints([.2,.3,.4]),include_points=True)
        long = build_evolution(OP,checkpoints([.2,.3,.4,99]),include_points=True)
        self.assertEqual(short["series"][0]["points"],long["series"][0]["points"][:3])

    def test_terminal_tp_is_not_the_label_for_intermediate_falling_price(self):
        operation = {**OP,"close_reason":"take_profit"}
        s = build_evolution(operation,checkpoints([.1,.2,.3],prices=[100,99,98]))["series"][0]
        self.assertLess(s["forward"]["20"]["mean_return_bps"],0)
        self.assertEqual(s["forward"]["240"]["n"],0)
        self.assertEqual(s["forward"]["240"]["excluded"]["right_censored"],3)

    def test_short_side_orients_price_return(self):
        s = build_evolution({**OP,"side":"short"},checkpoints([.1,.2],prices=[100,99]))["series"][0]
        self.assertAlmostEqual(s["forward"]["20"]["mean_return_bps"],100)

    def test_endpoint_delay_is_not_silently_a_different_horizon(self):
        s = build_evolution(OP,checkpoints([.1,.2],times=[0,25]))["series"][0]
        self.assertEqual(s["forward"]["20"]["excluded"]["endpoint_not_observed"],1)

    def test_formula_changes_do_not_merge(self):
        rows = checkpoints([.1,.2,.3])
        rows[2]["snapshot_json"]["rule_catalog"] = {"catalog_sha256":"different"}
        self.assertEqual(len(build_evolution(OP,rows)["series"]),2)

    def test_engine_version_does_not_split_identical_formula(self):
        rows=checkpoints([.1,.2,.3])
        for i,row in enumerate(rows):
            row["snapshot_json"]["version_contract"]={"engine_version":f"v{i}"}
        self.assertEqual(len(build_evolution(OP,rows)["series"]),1)

    def test_missing_and_blocked_are_not_neutral_numeric_values(self):
        rows=checkpoints([.1,.2,.3])
        rows[1]["snapshot_json"]["stage_rule_traces"]["intraday_short"][0]["status"]="blocked"
        s=build_evolution(OP,rows)["series"][0]
        self.assertEqual(s["controls"],2)
        self.assertEqual(s["continuity_resets"],1)
        self.assertFalse(s["latest"]["three_distinct_readings_same_sign"])

    def test_roundtrip_determinism_and_no_raw_series_in_storage(self):
        rows=checkpoints([.1,.2,.3])
        original=copy.deepcopy(rows)
        report=build_evolution(OP,rows)
        self.assertEqual(unpack(pack(report)),report)
        self.assertEqual(rows,original)
        self.assertNotIn("points",report["series"][0])
        self.assertLess(len(pack(report)),4096)
        self.assertEqual(report["semantics"]["production_effect"],"none")

    def test_comparison_excludes_future_wrong_pair_and_overlapping_episodes(self):
        prior=build_evolution(OP,checkpoints([.1,.2,.3,.4]))
        current={**prior,"operation_id":9,"started_at":(BASE+timedelta(days=10)).isoformat()}
        future={**prior,"closed_at":(BASE+timedelta(days=11)).isoformat()}
        other={**prior,"symbol":"ETHUSDT"}
        result=compare_episodes(current,[prior,dict(prior),future,other])
        self.assertEqual(result["eligible_prior_episodes"],1)
        self.assertTrue(result["comparisons"])
        self.assertTrue(all(c["prior_independent_episodes"]==1 for c in result["comparisons"]))

    def test_corrupt_storage_is_rejected(self):
        import json
        payload=json.loads(pack(build_evolution(OP,checkpoints([.1,.2]))))
        payload["sha256"]="bad"
        with self.assertRaises(ValueError):
            unpack(payload)

    def test_continuous_acceleration_uses_elapsed_time(self):
        d=state([{"time":0,"value":0},{"time":3600,"value":1},{"time":7200,"value":3}])
        self.assertEqual(d["acceleration_per_hour2"],1)

    def test_4h_endpoint_allows_bounded_cumulative_scheduler_drift(self):
        rows=checkpoints([.1+i*.01 for i in range(13)],times=[i*(20+1/6) for i in range(13)])
        outcome=build_evolution(OP,rows)["series"][0]["forward"]["240"]
        self.assertEqual(outcome["n"],1)
        self.assertAlmostEqual(outcome["actual_minutes_max"],242)

    def test_missing_traces_or_controls_never_claim_complete_evaluation(self):
        with self.assertRaisesRegex(ValueError,"no_checkpoints"):
            build_evolution(OP,[])
        rows=checkpoints([.1])
        rows[0]["snapshot_json"]={}
        with self.assertRaisesRegex(ValueError,"missing_rule_traces"):
            build_evolution(OP,rows)

    def test_raw_components_retain_evolution_without_becoming_forecast_signals(self):
        rows=checkpoints([.1,.2,.3])
        for i,row in enumerate(rows):
            row["snapshot_json"]["stage_rule_traces"]["intraday_short"][0]["outputs"]["sample_counter"]=i+1
        report=build_evolution(OP,rows)
        sample=next(s for s in report["series"] if s["metric"]=="sample_counter")
        self.assertEqual(sample["latest"]["direction"],"rising")
        self.assertEqual(sample["forward"],{})
        self.assertEqual(unpack(pack(report)),report)

    def test_public_view_omits_storage_membership_and_keeps_results(self):
        report=build_evolution(OP,checkpoints([.1,.2,.3]))
        view=report_view(report,rule_id=RULE)
        self.assertNotIn("_sample_ids",canonical(view))
        self.assertEqual(view["series"][0]["forward"]["20"]["n"],2)

    def test_storage_budget_is_hard_not_automatically_increased(self):
        from unittest.mock import patch
        report=build_evolution(OP,checkpoints([.1,.2,.3]))
        with patch("observation_numeric_evolution.MAX_PAYLOAD_BYTES",100):
            with self.assertRaisesRegex(ValueError,"storage_budget_exceeded"):
                pack(report)
        self.assertEqual(MAX_PAYLOAD_BYTES,65536)

    def test_factored_storage_restores_exact_nonrounded_values(self):
        values=[.1234567890123456,.9876543210123456,.3141592653589793]
        report=build_evolution(OP,checkpoints(values))
        restored=unpack(pack(report))
        self.assertEqual(canonical(restored),canonical(report))
        self.assertEqual(restored["series"][0]["last"],values[-1])


class StoreTests(unittest.TestCase):
    class FakeDb:
        def __init__(self):
            self.row=None
            self.writes=0
        def execute(self,sql,params):
            if "INSERT INTO" in sql:
                self.writes+=1
                self.row=dict(status=params[8],checkpoint_count=params[7],
                              input_sha256=params[9],payload_bytes=params[11])
            return self
        def fetchone(self):
            return self.row

    def source(self):
        rows=checkpoints([.1,.2,.3])
        for row in rows:
            row.update(contract_quality="exact",formal_learning_eligible=True)
        return {**OP,"status":"CLOSED"},rows

    def test_retry_does_not_add_another_record_and_changed_facts_are_not_hidden(self):
        db=self.FakeDb(); op,rows=self.source()
        first=persist_evolution(db,op,rows)
        second=persist_evolution(db,op,rows)
        self.assertEqual(first["status"],"complete")
        self.assertTrue(second["reused"])
        self.assertEqual(db.writes,1)
        rows[0]["market_price"]+=1
        with self.assertRaisesRegex(ValueError,"source_changed_requires_review"):
            persist_evolution(db,op,rows)

    def test_inexact_source_and_size_failure_produce_small_explicit_blocked_record(self):
        from unittest.mock import patch
        db=self.FakeDb(); op,rows=self.source()
        rows[1]["contract_quality"]="reconstructed"
        self.assertEqual(persist_evolution(db,op,rows)["status"],"blocked")
        self.assertLess(db.row["payload_bytes"],1024)
        db=self.FakeDb(); op,rows=self.source()
        with patch("observation_evolution_store.pack",side_effect=ValueError("too_large")):
            self.assertEqual(persist_evolution(db,op,rows)["status"],"blocked")

    def test_hash_ignores_unconsumed_snapshot_fields_but_not_eligibility(self):
        op,rows=self.source()
        before=source_identity(op,rows,20)
        rows[0]["snapshot_json"]["unrelated_metadata"]="full source snapshot"
        self.assertEqual(source_identity(op,rows,20),before)
        rows[0]["formal_learning_eligible"]=False
        self.assertNotEqual(source_identity(op,rows,20),before)

    def test_corrupt_evidence_is_recorded_without_stopping_worker_learning(self):
        op,rows=self.source()
        rows[0]["snapshot_json"]["stage_rule_traces"]={"encoding":"broken"}
        result=persist_evolution(self.FakeDb(),op,rows)
        self.assertEqual(result["status"],"blocked")
        self.assertLess(result["payload_bytes"],1024)

    def test_open_operation_cannot_persist_terminal_learning(self):
        op,rows=self.source()
        with self.assertRaisesRegex(ValueError,"closed_operation_required"):
            persist_evolution(self.FakeDb(),{**op,"status":"OPEN"},rows)


class ApiTests(unittest.TestCase):
    def test_stored_report_does_not_reload_source_snapshots(self):
        from contextlib import nullcontext
        from unittest.mock import patch, MagicMock
        from app import get_operation_observation_rule_evolution
        report=build_evolution(OP,checkpoints([.1,.2,.3]))
        with patch("app.current_user",return_value={"id":1,"username":"mauriciomc"}), \
             patch("app.connect",return_value=nullcontext(MagicMock())), \
             patch("app._observation_operation",return_value={"status":"CLOSED"}), \
             patch("observation_evolution_store.stored_report",return_value=report), \
             patch("observation_evolution_store.persisted_status",return_value={"status":"complete"}), \
             patch("observation_evolution_store.load_episode") as loader, \
             patch("observation_evolution_store.historical_comparison") as compare:
            result=get_operation_observation_rule_evolution(1,rule_id=RULE,session_token="test")
        self.assertEqual(result["checkpoint_count"],3)
        loader.assert_not_called()
        compare.assert_not_called()

    def test_non_operator_cannot_query_learning(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from app import get_operation_observation_rule_evolution
        with patch("app.current_user",return_value={"id":2,"username":"other"}), \
             patch("app.connect") as connect:
            with self.assertRaises(HTTPException) as err:
                get_operation_observation_rule_evolution(1,session_token="test")
        self.assertEqual(err.exception.status_code,403)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
