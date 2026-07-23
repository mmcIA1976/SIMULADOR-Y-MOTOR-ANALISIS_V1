from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

from versioning import EVIDENCE_RECONSTRUCTION_VERSION


ONE_MINUTE_MS = 60_000
AGG_TRADES_RETENTION_MS = 24 * 60 * ONE_MINUTE_MS
EVIDENCE_SOURCE = "binance_usdm_futures_klines_1m"
AGG_TRADE_SOURCE = "binance_usdm_futures_agg_trades"


def parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_ms(value) -> int | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return int(parsed.timestamp() * 1000)


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def reconstruction_window(operation: dict) -> dict:
    start_ms = timestamp_ms(operation.get("started_at"))
    recorded_close_ms = timestamp_ms(operation.get("closed_at"))
    close_ms = recorded_close_ms
    raw_exit_evidence = operation.get("exit_evidence_json")
    if isinstance(raw_exit_evidence, str):
        try:
            exit_evidence = json.loads(raw_exit_evidence)
        except json.JSONDecodeError:
            exit_evidence = {}
    elif isinstance(raw_exit_evidence, dict):
        exit_evidence = raw_exit_evidence
    else:
        exit_evidence = {}
    source = str(exit_evidence.get("source") or "")
    market_payload = exit_evidence.get("market_data")
    if source.endswith("1m_kline") and isinstance(market_payload, dict):
        evidence_close_ms = timestamp_ms(market_payload.get("close_time"))
        if evidence_close_ms is not None:
            close_ms = evidence_close_ms
    plan_end_ms = close_ms
    if (
        operation.get("close_reason") not in {"take_profit", "stop_loss"}
        and operation.get("observation_until")
    ):
        plan_end_ms = timestamp_ms(operation.get("observation_until")) or close_ms
    return {
        "start_ms": start_ms,
        "close_ms": close_ms,
        "recorded_close_ms": recorded_close_ms,
        "plan_end_ms": plan_end_ms,
    }


def normalize_klines(raw_klines: list[list], start_ms: int, end_ms: int) -> list[dict]:
    normalized: dict[int, dict] = {}
    for raw in raw_klines:
        if not isinstance(raw, (list, tuple)) or len(raw) < 7:
            continue
        try:
            candle = {
                "open_time_ms": int(raw[0]),
                "open": float(raw[1]),
                "high": float(raw[2]),
                "low": float(raw[3]),
                "close": float(raw[4]),
                "volume": float(raw[5]),
                "close_time_ms": int(raw[6]),
            }
        except (TypeError, ValueError):
            continue
        if candle["close_time_ms"] < start_ms or candle["open_time_ms"] > end_ms:
            continue
        normalized[candle["open_time_ms"]] = candle
    return [normalized[key] for key in sorted(normalized)]


