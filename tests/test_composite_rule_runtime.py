from __future__ import annotations

import unittest

from composite_rule_runtime import evaluate_composite_rule_family


ANALYSIS_AT = "2026-07-30T12:00:00+00:00"


def candles() -> list[dict]:
    rows = []
    for index in range(61 * 24 + 1):
        close = 100.0 + index * 0.002 + (index % 7 - 3) * 0.01
        rows.append(
            {
                "open": close - 0.02,
                "high": close + 0.08,
                "low": close - 0.08,
                "close": close,
                "volume": 10 + index % 5,
                "close_time_ms": index * 3_600_000,
            }
        )
    return rows


def trace(rule_id: str, outputs: dict, status: str) -> dict:
    return {
        "rule_id": rule_id,
        "status": status,
        "outputs": outputs,
        "trace_sha256": f"sha-{rule_id}",
    }


def m5_analysis() -> dict:
    return {
        "traces": [
            trace(
                "M4-RULE-VOLATILITY-RANK-001",
                {"volatility_percentile": 0.4},
                "evaluated",
            ),
            trace(
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                {"ATI_H": 0.35},
                "evaluated",
            ),
        ]
    }


def observations() -> list[dict]:
    return [
        trace(
            "LIB-CAND-RELATIVE-VOLUME-001",
            {
                "relative_horizon_volume": 1.2,
                "volume_midrank_60": 0.7,
            },
            "evaluated_shadow",
        ),
        trace(
            "LIB-CAND-EMA-TREND-001",
            {
                "side_adjusted_ema50_vs_ema200_log": 0.01,
                "side_adjusted_slope_atr": 0.2,
            },
            "evaluated_shadow",
        ),
        trace(
            "LIB-CAND-ATR-EXTENSION-001",
            {"side_adjusted_extension_atr": -0.4},
            "evaluated_shadow",
        ),
        trace(
            "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
            {
                "nearest_support": {"price": 99},
                "nearest_resistance": {"price": 102},
                "target_path_level_count": 2,
                "adverse_path_level_count": 1,
            },
            "evaluated_shadow",
        ),
    ]


class CompositeRuleRuntimeTests(unittest.TestCase):
    def test_all_three_composites_emit_vectors_without_scores(self) -> None:
        rows = candles()
        result = evaluate_composite_rule_family(
            selected_candles=rows,
            current_bars=rows[-24:],
            return_count=24,
            side="long",
            analysis_at=ANALYSIS_AT,
            m5_analysis=m5_analysis(),
            observational_traces=observations(),
        )

        self.assertEqual(result["status"], "evaluated_shadow")
        self.assertEqual(result["evaluated_rule_count"], 3)
        traces = {item["rule_id"]: item for item in result["traces"]}
        self.assertIn(
            "compression_vector",
            traces["LIB-CAND-COMPRESSION-001"]["outputs"],
        )
        self.assertIn(
            "absorption_vector",
            traces["LIB-CAND-ABSORPTION-001"]["outputs"],
        )
        self.assertIn(
            "pullback_context_vector",
            traces["LIB-CAND-PULLBACK-CONTEXT-001"]["outputs"],
        )
        for item in result["traces"]:
            self.assertNotIn("score", item["outputs"])
            self.assertEqual(
                item["probability_effect"],
                "none_shadow_observation",
            )

    def test_missing_parent_blocks_only_dependent_composite(self) -> None:
        rows = candles()
        incomplete = [
            item
            for item in observations()
            if item["rule_id"]
            != "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
        ]
        result = evaluate_composite_rule_family(
            selected_candles=rows,
            current_bars=rows[-24:],
            return_count=24,
            side="short",
            analysis_at=ANALYSIS_AT,
            m5_analysis=m5_analysis(),
            observational_traces=incomplete,
        )

        self.assertEqual(result["status"], "partially_evaluated_shadow")
        by_id = {item["rule_id"]: item for item in result["traces"]}
        self.assertEqual(
            by_id["LIB-CAND-PULLBACK-CONTEXT-001"]["status"],
            "blocked",
        )
        self.assertEqual(
            by_id["LIB-CAND-COMPRESSION-001"]["status"],
            "evaluated_shadow",
        )
        self.assertEqual(
            by_id["LIB-CAND-ABSORPTION-001"]["status"],
            "evaluated_shadow",
        )


if __name__ == "__main__":
    unittest.main()
