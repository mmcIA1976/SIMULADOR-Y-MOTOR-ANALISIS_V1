from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from db import close_pool, connect
from m8_evaluation import (
    AUDIT_DIR,
    CLASSES,
    FEATURE_NAMES,
    FIT_FEATURE_NAMES,
    RIDGE_CANDIDATES,
    TEMPERATURE_CANDIDATES,
    add_payload_hash,
    baseline_predictions,
    bootstrap_paired_differences,
    build_coefficient_artifact,
    candidate_predictions,
    competing_risk_compatibility,
    constant_predictions,
    eligible_labeled_rows,
    empirical_probabilities,
    enrich_outcomes,
    enrich_pretrade_features,
    evaluate_predictions,
    file_sha256,
    fit_evidence_coefficients,
    normalize_candidate_rows,
    normalize_legacy_probabilities,
    parse_utc,
    payload_sha256,
    public_record,
    standardization,
    subgroup_metrics,
    prepare_fit_rows,
)


INVENTORY_PATH = AUDIT_DIR / "inventario_elegibilidad_m8_2_v0_1.json"
PROTOCOL_PATH = AUDIT_DIR / "protocolo_evaluacion_m8_1_v0_1.json"
EXECUTION_CONTRACT_PATH = AUDIT_DIR / "contrato_ejecucion_m8_3_v0_1.json"
DATASET_PATH = AUDIT_DIR / "dataset_desarrollo_calibracion_m8_3_v0_1.json"
SEALED_FINAL_PATH = AUDIT_DIR / "dataset_final_sellado_m8_3_v0_1.json"
M83_REPORT_PATH = AUDIT_DIR / "2026-07-28_M8_3_reconstruccion_outcomes_v0_1.md"
M84_PATH = AUDIT_DIR / "evaluacion_baseline_m8_4_v0_1.json"
M84_REPORT_PATH = AUDIT_DIR / "2026-07-28_M8_4_evaluacion_baseline_v0_1.md"
M85_PATH = AUDIT_DIR / "modelo_estimado_calibrado_m8_5_v0_1.json"
M85_REPORT_PATH = AUDIT_DIR / "2026-07-28_M8_5_estimacion_calibracion_v0_1.md"
M86_PATH = AUDIT_DIR / "evaluacion_final_m8_6_v0_1.json"
M86_REPORT_PATH = AUDIT_DIR / "2026-07-28_M8_6_prueba_final_v0_1.md"
M87_PATH = AUDIT_DIR / "paquete_cierre_m8_7_v0_1.json"
M87_REPORT_PATH = AUDIT_DIR / "2026-07-28_M8_7_cierre_evaluacion_v0_1.md"

