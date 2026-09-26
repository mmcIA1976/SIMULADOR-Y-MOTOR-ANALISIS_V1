from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from current_engine_rule_direction import (
    compact_measurement_report, load_compact_measurement_cases,
    score_compact_measurements, screen_current_incremental,
)
from observational_direction_study import OUTCOMES

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
ABS = "LIB-CAND-ABSORPTION-001"
FUNDING = "M4-RULE-FUNDING-STATE-001"


def measurement_case(index=0, *, source="closed_operation", version="settled-funding-v1", rate=.00005):
    at = BASE+timedelta(days=index)
    return {"id":index+1,"operation_id":index+1,"symbol":"BTCUSDT","side":"long",
        "source_kind":source,"engine_version":"v0.11","time_horizon":"intraday_short",
        "analysis_at":at.isoformat(),"evaluation_expires_at":(at+timedelta(hours=4)).isoformat(),
        "episode_key":f"episode-{index}","closed_at":(at+timedelta(hours=1)).isoformat(),
        "plan_result":"plan_success","tp_probability":.4,"sl_probability":.4,"range_probability":.2,
        "signals_json": {FUNDING:{"value":None,"measurement":{
            "rule_version":version,"contract_version":"positioning-measurement-v1",
            "status":"evaluated_shadow","numeric_inputs":{"last_settled_funding_rate":rate,
                "settled_funding_rate_per_hour":rate/8,"observed_interval_hours":8}}}}}


class CompactMeasurementEvaluationTests(unittest.TestCase):
    def test_sources_versions_and_parent_episode_are_not_pooled(self):
        entry = measurement_case()
        control = {**measurement_case(1,source="operation_observation_checkpoint"),
            "operation_id":entry["operation_id"],"episode_key":"parent-episode",
            "exact_outcome_label":OUTCOMES[1]}
        report = compact_measurement_report([entry,control,{**control,"id":3}],include_cases=True)
        self.assertEqual(len(report["groups"]),2)
        controls = next(g for g in report["groups"] if g["source_kind"] != "closed_operation")
        self.assertEqual(controls["episode_buckets"],1)
        self.assertEqual(controls["rule_formula_summaries"][0]["independent_episodes"],1)
        self.assertEqual(controls["incremental_validation"],[])
        self.assertEqual(controls["operations"][0]["outcome"],OUTCOMES[1])
        entry_other_formula = measurement_case(2,version="another-funding-formula")
        group = compact_measurement_report([entry,entry_other_formula])["groups"][0]
        self.assertEqual(len(group["rule_formula_summaries"]),2)

    def test_control_without_own_counterfactual_does_not_inherit_parent_tp(self):
        report = compact_measurement_report([measurement_case(source="operation_observation_checkpoint")],include_cases=True)
        control = report["groups"][0]["operations"][0]
        self.assertIsNone(control["outcome"])
        self.assertEqual(control["fixed_horizon_outcome_status"],"checkpoint_exact_counterfactual_missing")

    def test_source_contract_change_splits_same_named_formula(self):
        first,second = measurement_case(),measurement_case(1)
        second["signals_json"][FUNDING]["measurement"]["contract_version"]="different-source-contract"
        report = compact_measurement_report([first,second])["groups"][0]
        self.assertEqual(len(report["rule_formula_summaries"]),2)

    def test_score_raw_values_remain_visible_below_integer_resolution(self):
        report = compact_measurement_report([measurement_case(rate=.000001)])["groups"][0]
        formula = report["rule_formula_summaries"][0]
        self.assertEqual(formula["integer_zero_readings"],1)
        self.assertLess(formula["raw_value_range"][0],0)
        self.assertEqual(formula["numeric_input_summary"]["last_settled_funding_rate"]["min"],.000001)

    def test_blocked_source_with_numeric_leftovers_cannot_score(self):
        case = measurement_case()
        case["signals_json"][FUNDING]["measurement"]["status"] = "blocked"
        score = score_compact_measurements(case)[0]
        self.assertIsNone(score["directional_score"])
        self.assertIsNone(score["raw_support_value"])

    def test_absorption_zero_diagnostic_separates_gating_and_rounding(self):
        from observational_measurement_scores import absorption_proxy
        inputs = {"ATI_H":.1,"relative_horizon_volume":1,"horizon_displacement_atr":2,"flow_opposing_wick_ratio":.1}
        self.assertEqual(absorption_proxy(inputs,side="long")["zero_cause"],"displacement_gate")
        low = absorption_proxy({**inputs,"horizon_displacement_atr":.2},side="long")
        self.assertEqual(low["zero_cause"],"integer_rounding")
        self.assertLess(low["raw_trade_support"],0)

    def test_temporal_purge_removes_training_labels_that_overlap_test(self):
        groups = {}
        for i in range(50):
            at = BASE+timedelta(days=i)
            expiry = at+timedelta(hours=4)
            if i == 29:
                expiry = BASE+timedelta(days=32)
            groups[("BTCUSDT","intraday_short",str(i))] = [{
                "analysis_at":at.isoformat(),"evaluation_expires_at":expiry.isoformat(),
                "outcome":OUTCOMES[i%3],"probabilities":dict(zip(OUTCOMES,(.4,.4,.2))),
                "scores":[{"rule_id":FUNDING,"formula_role":"new","trade_side_score":(-1)**i}]}]
        result = screen_current_incremental(groups,[{"score_kind":"directional_hypothesis",
            "symbol":"BTCUSDT","time_horizon":"intraday_short","rule_id":FUNDING,"formula_role":"new"}])[0]
        self.assertEqual(result["purged_training_episodes"],1)
        self.assertEqual(result["train_episodes"],29)
        self.assertEqual(result["test_episodes"],20)
        self.assertEqual(result["status"],"out_of_sample_screening_only_not_validated")
        for rows in groups.values(): rows[0]["scores"][0]["trade_side_score"] = 0
        result = screen_current_incremental(groups,[{"score_kind":"directional_hypothesis",
            "symbol":"BTCUSDT","time_horizon":"intraday_short","rule_id":FUNDING,"formula_role":"new"}])[0]
        self.assertEqual(result["status"],"no_training_score_variation")

    def test_keyset_loader_budget_and_coverage_fail_closed(self):
        class Cursor:
            def __init__(self,rows): self.rows=rows
            def fetchone(self): return self.rows[0]
            def fetchall(self): return self.rows
        class Session:
            def execute(self,sql,params):
                if "SELECT id FROM observational_learning_cohorts" in sql:
                    return Cursor([{"id":1}])
                if "count(*) AS cases" in sql:
                    return Cursor([{"cases":3,"max_id":8}])
                _,after,maximum,size = params
                return Cursor([{"id":i,"signals_json":{}} for i in (1,3,8) if after<i<=maximum][:size])
        rows,meta = load_compact_measurement_cases(Session(),batch_size=2)
        self.assertEqual([r["id"] for r in rows],[1,3,8])
        self.assertEqual(meta["batches"],2)
        self.assertFalse(meta["recommendation_snapshots_downloaded"])
        with self.assertRaisesRegex(ValueError,"transfer_budget_exceeded"):
            load_compact_measurement_cases(Session(),max_bytes=1)

    def test_no_new_contracts_is_reported_without_synthetic_learning(self):
        report = compact_measurement_report([])
        self.assertEqual(report["status"],"no_new_measurement_contracts_recorded")
        self.assertEqual(report["groups"],[])
        self.assertFalse(report["database_writes"])


if __name__ == "__main__":
    unittest.main()
