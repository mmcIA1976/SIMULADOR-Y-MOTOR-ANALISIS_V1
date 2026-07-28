from __future__ import annotations

from m6_competing_risks import EvidenceArtifactError
from m6_engine import (
    REQUIRED_M5_TRACES,
    blocked_result,
    canonical_sha256,
    m5_trace_map,
    probability_envelope,
    utc_now_iso,
)
from m6_first_passage import (
    FirstPassageConvergenceError,
    FirstPassageInputError,
    double_barrier_first_passage,
)
from m6_remediated_competing_risks import apply_competing_risk_evidence


ENGINE_VERSION = "M6-R1-internal-probability-engine-v0.1"


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
        result = blocked_result(
            analysis_id=analysis_id,
            code="probability_input_or_solver_invalid",
            details={
                "exception_type": type(exc).__name__,
                "message": str(exc),
            },
            executed_at=timestamp,
        )
        result["engine_version"] = ENGINE_VERSION
        result["result_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in result.items()
                if key != "result_sha256"
            }
        )
        return result

    probabilities = {
        "tp_first_within_horizon": evidence.p_tp,
        "sl_first_within_horizon": evidence.p_sl,
        "neither_barrier_before_expiry": evidence.p_expiry,
    }
    mass_error = abs(sum(probabilities.values()) - 1.0)
    if mass_error > 1e-12:
        result = blocked_result(
            analysis_id=analysis_id,
            code="probability_mass_invalid",
            details={"mass_error": mass_error},
            executed_at=timestamp,
        )
        result["engine_version"] = ENGINE_VERSION
        result["result_sha256"] = canonical_sha256(
            {
                key: value
                for key, value in result.items()
                if key != "result_sha256"
            }
        )
        return result
    trace = {
        "trace_version": "M6-R1-probability-trace-v0.1",
        "m5_analysis_id": m5_analysis.get("analysis_id"),
        "m5_analysis_trace_sha256": m5_analysis.get(
            "analysis_trace_sha256"
        ),
        "source_rule_trace_hashes": {
            rule_id: traces[rule_id].get("trace_sha256")
            for rule_id in REQUIRED_M5_TRACES
        },
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
            "M6-R1-NUMERICAL-TERMINAL-RECONCILIATION-009",
        ],
        "baseline": baseline.to_dict(),
        "evidence": evidence.to_dict(),
        "uncertainty": uncertainty,
        "remediation": {
            "id": "M6-R1",
            "scope": "machine_precision_terminal_survival_only",
            "historical_m6_modified": False,
        },
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
            "predictive calibration requires a new temporal holdout",
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
        "m9_started": False,
    }
    result["result_sha256"] = canonical_sha256(result)
    return result
