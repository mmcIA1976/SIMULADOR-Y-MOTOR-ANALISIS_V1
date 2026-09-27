"""Bounded four-hour proposals, not another probability engine.

Versioned pilot heuristics: trend alignment, structural invalidation and past
four-hour excursions. Their effectiveness must be measured prospectively.
All inputs are validated closed candles already loaded by the active engine.
"""
from __future__ import annotations

import hashlib
import json
import math

from structural_level_runtime import confirmed_pivots
from technical_rule_runtime import ema_series, wilder_atr


PLAN_VERSION = "short-structural-reach-plan-v1"
HORIZON_SECONDS = 14400
MIN_TP_PROBABILITY = .50
MAX_UNRESOLVED_PROBABILITY = .25
MIN_REWARD_RISK = 1.0
MIN_PATH_EFFICIENCY = .10
STOP_BUFFER_ATR = .25
TARGET_BUFFER_ATR = .15
MIN_TARGET_ATR = 2.0
TARGET_FRACTIONS = (.60, .85)
MAX_PROPOSALS_PER_SIDE = 2


class PlanRejected(ValueError):
    """Market context evaluated, but no defensible trade plan exists."""


def _efficiency(closes, length):
    values = closes[-length - 1:]
    travel = math.fsum(abs(b - a) for a, b in zip(values, values[1:]))
    return (values[-1] - values[0]) / travel if travel else 0.0


def context(material: dict, *, side: str, entry: float) -> dict:
    if side not in {"long", "short"} or not math.isfinite(entry) or entry <= 0:
        raise ValueError("short_plan_invalid_inputs")
    if int(material["return_count"]) != 48 or int(material["interval_seconds"]) != 300:
        raise ValueError("short_plan_requires_closed_5m_four_hour_material")
    rows = material["selected"]
    sign = 1 if side == "long" else -1
    closes = [float(r["close"]) for r in rows]
    fast = ema_series(closes, 20)
    slow = ema_series(closes, 50)
    efficiency_1h, efficiency_4h = _efficiency(closes, 12), _efficiency(closes, 48)
    atr = wilder_atr(rows[-200:])
    if atr <= 0 or not math.isfinite(atr):
        raise ValueError("short_plan_invalid_atr")
    if not (
        sign * efficiency_1h > 0
        and sign * efficiency_4h >= MIN_PATH_EFFICIENCY
        and sign * (fast[-1] - slow[-1]) > 0
        and sign * (fast[-1] - fast[-13]) > 0
        and sign * (entry - slow[-1]) > 0
    ):
        raise PlanRejected("short_plan_trend_not_aligned")

    # Completed, non-overlapping past windows only. The denominator is ATR
    # known at the START of each window, not volatility learned afterwards.
    excursions = []
    for start in range(48, len(rows) - 96, 48):
        baseline = float(rows[start]["close"])
        baseline_atr = wilder_atr(rows[max(0, start - 199):start + 1])
        window = rows[start + 1:start + 49]
        if baseline_atr <= 0 or len(window) != 48:
            continue
        extreme = (max(float(r["high"]) for r in window) if sign == 1
                   else min(float(r["low"]) for r in window))
        excursions.append(max(0.0, sign * (extreme - baseline)) / baseline_atr)
    if len(excursions) < 30:
        raise ValueError("short_plan_insufficient_complete_reference_windows")
    ordered = sorted(excursions)
    middle = len(ordered) // 2
    median = (ordered[middle] if len(ordered) % 2
              else (ordered[middle - 1] + ordered[middle]) / 2)
    reach = median * atr
    if reach <= 0 or not math.isfinite(reach):
        raise PlanRejected("short_plan_no_four_hour_reach")
    recent = rows[-48:]
    pivots = confirmed_pivots(recent, atr14=atr)
    anchor_type = "low" if sign == 1 else "high"
    anchors = [p for p in pivots if p["type"] == anchor_type
               and p["prominence_atr"] >= .5 and sign * (entry - p["price"]) > 0]
    if anchors:
        anchor = anchors[-1]
        anchor_price, anchor_at = float(anchor["price"]), int(anchor["pivot_close_time_ms"])
        anchor_kind = "confirmed_swing"
    else:
        # A closed one-hour support/resistance is still a price-defined
        # invalidation, never a stop moved outward to improve the forecast.
        anchor = (min(recent[-12:], key=lambda r: float(r["low"])) if sign == 1
                  else max(recent[-12:], key=lambda r: float(r["high"])))
        anchor_price = float(anchor["low"] if sign == 1 else anchor["high"])
        anchor_at, anchor_kind = int(anchor["close_time_ms"]), "closed_1h_extreme"
    stop = anchor_price - sign * STOP_BUFFER_ATR * atr
    if stop <= 0 or sign * (entry - stop) <= 0:
        raise PlanRejected("short_plan_invalidation_already_broken")
    opposition = [float(p["price"]) for p in pivots
                  if p["type"] != anchor_type and sign * (p["price"] - entry) > 0]
    obstacle = (min(opposition) if sign == 1 else max(opposition)) if opposition else None
    target_cap = reach
    if obstacle is not None:
        target_cap = min(target_cap, sign * (obstacle - entry) - TARGET_BUFFER_ATR * atr)
    return {
        "version": PLAN_VERSION, "horizon_seconds": HORIZON_SECONDS,
        "efficiency_1h": round(efficiency_1h, 6),
        "efficiency_4h": round(efficiency_4h, 6),
        "atr_5m": atr, "anchor_price": anchor_price, "anchor_at_ms": anchor_at,
        "anchor_kind": anchor_kind, "stop_loss": stop,
        "four_hour_reach": reach, "target_cap": target_cap,
        "reference_windows": len(excursions), "opposition_price": obstacle,
        "source_sha256": material["data_sha256"],
        "data_cutoff_at_ms": material["data_cutoff_at_ms"],
        "probability_effect": "none_proposal_construction_only",
    }


