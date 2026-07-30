from __future__ import annotations

import unittest

from data_quality_gate import (
    DataQualityError,
    FRESHNESS_RULE_ID,
    INTEGRITY_RULE_ID,
    validate_pretrade_candles,
)
from m8_evaluation import kline_fingerprint


INTERVAL_MS = 60_000
ANALYSIS_AT = "2026-07-30T12:00:00+00:00"


def candles(count: int = 4) -> list[dict]:
    first_open = 1_000_000
    rows = []
    for index in range(count):
        open_time = first_open + index * INTERVAL_MS
        close = 100.0 + index
        rows.append(
            {
                "open_time_ms": open_time,
                "open": close - 0.25,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 10.0 + index,
                "close_time_ms": open_time + INTERVAL_MS - 1,
            }
        )
    return rows


class DataQualityGateTests(unittest.TestCase):
    def test_validates_selected_history_once_and_emits_two_gate_traces(self):
        rows = candles()
        analysis_ms = rows[-1]["close_time_ms"]

        result = validate_pretrade_candles(
            rows,
            analysis_at=ANALYSIS_AT,
            analysis_at_ms=analysis_ms,
            interval_seconds=60,
            required_candle_count=4,
        )

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["validation_pass_count"], 1)
        self.assertEqual(
            result["source_data_sha256"],
            kline_fingerprint(rows),
        )
        self.assertEqual(
            [trace["rule_id"] for trace in result["traces"]],
            [FRESHNESS_RULE_ID, INTEGRITY_RULE_ID],
        )
        self.assertTrue(
            all(trace["status"] == "passed" for trace in result["traces"])
        )
        self.assertTrue(
            all(
                trace["probability_effect"] == "none_data_quality_gate"
                for trace in result["traces"]
            )
        )

    def test_stale_latest_candle_blocks_with_auditable_report(self):
        rows = candles()
        analysis_ms = (
            rows[-1]["close_time_ms"] + INTERVAL_MS + 60_001
        )

        with self.assertRaises(DataQualityError) as captured:
            validate_pretrade_candles(
                rows,
                analysis_at=ANALYSIS_AT,
                analysis_at_ms=analysis_ms,
                interval_seconds=60,
                required_candle_count=4,
            )

        self.assertEqual(str(captured.exception), "pretrade_candles_stale")
        report = captured.exception.report
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["traces"][0]["status"], "failed")
        self.assertEqual(report["traces"][1]["status"], "passed")

    def test_gap_or_duplicate_blocks_integrity(self):
        rows = candles()
        rows[2] = dict(rows[1])

        with self.assertRaises(DataQualityError) as captured:
            validate_pretrade_candles(
                rows,
                analysis_at=ANALYSIS_AT,
                analysis_at_ms=rows[-1]["close_time_ms"],
                interval_seconds=60,
                required_candle_count=4,
            )

        self.assertEqual(
            str(captured.exception),
            "pretrade_candle_integrity_failed",
        )
        integrity = captured.exception.report["traces"][1]
        self.assertEqual(integrity["status"], "failed")
        self.assertIn("duplicate_candles", integrity["reason_codes"])

    def test_incoherent_ohlc_blocks_integrity(self):
        rows = candles()
        rows[1]["high"] = rows[1]["close"] - 1.0

        with self.assertRaises(DataQualityError) as captured:
            validate_pretrade_candles(
                rows,
                analysis_at=ANALYSIS_AT,
                analysis_at_ms=rows[-1]["close_time_ms"],
                interval_seconds=60,
                required_candle_count=4,
            )

        integrity = captured.exception.report["traces"][1]
        self.assertIn("incoherent_ohlc", integrity["reason_codes"])

    def test_insufficient_history_preserves_existing_block_code(self):
        rows = candles(3)

        with self.assertRaises(DataQualityError) as captured:
            validate_pretrade_candles(
                rows,
                analysis_at=ANALYSIS_AT,
                analysis_at_ms=rows[-1]["close_time_ms"],
                interval_seconds=60,
                required_candle_count=4,
            )

        self.assertEqual(str(captured.exception), "insufficient_pretrade_history")
        report = captured.exception.report
        self.assertEqual(
            report["traces"][1]["outputs"]["missing_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
