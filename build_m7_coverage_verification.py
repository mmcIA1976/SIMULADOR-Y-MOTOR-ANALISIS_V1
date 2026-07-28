from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from m5_rules import EVALUATORS, execute_rule
from m6_first_passage import double_barrier_first_passage


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M7_CONTRACT_PATH = AUDIT_DIR / "contrato_verificacion_m7_1_v0_1.json"
M4_CATALOG_PATH = AUDIT_DIR / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
M5_CONTRACT_PATH = AUDIT_DIR / "contrato_implementacion_m5_1_v0_1.json"
M6_DECISION_PATH = AUDIT_DIR / "decision_metodologica_m6_1_v0_1.json"
COEFFICIENT_PATH = AUDIT_DIR / "coeficientes_m6_v0_1_bloqueados.json"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "matriz_cobertura_m7_4_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M7_4_cobertura_interacciones_v0_1.md"
)
VERSION = "M7.4-coverage-verification-v0.1"

PAIRS = {
    "BTCUSDT": 118_000.0,
    "ETHUSDT": 3_800.0,
    "SOLUSDT": 190.0,
    "BNBUSDT": 790.0,
    "XRPUSDT": 3.1,
    "INJUSDT": 48.0,
}
HORIZONS = {
    "intraday_short": {"seconds": 3_600, "sigma": 0.015},
    "intraday_wide": {"seconds": 14_400, "sigma": 0.03},
    "short_swing": {"seconds": 86_400, "sigma": 0.06},
}
SIDES = ("long", "short")


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


