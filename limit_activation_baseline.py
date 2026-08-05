from __future__ import annotations

import math
from typing import Any, Iterable

from limit_order_contract import (
    LIMIT_ORDER_ANALYSIS_FAMILY,
    LIMIT_ORDER_CONTRACT_VERSION,
    LIMIT_ORDER_TYPE,
)
from limit_activation_first_passage import (
    FirstPassageInputError,
    single_barrier_first_passage,
)


LIMIT_ACTIVATION_MODEL_VERSION = "limit-activation-first-passage-v0.1"
LIMIT_ACTIVATION_PRODUCTION_EFFECT = "shadow_only"
DEFAULT_TIME_CHECKPOINTS = (0.0, 0.25, 0.5, 0.75, 1.0)


class LimitActivationBaselineError(ValueError):
    pass


def _finite_positive(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise LimitActivationBaselineError(f"invalid_{name}")
    return float(value)


def _normalized_checkpoints(values: Iterable[float]) -> tuple[float, ...]:
    try:
        parsed = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise LimitActivationBaselineError(
            "invalid_time_checkpoints"
        ) from exc
    if not parsed:
        raise LimitActivationBaselineError("time_checkpoints_required")
    if any(
        not math.isfinite(value) or not 0.0 <= value <= 1.0
        for value in parsed
    ):
        raise LimitActivationBaselineError(
            "time_checkpoints_must_be_between_zero_and_one"
        )
    if tuple(sorted(set(parsed))) != parsed:
        raise LimitActivationBaselineError(
            "time_checkpoints_must_be_unique_and_sorted"
        )
    if parsed[-1] != 1.0:
        raise LimitActivationBaselineError(
            "time_checkpoints_must_include_expiry"
        )
    return parsed


def activation_log_distance(
    *,
    side: str,
    current_price: float,
    requested_entry: float,
) -> float:
    current = _finite_positive(current_price, "current_price")
    entry = _finite_positive(requested_entry, "requested_entry")
    normalized_side = str(side).lower()
    if normalized_side == "long":
        if not entry < current:
            raise LimitActivationBaselineError(
                "long_limit_entry_must_be_below_market"
            )
        return math.log(current / entry)
    if normalized_side == "short":
        if not entry > current:
            raise LimitActivationBaselineError(
                "short_limit_entry_must_be_above_market"
            )
        return math.log(entry / current)
    raise LimitActivationBaselineError("invalid_side")


def _validate_contract(contract: dict) -> dict:
    if not isinstance(contract, dict):
        raise LimitActivationBaselineError("contract_must_be_an_object")
    if contract.get("contract_version") != LIMIT_ORDER_CONTRACT_VERSION:
        raise LimitActivationBaselineError("limit_contract_version_mismatch")
    if contract.get("analysis_family") != LIMIT_ORDER_ANALYSIS_FAMILY:
        raise LimitActivationBaselineError("limit_analysis_family_mismatch")
    order = contract.get("order")
    if not isinstance(order, dict):
        raise LimitActivationBaselineError("limit_order_context_missing")
    if order.get("entry_order_type") != LIMIT_ORDER_TYPE:
        raise LimitActivationBaselineError(
            "limit_activation_supports_pullback_only"
        )
    windows = contract.get("windows")
    if not isinstance(windows, dict) or not isinstance(
        windows.get("activation"), dict
    ):
        raise LimitActivationBaselineError(
            "activation_window_missing"
        )
    return order


def build_limit_activation_baseline(
    contract: dict,
    *,
    sigma_horizon: float,
    time_checkpoints: Iterable[float] = DEFAULT_TIME_CHECKPOINTS,
) -> dict:
    order = _validate_contract(contract)
    sigma = _finite_positive(sigma_horizon, "sigma_horizon")
    checkpoints = _normalized_checkpoints(time_checkpoints)
    distance = activation_log_distance(
        side=str(order.get("side")),
        current_price=order.get("current_price"),
        requested_entry=order.get("requested_entry"),
    )
    try:
        checkpoint_results = [
            single_barrier_first_passage(
                log_distance=distance,
                sigma_horizon=sigma,
                time_fraction=fraction,
            )
            for fraction in checkpoints
        ]
    except FirstPassageInputError as exc:
        raise LimitActivationBaselineError(str(exc)) from exc
    final = checkpoint_results[-1]
    cdf = [
        {
            "time_fraction": result.time_fraction,
            "activated_by_time": result.p_hit,
            "not_activated_by_time": result.p_no_hit,
        }
        for result in checkpoint_results
    ]
    payload = {
        "model_version": LIMIT_ACTIVATION_MODEL_VERSION,
        "solver_version": final.solver_version,
        "analysis_id": contract.get("analysis_id"),
        "contract_version": contract.get("contract_version"),
        "analysis_family": contract.get("analysis_family"),
        "production_effect": LIMIT_ACTIVATION_PRODUCTION_EFFECT,
        "status": "evaluated_shadow_baseline",
        "probability_semantics": (
            "model_implied_unadjusted_first_passage_probability"
        ),
        "calibration_status": (
            "not_empirically_calibrated_for_limit_orders"
        ),
        "inputs": {
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "time_horizon": order.get("time_horizon"),
            "current_price": float(order["current_price"]),
            "requested_entry": float(order["requested_entry"]),
            "direction_to_activation": order.get(
                "direction_to_activation"
            ),
            "activation_horizon_seconds": contract.get("windows", {})
            .get("activation", {})
            .get("horizon_seconds"),
            "activation_log_distance": distance,
            "sigma_horizon": sigma,
            "distance_in_horizon_sigma": distance / sigma,
        },
        "probabilities": {
            "activated_by_expiry": final.p_hit,
            "not_activated_by_expiry": final.p_no_hit,
        },
        "activation_cdf": cdf,
        "numerics": {
            "method": final.numerical_method,
            "mass_error": final.mass_error,
            "drift": final.drift,
        },
        "assumptions": [
            "continuous_log_price_path",
            "zero_drift_baseline",
            "constant_total_horizon_volatility",
            "single_absorbing_activation_barrier",
            "barrier_touch_counts_as_activation",
        ],
        "excluded_effects": [
            "trend_and_regime",
            "support_resistance_and_fibonacci",
            "order_book_and_trade_flow",
            "open_interest_funding_and_basis",
            "liquidation_map",
            "jumps_gaps_and_provider_latency",
        ],
        "interpretation": {
            "is_calibrated_user_probability": False,
            "may_change_operation_or_market_scoring": False,
            "purpose": (
                "distance_volatility_time_reference_for_later_validation"
            ),
        },
    }
    probability_mass = math.fsum(payload["probabilities"].values())
    if not math.isclose(
        probability_mass,
        1.0,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise LimitActivationBaselineError(
            "activation_probability_mass_invalid"
        )
    payload["probability_mass"] = probability_mass
    return payload


__all__ = (
    "DEFAULT_TIME_CHECKPOINTS",
    "LIMIT_ACTIVATION_MODEL_VERSION",
    "LIMIT_ACTIVATION_PRODUCTION_EFFECT",
    "LimitActivationBaselineError",
    "activation_log_distance",
    "build_limit_activation_baseline",
)
