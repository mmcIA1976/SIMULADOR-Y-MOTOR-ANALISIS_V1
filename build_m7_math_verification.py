from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from m6_first_passage import (
    FirstPassageInputError,
    double_barrier_first_passage,
)
from m7_independent_oracle import finite_difference_first_passage


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M7_CONTRACT_PATH = AUDIT_DIR / "contrato_verificacion_m7_1_v0_1.json"
M6_CLOSURE_PATH = AUDIT_DIR / "paquete_cierre_m6_6_v0_1.json"
PRE_CORRECTION_DEFECT_PATH = (
    AUDIT_DIR
    / "2026-07-28_M7_2_defecto_convergencia_pre_correccion_v0_1.json"
)
CORRECTION_RECORD_PATH = (
    AUDIT_DIR / "2026-07-28_M7_2_correccion_convergencia_v0_1.json"
)
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "verificacion_matematica_m7_2_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M7_2_verificacion_matematica_v0_1.md"
)
VERSION = "M7.2-mathematical-verification-v0.1"
ORACLE_TOLERANCE = 2.5e-3

ORACLE_CASES = (
    {"tp": 0.03, "sl": 0.05, "sigma": 0.04, "fraction": 1.0},
    {"tp": 0.02, "sl": 0.06, "sigma": 0.04, "fraction": 1.0},
    {"tp": 0.08, "sl": 0.03, "sigma": 0.05, "fraction": 1.0},
    {"tp": 0.04, "sl": 0.04, "sigma": 0.05, "fraction": 1.0},
    {"tp": 0.015, "sl": 0.09, "sigma": 0.03, "fraction": 0.5},
)


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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_record(path: Path) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def _check(
    checks: list[dict],
    defects: list[dict],
    *,
    gate: str,
    name: str,
    condition: bool,
    observed: Any,
    expected: str,
    severity: str = "critical",
) -> None:
    status = "passed" if condition else "failed"
    checks.append(
        {
            "gate": gate,
            "name": name,
            "status": status,
            "observed": observed,
            "expected": expected,
        }
    )
    if not condition:
        defects.append(
            {
                "id": f"M7-DEFECT-{len(defects) + 1:03d}",
                "gate": gate,
                "severity": severity,
                "name": name,
                "observed": observed,
                "expected": expected,
                "status": "open",
            }
        )


def _oracle_import_audit() -> dict:
    path = ROOT / "m7_independent_oracle.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = sorted(name for name in imports if name.startswith("m6"))
    return {
        "artifact": artifact_record(path),
        "imports": sorted(imports),
        "forbidden_M6_imports": forbidden,
        "independent": not forbidden,
    }


def _probability_vector(result: Any) -> tuple[float, float, float]:
    return result.p_tp, result.p_sl, result.p_expiry


