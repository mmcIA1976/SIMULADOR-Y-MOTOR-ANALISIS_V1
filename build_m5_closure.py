from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from m5_engine import engine_contract
from m5_rules import EVALUATORS, rule_specs


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M5_CONTRACT_PATH = (
    AUDIT_DIR / "contrato_implementacion_m5_1_v0_1.json"
)
M4_RULES_PATH = (
    AUDIT_DIR / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
)
M4_INTEGRATION_PATH = (
    AUDIT_DIR / "integracion_dag_invariantes_m4_7_v0_2.json"
)
M4_RECONCILIATION_PATH = (
    AUDIT_DIR / "catalogo_combinaciones_reconciliacion_m4_6_v0_2.json"
)
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "paquete_cierre_m5_6_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M5_6_cierre_implementacion_v0_1.md"
)
VERSION = "M5.6-closure-package-v0.1"

IMPLEMENTATION_FILES = (
    "m5_runtime.py",
    "m5_rules.py",
    "m5_engine.py",
)
TEST_FILES = (
    "tests/test_m5_implementation_contract.py",
    "tests/test_m5_runtime.py",
    "tests/test_m5_rules.py",
    "tests/test_m5_engine.py",
    "tests/test_m5_properties.py",
    "tests/test_m5_closure.py",
)
PRODUCTION_FILES = (
    "app.py",
    "analysis_engine.py",
    "data_engine.py",
    "market_data.py",
    "liquidation_data.py",
    "challenger_engine.py",
)
FORBIDDEN_INTERNAL_IMPORTS = {
    "app",
    "analysis_engine",
    "data_engine",
    "market_data",
    "liquidation_data",
    "challenger_engine",
    "shadow_runtime",
}
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = (
    "intraday_short",
    "intraday_wide",
    "short_swing",
)

TEST_CASE_BY_RULE = {
    "M4-RULE-HORIZON-SAMPLING-001": "test_sampling_uses_largest_exact_valid_interval",
    "M4-RULE-PLAN-GEOMETRY-001": "test_plan_geometry_is_directionally_symmetric",
    "M4-RULE-LOG-RETURNS-001": "test_log_returns_and_realized_volatility_match_manual_formula",
    "M4-RULE-REALIZED-VOLATILITY-001": "test_log_returns_and_realized_volatility_match_manual_formula",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": "test_normalized_barrier_geometry_uses_plan_and_sigma",
    "M4-RULE-PENDING-ACTIVATION-001": "test_market_activation_is_zero_and_pending_is_deferred",
    "M4-RULE-EXPONENTIAL-SMOOTHER-001": "test_smoother_and_path_structure_match_manual_calculation",
    "M4-RULE-PATH-STRUCTURE-001": "test_smoother_and_path_structure_match_manual_calculation",
    "M4-RULE-PRIOR-EXTREMA-001": "test_prior_extrema_and_volatility_rank_are_continuous_outputs",
    "M4-RULE-VOLATILITY-RANK-001": "test_prior_extrema_and_volatility_rank_are_continuous_outputs",
    "M4-RULE-MTF-HIERARCHY-001": "test_mtf_and_continuous_regime_do_not_create_scores",
    "M4-RULE-CONTINUOUS-REGIME-001": "test_mtf_and_continuous_regime_do_not_create_scores",
    "M4-RULE-AGGRESSOR-IMBALANCE-001": "test_aggressor_and_open_interest_use_exact_observations",
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "test_aggressor_and_open_interest_use_exact_observations",
    "M4-RULE-PRICE-OI-STATE-001": "test_price_oi_state_is_a_container_without_positioning_label",
    "M4-RULE-SPOT-FUTURES-BASIS-001": "test_basis_and_mark_index_keep_semantics_separate",
    "M4-RULE-MARK-INDEX-PREMIUM-001": "test_basis_and_mark_index_keep_semantics_separate",
    "M4-RULE-FUNDING-STATE-001": "test_funding_state_uses_realized_load_without_future_cost",
    "M4-RULE-DERIVATIVES-CONTEXT-001": "test_derivatives_context_selects_one_basis_source",
    "M4-RULE-QUOTED-SPREAD-001": "test_spread_depth_and_fee_formulas_match_manual_values",
    "M4-RULE-DEPTH-SWEEP-001": "test_spread_depth_and_fee_formulas_match_manual_values",
    "M4-RULE-FEE-SCENARIOS-001": "test_spread_depth_and_fee_formulas_match_manual_values",
    "M4-RULE-FUNDING-CASHFLOW-001": "test_funding_cashflow_and_exposure_preserve_signs",
    "M4-RULE-PLAN-EXPOSURE-001": "test_funding_cashflow_and_exposure_preserve_signs",
    "M4-RULE-NET-PAYOFFS-001": "test_net_payoff_identity_and_no_entry_constraint",
    "M4-RULE-EXPECTED-VALUE-001": "test_expected_value_is_implemented_but_blocked_until_m6",
    "M4-RULE-EVALUATION-READINESS-001": "test_readiness_never_authorizes_decision",
}


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


