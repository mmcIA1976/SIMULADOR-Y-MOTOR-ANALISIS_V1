from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import math
import random
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from multiscale_feature_runtime import STAGE_ORDER, STAGE_PROFILES


ROOT = Path(__file__).resolve().parent
ARTIFACT_PATH = ROOT / "auditorias_motor" / "motor_v0_11_empirical_analog.json.gz"
ENGINE_VERSION = "TP-SL-EMPIRICAL-ANALOG-v0.11"
SCORING_VERSION = "historical-analog-first-touch-v0.11"
RUNTIME_VERSION = "empirical-analog-runtime-v0.11"

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
STAGE_BOUNDS = {
    "intraday_short": (0, 48),
    "intraday_wide": (48, 288),
    "short_swing": (288, 2016),
}
HORIZON_SECONDS = {
    name: int(profile["horizon_seconds"])
    for name, profile in STAGE_PROFILES.items()
}


class EmpiricalTemporalEngineError(ValueError):
    pass


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def selected_stage_order(time_horizon: str) -> tuple[str, ...]:
    try:
        index = STAGE_ORDER.index(str(time_horizon))
    except ValueError as exc:
        raise EmpiricalTemporalEngineError("unsupported_time_horizon") from exc
    return STAGE_ORDER[: index + 1]


def _validate_probability_map(values: dict[str, float], names: tuple[str, ...]) -> None:
    if set(values) != set(names):
        raise EmpiricalTemporalEngineError("probability_schema_invalid")
    probabilities = [float(values[name]) for name in names]
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in probabilities):
        raise EmpiricalTemporalEngineError("probability_bounds_invalid")
    if abs(math.fsum(probabilities) - 1.0) > 1e-10:
        raise EmpiricalTemporalEngineError("probability_mass_invalid")


