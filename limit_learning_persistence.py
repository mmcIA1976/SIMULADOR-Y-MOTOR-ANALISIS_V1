from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping

from limit_activation_baseline import LIMIT_ACTIVATION_MODEL_VERSION
from limit_context_rule_runtime import RULE_IDS, RUNTIME_VERSION
from limit_order_contract import (
    ACTIVATION_SNAPSHOT_FIELDS,
    CLOSURE_SNAPSHOT_FIELDS,
    LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES,
    LIMIT_ORDER_ANALYSIS_FAMILY,
    LIMIT_ORDER_CONTRACT_VERSION,
    LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY,
    LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES,
    LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS,
    PLACEMENT_SNAPSHOT_FIELDS,
    canonical_json,
    canonical_sha256,
    learning_label_for_terminal_event,
)


LIMIT_LEARNING_SNAPSHOT_VERSION = "limit-learning-snapshot-v0.1"
SNAPSHOT_TYPES = ("placement", "activation", "closure")
SNAPSHOT_BYTE_BUDGETS = dict(LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS)
MAX_SELECTED_CASES_PER_UTC_DAY = (
    LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY
)
ALLOCATED_BYTES_PER_OPERATION = LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES
PERSISTENCE_PRODUCTION_EFFECT = "none"

FORBIDDEN_RAW_FEED_KEYS = frozenset(
    {
        "asks",
        "bids",
        "candles",
        "clusters",
        "clusters_above",
        "clusters_below",
        "klines",
        "liquidation_heatmap",
        "order_book",
        "orderbook",
        "raw_candles",
        "raw_clusters",
        "raw_klines",
        "raw_liquidation_heatmap",
        "raw_order_book",
        "raw_orderbook",
        "raw_trades",
    }
)


class LimitLearningPersistenceError(ValueError):
    pass


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise LimitLearningPersistenceError(f"{name}_must_be_positive_int")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise LimitLearningPersistenceError(
            f"{name}_must_be_positive_int"
        ) from exc
    if parsed <= 0 or parsed != value:
        raise LimitLearningPersistenceError(f"{name}_must_be_positive_int")
    return parsed


def _optional_positive_int(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, name)


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise LimitLearningPersistenceError(f"{name}_must_be_finite")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise LimitLearningPersistenceError(f"{name}_must_be_finite") from exc
    if not math.isfinite(parsed):
        raise LimitLearningPersistenceError(f"{name}_must_be_finite")
    return parsed


def _utc_iso(value: Any, name: str) -> str:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LimitLearningPersistenceError(f"invalid_{name}") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise LimitLearningPersistenceError(f"invalid_{name}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LimitLearningPersistenceError(f"{name}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc).isoformat()


def _forbidden_raw_path(value: object, path: str = "payload") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            child_path = f"{path}.{key}"
            if normalized in FORBIDDEN_RAW_FEED_KEYS:
                return child_path
            nested = _forbidden_raw_path(child, child_path)
            if nested:
                return nested
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            nested = _forbidden_raw_path(child, f"{path}[{index}]")
            if nested:
                return nested
    return None


def _compact_json_value(value: object, path: str = "payload") -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise LimitLearningPersistenceError(f"non_finite_value:{path}")
        return float(format(value, ".12g"))
    if isinstance(value, Mapping):
        return {
            str(key): _compact_json_value(child, f"{path}.{key}")
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _compact_json_value(child, f"{path}[{index}]")
            for index, child in enumerate(value)
        ]
    raise LimitLearningPersistenceError(
        f"unsupported_payload_value:{path}:{type(value).__name__}"
    )


def _trace_map(context_runtime: Mapping[str, Any]) -> dict[str, dict]:
    traces = context_runtime.get("traces")
    if not isinstance(traces, list):
        raise LimitLearningPersistenceError("context_traces_required")
    return {
        str(trace.get("rule_id")): trace
        for trace in traces
        if isinstance(trace, dict) and trace.get("rule_id")
    }


def _dual_vector(value: object) -> list[float | None] | None:
    if not isinstance(value, Mapping):
        return None
    result = []
    for key in ("raw", "activation_adjusted", "reaction_adjusted"):
        item = value.get(key)
        result.append(_finite(item, key) if item is not None else None)
    return result


