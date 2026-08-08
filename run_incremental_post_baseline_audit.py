from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m8_evaluation as m8
from db import close_pool, connect
from m5_input_assembly import candidate_features_from_m5
from m6_active_engine import run_internal_probability_analysis
from m6_horizon_calibration import (
    horizon_calibration_profile,
    horizon_coefficient_artifact,
)
from m6_predictive_rules import (
    apply_provisional_rule_overlay,
    build_provisional_rule_signals,
)
from prospective_validation import (
    standardized_candidate_features,
    temperature_calibration,
)
from run_all_closed_operations_comparison import normalize_closed_row
from run_repaired_historical_comparison import top_class_accuracy


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
BASELINE_PATH = (
    AUDIT_DIR / "auditoria_integral_biblioteca_operaciones_cerradas_v0_1.json"
)
FROZEN_M6_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
OUTPUT_PATH = AUDIT_DIR / "auditoria_incremental_post_baseline_v0_1.json"
REPORT_PATH = (
    AUDIT_DIR / "2026-08-07_auditoria_incremental_post_baseline.md"
)

AUDIT_VERSION = "post-baseline-exact-horizon-comparison-v0.1"
MODEL_NAMES = (
    "stored_v04_served",
    "m6_global_core_frozen",
    "v05_horizon_core_replay",
    "v05_horizon_full_replay",
)

SQL_CLOSED = """
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
    r.app_version,
    r.scoring_version,
    r.snapshot_json,
    r.analysis_json,
    r.tp_probability,
    r.sl_probability,
    r.range_probability,
    e.reconstructed_plan_result,
    e.evidence_status,
    e.evidence_quality,
    e.evidence_path_resolution,
    e.first_plan_touch,
    e.first_plan_touch_at
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
) e ON TRUE
WHERE o.status = 'CLOSED'
ORDER BY o.id
"""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )


def load_incremental_rows() -> tuple[dict, list[dict], list[dict]]:
    baseline = read_json(BASELINE_PATH)
    baseline_ids = {
        int(case["operation_id"])
        for case in baseline.get("cases", [])
    }
    with connect() as db:
        raw_rows = [dict(row) for row in db.execute(SQL_CLOSED).fetchall()]
    close_pool()

    incremental_raw = [
        row
        for row in raw_rows
        if int(row["operation_id"]) not in baseline_ids
    ]
    normalized = []
    coverage = []
    for raw in incremental_raw:
        record, reasons = normalize_closed_row(raw)
        coverage.append(
            {
                "operation_id": int(raw["operation_id"]),
                "recommendation_id": raw.get("recommendation_id"),
                "normalization_status": (
                    "included" if record is not None else "excluded"
                ),
                "normalization_reasons": reasons,
            }
        )
        if record is not None:
            for key in (
                "app_version",
                "scoring_version",
                "reconstructed_plan_result",
                "evidence_status",
                "evidence_quality",
                "evidence_path_resolution",
                "first_plan_touch",
                "first_plan_touch_at",
            ):
                record[key] = raw.get(key)
            normalized.append(record)
    return baseline, normalized, coverage


def exact_outcomes(rows: list[dict]) -> None:
    captured_at = datetime.now(timezone.utc)
    cached = {}
    if OUTPUT_PATH.exists():
        previous = read_json(OUTPUT_PATH)
        cached = {
            int(case["operation_id"]): dict(case.get("outcome") or {})
            for case in previous.get("cases", [])
        }
    pending = []
    for row in rows:
        outcome = cached.get(int(row["operation_id"]))
        stable = bool(outcome) and outcome.get("status") in {
            "resolved",
            "ambiguous_same_minute",
            "ambiguous_boundary_minute",
        }
        if outcome and outcome.get("status") == "right_censored_not_expired":
            expiry = m8.parse_utc(row["expiry_at"])
            stable = expiry is not None and captured_at < expiry
        if stable:
            row["outcome"] = outcome
        else:
            pending.append(row)
    if pending:
        m8.enrich_outcomes(
            pending,
            captured_at=captured_at,
        )


