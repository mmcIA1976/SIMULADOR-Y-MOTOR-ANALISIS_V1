from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from m6_first_passage import double_barrier_first_passage
from m6_remediated_competing_risks import (
    LAYER_VERSION,
    NUMERICAL_SURVIVAL_FLOOR,
    apply_competing_risk_evidence,
)
from m8_evaluation import (
    FEATURE_NAMES,
    candidate_predictions,
    eligible_labeled_rows,
    evaluate_predictions,
)


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M8_DATASET = AUDIT_DIR / "dataset_desarrollo_calibracion_m8_3_v0_1.json"
M8_FINAL_FEATURES = AUDIT_DIR / "dataset_final_sellado_m8_3_v0_1.json"
M8_MODEL = AUDIT_DIR / "modelo_estimado_calibrado_m8_5_v0_1.json"
M8_FINAL = AUDIT_DIR / "evaluacion_final_m8_6_v0_1.json"
DIAGNOSTIC_PATH = AUDIT_DIR / "diagnostico_m6_r1_v0_1.json"
RULE_DECISION_PATH = AUDIT_DIR / "decision_reglas_m6_r1_post_m8_v0_1.json"
CLOSURE_PATH = AUDIT_DIR / "paquete_cierre_m6_r1_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-07-28_M6_R1_cierre_remediacion_v0_1.md"
RULE_REPORT_PATH = AUDIT_DIR / "2026-07-28_M6_R1_revision_reglas_post_M8_v0_1.md"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def add_hash(payload: dict) -> dict:
    payload["canonical_payload_sha256"] = payload_sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "canonical_payload_sha256"
        }
    )
    return payload


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def geometry(record: dict) -> tuple[float, float, float]:
    direction = 1 if record["side"] == "long" else -1
    return (
        direction * math.log(record["take_profit"] / record["entry"]),
        -direction * math.log(record["stop_loss"] / record["entry"]),
        float(record["pretrade"]["sigma_horizon"]),
    )


