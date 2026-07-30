from __future__ import annotations

import unittest
from datetime import datetime, timezone

from market_context_rule_runtime import (
    DAY_MS,
    evaluate_market_context_rule_family,
)


CUTOFF_MS = 1_800_000_000_000
ANALYSIS_AT = datetime.fromtimestamp(
    CUTOFF_MS / 1000,
    tz=timezone.utc,
).isoformat()


def complete_context() -> dict:
    return {
        "request_cutoff_ms": CUTOFF_MS,
        "captured_at_ms": CUTOFF_MS + 500,
        "market_breadth_assets": [
            {
                "id": f"asset-{index}",
                "symbol": f"A{index}",
                "market_cap_rank": index + 1,
                "last_updated": datetime.fromtimestamp(
                    (CUTOFF_MS - 1000 - index) / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                "price_change_percentage_1h_in_currency": index - 49.5,
                "price_change_percentage_24h_in_currency": index - 40,
                "price_change_percentage_7d_in_currency": index - 60,
            }
            for index in range(100)
        ],
        "fear_greed_history": [
            {
                "value": str(20 + index),
                "value_classification": "test",
                "timestamp": str(
                    (
                        CUTOFF_MS
                        - (60 - index) * DAY_MS
                    )
                    // 1000
                ),
            }
            for index in range(61)
        ],
    }


class MarketContextRuleRuntimeTests(unittest.TestCase):
    def test_complete_context_evaluates_breadth_and_sentiment(self) -> None:
        result = evaluate_market_context_rule_family(
            complete_context(),
            side="long",
            time_horizon="intraday_wide",
            analysis_at=ANALYSIS_AT,
        )

        self.assertEqual(result["status"], "evaluated_shadow")
        self.assertEqual(result["evaluated_rule_count"], 2)
        breadth, sentiment = result["traces"]
        self.assertEqual(breadth["outputs"]["universe_size"], 100)
        self.assertEqual(
            breadth["outputs"]["windows"]["1h"]["advancer_fraction"],
            0.5,
        )
        self.assertEqual(sentiment["outputs"]["reference_count"], 60)
        self.assertEqual(
            sentiment["outputs"]["sentiment_midrank_60"],
            1.0,
        )
        self.assertTrue(
            all(
                trace["probability_effect"]
                == "none_shadow_observation"
                for trace in result["traces"]
            )
        )

    def test_short_side_changes_only_descriptive_alignment(self) -> None:
        long_result = evaluate_market_context_rule_family(
            complete_context(),
            side="long",
            time_horizon="short_swing",
            analysis_at=ANALYSIS_AT,
        )
        short_result = evaluate_market_context_rule_family(
            complete_context(),
            side="short",
            time_horizon="short_swing",
            analysis_at=ANALYSIS_AT,
        )

        long_sentiment = long_result["traces"][1]["outputs"]
        short_sentiment = short_result["traces"][1]["outputs"]
        self.assertEqual(
            long_sentiment["sentiment_midrank_60"],
            short_sentiment["sentiment_midrank_60"],
        )
        self.assertEqual(
            long_sentiment["plan_side_sentiment_alignment"],
            -short_sentiment["plan_side_sentiment_alignment"],
        )

    def test_incomplete_breadth_universe_blocks_only_breadth(self) -> None:
        context = complete_context()
        context["market_breadth_assets"] = context[
            "market_breadth_assets"
        ][:-1]
        result = evaluate_market_context_rule_family(
            context,
            side="long",
            time_horizon="intraday_short",
            analysis_at=ANALYSIS_AT,
        )

        self.assertEqual(result["status"], "partially_evaluated_shadow")
        self.assertEqual(result["traces"][0]["status"], "blocked")
        self.assertIn(
            "incomplete_top_100_universe",
            result["traces"][0]["reason_codes"],
        )
        self.assertEqual(
            result["traces"][1]["status"],
            "evaluated_shadow",
        )

    def test_gapped_sentiment_history_is_not_imputed(self) -> None:
        context = complete_context()
        context["fear_greed_history"][30]["timestamp"] = str(
            (
                CUTOFF_MS - 28 * DAY_MS
            )
            // 1000
        )
        result = evaluate_market_context_rule_family(
            context,
            side="long",
            time_horizon="intraday_wide",
            analysis_at=ANALYSIS_AT,
        )

        sentiment = result["traces"][1]
        self.assertEqual(sentiment["status"], "blocked")
        self.assertTrue(
            {
                "duplicate_sentiment_timestamps",
                "gapped_daily_sentiment_history",
            }
            & set(sentiment["reason_codes"])
        )
        self.assertEqual(sentiment["outputs"], {})


if __name__ == "__main__":
    unittest.main()