def _compact_liquidation_summary(value: object) -> dict | None:
    if not isinstance(value, Mapping):
        return None
    nearest = value.get("nearest_to_entry")
    compact_nearest = None
    if isinstance(nearest, Mapping):
        compact_nearest = {
            "side": nearest.get("position_side"),
            "price": nearest.get("price"),
            "notional_usd": nearest.get("notional_usd"),
            "distance_log_sigma": nearest.get(
                "distance_from_entry_abs_log_sigma"
            ),
        }
    return {
        "count": value.get("cluster_count"),
        "notional_usd": value.get("visible_notional_usd"),
        "wallets": value.get("known_wallet_count"),
        "nearest": compact_nearest,
    }


def _rule_envelope(trace: Mapping[str, Any], vector: object) -> dict:
    envelope = {
        "status": trace.get("status"),
        "vector": vector,
    }
    reasons = list(trace.get("reason_codes") or [])
    if reasons:
        envelope["reasons"] = reasons
    return envelope


def compact_limit_context(context_runtime: Mapping[str, Any]) -> dict:
    if not isinstance(context_runtime, Mapping):
        raise LimitLearningPersistenceError("context_runtime_required")
    if context_runtime.get("runtime_version") != RUNTIME_VERSION:
        raise LimitLearningPersistenceError("context_runtime_version_mismatch")
    traces = _trace_map(context_runtime)
    if set(traces) != set(RULE_IDS):
        raise LimitLearningPersistenceError("context_rule_set_mismatch")

    trajectory = traces[RULE_IDS[0]]
    trajectory_outputs = trajectory.get("outputs") or {}
    trajectory_vector = {
        "path_h": [
            trajectory_outputs.get("raw_signed_path_efficiency_h"),
            trajectory_outputs.get("activation_adjusted_path_efficiency_h"),
            trajectory_outputs.get("reaction_adjusted_path_efficiency_h"),
        ],
        "displacement_h": [
            trajectory_outputs.get("raw_log_displacement_h"),
            trajectory_outputs.get("activation_adjusted_log_displacement_h"),
            trajectory_outputs.get("reaction_adjusted_log_displacement_h"),
        ],
        "mtf_activation": trajectory_outputs.get(
            "activation_adjusted_mtf_efficiencies"
        ),
        "mtf_reaction": trajectory_outputs.get(
            "reaction_adjusted_mtf_efficiencies"
        ),
        "volatility_rank": trajectory_outputs.get("volatility_percentile_60"),
        "ema": _dual_vector(trajectory_outputs.get("ema_slope_dual_role")),
        "rsi": _dual_vector(trajectory_outputs.get("rsi_dual_role")),
    }

    flow = traces[RULE_IDS[1]]
    flow_outputs = flow.get("outputs") or {}
    directional = flow_outputs.get("directional_components") or {}
    flow_vector = {
        "directional": {
            str(key): _dual_vector(value)
            for key, value in directional.items()
        },
        "context": flow_outputs.get("non_directional_context") or {},
    }

    zone = traces[RULE_IDS[2]]
    zone_outputs = zone.get("outputs") or {}
    desired_level = zone_outputs.get("desired_level")
    fibonacci_at_entry = zone_outputs.get("fibonacci_at_entry")
    zone_vector = {
        "desired_type": zone_outputs.get("desired_level_type"),
        "desired_level": (
            {
                "type": desired_level.get("type"),
                "price": desired_level.get("price"),
            }
            if isinstance(desired_level, Mapping)
            else None
        ),
        "fibonacci_at_entry": (
            {
                "set": fibonacci_at_entry.get("set"),
                "ratio": fibonacci_at_entry.get("ratio"),
                "price": fibonacci_at_entry.get("price"),
            }
            if isinstance(fibonacci_at_entry, Mapping)
            else None
        ),
        "retracement_fraction": zone_outputs.get(
            "entry_retracement_fraction"
        ),
        "components": zone_outputs.get("zone_vector") or {},
    }

    liquidations = traces[RULE_IDS[3]]
    liquidation_outputs = liquidations.get("outputs") or {}
    liquidation_vector = {
        "provider": liquidation_outputs.get("provider"),
        "scope": liquidation_outputs.get("scope"),
        "as_of": liquidation_outputs.get("as_of"),
        "age_seconds": liquidation_outputs.get("age_seconds"),
        "approach": _compact_liquidation_summary(
            liquidation_outputs.get("approach_path")
        ),
        "overshoot_to_sl": _compact_liquidation_summary(
            liquidation_outputs.get("overshoot_path_entry_to_sl")
        ),
        "post_activation_to_tp": _compact_liquidation_summary(
            liquidation_outputs.get("post_activation_target_path")
        ),
        "target_mass_fraction": liquidation_outputs.get(
            "target_fraction_of_visible_post_activation_mass"
        ),
    }

    return {
        "runtime_version": RUNTIME_VERSION,
        "runtime_trace_sha256": context_runtime.get("runtime_trace_sha256"),
        "rules": {
            RULE_IDS[0]: _rule_envelope(trajectory, trajectory_vector),
            RULE_IDS[1]: _rule_envelope(flow, flow_vector),
            RULE_IDS[2]: _rule_envelope(zone, zone_vector),
            RULE_IDS[3]: _rule_envelope(liquidations, liquidation_vector),
        },
    }


