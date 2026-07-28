from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import m8_evaluation as m8
from m6_remediated_competing_risks import apply_competing_risk_evidence
from run_m8_evaluation import enrich_outcomes, fetch_legacy


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
FINAL_PATH = AUDIT_DIR / "dataset_final_sellado_m8_3_v0_1.json"
MODEL_PATH = AUDIT_DIR / "modelo_estimado_calibrado_m8_5_v0_1.json"
FROZEN_CANDIDATE_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
OUTPUT_PATH = AUDIT_DIR / "comparacion_directa_motor_antiguo_nuevo_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-07-28_comparacion_directa_motor_antiguo_nuevo.md"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def repaired_candidate_predictions(
    rows: list[dict],
    artifact: dict,
    *,
    temperature: float,
    ablate_feature: str | None = None,
) -> dict[int, dict]:
    candidate = json.loads(json.dumps(artifact))
    if ablate_feature is not None:
        candidate["coefficients"]["tp"][ablate_feature] = 0.0
        candidate["coefficients"]["sl"][ablate_feature] = 0.0
    predictions = {}
    scaling = artifact["feature_standardization"]
    for row in rows:
        direction = 1 if row["side"] == "long" else -1
        features = m8.standardized_features(row, scaling)
        result = apply_competing_risk_evidence(
            tp_log_distance=direction
            * math.log(row["take_profit"] / row["entry"]),
            sl_log_distance=-direction
            * math.log(row["stop_loss"] / row["entry"]),
            sigma_horizon=row["pretrade"]["sigma_horizon"],
            interval_count=24,
            features=features,
            coefficient_artifact=candidate,
        )
        predictions[row["recommendation_id"]] = m8.apply_temperature(
            {
                m8.CLASSES[0]: result.p_tp,
                m8.CLASSES[1]: result.p_sl,
                m8.CLASSES[2]: result.p_expiry,
            },
            temperature,
        )
    return predictions


def top_class_accuracy(rows: list[dict], predictions: dict[int, dict]) -> dict:
    correct = 0
    for row in rows:
        predicted = max(
            predictions[row["recommendation_id"]],
            key=predictions[row["recommendation_id"]].get,
        )
        correct += predicted == row["outcome"]["label"]
    return {
        "correct": correct,
        "total": len(rows),
        "accuracy": correct / len(rows) if rows else None,
    }


def actual_class_probability(
    row: dict,
    predictions: dict[int, dict],
) -> float:
    return predictions[row["recommendation_id"]][row["outcome"]["label"]]


