from __future__ import annotations

import math

from m5_input_assembly import trace_map


RULE_MODEL_VERSION = "M6-active-predictive-rules-v0.1"

# Rules 9-11 already enter through the fitted M6 candidate. The remaining
# rules below receive explicit provisional log-hazard effects so every
# predictive rule with live data participates in the final probability.
FITTED_RULE_IDS = (
    "M4-RULE-PRIOR-EXTREMA-001",
    "M4-RULE-VOLATILITY-RANK-001",
    "M4-RULE-MTF-HIERARCHY-001",
)

FITTED_RULE_FEATURES = {
    "M4-RULE-PRIOR-EXTREMA-001": (
        "target_extreme_between_entry_and_tp",
    ),
    "M4-RULE-VOLATILITY-RANK-001": (
        "volatility_percentile_60",
    ),
    "M4-RULE-MTF-HIERARCHY-001": (
        "directional_path_efficiency_2h",
        "directional_path_efficiency_4h",
    ),
}

PROVISIONAL_RULE_WEIGHTS = {
    "M4-RULE-PATH-STRUCTURE-001": 0.12,
    "M4-RULE-CONTINUOUS-REGIME-001": 0.08,
    "M4-RULE-AGGRESSOR-IMBALANCE-001": 0.12,
    "M4-RULE-OPEN-INTEREST-CHANGE-001": 0.06,
    "M4-RULE-PRICE-OI-STATE-001": 0.10,
    "M4-RULE-SPOT-FUTURES-BASIS-001": 0.06,
    "M4-RULE-MARK-INDEX-PREMIUM-001": 0.06,
    "M4-RULE-FUNDING-STATE-001": 0.08,
}

ACTIVE_PREDICTIVE_RULE_IDS = (
    "M4-RULE-PATH-STRUCTURE-001",
    *FITTED_RULE_IDS,
    "M4-RULE-CONTINUOUS-REGIME-001",
    "M4-RULE-AGGRESSOR-IMBALANCE-001",
    "M4-RULE-OPEN-INTEREST-CHANGE-001",
    "M4-RULE-PRICE-OI-STATE-001",
    "M4-RULE-SPOT-FUTURES-BASIS-001",
    "M4-RULE-MARK-INDEX-PREMIUM-001",
    "M4-RULE-FUNDING-STATE-001",
)

ACTIVE_EVIDENCE_FAMILIES = {
    "FAMILY-PRICE-PATH": (
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-MTF-HIERARCHY-001",
    ),
    "FAMILY-STRUCTURAL-LEVELS": (
        "M4-RULE-PRIOR-EXTREMA-001",
    ),
    "FAMILY-VOLATILITY": (
        "M4-RULE-VOLATILITY-RANK-001",
    ),
    "FAMILY-PRICE-PATH-X-VOLATILITY": (
        "M4-RULE-CONTINUOUS-REGIME-001",
    ),
    "FAMILY-EXECUTED-FLOW": (
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
    ),
    "FAMILY-OPEN-INTEREST": (
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
        "M4-RULE-PRICE-OI-STATE-001",
    ),
    "FAMILY-PERPETUAL-DISLOCATION": (
        "M4-RULE-SPOT-FUTURES-BASIS-001",
        "M4-RULE-MARK-INDEX-PREMIUM-001",
        "M4-RULE-FUNDING-STATE-001",
    ),
}


def _finite(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name}_must_be_finite")
    return number


def _bounded(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))


