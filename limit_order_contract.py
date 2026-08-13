from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Mapping

from m7_joint_temporal_engine import HORIZON_SECONDS


LIMIT_ORDER_CONTRACT_VERSION = "limit-order-contract-v1.4"
LIMIT_ORDER_ANALYSIS_FAMILY = "pending_limit_two_stage"
LIMIT_ORDER_ENTRY_TYPE = "pending"
LIMIT_ORDER_TYPE = "limit_pullback"
LIMIT_ORDER_PRODUCTION_EFFECT = "served_two_stage_analysis"
LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES = 8 * 1024
LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS = {
    "placement": 3584,
    "activation": 1280,
    "closure": 1024,
}
LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES = sum(
    LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS.values()
)
LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY = 50

ACTIVATION_CLASSES = (
    "activated_by_expiry",
    "not_activated_by_expiry",
)
CONDITIONAL_OUTCOME_CLASSES = (
    "tp_first_within_outcome_horizon",
    "sl_first_within_outcome_horizon",
    "neither_barrier_before_outcome_expiry",
)
OVERALL_OUTCOME_CLASSES = (
    "activation_then_tp_first",
    "activation_then_sl_first",
    "activation_then_neither_barrier",
    "not_activated_by_expiry",
)


class LimitOrderContractError(ValueError):
    pass


class OperationStatus(StrEnum):
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class LifecycleEvent(StrEnum):
    ACTIVATED = "pending_entry_activated"
    PENDING_EXPIRED = "pending_entry_expired"
    PENDING_CANCELLED = "pending_entry_cancelled"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    OUTCOME_EXPIRED = "outcome_horizon_expired"
    MANUAL_CLOSE = "manual_close"


ALLOWED_TRANSITIONS = {
    (
        OperationStatus.PENDING_ENTRY,
        LifecycleEvent.ACTIVATED,
    ): OperationStatus.OPEN,
    (
        OperationStatus.PENDING_ENTRY,
        LifecycleEvent.PENDING_EXPIRED,
    ): OperationStatus.CLOSED,
    (
        OperationStatus.PENDING_ENTRY,
        LifecycleEvent.PENDING_CANCELLED,
    ): OperationStatus.CLOSED,
    (
        OperationStatus.OPEN,
        LifecycleEvent.TAKE_PROFIT,
    ): OperationStatus.CLOSED,
    (
        OperationStatus.OPEN,
        LifecycleEvent.STOP_LOSS,
    ): OperationStatus.CLOSED,
    (
        OperationStatus.OPEN,
        LifecycleEvent.OUTCOME_EXPIRED,
    ): OperationStatus.CLOSED,
    (
        OperationStatus.OPEN,
        LifecycleEvent.MANUAL_CLOSE,
    ): OperationStatus.CLOSED,
}

LEARNING_LABEL_BY_TERMINAL_EVENT = {
    LifecycleEvent.PENDING_EXPIRED: "not_activated_by_expiry",
    LifecycleEvent.PENDING_CANCELLED: "censored_before_activation",
    LifecycleEvent.TAKE_PROFIT: "activation_then_tp_first",
    LifecycleEvent.STOP_LOSS: "activation_then_sl_first",
    LifecycleEvent.OUTCOME_EXPIRED: "activation_then_neither_barrier",
    LifecycleEvent.MANUAL_CLOSE: "censored_after_activation",
}

PLACEMENT_SNAPSHOT_FIELDS = (
    "contract_version",
    "analysis_id",
    "analysis_at",
    "data_cutoff_at",
    "activation_expires_at",
    "symbol",
    "side",
    "time_horizon",
    "activation_horizon_seconds",
    "outcome_horizon_seconds",
    "current_price",
    "requested_entry",
    "stop_loss",
    "take_profit",
    "trigger_condition",
    "entry_order_type",
    "activation_feature_vector",
    "zone_feature_vector",
    "source_statuses",
)

