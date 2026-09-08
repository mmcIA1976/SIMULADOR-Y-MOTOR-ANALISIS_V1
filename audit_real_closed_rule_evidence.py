from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m8_evaluation as m8
from audit_final_rule_utility import (
    attach_episode_memberships,
    evaluate_predefined_combinations,
    evaluate_probability_ablations,
    extract_rule_variables,
    horizon_cutoffs,
    select_and_evaluate_rule_hypotheses,
)
from audit_full_rule_library_closed_operations import (
    CandleArchive,
    build_case,
    normalized_row,
    trace_registry,
)
from db import close_pool, connect
from predictive_rule_library import load_rule_library
from versioning import ENGINE_VERSION


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
OUTPUT_PATH = AUDIT_DIR / "auditoria_reglas_solo_operaciones_reales_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-08-13_auditoria_reglas_solo_operaciones_reales.md"
AUDIT_VERSION = "real-closed-operation-rule-evidence-v0.1"
CLASSES = m8.CLASSES


SQL_REAL_CLOSED = """
SELECT
    o.id AS operation_id,
    o.status,
    o.entry_type,
    o.started_at,
    o.created_at AS operation_created_at,
    o.closed_at,
    o.close_reason,
    o.entry,
    o.stop_loss,
    o.take_profit,
    o.margin,
    o.leverage,
    o.symbol AS operation_symbol,
    o.side AS operation_side,
    o.time_horizon AS operation_time_horizon,
    r.id AS recommendation_id,
    r.created_at AS analysis_at,
    r.symbol,
    r.side,
    r.time_horizon,
    r.engine_version,
    r.snapshot_json,
    r.analysis_json,
    r.tp_probability,
    r.sl_probability,
    r.range_probability,
    le.id AS learning_evaluation_id,
    le.evidence_status,
    le.evidence_source,
    le.evidence_quality,
    le.evidence_path_resolution,
    le.evidence_coverage_ratio,
    le.first_plan_touch,
    le.first_plan_touch_at,
    le.reconstructed_plan_result
FROM operations o
JOIN LATERAL (
    SELECT candidate.*
    FROM recommendations candidate
    WHERE candidate.operation_id = o.id
    ORDER BY candidate.created_at DESC, candidate.id DESC
    LIMIT 1
) r ON TRUE
LEFT JOIN LATERAL (
    SELECT candidate.*
    FROM learning_evaluations candidate
    WHERE candidate.operation_id = o.id
    ORDER BY candidate.updated_at DESC, candidate.id DESC
    LIMIT 1
) le ON TRUE
WHERE o.status = 'CLOSED'
ORDER BY o.id
"""


TOUCH_LABELS = {
    "take_profit": CLASSES[0],
    "stop_loss": CLASSES[1],
    "no_plan_touch": CLASSES[2],
}


def canonical_hash(payload: Any) -> str:
    return m8.payload_sha256(payload)


def read_only_rows() -> list[dict]:
    try:
        with connect() as db:
            db.execute("SET TRANSACTION READ ONLY")
            values = [dict(row) for row in db.execute(SQL_REAL_CLOSED).fetchall()]
            db.rollback()
        return values
    finally:
        close_pool()


def stored_outcome(raw: dict) -> dict:
    touch = str(raw.get("first_plan_touch") or "")
    label = TOUCH_LABELS.get(touch)
    if label is not None:
        return {
            "status": "resolved",
            "label": label,
            "first_touch_at": raw.get("first_plan_touch_at"),
            "source": "stored_learning_evaluation",
            "evidence_quality": raw.get("evidence_quality"),
            "coverage_ratio": raw.get("evidence_coverage_ratio"),
        }
    if touch in {"ambiguous_boundary_candle", "ambiguous_same_candle"}:
        return {
            "status": "ambiguous",
            "label": None,
            "first_touch_at": raw.get("first_plan_touch_at"),
            "source": "stored_learning_evaluation",
            "evidence_quality": raw.get("evidence_quality"),
            "coverage_ratio": raw.get("evidence_coverage_ratio"),
        }
    return {
        "status": "missing",
        "label": None,
        "first_touch_at": raw.get("first_plan_touch_at"),
        "source": "stored_learning_evaluation",
        "evidence_quality": raw.get("evidence_quality"),
        "coverage_ratio": raw.get("evidence_coverage_ratio"),
    }


def _normalized_probabilities(raw: dict) -> dict[str, float] | None:
    values = {
        CLASSES[0]: raw.get("tp_probability"),
        CLASSES[1]: raw.get("sl_probability"),
        CLASSES[2]: raw.get("range_probability"),
    }
    try:
        numbers = {name: float(value) for name, value in values.items()}
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value < 0 for value in numbers.values()):
        return None
    total = math.fsum(numbers.values())
    if total <= 0:
        return None
    return {name: value / total for name, value in numbers.items()}


