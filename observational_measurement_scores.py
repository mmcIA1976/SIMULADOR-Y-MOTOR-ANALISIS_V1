"""Outcome-blind research hypotheses, NOT calibrated probability weights."""
from __future__ import annotations

import math

ABSORPTION_SCORE_VERSION = "absorption-stall-wick-proxy-v1"


def absorption_proxy(outputs: dict, *, side: str) -> dict:
    names = ("ATI_H", "relative_horizon_volume", "horizon_displacement_atr", "flow_opposing_wick_ratio")
    values = {}
    for name in names:
        try:
            value = float(outputs.get(name))
        except (TypeError, ValueError):
            value = None
        values[name] = value if value is not None and math.isfinite(value) else None
    ati, volume, displacement, wick = (values[name] for name in names)
    reason = None
    if ati == 0 and wick is None:
        wick = 0.0
    if any(value is None for value in (ati, volume, displacement, wick)):
        reason = "complete_absorption_vector_missing"
    elif not -1 <= ati <= 1 or volume < 0 or not 0 <= wick <= 1:
        reason = "absorption_vector_invalid"
    direction = support = raw_direction = raw_support = None
    factors = {}
    if reason is None:
        # Hypothesis: aggressive pressure with stalled displacement and an
        # opposing wick suggests rejection, NOT proof of passive absorption.
        factors = {"aggressor_pressure": min(1, abs(ati)/0.1),
                   "relative_volume": min(1, volume/2),
                   "stalled_displacement": max(0, 1-abs(displacement)),
                   "opposing_wick": wick}
        intensity = math.prod(factors.values())
        raw_direction = -((ati > 0)-(ati < 0)) * intensity
        raw_support = raw_direction if side == "long" else -raw_direction
        direction = max(-5, min(5, round(5 * raw_direction)))
        support = direction if side == "long" else -direction
    return {"formula_version": ABSORPTION_SCORE_VERSION, "inputs": values,
            "directional_score": direction, "trade_side_score": support,
            "raw_directional_value": raw_direction, "raw_trade_support": raw_support,
            "factors": factors,
            "zero_cause": ("displacement_gate" if factors.get("stalled_displacement") == 0 else
                           "zero_component" if any(v == 0 for v in factors.values()) else
                           "integer_rounding" if direction == 0 else None) if reason is None else reason,
            "reason": reason, "probability_effect": "none"}
