from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
RULE_CATALOG_PATH = (
    AUDIT_DIR / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
)
COMBINATIONS_PATH = (
    AUDIT_DIR / "catalogo_combinaciones_reconciliacion_m4_6_v0_2.json"
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "integracion_dag_invariantes_m4_7_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_7_integracion_dag_invariantes_v0_2.md"
)

VERSION = "M4.7-final-integration-v0.2"

RULE_ROLES = {
    "M4-RULE-HORIZON-SAMPLING-001": "policy_operator",
    "M4-RULE-PLAN-GEOMETRY-001": "atomic_plan_input",
    "M4-RULE-LOG-RETURNS-001": "deterministic_transformation",
    "M4-RULE-REALIZED-VOLATILITY-001": "statistical_estimator",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": "deterministic_derived",
    "M4-RULE-PENDING-ACTIVATION-001": "deferred_branch_operator",
    "M4-RULE-EXPONENTIAL-SMOOTHER-001": "auxiliary_operator",
    "M4-RULE-PATH-STRUCTURE-001": "deterministic_derived",
    "M4-RULE-PRIOR-EXTREMA-001": "deterministic_derived",
    "M4-RULE-VOLATILITY-RANK-001": "deterministic_derived",
    "M4-RULE-MTF-HIERARCHY-001": "deterministic_derived",
    "M4-RULE-CONTINUOUS-REGIME-001": "deterministic_derived",
    "M4-RULE-AGGRESSOR-IMBALANCE-001": "observed_derived",
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "observed_derived",
    "M4-RULE-PRICE-OI-STATE-001": "composite_container",
    "M4-RULE-SPOT-FUTURES-BASIS-001": "observed_derived",
    "M4-RULE-MARK-INDEX-PREMIUM-001": "observed_derived",
    "M4-RULE-FUNDING-STATE-001": "observed_derived",
    "M4-RULE-DERIVATIVES-CONTEXT-001": "composite_container",
    "M4-RULE-QUOTED-SPREAD-001": "observed_derived",
    "M4-RULE-DEPTH-SWEEP-001": "execution_derived",
    "M4-RULE-FEE-SCENARIOS-001": "economic_scenario",
    "M4-RULE-FUNDING-CASHFLOW-001": "economic_scenario",
    "M4-RULE-PLAN-EXPOSURE-001": "deterministic_from_plan",
    "M4-RULE-NET-PAYOFFS-001": "economic_derived",
    "M4-RULE-EXPECTED-VALUE-001": "economic_derived",
    "M4-RULE-EVALUATION-READINESS-001": "readiness_gate",
}

RULE_DEPENDENCIES = {
    "M4-RULE-HORIZON-SAMPLING-001": [],
    "M4-RULE-PLAN-GEOMETRY-001": [],
    "M4-RULE-LOG-RETURNS-001": ["M4-RULE-HORIZON-SAMPLING-001"],
    "M4-RULE-REALIZED-VOLATILITY-001": [
        "M4-RULE-HORIZON-SAMPLING-001",
        "M4-RULE-LOG-RETURNS-001",
    ],
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": [
        "M4-RULE-PLAN-GEOMETRY-001",
        "M4-RULE-REALIZED-VOLATILITY-001",
    ],
    "M4-RULE-PENDING-ACTIVATION-001": [
        "M4-RULE-PLAN-GEOMETRY-001",
        "M4-RULE-REALIZED-VOLATILITY-001",
    ],
    "M4-RULE-EXPONENTIAL-SMOOTHER-001": [],
    "M4-RULE-PATH-STRUCTURE-001": [
        "M4-RULE-HORIZON-SAMPLING-001",
        "M4-RULE-LOG-RETURNS-001",
    ],
    "M4-RULE-PRIOR-EXTREMA-001": ["M4-RULE-PLAN-GEOMETRY-001"],
    "M4-RULE-VOLATILITY-RANK-001": [
        "M4-RULE-REALIZED-VOLATILITY-001"
    ],
    "M4-RULE-MTF-HIERARCHY-001": ["M4-RULE-PATH-STRUCTURE-001"],
    "M4-RULE-CONTINUOUS-REGIME-001": [
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-VOLATILITY-RANK-001",
    ],
    "M4-RULE-AGGRESSOR-IMBALANCE-001": [],
    "M4-RULE-OPEN-INTEREST-CHANGE-001": [],
    "M4-RULE-PRICE-OI-STATE-001": [
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
    ],
    "M4-RULE-SPOT-FUTURES-BASIS-001": [],
    "M4-RULE-MARK-INDEX-PREMIUM-001": [],
    "M4-RULE-FUNDING-STATE-001": [],
    "M4-RULE-DERIVATIVES-CONTEXT-001": [
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
        "M4-RULE-SPOT-FUTURES-BASIS-001",
        "M4-RULE-MARK-INDEX-PREMIUM-001",
        "M4-RULE-FUNDING-STATE-001",
    ],
    "M4-RULE-QUOTED-SPREAD-001": [],
    "M4-RULE-DEPTH-SWEEP-001": ["M4-RULE-QUOTED-SPREAD-001"],
    "M4-RULE-FEE-SCENARIOS-001": [],
    "M4-RULE-FUNDING-CASHFLOW-001": ["M4-RULE-FUNDING-STATE-001"],
    "M4-RULE-PLAN-EXPOSURE-001": ["M4-RULE-PLAN-GEOMETRY-001"],
    "M4-RULE-NET-PAYOFFS-001": [
        "M4-RULE-PLAN-GEOMETRY-001",
        "M4-RULE-DEPTH-SWEEP-001",
        "M4-RULE-FEE-SCENARIOS-001",
        "M4-RULE-FUNDING-CASHFLOW-001",
        "M4-RULE-PLAN-EXPOSURE-001",
    ],
    "M4-RULE-EXPECTED-VALUE-001": ["M4-RULE-NET-PAYOFFS-001"],
    "M4-RULE-EVALUATION-READINESS-001": [
        "M4-RULE-NET-PAYOFFS-001",
        "M4-RULE-EXPECTED-VALUE-001",
    ],
}

