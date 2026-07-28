from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M6_CLOSURE_PATH = AUDIT_DIR / "paquete_cierre_m6_6_v0_1.json"
M6_DECISION_PATH = AUDIT_DIR / "decision_metodologica_m6_1_v0_1.json"
M6_VERIFICATION_PATH = AUDIT_DIR / "verificacion_m6_5_v0_1.json"
M4_CATALOG_PATH = AUDIT_DIR / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "contrato_verificacion_m7_1_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M7_1_contrato_verificacion_v0_1.md"
)
VERSION = "M7.1-verification-contract-v0.1"

SUPPORTED_PAIRS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
SUPPORTED_HORIZONS = (
    "intraday_short",
    "intraday_wide",
    "short_swing",
)
SIDES = ("long", "short")

WORKSTREAMS = (
    {
        "id": "M7-GATE-EDGE-001",
        "roadmap_item": 1,
        "name": "Casos limite de entrada, TP, SL y horizonte",
        "subphase": "M7.2",
        "method": "boundary and adversarial tests",
    },
    {
        "id": "M7-GATE-SYMMETRY-002",
        "roadmap_item": 2,
        "name": "Simetria long/short",
        "subphase": "M7.2",
        "method": "metamorphic log-price reflection tests",
    },
    {
        "id": "M7-GATE-SHAPE-003",
        "roadmap_item": 3,
        "name": "Monotonicidad y continuidad",
        "subphase": "M7.2",
        "method": "property grids plus independent numerical oracle",
    },
    {
        "id": "M7-GATE-MASS-004",
        "roadmap_item": 4,
        "name": "Masa probabilistica",
        "subphase": "M7.2",
        "method": "bounds, conservation and residual-error tests",
    },
    {
        "id": "M7-GATE-DATA-005",
        "roadmap_item": 5,
        "name": "Datos ausentes, obsoletos, parciales o contradictorios",
        "subphase": "M7.3",
        "method": "invalid-input and fail-closed matrix",
    },
    {
        "id": "M7-GATE-PAIR-006",
        "roadmap_item": 6,
        "name": "Cobertura de todos los pares soportados",
        "subphase": "M7.4",
        "method": "six-pair scale and contract matrix",
    },
    {
        "id": "M7-GATE-HORIZON-007",
        "roadmap_item": 7,
        "name": "Cobertura de los tres marcos",
        "subphase": "M7.4",
        "method": "three-horizon exact-sampling matrix",
    },
    {
        "id": "M7-GATE-INTERACTION-008",
        "roadmap_item": 8,
        "name": "Doble conteo e interacciones",
        "subphase": "M7.4",
        "method": "rule-DAG and coefficient-feature uniqueness audit",
    },
    {
        "id": "M7-GATE-TRACE-009",
        "roadmap_item": 9,
        "name": "Reproducibilidad de traza y explicacion",
        "subphase": "M7.5",
        "method": "canonical replay and explanation completeness",
    },
    {
        "id": "M7-GATE-MANUAL-010",
        "roadmap_item": 10,
        "name": "Comparacion manual de una muestra de analisis",
        "subphase": "M7.5",
        "method": "predeclared cases recalculated outside M6",
    },
    {
        "id": "M7-GATE-RESILIENCE-011",
        "roadmap_item": 11,
        "name": "Rendimiento, latencia y tolerancia a fallos",
        "subphase": "M7.6",
        "method": "benchmarks, stress cases and failure injection",
    },
    {
        "id": "M7-GATE-REVIEW-012",
        "roadmap_item": 12,
        "name": "Revision independiente del codigo y formulas",
        "subphase": "M7.7",
        "method": "source-to-formula review and defect register",
    },
)