SQL_CANDIDATES = """
SELECT
    r.id AS recommendation_id,
    r.operation_id,
    r.created_at AS analysis_at,
    r.symbol,
    r.side,
    r.time_horizon,
    r.engine_version,
    r.snapshot_json,
    r.analysis_json,
    o.entry,
    o.stop_loss,
    o.take_profit
FROM recommendations r
JOIN operations o ON o.id = r.operation_id
WHERE r.operation_id IS NOT NULL
  AND COALESCE(o.entry_type, 'market') = 'market'
ORDER BY r.created_at, r.id
"""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def frozen_execution_contract() -> dict:
    payload = {
        "version": "M8.3-execution-contract-v0.1",
        "phase": "M8",
        "subphase": "M8.3",
        "status": "frozen_before_outcome_access",
        "outcome_source": "binance_usdm_futures_klines_1m",
        "outcome_classes": list(CLASSES),
        "outcome_rules": {
            "start": "recommendation.created_at",
            "expiry": "analysis_at+horizon_seconds",
            "same_minute_both_barriers": "ambiguous_excluded",
            "boundary_minute_touch": "ambiguous_excluded",
            "no_touch_after_expiry": CLASSES[2],
            "no_touch_before_expiry": "right_censored",
            "minimum_market_coverage": 0.98,
        },
        "horizon_policy": {
            "stored_exact": "formal cohort",
            "missing_exact_duration": {
                "intraday_short": 14400,
                "intraday_wide": 86400,
                "short_swing": 604800,
            },
            "missing_duration_status": "retrospective_policy_cohort_not_formal",
        },
        "pretrade_volatility": {
            "formula": "sigma_H=sqrt(sum(log_return_t^2))",
            "sampling": "M4 largest exact supported divisor with >=24 returns",
            "cutoff": "last fully closed Binance futures kline <= analysis_at",
            "reference_windows": 60,
        },
        "candidate_features": [
            {
                "name": name,
                "registered_rule": {
                    "directional_path_efficiency_h": "M4-RULE-PATH-STRUCTURE-001",
                    "directional_path_efficiency_2h": "M4-RULE-MTF-HIERARCHY-001",
                    "directional_path_efficiency_4h": "M4-RULE-MTF-HIERARCHY-001",
                    "volatility_percentile_60": "M4-RULE-VOLATILITY-RANK-001",
                    "target_extreme_between_entry_and_tp": "M4-RULE-PRIOR-EXTREMA-001",
                }[name],
            }
            for name in FEATURE_NAMES
        ],
        "feature_exclusions": {
            "reason": "No exact historical source window can be proven for every record.",
            "rule_groups": [
                "aggressor imbalance",
                "open interest change",
                "price/OI state",
                "spot/futures basis",
                "funding state",
                "liquidation map",
            ],
            "coefficient_effect": "fixed_zero_not_tested",
        },
        "fit": {
            "partition": "development_only",
            "ridge_candidates": list(RIDGE_CANDIDATES),
            "optimizer": "deterministic Adam, numeric eta gradient",
            "iterations": 300,
            "learning_rate": 0.04,
        },
        "calibration": {
            "partition": "calibration_only",
            "temperature_candidates": list(TEMPERATURE_CANDIDATES),
            "selection_metric": "multiclass_log_loss",
        },
        "final_test": {
            "labels_fetched_in": "M8.6_only",
            "legacy_probabilities_fetched_in": "M8.6_only",
            "retuning_after_open": False,
        },
        "production_effect": "none",
    }
    return add_payload_hash(payload)


def prepare() -> None:
    contract = frozen_execution_contract()
    write_json(EXECUTION_CONTRACT_PATH, contract)
    inventory = read_json(INVENTORY_PATH)
    cuts = inventory["chronological_cuts"]
    captured_at = datetime.now(timezone.utc)
    with connect() as db:
        raw_rows = [dict(row) for row in db.execute(SQL_CANDIDATES).fetchall()]
    close_pool()
    records = normalize_candidate_rows(raw_rows, cuts)
    records = enrich_pretrade_features(records)
    development_calibration = [
        row for row in records if row["partition"] != "final_test"
    ]
    final_rows = [row for row in records if row["partition"] == "final_test"]
    development_calibration = enrich_outcomes(
        development_calibration,
        captured_at=captured_at,
    )
    dataset = add_payload_hash(
        {
            "version": "M8.3-development-calibration-dataset-v0.1",
            "phase": "M8",
            "subphase": "M8.3",
            "captured_at": captured_at.isoformat(),
            "execution_contract_sha256": file_sha256(EXECUTION_CONTRACT_PATH),
            "final_test_labels_accessed": False,
            "legacy_probabilities_accessed": False,
            "records": [
                public_record(row, include_outcome=True)
                for row in development_calibration
            ],
        }
    )
    sealed = add_payload_hash(
        {
            "version": "M8.3-sealed-final-features-v0.1",
            "phase": "M8",
            "subphase": "M8.3",
            "captured_at": captured_at.isoformat(),
            "execution_contract_sha256": file_sha256(EXECUTION_CONTRACT_PATH),
            "status": "features_prepared_labels_not_fetched",
            "outcome_fields": [],
            "legacy_probability_fields": [],
            "records": [
                public_record(row, include_outcome=False) for row in final_rows
            ],
        }
    )
    write_json(DATASET_PATH, dataset)
    write_json(SEALED_FINAL_PATH, sealed)
    usable = eligible_labeled_rows(dataset["records"])
    counts = Counter(row["outcome"]["label"] for row in usable)
    horizon_counts = Counter(row["horizon_status"] for row in dataset["records"])
    report = "\n".join(
        [
            "# M8.3 - Reconstruccion de outcomes",
            "",
            "Estado: COMPLETADA; PRUEBA FINAL AUN SELLADA",
            "",
            f"- Registros desarrollo/calibracion: {len(dataset['records'])}.",
            f"- Outcomes utilizables: {len(usable)}.",
            f"- TP primero: {counts[CLASSES[0]]}.",
            f"- SL primero: {counts[CLASSES[1]]}.",
            f"- Sin barrera al expirar: {counts[CLASSES[2]]}.",
            f"- Horizonte exacto almacenado: {horizon_counts['stored_exact']}.",
            (
                "- Horizonte reconstruido por politica: "
                f"{horizon_counts['policy_reconstructed']}."
            ),
            "",
            "Los registros con horizonte reconstruido forman una cohorte",
            "retrospectiva y no satisfacen por si solos la validacion formal.",
            "",
            f"Registros finales sellados sin outcome: {len(sealed['records'])}.",
        ]
    )
    write_text(M83_REPORT_PATH, report)


