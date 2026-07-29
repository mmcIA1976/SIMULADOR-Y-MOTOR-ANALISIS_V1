from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone


RUNTIME_VERSION = "technical-rule-runtime-v0.1"
RULE_IDS = (
    "LIB-CAND-EMA-TREND-001",
    "LIB-CAND-RSI-WILDER-001",
    "LIB-CAND-ATR-EXTENSION-001",
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


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def ema_series(values: list[float], period: int) -> list[float | None]:
    if period < 2:
        raise ValueError("ema_period_must_be_at_least_two")
    if len(values) < period:
        raise ValueError("insufficient_values_for_ema")
    alpha = 2.0 / (period + 1.0)
    result: list[float | None] = [None] * (period - 1)
    current = math.fsum(values[:period]) / period
    result.append(current)
    for value in values[period:]:
        current = alpha * value + (1.0 - alpha) * current
        result.append(current)
    return result


def wilder_rsi(values: list[float], period: int = 14) -> float:
    if period < 2 or len(values) < period + 1:
        raise ValueError("insufficient_values_for_rsi")
    changes = [
        current - previous
        for previous, current in zip(values, values[1:])
    ]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = math.fsum(gains[:period]) / period
    avg_loss = math.fsum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
    if avg_gain == 0.0 and avg_loss == 0.0:
        return 50.0
    if avg_loss == 0.0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def wilder_atr(rows: list[dict], period: int = 14) -> float:
    if period < 2 or len(rows) < period:
        raise ValueError("insufficient_values_for_atr")
    true_ranges = []
    previous_close = None
    for index, row in enumerate(rows):
        high = _finite_positive(row["high"], f"high_{index}")
        low = _finite_positive(row["low"], f"low_{index}")
        close = _finite_positive(row["close"], f"close_{index}")
        if high < low:
            raise ValueError("high_must_not_be_below_low")
        true_range = high - low
        if previous_close is not None:
            true_range = max(
                true_range,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = close
    current = math.fsum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        current = ((period - 1) * current + true_range) / period
    return current


def _trace(
    *,
    rule_id: str,
    family_id: str,
    role: str,
    parent_rule_ids: list[str],
    formula_ids: list[str],
    inputs: dict,
    outputs: dict,
    source_data_sha256: str,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": family_id,
        "role": role,
        "parent_rule_ids": parent_rule_ids,
        "status": "evaluated_shadow",
        "formula_ids": formula_ids,
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": source_data_sha256,
        "executed_at": executed_at,
        "probability_effect": "none_shadow_observation",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def evaluate_technical_rule_family(
    candles: list[dict],
    *,
    side: str,
    analysis_at: str,
    interval_seconds: int,
    source_data_sha256: str,
) -> dict:
    if len(candles) < 206:
        return {
            "runtime_version": RUNTIME_VERSION,
            "status": "blocked",
            "reason": "insufficient_closed_candles_for_ema200_and_slope",
            "traces": [],
        }
    direction = _side_sign(side)
    closed = [
        row
        for row in candles
        if int(row["close_time_ms"])
        <= int(
            datetime.fromisoformat(
                analysis_at.replace("Z", "+00:00")
            ).timestamp()
            * 1000
        )
    ]
    if len(closed) < 206:
        return {
            "runtime_version": RUNTIME_VERSION,
            "status": "blocked",
            "reason": "insufficient_pretrade_closed_candles",
            "traces": [],
        }
    closes = [
        _finite_positive(row["close"], f"close_{index}")
        for index, row in enumerate(closed)
    ]
    ema20 = ema_series(closes, 20)
    ema50 = ema_series(closes, 50)
    ema200 = ema_series(closes, 200)
    atr14 = wilder_atr(closed, 14)
    current_close = closes[-1]
    current_ema20 = float(ema20[-1])
    current_ema50 = float(ema50[-1])
    prior_ema50 = float(ema50[-7])
    current_ema200 = float(ema200[-1])
    if atr14 <= 0.0:
        return {
            "runtime_version": RUNTIME_VERSION,
            "status": "blocked",
            "reason": "zero_atr",
            "traces": [],
        }
    rsi14 = wilder_rsi(closes, 14)
    slope_atr = (current_ema50 - prior_ema50) / atr14
    close_vs_ema50_log = math.log(current_close / current_ema50)
    ema50_vs_ema200_log = math.log(current_ema50 / current_ema200)
    extension_atr = (current_close - current_ema20) / atr14
    common_inputs = {
        "side": str(side).lower(),
        "interval_seconds": int(interval_seconds),
        "closed_candle_count": len(closed),
        "last_close_time_ms": int(closed[-1]["close_time_ms"]),
    }
    traces = [
        _trace(
            rule_id="LIB-CAND-EMA-TREND-001",
            family_id="FAMILY-TREND",
            role="contextual",
            parent_rule_ids=[],
            formula_ids=[
                "LIB-CAND-EMA-TREND-001-FORMULA-01",
                "LIB-CAND-EMA-TREND-001-FORMULA-02",
                "LIB-CAND-EMA-TREND-001-FORMULA-03",
            ],
            inputs=common_inputs,
            outputs={
                "close": current_close,
                "ema50": current_ema50,
                "ema200": current_ema200,
                "ema50_slope_6bars_atr": slope_atr,
                "close_vs_ema50_log": close_vs_ema50_log,
                "ema50_vs_ema200_log": ema50_vs_ema200_log,
                "side_adjusted_close_vs_ema50_log": (
                    direction * close_vs_ema50_log
                ),
                "side_adjusted_ema50_vs_ema200_log": (
                    direction * ema50_vs_ema200_log
                ),
                "side_adjusted_slope_atr": direction * slope_atr,
            },
            source_data_sha256=source_data_sha256,
            executed_at=analysis_at,
        ),
        _trace(
            rule_id="LIB-CAND-RSI-WILDER-001",
            family_id="FAMILY-MOMENTUM",
            role="contextual",
            parent_rule_ids=[],
            formula_ids=[
                "LIB-CAND-RSI-WILDER-001-FORMULA-01",
                "LIB-CAND-RSI-WILDER-001-FORMULA-02",
            ],
            inputs=common_inputs,
            outputs={
                "rsi14": rsi14,
                "centered_rsi": (rsi14 - 50.0) / 50.0,
                "side_adjusted_centered_rsi": (
                    direction * (rsi14 - 50.0) / 50.0
                ),
            },
            source_data_sha256=source_data_sha256,
            executed_at=analysis_at,
        ),
        _trace(
            rule_id="LIB-CAND-ATR-EXTENSION-001",
            family_id="FAMILY-TREND-X-VOLATILITY",
            role="interaction",
            parent_rule_ids=["LIB-CAND-EMA-TREND-001"],
            formula_ids=[
                "LIB-CAND-ATR-EXTENSION-001-FORMULA-01",
            ],
            inputs=common_inputs,
            outputs={
                "ema20": current_ema20,
                "atr14": atr14,
                "atr14_fraction_price": atr14 / current_close,
                "extension_atr": extension_atr,
                "side_adjusted_extension_atr": direction * extension_atr,
            },
            source_data_sha256=source_data_sha256,
            executed_at=analysis_at,
        ),
    ]
    result = {
        "runtime_version": RUNTIME_VERSION,
        "status": "evaluated_shadow",
        "analysis_at": analysis_at,
        "data_cutoff_at_ms": int(closed[-1]["close_time_ms"]),
        "source_data_sha256": source_data_sha256,
        "rule_ids": list(RULE_IDS),
        "traces": traces,
    }
    result["runtime_trace_sha256"] = canonical_sha256(result)
    return result
