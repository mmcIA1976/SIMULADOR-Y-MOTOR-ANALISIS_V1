from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from m7_first_touch_math import adjusted_interval_hazards, build_baseline_intervals


ROOT = Path(__file__).resolve().parent
ARTIFACT_PATH = ROOT / "auditorias_motor" / "motor_v0_7_temporal_conjunto.json"

ENGINE_VERSION = "TP-SL-TEMPORAL-FIRST-TOUCH-v0.7"
SCORING_VERSION = "joint-first-touch-curve-frozen-v0.7"
RUNTIME_VERSION = "joint-temporal-runtime-v0.7"
REFERENCE_HORIZON_SECONDS = 24 * 60 * 60
BASE_INTERVAL_SECONDS = 4 * 60 * 60
HORIZON_SECONDS = {
    "intraday_short": 4 * 60 * 60,
    "intraday_wide": 24 * 60 * 60,
    "short_swing": 7 * 24 * 60 * 60,
}
HORIZON_LABELS = {
    "intraday_short": "Intradía corto · hasta 4 h",
    "intraday_wide": "Intradía amplio · hasta 24 h",
    "short_swing": "Swing corto · hasta 7 días",
}
HORIZON_STEPS = {
    name: seconds // BASE_INTERVAL_SECONDS
    for name, seconds in HORIZON_SECONDS.items()
}
MAX_HORIZON_SECONDS = max(HORIZON_SECONDS.values())
MAX_INTERVAL_COUNT = MAX_HORIZON_SECONDS // BASE_INTERVAL_SECONDS

CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)
FEATURE_NAMES = (
    "directional_path_efficiency_h",
    "directional_path_efficiency_2h",
    "directional_path_efficiency_4h",
    "volatility_percentile_60",
    "target_extreme_between_entry_and_tp",
)
FIT_FEATURE_NAMES = ("intercept",) + FEATURE_NAMES
VOLATILITY_FEATURE = "volatility_percentile_60"
DIRECTIONAL_FEATURES = tuple(
    name for name in FEATURE_NAMES if name != VOLATILITY_FEATURE
)


class JointTemporalEngineError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise JointTemporalEngineError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number):
        raise JointTemporalEngineError(f"{name}_must_be_finite")
    return number


def _positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0:
        raise JointTemporalEngineError(f"{name}_must_be_positive")
    return number


def _artifact_without_hash(payload: dict) -> dict:
    return {
        key: value
        for key, value in payload.items()
        if key != "artifact_sha256"
    }


def validate_artifact(payload: dict) -> dict:
    if payload.get("engine_version") != ENGINE_VERSION:
        raise JointTemporalEngineError("artifact_engine_version_invalid")
    if payload.get("status") != "frozen_production":
        raise JointTemporalEngineError("artifact_not_frozen_for_production")
    if payload.get("production_authorized") is not True:
        raise JointTemporalEngineError("artifact_production_not_authorized")
    if tuple(payload.get("feature_names") or ()) != FEATURE_NAMES:
        raise JointTemporalEngineError("artifact_feature_schema_invalid")
    if payload.get("reference_horizon_seconds") != REFERENCE_HORIZON_SECONDS:
        raise JointTemporalEngineError("artifact_reference_horizon_invalid")
    if payload.get("base_interval_seconds") != BASE_INTERVAL_SECONDS:
        raise JointTemporalEngineError("artifact_base_interval_invalid")
    if payload.get("horizon_seconds") != HORIZON_SECONDS:
        raise JointTemporalEngineError("artifact_horizon_contract_invalid")
    expected = str(payload.get("artifact_sha256") or "")
    actual = canonical_sha256(_artifact_without_hash(payload))
    if expected != actual:
        raise JointTemporalEngineError("artifact_hash_invalid")

    scaling = payload.get("feature_standardization")
    coefficients = payload.get("coefficients")
    if not isinstance(scaling, dict) or set(scaling) != set(FEATURE_NAMES):
        raise JointTemporalEngineError("artifact_standardization_invalid")
    if not isinstance(coefficients, dict) or set(coefficients) != {"tp", "sl"}:
        raise JointTemporalEngineError("artifact_coefficients_invalid")
    if any(set(coefficients[cause]) != set(FIT_FEATURE_NAMES) for cause in ("tp", "sl")):
        raise JointTemporalEngineError("artifact_coefficient_schema_invalid")
    for name in FEATURE_NAMES:
        _finite(scaling[name].get("mean"), f"{name}_mean")
        if _positive(scaling[name].get("scale"), f"{name}_scale") <= 0:
            raise JointTemporalEngineError("artifact_scale_invalid")
    for cause in ("tp", "sl"):
        for name in FIT_FEATURE_NAMES:
            _finite(coefficients[cause][name], f"{cause}_{name}")

    tolerance = 1e-12
    if abs(coefficients["tp"]["intercept"] - coefficients["sl"]["intercept"]) > tolerance:
        raise JointTemporalEngineError("movement_intercept_not_shared")
    if abs(
        coefficients["tp"][VOLATILITY_FEATURE]
        - coefficients["sl"][VOLATILITY_FEATURE]
    ) > tolerance:
        raise JointTemporalEngineError("volatility_effect_not_shared")
    if coefficients["tp"][VOLATILITY_FEATURE] < 0:
        raise JointTemporalEngineError("volatility_resolution_effect_negative")
    for name in DIRECTIONAL_FEATURES:
        if abs(coefficients["tp"][name] + coefficients["sl"][name]) > tolerance:
            raise JointTemporalEngineError(
                f"directional_effect_not_antisymmetric:{name}"
            )
    return payload