def evidence_label(row: dict) -> str | None:
    touch = str(row.get("first_plan_touch") or "")
    if touch == "take_profit":
        return m8.CLASSES[0]
    if touch == "stop_loss":
        return m8.CLASSES[1]
    if touch == "no_plan_touch":
        return m8.CLASSES[2]
    return None


def run_core(
    row: dict,
    *,
    artifact: dict,
    temperature: float,
    analysis_suffix: str,
) -> tuple[dict[str, float], dict, dict]:
    m5_analysis = row["_snapshot"].get("m5_rule_trace")
    if not isinstance(m5_analysis, dict):
        raise ValueError("stored_m5_rule_trace_missing")
    feature_values = candidate_features_from_m5(
        m5_analysis,
        side=row["side"],
    )
    standardized = standardized_candidate_features(
        feature_values,
        artifact,
    )
    result = run_internal_probability_analysis(
        analysis_id=(
            f"incremental-audit-{row['recommendation_id']}:{analysis_suffix}"
        ),
        m5_analysis=m5_analysis,
        feature_snapshot=standardized,
        coefficient_artifact=artifact,
        executed_at=row["analysis_at"],
    )
    if result.get("status") != "evaluated_internal_only":
        raise ValueError(
            "m6_core_not_evaluated:"
            + str(result.get("block_code") or result.get("status"))
        )
    calibrated = temperature_calibration(
        result["probabilities"],
        temperature,
    )
    return calibrated, feature_values, m5_analysis


def build_predictions(
    rows: list[dict],
) -> tuple[dict[str, dict[int, dict]], list[dict]]:
    frozen = read_json(FROZEN_M6_PATH)
    global_artifact = frozen["coefficient_artifact"]
    global_temperature = float(
        global_artifact["calibration"]["temperature"]
    )
    predictions: dict[str, dict[int, dict]] = {
        name: {} for name in MODEL_NAMES
    }
    cases = []
    for row in rows:
        recommendation_id = int(row["recommendation_id"])
        model_errors = []
        active_overlay_rules: list[str] = []
        try:
            predictions["stored_v04_served"][recommendation_id] = dict(
                row["_legacy"]
            )
        except (TypeError, ValueError):
            model_errors.append("stored_probabilities_invalid")

        feature_values: dict[str, float] | None = None
        try:
            global_core, feature_values, _ = run_core(
                row,
                artifact=global_artifact,
                temperature=global_temperature,
                analysis_suffix="m6-global",
            )
            predictions["m6_global_core_frozen"][recommendation_id] = (
                global_core
            )
        except Exception as exc:
            model_errors.append(
                f"m6_global_core:{type(exc).__name__}:{exc}"
            )

        try:
            horizon_profile = horizon_calibration_profile(
                row["time_horizon"]
            )
            horizon_artifact = horizon_coefficient_artifact(
                row["time_horizon"]
            )
            horizon_core, horizon_features, m5_analysis = run_core(
                row,
                artifact=horizon_artifact,
                temperature=float(horizon_profile["temperature"]),
                analysis_suffix="v05-horizon",
            )
            predictions["v05_horizon_core_replay"][recommendation_id] = (
                horizon_core
            )
            signals = build_provisional_rule_signals(
                m5_analysis,
                side=row["side"],
                time_horizon=row["time_horizon"],
            )
            overlay = apply_provisional_rule_overlay(
                horizon_core,
                signals,
            )
            predictions["v05_horizon_full_replay"][recommendation_id] = dict(
                overlay["probabilities_after"]
            )
            active_overlay_rules = list(overlay["active_rule_ids"])
            if feature_values is None:
                feature_values = horizon_features
        except Exception as exc:
            model_errors.append(
                f"v05_horizon:{type(exc).__name__}:{exc}"
            )

        outcome = dict(row.get("outcome") or {})
        stored_evidence_label = evidence_label(row)
        cases.append(
            {
                "operation_id": int(row["operation_id"]),
                "recommendation_id": recommendation_id,
                "symbol": row["symbol"],
                "side": row["side"],
                "time_horizon": row["time_horizon"],
                "analysis_at": row["analysis_at"],
                "engine_version": row["engine_version"],
                "app_version": row.get("app_version"),
                "scoring_version": row.get("scoring_version"),
                "horizon_status": row["horizon_status"],
                "formal_eligible_horizon": bool(
                    row["formal_eligible_horizon"]
                ),
                "outcome": outcome,
                "stored_learning_evidence": {
                    "label": stored_evidence_label,
                    "status": row.get("evidence_status"),
                    "quality": row.get("evidence_quality"),
                    "path_resolution": row.get(
                        "evidence_path_resolution"
                    ),
                    "consistent_with_exact_reconstruction": (
                        stored_evidence_label == outcome.get("label")
                        if stored_evidence_label and outcome.get("label")
                        else None
                    ),
                },
                "feature_values": feature_values,
                "active_v05_overlay_rule_ids": active_overlay_rules,
                "model_errors": model_errors,
                "predictions": {
                    name: predictions[name].get(recommendation_id)
                    for name in MODEL_NAMES
                },
            }
        )
    return predictions, cases


