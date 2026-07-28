from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
SOURCE_CATALOG_PATHS = (
    AUDIT_DIR / "catalogo_alcanzabilidad_m4_2_v0_2.json",
    AUDIT_DIR / "catalogo_regimen_estructura_mtf_m4_3_v0_2.json",
    AUDIT_DIR / "catalogo_contexto_derivados_m4_4_v0_2.json",
    AUDIT_DIR / "catalogo_ejecucion_riesgo_m4_5_v0_2.json",
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_7_27_reglas_formulas_enmienda_v0_2.md"
)
DEFAULT_MANIFEST_PATH = AUDIT_DIR / "manifiesto_integridad_m4_7_v0_2.json"

VERSION = "M4.7-consolidated-rule-audit-v0.2"
EXPECTED_RULE_COUNTS = {
    "M4.2": 6,
    "M4.3": 6,
    "M4.4": 7,
    "M4.5": 8,
}

REQUIRED_FIELDS = (
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

AUXILIARY_RULE_IDS = {"M4-RULE-EXPONENTIAL-SMOOTHER-001"}

RESERVED_NULL_FIELDS = {
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": ["probability"],
    "M4-RULE-PENDING-ACTIVATION-001": ["activation_probability"],
    "M4-RULE-PATH-STRUCTURE-001": ["prediction"],
    "M4-RULE-VOLATILITY-RANK-001": ["regime_label"],
    "M4-RULE-MTF-HIERARCHY-001": [
        "aggregate_score",
        "probability_effect",
    ],
    "M4-RULE-CONTINUOUS-REGIME-001": [
        "regime_label",
        "directional_score",
        "probability_effect",
    ],
    "M4-RULE-AGGRESSOR-IMBALANCE-001": ["prediction"],
    "M4-RULE-PRICE-OI-STATE-001": [
        "positioning_label",
        "probability_effect",
    ],
    "M4-RULE-DERIVATIVES-CONTEXT-001": [
        "crowding_label",
        "aggregate_score",
        "probability_effect",
    ],
}

VALUE_QUALITY_TAXONOMY = {
    "observed_exact": "Direct provider/account observation with known semantics.",
    "deterministic_from_observation": (
        "Deterministic transformation of complete validated observations."
    ),
    "deterministic_from_plan": (
        "Deterministic transformation of explicit user plan inputs."
    ),
    "bounded_observation": (
        "Observed interval whose uncertainty bounds are explicitly retained."
    ),
    "estimated_model": (
        "Model estimate with model/version/features recorded in a separate trace."
    ),
    "scenario_point": "Conditional pre-trade value under one declared scenario.",
    "scenario_lower_bound": "Lower endpoint across declared scenarios.",
    "scenario_upper_bound": "Upper endpoint across declared scenarios.",
    "unavailable": (
        "No numeric substitution is authorized because inputs are incomplete."
    ),
    "not_applicable": "The field does not apply to the active branch.",
    "reserved_null": (
        "Field intentionally fixed to null until a later approved phase."
    ),
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


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [
            item if isinstance(item, str) else canonical_json(item)
            for item in value
        ]
    if isinstance(value, dict):
        return [canonical_json(value)]
    return [str(value)]


def evidence_category(source_type: str) -> str:
    if source_type in {
        "approved_internal_contract",
        "completed_internal_milestone",
    }:
        return "internal_project_contract"
    if source_type == "official_provider_documentation":
        return "provider_semantics"
    if source_type == "institutional_methodology":
        return "external_methodology"
    if source_type in {
        "primary_academic_publication",
        "primary_academic_preprint",
        "primary_institutional_research",
        "primary_regulatory_research",
    }:
        return "external_family_or_adjacent_evidence"
    if source_type == "official_investor_guidance":
        return "institutional_risk_guidance"
    raise ValueError(f"unclassified_source_type:{source_type}")


def classified_sources(sources: list[dict]) -> list[dict]:
    return [
        {
            **source,
            "evidence_category": evidence_category(source["type"]),
        }
        for source in sources
    ]


def claim_evidence_category(claim_level: str, source: dict) -> str:
    source_category = source["evidence_category"]
    if source_category == "provider_semantics":
        return "provider_semantics"
    if source_category == "internal_project_contract":
        return "internal_project_contract"
    if claim_level == "definition":
        return "mathematical_or_methodological_definition"
    if claim_level == "external_predictive_evidence":
        return "external_empirical_evidence_adjacent_to_project_target"
    if claim_level == "transfer_limit":
        return "transfer_limit_evidence"
    if claim_level in {"technical_foundation", "data_foundation"}:
        return "family_or_adjacent_foundation"
    if claim_level in {"internal_definition", "internal_methodology"}:
        return "internal_project_contract"
    raise ValueError(f"unclassified_claim_level:{claim_level}")


def build_catalog() -> dict:
    source_catalogs = [read_json(path) for path in SOURCE_CATALOG_PATHS]
    if {
        catalog["subphase"]: len(catalog["rules"])
        for catalog in source_catalogs
    } != EXPECTED_RULE_COUNTS:
        raise ValueError("unexpected_rule_count_by_subphase")

    rules = []
    formula_index = []
    source_registries = {}
    for catalog in source_catalogs:
        if catalog["status"] != (
            "completed_internal_milestone_m4_still_in_progress"
        ):
            raise ValueError(f"{catalog['subphase']}_not_completed")
        registry = classified_sources(catalog["sources"])
        source_ids = {source["id"] for source in registry}
        sources_by_id = {source["id"]: source for source in registry}
        source_registries[catalog["subphase"]] = registry
        for rule in catalog["rules"]:
            missing = [
                field
                for field in REQUIRED_FIELDS
                if field not in rule or rule[field] in (None, "", [])
            ]
            if missing:
                raise ValueError(
                    f"incomplete_rule:{rule['id']}:{','.join(missing)}"
                )
            used_sources = {
                item["source_id"]
                for item in rule["source_and_exact_supported_claim"]
            }
            if not used_sources.issubset(source_ids):
                raise ValueError(f"unknown_source:{rule['id']}")
            if (
                rule["direct_probability_effect_authorized"]
                or rule["numeric_weight_authorized"]
                or rule["production_authorized"]
            ):
                raise ValueError(f"unauthorized_rule:{rule['id']}")
            reserved_null = RESERVED_NULL_FIELDS.get(rule["id"], [])
            unknown_reserved = set(reserved_null) - set(rule["trace_output"])
            if unknown_reserved:
                raise ValueError(
                    f"reserved_null_not_in_trace:{rule['id']}:"
                    f"{','.join(sorted(unknown_reserved))}"
                )
            produced_trace = [
                field
                for field in rule["trace_output"]
                if field not in reserved_null
            ]
            classified_claims = [
                {
                    **claim,
                    "evidence_category": claim_evidence_category(
                        claim["level"],
                        sources_by_id[claim["source_id"]],
                    ),
                }
                for claim in rule["source_and_exact_supported_claim"]
            ]
            augmented = {
                "sequence": len(rules) + 1,
                "source_subphase": catalog["subphase"],
                **rule,
                "source_and_exact_supported_claim": classified_claims,
                "card_role": (
                    "auxiliary_operator"
                    if rule["id"] in AUXILIARY_RULE_IDS
                    else "p0_core_rule"
                ),
                "produced_trace_fields": produced_trace,
                "forbidden_or_reserved_null_fields": reserved_null,
            }
            rules.append(augmented)
            formula_index.append(
                {
                    "sequence": augmented["sequence"],
                    "id": rule["id"],
                    "subphase": catalog["subphase"],
                    "name": rule["name"],
                    "formula": rule["exact_transformation_and_formula"],
                }
            )

    ids = [rule["id"] for rule in rules]
    if len(ids) != 27 or len(ids) != len(set(ids)):
        raise ValueError("consolidated_rule_universe_not_27_unique")
    hypotheses = [
        rule["separate_predictive_hypothesis"]
        for rule in rules
        if rule["separate_predictive_hypothesis"] is not None
    ]
    if len(hypotheses) != 15:
        raise ValueError("consolidated_hypothesis_universe_not_15")
    policy_decision_records = [
        {
            "source_subphase": catalog["subphase"],
            **record,
            "evidence_category": (
                "internal_project_policy_not_external_evidence"
            ),
        }
        for catalog in source_catalogs
        for record in catalog.get("policy_decision_records", [])
    ]
    policy_ids = [record["id"] for record in policy_decision_records]
    if len(policy_ids) != len(set(policy_ids)):
        raise ValueError("duplicate_policy_decision_id")

    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.7",
        "status": "owner_audit_material_m4_not_closed",
        "date": "2026-07-27",
        "purpose": (
            "Single audit surface for every formal M4 rule and exact formula."
        ),
        "scope": {
            "rules": len(rules),
            "p0_core_rules": sum(
                rule["card_role"] == "p0_core_rule" for rule in rules
            ),
            "auxiliary_operators": sum(
                rule["card_role"] == "auxiliary_operator" for rule in rules
            ),
            "rules_by_subphase": EXPECTED_RULE_COUNTS,
            "predictive_hypotheses": len(hypotheses),
            "direct_probability_effects_authorized": 0,
            "numeric_weights_authorized": 0,
            "production_rules_authorized": 0,
            "m4_closed": False,
            "m5_started": False,
        },
        "reading_contract": {
            "formula_is_documented_operator": True,
            "formula_is_empirically_validated_probability": False,
            "hypotheses_are_unverified": True,
            "implementation_is_deferred_to_m5": True,
            "probability_integration_is_deferred_to_m6": True,
            "legacy_trace_output_is_combined": True,
            "produced_and_reserved_trace_fields_are_separated": True,
        },
        "runtime_value_trace_contract": {
            "required_per_emitted_value": [
                "field_id",
                "value",
                "unit",
                "source_or_plan_field",
                "observed_or_declared_at",
                "coverage_start",
                "coverage_end",
                "transformation_id",
                "value_quality",
            ],
            "value_quality_enum": list(VALUE_QUALITY_TAXONOMY),
            "model_trace_separate": True,
            "model_trace_required_fields": [
                "model_id",
                "model_version",
                "feature_snapshot_id",
                "calibration_version",
                "estimated_at",
            ],
            "silent_quality_upgrade_allowed": False,
        },
        "value_quality_taxonomy": VALUE_QUALITY_TAXONOMY,
        "policy_decision_records": policy_decision_records,
        "amendment": {
            "supersedes_version": "M4.7-consolidated-rule-audit-v0.1",
            "reason": (
                "Consolidate amended v0.2 rule cards, distinguish core and "
                "auxiliary cards, classify evidence, separate produced from "
                "reserved-null trace fields and add external file integrity."
            ),
            "production_effect": False,
        },
        "formula_index": formula_index,
        "rules": rules,
        "source_registries": source_registries,
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(path),
            }
            for path in SOURCE_CATALOG_PATHS
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "reading_contract": payload["reading_contract"],
                "value_quality_taxonomy": payload["value_quality_taxonomy"],
                "runtime_value_trace_contract": payload[
                    "runtime_value_trace_contract"
                ],
                "policy_decision_records": payload[
                    "policy_decision_records"
                ],
                "formula_index": payload["formula_index"],
                "rules": payload["rules"],
                "source_registries": payload["source_registries"],
            }
        )
    )
    return payload


