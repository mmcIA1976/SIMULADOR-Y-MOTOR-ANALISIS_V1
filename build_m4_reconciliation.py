from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M1_PATH = AUDIT_DIR / "matriz_decisiones_m1_v0_1.json"
M3_CATALOG_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
M3_MATRIX_PATH = (
    AUDIT_DIR / "matriz_dato_bloque_par_horizonte_m3_v0_1.json"
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_1_alcance_reconciliacion_resultado.md"
)

VERSION = "M4.1-reconciliation-v0.1"
P0_BLOCKS = {
    1: "Estructura del precio",
    3: "Multi-timeframe",
    7: "Order flow",
    9: "Open interest",
    10: "Funding",
    15: "Spot contra Futures",
    24: "Regimen",
    26: "Estadistica, volatilidad y alcanzabilidad",
    28: "Probabilidad TP/SL",
    29: "Ejecucion y costes",
    30: "Gestion de riesgo",
    32: "Evaluacion del rendimiento",
}

RULE_ADMISSION_FIELDS = (
    "id_and_version",
    "analytical_block",
    "concrete_objective",
    "rule_type",
    "raw_data_and_provider",
    "market_symbol_timestamp_unit_freshness",
    "exact_transformation_and_formula",
    "cross_pair_normalization",
    "applicable_horizons",
    "activation_and_non_application",
    "source_and_exact_supported_claim",
    "claims_not_supported_by_source",
    "separate_predictive_hypothesis",
    "expected_relation_to_tp_sl_or_expiry",
    "related_rules_and_double_counting",
    "missing_data_behavior",
    "unit_tests_limits_and_invariants",
    "trace_output",
    "refutation_suspension_or_withdrawal",
    "lifecycle_status",
)

SOURCE_LEVELS = (
    {
        "level": "definition",
        "meaning": "Standard formula or verifiable meaning of a datum.",
        "can_authorize": "deterministic calculation only",
        "cannot_authorize": "predictive sign, threshold, weight or probability",
    },
    {
        "level": "technical_foundation",
        "meaning": "Published interpretation or financial mechanism.",
        "can_authorize": "a mechanism stated with its assumptions",
        "cannot_authorize": "project-specific predictive effect or weight",
    },
    {
        "level": "external_predictive_evidence",
        "meaning": "Primary study with a comparable forward outcome.",
        "can_authorize": "a bounded candidate hypothesis",
        "cannot_authorize": "transfer across pairs, horizons or regimes",
    },
    {
        "level": "project_hypothesis",
        "meaning": "Preregistered relation to TP, SL or expiry.",
        "can_authorize": "shadow evaluation after M5-M7",
        "cannot_authorize": "production influence before M8-M9",
    },
)


def decision(
    disposition: str,
    subphase: str,
    target_families: list[str],
    reason: str,
    *,
    parent_block_gate: str = "p0_parent_available",
) -> dict:
    return {
        "disposition": disposition,
        "m4_subphase": subphase,
        "target_rule_families": target_families,
        "reason": reason,
        "parent_block_gate": parent_block_gate,
    }


