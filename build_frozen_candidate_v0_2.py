from __future__ import annotations

import json
from pathlib import Path

import m8_evaluation as m8
from m6_remediated_competing_risks import (
    apply_competing_risk_evidence,
    build_baseline_intervals,
)


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DATASET_PATH = AUDIT_DIR / "dataset_desarrollo_calibracion_m8_3_v0_1.json"
OUTPUT_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
REPORT_PATH = AUDIT_DIR / "2026-07-28_candidato_m6_v0_2_sin_path_h.md"
REMOVED_FEATURE = "directional_path_efficiency_h"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def install_remediated_layer() -> None:
    m8.build_baseline_intervals = build_baseline_intervals
    m8.apply_competing_risk_evidence = apply_competing_risk_evidence


def zero_removed_feature(rows: list[dict]) -> list[dict]:
    for row in rows:
        row["features"][REMOVED_FEATURE] = 0.0
    return rows


def candidate_predictions(
    rows: list[dict],
    artifact: dict,
    temperature: float,
) -> dict[int, dict]:
    return m8.candidate_predictions(
        rows,
        artifact,
        temperature=temperature,
    )


def build_candidate() -> dict:
    install_remediated_layer()
    records = m8.eligible_labeled_rows(read_json(DATASET_PATH)["records"])
    development = [
        row for row in records if row["partition"] == "development"
    ]
    calibration = [
        row for row in records if row["partition"] == "calibration"
    ]
    scaling = m8.standardization(development)
    prepared = zero_removed_feature(
        m8.prepare_fit_rows(development, scaling)
    )
    training_cutoff = max(row["analysis_at"] for row in development)
    candidates = []
    for ridge in m8.RIDGE_CANDIDATES:
        coefficients = m8.fit_evidence_coefficients(
            prepared,
            ridge=ridge,
        )
        coefficients["tp"][REMOVED_FEATURE] = 0.0
        coefficients["sl"][REMOVED_FEATURE] = 0.0
        artifact = m8.build_coefficient_artifact(
            coefficients=coefficients,
            scaling=scaling,
            training_cutoff=training_cutoff,
            ridge=ridge,
        )
        artifact["id"] = f"M6-CANDIDATE-NO-H-RIDGE-{ridge:g}-v0.2"
        artifact["version"] = "0.2"
        artifact["removed_predictive_features"] = [REMOVED_FEATURE]
        artifact["artifact_sha256"] = m8.payload_sha256(
            {
                key: value
                for key, value in artifact.items()
                if key != "artifact_sha256"
            }
        )
        raw = candidate_predictions(calibration, artifact, 1.0)
        temperature_rows = []
        for temperature in m8.TEMPERATURE_CANDIDATES:
            predictions = {
                recommendation_id: m8.apply_temperature(
                    probabilities,
                    temperature,
                )
                for recommendation_id, probabilities in raw.items()
            }
            metrics = m8.evaluate_predictions(
                calibration,
                predictions,
            )
            temperature_rows.append(
                {
                    "temperature": temperature,
                    "metrics": metrics,
                }
            )
        selected_temperature = min(
            temperature_rows,
            key=lambda row: (
                row["metrics"]["log_loss_3c"],
                row["metrics"]["brier_3c"],
                row["temperature"],
            ),
        )
        candidates.append(
            {
                "ridge": ridge,
                "artifact": artifact,
                "temperature_candidates": temperature_rows,
                "selected_temperature": selected_temperature["temperature"],
                "selected_metrics": selected_temperature["metrics"],
            }
        )
    selected = min(
        candidates,
        key=lambda row: (
            row["selected_metrics"]["log_loss_3c"],
            row["selected_metrics"]["brier_3c"],
            row["ridge"],
        ),
    )
    selected_artifact = selected["artifact"]
    selected_artifact["calibration"] = {
        "method": "multiclass_temperature",
        "temperature": selected["selected_temperature"],
        "selection_partition": "calibration",
        "selection_metric": "log_loss_3c_then_brier_3c",
    }
    selected_artifact["artifact_sha256"] = m8.payload_sha256(
        {
            key: value
            for key, value in selected_artifact.items()
            if key != "artifact_sha256"
        }
    )
    payload = {
        "version": "M6-frozen-candidate-no-H-v0.2",
        "status": "frozen_for_prospective_validation",
        "selection": {
            "development_records": len(development),
            "calibration_records": len(calibration),
            "final_test_records_accessed": 0,
            "removed_feature": REMOVED_FEATURE,
            "reason": "historical_ablation_and_prior_post_M8_rule_decision",
            "ridge_candidates": list(m8.RIDGE_CANDIDATES),
            "temperature_candidates": list(m8.TEMPERATURE_CANDIDATES),
            "selected_ridge": selected["ridge"],
            "selected_temperature": selected["selected_temperature"],
            "selected_calibration_metrics": selected["selected_metrics"],
        },
        "candidate_summaries": [
            {
                "ridge": row["ridge"],
                "artifact_id": row["artifact"]["id"],
                "selected_temperature": row["selected_temperature"],
                "selected_metrics": row["selected_metrics"],
            }
            for row in candidates
        ],
        "coefficient_artifact": selected_artifact,
        "boundaries": {
            "production_authorized": False,
            "production_effect": "none",
            "prospective_validation_required": True,
        },
    }
    return m8.add_payload_hash(payload)


def render_report(payload: dict) -> str:
    selection = payload["selection"]
    metrics = selection["selected_calibration_metrics"]
    artifact = payload["coefficient_artifact"]
    return "\n".join(
        [
            "# Candidato M6 v0.2 sin path H",
            "",
            f"- Desarrollo: {selection['development_records']} casos.",
            f"- Calibracion: {selection['calibration_records']} casos.",
            "- Casos finales usados para elegir: 0.",
            f"- Regla retirada: {selection['removed_feature']}.",
            f"- Ridge elegido: {selection['selected_ridge']}.",
            (
                "- Temperatura elegida: "
                f"{selection['selected_temperature']}."
            ),
            f"- Brier calibracion: {metrics['brier_3c']:.6f}.",
            f"- Log-loss calibracion: {metrics['log_loss_3c']:.6f}.",
            f"- Artefacto: {artifact['id']}.",
            "",
            "Estado: congelado para validacion prospectiva.",
            "Produccion autorizada: no.",
        ]
    )


def main() -> None:
    payload = build_candidate()
    write_json(OUTPUT_PATH, payload)
    REPORT_PATH.write_text(
        render_report(payload) + "\n",
        encoding="utf-8",
    )
    print(render_report(payload))


if __name__ == "__main__":
    main()
