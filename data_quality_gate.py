from __future__ import annotations

import hashlib
import json
import math


RUNTIME_VERSION = "pretrade-data-quality-gate-v0.1"
PERIOD_RELEASE_GRACE_MS = 60_000
FRESHNESS_RULE_ID = "LIB-CAND-DATA-FRESHNESS-001"
INTEGRITY_RULE_ID = "LIB-CAND-CANDLE-INTEGRITY-001"


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def candle_source_sha256(candles: list[dict]) -> str | None:
    if not candles:
        return None
    return canonical_sha256(
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


class DataQualityError(ValueError):
    def __init__(self, code: str, report: dict):
        super().__init__(code)
        self.report = report


def _trace(
    *,
    rule_id: str,
    status: str,
    outputs: dict,
    reason_codes: list[str],
    source_sha256: str | None,
    analysis_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": "FAMILY-DATA-QUALITY",
        "role": "blocking",
        "status": status,
        "reason_codes": reason_codes,
        "outputs": outputs,
        "source_data_sha256": source_sha256,
        "executed_at": analysis_at,
        "probability_effect": "none_data_quality_gate",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def validate_pretrade_candles(
    candles: list[dict],
    *,
    analysis_at: str,
    analysis_at_ms: int,
    interval_seconds: int,
    required_candle_count: int,
) -> dict:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds_must_be_positive")
    if required_candle_count < 2:
        raise ValueError("required_candle_count_must_be_at_least_two")

    interval_ms = int(interval_seconds) * 1000
    closed = []
    invalid_schema_count = 0
    for row in candles:
        try:
            close_time = int(row["close_time_ms"])
        except (KeyError, TypeError, ValueError):
            invalid_schema_count += 1
            continue
        if close_time <= analysis_at_ms:
            closed.append(row)

    selected = (
        closed[-required_candle_count:]
        if len(closed) >= required_candle_count
        else list(closed)
    )
    close_times = []
    open_times = []
    invalid_value_count = 0
    invalid_ohlc_count = 0
    invalid_duration_count = 0
    for row in selected:
        try:
            open_time = int(row["open_time_ms"])
            close_time = int(row["close_time_ms"])
            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close_price = float(row["close"])
            volume = float(row["volume"])
        except (KeyError, TypeError, ValueError):
            invalid_value_count += 1
            continue
        values = (open_price, high, low, close_price, volume)
        if (
            not all(math.isfinite(value) for value in values)
            or min(open_price, high, low, close_price) <= 0
            or volume < 0
        ):
            invalid_value_count += 1
        if high < max(open_price, close_price) or low > min(
            open_price,
            close_price,
        ):
            invalid_ohlc_count += 1
        if close_time - open_time + 1 != interval_ms:
            invalid_duration_count += 1
        open_times.append(open_time)
        close_times.append(close_time)

    duplicate_count = len(close_times) - len(set(close_times))
    duplicate_open_count = len(open_times) - len(set(open_times))
    out_of_order_count = sum(
        right <= left
        for left, right in zip(close_times, close_times[1:])
    )
    gap_count = sum(
        right - left != interval_ms
        for left, right in zip(close_times, close_times[1:])
    )
    missing_count = max(required_candle_count - len(selected), 0)
    latest_close_ms = close_times[-1] if close_times else None
    age_ms = (
        analysis_at_ms - latest_close_ms
        if latest_close_ms is not None
        else None
    )
    freshness_limit_ms = interval_ms + PERIOD_RELEASE_GRACE_MS
    freshness_valid = (
        age_ms is not None
        and age_ms >= 0
        and age_ms <= freshness_limit_ms
    )
    integrity_valid = (
        len(selected) == required_candle_count
        and len(close_times) == required_candle_count
        and invalid_schema_count == 0
        and invalid_value_count == 0
        and invalid_ohlc_count == 0
        and invalid_duration_count == 0
        and duplicate_count == 0
        and duplicate_open_count == 0
        and out_of_order_count == 0
        and gap_count == 0
        and missing_count == 0
    )
    source_sha256 = candle_source_sha256(selected)
    freshness_reasons = (
        []
        if freshness_valid
        else ["latest_closed_candle_outside_freshness_limit"]
    )
    integrity_reasons = []
    if missing_count:
        integrity_reasons.append("insufficient_pretrade_history")
    if invalid_schema_count or invalid_value_count:
        integrity_reasons.append("invalid_candle_values")
    if invalid_ohlc_count:
        integrity_reasons.append("incoherent_ohlc")
    if invalid_duration_count:
        integrity_reasons.append("invalid_candle_duration")
    if duplicate_count or duplicate_open_count:
        integrity_reasons.append("duplicate_candles")
    if out_of_order_count:
        integrity_reasons.append("candles_not_strictly_ordered")
    if gap_count:
        integrity_reasons.append("gapped_or_misaligned_candles")

    freshness_trace = _trace(
        rule_id=FRESHNESS_RULE_ID,
        status="passed" if freshness_valid else "failed",
        outputs={
            "latest_closed_candle_ms": latest_close_ms,
            "analysis_at_ms": analysis_at_ms,
            "age_ms": age_ms,
            "freshness_limit_ms": freshness_limit_ms,
            "fresh": freshness_valid,
        },
        reason_codes=freshness_reasons,
        source_sha256=source_sha256,
        analysis_at=analysis_at,
    )
    integrity_trace = _trace(
        rule_id=INTEGRITY_RULE_ID,
        status="passed" if integrity_valid else "failed",
        outputs={
            "required_candle_count": required_candle_count,
            "observed_closed_candle_count": len(selected),
            "missing_count": missing_count,
            "duplicate_count": duplicate_count,
            "duplicate_open_count": duplicate_open_count,
            "out_of_order_count": out_of_order_count,
            "gap_count": gap_count,
            "invalid_schema_count": invalid_schema_count,
            "invalid_value_count": invalid_value_count,
            "invalid_ohlc_count": invalid_ohlc_count,
            "invalid_duration_count": invalid_duration_count,
            "integrity_valid": integrity_valid,
        },
        reason_codes=integrity_reasons,
        source_sha256=source_sha256,
        analysis_at=analysis_at,
    )
    report = {
        "runtime_version": RUNTIME_VERSION,
        "status": (
            "valid"
            if freshness_valid and integrity_valid
            else "blocked"
        ),
        "validation_pass_count": 1,
        "selected_candle_count": len(selected),
        "source_data_sha256": source_sha256,
        "traces": [freshness_trace, integrity_trace],
    }
    report["report_sha256"] = canonical_sha256(report)
    if report["status"] != "valid":
        if missing_count:
            code = "insufficient_pretrade_history"
        elif not integrity_valid:
            code = "pretrade_candle_integrity_failed"
        else:
            code = "pretrade_candles_stale"
        raise DataQualityError(code, report)
    report["selected_candles"] = selected
    return report
