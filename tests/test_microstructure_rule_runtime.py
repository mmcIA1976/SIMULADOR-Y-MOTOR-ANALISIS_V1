from __future__ import annotations

import unittest

from microstructure_rule_runtime import (
    empirical_midrank,
    evaluate_microstructure_rule_family,
    theil_sen_slope,
)
from predictive_rule_library import rule_metadata


def candles() -> list[dict]:
    rows = []
    for index in range(61 * 24):
        price = 100.0 + index * 0.001
        rows.append(
            {
                "open_time_ms": index * 3_600_000,
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price + 0.05,
                "volume": 100.0 + (index // 24),
                "quote_volume": 10_000.0 + (index // 24) * 100,
                "taker_buy_quote_volume": 5_100.0,
                "close_time_ms": (index + 1) * 3_600_000,
            }
        )
    return rows


def live_context(current: list[dict]) -> dict:
    return {
        "captured_at_ms": current[-1]["close_time_ms"] + 100,
        "taker_history": [
            {
                "timestamp": row["open_time_ms"],
                "buyVol": str(10 + index),
                "sellVol": str(9 + index / 2),
            }
            for index, row in enumerate(current)
        ],
        "depth": {
            "bids": [
                [str(99.99 - index * 0.01), str(10 + index)]
                for index in range(100)
            ],
            "asks": [
                [str(100.01 + index * 0.01), str(8 + index)]
                for index in range(100)
            ],
        },
    }


class MicrostructureRuleRuntimeTests(unittest.TestCase):
    def test_midrank_is_bounded_and_handles_ties(self) -> None:
        self.assertEqual(empirical_midrank(2.0, [1.0, 2.0, 3.0]), 0.5)

    def test_theil_sen_slope_is_robust_for_linear_values(self) -> None:
        self.assertEqual(theil_sen_slope([1.0, 3.0, 5.0, 7.0]), 2.0)

    def test_complete_context_evaluates_all_three_rules(self) -> None:
        selected = candles()
        current = selected[-24:]
        result = evaluate_microstructure_rule_family(
            selected_candles=selected,
            current_bars=current,
            live_context=live_context(current),
            return_count=24,
            interval_seconds=3600,
            side="long",
            analysis_at="2026-07-29T12:00:00+00:00",
            source_data_sha256="candle-sha",
        )
        self.assertEqual(result["status"], "evaluated_shadow")
        self.assertEqual(result["evaluated_rule_count"], 3)
        traces = {
            trace["rule_id"]: trace for trace in result["traces"]
        }
        self.assertEqual(
            traces["LIB-CAND-RELATIVE-VOLUME-001"]["outputs"][
                "reference_horizon_count"
            ],
            60,
        )
        self.assertNotIn(
            "side_adjusted_log_relative_volume",
            traces["LIB-CAND-RELATIVE-VOLUME-001"]["outputs"],
        )
        for rule_id, trace in traces.items():
            expected_formula_ids = rule_metadata(rule_id)["formula_ids"]
            if rule_id == "LIB-CAND-ORDERBOOK-IMBALANCE-001":
                self.assertEqual(
                    trace["formula_ids"],
                    expected_formula_ids[:2],
                )
            else:
                self.assertEqual(
                    trace["formula_ids"],
                    expected_formula_ids,
                )
        self.assertAlmostEqual(
            sum(
                traces["LIB-CAND-ORDERBOOK-IMBALANCE-001"][
                    "outputs"
                ]["measures"]["top_5"].values()
            )
            - traces["LIB-CAND-ORDERBOOK-IMBALANCE-001"][
                "outputs"
            ]["measures"]["top_5"]["imbalance"],
            traces["LIB-CAND-ORDERBOOK-IMBALANCE-001"][
                "outputs"
            ]["measures"]["top_5"]["bid_notional"]
            + traces["LIB-CAND-ORDERBOOK-IMBALANCE-001"][
                "outputs"
            ]["measures"]["top_5"]["ask_notional"],
        )

    def test_missing_live_context_blocks_only_flow_and_book(self) -> None:
        selected = candles()
        result = evaluate_microstructure_rule_family(
            selected_candles=selected,
            current_bars=selected[-24:],
            live_context=None,
            return_count=24,
            interval_seconds=3600,
            side="long",
            analysis_at="2026-07-29T12:00:00+00:00",
            source_data_sha256="candle-sha",
        )
        statuses = {
            trace["rule_id"]: trace["status"]
            for trace in result["traces"]
        }
        self.assertEqual(
            statuses["LIB-CAND-RELATIVE-VOLUME-001"],
            "evaluated_shadow",
        )
        self.assertEqual(
            statuses["LIB-CAND-CVD-SLOPE-001"],
            "evaluated_shadow",
        )
        self.assertEqual(
            statuses["LIB-CAND-ORDERBOOK-IMBALANCE-001"],
            "blocked",
        )


if __name__ == "__main__":
    unittest.main()