def _direction(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def _signal_path(outputs: dict, direction: float) -> tuple[float, str]:
    value = direction * _finite(
        outputs["signed_path_efficiency"],
        "signed_path_efficiency",
    )
    return _bounded(value), "side_adjusted_signed_path_efficiency"


def _signal_regime(outputs: dict, direction: float) -> tuple[float, str]:
    efficiency = direction * _finite(
        outputs["signed_path_efficiency"],
        "signed_path_efficiency",
    )
    percentile = _finite(
        outputs["volatility_percentile"],
        "volatility_percentile",
    )
    value = efficiency * (2.0 * percentile - 1.0)
    return _bounded(value), "directional_efficiency_x_volatility_regime"


def _signal_aggressor(outputs: dict, direction: float) -> tuple[float, str]:
    value = direction * _finite(outputs["ATI_H"], "ATI_H")
    return _bounded(value), "side_adjusted_taker_imbalance"


def _signal_oi(outputs: dict, _direction_value: float) -> tuple[float, str]:
    change = abs(_finite(outputs["dOI_H"], "dOI_H"))
    return math.tanh(50.0 * change), "open_interest_activity_strength"


def _signal_price_oi(
    outputs: dict,
    direction: float,
) -> tuple[float, str]:
    displacement = _finite(outputs["D_H"], "D_H")
    oi_change = _finite(outputs["dOI_H"], "dOI_H")
    price_sign = 1.0 if displacement > 0 else -1.0 if displacement < 0 else 0.0
    value = direction * price_sign * math.tanh(50.0 * oi_change)
    return _bounded(value), "side_adjusted_price_direction_x_oi_change"


def _signal_basis(outputs: dict, direction: float) -> tuple[float, str]:
    basis = _finite(outputs["b_mid"], "b_mid")
    value = -direction * math.tanh(100.0 * basis)
    return _bounded(value), "contrarian_side_adjusted_spot_futures_basis"


def _signal_premium(outputs: dict, direction: float) -> tuple[float, str]:
    premium = _finite(
        outputs["mark_index_log_premium"],
        "mark_index_log_premium",
    )
    value = -direction * math.tanh(200.0 * premium)
    return _bounded(value), "contrarian_side_adjusted_mark_index_premium"


def _signal_funding(outputs: dict, direction: float) -> tuple[float, str]:
    rate = _finite(outputs["last_funding_rate"], "last_funding_rate")
    value = -direction * math.tanh(rate / 0.0005)
    return _bounded(value), "contrarian_side_adjusted_last_funding_rate"


SIGNAL_BUILDERS = {
    "M4-RULE-PATH-STRUCTURE-001": _signal_path,
    "M4-RULE-CONTINUOUS-REGIME-001": _signal_regime,
    "M4-RULE-AGGRESSOR-IMBALANCE-001": _signal_aggressor,
    "M4-RULE-OPEN-INTEREST-CHANGE-001": _signal_oi,
    "M4-RULE-PRICE-OI-STATE-001": _signal_price_oi,
    "M4-RULE-SPOT-FUTURES-BASIS-001": _signal_basis,
    "M4-RULE-MARK-INDEX-PREMIUM-001": _signal_premium,
    "M4-RULE-FUNDING-STATE-001": _signal_funding,
}

RULE_EFFECT_MODES = {
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "movement",
}


def build_provisional_rule_signals(
    m5_analysis: dict,
    *,
    side: str,
) -> dict:
    traces = trace_map(m5_analysis)
    direction = _direction(side)
    active = {}
    unavailable = {}
    for rule_id, weight in PROVISIONAL_RULE_WEIGHTS.items():
        trace = traces.get(rule_id)
        if not trace or trace.get("status") != "evaluated":
            unavailable[rule_id] = {
                "status": (trace or {}).get("status", "missing"),
                "reason_codes": (trace or {}).get("reason_codes", []),
            }
            continue
        signal, formula = SIGNAL_BUILDERS[rule_id](
            trace.get("outputs") or {},
            direction,
        )
        effect_mode = RULE_EFFECT_MODES.get(rule_id, "directional")
        if effect_mode == "movement":
            tp_effect = float(weight) * signal
            sl_effect = float(weight) * signal
            expiry_effect = -float(weight) * signal
        else:
            tp_effect = float(weight) * signal
            sl_effect = -float(weight) * signal
            expiry_effect = 0.0
        active[rule_id] = {
            "signal": signal,
            "weight": float(weight),
            "effect_mode": effect_mode,
            "tp_log_effect": tp_effect,
            "sl_log_effect": sl_effect,
            "expiry_log_effect": expiry_effect,
            "signal_formula": formula,
            "source_trace_sha256": trace.get("trace_sha256"),
        }
    return {
        "version": RULE_MODEL_VERSION,
        "active": active,
        "unavailable": unavailable,
    }


def _normalize_log_weights(log_weights: dict[str, float]) -> dict[str, float]:
    maximum = max(log_weights.values())
    weights = {
        name: math.exp(value - maximum)
        for name, value in log_weights.items()
    }
    total = math.fsum(weights.values())
    return {name: value / total for name, value in weights.items()}


def _apply_rule_effects(
    probabilities: dict[str, float],
    rules: dict[str, dict],
) -> dict[str, float]:
    current = dict(probabilities)
    for rule in rules.values():
        current = _normalize_log_weights(
            {
                "tp_first_within_horizon": (
                    math.log(current["tp_first_within_horizon"])
                    + rule["tp_log_effect"]
                ),
                "sl_first_within_horizon": (
                    math.log(current["sl_first_within_horizon"])
                    + rule["sl_log_effect"]
                ),
                "neither_barrier_before_expiry": (
                    math.log(current["neither_barrier_before_expiry"])
                    + rule["expiry_log_effect"]
                ),
            }
        )
    return current


def apply_provisional_rule_overlay(
    probabilities: dict[str, float],
    signal_snapshot: dict,
) -> dict:
    names = (
        "tp_first_within_horizon",
        "sl_first_within_horizon",
        "neither_barrier_before_expiry",
    )
    before = {name: _finite(probabilities[name], name) for name in names}
    if any(value <= 0.0 for value in before.values()):
        raise ValueError("probabilities_must_be_strictly_positive")
    current = dict(before)
    contributions = {}
    for rule_id, rule in signal_snapshot["active"].items():
        prior = dict(current)
        adjusted = {
            "tp_first_within_horizon": (
                math.log(prior["tp_first_within_horizon"])
                + rule["tp_log_effect"]
            ),
            "sl_first_within_horizon": (
                math.log(prior["sl_first_within_horizon"])
                + rule["sl_log_effect"]
            ),
            "neither_barrier_before_expiry": math.log(
                prior["neither_barrier_before_expiry"]
            ) + rule["expiry_log_effect"],
        }
        current = _normalize_log_weights(adjusted)
        contributions[rule_id] = {
            **rule,
            "probabilities_before": prior,
            "probabilities_after": dict(current),
            "tp_probability_delta": (
                current["tp_first_within_horizon"]
                - prior["tp_first_within_horizon"]
            ),
            "sl_probability_delta": (
                current["sl_first_within_horizon"]
                - prior["sl_first_within_horizon"]
            ),
        }
    for rule_id, contribution in contributions.items():
        rules_without = {
            other_id: rule
            for other_id, rule in signal_snapshot["active"].items()
            if other_id != rule_id
        }
        probabilities_without = _apply_rule_effects(
            before,
            rules_without,
        )
        contribution["ablation_probabilities_without_rule"] = (
            probabilities_without
        )
        contribution["ablation_probability_delta"] = {
            name: current[name] - probabilities_without[name]
            for name in names
        }
    return {
        "version": RULE_MODEL_VERSION,
        "probabilities_before": before,
        "probabilities_after": current,
        "rule_contributions": contributions,
        "unavailable_rules": signal_snapshot["unavailable"],
        "active_rule_ids": list(contributions),
        "probability_mass_error": abs(math.fsum(current.values()) - 1.0),
    }
