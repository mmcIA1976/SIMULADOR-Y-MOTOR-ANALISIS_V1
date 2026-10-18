"""Entry-only safety policy. Never edits forecasts, sizing or existing trades.

BTC plus >= 2/3 of the scanner universe defines recent market direction.
This is an observed-context veto, NOT a validated directional prediction.
All evidence is bounded; candles already loaded by the scan stay in memory.
"""
from __future__ import annotations

import math

VERSION = "market-losing-exposure-guard-v2-common-context"
# Freeze the existing recent-context scales in this production policy; do not
# import the unpublished research evaluator just to obtain its constants.
# NEVER choose a scale by bot horizon.
# Minutes detect a reversal; the hour describes recent movement. Opposing
# recent readings defer added losing exposure rather than averaging it away.
# 4h/24h explain background only; they cannot cancel a recent adverse movement.
RECENT_WINDOWS = ("15m", "1h")
CONTEXT_WINDOWS = ("4h", "24h")
INTERVAL_MS = 300_000
WINDOWS = {"15m": 3, "1h": 12, "4h": 48, "24h": 288}
REQUIRED_CANDLES = max(WINDOWS.values()) + 1
MAX_CONTEXT_AGE_SECONDS = 300
MAX_BOOK_GROUPS = 64


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def capture_context(materials, symbols, at):
    """Same 5m source and all scales for every bot; no horizon argument."""
    now_ms = int(at.timestamp() * 1000)
    anchors, missing = {}, []
    for symbol in symbols:
        try:
            material = materials[symbol]
            interval = int(material["interval_seconds"]) * 1000
            if interval != INTERVAL_MS:
                raise ValueError("invalid_interval")
            rows = material["selected"][-REQUIRED_CANDLES:]
            if len(rows) != REQUIRED_CANDLES:
                raise ValueError("insufficient_candles")
            times = [int(r["close_time_ms"]) for r in rows]
            closes = [positive(r["close"]) for r in rows]
            if (any(v is None for v in closes)
                    or not 0 <= now_ms - times[-1] <= interval + 1000
                    or any(b - a != interval for a, b in zip(times, times[1:]))):
                raise ValueError("invalid_candles")
            anchors[symbol] = {"prices": {name: closes[-count - 1] for name, count in WINDOWS.items()},
                               "last_closed_at_ms": times[-1]}
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
            missing.append(symbol)
    return {"version": VERSION, "captured_at_ms": now_ms, "interval_seconds": INTERVAL_MS // 1000,
            "anchors": anchors, "missing": missing, "symbols": list(symbols)}


