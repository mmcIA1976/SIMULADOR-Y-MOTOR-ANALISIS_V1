from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from analysis_engine import TradeProposal
from limit_order_contract import (
    LIMIT_ORDER_ANALYSIS_FAMILY,
    LIMIT_ORDER_CONTRACT_VERSION,
    LifecycleEvent,
    learning_label_for_terminal_event,
)
from m7_production_analysis import NewEngineAnalysisError, analyze_trade


LIMIT_LIFECYCLE_RUNTIME_VERSION = "limit-lifecycle-runtime-v0.1"


def parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_limit_context(analysis_payload: Mapping[str, Any] | None) -> dict | None:
    if not isinstance(analysis_payload, Mapping):
        return None
    limit_analysis = analysis_payload.get("limit_analysis")
    if not isinstance(limit_analysis, Mapping):
        return None
    contract = limit_analysis.get("contract")
    if not isinstance(contract, Mapping):
        return None
    if contract.get("contract_version") != LIMIT_ORDER_CONTRACT_VERSION:
        return None
    if contract.get("analysis_family") != LIMIT_ORDER_ANALYSIS_FAMILY:
        return None
    order = contract.get("order")
    if not isinstance(order, Mapping) or order.get("entry_order_type") != "limit_pullback":
        return None
    return {
        "contract": dict(contract),
        "activation_baseline": dict(limit_analysis.get("activation_baseline") or {}),
    }


def activation_expires_at(contract: Mapping[str, Any]) -> datetime:
    return parse_utc(contract["windows"]["activation"]["expires_at"])


def outcome_expires_at(contract: Mapping[str, Any], activated_at: Any) -> datetime:
    horizon_seconds = int(
        contract["windows"]["outcome_after_activation"]["horizon_seconds"]
    )
    return parse_utc(activated_at) + timedelta(seconds=horizon_seconds)


def trigger_observed_price(operation: Mapping[str, Any], evidence: Mapping[str, Any]) -> float:
    market = evidence.get("market_data") or {}
    if market.get("price") is not None:
        return float(market["price"])
    if str(operation.get("side")).lower() == "long" and market.get("low") is not None:
        return float(market["low"])
    if str(operation.get("side")).lower() == "short" and market.get("high") is not None:
        return float(market["high"])
    return float(operation.get("requested_entry") or operation["entry"])


def _activation_feature_vector(
    context: Mapping[str, Any],
    *,
    activated_at: datetime,
) -> dict:
    contract = context["contract"]
    baseline = context.get("activation_baseline") or {}
    inputs = baseline.get("inputs") or {}
    probabilities = baseline.get("probabilities") or {}
    starts_at = parse_utc(contract["windows"]["activation"]["starts_at"])
    horizon = float(contract["windows"]["activation"]["horizon_seconds"])
    waited = max(0.0, (activated_at - starts_at).total_seconds())
    return {
        "baseline_p": probabilities.get("activated_by_expiry"),
        "distance_sigma": inputs.get("distance_in_horizon_sigma"),
        "wait_fraction": min(1.0, waited / horizon) if horizon > 0 else None,
    }


def _source_statuses(result: Mapping[str, Any] | None, *, historical: bool) -> dict:
    if not isinstance(result, Mapping):
        return {
            "price": "available",
            "market_history": "blocked",
            "live_context": "not_reconstructed" if historical else "blocked",
            "liquidations": "not_reconstructed" if historical else "blocked",
        }
    availability = result.get("snapshot", {}).get("availability", {})
    return {
        "price": "available",
        "market_history": "available" if availability.get("futures_klines") else "blocked",
        "live_context": "not_reconstructed" if historical else "collected",
        "liquidations": (
            "available"
            if availability.get("liquidation_heatmap")
            else ("not_reconstructed" if historical else "unavailable")
        ),
    }


