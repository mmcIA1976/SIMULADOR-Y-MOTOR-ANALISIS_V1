from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from multiscale_feature_runtime import FLAT_FEATURE_NAMES, STAGE_ORDER, STAGE_PROFILES
from sequential_first_touch_math import double_barrier_first_touch


ROOT = Path(__file__).resolve().parent
ARTIFACT_PATH = ROOT / "auditorias_motor" / "motor_v0_8_sequential_multiscale.json"
ENGINE_VERSION = "TP-SL-SEQUENTIAL-MULTISCALE-v0.8"
SCORING_VERSION = "sequential-conditional-first-touch-frozen-v0.8"
RUNTIME_VERSION = "sequential-multiscale-runtime-v0.8"
HORIZON_SECONDS = {
    horizon: int(profile["horizon_seconds"])
    for horizon, profile in STAGE_PROFILES.items()
}
CONDITIONAL_CLASSES = (
    "tp_first_in_stage",
    "sl_first_in_stage",
    "survive_stage",
)
CUMULATIVE_CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)


class SequentialTemporalEngineError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_artifact(payload: dict) -> dict:
    expected_hash = str(payload.get("artifact_sha256") or "")
    actual_hash = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"}
    )
    if expected_hash != actual_hash:
        raise SequentialTemporalEngineError("artifact_hash_invalid")
    if payload.get("engine_version") != ENGINE_VERSION:
        raise SequentialTemporalEngineError("artifact_engine_version_invalid")
    if payload.get("scoring_version") != SCORING_VERSION:
        raise SequentialTemporalEngineError("artifact_scoring_version_invalid")
    if payload.get("status") != "frozen_production":
        raise SequentialTemporalEngineError("artifact_not_frozen_for_production")
    if payload.get("production_authorized") is not True:
        raise SequentialTemporalEngineError("artifact_not_authorized")
    if payload.get("single_engine") is not True:
        raise SequentialTemporalEngineError("artifact_not_single_engine")
    if payload.get("parallel_probability_engines") != 0:
        raise SequentialTemporalEngineError("parallel_engines_not_allowed")
    if tuple(payload.get("stage_order") or ()) != STAGE_ORDER:
        raise SequentialTemporalEngineError("artifact_stage_order_invalid")
    for horizon in STAGE_ORDER:
        if payload["stage_profiles"].get(horizon) != STAGE_PROFILES[horizon]:
            raise SequentialTemporalEngineError(
                f"artifact_stage_profile_invalid:{horizon}"
            )
        model = payload["stage_models"].get(horizon)
        if not isinstance(model, dict):
            raise SequentialTemporalEngineError(f"stage_model_missing:{horizon}")
        if model.get("enabled") is False:
            continue
        scaling = model.get("scaling")
        coefficients = model.get("coefficients")
        if not isinstance(scaling, dict) or not isinstance(coefficients, dict):
            raise SequentialTemporalEngineError(
                f"stage_model_schema_invalid:{horizon}"
            )
        if set(coefficients) != set(CONDITIONAL_CLASSES[:2]):
            raise SequentialTemporalEngineError(
                f"stage_coefficient_classes_invalid:{horizon}"
            )
        names = set(next(iter(coefficients.values())))
        if "intercept" not in names or set(scaling) != names - {"intercept"}:
            raise SequentialTemporalEngineError(
                f"stage_feature_schema_invalid:{horizon}"
            )
        if any(set(values) != names for values in coefficients.values()):
            raise SequentialTemporalEngineError(
                f"stage_coefficient_schema_invalid:{horizon}"
            )
        for item in scaling.values():
            if not math.isfinite(float(item["mean"])) or float(item["scale"]) <= 0:
                raise SequentialTemporalEngineError(
                    f"stage_scaling_invalid:{horizon}"
                )
        if any(
            not math.isfinite(float(value))
            for values in coefficients.values()
            for value in values.values()
        ):
            raise SequentialTemporalEngineError(
                f"stage_coefficient_nonfinite:{horizon}"
            )
    return payload


@lru_cache(maxsize=1)
def load_production_artifact() -> dict:
    return validate_artifact(json.loads(ARTIFACT_PATH.read_text(encoding="utf-8")))


