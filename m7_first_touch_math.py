from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any


MAX_INTERVAL_COUNT = 4096
NUMERICAL_SURVIVAL_FLOOR = 1e-10


class TemporalMathError(ValueError):
    pass


class TemporalMathConvergenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class CumulativeFirstTouch:
    p_tp: float
    p_sl: float
    p_expiry: float


def _positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TemporalMathError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise TemporalMathError(f"{name}_must_be_positive_finite")
    return number


def _non_negative(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TemporalMathError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise TemporalMathError(f"{name}_must_be_non_negative_finite")
    return number


def _one_sided_hit_bound(distance: float, sigma: float) -> float:
    return 2.0 * NormalDist().cdf(-(distance / sigma))


def _clip_probability(value: float, tolerance: float) -> float:
    if -tolerance <= value <= 0:
        return 0.0
    if 1 <= value <= 1 + tolerance:
        return 1.0
    if value < 0 or value > 1:
        raise TemporalMathConvergenceError(
            f"probability_out_of_bounds:{value}"
        )
    return value


def double_barrier_first_touch(
    *,
    tp_log_distance: float,
    sl_log_distance: float,
    sigma_horizon: float,
    time_fraction: float,
    tolerance: float = 1e-12,
    max_terms: int = 100_000,
) -> CumulativeFirstTouch:
    a = _positive(tp_log_distance, "tp_log_distance")
    b = _positive(sl_log_distance, "sl_log_distance")
    sigma = _positive(sigma_horizon, "sigma_horizon")
    fraction = _non_negative(time_fraction, "time_fraction")
    tol = _positive(tolerance, "tolerance")
    if fraction > 1:
        raise TemporalMathError("time_fraction_must_be_at_most_one")
    if not isinstance(max_terms, int) or max_terms < 10:
        raise TemporalMathError("max_terms_must_be_integer_at_least_10")
    if fraction == 0:
        return CumulativeFirstTouch(0.0, 0.0, 1.0)

    effective_sigma = sigma * math.sqrt(fraction)
    upper_bound = _one_sided_hit_bound(a, effective_sigma)
    lower_bound = _one_sided_hit_bound(b, effective_sigma)
    if upper_bound + lower_bound <= tol:
        return CumulativeFirstTouch(0.0, 0.0, 1.0)

    length = a + b
    cross_bound = _one_sided_hit_bound(length, effective_sigma)
    if 2.0 * cross_bound <= tol:
        p_tp = upper_bound
        p_sl = lower_bound
        p_expiry = 1.0 - p_tp - p_sl
        if p_expiry < 0 and p_expiry >= -tol:
            p_expiry = 0.0
        if p_expiry < 0:
            raise TemporalMathConvergenceError(
                "separated_barrier_probability_mass_invalid"
            )
        mass = p_tp + p_sl + p_expiry
        if mass != 1.0:
            p_expiry += 1.0 - mass
        return CumulativeFirstTouch(p_tp, p_sl, p_expiry)

    theta = math.pi * b / length
    decay = (
        math.pi * math.pi * effective_sigma * effective_sigma
        / (2.0 * length * length)
    )
    upper_terms = []
    lower_terms = []
    survival_terms = []
    converged = False
    for n in range(1, max_terms + 1):
        exponential = math.exp(-decay * n * n)
        sine = math.sin(n * theta)
        base = sine * exponential / n
        lower_terms.append(base)
        upper_terms.append((1 if n % 2 else -1) * base)
        if n % 2:
            survival_terms.append(base)
        if exponential / n <= tol * 0.1:
            converged = True
            break
    if not converged:
        raise TemporalMathConvergenceError(
            f"series_not_converged_within_{max_terms}_terms"
        )

    p_tp = _clip_probability(
        b / length - (2.0 / math.pi) * math.fsum(upper_terms),
        tol * 100,
    )
    p_sl = _clip_probability(
        a / length - (2.0 / math.pi) * math.fsum(lower_terms),
        tol * 100,
    )
    p_expiry = _clip_probability(1.0 - p_tp - p_sl, tol * 100)
    survival_series = (4.0 / math.pi) * math.fsum(survival_terms)
    mass = p_tp + p_sl + p_expiry
    if (
        abs(mass - 1.0) > max(1e-10, tol * 1000)
        or abs(p_expiry - survival_series) > max(1e-10, tol * 1000)
    ):
        raise TemporalMathConvergenceError(
            "double_barrier_series_crosscheck_failed"
        )
    if mass != 1.0:
        p_expiry += 1.0 - mass
    return CumulativeFirstTouch(p_tp, p_sl, p_expiry)


def build_baseline_intervals(
    *,
    tp_log_distance: float,
    sl_log_distance: float,
    sigma_horizon: float,
    interval_count: int,
) -> tuple[dict, ...]:
    if (
        not isinstance(interval_count, int)
        or isinstance(interval_count, bool)
        or interval_count < 1
        or interval_count > MAX_INTERVAL_COUNT
    ):
        raise TemporalMathError("interval_count_must_be_positive_integer")
    cumulative = [
        double_barrier_first_touch(
            tp_log_distance=tp_log_distance,
            sl_log_distance=sl_log_distance,
            sigma_horizon=sigma_horizon,
            time_fraction=index / interval_count,
        )
        for index in range(interval_count + 1)
    ]
    final = cumulative[-1]
    intervals = []
    terminal_reconciled = False
    for index in range(1, interval_count + 1):
        previous = cumulative[index - 1]
        current = cumulative[index]
        survival_before = previous.p_expiry
        if terminal_reconciled or survival_before <= 0:
            intervals.append(
                {
                    "interval": index,
                    "baseline_h_tp": 0.0,
                    "baseline_h_sl": 0.0,
                    "baseline_h_none": 1.0,
                }
            )
            continue
        if survival_before <= NUMERICAL_SURVIVAL_FLOOR:
            residual_tp = max(0.0, final.p_tp - previous.p_tp)
            residual_sl = max(0.0, final.p_sl - previous.p_sl)
            residual_none = max(0.0, final.p_expiry)
            residual_mass = residual_tp + residual_sl + residual_none
            if residual_mass <= 0:
                h_tp, h_sl, h_none = 0.0, 0.0, 1.0
            else:
                h_tp = residual_tp / residual_mass
                h_sl = residual_sl / residual_mass
                h_none = residual_none / residual_mass
            terminal_reconciled = True
        else:
            h_tp = max(0.0, current.p_tp - previous.p_tp) / survival_before
            h_sl = max(0.0, current.p_sl - previous.p_sl) / survival_before
            h_none = 1.0 - h_tp - h_sl
            if h_none < -1e-10:
                raise TemporalMathError("baseline_interval_hazard_mass_invalid")
            h_none = max(0.0, h_none)
        intervals.append(
            {
                "interval": index,
                "baseline_h_tp": h_tp,
                "baseline_h_sl": h_sl,
                "baseline_h_none": h_none,
            }
        )
    return tuple(intervals)


def adjusted_interval_hazards(
    baseline: dict,
    eta_tp: float,
    eta_sl: float,
) -> tuple[float, float, float]:
    h_tp = float(baseline["baseline_h_tp"])
    h_sl = float(baseline["baseline_h_sl"])
    h_none = float(baseline["baseline_h_none"])
    log_tp = math.log(h_tp) + eta_tp if h_tp > 0 else -math.inf
    log_sl = math.log(h_sl) + eta_sl if h_sl > 0 else -math.inf
    log_none = math.log(h_none) if h_none > 0 else -math.inf
    maximum = max(log_tp, log_sl, log_none)
    weighted_tp = math.exp(log_tp - maximum) if h_tp > 0 else 0.0
    weighted_sl = math.exp(log_sl - maximum) if h_sl > 0 else 0.0
    weighted_none = math.exp(log_none - maximum) if h_none > 0 else 0.0
    denominator = weighted_tp + weighted_sl + weighted_none
    if denominator <= 0 or not math.isfinite(denominator):
        raise TemporalMathError("adjusted_hazard_denominator_invalid")
    return (
        weighted_tp / denominator,
        weighted_sl / denominator,
        weighted_none / denominator,
    )


__all__ = (
    "TemporalMathConvergenceError",
    "TemporalMathError",
    "adjusted_interval_hazards",
    "build_baseline_intervals",
    "double_barrier_first_touch",
)