@lru_cache(maxsize=1)
def load_production_artifact() -> dict:
    payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    return validate_artifact(payload)


def standardized_features(
    feature_values: dict[str, float],
    artifact: dict,
) -> dict[str, float]:
    if set(feature_values) != set(FEATURE_NAMES):
        raise JointTemporalEngineError("feature_snapshot_schema_invalid")
    scaling = artifact["feature_standardization"]
    return {
        "intercept": 1.0,
        **{
            name: (
                _finite(feature_values[name], name)
                - _finite(scaling[name]["mean"], f"{name}_mean")
            )
            / _positive(scaling[name]["scale"], f"{name}_scale")
            for name in FEATURE_NAMES
        },
    }


def plan_log_distances(
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
) -> tuple[float, float]:
    normalized_side = str(side).lower()
    entry_value = _positive(entry, "entry")
    tp_value = _positive(take_profit, "take_profit")
    sl_value = _positive(stop_loss, "stop_loss")
    if normalized_side == "long":
        if not sl_value < entry_value < tp_value:
            raise JointTemporalEngineError("long_plan_geometry_invalid")
        return (
            math.log(tp_value / entry_value),
            math.log(entry_value / sl_value),
        )
    if normalized_side == "short":
        if not tp_value < entry_value < sl_value:
            raise JointTemporalEngineError("short_plan_geometry_invalid")
        return (
            math.log(entry_value / tp_value),
            math.log(sl_value / entry_value),
        )
    raise JointTemporalEngineError("side_must_be_long_or_short")


def _linear_predictor(coefficients: dict, features: dict) -> float:
    value = math.fsum(
        float(coefficients[name]) * float(features[name])
        for name in FIT_FEATURE_NAMES
    )
    if not math.isfinite(value):
        raise JointTemporalEngineError("linear_predictor_invalid")
    return value


def validate_temporal_curve(curve: dict[str, dict[str, float]]) -> None:
    if set(curve) != set(HORIZON_SECONDS):
        raise JointTemporalEngineError("temporal_curve_horizons_invalid")
    ordered = sorted(HORIZON_SECONDS, key=HORIZON_SECONDS.get)
    previous_tp = -1.0
    previous_sl = -1.0
    previous_expiry = 2.0
    for horizon in ordered:
        probabilities = curve[horizon]
        if set(probabilities) != set(CLASSES):
            raise JointTemporalEngineError("temporal_curve_classes_invalid")
        values = [_finite(probabilities[name], name) for name in CLASSES]
        if any(value < -1e-12 or value > 1.0 + 1e-12 for value in values):
            raise JointTemporalEngineError("temporal_curve_probability_bounds")
        if abs(math.fsum(values) - 1.0) > 1e-12:
            raise JointTemporalEngineError("temporal_curve_probability_mass")
        tp = probabilities[CLASSES[0]]
        sl = probabilities[CLASSES[1]]
        expiry = probabilities[CLASSES[2]]
        if tp + 1e-12 < previous_tp or sl + 1e-12 < previous_sl:
            raise JointTemporalEngineError("first_touch_incidence_not_monotone")
        if expiry - 1e-12 > previous_expiry:
            raise JointTemporalEngineError("expiry_probability_not_monotone")
        previous_tp = tp
        previous_sl = sl
        previous_expiry = expiry