def baseline() -> None:
    dataset = read_json(DATASET_PATH)
    rows = eligible_labeled_rows(dataset["records"])
    development = [row for row in rows if row["partition"] == "development"]
    calibration = [row for row in rows if row["partition"] == "calibration"]
    empirical = empirical_probabilities(development)
    baseline_values = baseline_predictions(calibration)
    empirical_values = constant_predictions(calibration, empirical)
    payload = add_payload_hash(
        {
            "version": "M8.4-baseline-evaluation-v0.1",
            "phase": "M8",
            "subphase": "M8.4",
            "status": "completed_retrospective_cohort",
            "dataset_sha256": file_sha256(DATASET_PATH),
            "formal_validation_possible": any(
                row["formal_eligible_horizon"] for row in calibration
            ),
            "development_n": len(development),
            "calibration_n": len(calibration),
            "development_class_frequency": empirical,
            "baseline": evaluate_predictions(calibration, baseline_values),
            "empirical_comparator": evaluate_predictions(
                calibration,
                empirical_values,
            ),
            "paired_baseline_minus_empirical": bootstrap_paired_differences(
                calibration,
                baseline_values,
                empirical_values,
            ),
            "production_effect": "none",
        }
    )
    write_json(M84_PATH, payload)
    write_text(
        M84_REPORT_PATH,
        "\n".join(
            [
                "# M8.4 - Evaluacion del baseline matematico",
                "",
                "Estado: COMPLETADA EN COHORTE RETROSPECTIVA",
                "",
                f"- Desarrollo utilizable: {len(development)}.",
                f"- Calibracion utilizable: {len(calibration)}.",
                f"- Brier baseline: {payload['baseline']['brier_3c']:.6f}.",
                f"- Log-loss baseline: {payload['baseline']['log_loss_3c']:.6f}.",
                (
                    "- Brier frecuencia empirica: "
                    f"{payload['empirical_comparator']['brier_3c']:.6f}."
                ),
                "",
                "No se ha abierto la prueba final.",
            ]
        ),
    )


