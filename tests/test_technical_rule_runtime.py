from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from technical_rule_runtime import (
    RULE_IDS,
    ema_series,
    evaluate_technical_rule_family,
    wilder_atr,
    wilder_rsi,
)


ANALYSIS_AT = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


def candles(count: int = 260, growth: float = 0.001) -> list[dict]:
    rows = []
    price = 100.0
    start_ms = int(ANALYSIS_AT.timestamp() * 1000) - count * 60_000
    for index in range(count):
        close = price * (1.0 + growth)
        rows.append(
            {
                "open_time_ms": start_ms + index * 60_000,
                "open": price,
                "high": max(price, close) + 0.2,
                "low": min(price, close) - 0.2,
                "close": close,
                "volume": 10.0,
                "close_time_ms": start_ms + (index + 1) * 60_000,
            }
        )
        price = close
    return rows


class TechnicalRuleRuntimeTests(unittest.TestCase):
    def test_ema_uses_sma_seed_and_standard_alpha(self) -> None:
        result = ema_series([1.0, 2.0, 3.0, 4.0], 3)
        self.assertEqual(result[:2], [None, None])
        self.assertEqual(result[2], 2.0)
        self.assertEqual(result[3], 3.0)

    def test_wilder_rsi_reaches_bounds_for_monotonic_series(self) -> None:
        self.assertEqual(wilder_rsi(list(range(1, 30))), 100.0)
        self.assertEqual(wilder_rsi(list(range(30, 1, -1))), 0.0)

    def test_wilder_atr_is_positive_and_finite(self) -> None:
        value = wilder_atr(candles(30))
        self.assertGreater(value, 0.0)
        self.assertTrue(math.isfinite(value))

    def test_family_produces_three_shadow_traces(self) -> None:
        result = evaluate_technical_rule_family(
            candles(),
            side="long",
            analysis_at=ANALYSIS_AT.isoformat(),
            interval_seconds=60,
            source_data_sha256="source-sha",
        )
        self.assertEqual(result["status"], "evaluated_shadow")
        self.assertEqual(
            {trace["rule_id"] for trace in result["traces"]},
            set(RULE_IDS),
        )
        for trace in result["traces"]:
            self.assertEqual(
                trace["probability_effect"],
                "none_shadow_observation",
            )
            self.assertTrue(trace["trace_sha256"])

    def test_short_side_inverts_directional_outputs(self) -> None:
        long_result = evaluate_technical_rule_family(
            candles(),
            side="long",
            analysis_at=ANALYSIS_AT.isoformat(),
            interval_seconds=60,
            source_data_sha256="source-sha",
        )
        short_result = evaluate_technical_rule_family(
            candles(),
            side="short",
            analysis_at=ANALYSIS_AT.isoformat(),
            interval_seconds=60,
            source_data_sha256="source-sha",
        )
        long_traces = {
            trace["rule_id"]: trace for trace in long_result["traces"]
        }
        short_traces = {
            trace["rule_id"]: trace for trace in short_result["traces"]
        }
        self.assertAlmostEqual(
            long_traces["LIB-CAND-RSI-WILDER-001"]["outputs"][
                "side_adjusted_centered_rsi"
            ],
            -short_traces["LIB-CAND-RSI-WILDER-001"]["outputs"][
                "side_adjusted_centered_rsi"
            ],
        )


if __name__ == "__main__":
    unittest.main()
