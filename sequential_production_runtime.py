from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from multiscale_feature_runtime import (
    STAGE_PROFILES,
    build_stage_context,
    required_candle_count,
)
from empirical_temporal_engine import (
    ENGINE_VERSION,
    empirical_probabilities,
    selected_stage_order,
)
from versioning import PROSPECTIVE_RUNTIME_VERSION


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_utc(value: Any) -> datetime | None:
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


def fetch_klines_range(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
) -> list[list]:
    rows: dict[int, list] = {}
    cursor = int(start_ms)
    while cursor <= end_ms:
        batch = loader(
            symbol,
            interval,
            1500,
            start_time_ms=cursor,
            end_time_ms=end_ms,
        )
        if not batch:
            break
        for raw in batch:
            if not isinstance(raw, (list, tuple)) or len(raw) < 7:
                continue
            rows[int(raw[0])] = list(raw)
        next_cursor = int(batch[-1][0]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("non_advancing_kline_cursor")
        cursor = next_cursor
        if len(batch) < 1500:
            break
    return [rows[key] for key in sorted(rows)]


def normalize_kline(raw: list) -> dict:
    normalized = {
        "open_time_ms": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_time_ms": int(raw[6]),
    }
    if len(raw) > 7:
        normalized["quote_volume"] = float(raw[7])
    if len(raw) > 9:
        normalized["taker_buy_base_volume"] = float(raw[9])
    if len(raw) > 10:
        normalized["taker_buy_quote_volume"] = float(raw[10])
    return normalized


def build_plan(proposal: Any, snapshot: dict) -> dict:
    time_horizon = str(proposal.time_horizon)
    horizons = selected_stage_order(time_horizon)
    analysis_at = str(snapshot["analysis_at"])
    expires_at = snapshot.get("evaluation_expires_at")
    if not expires_at:
        parsed = datetime.fromisoformat(analysis_at.replace("Z", "+00:00"))
        expires_at = datetime.fromtimestamp(
            parsed.timestamp() + STAGE_PROFILES[time_horizon]["horizon_seconds"],
            tz=timezone.utc,
        ).isoformat()
    return {
        "symbol": str(proposal.symbol).upper(),
        "side": str(proposal.side).lower(),
        "entry": float(proposal.entry),
        "margin": float(proposal.margin),
        "leverage": float(proposal.leverage),
        "take_profit": float(proposal.take_profit),
        "stop_loss": float(proposal.stop_loss),
        "entry_type": str(getattr(proposal, "entry_type", "market")).lower(),
        "time_horizon": time_horizon,
        "horizon_seconds": int(
            STAGE_PROFILES[time_horizon]["horizon_seconds"]
        ),
        "required_stages": list(horizons),
        "analysis_at": analysis_at,
        "evaluation_expires_at": str(expires_at),
    }


def _blocked(
    *, analysis_id: str, plan: dict, code: str, details: dict | None = None
) -> dict:
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "analysis_id": analysis_id,
        "status": "blocked",
        "block_code": code,
        "plan": plan,
        "stage_contexts": {},
        "probability_result": None,
        "data_cutoff_at": None,
        "source_data_sha256": None,
        "details": details or {},
        "production_effect": "none",
        "analysis_engine_execution_count": 0,
        "executed_analysis_engines": [],
    }


def _stage_plan(plan: dict, horizon: str) -> dict:
    profile = STAGE_PROFILES[horizon]
    return {
        **plan,
        "time_horizon": horizon,
        "horizon_seconds": int(profile["horizon_seconds"]),
    }


def build_production_probability_run(
    proposal: Any,
    snapshot: dict,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
    analysis_id: str,
) -> dict:
    plan = build_plan(proposal, snapshot)
    if plan["entry_type"] != "market":
        return _blocked(
            analysis_id=analysis_id,
            plan=plan,
            code="market_entry_required",
        )
    analysis_at = parse_utc(plan["analysis_at"])
    if analysis_at is None:
        return _blocked(
            analysis_id=analysis_id,
            plan=plan,
            code="analysis_timestamp_invalid",
        )
    analysis_ms = int(analysis_at.timestamp() * 1000)
    stage_contexts = {}
    try:
        for horizon in plan["required_stages"]:
            profile = STAGE_PROFILES[horizon]
            count = required_candle_count(horizon)
            start_ms = analysis_ms - (count + 2) * int(
                profile["interval_seconds"]
            ) * 1000
            raw = fetch_klines_range(
                plan["symbol"],
                str(profile["interval"]),
                start_ms,
                analysis_ms,
                loader=loader,
            )
            candles = [normalize_kline(row) for row in raw]
            stage_contexts[horizon] = build_stage_context(
                _stage_plan(plan, horizon), candles
            )
        probability_result = empirical_probabilities(
            symbol=plan["symbol"],
            side=plan["side"],
            entry=plan["entry"],
            take_profit=plan["take_profit"],
            stop_loss=plan["stop_loss"],
            time_horizon=plan["time_horizon"],
            stage_contexts=stage_contexts,
            analysis_at=plan["analysis_at"],
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        details = {
            "exception_type": type(exc).__name__,
            "completed_stages": list(stage_contexts),
        }
        report = getattr(exc, "report", None)
        if isinstance(report, dict):
            details["data_quality"] = report
        return _blocked(
            analysis_id=analysis_id,
            plan=plan,
            code=str(exc) or "sequential_calculation_blocked",
            details=details,
        )
    cutoff_ms = min(
        int(context["data_cutoff_at_ms"]) for context in stage_contexts.values()
    )
    data_cutoff_at = datetime.fromtimestamp(
        cutoff_ms / 1000, tz=timezone.utc
    ).isoformat()
    source_hashes = {
        horizon: context["source_data_sha256"]
        for horizon, context in stage_contexts.items()
    }
    compact_contexts = {
        horizon: {
            key: value
            for key, value in context.items()
            if key != "rule_traces"
        }
        for horizon, context in stage_contexts.items()
    }
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "analysis_id": analysis_id,
        "status": "evaluated",
        "block_code": None,
        "plan": plan,
        "stage_contexts": compact_contexts,
        "stage_rule_traces": {
            horizon: context["rule_traces"]
            for horizon, context in stage_contexts.items()
        },
        "probability_result": probability_result,
        "data_cutoff_at": data_cutoff_at,
        "source_data_sha256": _canonical_sha256(source_hashes),
        "source_data_sha256_by_stage": source_hashes,
        "horizon_volatility": stage_contexts[plan["time_horizon"]][
            "context_sigma"
        ],
        "details": {
            "single_engine": True,
            "stage_count": len(stage_contexts),
            "stage_order": list(stage_contexts),
        },
        "production_effect": "served",
        "analysis_engine_execution_count": 1,
        "executed_analysis_engines": [ENGINE_VERSION],
    }


__all__ = (
    "build_plan",
    "build_production_probability_run",
    "fetch_klines_range",
    "normalize_kline",
    "parse_utc",
)