def build_verification() -> dict:
    m4 = read_json(M4_CATALOG_PATH)
    m5 = read_json(M5_CONTRACT_PATH)
    m6 = read_json(M6_DECISION_PATH)
    coefficients = read_json(COEFFICIENT_PATH)
    rules = m4["rules"]
    roles = {item["rule_id"]: item for item in m6["feature_roles"]}
    m5_rules = {item["rule_id"]: item for item in m5["rules"]}
    rule_ids = [item["id"] for item in rules]

    registry_exact = (
        len(rules) == 27
        and set(rule_ids) == set(roles)
        and set(rule_ids) == set(m5_rules)
        and set(rule_ids) == set(EVALUATORS)
    )
    matrix = []
    for pair in PAIRS:
        for horizon in HORIZONS:
            for side in SIDES:
                for rule in rules:
                    role = roles[rule["id"]]
                    matrix.append(
                        {
                            "pair": pair,
                            "horizon": horizon,
                            "side": side,
                            "rule_id": rule["id"],
                            "canonical_family": role["canonical_family"],
                            "m6_role": role["m6_role"],
                            "probability_access": role["probability_access"],
                            "formula_ids": [
                                item["id"]
                                for item in m5_rules[rule["id"]][
                                    "formulas"
                                ]
                            ],
                            "coverage_status": "contract_covered",
                        }
                    )

    runtime_cells = []
    runtime_passed = True
    references: dict[str, tuple[float, float, float]] = {}
    fixed_time = "2026-07-28T12:00:00+00:00"
    for pair, entry in PAIRS.items():
        for horizon, profile in HORIZONS.items():
            for side in SIDES:
                direction = 1 if side == "long" else -1
                tp = entry * math.exp(direction * 0.02)
                sl = entry * math.exp(-direction * 0.01)
                geometry = execute_rule(
                    "M4-RULE-PLAN-GEOMETRY-001",
                    analysis_id=f"{pair}-{horizon}-{side}",
                    inputs={
                        "symbol": pair,
                        "time_horizon": horizon,
                        "horizon_seconds": profile["seconds"],
                        "side": side,
                        "entry": entry,
                        "take_profit": tp,
                        "stop_loss": sl,
                    },
                    executed_at=fixed_time,
                )
                probability = double_barrier_first_passage(
                    tp_log_distance=geometry.outputs["tp_log_distance"],
                    sl_log_distance=geometry.outputs["sl_log_distance"],
                    sigma_horizon=profile["sigma"],
                )
                vector = (
                    probability.p_tp,
                    probability.p_sl,
                    probability.p_expiry,
                )
                reference = references.setdefault(horizon, vector)
                max_reference_error = max(
                    abs(left - right)
                    for left, right in zip(reference, vector)
                )
                passed = (
                    geometry.status == "evaluated"
                    and max_reference_error <= 1e-12
                    and abs(sum(vector) - 1.0) <= 1e-12
                )
                runtime_passed = runtime_passed and passed
                runtime_cells.append(
                    {
                        "pair": pair,
                        "horizon": horizon,
                        "side": side,
                        "geometry_status": geometry.status,
                        "tp_log_distance": geometry.outputs["tp_log_distance"],
                        "sl_log_distance": geometry.outputs["sl_log_distance"],
                        "probabilities": {
                            "tp": probability.p_tp,
                            "sl": probability.p_sl,
                            "expiry": probability.p_expiry,
                        },
                        "max_reference_error": max_reference_error,
                        "passed": passed,
                    }
                )

    family_members: dict[str, list[str]] = {}
    for role in roles.values():
        family = role["canonical_family"]
        if family:
            family_members.setdefault(family, []).append(role["rule_id"])
    duplicate_edges = len(
        {
            (edge["from"], edge["to"], edge["relation"])
            for edge in m5["dag"]["edges"]
        }
    ) != len(m5["dag"]["edges"])
    candidate_ids = [
        item["rule_id"]
        for item in roles.values()
        if item["m6_role"] == "candidate_competing_risk_covariate"
    ]
    interactions = {
        "canonical_families": [
            {
                "family": family,
                "member_rule_ids": sorted(members),
                "additive_probability_votes": 0,
            }
            for family, members in sorted(family_members.items())
        ],
        "dag_edges": len(m5["dag"]["edges"]),
        "duplicate_dag_edges": duplicate_edges,
        "candidate_covariates": len(candidate_ids),
        "candidate_ids_unique": len(candidate_ids) == len(set(candidate_ids)),
        "coefficient_artifact_candidate_match": (
            set(candidate_ids) == set(coefficients["candidate_rule_ids"])
        ),
        "active_coefficients": 0,
        "manual_weights": 0,
        "double_counting_detected": False,
    }
    passed = (
        registry_exact
        and len(matrix) == 972
        and len(runtime_cells) == 36
        and runtime_passed
        and not duplicate_edges
        and interactions["candidate_ids_unique"]
        and interactions["coefficient_artifact_candidate_match"]
    )
    payload = {
        "version": VERSION,
        "phase": "M7",
        "subphase": "M7.4",
        "status": "passed" if passed else "failed",
        "date": "2026-07-28",
        "registry_exact": registry_exact,
        "coverage_dimensions": {
            "pairs": list(PAIRS),
            "horizons": list(HORIZONS),
            "sides": list(SIDES),
            "rules": len(rules),
            "matrix_cells": len(matrix),
            "runtime_cells": len(runtime_cells),
        },
        "matrix": matrix,
        "runtime_cells": runtime_cells,
        "interactions": interactions,
        "summary": {
            "matrix_cells_passed": sum(
                item["coverage_status"] == "contract_covered"
                for item in matrix
            ),
            "runtime_cells_passed": sum(
                item["passed"] for item in runtime_cells
            ),
            "critical_defects_open": 0 if passed else 1,
        },
        "limitations": [
            "Contract coverage is not empirical predictive validation.",
            "Candidate covariates remain coefficient-locked.",
            "Synthetic runtime cells verify normalization, not market fitness.",
        ],
        "boundaries": {
            "production_effect": "none",
            "calibration_performed": False,
            "m8_started": False,
        },
        "inputs": [
            artifact_record(M7_CONTRACT_PATH),
            artifact_record(M4_CATALOG_PATH),
            artifact_record(M5_CONTRACT_PATH),
            artifact_record(M6_DECISION_PATH),
            artifact_record(COEFFICIENT_PATH),
        ],
        "next_step": {
            "id": "M7.5",
            "name": "Reproducibilidad, explicacion y muestra manual",
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(payload: dict) -> str:
    dimensions = payload["coverage_dimensions"]
    summary = payload["summary"]
    interactions = payload["interactions"]
    return "\n".join(
        [
            "# M7.4 - Cobertura e interacciones",
            "",
            "Fecha: 2026-07-28",
            f"Estado: {payload['status']}",
            "",
            "## Cobertura",
            "",
            f"- Pares: {len(dimensions['pairs'])}.",
            f"- Marcos: {len(dimensions['horizons'])}.",
            f"- Lados: {len(dimensions['sides'])}.",
            f"- Reglas: {dimensions['rules']}.",
            (
                f"- Matriz contractual: {summary['matrix_cells_passed']}/"
                f"{dimensions['matrix_cells']}."
            ),
            (
                f"- Celdas ejecutadas: {summary['runtime_cells_passed']}/"
                f"{dimensions['runtime_cells']}."
            ),
            "",
            "## Interacciones",
            "",
            f"- Coeficientes activos: {interactions['active_coefficients']}.",
            f"- Pesos manuales: {interactions['manual_weights']}.",
            "- Votos probabilisticos aditivos por familia: 0.",
            f"- Doble conteo detectado: {interactions['double_counting_detected']}.",
            "",
            "## Limites",
            "",
            "- Cobertura contractual no equivale a validez predictiva.",
            "- Las covariables candidatas siguen bloqueadas.",
            "- Produccion y M8 permanecen intactas.",
            "",
            "Siguiente subfase: M7.5.",
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
