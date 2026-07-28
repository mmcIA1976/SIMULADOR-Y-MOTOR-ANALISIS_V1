from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M4_CATALOG_PATHS = (
    AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json",
    AUDIT_DIR / "catalogo_alcanzabilidad_m4_2_v0_2.json",
    AUDIT_DIR / "catalogo_regimen_estructura_mtf_m4_3_v0_2.json",
    AUDIT_DIR / "catalogo_contexto_derivados_m4_4_v0_2.json",
    AUDIT_DIR / "catalogo_ejecucion_riesgo_m4_5_v0_2.json",
    AUDIT_DIR / "catalogo_combinaciones_reconciliacion_m4_6_v0_2.json",
)
FINAL_INTEGRATION_PATH = (
    AUDIT_DIR / "integracion_dag_invariantes_m4_7_v0_2.json"
)
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "paquete_revision_m4_7_v0_3.json"
PRODUCTION_ACTIVATION_PATH = (
    AUDIT_DIR / "2026-07-28_activacion_motor_nuevo_unico.md"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_7_paquete_revision_cerrado_v0_3.md"
)
VERSION = "M4.7-owner-review-package-v0.3"
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = ("intraday_short", "intraday_wide", "short_swing")
P0_BLOCKS = (1, 3, 7, 9, 10, 15, 24, 26, 28, 29, 30, 32)

GENERATORS = (
    "build_m4_reconciliation.py",
    "build_m4_reachability.py",
    "build_m4_structure_regime.py",
    "build_m4_derivatives_context.py",
    "build_m4_execution_risk.py",
    "build_m4_combinations.py",
    "build_m4_rule_audit_report.py",
    "build_m4_final_integration.py",
)
REPORTS = (
    "auditorias_motor/2026-07-27_M4_1_alcance_reconciliacion_resultado.md",
    "auditorias_motor/2026-07-27_M4_2_alcanzabilidad_enmienda_v0_2.md",
    "auditorias_motor/2026-07-27_M4_3_regimen_estructura_mtf_enmienda_v0_2.md",
    "auditorias_motor/2026-07-27_M4_4_orderflow_oi_basis_funding_enmienda_v0_2.md",
    "auditorias_motor/2026-07-27_M4_5_ejecucion_costes_riesgo_enmienda_v0_2.md",
    "auditorias_motor/2026-07-27_M4_6_combinaciones_reconciliacion_enmienda_v0_2.md",
    "auditorias_motor/2026-07-27_M4_7_27_reglas_formulas_enmienda_v0_2.md",
    "auditorias_motor/2026-07-27_M4_7_integracion_dag_invariantes_v0_2.md",
)
OWNER_AUDIT_ARTIFACTS = (
    "auditorias_motor/catalogo_27_reglas_formulas_m4_7_v0_2.json",
    "auditorias_motor/manifiesto_integridad_m4_7_v0_2.json",
    "auditorias_motor/2026-07-27_M4_7_enmiendas_olas_1_2_resultado.md",
    "auditorias_motor/2026-07-27_M4_7_decision_P1_entradas_market.md",
    "auditorias_motor/integracion_dag_invariantes_m4_7_v0_2.json",
    "auditorias_motor/2026-07-27_M4_cierre_aprobado_propietario.md",
)
TESTS = (
    "tests/test_m4_reconciliation.py",
    "tests/test_m4_reachability.py",
    "tests/test_m4_structure_regime.py",
    "tests/test_m4_derivatives_context.py",
    "tests/test_m4_execution_risk.py",
    "tests/test_m4_combinations.py",
    "tests/test_m4_rule_audit_report.py",
    "tests/test_m4_final_integration.py",
    "tests/test_m4_review_package.py",
)
PRODUCTION_FILES = (
    "app.py",
    "analysis_engine.py",
    "data_engine.py",
    "market_data.py",
    "liquidation_data.py",
    "challenger_engine.py",
)

RULE_REQUIRED_FIELDS = (
    "id",
    "version",
    "name",
    "analytical_blocks",
    "concrete_objective",
    "rule_type",
    "raw_data_and_provider",
    "market_symbol_timestamp_unit_freshness",
    "exact_transformation_and_formula",
    "cross_pair_normalization",
    "applicable_horizons",
    "activation_conditions",
    "non_application_conditions",
    "source_and_exact_supported_claim",
    "claims_not_supported_by_source",
    "expected_relation_to_tp_sl_or_expiry",
    "related_rules",
    "double_counting_control",
    "missing_data_behavior",
    "unit_tests_limits_and_invariants",
    "trace_output",
    "refutation_suspension_or_withdrawal",
    "lifecycle_status",
    "direct_probability_effect_authorized",
    "numeric_weight_authorized",
    "production_authorized",
)