def metric_summary(
    rows: list[dict],
    predictions: dict[int, dict],
) -> dict:
    metrics = m8.evaluate_predictions(rows, predictions)
    metrics["top_class_accuracy"] = top_class_accuracy(rows, predictions)
    return metrics


def paired_delta(
    rows: list[dict],
    candidate: dict[int, dict],
    reference: dict[int, dict],
) -> dict:
    candidate_metrics = metric_summary(rows, candidate)
    reference_metrics = metric_summary(rows, reference)
    return {
        "candidate_minus_reference": {
            "brier_3c": (
                candidate_metrics["brier_3c"]
                - reference_metrics["brier_3c"]
            ),
            "log_loss_3c": (
                candidate_metrics["log_loss_3c"]
                - reference_metrics["log_loss_3c"]
            ),
            "top_class_accuracy": (
                candidate_metrics["top_class_accuracy"]["accuracy"]
                - reference_metrics["top_class_accuracy"]["accuracy"]
            ),
        },
        "calendar_block_bootstrap": m8.bootstrap_paired_differences(
            rows,
            candidate,
            reference,
            resamples=2000,
            seed=20260807,
        ),
    }


def selected_predictions(
    rows: list[dict],
    values: dict[int, dict],
) -> dict[int, dict]:
    return {
        int(row["recommendation_id"]): values[int(row["recommendation_id"])]
        for row in rows
    }


