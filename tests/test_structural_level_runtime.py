from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from structural_level_runtime import (
    RULE_IDS,
    alternating_pivots,
    confirmed_pivots,
    evaluate_structural_level_family,
)
from predictive_rule_library import rule_metadata
from technical_rule_runtime import wilder_atr


ANALYSIS_AT = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def candles(count: int = 160) -> list[dict]:
    rows = []
    start_ms = int(ANALYSIS_AT.timestamp() * 1000) - count * 3_600_000
    for index in range(count):
        center = 100.0 + 0.02 * index + 3.0 * math.sin(index / 4.0)
        rows.append(
            {
                "open_time_ms": start_ms + index * 3_600_000,
                "open": center - 0.1,
                "high": center + 0.45,
                "low": center - 0.45,
                "close": center,
                "volume": 10.0,
                "close_time_ms": start_ms + (index + 1) * 3_600_000,
            }
        )
    return rows


class StructuralLevelRuntimeTests(unittest.TestCase):
    def test_pivots_are_confirmed_only_after_right_hand_window(self):
        rows = candles()
        pivots = confirmed_pivots(
            rows,
            atr14=wilder_atr(rows, 14),
        )
        self.assertGreater(len(pivots), 4)
        self.assertTrue(
            all(
                pivot["confirmed_at_index"] == pivot["index"] + 3
                for pivot in pivots
            )
        )
        self.assertTrue(
            all(pivot["prominence_atr"] > 0 for pivot in pivots)
        )

    def test_alternating_series_collapses_same_type_extremes(self):
        result = alternating_pivots(
            [
                {"index": 1, "type": "high", "price": 10},
                {"index": 2, "type": "high", "price": 12},
                {"index": 3, "type": "low", "price": 8},
            ]
        )
        self.assertEqual(
            [(item["type"], item["price"]) for item in result],
            [("high", 12), ("low", 8)],
        )

    def test_family_produces_two_traced_shadow_rules(self):
        result = evaluate_structural_level_family(
            candles(),
            return_count=24,
            side="long",
            entry=102.0,
            take_profit=108.0,
            stop_loss=96.0,
            sigma_horizon=0.025,
            interval_seconds=3600,
            analysis_at=ANALYSIS_AT.isoformat(),
            source_data_sha256="source-sha",
        )
        self.assertEqual(result["status"], "evaluated_shadow")
        self.assertEqual(result["evaluated_rule_count"], 2)
        traces = {
            trace["rule_id"]: trace for trace in result["traces"]
        }
        self.assertEqual(set(traces), set(RULE_IDS))
        structural = traces[RULE_IDS[0]]
        fibonacci = traces[RULE_IDS[1]]
        self.assertGreater(
            structural["outputs"]["confirmed_pivot_count"],
            0,
        )
        self.assertGreater(
            fibonacci["outputs"]["move_atr14"],
            0,
        )
        self.assertEqual(
            fibonacci["parent_rule_ids"],
            [RULE_IDS[0]],
        )
        self.assertTrue(
            all(
                trace["probability_effect"]
                == "none_shadow_observation"
                for trace in traces.values()
            )
        )
        for rule_id, trace in traces.items():
            self.assertEqual(
                trace["formula_ids"],
                rule_metadata(rule_id)["formula_ids"],
            )

    def test_short_changes_only_side_adjusted_level_distance(self):
        common = {
            "candles": candles(),
            "return_count": 24,
            "entry": 102.0,
            "take_profit": 96.0,
            "stop_loss": 108.0,
            "sigma_horizon": 0.025,
            "interval_seconds": 3600,
            "analysis_at": ANALYSIS_AT.isoformat(),
            "source_data_sha256": "source-sha",
        }
        long_result = evaluate_structural_level_family(
            side="long",
            **{**common, "take_profit": 108.0, "stop_loss": 96.0},
        )
        short_result = evaluate_structural_level_family(
            side="short",
            **common,
        )
        long_level = long_result["traces"][0]["outputs"][
            "nearest_resistance"
        ]
        short_level = short_result["traces"][0]["outputs"][
            "nearest_resistance"
        ]
        self.assertAlmostEqual(
            long_level["distance_sigma_horizon"],
            short_level["distance_sigma_horizon"],
        )
        self.assertAlmostEqual(
            long_level["side_adjusted_distance_sigma_horizon"],
            -short_level["side_adjusted_distance_sigma_horizon"],
        )


if __name__ == "__main__":
    unittest.main()
