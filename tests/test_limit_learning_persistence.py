from __future__ import annotations

import json
import unittest
from pathlib import Path

from limit_activation_baseline import build_limit_activation_baseline
from limit_context_rule_runtime import evaluate_limit_context_rule_family
from limit_learning_persistence import (
    ALLOCATED_BYTES_PER_OPERATION,
    LIMIT_LEARNING_SNAPSHOT_VERSION,
    MAX_SELECTED_CASES_PER_UTC_DAY,
    SNAPSHOT_BYTE_BUDGETS,
    LimitLearningPersistenceError,
    build_activation_snapshot_record,
    build_closure_snapshot_record,
    build_placement_snapshot_record,
    persist_limit_learning_snapshot,
    projected_payload_bytes,
)
from limit_order_contract import (
    LIMIT_ORDER_CONTRACT_VERSION,
    LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES,
    LifecycleEvent,
    build_limit_order_contract,
    canonical_json,
    canonical_sha256,
)


def parent_trace(rule_id: str, outputs: dict, status: str = "evaluated") -> dict:
    return {
        "rule_id": rule_id,
        "status": status,
        "outputs": outputs,
        "trace_sha256": f"sha-{rule_id}",
    }


def contract() -> dict:
    return build_limit_order_contract(
        analysis_id="limit-persistence-test",
        symbol="BTCUSDT",
        side="long",
        time_horizon="intraday_short",
        analysis_at="2026-08-05T10:00:00+00:00",
        current_price=100,
        requested_entry=98,
        stop_loss=96,
        take_profit=103,
        trigger_condition="price_lte",
    )


def context_runtime(limit_contract: dict) -> dict:
    m5 = {
        "traces": [
            parent_trace(
                "M4-RULE-PATH-STRUCTURE-001",
                {
                    "signed_path_efficiency": -0.6,
                    "log_displacement": -0.02,
                },
            ),
            parent_trace(
                "M4-RULE-MTF-HIERARCHY-001",
                {
                    "signed_path_efficiencies": {
                        "H": -0.6,
                        "2H": -0.3,
                        "4H": 0.15,
                    }
                },
            ),
            parent_trace(
                "M4-RULE-VOLATILITY-RANK-001",
                {"volatility_percentile": 0.7},
            ),
            parent_trace(
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                {"ATI_H": -0.25},
            ),
            parent_trace(
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                {"dOI_H": 0.08},
            ),
            parent_trace(
                "M4-RULE-FUNDING-STATE-001",
                {"last_funding_rate": 0.0001},
            ),
        ]
    }
    observations = [
        parent_trace(
            "LIB-CAND-EMA-TREND-001",
            {"ema50_slope_6bars_atr": -0.3},
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-RSI-WILDER-001",
            {"centered_rsi": -0.2},
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-CVD-SLOPE-001",
            {
                "normalized_cvd_slope": -0.15,
                "terminal_taker_imbalance": -0.2,
            },
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-ORDERBOOK-IMBALANCE-001",
            {
                "spread_fraction": 0.0002,
                "measures": {"top_20": {"imbalance": -0.1}},
            },
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
            {
                "confirmed_pivot_count": 8,
                "nearest_support": {
                    "type": "low",
                    "price": 97.9,
                    "prominence_atr": 1.4,
                    "distance_sigma_horizon": -0.025,
                },
                "nearest_resistance": None,
                "target_path_level_count": 2,
                "adverse_path_level_count": 1,
                "strongest_target_path_prominence_atr": 1.8,
                "strongest_adverse_path_prominence_atr": 1.1,
            },
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-FIBONACCI-DISTANCE-001",
            {
                "nearest_to_entry": {
                    "set": "retracements",
                    "ratio": "0.618",
                    "price": 98.05,
                    "absolute_distance_sigma_horizon": 0.012,
                },
                "entry_retracement_fraction": 0.62,
            },
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-FUNDING-PERCENTILE-001",
            {"funding_midrank_60": 0.8},
            "evaluated_shadow",
        ),
        parent_trace(
            "LIB-CAND-CROWDING-PERCENTILE-001",
            {"centered_crowding_midrank_60": 0.4},
            "evaluated_shadow",
        ),
    ]
    liquidations = {
        "available": True,
        "status": "available",
        "provider": "hyperperps",
        "scope": "hyperliquid",
        "schema": "test-v1",
        "as_of": "2026-08-05T10:00:00+00:00",
        "age_seconds": 15,
        "clusters_below": [
            {
                "position_side": "long",
                "price": 99,
                "notional_usd": 1000,
                "wallet_count": 2,
            },
            {
                "position_side": "long",
                "price": 97,
                "notional_usd": 2000,
                "wallet_count": 3,
            },
        ],
        "clusters_above": [
            {
                "position_side": "short",
                "price": 101,
                "notional_usd": 3000,
                "wallet_count": 5,
            }
        ],
    }
    baseline = build_limit_activation_baseline(
        limit_contract,
        sigma_horizon=0.04,
    )
    return evaluate_limit_context_rule_family(
        limit_contract,
        baseline,
        m5_analysis=m5,
        observational_traces=observations,
        liquidation_context=liquidations,
    )