def _validate_contract(contract: Mapping[str, Any]) -> dict:
    if not isinstance(contract, Mapping):
        raise LimitLearningPersistenceError("contract_required")
    if contract.get("contract_version") != LIMIT_ORDER_CONTRACT_VERSION:
        raise LimitLearningPersistenceError("limit_contract_version_mismatch")
    if contract.get("analysis_family") != LIMIT_ORDER_ANALYSIS_FAMILY:
        raise LimitLearningPersistenceError("limit_analysis_family_mismatch")
    order = contract.get("order")
    if not isinstance(order, dict):
        raise LimitLearningPersistenceError("limit_order_context_missing")
    return order


def _record(
    *,
    snapshot_type: str,
    operation_id: int,
    recommendation_id: int | None,
    analysis_id: str,
    event_at: Any,
    symbol: str,
    side: str,
    time_horizon: str,
    payload: dict,
    learning_label: str | None = None,
) -> dict:
    if snapshot_type not in SNAPSHOT_TYPES:
        raise LimitLearningPersistenceError("invalid_snapshot_type")
    operation = _positive_int(operation_id, "operation_id")
    recommendation = _optional_positive_int(
        recommendation_id,
        "recommendation_id",
    )
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise LimitLearningPersistenceError("analysis_id_required")
    normalized_side = str(side).lower()
    if normalized_side not in {"long", "short"}:
        raise LimitLearningPersistenceError("invalid_side")
    event_time = _utc_iso(event_at, "event_at")
    compact_payload = _compact_json_value(payload)
    if not isinstance(compact_payload, dict):
        raise LimitLearningPersistenceError("payload_must_be_an_object")
    forbidden = _forbidden_raw_path(compact_payload)
    if forbidden:
        raise LimitLearningPersistenceError(
            f"raw_feed_forbidden:{forbidden}"
        )
    payload_json = canonical_json(compact_payload)
    payload_bytes = len(payload_json.encode("utf-8"))
    budget = SNAPSHOT_BYTE_BUDGETS[snapshot_type]
    if payload_bytes > budget:
        raise LimitLearningPersistenceError(
            f"{snapshot_type}_payload_budget_exceeded:{payload_bytes}>{budget}"
        )
    return {
        "snapshot_schema_version": LIMIT_LEARNING_SNAPSHOT_VERSION,
        "snapshot_type": snapshot_type,
        "operation_id": operation,
        "recommendation_id": recommendation,
        "analysis_id": analysis_id.strip(),
        "event_at": event_time,
        "selected_case_day": event_time[:10] if snapshot_type == "placement" else None,
        "symbol": str(symbol).strip().upper(),
        "side": normalized_side,
        "time_horizon": str(time_horizon),
        "learning_label": learning_label,
        "payload_json": payload_json,
        "payload_bytes": payload_bytes,
        "payload_sha256": canonical_sha256(compact_payload),
        "production_effect": PERSISTENCE_PRODUCTION_EFFECT,
    }


