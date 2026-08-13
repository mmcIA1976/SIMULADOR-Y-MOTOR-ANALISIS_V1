from __future__ import annotations

import gzip
import hashlib
import heapq
import json
import math
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from m5_input_assembly import _closed_material
from multiscale_feature_runtime import (
    FLAT_FEATURE_NAMES,
    STAGE_ORDER,
    STAGE_PROFILES,
)
from sequential_first_touch_math import double_barrier_first_touch
from nested_horizon_evaluation import NESTED_DATASET_PATH
from phase1_controlled_replay import (
    SYMBOLS,
    aggregate_candles,
    read_symbol_5m,
)


ROOT = Path(__file__).resolve().parent
DATASET_PATH = (
    ROOT
    / "data"
    / "phase1_controlled_replay"
    / "sequential_multiscale_cases_v0_1.jsonl.gz"
)
MANIFEST_PATH = ROOT / "auditorias_motor" / "sequential_multiscale_cohort_v0_1.json"
ARTIFACT_PATH = ROOT / "auditorias_motor" / "motor_v0_8_sequential_multiscale.json"
RESULT_PATH = ROOT / "auditorias_motor" / "sequential_multiscale_evaluation_v0_1.json"
REPORT_PATH = ROOT / "auditorias_motor" / "2026-08-13_motor_secuencial_multiescala.md"

ENGINE_VERSION = "TP-SL-SEQUENTIAL-MULTISCALE-v0.8"
SCORING_VERSION = "sequential-conditional-first-touch-frozen-v0.8"
DATASET_VERSION = "sequential-multiscale-cohort-v0.1"
EVALUATION_VERSION = "sequential-multiscale-evaluation-v0.1"
CLASSES = (
    "tp_first_in_stage",
    "sl_first_in_stage",
    "survive_stage",
)
CUMULATIVE_CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)
PARTITIONS = ("development", "calibration", "rule_test", "final_test")
RIDGE_CANDIDATES = (0.1, 1.0, 10.0)
FIT_CASE_LIMIT = 8_000
EVALUATION_CASE_LIMIT = 20_000
FIT_ITERATIONS = 60
RANDOM_SEED = 20260813
BOOTSTRAP_SAMPLES = 1_000


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_hash(payload: dict) -> dict:
    result = dict(payload)
    result["canonical_payload_sha256"] = canonical_sha256(result)
    return result


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _row_plan(row: dict, time_horizon: str) -> dict:
    profile = STAGE_PROFILES[time_horizon]
    return {
        "symbol": row["symbol"],
        "side": row["side"],
        "entry": float(row["entry"]),
        "take_profit": float(row["take_profit"]),
        "stop_loss": float(row["stop_loss"]),
        "entry_type": "market",
        "margin": 100.0,
        "leverage": 1.0,
        "time_horizon": time_horizon,
        "horizon_seconds": int(profile["horizon_seconds"]),
        "analysis_at": row["analysis_at"],
    }


def _anchor_sigmas(symbol: str, cutoffs: set[int]) -> dict[tuple[int, str], dict]:
    base = read_symbol_5m(symbol)
    result: dict[tuple[int, str], dict] = {}
    for horizon in STAGE_ORDER:
        profile = STAGE_PROFILES[horizon]
        candles = aggregate_candles(base, int(profile["interval_seconds"]))
        indexes = {
            int(row["close_time_ms"]): index for index, row in enumerate(candles)
        }
        for cutoff in sorted(cutoffs):
            index = indexes.get(cutoff)
            if index is None:
                continue
            shell = {
                "symbol": symbol,
                "side": "long",
                "entry": float(candles[index]["close"]),
                "take_profit": float(candles[index]["close"]) * 1.01,
                "stop_loss": float(candles[index]["close"]) * 0.99,
                "entry_type": "market",
                "margin": 100.0,
                "leverage": 1.0,
                "time_horizon": horizon,
                "horizon_seconds": int(profile["horizon_seconds"]),
                "analysis_at": datetime.fromtimestamp(
                    cutoff / 1000, tz=timezone.utc
                ).isoformat(),
            }
            return_count = int(profile["horizon_seconds"]) // int(
                profile["interval_seconds"]
            )
            required = 61 * return_count
            if index < required:
                continue
            try:
                material = _closed_material(
                    shell,
                    candles[index - required : index + 1],
                )
            except (KeyError, ValueError, ArithmeticError):
                continue
            variance = float(material["current_variance"])
            if not math.isfinite(variance) or variance <= 0:
                continue
            result[(cutoff, horizon)] = {
                "context_sigma": math.sqrt(variance),
                "interval": profile["interval"],
                "interval_seconds": int(profile["interval_seconds"]),
                "source_data_sha256": material["data_sha256"],
                "data_cutoff_at_ms": int(material["data_cutoff_at_ms"]),
            }
    return result


