from __future__ import annotations

import copy
import math
import unittest

from multiscale_feature_runtime import FLAT_FEATURE_NAMES, STAGE_ORDER
from sequential_temporal_engine import (
    CUMULATIVE_CLASSES,
    ENGINE_VERSION,
    load_production_artifact,
    selected_stage_order,
    sequential_probabilities,
)


def context(horizon: str, sigma: float, value: float = 0.0) -> dict:
    return {
        "time_horizon": horizon,
        "context_sigma": sigma,
        "feature_values": {name: value for name in FLAT_FEATURE_NAMES},
        "source_data_sha256": f"source-{horizon}",
    }


class SequentialTemporalEngineTests(unittest.TestCase):
    def test_selected_stage_order_is_strictly_cumulative(self) -> None:
        self.assertEqual(selected_stage_order("intraday_short"), STAGE_ORDER[:1])
        self.assertEqual(selected_stage_order("intraday_wide"), STAGE_ORDER[:2])
        self.assertEqual(selected_stage_order("short_swing"), STAGE_ORDER)

    def test_artifact_is_frozen_and_single_engine(self) -> None:
        artifact = load_production_artifact()
        self.assertEqual(artifact["engine_version"], ENGINE_VERSION)
        self.assertTrue(artifact["production_authorized"])
        self.assertTrue(artifact["single_engine"])
        self.assertEqual(artifact["parallel_probability_engines"], 0)

    def test_curve_preserves_first_touch_and_probability_mass(self) -> None:
        contexts = {
            "intraday_short": context("intraday_short", 0.008),
            "intraday_wide": context("intraday_wide", 0.018),
            "short_swing": context("short_swing", 0.045),
        }
        result = sequential_probabilities(
            side="long",
            entry=100.0,
            take_profit=102.0,
            stop_loss=98.5,
            time_horizon="short_swing",
            stage_contexts=contexts,
        )
        self.assertEqual(result["executed_stages"], list(STAGE_ORDER))
        self.assertEqual(result["executed_stage_count"], 3)
        previous_tp = previous_sl = 0.0
        previous_expiry = 1.0
        for horizon in STAGE_ORDER:
            probabilities = result["probability_curve"][horizon]
            self.assertAlmostEqual(math.fsum(probabilities.values()), 1.0, places=12)
            self.assertGreaterEqual(
                probabilities[CUMULATIVE_CLASSES[0]] + 1e-12, previous_tp
            )
            self.assertGreaterEqual(
                probabilities[CUMULATIVE_CLASSES[1]] + 1e-12, previous_sl
            )
            self.assertLessEqual(
                probabilities[CUMULATIVE_CLASSES[2]], previous_expiry + 1e-12
            )
            previous_tp = probabilities[CUMULATIVE_CLASSES[0]]
            previous_sl = probabilities[CUMULATIVE_CLASSES[1]]
            previous_expiry = probabilities[CUMULATIVE_CLASSES[2]]
        for trace in result["stage_traces"]:
            self.assertAlmostEqual(
                math.fsum(trace["conditional_probabilities"].values()),
                1.0,
                places=12,
            )

    def test_later_context_cannot_rewrite_earlier_horizons(self) -> None:
        first_contexts = {
            "intraday_short": context("intraday_short", 0.008),
            "intraday_wide": context("intraday_wide", 0.018),
            "short_swing": context("short_swing", 0.035),
        }
        second_contexts = copy.deepcopy(first_contexts)
        second_contexts["short_swing"] = context(
            "short_swing", 0.080, value=3.0
        )
        first = sequential_probabilities(
            side="short",
            entry=100.0,
            take_profit=98.0,
            stop_loss=101.5,
            time_horizon="short_swing",
            stage_contexts=first_contexts,
        )
        second = sequential_probabilities(
            side="short",
            entry=100.0,
            take_profit=98.0,
            stop_loss=101.5,
            time_horizon="short_swing",
            stage_contexts=second_contexts,
        )
        self.assertEqual(
            first["probability_curve"]["intraday_short"],
            second["probability_curve"]["intraday_short"],
        )
        self.assertEqual(
            first["probability_curve"]["intraday_wide"],
            second["probability_curve"]["intraday_wide"],
        )
        self.assertNotEqual(
            first["probability_curve"]["short_swing"],
            second["probability_curve"]["short_swing"],
        )

    def test_medium_horizon_executes_short_and_medium_only(self) -> None:
        contexts = {
            "intraday_short": context("intraday_short", 0.008),
            "intraday_wide": context("intraday_wide", 0.018),
        }
        result = sequential_probabilities(
            side="long",
            entry=100.0,
            take_profit=102.0,
            stop_loss=98.5,
            time_horizon="intraday_wide",
            stage_contexts=contexts,
        )
        self.assertEqual(
            list(result["probability_curve"]),
            ["intraday_short", "intraday_wide"],
        )
        self.assertEqual(result["executed_stage_count"], 2)


if __name__ == "__main__":
    unittest.main()