CANONICAL_FAMILIES = {
    "M4-RULE-HORIZON-SAMPLING-001": "M4-FAMILY-SAMPLING",
    "M4-RULE-PLAN-GEOMETRY-001": "M4-FAMILY-PLAN-GEOMETRY",
    "M4-RULE-LOG-RETURNS-001": "M4-FAMILY-RETURNS-VOLATILITY",
    "M4-RULE-REALIZED-VOLATILITY-001": "M4-FAMILY-RETURNS-VOLATILITY",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": "M4-FAMILY-REACHABILITY",
    "M4-RULE-PENDING-ACTIVATION-001": "M4-FAMILY-PENDING-ACTIVATION",
    "M4-RULE-PATH-STRUCTURE-001": "M4-FAMILY-PATH-STRUCTURE",
    "M4-RULE-PRIOR-EXTREMA-001": "M4-FAMILY-PATH-STRUCTURE",
    "M4-RULE-VOLATILITY-RANK-001": "M4-FAMILY-VOLATILITY-REGIME",
    "M4-RULE-MTF-HIERARCHY-001": "M4-FAMILY-PATH-STRUCTURE",
    "M4-RULE-CONTINUOUS-REGIME-001": "M4-FAMILY-VOLATILITY-REGIME",
    "M4-RULE-AGGRESSOR-IMBALANCE-001": "M4-FAMILY-AGGRESSOR-FLOW",
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "M4-FAMILY-OPEN-INTEREST",
    "M4-RULE-PRICE-OI-STATE-001": "M4-FAMILY-OPEN-INTEREST",
    "M4-RULE-SPOT-FUTURES-BASIS-001": "M4-FAMILY-BASIS",
    "M4-RULE-MARK-INDEX-PREMIUM-001": "M4-FAMILY-BASIS",
    "M4-RULE-FUNDING-STATE-001": "M4-FAMILY-FUNDING",
    "M4-RULE-DERIVATIVES-CONTEXT-001": "M4-FAMILY-DERIVATIVES-CONTAINER",
    "M4-RULE-QUOTED-SPREAD-001": "M4-FAMILY-EXECUTION",
    "M4-RULE-DEPTH-SWEEP-001": "M4-FAMILY-EXECUTION",
    "M4-RULE-FEE-SCENARIOS-001": "M4-FAMILY-FEES",
    "M4-RULE-FUNDING-CASHFLOW-001": "M4-FAMILY-FUNDING-CASHFLOW",
    "M4-RULE-PLAN-EXPOSURE-001": "M4-FAMILY-EXPOSURE",
    "M4-RULE-NET-PAYOFFS-001": "M4-FAMILY-ECONOMIC-EVALUATION",
    "M4-RULE-EXPECTED-VALUE-001": "M4-FAMILY-ECONOMIC-EVALUATION",
    "M4-RULE-EVALUATION-READINESS-001": "M4-FAMILY-ECONOMIC-EVALUATION",
}

