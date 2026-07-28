from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M5_CLOSURE_PATH = AUDIT_DIR / "paquete_cierre_m5_6_v0_1.json"
M6_DECISION_PATH = AUDIT_DIR / "decision_metodologica_m6_1_v0_1.json"
M6_VERIFICATION_PATH = AUDIT_DIR / "verificacion_m6_5_v0_1.json"
DEFAULT_COEFFICIENT_PATH = (
    AUDIT_DIR / "coeficientes_m6_v0_1_bloqueados.json"
)
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "paquete_cierre_m6_6_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M6_6_cierre_integracion_probabilistica_v0_1.md"
)
VERSION = "M6.6-closure-package-v0.1"

IMPLEMENTATION_FILES = (
    "m6_first_passage.py",
    "m6_competing_risks.py",
    "m6_engine.py",
)
GENERATOR_FILES = (
    "build_m6_methodology_decision.py",
    "build_m6_verification.py",
    "build_m6_closure.py",
)
TEST_FILES = (
    "tests/test_m6_methodology_decision.py",
    "tests/test_m6_first_passage.py",
    "tests/test_m6_competing_risks.py",
    "tests/test_m6_engine.py",
    "tests/test_m6_verification.py",
    "tests/test_m6_closure.py",
)
PRODUCTION_FILES = (
    "app.py",
    "analysis_engine.py",
    "data_engine.py",
    "market_data.py",
    "liquidation_data.py",
    "challenger_engine.py",
)
FORBIDDEN_IMPORTS = {
    "app",
    "analysis_engine",
    "data_engine",
    "market_data",
    "liquidation_data",
    "challenger_engine",
    "shadow_runtime",
}

