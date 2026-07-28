from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

from m6_first_passage import double_barrier_first_passage


LAYER_VERSION = "M6-discrete-competing-risks-v0.2"
ESTIMATED_STATUS = "estimated_internal_candidate"
LOCKED_STATUS = "locked_no_estimated_coefficients"
MAX_INTERVAL_COUNT = 4096


class EvidenceArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class CompetingRiskResult:
    p_tp: float
    p_sl: float
    p_expiry: float
    evidence_status: str
    coefficient_artifact_id: str | None
    interval_count: int
    intervals: tuple[dict, ...]
    mass_error: float
    layer_version: str = LAYER_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceArtifactError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number):
        raise EvidenceArtifactError(f"{name}_must_be_finite")
    return number


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
    intervals = []
    for index in range(1, interval_count + 1):
        previous = cumulative[index - 1]
        current = cumulative[index]
        survival_before = previous.p_expiry
        if survival_before <= 0:
            raise EvidenceArtifactError("baseline_survival_exhausted_before_horizon")
        delta_tp = max(0.0, current.p_tp - previous.p_tp)
        delta_sl = max(0.0, current.p_sl - previous.p_sl)
        h_tp = delta_tp / survival_before
        h_sl = delta_sl / survival_before
        h_none = 1.0 - h_tp - h_sl
        if h_none < -1e-10:
            raise EvidenceArtifactError("baseline_interval_hazard_mass_invalid")
        h_none = max(0.0, h_none)
        intervals.append(
            {
                "interval": index,
                "time_fraction_start": (index - 1) / interval_count,
                "time_fraction_end": index / interval_count,
                "survival_before": survival_before,
                "baseline_h_tp": h_tp,
                "baseline_h_sl": h_sl,
                "baseline_h_none": h_none,
                "baseline_cumulative_tp": current.p_tp,
                "baseline_cumulative_sl": current.p_sl,
                "baseline_survival_after": current.p_expiry,
            }
        )
    return tuple(intervals)


def validate_artifact(
    artifact: dict | None,
    features: dict[str, float],
) -> tuple[str, dict | None]:
    if artifact is None:
        return "baseline_only_no_artifact", None
    if not isinstance(artifact, dict):
        raise EvidenceArtifactError("coefficient_artifact_must_be_object")
    status = artifact.get("status")
    if status == LOCKED_STATUS:
        if artifact.get("coefficients") not in (None, {}, {"tp": {}, "sl": {}}):
            raise EvidenceArtifactError("locked_artifact_contains_coefficients")
        return "baseline_only_coefficients_locked", None
    if status != ESTIMATED_STATUS:
        raise EvidenceArtifactError("coefficient_artifact_status_not_allowed")
    if artifact.get("provenance") != "estimated_temporal_training":
        raise EvidenceArtifactError("manual_or_unknown_coefficient_provenance")
    if artifact.get("production_authorized") is not False:
        raise EvidenceArtifactError("coefficient_artifact_production_scope_invalid")
    if not artifact.get("training_cutoff"):
        raise EvidenceArtifactError("coefficient_artifact_training_cutoff_missing")
    coefficients = artifact.get("coefficients")
    if not isinstance(coefficients, dict) or set(coefficients) != {"tp", "sl"}:
        raise EvidenceArtifactError("coefficient_causes_must_be_tp_sl")
    tp_coefficients = coefficients["tp"]
    sl_coefficients = coefficients["sl"]
    if (
        not isinstance(tp_coefficients, dict)
        or not isinstance(sl_coefficients, dict)
        or set(tp_coefficients) != set(sl_coefficients)
    ):
        raise EvidenceArtifactError("coefficient_feature_schema_mismatch")
    if set(features) != set(tp_coefficients):
        raise EvidenceArtifactError("feature_snapshot_schema_mismatch")
    expected_hash = canonical_sha256(sorted(features))
    if artifact.get("feature_schema_sha256") != expected_hash:
        raise EvidenceArtifactError("feature_schema_hash_mismatch")
    for cause, values in coefficients.items():
        for feature, value in values.items():
            finite(value, f"{cause}_{feature}_coefficient")
    for feature, value in features.items():
        finite(value, f"{feature}_value")
    return "estimated_evidence_applied", artifact


def linear_predictor(coefficients: dict, features: dict) -> float:
    value = math.fsum(
        finite(coefficients[name], f"coefficient_{name}")
        * finite(features[name], f"feature_{name}")
        for name in sorted(features)
    )
    if not math.isfinite(value):
        raise EvidenceArtifactError("linear_predictor_must_be_finite")
    return value


def adjusted_interval_hazards(
    baseline: dict,
    eta_tp: float,
    eta_sl: float,
) -> tuple[float, float, float]:
    h_tp = baseline["baseline_h_tp"]
    h_sl = baseline["baseline_h_sl"]
    h_none = baseline["baseline_h_none"]
    log_tp = math.log(h_tp) + eta_tp if h_tp > 0 else -math.inf
    log_sl = math.log(h_sl) + eta_sl if h_sl > 0 else -math.inf
    log_none = math.log(h_none) if h_none > 0 else -math.inf
    maximum = max(log_tp, log_sl, log_none)
    weighted_tp = math.exp(log_tp - maximum) if h_tp > 0 else 0.0
    weighted_sl = math.exp(log_sl - maximum) if h_sl > 0 else 0.0
    weighted_none = math.exp(log_none - maximum) if h_none > 0 else 0.0
    denominator = weighted_none + weighted_tp + weighted_sl
    if denominator <= 0 or not math.isfinite(denominator):
        raise EvidenceArtifactError("adjusted_hazard_denominator_invalid")
    return (
        weighted_tp / denominator,
        weighted_sl / denominator,
        weighted_none / denominator,
    )


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
    )
