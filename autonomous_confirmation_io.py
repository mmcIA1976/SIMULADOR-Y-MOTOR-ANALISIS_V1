"""Bounded confirmation I/O; no forecast, risk, or sizing policy changes."""
from __future__ import annotations

import math
import time

from binance_request_budget import BinanceDeferred

VERSION = "autonomous-confirmation-io-v1"
MAX_RETRIES = 2
MAX_TOTAL_WAIT_SECONDS = 130.0
MAX_PANEL_AGE_SECONDS = 180.0
INTERVAL_MS = {"5m": 300_000, "1h": 3_600_000, "6h": 21_600_000}


def closed_request_key(symbol, interval, limit, start, end):
    """Same closed candle range => same key, even when seconds have changed.

    Round start UP (Binance selects by open time); discard only the forming
    candle at the end. Crossing a candle close necessarily changes the key.
    Unbounded/unsupported requests retain their original semantics.
    """
    key = (str(symbol).upper(), str(interval), int(limit),
           int(start) if start is not None else None,
           int(end) if end is not None else None)
    step = INTERVAL_MS.get(key[1])
    if step and key[3] is not None and key[4] is not None:
        first = -(-key[3] // step) * step
        last = ((key[4] + 1) // step) * step - 1
        if first <= last:
            return (*key[:3], first, last)
    return key


def deferred_seconds(exc):
    """Retry only explicit provider deferrals, not forecast/data-quality errors."""
    current = exc
    for _ in range(5):
        if isinstance(current, BinanceDeferred):
            value = current.retry_after_seconds
            break
        details = getattr(current, "details", {})
        if isinstance(details, dict) and (details.get("provider_deferred")
                or details.get("exception_type") == "BinanceDeferred"):
            value = details.get("retry_after_seconds")
            break
        current = getattr(current, "__cause__", None)
        if current is None:
            return None
    else:
        return None
    try:
        seconds = float(value) if value is not None else 65.0
    except (TypeError, ValueError):
        return None
    return max(2.0, seconds) if math.isfinite(seconds) and seconds >= 0 else None


def wait_for_retry(seconds):
    time.sleep(seconds)
    return False


def confirm_with_retry(attempt, *, clock, wait, cache, panel_at):
    """Wait outside DB transactions, in the scanner thread only.

    `wait` can be stop_event.wait, so deployment/shutdown cancels promptly.
    Each attempt must read a fresh worker quote and run the ordinary analysis.
    """
    evidence = {"version": VERSION, "attempts": 0, "wait_seconds": 0.0,
                "deferrals": [], "stop_reason": None}
    result = attempt(clock())
    evidence["attempts"] += 1
    for retry in range(MAX_RETRIES + 1):
        delay = result.data_retry_seconds
        if delay is None:
            break
        evidence["deferrals"].append({"at": result.analyzed_at.isoformat(),
                                      "reason": result.rejection_code,
                                      "retry_after_seconds": delay})
        age = (clock() - panel_at).total_seconds()
        if (retry >= MAX_RETRIES or not math.isfinite(delay) or delay < 0
                or evidence["wait_seconds"] + delay > MAX_TOTAL_WAIT_SECONDS
                or age < 0 or age + delay > MAX_PANEL_AGE_SECONDS):
            evidence["stop_reason"] = "confirmation_retry_budget_exhausted"
            break
        if wait(delay):
            evidence["stop_reason"] = "confirmation_retry_interrupted"
            break
        evidence["wait_seconds"] += delay
        at = clock()
        if not 0 <= (at - panel_at).total_seconds() <= MAX_PANEL_AGE_SECONDS:
            evidence["stop_reason"] = "confirmation_retry_panel_expired"
            break
        # Release local negative cache only after waiting. The provider's shared
        # quota/circuit still decides whether an upstream call may be sent.
        cache.resume_deferred()
        result = attempt(at)
        evidence["attempts"] += 1
    return result, evidence