def proposals(material: dict, *, side: str, entry: float) -> list[dict]:
    ctx = context(material, side=side, entry=entry)
    sign = 1 if side == "long" else -1
    risk = sign * (entry - ctx["stop_loss"])
    results = []
    for fraction in TARGET_FRACTIONS:
        reward = min(fraction * ctx["four_hour_reach"], ctx["target_cap"])
        if reward < max(MIN_TARGET_ATR * ctx["atr_5m"], MIN_REWARD_RISK * risk):
            continue
        target = entry + sign * reward
        if target <= 0 or any(abs(p["take_profit"] - target) <= entry * 1e-12 for p in results):
            continue
        lineage = json.dumps([PLAN_VERSION, side, ctx["anchor_kind"], ctx["anchor_at_ms"], fraction])
        results.append({
            **ctx, "take_profit": target, "target_fraction": fraction,
            "reward_risk_ratio": reward / risk,
            "lineage_key": hashlib.sha256(lineage.encode()).hexdigest()[:16],
        })
    if not results:
        raise PlanRejected("short_plan_no_feasible_reward_risk")
    return results[:MAX_PROPOSALS_PER_SIDE]


def validate_requote(plan: dict, material: dict, *, side: str, entry: float) -> dict:
    """Reassess the SAME absolute TP/SL with a fresh entry/context."""
    ctx = context(material, side=side, entry=entry)
    sign = 1 if side == "long" else -1
    reward = sign * (float(plan["take_profit"]) - entry)
    risk = sign * (entry - float(plan["stop_loss"]))
    if risk <= 0 or reward <= 0:
        raise PlanRejected("short_plan_barrier_already_crossed")
    if reward < max(MIN_TARGET_ATR * ctx["atr_5m"], MIN_REWARD_RISK * risk):
        raise PlanRejected("short_plan_reward_risk_lost")
    if reward > ctx["target_cap"] + entry * 1e-12:
        raise PlanRejected("short_plan_target_no_longer_reachable")
    return {**plan, "reward_risk_ratio": reward / risk,
            "revalidated_source_sha256": ctx["source_sha256"]}


def passes_forecast(candidate) -> bool:
    if not getattr(candidate, "trade_plan", None):
        return True  # Older candidates/reports retain their historical contract.
    reward = abs(candidate.take_profit - candidate.entry)
    risk = abs(candidate.entry - candidate.stop_loss)
    return (candidate.tp_probability is not None and candidate.tp_probability >= MIN_TP_PROBABILITY
            and candidate.unresolved_probability is not None
            and candidate.unresolved_probability <= MAX_UNRESOLVED_PROBABILITY
            and risk > 0 and reward / risk >= MIN_REWARD_RISK - 1e-12)