def recalculate_at_activation(
    operation: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    activated_at: Any,
    activation_evidence: Mapping[str, Any],
    analyzer: Callable[..., dict] = analyze_trade,
    now: datetime | None = None,
) -> dict:
    activation_time = parse_utc(activated_at)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    historical = activation_time < current_time - timedelta(minutes=2)
    observed_price = trigger_observed_price(operation, activation_evidence)
    proposal = TradeProposal(
        symbol=str(operation["symbol"]),
        side=str(operation["side"]),
        time_horizon=str(operation["time_horizon"]),
        entry=float(operation.get("requested_entry") or operation["entry"]),
        margin=float(operation["margin"]),
        leverage=float(operation["leverage"]),
        stop_loss=float(operation["stop_loss"]),
        take_profit=float(operation["take_profit"]),
        entry_type="market",
    )
    analyzer_kwargs: dict[str, Any] = {
        "context_market_price": observed_price,
        "effective_analysis_at": activation_time,
    }
    if historical:
        # Only candles can be reconstructed at a past activation time. Using
        # today's order book, funding or liquidation map would be look-ahead.
        analyzer_kwargs["context_loader"] = lambda **_kwargs: {}
    result: dict | None = None
    try:
        result = analyzer(proposal, **analyzer_kwargs)
        post_vector = {
            "status": "evaluated",
            "engine": result.get("engine_version"),
            "tp": result.get("tp_probability"),
            "sl": result.get("sl_probability"),
            "range": result.get("range_probability"),
            "active_rules": len(
                result.get("model_trace", {}).get("active_predictive_rule_ids") or []
            ),
            "mode": "historical_reconstruction" if historical else "live_activation",
        }
        data_cutoff_at = result.get("snapshot", {}).get("data_cutoff_at") or activation_time.isoformat()
    except NewEngineAnalysisError as exc:
        post_vector = {
            "status": "blocked",
            "code": exc.code,
            "mode": "historical_reconstruction" if historical else "live_activation",
        }
        data_cutoff_at = activation_time.isoformat()
    except Exception as exc:
        post_vector = {
            "status": "blocked",
            "code": f"activation_reanalysis_{type(exc).__name__}",
            "mode": "historical_reconstruction" if historical else "live_activation",
        }
        data_cutoff_at = activation_time.isoformat()

    contract = context["contract"]
    order = contract["order"]
    starts_at = parse_utc(contract["windows"]["activation"]["starts_at"])
    return {
        "contract_version": contract["contract_version"],
        "operation_id": int(operation["id"]),
        "activated_at": activation_time.isoformat(),
        "data_cutoff_at": parse_utc(data_cutoff_at).isoformat(),
        "outcome_expires_at": outcome_expires_at(contract, activation_time).isoformat(),
        "evidence_source": str(activation_evidence.get("source") or "worker_market_path"),
        "requested_entry": float(order["requested_entry"]),
        "trigger_observed_price": observed_price,
        "simulated_fill_price": float(order["requested_entry"]),
        "seconds_to_activation": max(0.0, (activation_time - starts_at).total_seconds()),
        "activation_feature_vector": _activation_feature_vector(
            context,
            activated_at=activation_time,
        ),
        "post_activation_feature_vector": post_vector,
        "source_statuses": _source_statuses(result, historical=historical),
    }


def directional_excursions(
    operation: Mapping[str, Any],
    market_klines: list[list] | None,
    *,
    until: Any,
    close_price: float | None,
) -> tuple[float | None, float | None]:
    entry = float(operation["entry"])
    side_multiplier = -1.0 if str(operation["side"]).lower() == "short" else 1.0
    started_ms = int(parse_utc(operation.get("triggered_at") or operation.get("started_at")).timestamp() * 1000)
    until_ms = int(parse_utc(until).timestamp() * 1000)
    variations: list[float] = []
    for row in market_klines or []:
        if int(row[0]) < started_ms or int(row[6]) > until_ms:
            continue
        for price in (float(row[2]), float(row[3])):
            variations.append(((price - entry) / entry) * side_multiplier)
    if close_price is not None:
        variations.append(((float(close_price) - entry) / entry) * side_multiplier)
    if not variations:
        return None, None
    return round(max(variations) * 100.0, 6), round(min(variations) * 100.0, 6)


def closure_snapshot_values(
    operation: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    closed_at: Any,
    terminal_event: str,
    evidence_source: str,
    close_price: float | None,
    pnl: float,
    market_klines: list[list] | None = None,
) -> dict:
    close_time = parse_utc(closed_at)
    activated_raw = operation.get("triggered_at") or operation.get("started_at")
    activated_at = parse_utc(activated_raw) if activated_raw else None
    seconds = (
        max(0.0, (close_time - activated_at).total_seconds())
        if activated_at is not None
        else None
    )
    mfe, mae = directional_excursions(
        operation,
        market_klines,
        until=close_time,
        close_price=close_price,
    ) if activated_at is not None else (None, None)
    entry = float(operation.get("entry") or 0)
    stop = float(operation.get("stop_loss") or 0)
    initial_risk = abs(entry - stop) * float(operation.get("margin") or 0) * float(operation.get("leverage") or 0) / entry if entry > 0 else 0
    label = learning_label_for_terminal_event(terminal_event)
    return {
        "contract_version": context["contract"]["contract_version"],
        "operation_id": int(operation["id"]),
        "closed_at": close_time.isoformat(),
        "terminal_event": terminal_event,
        "learning_label": label,
        "evidence_source": evidence_source,
        "close_price": float(close_price) if close_price is not None else None,
        "seconds_from_activation": seconds,
        "mfe_pct": mfe,
        "mae_pct": mae,
        "economic_result": {
            "pnl": float(pnl),
            "r_multiple": float(pnl) / initial_risk if initial_risk > 0 else None,
        },
    }


def finite_price(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if math.isfinite(parsed) and parsed > 0 else fallback


__all__ = (
    "LIMIT_LIFECYCLE_RUNTIME_VERSION",
    "activation_expires_at",
    "closure_snapshot_values",
    "extract_limit_context",
    "finite_price",
    "outcome_expires_at",
    "parse_utc",
    "recalculate_at_activation",
    "trigger_observed_price",
)