RECONCILIATION = {
    "IND-EMA-CORE": decision(
        "retain_definition_without_predictive_weight",
        "M4.3",
        ["M4-FAMILY-STRUCTURE-SMOOTHER"],
        (
            "A correctly initialized EMA may be a deterministic smoother. "
            "Its periods and predictive interpretation require separate rules."
        ),
    ),
    "IND-EMA200-FALLBACK": decision(
        "retire_without_replacement",
        "M4.3",
        [],
        (
            "A shorter history must not be labelled EMA200. M5 must block "
            "insufficient history instead of synthesizing an equivalent value."
        ),
    ),
    "IND-ATR14-CURRENT": decision(
        "exclude_current_formula_research_p0_volatility_separately",
        "M4.2",
        ["M4-FAMILY-REALIZED-VOLATILITY"],
        (
            "The current simple-mean ATR variant is not the approved P0 "
            "horizon volatility scale. M4.2 will define that scale directly."
        ),
        parent_block_gate="indicator_parent_deferred_p1",
    ),
    "IND-EMA-STACK": decision(
        "reformulate_as_preregistered_structure_hypothesis",
        "M4.3",
        ["M4-FAMILY-STRUCTURE-SMOOTHER", "M4-FAMILY-MTF-HIERARCHY"],
        (
            "EMA ordering can describe smoothed price structure but cannot "
            "retain the current directional score or arbitrary timeframe weights."
        ),
    ),
    "IND-SUPPORT-RESISTANCE": decision(
        "rebuild_detector_before_hypothesis",
        "M4.3",
        ["M4-FAMILY-STRUCTURAL-LEVELS"],
        (
            "The current clustering constants are internal. A deterministic "
            "level detector and barrier-distance contract must be defined first."
        ),
    ),
    "IND-CVD-PROXY": decision(
        "rename_and_reformulate",
        "M4.4",
        ["M4-FAMILY-AGGRESSOR-TRADE-IMBALANCE"],
        (
            "A bounded Binance aggTrades window is trade-flow imbalance, not "
            "full cumulative volume delta. The last-500 sample is forbidden."
        ),
    ),
    "IND-PENDING-ZONE": decision(
        "replace_with_pending_entry_geometry",
        "M4.2",
        ["M4-FAMILY-PENDING-ACTIVATION"],
        (
            "Pending entry must be represented as a separate activation event "
            "under the M2 probability tree, never as an additive TP score."
        ),
    ),
    "SCORE-TREND_BIAS": decision(
        "retire_points_rebuild_components",
        "M4.3",
        ["M4-FAMILY-STRUCTURE-SMOOTHER", "M4-FAMILY-MTF-HIERARCHY"],
        "The current points and timeframe weights have no admissible derivation.",
    ),
    "SCORE-TECHNICAL_DIRECTION_BIAS": decision(
        "retire_aggregate_rebuild_components",
        "M4.3",
        ["M4-FAMILY-STRUCTURE-SMOOTHER", "M4-FAMILY-MTF-HIERARCHY"],
        (
            "A technical rating cannot enter P0 as an opaque aggregate. Only "
            "individually documented components may survive."
        ),
    ),
    "SCORE-PRICE_VS_ENTRY_BIAS": decision(
        "retire_formula_use_m2_geometry",
        "M4.2",
        ["M4-FAMILY-BARRIER-GEOMETRY", "M4-FAMILY-PENDING-ACTIVATION"],
        (
            "The discontinuous current adjustment is replaced by continuous "
            "log-distance geometry already required by M2."
        ),
    ),
    "SCORE-MARKET_REGIME_BIAS": decision(
        "rebuild_regime_without_directional_points",
        "M4.3",
        ["M4-FAMILY-VOLATILITY-REGIME", "M4-FAMILY-TREND-REGIME"],
        (
            "Regime is contextual state, not an automatic long/short bonus. "
            "Its estimator, persistence and transition rules require definition."
        ),
    ),
    "SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT": decision(
        "defer_parent_block_to_m10",
        "M4.1",
        [],
        (
            "Fibonacci belongs to P1 block 4. Its presence in block 28 cannot "
            "bypass the priority gate or create a P0 probability adjustment."
        ),
        parent_block_gate="blocked_parent_is_p1",
    ),
    "SCORE-ZONE_PROBABILITY_ADJUSTMENT": decision(
        "retire_points_rebuild_pending_semantics",
        "M4.2",
        ["M4-FAMILY-PENDING-ACTIVATION"],
        "Zone quality must affect an activation event, not add TP points.",
    ),
    "SCORE-TAKER_FLOW_BIAS": decision(
        "reformulate_as_windowed_flow_hypothesis",
        "M4.4",
        ["M4-FAMILY-AGGRESSOR-TRADE-IMBALANCE"],
        (
            "The datum is viable, but fixed ratio thresholds and points are "
            "withdrawn pending an exact event window and normalization."
        ),
    ),
    "SCORE-CVD_BIAS": decision(
        "merge_duplicate_evidence_family",
        "M4.4",
        ["M4-FAMILY-AGGRESSOR-TRADE-IMBALANCE"],
        "This is not independent evidence from the taker-flow family.",
    ),
    "SCORE-OI_TREND_BIAS": decision(
        "reformulate_as_joint_state_hypothesis",
        "M4.4",
        ["M4-FAMILY-OI-CHANGE", "M4-FAMILY-PRICE-OI-STATE"],
        (
            "OI is unsigned activity. Directional interpretation requires an "
            "explicit interaction with price and cannot retain current points."
        ),
    ),
    "SCORE-VOLATILITY_PENALTY": decision(
        "replace_with_continuous_reachability_geometry",
        "M4.2",
        ["M4-FAMILY-REALIZED-VOLATILITY", "M4-FAMILY-BARRIER-REACHABILITY"],
        (
            "A barrier-to-volatility ratio is continuous plan geometry; fixed "
            "penalty bands are withdrawn."
        ),
    ),
    "SCORE-LIQUIDITY_PENALTY": decision(
        "separate_execution_from_market_probability",
        "M4.5",
        ["M4-FAMILY-SPREAD", "M4-FAMILY-DEPTH-SLIPPAGE"],
        (
            "Spread and depth affect executable price and costs. They do not "
            "directly alter market-path probability without a separate study."
        ),
    ),
    "SCORE-OVEREXTENSION_PENALTY": decision(
        "reformulate_as_normalized_structure_hypothesis",
        "M4.3",
        ["M4-FAMILY-STRUCTURE-DISPLACEMENT"],
        (
            "Distance from a smoother must be volatility-normalized. Mean "
            "reversion or continuation remains an unproven project hypothesis."
        ),
    ),
    "SCORE-FUNDING_PENALTY": decision(
        "merge_funding_evidence_family",
        "M4.4",
        ["M4-FAMILY-FUNDING-STATE"],
        (
            "Funding sign and magnitude are retained as state and cost inputs; "
            "the current directional penalty is withdrawn."
        ),
    ),
    "SCORE-FUNDING_RELATIVE_PENALTY": decision(
        "reformulate_with_historical_normalization",
        "M4.4",
        ["M4-FAMILY-FUNDING-STATE"],
        (
            "Relative funding needs interval-aware history and robust "
            "normalization; it is the same evidence family as current funding."
        ),
    ),
    "SCORE-LEVEL_PENALTY": decision(
        "merge_structural_barrier_family",
        "M4.3",
        ["M4-FAMILY-STRUCTURAL-LEVELS"],
        "Current points are withdrawn; only explicit level-to-barrier geometry remains.",
    ),
    "SCORE-HIGHER_TIMEFRAME_PENALTY": decision(
        "merge_mtf_family",
        "M4.3",
        ["M4-FAMILY-MTF-HIERARCHY"],
        (
            "Higher-timeframe evidence must be represented once through a "
            "declared hierarchy, not duplicated as trend and penalty."
        ),
    ),
    "SCORE-TECHNICAL_ENTRY_TIMING_PENALTY": decision(
        "retire_opaque_aggregate",
        "M4.3",
        [],
        "The aggregate mixes P0 and deferred P1 signals and has no unique formula.",
    ),
    "SCORE-TECHNICAL_BARRIER_PENALTY": decision(
        "merge_structural_barrier_family",
        "M4.3",
        ["M4-FAMILY-STRUCTURAL-LEVELS"],
        "This duplicates the level family and cannot contribute independently.",
    ),
    "SCORE-OI_CONTEXT_PENALTY": decision(
        "merge_joint_oi_family",
        "M4.4",
        ["M4-FAMILY-OI-CHANGE", "M4-FAMILY-PRICE-OI-STATE"],
        "This duplicates the price-OI interaction and retains no separate points.",
    ),
    "SCORE-CONTRADICTION_PENALTY": decision(
        "retire_count_use_preregistered_interactions",
        "M4.6",
        ["M4-FAMILY-INTERACTION-MATRIX"],
        (
            "Counting heterogeneous contradictions assumes equal and independent "
            "effects. M4.6 will define explicit interactions instead."
        ),
    ),
    "SCORE-RISK_CALIBRATION_TP_ADJUSTMENT": decision(
        "retire_learning_derived_adjustment",
        "M4.1",
        [],
        (
            "The learning engine is paused and evidence from the old heuristic "
            "engine cannot define P0 rules or probability weights."
        ),
    ),
    "SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT": decision(
        "replace_with_m2_probability_tree_semantics",
        "M4.2",
        ["M4-FAMILY-PENDING-ACTIVATION"],
        (
            "No-entry and expiry-after-entry remain separate outcomes; a range "
            "adjustment cannot merge their probability mass."
        ),
    ),
    "SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT": decision(
        "retire_learning_derived_adjustment",
        "M4.1",
        [],
        "Old retrospective calibration cannot set the new unresolved probability.",
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


def candidate_universe(m1: dict) -> list[dict]:
    return [
        item
        for item in m1["decisions"]
        if item["initial_action_phase"] == "M4"
        or item["replacement_phase"] == "M4"
    ]


def m3_requirements_by_block(matrix: dict) -> dict[int, dict]:
    requirements = {}
    for row in matrix["rows"]:
        block_id = int(row["block_id"])
        if block_id not in P0_BLOCKS or block_id in requirements:
            continue
        requirements[block_id] = {
            "required_data_ids": list(row["required_data_ids"]),
            "conditional_data_ids": list(row["conditional_data_ids"]),
        }
    if set(requirements) != set(P0_BLOCKS):
        raise ValueError("m3_matrix_missing_p0_blocks")
    return requirements


def build_reconciliation() -> dict:
    m1 = read_json(M1_PATH)
    m3_catalog = read_json(M3_CATALOG_PATH)
    m3_matrix = read_json(M3_MATRIX_PATH)
    candidates = candidate_universe(m1)
    candidate_ids = {item["id"] for item in candidates}
    decision_ids = set(RECONCILIATION)
    if candidate_ids != decision_ids:
        raise ValueError(
            "m4_reconciliation_universe_mismatch:"
            f"missing={sorted(candidate_ids - decision_ids)}:"
            f"extra={sorted(decision_ids - candidate_ids)}"
        )
    if m3_catalog["status"] != "completed_owner_approved":
        raise ValueError("m3_not_owner_approved")

    block_requirements = m3_requirements_by_block(m3_matrix)
    rows = []
    for item in candidates:
        manual = RECONCILIATION[item["id"]]
        p0_blocks = sorted(set(item["block_ids"]) & set(P0_BLOCKS))
        non_p0_blocks = sorted(set(item["block_ids"]) - set(P0_BLOCKS))
        required_data = sorted(
            {
                data_id
                for block_id in p0_blocks
                for data_id in block_requirements[block_id][
                    "required_data_ids"
                ]
            }
        )
        conditional_data = sorted(
            {
                data_id
                for block_id in p0_blocks
                for data_id in block_requirements[block_id][
                    "conditional_data_ids"
                ]
            }
            - set(required_data)
        )
        rows.append(
            {
                "current_rule_id": item["id"],
                "current_name": item["name"],
                "current_kind": item["current_kind"],
                "current_formula": item["formula"],
                "current_decision": item["m1_decision"],
                "current_probability_action": item[
                    "current_probability_action"
                ],
                "p0_blocks": p0_blocks,
                "p0_block_names": [P0_BLOCKS[value] for value in p0_blocks],
                "non_p0_blocks": non_p0_blocks,
                "m3_required_data_ids": required_data,
                "m3_conditional_data_ids": conditional_data,
                **manual,
                "current_points_or_weight_authorized": False,
                "direct_probability_effect_authorized": False,
                "production_modified": False,
            }
        )

    dispositions = Counter(row["disposition"] for row in rows)
    subphases = Counter(row["m4_subphase"] for row in rows)
    family_members = Counter(
        family
        for row in rows
        for family in row["target_rule_families"]
    )
    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.1",
        "status": "completed_internal_milestone_m4_still_in_progress",
        "date": "2026-07-27",
        "purpose": (
            "Reconcile every M1 item assigned to M4 before defining new "
            "rules, without carrying current heuristic effects forward."
        ),
        "scope": {
            "m4_started": True,
            "m4_current_subphase": "M4.1",
            "m4_next_subphase": "M4.2",
            "m5_started": False,
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "new_predictive_weight_authorized": False,
        },
        "universe": m3_catalog["universe"],
        "p0_blocks": [
            {"id": block_id, "name": name}
            for block_id, name in P0_BLOCKS.items()
        ],
        "admission_contract": {
            "mandatory_fields": list(RULE_ADMISSION_FIELDS),
            "source_levels": list(SOURCE_LEVELS),
            "hard_gates": [
                "A data source validates meaning and availability, not prediction.",
                "No current point, threshold or weight transfers automatically.",
                "A P1 parent cannot influence P0 through probability block 28.",
                "Definitions and hypotheses remain separate records.",
                "No rule receives direct probability mass in M4.",
                "Every target family must later name exact M3 data contracts.",
                "Missing or stale data never becomes neutral evidence.",
                "All pairs and horizons require the same formula and declared parameters.",
                "Combinations are preregistered before empirical evaluation.",
            ],
        },
        "summary": {
            "m1_candidates": len(candidates),
            "reconciled": len(rows),
            "p0_blocks": len(P0_BLOCKS),
            "target_families": len(family_members),
            "rows_with_direct_probability_authorized": sum(
                1
                for row in rows
                if row["direct_probability_effect_authorized"]
            ),
            "production_modified": False,
            "disposition_counts": dict(sorted(dispositions.items())),
            "subphase_counts": dict(sorted(subphases.items())),
        },
        "target_family_seed_registry": [
            {
                "family_id": family,
                "member_count": count,
                "status": "seed_only_not_a_rule",
                "formula_defined": False,
                "predictive_effect_defined": False,
                "note": (
                    "M4.1 groups legacy elements only. Formal rule cards "
                    "begin in M4.2 and cannot inherit legacy effects."
                ),
            }
            for family, count in sorted(family_members.items())
        ],
        "rows": rows,
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in (
                ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
                M1_PATH,
                M3_CATALOG_PATH,
                M3_MATRIX_PATH,
            )
        ],
    }
    payload["reconciliation_sha256"] = sha256_text(
        canonical_json(
            {
                "admission_contract": payload["admission_contract"],
                "p0_blocks": payload["p0_blocks"],
                "target_family_seed_registry": payload[
                    "target_family_seed_registry"
                ],
                "rows": rows,
            }
        )
    )
    return payload