def build_placement_snapshot_record(
    contract: Mapping[str, Any],
    activation_baseline: Mapping[str, Any],
    context_runtime: Mapping[str, Any],
    *,
    operation_id: int,
    recommendation_id: int | None = None,
    data_cutoff_at: Any | None = None,
) -> dict:
    order = _validate_contract(contract)
    if (
        activation_baseline.get("model_version")
        != LIMIT_ACTIVATION_MODEL_VERSION
    ):
        raise LimitLearningPersistenceError(
            "activation_baseline_version_mismatch"
        )
    if activation_baseline.get("contract_version") != contract.get(
        "contract_version"
    ):
        raise LimitLearningPersistenceError(
            "activation_contract_version_mismatch"
        )
    if activation_baseline.get("analysis_id") != contract.get("analysis_id"):
        raise LimitLearningPersistenceError("activation_analysis_id_mismatch")
    if context_runtime.get("analysis_id") != contract.get("analysis_id"):
        raise LimitLearningPersistenceError("context_analysis_id_mismatch")
    activation_inputs = activation_baseline.get("inputs") or {}
    activation_probabilities = activation_baseline.get("probabilities") or {}
    analysis_at = (
        contract.get("windows", {}).get("activation", {}).get("starts_at")
    )
    activation_expires_at = (
        contract.get("windows", {}).get("activation", {}).get("expires_at")
    )
    payload = {
        "contract_version": contract.get("contract_version"),
        "analysis_id": contract.get("analysis_id"),
        "analysis_at": analysis_at,
        "data_cutoff_at": (
            _utc_iso(data_cutoff_at, "data_cutoff_at")
            if data_cutoff_at is not None
            else analysis_at
        ),
        "activation_expires_at": activation_expires_at,
        "plan": {
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "time_horizon": order.get("time_horizon"),
            "activation_horizon_seconds": contract.get("windows", {})
            .get("activation", {})
            .get("horizon_seconds"),
            "outcome_horizon_seconds": contract.get("windows", {})
            .get("outcome_after_activation", {})
            .get("horizon_seconds"),
            "current_price": order.get("current_price"),
            "requested_entry": order.get("requested_entry"),
            "stop_loss": order.get("stop_loss"),
            "take_profit": order.get("take_profit"),
            "trigger_condition": order.get("trigger_condition"),
            "entry_order_type": order.get("entry_order_type"),
        },
        "activation_baseline": {
            "model_version": activation_baseline.get("model_version"),
            "probabilities": activation_probabilities,
            "activation_log_distance": activation_inputs.get(
                "activation_log_distance"
            ),
            "sigma_horizon": activation_inputs.get("sigma_horizon"),
            "distance_in_horizon_sigma": activation_inputs.get(
                "distance_in_horizon_sigma"
            ),
            "source_sha256": canonical_sha256(activation_baseline),
        },
        "context": compact_limit_context(context_runtime),
        "contract_sha256": contract.get("contract_sha256"),
    }
    required_projection = {
        "contract_version": payload["contract_version"],
        "analysis_id": payload["analysis_id"],
        "analysis_at": payload["analysis_at"],
        "data_cutoff_at": payload["data_cutoff_at"],
        "activation_expires_at": payload["activation_expires_at"],
        **payload["plan"],
        "activation_feature_vector": payload["activation_baseline"],
        "zone_feature_vector": payload["context"]["rules"][RULE_IDS[2]][
            "vector"
        ],
        "source_statuses": {
            rule_id: payload["context"]["rules"][rule_id]["status"]
            for rule_id in RULE_IDS
        },
    }
    missing = [
        field
        for field in PLACEMENT_SNAPSHOT_FIELDS
        if field not in required_projection
    ]
    if missing:
        raise LimitLearningPersistenceError(
            f"placement_projection_missing:{','.join(missing)}"
        )
    return _record(
        snapshot_type="placement",
        operation_id=operation_id,
        recommendation_id=recommendation_id,
        analysis_id=str(contract.get("analysis_id")),
        event_at=analysis_at,
        symbol=str(order.get("symbol")),
        side=str(order.get("side")),
        time_horizon=str(order.get("time_horizon")),
        payload=payload,
    )


def _build_lifecycle_record(
    snapshot_type: str,
    contract: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    operation_id: int,
    recommendation_id: int | None,
) -> dict:
    order = _validate_contract(contract)
    if not isinstance(values, Mapping):
        raise LimitLearningPersistenceError("snapshot_values_required")
    required = (
        ACTIVATION_SNAPSHOT_FIELDS
        if snapshot_type == "activation"
        else CLOSURE_SNAPSHOT_FIELDS
    )
    missing = [field for field in required if field not in values]
    if missing:
        raise LimitLearningPersistenceError(
            f"{snapshot_type}_fields_missing:{','.join(missing)}"
        )
    if values.get("contract_version") != contract.get("contract_version"):
        raise LimitLearningPersistenceError("snapshot_contract_version_mismatch")
    if _positive_int(values.get("operation_id"), "snapshot_operation_id") != (
        _positive_int(operation_id, "operation_id")
    ):
        raise LimitLearningPersistenceError("snapshot_operation_id_mismatch")
    payload = {
        "analysis_id": contract.get("analysis_id"),
        **{field: values[field] for field in required},
    }
    learning_label = None
    if snapshot_type == "activation":
        event_at = values["activated_at"]
    else:
        event_at = values["closed_at"]
        expected = learning_label_for_terminal_event(values["terminal_event"])
        if values["learning_label"] != expected:
            raise LimitLearningPersistenceError("closure_learning_label_mismatch")
        learning_label = expected
    return _record(
        snapshot_type=snapshot_type,
        operation_id=operation_id,
        recommendation_id=recommendation_id,
        analysis_id=str(contract.get("analysis_id")),
        event_at=event_at,
        symbol=str(order.get("symbol")),
        side=str(order.get("side")),
        time_horizon=str(order.get("time_horizon")),
        payload=payload,
        learning_label=learning_label,
    )


