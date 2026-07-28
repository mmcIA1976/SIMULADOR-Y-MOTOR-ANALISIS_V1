from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M4_RULES_PATH = (
    AUDIT_DIR / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
)
M4_INTEGRATION_PATH = (
    AUDIT_DIR / "integracion_dag_invariantes_m4_7_v0_2.json"
)
M4_CLOSURE_PATH = AUDIT_DIR / "paquete_revision_m4_7_v0_3.json"
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "contrato_implementacion_m5_1_v0_1.json"
)
PRODUCTION_ACTIVATION_PATH = (
    AUDIT_DIR / "2026-07-28_activacion_motor_nuevo_unico.md"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M5_1_inicio_contrato_ejecutable_v0_1.md"
)
VERSION = "M5.1-implementation-contract-v0.1"

PRODUCTION_FILES = (
    "app.py",
    "analysis_engine.py",
    "data_engine.py",
    "market_data.py",
    "liquidation_data.py",
    "challenger_engine.py",
)
TRACE_REQUIRED_FIELDS = (
    "analysis_id",
    "rule_id",
    "implementation_version",
    "executed_at",
    "status",
    "source_observations",
    "inputs",
    "outputs",
    "formula_ids",
    "invariant_results",
    "reason_codes",
    "dependencies",
    "canonical_family",
    "production_effect",
)
TRACE_STATUSES = (
    "evaluated",
    "blocked",
    "not_applicable",
    "deferred",
    "error",
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


def source_record(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing_source:{path}")
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def runtime_activation(rule_id: str) -> dict:
    if rule_id == "M4-RULE-PENDING-ACTIVATION-001":
        return {
            "state": "market_branch_only",
            "reason": (
                "Owner scope admits MARKET entries; pending-order branches "
                "remain deferred."
            ),
        }
    if rule_id == "M4-RULE-EXPECTED-VALUE-001":
        return {
            "state": "blocked_until_m6_probabilities",
            "reason": (
                "The identity must be implemented in M5 but cannot be "
                "evaluated before coherent probabilities exist in M6."
            ),
        }
    return {
        "state": "internal_shadow_only",
        "reason": "Implement and trace without changing production output.",
    }


def validate_m4_closure(closure: dict) -> None:
    if closure["status"] != "completed_owner_approved":
        raise ValueError("m4_owner_approval_missing")
    if not closure["scope"]["m4_closed"]:
        raise ValueError("m4_not_closed")
    if closure["scope"]["m5_started"]:
        raise ValueError("m4_snapshot_must_precede_m5")
    if closure["scope"]["production_modified"]:
        raise ValueError("m4_production_boundary_broken")
    approval = closure["owner_approval_record"]
    if not approval["approved"] or approval["production_authorized"]:
        raise ValueError("invalid_m4_owner_approval_scope")


def build_contract() -> dict:
    if PRODUCTION_ACTIVATION_PATH.is_file() and DEFAULT_OUTPUT_PATH.is_file():
        return read_json(DEFAULT_OUTPUT_PATH)

    rule_catalog = read_json(M4_RULES_PATH)
    integration = read_json(M4_INTEGRATION_PATH)
    closure = read_json(M4_CLOSURE_PATH)
    validate_m4_closure(closure)

    rules = rule_catalog["rules"]
    nodes = {
        node["id"]: node
        for node in integration["rule_dag"]["nodes"]
    }
    rule_ids = {rule["id"] for rule in rules}
    if len(rules) != 27 or len(rule_ids) != 27:
        raise ValueError("m5_rule_universe_not_27_unique")
    if set(nodes) != rule_ids:
        raise ValueError("m5_rule_node_universe_mismatch")

    dependencies = {rule_id: [] for rule_id in rule_ids}
    for edge in integration["rule_dag"]["edges"]:
        if edge["from"] not in rule_ids or edge["to"] not in rule_ids:
            raise ValueError("m5_unknown_dag_edge")
        dependencies[edge["to"]].append(edge["from"])

    invariant_by_rule = {rule_id: [] for rule_id in rule_ids}
    for invariant in integration["invariant_matrix"]:
        invariant_by_rule[invariant["rule_id"]].append(invariant)
    if sum(len(items) for items in invariant_by_rule.values()) != 108:
        raise ValueError("m5_invariant_universe_not_108")

    implementation_rules = []
    formula_total = 0
    for rule in sorted(rules, key=lambda item: item["sequence"]):
        formulas = rule["exact_transformation_and_formula"]
        if not isinstance(formulas, list):
            formulas = [formulas]
        formula_contracts = [
            {
                "id": f"M5-FORMULA-{rule['sequence']:02d}-{index:02d}",
                "ordinal": index,
                "expression": str(expression),
                "implementation_status": "pending_m5_code",
            }
            for index, expression in enumerate(formulas, start=1)
        ]
        formula_total += len(formula_contracts)
        invariant_contracts = [
            {
                "m4_invariant_id": item["id"],
                "m5_test_id": item["m5_required_test_id"],
                "statement": item["statement"],
                "implementation_status": "pending_m5_test",
            }
            for item in invariant_by_rule[rule["id"]]
        ]
        node = nodes[rule["id"]]
        implementation_rules.append(
            {
                "sequence": rule["sequence"],
                "rule_id": rule["id"],
                "rule_version": rule["version"],
                "name": rule["name"],
                "source_subphase": rule["source_subphase"],
                "card_role": node["card_role"],
                "computational_role": node["computational_role"],
                "canonical_family": node["canonical_family"],
                "dependencies": sorted(dependencies[rule["id"]]),
                "input_contract": rule["raw_data_and_provider"],
                "market_time_unit_freshness": (
                    rule["market_symbol_timestamp_unit_freshness"]
                ),
                "formulas": formula_contracts,
                "pseudocode": rule.get("pseudocode", []),
                "pseudocode_status": (
                    "source_preserved"
                    if rule.get("pseudocode")
                    else "not_declared_in_m4_use_formulas_only"
                ),
                "activation_conditions": rule["activation_conditions"],
                "non_application_conditions": (
                    rule["non_application_conditions"]
                ),
                "missing_data_behavior": rule["missing_data_behavior"],
                "required_trace_outputs": rule["produced_trace_fields"],
                "invariants": invariant_contracts,
                "runtime_activation": runtime_activation(rule["id"]),
                "implementation_requirement": "required_in_m5",
                "implementation_status": "contract_frozen_code_pending",
                "direct_probability_effect_authorized": False,
                "numeric_weight_authorized": False,
                "production_authorized": False,
            }
        )

    topological_order = integration["rule_dag"]["topological_order"]
    if len(topological_order) != 27 or set(topological_order) != rule_ids:
        raise ValueError("m5_topological_order_invalid")
    order = {
        rule_id: index
        for index, rule_id in enumerate(topological_order)
    }
    for rule_id, parents in dependencies.items():
        if any(order[parent] >= order[rule_id] for parent in parents):
            raise ValueError("m5_dependency_order_invalid")

    tracked_sources = (
        M4_RULES_PATH,
        M4_INTEGRATION_PATH,
        M4_CLOSURE_PATH,
        ROOT / "build_m5_implementation_contract.py",
        ROOT / "tests" / "test_m5_implementation_contract.py",
    )
    payload = {
        "version": VERSION,
        "phase": "M5",
        "subphase": "M5.1",
        "status": "completed_contract_frozen_implementation_pending",
        "date": "2026-07-27",
        "owner_authorization": {
            "authorized": True,
            "statement": "bien inicia m5",
            "authorized_at": "2026-07-27",
            "scope": "start_m5_traceable_internal_implementation",
            "production_authorized": False,
            "probability_integration_authorized": False,
            "learning_engine_authorized": False,
        },
        "scope": {
            "rules": len(implementation_rules),
            "p0_core_rules": sum(
                item["card_role"] == "p0_core_rule"
                for item in implementation_rules
            ),
            "auxiliary_operators": sum(
                item["card_role"] == "auxiliary_operator"
                for item in implementation_rules
            ),
            "formulas": formula_total,
            "invariants": sum(
                len(item["invariants"])
                for item in implementation_rules
            ),
            "dag_edges": len(integration["rule_dag"]["edges"]),
            "production_modified": False,
            "analysis_engine_modified": False,
            "m5_started": True,
            "m5_closed": False,
            "m6_started": False,
        },
        "implementation_boundary": {
            "execution_mode": "internal_shadow_only",
            "production_output_effect": "none",
            "probability_output_effect": "none",
            "numeric_weights_allowed": False,
            "learning_feedback_allowed": False,
            "automatic_trading_allowed": False,
            "presentation_layer_change_allowed": False,
            "deferred_outside_scope": integration[
                "deferred_outside_current_scope"
            ],
        },
        "trace_contract": {
            "schema_version": "M5-rule-trace-v0.1",
            "required_fields": list(TRACE_REQUIRED_FIELDS),
            "allowed_statuses": list(TRACE_STATUSES),
            "rules": [
                "evaluated requires validated inputs and explicit outputs",
                "blocked requires reason_codes and forbids synthetic neutral outputs",
                "not_applicable requires a declared non-application condition",
                "deferred requires an owner-approved scope reason",
                "every output names the formula_ids and invariant results used",
                "production_effect is always none throughout M5",
            ],
        },
        "dag": {
            "acyclic": integration["rule_dag"]["acyclic"],
            "topological_order": topological_order,
            "edges": integration["rule_dag"]["edges"],
            "alternative_input_groups": integration["rule_dag"][
                "alternative_input_groups"
            ],
        },
        "rules": implementation_rules,
        "m5_test_registry": [
            {
                "test_id": invariant["m5_required_test_id"],
                "m4_invariant_id": invariant["id"],
                "rule_id": invariant["rule_id"],
                "statement": invariant["statement"],
                "status": "required_not_implemented",
            }
            for invariant in integration["invariant_matrix"]
        ],
        "production_source_hashes_at_start": [
            source_record(ROOT / path)
            for path in PRODUCTION_FILES
        ],
        "frozen_sources": [
            source_record(path)
            for path in tracked_sources
        ],
        "next_subphase": {
            "id": "M5.2",
            "name": "Contratos de entrada, salida y traza en codigo",
            "authorized": False,
            "required_action": "continue M5 after reporting M5.1 closure",
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


def render_report(contract: dict) -> str:
    scope = contract["scope"]
    lines = [
        "# M5.1 - Inicio y contrato ejecutable",
        "",
        "Fecha: 2026-07-27",
        "Estado: M5 INICIADA; M5.1 COMPLETADA",
        "",
        "## Autorizacion",
        "",
        "Orden expresa del propietario: `bien inicia m5`.",
        "",
        "La autorizacion inicia la implementacion interna trazable. No",
        "autoriza produccion, probabilidades, aprendizaje ni trading automatico.",
        "",
        "## Alcance congelado",
        "",
        f"- Reglas: {scope['rules']} "
        f"({scope['p0_core_rules']} nucleares y "
        f"{scope['auxiliary_operators']} auxiliar).",
        f"- Formulas identificadas: {scope['formulas']}.",
        f"- Dependencias del DAG: {scope['dag_edges']}.",
        f"- Invariantes con prueba M5 obligatoria: {scope['invariants']}.",
        "- Entradas: MARKET; la rama pendiente permanece diferida.",
        "- Valor esperado: interfaz obligatoria, evaluacion bloqueada hasta M6.",
        "",
        "## Contrato de implementacion",
        "",
        "Cada regla conserva sus datos, formula literal, dependencias,",
        "condiciones, bloqueo por ausencia y campos de traza aprobados en M4.",
        "Cada formula y cada prueba futura posee un identificador estable.",
        "",
        "## Frontera",
        "",
        "- Efecto en el resultado productivo: NINGUNO.",
        "- Pesos o puntos: NO AUTORIZADOS.",
        "- Probabilidades: M6, NO INICIADA.",
        "- Motor de aprendizaje: FUERA DE ALCANCE.",
        "- M5 cerrada: NO.",
        "",
        "## Siguiente subfase",
        "",
        "`M5.2`: implementar en codigo los contratos de entrada, salida y",
        "traza antes de programar las transformaciones de las reglas.",
        "",
        "SHA-256 del payload canonico: "
        f"`{contract['canonical_payload_sha256']}`.",
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

    contract = build_contract()
    write_or_check(
        args.output,
        json.dumps(contract, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(contract), args.check)


if __name__ == "__main__":
    main()