TEST_MODULE_BY_SUBPHASE = {
    "M4.2": "tests.test_m4_reachability",
    "M4.3": "tests.test_m4_structure_regime",
    "M4.4": "tests.test_m4_derivatives_context",
    "M4.5": "tests.test_m4_execution_risk",
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


def topological_order(rule_ids: set[str]) -> list[str]:
    remaining = {
        rule_id: set(RULE_DEPENDENCIES[rule_id])
        for rule_id in rule_ids
    }
    ordered = []
    while remaining:
        ready = sorted(
            rule_id
            for rule_id, dependencies in remaining.items()
            if not dependencies
        )
        if not ready:
            raise ValueError("rule_dag_contains_cycle")
        ordered.extend(ready)
        for rule_id in ready:
            del remaining[rule_id]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return ordered


def build_invariant_matrix(rules: list[dict]) -> list[dict]:
    matrix = []
    for rule in rules:
        statements = rule["unit_tests_limits_and_invariants"]
        if not isinstance(statements, list):
            statements = [statements]
        for index, statement in enumerate(statements, start=1):
            matrix.append(
                {
                    "id": (
                        f"M4-INV-{rule['sequence']:02d}-{index:02d}"
                    ),
                    "rule_id": rule["id"],
                    "source_subphase": rule["source_subphase"],
                    "statement": str(statement),
                    "m4_reference_test_module": TEST_MODULE_BY_SUBPHASE[
                        rule["source_subphase"]
                    ],
                    "m4_verification_status": "formal_contract_present",
                    "m5_required_test_id": (
                        f"M5-TEST-{rule['sequence']:02d}-{index:02d}"
                    ),
                    "m5_production_gate_status": "pending_m5_implementation",
                }
            )
    return matrix


def build_catalog() -> dict:
    rule_catalog = read_json(RULE_CATALOG_PATH)
    combinations = read_json(COMBINATIONS_PATH)
    rules = rule_catalog["rules"]
    rule_ids = {rule["id"] for rule in rules}
    if len(rules) != 27 or len(rule_ids) != 27:
        raise ValueError("final_rule_universe_not_27_unique")
    if set(RULE_ROLES) != rule_ids:
        raise ValueError("rule_role_registry_not_exact")
    if set(RULE_DEPENDENCIES) != rule_ids:
        raise ValueError("rule_dependency_registry_not_exact")
    if set(CANONICAL_FAMILIES) != (
        rule_ids - {"M4-RULE-EXPONENTIAL-SMOOTHER-001"}
    ):
        raise ValueError("canonical_family_registry_not_exact")
    for rule_id, dependencies in RULE_DEPENDENCIES.items():
        if not set(dependencies).issubset(rule_ids - {rule_id}):
            raise ValueError(f"unknown_or_self_dependency:{rule_id}")

    ordered = topological_order(rule_ids)
    position = {rule_id: index for index, rule_id in enumerate(ordered)}
    edges = [
        {
            "from": dependency,
            "to": rule_id,
            "relation": (
                "alternative_basis_input"
                if rule_id == "M4-RULE-DERIVATIVES-CONTEXT-001"
                and dependency in {
                    "M4-RULE-SPOT-FUTURES-BASIS-001",
                    "M4-RULE-MARK-INDEX-PREMIUM-001",
                }
                else "declared_computational_dependency"
            ),
        }
        for rule_id, dependencies in RULE_DEPENDENCIES.items()
        for dependency in dependencies
    ]
    if any(position[edge["from"]] >= position[edge["to"]] for edge in edges):
        raise ValueError("invalid_topological_order")

    nodes = [
        {
            "id": rule["id"],
            "sequence": rule["sequence"],
            "name": rule["name"],
            "source_subphase": rule["source_subphase"],
            "card_role": rule["card_role"],
            "computational_role": RULE_ROLES[rule["id"]],
            "canonical_family": CANONICAL_FAMILIES.get(rule["id"]),
            "additive_vote_authorized": False,
            "production_authorized": False,
        }
        for rule in rules
    ]
    invariant_matrix = build_invariant_matrix(rules)
    hypotheses = [
        {
            "id": rule["separate_predictive_hypothesis"]["id"],
            "origin_rule_id": rule["id"],
            "status": rule["separate_predictive_hypothesis"]["status"],
            "production_weight_authorized": False,
        }
        for rule in rules
        if rule["separate_predictive_hypothesis"] is not None
    ]
    if len(hypotheses) != 15:
        raise ValueError("final_hypothesis_inventory_not_15")

    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.7",
        "status": "technical_integration_complete_owner_approval_pending",
        "date": "2026-07-27",
        "scope": {
            "rules": len(nodes),
            "p0_core_rules": sum(
                node["card_role"] == "p0_core_rule" for node in nodes
            ),
            "auxiliary_operators": sum(
                node["card_role"] == "auxiliary_operator" for node in nodes
            ),
            "dag_edges": len(edges),
            "canonical_families": len(set(CANONICAL_FAMILIES.values())),
            "invariants": len(invariant_matrix),
            "hypotheses": len(hypotheses),
            "feature_slots": len(combinations["feature_slots"]),
            "relations": len(combinations["relation_matrix"]),
            "combinations": len(combinations["preregistered_combinations"]),
            "production_modified": False,
            "m4_closed": False,
            "m5_started": False,
        },
        "rule_dag": {
            "nodes": nodes,
            "edges": edges,
            "topological_order": ordered,
            "acyclic": True,
            "alternative_input_groups": [
                {
                    "id": "M4-ALT-BASIS-MODE-001",
                    "target_rule": "M4-RULE-DERIVATIVES-CONTEXT-001",
                    "members": [
                        "M4-RULE-SPOT-FUTURES-BASIS-001",
                        "M4-RULE-MARK-INDEX-PREMIUM-001",
                    ],
                    "simultaneous_additive_use_authorized": False,
                }
            ],
        },
        "canonical_family_assignment": [
            {
                "rule_id": rule_id,
                "family_id": family_id,
                "assignment_count": 1,
                "additive_duplicate_route_authorized": False,
            }
            for rule_id, family_id in sorted(CANONICAL_FAMILIES.items())
        ],
        "invariant_matrix": invariant_matrix,
        "hypothesis_inventory": hypotheses,
        "future_promotion_gate": {
            "id": "M8-GATE-RULE-PROMOTION-001",
            "status": "registered_not_active",
            "empirical_thresholds_defined": False,
            "activation_phase": "M8",
            "requires_independent_temporal_validation": True,
            "production_promotion_authorized": False,
        },
        "deferred_outside_current_scope": [
            "pending_order_automation",
            "analysis_revalidation_policy",
            "automatic_time_expiry_execution",
            "production_first_passage_correction",
        ],
        "integration_assertions": {
            "all_rules_in_dag": True,
            "dag_acyclic": True,
            "one_canonical_family_per_core_rule": True,
            "auxiliary_excluded_from_evidence_vote": True,
            "all_invariants_have_future_test_ids": True,
            "probability_weights_authorized": 0,
            "production_rules_authorized": 0,
        },
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(path),
            }
            for path in (RULE_CATALOG_PATH, COMBINATIONS_PATH)
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "rule_dag": payload["rule_dag"],
                "canonical_family_assignment": payload[
                    "canonical_family_assignment"
                ],
                "invariant_matrix": payload["invariant_matrix"],
                "hypothesis_inventory": payload["hypothesis_inventory"],
                "future_promotion_gate": payload["future_promotion_gate"],
                "deferred_outside_current_scope": payload[
                    "deferred_outside_current_scope"
                ],
                "integration_assertions": payload["integration_assertions"],
            }
        )
    )
    return payload


