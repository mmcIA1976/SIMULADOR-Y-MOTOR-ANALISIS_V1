from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from counterfactual_learning import (
    COUNTERFACTUAL_EVALUATOR_VERSION,
    LEGACY_PROXY_EVALUATOR_VERSION,
    build_counterfactual_payload,
    evaluate_counterfactual_records,
    normalize_legacy_market_recommendation,
    normalize_unlinked_recommendation,
    persist_counterfactual_payload,
)


CAPTURED_AT = datetime(2026, 8, 12, tzinfo=timezone.utc)


def valid_row() -> dict:
    return {
        "recommendation_id": 101,
        "operation_id": None,
        "user_id": 7,
        "symbol": "BTCUSDT",
        "side": "long",
        "time_horizon": "intraday_short",
        "tp_probability": 0.5,
        "sl_probability": 0.3,
        "range_probability": 0.2,
        "engine_version": "TP-SL-PROBABILITY-ENGINE-v0.6-stable-global",
        "scoring_version": "m6-global-frozen-champion-v0.6",
        "snapshot_json": json.dumps(
            {
                "symbol": "BTCUSDT",
                "side": "long",
                "time_horizon": "intraday_short",
                "entry": 100.0,
                "take_profit": 110.0,
                "stop_loss": 95.0,
                "analysis_at": "2026-08-01T10:00:00+00:00",
                "data_cutoff_at": "2026-08-01T09:59:59+00:00",
                "evaluation_expires_at": "2026-08-01T14:00:00+00:00",
                "evaluation_horizon_seconds": 14400,
                "entry_order_context": {"entry_type": "market"},
            }
        ),
    }


def valid_legacy_row() -> dict:
    row = valid_row()
    row["engine_version"] = "rules-v0.11-underweighted-risk-cluster"
    row["scoring_version"] = None
    row["created_at"] = "2026-07-15T10:00:00+00:00"
    snapshot = json.loads(row["snapshot_json"])
    for key in (
        "analysis_at",
        "data_cutoff_at",
        "evaluation_expires_at",
        "evaluation_horizon_seconds",
        "entry",
        "take_profit",
        "stop_loss",
    ):
        snapshot.pop(key, None)
    snapshot["entry_order_context"] = {
        "entry_type": "market",
        "requested_entry": 100.0,
    }
    snapshot["risk_distance_pct"] = 5.0
    snapshot["reward_distance_pct"] = 10.0
    snapshot["risk_reward_ratio"] = 2.0
    row["snapshot_json"] = json.dumps(snapshot)
    return row


