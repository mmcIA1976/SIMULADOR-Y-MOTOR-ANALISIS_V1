from __future__ import annotations

import json
import unittest

from champion_shadow_learning import (
    build_champion_shadow_learning_audit,
    evaluate_champion_shadow_rows,
)


def row(operation_id: int, horizon: str, touch: str, challenger: dict) -> dict:
    return {
        "operation_id": operation_id,
        "time_horizon": horizon,
        "first_plan_touch": touch,
        "tp_probability": 0.50,
        "sl_probability": 0.30,
        "range_probability": 0.20,
        "snapshot_json": json.dumps(
            {
                "m6_probability_trace": {
                    "shadow_challenger": {
                        "probabilities": challenger,
                    }
                }
            }
        ),
    }


class ChampionShadowLearningTests(unittest.TestCase):
    def test_scores_only_exact_outcomes_and_never_auto_promotes(self):
        result = evaluate_champion_shadow_rows(
            [
                row(
                    1,
                    "intraday_short",
                    "take_profit",
                    {
                        "tp_first_within_horizon": 0.70,
                        "sl_first_within_horizon": 0.20,
                        "neither_barrier_before_expiry": 0.10,
                    },
                ),
                row(
                    2,
                    "intraday_wide",
                    "ambiguous_same_candle",
                    {
                        "tp_first_within_horizon": 0.40,
                        "sl_first_within_horizon": 0.30,
                        "neither_barrier_before_expiry": 0.30,
                    },
                ),
            ]
        )

        self.assertEqual(result["eligible_cases"], 1)
        self.assertEqual(result["excluded_cases"], 1)
        self.assertLess(
            result["overall"]["challenger"]["log_loss_3c"],
            result["overall"]["champion"]["log_loss_3c"],
        )
        self.assertFalse(result["automatic_promotion"])
        self.assertEqual(
            result["learning_judgement"],
            "collecting_below_interim_sample",
        )

    def test_empty_cohort_is_reported_as_collection_not_learning(self):
        result = evaluate_champion_shadow_rows([])

        self.assertEqual(result["eligible_cases"], 0)
        self.assertEqual(
            result["learning_judgement"],
            "collecting_no_resolved_exact_cases",
        )

    def test_native_rule_ablation_uses_independent_overlapping_episode(self):
        rows = []
        for operation_id, analysis_at, touch in (
            (10, "2026-08-12T10:00:00+00:00", "take_profit"),
            (11, "2026-08-12T11:00:00+00:00", "stop_loss"),
        ):
            item = row(
                operation_id,
                "intraday_short",
                touch,
                {
                    "tp_first_within_horizon": 0.55,
                    "sl_first_within_horizon": 0.35,
                    "neither_barrier_before_expiry": 0.10,
                },
            )
            snapshot = json.loads(item["snapshot_json"])
            snapshot["m6_probability_trace"]["fitted_rule_ablation"] = {
                "M4-RULE-VOLATILITY-RANK-001": {
                    "probabilities_without_rule": {
                        "tp_first_within_horizon": 0.40,
                        "sl_first_within_horizon": 0.40,
                        "neither_barrier_before_expiry": 0.20,
                    }
                }
            }
            item.update(
                {
                    "symbol": "BTCUSDT",
                    "analysis_at": analysis_at,
                    "snapshot_json": json.dumps(snapshot),
                }
            )
            rows.append(item)

        result = evaluate_champion_shadow_rows(rows)

        self.assertEqual(
            result["independent_episode_comparison"]["raw_cases"],
            2,
        )
        self.assertEqual(
            result["independent_episode_comparison"]["effective_episodes"],
            1,
        )
        rule = result["native_rule_ablation"]["rules"][
            "M4-RULE-VOLATILITY-RANK-001"
        ]["intraday_short"]
        self.assertEqual(rule["raw_cases"], 2)
        self.assertEqual(rule["effective_episodes"], 1)
        self.assertEqual(
            rule["evidence_status"],
            "insufficient_effective_evidence",
        )

    def test_database_query_avoids_psycopg_percent_placeholder_collision(self):
        class Result:
            @staticmethod
            def fetchall():
                return []

        class FakeDb:
            query = ""

            def execute(self, query, _params):
                self.query = query
                return Result()

        db = FakeDb()
        result = build_champion_shadow_learning_audit(db, 1)

        self.assertEqual(result["eligible_cases"], 0)
        self.assertNotIn("LIKE 'complete%'", db.query)
        self.assertIn("LEFT(COALESCE(le.evidence_quality, ''), 8)", db.query)


if __name__ == "__main__":
    unittest.main()
