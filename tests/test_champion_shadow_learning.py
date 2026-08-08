from __future__ import annotations

import json
import unittest

from champion_shadow_learning import evaluate_champion_shadow_rows


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


if __name__ == "__main__":
    unittest.main()