class CounterfactualLearningTests(unittest.TestCase):
    def test_schema_uses_trigger_compatible_with_on_conflict(self) -> None:
        schema = (
            Path(__file__).resolve().parents[1] / "supabase" / "schema.sql"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "recommendation_counterfactual_evaluations_append_only",
            schema,
        )
        self.assertIn(
            "prevent_counterfactual_evaluation_mutation",
            schema,
        )
        self.assertNotIn(
            "CREATE RULE recommendation_counterfactual_evaluations_no_update",
            schema,
        )

    def test_normalizes_exact_matured_market_contract(self) -> None:
        record, rejection = normalize_unlinked_recommendation(
            valid_row(),
            captured_at=CAPTURED_AT,
        )
        self.assertIsNone(rejection)
        self.assertEqual(record["recommendation_id"], 101)
        self.assertEqual(record["horizon_seconds"], 14400)
        self.assertEqual(record["entry"], 100.0)

    def test_accepts_six_decimal_probability_rounding(self) -> None:
        row = valid_row()
        row["tp_probability"] = 0.131048
        row["sl_probability"] = 0.453986
        row["range_probability"] = 0.414967
        record, rejection = normalize_unlinked_recommendation(
            row,
            captured_at=CAPTURED_AT,
        )
        self.assertIsNone(rejection)
        self.assertIsNotNone(record)

    def test_reconstructs_legacy_plan_but_keeps_it_non_formal(self) -> None:
        record, rejection = normalize_legacy_market_recommendation(
            valid_legacy_row(),
            captured_at=CAPTURED_AT,
        )
        self.assertIsNone(rejection)
        self.assertEqual(record["entry"], 100.0)
        self.assertAlmostEqual(record["take_profit"], 110.0)
        self.assertAlmostEqual(record["stop_loss"], 95.0)
        self.assertEqual(record["horizon_seconds"], 14400)
        self.assertEqual(
            record["contract_quality"],
            "legacy_upper_bound_proxy",
        )
        self.assertFalse(record["formal_learning_eligible"])
        self.assertEqual(
            record["evaluator_version"],
            LEGACY_PROXY_EVALUATOR_VERSION,
        )

    def test_legacy_plan_requires_requested_entry(self) -> None:
        row = valid_legacy_row()
        snapshot = json.loads(row["snapshot_json"])
        snapshot["entry_order_context"].pop("requested_entry")
        row["snapshot_json"] = json.dumps(snapshot)
        record, rejection = normalize_legacy_market_recommendation(
            row,
            captured_at=CAPTURED_AT,
        )
        self.assertIsNone(record)
        self.assertEqual(rejection, "legacy_requested_entry_missing")

    def test_legacy_payload_carries_non_formal_provenance(self) -> None:
        record, _ = normalize_legacy_market_recommendation(
            valid_legacy_row(),
            captured_at=CAPTURED_AT,
        )
        record["pretrade"] = {
            "status": "evaluated",
            "interval": "5m",
            "feature_values": {},
        }
        record["outcome"] = {
            "status": "resolved",
            "label": "tp_first_within_horizon",
            "first_touch_at": "2026-07-15T10:10:00+00:00",
            "coverage_ratio": 1.0,
            "candle_count": 241,
            "expected_candle_count": 241,
            "market_sha256": "e" * 64,
        }
        payload = build_counterfactual_payload(record)
        self.assertEqual(
            payload["contract_quality"],
            "legacy_upper_bound_proxy",
        )
        self.assertFalse(payload["formal_learning_eligible"])
        self.assertEqual(
            payload["analysis_at_source"],
            "recommendations.created_at_proxy",
        )

    def test_rejects_limit_contract(self) -> None:
        row = valid_row()
        snapshot = json.loads(row["snapshot_json"])
        snapshot["entry_order_context"]["entry_type"] = "pending"
        row["snapshot_json"] = json.dumps(snapshot)
        record, rejection = normalize_unlinked_recommendation(
            row,
            captured_at=CAPTURED_AT,
        )
        self.assertIsNone(record)
        self.assertEqual(rejection, "entry_type_not_market")

    def test_rejects_not_matured_contract(self) -> None:
        row = valid_row()
        snapshot = json.loads(row["snapshot_json"])
        snapshot["analysis_at"] = "2026-08-12T10:00:00+00:00"
        snapshot["data_cutoff_at"] = "2026-08-12T09:59:59+00:00"
        snapshot["evaluation_expires_at"] = "2026-08-12T14:00:00+00:00"
        row["snapshot_json"] = json.dumps(snapshot)
        record, rejection = normalize_unlinked_recommendation(
            row,
            captured_at=datetime(2026, 8, 12, 11, tzinfo=timezone.utc),
        )
        self.assertIsNone(record)
        self.assertEqual(rejection, "not_matured")

    def test_evaluation_uses_injected_enrichers(self) -> None:
        record, _ = normalize_unlinked_recommendation(
            valid_row(),
            captured_at=CAPTURED_AT,
        )

        def add_features(records):
            records[0]["pretrade"] = {
                "status": "evaluated",
                "interval": "5m",
                "feature_values": {"volatility_percentile_60": 0.7},
            }
            return records

        def add_outcome(records, *, captured_at):
            records[0]["outcome"] = {
                "status": "resolved",
                "label": "tp_first_within_horizon",
                "first_touch_at": captured_at.isoformat(),
                "coverage_ratio": 1.0,
                "candle_count": 241,
                "expected_candle_count": 241,
                "market_sha256": "a" * 64,
            }
            return records

        evaluated = evaluate_counterfactual_records(
            [record],
            captured_at=CAPTURED_AT,
            pretrade_enricher=add_features,
            outcome_enricher=add_outcome,
        )
        payload = build_counterfactual_payload(evaluated[0])
        self.assertEqual(payload["evaluation_status"], "evaluated")
        self.assertEqual(
            payload["outcome_label"],
            "tp_first_within_horizon",
        )
        self.assertEqual(
            payload["evaluator_version"],
            COUNTERFACTUAL_EVALUATOR_VERSION,
        )
        self.assertLess(payload["feature_payload_bytes"], 4096)

    def test_ambiguous_outcome_is_excluded_not_forced(self) -> None:
        record, _ = normalize_unlinked_recommendation(
            valid_row(),
            captured_at=CAPTURED_AT,
        )
        record["pretrade"] = {
            "status": "evaluated",
            "interval": "5m",
            "feature_values": {},
        }
        record["outcome"] = {
            "status": "ambiguous_same_minute",
            "label": None,
            "first_touch_at": "2026-08-01T10:05:00+00:00",
            "coverage_ratio": 1.0,
            "candle_count": 241,
            "expected_candle_count": 241,
            "market_sha256": "b" * 64,
        }
        payload = build_counterfactual_payload(record)
        self.assertEqual(payload["evaluation_status"], "excluded")
        self.assertEqual(
            payload["exclusion_code"],
            "outcome_ambiguous_same_minute",
        )
        self.assertIsNone(payload["outcome_label"])

    def test_exact_outcome_survives_missing_reconstructed_features(self) -> None:
        record, _ = normalize_unlinked_recommendation(
            valid_row(),
            captured_at=CAPTURED_AT,
        )
        record["pretrade"] = {
            "status": "insufficient_pretrade_history",
            "feature_values": {},
        }
        record["outcome"] = {
            "status": "resolved",
            "label": "sl_first_within_horizon",
            "first_touch_at": "2026-08-01T10:10:00+00:00",
            "coverage_ratio": 1.0,
            "candle_count": 241,
            "expected_candle_count": 241,
            "market_sha256": "c" * 64,
        }
        payload = build_counterfactual_payload(record)
        self.assertEqual(payload["evaluation_status"], "evaluated")
        self.assertEqual(payload["outcome_label"], "sl_first_within_horizon")
        self.assertEqual(
            payload["pretrade_status"],
            "insufficient_pretrade_history",
        )

    def test_persistence_is_idempotent_and_checks_hashes(self) -> None:
        class Cursor:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class FakeDb:
            def __init__(self):
                self.existing = None

            def execute(self, query, params):
                if "INSERT INTO" in query:
                    if self.existing:
                        return Cursor(None)
                    columns = [
                        value.strip()
                        for value in query.split("(", 1)[1]
                        .split(")", 1)[0]
                        .split(",")
                    ]
                    values = dict(zip(columns, params))
                    self.existing = {
                        "run_key": values["run_key"],
                        "source_snapshot_sha256": values[
                            "source_snapshot_sha256"
                        ],
                        "result_sha256": values["result_sha256"],
                    }
                    return Cursor({"id": 1})
                return Cursor(self.existing)

        record, _ = normalize_unlinked_recommendation(
            valid_row(),
            captured_at=CAPTURED_AT,
        )
        record["pretrade"] = {
            "status": "evaluated",
            "interval": "5m",
            "feature_values": {},
        }
        record["outcome"] = {
            "status": "resolved",
            "label": "tp_first_within_horizon",
            "first_touch_at": "2026-08-01T10:10:00+00:00",
            "coverage_ratio": 1.0,
            "candle_count": 241,
            "expected_candle_count": 241,
            "market_sha256": "d" * 64,
        }
        payload = build_counterfactual_payload(record)
        db = FakeDb()
        self.assertTrue(persist_counterfactual_payload(db, payload))
        self.assertFalse(persist_counterfactual_payload(db, payload))


if __name__ == "__main__":
    unittest.main()