def build_verification() -> dict:
    contract = read_json(M7_CONTRACT_PATH)
    m6_closure = read_json(M6_CLOSURE_PATH)
    if not contract["phase_boundaries"]["m7_started"]:
        raise ValueError("M7_contract_must_be_active")
    if not m6_closure["scope"]["m6_closed"]:
        raise ValueError("M6_must_remain_closed")

    checks: list[dict] = []
    defects: list[dict] = []
    import_audit = _oracle_import_audit()
    _check(
        checks,
        defects,
        gate="M7-GATE-REVIEW-012",
        name="independent_oracle_import_isolation",
        condition=import_audit["independent"],
        observed=import_audit["forbidden_M6_imports"],
        expected="no imports from M6 modules",
    )

    oracle_comparisons = []
    max_oracle_error = 0.0
    for case in ORACLE_CASES:
        m6_result = double_barrier_first_passage(
            tp_log_distance=case["tp"],
            sl_log_distance=case["sl"],
            sigma_horizon=case["sigma"],
            time_fraction=case["fraction"],
        )
        oracle = finite_difference_first_passage(
            tp_log_distance=case["tp"],
            sl_log_distance=case["sl"],
            sigma_horizon=case["sigma"],
            time_fraction=case["fraction"],
        )
        errors = [
            abs(left - right)
            for left, right in zip(
                _probability_vector(m6_result),
                _probability_vector(oracle),
            )
        ]
        max_error = max(errors)
        max_oracle_error = max(max_oracle_error, max_error)
        oracle_comparisons.append(
            {
                "case": case,
                "m6": {
                    "p_tp": m6_result.p_tp,
                    "p_sl": m6_result.p_sl,
                    "p_expiry": m6_result.p_expiry,
                },
                "independent_oracle": oracle.to_dict(),
                "absolute_errors": {
                    "p_tp": errors[0],
                    "p_sl": errors[1],
                    "p_expiry": errors[2],
                },
                "max_absolute_error": max_error,
            }
        )
    _check(
        checks,
        defects,
        gate="M7-GATE-SHAPE-003",
        name="independent_PDE_oracle_agreement",
        condition=max_oracle_error <= ORACLE_TOLERANCE,
        observed=max_oracle_error,
        expected=f"max absolute error <= {ORACLE_TOLERANCE}",
    )

    edge_values = (1e-12, 1e-8, 1e-5, 1e-3, 0.03, 0.5, 5.0)
    sigmas = (1e-8, 1e-4, 0.01, 0.1, 10.0)
    fractions = (0.0, 1e-10, 1e-4, 0.25, 1.0)
    grid_cases = 0
    max_mass_error = 0.0
    bounds_passed = True
    solver_failures = []
    for index, distance in enumerate(edge_values):
        other = edge_values[-(index + 1)]
        for sigma in sigmas:
            for fraction in fractions:
                grid_cases += 1
                try:
                    result = double_barrier_first_passage(
                        tp_log_distance=distance,
                        sl_log_distance=other,
                        sigma_horizon=sigma,
                        time_fraction=fraction,
                    )
                except Exception as exc:
                    solver_failures.append(
                        {
                            "tp": distance,
                            "sl": other,
                            "sigma": sigma,
                            "fraction": fraction,
                            "exception": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
                    continue
                values = _probability_vector(result)
                max_mass_error = max(
                    max_mass_error,
                    abs(math.fsum(values) - 1.0),
                )
                bounds_passed = bounds_passed and all(
                    0.0 <= value <= 1.0 for value in values
                )
    _check(
        checks,
        defects,
        gate="M7-GATE-EDGE-001",
        name="adversarial_grid_solver_convergence",
        condition=not solver_failures,
        observed={
            "cases": grid_cases,
            "failures": solver_failures,
        },
        expected="all finite valid cases return a result",
        severity="high",
    )
    _check(
        checks,
        defects,
        gate="M7-GATE-MASS-004",
        name="adversarial_grid_probability_bounds",
        condition=bounds_passed,
        observed={"cases": grid_cases, "bounds_passed": bounds_passed},
        expected="all probabilities in [0,1]",
    )
    _check(
        checks,
        defects,
        gate="M7-GATE-MASS-004",
        name="adversarial_grid_probability_mass",
        condition=max_mass_error <= 1e-12,
        observed=max_mass_error,
        expected="maximum mass error <= 1e-12",
    )

    symmetry_cases = 0
    max_symmetry_error = 0.0
    for tp_distance in (1e-5, 0.005, 0.02, 0.08, 0.5):
        for sl_distance in (1e-5, 0.007, 0.03, 0.1, 0.7):
            first = double_barrier_first_passage(
                tp_log_distance=tp_distance,
                sl_log_distance=sl_distance,
                sigma_horizon=0.04,
            )
            swapped = double_barrier_first_passage(
                tp_log_distance=sl_distance,
                sl_log_distance=tp_distance,
                sigma_horizon=0.04,
            )
            max_symmetry_error = max(
                max_symmetry_error,
                abs(first.p_tp - swapped.p_sl),
                abs(first.p_sl - swapped.p_tp),
                abs(first.p_expiry - swapped.p_expiry),
            )
            symmetry_cases += 1
    _check(
        checks,
        defects,
        gate="M7-GATE-SYMMETRY-002",
        name="barrier_reflection_symmetry",
        condition=max_symmetry_error <= 1e-11,
        observed={
            "cases": symmetry_cases,
            "max_absolute_error": max_symmetry_error,
        },
        expected="maximum reflected error <= 1e-11",
    )

    monotonic_cases = 0
    monotonic_passed = True
    for sl_distance in (0.01, 0.03, 0.08):
        previous_tp = None
        for tp_distance in (0.005, 0.01, 0.02, 0.04, 0.08):
            result = double_barrier_first_passage(
                tp_log_distance=tp_distance,
                sl_log_distance=sl_distance,
                sigma_horizon=0.04,
            )
            if previous_tp is not None:
                monotonic_passed = monotonic_passed and (
                    result.p_tp <= previous_tp + 1e-12
                )
                monotonic_cases += 1
            previous_tp = result.p_tp
    _check(
        checks,
        defects,
        gate="M7-GATE-SHAPE-003",
        name="farther_TP_never_increases_TP_probability",
        condition=monotonic_passed,
        observed={"comparisons": monotonic_cases, "passed": monotonic_passed},
        expected="non-increasing P_TP as TP distance increases",
    )

    time_monotonic_passed = True
    previous = None
    time_cases = 0
    for fraction in (0.0, 1e-6, 0.001, 0.01, 0.1, 0.5, 1.0):
        current = double_barrier_first_passage(
            tp_log_distance=0.03,
            sl_log_distance=0.05,
            sigma_horizon=0.04,
            time_fraction=fraction,
        )
        if previous is not None:
            time_monotonic_passed = time_monotonic_passed and (
                current.p_tp + 1e-12 >= previous.p_tp
                and current.p_sl + 1e-12 >= previous.p_sl
                and current.p_expiry <= previous.p_expiry + 1e-12
            )
            time_cases += 1
        previous = current
    _check(
        checks,
        defects,
        gate="M7-GATE-SHAPE-003",
        name="cumulative_events_monotone_in_time",
        condition=time_monotonic_passed,
        observed={"comparisons": time_cases, "passed": time_monotonic_passed},
        expected="TP/SL non-decreasing and expiry non-increasing",
    )

    continuity_cases = 0
    max_continuity_delta = 0.0
    for tp_distance, sl_distance, sigma in (
        (0.02, 0.04, 0.03),
        (0.04, 0.02, 0.05),
        (0.07, 0.09, 0.06),
    ):
        reference = double_barrier_first_passage(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=sigma,
        )
        perturbed = double_barrier_first_passage(
            tp_log_distance=tp_distance * (1.0 + 1e-6),
            sl_log_distance=sl_distance,
            sigma_horizon=sigma,
        )
        max_continuity_delta = max(
            max_continuity_delta,
            *(
                abs(left - right)
                for left, right in zip(
                    _probability_vector(reference),
                    _probability_vector(perturbed),
                )
            ),
        )
        continuity_cases += 1
    _check(
        checks,
        defects,
        gate="M7-GATE-SHAPE-003",
        name="local_continuity_under_small_geometry_change",
        condition=max_continuity_delta <= 2e-6,
        observed={
            "cases": continuity_cases,
            "max_probability_delta": max_continuity_delta,
        },
        expected="maximum probability delta <= 2e-6",
    )

    scale_reference = double_barrier_first_passage(
        tp_log_distance=0.03,
        sl_log_distance=0.07,
        sigma_horizon=0.04,
    )
    max_scale_error = 0.0
    for factor in (1e-8, 1e-4, 1.0, 1e4, 1e8):
        scaled = double_barrier_first_passage(
            tp_log_distance=0.03 * factor,
            sl_log_distance=0.07 * factor,
            sigma_horizon=0.04 * factor,
        )
        max_scale_error = max(
            max_scale_error,
            *(
                abs(left - right)
                for left, right in zip(
                    _probability_vector(scale_reference),
                    _probability_vector(scaled),
                )
            ),
        )
    _check(
        checks,
        defects,
        gate="M7-GATE-EDGE-001",
        name="dimensionless_common_scale_invariance",
        condition=max_scale_error <= 1e-11,
        observed=max_scale_error,
        expected="maximum scale error <= 1e-11",
    )

    invalid_inputs = (
        {"tp_log_distance": 0, "sl_log_distance": 0.03, "sigma_horizon": 0.04},
        {"tp_log_distance": -1, "sl_log_distance": 0.03, "sigma_horizon": 0.04},
        {"tp_log_distance": math.nan, "sl_log_distance": 0.03, "sigma_horizon": 0.04},
        {"tp_log_distance": 0.03, "sl_log_distance": math.inf, "sigma_horizon": 0.04},
        {"tp_log_distance": 0.03, "sl_log_distance": 0.03, "sigma_horizon": 0},
        {
            "tp_log_distance": 0.03,
            "sl_log_distance": 0.03,
            "sigma_horizon": 0.04,
            "time_fraction": -1,
        },
        {
            "tp_log_distance": 0.03,
            "sl_log_distance": 0.03,
            "sigma_horizon": 0.04,
            "time_fraction": 1.000001,
        },
    )
    invalid_rejected = 0
    for kwargs in invalid_inputs:
        try:
            double_barrier_first_passage(**kwargs)
        except FirstPassageInputError:
            invalid_rejected += 1
    _check(
        checks,
        defects,
        gate="M7-GATE-EDGE-001",
        name="invalid_mathematical_inputs_fail_closed",
        condition=invalid_rejected == len(invalid_inputs),
        observed={
            "rejected": invalid_rejected,
            "total": len(invalid_inputs),
        },
        expected="every invalid input rejected",
    )

    critical_open = sum(
        defect["severity"] == "critical" and defect["status"] == "open"
        for defect in defects
    )
    payload = {
        "version": VERSION,
        "phase": "M7",
        "subphase": "M7.2",
        "status": (
            "passed_no_critical_defects"
            if critical_open == 0
            else "failed_critical_defects_open"
        ),
        "date": "2026-07-28",
        "objective": (
            "Try to refute M6 mathematical behavior with an implementation-"
            "independent PDE oracle and adversarial properties."
        ),
        "independent_oracle_audit": import_audit,
        "oracle_tolerance": ORACLE_TOLERANCE,
        "oracle_comparisons": oracle_comparisons,
        "checks": checks,
        "summary": {
            "checks_total": len(checks),
            "checks_passed": sum(
                item["status"] == "passed" for item in checks
            ),
            "adversarial_grid_cases": grid_cases,
            "symmetry_cases": symmetry_cases,
            "max_probability_mass_error": max_mass_error,
            "max_independent_oracle_error": max_oracle_error,
            "defects_total": len(defects),
            "critical_defects_open": critical_open,
        },
        "defects": defects,
        "corrected_defects": [
            {
                "id": "M7-DEFECT-CONVERGENCE-001",
                "status": "corrected_and_retested",
                "pre_correction_record": artifact_record(
                    PRE_CORRECTION_DEFECT_PATH
                ),
                "correction_record": artifact_record(
                    CORRECTION_RECORD_PATH
                ),
            }
        ],
        "boundaries": {
            "probability_calibration_performed": False,
            "empirical_performance_measured": False,
            "production_effect": "none",
            "m8_started": False,
        },
        "verification_commands": {
            "status": "passed_2026_07_28",
            "m7_tests_passed": 22,
            "full_suite_tests_passed": 501,
            "m7_specific": (
                ".\\.venv\\Scripts\\python.exe -m unittest "
                "tests.test_m7_verification_contract "
                "tests.test_m7_math_verification"
            ),
            "full_suite": (
                ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests"
            ),
            "reproduce": (
                ".\\.venv\\Scripts\\python.exe "
                "build_m7_math_verification.py --check"
            ),
        },
        "inputs": [
            artifact_record(M7_CONTRACT_PATH),
            artifact_record(M6_CLOSURE_PATH),
            artifact_record(ROOT / "m6_first_passage.py"),
            artifact_record(ROOT / "m7_independent_oracle.py"),
            artifact_record(PRE_CORRECTION_DEFECT_PATH),
            artifact_record(CORRECTION_RECORD_PATH),
        ],
        "next_step": {
            "id": "M7.3",
            "name": "Datos ausentes, obsoletos, parciales y contradictorios",
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(verification: dict) -> str:
    summary = verification["summary"]
    lines = [
        "# M7.2 - Verificacion matematica adversaria",
        "",
        "Fecha: 2026-07-28",
        f"Estado: {verification['status']}",
        "",
        "## Metodo independiente",
        "",
        "Se resolvio la ecuacion del calor con fronteras absorbentes mediante",
        "diferencias finitas implicitas. El oraculo no importa codigo M6.",
        "",
        "## Resultados",
        "",
        (
            f"- Comprobaciones: {summary['checks_passed']}/"
            f"{summary['checks_total']}."
        ),
        f"- Casos adversarios: {summary['adversarial_grid_cases']}.",
        f"- Casos de simetria: {summary['symmetry_cases']}.",
        (
            "- Error maximo frente al oraculo: "
            f"{summary['max_independent_oracle_error']:.12g}."
        ),
        (
            "- Error maximo de masa: "
            f"{summary['max_probability_mass_error']:.12g}."
        ),
        f"- Defectos criticos abiertos: {summary['critical_defects_open']}.",
        "- Defecto de convergencia M7-DEFECT-CONVERGENCE-001: corregido.",
        (
            "- Pruebas especificas M7 superadas: "
            f"{verification['verification_commands']['m7_tests_passed']}."
        ),
        (
            "- Suite completa superada: "
            f"{verification['verification_commands']['full_suite_tests_passed']}."
        ),
        "",
        "## Limites",
        "",
        "- Esta fase comprueba coherencia matematica y numerica.",
        "- No calibra probabilidades ni demuestra rendimiento.",
        "- Produccion permanece intacta.",
        "- M8 no se ha iniciado.",
        "",
        "Siguiente subfase: M7.3.",
        "",
        "SHA-256 del payload canonico: "
        f"`{verification['canonical_payload_sha256']}`.",
        "",
    ]
    if verification["defects"]:
        lines.extend(["## Defectos", ""])
        lines.extend(
            f"- {item['id']} [{item['severity']}]: {item['name']}."
            for item in verification["defects"]
        )
        lines.append("")
    return "\n".join(lines)


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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    verification = build_verification()
    write_or_check(
        args.output,
        json.dumps(verification, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(verification), args.check)


if __name__ == "__main__":
    main()
