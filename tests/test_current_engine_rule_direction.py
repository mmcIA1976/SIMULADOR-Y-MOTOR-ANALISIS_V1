from __future__ import annotations

import unittest

from current_engine_rule_direction import (
    all_closed_summary, compact_closed_report, current_engine_summary,
    load_all_closed_cases, score_current_signal, score_current_trace_case,
)


class CurrentEngineRuleDirectionTests(unittest.TestCase):
    def test_all_closed_audit_keeps_versions_and_exclusions_explicit(self):
        base = {"operation_id": 1,"recommendation_id": 10,"symbol": "BTCUSDT",
                "side": "long","time_horizon": "intraday_short",
                "analysis_at": "2026-09-01T00:00:00Z",
                "evaluation_expires_at": "2026-09-01T04:00:00Z",
                "closed_at": "2026-09-01T01:00:00Z","plan_result": "plan_success",
                "traces": [{"rule_id": "M4-RULE-PATH-STRUCTURE-001",
                            "outputs": {"directional_path_efficiency_h": 0.2}}]}
        report = all_closed_summary([
            {**base,"engine_version": "older"},
            {**base,"operation_id": 2,"engine_version": "newer"},
            {**base,"operation_id": 3,"traces": []},
            {**base,"operation_id": 4,"recommendation_id": None},
        ])
        self.assertEqual(report["closed_operations_inspected"],4)
        self.assertEqual(report["operations_with_any_directional_score"],2)
        self.assertEqual(len(report["version_reports"]),2)
        self.assertEqual(report["exclusion_reasons"],
                         {"no_preserved_rule_traces": 1,"no_linked_pretrade_analysis": 1})
        digest = compact_closed_report(report)
        self.assertEqual(len(digest["rule_bands"]),2)
        self.assertEqual(digest["excluded_operation_ids"]["no_preserved_rule_traces"],[3])

    def test_all_closed_loader_pages_without_silent_limit_or_duplicates(self):
        class Cursor:
            def __init__(self,rows): self.rows=rows
            def fetchone(self): return self.rows[0]
            def fetchall(self): return self.rows
        class Session:
            def __init__(self): self.pages=[]
            def execute(self,query,params=None):
                if params is None: return Cursor([{"operations": 5,"max_id": 9}])
                after,maximum,size,_ = params
                self.pages.append(after)
                return Cursor([{"operation_id": i} for i in (1,3,4,8,9)
                               if after < i <= maximum][:size])
        session=Session()
        rows,metadata=load_all_closed_cases(session,batch_size=2)
        self.assertEqual([row["operation_id"] for row in rows],[1,3,4,8,9])
        self.assertEqual(session.pages,[0,3,8])
        self.assertTrue(metadata["complete_coverage"])
        with self.assertRaisesRegex(ValueError,"transfer_budget_exceeded"):
            load_all_closed_cases(Session(),batch_size=2,max_bytes=1)

    def test_projected_dotted_inputs_keep_same_rule_score(self):
        base={"side": "short","time_horizon": "intraday_short"}
        metadata={"rule_id": "LIB-CAND-ORDERBOOK-IMBALANCE-001","status": "evaluated_shadow"}
        full={**base,"traces": [{**metadata,"outputs": {
            "current_snapshot": {"side_adjusted_imbalances": {"top_20": 0.2}},
            "persistence": {"top_20": {"side_adjusted_mean": 0.1}},
            "executed_flow": {"side_adjusted_executed_flow_imbalance": 0.3}}}]}
        projected={**base,"traces": [{**metadata,"outputs": {
            "current_snapshot.side_adjusted_imbalances.top_20": 0.2,
            "persistence.top_20.side_adjusted_mean": 0.1,
            "executed_flow.side_adjusted_executed_flow_imbalance": 0.3}}]}
        self.assertEqual(score_current_trace_case(full)[0]["directional_score"],
                         score_current_trace_case(projected)[0]["directional_score"])

    def test_long_and_short_translate_support_to_native_market_direction(self):
        signal = {
            "rule_id": "M4-RULE-PATH-STRUCTURE-001", "score": 0.12,
            "formula_role": "whole_rule", "formula_outputs": ["directional_path_efficiency_h"],
        }
        long = score_current_signal(signal, side="long")
        short = score_current_signal(signal, side="short")
        self.assertEqual(long["trade_side_score"], 3)
        self.assertEqual(long["directional_score"], 3)
        self.assertEqual(short["directional_score"], -3)
        self.assertNotIn("formula_outputs", long)
        self.assertEqual(long["formula_output_count"], 1)

    def test_activity_and_levels_are_not_fabricated_as_bullish(self):
        for rule, metric, kind in (
            ("LIB-CAND-RELATIVE-VOLUME-001", "volume_midrank_60", "volume_activity"),
            ("M4-RULE-VOLATILITY-RANK-001", "volatility_percentile_60", "volatility_activity"),
        ):
            row = score_current_signal({
                "rule_id": rule, "score": None,
                "metrics": [{"key": metric, "value": 0.9}],
            }, side="long")
            self.assertIsNone(row["directional_score"])
            self.assertEqual(row["context_score"], 4)
            self.assertEqual(row["context_kind"], kind)
        fib = score_current_signal({
            "rule_id": "LIB-CAND-FIBONACCI-DISTANCE-001", "score": None,
            "metrics": [
                {"key": "nearest_to_take_profit.absolute_distance_sigma_horizon", "value": 0.2},
                {"key": "nearest_to_stop_loss.absolute_distance_sigma_horizon", "value": 0.8},
            ],
        }, side="long")
        self.assertIsNone(fib["directional_score"])
        self.assertGreater(fib["context_score"], 0)

    def test_absorption_vector_without_absorption_formula_stays_missing(self):
        row = score_current_signal({
            "rule_id": "LIB-CAND-ABSORPTION-001", "score": None,
            "formula_outputs": ["absorption_vector.aggressor_imbalance"],
        }, side="long")
        self.assertIsNone(row["directional_score"])
        self.assertEqual(row["status"], "missing_or_unsupported_formula")

    def test_trace_reader_uses_executed_current_rules_only(self):
        case = {
            "side": "long", "time_horizon": "intraday_short",
            "traces": [{
                "rule_id": "M4-RULE-PATH-STRUCTURE-001", "status": "evaluated",
                "probability_effect": "active", "outputs": {"directional_path_efficiency_h": 0.2},
            }],
        }
        rows = score_current_trace_case(case)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["directional_score"], 5)

    def test_late_close_is_not_a_verified_within_horizon_tp(self):
        case = {
            "operation_id": 700, "symbol": "BTCUSDT", "side": "long",
            "time_horizon": "intraday_short", "analysis_at": "2026-09-10T00:00:00+00:00",
            "evaluation_expires_at": "2026-09-10T04:00:00+00:00",
            "closed_at": "2026-09-10T07:00:00+00:00", "plan_result": "plan_success",
            "traces": [],
        }
        result = current_engine_summary([case])["operations"][0]
        self.assertIsNone(result["outcome"])
        self.assertEqual(result["fixed_horizon_outcome_status"], "late_or_indirect_label_not_verified")

    def test_score_band_includes_reconstructed_no_touch(self):
        trace = [{
            "rule_id": "M4-RULE-PATH-STRUCTURE-001", "status": "evaluated",
            "probability_effect": "active", "outputs": {"directional_path_efficiency_h": 0.2},
        }]
        first = {
            "operation_id": 701, "symbol": "BTCUSDT", "side": "long",
            "time_horizon": "intraday_short", "analysis_at": "2026-09-10T00:00:00+00:00",
            "evaluation_expires_at": "2026-09-10T04:00:00+00:00",
            "closed_at": "2026-09-10T01:00:00+00:00", "plan_result": "plan_success",
            "traces": trace,
        }
        second = {
            **first, "operation_id": 702, "analysis_at": "2026-09-11T00:00:00+00:00",
            "evaluation_expires_at": "2026-09-11T04:00:00+00:00",
            "closed_at": "2026-09-11T07:00:00+00:00",
            "evidence_status": "complete", "evidence_quality": "complete_1m_with_boundary_approximation",
            "evidence_coverage_ratio": 1.0,
            "evidence_start_at": "2026-09-11T00:00:05+00:00",
            "evidence_end_at": "2026-09-11T07:00:00+00:00",
            "first_plan_touch_at": "2026-09-11T05:00:00+00:00",
            "reconstructed_plan_result": "plan_success",
        }
        report = current_engine_summary([first, second])
        row = next(item for item in report["rule_formula_summaries"]
                   if item["rule_id"] == "M4-RULE-PATH-STRUCTURE-001")
        band = row["outcome_by_score_band"]["strong_positive"]
        self.assertEqual(band["episodes"], 2)
        self.assertEqual(band["tp_first_within_horizon"], 0.5)
        self.assertEqual(band["neither_barrier_before_expiry"], 0.5)


if __name__ == "__main__":
    unittest.main()
