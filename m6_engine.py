from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

from m6_competing_risks import (
    EvidenceArtifactError,
    apply_competing_risk_evidence,
)
from m6_first_passage import (
    FirstPassageConvergenceError,
    FirstPassageInputError,
    double_barrier_first_passage,
)


ENGINE_VERSION = "M6-internal-probability-engine-v0.1"
REQUIRED_M5_TRACES = (
    "M4-RULE-HORIZON-SAMPLING-001",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def blocked_result(
    *,
    analysis_id: str,
    code: str,
    details: dict | None = None,
    executed_at: str | None = None,
) -> dict:
    result = {
        "engine_version": ENGINE_VERSION,
        "analysis_id": analysis_id,
        "executed_at": executed_at or utc_now_iso(),
        "status": "blocked",
        "block_code": code,
        "details": details or {},
        "probabilities": None,
        "trace": None,
        "production_effect": "none",
        "m7_started": False,
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def m5_trace_map(m5_analysis: dict) -> dict[str, dict]:
    traces = m5_analysis.get("traces")
    if not isinstance(traces, list):
        raise ValueError("m5_traces_missing")
    registry = {
        trace.get("rule_id"): trace
        for trace in traces
        if isinstance(trace, dict) and trace.get("rule_id")
    }
    if len(registry) != len(traces):
        raise ValueError("m5_trace_ids_invalid_or_duplicate")
    return registry


def probability_envelope(
    *,
    tp_log_distance: float,
    sl_log_distance: float,
    sigma_horizon: float,
    sigma_scenarios: dict | None,
) -> dict:
    if sigma_scenarios is None:
        return {
            "status": "not_quantified_no_sigma_interval",
            "interpretation": (
                "point probabilities are conditional on sigma_horizon; "
                "they are not a confidence interval"
            ),
            "sigma_values": [sigma_horizon],
            "probability_envelope": None,
        }
    if set(sigma_scenarios) != {"low", "high"}:
        raise ValueError("sigma_scenarios_must_have_low_high")
    low = float(sigma_scenarios["low"])
    high = float(sigma_scenarios["high"])
    if (
        not math.isfinite(low)
        or not math.isfinite(high)
        or low <= 0
        or high <= 0
        or low > sigma_horizon
        or high < sigma_horizon
    ):
        raise ValueError("sigma_scenarios_must_bracket_point_sigma")
    values = [low, sigma_horizon, high]
    scenarios = [
        double_barrier_first_passage(
            tp_log_distance=tp_log_distance,
            sl_log_distance=sl_log_distance,
            sigma_horizon=value,
        )
        for value in values
    ]
    return {
        "status": "scenario_envelope_not_confidence_interval",
        "interpretation": (
            "range across supplied sigma scenarios; coverage is not claimed"
        ),
        "sigma_values": values,
        "probability_envelope": {
            "p_tp": [
                min(item.p_tp for item in scenarios),
                max(item.p_tp for item in scenarios),
            ],
            "p_sl": [
                min(item.p_sl for item in scenarios),
                max(item.p_sl for item in scenarios),
            ],
            "p_expiry": [
                min(item.p_expiry for item in scenarios),
                max(item.p_expiry for item in scenarios),
            ],
        },
    }


def run_internal_probability_analysis(
    *,
    analysis_id: str,
    m5_analysis: dict,
    feature_snapshot: dict[str, float] | None = None,
    coefficient_artifact: dict | None = None,
    sigma_scenarios: dict | None = None,
    interval_count: int = 24,
    executed_at: str | None = None,
) -> dict:
    if not analysis_id:
        raise ValueError("analysis_id_required")
    timestamp = executed_at or utc_now_iso()
    if m5_analysis.get("production_effect") != "none":
        return blocked_result(
            analysis_id=analysis_id,
            code="m5_production_boundary_invalid",
            executed_at=timestamp,
        )
    try:
        traces = m5_trace_map(m5_analysis)
    except ValueError as exc:
        return blocked_result(
            analysis_id=analysis_id,
            code=str(exc),
            executed_at=timestamp,
        )
    missing = [rule_id for rule_id in REQUIRED_M5_TRACES if rule_id not in traces]
    if missing:
        return blocked_result(
            analysis_id=analysis_id,
            code="required_m5_trace_missing",
            details={"rule_ids": missing},
            executed_at=timestamp,
        )
    unavailable = [
        rule_id
        for rule_id in REQUIRED_M5_TRACES
        if traces[rule_id].get("status") != "evaluated"
    ]
    if unavailable:
        return blocked_result(
            analysis_id=analysis_id,
            code="required_m5_trace_not_evaluated",
            details={"rule_ids": unavailable},
            executed_at=timestamp,
        )

    sampling = traces["M4-RULE-HORIZON-SAMPLING-001"]["outputs"]
    geometry = traces[
        "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002"
    ]["outputs"]
    try:
        tp_distance = float(geometry["tp_log_distance"])
        sl_distance = float(geometry["sl_log_distance"])
        sigma = float(geometry["sigma_prev_horizon"])
        horizon_seconds = int(sampling["horizon_seconds"])
        baseline = double_barrier_first_passage(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=sigma,
        )
        evidence = apply_competing_risk_evidence(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=sigma,
            interval_count=interval_count,
            features=feature_snapshot,
            coefficient_artifact=coefficient_artifact,
        )
        uncertainty = probability_envelope(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=sigma,
            sigma_scenarios=sigma_scenarios,
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        ArithmeticError,
        FirstPassageInputError,
        FirstPassageConvergenceError,
        EvidenceArtifactError,
    ) as exc:
        return blocked_result(
            analysis_id=analysis_id,
            code="probability_input_or_solver_invalid",
            details={
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
            executed_at=timestamp,
        )

    probabilities = {
        "tp_first_within_horizon": evidence.p_tp,
        "sl_first_within_horizon": evidence.p_sl,
        "neither_barrier_before_expiry": evidence.p_expiry,
    }
    mass_error = abs(sum(probabilities.values()) - 1.0)
    if mass_error > 1e-12:
        return blocked_result(
            analysis_id=analysis_id,
            code="probability_mass_invalid",
            details={"mass_error": mass_error},
            executed_at=timestamp,
        )
    source_trace_hashes = {
        rule_id: traces[rule_id].get("trace_sha256")
        for rule_id in REQUIRED_M5_TRACES
    }
    trace = {
        "trace_version": "M6-probability-trace-v0.1",
        "m5_analysis_id": m5_analysis.get("analysis_id"),
        "m5_analysis_trace_sha256": m5_analysis.get(
            "analysis_trace_sha256"
        ),
        "source_rule_trace_hashes": source_trace_hashes,
        "inputs": {
            "horizon_seconds": horizon_seconds,
            "tp_log_distance": tp_distance,
            "sl_log_distance": sl_distance,
            "sigma_horizon": sigma,
            "interval_count": interval_count,
        },
        "formulas": [
            "M6-FORMULA-DB-TRANSITION-001",
            "M6-FORMULA-DB-TP-002",
            "M6-FORMULA-DB-SL-003",
            "M6-FORMULA-DB-EXPIRY-004",
            "M6-FORMULA-INTERVAL-HAZARD-005",
            "M6-FORMULA-EVIDENCE-OFFSET-006",
            "M6-FORMULA-CIF-007",
            "M6-FORMULA-SURVIVAL-008",
        ],
        "baseline": baseline.to_dict(),
        "evidence": evidence.to_dict(),
        "uncertainty": uncertainty,
        "assumptions": [
            "zero drift",
            "continuous log-price diffusion baseline",
            "sigma_horizon is total volatility for the exact horizon",
            "constant barriers during the horizon",
            "no manual evidence coefficients",
        ],
        "limitations": [
            "Brownian adequacy is not established",
            "point sigma is not a confidence interval",
            "predictive calibration remains unverified",
            "profitability is not implied",
        ],
        "probability_mass_error": mass_error,
        "production_effect": "none",
    }
    result = {
        "engine_version": ENGINE_VERSION,
        "analysis_id": analysis_id,
        "executed_at": timestamp,
        "status": "evaluated_internal_only",
        "block_code": None,
        "probabilities": probabilities,
        "trace": trace,
        "production_effect": "none",
        "m7_started": False,
    }
    result["result_sha256"] = canonical_sha256(result)
    return result
