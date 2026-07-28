from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from build_m7_trace_verification import (
    FIXED_TIME,
    PREDECLARED_CASES,
    m5_analysis,
)
from m6_competing_risks import (
    MAX_INTERVAL_COUNT,
    apply_competing_risk_evidence,
    canonical_sha256,
)
from m6_engine import run_internal_probability_analysis
from m6_first_passage import double_barrier_first_passage


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M7_CONTRACT_PATH = AUDIT_DIR / "contrato_verificacion_m7_1_v0_1.json"
PRE_CORRECTION_PATH = (
    AUDIT_DIR
    / "2026-07-28_M7_6_defectos_resiliencia_pre_correccion_v0_1.json"
)
CORRECTION_PATH = (
    AUDIT_DIR / "2026-07-28_M7_6_correcciones_resiliencia_v0_1.json"
)
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "verificacion_resiliencia_m7_6_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M7_6_rendimiento_resiliencia_v0_1.md"
)
VERSION = "M7.6-resilience-verification-v0.1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_record(path: Path) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def estimated_artifact(
    *,
    tp_beta: float,
    sl_beta: float,
) -> tuple[dict, dict]:
    features = {"x": 1.0}
    artifact = {
        "id": "M7-FAULT-INJECTION",
        "status": "estimated_internal_candidate",
        "provenance": "estimated_temporal_training",
        "production_authorized": False,
        "training_cutoff": "2026-01-01T00:00:00Z",
        "coefficients": {
            "tp": {"x": tp_beta},
            "sl": {"x": sl_beta},
        },
        "feature_schema_sha256": canonical_sha256(sorted(features)),
    }
    return features, artifact


def run_engine(**kwargs) -> dict:
    parameters = {
        "analysis_id": "m7-fault",
        "m5_analysis": m5_analysis(PREDECLARED_CASES[0]),
        "executed_at": FIXED_TIME,
    }
    parameters.update(kwargs)
    return run_internal_probability_analysis(**parameters)


def fault_cases() -> list[dict]:
    cases = []

    def record(name: str, expected: str, call: Callable[[], dict]) -> None:
        try:
            result = call()
            observed = result.get("status")
            unhandled = None
        except Exception as exc:
            result = {}
            observed = "unhandled_exception"
            unhandled = f"{type(exc).__name__}:{exc}"
        cases.append(
            {
                "name": name,
                "expected_status": expected,
                "observed_status": observed,
                "block_code": result.get("block_code"),
                "unhandled_exception": unhandled,
                "passed": observed == expected and unhandled is None,
            }
        )

    features, extreme = estimated_artifact(tp_beta=1000.0, sl_beta=-1000.0)
    record(
        "finite_extreme_predictor",
        "evaluated_internal_only",
        lambda: run_engine(
            feature_snapshot=features,
            coefficient_artifact=extreme,
        ),
    )
    huge_features, huge = estimated_artifact(
        tp_beta=1e308,
        sl_beta=-1e308,
    )
    huge_features["x"] = 1e308
    record(
        "non_finite_linear_predictor",
        "blocked",
        lambda: run_engine(
            feature_snapshot=huge_features,
            coefficient_artifact=huge,
        ),
    )
    record(
        "boolean_interval_count",
        "blocked",
        lambda: run_engine(interval_count=True),
    )
    record(
        "oversized_interval_count",
        "blocked",
        lambda: run_engine(interval_count=MAX_INTERVAL_COUNT + 1),
    )
    record(
        "zero_interval_count",
        "blocked",
        lambda: run_engine(interval_count=0),
    )

    duplicate = m5_analysis(PREDECLARED_CASES[0])
    duplicate["traces"].append(deepcopy(duplicate["traces"][0]))
    record(
        "duplicate_m5_trace",
        "blocked",
        lambda: run_engine(m5_analysis=duplicate),
    )
    missing = m5_analysis(PREDECLARED_CASES[0])
    missing["traces"] = []
    record(
        "missing_required_m5_trace",
        "blocked",
        lambda: run_engine(m5_analysis=missing),
    )
    production = m5_analysis(PREDECLARED_CASES[0])
    production["production_effect"] = "changed"
    record(
        "invalid_production_boundary",
        "blocked",
        lambda: run_engine(m5_analysis=production),
    )
    record(
        "invalid_sigma_envelope",
        "blocked",
        lambda: run_engine(sigma_scenarios={"low": 0.03, "high": 0.01}),
    )
    record(
        "invalid_interval_type",
        "blocked",
        lambda: run_engine(interval_count="24"),
    )
    locked_with_values = {
        "id": "BAD-LOCK",
        "status": "locked_no_estimated_coefficients",
        "coefficients": {"tp": {"x": 1.0}, "sl": {"x": 1.0}},
    }
    record(
        "locked_artifact_hides_values",
        "blocked",
        lambda: run_engine(coefficient_artifact=locked_with_values),
    )
    features, mismatch = estimated_artifact(tp_beta=1.0, sl_beta=1.0)
    mismatch["feature_schema_sha256"] = "bad"
    record(
        "feature_schema_hash_mismatch",
        "blocked",
        lambda: run_engine(
            feature_snapshot=features,
            coefficient_artifact=mismatch,
        ),
    )
    return cases