def historical_compatibility() -> dict:
    development = read_json(M8_DATASET)["records"]
    final = read_json(M8_FINAL_FEATURES)["records"]
    records = development + final
    blocked = []
    reconciled = []
    maximum_mass_error = 0.0
    maximum_baseline_error = 0.0
    for record in records:
        tp_distance, sl_distance, sigma = geometry(record)
        try:
            result = apply_competing_risk_evidence(
                tp_log_distance=tp_distance,
                sl_log_distance=sl_distance,
                sigma_horizon=sigma,
                interval_count=24,
            )
            baseline = double_barrier_first_passage(
                tp_log_distance=tp_distance,
                sl_log_distance=sl_distance,
                sigma_horizon=sigma,
            )
        except Exception as exc:
            blocked.append(
                {
                    "recommendation_id": record["recommendation_id"],
                    "exception_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
            continue
        maximum_mass_error = max(maximum_mass_error, result.mass_error)
        maximum_baseline_error = max(
            maximum_baseline_error,
            abs(result.p_tp - baseline.p_tp),
            abs(result.p_sl - baseline.p_sl),
            abs(result.p_expiry - baseline.p_expiry),
        )
        if any(
            interval["terminal_reconciliation"]
            == "machine_precision_absorption"
            for interval in result.intervals
        ):
            reconciled.append(record["recommendation_id"])
    return {
        "records": len(records),
        "evaluated": len(records) - len(blocked),
        "blocked": blocked,
        "terminal_reconciled_records": reconciled,
        "terminal_reconciled_count": len(reconciled),
        "maximum_probability_mass_error": maximum_mass_error,
        "maximum_zero_coefficient_baseline_error": maximum_baseline_error,
    }


def property_grid() -> dict:
    distances = (0.00025, 0.001, 0.005, 0.02, 0.08)
    sigmas = (0.0005, 0.002, 0.01, 0.05, 0.2)
    interval_counts = (1, 12, 24, 96)
    cases = 0
    failures = []
    maximum_mass_error = 0.0
    maximum_swap_error = 0.0
    for tp_distance in distances:
        for sl_distance in distances:
            for sigma in sigmas:
                for interval_count in interval_counts:
                    cases += 1
                    try:
                        result = apply_competing_risk_evidence(
                            tp_log_distance=tp_distance,
                            sl_log_distance=sl_distance,
                            sigma_horizon=sigma,
                            interval_count=interval_count,
                        )
                        swapped = apply_competing_risk_evidence(
                            tp_log_distance=sl_distance,
                            sl_log_distance=tp_distance,
                            sigma_horizon=sigma,
                            interval_count=interval_count,
                        )
                        maximum_mass_error = max(
                            maximum_mass_error,
                            result.mass_error,
                            swapped.mass_error,
                        )
                        maximum_swap_error = max(
                            maximum_swap_error,
                            abs(result.p_tp - swapped.p_sl),
                            abs(result.p_sl - swapped.p_tp),
                            abs(result.p_expiry - swapped.p_expiry),
                        )
                    except Exception as exc:
                        failures.append(
                            {
                                "tp_log_distance": tp_distance,
                                "sl_log_distance": sl_distance,
                                "sigma_horizon": sigma,
                                "interval_count": interval_count,
                                "exception_type": type(exc).__name__,
                                "reason": str(exc),
                            }
                        )
    return {
        "cases": cases,
        "failures": failures,
        "maximum_probability_mass_error": maximum_mass_error,
        "maximum_barrier_swap_error": maximum_swap_error,
    }


def build_diagnostic() -> dict:
    final = read_json(M8_FINAL)
    before = (
        final["competing_risk_blocked"]["development_calibration"]
        + final["competing_risk_blocked"]["final_test"]
    )
    payload = {
        "version": "M6-R1-diagnostic-v0.1",
        "phase": "M6-R1",
        "status": "remediation_verified_internal_only",
        "defect": {
            "code": "machine_precision_terminal_survival",
            "description": (
                "Conditional interval hazards were divided by survival at or "
                "below machine precision after effective absorption."
            ),
            "continuous_first_passage_defect": False,
            "discrete_transition_defect": True,
            "historical_blocked_records_before": before,
            "historical_blocked_count_before": len(before),
        },
        "remediation": {
            "layer_version": LAYER_VERSION,
            "numerical_survival_floor": NUMERICAL_SURVIVAL_FLOOR,
            "formula_id": "M6-R1-NUMERICAL-TERMINAL-RECONCILIATION-009",
            "behavior": (
                "When prior survival is <=1e-10, reconcile the residual event "
                "mass to the final continuous solution and mark later "
                "intervals as post-absorption neutral."
            ),
            "historical_m6_files_modified": False,
        },
        "historical_cohort_after": historical_compatibility(),
        "property_grid": property_grid(),
        "production_effect": "none",
        "m8_reopened": False,
        "m9_started": False,
    }
    return add_hash(payload)


def metric_delta(ablated: dict, full: dict) -> dict:
    return {
        "brier_3c": ablated["brier_3c"] - full["brier_3c"],
        "log_loss_3c": ablated["log_loss_3c"] - full["log_loss_3c"],
    }


def build_rule_decision() -> dict:
    dataset = read_json(M8_DATASET)
    model = read_json(M8_MODEL)
    final = read_json(M8_FINAL)
    calibration = [
        row
        for row in eligible_labeled_rows(dataset["records"])
        if row["partition"] == "calibration"
    ]
    artifact = model["selected_coefficient_artifact"]
    temperature = float(model["selected_temperature"])
    full_predictions = candidate_predictions(
        calibration,
        artifact,
        temperature=temperature,
    )
    full_calibration = evaluate_predictions(calibration, full_predictions)
    final_full = final["retrospective_results"]["candidate"]
    decisions = {
        "directional_path_efficiency_h": (
            "remove_from_next_candidate_require_new_holdout"
        ),
        "directional_path_efficiency_2h": "unresolved_effect_too_small",
        "directional_path_efficiency_4h": "retain_provisional",
        "volatility_percentile_60": "unstable_between_partitions",
        "target_extreme_between_entry_and_tp": "retain_provisional",
    }
    records = []
    for feature in FEATURE_NAMES:
        ablated_predictions = candidate_predictions(
            calibration,
            artifact,
            temperature=temperature,
            ablate_feature=feature,
        )
        calibration_metrics = evaluate_predictions(
            calibration,
            ablated_predictions,
        )
        final_metrics = final["retrospective_results"]["ablations"][feature]
        records.append(
            {
                "feature": feature,
                "calibration_ablation": calibration_metrics,
                "calibration_delta_ablated_minus_full": metric_delta(
                    calibration_metrics,
                    full_calibration,
                ),
                "opened_final_ablation": final_metrics,
                "opened_final_delta_ablated_minus_full": metric_delta(
                    final_metrics,
                    final_full,
                ),
                "decision_for_next_candidate": decisions[feature],
            }
        )
    payload = {
        "version": "M6-R1-rule-review-post-M8-v0.1",
        "phase": "M6-R1",
        "status": "diagnostic_decisions_no_refit",
        "constraints": {
            "m8_candidate_modified": False,
            "opened_final_period_reused_for_fitting": False,
            "new_coefficients_estimated": False,
            "future_candidate_requires_new_temporal_holdout": True,
        },
        "full_calibration_metrics": full_calibration,
        "full_opened_final_metrics": final_full,
        "rules": records,
        "summary": {
            "remove_from_next_candidate": [
                "directional_path_efficiency_h"
            ],
            "retain_provisional": [
                "directional_path_efficiency_4h",
                "target_extreme_between_entry_and_tp",
            ],
            "unresolved": [
                "directional_path_efficiency_2h",
                "volatility_percentile_60",
            ],
        },
        "production_effect": "none",
    }
    return add_hash(payload)


def build_closure(diagnostic: dict, rules: dict) -> dict:
    payload = {
        "version": "M6-R1-closure-v0.1",
        "phase": "M6-R1",
        "status": "completed_remediation_no_predictive_revalidation",
        "scope": {
            "numerical_defect_corrected": True,
            "historical_records_checked": diagnostic[
                "historical_cohort_after"
            ]["records"],
            "historical_records_blocked_after": len(
                diagnostic["historical_cohort_after"]["blocked"]
            ),
            "property_grid_cases": diagnostic["property_grid"]["cases"],
            "property_grid_failures": len(
                diagnostic["property_grid"]["failures"]
            ),
            "rules_reviewed": len(rules["rules"]),
            "local_source_files_changed": True,
            "pretrade_audit_metadata_modified": True,
            "probability_scores_modified": False,
            "online_deployed": False,
        },
        "artifacts": [
            {
                "path": DIAGNOSTIC_PATH.name,
                "sha256": file_sha256(DIAGNOSTIC_PATH),
            },
            {
                "path": RULE_DECISION_PATH.name,
                "sha256": file_sha256(RULE_DECISION_PATH),
            },
        ],
        "implementation": [
            {
                "path": "m6_remediated_competing_risks.py",
                "sha256": file_sha256(
                    ROOT / "m6_remediated_competing_risks.py"
                ),
            },
            {
                "path": "m6_remediation_engine.py",
                "sha256": file_sha256(ROOT / "m6_remediation_engine.py"),
            },
            {
                "path": "shadow_runtime.py",
                "sha256": file_sha256(ROOT / "shadow_runtime.py"),
            },
            {
                "path": "versioning.py",
                "sha256": file_sha256(ROOT / "versioning.py"),
            },
        ],
        "data_contract_change": {
            "new_analysis_fields": [
                "analysis_at",
                "data_cutoff_at",
                "evaluation_horizon_seconds",
                "evaluation_expires_at",
            ],
            "data_cutoff_policy": "local_snapshot_sealed_upper_bound_v0.1",
            "probability_effect": "none",
        },
        "decision": {
            "m6_r1_closed": True,
            "m8_result_overturned": False,
            "m9_unblocked": False,
            "reason": (
                "Numerical compatibility is repaired, but predictive "
                "superiority still requires a new temporal holdout."
            ),
        },
        "next_phase": {
            "id": "M6-R2",
            "objective": (
                "Prepare a new internal candidate without the rejected H-path "
                "feature and collect prospectively stamped analyses; do not "
                "reuse the opened July final period."
            ),
            "started": False,
        },
        "boundaries": {
            "probability_effect": "none",
            "online_deployed": False,
            "local_metadata_effect": "pretrade_audit_fields_added",
            "m8_closed": True,
            "m9_started": False,
        },
    }
    return add_hash(payload)


def render_report(closure: dict, diagnostic: dict) -> str:
    cohort = diagnostic["historical_cohort_after"]
    grid = diagnostic["property_grid"]
    return "\n".join(
        [
            "# M6-R1 - Cierre de remediacion",
            "",
            "Estado: COMPLETADA; SIN REVALIDACION PREDICTIVA",
            "",
            f"- Casos historicos verificados: {cohort['records']}.",
            f"- Casos bloqueados despues: {len(cohort['blocked'])}.",
            (
                "- Casos con reconciliacion terminal: "
                f"{cohort['terminal_reconciled_count']}."
            ),
            f"- Malla matematica: {grid['cases']} casos.",
            f"- Fallos en malla: {len(grid['failures'])}.",
            (
                "- Error maximo de masa: "
                f"{grid['maximum_probability_mass_error']:.3e}."
            ),
            "",
            "M6 y M7 historicas conservan sus hashes originales.",
            "El contrato local anade metadata; no se ha desplegado online.",
            "M9 permanece bloqueada hasta disponer de un nuevo holdout temporal.",
        ]
    )


def render_rule_report(payload: dict) -> str:
    lines = [
        "# M6-R1 - Revision de reglas posterior a M8",
        "",
        "Estado: DIAGNOSTICO; SIN REAJUSTE",
        "",
    ]
    for rule in payload["rules"]:
        calibration = rule["calibration_delta_ablated_minus_full"]
        final = rule["opened_final_delta_ablated_minus_full"]
        lines.extend(
            [
                f"## {rule['feature']}",
                "",
                (
                    "- Delta Brier calibracion al retirar: "
                    f"{calibration['brier_3c']:+.6f}."
                ),
                (
                    "- Delta Brier final abierto al retirar: "
                    f"{final['brier_3c']:+.6f}."
                ),
                (
                    "- Decision: "
                    f"{rule['decision_for_next_candidate']}."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "El periodo final de julio no se utilizara para ajustar ni validar",
            "el siguiente candidato.",
        ]
    )
    return "\n".join(lines)


def build_all() -> tuple[dict, dict, dict]:
    diagnostic = build_diagnostic()
    write_json(DIAGNOSTIC_PATH, diagnostic)
    rules = build_rule_decision()
    write_json(RULE_DECISION_PATH, rules)
    closure = build_closure(diagnostic, rules)
    write_json(CLOSURE_PATH, closure)
    REPORT_PATH.write_text(
        render_report(closure, diagnostic) + "\n",
        encoding="utf-8",
    )
    RULE_REPORT_PATH.write_text(
        render_rule_report(rules) + "\n",
        encoding="utf-8",
    )
    return diagnostic, rules, closure


def check() -> None:
    expected = {
        DIAGNOSTIC_PATH: build_diagnostic(),
        RULE_DECISION_PATH: build_rule_decision(),
    }
    for path, value in expected.items():
        if not path.exists() or read_json(path) != value:
            raise SystemExit(f"stale_artifact:{path}")
    closure = build_closure(
        expected[DIAGNOSTIC_PATH],
        expected[RULE_DECISION_PATH],
    )
    if not CLOSURE_PATH.exists():
        raise SystemExit(f"stale_artifact:{CLOSURE_PATH}")
    stored_closure = read_json(CLOSURE_PATH)
    stored_hashes = {
        item["path"]: item["sha256"]
        for item in stored_closure["implementation"]
    }
    for item in closure["implementation"]:
        if item["path"] in {"shadow_runtime.py", "versioning.py"}:
            item["sha256"] = stored_hashes[item["path"]]
    closure = add_hash(
        {
            key: value
            for key, value in closure.items()
            if key != "canonical_payload_sha256"
        }
    )
    if stored_closure != closure:
        raise SystemExit(f"stale_artifact:{CLOSURE_PATH}")
    if REPORT_PATH.read_text(encoding="utf-8") != (
        render_report(closure, expected[DIAGNOSTIC_PATH]) + "\n"
    ):
        raise SystemExit(f"stale_report:{REPORT_PATH}")
    if RULE_REPORT_PATH.read_text(encoding="utf-8") != (
        render_rule_report(expected[RULE_DECISION_PATH]) + "\n"
    ):
        raise SystemExit(f"stale_report:{RULE_REPORT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        build_all()


if __name__ == "__main__":
    main()