def selected_stage_order(time_horizon: str) -> tuple[str, ...]:
    try:
        index = STAGE_ORDER.index(str(time_horizon))
    except ValueError as exc:
        raise SequentialTemporalEngineError("unsupported_time_horizon") from exc
    return STAGE_ORDER[: index + 1]


def plan_log_distances(
    *, side: str, entry: float, take_profit: float, stop_loss: float
) -> tuple[float, float]:
    entry_value = float(entry)
    tp_value = float(take_profit)
    sl_value = float(stop_loss)
    if not all(
        math.isfinite(value) and value > 0
        for value in (entry_value, tp_value, sl_value)
    ):
        raise SequentialTemporalEngineError("plan_prices_invalid")
    if str(side).lower() == "long" and sl_value < entry_value < tp_value:
        return math.log(tp_value / entry_value), math.log(entry_value / sl_value)
    if str(side).lower() == "short" and tp_value < entry_value < sl_value:
        return math.log(entry_value / tp_value), math.log(sl_value / entry_value)
    raise SequentialTemporalEngineError("plan_geometry_invalid")


def _cumulative_baseline(
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    stage_contexts: dict[str, dict],
    horizons: tuple[str, ...],
) -> dict[str, dict[str, float]]:
    tp_distance, sl_distance = plan_log_distances(
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
    )
    cumulative_variance = 0.0
    curve = {}
    for horizon in horizons:
        profile = STAGE_PROFILES[horizon]
        sigma = float(stage_contexts[horizon]["context_sigma"])
        if not math.isfinite(sigma) or sigma <= 0:
            raise SequentialTemporalEngineError(
                f"stage_context_sigma_invalid:{horizon}"
            )
        cumulative_variance += sigma * sigma * (
            float(profile["increment_seconds"]) / float(profile["horizon_seconds"])
        )
        result = double_barrier_first_touch(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=math.sqrt(cumulative_variance),
            time_fraction=1.0,
        )
        curve[horizon] = {
            CUMULATIVE_CLASSES[0]: result.p_tp,
            CUMULATIVE_CLASSES[1]: result.p_sl,
            CUMULATIVE_CLASSES[2]: result.p_expiry,
        }
    return curve


