from __future__ import annotations

import hashlib
import json
import math
from statistics import median


RUNTIME_VERSION = "positioning-rule-runtime-v0.1"
REFERENCE_COUNT = 60
RULE_IDS = (
    "LIB-CAND-FUNDING-PERCENTILE-001",
    "LIB-CAND-CROWDING-PERCENTILE-001",
)


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name}_must_be_finite")
    return number


def _finite_positive(value, name: str) -> float:
    number = _finite(value, name)
    if number <= 0:
        raise ValueError(f"{name}_must_be_positive")
    return number


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def empirical_midrank(value: float, reference: list[float]) -> float:
    if not reference:
        raise ValueError("reference_required")
    below = sum(item < value for item in reference)
    equal = sum(item == value for item in reference)
    return (below + 0.5 * equal) / len(reference)


def robust_summary(
    value: float,
    reference: list[float],
) -> tuple[float, float, float | None]:
    location = median(reference)
    mad = median(abs(item - location) for item in reference)
    robust_z = (
        (value - location) / (1.4826 * mad)
        if mad > 0
        else None
    )
    return location, mad, robust_z


def _trace(
    *,
    rule_id: str,
    family_id: str,
    parent_rule_ids: list[str],
    formula_ids: list[str],
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    source_payload: dict,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": family_id,
        "role": "contextual",
        "parent_rule_ids": parent_rule_ids,
        "status": status,
        "reason_codes": reason_codes,
        "formula_ids": formula_ids,
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": canonical_sha256(source_payload),
        "executed_at": executed_at,
        "probability_effect": "none_shadow_observation",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def evaluate_funding_relative(
    live_context: dict,
    *,
    side: str,
    analysis_at: str,
) -> dict:
    snapshot = live_context.get("funding_snapshot") or {}
    captured_at_ms = int(live_context.get("captured_at_ms") or 0)
    inputs = {
        "provider": "binance_usdm_premium_index_and_funding_history",
        "reference_count_required": REFERENCE_COUNT,
        "reference_policy": "last_60_strictly_prior_settled_rates",
        "current_rate_semantics": "premium_index_lastFundingRate",
        "side": str(side).lower(),
    }
    try:
        current_rate = _finite(
            snapshot["lastFundingRate"],
            "lastFundingRate",
        )
        current_time_ms = int(snapshot.get("time") or captured_at_ms)
    except (KeyError, TypeError, ValueError):
        return _trace(
            rule_id=RULE_IDS[0],
            family_id="FAMILY-PERPETUAL-DISLOCATION",
            parent_rule_ids=["M4-RULE-FUNDING-STATE-001"],
            formula_ids=[
                f"{RULE_IDS[0]}-FORMULA-01",
                f"{RULE_IDS[0]}-FORMULA-02",
                f"{RULE_IDS[0]}-FORMULA-03",
            ],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["missing_or_invalid_current_funding_rate"],
            source_payload={},
            executed_at=analysis_at,
        )
    if (
        captured_at_ms <= 0
        or current_time_ms <= 0
        or current_time_ms > captured_at_ms
    ):
        return _trace(
            rule_id=RULE_IDS[0],
            family_id="FAMILY-PERPETUAL-DISLOCATION",
            parent_rule_ids=["M4-RULE-FUNDING-STATE-001"],
            formula_ids=[
                f"{RULE_IDS[0]}-FORMULA-01",
                f"{RULE_IDS[0]}-FORMULA-02",
                f"{RULE_IDS[0]}-FORMULA-03",
            ],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["funding_snapshot_timestamp_after_capture"],
            source_payload={"snapshot": snapshot},
            executed_at=analysis_at,
        )

    rows = []
    invalid_count = 0
    for raw in live_context.get("funding_history", []):
        try:
            timestamp = int(raw["fundingTime"])
            rate = _finite(raw["fundingRate"], "fundingRate")
        except (KeyError, TypeError, ValueError):
            invalid_count += 1
            continue
        if (
            timestamp < current_time_ms
            and timestamp <= captured_at_ms
            and str(raw.get("rateType", "Regular")) == "Regular"
        ):
            rows.append((timestamp, rate))
    rows.sort()
    timestamps = [timestamp for timestamp, _ in rows]
    if len(timestamps) != len(set(timestamps)):
        reasons = ["duplicate_funding_timestamps"]
    elif len(rows) < REFERENCE_COUNT:
        reasons = ["insufficient_60_prior_funding_rates"]
    else:
        reasons = []
    if reasons:
        return _trace(
            rule_id=RULE_IDS[0],
            family_id="FAMILY-PERPETUAL-DISLOCATION",
            parent_rule_ids=["M4-RULE-FUNDING-STATE-001"],
            formula_ids=[
                f"{RULE_IDS[0]}-FORMULA-01",
                f"{RULE_IDS[0]}-FORMULA-02",
                f"{RULE_IDS[0]}-FORMULA-03",
            ],
            inputs={
                **inputs,
                "valid_prior_count": len(rows),
                "invalid_row_count": invalid_count,
            },
            outputs={},
            status="blocked",
            reason_codes=reasons,
            source_payload={"snapshot": snapshot, "history": rows},
            executed_at=analysis_at,
        )

    reference_rows = rows[-REFERENCE_COUNT:]
    reference = [rate for _, rate in reference_rows]
    percentile = empirical_midrank(current_rate, reference)
    location, mad, robust_z = robust_summary(current_rate, reference)
    evaluated_reasons = (
        ["zero_mad_robust_z_unavailable"] if robust_z is None else []
    )
    source_payload = {
        "snapshot_time_ms": current_time_ms,
        "current_rate": current_rate,
        "reference_rows": reference_rows,
    }
    return _trace(
        rule_id=RULE_IDS[0],
        family_id="FAMILY-PERPETUAL-DISLOCATION",
        parent_rule_ids=["M4-RULE-FUNDING-STATE-001"],
        formula_ids=[
            f"{RULE_IDS[0]}-FORMULA-01",
            f"{RULE_IDS[0]}-FORMULA-02",
            f"{RULE_IDS[0]}-FORMULA-03",
        ],
        inputs={
            **inputs,
            "current_timestamp_ms": current_time_ms,
            "reference_first_timestamp_ms": reference_rows[0][0],
            "reference_last_timestamp_ms": reference_rows[-1][0],
            "invalid_row_count": invalid_count,
        },
        outputs={
            "current_funding_rate": current_rate,
            "reference_count": len(reference),
            "reference_median": location,
            "reference_mad": mad,
            "funding_midrank_60": percentile,
            "centered_funding_midrank_60": 2.0 * percentile - 1.0,
            "funding_robust_z_60": robust_z,
            "plan_side_funding_cost_rate": (
                _side_sign(side) * current_rate
            ),
        },
        status="evaluated_shadow",
        reason_codes=evaluated_reasons,
        source_payload=source_payload,
        executed_at=analysis_at,
    )


def evaluate_crowding_relative(
    live_context: dict,
    *,
    side: str,
    analysis_at: str,
    interval_seconds: int,
) -> dict:
    cutoff_ms = int(live_context.get("request_cutoff_ms") or 0)
    interval_ms = int(interval_seconds) * 1000
    inputs = {
        "provider": "binance_usdm_global_long_short_account_ratio",
        "reference_count_required": REFERENCE_COUNT,
        "reference_policy": "current_plus_60_strictly_prior_periods",
        "period": live_context.get("interval"),
        "interval_seconds": int(interval_seconds),
        "ratio_semantics": "long_account_count_over_short_account_count",
        "side": str(side).lower(),
    }
    rows = []
    invalid_count = 0
    for raw in live_context.get("global_long_short_history", []):
        try:
            timestamp = int(raw["timestamp"])
            ratio = _finite_positive(
                raw["longShortRatio"],
                "longShortRatio",
            )
            long_account = _finite(
                raw.get("longAccount"),
                "longAccount",
            )
            short_account = _finite(
                raw.get("shortAccount"),
                "shortAccount",
            )
            if not (
                0 <= long_account <= 1
                and 0 <= short_account <= 1
            ):
                raise ValueError("account_shares_outside_unit_interval")
        except (KeyError, TypeError, ValueError):
            invalid_count += 1
            continue
        if timestamp <= cutoff_ms:
            rows.append(
                (timestamp, ratio, long_account, short_account)
            )
    rows.sort()
    timestamps = [row[0] for row in rows]
    reasons = []
    if cutoff_ms <= 0:
        reasons.append("missing_request_cutoff")
    if len(timestamps) != len(set(timestamps)):
        reasons.append("duplicate_crowding_timestamps")
    if len(rows) < REFERENCE_COUNT + 1:
        reasons.append("insufficient_current_plus_60_crowding_periods")
    selected = rows[-(REFERENCE_COUNT + 1):]
    if (
        len(selected) == REFERENCE_COUNT + 1
        and any(
            right[0] - left[0] != interval_ms
            for left, right in zip(selected, selected[1:])
        )
    ):
        reasons.append("gapped_crowding_history")
    if reasons:
        return _trace(
            rule_id=RULE_IDS[1],
            family_id="FAMILY-POSITIONING",
            parent_rule_ids=[],
            formula_ids=[
                f"{RULE_IDS[1]}-FORMULA-01",
                f"{RULE_IDS[1]}-FORMULA-02",
                f"{RULE_IDS[1]}-FORMULA-03",
            ],
            inputs={
                **inputs,
                "valid_period_count": len(rows),
                "invalid_row_count": invalid_count,
            },
            outputs={},
            status="blocked",
            reason_codes=reasons,
            source_payload={"rows": rows},
            executed_at=analysis_at,
        )

    current = selected[-1]
    reference_rows = selected[:-1]
    current_log_ratio = math.log(current[1])
    reference = [math.log(row[1]) for row in reference_rows]
    percentile = empirical_midrank(current_log_ratio, reference)
    location, mad, robust_z = robust_summary(
        current_log_ratio,
        reference,
    )
    side_percentile = (
        percentile if _side_sign(side) > 0 else 1.0 - percentile
    )
    evaluated_reasons = (
        ["zero_mad_robust_z_unavailable"] if robust_z is None else []
    )
    return _trace(
        rule_id=RULE_IDS[1],
        family_id="FAMILY-POSITIONING",
        parent_rule_ids=[],
        formula_ids=[
            f"{RULE_IDS[1]}-FORMULA-01",
            f"{RULE_IDS[1]}-FORMULA-02",
            f"{RULE_IDS[1]}-FORMULA-03",
        ],
        inputs={
            **inputs,
            "current_timestamp_ms": current[0],
            "reference_first_timestamp_ms": reference_rows[0][0],
            "reference_last_timestamp_ms": reference_rows[-1][0],
            "invalid_row_count": invalid_count,
        },
        outputs={
            "current_long_short_ratio": current[1],
            "current_long_account_fraction": current[2],
            "current_short_account_fraction": current[3],
            "current_log_long_short_ratio": current_log_ratio,
            "reference_count": len(reference),
            "reference_log_ratio_median": location,
            "reference_log_ratio_mad": mad,
            "crowding_midrank_60": percentile,
            "centered_crowding_midrank_60": 2.0 * percentile - 1.0,
            "crowding_robust_z_60": robust_z,
            "plan_side_crowding_midrank_60": side_percentile,
            "plan_side_crowding_centered_60": (
                2.0 * side_percentile - 1.0
            ),
        },
        status="evaluated_shadow",
        reason_codes=evaluated_reasons,
        source_payload={"selected_rows": selected},
        executed_at=analysis_at,
    )


def evaluate_positioning_rule_family(
    live_context: dict | None,
    *,
    side: str,
    analysis_at: str,
    interval_seconds: int,
) -> dict:
    context = live_context or {}
    traces = [
        evaluate_funding_relative(
            context,
            side=side,
            analysis_at=analysis_at,
        ),
        evaluate_crowding_relative(
            context,
            side=side,
            analysis_at=analysis_at,
            interval_seconds=interval_seconds,
        ),
    ]
    evaluated_count = sum(
        trace["status"] == "evaluated_shadow" for trace in traces
    )
    payload = {
        "runtime_version": RUNTIME_VERSION,
        "status": (
            "evaluated_shadow"
            if evaluated_count == len(traces)
            else "partially_evaluated_shadow"
            if evaluated_count
            else "blocked"
        ),
        "evaluated_rule_count": evaluated_count,
        "traces": traces,
    }
    payload["runtime_trace_sha256"] = canonical_sha256(payload)
    return payload