def placement_record(operation_id: int = 10) -> dict:
    limit_contract = contract()
    baseline = build_limit_activation_baseline(
        limit_contract,
        sigma_horizon=0.04,
    )
    return build_placement_snapshot_record(
        limit_contract,
        baseline,
        context_runtime(limit_contract),
        operation_id=operation_id,
        recommendation_id=20,
    )


def activation_values(operation_id: int = 10) -> dict:
    return {
        "contract_version": LIMIT_ORDER_CONTRACT_VERSION,
        "operation_id": operation_id,
        "activated_at": "2026-08-05T10:10:00+00:00",
        "data_cutoff_at": "2026-08-05T10:10:00+00:00",
        "outcome_expires_at": "2026-08-05T14:10:00+00:00",
        "evidence_source": "worker_tick",
        "requested_entry": 98,
        "trigger_observed_price": 97.99,
        "simulated_fill_price": 98,
        "seconds_to_activation": 600,
        "activation_feature_vector": {"distance_sigma": 0.5},
        "post_activation_feature_vector": {"trend": 0.2, "rsi": -0.1},
        "source_statuses": {"price": "available"},
    }


def closure_values(operation_id: int = 10) -> dict:
    return {
        "contract_version": LIMIT_ORDER_CONTRACT_VERSION,
        "operation_id": operation_id,
        "closed_at": "2026-08-05T11:00:00+00:00",
        "terminal_event": LifecycleEvent.TAKE_PROFIT.value,
        "learning_label": "activation_then_tp_first",
        "evidence_source": "worker_tick",
        "close_price": 103,
        "seconds_from_activation": 3000,
        "mfe_pct": 5.1,
        "mae_pct": -0.5,
        "economic_result": {"pnl": 10, "r_multiple": 2.5},
    }


class FakeCursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDb:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split()).lower()
        if "select id, payload_sha256, daily_slot" in normalized:
            operation_id, snapshot_type = params
            row = next(
                (
                    item
                    for item in self.rows
                    if item["operation_id"] == operation_id
                    and item["snapshot_type"] == snapshot_type
                ),
                None,
            )
            return FakeCursor(
                {
                    "id": row["id"],
                    "payload_sha256": row["payload_sha256"],
                    "daily_slot": row.get("daily_slot"),
                }
                if row
                else None
            )
        if "select id from limit_learning_snapshots" in normalized:
            operation_id = params[0]
            row = next(
                (
                    item
                    for item in self.rows
                    if item["operation_id"] == operation_id
                    and item["snapshot_type"] == "placement"
                ),
                None,
            )
            return FakeCursor({"id": row["id"]} if row else None)
        if "coalesce(max(daily_slot), 0)" in normalized:
            selected_day = params[0]
            used = max(
                (
                    int(item.get("daily_slot") or 0)
                    for item in self.rows
                    if item["snapshot_type"] == "placement"
                    and item.get("selected_case_day") == selected_day
                ),
                default=0,
            )
            return FakeCursor({"used_slots": used})
        if normalized.startswith("insert into limit_learning_snapshots"):
            if "on conflict" in normalized:
                raise AssertionError(
                    "append-only PostgreSQL tables reject INSERT ON CONFLICT"
                )
            (
                operation_id,
                recommendation_id,
                analysis_id,
                snapshot_type,
                schema_version,
                event_at,
                selected_day,
                daily_slot,
                symbol,
                side,
                time_horizon,
                learning_label,
                payload_sha256,
                payload_bytes,
                payload_json,
                production_effect,
            ) = params
            conflict = any(
                (
                    row["operation_id"] == operation_id
                    and row["snapshot_type"] == snapshot_type
                )
                or (
                    selected_day is not None
                    and row.get("selected_case_day") == selected_day
                    and row.get("daily_slot") == daily_slot
                )
                for row in self.rows
            )
            if conflict:
                return FakeCursor(None)
            row = {
                "id": self.next_id,
                "operation_id": operation_id,
                "recommendation_id": recommendation_id,
                "analysis_id": analysis_id,
                "snapshot_type": snapshot_type,
                "snapshot_schema_version": schema_version,
                "event_at": event_at,
                "selected_case_day": selected_day,
                "daily_slot": daily_slot,
                "symbol": symbol,
                "side": side,
                "time_horizon": time_horizon,
                "learning_label": learning_label,
                "payload_sha256": payload_sha256,
                "payload_bytes": payload_bytes,
                "payload_json": payload_json,
                "production_effect": production_effect,
            }
            self.rows.append(row)
            self.next_id += 1
            return FakeCursor({"id": row["id"], "daily_slot": daily_slot})
        raise AssertionError(f"unexpected_query:{normalized}")