def fit() -> None:
    dataset = read_json(DATASET_PATH)
    rows = eligible_labeled_rows(dataset["records"])
    development = [row for row in rows if row["partition"] == "development"]
    calibration = [row for row in rows if row["partition"] == "calibration"]
    if len(development) < 10 or len(calibration) < 5:
        raise RuntimeError("insufficient_rows_for_fit_and_calibration")
    development_fit, development_blocked = competing_risk_compatibility(
        development
    )
    calibration_fit, calibration_blocked = competing_risk_compatibility(
        calibration
    )
    if len(development_fit) < 10 or len(calibration_fit) < 5:
        raise RuntimeError("insufficient_competing_risk_compatible_rows")
    scaling = standardization(development_fit)
    prepared = prepare_fit_rows(development_fit, scaling)
    candidates = []
    for ridge in RIDGE_CANDIDATES:
        coefficients = fit_evidence_coefficients(prepared, ridge=ridge)
        artifact = build_coefficient_artifact(
            coefficients=coefficients,
            scaling=scaling,
            training_cutoff=max(row["analysis_at"] for row in development),
            ridge=ridge,
        )
        predictions = candidate_predictions(calibration_fit, artifact)
        metrics = evaluate_predictions(calibration_fit, predictions)
        candidates.append(
            {
                "ridge_lambda": ridge,
                "artifact": artifact,
                "calibration_metrics_raw": metrics,
            }
        )
    selected = min(
        candidates,
        key=lambda item: item["calibration_metrics_raw"]["log_loss_3c"],
    )
    temperatures = []
    for temperature in TEMPERATURE_CANDIDATES:
        predictions = candidate_predictions(
            calibration_fit,
            selected["artifact"],
            temperature=temperature,
        )
        temperatures.append(
            {
                "temperature": temperature,
                "metrics": evaluate_predictions(calibration, predictions),
            }
        )
    selected_temperature = min(
        temperatures,
        key=lambda item: item["metrics"]["log_loss_3c"],
    )
    payload = add_payload_hash(
        {
            "version": "M8.5-estimated-calibrated-model-v0.1",
            "phase": "M8",
            "subphase": "M8.5",
            "status": "frozen_internal_candidate_retrospective_training",
            "dataset_sha256": file_sha256(DATASET_PATH),
            "development_n": len(development),
            "calibration_n": len(calibration),
            "development_fit_n": len(development_fit),
            "calibration_fit_n": len(calibration_fit),
            "competing_risk_blocked": (
                development_blocked + calibration_blocked
            ),
            "feature_names": list(FIT_FEATURE_NAMES),
            "candidate_summary": [
                {
                    "ridge_lambda": item["ridge_lambda"],
                    "artifact_id": item["artifact"]["id"],
                    "calibration_metrics_raw": item[
                        "calibration_metrics_raw"
                    ],
                }
                for item in candidates
            ],
            "selected_coefficient_artifact": selected["artifact"],
            "temperature_candidates": temperatures,
            "selected_temperature": selected_temperature["temperature"],
            "selected_calibration_metrics": selected_temperature["metrics"],
            "locked_before_final_test": True,
            "production_authorized": False,
        }
    )
    write_json(M85_PATH, payload)
    write_text(
        M85_REPORT_PATH,
        "\n".join(
            [
                "# M8.5 - Estimacion y calibracion",
                "",
                "Estado: CANDIDATO INTERNO CONGELADO",
                "",
                (
                    "- Lambda seleccionada: "
                    f"{selected['ridge_lambda']:g}."
                ),
                (
                    "- Temperatura seleccionada: "
                    f"{selected_temperature['temperature']:g}."
                ),
                (
                    "- Brier calibracion: "
                    f"{selected_temperature['metrics']['brier_3c']:.6f}."
                ),
                (
                    "- Log-loss calibracion: "
                    f"{selected_temperature['metrics']['log_loss_3c']:.6f}."
                ),
                "",
                (
                    "- Casos bloqueados por la capa discreta M6: "
                    f"{len(development_blocked) + len(calibration_blocked)}."
                ),
                "Los coeficientes no estan autorizados para produccion.",
                "La prueba final continuaba sellada al congelar el candidato.",
            ]
        ),
    )


def fetch_legacy(rows: list[dict]) -> dict[int, dict]:
    ids = [row["recommendation_id"] for row in rows]
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    query = f"""
        SELECT id, tp_probability, sl_probability, range_probability
        FROM recommendations
        WHERE id IN ({placeholders})
    """
    with connect() as db:
        raw = [dict(row) for row in db.execute(query, ids).fetchall()]
    close_pool()
    return {
        int(row["id"]): values
        for row in raw
        if (values := normalize_legacy_probabilities(row)) is not None
    }


