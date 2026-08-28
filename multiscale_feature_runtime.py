from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from composite_rule_runtime import evaluate_absorption
from data_quality_gate import validate_pretrade_candles
from microstructure_rule_runtime import evaluate_microstructure_rule_family
from structural_level_runtime import (
    PIVOT_HALF_WINDOW,
    _fibonacci_outputs,
    _structural_outputs,
    confirmed_pivots,
)
from technical_rule_runtime import evaluate_technical_rule_family, wilder_atr


STAGE_ORDER = ("intraday_short", "intraday_wide", "short_swing")
STAGE_PROFILES = {
    "intraday_short": {
        "stage_id": "stage_0_4h",
        "label": "0-4 h",
        "horizon_seconds": 4 * 60 * 60,
        "increment_seconds": 4 * 60 * 60,
        "interval": "5m",
        "interval_seconds": 5 * 60,
    },
    "intraday_wide": {
        "stage_id": "stage_4_24h",
        "label": "4-24 h",
        "horizon_seconds": 24 * 60 * 60,
        "increment_seconds": 20 * 60 * 60,
        "interval": "1h",
        "interval_seconds": 60 * 60,
    },
    "short_swing": {
        "stage_id": "stage_24h_7d",
        "label": "24 h-7 d",
        "horizon_seconds": 7 * 24 * 60 * 60,
        "increment_seconds": 6 * 24 * 60 * 60,
        "interval": "6h",
        "interval_seconds": 6 * 60 * 60,
    },
}

RULE_FEATURES = {
    "M4-RULE-PATH-STRUCTURE-001": ("directional_path_efficiency_h",),
    "M4-RULE-MTF-HIERARCHY-001": (
        "directional_path_efficiency_2h",
        "directional_path_efficiency_4h",
    ),
    "M4-RULE-VOLATILITY-RANK-001": ("volatility_percentile_60",),
    "M4-RULE-PRIOR-EXTREMA-001": (
        "target_extreme_between_entry_and_tp",
    ),
    "LIB-CAND-EMA-TREND-001": (
        "side_adjusted_close_vs_ema50_log",
        "side_adjusted_ema50_vs_ema200_log",
        "side_adjusted_slope_atr",
    ),
    "LIB-CAND-RSI-WILDER-001": ("side_adjusted_centered_rsi",),
    "LIB-CAND-ATR-EXTENSION-001": ("side_adjusted_extension_atr",),
    "LIB-CAND-RELATIVE-VOLUME-001": ("log_relative_horizon_volume",),
    "LIB-CAND-CVD-SLOPE-001": (
        "side_adjusted_normalized_cvd_slope",
    ),
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": (
        "target_path_level_count",
        "adverse_path_level_count",
    ),
    "LIB-CAND-FIBONACCI-DISTANCE-001": (
        "nearest_to_take_profit.absolute_distance_sigma_horizon",
        "nearest_to_stop_loss.absolute_distance_sigma_horizon",
    ),
    "LIB-CAND-COMPRESSION-001": (
        "compression_vector.atr_rank",
        "compression_vector.bollinger_width_rank",
    ),
    "LIB-CAND-ABSORPTION-001": (
        "side_adjusted_horizon_displacement_atr",
        "flow_opposing_wick_ratio",
    ),
}

CANONICAL_RULE_FEATURES = tuple(
    (rule_id, name)
    for rule_id, names in RULE_FEATURES.items()
    for name in names
)
FLAT_FEATURE_NAMES = tuple(
    f"{rule_id}::{name}" for rule_id, name in CANONICAL_RULE_FEATURES
)