class LimitLearningPersistenceTests(unittest.TestCase):
    def test_placement_is_compact_deterministic_and_raw_feed_free(self):
        first = placement_record()
        second = placement_record()
        payload = json.loads(first["payload_json"])

        self.assertEqual(first["payload_sha256"], second["payload_sha256"])
        self.assertLessEqual(
            first["payload_bytes"], SNAPSHOT_BYTE_BUDGETS["placement"]
        )
        self.assertNotIn("clusters_below", first["payload_json"])
        self.assertNotIn("order_book", payload)
        self.assertEqual(
            payload["context"]["rules"][
                "LIMIT-CAND-LIQUIDATION-PATH-001"
            ]["vector"]["approach"]["notional_usd"],
            1000,
        )

    def test_allocated_budget_is_below_original_contract_ceiling(self):
        self.assertEqual(ALLOCATED_BYTES_PER_OPERATION, 5888)
        self.assertLess(
            ALLOCATED_BYTES_PER_OPERATION,
            LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES,
        )

    def test_projection_for_fifty_cases_stays_bounded(self):
        annual = projected_payload_bytes(
            selected_cases_per_day=50,
            days=365,
        )

        self.assertEqual(annual, 107_456_000)
        self.assertLess(annual, 110 * 1024 * 1024)
        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "daily_selected_case_cap_exceeded",
        ):
            projected_payload_bytes(selected_cases_per_day=51, days=1)

    def test_activation_and_closure_have_independent_budgets(self):
        limit_contract = contract()
        activation = build_activation_snapshot_record(
            limit_contract,
            activation_values(),
            operation_id=10,
        )
        closure = build_closure_snapshot_record(
            limit_contract,
            closure_values(),
            operation_id=10,
        )

        self.assertLessEqual(
            activation["payload_bytes"], SNAPSHOT_BYTE_BUDGETS["activation"]
        )
        self.assertLessEqual(
            closure["payload_bytes"], SNAPSHOT_BYTE_BUDGETS["closure"]
        )
        self.assertEqual(
            closure["learning_label"], "activation_then_tp_first"
        )

    def test_lifecycle_snapshots_reject_raw_feeds(self):
        values = activation_values()
        values["post_activation_feature_vector"] = {
            "candles": [[1, 2, 3, 4]]
        }

        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "raw_feed_forbidden",
        ):
            build_activation_snapshot_record(
                contract(),
                values,
                operation_id=10,
            )

    def test_non_finite_feature_values_are_rejected(self):
        values = activation_values()
        values["post_activation_feature_vector"] = {"trend": float("nan")}

        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "non_finite_value",
        ):
            build_activation_snapshot_record(
                contract(),
                values,
                operation_id=10,
            )

    def test_closure_label_must_match_terminal_event(self):
        values = closure_values()
        values["learning_label"] = "activation_then_sl_first"

        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "closure_learning_label_mismatch",
        ):
            build_closure_snapshot_record(
                contract(),
                values,
                operation_id=10,
            )

    def test_persistence_is_idempotent_and_never_overwrites(self):
        db = FakeDb()
        record = placement_record()

        first = persist_limit_learning_snapshot(db, record)
        second = persist_limit_learning_snapshot(db, record)

        self.assertEqual(first["status"], "recorded")
        self.assertEqual(first["daily_slot"], 1)
        self.assertEqual(second["status"], "idempotent_skip")
        self.assertEqual(len(db.rows), 1)

        changed = dict(record)
        changed_payload = json.loads(changed["payload_json"])
        changed_payload["data_cutoff_at"] = "2026-08-05T09:59:00+00:00"
        changed["payload_json"] = canonical_json(changed_payload)
        changed["payload_bytes"] = len(changed["payload_json"].encode("utf-8"))
        changed["payload_sha256"] = canonical_sha256(changed_payload)
        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "snapshot_conflict_existing_payload",
        ):
            persist_limit_learning_snapshot(db, changed)

    def test_activation_requires_placement_but_closure_does_not_require_activation(self):
        db = FakeDb()
        activation = build_activation_snapshot_record(
            contract(),
            activation_values(),
            operation_id=10,
        )
        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "placement_snapshot_required",
        ):
            persist_limit_learning_snapshot(db, activation)

        persist_limit_learning_snapshot(db, placement_record())
        closure = build_closure_snapshot_record(
            contract(),
            closure_values(),
            operation_id=10,
        )
        result = persist_limit_learning_snapshot(db, closure)
        self.assertEqual(result["status"], "recorded")
        self.assertIsNone(result["daily_slot"])

    def test_daily_cap_blocks_placement_fifty_one(self):
        db = FakeDb()
        selected_day = "2026-08-05"
        for slot in range(1, MAX_SELECTED_CASES_PER_UTC_DAY + 1):
            db.rows.append(
                {
                    "id": slot,
                    "operation_id": 1000 + slot,
                    "snapshot_type": "placement",
                    "selected_case_day": selected_day,
                    "daily_slot": slot,
                    "payload_sha256": str(slot).zfill(64),
                }
            )

        with self.assertRaisesRegex(
            LimitLearningPersistenceError,
            "daily_selected_case_cap_reached",
        ):
            persist_limit_learning_snapshot(db, placement_record())

    def test_schema_enforces_budget_slots_and_append_only_rows(self):
        schema = Path("supabase/schema.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS limit_learning_snapshots", schema)
        self.assertIn("UNIQUE(operation_id, snapshot_type)", schema)
        self.assertIn("idx_limit_learning_daily_slot", schema)
        self.assertIn("WHERE snapshot_type = 'placement'", schema)
        self.assertIn("daily_slot BETWEEN 1 AND 50", schema)
        self.assertIn("AND daily_slot IS NOT NULL", schema)
        self.assertIn("WHEN 'placement' THEN 3584", schema)
        self.assertIn("snapshot_schema_version = 'limit-learning-snapshot-v0.1'", schema)
        self.assertIn("snapshot_type = 'closure' AND learning_label IS NOT NULL", schema)
        self.assertIn("limit_learning_snapshots_no_update", schema)
        self.assertIn("limit_learning_snapshots_no_delete", schema)

    def test_record_metadata_is_queryable_without_opening_payload(self):
        record = placement_record()

        self.assertEqual(record["snapshot_schema_version"], LIMIT_LEARNING_SNAPSHOT_VERSION)
        self.assertEqual(record["snapshot_type"], "placement")
        self.assertEqual(record["symbol"], "BTCUSDT")
        self.assertEqual(record["side"], "long")
        self.assertEqual(record["selected_case_day"], "2026-08-05")
        self.assertEqual(record["production_effect"], "none")


if __name__ == "__main__":
    unittest.main()
