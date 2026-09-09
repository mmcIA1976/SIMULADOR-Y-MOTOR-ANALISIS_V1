from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from observational_shadow_evaluation import (
    EMA_CANDIDATE_LOG_ODDS_WEIGHTS,
    EMA_RULE_ID,
    PROSPECTIVE_COHORT_START_AT,
    _validation_gate,
    apply_conditional_tp_sl_weight,
    build_observational_shadow_report,
    build_observational_shadow_report_from_rows,
    ema_alignment_signal,
)


def structured_payload(
    horizon: str,
    *,
    close_vs_ema: float,
    ema_gap: float,
    slope: float,
) -> dict:
    return {
        "analysis_context": {
            "predictive_rules": {
                "observational_rules": {
                    EMA_RULE_ID: {
                        "probability_effect": "none_observation_only",
                        "stage_traces": [
                            {
                                "rule_id": EMA_RULE_ID,
                                "time_horizon": horizon,
                                "status": "evaluated_shadow",
                                "trace_sha256": "ema-trace",
                                "outputs": {
                                    "side_adjusted_close_vs_ema50_log": close_vs_ema,
                                    "side_adjusted_ema50_vs_ema200_log": ema_gap,
                                    "side_adjusted_slope_atr": slope,
                                },
                            }
                        ],
                    }
                }
            }
        }
    }


def row(
    operation_id: int,
    *,
    analysis_at: str,
    outcome: str,
    aligned: bool,
    horizon: str = "intraday_short",
) -> dict:
    direction = 1.0 if aligned else -1.0
    return {
        "operation_id": operation_id,
        "plan_result": outcome,
        "time_horizon": horizon,
        "side": "long",
        "symbol": "ETHUSDT",
        "analysis_at": analysis_at,
        "tp_probability": 0.45,
        "sl_probability": 0.45,
        "range_probability": 0.10,
        "structured_json": structured_payload(
            horizon,
            close_vs_ema=0.002 * direction,
            ema_gap=0.001 * direction,
            slope=0.5 * direction,
        ),
    }


