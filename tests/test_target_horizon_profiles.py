from __future__ import annotations

import gzip
import json
import math
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from empirical_temporal_engine import (
    ENGINE_VERSION,
    SCORING_VERSION,
    canonical_sha256,
    empirical_probabilities,
    load_production_artifact,
    selected_stage_order,
)
from multiscale_feature_runtime import STAGE_ORDER


ROOT = Path(__file__).resolve().parents[1]
V010_PATH = ROOT / "auditorias_motor" / "motor_v0_10_empirical_analog.json.gz"


def v010_compatibility_artifact() -> dict:
    with gzip.open(V010_PATH, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    payload = deepcopy(payload)
    payload["engine_version"] = ENGINE_VERSION
    payload["scoring_version"] = SCORING_VERSION
    payload["target_horizon_rule_profiles"] = {
        target: {"profile": "v0_10_exact", "overrides": {}}
        for target in STAGE_ORDER
    }
    for analog in payload["analogs"]:
        analog["target_profile_feature_vectors"] = {}
    payload["active_rule_ids_by_target_horizon"] = {}
    for target in STAGE_ORDER:
        active = set()
        for stage in selected_stage_order(target):
            for name in payload["feature_names"][stage]:
                parts = str(name).split("::", 2)
                if len(parts) == 3:
                    active.add(parts[1])
        payload["active_rule_ids_by_target_horizon"][target] = sorted(active)
    payload.pop("artifact_sha256", None)
    payload["artifact_sha256"] = canonical_sha256(payload)
    return payload


def _merge_inverse_vector(
    contexts: dict[str, dict], names: list[str], scaling: list[list[float]], vector: list[float]
) -> None:
    for name, (center, scale), standardized in zip(names, scaling, vector):
        raw = float(center) + float(scale) * float(standardized)
        stage, feature = str(name).split("::", 1)
        if feature == "log_context_sigma":
            contexts[stage]["context_sigma"] = math.exp(raw)
        else:
            contexts[stage]["feature_values"][feature] = raw


def contexts_from_analog(artifact: dict, analog: dict, target: str) -> dict[str, dict]:
    contexts = {
        stage: {"context_sigma": None, "feature_values": {}}
        for stage in selected_stage_order(target)
    }
    for stage in selected_stage_order(target):
        stage_index = STAGE_ORDER.index(stage)
        _merge_inverse_vector(
            contexts,
            artifact["feature_names"][stage],
            artifact["feature_scaling"][stage],
            analog["feature_vectors"][stage_index][0],
        )
    profile = artifact["target_horizon_rule_profiles"][target]
    for override in profile["overrides"].values():
        _merge_inverse_vector(
            contexts,
            override["feature_names"],
            override["feature_scaling"],
            analog["target_profile_feature_vectors"][override["profile_id"]][0],
        )
    return contexts


def run(artifact: dict, target: str, contexts: dict[str, dict], analysis_at: str) -> dict:
    return empirical_probabilities(
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        take_profit=101.5,
        stop_loss=98.5,
        time_horizon=target,
        stage_contexts=contexts,
        analysis_at=analysis_at,
        artifact=artifact,
    )


class TargetHorizonProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.current = load_production_artifact()
        cls.v010 = v010_compatibility_artifact()
        cls.analog = max(
            cls.current["analogs"], key=lambda item: float(item["analysis_epoch"])
        )
        cls.analysis_at = (
            datetime.fromtimestamp(
                float(cls.analog["analysis_epoch"]), tz=timezone.utc
            )
            + timedelta(seconds=1)
        ).isoformat()

    def test_short_and_swing_point_estimates_are_exactly_v010(self) -> None:
        for target in ("intraday_short", "short_swing"):
            contexts = contexts_from_analog(self.current, self.analog, target)
            previous = run(self.v010, target, contexts, self.analysis_at)
            current = run(self.current, target, contexts, self.analysis_at)
            self.assertEqual(current["probabilities"], previous["probabilities"])
            self.assertEqual(current["probability_curve"], previous["probability_curve"])
            self.assertEqual(
                [trace["weighted_outcome_counts"] for trace in current["stage_traces"]],
                [trace["weighted_outcome_counts"] for trace in previous["stage_traces"]],
            )

    def test_medium_target_uses_only_its_validated_volume_override(self) -> None:
        target = "intraday_wide"
        contexts = contexts_from_analog(self.current, self.analog, target)
        current = run(self.current, target, contexts, self.analysis_at)
        self.assertFalse(
            current["stage_traces"][0]["target_horizon_specific_override"]
        )
        self.assertTrue(
            current["stage_traces"][1]["target_horizon_specific_override"]
        )
        self.assertEqual(
            current["stage_traces"][1]["active_probability_outputs"],
            {
                "LIB-CAND-RELATIVE-VOLUME-001": [
                    "log_relative_horizon_volume"
                ]
            },
        )
        self.assertEqual(
            self.current["target_horizon_rule_profiles"]["short_swing"][
                "overrides"
            ],
            {},
        )


if __name__ == "__main__":
    unittest.main()