def render_report(catalog: dict) -> str:
    scope = catalog["scope"]
    lines = [
        "# M4.7 - Integracion final: DAG e invariantes",
        "",
        "Fecha: 2026-07-27",
        "Estado: INTEGRACION TECNICA COMPLETA; APROBACION PENDIENTE",
        "",
        "## Resultado",
        "",
        f"- Reglas en el DAG: {scope['rules']}/27.",
        f"- Reglas nucleares: {scope['p0_core_rules']}; auxiliares: "
        f"{scope['auxiliary_operators']}.",
        f"- Aristas declaradas: {scope['dag_edges']}.",
        f"- Familias canonicas: {scope['canonical_families']}.",
        f"- Invariantes trazados: {scope['invariants']}.",
        f"- Hipotesis enlazadas: {scope['hypotheses']}/15.",
        "- Ciclos: 0.",
        "- Pesos, votos aditivos y reglas productivas autorizados: 0.",
        "",
        "## Garantias",
        "",
        "- Cada regla nuclear tiene una sola familia canonica.",
        "- El suavizador exponencial queda fuera del voto de evidencia.",
        "- Spot-futures y mark-index son alternativas, no sumandos.",
        "- Cada invariante posee ID estable y futura prueba M5.",
        "- La puerta M8 queda registrada sin inventar umbrales.",
        "- Produccion no se ha modificado.",
        "",
        "## Fuera de alcance",
        "",
    ]
    for item in catalog["deferred_outside_current_scope"]:
        lines.append(f"- `{item}`")
    lines.extend(
        [
            "",
            "M4 permanece abierta hasta aprobacion expresa del propietario.",
            "",
            "SHA-256 del payload canonico: "
            f"`{catalog['canonical_payload_sha256']}`.",
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
    catalog = build_catalog()
    write_or_check(
        args.output,
        json.dumps(catalog, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(catalog), args.check)


if __name__ == "__main__":
    main()
