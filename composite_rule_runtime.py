from __future__ import annotations

import hashlib
import json
import math
from statistics import median

from microstructure_rule_runtime import empirical_midrank
from technical_rule_runtime import wilder_atr


RUNTIME_VERSION = "composite-rule-runtime-v0.1"
RULE_IDS = (
    "LIB-CAND-COMPRESSION-001",
    "LIB-CAND-ABSORPTION-001",
    "LIB-CAND-PULLBACK-CONTEXT-001",
)


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


def _finite(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name}_must_be_finite")
    return number


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def _trace_map(*analyses: object) -> dict[str, dict]:
    result = {}
    for analysis in analyses:
        if isinstance(analysis, dict):
            traces = analysis.get("traces", [])
        elif isinstance(analysis, list):
            traces = analysis
        else:
            traces = []
        for trace in traces:
            if isinstance(trace, dict) and trace.get("rule_id"):
                result[str(trace["rule_id"])] = trace
    return result


def _available_parent(
    traces: dict[str, dict],
    rule_id: str,
) -> dict | None:
    trace = traces.get(rule_id)
    if not trace or trace.get("status") not in {
        "evaluated",
        "evaluated_shadow",
    }:
        return None
    outputs = trace.get("outputs")
    return trace if isinstance(outputs, dict) else None