def probability_metrics(records: list[dict]) -> dict:
    usable = []
    for record in records:
        label = (record.get("outcome") or {}).get("label")
        probabilities = _normalized_probabilities(record)
        if label not in CLASSES or probabilities is None:
            continue
        log_loss = -math.log(max(probabilities[label], 1e-15))
        brier = math.fsum(
            (probabilities[name] - (1.0 if name == label else 0.0)) ** 2
            for name in CLASSES
        )
        usable.append((label, probabilities, log_loss, brier))
    if not usable:
        return {"n": 0}
    return {
        "n": len(usable),
        "log_loss_3c": math.fsum(item[2] for item in usable) / len(usable),
        "brier_3c": math.fsum(item[3] for item in usable) / len(usable),
        "top_class_accuracy": sum(
            max(item[1], key=item[1].get) == item[0] for item in usable
        )
        / len(usable),
        "outcomes": dict(Counter(item[0] for item in usable)),
    }


def build_real_cases(raw_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    normalized = [normalized_row(raw) for raw in raw_rows]
    outcomes = {int(raw["operation_id"]): stored_outcome(raw) for raw in raw_rows}
    archive = CandleArchive.load()
    archive.ensure(normalized)
    library = load_rule_library()
    rules = {item["rule_id"]: item for item in library["rules"]}
    cases = []
    for raw, row in zip(raw_rows, normalized, strict=True):
        outcome = outcomes[int(row["operation_id"])]
        case = build_case(row, rules, archive, outcome)
        case.update(
            {
                "case_id": int(row["operation_id"]),
                "source_kind": "closed_operation",
                "source_id": int(row["operation_id"]),
                "expiry_at": row.get("expiry_at"),
                "horizon_seconds": row.get("horizon_seconds"),
                "learning_evaluation_id": raw.get("learning_evaluation_id"),
            }
        )
        cases.append(case)
    return normalized, cases


def _nested_counter(rows: list[dict], keys: tuple[str, ...]) -> dict:
    result: dict = {}
    for row in rows:
        current = result
        for key in keys[:-1]:
            value = str(row.get(key) or "missing")
            current = current.setdefault(value, {})
        leaf = str(row.get(keys[-1]) or "missing")
        current[leaf] = current.get(leaf, 0) + 1
    return result


def _outcome_counts(rows: list[dict]) -> dict[str, int]:
    return dict(
        Counter(
            str((row.get("outcome") or {}).get("label") or "ambiguous_excluded")
            for row in rows
        )
    )


def _trace_coverage(raw_rows: list[dict]) -> dict:
    coverage: dict[str, dict] = defaultdict(
        lambda: {
            "recorded_operations": 0,
            "by_engine": Counter(),
            "by_horizon": Counter(),
        }
    )
    for raw in raw_rows:
        snapshot = raw.get("snapshot_json")
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                snapshot = {}
        registry = trace_registry(snapshot if isinstance(snapshot, dict) else {})
        for rule_id in registry:
            item = coverage[rule_id]
            item["recorded_operations"] += 1
            item["by_engine"][str(raw.get("engine_version") or "missing")] += 1
            item["by_horizon"][str(raw.get("time_horizon") or "missing")] += 1
    return {
        rule_id: {
            "recorded_operations": item["recorded_operations"],
            "by_engine": dict(item["by_engine"]),
            "by_horizon": dict(item["by_horizon"]),
        }
        for rule_id, item in sorted(coverage.items())
    }


def classify_real_rule_evidence(
    library: dict,
    coverage: dict,
    hypotheses: list[dict],
    ablations: list[dict],
) -> list[dict]:
    hypothesis_by_rule: dict[str, list[dict]] = defaultdict(list)
    ablation_by_rule: dict[str, list[dict]] = defaultdict(list)
    for item in hypotheses:
        hypothesis_by_rule[item["rule_id"]].append(item)
    for item in ablations:
        ablation_by_rule[item["rule_id"]].append(item)
    decisions = []
    for rule in library["rules"]:
        rule_id = rule["rule_id"]
        members = hypothesis_by_rule.get(rule_id, [])
        rule_ablations = ablation_by_rule.get(rule_id, [])
        supported = [
            item
            for item in members
            if item.get("evidence_status")
            == "supported_on_frozen_latest_segment"
        ]
        contradicted = [
            item
            for item in members
            if item.get("evidence_status")
            == "contradicted_on_frozen_latest_segment"
        ]
        supported_ablations = [
            item
            for item in rule_ablations
            if item.get("evidence_status") == "supported_material_stable_ablation"
        ]
        contradicted_ablations = [
            item
            for item in rule_ablations
            if item.get("evidence_status") == "materially_harmful_stable_ablation"
        ]
        if contradicted or contradicted_ablations:
            decision = "current_hypothesis_contradicted_on_real_operations"
        elif supported_ablations:
            decision = "duration_recalibration_candidate_for_shadow_only"
        elif supported:
            decision = "candidate_for_prospective_shadow_not_production"
        elif members:
            decision = "insufficient_or_unstable_real_operation_evidence"
        else:
            decision = "no_exact_real_operation_signal_available"
        decisions.append(
            {
                "rule_id": rule_id,
                "name": rule.get("name"),
                "lifecycle_status": rule.get("lifecycle_status"),
                "decision": decision,
                "supported_horizons": sorted(
                    {item["time_horizon"] for item in supported}
                ),
                "contradicted_horizons": sorted(
                    {item["time_horizon"] for item in contradicted}
                ),
                "supported_ablation_horizons": sorted(
                    {item["time_horizon"] for item in supported_ablations}
                ),
                "contradicted_ablation_horizons": sorted(
                    {item["time_horizon"] for item in contradicted_ablations}
                ),
                "tested_horizons": sorted(
                    {item["time_horizon"] for item in members}
                ),
                "reconstructed_exact_cases": int(
                    (coverage.get(rule_id) or {}).get("exact_cases", 0)
                ),
                "probability_ablation_horizons": sorted(
                    {item["time_horizon"] for item in rule_ablations}
                ),
            }
        )
    return decisions


def run_real_closed_audit() -> dict:
    captured_at = datetime.now(timezone.utc)
    print("REAL_AUDIT_STAGE=load_closed_operations", flush=True)
    raw_rows = read_only_rows()
    print(f"REAL_AUDIT_STAGE=replay_real_plans:rows={len(raw_rows)}", flush=True)
    normalized, cases = build_real_cases(raw_rows)
    print(f"REAL_AUDIT_STAGE=group_overlapping_episodes:cases={len(cases)}", flush=True)
    cases, episodes = attach_episode_memberships(cases)
    library = load_rule_library()
    library_rules = {item["rule_id"]: item for item in library["rules"]}
    variable_rows, coverage = extract_rule_variables(cases, library_rules)
    cutoffs = horizon_cutoffs(cases)
    print(
        f"REAL_AUDIT_STAGE=evaluate_individual_rules:variables={len(variable_rows)}",
        flush=True,
    )
    hypotheses, selected_specs = select_and_evaluate_rule_hypotheses(
        variable_rows, cutoffs
    )
    print("REAL_AUDIT_STAGE=evaluate_probability_ablations", flush=True)
    ablations = evaluate_probability_ablations(cases, cutoffs)
    print("REAL_AUDIT_STAGE=evaluate_predefined_combinations", flush=True)
    combinations = evaluate_predefined_combinations(
        cases, variable_rows, selected_specs, cutoffs
    )
    print("REAL_AUDIT_STAGE=classify_rules", flush=True)
    decisions = classify_real_rule_evidence(
        library, coverage, hypotheses, ablations
    )

    raw_with_outcome = []
    for raw in raw_rows:
        raw_with_outcome.append({**raw, "outcome": stored_outcome(raw)})
    probability_by_engine = {
        engine: probability_metrics(
            [row for row in raw_with_outcome if row.get("engine_version") == engine]
        )
        for engine in sorted(
            {str(row.get("engine_version") or "missing") for row in raw_rows}
        )
    }
    current_rows = [
        row for row in raw_with_outcome if row.get("engine_version") == ENGINE_VERSION
    ]
    current_by_horizon = {
        horizon: probability_metrics(
            [row for row in current_rows if row.get("time_horizon") == horizon]
        )
        for horizon in m8.HORIZON_SECONDS
    }
    resolved = [
        row
        for row in raw_with_outcome
        if (row.get("outcome") or {}).get("label") in CLASSES
    ]
    ambiguous = [
        row
        for row in raw_with_outcome
        if (row.get("outcome") or {}).get("status") == "ambiguous"
    ]
    deterministic = {
        "audit_version": AUDIT_VERSION,
        "source_scope": "closed_operations_only",
        "counterfactual_cases": 0,
        "synthetic_market_plans": 0,
        "production_effect": "none",
        "supabase_writes": 0,
        "protocol": {
            "outcome_source": "stored_learning_evaluation_first_plan_touch",
            "rule_signal_source": (
                "recorded traces when present; otherwise deterministic replay of "
                "the current rule formulas on the real operation plan and its "
                "pretrade market context"
            ),
            "independent_unit": "overlapping_episode_by_symbol_and_horizon",
            "temporal_validation": (
                "select_variable_and_orientation_on_earliest_70_percent; "
                "evaluate_frozen_choice_on_latest_30_percent"
            ),
            "multiple_testing": "Benjamini-Hochberg FDR 0.10",
            "automatic_promotion": False,
        },
        "inventory": {
            "closed_operations": len(raw_rows),
            "normalized_operations": len(normalized),
            "resolved_unambiguous": len(resolved),
            "ambiguous_excluded_from_metrics": len(ambiguous),
            "missing_outcome": len(raw_rows) - len(resolved) - len(ambiguous),
            "market_operations": sum(
                str(row.get("entry_type") or "market").lower() == "market"
                for row in raw_rows
            ),
            "pending_operations": sum(
                str(row.get("entry_type") or "market").lower() != "market"
                for row in raw_rows
            ),
            "with_learning_evaluation": sum(
                row.get("learning_evaluation_id") is not None for row in raw_rows
            ),
            "full_evidence_coverage": sum(
                float(row.get("evidence_coverage_ratio") or 0.0) >= 0.999
                for row in raw_rows
            ),
            "by_engine_horizon_entry_type": _nested_counter(
                raw_rows, ("engine_version", "time_horizon", "entry_type")
            ),
            "outcomes": _outcome_counts(raw_with_outcome),
        },
        "recorded_rule_trace_coverage": _trace_coverage(raw_rows),
        "episodes": episodes,
        "probability_metrics_by_original_engine": probability_by_engine,
        "current_engine_real_cohort": {
            "engine_version": ENGINE_VERSION,
            "closed_operations": len(current_rows),
            "by_horizon": current_by_horizon,
            "outcomes": _outcome_counts(current_rows),
            "production_conclusion_authorized": False,
        },
        "individual_rule_hypotheses": hypotheses,
        "active_probability_ablations": ablations,
        "predefined_combinations": combinations,
        "rule_decisions": decisions,
        "decision_summary": dict(Counter(item["decision"] for item in decisions)),
        "conclusion": {
            "current_engine_has_enough_native_closed_cases": False,
            "historical_versions_can_validate_current_weights_directly": False,
            "historical_real_plans_are_valid_for_deterministic_rule_replay": True,
            "production_rule_change_authorized": False,
            "next_allowed_use": "prospective_shadow_only_for_supported_candidates",
        },
    }
    deterministic["audit_sha256"] = canonical_hash(deterministic)
    return {**deterministic, "generated_at": captured_at.isoformat()}


def build_report(payload: dict) -> str:
    inventory = payload["inventory"]
    current = payload["current_engine_real_cohort"]
    lines = [
        "# Auditoría de reglas usando únicamente operaciones reales",
        "",
        f"- Operaciones cerradas: **{inventory['closed_operations']}**.",
        f"- Desenlaces inequívocos: **{inventory['resolved_unambiguous']}**.",
        f"- Casos ambiguos excluidos: **{inventory['ambiguous_excluded_from_metrics']}**.",
        "- Casos contrafactuales o planes sintéticos: **0**.",
        f"- Operaciones nativas del motor actual: **{current['closed_operations']}**.",
        "- Cambio en producción: **ninguno**.",
        "",
        "## Interpretación",
        "",
        "Las versiones históricas sólo aportan planes reales y desenlaces reales. "
        "Cuando una regla actual no estaba almacenada, su señal se reconstruye con "
        "la fórmula actual y se etiqueta como replay; no se afirma que aquella regla "
        "participara en la decisión original.",
        "",
        "## Decisiones de reglas",
        "",
        "| Regla | Decisión | Asociación favorable | Ablación favorable | Contrarios |",
        "|---|---|---|---|---|",
    ]
    for item in payload["rule_decisions"]:
        lines.append(
            f"| `{item['rule_id']}` | `{item['decision']}` | "
            f"{', '.join(item['supported_horizons']) or '-'} | "
            f"{', '.join(item['supported_ablation_horizons']) or '-'} | "
            f"{', '.join(sorted(set(item['contradicted_horizons']) | set(item['contradicted_ablation_horizons']))) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Dictamen",
            "",
            "Las reglas con evidencia favorable sólo pueden pasar a sombra. "
            "Ninguna cambia pesos ni probabilidades de producción mediante esta auditoría.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(payload: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(build_report(payload), encoding="utf-8")


__all__ = [
    "AUDIT_VERSION",
    "OUTPUT_PATH",
    "REPORT_PATH",
    "TOUCH_LABELS",
    "build_report",
    "classify_real_rule_evidence",
    "probability_metrics",
    "run_real_closed_audit",
    "stored_outcome",
    "write_outputs",
]
