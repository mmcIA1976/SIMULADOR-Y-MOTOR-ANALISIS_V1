from __future__ import annotations

import math

from m6_competing_risks import (
    CompetingRiskResult,
    EvidenceArtifactError,
    MAX_INTERVAL_COUNT,
    adjusted_interval_hazards,
    finite,
    linear_predictor,
    validate_artifact,
)
from m6_first_passage import double_barrier_first_passage


LAYER_VERSION = "M6-R1-discrete-competing-risks-v0.1"
NUMERICAL_SURVIVAL_FLOOR = 1e-10


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
        raise EvidenceArtifactError("interval_count_must_be_positive_integer")
    cumulative = [
        double_barrier_first_passage(
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
                    "time_fraction_start": (index - 1) / interval_count,
                    "time_fraction_end": index / interval_count,
                    "survival_before": 0.0,
                    "baseline_h_tp": 0.0,
                    "baseline_h_sl": 0.0,
                    "baseline_h_none": 1.0,
                    "baseline_cumulative_tp": final.p_tp,
                    "baseline_cumulative_sl": final.p_sl,
                    "baseline_survival_after": final.p_expiry,
                    "terminal_reconciliation": "post_absorption_neutral_interval",
                    "numerical_survival_floor": NUMERICAL_SURVIVAL_FLOOR,
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
            intervals.append(
                {
                    "interval": index,
                    "time_fraction_start": (index - 1) / interval_count,
                    "time_fraction_end": index / interval_count,
                    "survival_before": survival_before,
                    "baseline_h_tp": h_tp,
                    "baseline_h_sl": h_sl,
                    "baseline_h_none": h_none,
                    "baseline_cumulative_tp": final.p_tp,
                    "baseline_cumulative_sl": final.p_sl,
                    "baseline_survival_after": final.p_expiry,
                    "terminal_reconciliation": "machine_precision_absorption",
                    "numerical_survival_floor": NUMERICAL_SURVIVAL_FLOOR,
                }
            )
            terminal_reconciled = True
            continue
        delta_tp = max(0.0, current.p_tp - previous.p_tp)
        delta_sl = max(0.0, current.p_sl - previous.p_sl)
        h_tp = delta_tp / survival_before
        h_sl = delta_sl / survival_before
        h_none = 1.0 - h_tp - h_sl
        if h_none < -1e-10:
            raise EvidenceArtifactError("baseline_interval_hazard_mass_invalid")
        intervals.append(
            {
                "interval": index,
                "time_fraction_start": (index - 1) / interval_count,
                "time_fraction_end": index / interval_count,
                "survival_before": survival_before,
                "baseline_h_tp": h_tp,
                "baseline_h_sl": h_sl,
                "baseline_h_none": max(0.0, h_none),
                "baseline_cumulative_tp": current.p_tp,
                "baseline_cumulative_sl": current.p_sl,
                "baseline_survival_after": current.p_expiry,
                "terminal_reconciliation": None,
                "numerical_survival_floor": NUMERICAL_SURVIVAL_FLOOR,
            }
        )
    return tuple(intervals)


def apply_competing_risk_evidence(
    *,
    tp_log_distance: float,
    sl_log_distance: float,
    sigma_horizon: float,
    interval_count: int = 24,
    features: dict[str, float] | None = None,
    coefficient_artifact: dict | None = None,
) -> CompetingRiskResult:
    feature_values = features or {}
    evidence_status, validated_artifact = validate_artifact(
        coefficient_artifact,
        feature_values,
    )
    baseline_intervals = build_baseline_intervals(
        tp_log_distance=tp_log_distance,
        sl_log_distance=sl_log_distance,
        sigma_horizon=sigma_horizon,
        interval_count=interval_count,
    )
    if validated_artifact is None:
        eta_tp = 0.0
        eta_sl = 0.0
        artifact_id = (
            coefficient_artifact.get("id")
            if isinstance(coefficient_artifact, dict)
            else None
        )
    else:
        eta_tp = linear_predictor(
            validated_artifact["coefficients"]["tp"],
            feature_values,
        )
        eta_sl = linear_predictor(
            validated_artifact["coefficients"]["sl"],
            feature_values,
        )
        artifact_id = str(validated_artifact.get("id") or "")
        if not artifact_id:
            raise EvidenceArtifactError("coefficient_artifact_id_missing")

    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    traced_intervals = []
    for baseline in baseline_intervals:
        h_tp, h_sl, h_none = adjusted_interval_hazards(
            baseline,
            eta_tp,
            eta_sl,
        )
        incidence_tp = survival * h_tp
        incidence_sl = survival * h_sl
        cumulative_tp += incidence_tp
        cumulative_sl += incidence_sl
        survival *= h_none
        traced_intervals.append(
            baseline
            | {
                "eta_tp": eta_tp,
                "eta_sl": eta_sl,
                "adjusted_h_tp": h_tp,
                "adjusted_h_sl": h_sl,
                "adjusted_h_none": h_none,
                "adjusted_incidence_tp": incidence_tp,
                "adjusted_incidence_sl": incidence_sl,
                "adjusted_cumulative_tp": cumulative_tp,
                "adjusted_cumulative_sl": cumulative_sl,
                "adjusted_survival_after": survival,
            }
        )
    mass_error = abs(cumulative_tp + cumulative_sl + survival - 1.0)
    if mass_error > 1e-12:
        raise EvidenceArtifactError("competing_risk_probability_mass_invalid")
    return CompetingRiskResult(
        p_tp=cumulative_tp,
        p_sl=cumulative_sl,
        p_expiry=survival,
        evidence_status=evidence_status,
        coefficient_artifact_id=artifact_id,
        interval_count=interval_count,
        intervals=tuple(traced_intervals),
        mass_error=mass_error,
        layer_version=LAYER_VERSION,
    )
