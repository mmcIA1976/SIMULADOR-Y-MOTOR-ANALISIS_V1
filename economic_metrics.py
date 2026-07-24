from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from math import isfinite
from statistics import mean, median

from versioning import ECONOMIC_NORMALIZATION_VERSION


MANUAL_CLOSE_REASONS = {
    "manual",
    "cut_loss",
    "take_partial",
    "emotion",
    "invalidated",
}


def finite_float(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def closure_type(close_reason: str | None) -> str:
    if close_reason in {"take_profit", "stop_loss"}:
        return "automatic_plan"
    if close_reason in MANUAL_CLOSE_REASONS:
        return "manual"
    if close_reason == "contest_expired":
        return "contest_expiry"
    return "other"


def economic_plan_outcome(plan_result: str | None) -> str:
    if plan_result in {"plan_success", "plan_would_succeed"}:
        return "take_profit"
    if plan_result in {"plan_failure", "plan_would_fail"}:
        return "stop_loss"
    if plan_result == "ambiguous_same_candle":
        return "ambiguous"
    if plan_result == "contest_expiry_mark_to_market":
        return "mark_to_market"
    if plan_result in {"plan_unresolved", "manual_pending_or_unclassified"}:
        return "unresolved"
    return "not_available"


def excluded_metrics(
    operation: dict,
    reason: str,
    normalized_at: str,
    effective_plan_result: str | None,
) -> dict:
    return {
        "version": ECONOMIC_NORMALIZATION_VERSION,
        "status": "excluded",
        "exclusion_reason": reason,
        "normalized_at": normalized_at,
        "closure_type": closure_type(operation.get("close_reason")),
        "notional_amount": None,
        "initial_risk_pct": None,
        "initial_risk_amount": None,
        "unleveraged_return_pct": None,
        "margin_return_pct": None,
        "r_multiple": None,
        "economic_plan_outcome": economic_plan_outcome(effective_plan_result),
        "final_pnl_secondary": finite_float(operation.get("final_pnl")),
        "closed_at": operation.get("closed_at"),
    }


def normalize_operation_economics(
    operation: dict,
    effective_plan_result: str | None = None,
    normalized_at: str | None = None,
) -> dict:
    timestamp = normalized_at or datetime.now(timezone.utc).isoformat()
    plan_result = (
        effective_plan_result
        or operation.get("reconstructed_plan_result")
        or operation.get("plan_result")
    )
    side = str(operation.get("side") or "")
    entry = finite_float(operation.get("entry"))
    margin = finite_float(operation.get("margin"))
    leverage = finite_float(operation.get("leverage"))
    stop_loss = finite_float(operation.get("stop_loss"))
    final_pnl = finite_float(operation.get("final_pnl"))

    validations = (
        ("invalid_side", side not in {"long", "short"}),
        ("invalid_entry", entry is None or entry <= 0),
        ("invalid_margin", margin is None or margin <= 0),
        ("invalid_leverage", leverage is None or leverage <= 0),
        ("invalid_stop_loss", stop_loss is None or stop_loss <= 0),
        ("missing_final_pnl", final_pnl is None),
    )
    for reason, invalid in validations:
        if invalid:
            return excluded_metrics(operation, reason, timestamp, plan_result)

    if side == "long":
        risk_fraction = (entry - stop_loss) / entry
        if risk_fraction <= 0:
            return excluded_metrics(
                operation,
                "stop_not_adverse_to_long",
                timestamp,
                plan_result,
            )
    else:
        risk_fraction = (stop_loss - entry) / entry
        if risk_fraction <= 0:
            return excluded_metrics(
                operation,
                "stop_not_adverse_to_short",
                timestamp,
                plan_result,
            )

    notional = margin * leverage
    initial_risk_amount = notional * risk_fraction
    if not isfinite(initial_risk_amount) or initial_risk_amount <= 0:
        return excluded_metrics(operation, "zero_initial_risk", timestamp, plan_result)

    return {
        "version": ECONOMIC_NORMALIZATION_VERSION,
        "status": "included",
        "exclusion_reason": None,
        "normalized_at": timestamp,
        "closure_type": closure_type(operation.get("close_reason")),
        "notional_amount": round(notional, 8),
        "initial_risk_pct": round(risk_fraction * 100, 8),
        "initial_risk_amount": round(initial_risk_amount, 8),
        "unleveraged_return_pct": round((final_pnl / notional) * 100, 8),
        "margin_return_pct": round((final_pnl / margin) * 100, 8),
        "r_multiple": round(final_pnl / initial_risk_amount, 8),
        "economic_plan_outcome": economic_plan_outcome(plan_result),
        "final_pnl_secondary": round(final_pnl, 8),
        "closed_at": operation.get("closed_at"),
    }


def economic_case_fields(row: dict) -> dict:
    return {
        "economic_normalization_version": row.get("economic_normalization_version"),
        "economic_normalization_status": row.get("economic_normalization_status"),
        "economic_exclusion_reason": row.get("economic_exclusion_reason"),
        "closure_type": row.get("closure_type"),
        "initial_risk_amount": finite_float(row.get("initial_risk_amount")),
        "unleveraged_return_pct": finite_float(row.get("unleveraged_return_pct")),
        "margin_return_pct": finite_float(row.get("margin_return_pct")),
        "r_multiple": finite_float(row.get("r_multiple")),
        "economic_plan_outcome": row.get("economic_plan_outcome"),
        "economic_final_pnl": finite_float(row.get("economic_final_pnl")),
        "closed_at": row.get("closed_at"),
    }


def economic_metrics_case_fields(metrics: dict) -> dict:
    return {
        "economic_normalization_version": metrics.get("version"),
        "economic_normalization_status": metrics.get("status"),
        "economic_exclusion_reason": metrics.get("exclusion_reason"),
        "closure_type": metrics.get("closure_type"),
        "initial_risk_amount": finite_float(metrics.get("initial_risk_amount")),
        "unleveraged_return_pct": finite_float(
            metrics.get("unleveraged_return_pct")
        ),
        "margin_return_pct": finite_float(metrics.get("margin_return_pct")),
        "r_multiple": finite_float(metrics.get("r_multiple")),
        "economic_plan_outcome": metrics.get("economic_plan_outcome"),
        "economic_final_pnl": finite_float(metrics.get("final_pnl_secondary")),
        "closed_at": metrics.get("closed_at"),
    }


def maximum_cumulative_drawdown(values: list[float]) -> float | None:
    if not values:
        return None
    cumulative = 0.0
    peak = 0.0
    maximum = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return round(maximum, 8)


def chronological_cases(cases: list[dict]) -> list[dict]:
    return sorted(
        cases,
        key=lambda item: (
            str(item.get("closed_at") or ""),
            int(item.get("operation_id") or 0),
        ),
    )


def summarize_economic_cases(cases: list[dict]) -> dict:
    included = [
        case
        for case in cases
        if case.get("economic_normalization_status") == "included"
        and finite_float(case.get("r_multiple")) is not None
    ]
    excluded = [case for case in cases if case not in included]
    ordered = chronological_cases(included)
    r_values = [float(case["r_multiple"]) for case in included]
    unleveraged = [
        float(case["unleveraged_return_pct"])
        for case in included
        if finite_float(case.get("unleveraged_return_pct")) is not None
    ]
    margin_returns = [
        float(case["margin_return_pct"])
        for case in included
        if finite_float(case.get("margin_return_pct")) is not None
    ]
    pnl_values = [
        float(
            case.get("economic_final_pnl")
            if finite_float(case.get("economic_final_pnl")) is not None
            else case.get("final_pnl")
            or 0
        )
        for case in cases
    ]
    outcome_counts = Counter(
        str(case.get("economic_plan_outcome") or "not_available")
        for case in cases
    )
    exclusion_counts = Counter(
        str(case.get("economic_exclusion_reason") or "not_normalized")
        for case in excluded
    )
    return {
        "economic_metric_role": "primary",
        "normalized_cases": len(included),
        "excluded_cases": len(excluded),
        "exclusion_reasons": dict(exclusion_counts),
        "avg_r_multiple": round(mean(r_values), 8) if r_values else None,
        "median_r_multiple": round(median(r_values), 8) if r_values else None,
        "total_r_multiple": round(sum(r_values), 8) if r_values else None,
        "avg_unleveraged_return_pct": (
            round(mean(unleveraged), 8) if unleveraged else None
        ),
        "avg_margin_return_pct": (
            round(mean(margin_returns), 8) if margin_returns else None
        ),
        "max_cumulative_r_drawdown": maximum_cumulative_drawdown(
            [float(case["r_multiple"]) for case in ordered]
        ),
        "economic_plan_outcomes": dict(outcome_counts),
        "pnl_metric_role": "secondary",
        "total_pnl": round(sum(pnl_values), 4),
        "avg_pnl": round(mean(pnl_values), 4) if pnl_values else None,
    }


def group_economic_cases(cases: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for case in cases:
        groups.setdefault(str(case.get(key) or "sin_dato"), []).append(case)
    return [
        {"name": name, "cases": len(items), **summarize_economic_cases(items)}
        for name, items in sorted(
            groups.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]


def signal_pattern_read(
    successes: int,
    failures: int,
    avg_r_multiple: float | None,
) -> str:
    if avg_r_multiple is not None:
        if failures > successes and avg_r_multiple < 0:
            return "observed_risk_pattern"
        if successes >= failures and avg_r_multiple >= 0:
            return "observed_winner_pattern"
        return "mixed_context_needs_review"
    if failures > successes:
        return "observed_risk_pattern"
    if successes > failures:
        return "observed_winner_pattern"
    return "mixed_context_needs_review"
