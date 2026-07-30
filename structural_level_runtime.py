from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

from technical_rule_runtime import wilder_atr


RUNTIME_VERSION = "structural-level-runtime-v0.1"
RULE_IDS = (
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
    "LIB-CAND-FIBONACCI-DISTANCE-001",
)
PIVOT_HALF_WINDOW = 3
FIB_RETRACEMENTS = (0.236, 0.382, 0.5, 0.618, 0.786)
FIB_EXTENSIONS = (1.0, 1.272, 1.618)


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite_positive(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name}_must_be_finite_and_positive")
    return number


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def _trace(
    *,
    rule_id: str,
    role: str,
    parent_rule_ids: list[str],
    formula_ids: list[str],
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    source_data_sha256: str,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": "FAMILY-STRUCTURAL-LEVELS",
        "role": role,
        "parent_rule_ids": parent_rule_ids,
        "status": status,
        "reason_codes": reason_codes,
        "formula_ids": formula_ids,
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": source_data_sha256,
        "executed_at": executed_at,
        "probability_effect": "none_shadow_observation",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def confirmed_pivots(
    candles: list[dict],
    *,
    atr14: float,
    half_window: int = PIVOT_HALF_WINDOW,
) -> list[dict]:
    if half_window < 1:
        raise ValueError("pivot_half_window_must_be_positive")
    if len(candles) < 2 * half_window + 1:
        return []
    highs = [
        _finite_positive(row["high"], f"high_{index}")
        for index, row in enumerate(candles)
    ]
    lows = [
        _finite_positive(row["low"], f"low_{index}")
        for index, row in enumerate(candles)
    ]
    pivots = []
    for index in range(half_window, len(candles) - half_window):
        high = highs[index]
        low = lows[index]
        high_window = highs[
            index - half_window : index + half_window + 1
        ]
        low_window = lows[
            index - half_window : index + half_window + 1
        ]
        if high == max(high_window) and high_window.count(high) == 1:
            local_base = max(
                min(lows[index - half_window : index]),
                min(lows[index + 1 : index + half_window + 1]),
            )
            pivots.append(
                {
                    "index": index,
                    "type": "high",
                    "price": high,
                    "prominence_atr": (high - local_base) / atr14,
                    "confirmed_at_index": index + half_window,
                    "pivot_close_time_ms": int(
                        candles[index]["close_time_ms"]
                    ),
                    "confirmed_close_time_ms": int(
                        candles[index + half_window]["close_time_ms"]
                    ),
                }
            )
        if low == min(low_window) and low_window.count(low) == 1:
            local_cap = min(
                max(highs[index - half_window : index]),
                max(highs[index + 1 : index + half_window + 1]),
            )
            pivots.append(
                {
                    "index": index,
                    "type": "low",
                    "price": low,
                    "prominence_atr": (local_cap - low) / atr14,
                    "confirmed_at_index": index + half_window,
                    "pivot_close_time_ms": int(
                        candles[index]["close_time_ms"]
                    ),
                    "confirmed_close_time_ms": int(
                        candles[index + half_window]["close_time_ms"]
                    ),
                }
            )
    by_index = {}
    for pivot in pivots:
        existing = by_index.get(pivot["index"])
        if (
            existing is None
            or pivot["prominence_atr"] > existing["prominence_atr"]
        ):
            by_index[pivot["index"]] = pivot
    return [by_index[index] for index in sorted(by_index)]


def alternating_pivots(pivots: list[dict]) -> list[dict]:
    result = []
    for pivot in sorted(pivots, key=lambda item: item["index"]):
        if not result or result[-1]["type"] != pivot["type"]:
            result.append(pivot)
            continue
        previous = result[-1]
        more_extreme = (
            pivot["price"] > previous["price"]
            if pivot["type"] == "high"
            else pivot["price"] < previous["price"]
        )
        if more_extreme:
            result[-1] = pivot
    return result


def _level_payload(
    pivot: dict,
    *,
    entry: float,
    sigma_horizon: float,
    side_sign: float,
) -> dict:
    log_distance = math.log(pivot["price"] / entry)
    return {
        **pivot,
        "log_distance_from_entry": log_distance,
        "distance_sigma_horizon": log_distance / sigma_horizon,
        "side_adjusted_distance_sigma_horizon": (
            side_sign * log_distance / sigma_horizon
        ),
    }


def _between(value: float, left: float, right: float) -> bool:
    return min(left, right) < value < max(left, right)


def _nearest(values: list[dict]) -> dict | None:
    if not values:
        return None
    return min(
        values,
        key=lambda item: abs(item["log_distance_from_entry"]),
    )


def _structural_outputs(
    pivots: list[dict],
    *,
    entry: float,
    take_profit: float,
    stop_loss: float,
    side: str,
    sigma_horizon: float,
) -> dict:
    direction = _side_sign(side)
    levels = [
        _level_payload(
            pivot,
            entry=entry,
            sigma_horizon=sigma_horizon,
            side_sign=direction,
        )
        for pivot in pivots
    ]
    supports = [
        level
        for level in levels
        if level["type"] == "low" and level["price"] < entry
    ]
    resistances = [
        level
        for level in levels
        if level["type"] == "high" and level["price"] > entry
    ]
    target_type = "high" if direction > 0 else "low"
    adverse_type = "low" if direction > 0 else "high"
    target_path = [
        level
        for level in levels
        if level["type"] == target_type
        and _between(level["price"], entry, take_profit)
    ]
    adverse_path = [
        level
        for level in levels
        if level["type"] == adverse_type
        and _between(level["price"], entry, stop_loss)
    ]

    def ordered(items: list[dict]) -> list[dict]:
        return sorted(
            items,
            key=lambda item: abs(item["log_distance_from_entry"]),
        )[:12]

    return {
        "confirmed_pivot_count": len(pivots),
        "support_count": len(supports),
        "resistance_count": len(resistances),
        "nearest_support": _nearest(supports),
        "nearest_resistance": _nearest(resistances),
        "target_path_level_count": len(target_path),
        "adverse_path_level_count": len(adverse_path),
        "target_path_levels": ordered(target_path),
        "adverse_path_levels": ordered(adverse_path),
        "strongest_target_path_prominence_atr": (
            max(level["prominence_atr"] for level in target_path)
            if target_path
            else None
        ),
        "strongest_adverse_path_prominence_atr": (
            max(level["prominence_atr"] for level in adverse_path)
            if adverse_path
            else None
        ),
    }


def _fib_key(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _fibonacci_levels(start: dict, end: dict) -> dict:
    start_price = float(start["price"])
    end_price = float(end["price"])
    move = abs(end_price - start_price)
    direction = 1.0 if end_price > start_price else -1.0
    retracements = {
        _fib_key(ratio): start_price + direction * (1.0 - ratio) * move
        for ratio in FIB_RETRACEMENTS
    }
    extensions = {
        _fib_key(ratio): start_price + direction * ratio * move
        for ratio in FIB_EXTENSIONS
    }
    return {
        "direction": "up" if direction > 0 else "down",
        "start": start,
        "end": end,
        "move_price": move,
        "retracements": retracements,
        "extensions": extensions,
    }


def _nearest_fibonacci_level(
    price: float,
    levels: dict,
    *,
    sigma_horizon: float,
) -> dict:
    candidates = [
        {
            "set": set_name,
            "ratio": ratio,
            "price": level_price,
            "signed_log_distance": math.log(level_price / price),
        }
        for set_name in ("retracements", "extensions")
        for ratio, level_price in levels[set_name].items()
    ]
    nearest = min(
        candidates,
        key=lambda item: abs(item["signed_log_distance"]),
    )
    return {
        **nearest,
        "absolute_distance_sigma_horizon": (
            abs(nearest["signed_log_distance"]) / sigma_horizon
        ),
    }


def _retracement_fraction(price: float, levels: dict) -> float:
    start = float(levels["start"]["price"])
    end = float(levels["end"]["price"])
    move = abs(end - start)
    if levels["direction"] == "up":
        return (end - price) / move
    return (price - end) / move


def _fibonacci_outputs(
    pivots: list[dict],
    *,
    entry: float,
    take_profit: float,
    stop_loss: float,
    sigma_horizon: float,
    atr14: float,
) -> dict | None:
    alternating = alternating_pivots(pivots)
    if len(alternating) < 2:
        return None
    start, end = alternating[-2:]
    if start["type"] == end["type"] or start["index"] >= end["index"]:
        return None
    levels = _fibonacci_levels(start, end)
    move_atr = levels["move_price"] / atr14
    confluences = []
    for set_name in ("retracements", "extensions"):
        for ratio, fib_price in levels[set_name].items():
            nearest_pivot = min(
                pivots,
                key=lambda pivot: abs(
                    math.log(float(pivot["price"]) / fib_price)
                ),
            )
            separation = abs(
                math.log(float(nearest_pivot["price"]) / fib_price)
            ) / sigma_horizon
            confluences.append(
                {
                    "set": set_name,
                    "ratio": ratio,
                    "fibonacci_price": fib_price,
                    "pivot_type": nearest_pivot["type"],
                    "pivot_price": nearest_pivot["price"],
                    "pivot_prominence_atr": nearest_pivot[
                        "prominence_atr"
                    ],
                    "separation_sigma_horizon": separation,
                }
            )
    confluences.sort(
        key=lambda item: item["separation_sigma_horizon"]
    )
    return {
        **levels,
        "move_atr14": move_atr,
        "entry_retracement_fraction": _retracement_fraction(
            entry,
            levels,
        ),
        "take_profit_retracement_fraction": _retracement_fraction(
            take_profit,
            levels,
        ),
        "stop_loss_retracement_fraction": _retracement_fraction(
            stop_loss,
            levels,
        ),
        "nearest_to_entry": _nearest_fibonacci_level(
            entry,
            levels,
            sigma_horizon=sigma_horizon,
        ),
        "nearest_to_take_profit": _nearest_fibonacci_level(
            take_profit,
            levels,
            sigma_horizon=sigma_horizon,
        ),
        "nearest_to_stop_loss": _nearest_fibonacci_level(
            stop_loss,
            levels,
            sigma_horizon=sigma_horizon,
        ),
        "nearest_structural_confluences": confluences[:8],
        "minimum_confluence_distance_sigma_horizon": (
            confluences[0]["separation_sigma_horizon"]
        ),
    }


def evaluate_structural_level_family(
    candles: list[dict],
    *,
    return_count: int,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    sigma_horizon: float,
    interval_seconds: int,
    analysis_at: str,
    source_data_sha256: str,
) -> dict:
    analysis_ms = int(
        datetime.fromisoformat(
            analysis_at.replace("Z", "+00:00")
        ).timestamp()
        * 1000
    )
    closed = [
        row
        for row in candles
        if int(row["close_time_ms"]) <= analysis_ms
    ]
    lookback = max(
        34,
        4 * int(return_count) + 2 * PIVOT_HALF_WINDOW + 1,
    )
    context = closed[-lookback:]
    try:
        validated_sigma = _finite_positive(
            sigma_horizon,
            "sigma_horizon",
        )
    except (TypeError, ValueError):
        validated_sigma = None
    common_inputs = {
        "side": str(side).lower(),
        "entry": _finite_positive(entry, "entry"),
        "take_profit": _finite_positive(take_profit, "take_profit"),
        "stop_loss": _finite_positive(stop_loss, "stop_loss"),
        "sigma_horizon": validated_sigma,
        "interval_seconds": int(interval_seconds),
        "return_count_per_horizon": int(return_count),
        "context_horizons": 4,
        "pivot_half_window": PIVOT_HALF_WINDOW,
        "required_closed_candles": lookback,
        "observed_closed_candles": len(context),
        "retracement_ratios": list(FIB_RETRACEMENTS),
        "extension_ratios": list(FIB_EXTENSIONS),
    }
    structural_formula_ids = [
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001-FORMULA-01",
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001-FORMULA-02",
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001-FORMULA-03",
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001-FORMULA-04",
    ]
    fibonacci_formula_ids = [
        "LIB-CAND-FIBONACCI-DISTANCE-001-FORMULA-01",
        "LIB-CAND-FIBONACCI-DISTANCE-001-FORMULA-02",
        "LIB-CAND-FIBONACCI-DISTANCE-001-FORMULA-03",
        "LIB-CAND-FIBONACCI-DISTANCE-001-FORMULA-04",
        "LIB-CAND-FIBONACCI-DISTANCE-001-FORMULA-05",
    ]
    if len(context) < lookback or validated_sigma is None:
        block_reason = (
            "insufficient_four_horizon_context"
            if len(context) < lookback
            else "non_positive_horizon_volatility"
        )
        traces = [
            _trace(
                rule_id=RULE_IDS[0],
                role="contextual",
                parent_rule_ids=[],
                formula_ids=structural_formula_ids,
                inputs=common_inputs,
                outputs={},
                status="blocked",
                reason_codes=[block_reason],
                source_data_sha256=source_data_sha256,
                executed_at=analysis_at,
            ),
            _trace(
                rule_id=RULE_IDS[1],
                role="contextual",
                parent_rule_ids=[RULE_IDS[0]],
                formula_ids=fibonacci_formula_ids,
                inputs=common_inputs,
                outputs={},
                status="blocked",
                reason_codes=[block_reason],
                source_data_sha256=source_data_sha256,
                executed_at=analysis_at,
            ),
        ]
    else:
        atr14 = wilder_atr(context, 14)
        pivots = confirmed_pivots(context, atr14=atr14)
        structural_outputs = _structural_outputs(
            pivots,
            entry=float(entry),
            take_profit=float(take_profit),
            stop_loss=float(stop_loss),
            side=side,
            sigma_horizon=validated_sigma,
        )
        structural_status = (
            "evaluated_shadow" if pivots else "blocked"
        )
        structural_reasons = [] if pivots else [
            "no_confirmed_pivots_in_four_horizon_context"
        ]
        fib_outputs = (
            _fibonacci_outputs(
                pivots,
                entry=float(entry),
                take_profit=float(take_profit),
                stop_loss=float(stop_loss),
                sigma_horizon=validated_sigma,
                atr14=atr14,
            )
            if pivots
            else None
        )
        traces = [
            _trace(
                rule_id=RULE_IDS[0],
                role="contextual",
                parent_rule_ids=[],
                formula_ids=structural_formula_ids,
                inputs={**common_inputs, "atr14": atr14},
                outputs=structural_outputs if pivots else {},
                status=structural_status,
                reason_codes=structural_reasons,
                source_data_sha256=source_data_sha256,
                executed_at=analysis_at,
            ),
            _trace(
                rule_id=RULE_IDS[1],
                role="contextual",
                parent_rule_ids=[RULE_IDS[0]],
                formula_ids=fibonacci_formula_ids,
                inputs={**common_inputs, "atr14": atr14},
                outputs=fib_outputs or {},
                status=(
                    "evaluated_shadow"
                    if fib_outputs is not None
                    else "blocked"
                ),
                reason_codes=(
                    []
                    if fib_outputs is not None
                    else ["no_completed_opposing_pivot_swing"]
                ),
                source_data_sha256=source_data_sha256,
                executed_at=analysis_at,
            ),
        ]
    evaluated = sum(
        trace["status"] == "evaluated_shadow" for trace in traces
    )
    result = {
        "runtime_version": RUNTIME_VERSION,
        "status": (
            "evaluated_shadow"
            if evaluated == len(traces)
            else "partially_evaluated_shadow"
            if evaluated
            else "blocked"
        ),
        "analysis_at": analysis_at,
        "rule_ids": list(RULE_IDS),
        "evaluated_rule_count": evaluated,
        "traces": traces,
    }
    result["runtime_trace_sha256"] = canonical_sha256(result)
    return result
