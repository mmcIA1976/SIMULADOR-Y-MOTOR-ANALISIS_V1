from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any


class SequentialFirstTouchMathError(ValueError):
    pass


class SequentialFirstTouchConvergenceError(RuntimeError):
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
        raise SequentialFirstTouchMathError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise SequentialFirstTouchMathError(
            f"{name}_must_be_positive_finite"
        )
    return number


def _non_negative(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SequentialFirstTouchMathError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise SequentialFirstTouchMathError(
            f"{name}_must_be_non_negative_finite"
        )
    return number


def _one_sided_hit_bound(distance: float, sigma: float) -> float:
    return 2.0 * NormalDist().cdf(-(distance / sigma))


def _clip_probability(value: float, tolerance: float) -> float:
    if -tolerance <= value <= 0:
        return 0.0
    if 1 <= value <= 1 + tolerance:
        return 1.0
    if value < 0 or value > 1:
        raise SequentialFirstTouchConvergenceError(
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
    """Absorbing first-touch probabilities for two log-price barriers."""
    a = _positive(tp_log_distance, "tp_log_distance")
    b = _positive(sl_log_distance, "sl_log_distance")
    sigma = _positive(sigma_horizon, "sigma_horizon")
    fraction = _non_negative(time_fraction, "time_fraction")
    tol = _positive(tolerance, "tolerance")
    if fraction > 1:
        raise SequentialFirstTouchMathError(
            "time_fraction_must_be_at_most_one"
        )
    if not isinstance(max_terms, int) or max_terms < 10:
        raise SequentialFirstTouchMathError(
            "max_terms_must_be_integer_at_least_10"
        )
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
            raise SequentialFirstTouchConvergenceError(
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
    upper_terms: list[float] = []
    lower_terms: list[float] = []
    survival_terms: list[float] = []
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
        raise SequentialFirstTouchConvergenceError(
            f"series_not_converged_within_{max_terms}_terms"
        )

    p_tp = _clip_probability(
        b / length - (2.0 / math.pi) * math.fsum(upper_terms), tol * 100
    )
    p_sl = _clip_probability(
        a / length - (2.0 / math.pi) * math.fsum(lower_terms), tol * 100
    )
    p_expiry = _clip_probability(1.0 - p_tp - p_sl, tol * 100)
    survival_series = (4.0 / math.pi) * math.fsum(survival_terms)
    mass = p_tp + p_sl + p_expiry
    if (
        abs(mass - 1.0) > max(1e-10, tol * 1000)
        or abs(p_expiry - survival_series) > max(1e-10, tol * 1000)
    ):
        raise SequentialFirstTouchConvergenceError(
            "double_barrier_series_crosscheck_failed"
        )
    if mass != 1.0:
        p_expiry += 1.0 - mass
    return CumulativeFirstTouch(p_tp, p_sl, p_expiry)


__all__ = (
    "CumulativeFirstTouch",
    "SequentialFirstTouchConvergenceError",
    "SequentialFirstTouchMathError",
    "double_barrier_first_touch",
)
