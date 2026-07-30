from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from statistics import median

from positioning_rule_runtime import empirical_midrank, robust_summary


RUNTIME_VERSION = "market-context-rule-runtime-v0.1"
REFERENCE_COUNT = 60
EXPECTED_BREADTH_UNIVERSE = 100
DAY_MS = 86_400_000
RULE_IDS = (
    "LIB-CAND-BREADTH-001",
    "LIB-CAND-SENTIMENT-PERCENTILE-001",
)
BREADTH_WINDOWS = {
    "1h": "price_change_percentage_1h_in_currency",
    "24h": "price_change_percentage_24h_in_currency",
    "7d": "price_change_percentage_7d_in_currency",
}


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


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def _timestamp_ms(value) -> int:
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        number = int(value)
        return number * 1000 if number < 10_000_000_000 else number
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def _trace(
    *,
    rule_id: str,
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    formula_ids: list[str],
    source_payload: object,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": "FAMILY-MARKET-CONTEXT",
        "role": "contextual",
        "parent_rule_ids": [],
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


def evaluate_cross_crypto_breadth(
    live_context: dict,
    *,
    side: str,
    time_horizon: str,
    analysis_at: str,
) -> dict:
    captured_at_ms = int(live_context.get("captured_at_ms") or 0)
    inputs = {
        "provider": "coingecko_coins_markets_top_100",
        "universe_policy": (
            "first_100_assets_ordered_by_current_market_cap_desc"
        ),
        "stablecoin_policy": (
            "included_because_provider_response_has_no_reliable_category_field"
        ),
        "return_windows": list(BREADTH_WINDOWS),
        "time_horizon": str(time_horizon),
        "side": str(side).lower(),
    }
    normalized = []
    invalid_timestamp_count = 0
    for raw in live_context.get("market_breadth_assets", []):
        asset_id = str(raw.get("id") or "").strip()
        if not asset_id:
            continue
        try:
            updated_at_ms = _timestamp_ms(raw["last_updated"])
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid_timestamp_count += 1
            continue
        changes = {}
        for window, key in BREADTH_WINDOWS.items():
            try:
                changes[window] = _finite(raw.get(key), key) / 100.0
            except (TypeError, ValueError):
                changes[window] = None
        normalized.append(
            {
                "id": asset_id,
                "symbol": str(raw.get("symbol") or "").upper(),
                "market_cap_rank": raw.get("market_cap_rank"),
                "updated_at_ms": updated_at_ms,
                "returns": changes,
            }
        )
    ids = [row["id"] for row in normalized]
    reasons = []
    if captured_at_ms <= 0:
        reasons.append("missing_capture_timestamp")
    if len(normalized) != EXPECTED_BREADTH_UNIVERSE:
        reasons.append("incomplete_top_100_universe")
    if len(ids) != len(set(ids)):
        reasons.append("duplicate_asset_ids")
    if any(row["updated_at_ms"] > captured_at_ms for row in normalized):
        reasons.append("breadth_timestamp_after_capture")
    valid_by_window = {
        window: [
            row["returns"][window]
            for row in normalized
            if row["returns"][window] is not None
        ]
        for window in BREADTH_WINDOWS
    }
    if any(not values for values in valid_by_window.values()):
        reasons.append("missing_return_window")
    if reasons:
        return _trace(
            rule_id=RULE_IDS[0],
            inputs={
                **inputs,
                "observed_universe_size": len(normalized),
                "invalid_timestamp_count": invalid_timestamp_count,
                "valid_counts": {
                    window: len(values)
                    for window, values in valid_by_window.items()
                },
            },
            outputs={},
            status="blocked",
            reason_codes=reasons,
            formula_ids=[
                f"{RULE_IDS[0]}-FORMULA-01",
                f"{RULE_IDS[0]}-FORMULA-02",
                f"{RULE_IDS[0]}-FORMULA-03",
            ],
            source_payload=normalized,
            executed_at=analysis_at,
        )

    direction = _side_sign(side)
    outputs = {
        "universe_size": len(normalized),
        "universe_ids": ids,
        "oldest_asset_update_ms": min(
            row["updated_at_ms"] for row in normalized
        ),
        "newest_asset_update_ms": max(
            row["updated_at_ms"] for row in normalized
        ),
        "windows": {},
    }
    for window, values in valid_by_window.items():
        breadth = sum(value > 0 for value in values) / len(values)
        median_return = median(values)
        outputs["windows"][window] = {
            "valid_count": len(values),
            "coverage_fraction": len(values) / len(normalized),
            "advancer_fraction": breadth,
            "centered_advancer_fraction": 2.0 * breadth - 1.0,
            "median_return_fraction": median_return,
            "side_adjusted_centered_advancer_fraction": (
                direction * (2.0 * breadth - 1.0)
            ),
            "side_adjusted_median_return_fraction": (
                direction * median_return
            ),
        }
    return _trace(
        rule_id=RULE_IDS[0],
        inputs={
            **inputs,
            "invalid_timestamp_count": invalid_timestamp_count,
        },
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        formula_ids=[
            f"{RULE_IDS[0]}-FORMULA-01",
            f"{RULE_IDS[0]}-FORMULA-02",
            f"{RULE_IDS[0]}-FORMULA-03",
        ],
        source_payload=normalized,
        executed_at=analysis_at,
    )


def evaluate_external_sentiment(
    live_context: dict,
    *,
    side: str,
    analysis_at: str,
) -> dict:
    cutoff_ms = int(live_context.get("request_cutoff_ms") or 0)
    inputs = {
        "provider": "alternative_me_crypto_fear_and_greed",
        "index_scope": "bitcoin_and_broad_crypto_market_sentiment",
        "reference_count_required": REFERENCE_COUNT,
        "reference_policy": "current_daily_value_plus_60_prior_days",
        "side": str(side).lower(),
    }
    rows = []
    invalid_count = 0
    for raw in live_context.get("fear_greed_history", []):
        try:
            timestamp_ms = _timestamp_ms(raw["timestamp"])
            value = _finite(raw["value"], "fear_greed_value")
            if not 0 <= value <= 100:
                raise ValueError("fear_greed_value_outside_0_100")
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid_count += 1
            continue
        if timestamp_ms <= cutoff_ms:
            rows.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "value": value,
                    "classification": raw.get("value_classification"),
                }
            )
    rows.sort(key=lambda row: row["timestamp_ms"])
    timestamps = [row["timestamp_ms"] for row in rows]
    reasons = []
    if cutoff_ms <= 0:
        reasons.append("missing_request_cutoff")
    if len(timestamps) != len(set(timestamps)):
        reasons.append("duplicate_sentiment_timestamps")
    if len(rows) < REFERENCE_COUNT + 1:
        reasons.append("insufficient_current_plus_60_sentiment_days")
    selected = rows[-(REFERENCE_COUNT + 1):]
    if (
        len(selected) == REFERENCE_COUNT + 1
        and any(
            right["timestamp_ms"] - left["timestamp_ms"] != DAY_MS
            for left, right in zip(selected, selected[1:])
        )
    ):
        reasons.append("gapped_daily_sentiment_history")
    if (
        selected
        and cutoff_ms - selected[-1]["timestamp_ms"] >= 2 * DAY_MS
    ):
        reasons.append("stale_daily_sentiment")
    if reasons:
        return _trace(
            rule_id=RULE_IDS[1],
            inputs={
                **inputs,
                "valid_day_count": len(rows),
                "invalid_row_count": invalid_count,
            },
            outputs={},
            status="blocked",
            reason_codes=reasons,
            formula_ids=[
                f"{RULE_IDS[1]}-FORMULA-01",
                f"{RULE_IDS[1]}-FORMULA-02",
                f"{RULE_IDS[1]}-FORMULA-03",
            ],
            source_payload=rows,
            executed_at=analysis_at,
        )

    current = selected[-1]
    reference_rows = selected[:-1]
    reference = [row["value"] for row in reference_rows]
    percentile = empirical_midrank(current["value"], reference)
    location, mad, robust_z = robust_summary(
        current["value"],
        reference,
    )
    direction = _side_sign(side)
    centered_percentile = 2.0 * percentile - 1.0
    reason_codes = (
        ["zero_mad_robust_z_unavailable"] if robust_z is None else []
    )
    return _trace(
        rule_id=RULE_IDS[1],
        inputs={
            **inputs,
            "current_timestamp_ms": current["timestamp_ms"],
            "reference_first_timestamp_ms": (
                reference_rows[0]["timestamp_ms"]
            ),
            "reference_last_timestamp_ms": (
                reference_rows[-1]["timestamp_ms"]
            ),
            "invalid_row_count": invalid_count,
        },
        outputs={
            "current_value": current["value"],
            "current_classification": current["classification"],
            "current_age_seconds": (
                cutoff_ms - current["timestamp_ms"]
            ) / 1000.0,
            "reference_count": len(reference),
            "reference_median": location,
            "reference_mad": mad,
            "sentiment_midrank_60": percentile,
            "centered_sentiment_midrank_60": centered_percentile,
            "sentiment_robust_z_60": robust_z,
            "centered_raw_sentiment": (
                current["value"] - 50.0
            ) / 50.0,
            "plan_side_sentiment_alignment": (
                direction * (current["value"] - 50.0) / 50.0
            ),
            "plan_side_percentile_alignment": (
                direction * centered_percentile
            ),
        },
        status="evaluated_shadow",
        reason_codes=reason_codes,
        formula_ids=[
            f"{RULE_IDS[1]}-FORMULA-01",
            f"{RULE_IDS[1]}-FORMULA-02",
            f"{RULE_IDS[1]}-FORMULA-03",
        ],
        source_payload=selected,
        executed_at=analysis_at,
    )


def evaluate_market_context_rule_family(
    live_context: dict | None,
    *,
    side: str,
    time_horizon: str,
    analysis_at: str,
) -> dict:
    context = live_context or {}
    traces = [
        evaluate_cross_crypto_breadth(
            context,
            side=side,
            time_horizon=time_horizon,
            analysis_at=analysis_at,
        ),
        evaluate_external_sentiment(
            context,
            side=side,
            analysis_at=analysis_at,
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