def build_activation_snapshot_record(
    contract: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    operation_id: int,
    recommendation_id: int | None = None,
) -> dict:
    return _build_lifecycle_record(
        "activation",
        contract,
        values,
        operation_id=operation_id,
        recommendation_id=recommendation_id,
    )


def build_closure_snapshot_record(
    contract: Mapping[str, Any],
    values: Mapping[str, Any],
    *,
    operation_id: int,
    recommendation_id: int | None = None,
) -> dict:
    return _build_lifecycle_record(
        "closure",
        contract,
        values,
        operation_id=operation_id,
        recommendation_id=recommendation_id,
    )


def projected_payload_bytes(
    *,
    selected_cases_per_day: int,
    days: int,
) -> int:
    cases = _positive_int(selected_cases_per_day, "selected_cases_per_day")
    period = _positive_int(days, "days")
    if cases > MAX_SELECTED_CASES_PER_UTC_DAY:
        raise LimitLearningPersistenceError("daily_selected_case_cap_exceeded")
    return cases * period * ALLOCATED_BYTES_PER_OPERATION


def _row_dict(row: object) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def _existing_snapshot(db, record: Mapping[str, Any]) -> dict | None:
    return _row_dict(
        db.execute(
            """
            SELECT id, payload_sha256, daily_slot
            FROM limit_learning_snapshots
            WHERE operation_id = ? AND snapshot_type = ?
            LIMIT 1
            """,
            (record["operation_id"], record["snapshot_type"]),
        ).fetchone()
    )


def _validate_record_integrity(record: Mapping[str, Any]) -> None:
    required = {
        "snapshot_schema_version",
        "snapshot_type",
        "operation_id",
        "analysis_id",
        "event_at",
        "symbol",
        "side",
        "time_horizon",
        "payload_json",
        "payload_bytes",
        "payload_sha256",
        "production_effect",
    }
    missing = sorted(required.difference(record))
    if missing:
        raise LimitLearningPersistenceError(
            f"snapshot_record_fields_missing:{','.join(missing)}"
        )
    if record["snapshot_schema_version"] != LIMIT_LEARNING_SNAPSHOT_VERSION:
        raise LimitLearningPersistenceError("snapshot_schema_version_mismatch")
    snapshot_type = str(record["snapshot_type"])
    if snapshot_type not in SNAPSHOT_TYPES:
        raise LimitLearningPersistenceError("invalid_snapshot_type")
    if record["production_effect"] != PERSISTENCE_PRODUCTION_EFFECT:
        raise LimitLearningPersistenceError("invalid_production_effect")
    payload_json = record["payload_json"]
    if not isinstance(payload_json, str):
        raise LimitLearningPersistenceError("payload_json_must_be_text")
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise LimitLearningPersistenceError("payload_json_invalid") from exc
    if not isinstance(payload, dict) or canonical_json(payload) != payload_json:
        raise LimitLearningPersistenceError("payload_json_must_be_canonical_object")
    payload_bytes = len(payload_json.encode("utf-8"))
    if record["payload_bytes"] != payload_bytes:
        raise LimitLearningPersistenceError("payload_byte_count_mismatch")
    if payload_bytes > SNAPSHOT_BYTE_BUDGETS[snapshot_type]:
        raise LimitLearningPersistenceError("snapshot_payload_budget_exceeded")
    if record["payload_sha256"] != canonical_sha256(payload):
        raise LimitLearningPersistenceError("snapshot_payload_hash_mismatch")
    forbidden = _forbidden_raw_path(payload)
    if forbidden:
        raise LimitLearningPersistenceError(
            f"raw_feed_forbidden:{forbidden}"
        )
    event_at = _utc_iso(record["event_at"], "event_at")
    if event_at != record["event_at"]:
        raise LimitLearningPersistenceError("event_at_must_be_canonical_utc")
    selected_day = record.get("selected_case_day")
    if snapshot_type == "placement" and selected_day != event_at[:10]:
        raise LimitLearningPersistenceError("selected_case_day_mismatch")
    if snapshot_type != "placement" and selected_day is not None:
        raise LimitLearningPersistenceError("selected_case_day_only_for_placement")