def build_dataset() -> dict:
    anchors_by_symbol: dict[str, set[int]] = {symbol: set() for symbol in SYMBOLS}
    with gzip.open(NESTED_DATASET_PATH, "rt", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            symbol = str(row["symbol"])
            cutoff = int(str(row["anchor_id"]).rsplit(":", 1)[1])
            anchors_by_symbol.setdefault(symbol, set()).add(cutoff)

    sigma_maps = {
        symbol: _anchor_sigmas(symbol, anchors_by_symbol[symbol])
        for symbol in SYMBOLS
    }
    counters: Counter = Counter()
    by_partition: Counter = Counter()
    by_horizon: Counter = Counter()
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(NESTED_DATASET_PATH, "rt", encoding="utf-8") as source, gzip.open(
        DATASET_PATH, "wt", encoding="utf-8", newline="\n"
    ) as output:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            cutoff = int(str(row["anchor_id"]).rsplit(":", 1)[1])
            horizon = str(row["time_horizon"])
            context = sigma_maps[str(row["symbol"])].get((cutoff, horizon))
            if context is None:
                counters["missing_multiscale_context"] += 1
                continue
            record = {
                **row,
                "version": DATASET_VERSION,
                "multiscale_context": context,
            }
            output.write(canonical_json(record) + "\n")
            counters["cases"] += 1
            by_partition[row["partition"]] += 1
            by_horizon[horizon] += 1
    if counters["cases"] % len(STAGE_ORDER) != 0:
        raise RuntimeError("sequential_dataset_group_count_invalid")
    manifest = add_hash(
        {
            "version": DATASET_VERSION,
            "source_nested_dataset_sha256": sha256_file(NESTED_DATASET_PATH),
            "dataset_path": str(DATASET_PATH.relative_to(ROOT)),
            "dataset_sha256": sha256_file(DATASET_PATH),
            "cases": counters["cases"],
            "plan_groups": counters["cases"] // len(STAGE_ORDER),
            "cases_by_partition": dict(by_partition),
            "cases_by_horizon": dict(by_horizon),
            "blocked": {
                key: value for key, value in counters.items() if key != "cases"
            },
            "stage_contract": {
                horizon: dict(STAGE_PROFILES[horizon]) for horizon in STAGE_ORDER
            },
            "same_plan_across_stages": True,
            "past_data_only": True,
            "first_touch_nested": True,
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(MANIFEST_PATH, manifest)
    return manifest


def iter_groups() -> Iterable[dict[str, dict]]:
    current_id = None
    rows: dict[str, dict] = {}
    with gzip.open(DATASET_PATH, "rt", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            group_id = str(row["plan_group_id"])
            if current_id is not None and group_id != current_id:
                if set(rows) != set(STAGE_ORDER):
                    raise ValueError("sequential_dataset_incomplete_group")
                yield rows
                rows = {}
            current_id = group_id
            rows[str(row["time_horizon"])] = row
    if rows:
        if set(rows) != set(STAGE_ORDER):
            raise ValueError("sequential_dataset_incomplete_group")
        yield rows


def _log_distances(row: dict) -> tuple[float, float]:
    side = str(row["side"]).lower()
    entry = float(row["entry"])
    tp = float(row["take_profit"])
    sl = float(row["stop_loss"])
    if side == "long":
        return math.log(tp / entry), math.log(entry / sl)
    return math.log(entry / tp), math.log(sl / entry)


def _cumulative_baseline(rows: dict[str, dict]) -> dict[str, dict[str, float]]:
    reference = rows[STAGE_ORDER[0]]
    tp_distance, sl_distance = _log_distances(reference)
    cumulative_variance = 0.0
    curve = {}
    for horizon in STAGE_ORDER:
        profile = STAGE_PROFILES[horizon]
        sigma = float(rows[horizon]["multiscale_context"]["context_sigma"])
        fraction = float(profile["increment_seconds"]) / float(
            profile["horizon_seconds"]
        )
        cumulative_variance += sigma * sigma * fraction
        result = double_barrier_first_touch(
            tp_log_distance=tp_distance,
            sl_log_distance=sl_distance,
            sigma_horizon=math.sqrt(cumulative_variance),
            time_fraction=1.0,
        )
        curve[horizon] = {
            CUMULATIVE_CLASSES[0]: result.p_tp,
            CUMULATIVE_CLASSES[1]: result.p_sl,
            CUMULATIVE_CLASSES[2]: result.p_expiry,
        }
    return curve


def _conditional_baseline(curve: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    previous_tp = 0.0
    previous_sl = 0.0
    previous_survival = 1.0
    stages = {}
    for horizon in STAGE_ORDER:
        current = curve[horizon]
        if previous_survival <= 1e-12:
            hazards = {CLASSES[0]: 0.0, CLASSES[1]: 0.0, CLASSES[2]: 1.0}
        else:
            hazards = {
                CLASSES[0]: max(
                    0.0,
                    current[CUMULATIVE_CLASSES[0]] - previous_tp,
                )
                / previous_survival,
                CLASSES[1]: max(
                    0.0,
                    current[CUMULATIVE_CLASSES[1]] - previous_sl,
                )
                / previous_survival,
                CLASSES[2]: max(0.0, current[CUMULATIVE_CLASSES[2]])
                / previous_survival,
            }
            total = math.fsum(hazards.values())
            hazards = {name: value / total for name, value in hazards.items()}
        stages[horizon] = hazards
        previous_tp = current[CUMULATIVE_CLASSES[0]]
        previous_sl = current[CUMULATIVE_CLASSES[1]]
        previous_survival = current[CUMULATIVE_CLASSES[2]]
    return stages


def _stage_labels(rows: dict[str, dict]) -> dict[str, str | None]:
    labels: dict[str, str | None] = {}
    at_risk = True
    for horizon in STAGE_ORDER:
        cumulative = rows[horizon]["outcome"]["label"]
        if not at_risk:
            labels[horizon] = None
            continue
        if cumulative == CUMULATIVE_CLASSES[0]:
            labels[horizon] = CLASSES[0]
            at_risk = False
        elif cumulative == CUMULATIVE_CLASSES[1]:
            labels[horizon] = CLASSES[1]
            at_risk = False
        else:
            labels[horizon] = CLASSES[2]
    return labels


def _raw_features(rows: dict[str, dict], stage_index: int) -> dict[str, float]:
    horizon = STAGE_ORDER[stage_index]
    tp_distance, sl_distance = _log_distances(rows[horizon])
    sigma = float(rows[horizon]["multiscale_context"]["context_sigma"])
    result = {
        "intercept": 1.0,
        "geometry::tp_sigma_units": tp_distance / sigma,
        "geometry::sl_sigma_units": sl_distance / sigma,
        "geometry::log_tp_sl_ratio": math.log(tp_distance / sl_distance),
        "geometry::log_context_sigma": math.log(sigma),
    }
    for inherited in STAGE_ORDER[: stage_index + 1]:
        values = rows[inherited]["horizon_rule_features"]
        for name in FLAT_FEATURE_NAMES:
            result[f"{inherited}::{name}"] = float(values[name])
        inherited_sigma = float(
            rows[inherited]["multiscale_context"]["context_sigma"]
        )
        result[f"{inherited}::context_sigma"] = inherited_sigma
    return result


def _sample(
    partitions: set[str],
    stage_index: int,
    limit: int,
    *,
    seed_suffix: str,
) -> list[dict]:
    horizon = STAGE_ORDER[stage_index]
    heap: list[tuple[int, str, dict]] = []
    for rows in iter_groups():
        row = rows[horizon]
        if row["partition"] not in partitions:
            continue
        label = _stage_labels(rows)[horizon]
        if label is None:
            continue
        base = _conditional_baseline(_cumulative_baseline(rows))[horizon]
        record = {
            "group_id": row["plan_group_id"],
            "partition": row["partition"],
            "inference_cluster_id": row["inference_cluster_id"],
            "label": label,
            "base": base,
            "features": _raw_features(rows, stage_index),
        }
        digest = hashlib.sha256(
            f"{RANDOM_SEED}:{seed_suffix}:{record['group_id']}".encode("utf-8")
        ).digest()
        score = int.from_bytes(digest[:8], "big")
        item = (-score, str(record["group_id"]), record)
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    return [item[2] for item in sorted(heap, reverse=True)]


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def fit_scaling(rows: list[dict]) -> dict[str, dict[str, float]]:
    names = tuple(rows[0]["features"])
    result = {}
    for name in names:
        if name == "intercept":
            continue
        values = [float(row["features"][name]) for row in rows]
        mean = _mean(values)
        variance = _mean([(value - mean) ** 2 for value in values])
        result[name] = {"mean": mean, "scale": max(math.sqrt(variance), 1e-12)}
    return result


def standardized_features(
    raw: dict[str, float], scaling: dict[str, dict[str, float]]
) -> dict[str, float]:
    return {
        name: (
            float(value)
            if name == "intercept"
            else (float(value) - scaling[name]["mean"]) / scaling[name]["scale"]
        )
        for name, value in raw.items()
    }


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    maximum = max(logits.values())
    values = {name: math.exp(value - maximum) for name, value in logits.items()}
    total = math.fsum(values.values())
    return {name: value / total for name, value in values.items()}


def predict(model: dict, row: dict) -> dict[str, float]:
    if not model.get("enabled", True):
        return dict(row["base"])
    features = standardized_features(row["features"], model["scaling"])
    logits = {name: math.log(max(float(row["base"][name]), 1e-15)) for name in CLASSES}
    for cause in CLASSES[:2]:
        logits[cause] += math.fsum(
            float(model["coefficients"][cause].get(name, 0.0)) * value
            for name, value in features.items()
        )
    return _softmax(logits)


def fit_model(rows: list[dict], ridge: float, scaling: dict) -> dict:
    compiled = [
        (
            row["base"],
            row["label"],
            standardized_features(row["features"], scaling),
        )
        for row in rows
    ]
    names = tuple(compiled[0][2])
    coefficients = {cause: {name: 0.0 for name in names} for cause in CLASSES[:2]}
    first = {cause: {name: 0.0 for name in names} for cause in CLASSES[:2]}
    second = {cause: {name: 0.0 for name in names} for cause in CLASSES[:2]}
    count = len(compiled)
    for iteration in range(1, FIT_ITERATIONS + 1):
        gradients = {cause: {name: 0.0 for name in names} for cause in CLASSES[:2]}
        for base, label, features in compiled:
            logits = {name: math.log(max(float(base[name]), 1e-15)) for name in CLASSES}
            for cause in CLASSES[:2]:
                logits[cause] += math.fsum(
                    coefficients[cause][name] * value
                    for name, value in features.items()
                )
            probabilities = _softmax(logits)
            for cause in CLASSES[:2]:
                residual = probabilities[cause] - (1.0 if label == cause else 0.0)
                for name, value in features.items():
                    gradients[cause][name] += residual * value / count
        for cause in CLASSES[:2]:
            for name in names:
                if name != "intercept":
                    gradients[cause][name] += ridge * coefficients[cause][name] / count
                gradient = max(-10.0, min(10.0, gradients[cause][name]))
                first[cause][name] = 0.9 * first[cause][name] + 0.1 * gradient
                second[cause][name] = 0.999 * second[cause][name] + 0.001 * gradient * gradient
                first_hat = first[cause][name] / (1.0 - 0.9**iteration)
                second_hat = second[cause][name] / (1.0 - 0.999**iteration)
                coefficients[cause][name] -= 0.025 * first_hat / (math.sqrt(second_hat) + 1e-8)
    return {
        "enabled": True,
        "ridge": ridge,
        "scaling": scaling,
        "coefficients": coefficients,
        "fit_case_count": count,
        "fit_iterations": FIT_ITERATIONS,
    }


def _losses(label: str, probabilities: dict[str, float]) -> tuple[float, float]:
    log_loss = -math.log(max(float(probabilities[label]), 1e-15))
    brier = math.fsum(
        (float(probabilities[name]) - (1.0 if name == label else 0.0)) ** 2
        for name in probabilities
    )
    return log_loss, brier


def conditional_metrics(model: dict, rows: list[dict]) -> dict:
    model_losses = [_losses(row["label"], predict(model, row)) for row in rows]
    baseline_losses = [_losses(row["label"], row["base"]) for row in rows]
    return {
        "cases": len(rows),
        "model_log_loss": _mean([item[0] for item in model_losses]),
        "model_brier": _mean([item[1] for item in model_losses]),
        "baseline_log_loss": _mean([item[0] for item in baseline_losses]),
        "baseline_brier": _mean([item[1] for item in baseline_losses]),
        "log_loss_improvement": _mean(
            [base[0] - model[0] for base, model in zip(baseline_losses, model_losses)]
        ),
        "brier_improvement": _mean(
            [base[1] - model[1] for base, model in zip(baseline_losses, model_losses)]
        ),
        "class_counts": dict(Counter(row["label"] for row in rows)),
    }


def combine_stages(stage_probabilities: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    curve = {}
    for horizon in STAGE_ORDER:
        stage = stage_probabilities[horizon]
        cumulative_tp += survival * float(stage[CLASSES[0]])
        cumulative_sl += survival * float(stage[CLASSES[1]])
        survival *= float(stage[CLASSES[2]])
        mass = cumulative_tp + cumulative_sl + survival
        survival += 1.0 - mass
        curve[horizon] = {
            CUMULATIVE_CLASSES[0]: cumulative_tp,
            CUMULATIVE_CLASSES[1]: cumulative_sl,
            CUMULATIVE_CLASSES[2]: survival,
        }
    return curve


def _predict_group(rows: dict[str, dict], models: dict[str, dict]) -> dict[str, dict[str, float]]:
    baselines = _conditional_baseline(_cumulative_baseline(rows))
    stage_probabilities = {}
    for index, horizon in enumerate(STAGE_ORDER):
        record = {"base": baselines[horizon], "features": _raw_features(rows, index)}
        stage_probabilities[horizon] = predict(models[horizon], record)
    return combine_stages(stage_probabilities)


def _old_curve(rows: dict[str, dict]) -> dict[str, dict[str, float]]:
    return {
        horizon: {
            name: float(rows[horizon]["horizon_aware_probabilities"][name])
            for name in CUMULATIVE_CLASSES
        }
        for horizon in STAGE_ORDER
    }


def evaluate_cumulative(models: dict[str, dict], partition: str) -> dict:
    totals = {
        horizon: {
            "n": 0,
            "candidate_log": 0.0,
            "candidate_brier": 0.0,
            "old_log": 0.0,
            "old_brier": 0.0,
        }
        for horizon in STAGE_ORDER
    }
    weekly: dict[str, list[float]] = {}
    invariant_errors = Counter()
    for rows in iter_groups():
        if rows[STAGE_ORDER[0]]["partition"] != partition:
            continue
        candidate = _predict_group(rows, models)
        old = _old_curve(rows)
        previous_tp = previous_sl = 0.0
        previous_survival = 1.0
        group_delta = [0.0, 0.0, 0]
        for horizon in STAGE_ORDER:
            probabilities = candidate[horizon]
            if abs(math.fsum(probabilities.values()) - 1.0) > 1e-10:
                invariant_errors["mass"] += 1
            if probabilities[CUMULATIVE_CLASSES[0]] + 1e-12 < previous_tp:
                invariant_errors["tp_monotonic"] += 1
            if probabilities[CUMULATIVE_CLASSES[1]] + 1e-12 < previous_sl:
                invariant_errors["sl_monotonic"] += 1
            if probabilities[CUMULATIVE_CLASSES[2]] - 1e-12 > previous_survival:
                invariant_errors["survival_monotonic"] += 1
            previous_tp = probabilities[CUMULATIVE_CLASSES[0]]
            previous_sl = probabilities[CUMULATIVE_CLASSES[1]]
            previous_survival = probabilities[CUMULATIVE_CLASSES[2]]
            label = rows[horizon]["outcome"]["label"]
            candidate_loss = _losses(label, probabilities)
            old_loss = _losses(label, old[horizon])
            item = totals[horizon]
            item["n"] += 1
            item["candidate_log"] += candidate_loss[0]
            item["candidate_brier"] += candidate_loss[1]
            item["old_log"] += old_loss[0]
            item["old_brier"] += old_loss[1]
            group_delta[0] += old_loss[0] - candidate_loss[0]
            group_delta[1] += old_loss[1] - candidate_loss[1]
            group_delta[2] += 1
        week = rows[STAGE_ORDER[0]]["inference_cluster_id"]
        values = weekly.setdefault(week, [0.0, 0.0, 0])
        values[0] += group_delta[0] / group_delta[2]
        values[1] += group_delta[1] / group_delta[2]
        values[2] += 1
    by_horizon = {}
    for horizon, item in totals.items():
        n = item["n"]
        by_horizon[horizon] = {
            "n": n,
            "candidate_log_loss": item["candidate_log"] / n,
            "candidate_brier": item["candidate_brier"] / n,
            "v0_7_log_loss": item["old_log"] / n,
            "v0_7_brier": item["old_brier"] / n,
            "log_loss_improvement": (item["old_log"] - item["candidate_log"]) / n,
            "brier_improvement": (item["old_brier"] - item["candidate_brier"]) / n,
        }
    week_values = [(value[0] / value[2], value[1] / value[2]) for value in weekly.values()]
    rng = random.Random(RANDOM_SEED + 77)
    log_samples = []
    brier_samples = []
    if week_values:
        indexes = list(range(len(week_values)))
        for _ in range(BOOTSTRAP_SAMPLES):
            sample = [week_values[rng.choice(indexes)] for _ in indexes]
            log_samples.append(_mean([value[0] for value in sample]))
            brier_samples.append(_mean([value[1] for value in sample]))
    return {
        "partition": partition,
        "by_horizon": by_horizon,
        "macro_log_loss_improvement": _mean(
            [value["log_loss_improvement"] for value in by_horizon.values()]
        ),
        "macro_brier_improvement": _mean(
            [value["brier_improvement"] for value in by_horizon.values()]
        ),
        "complete_utc_weeks": len(week_values),
        "weekly_bootstrap_log_loss_95ci": (
            [
                sorted(log_samples)[int(0.025 * (len(log_samples) - 1))],
                sorted(log_samples)[int(0.975 * (len(log_samples) - 1))],
            ]
            if log_samples
            else None
        ),
        "weekly_bootstrap_brier_95ci": (
            [
                sorted(brier_samples)[int(0.025 * (len(brier_samples) - 1))],
                sorted(brier_samples)[int(0.975 * (len(brier_samples) - 1))],
            ]
            if brier_samples
            else None
        ),
        "invariant_errors": dict(invariant_errors),
    }


def disabled_model() -> dict:
    return {"enabled": False, "ridge": None, "scaling": {}, "coefficients": {}}


def train_and_evaluate() -> dict:
    if not DATASET_PATH.exists():
        build_dataset()
    stage_audits = {}
    selected_ridges = {}
    prefinal_models = {}
    for index, horizon in enumerate(STAGE_ORDER):
        development = _sample(
            {"development"}, index, FIT_CASE_LIMIT, seed_suffix=f"dev:{horizon}"
        )
        calibration = _sample(
            {"calibration"}, index, EVALUATION_CASE_LIMIT, seed_suffix=f"cal:{horizon}"
        )
        scaling = fit_scaling(development)
        candidates = []
        for ridge in RIDGE_CANDIDATES:
            model = fit_model(development, ridge, scaling)
            candidates.append(
                {"ridge": ridge, "model": model, "calibration": conditional_metrics(model, calibration)}
            )
        selected = min(
            candidates,
            key=lambda item: (
                item["calibration"]["model_log_loss"],
                item["calibration"]["model_brier"],
                item["ridge"],
            ),
        )
        selected_ridges[horizon] = selected["ridge"]
        prefinal_fit = _sample(
            {"development", "calibration"},
            index,
            FIT_CASE_LIMIT,
            seed_suffix=f"prefinal:{horizon}",
        )
        prefinal_scaling = fit_scaling(prefinal_fit)
        prefinal = fit_model(prefinal_fit, selected["ridge"], prefinal_scaling)
        rule_test = _sample(
            {"rule_test"}, index, EVALUATION_CASE_LIMIT, seed_suffix=f"test:{horizon}"
        )
        test_metrics = conditional_metrics(prefinal, rule_test)
        enabled = (
            selected["calibration"]["log_loss_improvement"] > 0
            and selected["calibration"]["brier_improvement"] > 0
            and test_metrics["log_loss_improvement"] > 0
            and test_metrics["brier_improvement"] > 0
        )
        prefinal_models[horizon] = prefinal if enabled else disabled_model()
        stage_audits[horizon] = {
            "stage_id": STAGE_PROFILES[horizon]["stage_id"],
            "development_cases": len(development),
            "selected_ridge": selected["ridge"],
            "calibration_by_ridge": [
                {"ridge": item["ridge"], "metrics": item["calibration"]}
                for item in candidates
            ],
            "rule_test": test_metrics,
            "rule_layer_enabled": enabled,
        }
    rule_test_cumulative = evaluate_cumulative(prefinal_models, "rule_test")

    final_models = {}
    for index, horizon in enumerate(STAGE_ORDER):
        if not stage_audits[horizon]["rule_layer_enabled"]:
            final_models[horizon] = disabled_model()
            continue
        final_fit = _sample(
            {"development", "calibration", "rule_test"},
            index,
            FIT_CASE_LIMIT,
            seed_suffix=f"finalfit:{horizon}",
        )
        scaling = fit_scaling(final_fit)
        final_models[horizon] = fit_model(
            final_fit, selected_ridges[horizon], scaling
        )
    final_evaluation = evaluate_cumulative(final_models, "final_test")
    log_ci = final_evaluation["weekly_bootstrap_log_loss_95ci"]
    brier_ci = final_evaluation["weekly_bootstrap_brier_95ci"]
    production_gate = (
        not final_evaluation["invariant_errors"]
        and log_ci is not None
        and brier_ci is not None
        and log_ci[0] > 0
        and brier_ci[0] > 0
        and all(
            item["log_loss_improvement"] >= 0
            for item in final_evaluation["by_horizon"].values()
        )
        and final_evaluation["macro_brier_improvement"] >= 0
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifact_without_hash = {
        "artifact_id": "TP-SL-SEQUENTIAL-MULTISCALE-v0.8-frozen-001",
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "status": "frozen_production" if production_gate else "rejected",
        "production_authorized": production_gate,
        "single_engine": True,
        "parallel_probability_engines": 0,
        "automatic_weight_updates": False,
        "stage_order": list(STAGE_ORDER),
        "stage_profiles": {
            horizon: dict(STAGE_PROFILES[horizon]) for horizon in STAGE_ORDER
        },
        "stage_models": final_models,
        "feature_schema": {
            "base_rule_features": list(FLAT_FEATURE_NAMES),
            "inheritance": {
                horizon: list(STAGE_ORDER[: index + 1])
                for index, horizon in enumerate(STAGE_ORDER)
            },
            "geometry": [
                "tp_sigma_units",
                "sl_sigma_units",
                "log_tp_sl_ratio",
                "log_context_sigma",
            ],
        },
        "baseline": {
            "method": "piecewise_variance_first_touch",
            "incremental_variance": (
                "context_sigma_squared * increment_seconds / context_horizon_seconds"
            ),
        },
        "training_dataset_sha256": manifest["dataset_sha256"],
        "evaluation_sha256": None,
        "invariants": {
            "first_touch_absorbing": True,
            "tp_cumulative_non_decreasing": True,
            "sl_cumulative_non_decreasing": True,
            "expiry_non_increasing": True,
            "probability_mass_one": True,
        },
    }
    result = add_hash(
        {
            "version": EVALUATION_VERSION,
            "engine_version": ENGINE_VERSION,
            "dataset_sha256": manifest["dataset_sha256"],
            "stage_audits": stage_audits,
            "rule_test_cumulative": rule_test_cumulative,
            "sealed_final": final_evaluation,
            "production_gate_passed": production_gate,
            "decision": (
                "promote_single_sequential_multiscale_engine"
                if production_gate
                else "do_not_promote_sequential_candidate"
            ),
            "production_effect": "pending_integration" if production_gate else "none",
            "promotion_gate": {
                "primary_metric": "log_loss_improves_in_every_horizon",
                "secondary_metric": "macro_brier_improves_with_positive_weekly_95ci",
                "temporal_invariants": "zero_errors_required",
            },
            "supabase_writes": 0,
        }
    )
    write_json(RESULT_PATH, result)
    artifact_without_hash["evaluation_sha256"] = result["canonical_payload_sha256"]
    artifact = dict(artifact_without_hash)
    artifact["artifact_sha256"] = canonical_sha256(artifact_without_hash)
    write_json(ARTIFACT_PATH, artifact)
    write_report(result, artifact)
    return result


def write_report(result: dict, artifact: dict) -> None:
    lines = [
        "# Motor secuencial multiescala",
        "",
        f"- Motor: `{ENGINE_VERSION}`.",
        f"- Decisión: **`{result['decision']}`**.",
        f"- Autorizado para producción: **{artifact['production_authorized']}**.",
        "- Arquitectura: un único motor con etapas condicionales anidadas.",
        "",
        "## Etapas",
        "",
        "| Tramo | Datos propios | Hereda | Reglas activas |",
        "|---|---|---|---|",
    ]
    for index, horizon in enumerate(STAGE_ORDER):
        profile = STAGE_PROFILES[horizon]
        audit = result["stage_audits"][horizon]
        lines.append(
            f"| {profile['label']} | {profile['interval']} sobre contexto "
            f"{profile['horizon_seconds'] // 3600} h | "
            f"{', '.join(STAGE_ORDER[:index]) or 'ninguno'} | "
            f"{audit['rule_layer_enabled']} |"
        )
    lines.extend(
        [
            "",
            "`False` en el último tramo no significa que el marco largo quede sin analizar:",
            "mantiene la física de primer toque, la volatilidad propia 6h/7d y toda la",
            "probabilidad heredada de 0-24h. Significa únicamente que el ajuste direccional",
            "de las reglas fue rechazado al empeorar fuera de muestra y, por tanto, no se",
            "forzó un peso sin evidencia.",
            "",
            "## Prueba final frente a v0.7",
            "",
            "| Marco | Δ log-loss | Δ Brier |",
            "|---|---:|---:|",
        ]
    )
    for horizon, metrics in result["sealed_final"]["by_horizon"].items():
        lines.append(
            f"| `{horizon}` | {metrics['log_loss_improvement']:.6f} | "
            f"{metrics['brier_improvement']:.6f} |"
        )
    lines.extend(
        [
            "",
            f"- IC95% semanal log-loss: `{result['sealed_final']['weekly_bootstrap_log_loss_95ci']}`.",
            f"- IC95% semanal Brier: `{result['sealed_final']['weekly_bootstrap_brier_95ci']}`.",
            f"- Errores de invariantes: `{result['sealed_final']['invariant_errors']}`.",
            "",
            "El resultado de un tramo sólo se añade a la masa que sobrevivió al anterior; "
            "un primer toque anterior nunca puede reclasificarse.",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def finalize_existing_evaluation() -> dict:
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    final = result["sealed_final"]
    log_ci = final["weekly_bootstrap_log_loss_95ci"]
    brier_ci = final["weekly_bootstrap_brier_95ci"]
    production_gate = (
        not final["invariant_errors"]
        and log_ci is not None
        and brier_ci is not None
        and log_ci[0] > 0
        and brier_ci[0] > 0
        and all(
            item["log_loss_improvement"] >= 0
            for item in final["by_horizon"].values()
        )
        and final["macro_brier_improvement"] >= 0
    )
    clean_result = {
        key: value
        for key, value in result.items()
        if key != "canonical_payload_sha256"
    }
    clean_result.update(
        {
            "production_gate_passed": production_gate,
            "decision": (
                "promote_single_sequential_multiscale_engine"
                if production_gate
                else "do_not_promote_sequential_candidate"
            ),
            "production_effect": "pending_integration" if production_gate else "none",
            "promotion_gate": {
                "primary_metric": "log_loss_improves_in_every_horizon",
                "secondary_metric": "macro_brier_improves_with_positive_weekly_95ci",
                "temporal_invariants": "zero_errors_required",
            },
        }
    )
    result = add_hash(clean_result)
    clean_artifact = {
        key: value for key, value in artifact.items() if key != "artifact_sha256"
    }
    clean_artifact.update(
        {
            "status": "frozen_production" if production_gate else "rejected",
            "production_authorized": production_gate,
            "evaluation_sha256": result["canonical_payload_sha256"],
        }
    )
    artifact = dict(clean_artifact)
    artifact["artifact_sha256"] = canonical_sha256(clean_artifact)
    write_json(RESULT_PATH, result)
    write_json(ARTIFACT_PATH, artifact)
    write_report(result, artifact)
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "train", "finalize", "all"))
    args = parser.parse_args()
    if args.command in {"build", "all"}:
        manifest = build_dataset()
        print(f"SEQUENTIAL_DATASET_SHA256={manifest['dataset_sha256']}")
    if args.command in {"train", "all"}:
        result = train_and_evaluate()
        print(f"SEQUENTIAL_DECISION={result['decision']}")
        print(f"SEQUENTIAL_EVALUATION_SHA256={result['canonical_payload_sha256']}")
    if args.command == "finalize":
        result = finalize_existing_evaluation()
        print(f"SEQUENTIAL_DECISION={result['decision']}")
        print(f"SEQUENTIAL_EVALUATION_SHA256={result['canonical_payload_sha256']}")


if __name__ == "__main__":
    main()