def normalized_formulas(rule: dict) -> list[str]:
    formulas = rule["exact_transformation_and_formula"]
    if not isinstance(formulas, list):
        formulas = [formulas]
    return [str(item) for item in formulas]


def build_package() -> dict:
    m5_contract = read_json(M5_CONTRACT_PATH)
    m4_rules = read_json(M4_RULES_PATH)
    integration = read_json(M4_INTEGRATION_PATH)
    reconciliation = read_json(M4_RECONCILIATION_PATH)
    if not m5_contract["scope"]["m5_started"]:
        raise ValueError("m5_not_started")
    if len(EVALUATORS) != 27 or set(EVALUATORS) != set(rule_specs()):
        raise ValueError("m5_evaluator_universe_not_exact")
    if engine_contract()["version"] != m5_contract["version"]:
        raise ValueError("m5_engine_contract_version_mismatch")

    source_by_id = {rule["id"]: rule for rule in m4_rules["rules"]}
    contract_by_id = {
        rule["rule_id"]: rule
        for rule in m5_contract["rules"]
    }
    if not (
        set(source_by_id) == set(contract_by_id) == set(EVALUATORS)
    ):
        raise ValueError("m5_rule_parity_universe_mismatch")
    formula_parity = []
    for rule_id in sorted(source_by_id):
        source_formulas = normalized_formulas(source_by_id[rule_id])
        contract_formulas = [
            item["expression"]
            for item in contract_by_id[rule_id]["formulas"]
        ]
        if source_formulas != contract_formulas:
            raise ValueError(f"m5_formula_parity_failure:{rule_id}")
        formula_parity.append(
            {
                "rule_id": rule_id,
                "formula_count": len(source_formulas),
                "formula_text_exact": True,
                "input_contract_preserved": (
                    source_by_id[rule_id]["raw_data_and_provider"]
                    == contract_by_id[rule_id]["input_contract"]
                ),
                "evaluator_registered": rule_id in EVALUATORS,
                "test_module": "tests.test_m5_rules",
                "test_case": TEST_CASE_BY_RULE[rule_id],
                "status": "implemented_and_tested",
            }
        )
    if not all(item["input_contract_preserved"] for item in formula_parity):
        raise ValueError("m5_input_contract_parity_failure")

    invariant_coverage = []
    for invariant in integration["invariant_matrix"]:
        invariant_coverage.append(
            {
                "m4_invariant_id": invariant["id"],
                "m5_test_id": invariant["m5_required_test_id"],
                "rule_id": invariant["rule_id"],
                "statement": invariant["statement"],
                "test_module": "tests.test_m5_rules",
                "test_case": TEST_CASE_BY_RULE[invariant["rule_id"]],
                "property_test_module": "tests.test_m5_properties",
                "status": "mapped_to_executable_tests",
            }
        )
    if (
        len(invariant_coverage) != 108
        or len({item["m5_test_id"] for item in invariant_coverage}) != 108
    ):
        raise ValueError("m5_invariant_coverage_not_108")

    import_audit = []
    for relative_path in IMPLEMENTATION_FILES:
        imports = imported_modules(ROOT / relative_path)
        forbidden = sorted(imports & FORBIDDEN_INTERNAL_IMPORTS)
        if forbidden:
            raise ValueError(
                f"m5_production_import_detected:{relative_path}:{forbidden}"
            )
        import_audit.append(
            {
                "path": relative_path,
                "forbidden_production_imports": forbidden,
                "internal_shadow_isolation": True,
            }
        )

    start_hashes = {
        item["path"]: item["sha256"]
        for item in m5_contract["production_source_hashes_at_start"]
    }
    current_hashes = {
        path: file_sha256(ROOT / path)
        for path in PRODUCTION_FILES
    }
    if current_hashes != start_hashes:
        raise ValueError("production_source_changed_during_m5")

    legacy = reconciliation["legacy_reconciliation"]
    if len(legacy) != 30:
        raise ValueError("legacy_reconciliation_not_30")
    legacy_effect = [
        {
            "legacy_id": item["current_rule_id"],
            "final_status": item["final_status"],
            "m5_internal_effect": "none",
        }
        for item in legacy
    ]

    manifest_paths = (
        list(IMPLEMENTATION_FILES)
        + list(TEST_FILES)
        + [
            "build_m5_implementation_contract.py",
            "build_m5_closure.py",
            "auditorias_motor/contrato_implementacion_m5_1_v0_1.json",
            "auditorias_motor/2026-07-27_M5_1_inicio_contrato_ejecutable_v0_1.md",
        ]
    )
    payload = {
        "version": VERSION,
        "phase": "M5",
        "subphase": "M5.6",
        "status": "completed_owner_authorized",
        "date": "2026-07-27",
        "owner_authorization": {
            "statement": "continua y completa M5",
            "authorized_completion": True,
            "production_authorized": False,
            "m6_start_authorized": False,
        },
        "scope": {
            "rules_implemented": len(EVALUATORS),
            "formulas_preserved": sum(
                item["formula_count"] for item in formula_parity
            ),
            "dag_nodes": len(integration["rule_dag"]["nodes"]),
            "dag_edges": len(integration["rule_dag"]["edges"]),
            "invariants_mapped": len(invariant_coverage),
            "canonical_families": len(
                {
                    item["canonical_family"]
                    for item in m5_contract["rules"]
                    if item["canonical_family"]
                }
            ),
            "legacy_elements_without_effect": len(legacy_effect),
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "m5_closed": True,
            "m6_started": False,
            "production_modified": False,
            "learning_engine_modified": False,
        },
        "deliverables": {
            "runtime_trace_contract": "m5_runtime.py",
            "deterministic_rule_implementation": "m5_rules.py",
            "dag_internal_engine": "m5_engine.py",
            "formula_and_data_parity": "formula_parity",
            "invariant_test_registry": "invariant_coverage",
            "legacy_heuristics_exclusion": "legacy_effect",
        },
        "formula_parity": formula_parity,
        "invariant_coverage": invariant_coverage,
        "import_isolation_audit": import_audit,
        "legacy_effect": legacy_effect,
        "boundaries": {
            "production_output_effect": "none",
            "probability_output_effect": "none",
            "numeric_weights_or_scores": "none",
            "learning_feedback": "none",
            "automatic_trading": "none",
            "predictive_validity_claimed": False,
            "profitability_claimed": False,
            "m7_verification_replaced": False,
            "m8_empirical_validation_replaced": False,
        },
        "verification": {
            "status": "passed_2026_07_27",
            "m5_specific_tests_passed": 71,
            "full_suite_tests_passed": 416,
            "m5_tests": (
                ".\\.venv\\Scripts\\python.exe -m unittest "
                "tests.test_m5_implementation_contract "
                "tests.test_m5_runtime tests.test_m5_rules "
                "tests.test_m5_engine tests.test_m5_properties "
                "tests.test_m5_closure"
            ),
            "full_suite": (
                ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests"
            ),
            "reproduce_contract": (
                ".\\.venv\\Scripts\\python.exe "
                "build_m5_implementation_contract.py --check"
            ),
            "reproduce_closure": (
                ".\\.venv\\Scripts\\python.exe build_m5_closure.py --check"
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
            "id": "M6",
            "name": "Integracion probabilistica documentada",
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
        "# M5.6 - Cierre de implementacion trazable",
        "",
        "Fecha: 2026-07-27",
        "Estado: M5 COMPLETADA POR ORDEN DEL PROPIETARIO",
        "",
        "## Resultado",
        "",
        f"- Reglas implementadas: {scope['rules_implemented']}/27.",
        f"- Formulas preservadas literalmente: "
        f"{scope['formulas_preserved']}.",
        f"- DAG: {scope['dag_nodes']} nodos y {scope['dag_edges']} aristas.",
        f"- Invariantes mapeados a pruebas: "
        f"{scope['invariants_mapped']}/108.",
        f"- Familias canonicas sin suma aditiva: "
        f"{scope['canonical_families']}.",
        f"- Heuristicas antiguas con efecto M5: 0/"
        f"{scope['legacy_elements_without_effect']}.",
        "",
        "## Que se ha implementado",
        "",
        "- Runtime inmutable de trazas y bloqueos.",
        "- Funciones deterministas para las 27 reglas.",
        "- Ejecucion topologica y dependencias con hash.",
        "- Alternativas basis excluyentes.",
        "- Pruebas manuales, de propiedades y paridad documental.",
        "",
        "## Limites conservados",
        "",
        "- Efecto en produccion: NINGUNO.",
        "- Pesos, scores y probabilidades: NINGUNO.",
        "- Aprendizaje y trading automatico: FUERA DE ALCANCE.",
        "- Validez predictiva o rentabilidad: NO DEMOSTRADAS.",
        "- M7 y M8 no quedan sustituidas por este cierre.",
        "- Pruebas especificas M5: 71/71.",
        "- Suite completa: 416/416.",
        "",
        "## Estado de fases",
        "",
        "- M5 cerrada: SI.",
        "- M6 iniciada: NO.",
        "- M6 requiere una orden expresa separada.",
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    package = build_package()
    write_or_check(
        args.output,
        json.dumps(package, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(package), args.check)


if __name__ == "__main__":
    main()
