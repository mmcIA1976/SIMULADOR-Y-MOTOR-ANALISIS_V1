from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from observational_direction_study import (
    SCORE_VERSION,
    build_study,
    consensus_from_scores,
    fit_outcome_blind_scales,
    score_case,
)
from observational_learning_base import FROZEN_SIGNAL_VARIABLES, current_snapshot_rule_values


def case(*, partition="prospective", source="closed_operation", episode="episode-1",
         side="long", horizon="intraday_wide", outcome="tp_first_within_horizon",
         signals=None):
    return {
        "cohort_partition": partition,
        "source_kind": source,
        "source_reference": f"{source}:{episode}",
        "episode_key": episode,
        "side": side,
        "time_horizon": horizon,
        "outcome_label": outcome,
        "signals_json": json.dumps({name: {"value": value, "variable": FROZEN_SIGNAL_VARIABLES[name]}
                                   for name, value in (signals or {}).items()}),
    }


class ObservationalDirectionStudyTests(unittest.TestCase):
    def test_direction_is_native_bullish_or_bearish_and_missing_is_not_zero(self):
        rule = "LIB-CAND-CVD-SLOPE-001"
        scales = {(rule, "intraday_wide"): {"neutral": 0.0, "scale": 0.1}}
        long = score_case(case(signals={rule: 0.08}), scales)[rule]
        short = score_case(case(side="short", signals={rule: 0.08}), scales)[rule]
        missing = score_case(case(), scales)[rule]
        self.assertEqual(long["directional_score"], 4)
        self.assertEqual(short["directional_score"], -4)
        self.assertEqual(short["trade_side_score"], 4)
        self.assertIsNone(missing["directional_score"])
        self.assertEqual(missing["status"], "missing_signal")

    def test_volume_and_oi_do_not_invent_a_direction(self):
        volume = "LIB-CAND-RELATIVE-VOLUME-001"
        oi = "M4-RULE-OPEN-INTEREST-CHANGE-001"
        scales = {
            (volume, "intraday_wide"): {"neutral": 0.0, "scale": 1.0},
            (oi, "intraday_wide"): {"neutral": 0.0, "scale": 1.0},
        }
        scores = score_case(case(signals={volume: 0.8, oi: 0.8}), scales)
        for name in (volume, oi):
            self.assertIsNone(scores[name]["directional_score"])
            self.assertEqual(scores[name]["activity_score"], 4)
            self.assertEqual(scores[name]["status"], "activity_only_not_directional")

    def test_fibonacci_proximity_is_context_not_bullish_or_bearish(self):
        rule = "LIB-CAND-FIBONACCI-DISTANCE-001"
        scales = {(rule, "short_swing"): {"neutral": 0.0, "scale": 1.0}}
        for side in ("long", "short"):
            score = score_case(case(side=side, horizon="short_swing", signals={rule: 0.8}), scales)[rule]
            self.assertIsNone(score["directional_score"])
            self.assertIsNone(score["trade_side_score"])
            self.assertEqual(score["context_score"], 4)
            self.assertEqual(score["status"], "level_asymmetry_not_directional")

    def test_prior_extreme_is_adverse_to_target_not_bullish(self):
        rule = "M4-RULE-PRIOR-EXTREMA-001"
        scales = {(rule, "short_swing"): {"neutral": 0.0, "scale": 1.0}}
        long = score_case(case(horizon="short_swing", signals={rule: 1.0}), scales)[rule]
        short = score_case(case(horizon="short_swing", side="short", signals={rule: 1.0}), scales)[rule]
        self.assertEqual(long["trade_side_score"], -5)
        self.assertEqual(long["directional_score"], -5)
        self.assertEqual(short["directional_score"], 5)

    def test_consensus_excludes_alias_and_movement_only_and_detects_conflict(self):
        scores = {
            "aggressor": {"duplicate_of": None, "directional_score": 4},
            "absorption": {"duplicate_of": "aggressor", "directional_score": 4},
            "cvd": {"duplicate_of": None, "directional_score": -2},
            "volume": {"duplicate_of": None, "directional_score": None},
        }
        vote = consensus_from_scores(scores)
        self.assertEqual(vote["evaluated_independent_rules"], 2)
        self.assertEqual((vote["bullish_rules"], vote["bearish_rules"]), (1, 1))
        self.assertTrue(vote["conflicting_signals"])

    def test_changed_variable_is_not_scored_as_if_formula_were_unchanged(self):
        rule = "LIB-CAND-CVD-SLOPE-001"
        row = case(signals={rule: 0.08})
        signals = json.loads(row["signals_json"])
        signals[rule]["variable"] = "different_formula"
        row["signals_json"] = json.dumps(signals)
        score = score_case(row, {(rule, "intraday_wide"): {"neutral": 0.0, "scale": 0.1}})[rule]
        self.assertIsNone(score["directional_score"])
        self.assertEqual(score["status"], "variable_contract_mismatch")

    def test_historical_scale_uses_episode_means_not_result_labels_or_control_count(self):
        rule = "LIB-CAND-CVD-SLOPE-001"
        rows = [case(partition="historical", episode=f"hist-{i}", signals={rule: i / 100})
                for i in range(1, 11)]
        original = fit_outcome_blind_scales(rows)[(rule, "intraday_wide")]
        rows[0]["outcome_label"] = "sl_first_within_horizon"
        rows.extend([case(partition="historical", episode="hist-1", signals={rule: 0.01})
                     for _ in range(30)])
        repeated = fit_outcome_blind_scales(rows)[(rule, "intraday_wide")]
        self.assertEqual(original, repeated)
        self.assertEqual(original["reference_episodes"], 10)

    def test_controls_do_not_become_independent_opening_operations(self):
        ema = "LIB-CAND-EMA-TREND-001"
        cvd = "LIB-CAND-CVD-SLOPE-001"
        rows = [case(partition="historical", episode=f"hist-{i}",
                     signals={ema: 0.01 * i, cvd: 0.01 * i}) for i in range(1, 11)]
        rows += [case(episode="shared", signals={ema: 0.08, cvd: 0.08}),
                 case(episode="shared", outcome="sl_first_within_horizon",
                      signals={ema: 0.08, cvd: 0.08})]
        rows += [case(source="operation_observation_checkpoint", episode="same-operation",
                      signals={ema: 0.08, cvd: 0.08}) for _ in range(20)]
        report = build_study(rows, cohort_sha256="a" * 64)
        result = next(r for r in report["rule_results"] if r["rule_id"] == ema
                      and r["partition"] == "prospective")
        self.assertEqual(report["score_version"], SCORE_VERSION)
        self.assertEqual(report["production_effect"], "none")
        self.assertFalse(report["database_writes"])
        self.assertEqual(result["raw_cases"], 2)
        self.assertEqual(result["effective_episodes"], 1)
        self.assertEqual(report["observation_control_counts"]["prospective"], 20)

    def test_price_oi_state_is_extracted_from_current_trace_like_sealed_builder(self):
        rule = "M4-RULE-PRICE-OI-STATE-001"
        snapshot = {"stage_rule_traces": {"intraday_short": [{
            "rule_id": rule, "status": "evaluated_shadow", "trace_sha256": "hash",
            "outputs": {"D_H": 0.02, "dOI_H": 0.01},
        }]}}
        values, missing = current_snapshot_rule_values(
            snapshot, side="long", time_horizon="intraday_short",
            baseline_specs=[{"rule_id": rule, "selected_variable": "__current_formula_signal"}],
        )
        self.assertFalse(missing)
        self.assertGreater(values[rule]["value"], 0)

    def test_joint_bearish_short_tp_is_price_down_not_price_up(self):
        ema = "LIB-CAND-EMA-TREND-001"
        cvd = "LIB-CAND-CVD-SLOPE-001"
        rows = [case(partition="historical", episode=f"hist-{i}",
                     signals={ema: 0.01 * i, cvd: 0.01 * i}) for i in range(1, 11)]
        rows.append(case(side="short", signals={ema: 0.1, cvd: 0.1}))
        report = build_study(rows, cohort_sha256="a" * 64)
        pair = next(p for p in report["predeclared_pair_results"]
                    if p["left"] == ema and p["right"] == cvd
                    and p["partition"] == "prospective" and p["state"] == "bearish")
        self.assertEqual(pair["episodes"], 1)
        self.assertEqual(pair["price_up_episode_share"], 0.0)

    def test_no_touch_is_retained_in_three_class_band_not_silently_dropped(self):
        ema = "LIB-CAND-EMA-TREND-001"
        rows = [case(partition="historical", episode=f"hist-{i}", signals={ema: i / 100})
                for i in range(1, 11)]
        rows += [case(episode="tp", signals={ema: 0.1}),
                 case(episode="no-touch", outcome="neither_barrier_before_expiry", signals={ema: 0.1})]
        report = build_study(rows, cohort_sha256="a" * 64)
        rule = next(r for r in report["rule_results"] if r["rule_id"] == ema
                    and r["partition"] == "prospective")
        self.assertEqual(rule["effective_episodes"], 1)
        self.assertEqual(rule["episodes_with_three_class_outcome"], 2)
        band = rule["three_class_outcome_bands"]["strong_for_trade"]
        self.assertEqual(band["episodes"], 2)
        self.assertEqual((band["tp_share"], band["sl_share"], band["neither_share"]),
                         (0.5, 0.0, 0.5))

    def test_unverified_late_close_does_not_count_as_tp_in_primary_results(self):
        rule = "LIB-CAND-EMA-TREND-001"
        historical = [case(partition="historical", episode=f"hist-{i}", signals={rule: i / 100})
                      for i in range(1, 11)]
        late = case(episode="late", signals={rule: 0.1})
        late.update(study_outcome_label=None,
                    fixed_horizon_label_status="late_close_label_not_verified")
        result = build_study(historical + [late], cohort_sha256="a" * 64)
        row = next(item for item in result["rule_results"] if item["rule_id"] == rule
                   and item["partition"] == "prospective")
        self.assertEqual(row["raw_cases"], 0)
        self.assertEqual(result["excluded_late_close_labels"]["prospective"], 1)

    def test_incremental_screen_is_chronological_and_requires_all_three_outcomes(self):
        rule = "LIB-CAND-EMA-TREND-001"
        historical = [case(partition="historical", episode=f"hist-{i}", signals={rule: i / 100})
                      for i in range(1, 11)]
        prospective = []
        start = datetime(2026, 9, 10, tzinfo=timezone.utc)
        outcomes = ("tp_first_within_horizon", "sl_first_within_horizon",
                    "neither_barrier_before_expiry")
        for i in range(42):
            outcome = outcomes[i % 3]
            value = 0.1 if i % 3 == 0 else -0.1 if i % 3 == 1 else 0.0
            row = case(episode=f"episode-{i}", outcome=outcome, signals={rule: value})
            row.update(symbol="BTCUSDT", engine_version="engine-fixed",
                       analysis_at=(start + timedelta(days=i)).isoformat(),
                       probabilities_json=json.dumps(dict(zip(outcomes, (0.34, 0.33, 0.33)))))
            prospective.append(row)
        report = build_study(historical + prospective, cohort_sha256="a" * 64)
        result = next(item for item in report["incremental_validation"] if item["rule_id"] == rule)
        self.assertEqual(result["status"], "out_of_sample_screening_only_not_validated")
        self.assertGreater(result["candidate_coefficient"], 0)
        self.assertGreater(result["brier_improvement"], 0)
        self.assertEqual(result["production_effect"], "none")

        for row in prospective:
            if row["outcome_label"] == "neither_barrier_before_expiry":
                row["outcome_label"] = "sl_first_within_horizon"
        gated = build_study(historical + prospective, cohort_sha256="a" * 64)
        result = next(item for item in gated["incremental_validation"] if item["rule_id"] == rule)
        self.assertEqual(result["status"], "incomplete_three_class_outcomes")
        self.assertIsNone(result["candidate_coefficient"])


if __name__ == "__main__":
    unittest.main()
