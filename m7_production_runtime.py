from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from data_quality_gate import validate_pretrade_candles
from m7_joint_temporal_engine import (
    ENGINE_VERSION,
    HORIZON_LABELS,
    HORIZON_SECONDS,
    REFERENCE_HORIZON_SECONDS,
    canonical_sha256,
    joint_temporal_probabilities,
    load_production_artifact,
    select_horizon,
)
from versioning import PROSPECTIVE_RUNTIME_VERSION


REFERENCE_INTERVAL_SECONDS = 60 * 60
REFERENCE_INTERVAL = "1h"
REFERENCE_RETURN_COUNT = REFERENCE_HORIZON_SECONDS // REFERENCE_INTERVAL_SECONDS
REFERENCE_WINDOW_COUNT = 60
REQUIRED_RETURNS = (REFERENCE_WINDOW_COUNT + 1) * REFERENCE_RETURN_COUNT


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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


def kline_fingerprint(candles: list[dict]) -> str | None:
    if not candles:
        return None
    return _payload_sha256(
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


def build_plan(proposal: Any, snapshot: dict) -> dict:
    analysis_at = str(snapshot["analysis_at"])
    horizon_seconds = int(snapshot["evaluation_horizon_seconds"])
    time_horizon = str(proposal.time_horizon)
    if HORIZON_SECONDS.get(time_horizon) != horizon_seconds:
        raise ValueError("selected_horizon_contract_invalid")
    expires_at = snapshot.get("evaluation_expires_at")
    if not expires_at:
        parsed = datetime.fromisoformat(analysis_at.replace("Z", "+00:00"))
        expires_at = datetime.fromtimestamp(
            parsed.timestamp() + horizon_seconds,
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
        "horizon_seconds": horizon_seconds,
        "analysis_at": analysis_at,
        "evaluation_expires_at": str(expires_at),
    }


def _market_material(plan: dict, candles: list[dict]) -> dict:
    analysis_at = parse_utc(plan["analysis_at"])
    if analysis_at is None:
        raise ValueError("analysis_timestamp_invalid")
    analysis_ms = int(analysis_at.timestamp() * 1000)
    quality = validate_pretrade_candles(
        candles,
        analysis_at=plan["analysis_at"],
        analysis_at_ms=analysis_ms,
        interval_seconds=REFERENCE_INTERVAL_SECONDS,
        required_candle_count=REQUIRED_RETURNS + 1,
    )
    selected = quality.pop("selected_candles")
    closes = [float(row["close"]) for row in selected]
    returns = _returns(closes)
    current = returns[-REFERENCE_RETURN_COUNT:]
    current_bars = selected[-REFERENCE_RETURN_COUNT:]
    variance = math.fsum(value * value for value in current)
    if not math.isfinite(variance) or variance <= 0:
        raise ValueError("reference_realized_volatility_invalid")
    reference = [
        math.fsum(
            value * value
            for value in returns[index : index + REFERENCE_RETURN_COUNT]
        )
        for index in range(
            0,
            REFERENCE_WINDOW_COUNT * REFERENCE_RETURN_COUNT,
            REFERENCE_RETURN_COUNT,
        )
    ]
    direction = 1.0 if plan["side"] == "long" else -1.0
    target_extreme = (
        max(float(row["high"]) for row in current_bars)
        if direction > 0
        else min(float(row["low"]) for row in current_bars)
    )
    target_between = (
        plan["entry"] < target_extreme < plan["take_profit"]
        if direction > 0
        else plan["take_profit"] < target_extreme < plan["entry"]
    )
    features = {
        "directional_path_efficiency_h": direction
        * _signed_efficiency(returns[-REFERENCE_RETURN_COUNT:]),
        "directional_path_efficiency_2h": direction
        * _signed_efficiency(returns[-2 * REFERENCE_RETURN_COUNT:]),
        "directional_path_efficiency_4h": direction
        * _signed_efficiency(returns[-4 * REFERENCE_RETURN_COUNT:]),
        "volatility_percentile_60": _midrank(variance, reference),
        "target_extreme_between_entry_and_tp": 1.0 if target_between else 0.0,
    }
    return {
        "reference_sigma_24h": math.sqrt(variance),
        "feature_values": features,
        "data_cutoff_at_ms": int(selected[-1]["close_time_ms"]),
        "data_sha256": kline_fingerprint(selected),
        "data_quality": quality,
    }


def _blocked(
    *,
    analysis_id: str,
    plan: dict,
    code: str,
    details: dict | None = None,
) -> dict:
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "analysis_id": analysis_id,
        "status": "blocked",
        "block_code": code,
        "plan": plan,
        "feature_snapshot": {},
        "probability_result": None,
        "data_cutoff_at": None,
        "source_data_sha256": None,
        "details": details or {},
        "production_effect": "none",
        "analysis_engine_execution_count": 0,
        "executed_analysis_engines": [],
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
    start_ms = (
        analysis_ms
        - (REQUIRED_RETURNS + 2) * REFERENCE_INTERVAL_SECONDS * 1000
    )
    try:
        raw = fetch_klines_range(
            plan["symbol"],
            REFERENCE_INTERVAL,
            start_ms,
            analysis_ms,
            loader=loader,
        )
        candles = [normalize_kline(row) for row in raw]
        material = _market_material(plan, candles)
        artifact = load_production_artifact()
        probability_result = joint_temporal_probabilities(
            side=plan["side"],
            entry=plan["entry"],
            take_profit=plan["take_profit"],
            stop_loss=plan["stop_loss"],
            reference_sigma_24h=material["reference_sigma_24h"],
            feature_values=material["feature_values"],
            artifact=artifact,
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        details = {"exception_type": type(exc).__name__}
        report = getattr(exc, "report", None)
        if isinstance(report, dict):
            details["data_quality"] = report
        return _blocked(
            analysis_id=analysis_id,
            plan=plan,
            code=str(exc) or "m7_calculation_blocked",
            details=details,
        )

    selected = select_horizon(probability_result, plan["time_horizon"])
    resolution = selected["tp_first_within_horizon"] + selected[
        "sl_first_within_horizon"
    ]
    full_curve_result_sha256 = probability_result["result_sha256"]
    probability_result = {
        **probability_result,
        "time_horizon": plan["time_horizon"],
        "horizon_seconds": plan["horizon_seconds"],
        "horizon_label": HORIZON_LABELS[plan["time_horizon"]],
        "probabilities": selected,
        "decision_probabilities": {
            "tp_before_sl_within_horizon": selected[
                "tp_first_within_horizon"
            ],
            "sl_before_tp_within_horizon": selected[
                "sl_first_within_horizon"
            ],
            "neither_before_expiry": selected[
                "neither_barrier_before_expiry"
            ],
            "resolution_within_horizon": resolution,
            "tp_given_resolution": (
                selected["tp_first_within_horizon"] / resolution
                if resolution > 0
                else 0.5
            ),
        },
    }
    # The complete 42-step diagnostic is useful to build the frozen artifact,
    # but production only stores the three cumulative reads to limit volume.
    probability_result.pop("interval_trace", None)
    probability_result["full_curve_result_sha256"] = full_curve_result_sha256
    probability_result.pop("result_sha256", None)
    probability_result["result_sha256"] = canonical_sha256(probability_result)
    data_cutoff_at = datetime.fromtimestamp(
        material["data_cutoff_at_ms"] / 1000,
        tz=timezone.utc,
    ).isoformat()
    feature_snapshot = {
        "status": "evaluated",
        "reference_window": "24h",
        "reference_interval_seconds": REFERENCE_INTERVAL_SECONDS,
        "values": material["feature_values"],
        "standardized_values": probability_result["standardized_features"],
        "coefficient_artifact_id": artifact["artifact_id"],
        "coefficient_artifact_sha256": artifact["artifact_sha256"],
        "validated_nonzero_directional_rule_count": sum(
            any(
                float(artifact["coefficients"][cause][name]) != 0.0
                for cause in ("tp", "sl")
            )
            for name in material["feature_values"]
        ),
        "data_cutoff_at": data_cutoff_at,
        "pretrade_candle_sha256": material["data_sha256"],
        "data_quality": material["data_quality"],
    }
    selected_sigma = material["reference_sigma_24h"] * math.sqrt(
        plan["horizon_seconds"] / REFERENCE_HORIZON_SECONDS
    )
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "analysis_id": analysis_id,
        "status": "evaluated",
        "block_code": None,
        "plan": plan,
        "feature_snapshot": feature_snapshot,
        "probability_result": probability_result,
        "data_quality": material["data_quality"],
        "data_cutoff_at": data_cutoff_at,
        "source_data_sha256": material["data_sha256"],
        "reference_sigma_24h": material["reference_sigma_24h"],
        "horizon_volatility": selected_sigma,
        "details": {
            "artifact_id": artifact["artifact_id"],
            "artifact_sha256": artifact["artifact_sha256"],
            "weights_decision": artifact["selection"]["weights_decision"],
            "single_engine": True,
        },
        "production_effect": "served",
        "analysis_engine_execution_count": 1,
        "executed_analysis_engines": [ENGINE_VERSION],
    }


__all__ = (
    "REFERENCE_INTERVAL_SECONDS",
    "build_plan",
    "build_production_probability_run",
)
