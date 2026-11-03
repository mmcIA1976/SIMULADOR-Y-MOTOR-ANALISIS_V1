"""Bounded swing barrier proposals from completed, direction-neutral paths.

Seven days remains the forecast horizon. Proposal durations describe only the
historical excursions used to construct levels, never a forced exit deadline.
No outcomes from the contest or engine probabilities calibrate these radii.
"""
from __future__ import annotations

import hashlib
import json
import math


PLAN_VERSION = "swing-neutral-excursion-plan-v1"
HORIZON_SECONDS = 7 * 24 * 3600
PROPOSAL_HOURS = (24, 48, 72)
REFERENCE_WINDOWS = 60
REACH_QUANTILE = .25


class PlanRejected(ValueError):
    pass


def _sigma(rows):
    closes = [float(row["close"]) for row in rows]
    if any(not math.isfinite(v) or v <= 0 for v in closes):
        raise PlanRejected("swing_plan_invalid_closed_prices")
    return math.sqrt(math.fsum(math.log(b / a) ** 2 for a, b in zip(closes, closes[1:])))


def _validate(material, side, entry):
    if side not in {"long", "short"} or not math.isfinite(entry) or entry <= 0:
        raise PlanRejected("swing_plan_invalid_inputs")
    if material.get("interval_seconds") != 21600 or material.get("return_count") != 28:
        raise PlanRejected("swing_plan_requires_closed_six_hour_material")
    rows = material["selected"]
    if not rows or rows[-1]["close_time_ms"] > material["data_cutoff_at_ms"]:
        raise PlanRejected("swing_plan_unclosed_material")
    return rows


def proposals(material: dict, *, side: str, entry: float) -> list[dict]:
    rows = _validate(material, side, entry)
    plans = []
    sign = 1 if side == "long" else -1
    for hours in PROPOSAL_HOURS:
        bars = hours // 6
        required = (REFERENCE_WINDOWS + 2) * bars + 1
        if len(rows) < required:
            raise PlanRejected("swing_plan_insufficient_closed_history")
        history = rows[-required:]
        for left, right in zip(history, history[1:]):
            if right["open_time_ms"] - left["open_time_ms"] != 21600000:
                raise PlanRejected("swing_plan_closed_history_gap")
        current_sigma = _sigma(history[-bars - 1:])
        if current_sigma <= 0:
            continue
        reaches = []
        for index in range(REFERENCE_WINDOWS):
            anchor = (index + 1) * bars
            known_sigma = _sigma(history[anchor - bars:anchor + 1])
            if known_sigma <= 0:
                continue
            baseline = float(history[anchor]["close"])
            future = history[anchor + 1:anchor + bars + 1]
            highs = [float(row["high"]) for row in future]
            lows = [float(row["low"]) for row in future]
            if any(not math.isfinite(v) or v <= 0 for v in highs + lows):
                raise PlanRejected("swing_plan_invalid_closed_prices")
            reaches.append(max(max(highs) / baseline - 1, 1 - min(lows) / baseline, 0) / known_sigma)
        if len(reaches) < 30:
            continue
        ordered = sorted(reaches)
        position = (len(ordered) - 1) * REACH_QUANTILE
        lower, upper = math.floor(position), math.ceil(position)
        multiple = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
        radius = multiple * current_sigma
        if not math.isfinite(radius) or not 1e-12 < radius < .5:
            continue
        if any(math.isclose(radius, p["radius_fraction"], rel_tol=1e-9, abs_tol=1e-12) for p in plans):
            continue
        lineage = [PLAN_VERSION, side, material["data_sha256"], hours, radius]
        plans.append({
            "version": PLAN_VERSION, "horizon_seconds": HORIZON_SECONDS,
            "proposal_hours": hours, "reach_quantile": REACH_QUANTILE,
            "reference_windows": len(reaches), "reference_window_bars": bars,
            "reference_first_anchor_at_ms": history[bars]["close_time_ms"],
            "reference_last_end_at_ms": history[-bars - 1]["close_time_ms"],
            "current_window_start_at_ms": history[-bars]["open_time_ms"],
            "current_sigma": current_sigma, "normalized_reach_quantile": multiple,
            "radius_fraction": radius, "reward_risk_ratio": 1.,
            "take_profit": entry * (1 + sign * radius),
            "stop_loss": entry * (1 - sign * radius),
            "source_sha256": material["data_sha256"],
            "data_cutoff_at_ms": material["data_cutoff_at_ms"],
            "probability_effect": "none_proposal_construction_only",
            "lineage_key": hashlib.sha256(json.dumps(lineage).encode()).hexdigest()[:16],
        })
    if not plans:
        raise PlanRejected("swing_plan_no_valid_excursion_geometry")
    return plans


def validate_requote(plan: dict, material: dict, *, side: str, entry: float) -> dict:
    """Reanalyse the selected radius at the fresh price; never select a new one."""
    _validate(material, side, entry)
    radius = plan.get("radius_fraction")
    if (plan.get("version") != PLAN_VERSION or type(radius) not in {int, float}
            or not math.isfinite(radius) or not 0 < radius < .5
            or not plan.get("lineage_key")
            or plan.get("horizon_seconds") != HORIZON_SECONDS):
        raise PlanRejected("swing_plan_invalid_frozen_geometry")
    sign = 1 if side == "long" else -1
    return {**plan, "take_profit": entry * (1 + sign * radius),
            "stop_loss": entry * (1 - sign * radius),
            "revalidated_source_sha256": material["data_sha256"],
            "revalidated_data_cutoff_at_ms": material["data_cutoff_at_ms"]}
