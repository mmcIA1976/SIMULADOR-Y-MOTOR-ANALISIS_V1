from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


ORACLE_VERSION = "M7-independent-implicit-PDE-v0.1"


class IndependentOracleInputError(ValueError):
    pass


@dataclass(frozen=True)
class IndependentOracleResult:
    p_tp: float
    p_sl: float
    p_expiry: float
    spatial_intervals: int
    time_steps: int
    mass_error: float
    oracle_version: str = ORACLE_VERSION
    numerical_method: str = (
        "backward_euler_finite_difference_absorbing_boundaries"
    )

    def to_dict(self) -> dict:
        return asdict(self)


def _positive_finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IndependentOracleInputError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise IndependentOracleInputError(f"{name}_must_be_positive_finite")
    return number


def _fraction(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise IndependentOracleInputError(
            "time_fraction_must_be_numeric"
        ) from exc
    if not math.isfinite(number) or number < 0 or number > 1:
        raise IndependentOracleInputError(
            "time_fraction_must_be_between_zero_and_one"
        )
    return number


def _integer_at_least(value: Any, name: str, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise IndependentOracleInputError(
            f"{name}_must_be_integer_at_least_{minimum}"
        )
    return value


def _tridiagonal_plan(
    size: int,
    diagonal: float,
    off_diagonal: float,
) -> tuple[list[float], list[float]]:
    c_prime = [0.0] * size
    inverse_denominator = [0.0] * size
    inverse_denominator[0] = 1.0 / diagonal
    if size > 1:
        c_prime[0] = off_diagonal * inverse_denominator[0]
    for index in range(1, size):
        denominator = diagonal - off_diagonal * c_prime[index - 1]
        inverse_denominator[index] = 1.0 / denominator
        if index < size - 1:
            c_prime[index] = off_diagonal * inverse_denominator[index]
    return c_prime, inverse_denominator


def _solve_with_plan(
    rhs: list[float],
    *,
    off_diagonal: float,
    c_prime: list[float],
    inverse_denominator: list[float],
) -> list[float]:
    size = len(rhs)
    d_prime = [0.0] * size
    d_prime[0] = rhs[0] * inverse_denominator[0]
    for index in range(1, size):
        d_prime[index] = (
            rhs[index] - off_diagonal * d_prime[index - 1]
        ) * inverse_denominator[index]
    solution = [0.0] * size
    solution[-1] = d_prime[-1]
    for index in range(size - 2, -1, -1):
        solution[index] = (
            d_prime[index] - c_prime[index] * solution[index + 1]
        )
    return solution


def _interpolate_grid_value(
    interior: list[float],
    position: float,
    intervals: int,
    *,
    left_boundary: float,
    right_boundary: float,
) -> float:
    lower_index = int(math.floor(position))
    weight = position - lower_index

    def at(index: int) -> float:
        if index <= 0:
            return left_boundary
        if index >= intervals:
            return right_boundary
        return interior[index - 1]

    return (1.0 - weight) * at(lower_index) + weight * at(
        lower_index + 1
    )


def finite_difference_first_passage(
    *,
    tp_log_distance: float,
    sl_log_distance: float,
    sigma_horizon: float,
    time_fraction: float = 1.0,
    spatial_intervals: int = 240,
    time_steps: int = 1200,
) -> IndependentOracleResult:
    tp_distance = _positive_finite(tp_log_distance, "tp_log_distance")
    sl_distance = _positive_finite(sl_log_distance, "sl_log_distance")
    sigma = _positive_finite(sigma_horizon, "sigma_horizon")
    fraction = _fraction(time_fraction)
    intervals = _integer_at_least(
        spatial_intervals,
        "spatial_intervals",
        40,
    )
    steps = _integer_at_least(time_steps, "time_steps", 10)
    if fraction == 0:
        return IndependentOracleResult(
            p_tp=0.0,
            p_sl=0.0,
            p_expiry=1.0,
            spatial_intervals=intervals,
            time_steps=steps,
            mass_error=0.0,
        )

    length = tp_distance + sl_distance
    dx = length / intervals
    dt = fraction / steps
    diffusion = sigma * sigma / 2.0
    ratio = diffusion * dt / (dx * dx)
    interior_size = intervals - 1
    diagonal = 1.0 + 2.0 * ratio
    off_diagonal = -ratio
    c_prime, inverse_denominator = _tridiagonal_plan(
        interior_size,
        diagonal,
        off_diagonal,
    )

    upper = [0.0] * interior_size
    lower = [0.0] * interior_size
    for _ in range(steps):
        upper_rhs = upper.copy()
        lower_rhs = lower.copy()
        upper_rhs[-1] += ratio
        lower_rhs[0] += ratio
        upper = _solve_with_plan(
            upper_rhs,
            off_diagonal=off_diagonal,
            c_prime=c_prime,
            inverse_denominator=inverse_denominator,
        )
        lower = _solve_with_plan(
            lower_rhs,
            off_diagonal=off_diagonal,
            c_prime=c_prime,
            inverse_denominator=inverse_denominator,
        )

    start_position = sl_distance / dx
    p_tp = _interpolate_grid_value(
        upper,
        start_position,
        intervals,
        left_boundary=0.0,
        right_boundary=1.0,
    )
    p_sl = _interpolate_grid_value(
        lower,
        start_position,
        intervals,
        left_boundary=1.0,
        right_boundary=0.0,
    )
    p_expiry = 1.0 - p_tp - p_sl
    numerical_tolerance = 1e-9
    if -numerical_tolerance < p_expiry < 0:
        p_expiry = 0.0
    if min(p_tp, p_sl, p_expiry) < 0 or max(p_tp, p_sl, p_expiry) > 1:
        raise RuntimeError("independent_oracle_probability_out_of_bounds")
    mass_error = abs(p_tp + p_sl + p_expiry - 1.0)
    return IndependentOracleResult(
        p_tp=p_tp,
        p_sl=p_sl,
        p_expiry=p_expiry,
        spatial_intervals=intervals,
        time_steps=steps,
        mass_error=mass_error,
    )
