from __future__ import annotations

import unittest

from positioning_rule_runtime import (
    REFERENCE_COUNT,
    evaluate_positioning_rule_family,
)


HOUR_MS = 3_600_000
CUTOFF_MS = 1_800_000_000_000
ANALYSIS_AT = "2027-01-15T08:00:00+00:00"


def complete_context(
    *,
    funding_rates: list[float] | None = None,
    crowding_ratios: list[float] | None = None,
) -> dict:
    funding = funding_rates or [
        0.00001 * (index + 1)
        for index in range(REFERENCE_COUNT)
    ]
    crowding = crowding_ratios or [
        0.8 + 0.01 * index
        for index in range(REFERENCE_COUNT + 1)
    ]
    return {
        "request_cutoff_ms": CUTOFF_MS,
        "captured_at_ms": CUTOFF_MS + 250,
        "interval": "1h",
        "funding_snapshot": {
            "lastFundingRate": "0.0007",
            "time": CUTOFF_MS + 100,
        },
        "funding_history": [
            {
                "fundingTime": (
                    CUTOFF_MS - (REFERENCE_COUNT - index) * 8 * HOUR_MS
                ),
                "fundingRate": str(rate),
                "rateType": "Regular",
            }
            for index, rate in enumerate(funding)
        ],
        "global_long_short_history": [
            {
                "timestamp": (
                    CUTOFF_MS - (REFERENCE_COUNT - index) * HOUR_MS
                ),
                "longShortRatio": str(ratio),
                "longAccount": str(ratio / (1.0 + ratio)),
                "shortAccount": str(1.0 / (1.0 + ratio)),
            }
            for index, ratio in enumerate(crowding)
        ],
    }


class PositioningRuleRuntimeTests(unittest.TestCase):
    def test_complete_history_evaluates_both_rules_without_probability_effect(
        self,
    ) -> None:
        result = evaluate_positioning_rule_family(
            complete_context(),
            side="long",
            analysis_at=ANALYSIS_AT,
            interval_seconds=3600,
        )

        self.assertEqual(result["status"], "evaluated_shadow")
        self.assertEqual(result["evaluated_rule_count"], 2)
        traces = {trace["rule_id"]: trace for trace in result["traces"]}
        funding = traces["LIB-CAND-FUNDING-PERCENTILE-001"]
        crowding = traces["LIB-CAND-CROWDING-PERCENTILE-001"]
        self.assertEqual(funding["outputs"]["reference_count"], 60)
        self.assertEqual(funding["outputs"]["funding_midrank_60"], 1.0)
        self.assertEqual(crowding["outputs"]["reference_count"], 60)
        self.assertEqual(
            crowding["outputs"]["crowding_midrank_60"],
            1.0,
        )
        self.assertTrue(
            all(
                trace["probability_effect"]
                == "none_shadow_observation"
                for trace in result["traces"]
            )
        )

    def test_short_side_inverts_only_plan_side_crowding_view(self) -> None:
        result = evaluate_positioning_rule_family(
            complete_context(),
            side="short",
            analysis_at=ANALYSIS_AT,
            interval_seconds=3600,
        )
        crowding = result["traces"][1]["outputs"]

        self.assertEqual(crowding["crowding_midrank_60"], 1.0)
        self.assertEqual(
            crowding["plan_side_crowding_midrank_60"],
            0.0,
        )
        self.assertEqual(
            crowding["plan_side_crowding_centered_60"],
            -1.0,
        )

    def test_zero_mad_preserves_percentile_and_marks_z_unavailable(
        self,
    ) -> None:
        context = complete_context(
            funding_rates=[0.0001] * REFERENCE_COUNT,
            crowding_ratios=[1.0] * (REFERENCE_COUNT + 1),
        )
        result = evaluate_positioning_rule_family(
            context,
            side="long",
            analysis_at=ANALYSIS_AT,
            interval_seconds=3600,
        )

        for trace in result["traces"]:
            self.assertEqual(trace["status"], "evaluated_shadow")
            self.assertIn(
                "zero_mad_robust_z_unavailable",
                trace["reason_codes"],
            )
        self.assertIsNone(
            result["traces"][0]["outputs"]["funding_robust_z_60"]
        )
        self.assertIsNone(
            result["traces"][1]["outputs"]["crowding_robust_z_60"]
        )

    def test_incomplete_history_blocks_without_fabricating_values(self) -> None:
        context = complete_context()
        context["funding_history"] = context["funding_history"][-10:]
        context["global_long_short_history"] = context[
            "global_long_short_history"
        ][-10:]
        result = evaluate_positioning_rule_family(
            context,
            side="long",
            analysis_at=ANALYSIS_AT,
            interval_seconds=3600,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["evaluated_rule_count"], 0)
        self.assertTrue(
            all(trace["outputs"] == {} for trace in result["traces"])
        )


if __name__ == "__main__":
    unittest.main()