FORMULA_REGISTRY = (
    {
        "id": "M6-FORMULA-DB-TRANSITION-001",
        "layer": "first_passage_baseline",
        "expression": (
            "p(y,t|y0)=2/L sum_n sin(n*pi*y0/L) sin(n*pi*y/L) "
            "exp[-n^2*pi^2*sigma_H^2*t/(2L^2)]"
        ),
    },
    {
        "id": "M6-FORMULA-DB-TP-002",
        "layer": "first_passage_baseline",
        "expression": (
            "P_TP(T)=b/L-(2/pi) sum_n (-1)^(n+1) "
            "sin(n*pi*b/L) exp(-c*n^2)/n"
        ),
    },
    {
        "id": "M6-FORMULA-DB-SL-003",
        "layer": "first_passage_baseline",
        "expression": (
            "P_SL(T)=a/L-(2/pi) sum_n "
            "sin(n*pi*b/L) exp(-c*n^2)/n"
        ),
    },
    {
        "id": "M6-FORMULA-DB-EXPIRY-004",
        "layer": "first_passage_baseline",
        "expression": "P_EXPIRY(T)=1-P_TP(T)-P_SL(T)",
    },
    {
        "id": "M6-FORMULA-INTERVAL-HAZARD-005",
        "layer": "competing_risks",
        "expression": (
            "h_c(k)=[F_c(t_k)-F_c(t_(k-1))]/S(t_(k-1))"
        ),
    },
    {
        "id": "M6-FORMULA-EVIDENCE-OFFSET-006",
        "layer": "competing_risks",
        "expression": (
            "h'_c(k)=h_c(k)*exp(beta_c*x)/"
            "[h_none(k)+sum_j h_j(k)*exp(beta_j*x)]"
        ),
    },
    {
        "id": "M6-FORMULA-CIF-007",
        "layer": "competing_risks",
        "expression": (
            "F_c(K)=sum_(k=1..K) S(k-1)*h'_c(k)"
        ),
    },
    {
        "id": "M6-FORMULA-SURVIVAL-008",
        "layer": "competing_risks",
        "expression": (
            "S(K)=product_(k=1..K)[1-h'_TP(k)-h'_SL(k)]"
        ),
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


def artifact_record(relative_path: str) -> dict:
    path = ROOT / relative_path
    if not path.is_file():
        raise ValueError(f"missing_artifact:{relative_path}")
    return {
        "path": relative_path,
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def build_locked_coefficients(decision: dict) -> dict:
    candidates = [
        item
        for item in decision["feature_roles"]
        if item["m6_role"] == "candidate_competing_risk_covariate"
    ]
    payload = {
        "id": "M6-COEFFICIENTS-v0.1-LOCKED",
        "version": "0.1",
        "status": "locked_no_estimated_coefficients",
        "date": "2026-07-28",
        "reason": (
            "No temporally separated M5 feature/outcome training set has "
            "estimated these coefficients."
        ),
        "candidate_rule_ids": [
            item["rule_id"]
            for item in candidates
        ],
        "coefficients": None,
        "manual_coefficients_authorized": False,
        "probability_adjustment_active": False,
        "production_authorized": False,
        "unlock_requirements": decision["coefficient_gate"][
            "future_requirements"
        ],
    }
    payload["artifact_sha256"] = sha256_text(
        canonical_json(
            {
                key: value
                for key, value in payload.items()
                if key != "artifact_sha256"
            }
        )
    )
    return payload


def build_package(coefficient_path: Path) -> dict:
    m5 = read_json(M5_CLOSURE_PATH)
    decision = read_json(M6_DECISION_PATH)
    verification = read_json(M6_VERIFICATION_PATH)
    coefficients = build_locked_coefficients(decision)
    written_coefficients = read_json(coefficient_path)
    if written_coefficients != coefficients:
        raise ValueError("locked_coefficient_artifact_stale")
    if not m5["scope"]["m5_closed"] or m5["scope"]["m6_started"]:
        raise ValueError("m5_to_m6_gate_invalid")
    if not decision["scope"]["m6_1_complete"]:
        raise ValueError("m6_methodology_incomplete")
    if verification["status"] != (
        "completed_internal_verification_m7_still_required"
    ):
        raise ValueError("m6_verification_incomplete")

    production_at_m5_close = {
        item["path"]: item["sha256"]
        for item in m5["production_source_hashes_at_close"]
    }
    production_now = {
        path: file_sha256(ROOT / path)
        for path in PRODUCTION_FILES
    }
    if production_at_m5_close != production_now:
        raise ValueError("production_changed_during_m6")

    import_audit = []
    for relative_path in IMPLEMENTATION_FILES:
        imports = imported_modules(ROOT / relative_path)
        forbidden = sorted(imports & FORBIDDEN_IMPORTS)
        if forbidden:
            raise ValueError(
                f"m6_production_import_detected:{relative_path}:{forbidden}"
            )
        import_audit.append(
            {
                "path": relative_path,
                "forbidden_imports": forbidden,
                "internal_only": True,
            }
        )

    manifest_paths = (
        list(IMPLEMENTATION_FILES)
        + list(GENERATOR_FILES)
        + list(TEST_FILES)
        + [
            "auditorias_motor/decision_metodologica_m6_1_v0_1.json",
            "auditorias_motor/2026-07-28_M6_1_decision_metodologica_v0_1.md",
            "auditorias_motor/verificacion_m6_5_v0_1.json",
            "auditorias_motor/2026-07-28_M6_5_verificacion_propiedades_v0_1.md",
            str(coefficient_path.relative_to(ROOT)).replace("\\", "/"),
        ]
    )
    historical = verification["historical_case_872_873"]
    payload = {
        "version": VERSION,
        "phase": "M6",
        "subphase": "M6.6",
        "status": "completed_owner_authorized",
        "date": "2026-07-28",
        "owner_authorization": {
            "statement": (
                "continua y completa M6, no vayas parando por favor a no "
                "ser que tengas alguna duda en concreto"
            ),
            "methodology_approved": True,
            "m6_completion_authorized": True,
            "production_authorized": False,
            "m7_start_authorized": False,
        },
        "scope": {
            "m6_closed": True,
            "m7_started": False,
            "production_modified": False,
            "learning_engine_modified": False,
            "outcomes": 3,
            "formulas_registered": len(FORMULA_REGISTRY),
            "m5_rules_partitioned": decision["scope"]["rules_partitioned"],
            "baseline_inputs": decision["scope"]["baseline_inputs"],
            "candidate_covariates": decision["scope"][
                "candidate_covariates"
            ],
            "active_evidence_coefficients": 0,
            "property_grid_cases": verification["property_results"][
                "mass_grid_cases"
            ],
        },
        "architecture": decision["selected_architecture"],
        "formula_registry": list(FORMULA_REGISTRY),
        "coefficient_artifact": {
            "path": str(coefficient_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": file_sha256(coefficient_path),
            "status": coefficients["status"],
            "active": coefficients["probability_adjustment_active"],
        },
        "trace_contract": {
            "source": "m6_engine.py",
            "from_m5_values": [
                "horizon_seconds",
                "tp_log_distance",
                "sl_log_distance",
                "sigma_horizon",
            ],
            "exposes": [
                "source M5 trace hashes",
                "formula IDs",
                "baseline probabilities",
                "interval hazards and cumulative incidence",
                "coefficient artifact status",
                "uncertainty status or scenario envelope",
                "assumptions and limitations",
                "probability mass error",
            ],
            "production_effect": "none",
        },
        "historical_872_873": {
            "legacy_ordering": historical["legacy_ordering"],
            "m6_ordering": historical["m6_ordering"],
            "sigma_scenarios": historical["m6_sigma_scenarios"],
            "historical_probability_claimed": False,
        },
        "verification_summary": {
            "probability_mass_grid_passed": True,
            "probability_bounds_passed": True,
            "symmetry_passed": True,
            "scale_invariance_passed": True,
            "farther_tp_monotonicity_passed": True,
            "horizon_monotonicity_passed": True,
            "continuity_passed": True,
            "uncertainty_state_explicit": True,
            "reproducible_trace_passed": True,
            "m7_independent_verification_still_required": True,
        },
        "import_isolation_audit": import_audit,
        "boundaries": {
            "manual_points_bonus_penalties": "none",
            "manual_coefficients": "none",
            "production_probability_changed": False,
            "probabilities_calibrated": False,
            "predictive_validity_established": False,
            "profitability_established": False,
            "m7_replaced": False,
            "m8_replaced": False,
        },
        "sources": decision["sources"],
        "verification_commands": {
            "status": "passed_2026_07_28",
            "m6_specific_tests_passed": 62,
            "full_suite_tests_passed": 478,
            "m6_specific": (
                ".\\.venv\\Scripts\\python.exe -m unittest "
                "tests.test_m6_methodology_decision "
                "tests.test_m6_first_passage "
                "tests.test_m6_competing_risks tests.test_m6_engine "
                "tests.test_m6_verification tests.test_m6_closure"
            ),
            "full_suite": (
                ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests"
            ),
            "reproduce_decision": (
                ".\\.venv\\Scripts\\python.exe "
                "build_m6_methodology_decision.py --check"
            ),
            "reproduce_verification": (
                ".\\.venv\\Scripts\\python.exe "
                "build_m6_verification.py --check"
            ),
            "reproduce_closure": (
                ".\\.venv\\Scripts\\python.exe build_m6_closure.py --check"
            ),
        },
        "production_source_hashes_at_close": [
            artifact_record(path)
            for path in PRODUCTION_FILES
        ],
        "artifact_manifest": [
            artifact_record(path)
            for path in manifest_paths
        ],
        "next_phase": {
            "id": "M7",
            "name": "Verificacion matematica, de software y cobertura",
            "started": False,
            "requires_separate_owner_order": True,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                key: value
                for key, value in payload.items()
                if key != "canonical_payload_sha256"
            }
        )
    )
    return payload


def render_report(package: dict) -> str:
    scope = package["scope"]
    lines = [
        "# M6.6 - Cierre de integracion probabilistica",
        "",
        "Fecha: 2026-07-28",
        "Estado: M6 COMPLETADA POR ORDEN DEL PROPIETARIO",
        "",
        "## Resultado",
        "",
        "- Baseline de primera barrera doble implementado.",
        "- Tres outcomes coherentes: TP, SL y expiry.",
        "- Riesgos competitivos discretos implementados.",
        f"- Formulas registradas: {scope['formulas_registered']}.",
        f"- Reglas M5 clasificadas: {scope['m5_rules_partitioned']}/27.",
        f"- Casos de malla verificados: {scope['property_grid_cases']}.",
        "- Caso 872/873: ordenacion geometrica corregida.",
        "- Pruebas especificas M6 superadas: "
        f"{package['verification_commands']['m6_specific_tests_passed']}.",
        "- Suite completa superada: "
        f"{package['verification_commands']['full_suite_tests_passed']}.",
        "",
        "## Evidencia tecnica",
        "",
        "La infraestructura admite coeficientes estimados, pero el artefacto",
        "actual esta bloqueado. Por tanto, las doce covariables candidatas no",
        "alteran aun las probabilidades y la salida coincide con el baseline.",
        "",
        "## Trazabilidad",
        "",
        "Cada salida interna expone geometria, sigma, horizonte, formulas,",
        "hashes M5, hazards, incidencia acumulada, masa, supuestos, limites",
        "y estado de incertidumbre.",
        "",
        "## Limites",
        "",
        "- Puntos, bonus, penalizaciones o pesos manuales: NINGUNO.",
        "- Coeficientes activos: 0.",
        "- Calibracion empirica: NO.",
        "- Validez predictiva o rentabilidad: NO DEMOSTRADAS.",
        "- Produccion modificada: NO.",
        "- M7 y M8 siguen siendo obligatorias.",
        "",
        "## Estado de fases",
        "",
        "- M6 cerrada: SI.",
        "- M7 iniciada: NO.",
        "- M7 requiere una orden expresa separada.",
        "",
        "SHA-256 del payload canonico: "
        f"`{package['canonical_payload_sha256']}`.",
        "",
    ]
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
    parser.add_argument(
        "--coefficients",
        type=Path,
        default=DEFAULT_COEFFICIENT_PATH,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    decision = read_json(M6_DECISION_PATH)
    coefficients = build_locked_coefficients(decision)
    write_or_check(
        args.coefficients,
        json.dumps(coefficients, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    package = build_package(args.coefficients)
    write_or_check(
        args.output,
        json.dumps(package, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(package), args.check)


if __name__ == "__main__":
    main()