def _trace(
    *,
    rule_id: str,
    family_id: str,
    parent_rule_ids: list[str],
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    source_payload: object,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": family_id,
        "role": "interaction",
        "parent_rule_ids": parent_rule_ids,
        "status": status,
        "reason_codes": reason_codes,
        "formula_ids": [
            f"{rule_id}-FORMULA-01",
            f"{rule_id}-FORMULA-02",
            f"{rule_id}-FORMULA-03",
        ],
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": canonical_sha256(source_payload),
        "executed_at": executed_at,
        "probability_effect": "none_shadow_observation",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def _blocked_parent_trace(
    *,
    rule_id: str,
    family_id: str,
    parent_rule_ids: list[str],
    traces: dict[str, dict],
    executed_at: str,
) -> dict | None:
    missing = [
        parent
        for parent in parent_rule_ids
        if _available_parent(traces, parent) is None
    ]
    if not missing:
        return None
    return _trace(
        rule_id=rule_id,
        family_id=family_id,
        parent_rule_ids=parent_rule_ids,
        inputs={"missing_or_blocked_parent_rule_ids": missing},
        outputs={},
        status="blocked",
        reason_codes=["parent_rule_unavailable"],
        source_payload={
            parent: traces.get(parent) for parent in parent_rule_ids
        },
        executed_at=executed_at,
    )


def _bollinger_width(rows: list[dict], end_index: int) -> float:
    closes = [
        _finite_positive(row["close"], "close")
        for row in rows[end_index - 19 : end_index + 1]
    ]
    middle = math.fsum(closes) / 20.0
    variance = math.fsum(
        (value - middle) ** 2 for value in closes
    ) / 20.0
    return 4.0 * math.sqrt(variance) / middle


def evaluate_compression(
    candles: list[dict],
    traces: dict[str, dict],
    *,
    return_count: int,
    analysis_at: str,
) -> dict:
    parents = [
        "M4-RULE-VOLATILITY-RANK-001",
        "LIB-CAND-RELATIVE-VOLUME-001",
    ]
    blocked = _blocked_parent_trace(
        rule_id=RULE_IDS[0],
        family_id="FAMILY-VOLATILITY-X-VOLUME",
        parent_rule_ids=parents,
        traces=traces,
        executed_at=analysis_at,
    )
    if blocked:
        return blocked
    endpoints = [
        len(candles) - 1 - offset * int(return_count)
        for offset in range(60, -1, -1)
    ]
    inputs = {
        "return_count_per_horizon": int(return_count),
        "reference_count": 60,
        "bollinger_period": 20,
        "bollinger_population_sigma_multiplier": 2.0,
        "parent_trace_sha256": {
            parent: traces[parent].get("trace_sha256")
            for parent in parents
        },
    }
    if not endpoints or endpoints[0] < 19:
        return _trace(
            rule_id=RULE_IDS[0],
            family_id="FAMILY-VOLATILITY-X-VOLUME",
            parent_rule_ids=parents,
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["insufficient_61_horizon_endpoints"],
            source_payload={},
            executed_at=analysis_at,
        )
    try:
        atr_norms = []
        band_widths = []
        for endpoint in endpoints:
            prefix = candles[: endpoint + 1]
            atr14 = wilder_atr(prefix, 14)
            close = _finite_positive(
                candles[endpoint]["close"],
                "endpoint_close",
            )
            atr_norms.append(atr14 / close)
            band_widths.append(_bollinger_width(candles, endpoint))
        relative_outputs = traces[
            "LIB-CAND-RELATIVE-VOLUME-001"
        ]["outputs"]
        relative_volume = _finite(
            relative_outputs["relative_horizon_volume"],
            "relative_horizon_volume",
        )
        volume_midrank = _finite(
            relative_outputs["volume_midrank_60"],
            "volume_midrank_60",
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return _trace(
            rule_id=RULE_IDS[0],
            family_id="FAMILY-VOLATILITY-X-VOLUME",
            parent_rule_ids=parents,
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "compression_input_invalid"],
            source_payload={},
            executed_at=analysis_at,
        )
    outputs = {
        "atr14_fraction_price": atr_norms[-1],
        "atr14_fraction_midrank_60": empirical_midrank(
            atr_norms[-1],
            atr_norms[:-1],
        ),
        "bollinger_width_20_2sigma": band_widths[-1],
        "bollinger_width_midrank_60": empirical_midrank(
            band_widths[-1],
            band_widths[:-1],
        ),
        "relative_horizon_volume": relative_volume,
        "volume_midrank_60": volume_midrank,
        "compression_vector": {
            "atr_rank": empirical_midrank(
                atr_norms[-1],
                atr_norms[:-1],
            ),
            "bollinger_width_rank": empirical_midrank(
                band_widths[-1],
                band_widths[:-1],
            ),
            "relative_volume": relative_volume,
            "volume_rank": volume_midrank,
        },
    }
    return _trace(
        rule_id=RULE_IDS[0],
        family_id="FAMILY-VOLATILITY-X-VOLUME",
        parent_rule_ids=parents,
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload={
            "atr_norms": atr_norms,
            "band_widths": band_widths,
            "relative_volume_parent": traces[
                "LIB-CAND-RELATIVE-VOLUME-001"
            ],
        },
        executed_at=analysis_at,
    )


def evaluate_absorption(
    selected_candles: list[dict],
    current_bars: list[dict],
    traces: dict[str, dict],
    *,
    side: str,
    analysis_at: str,
) -> dict:
    parents = [
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
        "LIB-CAND-RELATIVE-VOLUME-001",
    ]
    blocked = _blocked_parent_trace(
        rule_id=RULE_IDS[1],
        family_id="FAMILY-EXECUTED-FLOW-X-PRICE",
        parent_rule_ids=parents,
        traces=traces,
        executed_at=analysis_at,
    )
    if blocked:
        return blocked
    inputs = {
        "horizon_bar_count": len(current_bars),
        "side": str(side).lower(),
        "parent_trace_sha256": {
            parent: traces[parent].get("trace_sha256")
            for parent in parents
        },
    }
    try:
        if not current_bars:
            raise ValueError("current_horizon_bars_required")
        open_price = _finite_positive(current_bars[0]["open"], "open")
        close_price = _finite_positive(
            current_bars[-1]["close"],
            "close",
        )
        high = max(
            _finite_positive(row["high"], "high")
            for row in current_bars
        )
        low = min(
            _finite_positive(row["low"], "low")
            for row in current_bars
        )
        if high <= low:
            raise ValueError("zero_horizon_price_range")
        upper_wick = max(high - max(open_price, close_price), 0.0)
        lower_wick = max(min(open_price, close_price) - low, 0.0)
        ati = _finite(
            traces["M4-RULE-AGGRESSOR-IMBALANCE-001"][
                "outputs"
            ]["ATI_H"],
            "ATI_H",
        )
        relative_volume = _finite(
            traces["LIB-CAND-RELATIVE-VOLUME-001"]["outputs"][
                "relative_horizon_volume"
            ],
            "relative_horizon_volume",
        )
        atr14 = wilder_atr(selected_candles, 14)
        atr_fraction = atr14 / close_price
        displacement = math.log(close_price / open_price) / atr_fraction
        opposing_wick = (
            upper_wick if ati > 0
            else lower_wick if ati < 0
            else None
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return _trace(
            rule_id=RULE_IDS[1],
            family_id="FAMILY-EXECUTED-FLOW-X-PRICE",
            parent_rule_ids=parents,
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "absorption_input_invalid"],
            source_payload={},
            executed_at=analysis_at,
        )
    price_range = high - low
    direction = _side_sign(side)
    outputs = {
        "ATI_H": ati,
        "side_adjusted_ATI_H": direction * ati,
        "relative_horizon_volume": relative_volume,
        "horizon_log_return": math.log(close_price / open_price),
        "horizon_displacement_atr": displacement,
        "side_adjusted_horizon_displacement_atr": (
            direction * displacement
        ),
        "upper_wick_ratio": upper_wick / price_range,
        "lower_wick_ratio": lower_wick / price_range,
        "flow_opposing_wick_ratio": (
            opposing_wick / price_range
            if opposing_wick is not None
            else None
        ),
        "absorption_vector": {
            "aggressor_imbalance": ati,
            "relative_volume": relative_volume,
            "displacement_atr": displacement,
            "flow_opposing_wick_ratio": (
                opposing_wick / price_range
                if opposing_wick is not None
                else None
            ),
        },
    }
    return _trace(
        rule_id=RULE_IDS[1],
        family_id="FAMILY-EXECUTED-FLOW-X-PRICE",
        parent_rule_ids=parents,
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload={
            "current_bars": current_bars,
            "parent_traces": {
                parent: traces[parent] for parent in parents
            },
        },
        executed_at=analysis_at,
    )


def evaluate_pullback(
    traces: dict[str, dict],
    *,
    side: str,
    analysis_at: str,
) -> dict:
    parents = [
        "LIB-CAND-EMA-TREND-001",
        "LIB-CAND-ATR-EXTENSION-001",
        "LIB-CAND-RELATIVE-VOLUME-001",
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
    ]
    blocked = _blocked_parent_trace(
        rule_id=RULE_IDS[2],
        family_id="FAMILY-TREND-X-STRUCTURE-X-FLOW",
        parent_rule_ids=parents,
        traces=traces,
        executed_at=analysis_at,
    )
    if blocked:
        return blocked
    inputs = {
        "side": str(side).lower(),
        "parent_trace_sha256": {
            parent: traces[parent].get("trace_sha256")
            for parent in parents
        },
    }
    try:
        ema = traces["LIB-CAND-EMA-TREND-001"]["outputs"]
        extension = traces["LIB-CAND-ATR-EXTENSION-001"]["outputs"]
        volume = traces["LIB-CAND-RELATIVE-VOLUME-001"]["outputs"]
        flow = traces["M4-RULE-AGGRESSOR-IMBALANCE-001"]["outputs"]
        structural = traces[
            "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
        ]["outputs"]
        outputs = {
            "side_adjusted_ema50_vs_ema200_log": _finite(
                ema["side_adjusted_ema50_vs_ema200_log"],
                "side_adjusted_ema50_vs_ema200_log",
            ),
            "side_adjusted_ema50_slope_6bars_atr": _finite(
                ema["side_adjusted_slope_atr"],
                "side_adjusted_slope_atr",
            ),
            "side_adjusted_extension_atr": _finite(
                extension["side_adjusted_extension_atr"],
                "side_adjusted_extension_atr",
            ),
            "relative_horizon_volume": _finite(
                volume["relative_horizon_volume"],
                "relative_horizon_volume",
            ),
            "volume_midrank_60": _finite(
                volume["volume_midrank_60"],
                "volume_midrank_60",
            ),
            "side_adjusted_ATI_H": (
                _side_sign(side) * _finite(flow["ATI_H"], "ATI_H")
            ),
            "nearest_support": structural.get("nearest_support"),
            "nearest_resistance": structural.get("nearest_resistance"),
            "target_path_level_count": int(
                structural["target_path_level_count"]
            ),
            "adverse_path_level_count": int(
                structural["adverse_path_level_count"]
            ),
        }
        outputs["pullback_context_vector"] = {
            key: outputs[key]
            for key in (
                "side_adjusted_ema50_vs_ema200_log",
                "side_adjusted_ema50_slope_6bars_atr",
                "side_adjusted_extension_atr",
                "relative_horizon_volume",
                "volume_midrank_60",
                "side_adjusted_ATI_H",
                "target_path_level_count",
                "adverse_path_level_count",
            )
        }
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return _trace(
            rule_id=RULE_IDS[2],
            family_id="FAMILY-TREND-X-STRUCTURE-X-FLOW",
            parent_rule_ids=parents,
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "pullback_input_invalid"],
            source_payload={},
            executed_at=analysis_at,
        )
    return _trace(
        rule_id=RULE_IDS[2],
        family_id="FAMILY-TREND-X-STRUCTURE-X-FLOW",
        parent_rule_ids=parents,
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload={
            parent: traces[parent] for parent in parents
        },
        executed_at=analysis_at,
    )


def evaluate_composite_rule_family(
    *,
    selected_candles: list[dict],
    current_bars: list[dict],
    return_count: int,
    side: str,
    analysis_at: str,
    m5_analysis: dict,
    observational_traces: list[dict],
) -> dict:
    traces = _trace_map(m5_analysis, observational_traces)
    results = [
        evaluate_compression(
            selected_candles,
            traces,
            return_count=return_count,
            analysis_at=analysis_at,
        ),
        evaluate_absorption(
            selected_candles,
            current_bars,
            traces,
            side=side,
            analysis_at=analysis_at,
        ),
        evaluate_pullback(
            traces,
            side=side,
            analysis_at=analysis_at,
        ),
    ]
    evaluated_count = sum(
        trace["status"] == "evaluated_shadow" for trace in results
    )
    payload = {
        "runtime_version": RUNTIME_VERSION,
        "status": (
            "evaluated_shadow"
            if evaluated_count == len(results)
            else "partially_evaluated_shadow"
            if evaluated_count
            else "blocked"
        ),
        "evaluated_rule_count": evaluated_count,
        "traces": results,
    }
    payload["runtime_trace_sha256"] = canonical_sha256(payload)
    return payload