def source_lookup(catalog: dict, subphase: str) -> dict[str, dict]:
    return {
        source["id"]: source
        for source in catalog["source_registries"][subphase]
    }


def append_bullets(lines: list[str], values: Any) -> None:
    for value in normalize_list(values):
        lines.append(f"- {value}")


def render_report(catalog: dict) -> str:
    lines = [
        "# M4.7 - 26 reglas nucleares y 1 operador auxiliar",
        "",
        "Fecha: 2026-07-27",
        "Estado: MATERIAL DE AUDITORIA; M4 NO CERRADA; M5 NO INICIADA",
        "",
        "## Como leer este documento",
        "",
        "El catalogo contiene 26 reglas nucleares P0 y 1 operador auxiliar.",
        "Una formula documentada no equivale a una probabilidad validada.",
        "Las 15 hipotesis siguen sin verificar y no tienen peso productivo.",
        "Las decisiones de politica provisionales se registran aparte de la evidencia.",
        "",
        "## Indice rapido de formulas",
        "",
        "| # | ID | Subfase | Formula |",
        "|---:|---|---|---|",
    ]
    for item in catalog["formula_index"]:
        formula = "<br>".join(
            str(part).replace("|", "\\|") for part in item["formula"]
        )
        lines.append(
            f"| {item['sequence']} | `{item['id']}` | "
            f"{item['subphase']} | `{formula}` |"
        )

    for rule in catalog["rules"]:
        sources = source_lookup(catalog, rule["source_subphase"])
        lines.extend(
            [
                "",
                f"## {rule['sequence']}. {rule['id']}",
                "",
                f"**Nombre:** {rule['name']}",
                "",
                f"**Subfase:** {rule['source_subphase']}",
                "",
                f"**Bloques:** {', '.join(map(str, rule['analytical_blocks']))}",
                "",
                f"**Tipo:** `{rule['rule_type']}`",
                "",
                f"**Estado:** `{rule['lifecycle_status']}`",
                "",
                "### Objetivo",
                "",
                str(rule["concrete_objective"]),
                "",
                "### Datos",
                "",
            ]
        )
        append_bullets(lines, rule["raw_data_and_provider"])
        lines.extend(["", "### Tiempo, unidades y frescura", ""])
        append_bullets(
            lines,
            rule["market_symbol_timestamp_unit_freshness"],
        )
        lines.extend(["", "### Formula exacta", "", "```text"])
        lines.extend(str(item) for item in rule["exact_transformation_and_formula"])
        lines.extend(["```", "", "### Normalizacion entre pares", ""])
        append_bullets(lines, rule["cross_pair_normalization"])
        lines.extend(["", "### Horizontes", ""])
        append_bullets(lines, rule["applicable_horizons"])
        lines.extend(["", "### Activacion", ""])
        append_bullets(lines, rule["activation_conditions"])
        lines.extend(["", "### No aplicacion o bloqueo", ""])
        append_bullets(lines, rule["non_application_conditions"])
        lines.extend(["", "### Fuentes y afirmacion respaldada", ""])
        for claim in rule["source_and_exact_supported_claim"]:
            source = sources[claim["source_id"]]
            url = source.get("url")
            label = (
                f"[{claim['source_id']}]({url})"
                if url
                else f"`{claim['source_id']}`"
            )
            lines.append(
                f"- {label} "
                f"[{claim['evidence_category']}]: {claim['claim']}"
            )
        lines.extend(["", "### Lo que las fuentes no respaldan", ""])
        append_bullets(lines, rule["claims_not_supported_by_source"])
        lines.extend(["", "### Relacion esperada con resultados", ""])
        append_bullets(
            lines,
            rule["expected_relation_to_tp_sl_or_expiry"],
        )
        lines.extend(["", "### Control de doble conteo", ""])
        append_bullets(lines, rule["double_counting_control"])
        lines.extend(["", "### Ausencia de datos", ""])
        append_bullets(lines, rule["missing_data_behavior"])
        lines.extend(["", "### Pruebas, limites e invariantes", ""])
        append_bullets(lines, rule["unit_tests_limits_and_invariants"])
        lines.extend(["", "### Traza producida", ""])
        append_bullets(lines, rule["produced_trace_fields"])
        lines.extend(["", "### Campos prohibidos o reservados a null", ""])
        if rule["forbidden_or_reserved_null_fields"]:
            append_bullets(
                lines,
                rule["forbidden_or_reserved_null_fields"],
            )
        else:
            lines.append("- Ninguno en esta ficha.")
        lines.extend(["", "### Refutacion, suspension o retirada", ""])
        append_bullets(
            lines,
            rule["refutation_suspension_or_withdrawal"],
        )
        lines.extend(["", "### Hipotesis predictiva separada", ""])
        hypothesis = rule["separate_predictive_hypothesis"]
        if hypothesis is None:
            lines.append("- Ninguna.")
        else:
            lines.append(f"- ID: `{hypothesis['id']}`.")
            lines.append(f"- Estado: `{hypothesis['status']}`.")
            lines.append(f"- Enunciado: {hypothesis['statement']}")
            if hypothesis.get("not_a_claim"):
                lines.append(f"- No afirma: {hypothesis['not_a_claim']}")
        lines.extend(
            [
                "",
                "### Autorizacion actual",
                "",
                "- Efecto probabilistico directo: **NO**.",
                "- Peso numerico: **NO**.",
                "- Produccion: **NO**.",
            ]
        )

    lines.extend(
        [
            "",
            "## Cierre de lectura",
            "",
            "El propietario puede objetar cualquier ficha citando su ID.",
            "M4 permanece abierta hasta una aprobacion expresa.",
            "",
            "SHA-256 del payload canonico consolidado: "
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


def build_integrity_manifest(
    output_path: Path,
    output_content: str,
    report_path: Path,
    report_content: str,
    catalog: dict,
) -> dict:
    artifacts = []
    for path, content, artifact_type in (
        (output_path, output_content, "consolidated_catalog"),
        (report_path, report_content, "human_audit_report"),
    ):
        encoded = content.encode("utf-8")
        artifacts.append(
            {
                "artifact_type": artifact_type,
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256_full_file": hashlib.sha256(encoded).hexdigest(),
                "bytes_utf8": len(encoded),
            }
        )
    return {
        "version": "M4.7-integrity-manifest-v0.2",
        "date": "2026-07-27",
        "hash_scope": "complete_utf8_file_bytes",
        "canonical_payload_sha256": catalog[
            "canonical_payload_sha256"
        ],
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
    )
    args = parser.parse_args()

    catalog = build_catalog()
    output_content = json.dumps(
        catalog,
        ensure_ascii=True,
        indent=2,
    ) + "\n"
    report_content = render_report(catalog)
    write_or_check(
        args.output,
        output_content,
        args.check,
    )
    write_or_check(args.report, report_content, args.check)
    manifest = build_integrity_manifest(
        args.output,
        output_content,
        args.report,
        report_content,
        catalog,
    )
    write_or_check(
        args.manifest,
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )


if __name__ == "__main__":
    main()