def required_candle_count(time_horizon: str) -> int:
    profile = STAGE_PROFILES[time_horizon]
    returns_per_horizon = (
        int(profile["horizon_seconds"]) // int(profile["interval_seconds"])
    )
    return 61 * returns_per_horizon + 1


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _kline_fingerprint(candles: list[dict]) -> str:
    return _canonical_sha256(
        [
            [
                row["open_time_ms"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                row["close_time_ms"],
            ]
            for row in candles
        ]
    )


def _returns(closes: list[float]) -> list[float]:
    return [
        math.log(current / previous)
        for previous, current in zip(closes, closes[1:])
    ]


def _signed_efficiency(values: list[float]) -> float:
    displacement = math.fsum(values)
    variation = math.fsum(abs(value) for value in values)
    return displacement / variation if variation > 0 else 0.0


def _midrank(current: float, reference: list[float]) -> float:
    below = sum(value < current for value in reference)
    equal = sum(value == current for value in reference)
    return (below + 0.5 * equal) / len(reference)


def _closed_material(plan: dict, candles: list[dict]) -> dict:
    horizon = str(plan["time_horizon"])
    profile = STAGE_PROFILES[horizon]
    analysis_at = _parse_utc(plan["analysis_at"])
    if analysis_at is None:
        raise ValueError("analysis_timestamp_invalid")
    analysis_ms = int(analysis_at.timestamp() * 1000)
    interval_seconds = int(profile["interval_seconds"])
    return_count = int(profile["horizon_seconds"]) // interval_seconds
    required_returns = 61 * return_count
    data_quality = validate_pretrade_candles(
        candles,
        analysis_at=plan["analysis_at"],
        analysis_at_ms=analysis_ms,
        interval_seconds=interval_seconds,
        required_candle_count=required_returns + 1,
    )
    selected = data_quality.pop("selected_candles")
    closes = [float(row["close"]) for row in selected]
    returns = _returns(closes)
    current_returns = returns[-return_count:]
    current_bars = selected[-return_count:]
    reference_variances = [
        math.fsum(
            value * value
            for value in returns[index : index + return_count]
        )
        for index in range(0, 60 * return_count, return_count)
    ]
    return {
        "analysis_ms": analysis_ms,
        "interval_seconds": interval_seconds,
        "return_count": return_count,
        "selected": selected,
        "current_bars": current_bars,
        "current_returns": current_returns,
        "current_variance": math.fsum(
            value * value for value in current_returns
        ),
        "reference_variances": reference_variances,
        "signed_efficiencies": {
            "H": _signed_efficiency(returns[-return_count:]),
            "2H": _signed_efficiency(returns[-2 * return_count :]),
            "4H": _signed_efficiency(returns[-4 * return_count :]),
        },
        "data_cutoff_at_ms": int(selected[-1]["close_time_ms"]),
        "data_sha256": _kline_fingerprint(selected),
        "data_quality": data_quality,
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(item, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            result[prefix] = number
    return result


def _extract_trace_features(traces: list[dict]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for trace in traces:
        rule_id = str(trace.get("rule_id") or "")
        if rule_id not in RULE_FEATURES:
            continue
        if trace.get("status") not in {"evaluated", "evaluated_shadow"}:
            continue
        flattened = _flatten(trace.get("outputs") or {})
        selected = {
            name: flattened[name]
            for name in RULE_FEATURES[rule_id]
            if name in flattened
        }
        if len(selected) == len(RULE_FEATURES[rule_id]):
            result[rule_id] = selected
    return result


def flatten_rule_features(features: dict[str, dict[str, float]]) -> dict[str, float]:
    missing = [
        f"{rule_id}::{name}"
        for rule_id, name in CANONICAL_RULE_FEATURES
        if rule_id not in features or name not in features[rule_id]
    ]
    if missing:
        raise ValueError("multiscale_features_unavailable:" + ",".join(missing))
    return {
        f"{rule_id}::{name}": float(features[rule_id][name])
        for rule_id, name in CANONICAL_RULE_FEATURES
    }


def _compression_features(material: dict) -> dict[str, float]:
    candles = material["selected"]
    return_count = int(material["return_count"])
    endpoints = [
        len(candles) - 1 - offset * return_count
        for offset in range(60, -1, -1)
    ]
    true_ranges: list[float] = []
    previous_close = None
    for row in candles:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        true_range = high - low
        if previous_close is not None:
            true_range = max(
                true_range,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = close
    period = 14
    current = math.fsum(true_ranges[:period]) / period
    atr_by_index = {period - 1: current}
    for index in range(period, len(true_ranges)):
        current = ((period - 1) * current + true_ranges[index]) / period
        atr_by_index[index] = current
    atr_norms = []
    band_widths = []
    for endpoint in endpoints:
        close = float(candles[endpoint]["close"])
        atr_norms.append(atr_by_index[endpoint] / close)
        closes = [
            float(row["close"])
            for row in candles[endpoint - 19 : endpoint + 1]
        ]
        middle = math.fsum(closes) / 20.0
        variance = math.fsum((value - middle) ** 2 for value in closes) / 20.0
        band_widths.append(4.0 * math.sqrt(variance) / middle)

    def midrank(value: float, reference: list[float]) -> float:
        below = sum(item < value for item in reference)
        equal = sum(item == value for item in reference)
        return (below + 0.5 * equal) / len(reference)

    return {
        "compression_vector.atr_rank": midrank(atr_norms[-1], atr_norms[:-1]),
        "compression_vector.bollinger_width_rank": midrank(
            band_widths[-1], band_widths[:-1]
        ),
    }


def _base_rule_context(plan: dict, material: dict) -> tuple[dict, list[dict]]:
    side = str(plan["side"]).lower()
    direction = 1.0 if side == "long" else -1.0
    signed = material["signed_efficiencies"]
    volatility_rank = _midrank(
        float(material["current_variance"]),
        [float(value) for value in material["reference_variances"]],
    )
    features = {
        "M4-RULE-PATH-STRUCTURE-001": {
            "directional_path_efficiency_h": direction * float(signed["H"])
        },
        "M4-RULE-MTF-HIERARCHY-001": {
            "directional_path_efficiency_2h": direction * float(signed["2H"]),
            "directional_path_efficiency_4h": direction * float(signed["4H"]),
        },
        "M4-RULE-VOLATILITY-RANK-001": {
            "volatility_percentile_60": volatility_rank
        },
    }
    traces = [
        {
            "rule_id": "M4-RULE-PATH-STRUCTURE-001",
            "status": "evaluated",
            "outputs": features["M4-RULE-PATH-STRUCTURE-001"],
        },
        {
            "rule_id": "M4-RULE-MTF-HIERARCHY-001",
            "status": "evaluated",
            "outputs": features["M4-RULE-MTF-HIERARCHY-001"],
        },
        {
            "rule_id": "M4-RULE-VOLATILITY-RANK-001",
            "status": "evaluated",
            "outputs": features["M4-RULE-VOLATILITY-RANK-001"],
        },
    ]
    buy_taker = math.fsum(
        float(row["taker_buy_quote_volume"])
        for row in material["current_bars"]
    )
    total_activity = math.fsum(
        float(row["quote_volume"]) for row in material["current_bars"]
    )
    if total_activity <= 0 or buy_taker < 0 or buy_taker > total_activity:
        raise ValueError("multiscale_aggressor_activity_invalid")
    sell_taker = total_activity - buy_taker
    aggressor_outputs = {
        "buy_taker_volume": buy_taker,
        "sell_taker_volume": sell_taker,
        "total_activity": total_activity,
        "ATI_H": (buy_taker - sell_taker) / total_activity,
        "activity_unit": "quote_asset_volume_from_closed_klines",
        "coverage_complete": True,
    }
    traces.append(
        {
            "rule_id": "M4-RULE-AGGRESSOR-IMBALANCE-001",
            "status": "evaluated",
            "outputs": aggressor_outputs,
            "source_data_sha256": material["data_sha256"],
        }
    )
    technical = evaluate_technical_rule_family(
        material["selected"],
        side=side,
        analysis_at=plan["analysis_at"],
        interval_seconds=material["interval_seconds"],
        source_data_sha256=material["data_sha256"],
    )
    microstructure = evaluate_microstructure_rule_family(
        selected_candles=material["selected"],
        current_bars=material["current_bars"],
        live_context=None,
        return_count=material["return_count"],
        interval_seconds=material["interval_seconds"],
        side=side,
        analysis_at=plan["analysis_at"],
        source_data_sha256=material["data_sha256"],
    )
    traces.extend(technical.get("traces", []))
    traces.extend(microstructure.get("traces", []))
    features.update(
        _extract_trace_features(
            technical.get("traces", []) + microstructure.get("traces", [])
        )
    )
    features["LIB-CAND-COMPRESSION-001"] = _compression_features(material)
    trace_by_id = {
        str(trace.get("rule_id")): trace
        for trace in traces
        if trace.get("rule_id")
    }
    absorption = evaluate_absorption(
        material["selected"],
        material["current_bars"],
        trace_by_id,
        side=side,
        analysis_at=plan["analysis_at"],
    )
    traces.append(absorption)
    features.update(_extract_trace_features([absorption]))
    if (
        absorption.get("status") in {"evaluated", "evaluated_shadow"}
        and absorption.get("outputs", {}).get("flow_opposing_wick_ratio")
        is None
    ):
        # ATI=0 has no opposing flow direction. The audited feature is then
        # exactly neutral, not missing evidence and not a reason to block the
        # complete pre-trade analysis.
        features["LIB-CAND-ABSORPTION-001"] = {
            "side_adjusted_horizon_displacement_atr": float(
                absorption["outputs"][
                    "side_adjusted_horizon_displacement_atr"
                ]
            ),
            "flow_opposing_wick_ratio": 0.0,
        }
        absorption["model_input_projection"] = {
            "flow_opposing_wick_ratio": 0.0,
            "reason": "neutral_aggressor_flow_has_no_opposing_direction",
        }
    return features, traces


def _structural_features(plan: dict, material: dict) -> dict[str, dict[str, float]]:
    lookback = max(
        34,
        4 * int(material["return_count"]) + 2 * PIVOT_HALF_WINDOW + 1,
    )
    context = material["selected"][-lookback:]
    atr14 = wilder_atr(context, 14)
    pivots = confirmed_pivots(context, atr14=atr14)
    if not pivots:
        raise ValueError("multiscale_structural_pivots_unavailable")
    sigma = math.sqrt(float(material["current_variance"]))
    structural = _structural_outputs(
        pivots,
        entry=float(plan["entry"]),
        take_profit=float(plan["take_profit"]),
        stop_loss=float(plan["stop_loss"]),
        side=plan["side"],
        sigma_horizon=sigma,
    )
    fibonacci = _fibonacci_outputs(
        pivots,
        entry=float(plan["entry"]),
        take_profit=float(plan["take_profit"]),
        stop_loss=float(plan["stop_loss"]),
        sigma_horizon=sigma,
        atr14=float(atr14),
    )
    if fibonacci is None:
        raise ValueError("multiscale_fibonacci_unavailable")
    return {
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": {
            "target_path_level_count": float(
                structural["target_path_level_count"]
            ),
            "adverse_path_level_count": float(
                structural["adverse_path_level_count"]
            ),
        },
        "LIB-CAND-FIBONACCI-DISTANCE-001": {
            "nearest_to_take_profit.absolute_distance_sigma_horizon": float(
                fibonacci["nearest_to_take_profit"][
                    "absolute_distance_sigma_horizon"
                ]
            ),
            "nearest_to_stop_loss.absolute_distance_sigma_horizon": float(
                fibonacci["nearest_to_stop_loss"][
                    "absolute_distance_sigma_horizon"
                ]
            ),
        },
    }


def build_stage_context(plan: dict, candles: list[dict]) -> dict:
    time_horizon = str(plan["time_horizon"])
    if time_horizon not in STAGE_PROFILES:
        raise ValueError("unsupported_multiscale_horizon")
    profile = STAGE_PROFILES[time_horizon]
    if int(plan["horizon_seconds"]) != int(profile["horizon_seconds"]):
        raise ValueError("multiscale_horizon_seconds_mismatch")
    material = _closed_material(plan, candles)
    if int(material["interval_seconds"]) != int(profile["interval_seconds"]):
        raise ValueError("multiscale_interval_mismatch")
    features, traces = _base_rule_context(plan, material)
    direction = 1.0 if str(plan["side"]).lower() == "long" else -1.0
    target_extreme = (
        max(float(row["high"]) for row in material["current_bars"])
        if direction > 0
        else min(float(row["low"]) for row in material["current_bars"])
    )
    target_between = (
        float(plan["entry"]) < target_extreme < float(plan["take_profit"])
        if direction > 0
        else float(plan["take_profit"]) < target_extreme < float(plan["entry"])
    )
    features["M4-RULE-PRIOR-EXTREMA-001"] = {
        "target_extreme_between_entry_and_tp": 1.0 if target_between else 0.0
    }
    features.update(_structural_features(plan, material))
    # Keep a complete per-stage trace for every deterministic feature that is
    # stored in the v0.9 snapshot.  The empirical model remains frozen: only
    # the four audited analog-distance inputs below affect probabilities; the
    # rest are explicitly observational and can be evaluated after closure.
    active_analog_rules = {
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-MTF-HIERARCHY-001",
        "M4-RULE-VOLATILITY-RANK-001",
        "LIB-CAND-COMPRESSION-001",
    }
    trace_by_id = {
        str(trace.get("rule_id")): trace
        for trace in traces
        if isinstance(trace, dict) and trace.get("rule_id")
    }
    for rule_id, outputs in features.items():
        trace = trace_by_id.get(rule_id)
        if trace is None:
            trace = {
                "rule_id": rule_id,
                "status": (
                    "evaluated"
                    if rule_id in active_analog_rules
                    else "evaluated_shadow"
                ),
                "outputs": outputs,
                "source_data_sha256": material["data_sha256"],
            }
            traces.append(trace)
            trace_by_id[rule_id] = trace
        trace["probability_effect"] = (
            "analog_distance_input"
            if rule_id in active_analog_rules
            else "none_observation_only"
        )
    flat = flatten_rule_features(features)
    sigma = math.sqrt(float(material["current_variance"]))
    return {
        "stage_id": profile["stage_id"],
        "time_horizon": time_horizon,
        "label": profile["label"],
        "horizon_seconds": int(profile["horizon_seconds"]),
        "increment_seconds": int(profile["increment_seconds"]),
        "interval": profile["interval"],
        "interval_seconds": int(profile["interval_seconds"]),
        "required_candle_count": required_candle_count(time_horizon),
        "context_sigma": sigma,
        "feature_values": flat,
        "data_cutoff_at_ms": int(material["data_cutoff_at_ms"]),
        "source_data_sha256": material["data_sha256"],
        "data_quality": material["data_quality"],
        "rule_traces": traces,
    }


__all__ = (
    "CANONICAL_RULE_FEATURES",
    "FLAT_FEATURE_NAMES",
    "STAGE_ORDER",
    "STAGE_PROFILES",
    "build_stage_context",
    "flatten_rule_features",
    "required_candle_count",
)