def validate_artifact(payload: dict) -> dict:
    expected_hash = str(payload.get("artifact_sha256") or "")
    actual_hash = canonical_sha256(
        {key: value for key, value in payload.items() if key != "artifact_sha256"}
    )
    if expected_hash != actual_hash:
        raise EmpiricalTemporalEngineError("artifact_hash_invalid")
    if payload.get("engine_version") != ENGINE_VERSION:
        raise EmpiricalTemporalEngineError("artifact_engine_version_invalid")
    if payload.get("scoring_version") != SCORING_VERSION:
        raise EmpiricalTemporalEngineError("artifact_scoring_version_invalid")
    if payload.get("status") != "frozen_production":
        raise EmpiricalTemporalEngineError("artifact_not_frozen_for_production")
    if payload.get("production_authorized") is not True:
        raise EmpiricalTemporalEngineError("artifact_not_authorized")
    if payload.get("single_engine") is not True:
        raise EmpiricalTemporalEngineError("artifact_not_single_engine")
    if payload.get("parallel_probability_engines") != 0:
        raise EmpiricalTemporalEngineError("parallel_engines_not_allowed")
    if tuple(payload.get("stage_order") or ()) != STAGE_ORDER:
        raise EmpiricalTemporalEngineError("artifact_stage_order_invalid")
    if not isinstance(payload.get("analogs"), list) or not payload["analogs"]:
        raise EmpiricalTemporalEngineError("artifact_analogs_missing")
    for horizon in STAGE_ORDER:
        names = payload.get("feature_names", {}).get(horizon)
        scaling = payload.get("feature_scaling", {}).get(horizon)
        if not isinstance(names, list) or not names:
            raise EmpiricalTemporalEngineError(f"artifact_features_missing:{horizon}")
        if not isinstance(scaling, list) or len(scaling) != len(names):
            raise EmpiricalTemporalEngineError(f"artifact_scaling_invalid:{horizon}")
        for item in scaling:
            if not math.isfinite(float(item[0])) or not math.isfinite(float(item[1])):
                raise EmpiricalTemporalEngineError(f"artifact_scaling_nonfinite:{horizon}")
            if float(item[1]) <= 0.0:
                raise EmpiricalTemporalEngineError(f"artifact_scaling_nonpositive:{horizon}")
    profiles = payload.get("target_horizon_rule_profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(STAGE_ORDER):
        raise EmpiricalTemporalEngineError("artifact_target_profiles_invalid")
    declared_profile_ids = {}
    for target_horizon in STAGE_ORDER:
        profile = profiles.get(target_horizon)
        overrides = profile.get("overrides") if isinstance(profile, dict) else None
        if not isinstance(overrides, dict):
            raise EmpiricalTemporalEngineError(
                f"artifact_target_overrides_invalid:{target_horizon}"
            )
        allowed_stages = set(selected_stage_order(target_horizon))
        if not set(overrides) <= allowed_stages:
            raise EmpiricalTemporalEngineError(
                f"artifact_target_override_stage_invalid:{target_horizon}"
            )
        for stage, override in overrides.items():
            profile_id = str(override.get("profile_id") or "")
            names = override.get("feature_names")
            scaling = override.get("feature_scaling")
            if not profile_id or profile_id in declared_profile_ids:
                raise EmpiricalTemporalEngineError(
                    f"artifact_target_profile_id_invalid:{target_horizon}:{stage}"
                )
            if override.get("distance_method") != "coordinate_equal":
                raise EmpiricalTemporalEngineError(
                    f"artifact_target_distance_method_invalid:{target_horizon}:{stage}"
                )
            if not isinstance(names, list) or not names:
                raise EmpiricalTemporalEngineError(
                    f"artifact_target_features_invalid:{target_horizon}:{stage}"
                )
            if not isinstance(scaling, list) or len(scaling) != len(names):
                raise EmpiricalTemporalEngineError(
                    f"artifact_target_scaling_invalid:{target_horizon}:{stage}"
                )
            support_limit = float(
                override.get("maximum_nearest_context_distance", 0.0)
            )
            if not math.isfinite(support_limit) or support_limit <= 0.0:
                raise EmpiricalTemporalEngineError(
                    f"artifact_target_support_invalid:{target_horizon}:{stage}"
                )
            declared_profile_ids[profile_id] = len(names)
    for analog in payload["analogs"]:
        vectors = analog.get("target_profile_feature_vectors")
        if not isinstance(vectors, dict) or set(vectors) != set(declared_profile_ids):
            raise EmpiricalTemporalEngineError(
                f"artifact_target_vectors_invalid:{analog.get('id')}"
            )
        for profile_id, width in declared_profile_ids.items():
            orientations = vectors.get(profile_id)
            if (
                not isinstance(orientations, list)
                or len(orientations) != 2
                or any(
                    not isinstance(vector, list) or len(vector) != width
                    for vector in orientations
                )
            ):
                raise EmpiricalTemporalEngineError(
                    f"artifact_target_vector_width_invalid:{analog.get('id')}:{profile_id}"
                )
    active_by_target = payload.get("active_rule_ids_by_target_horizon")
    if not isinstance(active_by_target, dict) or set(active_by_target) != set(
        STAGE_ORDER
    ):
        raise EmpiricalTemporalEngineError("artifact_target_active_rules_invalid")
    for target_horizon in STAGE_ORDER:
        expected_active = set()
        profile = profiles[target_horizon]
        for stage in selected_stage_order(target_horizon):
            override = profile["overrides"].get(stage)
            names = (
                override["feature_names"]
                if override is not None
                else payload["feature_names"][stage]
            )
            expected_active.update(
                parts[1]
                for name in names
                if len(parts := str(name).split("::", 2)) == 3
            )
        if set(active_by_target[target_horizon]) != expected_active:
            raise EmpiricalTemporalEngineError(
                f"artifact_target_active_rules_mismatch:{target_horizon}"
            )
    return payload


@lru_cache(maxsize=1)
def load_production_artifact() -> dict:
    with gzip.open(ARTIFACT_PATH, "rt", encoding="utf-8") as source:
        return validate_artifact(json.load(source))


def plan_log_distances(
    *, side: str, entry: float, take_profit: float, stop_loss: float
) -> tuple[float, float]:
    values = (float(entry), float(take_profit), float(stop_loss))
    if not all(math.isfinite(value) and value > 0.0 for value in values):
        raise EmpiricalTemporalEngineError("plan_prices_invalid")
    entry_value, tp_value, sl_value = values
    if str(side).lower() == "long" and sl_value < entry_value < tp_value:
        return math.log(tp_value / entry_value), math.log(entry_value / sl_value)
    if str(side).lower() == "short" and tp_value < entry_value < sl_value:
        return math.log(entry_value / tp_value), math.log(sl_value / entry_value)
    raise EmpiricalTemporalEngineError("plan_geometry_invalid")


def _current_feature_map(
    horizon: str,
    stage_contexts: dict[str, dict],
    feature_names: list[str],
) -> dict[str, float]:
    inherited = selected_stage_order(horizon)
    values: dict[str, float] = {}
    for stage in inherited:
        context = stage_contexts.get(stage)
        if not isinstance(context, dict):
            raise EmpiricalTemporalEngineError(f"stage_context_missing:{stage}")
        feature_values = context.get("feature_values")
        if not isinstance(feature_values, dict):
            raise EmpiricalTemporalEngineError(f"stage_features_missing:{stage}")
        for name, value in feature_values.items():
            values[f"{stage}::{name}"] = float(value)
        sigma = float(context.get("context_sigma") or 0.0)
        if not math.isfinite(sigma) or sigma <= 0.0:
            raise EmpiricalTemporalEngineError(f"stage_context_sigma_invalid:{stage}")
        values[f"{stage}::log_context_sigma"] = math.log(sigma)
    missing = [name for name in feature_names if name not in values]
    if missing:
        raise EmpiricalTemporalEngineError(
            "runtime_feature_schema_mismatch:" + ",".join(missing)
        )
    return {name: float(values[name]) for name in feature_names}


def _standardize(values: dict[str, float], names: list[str], scaling: list[list[float]]) -> list[float]:
    result = []
    for name, (center, scale) in zip(names, scaling):
        value = float(values[name])
        if not math.isfinite(value):
            raise EmpiricalTemporalEngineError(f"runtime_feature_nonfinite:{name}")
        result.append((value - float(center)) / float(scale))
    return result


def _distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise EmpiricalTemporalEngineError("analog_feature_vector_invalid")
    squared = math.fsum(min(36.0, (a - b) ** 2) for a, b in zip(left, right))
    return math.sqrt(squared / len(left))


def _first_crossing(frontier: list[list[float]], threshold: float) -> int | None:
    if not frontier:
        return None
    levels = [float(item[0]) for item in frontier]
    index = bisect.bisect_left(levels, float(threshold))
    if index >= len(frontier):
        return None
    return int(frontier[index][1])


def _stage_label(
    analog: dict,
    orientation: int,
    *,
    tp_distance: float,
    sl_distance: float,
    start_step: int,
    end_step: int,
) -> str | None:
    if orientation == 0:
        favorable = analog["up_frontier"]
        adverse = analog["down_frontier"]
    else:
        favorable = analog["down_frontier"]
        adverse = analog["up_frontier"]
    tp_step = _first_crossing(favorable, tp_distance)
    sl_step = _first_crossing(adverse, sl_distance)
    first_step = min(
        tp_step if tp_step is not None else 10**9,
        sl_step if sl_step is not None else 10**9,
    )
    if first_step <= start_step:
        return None
    if first_step > end_step:
        return CONDITIONAL_CLASSES[2]
    if tp_step == sl_step:
        return "ambiguous"
    if tp_step is not None and tp_step == first_step:
        return CONDITIONAL_CLASSES[0]
    return CONDITIONAL_CLASSES[1]


def _nearest_eligible(
    *,
    artifact: dict,
    horizon: str,
    current: list[float],
    symbol: str,
    tp_distance: float,
    sl_distance: float,
    analysis_epoch: float,
    target_override: dict | None = None,
) -> tuple[list[dict], dict]:
    stage_index = STAGE_ORDER.index(horizon)
    start_step, end_step = STAGE_BOUNDS[horizon]
    cross_symbol_penalty = float(artifact["selection"]["cross_symbol_penalty"])
    recency_penalty = float(
        artifact["selection"].get("recency_penalty_per_year", 0.0)
    )
    ranked = []
    for analog in artifact["analogs"]:
        analog_epoch = float(analog["analysis_epoch"])
        if analog_epoch >= analysis_epoch:
            continue
        same_symbol = str(analog["symbol"]).upper() == symbol.upper()
        for orientation in (0, 1):
            vector = (
                analog["target_profile_feature_vectors"][
                    target_override["profile_id"]
                ][orientation]
                if target_override is not None
                else analog["feature_vectors"][stage_index][orientation]
            )
            distance = _distance(current, vector)
            if not same_symbol:
                distance += cross_symbol_penalty
            age_years = max(
                0.0,
                (analysis_epoch - analog_epoch) / (365.25 * 24.0 * 3600.0),
            )
            distance += recency_penalty * age_years
            ranked.append((distance, analog, orientation, same_symbol))
    ranked.sort(key=lambda item: (item[0], item[1]["id"], item[2]))
    if not ranked:
        raise EmpiricalTemporalEngineError(f"historical_context_unavailable:{horizon}")
    if target_override is not None:
        support_limit = float(
            target_override["maximum_nearest_context_distance"]
        )
    else:
        support_limits = artifact["selection"].get(
            "maximum_nearest_context_distance_by_horizon", {}
        )
        support_limit = float(support_limits.get(horizon, math.inf))
    if float(ranked[0][0]) > support_limit:
        raise EmpiricalTemporalEngineError(
            f"context_outside_historical_support:{horizon}:"
            f"{float(ranked[0][0]):.6f}>{support_limit:.6f}"
        )
    target = int(artifact["selection"]["neighbor_count"])
    maximum = int(artifact["selection"].get("maximum_scanned", len(ranked)))
    selected = []
    ambiguous = 0
    pre_stage_resolved = 0
    scanned = 0
    for distance, analog, orientation, same_symbol in ranked[:maximum]:
        scanned += 1
        label = _stage_label(
            analog,
            orientation,
            tp_distance=tp_distance,
            sl_distance=sl_distance,
            start_step=start_step,
            end_step=end_step,
        )
        if label is None:
            pre_stage_resolved += 1
            continue
        if label == "ambiguous":
            ambiguous += 1
            continue
        selected.append(
            {
                "distance": float(distance),
                "label": label,
                "same_symbol": same_symbol,
                "analog_id": analog["id"],
                "orientation": "long" if orientation == 0 else "short",
            }
        )
        if len(selected) >= target:
            break
    return selected, {
        "ranked_candidates": len(ranked),
        "nearest_context_distance": float(ranked[0][0]),
        "maximum_context_distance_allowed": support_limit,
        "scanned_candidates": scanned,
        "selected_analogs": len(selected),
        "same_symbol_analogs": sum(1 for item in selected if item["same_symbol"]),
        "ambiguous_excluded": ambiguous,
        "resolved_before_stage_excluded": pre_stage_resolved,
        "conditional_sample_sparse": len(selected) < int(
            artifact["selection"]["minimum_analogs"]
        ),
        "conditional_sample_empty": not selected,
        "uncertainty_policy": "empirical_dirichlet_widens_when_survivors_are_sparse",
        "selection_profile_id": (
            target_override["profile_id"]
            if target_override is not None
            else f"v0_10_exact::{horizon}"
        ),
        "target_horizon_specific_override": target_override is not None,
    }


def target_stage_feature_names(
    artifact: dict, target_horizon: str, stage: str
) -> list[str]:
    profile = artifact["target_horizon_rule_profiles"][target_horizon]
    override = profile["overrides"].get(stage)
    return list(
        override["feature_names"]
        if override is not None
        else artifact["feature_names"][stage]
    )


def target_stage_active_outputs(
    artifact: dict, target_horizon: str, stage: str
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for name in target_stage_feature_names(artifact, target_horizon, stage):
        parts = str(name).split("::", 2)
        if len(parts) != 3:
            continue
        _, rule_id, output_name = parts
        result.setdefault(rule_id, []).append(output_name)
    return {rule_id: sorted(set(outputs)) for rule_id, outputs in result.items()}


def target_context_active_outputs(
    artifact: dict, target_horizon: str, context_stage: str
) -> dict[str, list[str]]:
    """Return outputs from one context used anywhere in the target chain."""

    result: dict[str, set[str]] = {}
    for selection_stage in selected_stage_order(target_horizon):
        for name in target_stage_feature_names(
            artifact, target_horizon, selection_stage
        ):
            parts = str(name).split("::", 2)
            if len(parts) != 3 or parts[0] != context_stage:
                continue
            _, rule_id, output_name = parts
            result.setdefault(rule_id, set()).add(output_name)
    return {
        rule_id: sorted(outputs) for rule_id, outputs in result.items()
    }


def _weighted_probabilities(
    selected: list[dict],
    *,
    probability_temperature: float = 1.0,
) -> tuple[dict[str, float], dict]:
    bandwidth = max(0.25, float(selected[-1]["distance"])) if selected else 1.0
    counts = {name: 0.0 for name in CONDITIONAL_CLASSES}
    weights = []
    for item in selected:
        weight = math.exp(-0.5 * (float(item["distance"]) / bandwidth) ** 2)
        counts[item["label"]] += weight
        weights.append(weight)
    prior_per_class = 0.5
    denominator = math.fsum(counts.values()) + prior_per_class * len(
        CONDITIONAL_CLASSES
    )
    probabilities = {
        name: (counts[name] + prior_per_class) / denominator
        for name in CONDITIONAL_CLASSES
    }
    temperature = float(probability_temperature)
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise EmpiricalTemporalEngineError("probability_temperature_invalid")
    tempered = {
        name: probabilities[name] ** (1.0 / temperature)
        for name in CONDITIONAL_CLASSES
    }
    tempered_total = math.fsum(tempered.values())
    probabilities = {
        name: tempered[name] / tempered_total for name in CONDITIONAL_CLASSES
    }
    _validate_probability_map(probabilities, CONDITIONAL_CLASSES)
    total_weight = math.fsum(weights)
    effective = (
        total_weight * total_weight / math.fsum(weight * weight for weight in weights)
        if weights
        else 0.0
    )
    return probabilities, {
        "kernel": "adaptive_gaussian",
        "bandwidth": bandwidth,
        "weighted_outcome_counts": counts,
        "dirichlet_prior_per_class": prior_per_class,
        "probability_temperature": temperature,
        "posterior_alpha": {
            name: counts[name] + prior_per_class for name in CONDITIONAL_CLASSES
        },
        "effective_sample_size": effective,
        "nearest_distance": float(selected[0]["distance"]) if selected else None,
        "furthest_selected_distance": (
            float(selected[-1]["distance"]) if selected else None
        ),
    }


def _sample_cumulative_ranges(
    stage_traces: list[dict], *, seed_material: dict, samples: int = 1200
) -> dict[str, dict[str, float]]:
    rng = random.Random(int(canonical_sha256(seed_material)[:16], 16))
    draws = {name: [] for name in CUMULATIVE_CLASSES}
    for _ in range(samples):
        cumulative_tp = 0.0
        cumulative_sl = 0.0
        survival = 1.0
        for trace in stage_traces:
            posterior = trace["posterior_alpha"]
            alpha = [float(posterior[name]) for name in CONDITIONAL_CLASSES]
            gamma = [rng.gammavariate(value, 1.0) for value in alpha]
            total = math.fsum(gamma)
            conditional = [value / total for value in gamma]
            temperature = float(trace["probability_temperature"])
            conditional = [value ** (1.0 / temperature) for value in conditional]
            tempered_total = math.fsum(conditional)
            conditional = [value / tempered_total for value in conditional]
            cumulative_tp += survival * conditional[0]
            cumulative_sl += survival * conditional[1]
            survival *= conditional[2]
        draws[CUMULATIVE_CLASSES[0]].append(cumulative_tp)
        draws[CUMULATIVE_CLASSES[1]].append(cumulative_sl)
        draws[CUMULATIVE_CLASSES[2]].append(survival)
    result = {}
    low_index = int(samples * 0.025)
    high_index = min(samples - 1, int(samples * 0.975))
    for name, values in draws.items():
        ordered = sorted(values)
        result[name] = {
            "low": ordered[low_index],
            "high": ordered[high_index],
            "method": "deterministic_dirichlet_neighbor_uncertainty_95pct",
        }
    return result


def validate_temporal_curve(curve: dict[str, dict[str, float]]) -> None:
    previous_tp = previous_sl = 0.0
    previous_survival = 1.0
    for horizon, probabilities in curve.items():
        _validate_probability_map(probabilities, CUMULATIVE_CLASSES)
        tp = probabilities[CUMULATIVE_CLASSES[0]]
        sl = probabilities[CUMULATIVE_CLASSES[1]]
        survival = probabilities[CUMULATIVE_CLASSES[2]]
        if tp + 1e-12 < previous_tp or sl + 1e-12 < previous_sl:
            raise EmpiricalTemporalEngineError(f"first_touch_not_monotone:{horizon}")
        if survival > previous_survival + 1e-12:
            raise EmpiricalTemporalEngineError(f"expiry_not_monotone:{horizon}")
        previous_tp, previous_sl, previous_survival = tp, sl, survival


def empirical_probabilities(
    *,
    symbol: str,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    time_horizon: str,
    stage_contexts: dict[str, dict],
    analysis_at: str,
    artifact: dict | None = None,
) -> dict:
    model = validate_artifact(artifact) if artifact is not None else load_production_artifact()
    try:
        analysis_epoch = datetime.fromisoformat(
            str(analysis_at).replace("Z", "+00:00")
        ).timestamp()
    except (TypeError, ValueError) as exc:
        raise EmpiricalTemporalEngineError("analysis_at_invalid") from exc
    horizons = selected_stage_order(time_horizon)
    if set(stage_contexts) != set(horizons):
        raise EmpiricalTemporalEngineError("executed_stage_contexts_invalid")
    tp_distance, sl_distance = plan_log_distances(
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
    )
    survival = 1.0
    cumulative_tp = cumulative_sl = 0.0
    curve: dict[str, dict[str, float]] = {}
    traces = []
    for horizon in horizons:
        target_profile = model["target_horizon_rule_profiles"][time_horizon]
        target_override = target_profile["overrides"].get(horizon)
        names = (
            target_override["feature_names"]
            if target_override is not None
            else model["feature_names"][horizon]
        )
        scaling = (
            target_override["feature_scaling"]
            if target_override is not None
            else model["feature_scaling"][horizon]
        )
        current_map = _current_feature_map(horizon, stage_contexts, names)
        current = _standardize(current_map, names, scaling)
        selected, selection_trace = _nearest_eligible(
            artifact=model,
            horizon=horizon,
            current=current,
            symbol=symbol,
            tp_distance=tp_distance,
            sl_distance=sl_distance,
            analysis_epoch=analysis_epoch,
            target_override=target_override,
        )
        probabilities, estimate_trace = _weighted_probabilities(
            selected,
            probability_temperature=float(
                model["selection"].get("probability_temperature", 1.0)
            ),
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
        traces.append(
            {
                "stage_id": STAGE_PROFILES[horizon]["stage_id"],
                "time_horizon": horizon,
                "label": STAGE_PROFILES[horizon]["label"],
                "interval": STAGE_PROFILES[horizon]["interval"],
                "survival_entering_stage": survival_before,
                "conditional_probabilities": probabilities,
                "cumulative_probabilities": curve[horizon],
                "current_feature_values": current_map,
                "active_rule_groups": model.get(
                    "active_rule_groups_by_horizon", {}
                ).get(horizon, model["active_rule_groups"]),
                "active_probability_outputs": target_stage_active_outputs(
                    model, time_horizon, horizon
                ),
                "target_horizon_rule_profile": target_profile["profile"],
                "geometry_application": {
                    "method": "exact_barrier_replay_on_historical_future_paths",
                    "tp_log_distance": tp_distance,
                    "sl_log_distance": sl_distance,
                    "coefficient_or_distance_heuristic": False,
                },
                **selection_trace,
                **estimate_trace,
            }
        )
    validate_temporal_curve(curve)
    selected_probabilities = curve[time_horizon]
    ranges = _sample_cumulative_ranges(
        traces,
        seed_material={
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "time_horizon": time_horizon,
            "analysis_at": analysis_at,
            "artifact": model["artifact_id"],
        },
    )
    result = {
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "single_engine": True,
        "parallel_probability_engines_executed": 0,
        "artifact_id": model["artifact_id"],
        "artifact_sha256": model["artifact_sha256"],
        "selected_horizon": time_horizon,
        "executed_stage_count": len(horizons),
        "executed_stages": list(horizons),
        "target_horizon_rule_profile": model[
            "target_horizon_rule_profiles"
        ][time_horizon]["profile"],
        "plan": {
            "symbol": symbol,
            "side": side,
            "entry": float(entry),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
            "tp_log_distance": tp_distance,
            "sl_log_distance": sl_distance,
        },
        "stage_traces": traces,
        "probability_curve": curve,
        "probabilities": selected_probabilities,
        "probability_ranges_95pct": ranges,
        "decision_probabilities": {
            "tp_before_sl_within_horizon": selected_probabilities[CUMULATIVE_CLASSES[0]],
            "sl_before_tp_within_horizon": selected_probabilities[CUMULATIVE_CLASSES[1]],
            "neither_before_expiry": selected_probabilities[CUMULATIVE_CLASSES[2]],
            "resolution_within_horizon": (
                selected_probabilities[CUMULATIVE_CLASSES[0]]
                + selected_probabilities[CUMULATIVE_CLASSES[1]]
            ),
            "tp_given_resolution": (
                selected_probabilities[CUMULATIVE_CLASSES[0]]
                / (
                    selected_probabilities[CUMULATIVE_CLASSES[0]]
                    + selected_probabilities[CUMULATIVE_CLASSES[1]]
                )
                if selected_probabilities[CUMULATIVE_CLASSES[0]]
                + selected_probabilities[CUMULATIVE_CLASSES[1]]
                > 0.0
                else 0.5
            ),
        },
        "historical_evidence": {
            "source": model["historical_source"],
            "coverage": model["historical_coverage"],
            "analog_records": len(model["analogs"]),
            "outcome_method": "observed_5m_high_low_first_touch",
            "arbitrary_plan_geometry_supported": True,
            "geometry_model_coefficients": False,
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
    "ARTIFACT_PATH",
    "CONDITIONAL_CLASSES",
    "CUMULATIVE_CLASSES",
    "ENGINE_VERSION",
    "EmpiricalTemporalEngineError",
    "HORIZON_SECONDS",
    "RUNTIME_VERSION",
    "SCORING_VERSION",
    "canonical_sha256",
    "empirical_probabilities",
    "load_production_artifact",
    "plan_log_distances",
    "selected_stage_order",
    "target_context_active_outputs",
    "target_stage_active_outputs",
    "target_stage_feature_names",
    "validate_artifact",
    "validate_temporal_curve",
)