def build_report(payload: dict) -> str:
    inventory = payload["inventory"]
    metrics = payload["metrics"]
    comparisons = payload["comparisons"]
    labels = {
        "stored_v04_served": "v0.4 servido",
        "m6_global_core_frozen": "M6 global congelado",
        "v05_horizon_core_replay": "v0.5 nucleo por horizonte",
        "v05_horizon_full_replay": "v0.5 completo",
    }
    lines = [
        "# Auditoria incremental posterior al baseline",
        "",
        f"Fecha: {payload['generated_at']}",
        "",
        "## Alcance",
        "",
        (
            "Esta auditoria conserva sin cambios el baseline del 30 de julio "
            "y evalua exclusivamente las operaciones cerradas que no estaban "
            "incluidas en aquel artefacto."
        ),
        "",
        f"- Operaciones del baseline: {inventory['baseline_closed_operations']}.",
        f"- Operaciones incrementales encontradas: {inventory['incremental_closed_operations']}.",
        f"- Horizontes exactos preoperacion: {inventory['exact_horizon_operations']}.",
        f"- Casos resueltos utilizables: {inventory['metric_eligible_operations']}.",
        f"- Casos ambiguos o excluidos: {inventory['outcome_excluded_operations']}.",
        f"- Operaciones cerradas originalmente por v0.5: {inventory['prospective_v05_closed_operations']}.",
        "",
        "Todos los modelos se comparan contra la misma reconstruccion de "
        "primera barrera con velas cerradas de un minuto.",
        "",
        "## Resultados agregados",
        "",
        "| Modelo | N | Brier | Log-loss | Acierto principal |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in MODEL_NAMES:
        item = metrics["overall"][name]
        lines.append(
            f"| {labels[name]} | {item['n']} | "
            f"{item['brier_3c']:.6f} | {item['log_loss_3c']:.6f} | "
            f"{item['top_class_accuracy']['accuracy']:.2%} |"
        )
    lines.extend(["", "## Resultados por horizonte", ""])
    for horizon, horizon_metrics in metrics["by_horizon"].items():
        lines.extend(
            [
                f"### {horizon}",
                "",
                "| Modelo | N | Brier | Log-loss | Acierto principal |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for name in MODEL_NAMES:
            item = horizon_metrics[name]
            lines.append(
                f"| {labels[name]} | {item['n']} | "
                f"{item['brier_3c']:.6f} | {item['log_loss_3c']:.6f} | "
                f"{item['top_class_accuracy']['accuracy']:.2%} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Comparaciones directas",
            "",
            (
                "Los deltas son candidato menos referencia. Un valor negativo "
                "en Brier o log-loss significa menor error."
            ),
            "",
            "| Candidato | Referencia | Delta Brier | Delta log-loss | Delta acierto |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for comparison in comparisons.values():
        delta = comparison["result"]["candidate_minus_reference"]
        lines.append(
            f"| {labels[comparison['candidate']]} | "
            f"{labels[comparison['reference']]} | "
            f"{delta['brier_3c']:+.6f} | "
            f"{delta['log_loss_3c']:+.6f} | "
            f"{delta['top_class_accuracy']:+.2%} |"
        )

    champion = payload["decision"]["lowest_observed_log_loss_model"]
    v05_vs_global = comparisons["v05_full_vs_m6_global"]["result"]
    v05_vs_global_delta = v05_vs_global["candidate_minus_reference"]
    v05_vs_global_interval = v05_vs_global["calendar_block_bootstrap"][
        "left_minus_right"
    ]["log_loss_3c"]
    overlay_delta = comparisons["v05_full_vs_v05_core"]["result"][
        "candidate_minus_reference"
    ]
    evidence = inventory["stored_learning_evidence_consistency"]
    inconsistent_cases = [
        case
        for case in payload["cases"]
        if case["stored_learning_evidence"][
            "consistent_with_exact_reconstruction"
        ] is False
    ]
    lines.extend(
        [
            "",
            "## Hallazgos",
            "",
            (
                "- Frente al nucleo M6 global, v0.5 completo aumenta el Brier "
                f"en {v05_vs_global_delta['brier_3c']:+.6f} y el log-loss "
                f"en {v05_vs_global_delta['log_loss_3c']:+.6f}."
            ),
            (
                "- En el bootstrap por bloques de calendario, el intervalo del "
                "95 % para el empeoramiento de log-loss de v0.5 completo es "
                f"[{v05_vs_global_interval['lower_95']:+.6f}, "
                f"{v05_vs_global_interval['upper_95']:+.6f}]."
            ),
            (
                "- v0.5 mejora la muestra intraday_wide, pero empeora "
                "intraday_short y especialmente short_swing frente al nucleo "
                "M6 global. La calibracion no mejora de forma consistente los "
                "tres marcos temporales."
            ),
            (
                "- Los overlays de v0.5 empeoran su propio nucleo en "
                f"{overlay_delta['log_loss_3c']:+.6f} de log-loss y "
                f"{overlay_delta['brier_3c']:+.6f} de Brier en el agregado."
            ),
            (
                "- La evidencia de aprendizaje almacenada coincide con la "
                f"reconstruccion exacta en {evidence.get('consistent', 0)} "
                f"casos, discrepa en {evidence.get('inconsistent', 0)} y no es "
                f"comparable en {evidence.get('not_comparable', 0)}."
            ),
            *(
                [
                    (
                        "- La discrepancia es la operacion "
                        f"#{inconsistent_cases[0]['operation_id']}: el aprendizaje "
                        "la corto como `no_plan_touch` tras el cierre manual, pero "
                        "la observacion hasta el vencimiento exacto registro SL "
                        f"primero en {inconsistent_cases[0]['outcome'].get('first_touch_at')}."
                    )
                ]
                if inconsistent_cases
                else []
            ),
            "",
            "## Lectura metodologica",
            "",
            (
                f"El menor log-loss observado en este incremento corresponde a "
                f"**{labels[champion]}**. Esto describe la muestra; no autoriza "
                "automaticamente una promocion."
            ),
            "",
            (
                "La salida v0.4 es evidencia preoperacion real. El nucleo M6 "
                "global ya estaba congelado antes del primer caso incremental y "
                "se reproduce sobre trazas preoperacion exactas. v0.5 fue creado "
                "despues de estos casos, por lo que sus dos columnas son replay "
                "retrospectivo, aunque no utilicen datos posteriores a cada entrada."
            ),
            "",
            (
                "No existe todavia ninguna operacion cerrada cuya recomendacion "
                "original proceda de v0.5. Por ello esta auditoria no autoriza "
                "declarar v0.5 validado ni sustituir el baseline historico."
            ),
            "",
            "## Decision",
            "",
            f"- Promocion automatica de v0.5: **NO**.",
            f"- Cambios de pesos derivados de esta muestra: **NO**.",
            f"- Modificaciones en Supabase o produccion: **NINGUNA**.",
            (
                "- Siguiente evidencia necesaria: operaciones cerradas analizadas "
                "originalmente por v0.5, evaluadas por horizonte y sin recalibrar "
                "el motor durante la cohorte."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def run() -> dict:
    baseline, rows, coverage = load_incremental_rows()
    exact_outcomes(rows)
    predictions, cases = build_predictions(rows)

    eligible = [
        row
        for row in rows
        if row.get("formal_eligible_horizon")
        and (row.get("outcome") or {}).get("status") == "resolved"
        and (row.get("outcome") or {}).get("label") in m8.CLASSES
        and all(
            int(row["recommendation_id"]) in predictions[name]
            for name in MODEL_NAMES
        )
    ]
    eligible_ids = {int(row["operation_id"]) for row in eligible}
    for item in coverage:
        if item["operation_id"] not in eligible_ids:
            matching = next(
                (
                    row for row in rows
                    if int(row["operation_id"]) == item["operation_id"]
                ),
                None,
            )
            if matching is not None:
                outcome = matching.get("outcome") or {}
                item["metric_exclusion"] = (
                    outcome.get("status")
                    or "model_prediction_unavailable"
                )

    overall = {
        name: metric_summary(eligible, predictions[name])
        for name in MODEL_NAMES
    }
    by_horizon = {}
    for horizon in sorted({row["time_horizon"] for row in eligible}):
        members = [
            row for row in eligible if row["time_horizon"] == horizon
        ]
        by_horizon[horizon] = {
            name: metric_summary(
                members,
                selected_predictions(members, predictions[name]),
            )
            for name in MODEL_NAMES
        }

    comparison_specs = {
        "m6_global_vs_stored_v04": (
            "m6_global_core_frozen",
            "stored_v04_served",
        ),
        "v05_core_vs_m6_global": (
            "v05_horizon_core_replay",
            "m6_global_core_frozen",
        ),
        "v05_full_vs_m6_global": (
            "v05_horizon_full_replay",
            "m6_global_core_frozen",
        ),
        "v05_full_vs_v05_core": (
            "v05_horizon_full_replay",
            "v05_horizon_core_replay",
        ),
    }
    comparisons = {
        key: {
            "candidate": candidate,
            "reference": reference,
            "result": paired_delta(
                eligible,
                predictions[candidate],
                predictions[reference],
            ),
        }
        for key, (candidate, reference) in comparison_specs.items()
    }

    outcome_statuses = Counter(
        str((row.get("outcome") or {}).get("status") or "missing")
        for row in rows
    )
    exact_horizons = sum(
        bool(row.get("formal_eligible_horizon")) for row in rows
    )
    current_v05_closed = sum(
        str(row.get("engine_version")) == "TP-SL-PROBABILITY-ENGINE-v0.5"
        for row in rows
    )
    evidence_consistency = Counter()
    for case in cases:
        value = case["stored_learning_evidence"][
            "consistent_with_exact_reconstruction"
        ]
        evidence_consistency[
            "consistent" if value is True
            else "inconsistent" if value is False
            else "not_comparable"
        ] += 1

    champion = min(
        MODEL_NAMES,
        key=lambda name: (
            overall[name]["log_loss_3c"],
            overall[name]["brier_3c"],
        ),
    )
    payload = {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "path": str(BASELINE_PATH.relative_to(ROOT)),
            "audit_version": baseline.get("audit_version"),
            "generated_at": baseline.get("generated_at"),
            "audit_sha256": baseline.get("audit_sha256"),
            "closed_operations": len(baseline.get("cases", [])),
            "maximum_operation_id": max(
                int(case["operation_id"])
                for case in baseline.get("cases", [])
            ),
        },
        "scope": {
            "selection": "closed_operations_not_present_in_baseline_case_ids",
            "outcome_contract": list(m8.CLASSES),
            "outcome_source": "binance_usdm_closed_1m_first_passage_reconstruction",
            "pretrade_input_source": "stored_recommendation_snapshot_m5_rule_trace",
            "no_missing_to_neutral": True,
            "production_changes": False,
            "supabase_writes": False,
        },
        "model_roles": {
            "stored_v04_served": "prospective_original_served_output",
            "m6_global_core_frozen": (
                "predeclared_before_incremental_cohort_exact_input_replay"
            ),
            "v05_horizon_core_replay": (
                "post_cohort_retrospective_exact_input_replay"
            ),
            "v05_horizon_full_replay": (
                "post_cohort_retrospective_exact_input_replay"
            ),
        },
        "inventory": {
            "baseline_closed_operations": len(baseline.get("cases", [])),
            "incremental_closed_operations": len(rows),
            "exact_horizon_operations": exact_horizons,
            "metric_eligible_operations": len(eligible),
            "outcome_excluded_operations": len(rows) - len(eligible),
            "outcome_status_counts": dict(outcome_statuses),
            "horizon_counts": dict(
                Counter(row["time_horizon"] for row in rows)
            ),
            "engine_version_counts": dict(
                Counter(row["engine_version"] for row in rows)
            ),
            "prospective_v05_closed_operations": current_v05_closed,
            "stored_learning_evidence_consistency": dict(
                evidence_consistency
            ),
        },
        "metrics": {
            "overall": overall,
            "by_horizon": by_horizon,
        },
        "comparisons": comparisons,
        "decision": {
            "lowest_observed_log_loss_model": champion,
            "v05_promotion_authorized": False,
            "reason": "no_closed_operation_originally_analyzed_by_v05",
            "automatic_weight_changes_authorized": False,
            "recommended_engine_action": (
                "do_not_treat_v05_as_champion; preserve_m6_global_frozen_"
                "as_reference_and_collect_a_frozen_forward_cohort"
            ),
            "production_effect": "none",
        },
        "operation_coverage": coverage,
        "cases": cases,
    }
    payload = m8.add_payload_hash(payload)
    write_json(OUTPUT_PATH, payload)
    REPORT_PATH.write_text(build_report(payload), encoding="utf-8")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print(f"ELIGIBLE={len(eligible)}/{len(rows)}")
    print(f"CHAMPION={champion}")
    print(f"SHA256={payload['canonical_payload_sha256']}")
    return payload


if __name__ == "__main__":
    run()