def build_comparison() -> dict:
    final = read_json(FINAL_PATH)
    model = read_json(MODEL_PATH)
    frozen_candidate = read_json(FROZEN_CANDIDATE_PATH)
    captured_at = datetime.now(timezone.utc)
    rows = enrich_outcomes(
        [dict(row) for row in final["records"]],
        captured_at=captured_at,
    )
    labeled = m8.eligible_labeled_rows(rows)
    artifact = frozen_candidate["coefficient_artifact"]
    temperature = float(artifact["calibration"]["temperature"])

    candidate = repaired_candidate_predictions(
        labeled,
        artifact,
        temperature=temperature,
    )
    diagnostic_no_h = repaired_candidate_predictions(
        labeled,
        artifact,
        temperature=temperature,
        ablate_feature="directional_path_efficiency_h",
    )
    baseline = m8.baseline_predictions(labeled)
    legacy_all = fetch_legacy(labeled)
    common = [
        row
        for row in labeled
        if row["recommendation_id"] in legacy_all
    ]
    legacy = {
        row["recommendation_id"]: legacy_all[row["recommendation_id"]]
        for row in common
    }
    candidate_common = {
        row["recommendation_id"]: candidate[row["recommendation_id"]]
        for row in common
    }
    baseline_common = {
        row["recommendation_id"]: baseline[row["recommendation_id"]]
        for row in common
    }
    no_h_common = {
        row["recommendation_id"]: diagnostic_no_h[
            row["recommendation_id"]
        ]
        for row in common
    }

    cases = []
    candidate_wins = 0
    legacy_wins = 0
    ties = 0
    for row in common:
        candidate_actual = actual_class_probability(row, candidate_common)
        legacy_actual = actual_class_probability(row, legacy)
        if candidate_actual > legacy_actual:
            candidate_wins += 1
            comparison = "new"
        elif legacy_actual > candidate_actual:
            legacy_wins += 1
            comparison = "old"
        else:
            ties += 1
            comparison = "tie"
        cases.append(
            {
                "recommendation_id": row["recommendation_id"],
                "operation_id": row.get("operation_id"),
                "symbol": row["symbol"],
                "side": row["side"],
                "time_horizon": row["time_horizon"],
                "horizon_status": row["horizon_status"],
                "actual_outcome": row["outcome"]["label"],
                "old_engine": legacy[row["recommendation_id"]],
                "new_baseline": baseline_common[row["recommendation_id"]],
                "new_candidate": candidate_common[row["recommendation_id"]],
                "diagnostic_candidate_without_h": no_h_common[
                    row["recommendation_id"]
                ],
                "actual_outcome_probability": {
                    "old_engine": legacy_actual,
                    "new_candidate": candidate_actual,
                },
                "higher_probability_for_actual_outcome": comparison,
            }
        )

    candidate_metrics = m8.evaluate_predictions(common, candidate_common)
    legacy_metrics = m8.evaluate_predictions(common, legacy)
    baseline_metrics = m8.evaluate_predictions(common, baseline_common)
    no_h_metrics = m8.evaluate_predictions(common, no_h_common)
    paired = m8.bootstrap_paired_differences(
        common,
        candidate_common,
        legacy,
    )
    brier_improvement = (
        legacy_metrics["brier_3c"] - candidate_metrics["brier_3c"]
    )
    log_loss_improvement = (
        legacy_metrics["log_loss_3c"]
        - candidate_metrics["log_loss_3c"]
    )
    payload = {
        "version": "direct-old-vs-repaired-new-v0.1",
        "captured_at": captured_at.isoformat(),
        "scope": {
            "sealed_final_records": len(rows),
            "resolved_records": len(labeled),
            "directly_comparable_records": len(common),
            "formal_exact_horizon_records": sum(
                bool(row["formal_eligible_horizon"]) for row in common
            ),
            "policy_reconstructed_horizon_records": sum(
                not bool(row["formal_eligible_horizon"]) for row in common
            ),
        },
        "engines": {
            "old": "stored_legacy_probabilities",
            "new_baseline": "M6-R1-remediated-zero-coefficient-baseline",
            "new_candidate": artifact["id"],
            "new_candidate_version": frozen_candidate["version"],
            "temperature": temperature,
        },
        "metrics": {
            "old_engine": legacy_metrics,
            "new_baseline": baseline_metrics,
            "new_candidate": candidate_metrics,
            "diagnostic_candidate_without_h_no_refit": no_h_metrics,
            "top_class_accuracy": {
                "old_engine": top_class_accuracy(common, legacy),
                "new_baseline": top_class_accuracy(common, baseline_common),
                "new_candidate": top_class_accuracy(common, candidate_common),
            },
            "new_candidate_improvement": {
                "brier_reduction": brier_improvement,
                "brier_reduction_pct": (
                    brier_improvement / legacy_metrics["brier_3c"] * 100
                ),
                "log_loss_reduction": log_loss_improvement,
                "log_loss_reduction_pct": (
                    log_loss_improvement
                    / legacy_metrics["log_loss_3c"]
                    * 100
                ),
                "cases_higher_probability_for_actual_outcome": {
                    "new": candidate_wins,
                    "old": legacy_wins,
                    "ties": ties,
                },
                "paired_bootstrap": paired,
            },
        },
        "cases": cases,
        "decision": {
            "historical_result": (
                "new_candidate_better_than_old"
                if brier_improvement > 0 and log_loss_improvement > 0
                else "new_candidate_not_better_than_old"
            ),
            "production_authorized": False,
            "reason": (
                "Only one comparison record stored its exact horizon before "
                "the outcome; the other horizons are retrospective policy."
            ),
        },
        "production_effect": "none",
    }
    return m8.add_payload_hash(payload)


def render_report(payload: dict) -> str:
    scope = payload["scope"]
    metrics = payload["metrics"]
    old = metrics["old_engine"]
    new = metrics["new_candidate"]
    accuracy = metrics["top_class_accuracy"]
    improvement = metrics["new_candidate_improvement"]
    wins = improvement["cases_higher_probability_for_actual_outcome"]
    return "\n".join(
        [
            "# Comparacion directa: motor antiguo frente a motor nuevo",
            "",
            f"- Casos cerrados comparados: {scope['directly_comparable_records']}.",
            f"- Brier antiguo: {old['brier_3c']:.6f}.",
            f"- Brier nuevo: {new['brier_3c']:.6f}.",
            (
                "- Reduccion del error Brier: "
                f"{improvement['brier_reduction_pct']:.2f}%."
            ),
            f"- Log-loss antiguo: {old['log_loss_3c']:.6f}.",
            f"- Log-loss nuevo: {new['log_loss_3c']:.6f}.",
            (
                "- Reduccion del log-loss: "
                f"{improvement['log_loss_reduction_pct']:.2f}%."
            ),
            (
                "- Aciertos de clase principal antiguo: "
                f"{accuracy['old_engine']['correct']}/"
                f"{accuracy['old_engine']['total']}."
            ),
            (
                "- Aciertos de clase principal nuevo: "
                f"{accuracy['new_candidate']['correct']}/"
                f"{accuracy['new_candidate']['total']}."
            ),
            (
                "- Mayor probabilidad al resultado real: "
                f"nuevo {wins['new']}, antiguo {wins['old']}, "
                f"empates {wins['ties']}."
            ),
            (
                "- Horizontes exactos preoperacion: "
                f"{scope['formal_exact_horizon_records']}."
            ),
            "",
            f"Resultado: {payload['decision']['historical_result']}.",
            "Produccion autorizada: no.",
        ]
    )


def main() -> None:
    payload = build_comparison()
    write_json(OUTPUT_PATH, payload)
    REPORT_PATH.write_text(
        render_report(payload) + "\n",
        encoding="utf-8",
    )
    print(render_report(payload))


if __name__ == "__main__":
    main()