SEVERITY_POLICY = (
    {
        "severity": "critical",
        "definition": (
            "Can produce invalid probabilities, invert a required mathematical "
            "relation, accept leakage or contradictory inputs silently, mutate "
            "production, or make an analysis non-reproducible."
        ),
        "closure_policy": "must_be_fixed_and_retested_before_M7_closure",
    },
    {
        "severity": "high",
        "definition": (
            "Breaks a supported pair, side, horizon, trace field, or declared "
            "fail-closed behavior without corrupting every result."
        ),
        "closure_policy": "must_be_fixed_or_explicitly_block_affected_scope",
    },
    {
        "severity": "medium",
        "definition": (
            "Weakens diagnostics, numerical precision, coverage evidence, "
            "latency margin, or explanation quality."
        ),
        "closure_policy": "fix_or_declare_with_owner_review",
    },
    {
        "severity": "low",
        "definition": (
            "Documentation or maintainability defect with no demonstrated "
            "effect on calculation or supported behavior."
        ),
        "closure_policy": "record_and_schedule",
    },
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


def build_contract() -> dict:
    m6_closure = read_json(M6_CLOSURE_PATH)
    m6_decision = read_json(M6_DECISION_PATH)
    m6_verification = read_json(M6_VERIFICATION_PATH)
    m4_catalog = read_json(M4_CATALOG_PATH)

    if not m6_closure["scope"]["m6_closed"]:
        raise ValueError("M6_must_be_closed_before_M7")
    if m6_closure["scope"]["m7_started"]:
        raise ValueError("historical_M6_closure_must_remain_immutable")
    if len(m4_catalog["rules"]) != 27:
        raise ValueError("M7_requires_the_frozen_27_rule_catalog")

    catalog_pairs = tuple(
        m4_catalog["rules"][0]["market_symbol_timestamp_unit_freshness"][
            "symbols"
        ]
    )
    catalog_horizons = tuple(m4_catalog["rules"][0]["applicable_horizons"])
    if catalog_pairs != SUPPORTED_PAIRS:
        raise ValueError("supported_pair_contract_mismatch")
    if catalog_horizons[:3] != SUPPORTED_HORIZONS:
        raise ValueError("supported_horizon_contract_mismatch")

    payload = {
        "version": VERSION,
        "phase": "M7",
        "subphase": "M7.1",
        "status": "in_progress_owner_authorized",
        "date": "2026-07-28",
        "owner_authorization": {
            "instruction": "perfecto empecemos con M7",
            "m7_started": True,
            "m8_started": False,
            "production_authorized": False,
        },
        "objective": (
            "Attempt to refute the frozen M6 revision through independent "
            "mathematical, software and coverage verification before any "
            "empirical performance evaluation."
        ),
        "explicit_exclusions": [
            "no probability calibration",
            "no coefficient estimation",
            "no profitability claim",
            "no use of legacy scores as truth",
            "no production activation",
            "no M8 empirical evaluation",
        ],
        "independence_contract": {
            "oracles_must_not_call_M6_solver": True,
            "manual_cases_must_be_recalculated_outside_M6": True,
            "property_tests_must_not_copy_expected_M6_outputs": True,
            "formula_review_must_map_expression_to_primary_source": True,
            "failures_must_be_recorded_before_correction": True,
            "production_hashes_must_match_M6_close": True,
        },
        "workstreams": list(WORKSTREAMS),
        "severity_policy": list(SEVERITY_POLICY),
        "coverage_contract": {
            "pairs": list(SUPPORTED_PAIRS),
            "horizons": list(SUPPORTED_HORIZONS),
            "sides": list(SIDES),
            "pair_horizon_side_cells": (
                len(SUPPORTED_PAIRS)
                * len(SUPPORTED_HORIZONS)
                * len(SIDES)
            ),
            "frozen_rules": 27,
            "rule_coverage_cells": (
                len(SUPPORTED_PAIRS)
                * len(SUPPORTED_HORIZONS)
                * len(SIDES)
                * 27
            ),
            "coverage_does_not_claim_predictive_validity": True,
        },
        "required_deliverables": [
            "verification test suite",
            "defect and correction register",
            "pair-horizon-rule matrix",
            "manual independent sample",
            "performance and fault-tolerance report",
            "independent code and formula review",
            "proof that production remains unchanged",
        ],
        "closure_gates": {
            "all_12_workstreams_completed": True,
            "critical_defects_open": 0,
            "all_remaining_limitations_declared": True,
            "production_unchanged": True,
            "owner_approval_required": True,
        },
        "phase_boundaries": {
            "m6_frozen": True,
            "m7_started": True,
            "m7_closed": False,
            "m8_blocked": True,
            "production_effect": "none",
        },
        "inputs": [
            artifact_record(M6_CLOSURE_PATH),
            artifact_record(M6_DECISION_PATH),
            artifact_record(M6_VERIFICATION_PATH),
            artifact_record(M4_CATALOG_PATH),
        ],
        "m6_formula_count": len(m6_closure["formula_registry"]),
        "m6_source_count": len(m6_decision["sources"]),
        "m6_verification_status": m6_verification["status"],
        "production_source_hashes_frozen": m6_closure[
            "production_source_hashes_at_close"
        ],
        "next_step": {
            "id": "M7.2",
            "name": "Pruebas matematicas adversarias y oraculos independientes",
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(contract: dict) -> str:
    coverage = contract["coverage_contract"]
    lines = [
        "# M7.1 - Contrato de verificacion independiente",
        "",
        "Fecha: 2026-07-28",
        "Estado: M7 INICIADA; M7.1 COMPLETADA",
        "",
        "## Objetivo",
        "",
        "Intentar refutar M6 antes de medir rendimiento empirico.",
        "",
        "## Alcance obligatorio",
        "",
    ]
    lines.extend(
        f"{item['roadmap_item']}. {item['name']} ({item['subphase']})."
        for item in contract["workstreams"]
    )
    lines.extend(
        [
            "",
            "## Cobertura congelada",
            "",
            f"- Pares: {', '.join(coverage['pairs'])}.",
            f"- Marcos: {', '.join(coverage['horizons'])}.",
            f"- Lados: {', '.join(coverage['sides'])}.",
            (
                "- Celdas par-marco-lado: "
                f"{coverage['pair_horizon_side_cells']}."
            ),
            (
                "- Celdas maximas par-marco-lado-regla: "
                f"{coverage['rule_coverage_cells']}."
            ),
            "",
            "## Independencia",
            "",
            "- Los oraculos no pueden llamar al solver M6.",
            "- Los casos manuales se recalcularan fuera de M6.",
            "- Las propiedades no copiaran salidas esperadas de M6.",
            "- Cada formula se contrastara con su fuente primaria.",
            "- Todo fallo se registrara antes de corregirse.",
            "",
            "## Cierre",
            "",
            "- Cero fallos criticos abiertos.",
            "- Toda limitacion restante declarada.",
            "- Produccion intacta.",
            "- Aprobacion expresa del propietario.",
            "",
            "## Limites",
            "",
            "- M7 no calibra probabilidades ni estima coeficientes.",
            "- M7 no demuestra rentabilidad.",
            "- M8 permanece bloqueada.",
            "- Produccion no queda autorizada.",
            "",
            "Siguiente subfase: M7.2.",
            "",
            "SHA-256 del payload canonico: "
            f"`{contract['canonical_payload_sha256']}`.",
            "",
        ]
    )
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

    contract = build_contract()
    write_or_check(
        args.output,
        json.dumps(contract, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(contract), args.check)


if __name__ == "__main__":
    main()