def render_report(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# M4.1 - Alcance y reconciliacion M1-M3",
        "",
        "Fecha: 2026-07-27",
        "Estado: HITO INTERNO COMPLETADO; M4 SIGUE EN CURSO",
        "",
        "## 1. Resultado",
        "",
        f"- Candidatos remitidos por M1: **{summary['m1_candidates']}**.",
        f"- Candidatos reconciliados: **{summary['reconciled']}**.",
        f"- Bloques P0: **{summary['p0_blocks']}**.",
        f"- Familias semilla: **{summary['target_families']}**.",
        "- Pesos o efectos probabilisticos autorizados: **0**.",
        "- Cambios productivos: **ninguno**.",
        "",
        "M4.1 no ha definido reglas predictivas. Ha impedido que las reglas",
        "actuales entren al catalogo nuevo por continuidad, nombre o costumbre.",
        "Cada elemento queda retirado, fusionado, pospuesto o asignado a una",
        "familia semilla que debera obtener ficha completa en M4.2-M4.6.",
        "",
        "## 2. Puertas de admision",
        "",
    ]
    lines.extend(
        f"- {item}"
        for item in payload["admission_contract"]["hard_gates"]
    )
    lines.extend(
        [
            "",
            "Las cuatro capas de respaldo permanecen separadas: definicion,",
            "fundamento tecnico, evidencia predictiva externa e hipotesis del",
            "proyecto. Ninguna capa sustituye a la siguiente.",
            "",
            "## 3. Reconciliacion exacta",
            "",
            "| Elemento actual | Disposicion | Subfase | Familias destino |",
            "|---|---|---|---|",
        ]
    )
    for row in payload["rows"]:
        families = ", ".join(row["target_rule_families"]) or "ninguna"
        lines.append(
            f"| `{row['current_rule_id']}` | `{row['disposition']}` | "
            f"`{row['m4_subphase']}` | {families} |"
        )
    lines.extend(
        [
            "",
            "## 4. Limites",
            "",
            "- Las familias semilla no son reglas y no tienen formula ni efecto.",
            "- Los datos M3 quedan vinculados por bloque, no aun por regla exacta.",
            "- La bibliografia se asignara a afirmaciones concretas en cada ficha.",
            "- Fibonacci queda bloqueado por pertenecer a P1.",
            "- Ajustes derivados del aprendizaje antiguo quedan retirados.",
            "- M5 y produccion permanecen intactos.",
            "",
            "## 5. Siguiente paso",
            "",
            "`M4.2`: definir alcanzabilidad por geometria, volatilidad y horizonte.",
            "Debe comenzar por transformaciones deterministas y mantener separada",
            "cualquier hipotesis predictiva. M4 no esta cerrada ni pendiente de",
            "aprobacion final todavia.",
            "",
            f"SHA-256: `{payload['reconciliation_sha256']}`.",
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

    payload = build_reconciliation()
    report = render_report(payload)
    write_or_check(
        args.output,
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, report, args.check)


if __name__ == "__main__":
    main()
