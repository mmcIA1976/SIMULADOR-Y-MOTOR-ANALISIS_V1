from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from m7_joint_temporal_engine import ENGINE_VERSION, HORIZON_SECONDS
from m7_production_runtime import build_production_probability_run


ANALYSIS_AT = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
HOUR_MS = 3_600_000


def proposal(horizon: str):
    return SimpleNamespace(
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        take_profit=103.0,
        stop_loss=98.0,
        entry_type="market",
        time_horizon=horizon,
        margin=100.0,
        leverage=2.0,
    )


def snapshot(horizon: str) -> dict:
    seconds = HORIZON_SECONDS[horizon]
    return {
        "analysis_at": ANALYSIS_AT.isoformat(),
        "evaluation_horizon_seconds": seconds,
        "evaluation_expires_at": (
            ANALYSIS_AT + timedelta(seconds=seconds)
        ).isoformat(),
    }


def raw_candles() -> list[list]:
    count = 61 * 24 + 1
    final_close_ms = int(ANALYSIS_AT.timestamp() * 1000)
    first_close_ms = final_close_ms - (count - 1) * HOUR_MS
    rows = []
    for index in range(count):
        close_time = first_close_ms + index * HOUR_MS
        close = 100.0 + 0.08 * ((index % 19) - 9) + index * 0.0007
        rows.append(
            [
                close_time - HOUR_MS + 1,
                str(close - 0.03),
                str(close + 0.10),
                str(close - 0.10),
                str(close),
                "10",
                close_time,
            ]
        )
    return rows


def paged_loader(rows: list[list], calls: list[tuple]):
    def loader(
        symbol,
        interval,
        limit,
        start_time_ms=None,
        end_time_ms=None,
    ):
        calls.append((symbol, interval, limit, start_time_ms, end_time_ms))
        selected = [
            row
            for row in rows
            if (start_time_ms is None or row[0] >= start_time_ms)
            and (end_time_ms is None or row[0] <= end_time_ms)
        ]
        return selected[:limit]

    return loader


class ProductionRuntimeTests(unittest.TestCase):
    def test_all_horizons_read_the_same_reference_curve(self):
        rows = raw_candles()
        results = {}
        intervals = set()
        for horizon in HORIZON_SECONDS:
            calls = []
            result = build_production_probability_run(
                proposal(horizon),
                snapshot(horizon),
                loader=paged_loader(rows, calls),
                analysis_id=f"test-{horizon}",
            )
            self.assertEqual(result["status"], "evaluated")
            self.assertEqual(result["analysis_engine_execution_count"], 1)
            self.assertEqual(result["executed_analysis_engines"], [ENGINE_VERSION])
            self.assertEqual(
                result["probability_result"]["parallel_probability_engines_executed"],
                0,
            )
            self.assertNotIn("interval_trace", result["probability_result"])
            results[horizon] = result["probability_result"]["probability_curve"]
            intervals.update(call[1] for call in calls)

        self.assertEqual(results["intraday_short"], results["intraday_wide"])
        self.assertEqual(results["intraday_wide"], results["short_swing"])
        self.assertEqual(intervals, {"1h"})

    def test_selected_probability_is_only_a_read_from_the_curve(self):
        result = build_production_probability_run(
            proposal("short_swing"),
            snapshot("short_swing"),
            loader=paged_loader(raw_candles(), []),
            analysis_id="test-selected-read",
        )

        self.assertEqual(
            result["probability_result"]["probabilities"],
            result["probability_result"]["probability_curve"]["short_swing"],
        )


if __name__ == "__main__":
    unittest.main()