def market_state(context, prices, at):
    now_ms = int(at.timestamp() * 1000)
    symbols = context.get("symbols", [])
    age = (now_ms - context.get("captured_at_ms", 0)) / 1000
    cutoffs = {a["last_closed_at_ms"] for a in context.get("anchors", {}).values()}
    usable = (context.get("version") == VERSION and bool(symbols)
              and "BTCUSDT" in symbols and not context.get("missing")
              and len(cutoffs) == 1 and 0 <= age <= MAX_CONTEXT_AGE_SECONDS)
    cutoff = next(iter(cutoffs)) if len(cutoffs) == 1 else None
    windows = {}
    for name, count in WINDOWS.items():
        returns, bases = {}, {}
        for symbol in symbols:
            anchor = context.get("anchors", {}).get(symbol, {})
            base = positive(anchor.get("prices", {}).get(name))
            price = positive(prices.get(symbol))
            if base and price:
                change = price / base - 1
                if math.isfinite(change):
                    returns[symbol], bases[symbol] = change, base
        up = sum(r > 1e-12 for r in returns.values())
        down = sum(r < -1e-12 for r in returns.values())
        direction = "unknown"
        if usable and len(returns) == len(symbols):
            breadth = math.ceil(2 * len(symbols) / 3)
            direction = ("bearish" if returns["BTCUSDT"] < -1e-12 and down >= breadth
                         else "bullish" if returns["BTCUSDT"] > 1e-12 and up >= breadth
                         else "mixed")
        windows[name] = {"direction": direction, "up": up, "down": down,
                         "role": "recent_veto" if name in RECENT_WINDOWS else "background_only",
                         "anchor_at_ms": cutoff - count * INTERVAL_MS if cutoff is not None else None,
                         "anchor_prices": bases, "returns": {s: round(r, 10) for s, r in returns.items()}}
    recent = {windows[name]["direction"] for name in RECENT_WINDOWS}
    direction = ("unknown" if "unknown" in recent else "conflict"
                 if {"bullish", "bearish"} <= recent else "bearish" if "bearish" in recent
                 else "bullish" if "bullish" in recent else "mixed")
    return {"direction": direction, "windows": windows,
            "context_age_seconds": round(age, 3), "last_closed_at_ms": cutoff,
            "source_interval_seconds": INTERVAL_MS // 1000}


def read_book(db, user_id, season_id):
    """Aggregate on indexed owner/season/status, not one transfer per trade."""
    rows = db.execute("""
        SELECT symbol, side, COUNT(*) AS open_count,
               MIN(entry) AS min_entry, MAX(entry) AS max_entry,
               SUM(CASE WHEN entry > 0 AND margin > 0 AND leverage > 0
                        THEN margin * leverage ELSE 0 END) AS notional,
               SUM(CASE WHEN entry > 0 AND margin > 0 AND leverage > 0
                        THEN margin * leverage / entry ELSE 0 END) AS units,
               SUM(CASE WHEN entry > 0 AND margin > 0 AND leverage > 0
                        THEN 0 ELSE 1 END) AS invalid_count
        FROM operations
        WHERE user_id = ? AND mode = 'contest' AND contest_season_id = ?
          AND status = 'OPEN'
        GROUP BY symbol, side
        ORDER BY symbol, side
        LIMIT 65
    """, (int(user_id), int(season_id))).fetchall()
    if len(rows) > MAX_BOOK_GROUPS:
        raise ValueError("entry_guard_book_group_budget_exceeded")
    return [dict(row) for row in rows]


def assess(context, book, prices, at):
    market = market_state(context, prices, at)
    direction = market["direction"]
    states = {side: {"open_count": 0, "losing_groups": 0, "unknown_groups": 0,
                     "gross_pnl": 0.0} for side in ("long", "short")}
    groups = []
    for row in book:
        side = str(row["side"]).lower()
        if side not in states:
            raise ValueError("entry_guard_unknown_position_side")
        state = states[side]
        state["open_count"] += int(row["open_count"])
        mark = positive(prices.get(row["symbol"]))
        low, high = positive(row["min_entry"]), positive(row["max_entry"])
        notional, units = positive(row["notional"]), positive(row["units"])
        known = bool(mark and low and high and notional and units and not row["invalid_count"])
        losing = bool(known and (mark < high if side == "long" else mark > low))
        pnl = ((mark * units - notional) * (1 if side == "long" else -1)) if known else None
        state["losing_groups"] += int(losing)
        state["unknown_groups"] += int(not known)
        if pnl is not None:
            state["gross_pnl"] += pnl
        groups.append({"symbol": row["symbol"], "side": side, "count": int(row["open_count"]),
                       "min_entry": low, "max_entry": high, "mark": mark,
                       "has_loss": losing if known else None})
    decisions = {}
    for side, state in states.items():
        adverse = direction == ("bearish" if side == "long" else "bullish")
        status, reason = "allowed", "market_exposure_guard_passed"
        at_risk = state["losing_groups"] or state["unknown_groups"]
        if adverse and state["losing_groups"]:
            status, reason = "blocked", "market_against_losing_" + side + "_exposure"
        elif at_risk and direction == "conflict":
            status, reason = "deferred", "market_recent_conflict_with_losing_exposure"
        elif at_risk and (direction == "unknown" or (adverse and state["unknown_groups"])):
            status, reason = "deferred", "market_exposure_guard_data_unavailable"
        decisions[side] = {"status": status, "reason": reason}
        state["gross_pnl"] = round(state["gross_pnl"], 6) if not state["unknown_groups"] else None
    return {"version": VERSION, "checked_at": at.isoformat(),
            "market": market,
            "book": states, "groups": groups, "decisions": decisions}


def unavailable(at):
    return {"version": VERSION, "checked_at": at.isoformat(), "market": {"direction": "unknown"},
            "decisions": {s: {"status": "deferred", "reason": "market_exposure_guard_data_unavailable"}
                          for s in ("long", "short")}}


def apply(candidates, evidence, context):
    for candidate in candidates:
        old = candidate.entry_guard
        if old.get("status") in {"blocked", "deferred"} and candidate.rejection_code == old.get("reason"):
            candidate.rejection_code = None
        candidate.entry_guard = dict(evidence["decisions"][candidate.side])
        candidate.market_guard_context = context
        candidate.market_guard_evidence = evidence
        if candidate.entry_guard["status"] != "allowed" and candidate.rejection_code is None:
            candidate.rejection_code = candidate.entry_guard["reason"]
