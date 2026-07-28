from __future__ import annotations

import hashlib
import json
from typing import Any


AUDIT_VERSION = "M7-trace-audit-v0.1"


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_result_integrity(result: Any) -> tuple[str, ...]:
    if not isinstance(result, dict):
        return ("result_must_be_object",)
    issues = []
    stored_hash = result.get("result_sha256")
    if not isinstance(stored_hash, str) or len(stored_hash) != 64:
        issues.append("result_hash_missing_or_invalid")
    else:
        payload = {
            key: value
            for key, value in result.items()
            if key != "result_sha256"
        }
        if canonical_sha256(payload) != stored_hash:
            issues.append("result_hash_mismatch")
    if result.get("status") != "evaluated_internal_only":
        issues.append("result_not_evaluated")
    probabilities = result.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != {
        "tp_first_within_horizon",
        "sl_first_within_horizon",
        "neither_barrier_before_expiry",
    }:
        issues.append("probability_schema_invalid")
    elif abs(sum(probabilities.values()) - 1.0) > 1e-12:
        issues.append("probability_mass_invalid")
    trace = result.get("trace")
    if not isinstance(trace, dict):
        issues.append("trace_missing")
    else:
        required = {
            "source_rule_trace_hashes",
            "inputs",
            "formulas",
            "baseline",
            "evidence",
            "uncertainty",
            "assumptions",
            "limitations",
            "probability_mass_error",
        }
        if not required.issubset(trace):
            issues.append("trace_fields_incomplete")
        hashes = trace.get("source_rule_trace_hashes")
        if not isinstance(hashes, dict) or any(
            not isinstance(value, str) or len(value) != 64
            for value in hashes.values()
        ):
            issues.append("source_trace_hash_invalid")
    if result.get("production_effect") != "none":
        issues.append("production_boundary_invalid")
    return tuple(issues)


def explain_probability_result(result: dict) -> dict:
    issues = verify_result_integrity(result)
    if issues:
        return {
            "status": "blocked",
            "reason_codes": list(issues),
            "explanation": None,
            "audit_version": AUDIT_VERSION,
        }
    trace = result["trace"]
    explanation = {
        "analysis_id": result["analysis_id"],
        "outcomes": result["probabilities"],
        "geometry_and_horizon": trace["inputs"],
        "baseline": {
            "method": trace["baseline"]["numerical_method"],
            "solver_version": trace["baseline"]["solver_version"],
            "terms_used": trace["baseline"]["terms_used"],
            "absolute_error_bound": trace["baseline"][
                "absolute_error_bound"
            ],
        },
        "evidence": {
            "status": trace["evidence"]["evidence_status"],
            "coefficient_artifact_id": trace["evidence"][
                "coefficient_artifact_id"
            ],
        },
        "uncertainty": trace["uncertainty"],
        "formula_ids": trace["formulas"],
        "source_rule_trace_hashes": trace["source_rule_trace_hashes"],
        "assumptions": trace["assumptions"],
        "limitations": trace["limitations"],
        "production_effect": "none",
    }
    return {
        "status": "explained",
        "reason_codes": [],
        "explanation": explanation,
        "explanation_sha256": canonical_sha256(explanation),
        "audit_version": AUDIT_VERSION,
    }
