from __future__ import annotations

import math
from dataclasses import asdict, dataclass

SINGLE_BARRIER_SOLVER_VERSION = "LIMIT-single-barrier-first-passage-v0.1"


class FirstPassageInputError(ValueError):
    pass


class FirstPassageConvergenceError(RuntimeError):
    pass


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


@dataclass(frozen=True)
class SingleBarrierFirstPassageResult:
    p_hit: float
    p_no_hit: float
    log_distance: float
    sigma_horizon: float
    time_fraction: float
    solver_version: str
    numerical_method: str
    mass_error: float
    drift: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def single_barrier_first_passage(
    *,
    log_distance: float,
    sigma_horizon: float,
    time_fraction: float = 1.0,
) -> SingleBarrierFirstPassageResult:
    """Probability of touching one log-price barrier under zero drift.

    ``sigma_horizon`` is the total standard deviation for the complete
    horizon. ``time_fraction`` scales that horizon without changing the
    volatility convention. The reflection principle gives the exact
    model-implied hit probability as ``erfc(z / sqrt(2))``.

    This activation-stage solver is independent from the production TP/SL
    probability engine and does not execute an alternative market model.
    """

    distance = positive_finite(log_distance, "log_distance")
    sigma = positive_finite(sigma_horizon, "sigma_horizon")
    fraction = non_negative_finite(time_fraction, "time_fraction")
    if fraction > 1:
        raise FirstPassageInputError("time_fraction_must_be_at_most_one")
    if fraction == 0:
        return SingleBarrierFirstPassageResult(
            p_hit=0.0,
            p_no_hit=1.0,
            log_distance=distance,
            sigma_horizon=sigma,
            time_fraction=fraction,
            solver_version=SINGLE_BARRIER_SOLVER_VERSION,
            numerical_method="exact_time_zero",
            mass_error=0.0,
        )

    effective_sigma = sigma * math.sqrt(fraction)
    z = distance / effective_sigma
    p_hit = math.erfc(z / math.sqrt(2.0))
    p_hit = min(1.0, max(0.0, p_hit))
    p_no_hit = 1.0 - p_hit
    mass_error = abs(math.fsum((p_hit, p_no_hit)) - 1.0)
    if mass_error > 1e-15:
        raise FirstPassageConvergenceError(
            "single_barrier_probability_mass_invalid"
        )
    return SingleBarrierFirstPassageResult(
        p_hit=p_hit,
        p_no_hit=p_no_hit,
        log_distance=distance,
        sigma_horizon=sigma,
        time_fraction=fraction,
        solver_version=SINGLE_BARRIER_SOLVER_VERSION,
        numerical_method="reflection_principle_erfc",
        mass_error=mass_error,
    )


__all__ = (
    "FirstPassageConvergenceError",
    "FirstPassageInputError",
    "SINGLE_BARRIER_SOLVER_VERSION",
    "SingleBarrierFirstPassageResult",
    "single_barrier_first_passage",
)
