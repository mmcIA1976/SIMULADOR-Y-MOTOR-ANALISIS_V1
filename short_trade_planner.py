"""Bounded four-hour proposals, not another probability engine.

Construct symmetric levels from observed either-side four-hour excursions,
then let the production engine assess direction and first touch. Quantiles
are direction-neutral proposal sizes, not probabilities of winning.
All inputs are validated closed candles already loaded by the active engine.
"""
from __future__ import annotations

import hashlib
import json
import math

from technical_rule_runtime import wilder_atr


PLAN_VERSION = "short-horizon-excursion-plan-v3-symmetric"
HORIZON_SECONDS = 14400
MIN_TP_PROBABILITY = .50
MAX_UNRESOLVED_PROBABILITY = .20
EXCURSION_QUANTILES = (.25, .50)
MAX_PROPOSALS_PER_SIDE = 2


class PlanRejected(ValueError):
    """Market context evaluated, but no defensible trade plan exists."""


def symmetric_radius_fraction(entry, take_profit, stop_loss, side):
    """Return a valid 1:1 radius, or None; never repair an asymmetric analysis."""
    if side not in {"long", "short"}:
        return None
    try:
        if any(isinstance(v, bool) for v in (entry, take_profit, stop_loss)):
            return None
        entry, take_profit, stop_loss = map(float, (entry, take_profit, stop_loss))
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) and v > 0 for v in (entry, take_profit, stop_loss)):
        return None
    sign = 1 if side == "long" else -1
    reward, risk = sign * (take_profit - entry), sign * (entry - stop_loss)
    if min(reward, risk) <= entry * 1e-12 or not math.isclose(
        reward, risk, rel_tol=1e-9, abs_tol=entry * 1e-12,
    ):
        return None
    return (reward + risk) / (2 * entry)


def _quantile(values, quantile):
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def context(material: dict, *, side: str, entry: float) -> dict:
    if side not in {"long", "short"} or not math.isfinite(entry) or entry <= 0:
        raise ValueError("short_plan_invalid_inputs")
    if int(material["return_count"]) != 48 or int(material["interval_seconds"]) != 300:
        raise ValueError("short_plan_requires_closed_5m_four_hour_material")
    rows = material["selected"]
    sign = 1 if side == "long" else -1
    atr = wilder_atr(rows[-200:])
    if atr <= 0 or not math.isfinite(atr):
        raise ValueError("short_plan_invalid_atr")
    # Completed, non-overlapping past windows only. The denominator is ATR
    # known at the START of each window, not volatility learned afterwards.
    favorable, adverse, reaches = [], [], []
    for start in range(48, len(rows) - 96, 48):
        baseline = float(rows[start]["close"])
        baseline_atr = wilder_atr(rows[max(0, start - 199):start + 1])
        window = rows[start + 1:start + 49]
        if baseline_atr <= 0 or len(window) != 48:
            continue
        extreme = (max(float(r["high"]) for r in window) if sign == 1
                   else min(float(r["low"]) for r in window))
        opposite = (min(float(r["low"]) for r in window) if sign == 1
                    else max(float(r["high"]) for r in window))
        favorable.append(max(0.0, sign * (extreme - baseline)) / baseline_atr)
        adverse.append(max(0.0, sign * (baseline - opposite)) / baseline_atr)
        reaches.append(max(favorable[-1], adverse[-1]))
    if len(favorable) < 30:
        raise ValueError("short_plan_insufficient_complete_reference_windows")
    return {
        "version": PLAN_VERSION, "horizon_seconds": HORIZON_SECONDS,
        "atr_5m": atr,
        "four_hour_reach": _quantile(favorable, .50) * atr,
        "four_hour_adverse_reach": _quantile(adverse, .50) * atr,
        "four_hour_symmetric_reach": _quantile(reaches, .50) * atr,
        "reference_windows": len(favorable),
        "excursion_sizes": [
            {"quantile": q, "radius": _quantile(reaches, q) * atr,
             "favorable": _quantile(favorable, q) * atr,
             "adverse": _quantile(adverse, q) * atr} for q in EXCURSION_QUANTILES
        ],
        "source_sha256": material["data_sha256"],
        "data_cutoff_at_ms": material["data_cutoff_at_ms"],
        "probability_effect": "none_proposal_construction_only",
    }


def proposals(material: dict, *, side: str, entry: float) -> list[dict]:
    ctx = context(material, side=side, entry=entry)
    sign = 1 if side == "long" else -1
    results = []
    for sizes in ctx["excursion_sizes"]:
        reward = risk = sizes["radius"]
        if not all(math.isfinite(v) and v > entry * 1e-12 for v in (reward, risk)):
            continue
        target, stop = entry + sign * reward, entry - sign * risk
        if min(target, stop) <= 0 or any(
            abs(p["take_profit"] - target) <= entry * 1e-12
            and abs(p["stop_loss"] - stop) <= entry * 1e-12 for p in results
        ):
            continue
        lineage = json.dumps([PLAN_VERSION, side, material["data_cutoff_at_ms"],
                              sizes["quantile"], target, stop])
        results.append({
            **{k: v for k, v in ctx.items() if k != "excursion_sizes"},
            "take_profit": target, "stop_loss": stop,
            "excursion_quantile": sizes["quantile"],
            "radius_fraction": reward / entry,
            "reward_risk_ratio": reward / risk,
            "lineage_key": hashlib.sha256(lineage.encode()).hexdigest()[:16],
        })
    if not results:
        raise PlanRejected("short_plan_no_positive_four_hour_geometry")
    return results[:MAX_PROPOSALS_PER_SIDE]


def validate_requote(plan: dict, material: dict, *, side: str, entry: float) -> dict:
    """Keep the monitored radius/lineage, recenter BOTH levels before analysis."""
    ctx = context(material, side=side, entry=entry)
    radius = plan.get("radius_fraction")
    if (plan.get("version") != PLAN_VERSION or type(radius) not in {int, float}
            or not math.isfinite(radius) or not 0 < radius < 1):
        raise PlanRejected("short_plan_symmetric_radius_missing")
    sign = 1 if side == "long" else -1
    target, stop = entry * (1 + sign * radius), entry * (1 - sign * radius)
    return {**plan, "take_profit": target, "stop_loss": stop, "reward_risk_ratio": 1.,
            "revalidated_source_sha256": ctx["source_sha256"]}


def passes_forecast(candidate) -> bool:
    if symmetric_radius_fraction(candidate.entry, candidate.take_profit,
                                 candidate.stop_loss, candidate.side) is None:
        return False
    if not getattr(candidate, "trade_plan", None):
        return True  # Older candidates/reports retain their historical contract.
    if any(v is None or not math.isfinite(v) for v in
           (candidate.take_profit, candidate.entry, candidate.stop_loss)):
        return False
    sign = 1 if candidate.side == "long" else -1
    reward = sign * (candidate.take_profit - candidate.entry)
    risk = sign * (candidate.entry - candidate.stop_loss)
    return (candidate.tp_probability is not None and candidate.tp_probability >= MIN_TP_PROBABILITY
            and candidate.unresolved_probability is not None
            and candidate.unresolved_probability <= MAX_UNRESOLVED_PROBABILITY
            and candidate.sl_probability is not None and risk > 0 and reward > 0
            and candidate.tp_probability * reward > candidate.sl_probability * risk)
