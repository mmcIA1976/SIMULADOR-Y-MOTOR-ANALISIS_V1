from __future__ import annotations

import copy
import math
import unittest

from empirical_temporal_engine import (
    CUMULATIVE_CLASSES,
    ENGINE_VERSION,
    EmpiricalTemporalEngineError,
    canonical_sha256,
    empirical_probabilities,
    selected_stage_order,
)
from multiscale_feature_runtime import STAGE_ORDER, STAGE_PROFILES


FEATURE = "synthetic_feature"


def context(horizon: str, value: float = 0.0) -> dict:
    return {
        "time_horizon": horizon,
        "context_sigma": 0.02,
        "feature_values": {FEATURE: value},
    }


def artifact() -> dict:
    names = {
        horizon: [
            f"{stage}::{FEATURE}"
            for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
        ]
        for horizon in STAGE_ORDER
    }
    analogs = []
    for index in range(8):
        feature_vectors = []
        for horizon in STAGE_ORDER:
            width = len(names[horizon])
            feature_vectors.append([[0.0] * width, [5.0] * width])
        analogs.append(
            {
                "id": f"analog-{index}",
                "symbol": "BTCUSDT",
                "analysis_at": f"2025-01-{index + 1:02d}T00:00:00+00:00",
                "analysis_epoch": 1_735_689_600.0 + index * 86_400.0,
                # For a long, the farther downside barrier is observed first.
                "up_frontier": [[0.005, 12], [0.04, 120]],
                "down_frontier": [[0.03, 10]],
                "feature_vectors": feature_vectors,
            }
        )
    payload = {
        "artifact_id": "synthetic-empirical-v0.9",
        "engine_version": ENGINE_VERSION,
        "scoring_version": "historical-analog-first-touch-v0.9",
        "build_version": "test",
        "status": "frozen_production",
        "production_authorized": True,
        "single_engine": True,
        "parallel_probability_engines": 0,
        "automatic_weight_updates": False,
        "stage_order": list(STAGE_ORDER),
        "stage_profiles": {name: dict(STAGE_PROFILES[name]) for name in STAGE_ORDER},
        "active_rule_groups": ["synthetic"],
        "rule_group_features": {"synthetic": [FEATURE]},
        "excluded_unvalidated_rules": {},
        "feature_names": names,
        "feature_scaling": {
            horizon: [[0.0, 1.0] for _ in values]
            for horizon, values in names.items()
        },
        "selection": {
            "neighbor_count": 8,
            "minimum_analogs": 4,
            "maximum_scanned": 100,
            "cross_symbol_penalty": 0.15,
            "recency_penalty_per_year": 0.0,
            "maximum_nearest_context_distance_by_horizon": {
                horizon: 2.0 for horizon in STAGE_ORDER
            },
        },
        "historical_source": "synthetic",
        "historical_coverage": {"records": len(analogs)},
        "analogs": analogs,
    }
    payload["artifact_sha256"] = canonical_sha256(payload)
    return payload


def run(*, horizon: str = "short_swing", contexts: dict | None = None) -> dict:
    selected = selected_stage_order(horizon)
    return empirical_probabilities(
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        take_profit=101.0,
        stop_loss=98.0,
        time_horizon=horizon,
        stage_contexts=contexts
        or {stage: context(stage) for stage in selected},
        analysis_at="2026-01-01T00:00:00+00:00",
        artifact=artifact(),
    )


class EmpiricalTemporalEngineTests(unittest.TestCase):
    def test_selected_stage_order_is_strictly_cumulative(self) -> None:
        self.assertEqual(selected_stage_order("intraday_short"), STAGE_ORDER[:1])
        self.assertEqual(selected_stage_order("intraday_wide"), STAGE_ORDER[:2])
        self.assertEqual(selected_stage_order("short_swing"), STAGE_ORDER)

    def test_observed_paths_override_closer_barrier_heuristic(self) -> None:
        result = run(horizon="intraday_short")
        probabilities = result["probabilities"]
        self.assertGreater(
            probabilities["sl_first_within_horizon"],
            probabilities["tp_first_within_horizon"],
        )
        self.assertFalse(
            result["stage_traces"][0]["geometry_application"][
                "coefficient_or_distance_heuristic"
            ]
        )

    def test_curve_preserves_first_touch_and_probability_mass(self) -> None:
        result = run()
        previous_tp = previous_sl = 0.0
        previous_expiry = 1.0
        for horizon in STAGE_ORDER:
            probabilities = result["probability_curve"][horizon]
            self.assertAlmostEqual(math.fsum(probabilities.values()), 1.0, places=12)
            self.assertGreaterEqual(probabilities[CUMULATIVE_CLASSES[0]], previous_tp)
            self.assertGreaterEqual(probabilities[CUMULATIVE_CLASSES[1]], previous_sl)
            self.assertLessEqual(probabilities[CUMULATIVE_CLASSES[2]], previous_expiry)
            previous_tp = probabilities[CUMULATIVE_CLASSES[0]]
            previous_sl = probabilities[CUMULATIVE_CLASSES[1]]
            previous_expiry = probabilities[CUMULATIVE_CLASSES[2]]

    def test_later_context_cannot_rewrite_earlier_horizons(self) -> None:
        contexts = {stage: context(stage) for stage in STAGE_ORDER}
        changed = copy.deepcopy(contexts)
        changed["short_swing"] = context("short_swing", 0.5)
        first = run(contexts=contexts)
        second = run(contexts=changed)
        self.assertEqual(
            first["probability_curve"]["intraday_short"],
            second["probability_curve"]["intraday_short"],
        )
        self.assertEqual(
            first["probability_curve"]["intraday_wide"],
            second["probability_curve"]["intraday_wide"],
        )

    def test_uncertainty_is_not_a_fake_point_range(self) -> None:
        ranges = run(horizon="intraday_short")["probability_ranges_95pct"]
        self.assertTrue(
            all(item["low"] < item["high"] for item in ranges.values())
        )

    def test_out_of_historical_context_blocks(self) -> None:
        with self.assertRaisesRegex(
            EmpiricalTemporalEngineError, "context_outside_historical_support"
        ):
            run(
                horizon="intraday_short",
                contexts={"intraday_short": context("intraday_short", 20.0)},
            )


if __name__ == "__main__":
    unittest.main()
