from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

import m8_evaluation as m8
from m6_remediated_competing_risks import (
    apply_competing_risk_evidence,
    build_baseline_intervals,
)


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DATASET_PATH = AUDIT_DIR / "dataset_desarrollo_calibracion_m8_3_v0_1.json"
GLOBAL_CANDIDATE_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
OUTPUT_PATH = AUDIT_DIR / "calibracion_horizontes_m6_v0_1.json"
HORIZONS = ("intraday_short", "intraday_wide", "short_swing")
TEMPERATURE_CANDIDATES = (
    0.5,
    0.75,
    1.0,
    1.25,
    1.5,
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    6.0,
)
GLOBAL_TEMPERATURE = 1.5
COEFFICIENT_PRIOR_STRENGTH = 30
TEMPERATURE_PRIOR_STRENGTH = 20
RIDGE = 10.0
REMOVED_FEATURE = "directional_path_efficiency_h"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def install_remediated_layer() -> None:
    m8.build_baseline_intervals = build_baseline_intervals
    m8.apply_competing_risk_evidence = apply_competing_risk_evidence


def metric_pair(rows: list[dict], predictions: dict[int, dict]) -> dict:
    return {
        "log_loss": m8.metric_log_loss(rows, predictions),
        "brier_3c": m8.metric_brier(rows, predictions),
    }


def pool_coefficients(
    global_artifact: dict,
    local_coefficients: dict,
    *,
    local_records: int,
) -> tuple[dict, float]:
    weight = local_records / (
        local_records + COEFFICIENT_PRIOR_STRENGTH
    )
    pooled = {
        cause: {
            feature: (
                weight * float(local_coefficients[cause][feature])
                + (1.0 - weight)
                * float(global_artifact["coefficients"][cause][feature])
            )
            for feature in global_artifact["coefficients"][cause]
        }
        for cause in ("tp", "sl")
    }
    return pooled, weight


def candidate_artifact(
    global_artifact: dict,
    *,
    horizon: str,
    coefficients: dict,
    training_cutoff: str,
    coefficient_weight: float,
    selection_status: str,
) -> dict:
    artifact = copy.deepcopy(global_artifact)
    artifact.update(
        {
            "id": (
                f"M6-HORIZON-{horizon.upper().replace('_', '-')}-"
                "PARTIAL-POOL-v0.1"
            ),
            "version": "0.1",
            "training_cutoff": training_cutoff,
            "coefficients": coefficients,
            "partial_pooling": {
                "selection_status": selection_status,
                "local_weight": coefficient_weight,
                "global_weight": 1.0 - coefficient_weight,
                "prior_strength_records": COEFFICIENT_PRIOR_STRENGTH,
                "source_global_artifact_id": global_artifact["id"],
            },
        }
    )
    artifact["artifact_sha256"] = m8.payload_sha256(
        {
            key: value
            for key, value in artifact.items()
            if key != "artifact_sha256"
        }
    )
    return artifact


def select_temperature(
    rows: list[dict],
    artifact: dict,
) -> tuple[float, dict]:
    evaluated = []
    for temperature in TEMPERATURE_CANDIDATES:
        predictions = m8.candidate_predictions(
            rows,
            artifact,
            temperature=temperature,
        )
        metrics = metric_pair(rows, predictions)
        evaluated.append(
            {
                "temperature": temperature,
                **metrics,
            }
        )
    selected = min(
        evaluated,
        key=lambda item: (
            item["log_loss"],
            item["brier_3c"],
            item["temperature"],
        ),
    )
    return float(selected["temperature"]), selected