def _conditional_baseline(
    curve: dict[str, dict[str, float]], horizons: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    previous_tp = previous_sl = 0.0
    previous_survival = 1.0
    result = {}
    for horizon in horizons:
        cumulative = curve[horizon]
        if previous_survival <= 1e-12:
            conditional = {
                CONDITIONAL_CLASSES[0]: 0.0,
                CONDITIONAL_CLASSES[1]: 0.0,
                CONDITIONAL_CLASSES[2]: 1.0,
            }
        else:
            conditional = {
                CONDITIONAL_CLASSES[0]: max(
                    0.0, cumulative[CUMULATIVE_CLASSES[0]] - previous_tp
                )
                / previous_survival,
                CONDITIONAL_CLASSES[1]: max(
                    0.0, cumulative[CUMULATIVE_CLASSES[1]] - previous_sl
                )
                / previous_survival,
                CONDITIONAL_CLASSES[2]: max(
                    0.0, cumulative[CUMULATIVE_CLASSES[2]]
                )
                / previous_survival,
            }
            mass = math.fsum(conditional.values())
            conditional = {
                name: value / mass for name, value in conditional.items()
            }
        result[horizon] = conditional
        previous_tp = cumulative[CUMULATIVE_CLASSES[0]]
        previous_sl = cumulative[CUMULATIVE_CLASSES[1]]
        previous_survival = cumulative[CUMULATIVE_CLASSES[2]]
    return result


def raw_stage_features(
    *,
    stage_index: int,
    tp_distance: float,
    sl_distance: float,
    stage_contexts: dict[str, dict],
) -> dict[str, float]:
    horizon = STAGE_ORDER[stage_index]
    sigma = float(stage_contexts[horizon]["context_sigma"])
    result = {
        "intercept": 1.0,
        "geometry::tp_sigma_units": tp_distance / sigma,
        "geometry::sl_sigma_units": sl_distance / sigma,
        "geometry::log_tp_sl_ratio": math.log(tp_distance / sl_distance),
        "geometry::log_context_sigma": math.log(sigma),
    }
    for inherited in STAGE_ORDER[: stage_index + 1]:
        values = stage_contexts[inherited]["feature_values"]
        if set(values) != set(FLAT_FEATURE_NAMES):
            raise SequentialTemporalEngineError(
                f"stage_feature_values_invalid:{inherited}"
            )
        for name in FLAT_FEATURE_NAMES:
            result[f"{inherited}::{name}"] = float(values[name])
        result[f"{inherited}::context_sigma"] = float(
            stage_contexts[inherited]["context_sigma"]
        )
    return result


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    maximum = max(logits.values())
    values = {name: math.exp(value - maximum) for name, value in logits.items()}
    total = math.fsum(values.values())
    if not math.isfinite(total) or total <= 0:
        raise SequentialTemporalEngineError("softmax_denominator_invalid")
    return {name: value / total for name, value in values.items()}


def _apply_stage_model(
    baseline: dict[str, float], raw_features: dict[str, float], model: dict
) -> tuple[dict[str, float], dict]:
    if model.get("enabled") is False:
        return dict(baseline), {
            "rule_layer_enabled": False,
            "reason": "directional_rules_rejected_out_of_sample",
            "feature_contributions": {},
        }
    scaling = model["scaling"]
    expected_names = set(next(iter(model["coefficients"].values())))
    if set(raw_features) != expected_names:
        raise SequentialTemporalEngineError("runtime_feature_schema_mismatch")
    standardized = {
        name: (
            value
            if name == "intercept"
            else (value - float(scaling[name]["mean"]))
            / float(scaling[name]["scale"])
        )
        for name, value in raw_features.items()
    }
    logits = {
        name: math.log(max(float(baseline[name]), 1e-15))
        for name in CONDITIONAL_CLASSES
    }
    contributions = {}
    for cause in CONDITIONAL_CLASSES[:2]:
        contributions[cause] = {}
        for name, value in standardized.items():
            coefficient = float(model["coefficients"][cause].get(name, 0.0))
            contribution = coefficient * value
            logits[cause] += contribution
            contributions[cause][name] = {
                "raw_value": float(raw_features[name]),
                "standardized_value": float(value),
                "coefficient": coefficient,
                "linear_contribution": contribution,
            }
    return _softmax(logits), {
        "rule_layer_enabled": True,
        "ridge": model["ridge"],
        "feature_contributions": contributions,
    }


def validate_temporal_curve(curve: dict[str, dict[str, float]]) -> None:
    previous_tp = previous_sl = 0.0
    previous_expiry = 1.0
    for horizon in curve:
        probabilities = curve[horizon]
        if set(probabilities) != set(CUMULATIVE_CLASSES):
            raise SequentialTemporalEngineError("curve_class_schema_invalid")
        values = [float(probabilities[name]) for name in CUMULATIVE_CLASSES]
        if any(value < -1e-12 or value > 1.0 + 1e-12 for value in values):
            raise SequentialTemporalEngineError("curve_probability_bounds")
        if abs(math.fsum(values) - 1.0) > 1e-12:
            raise SequentialTemporalEngineError("curve_probability_mass")
        tp, sl, expiry = values
        if tp + 1e-12 < previous_tp or sl + 1e-12 < previous_sl:
            raise SequentialTemporalEngineError("curve_first_touch_not_monotone")
        if expiry - 1e-12 > previous_expiry:
            raise SequentialTemporalEngineError("curve_expiry_not_monotone")
        previous_tp, previous_sl, previous_expiry = tp, sl, expiry


def sequential_probabilities(
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    time_horizon: str,
    stage_contexts: dict[str, dict],
    artifact: dict | None = None,
) -> dict:
    model_artifact = validate_artifact(artifact) if artifact else load_production_artifact()
    horizons = selected_stage_order(time_horizon)
    if set(stage_contexts) != set(horizons):
        raise SequentialTemporalEngineError("executed_stage_contexts_invalid")
    tp_distance, sl_distance = plan_log_distances(
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
    )
    cumulative_baseline = _cumulative_baseline(
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
        stage_contexts=stage_contexts,
        horizons=horizons,
    )
    conditional_baseline = _conditional_baseline(cumulative_baseline, horizons)
    survival = 1.0
    cumulative_tp = cumulative_sl = 0.0
    curve = {}
    stages = []
    for stage_index, horizon in enumerate(horizons):
        raw_features = raw_stage_features(
            stage_index=stage_index,
            tp_distance=tp_distance,
            sl_distance=sl_distance,
            stage_contexts=stage_contexts,
        )
        probabilities, model_trace = _apply_stage_model(
            conditional_baseline[horizon],
            raw_features,
            model_artifact["stage_models"][horizon],
        )
        survival_before = survival
        cumulative_tp += survival_before * probabilities[CONDITIONAL_CLASSES[0]]
        cumulative_sl += survival_before * probabilities[CONDITIONAL_CLASSES[1]]
        survival *= probabilities[CONDITIONAL_CLASSES[2]]
        survival += 1.0 - (cumulative_tp + cumulative_sl + survival)
        curve[horizon] = {
            CUMULATIVE_CLASSES[0]: cumulative_tp,
            CUMULATIVE_CLASSES[1]: cumulative_sl,
            CUMULATIVE_CLASSES[2]: survival,
        }
        stages.append(
            {
                "stage_id": STAGE_PROFILES[horizon]["stage_id"],
                "time_horizon": horizon,
                "label": STAGE_PROFILES[horizon]["label"],
                "interval": STAGE_PROFILES[horizon]["interval"],
                "increment_seconds": STAGE_PROFILES[horizon]["increment_seconds"],
                "survival_entering_stage": survival_before,
                "baseline_conditional_probabilities": conditional_baseline[horizon],
                "conditional_probabilities": probabilities,
                "cumulative_probabilities": curve[horizon],
                "context_sigma": stage_contexts[horizon]["context_sigma"],
                "source_data_sha256": stage_contexts[horizon][
                    "source_data_sha256"
                ],
                **model_trace,
            }
        )
    validate_temporal_curve(curve)
    selected = curve[time_horizon]
    result = {
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "single_engine": True,
        "parallel_probability_engines_executed": 0,
        "artifact_id": model_artifact["artifact_id"],
        "artifact_sha256": model_artifact["artifact_sha256"],
        "selected_horizon": time_horizon,
        "executed_stage_count": len(horizons),
        "executed_stages": list(horizons),
        "plan": {
            "side": str(side).lower(),
            "entry": float(entry),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
            "tp_log_distance": tp_distance,
            "sl_log_distance": sl_distance,
        },
        "stage_traces": stages,
        "probability_curve": curve,
        "probabilities": selected,
        "decision_probabilities": {
            "tp_before_sl_within_horizon": selected[CUMULATIVE_CLASSES[0]],
            "sl_before_tp_within_horizon": selected[CUMULATIVE_CLASSES[1]],
            "neither_before_expiry": selected[CUMULATIVE_CLASSES[2]],
            "resolution_within_horizon": (
                selected[CUMULATIVE_CLASSES[0]] + selected[CUMULATIVE_CLASSES[1]]
            ),
            "tp_given_resolution": (
                selected[CUMULATIVE_CLASSES[0]]
                / (
                    selected[CUMULATIVE_CLASSES[0]]
                    + selected[CUMULATIVE_CLASSES[1]]
                )
                if selected[CUMULATIVE_CLASSES[0]]
                + selected[CUMULATIVE_CLASSES[1]]
                > 0
                else 0.5
            ),
        },
        "invariants": {
            "first_touch_absorbing": True,
            "tp_cumulative_non_decreasing": True,
            "sl_cumulative_non_decreasing": True,
            "expiry_non_increasing": True,
            "probability_mass_one": True,
            "later_stages_only_receive_survivors": True,
        },
        "production_effect": "served",
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


__all__ = (
    "CUMULATIVE_CLASSES",
    "ENGINE_VERSION",
    "HORIZON_SECONDS",
    "RUNTIME_VERSION",
    "SCORING_VERSION",
    "SequentialTemporalEngineError",
    "canonical_sha256",
    "load_production_artifact",
    "selected_stage_order",
    "sequential_probabilities",
    "validate_temporal_curve",
)