def expected_candle_count(start_ms: int, end_ms: int) -> int:
    if end_ms < start_ms:
        return 0
    return (end_ms // ONE_MINUTE_MS) - (start_ms // ONE_MINUTE_MS) + 1


def evidence_quality(start_ms: int, end_ms: int, candle_count: int, expected_count: int) -> str:
    if candle_count == 0 or expected_count == 0:
        return "unavailable"
    coverage = candle_count / expected_count
    if coverage < 0.98:
        return "partial_1m"
    start_aligned = start_ms % ONE_MINUTE_MS == 0
    end_aligned = end_ms % ONE_MINUTE_MS in {0, ONE_MINUTE_MS - 1}
    if start_aligned and end_aligned:
        return "complete_1m"
    return "complete_1m_with_boundary_approximation"


def candles_for_window(candles: list[dict], start_ms: int, end_ms: int) -> list[dict]:
    return [
        candle
        for candle in candles
        if candle["close_time_ms"] >= start_ms and candle["open_time_ms"] <= end_ms
    ]


def excursion_metrics(operation: dict, candles: list[dict]) -> dict:
    if not candles:
        return {
            "max_favorable_pct": None,
            "max_adverse_pct": None,
            "max_favorable_pnl": None,
            "max_adverse_pnl": None,
        }
    entry = float(operation["entry"])
    margin = float(operation["margin"])
    leverage = float(operation["leverage"])
    if operation["side"] == "short":
        favorable = max(0.0, (entry - min(item["low"] for item in candles)) / entry)
        adverse = min(0.0, (entry - max(item["high"] for item in candles)) / entry)
    else:
        favorable = max(0.0, (max(item["high"] for item in candles) - entry) / entry)
        adverse = min(0.0, (min(item["low"] for item in candles) - entry) / entry)
    return {
        "max_favorable_pct": round(favorable * 100, 4),
        "max_adverse_pct": round(adverse * 100, 4),
        "max_favorable_pnl": round(margin * leverage * favorable, 4),
        "max_adverse_pnl": round(margin * leverage * adverse, 4),
    }


def candle_hits(operation: dict, candle: dict) -> tuple[bool, bool]:
    stop_loss = float(operation["stop_loss"])
    take_profit = float(operation["take_profit"])
    if operation["side"] == "short":
        return candle["high"] >= stop_loss, candle["low"] <= take_profit
    return candle["low"] <= stop_loss, candle["high"] >= take_profit


def price_touch_reason(operation: dict, price: float) -> str | None:
    if operation["side"] == "short":
        if price >= float(operation["stop_loss"]):
            return "stop_loss"
        if price <= float(operation["take_profit"]):
            return "take_profit"
    else:
        if price <= float(operation["stop_loss"]):
            return "stop_loss"
        if price >= float(operation["take_profit"]):
            return "take_profit"
    return None


def resolve_touch_with_trades(
    operation: dict,
    start_ms: int,
    end_ms: int,
    trade_loader: Callable[[int, int], list[dict]] | None,
) -> dict | None:
    if trade_loader is None:
        return None
    try:
        trades = trade_loader(start_ms, end_ms)
    except Exception:
        return None
    ordered = sorted(
        (trade for trade in trades if isinstance(trade, dict)),
        key=lambda item: int(item.get("T", start_ms)),
    )
    for trade in ordered:
        try:
            trade_time_ms = int(trade.get("T", start_ms))
            price = float(trade["p"])
        except (KeyError, TypeError, ValueError):
            continue
        if trade_time_ms < start_ms or trade_time_ms > end_ms:
            continue
        reason = price_touch_reason(operation, price)
        if reason:
            return {
                "status": "resolved",
                "reason": reason,
                "price": float(operation[reason]),
                "touched_at": iso_from_ms(trade_time_ms),
                "time_precision": "aggregate_trade",
                "source": AGG_TRADE_SOURCE,
            }
    return None


def first_plan_touch(
    operation: dict,
    candles: list[dict],
    start_ms: int,
    end_ms: int,
    trade_loader: Callable[[int, int], list[dict]] | None = None,
    now_ms: int | None = None,
) -> dict:
    effective_now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    for candle in candles_for_window(candles, start_ms, end_ms):
        stop_hit, target_hit = candle_hits(operation, candle)
        if not stop_hit and not target_hit:
            continue
        exact_start = max(start_ms, candle["open_time_ms"])
        exact_end = min(end_ms, candle["close_time_ms"])
        boundary_partial = exact_start > candle["open_time_ms"] or exact_end < candle["close_time_ms"]
        trades_available = effective_now_ms - exact_end <= AGG_TRADES_RETENTION_MS
        if (stop_hit and target_hit) or boundary_partial:
            resolved = resolve_touch_with_trades(
                operation,
                exact_start,
                exact_end,
                trade_loader if trades_available else None,
            )
            if resolved:
                return resolved
            status = "ambiguous_same_candle" if stop_hit and target_hit else "ambiguous_boundary_candle"
            return {
                "status": status,
                "reason": None,
                "price": None,
                "touched_at": iso_from_ms(candle["open_time_ms"]),
                "time_precision": "minute",
                "source": EVIDENCE_SOURCE,
                "stop_hit": stop_hit,
                "target_hit": target_hit,
                "aggregate_trades_available": trades_available,
            }
        reason = "stop_loss" if stop_hit else "take_profit"
        return {
            "status": "resolved",
            "reason": reason,
            "price": float(operation[reason]),
            "touched_at": iso_from_ms(candle["open_time_ms"]),
            "time_precision": "minute",
            "source": EVIDENCE_SOURCE,
        }
    return {
        "status": "no_plan_touch",
        "reason": None,
        "price": None,
        "touched_at": None,
        "time_precision": None,
        "source": EVIDENCE_SOURCE,
    }


def recorded_result_consistency(operation: dict, first_touch: dict, post_close_touch: dict | None) -> str:
    if first_touch.get("status", "").startswith("ambiguous"):
        return "ambiguous"
    close_reason = operation.get("close_reason")
    if close_reason in {"stop_loss", "take_profit"}:
        if first_touch.get("status") != "resolved":
            return "mismatch"
        return "consistent" if first_touch.get("reason") == close_reason else "mismatch"
    observation_result = operation.get("observation_result")
    expected = None
    if observation_result in {"manual_protected", "manual_worse_than_plan"}:
        expected = "stop_loss"
    elif observation_result in {"manual_left_profit", "manual_better_than_plan"}:
        expected = "take_profit"
    elif observation_result == "plan_unresolved":
        expected = "no_plan_touch"
    if expected is None or post_close_touch is None:
        return "not_comparable"
    if post_close_touch.get("status", "").startswith("ambiguous"):
        return "ambiguous"
    reconstructed = post_close_touch.get("reason") or post_close_touch.get("status")
    return "consistent" if reconstructed == expected else "mismatch"


def reconstructed_plan_result(operation: dict, first_touch: dict, post_close_touch: dict | None) -> str:
    close_reason = operation.get("close_reason")
    if close_reason == "contest_expired":
        return "contest_expiry_mark_to_market"
    if close_reason in {"stop_loss", "take_profit"}:
        if first_touch.get("status") == "resolved":
            return "plan_success" if first_touch.get("reason") == "take_profit" else "plan_failure"
        if first_touch.get("status", "").startswith("ambiguous"):
            return "ambiguous_same_candle"
        return "plan_unresolved"
    if post_close_touch is None:
        return "manual_pending_or_unclassified"
    if post_close_touch.get("status") == "resolved":
        return "plan_would_succeed" if post_close_touch.get("reason") == "take_profit" else "plan_would_fail"
    if post_close_touch.get("status", "").startswith("ambiguous"):
        return "ambiguous_same_candle"
    return "plan_unresolved"


def candle_fingerprint(candles: list[dict]) -> str | None:
    if not candles:
        return None
    payload = [
        [
            candle["open_time_ms"],
            candle["open"],
            candle["high"],
            candle["low"],
            candle["close"],
            candle["volume"],
            candle["close_time_ms"],
        ]
        for candle in candles
    ]
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def build_historical_evidence(
    operation: dict,
    raw_klines: list[list],
    trade_loader: Callable[[int, int], list[dict]] | None = None,
    now_ms: int | None = None,
) -> dict:
    reconstructed_at = datetime.now(timezone.utc).isoformat()
    window = reconstruction_window(operation)
    start_ms = window["start_ms"]
    close_ms = window["close_ms"]
    plan_end_ms = window["plan_end_ms"]
    if start_ms is None or close_ms is None or plan_end_ms is None or close_ms < start_ms or plan_end_ms < close_ms:
        return {
            "version": EVIDENCE_RECONSTRUCTION_VERSION,
            "status": "invalid_window",
            "source": EVIDENCE_SOURCE,
            "quality": "unavailable",
            "path_resolution": "not_evaluable",
            "reconstructed_at": reconstructed_at,
            "error": "La operacion no contiene una ventana temporal valida.",
        }

    candles = normalize_klines(raw_klines, start_ms, plan_end_ms)
    expected = expected_candle_count(start_ms, plan_end_ms)
    coverage_ratio = round(len(candles) / expected, 6) if expected else 0
    quality = evidence_quality(start_ms, plan_end_ms, len(candles), expected)
    trade_candles = candles_for_window(candles, start_ms, close_ms)
    post_close_candles = (
        candles_for_window(candles, close_ms, plan_end_ms)
        if plan_end_ms > close_ms
        else []
    )
    first_touch = first_plan_touch(
        operation,
        candles,
        start_ms,
        plan_end_ms,
        trade_loader=trade_loader,
        now_ms=now_ms,
    )
    post_close_touch = (
        first_plan_touch(
            operation,
            candles,
            close_ms,
            plan_end_ms,
            trade_loader=trade_loader,
            now_ms=now_ms,
        )
        if plan_end_ms > close_ms
        else None
    )
    return {
        "version": EVIDENCE_RECONSTRUCTION_VERSION,
        "status": "complete" if quality.startswith("complete") else "partial" if candles else "unavailable",
        "source": EVIDENCE_SOURCE,
        "quality": quality,
        "path_resolution": first_touch["status"],
        "reconstructed_at": reconstructed_at,
        "requested_window": {
            "started_at": iso_from_ms(start_ms),
            "closed_at": iso_from_ms(close_ms),
            "recorded_closed_at": (
                iso_from_ms(window["recorded_close_ms"])
                if window.get("recorded_close_ms") is not None
                else None
            ),
            "plan_end_at": iso_from_ms(plan_end_ms),
        },
        "actual_window": {
            "first_candle_open_at": iso_from_ms(candles[0]["open_time_ms"]) if candles else None,
            "last_candle_close_at": iso_from_ms(candles[-1]["close_time_ms"]) if candles else None,
        },
        "candle_count": len(candles),
        "expected_candle_count": expected,
        "coverage_ratio": coverage_ratio,
        "candle_sha256": candle_fingerprint(candles),
        "trade_excursion": excursion_metrics(operation, trade_candles),
        "plan_excursion": excursion_metrics(operation, candles),
        "post_close_excursion": excursion_metrics(operation, post_close_candles),
        "first_plan_touch": first_touch,
        "first_post_close_plan_touch": post_close_touch,
        "recorded_result_consistency": recorded_result_consistency(
            operation,
            first_touch,
            post_close_touch,
        ),
        "reconstructed_plan_result": reconstructed_plan_result(
            operation,
            first_touch,
            post_close_touch,
        ),
        "limitations": [
            "Las velas de 1 minuto no ordenan maximo y minimo dentro de la misma vela.",
            "Las velas de borde pueden incluir segundos anteriores a la apertura o posteriores al cierre.",
            "Binance limita los trades agregados historicos a las ultimas 24 horas.",
        ],
    }


def apply_evidence_to_structured(structured: dict, evidence: dict) -> dict:
    updated = json.loads(json.dumps(structured))
    previous_excursion = updated.get("excursion")
    if "legacy_tick_excursion" not in updated:
        updated["legacy_tick_excursion"] = previous_excursion
    authoritative_excursion = (
        evidence.get("trade_excursion")
        if str(evidence.get("quality") or "").startswith("complete")
        else None
    )
    if authoritative_excursion:
        updated["excursion"] = authoritative_excursion
    updated["historical_evidence"] = evidence
    post_trade = updated.get("post_trade_outcomes")
    if isinstance(post_trade, dict):
        if "legacy_tick_excursion" not in post_trade:
            post_trade["legacy_tick_excursion"] = post_trade.get("excursion")
        if authoritative_excursion:
            post_trade["excursion"] = authoritative_excursion
        post_trade["historical_evidence"] = evidence
    return updated