def final_test() -> None:
    sealed = read_json(SEALED_FINAL_PATH)
    model = read_json(M85_PATH)
    captured_at = datetime.now(timezone.utc)
    rows = enrich_outcomes(
        [dict(row) for row in sealed["records"]],
        captured_at=captured_at,
    )
    labeled = eligible_labeled_rows(rows)
    candidate_rows, final_model_blocked = competing_risk_compatibility(labeled)
    formal = [
        row for row in candidate_rows if row["formal_eligible_horizon"]
    ]
    baseline_values = baseline_predictions(candidate_rows)
    artifact = model["selected_coefficient_artifact"]
    temperature = float(model["selected_temperature"])
    candidate_values = candidate_predictions(
        candidate_rows,
        artifact,
        temperature=temperature,
    )
    development = eligible_labeled_rows(read_json(DATASET_PATH)["records"])
    development = [
        row for row in development if row["partition"] == "development"
    ]
    empirical = empirical_probabilities(development)
    empirical_values = constant_predictions(candidate_rows, empirical)
    legacy_all = fetch_legacy(candidate_rows)
    legacy_rows = [
        row
        for row in candidate_rows
        if row["recommendation_id"] in legacy_all
    ]
    legacy_values = {
        row["recommendation_id"]: legacy_all[row["recommendation_id"]]
        for row in legacy_rows
    }
    candidate_legacy = {
        row["recommendation_id"]: candidate_values[row["recommendation_id"]]
        for row in legacy_rows
    }
    ablations = {}
    for feature in FEATURE_NAMES:
        values = candidate_predictions(
            candidate_rows,
            artifact,
            temperature=temperature,
            ablate_feature=feature,
        )
        ablations[feature] = evaluate_predictions(candidate_rows, values)
    earlier_model_blocks = model.get("competing_risk_blocked") or []
    if earlier_model_blocks or final_model_blocked:
        strict_reason = "m6_discrete_hazard_mass_defect"
        decision = "return_to_earlier_phase"
    elif not formal:
        strict_reason = "no_resolved_formal_records"
        decision = "insufficient_evidence"
    elif len(formal) < 20:
        strict_reason = "formal_sample_too_small"
        decision = "insufficient_evidence"
    else:
        strict_reason = None
        decision = "approved_for_M9_consideration"
    payload = add_payload_hash(
        {
            "version": "M8.6-locked-final-test-v0.1",
            "phase": "M8",
            "subphase": "M8.6",
            "status": "final_test_opened_once_no_retuning",
            "captured_at": captured_at.isoformat(),
            "sealed_dataset_sha256": file_sha256(SEALED_FINAL_PATH),
            "frozen_model_sha256": file_sha256(M85_PATH),
            "final_records_total": len(rows),
            "final_records_labeled": len(labeled),
            "final_records_candidate_compatible": len(candidate_rows),
            "final_records_formal": len(formal),
            "competing_risk_blocked": {
                "development_calibration": earlier_model_blocks,
                "final_test": final_model_blocked,
            },
            "outcome_status_counts": dict(
                Counter(row["outcome"]["status"] for row in rows)
            ),
            "retrospective_results": {
                "candidate": evaluate_predictions(
                    candidate_rows,
                    candidate_values,
                ),
                "baseline": evaluate_predictions(
                    candidate_rows,
                    baseline_values,
                ),
                "empirical": evaluate_predictions(
                    candidate_rows,
                    empirical_values,
                ),
                "legacy": (
                    evaluate_predictions(legacy_rows, legacy_values)
                    if legacy_rows
                    else {"n": 0, "status": "unavailable"}
                ),
                "candidate_minus_baseline_bootstrap": (
                    bootstrap_paired_differences(
                        candidate_rows,
                        candidate_values,
                        baseline_values,
                    )
                ),
                "candidate_minus_legacy_bootstrap": (
                    bootstrap_paired_differences(
                        legacy_rows,
                        candidate_legacy,
                        legacy_values,
                    )
                    if legacy_rows
                    else {"status": "unavailable"}
                ),
                "stability": subgroup_metrics(
                    candidate_rows,
                    candidate_values,
                ),
                "ablations": ablations,
            },
            "formal_results": (
                {
                    "candidate": evaluate_predictions(
                        formal,
                        {
                            row["recommendation_id"]: candidate_values[
                                row["recommendation_id"]
                            ]
                            for row in formal
                        },
                    )
                }
                if formal
                else {"n": 0, "status": "no_resolved_formal_records"}
            ),
            "decision": {
                "state": decision,
                "reason": strict_reason,
                "m9_unblocked": decision == "approved_for_M9_consideration",
            },
            "retuning_after_final_open": False,
            "production_effect": "none",
        }
    )
    write_json(M86_PATH, payload)
    retrospective = payload["retrospective_results"]
    write_text(
        M86_REPORT_PATH,
        "\n".join(
            [
                "# M8.6 - Prueba final bloqueada",
                "",
                "Estado: ABIERTA UNA VEZ; SIN RETOQUES POSTERIORES",
                "",
                f"- Registros finales: {len(rows)}.",
                f"- Outcomes utilizables: {len(labeled)}.",
                f"- Registros formalmente validos: {len(formal)}.",
                (
                    "- Brier candidato retrospectivo: "
                    f"{retrospective['candidate']['brier_3c']:.6f}."
                    if candidate_rows
                    else "- Brier candidato: no evaluable."
                ),
                (
                    "- Brier baseline retrospectivo: "
                    f"{retrospective['baseline']['brier_3c']:.6f}."
                    if candidate_rows
                    else "- Brier baseline: no evaluable."
                ),
                "",
                f"Decision formal: {decision}.",
                f"Motivo: {strict_reason}.",
                "",
                "No se autoriza produccion ni se desbloquea M9.",
            ]
        ),
    )