COMBINATION_REQUIRED_FIELDS = (
    "id",
    "version",
    "name",
    "layer",
    "parent_slots",
    "parent_rules",
    "parent_hypotheses",
    "operator_and_order",
    "mutually_exclusive_or_duplicate_inputs",
    "activation_and_block_conditions",
    "source_and_exact_supported_claim",
    "claims_not_supported_by_source",
    "double_counting_control",
    "missing_data_behavior",
    "trace_output",
    "null_or_refutation_statement",
    "refutation_suspension_or_withdrawal",
    "lifecycle_status",
    "direct_probability_effect_authorized",
    "numeric_weight_authorized",
    "production_authorized",
    "m6_model_authorized",
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


def validate_rule_contract(catalog: dict) -> list[dict]:
    source_ids = {source["id"] for source in catalog["sources"]}
    normalized = []
    for rule in catalog["rules"]:
        missing = [
            field
            for field in RULE_REQUIRED_FIELDS
            if field not in rule or rule[field] in (None, "", [])
        ]
        if missing:
            raise ValueError(
                f"incomplete_rule_contract:{rule['id']}:{','.join(missing)}"
            )
        used_sources = {
            source["source_id"]
            for source in rule["source_and_exact_supported_claim"]
        }
        if not used_sources.issubset(source_ids):
            raise ValueError(f"unknown_rule_source:{rule['id']}")
        if (
            rule["direct_probability_effect_authorized"]
            or rule["numeric_weight_authorized"]
            or rule["production_authorized"]
        ):
            raise ValueError(f"unauthorized_rule_effect:{rule['id']}")
        normalized.append(
            {
                "id": rule["id"],
                "subphase": catalog["subphase"],
                "name": rule["name"],
                "analytical_blocks": rule["analytical_blocks"],
                "formula_count": len(rule["exact_transformation_and_formula"]),
                "source_ids": sorted(used_sources),
                "has_trace_contract": True,
                "has_refutation_contract": True,
                "predictive_hypothesis_id": (
                    rule["separate_predictive_hypothesis"]["id"]
                    if rule["separate_predictive_hypothesis"]
                    else None
                ),
                "probability_effect_authorized": False,
                "production_authorized": False,
            }
        )
    return normalized


def build_decisions() -> list[dict]:
    return [
        {
            "id": "M4-OWNER-DECISION-001",
            "question": (
                "Aceptar provisionalmente las 26 reglas nucleares y el "
                "operador auxiliar corregidos en v0.2."
            ),
            "acceptance_means": (
                "Se aceptan las enmiendas de las olas 1 y 2; el conjunto final "
                "sigue sujeto a P1-P4 y a la regeneracion del DAG."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-DECISION-002",
            "question": (
                "Aceptar las 15 hipotesis como universo candidato no "
                "verificado para M6-M8."
            ),
            "acceptance_means": (
                "No podran agregarse efectos retrospectivamente sin nueva "
                "version y nueva aprobacion."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-DECISION-003",
            "question": (
                "Aceptar los 15 slots, 16 relaciones y 8 combinaciones "
                "prerregistradas de M4.6."
            ),
            "acceptance_means": (
                "Se prohibe contar dos veces padres, etiquetas, contenedores "
                "o fuentes alternativas."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-DECISION-004",
            "question": (
                "Aceptar la disposicion final de los 30 elementos antiguos."
            ),
            "acceptance_means": (
                "Ningun punto, penalizacion o ajuste antiguo pasa al motor "
                "nuevo por herencia."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-DECISION-005",
            "question": (
                "Aceptar los limites que permanecen bloqueados para fases "
                "posteriores."
            ),
            "acceptance_means": (
                "Probabilidades, coeficientes, validacion, riesgo de cuenta y "
                "politica de decision siguen sin resolverse en M4."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-DECISION-006",
            "question": "Cerrar M4 sin iniciar M5.",
            "acceptance_means": (
                "Completa M4; M5 requiere otra orden expresa y siguen sin "
                "autorizarse produccion, pesos, rentabilidad ni trading real."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-P1-ORDER-TYPES",
            "question": (
                "Aplicar solo entradas MARKET en el alcance inmediato."
            ),
            "acceptance_means": (
                "LIMIT, STOP_MARKET, STOP_LIMIT, triggers y timeInForce quedan "
                "diferidos hasta que exista operacion autonoma continua."
            ),
            "status": "resolved_owner_approved_2026_07_27",
        },
        {
            "id": "M4-OWNER-P2-PRICE-REFERENCES",
            "question": (
                "Definir las referencias de precio para entrada, TP y SL."
            ),
            "acceptance_means": (
                "Los analisis nuevos registraran CONTRACT_PRICE o MARK_PRICE; "
                "los historicos sin evidencia quedaran como referencia "
                "desconocida."
            ),
            "status": "deferred_outside_current_m4_scope_owner_direction",
        },
        {
            "id": "M4-OWNER-P3-LIQUIDATION-SEMANTICS",
            "question": (
                "Definir la liquidacion cuando no existe estado completo de cuenta."
            ),
            "acceptance_means": (
                "Solo el margen aislado con datos suficientes podra producir "
                "un escenario; cross o modo desconocido quedaran unknown y "
                "bloquearan payoff apalancado, no probabilidad fisica."
            ),
            "status": "deferred_outside_current_m4_scope_owner_direction",
        },
        {
            "id": "M4-OWNER-P4-EXPIRY-PAYOFF",
            "question": "Definir el cierre y payoff de la rama expiry.",
            "acceptance_means": (
                "El payoff pre-trade sera una variable o distribucion "
                "condicional; no se inventara un precio terminal puntual."
            ),
            "status": "deferred_outside_current_m4_scope_owner_direction",
        },
    ]


def build_catalog() -> dict:
    if PRODUCTION_ACTIVATION_PATH.is_file() and DEFAULT_OUTPUT_PATH.is_file():
        return json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))

    catalogs = [read_json(path) for path in M4_CATALOG_PATHS]
    final_integration = read_json(FINAL_INTEGRATION_PATH)
    m4_1, m4_2, m4_3, m4_4, m4_5, m4_6 = catalogs
    expected_subphases = ("M4.1", "M4.2", "M4.3", "M4.4", "M4.5", "M4.6")
    if tuple(catalog["subphase"] for catalog in catalogs) != expected_subphases:
        raise ValueError("unexpected_m4_subphase_order")
    if any(
        catalog["status"]
        != "completed_internal_milestone_m4_still_in_progress"
        for catalog in catalogs
    ):
        raise ValueError("upstream_m4_subphase_not_completed")

    rule_catalogs = (m4_2, m4_3, m4_4, m4_5)
    rule_audit = [
        rule
        for catalog in rule_catalogs
        for rule in validate_rule_contract(catalog)
    ]
    rule_ids = [rule["id"] for rule in rule_audit]
    if len(rule_ids) != 27 or len(rule_ids) != len(set(rule_ids)):
        raise ValueError("rule_review_universe_not_27_unique")

    hypotheses = [
        hypothesis
        for catalog in rule_catalogs
        for hypothesis in catalog["preregistered_hypotheses"]
    ]
    hypothesis_ids = [hypothesis["id"] for hypothesis in hypotheses]
    if len(hypothesis_ids) != 15 or len(hypothesis_ids) != len(
        set(hypothesis_ids)
    ):
        raise ValueError("hypothesis_review_universe_not_15_unique")
    linked_hypotheses = {
        rule["predictive_hypothesis_id"]
        for rule in rule_audit
        if rule["predictive_hypothesis_id"]
    }
    if linked_hypotheses != set(hypothesis_ids):
        raise ValueError("hypothesis_rule_linkage_not_exact")

    combinations = m4_6["preregistered_combinations"]
    combination_source_ids = {source["id"] for source in m4_6["sources"]}
    for item in combinations:
        missing = [
            field
            for field in COMBINATION_REQUIRED_FIELDS
            if field not in item
            or (
                item[field] in (None, "", [])
                and field != "parent_hypotheses"
            )
        ]
        if missing:
            raise ValueError(
                f"incomplete_combination:{item['id']}:{','.join(missing)}"
            )
        used_sources = {
            source["source_id"]
            for source in item["source_and_exact_supported_claim"]
        }
        if not used_sources.issubset(combination_source_ids):
            raise ValueError(f"unknown_combination_source:{item['id']}")
        if (
            item["direct_probability_effect_authorized"]
            or item["numeric_weight_authorized"]
            or item["production_authorized"]
            or item["m6_model_authorized"]
        ):
            raise ValueError(f"unauthorized_combination:{item['id']}")
    if len(combinations) != 8:
        raise ValueError("combination_review_universe_not_8")

    legacy = m4_6["legacy_reconciliation"]
    if len(legacy) != 30 or m4_6["summary"]["unresolved_legacy_elements"] != 0:
        raise ValueError("legacy_review_not_complete")
    if {item["block"] for item in m4_6["p0_block_coverage"]} != set(
        P0_BLOCKS
    ):
        raise ValueError("p0_review_not_complete")
    if len(m4_6["feature_slots"]) != 15:
        raise ValueError("slot_review_not_complete")
    if len(m4_6["relation_matrix"]) != 16:
        raise ValueError("relation_review_not_complete")
    if final_integration["status"] != (
        "technical_integration_complete_owner_approval_pending"
    ):
        raise ValueError("m4_7_final_integration_not_complete")
    if (
        final_integration["scope"]["rules"] != 27
        or not final_integration["rule_dag"]["acyclic"]
        or final_integration["scope"]["p0_core_rules"] != 26
        or final_integration["scope"]["auxiliary_operators"] != 1
    ):
        raise ValueError("m4_7_final_integration_contract_invalid")

    manifest_paths = (
        list(GENERATORS)
        + [str(path.relative_to(ROOT)).replace("\\", "/") for path in M4_CATALOG_PATHS]
        + list(REPORTS)
        + list(OWNER_AUDIT_ARTIFACTS)
        + list(TESTS)
    )
    manifest = [artifact_record(path) for path in manifest_paths]
    if len({item["path"] for item in manifest}) != len(manifest):
        raise ValueError("duplicate_manifest_path")
    production_hashes = [
        artifact_record(path) for path in PRODUCTION_FILES
    ]

    decisions = build_decisions()
    owner_approval_record = {
        "approved": True,
        "approved_at": "2026-07-27",
        "owner_statement": "cierra M4",
        "scope": "documentary_and_technical_m4_only",
        "predictive_validation_claimed": False,
        "profitability_claimed": False,
        "production_authorized": False,
        "m5_start_authorized": False,
        "deferred_work_preserved": True,
    }
    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.7",
        "status": "completed_owner_approved",
        "date": "2026-07-27",
        "scope": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "p0_blocks": list(P0_BLOCKS),
            "rules_reviewed": len(rule_audit),
            "p0_core_rules_reviewed": 26,
            "auxiliary_operators_reviewed": 1,
            "hypotheses_reviewed": len(hypotheses),
            "combinations_reviewed": len(combinations),
            "legacy_elements_reviewed": len(legacy),
            "feature_slots_reviewed": len(m4_6["feature_slots"]),
            "relations_reviewed": len(m4_6["relation_matrix"]),
            "dag_nodes_reviewed": final_integration["scope"]["rules"],
            "dag_edges_reviewed": final_integration["scope"]["dag_edges"],
            "invariants_reviewed": final_integration["scope"]["invariants"],
            "canonical_families_reviewed": final_integration["scope"][
                "canonical_families"
            ],
            "manifest_artifacts": len(manifest),
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m4_closed": True,
            "m5_started": False,
        },
        "meaning_of_owner_approval": {
            "does_mean": [
                "accept amendment waves 1 and 2 plus final technical integration",
                "freeze hypotheses and combinations before empirical results",
                "complete M4 while leaving M5 subject to a separate owner order",
            ],
            "does_not_mean": [
                "rules are empirically validated",
                "probabilities or coefficients already exist",
                "profitability is established",
                "production deployment or automatic trading is authorized",
            ],
        },
        "technical_review": {
            "rule_contract_complete": True,
            "source_claim_and_transfer_limit_complete": True,
            "trace_and_refutation_complete": True,
            "hypothesis_linkage_complete": True,
            "double_counting_registry_complete": True,
            "legacy_reconciliation_complete": True,
            "p0_block_coverage_complete": True,
            "reproducible_artifact_manifest_complete": True,
            "amendment_waves_1_2_complete": True,
            "p1_order_scope_complete": True,
            "operational_extensions_deferred": True,
            "final_dag_and_invariants_complete": True,
            "owner_approval_complete": True,
        },
        "owner_approval_record": owner_approval_record,
        "rule_audit": rule_audit,
        "hypotheses": hypotheses,
        "combinations": [
            {
                "id": item["id"],
                "name": item["name"],
                "layer": item["layer"],
                "parent_slots": item["parent_slots"],
                "parent_hypotheses": item["parent_hypotheses"],
                "status": item["status"],
                "has_operator": True,
                "has_sources": True,
                "has_trace_contract": True,
                "has_refutation_contract": True,
                "probability_effect_authorized": False,
                "production_authorized": False,
            }
            for item in combinations
        ],
        "legacy_disposition_summary": {
            status: sum(
                1 for row in legacy if row["final_status"] == status
            )
            for status in sorted({row["final_status"] for row in legacy})
        },
        "known_limits_preserved": m4_6["unresolved_for_later_phases"],
        "final_integration": {
            "version": final_integration["version"],
            "status": final_integration["status"],
            "dag_acyclic": final_integration["rule_dag"]["acyclic"],
            "dag_nodes": final_integration["scope"]["rules"],
            "dag_edges": final_integration["scope"]["dag_edges"],
            "canonical_families": final_integration["scope"][
                "canonical_families"
            ],
            "invariants": final_integration["scope"]["invariants"],
            "future_promotion_gate": final_integration[
                "future_promotion_gate"
            ],
            "deferred_outside_current_scope": final_integration[
                "deferred_outside_current_scope"
            ],
        },
        "owner_decisions": decisions,
        "owner_audit_surfaces": {
            "human_readable_rule_catalog": (
                "auditorias_motor/"
                "2026-07-27_M4_7_27_reglas_formulas_enmienda_v0_2.md"
            ),
            "structured_rule_catalog": (
                "auditorias_motor/"
                "catalogo_27_reglas_formulas_m4_7_v0_2.json"
            ),
            "integrity_manifest": (
                "auditorias_motor/manifiesto_integridad_m4_7_v0_2.json"
            ),
            "amendment_result": (
                "auditorias_motor/"
                "2026-07-27_M4_7_enmiendas_olas_1_2_resultado.md"
            ),
            "dag_and_invariant_integration": (
                "auditorias_motor/"
                "2026-07-27_M4_7_integracion_dag_invariantes_v0_2.md"
            ),
            "review_decisions": (
                "auditorias_motor/"
                "2026-07-27_M4_7_paquete_revision_cerrado_v0_3.md"
            ),
            "owner_closure_record": (
                "auditorias_motor/"
                "2026-07-27_M4_cierre_aprobado_propietario.md"
            ),
        },
        "closure_gate": {
            "technical_gate": "passed",
            "owner_gate": "passed",
            "m4_close_authorized": True,
            "m5_start_authorized": False,
            "required_final_action": "none_for_m4_closure",
            "next_required_action": (
                "explicit owner authorization to start M5"
            ),
        },
        "reproduction": {
            "python": ".\\.venv\\Scripts\\python.exe",
            "generate_in_order": [
                f".\\.venv\\Scripts\\python.exe {script}"
                for script in GENERATORS
            ],
            "check_in_order": [
                f".\\.venv\\Scripts\\python.exe {script} --check"
                for script in GENERATORS
            ],
            "m4_tests": (
                ".\\.venv\\Scripts\\python.exe -m unittest "
                "tests.test_m4_reconciliation tests.test_m4_reachability "
                "tests.test_m4_structure_regime "
                "tests.test_m4_derivatives_context "
                "tests.test_m4_execution_risk "
                "tests.test_m4_combinations "
                "tests.test_m4_rule_audit_report "
                "tests.test_m4_final_integration "
                "tests.test_m4_review_package"
            ),
            "full_tests": (
                ".\\.venv\\Scripts\\python.exe -m unittest discover -s tests"
            ),
        },
        "artifact_manifest": manifest,
        "production_source_hashes_at_review": production_hashes,
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(path),
            }
            for path in (
                ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
                *M4_CATALOG_PATHS,
                FINAL_INTEGRATION_PATH,
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "scope": payload["scope"],
                "meaning_of_owner_approval": payload[
                    "meaning_of_owner_approval"
                ],
                "technical_review": payload["technical_review"],
                "owner_approval_record": payload["owner_approval_record"],
                "rule_audit": payload["rule_audit"],
                "hypotheses": payload["hypotheses"],
                "combinations": payload["combinations"],
                "legacy_disposition_summary": payload[
                    "legacy_disposition_summary"
                ],
                "known_limits_preserved": payload["known_limits_preserved"],
                "final_integration": payload["final_integration"],
                "owner_decisions": payload["owner_decisions"],
                "owner_audit_surfaces": payload["owner_audit_surfaces"],
                "closure_gate": payload["closure_gate"],
                "reproduction": payload["reproduction"],
                "artifact_manifest": payload["artifact_manifest"],
                "production_source_hashes_at_review": payload[
                    "production_source_hashes_at_review"
                ],
            }
        )
    )
    return payload


def render_report(package: dict) -> str:
    lines = [
        "# M4.7 - Paquete de revision del propietario",
        "",
        "Fecha: 2026-07-27",
        "Estado: M4 COMPLETADA Y APROBADA POR EL PROPIETARIO",
        "",
        "## 1. Que se revisa",
        "",
        f"- {package['scope']['rules_reviewed']} reglas formales completas.",
        f"- {package['scope']['hypotheses_reviewed']} hipotesis no verificadas.",
        f"- {package['scope']['feature_slots_reviewed']} slots canonicos.",
        f"- {package['scope']['relations_reviewed']} relaciones anti-duplicidad.",
        f"- {package['scope']['dag_nodes_reviewed']} nodos y "
        f"{package['scope']['dag_edges_reviewed']} aristas sin ciclos.",
        f"- {package['scope']['invariants_reviewed']} invariantes trazados.",
        f"- {package['scope']['combinations_reviewed']} combinaciones.",
        f"- {package['scope']['legacy_elements_reviewed']} elementos antiguos.",
        f"- {package['scope']['manifest_artifacts']} artefactos con hash.",
        "",
        "## 2. Significado exacto de aprobar M4",
        "",
        "Aprobar significa aceptar las enmiendas y su integracion tecnica final.",
        "No significa que las reglas ya sean predictivas, rentables o aptas",
        "para produccion. Los temas operativos apartados siguen diferidos.",
        "",
        "## 3. Resultado tecnico",
        "",
        "- Formula, datos, unidades y condiciones: completos 27/27.",
        "- Fuente y limite de transferencia: completos 27/27.",
        "- Traza y regla de refutacion: completas 27/27.",
        "- Hipotesis enlazadas con ficha: 15/15.",
        "- Reconciliacion antigua: 30/30, sin efecto heredado.",
        "- Bloques P0: 12/12.",
        "- DAG: 27/27 reglas, 0 ciclos.",
        "- Invariantes: todos con ID y prueba futura M5.",
        "- Pesos, puntos y efectos productivos autorizados: 0.",
        "",
        "## 4. Reglas",
        "",
        "| ID | Subfase | Nombre | Hipotesis |",
        "|---|---|---|---|",
    ]
    for rule in package["rule_audit"]:
        hypothesis = rule["predictive_hypothesis_id"] or "ninguna"
        lines.append(
            f"| `{rule['id']}` | {rule['subphase']} | "
            f"{rule['name']} | `{hypothesis}` |"
        )
    lines.extend(
        [
            "",
            "## 5. Combinaciones",
            "",
            "| ID | Capa | Estado |",
            "|---|---|---|",
        ]
    )
    for item in package["combinations"]:
        lines.append(
            f"| `{item['id']}` | {item['layer']} | no verificada |"
        )
    lines.extend(
        [
            "",
            "## 6. Decisiones registradas",
            "",
        ]
    )
    for decision in package["owner_decisions"]:
        lines.append(
            f"- `{decision['id']}` [{decision['status']}]: "
            f"{decision['question']}"
        )
        lines.append(f"  Significa: {decision['acceptance_means']}")
    lines.extend(
        [
            "",
            "## 7. Puerta de cierre",
            "",
            "- Puerta tecnica final: SUPERADA.",
            "- Extensiones operativas ajenas al alcance actual: DIFERIDAS.",
            "- Aprobacion del propietario: REGISTRADA.",
            "- M4 cerrada: SI.",
            "- Inicio de M5 autorizado: NO.",
            "",
            "M5 requiere una orden expresa e independiente del propietario.",
            "",
            "SHA-256 del payload canonico del paquete: "
            f"`{package['canonical_payload_sha256']}`.",
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

    package = build_catalog()
    write_or_check(
        args.output,
        json.dumps(package, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(package), args.check)


if __name__ == "__main__":
    main()
