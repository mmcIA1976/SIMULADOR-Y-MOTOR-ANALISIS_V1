from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist


SOLVER_VERSION = "M6-double-barrier-first-passage-v0.2"


class FirstPassageInputError(ValueError):
    pass


class FirstPassageConvergenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FirstPassageResult:
    p_tp: float
    p_sl: float
    p_expiry: float
    tp_log_distance: float
    sl_log_distance: float
    sigma_horizon: float
    time_fraction: float
    solver_version: str
    numerical_method: str
    terms_used: int
    requested_tolerance: float
    mass_error: float
    survival_crosscheck_error: float
    absolute_error_bound: float | None
    drift: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def positive_finite(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FirstPassageInputError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise FirstPassageInputError(f"{name}_must_be_positive_finite")
    return number


def non_negative_finite(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FirstPassageInputError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise FirstPassageInputError(f"{name}_must_be_non_negative_finite")
    return number


def one_sided_hit_upper_bound(distance: float, sigma: float) -> float:
    z = distance / sigma
    return 2.0 * NormalDist().cdf(-z)


def _clip_probability(value: float, tolerance: float) -> float:
    if -tolerance <= value <= 0:
        return 0.0
    if 1 <= value <= 1 + tolerance:
        return 1.0
    if value < 0 or value > 1:
        raise FirstPassageConvergenceError(
            f"probability_out_of_bounds:{value}"
        )
    return value


def double_barrier_first_passage(
    *,
    tp_log_distance: float,
    sl_log_distance: float,
    sigma_horizon: float,
    time_fraction: float = 1.0,
    tolerance: float = 1e-12,
    max_terms: int = 100_000,
) -> FirstPassageResult:
    a = positive_finite(tp_log_distance, "tp_log_distance")
    b = positive_finite(sl_log_distance, "sl_log_distance")
    sigma = positive_finite(sigma_horizon, "sigma_horizon")
    fraction = non_negative_finite(time_fraction, "time_fraction")
    tol = positive_finite(tolerance, "tolerance")
    if fraction > 1:
        raise FirstPassageInputError("time_fraction_must_be_at_most_one")
    if not isinstance(max_terms, int) or max_terms < 10:
        raise FirstPassageInputError("max_terms_must_be_integer_at_least_10")
    if fraction == 0:
        return FirstPassageResult(
            p_tp=0.0,
            p_sl=0.0,
            p_expiry=1.0,
            tp_log_distance=a,
            sl_log_distance=b,
            sigma_horizon=sigma,
            time_fraction=fraction,
            solver_version=SOLVER_VERSION,
            numerical_method="exact_time_zero",
            terms_used=0,
            requested_tolerance=tol,
            mass_error=0.0,
            survival_crosscheck_error=0.0,
            absolute_error_bound=0.0,
        )

    effective_sigma = sigma * math.sqrt(fraction)
    upper_bound = one_sided_hit_upper_bound(a, effective_sigma)
    lower_bound = one_sided_hit_upper_bound(b, effective_sigma)
    union_bound = upper_bound + lower_bound
    if union_bound <= tol:
        return FirstPassageResult(
            p_tp=0.0,
            p_sl=0.0,
            p_expiry=1.0,
            tp_log_distance=a,
            sl_log_distance=b,
            sigma_horizon=sigma,
            time_fraction=fraction,
            solver_version=SOLVER_VERSION,
            numerical_method="reflection_principle_tail_bound",
            terms_used=0,
            requested_tolerance=tol,
            mass_error=0.0,
            survival_crosscheck_error=0.0,
            absolute_error_bound=union_bound,
        )

    length = a + b
    cross_bound = one_sided_hit_upper_bound(length, effective_sigma)
    vector_error_bound = 2.0 * cross_bound
    if vector_error_bound <= tol:
        # A path counted by a one-sided hit but not by first passage must cross
        # the full interval after touching the opposite barrier.
        p_tp = upper_bound
        p_sl = lower_bound
        p_expiry = 1.0 - p_tp - p_sl
        if p_expiry < 0 and p_expiry >= -tol:
            p_expiry = 0.0
        if p_expiry < 0:
            raise FirstPassageConvergenceError(
                "separated_barrier_probability_mass_invalid"
            )
        mass = p_tp + p_sl + p_expiry
        if mass != 1.0:
            p_expiry += 1.0 - mass
        return FirstPassageResult(
            p_tp=p_tp,
            p_sl=p_sl,
            p_expiry=p_expiry,
            tp_log_distance=a,
            sl_log_distance=b,
            sigma_horizon=sigma,
            time_fraction=fraction,
            solver_version=SOLVER_VERSION,
            numerical_method="reflection_principle_separated_barriers",
            terms_used=0,
            requested_tolerance=tol,
            mass_error=abs(p_tp + p_sl + p_expiry - 1.0),
            survival_crosscheck_error=0.0,
            absolute_error_bound=vector_error_bound,
        )

    theta = math.pi * b / length
    decay = (
        math.pi * math.pi * effective_sigma * effective_sigma
        / (2.0 * length * length)
    )
    upper_terms = []
    lower_terms = []
    survival_terms = []
    terms_used = 0
    converged = False
    for n in range(1, max_terms + 1):
        exponential = math.exp(-decay * n * n)
        sine = math.sin(n * theta)
        base = sine * exponential / n
        lower_terms.append(base)
        upper_terms.append((1 if n % 2 else -1) * base)
        if n % 2:
            survival_terms.append(base)
        terms_used = n
        if exponential / n <= tol * 0.1:
            converged = True
            break
    if not converged:
        raise FirstPassageConvergenceError(
            f"series_not_converged_within_{max_terms}_terms"
        )

    p_tp_raw = b / length - (2.0 / math.pi) * math.fsum(upper_terms)
    p_sl_raw = a / length - (2.0 / math.pi) * math.fsum(lower_terms)
    survival_series = (4.0 / math.pi) * math.fsum(survival_terms)
    p_tp = _clip_probability(p_tp_raw, tol * 100)
    p_sl = _clip_probability(p_sl_raw, tol * 100)
    p_expiry = _clip_probability(1.0 - p_tp - p_sl, tol * 100)
    mass = p_tp + p_sl + p_expiry
    mass_error = abs(mass - 1.0)
    survival_error = abs(p_expiry - survival_series)
    allowed_error = max(1e-10, tol * 1000)
    if mass_error > allowed_error or survival_error > allowed_error:
        raise FirstPassageConvergenceError(
            "double_barrier_series_crosscheck_failed"
        )
    if mass != 1.0:
        p_expiry += 1.0 - mass
        mass_error = abs(p_tp + p_sl + p_expiry - 1.0)
    return FirstPassageResult(
        p_tp=p_tp,
        p_sl=p_sl,
        p_expiry=p_expiry,
        tp_log_distance=a,
        sl_log_distance=b,
        sigma_horizon=sigma,
        time_fraction=fraction,
        solver_version=SOLVER_VERSION,
        numerical_method="absorbing_interval_eigenfunction_series",
        terms_used=terms_used,
        requested_tolerance=tol,
        mass_error=mass_error,
        survival_crosscheck_error=survival_error,
        absolute_error_bound=None,
    )