ACTIVATION_SNAPSHOT_FIELDS = (
    "contract_version",
    "operation_id",
    "activated_at",
    "data_cutoff_at",
    "outcome_expires_at",
    "evidence_source",
    "requested_entry",
    "trigger_observed_price",
    "simulated_fill_price",
    "seconds_to_activation",
    "activation_feature_vector",
    "post_activation_feature_vector",
    "source_statuses",
)

CLOSURE_SNAPSHOT_FIELDS = (
    "contract_version",
    "operation_id",
    "closed_at",
    "terminal_event",
    "learning_label",
    "evidence_source",
    "close_price",
    "seconds_from_activation",
    "mfe_pct",
    "mae_pct",
    "economic_result",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _finite_positive(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise LimitOrderContractError(f"invalid_{name}")
    return float(value)


def _utc_datetime(value: str | datetime, name: str) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LimitOrderContractError(f"invalid_{name}") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise LimitOrderContractError(f"invalid_{name}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LimitOrderContractError(f"{name}_must_be_timezone_aware")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _validate_probability(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise LimitOrderContractError(f"invalid_probability:{name}")
    return float(value)


def _validate_probability_distribution(
    probabilities: Mapping[str, float],
    expected_keys: tuple[str, ...],
) -> dict[str, float]:
    if set(probabilities) != set(expected_keys):
        raise LimitOrderContractError("probability_keys_mismatch")
    parsed = {
        key: _validate_probability(probabilities[key], key)
        for key in expected_keys
    }
    if not math.isclose(
        math.fsum(parsed.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise LimitOrderContractError("probability_mass_not_one")
    return parsed


def trigger_condition_for_limit(side: str) -> str:
    if side == "long":
        return "price_lte"
    if side == "short":
        return "price_gte"
    raise LimitOrderContractError("invalid_side")


def validate_limit_plan(
    *,
    side: str,
    current_price: float,
    requested_entry: float,
    stop_loss: float,
    take_profit: float,
    trigger_condition: str,
) -> dict[str, Any]:
    side = str(side).lower()
    if side not in {"long", "short"}:
        raise LimitOrderContractError("invalid_side")
    current = _finite_positive(current_price, "current_price")
    entry = _finite_positive(requested_entry, "requested_entry")
    stop = _finite_positive(stop_loss, "stop_loss")
    target = _finite_positive(take_profit, "take_profit")
    expected_trigger = trigger_condition_for_limit(side)
    if trigger_condition != expected_trigger:
        raise LimitOrderContractError(
            "limit_v1_supports_pullback_orders_only"
        )
    entry_waits_below_market = side == "long" and entry < current
    entry_waits_above_market = side == "short" and entry > current
    if not (entry_waits_below_market or entry_waits_above_market):
        raise LimitOrderContractError("limit_trigger_already_satisfied")
    valid_barriers = (
        stop < entry < target
        if side == "long"
        else target < entry < stop
    )
    if not valid_barriers:
        raise LimitOrderContractError("invalid_barrier_geometry")
    return {
        "side": side,
        "current_price": current,
        "requested_entry": entry,
        "stop_loss": stop,
        "take_profit": target,
        "trigger_condition": expected_trigger,
        "entry_type": LIMIT_ORDER_ENTRY_TYPE,
        "entry_order_type": LIMIT_ORDER_TYPE,
        "direction_to_activation": "down" if side == "long" else "up",
        "expected_reaction_after_activation": (
            "up" if side == "long" else "down"
        ),
    }


def transition_target(
    current_status: str | OperationStatus,
    event: str | LifecycleEvent,
) -> OperationStatus:
    try:
        normalized_status = OperationStatus(current_status)
        normalized_event = LifecycleEvent(event)
    except ValueError as exc:
        raise LimitOrderContractError("unknown_lifecycle_value") from exc
    target = ALLOWED_TRANSITIONS.get(
        (normalized_status, normalized_event)
    )
    if target is None:
        raise LimitOrderContractError("invalid_lifecycle_transition")
    return target


def learning_label_for_terminal_event(
    event: str | LifecycleEvent,
) -> str:
    try:
        normalized_event = LifecycleEvent(event)
    except ValueError as exc:
        raise LimitOrderContractError("unknown_lifecycle_event") from exc
    label = LEARNING_LABEL_BY_TERMINAL_EVENT.get(normalized_event)
    if label is None:
        raise LimitOrderContractError("event_is_not_terminal")
    return label


def compose_limit_probability_tree(
    activation_probability: float,
    conditional_after_activation: Mapping[str, float],
) -> dict[str, Any]:
    p_activation = _validate_probability(
        activation_probability,
        "activated_by_expiry",
    )
    conditional = _validate_probability_distribution(
        conditional_after_activation,
        CONDITIONAL_OUTCOME_CLASSES,
    )
    activation = {
        "activated_by_expiry": p_activation,
        "not_activated_by_expiry": 1.0 - p_activation,
    }
    overall = {
        "activation_then_tp_first": p_activation
        * conditional["tp_first_within_outcome_horizon"],
        "activation_then_sl_first": p_activation
        * conditional["sl_first_within_outcome_horizon"],
        "activation_then_neither_barrier": p_activation
        * conditional["neither_barrier_before_outcome_expiry"],
        "not_activated_by_expiry": 1.0 - p_activation,
    }
    _validate_probability_distribution(activation, ACTIVATION_CLASSES)
    _validate_probability_distribution(overall, OVERALL_OUTCOME_CLASSES)
    return {
        "activation": activation,
        "conditional_after_activation": conditional,
        "overall": overall,
        "activation_mass": math.fsum(activation.values()),
        "conditional_mass": math.fsum(conditional.values()),
        "overall_mass": math.fsum(overall.values()),
    }


def build_limit_order_contract(
    *,
    analysis_id: str,
    symbol: str,
    side: str,
    time_horizon: str,
    analysis_at: str | datetime,
    current_price: float,
    requested_entry: float,
    stop_loss: float,
    take_profit: float,
    trigger_condition: str,
) -> dict[str, Any]:
    if not isinstance(analysis_id, str) or not analysis_id.strip():
        raise LimitOrderContractError("invalid_analysis_id")
    normalized_symbol = str(symbol).strip().upper()
    if not 5 <= len(normalized_symbol) <= 20:
        raise LimitOrderContractError("invalid_symbol")
    if time_horizon not in HORIZON_SECONDS:
        raise LimitOrderContractError("unsupported_time_horizon")
    plan = validate_limit_plan(
        side=side,
        current_price=current_price,
        requested_entry=requested_entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        trigger_condition=trigger_condition,
    )
    analysis_time = _utc_datetime(analysis_at, "analysis_at")
    horizon_seconds = int(HORIZON_SECONDS[time_horizon])
    activation_expiry = analysis_time + timedelta(seconds=horizon_seconds)
    payload = {
        "contract_version": LIMIT_ORDER_CONTRACT_VERSION,
        "analysis_family": LIMIT_ORDER_ANALYSIS_FAMILY,
        "analysis_id": analysis_id.strip(),
        "production_effect": LIMIT_ORDER_PRODUCTION_EFFECT,
        "market_engine_modified": False,
        "legacy_engine_executed": False,
        "order": {
            "symbol": normalized_symbol,
            "time_horizon": time_horizon,
            **plan,
        },
        "windows": {
            "activation": {
                "starts_at": _iso_utc(analysis_time),
                "expires_at": _iso_utc(activation_expiry),
                "horizon_seconds": horizon_seconds,
                "boundary_policy": "trigger_at_or_before_expiry_counts",
            },
            "outcome_after_activation": {
                "starts_at": "actual_activation_at",
                "expires_at": (
                    "actual_activation_at_plus_outcome_horizon_seconds"
                ),
                "horizon_seconds": horizon_seconds,
                "policy": "fresh_selected_horizon_from_activation",
            },
        },
        "execution": {
            "requested_entry_is_immutable_barrier": True,
            "trigger_observed_price_is_separate": True,
            "simulated_fill_policy": (
                "requested_limit_price_conservative_no_price_improvement_v1"
            ),
            "partial_fills_supported": False,
            "post_activation_v0_7_entry": "simulated_fill_price",
        },
        "probability_spaces": {
            "activation": {
                "classes": list(ACTIVATION_CLASSES),
                "status": "served_uncalibrated_reference",
            },
            "conditional_after_activation": {
                "classes": list(CONDITIONAL_OUTCOME_CLASSES),
                "status": "placement_preview_served_rerun_at_activation",
            },
            "overall": {
                "classes": list(OVERALL_OUTCOME_CLASSES),
                "status": "served_reference_not_empirically_calibrated",
            },
        },
        "context_rule_spaces": {
            "activation_trajectory": "not_executed",
            "flow_dual_role": "not_executed",
            "zone_structure": "not_executed",
            "liquidation_path": "not_executed",
            "policy": "disabled_by_single_engine_v0.7",
            "probability_effect": "none",
        },
        "lifecycle": {
            "stable_statuses": [status.value for status in OperationStatus],
            "activation_is_event_not_stable_status": True,
            "pending_cancellation_is_censored": True,
            "pending_expiry_is_no_activation_outcome": True,
            "manual_close_after_activation_is_censored": True,
        },
        "snapshots": {
            "placement_required_fields": list(
                PLACEMENT_SNAPSHOT_FIELDS
            ),
            "activation_required_fields": list(
                ACTIVATION_SNAPSHOT_FIELDS
            ),
            "closure_required_fields": list(CLOSURE_SNAPSHOT_FIELDS),
        },
        "persistence": {
            "max_new_learning_payload_bytes_per_operation": (
                LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES
            ),
            "snapshot_schema_version": "limit-learning-snapshot-v0.1",
            "allocated_snapshot_bytes_per_operation": (
                LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES
            ),
            "snapshot_byte_budgets": dict(
                LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS
            ),
            "max_selected_cases_per_utc_day": (
                LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY
            ),
            "persist_candidate_analyses": False,
            "idempotency_key": "operation_id_plus_snapshot_type",
            "persist_raw_candles": False,
            "persist_raw_order_book": False,
            "persist_raw_liquidation_heatmap": False,
            "persist_every_worker_poll": False,
            "persist_compact_derived_features_only": True,
        },
        "invariants": [
            "activation_probability_is_not_tp_probability",
            "no_activation_is_not_post_activation_neither",
            "cancelled_pending_order_is_censored_not_negative",
            "placement_snapshot_is_never_overwritten_by_activation_snapshot",
            "v0_7_is_the_only_post_activation_tp_sl_engine",
            "missing_optional_context_cannot_be_invented",
            "probability_effect_requires_validated_coefficients",
        ],
    }
    payload["contract_sha256"] = canonical_sha256(payload)
    return payload


__all__ = (
    "ACTIVATION_CLASSES",
    "ALLOWED_TRANSITIONS",
    "CONDITIONAL_OUTCOME_CLASSES",
    "CLOSURE_SNAPSHOT_FIELDS",
    "LIMIT_ORDER_ANALYSIS_FAMILY",
    "LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES",
    "LIMIT_ORDER_CONTRACT_VERSION",
    "LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY",
    "LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES",
    "LIMIT_ORDER_PRODUCTION_EFFECT",
    "LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS",
    "LifecycleEvent",
    "LimitOrderContractError",
    "OperationStatus",
    "OVERALL_OUTCOME_CLASSES",
    "PLACEMENT_SNAPSHOT_FIELDS",
    "ACTIVATION_SNAPSHOT_FIELDS",
    "build_limit_order_contract",
    "canonical_sha256",
    "compose_limit_probability_tree",
    "learning_label_for_terminal_event",
    "transition_target",
    "trigger_condition_for_limit",
    "validate_limit_plan",
)