def joint_temporal_probabilities(
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    reference_sigma_24h: float,
    feature_values: dict[str, float],
    artifact: dict | None = None,
) -> dict:
    model = validate_artifact(artifact) if artifact is not None else load_production_artifact()
    tp_distance, sl_distance = plan_log_distances(
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
    )
    sigma_reference = _positive(reference_sigma_24h, "reference_sigma_24h")
    sigma_max = sigma_reference * math.sqrt(
        MAX_HORIZON_SECONDS / REFERENCE_HORIZON_SECONDS
    )
    features = standardized_features(feature_values, model)
    eta_tp = _linear_predictor(model["coefficients"]["tp"], features)
    eta_sl = _linear_predictor(model["coefficients"]["sl"], features)
    baseline = build_baseline_intervals(
        tp_log_distance=tp_distance,
        sl_log_distance=sl_distance,
        sigma_horizon=sigma_max,
        interval_count=MAX_INTERVAL_COUNT,
    )

    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    by_step = {}
    interval_trace = []
    selected_steps = set(HORIZON_STEPS.values())
    for item in baseline:
        h_tp, h_sl, h_none = adjusted_interval_hazards(
            item,
            eta_tp,
            eta_sl,
        )
        incidence_tp = survival * h_tp
        incidence_sl = survival * h_sl
        cumulative_tp += incidence_tp
        cumulative_sl += incidence_sl
        survival *= h_none
        step = int(item["interval"])
        if step in selected_steps:
            mass = cumulative_tp + cumulative_sl + survival
            if mass != 1.0:
                survival += 1.0 - mass
            by_step[step] = {
                CLASSES[0]: cumulative_tp,
                CLASSES[1]: cumulative_sl,
                CLASSES[2]: survival,
            }
        interval_trace.append(
            {
                "interval": step,
                "end_seconds": step * BASE_INTERVAL_SECONDS,
                "adjusted_h_tp": h_tp,
                "adjusted_h_sl": h_sl,
                "adjusted_h_none": h_none,
                "cumulative_tp": cumulative_tp,
                "cumulative_sl": cumulative_sl,
                "survival": survival,
            }
        )

    curve = {
        horizon: by_step[HORIZON_STEPS[horizon]]
        for horizon in HORIZON_SECONDS
    }
    validate_temporal_curve(curve)
    result = {
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "status": "evaluated_active",
        "single_engine": True,
        "parallel_probability_engines_executed": 0,
        "artifact_id": model["artifact_id"],
        "artifact_sha256": model["artifact_sha256"],
        "reference_horizon_seconds": REFERENCE_HORIZON_SECONDS,
        "reference_sigma_24h": sigma_reference,
        "maximum_horizon_seconds": MAX_HORIZON_SECONDS,
        "base_interval_seconds": BASE_INTERVAL_SECONDS,
        "plan": {
            "side": str(side).lower(),
            "entry": float(entry),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
            "tp_log_distance": tp_distance,
            "sl_log_distance": sl_distance,
        },
        "standardized_features": features,
        "linear_predictors": {"tp": eta_tp, "sl": eta_sl},
        "probability_curve": curve,
        "invariants": {
            "tp_cumulative_non_decreasing": True,
            "sl_cumulative_non_decreasing": True,
            "expiry_non_increasing": True,
            "mass_equals_one_each_horizon": True,
            "first_touch_absorbing": True,
        },
        "interval_trace": interval_trace,
        "production_effect": "served",
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def select_horizon(result: dict, time_horizon: str) -> dict[str, float]:
    try:
        probabilities = result["probability_curve"][time_horizon]
    except KeyError as exc:
        raise JointTemporalEngineError("unsupported_time_horizon") from exc
    return dict(probabilities)
