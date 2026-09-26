from __future__ import annotations

import unittest
from pathlib import Path

from observational_learning_base import (
    PROBABILITY_WEIGHT,
    RETAINED_RULE_HORIZONS,
    current_snapshot_rule_values,
    _compact_progress_metric,
    observation_checkpoint_partition,
    payload_sha256,
    prospective_episode_key,
    persist_closed_observational_case,
    fixed_horizon_outcome_from_evidence,
)
from audit_final_rule_utility import stored_counterfactual_outcome


ROOT = Path(__file__).resolve().parents[1]


class ObservationalLearningBaseTests(unittest.TestCase):
    def test_reconstructs_no_touch_only_from_complete_1m_horizon_evidence(self):
        base = dict(
            recorded_outcome="tp_first_within_horizon", plan_result="plan_success",
            analysis_at="2026-09-10T00:00:00+00:00",
            evaluation_expires_at="2026-09-10T04:00:00+00:00",
            closed_at="2026-09-10T07:00:00+00:00",
            evidence_status="complete", evidence_quality="complete_1m_with_boundary_approximation",
            evidence_coverage_ratio=1.0,
            evidence_start_at="2026-09-10T00:00:08+00:00",
            evidence_end_at="2026-09-10T07:00:00+00:00",
            first_plan_touch_at="2026-09-10T04:01:30+00:00",
            reconstructed_plan_result="plan_success",
        )
        self.assertEqual(fixed_horizon_outcome_from_evidence(**base),
                         ("neither_barrier_before_expiry", "reconstructed_1m_no_touch"))
        self.assertEqual(fixed_horizon_outcome_from_evidence(
            **{**base, "first_plan_touch_at": "2026-09-10T04:00:30+00:00"}),
            (None, "boundary_touch_ambiguous"))
        self.assertEqual(fixed_horizon_outcome_from_evidence(
            **{**base, "evidence_start_at": "2026-09-10T00:01:00+00:00"}),
            (None, "late_or_indirect_label_not_verified"))

    def test_late_tp_without_exact_horizon_evidence_is_not_persisted(self):
        class Cursor:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class FakeDb:
            def __init__(self):
                self.inserted = False

            def execute(self, sql, _params=()):
                if "SELECT id, historical_cutoff_at" in sql:
                    return Cursor({"id": 1, "historical_cutoff_at": "2026-09-09T00:00:00+00:00"})
                if "SELECT\n            o.id AS operation_id" in sql:
                    return Cursor({
                        "operation_id": 700, "symbol": "BTCUSDT", "side": "long",
                        "time_horizon": "intraday_short", "closed_at": "2026-09-10T07:00:00+00:00",
                        "recommendation_id": 10,
                        "snapshot_json": ('{"analysis_at":"2026-09-10T00:00:00+00:00",'
                                          '"evaluation_expires_at":"2026-09-10T04:00:00+00:00"}'),
                        "plan_result": "plan_success", "tp_probability": 0.4,
                        "sl_probability": 0.4, "range_probability": 0.2,
                    })
                if "FROM recommendation_counterfactual_evaluations" in sql:
                    return Cursor(None)
                if "INSERT INTO observational_learning_cases" in sql:
                    self.inserted = True
                raise AssertionError(f"unexpected query: {sql[:80]}")

        db = FakeDb()
        self.assertFalse(persist_closed_observational_case(db, 700))
        self.assertFalse(db.inserted)

    def test_retained_decision_is_fourteen_rules_and_seventeen_horizon_contracts(self):
        self.assertEqual(len(RETAINED_RULE_HORIZONS), 14)
        self.assertEqual(sum(map(len, RETAINED_RULE_HORIZONS.values())), 17)
        self.assertEqual(PROBABILITY_WEIGHT, 0.0)

    def test_current_snapshot_extracts_only_frozen_variable_for_selected_horizon(self):
        snapshot = {
            "stage_rule_traces": {
                "intraday_short": [
                    {
                        "rule_id": "LIB-CAND-CVD-SLOPE-001",
                        "status": "evaluated_shadow",
                        "outputs": {
                            "side_adjusted_normalized_cvd_slope": -0.9,
                        },
                    }
                ],
                "intraday_wide": [
                    {
                        "rule_id": "LIB-CAND-CVD-SLOPE-001",
                        "status": "evaluated_shadow",
                        "trace_sha256": "trace-wide",
                        "outputs": {
                            "side_adjusted_normalized_cvd_slope": 0.35,
                            "terminal_cvd": 9_999_999,
                        },
                    }
                ],
            }
        }
        values, missing = current_snapshot_rule_values(
            snapshot,
            side="long",
            time_horizon="intraday_wide",
            baseline_specs=[
                {
                    "rule_id": "LIB-CAND-CVD-SLOPE-001",
                    "selected_variable": "side_adjusted_normalized_cvd_slope",
                }
            ],
        )
        self.assertEqual(missing, [])
        self.assertEqual(
            values["LIB-CAND-CVD-SLOPE-001"]["value"],
            0.35,
        )
        self.assertNotIn(
            "terminal_cvd",
            values["LIB-CAND-CVD-SLOPE-001"]["available_variables"],
        )

    def test_changed_or_missing_formula_variable_is_not_silently_proxied(self):
        snapshot = {
            "stage_rule_traces": {
                "intraday_wide": [
                    {
                        "rule_id": "LIB-CAND-CVD-SLOPE-001",
                        "status": "evaluated_shadow",
                        "outputs": {"different_future_variable": 0.9},
                    }
                ]
            }
        }
        values, missing = current_snapshot_rule_values(
            snapshot,
            side="long",
            time_horizon="intraday_wide",
            baseline_specs=[
                {
                    "rule_id": "LIB-CAND-CVD-SLOPE-001",
                    "selected_variable": "side_adjusted_normalized_cvd_slope",
                }
            ],
        )
        self.assertEqual(values, {})
        self.assertEqual(missing, ["LIB-CAND-CVD-SLOPE-001"])

    def test_case_identity_hash_is_deterministic(self):
        left = {"source": "operation:404", "outcome": "tp", "signal": 0.3}
        right = {"signal": 0.3, "outcome": "tp", "source": "operation:404"}
        self.assertEqual(payload_sha256(left), payload_sha256(right))

    def test_prospective_episode_key_groups_same_symbol_horizon_bucket(self):
        first = prospective_episode_key(
            symbol="ethusdt",
            time_horizon="intraday_short",
            analysis_at="2026-09-10T01:00:00+00:00",
        )
        same_bucket = prospective_episode_key(
            symbol="ETHUSDT",
            time_horizon="intraday_short",
            analysis_at="2026-09-10T02:30:00+00:00",
        )
        next_bucket = prospective_episode_key(
            symbol="ETHUSDT",
            time_horizon="intraday_short",
            analysis_at="2026-09-10T05:00:00+00:00",
        )
        self.assertEqual(first, same_bucket)
        self.assertNotEqual(first, next_bucket)

    def test_cutoff_straddling_observation_is_prospective(self):
        self.assertEqual(
            observation_checkpoint_partition(
                analysis_at="2026-09-09T17:00:00+00:00",
                operation_closed_at="2026-09-10T12:15:00+00:00",
                historical_cutoff_at="2026-09-09T17:12:19+00:00",
            ),
            "prospective",
        )

    def test_resolved_pre_cutoff_observation_is_not_appended_again(self):
        self.assertIsNone(
            observation_checkpoint_partition(
                analysis_at="2026-09-09T15:00:00+00:00",
                operation_closed_at="2026-09-09T15:05:00+00:00",
                historical_cutoff_at="2026-09-09T17:12:19+00:00",
            )
        )

    def test_compact_progress_counts_overlapping_cases_as_one_episode(self):
        metric = _compact_progress_metric(
            [
                {
                    "episode_key": "same",
                    "outcome_label": "tp_first_within_horizon",
                    "value": 0.8,
                },
                {
                    "episode_key": "same",
                    "outcome_label": "sl_first_within_horizon",
                    "value": 0.4,
                },
                {
                    "episode_key": "different",
                    "outcome_label": "tp_first_within_horizon",
                    "value": 0.9,
                },
            ],
            "directional",
            1,
        )
        self.assertEqual(metric["raw_cases"], 3)
        self.assertEqual(metric["effective_episodes"], 2)
        self.assertEqual(metric["effective_positive_mass"], 1.5)

    def test_migration_keeps_learning_tables_internal_and_append_only(self):
        migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20260909_observational_learning_base.sql"
        ).read_text(encoding="utf-8")
        for table in (
            "observational_learning_cohorts",
            "observational_rule_baselines",
            "observational_learning_cases",
        ):
            self.assertIn(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY", migration)
            self.assertIn(table, migration)
        self.assertIn("observational_learning_cases_append_only", migration)
        self.assertIn("probability_weight = 0", migration)

    def test_closed_case_loader_requires_opening_pre_trade_analysis(self):
        source = (ROOT / "observational_learning_base.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("AND r2.analysis_type = 'pre_trade'"), 2)

    def test_terminal_observation_outcome_is_formally_resolved(self):
        outcome = stored_counterfactual_outcome(
            {
                "evaluation_status": "evaluated",
                "outcome_status": "resolved_from_operation_terminal_event",
                "outcome_label": "sl_first_within_horizon",
            }
        )
        self.assertEqual(outcome["status"], "resolved")
        self.assertEqual(
            outcome["recorded_status"],
            "resolved_from_operation_terminal_event",
        )

    def test_observation_finalizer_appends_compact_checkpoint_cases(self):
        source = (ROOT / "operation_observation_learning.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("persist_observation_checkpoint_cases", source)


if __name__ == "__main__":
    unittest.main()
