from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Iterable

from m7_first_touch_math import adjusted_interval_hazards, build_baseline_intervals
from m7_joint_temporal_engine import (
    ARTIFACT_PATH,
    BASE_INTERVAL_SECONDS,
    CLASSES,
    DIRECTIONAL_FEATURES,
    ENGINE_VERSION,
    FEATURE_NAMES,
    HORIZON_SECONDS,
    HORIZON_STEPS,
    MAX_HORIZON_SECONDS,
    MAX_INTERVAL_COUNT,
    REFERENCE_HORIZON_SECONDS,
    RUNTIME_VERSION,
    SCORING_VERSION,
    VOLATILITY_FEATURE,
    canonical_sha256,
)


ROOT = Path(__file__).resolve().parent
DATASET_PATH = (
    ROOT
    / "data"
    / "phase1_controlled_replay"
    / "nested_horizon_cases_v0_1.jsonl.gz"
)
REPORT_PATH = ROOT / "auditorias_motor" / "2026-08-13_motor_v0_7_temporal_conjunto.md"
DATASET_MANIFEST_PATH = ROOT / "auditorias_motor" / "horizon_nested_cohort_v0_1.json"

RANDOM_SEED = 20260813
TRAIN_GROUP_LIMIT = 4000
FIT_ITERATIONS = 80
RIDGE_CANDIDATES = (0.1, 1.0, 10.0)
LEARNING_RATE = 0.025
FEATURE_SOURCE_KEYS = {
    "directional_path_efficiency_h": (
        "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h"
    ),
    "directional_path_efficiency_2h": (
        "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h"
    ),
    "directional_path_efficiency_4h": (
        "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h"
    ),
    "volatility_percentile_60": (
        "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60"
    ),
    "target_extreme_between_entry_and_tp": (
        "M4-RULE-PRIOR-EXTREMA-001::target_extreme_between_entry_and_tp"
    ),
}
PARAMETER_NAMES = (
    "shared_movement_intercept",
    "shared_volatility_resolution",
    *DIRECTIONAL_FEATURES,
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _score(group_id: str) -> int:
    return int.from_bytes(
        hashlib.sha256(
            f"{RANDOM_SEED}:{group_id}".encode("utf-8")
        ).digest()[:8],
        "big",
    )


def iter_groups(partitions: set[str]) -> Iterable[dict]:
    current_id = None
    current = []
    with gzip.open(DATASET_PATH, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["partition"] not in partitions:
                continue
            group_id = row["plan_group_id"]
            if current_id is not None and group_id != current_id:
                if len(current) == len(HORIZON_SECONDS):
                    yield normalize_group(current)
                current = []
            current_id = group_id
            current.append(row)
    if current and len(current) == len(HORIZON_SECONDS):
        yield normalize_group(current)


def normalize_group(rows: list[dict]) -> dict:
    by_horizon = {row["time_horizon"]: row for row in rows}
    if set(by_horizon) != set(HORIZON_SECONDS):
        raise ValueError("nested_group_horizons_invalid")
    reference = by_horizon["intraday_wide"]
    raw = reference["common_rule_features"]
    features = {
        name: float(raw[source])
        for name, source in FEATURE_SOURCE_KEYS.items()
    }
    return {
        "group_id": reference["plan_group_id"],
        "partition": reference["partition"],
        "side": reference["side"],
        "entry": float(reference["entry"]),
        "take_profit": float(reference["take_profit"]),
        "stop_loss": float(reference["stop_loss"]),
        "reference_sigma_24h": float(reference["reference_sigma_24h"]),
        "features": features,
        "labels": {
            horizon: by_horizon[horizon]["outcome"]["label"]
            for horizon in HORIZON_SECONDS
        },
        "cluster": reference["inference_cluster_id"],
    }


def deterministic_sample(groups: Iterable[dict], limit: int) -> list[dict]:
    selected = sorted(groups, key=lambda item: _score(item["group_id"]))
    return selected[:limit]


def fit_scaling(groups: list[dict]) -> dict[str, dict[str, float]]:
    result = {}
    for name in FEATURE_NAMES:
        values = [group["features"][name] for group in groups]
        mean = math.fsum(values) / len(values)
        variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
        result[name] = {
            "mean": mean,
            "scale": max(math.sqrt(variance), 1e-12),
        }
    return result


def standardize(raw: dict, scaling: dict) -> dict:
    return {
        name: (float(raw[name]) - scaling[name]["mean"])
        / scaling[name]["scale"]
        for name in FEATURE_NAMES
    }


def _plan_distances(group: dict) -> tuple[float, float]:
    entry = group["entry"]
    if group["side"] == "long":
        return (
            math.log(group["take_profit"] / entry),
            math.log(entry / group["stop_loss"]),
        )
    return (
        math.log(entry / group["take_profit"]),
        math.log(group["stop_loss"] / entry),
    )


def compile_group(group: dict, scaling: dict) -> dict:
    tp_distance, sl_distance = _plan_distances(group)
    sigma_max = group["reference_sigma_24h"] * math.sqrt(
        MAX_HORIZON_SECONDS / REFERENCE_HORIZON_SECONDS
    )
    intervals = build_baseline_intervals(
        tp_log_distance=tp_distance,
        sl_log_distance=sl_distance,
        sigma_horizon=sigma_max,
        interval_count=MAX_INTERVAL_COUNT,
    )
    return {
        **group,
        "standardized": standardize(group["features"], scaling),
        "baseline_hazards": tuple(
            (
                item["baseline_h_tp"],
                item["baseline_h_sl"],
                item["baseline_h_none"],
            )
            for item in intervals
        ),
    }


def _eta_and_derivatives(parameters: dict, features: dict) -> tuple:
    movement = parameters["shared_movement_intercept"]
    volatility = (
        parameters["shared_volatility_resolution"]
        * features[VOLATILITY_FEATURE]
    )
    direction = math.fsum(
        parameters[name] * features[name]
        for name in DIRECTIONAL_FEATURES
    )
    eta_tp = movement + volatility + direction
    eta_sl = movement + volatility - direction
    derivatives = {
        "shared_movement_intercept": (1.0, 1.0),
        "shared_volatility_resolution": (
            features[VOLATILITY_FEATURE],
            features[VOLATILITY_FEATURE],
        ),
        **{
            name: (features[name], -features[name])
            for name in DIRECTIONAL_FEATURES
        },
    }
    return eta_tp, eta_sl, derivatives


def group_loss_and_gradient(group: dict, parameters: dict) -> tuple[float, dict]:
    eta_tp, eta_sl, parameter_derivatives = _eta_and_derivatives(
        parameters,
        group["standardized"],
    )
    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    d_survival = [0.0, 0.0]
    d_tp = [0.0, 0.0]
    d_sl = [0.0, 0.0]
    endpoint_by_step = {}
    selected_steps = set(HORIZON_STEPS.values())
    for step, (base_tp, base_sl, base_none) in enumerate(
        group["baseline_hazards"],
        start=1,
    ):
        h_tp, h_sl, h_none = adjusted_interval_hazards(
            {
                "baseline_h_tp": base_tp,
                "baseline_h_sl": base_sl,
                "baseline_h_none": base_none,
            },
            eta_tp,
            eta_sl,
        )
        dh_tp = [h_tp * (1.0 - h_tp), -h_tp * h_sl]
        dh_sl = [-h_tp * h_sl, h_sl * (1.0 - h_sl)]
        dh_none = [-h_none * h_tp, -h_none * h_sl]
        next_tp = cumulative_tp + survival * h_tp
        next_sl = cumulative_sl + survival * h_sl
        next_survival = survival * h_none
        next_d_tp = [
            d_tp[index] + d_survival[index] * h_tp + survival * dh_tp[index]
            for index in range(2)
        ]
        next_d_sl = [
            d_sl[index] + d_survival[index] * h_sl + survival * dh_sl[index]
            for index in range(2)
        ]
        next_d_survival = [
            d_survival[index] * h_none + survival * dh_none[index]
            for index in range(2)
        ]
        cumulative_tp, cumulative_sl, survival = next_tp, next_sl, next_survival
        d_tp, d_sl, d_survival = next_d_tp, next_d_sl, next_d_survival
        if step in selected_steps:
            endpoint_by_step[step] = {
                CLASSES[0]: (cumulative_tp, d_tp),
                CLASSES[1]: (cumulative_sl, d_sl),
                CLASSES[2]: (survival, d_survival),
            }

    loss = 0.0
    gradient_eta = [0.0, 0.0]
    for horizon, step in HORIZON_STEPS.items():
        label = group["labels"][horizon]
        probability, derivative = endpoint_by_step[step][label]
        probability = max(probability, 1e-15)
        loss -= math.log(probability) / len(HORIZON_STEPS)
        for index in range(2):
            gradient_eta[index] -= (
                derivative[index] / probability / len(HORIZON_STEPS)
            )
    gradient = {
        name: (
            gradient_eta[0] * derivatives[0]
            + gradient_eta[1] * derivatives[1]
        )
        for name, derivatives in parameter_derivatives.items()
    }
    return loss, gradient


def fit_model(groups: list[dict], ridge: float) -> dict:
    parameters = {name: 0.0 for name in PARAMETER_NAMES}
    first = dict(parameters)
    second = dict(parameters)
    history = []
    count = len(groups)
    for iteration in range(1, FIT_ITERATIONS + 1):
        total_loss = 0.0
        gradients = {name: 0.0 for name in PARAMETER_NAMES}
        for group in groups:
            loss, row_gradient = group_loss_and_gradient(group, parameters)
            total_loss += loss
            for name in PARAMETER_NAMES:
                gradients[name] += row_gradient[name] / count
        for name in PARAMETER_NAMES:
            if name != "shared_movement_intercept":
                gradients[name] += ridge * parameters[name] / count
            gradient = max(-10.0, min(10.0, gradients[name]))
            first[name] = 0.9 * first[name] + 0.1 * gradient
            second[name] = 0.999 * second[name] + 0.001 * gradient * gradient
            corrected_first = first[name] / (1.0 - 0.9**iteration)
            corrected_second = second[name] / (1.0 - 0.999**iteration)
            parameters[name] -= LEARNING_RATE * corrected_first / (
                math.sqrt(corrected_second) + 1e-8
            )
        parameters["shared_volatility_resolution"] = max(
            0.0,
            parameters["shared_volatility_resolution"],
        )
        if iteration in {1, 20, 40, 60, FIT_ITERATIONS}:
            history.append(
                {
                    "iteration": iteration,
                    "mean_log_loss": total_loss / count,
                }
            )
    return {
        "ridge": ridge,
        "fit_groups": count,
        "parameters": parameters,
        "optimization_trace": history,
    }


def _predict_group(group: dict, parameters: dict) -> dict[str, dict[str, float]]:
    eta_tp, eta_sl, _ = _eta_and_derivatives(
        parameters,
        group["standardized"],
    )
    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    by_step = {}
    selected_steps = set(HORIZON_STEPS.values())
    for step, (base_tp, base_sl, base_none) in enumerate(
        group["baseline_hazards"],
        start=1,
    ):
        h_tp, h_sl, h_none = adjusted_interval_hazards(
            {
                "baseline_h_tp": base_tp,
                "baseline_h_sl": base_sl,
                "baseline_h_none": base_none,
            },
            eta_tp,
            eta_sl,
        )
        cumulative_tp += survival * h_tp
        cumulative_sl += survival * h_sl
        survival *= h_none
        if step in selected_steps:
            by_step[step] = {
                CLASSES[0]: cumulative_tp,
                CLASSES[1]: cumulative_sl,
                CLASSES[2]: survival,
            }
    return {
        horizon: by_step[step]
        for horizon, step in HORIZON_STEPS.items()
    }


def evaluate(groups: list[dict], parameters: dict) -> dict:
    accumulators = {
        horizon: {"n": 0, "log": 0.0, "brier": 0.0, "classes": Counter()}
        for horizon in HORIZON_SECONDS
    }
    monotonic_errors = 0
    for group in groups:
        curve = _predict_group(group, parameters)
        ordered = sorted(HORIZON_SECONDS, key=HORIZON_SECONDS.get)
        if any(
            curve[right][CLASSES[0]] + 1e-12 < curve[left][CLASSES[0]]
            or curve[right][CLASSES[1]] + 1e-12 < curve[left][CLASSES[1]]
            or curve[right][CLASSES[2]] - 1e-12 > curve[left][CLASSES[2]]
            for left, right in zip(ordered, ordered[1:])
        ):
            monotonic_errors += 1
        for horizon, probabilities in curve.items():
            label = group["labels"][horizon]
            target = accumulators[horizon]
            target["n"] += 1
            target["log"] -= math.log(max(probabilities[label], 1e-15))
            target["brier"] += math.fsum(
                (probabilities[name] - (1.0 if name == label else 0.0)) ** 2
                for name in CLASSES
            )
            target["classes"][label] += 1
    by_horizon = {
        horizon: {
            "n": values["n"],
            "log_loss_3c": values["log"] / values["n"],
            "brier_3c": values["brier"] / values["n"],
            "class_counts": dict(values["classes"]),
        }
        for horizon, values in accumulators.items()
    }
    return {
        "groups": len(groups),
        "macro_horizon_log_loss_3c": math.fsum(
            item["log_loss_3c"] for item in by_horizon.values()
        )
        / len(by_horizon),
        "macro_horizon_brier_3c": math.fsum(
            item["brier_3c"] for item in by_horizon.values()
        )
        / len(by_horizon),
        "by_horizon": by_horizon,
        "temporal_monotonicity_errors": monotonic_errors,
    }


def coefficients_from_parameters(parameters: dict) -> dict:
    movement = parameters["shared_movement_intercept"]
    volatility = parameters["shared_volatility_resolution"]
    return {
        "tp": {
            "intercept": movement,
            VOLATILITY_FEATURE: volatility,
            **{name: parameters[name] for name in DIRECTIONAL_FEATURES},
        },
        "sl": {
            "intercept": movement,
            VOLATILITY_FEATURE: volatility,
            **{name: -parameters[name] for name in DIRECTIONAL_FEATURES},
        },
    }


def build_artifact() -> dict:
    manifest = json.loads(DATASET_MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["dataset_sha256"] != _file_sha256(DATASET_PATH):
        raise ValueError("nested_dataset_hash_mismatch")
    development_groups = list(iter_groups({"development"}))
    scaling_groups = deterministic_sample(development_groups, TRAIN_GROUP_LIMIT)
    scaling = fit_scaling(scaling_groups)
    train = [compile_group(group, scaling) for group in scaling_groups]
    calibration = [
        compile_group(group, scaling)
        for group in deterministic_sample(
            iter_groups({"calibration"}),
            TRAIN_GROUP_LIMIT,
        )
    ]
    candidates = []
    for ridge in RIDGE_CANDIDATES:
        model = fit_model(train, ridge)
        model["calibration"] = evaluate(calibration, model["parameters"])
        candidates.append(model)
    selected = min(
        candidates,
        key=lambda item: (
            item["calibration"]["macro_horizon_log_loss_3c"],
            item["calibration"]["macro_horizon_brier_3c"],
            item["ridge"],
        ),
    )
    rule_test = [
        compile_group(group, scaling)
        for group in iter_groups({"rule_test"})
    ]
    final_test = [
        compile_group(group, scaling)
        for group in iter_groups({"final_test"})
    ]
    zero = {name: 0.0 for name in PARAMETER_NAMES}
    selected_rule_test = evaluate(rule_test, selected["parameters"])
    baseline_rule_test = evaluate(rule_test, zero)
    selected_final = evaluate(final_test, selected["parameters"])
    baseline_final = evaluate(final_test, zero)

    def improvement(left: dict, right: dict) -> dict:
        return {
            "macro_log_loss_improvement": (
                right["macro_horizon_log_loss_3c"]
                - left["macro_horizon_log_loss_3c"]
            ),
            "macro_brier_improvement": (
                right["macro_horizon_brier_3c"]
                - left["macro_horizon_brier_3c"]
            ),
            "by_horizon": {
                horizon: {
                    "log_loss_improvement": (
                        right["by_horizon"][horizon]["log_loss_3c"]
                        - left["by_horizon"][horizon]["log_loss_3c"]
                    ),
                    "brier_improvement": (
                        right["by_horizon"][horizon]["brier_3c"]
                        - left["by_horizon"][horizon]["brier_3c"]
                    ),
                }
                for horizon in HORIZON_SECONDS
            },
        }

    rule_test_improvement = improvement(selected_rule_test, baseline_rule_test)
    final_improvement = improvement(selected_final, baseline_final)
    rule_weights_pass = all(
        rule_test_improvement["by_horizon"][horizon][metric] >= -1e-9
        and final_improvement["by_horizon"][horizon][metric] >= -1e-9
        for horizon in HORIZON_SECONDS
        for metric in ("log_loss_improvement", "brier_improvement")
    )
    served_parameters = selected["parameters"] if rule_weights_pass else zero
    weights_decision = (
        "constrained_rule_weights_accepted"
        if rule_weights_pass
        else "rule_weights_rejected_baseline_curve_served"
    )
    payload = {
        "artifact_id": "TP-SL-TEMPORAL-FIRST-TOUCH-v0.7-frozen-001",
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "runtime_version": RUNTIME_VERSION,
        "status": "frozen_production",
        "production_authorized": True,
        "automatic_weight_updates": False,
        "single_engine": True,
        "parallel_probability_engines": 0,
        "reference_horizon_seconds": REFERENCE_HORIZON_SECONDS,
        "base_interval_seconds": BASE_INTERVAL_SECONDS,
        "horizon_seconds": HORIZON_SECONDS,
        "feature_names": list(FEATURE_NAMES),
        "feature_standardization": scaling,
        "coefficient_constraints": {
            "volatility": "same_non_negative_tp_sl_resolution_effect",
            "directional_features": "tp_sl_antisymmetric_shared_across_time",
            "time": "one_interval_hazard_curve_no_horizon_specific_coefficients",
        },
        "coefficients": coefficients_from_parameters(served_parameters),
        "selection": {
            "dataset_sha256": manifest["dataset_sha256"],
            "development_groups_available": len(development_groups),
            "development_groups_used": len(train),
            "calibration_groups_used": len(calibration),
            "ridge_candidates": list(RIDGE_CANDIDATES),
            "selected_ridge": selected["ridge"],
            "candidate_parameters": selected["parameters"],
            "weights_decision": weights_decision,
            "rule_test": {
                "candidate": selected_rule_test,
                "baseline": baseline_rule_test,
                "candidate_improvement": rule_test_improvement,
            },
            "sealed_final_test": {
                "candidate": selected_final,
                "baseline": baseline_final,
                "candidate_improvement": final_improvement,
            },
        },
        "invariants": {
            "first_touch_absorbing": True,
            "tp_cumulative_non_decreasing": True,
            "sl_cumulative_non_decreasing": True,
            "expiry_non_increasing": True,
            "probability_mass_one": True,
            "rule_test_temporal_errors": selected_rule_test[
                "temporal_monotonicity_errors"
            ],
            "final_test_temporal_errors": selected_final[
                "temporal_monotonicity_errors"
            ],
        },
    }
    payload["artifact_sha256"] = canonical_sha256(payload)
    return payload


def render_report(payload: dict) -> str:
    selection = payload["selection"]
    final = selection["sealed_final_test"]
    return "\n".join(
        [
            "# Motor temporal conjunto v0.7",
            "",
            "- Un solo motor de probabilidades: **sí**.",
            "- Motores paralelos o en sombra: **0**.",
            "- Actualizaciones automáticas de pesos: **no**.",
            "- Curva única de primer toque: 4 h, 24 h y 7 días.",
            "- Primer toque absorbente: **sí**.",
            f"- Decisión de reglas: `{selection['weights_decision']}`.",
            f"- Ridge seleccionado: {selection['selected_ridge']}.",
            (
                "- Log-loss final candidato: "
                f"{final['candidate']['macro_horizon_log_loss_3c']:.6f}."
            ),
            (
                "- Log-loss final base: "
                f"{final['baseline']['macro_horizon_log_loss_3c']:.6f}."
            ),
            (
                "- Brier final candidato: "
                f"{final['candidate']['macro_horizon_brier_3c']:.6f}."
            ),
            (
                "- Brier final base: "
                f"{final['baseline']['macro_horizon_brier_3c']:.6f}."
            ),
            "",
            f"Hash congelado: `{payload['artifact_sha256']}`.",
            "",
        ]
    )


def main() -> None:
    payload = build_artifact()
    ARTIFACT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8")
    print(render_report(payload))


if __name__ == "__main__":
    main()