def benchmark_buckets() -> dict:
    solver_calls = 200
    start = time.perf_counter()
    for index in range(solver_calls):
        double_barrier_first_passage(
            tp_log_distance=0.01 + (index % 7) * 0.005,
            sl_log_distance=0.015 + (index % 5) * 0.006,
            sigma_horizon=0.04,
        )
    solver_average_ms = (
        (time.perf_counter() - start) * 1000 / solver_calls
    )

    engine_calls = 50
    source = m5_analysis(PREDECLARED_CASES[0])
    start = time.perf_counter()
    for index in range(engine_calls):
        run_internal_probability_analysis(
            analysis_id=f"benchmark-{index}",
            m5_analysis=source,
            executed_at=FIXED_TIME,
        )
    engine_average_ms = (
        (time.perf_counter() - start) * 1000 / engine_calls
    )

    interval_count = 512
    start = time.perf_counter()
    apply_competing_risk_evidence(
        tp_log_distance=0.03,
        sl_log_distance=0.05,
        sigma_horizon=0.04,
        interval_count=interval_count,
    )
    interval_total_ms = (time.perf_counter() - start) * 1000
    return {
        "measurement_retention": (
            "pass_fail_bucket_only_to_keep_artifact_reproducible"
        ),
        "solver": {
            "calls": solver_calls,
            "budget_average_ms": 5.0,
            "within_budget": solver_average_ms <= 5.0,
        },
        "engine": {
            "calls": engine_calls,
            "budget_average_ms": 50.0,
            "within_budget": engine_average_ms <= 50.0,
        },
        "interval_stress": {
            "interval_count": interval_count,
            "budget_total_ms": 2000.0,
            "within_budget": interval_total_ms <= 2000.0,
        },
    }


def build_verification() -> dict:
    faults = fault_cases()
    benchmarks = benchmark_buckets()
    fault_passed = all(item["passed"] for item in faults)
    no_unhandled = all(item["unhandled_exception"] is None for item in faults)
    performance_passed = all(
        benchmarks[key]["within_budget"]
        for key in ("solver", "engine", "interval_stress")
    )
    passed = fault_passed and no_unhandled and performance_passed
    payload = {
        "version": VERSION,
        "phase": "M7",
        "subphase": "M7.6",
        "status": "passed" if passed else "failed",
        "date": "2026-07-28",
        "fault_injection_cases": faults,
        "performance_buckets": benchmarks,
        "resource_contract": {
            "minimum_interval_count": 1,
            "maximum_interval_count": MAX_INTERVAL_COUNT,
            "boolean_is_not_integer_count": True,
            "oversized_count_fails_before_iteration": True,
        },
        "corrected_defects": [
            "M7-DEFECT-NUMERIC-002",
            "M7-DEFECT-RESOURCE-003",
        ],
        "summary": {
            "fault_cases_total": len(faults),
            "fault_cases_passed": sum(item["passed"] for item in faults),
            "unhandled_exceptions": sum(
                item["unhandled_exception"] is not None for item in faults
            ),
            "performance_buckets_passed": sum(
                benchmarks[key]["within_budget"]
                for key in ("solver", "engine", "interval_stress")
            ),
            "critical_defects_open": 0 if passed else 1,
            "high_defects_open": 0 if passed else 1,
        },
        "limitations": [
            "Latency budgets are internal engineering limits, not exchange SLA.",
            "Benchmarks run on synthetic local inputs without network latency.",
            "Pass/fail buckets are retained instead of volatile exact timings.",
        ],
        "boundaries": {
            "production_effect": "none",
            "calibration_performed": False,
            "m8_started": False,
        },
        "inputs": [
            artifact_record(M7_CONTRACT_PATH),
            artifact_record(PRE_CORRECTION_PATH),
            artifact_record(CORRECTION_PATH),
            artifact_record(ROOT / "m6_competing_risks.py"),
            artifact_record(ROOT / "m6_engine.py"),
        ],
        "next_step": {
            "id": "M7.7",
            "name": "Revision independiente de codigo y formulas",
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(payload: dict) -> str:
    summary = payload["summary"]
    return "\n".join(
        [
            "# M7.6 - Rendimiento y tolerancia a fallos",
            "",
            "Fecha: 2026-07-28",
            f"Estado: {payload['status']}",
            "",
            "## Fallos",
            "",
            (
                f"- Casos superados: {summary['fault_cases_passed']}/"
                f"{summary['fault_cases_total']}."
            ),
            f"- Excepciones no controladas: {summary['unhandled_exceptions']}.",
            "- Defectos M7-DEFECT-NUMERIC-002 y RESOURCE-003: corregidos.",
            "",
            "## Rendimiento",
            "",
            (
                "- Presupuestos superados: "
                f"{summary['performance_buckets_passed']}/3."
            ),
            "- Solver medio <= 5 ms.",
            "- Motor probabilistico medio <= 50 ms.",
            "- Discretizacion de 512 intervalos <= 2000 ms.",
            "",
            "## Limites",
            "",
            "- Medicion local sintetica, sin red ni SLA de exchange.",
            "- Produccion y M8 permanecen intactas.",
            "",
            "Siguiente subfase: M7.7.",
            "",
            "SHA-256 del payload canonico: "
            f"`{payload['canonical_payload_sha256']}`.",
            "",
        ]
    )


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            raise SystemExit(f"Generated artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_verification()
    write_or_check(
        DEFAULT_OUTPUT_PATH,
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(DEFAULT_REPORT_PATH, render_report(payload), args.check)


if __name__ == "__main__":
    main()
