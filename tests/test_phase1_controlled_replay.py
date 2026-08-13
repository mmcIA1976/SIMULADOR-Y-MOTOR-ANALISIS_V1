from __future__ import annotations

import math
import json
import unittest

import phase1_controlled_replay as replay


class Phase1ControlledReplayTests(unittest.TestCase):
    def test_month_range_is_closed_and_chronological(self) -> None:
        self.assertEqual(
            replay.month_range("2025-11", "2026-02"),
            ["2025-11", "2025-12", "2026-01", "2026-02"],
        )

    def test_chronological_partitions_keep_sealed_final_separate(self) -> None:
        def milliseconds(value: str) -> int:
            from datetime import datetime

            return int(datetime.fromisoformat(value).timestamp() * 1000)

        self.assertEqual(
            replay.partition_for_ms(milliseconds("2025-03-01T00:00:00+00:00")),
            "calibration",
        )
        self.assertEqual(
            replay.partition_for_ms(milliseconds("2025-09-01T00:00:00+00:00")),
            "rule_test",
        )
        self.assertEqual(
            replay.partition_for_ms(milliseconds("2026-03-01T00:00:00+00:00")),
            "final_test",
        )

    def test_aggregate_candles_requires_complete_bucket(self) -> None:
        values = []
        for index in range(12):
            values.append(
                {
                    "open_time_ms": index * 300_000,
                    "open": 100 + index,
                    "high": 102 + index,
                    "low": 99 + index,
                    "close": 101 + index,
                    "volume": 1.0,
                    "close_time_ms": (index + 1) * 300_000 - 1,
                    "quote_volume": 100.0,
                    "taker_buy_base_volume": 0.5,
                    "taker_buy_quote_volume": 50.0,
                }
            )
        aggregated = replay.aggregate_candles(values, 3600)
        self.assertEqual(len(aggregated), 1)
        self.assertEqual(aggregated[0]["open"], 100)
        self.assertEqual(aggregated[0]["close"], 112)
        self.assertEqual(aggregated[0]["volume"], 12.0)

    def test_first_touch_never_relabels_later_tp(self) -> None:
        future = [
            {"open_time_ms": 0, "high": 101, "low": 98},
            {"open_time_ms": 300_000, "high": 103, "low": 100},
        ]
        outcome = replay._outcome(
            future=future,
            side="long",
            take_profit=102,
            stop_loss=99,
        )
        self.assertEqual(outcome["label"], replay.CLASSES[1])

    def test_same_candle_double_touch_is_ambiguous(self) -> None:
        outcome = replay._outcome(
            future=[{"open_time_ms": 0, "high": 103, "low": 98}],
            side="long",
            take_profit=102,
            stop_loss=99,
        )
        self.assertEqual(outcome["status"], "ambiguous")
        self.assertIsNone(outcome["label"])

    def test_softmax_offset_preserves_probability_mass(self) -> None:
        row = {
            "baseline_probabilities": {
                replay.CLASSES[0]: 0.4,
                replay.CLASSES[1]: 0.3,
                replay.CLASSES[2]: 0.3,
            }
        }
        coefficients = {
            replay.CLASSES[0]: {"intercept": 0.2},
            replay.CLASSES[1]: {"intercept": -0.1},
        }
        result = replay.predict_softmax_offset(
            row,
            coefficients,
            {"intercept": 1.0},
        )
        self.assertAlmostEqual(math.fsum(result.values()), 1.0)
        self.assertTrue(all(0 <= value <= 1 for value in result.values()))

    def test_frozen_current_engine_probability_mass(self) -> None:
        artifact = json.loads(
            (
                replay.AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
            ).read_text(encoding="utf-8")
        )["coefficient_artifact"]
        row = {
            "tp_sigma_multiple": 1.0,
            "sl_sigma_multiple": 1.0,
            "rule_features": {
                "M4-RULE-PATH-STRUCTURE-001": {
                    "directional_path_efficiency_h": 0.1
                },
                "M4-RULE-MTF-HIERARCHY-001": {
                    "directional_path_efficiency_2h": 0.05,
                    "directional_path_efficiency_4h": -0.02,
                },
                "M4-RULE-VOLATILITY-RANK-001": {
                    "volatility_percentile_60": 0.5
                },
                "M4-RULE-PRIOR-EXTREMA-001": {
                    "target_extreme_between_entry_and_tp": 1.0
                },
            },
        }
        result = replay._current_engine_probabilities(row, artifact, {})
        self.assertAlmostEqual(math.fsum(result.values()), 1.0)
        self.assertTrue(all(0 < value < 1 for value in result.values()))

    def test_fit_sample_keeps_complete_episodes_and_is_deterministic(self) -> None:
        rows = [
            {"episode_id": f"episode-{episode}", "case_id": f"{episode}-{case}"}
            for episode in range(10)
            for case in range(3)
        ]
        first = replay.deterministic_episode_sample(rows, max_cases=10, seed=7)
        second = replay.deterministic_episode_sample(rows, max_cases=10, seed=7)
        self.assertEqual(first, second)
        counts = {}
        for row in first:
            counts[row["episode_id"]] = counts.get(row["episode_id"], 0) + 1
        self.assertTrue(counts)
        self.assertTrue(all(value == 3 for value in counts.values()))

    def test_benjamini_hochberg_adjustment_is_monotonic(self) -> None:
        adjusted = replay.benjamini_hochberg(
            [(0, 0.001), (1, 0.02), (2, 0.04), (3, 0.5)]
        )
        self.assertLessEqual(adjusted[0], adjusted[1])
        self.assertLessEqual(adjusted[1], adjusted[2])
        self.assertLessEqual(adjusted[2], adjusted[3])
        self.assertAlmostEqual(adjusted[0], 0.004)

    def test_joint_feature_names_keep_rule_provenance(self) -> None:
        names = replay.joint_feature_names(
            ["M4-RULE-PATH-STRUCTURE-001", "M4-RULE-MTF-HIERARCHY-001"]
        )
        self.assertEqual(len(names), 3)
        self.assertTrue(all("::" in name for name in names))
        self.assertEqual(len(names), len(set(names)))

    def test_paired_inference_clusters_correlated_symbols_by_time(self) -> None:
        rows = [
            {
                "case_id": symbol,
                "episode_id": f"{symbol}:short:1",
                "inference_cluster_id": "short:1",
                "outcome": {"label": replay.CLASSES[0]},
            }
            for symbol in ("BTCUSDT", "ETHUSDT")
        ]
        better = {
            symbol: {
                replay.CLASSES[0]: 0.8,
                replay.CLASSES[1]: 0.1,
                replay.CLASSES[2]: 0.1,
            }
            for symbol in ("BTCUSDT", "ETHUSDT")
        }
        worse = {
            symbol: {
                replay.CLASSES[0]: 0.5,
                replay.CLASSES[1]: 0.25,
                replay.CLASSES[2]: 0.25,
            }
            for symbol in ("BTCUSDT", "ETHUSDT")
        }
        result = replay.paired_episode_improvements(rows, better, worse)
        self.assertEqual(len(result), 1)

    def test_freeze_manifest_records_unapproved_original_artifact(self) -> None:
        result = replay.build_freeze_manifest()
        self.assertFalse(result["artifact_production_authorized_field"])
        self.assertIsNone(result["baseline_variant"]["coefficient_artifact"])


if __name__ == "__main__":
    unittest.main()