class ObservationalShadowEvaluationTests(unittest.TestCase):
    def test_weight_moves_only_tp_sl_and_preserves_probability_mass(self):
        base = {"tp": 0.40, "sl": 0.35, "range": 0.25}

        aligned = apply_conditional_tp_sl_weight(
            base,
            signal=1.0,
            log_odds_weight=0.35,
        )
        opposed = apply_conditional_tp_sl_weight(
            base,
            signal=-1.0,
            log_odds_weight=0.35,
        )

        self.assertGreater(aligned["tp"], base["tp"])
        self.assertLess(aligned["sl"], base["sl"])
        self.assertLess(opposed["tp"], base["tp"])
        self.assertGreater(opposed["sl"], base["sl"])
        self.assertEqual(aligned["range"], base["range"])
        self.assertEqual(opposed["range"], base["range"])
        self.assertTrue(math.isclose(sum(aligned.values()), 1.0))
        self.assertTrue(math.isclose(sum(opposed.values()), 1.0))

    def test_zero_weight_is_exact_production_identity(self):
        base = {"tp": 0.39, "sl": 0.41, "range": 0.20}

        result = apply_conditional_tp_sl_weight(
            base,
            signal=1.0,
            log_odds_weight=0.0,
        )

        self.assertEqual(result, base)

    def test_ema_signal_uses_the_selected_horizon_and_three_votes(self):
        source = row(
            1,
            analysis_at="2026-09-06T10:00:00+00:00",
            outcome="plan_success",
            aligned=True,
            horizon="intraday_wide",
        )

        signal = ema_alignment_signal(source)

        self.assertEqual(signal["state"], "fully_aligned")
        self.assertEqual(signal["score"], 1.0)
        self.assertEqual(signal["source_trace_sha256"], "ema-trace")

    def test_report_freezes_discovery_and_prospective_cohorts(self):
        rows = [
            row(
                1,
                analysis_at="2026-09-06T10:00:00+00:00",
                outcome="plan_success",
                aligned=True,
            ),
            row(
                2,
                analysis_at=PROSPECTIVE_COHORT_START_AT,
                outcome="plan_failure",
                aligned=False,
            ),
        ]

        report = build_observational_shadow_report_from_rows(
            rows,
            generated_at=datetime(2026, 9, 7, 1, tzinfo=timezone.utc),
        )
        experiment = report["experiments"][0]
        discovery = experiment["cohorts"]["discovery"]["report"]
        prospective = experiment["cohorts"]["prospective"]["report"]

        self.assertEqual(discovery["cases"], 1)
        self.assertEqual(prospective["cases"], 1)
        self.assertEqual(
            experiment["candidate_log_odds_weights"],
            list(EMA_CANDIDATE_LOG_ODDS_WEIGHTS),
        )
        self.assertEqual(
            report["production_isolation"]["production_effect"],
            "none",
        )
        self.assertFalse(report["manual_governance"]["automatic_weight_selection"])

    def test_v09_observation_snapshot_joins_the_same_rule_evaluator(self):
        source = {
            "operation_id": 429,
            "plan_result": "plan_failure",
            "time_horizon": "intraday_wide",
            "side": "short",
            "symbol": "BTCUSDT",
            "analysis_at": PROSPECTIVE_COHORT_START_AT,
            "tp_probability": 0.70,
            "sl_probability": 0.25,
            "range_probability": 0.05,
            "structured_json": None,
            "case_origin": "observation",
            "snapshot_json": {
                "stage_rule_traces": {
                    "intraday_wide": [
                        {
                            "rule_id": EMA_RULE_ID,
                            "status": "evaluated_shadow",
                            "probability_effect": "none_observation_only",
                            "trace_sha256": "observation-ema-trace",
                            "outputs": {
                                "side_adjusted_close_vs_ema50_log": -0.002,
                                "side_adjusted_ema50_vs_ema200_log": -0.001,
                                "side_adjusted_slope_atr": -0.5,
                            },
                        }
                    ]
                }
            },
        }

        report = build_observational_shadow_report_from_rows([source])
        prospective = report["experiments"][0]["cohorts"]["prospective"][
            "report"
        ]

        self.assertEqual(prospective["cases"], 1)
        self.assertEqual(prospective["distinct_episodes"], 1)
        self.assertEqual(prospective["origins"], {"observation": 1})
        self.assertEqual(prospective["outcomes"], {"sl": 1})

    def test_episode_cannot_be_split_across_discovery_and_prospective(self):
        rows = [
            row(
                429,
                analysis_at="2026-09-06T11:00:00+00:00",
                outcome="plan_failure",
                aligned=False,
            ),
            row(
                429,
                analysis_at="2026-09-06T12:00:00+00:00",
                outcome="plan_failure",
                aligned=False,
            ),
        ]

        report = build_observational_shadow_report_from_rows(rows)
        cohorts = report["experiments"][0]["cohorts"]

        self.assertEqual(cohorts["discovery"]["report"]["cases"], 2)
        self.assertEqual(cohorts["prospective"]["report"]["cases"], 0)

    def test_counterfactual_weight_can_be_compared_without_mutating_rows(self):
        rows = [
            row(
                1,
                analysis_at="2026-09-06T10:00:00+00:00",
                outcome="plan_success",
                aligned=True,
            ),
            row(
                2,
                analysis_at="2026-09-06T10:05:00+00:00",
                outcome="plan_failure",
                aligned=False,
            ),
        ]
        original_probabilities = [
            (
                item["tp_probability"],
                item["sl_probability"],
                item["range_probability"],
            )
            for item in rows
        ]

        report = build_observational_shadow_report_from_rows(rows)
        candidates = report["experiments"][0]["cohorts"]["discovery"][
            "report"
        ]["candidates"]
        baseline = candidates[0]
        weighted = candidates[-1]

        self.assertGreater(
            weighted["delta_vs_baseline"]["log_loss_improvement"],
            0.0,
        )
        self.assertGreater(
            weighted["delta_vs_baseline"][
                "resolved_binary_brier_improvement"
            ],
            0.0,
        )
        self.assertEqual(
            [
                (
                    item["tp_probability"],
                    item["sl_probability"],
                    item["range_probability"],
                )
                for item in rows
            ],
            original_probabilities,
        )
        self.assertEqual(baseline["log_odds_weight"], 0.0)

    def test_repeated_checkpoints_share_one_episode_weight(self):
        repeated = [
            row(
                429,
                analysis_at=f"2026-09-07T10:{minute:02d}:00+00:00",
                outcome="plan_failure",
                aligned=True,
            )
            for minute in range(10)
        ]
        independent = row(
            430,
            analysis_at="2026-09-07T11:00:00+00:00",
            outcome="plan_success",
            aligned=True,
        )

        report = build_observational_shadow_report_from_rows(
            [*repeated, independent]
        )["experiments"][0]["cohorts"]["prospective"]["report"]
        candidate = report["candidates"][0]

        self.assertEqual(report["cases"], 11)
        self.assertEqual(report["distinct_episodes"], 2)
        self.assertAlmostEqual(candidate["baseline"]["total_weight"], 2.0)
        self.assertAlmostEqual(
            candidate["baseline"]["weighted_outcomes"]["tp"],
            1.0,
        )
        self.assertAlmostEqual(
            candidate["baseline"]["weighted_outcomes"]["sl"],
            1.0,
        )
        self.assertEqual(
            candidate["analysis_level_diagnostic"]["baseline"]["cases"],
            11,
        )

    def test_validation_gate_counts_operations_not_checkpoints(self):
        direct_gate = _validation_gate(
            [
                {
                    "operation_id": 429,
                    "outcome": "sl",
                    "time_horizon": "intraday_short",
                }
                for _ in range(200)
            ]
        )

        self.assertEqual(direct_gate["status"], "collecting")
        self.assertEqual(
            direct_gate["manual_weight_review"]["current_total_cases"],
            1,
        )
        self.assertFalse(direct_gate["manual_weight_review"]["ready"])

    def test_database_adapter_performs_one_read_only_query(self):
        class Cursor:
            def fetchall(self):
                return []

        class Db:
            def __init__(self):
                self.calls = []

            def execute(self, query, params):
                self.calls.append((query, params))
                return Cursor()

        db = Db()

        report = build_observational_shadow_report(db)

        self.assertEqual(len(db.calls), 1)
        self.assertTrue(db.calls[0][0].lstrip().startswith("SELECT"))
        self.assertFalse(report["production_isolation"]["database_writes"])


if __name__ == "__main__":
    unittest.main()