def fetch_economics(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    query = f"""
        SELECT
            r.id AS recommendation_id,
            o.final_pnl,
            o.margin,
            o.leverage,
            o.close_reason
        FROM recommendations r
        JOIN operations o ON o.id = r.operation_id
        WHERE r.id IN ({placeholders})
    """
    with connect() as db:
        rows = [dict(row) for row in db.execute(query, ids).fetchall()]
    close_pool()
    return rows


def close_m8() -> None:
    final_payload = read_json(M86_PATH)
    sealed = read_json(SEALED_FINAL_PATH)
    captured_at = parse_utc(final_payload["captured_at"])
    rows = enrich_outcomes(
        [dict(row) for row in sealed["records"]],
        captured_at=captured_at,
    )
    labeled = eligible_labeled_rows(rows)
    economics = fetch_economics(
        [row["recommendation_id"] for row in labeled]
    )
    pnl_values = [
        float(row["final_pnl"])
        for row in economics
        if row.get("final_pnl") is not None
        and math.isfinite(float(row["final_pnl"]))
    ]
    realized_plan_r = []
    for row in labeled:
        risk = abs(row["entry"] - row["stop_loss"])
        reward = abs(row["take_profit"] - row["entry"])
        label = row["outcome"]["label"]
        realized_plan_r.append(
            reward / risk
            if label == CLASSES[0]
            else -1.0
            if label == CLASSES[1]
            else 0.0
        )
    decision = final_payload["decision"]
    payload = add_payload_hash(
        {
            "version": "M8.7-closure-package-v0.1",
            "phase": "M8",
            "subphase": "M8.7",
            "status": "m8_closed",
            "decision": decision,
            "inputs": [
                {
                    "path": path.name,
                    "sha256": file_sha256(path),
                }
                for path in (
                    PROTOCOL_PATH,
                    INVENTORY_PATH,
                    EXECUTION_CONTRACT_PATH,
                    DATASET_PATH,
                    SEALED_FINAL_PATH,
                    M84_PATH,
                    M85_PATH,
                    M86_PATH,
                )
            ],
            "secondary_economics": {
                "labeled_final_records": len(labeled),
                "mean_realized_plan_r": (
                    math.fsum(realized_plan_r) / len(realized_plan_r)
                    if realized_plan_r
                    else None
                ),
                "actual_user_pnl_records": len(pnl_values),
                "mean_actual_user_pnl": (
                    math.fsum(pnl_values) / len(pnl_values)
                    if pnl_values
                    else None
                ),
                "actual_user_pnl_role": (
                    "secondary_descriptive_only_mixes_execution_leverage_and_user_behavior"
                ),
                "fees_slippage_funding": "not_reconstructible_consistently",
                "profitability_claim": False,
            },
            "quantified_blockers": {
                "historical_records_without_stored_exact_horizon": (
                    sum(
                        row["horizon_status"] == "policy_reconstructed"
                        for row in read_json(DATASET_PATH)["records"]
                    )
                    + sum(
                        row["horizon_status"] == "policy_reconstructed"
                        for row in sealed["records"]
                    )
                ),
                "formal_final_records": final_payload["final_records_formal"],
                "final_labeled_retrospective_records": final_payload[
                    "final_records_labeled"
                ],
            },
            "required_next_actions": [
                "Store analysis_at, data_cutoff_at and exact horizon_seconds for every new analysis.",
                "Run the frozen M5/M6 design prospectively without production effect.",
                "Accumulate a temporally later final cohort containing resolved TP, SL and expiry classes.",
                "Repeat M8 final evaluation without reusing the opened 2026-07 final period.",
            ],
            "boundaries": {
                "m8_closed": True,
                "m9_started": False,
                "m9_blocked": not decision["m9_unblocked"],
                "production_effect": "none",
                "production_authorized": False,
            },
        }
    )
    write_json(M87_PATH, payload)
    write_text(
        M87_REPORT_PATH,
        "\n".join(
            [
                "# M8.7 - Cierre de evaluacion",
                "",
                "Estado: M8 CERRADA",
                "",
                f"Decision: {decision['state']}.",
                f"Motivo: {decision['reason']}.",
                (
                    "- Registros historicos sin horizonte exacto: "
                    f"{payload['quantified_blockers']['historical_records_without_stored_exact_horizon']}."
                ),
                (
                    "- Registros formales en prueba final: "
                    f"{payload['quantified_blockers']['formal_final_records']}."
                ),
                (
                    "- Registros retrospectivos finales evaluables: "
                    f"{payload['quantified_blockers']['final_labeled_retrospective_records']}."
                ),
                "",
                "La evidencia retrospectiva se conserva como diagnostico.",
                "No autoriza produccion, rentabilidad ni el inicio de M9.",
            ]
        ),
    )


def check() -> None:
    paths = (
        EXECUTION_CONTRACT_PATH,
        DATASET_PATH,
        SEALED_FINAL_PATH,
        M84_PATH,
        M85_PATH,
        M86_PATH,
        M87_PATH,
    )
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise SystemExit(f"missing_artifacts:{','.join(missing)}")
    for path in paths:
        payload = read_json(path)
        expected = payload.get("canonical_payload_sha256")
        actual = payload_sha256(
            {
                key: value
                for key, value in payload.items()
                if key != "canonical_payload_sha256"
            }
        )
        if expected != actual:
            raise SystemExit(f"artifact_hash_mismatch:{path.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage",
        choices=("prepare", "baseline", "fit", "final", "close", "all", "check"),
    )
    args = parser.parse_args()
    if args.stage == "check":
        check()
        return
    stages = (
        ("prepare", prepare),
        ("baseline", baseline),
        ("fit", fit),
        ("final", final_test),
        ("close", close_m8),
    )
    for name, function in stages:
        if args.stage in {name, "all"}:
            function()


if __name__ == "__main__":
    main()