def build_payload() -> dict:
    install_remediated_layer()
    rows = m8.eligible_labeled_rows(read_json(DATASET_PATH)["records"])
    global_payload = read_json(GLOBAL_CANDIDATE_PATH)
    global_artifact = global_payload["coefficient_artifact"]
    profiles = {}
    for horizon in HORIZONS:
        development = [
            row
            for row in rows
            if row["partition"] == "development"
            and row["time_horizon"] == horizon
        ]
        calibration = [
            row
            for row in rows
            if row["partition"] == "calibration"
            and row["time_horizon"] == horizon
        ]
        prepared = m8.prepare_fit_rows(
            development,
            global_artifact["feature_standardization"],
        )
        local_coefficients = m8.fit_evidence_coefficients(
            prepared,
            ridge=RIDGE,
        )
        local_coefficients["tp"][REMOVED_FEATURE] = 0.0
        local_coefficients["sl"][REMOVED_FEATURE] = 0.0
        pooled_coefficients, coefficient_weight = pool_coefficients(
            global_artifact,
            local_coefficients,
            local_records=len(development),
        )
        training_cutoff = max(row["analysis_at"] for row in development)
        pooled_artifact = candidate_artifact(
            global_artifact,
            horizon=horizon,
            coefficients=pooled_coefficients,
            training_cutoff=training_cutoff,
            coefficient_weight=coefficient_weight,
            selection_status="candidate_partial_pooling",
        )

        global_predictions = m8.candidate_predictions(
            calibration,
            global_artifact,
            temperature=GLOBAL_TEMPERATURE,
        )
        global_metrics = metric_pair(calibration, global_predictions)
        pooled_best_temperature, pooled_best = select_temperature(
            calibration,
            pooled_artifact,
        )
        pooled_improves = (
            pooled_best["log_loss"] <= global_metrics["log_loss"]
            and pooled_best["brier_3c"] <= global_metrics["brier_3c"]
        )
        if pooled_improves:
            selected_artifact = candidate_artifact(
                global_artifact,
                horizon=horizon,
                coefficients=pooled_coefficients,
                training_cutoff=training_cutoff,
                coefficient_weight=coefficient_weight,
                selection_status="selected_partial_pooling",
            )
            coefficient_selection = "selected_partial_pooling"
        else:
            selected_artifact = candidate_artifact(
                global_artifact,
                horizon=horizon,
                coefficients=copy.deepcopy(global_artifact["coefficients"]),
                training_cutoff=global_artifact["training_cutoff"],
                coefficient_weight=0.0,
                selection_status="fallback_global_no_holdout_improvement",
            )
            coefficient_selection = "fallback_global_no_holdout_improvement"

        local_temperature, local_best = select_temperature(
            calibration,
            selected_artifact,
        )
        temperature_weight = len(calibration) / (
            len(calibration) + TEMPERATURE_PRIOR_STRENGTH
        )
        served_temperature = math.exp(
            temperature_weight * math.log(local_temperature)
            + (1.0 - temperature_weight)
            * math.log(GLOBAL_TEMPERATURE)
        )
        served_predictions = m8.candidate_predictions(
            calibration,
            selected_artifact,
            temperature=served_temperature,
        )
        served_metrics = metric_pair(calibration, served_predictions)
        if (
            served_metrics["log_loss"] > global_metrics["log_loss"]
            or served_metrics["brier_3c"] > global_metrics["brier_3c"]
        ):
            raise RuntimeError(f"{horizon}_served_profile_not_improved")
        if len(calibration) >= 20:
            support_status = "provisional_partial_pooling"
        elif len(calibration) >= 10:
            support_status = "limited_partial_pooling"
        else:
            support_status = "low_sample_partial_pooling"
        profiles[horizon] = {
            "development_records": len(development),
            "calibration_records": len(calibration),
            "coefficient_selection": coefficient_selection,
            "coefficient_local_weight": selected_artifact[
                "partial_pooling"
            ]["local_weight"],
            "pooled_candidate_best_temperature": pooled_best_temperature,
            "pooled_candidate_best_log_loss": pooled_best["log_loss"],
            "pooled_candidate_best_brier_3c": pooled_best["brier_3c"],
            "local_best_temperature": local_temperature,
            "local_best_log_loss": local_best["log_loss"],
            "local_best_brier_3c": local_best["brier_3c"],
            "served_temperature": served_temperature,
            "global_log_loss": global_metrics["log_loss"],
            "served_log_loss": served_metrics["log_loss"],
            "global_brier_3c": global_metrics["brier_3c"],
            "served_brier_3c": served_metrics["brier_3c"],
            "support_status": support_status,
            "coefficient_artifact": selected_artifact,
        }

    payload = {
        "version": "M6-horizon-calibration-v0.1",
        "method": "hierarchical_coefficients_and_log_temperature_partial_pooling",
        "source_candidate": global_artifact["id"],
        "source_dataset": DATASET_PATH.name,
        "selection_partition": "calibration",
        "selection_metric": "log_loss_3c_then_brier_3c",
        "global_temperature": GLOBAL_TEMPERATURE,
        "coefficient_prior_strength_records": COEFFICIENT_PRIOR_STRENGTH,
        "temperature_prior_strength_records": TEMPERATURE_PRIOR_STRENGTH,
        "local_temperature_candidates": list(TEMPERATURE_CANDIDATES),
        "profiles": profiles,
    }
    payload["canonical_payload_sha256"] = m8.payload_sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build_payload()
    if args.write:
        OUTPUT_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
