from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from m8_evaluation import (
    CLASSES,
    apply_temperature,
    classify_outcome,
    competing_risk_compatibility,
    merge_ranges,
    midrank_percentile,
    normalize_legacy_probabilities,
    normalize_candidate_rows,
    rank_auc,
    resolve_horizon,
    selected_interval_seconds,
)


def candle(open_ms: int, high: float, low: float) -> dict:
    return {
        "open_time_ms": open_ms,
        "open": 100.0,
        "high": high,
        "low": low,
        "close": 100.0,
        "volume": 1.0,
        "close_time_ms": open_ms + 59_999,
    }


def record(side: str = "long") -> dict:
    return {
        "analysis_at": "2026-07-01T12:00:00+00:00",
        "expiry_at": "2026-07-01T12:02:00+00:00",
        "side": side,
        "entry": 100.0,
        "take_profit": 110.0 if side == "long" else 90.0,
        "stop_loss": 90.0 if side == "long" else 110.0,
    }


class M8EvaluationTests(unittest.TestCase):
    def test_stored_horizon_is_formal(self) -> None:
        result = resolve_horizon(
            {"evaluation_horizon_seconds": 3600},
            "intraday_short",
        )
        self.assertEqual(result["status"], "stored_exact")
        self.assertTrue(result["formal_eligible"])

    def test_missing_horizon_is_reconstructed_but_not_formal(self) -> None:
        result = resolve_horizon({}, "intraday_wide")
        self.assertEqual(result["seconds"], 86400)
        self.assertEqual(result["status"], "policy_reconstructed")
        self.assertFalse(result["formal_eligible"])

    def test_sampling_policy_selects_exact_largest_supported_interval(self) -> None:
        self.assertEqual(
            selected_interval_seconds("intraday_short", 14400),
            300,
        )
        self.assertEqual(
            selected_interval_seconds("intraday_wide", 86400),
            3600,
        )
        self.assertEqual(
            selected_interval_seconds("short_swing", 604800),
            21600,
        )

    def test_ranges_merge_only_when_overlapping_or_adjacent(self) -> None:
        self.assertEqual(
            merge_ranges([(0, 60_000), (120_000, 180_000), (400_000, 500_000)]),
            [(0, 180_000), (400_000, 500_000)],
        )

    def test_tp_first_is_resolved(self) -> None:
        rows = [
            candle(1782907200000, 111.0, 99.0),
            candle(1782907260000, 101.0, 99.0),
            candle(1782907320000, 101.0, 99.0),
        ]
        result = classify_outcome(
            record(),
            rows,
            captured_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result["label"], CLASSES[0])

    def test_same_minute_is_ambiguous(self) -> None:
        rows = [
            candle(1782907200000, 111.0, 89.0),
            candle(1782907260000, 101.0, 99.0),
            candle(1782907320000, 101.0, 99.0),
        ]
        result = classify_outcome(
            record(),
            rows,
            captured_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result["status"], "ambiguous_same_minute")
        self.assertIsNone(result["label"])

    def test_no_touch_after_expiry_is_neither(self) -> None:
        rows = [
            candle(1782907200000, 101.0, 99.0),
            candle(1782907260000, 101.0, 99.0),
            candle(1782907320000, 101.0, 99.0),
        ]
        result = classify_outcome(
            record(),
            rows,
            captured_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(result["label"], CLASSES[2])

    def test_temperature_preserves_probability_mass(self) -> None:
        result = apply_temperature(
            {CLASSES[0]: 0.6, CLASSES[1]: 0.3, CLASSES[2]: 0.1},
            1.5,
        )
        self.assertAlmostEqual(sum(result.values()), 1.0, places=12)

    def test_midrank_percentile_counts_equal_half(self) -> None:
        self.assertEqual(midrank_percentile(2.0, [1.0, 2.0, 3.0]), 0.5)

    def test_auc_handles_ties(self) -> None:
        self.assertEqual(rank_auc([0.5, 0.5], [1, 0]), 0.5)

    def test_legacy_percentages_are_normalized(self) -> None:
        result = normalize_legacy_probabilities(
            {
                "tp_probability": 50,
                "sl_probability": 30,
                "range_probability": 20,
            }
        )
        self.assertEqual(result[CLASSES[0]], 0.5)
        self.assertTrue(math.isclose(sum(result.values()), 1.0))

    def test_candidate_without_structured_analysis_is_excluded(self) -> None:
        rows = [
            {
                "recommendation_id": 1,
                "operation_id": 2,
                "analysis_at": "2026-07-01T12:00:00+00:00",
                "symbol": "BTCUSDT",
                "side": "long",
                "time_horizon": "intraday_short",
                "engine_version": "legacy",
                "snapshot_json": '{"valid": true}',
                "analysis_json": None,
                "entry": 100,
                "take_profit": 110,
                "stop_loss": 90,
            }
        ]
        result = normalize_candidate_rows(
            rows,
            {
                "development_end": "2026-07-04",
                "calibration_end": "2026-07-16",
            },
        )
        self.assertEqual(result, [])

    def test_competing_risk_compatibility_reports_invalid_row(self) -> None:
        invalid = {
            "recommendation_id": 1,
            "partition": "development",
            "symbol": "BTCUSDT",
            "side": "long",
            "time_horizon": "intraday_short",
            "entry": 100.0,
            "take_profit": 100.0,
            "stop_loss": 90.0,
            "pretrade": {"sigma_horizon": 0.1},
        }
        compatible, blocked = competing_risk_compatibility([invalid])
        self.assertEqual(compatible, [])
        self.assertEqual(len(blocked), 1)


if __name__ == "__main__":
    unittest.main()
