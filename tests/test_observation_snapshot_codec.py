from __future__ import annotations

import base64
import copy
import hashlib
import json
import unittest
import zlib
from unittest.mock import patch

import operation_observation_learning as observations
from app import empirical_predictive_rule_learning_snapshot
from observation_snapshot_codec import (
    MAX_EXPANDED_TRACE_BYTES, TRACE_ENCODING, pack_rule_traces, snapshot_rule_traces,
)
from observational_learning_base import current_snapshot_rule_values
from observational_shadow_evaluation import ema_alignment_signal


RULE_IDS = ["M4-RULE-PATH-STRUCTURE-001","M4-RULE-MTF-HIERARCHY-001","M4-RULE-VOLATILITY-RANK-001","M4-RULE-AGGRESSOR-IMBALANCE-001","LIB-CAND-EMA-TREND-001","LIB-CAND-RSI-WILDER-001","LIB-CAND-ATR-EXTENSION-001","LIB-CAND-RELATIVE-VOLUME-001","LIB-CAND-CVD-SLOPE-001","LIB-CAND-ABSORPTION-001","LIB-CAND-COMPRESSION-001","M4-RULE-PRIOR-EXTREMA-001","LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001","LIB-CAND-FIBONACCI-DISTANCE-001","LIB-CAND-LIQUIDATION-ZONE-001","LIB-CAND-ORDERBOOK-IMBALANCE-001"]


def large_three_stage_snapshot():
    stages = ("intraday_short", "intraday_wide", "short_swing")
    snapshot = {
        "symbol": "BTCUSDT", "side": "short", "time_horizon": "short_swing",
        "entry": 84000.1, "take_profit": 82000.2, "stop_loss": 86000.3,
        "decision_probabilities": {"tp": 0.49, "sl": 0.50, "range": 0.01},
        "stage_rule_traces": {}, "stage_contexts": {},
        "probability_trace": {"stage_traces": []},
    }
    for stage in stages:
        features = {f"{stage}::M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h": 0.45}
        snapshot["probability_trace"]["stage_traces"].append({
            "time_horizon": stage, "current_feature_values": features,
            "active_rule_groups": ["path"],
        })
        snapshot["stage_rule_traces"][stage] = [
            {
                "rule_id": rule, "rule_version": "0.1", "status": "evaluated_shadow",
                "probability_effect": "none_observation_only",
                "source_data_sha256": "a" * 64, "trace_sha256": "b" * 64,
                "outputs": {
                    **{f"side_adjusted_measure_{i:03d}": i / 97.0 for i in range(65)},
                    "side_adjusted_close_vs_ema50_log": 0.14,
                    "side_adjusted_ema50_vs_ema200_log": 0.23,
                    "side_adjusted_slope_atr": -0.3456789012345678,
                },
            }
            for rule in RULE_IDS
        ]
    return snapshot


class ObservationSnapshotCodecTests(unittest.TestCase):
    def test_large_three_stage_case_fits_without_changing_learning(self):
        source = large_three_stage_snapshot()
        untouched = copy.deepcopy(source)
        with patch.object(observations, "pack_rule_traces", lambda value: value):
            with self.assertRaisesRegex(ValueError, "compact_snapshot_too_large"):
                observations.compact_observation_snapshot(source)
            with patch.object(observations, "MAX_COMPACT_SNAPSHOT_BYTES", 1_000_000):
                previous = observations.compact_observation_snapshot(source)
        compact = observations.compact_observation_snapshot(source)
        self.assertEqual(source, untouched)
        self.assertLess(len(observations.canonical_json(compact).encode()), 30_000)
        self.assertEqual(snapshot_rule_traces(compact), previous["stage_rule_traces"])
        self.assertEqual(compact["decision_probabilities"], source["decision_probabilities"])
        self.assertEqual(compact["stage_contexts"], previous["stage_contexts"])
        self.assertEqual(compact["probability_trace"], previous["probability_trace"])
        self.assertEqual(
            observations.observation_rule_signals(compact),
            observations.observation_rule_signals(previous),
        )
        self.assertEqual(
            empirical_predictive_rule_learning_snapshot(compact, plan_result="plan_success"),
            empirical_predictive_rule_learning_snapshot(previous, plan_result="plan_success"),
        )
        def row(snapshot):
            return {"snapshot_json": json.dumps(snapshot), "time_horizon": "short_swing"}
        self.assertIsNotNone(ema_alignment_signal(row(compact)))
        self.assertEqual(ema_alignment_signal(row(compact)), ema_alignment_signal(row(previous)))
        specs = [{"rule_id": "LIB-CAND-EMA-TREND-001", "selected_variable": "side_adjusted_slope_atr"}]
        args = dict(side="short", time_horizon="short_swing", baseline_specs=specs)
        self.assertEqual(
            current_snapshot_rule_values(compact, **args),
            current_snapshot_rule_values(previous, **args),
        )
        self.assertIs(observations.compact_observation_snapshot(compact), compact)

    def test_round_trip_keeps_exact_numbers_unicode_and_legacy_format(self):
        traces = {"intraday_short": [{"outputs": {"señal": 1.2345678901234567, "n": None, "ok": True, "repeated": "x" * 3000}}]}
        encoded = pack_rule_traces(traces)
        self.assertEqual(encoded["encoding"], TRACE_ENCODING)
        self.assertEqual(snapshot_rule_traces({"stage_rule_traces": encoded}), traces)
        self.assertIs(snapshot_rule_traces({"stage_rule_traces": traces}), traces)
        self.assertEqual(snapshot_rule_traces({}), {})

    def test_corrupt_evidence_is_not_silently_dropped(self):
        encoded = pack_rule_traces({"a": [{"outputs": {"text": "x" * 3000}}]})
        for updates in ({"sha256": "0" * 64}, {"data": "!bad!"}, {"uncompressed_bytes": 1}, {"encoding": "unknown"}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                snapshot_rule_traces({"stage_rule_traces": {**encoded, **updates}})

    def test_decoder_enforces_expanded_size_not_only_declared_size(self):
        raw = b"x" * (MAX_EXPANDED_TRACE_BYTES + 1)
        encoded = {
            "encoding": TRACE_ENCODING, "uncompressed_bytes": 100,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "data": base64.b64encode(zlib.compress(raw)).decode(),
        }
        with self.assertRaisesRegex(ValueError, "payload_invalid"):
            snapshot_rule_traces({"stage_rule_traces": encoded})

    def test_snapshot_size_limit_cannot_be_bypassed_by_existing_profile(self):
        source = {"storage_profile": observations.OBSERVATION_STORAGE_PROFILE, "extra": "x" * 48_001}
        with self.assertRaisesRegex(ValueError, "compact_snapshot_too_large"):
            observations.compact_observation_snapshot(source)

    def test_compressed_stream_must_be_complete_and_without_trailing_data(self):
        encoded = pack_rule_traces({"a": [{"outputs": {"text": "x" * 3000}}]})
        raw = base64.b64decode(encoded["data"])
        for invalid in (raw[:-1], raw + b"extra"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                snapshot_rule_traces({"stage_rule_traces": {**encoded, "data": base64.b64encode(invalid).decode()}})


if __name__ == "__main__":
    unittest.main()