def _idempotent_result(existing: Mapping[str, Any], record: Mapping[str, Any]) -> dict:
    if existing.get("payload_sha256") != record.get("payload_sha256"):
        raise LimitLearningPersistenceError("snapshot_conflict_existing_payload")
    return {
        "status": "idempotent_skip",
        "snapshot_id": int(existing["id"]),
        "snapshot_type": record["snapshot_type"],
        "daily_slot": existing.get("daily_slot"),
        "payload_bytes": record["payload_bytes"],
        "production_effect": PERSISTENCE_PRODUCTION_EFFECT,
    }


def persist_limit_learning_snapshot(db, record: Mapping[str, Any]) -> dict:
    if not isinstance(record, Mapping):
        raise LimitLearningPersistenceError("snapshot_record_required")
    _validate_record_integrity(record)
    existing = _existing_snapshot(db, record)
    if existing:
        return _idempotent_result(existing, record)

    snapshot_type = str(record.get("snapshot_type"))
    if snapshot_type != "placement":
        placement = _row_dict(
            db.execute(
                """
                SELECT id FROM limit_learning_snapshots
                WHERE operation_id = ? AND snapshot_type = 'placement'
                LIMIT 1
                """,
                (record["operation_id"],),
            ).fetchone()
        )
        if not placement:
            raise LimitLearningPersistenceError("placement_snapshot_required")

    attempts = 3 if snapshot_type == "placement" else 1
    for _ in range(attempts):
        daily_slot = None
        if snapshot_type == "placement":
            usage = _row_dict(
                db.execute(
                    """
                    SELECT COALESCE(MAX(daily_slot), 0) AS used_slots
                    FROM limit_learning_snapshots
                    WHERE snapshot_type = 'placement'
                      AND selected_case_day = ?
                    """,
                    (record["selected_case_day"],),
                ).fetchone()
            ) or {"used_slots": 0}
            daily_slot = int(usage.get("used_slots") or 0) + 1
            if daily_slot > MAX_SELECTED_CASES_PER_UTC_DAY:
                raise LimitLearningPersistenceError(
                    "daily_selected_case_cap_reached"
                )
        cursor = db.execute(
            """
            INSERT INTO limit_learning_snapshots (
                operation_id, recommendation_id, analysis_id, snapshot_type,
                snapshot_schema_version, event_at, selected_case_day,
                daily_slot, symbol, side, time_horizon, learning_label,
                payload_sha256, payload_bytes, payload_json,
                production_effect
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            RETURNING id, daily_slot
            """,
            (
                record["operation_id"],
                record.get("recommendation_id"),
                record["analysis_id"],
                snapshot_type,
                record["snapshot_schema_version"],
                record["event_at"],
                record.get("selected_case_day"),
                daily_slot,
                record["symbol"],
                record["side"],
                record["time_horizon"],
                record.get("learning_label"),
                record["payload_sha256"],
                record["payload_bytes"],
                record["payload_json"],
                PERSISTENCE_PRODUCTION_EFFECT,
            ),
        )
        inserted = _row_dict(cursor.fetchone())
        if inserted:
            return {
                "status": "recorded",
                "snapshot_id": int(inserted["id"]),
                "snapshot_type": snapshot_type,
                "daily_slot": inserted.get("daily_slot"),
                "payload_bytes": record["payload_bytes"],
                "production_effect": PERSISTENCE_PRODUCTION_EFFECT,
            }
        existing = _existing_snapshot(db, record)
        if existing:
            return _idempotent_result(existing, record)
    raise LimitLearningPersistenceError("daily_slot_contention")


if ALLOCATED_BYTES_PER_OPERATION > LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES:
    raise RuntimeError("limit_learning_budget_exceeds_contract")


__all__ = (
    "ALLOCATED_BYTES_PER_OPERATION",
    "LIMIT_LEARNING_SNAPSHOT_VERSION",
    "MAX_SELECTED_CASES_PER_UTC_DAY",
    "PERSISTENCE_PRODUCTION_EFFECT",
    "SNAPSHOT_BYTE_BUDGETS",
    "LimitLearningPersistenceError",
    "build_activation_snapshot_record",
    "build_closure_snapshot_record",
    "build_placement_snapshot_record",
    "compact_limit_context",
    "persist_limit_learning_snapshot",
    "projected_payload_bytes",
)
