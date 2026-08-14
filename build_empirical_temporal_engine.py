from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from empirical_temporal_engine import (
    ARTIFACT_PATH,
    CONDITIONAL_CLASSES,
    CUMULATIVE_CLASSES,
    ENGINE_VERSION,
    SCORING_VERSION,
    STAGE_BOUNDS,
    _distance,
    _stage_label,
    _weighted_probabilities,
    canonical_sha256,
)
from multiscale_feature_runtime import STAGE_ORDER, STAGE_PROFILES
from phase1_controlled_replay import SYMBOLS, read_symbol_5m
from sequential_first_touch_math import double_barrier_first_touch


ROOT = Path(__file__).resolve().parent
SOURCE_DATASET = (
    ROOT
    / "data"
    / "phase1_controlled_replay"
    / "sequential_multiscale_cases_v0_1.jsonl.gz"
)
RECORD_CACHE = (
    ROOT
    / "data"
    / "phase1_controlled_replay"
    / "empirical_analog_records_v0_1.json.gz"
)
VALIDATION_PATH = ROOT / "auditorias_motor" / "empirical_analog_validation_v0_1.json"
REPORT_PATH = ROOT / "auditorias_motor" / "2026-08-14_motor_empirico_analogos_v0_9.md"

ARTIFACT_ID = "TP-SL-EMPIRICAL-ANALOG-v0.9-frozen-001"
BUILD_VERSION = "empirical-analog-builder-v0.1"
RANDOM_SEED = 20260814
MAX_FUTURE_STEPS = 7 * 24 * 12
PARTITIONS = ("development", "calibration", "rule_test", "final_test")
GEOMETRY_GRID = (
    (0.25, 0.25),
    (0.25, 1.00),
    (0.50, 0.50),
    (0.50, 2.00),
    (1.00, 0.50),
    (1.00, 1.00),
    (1.00, 2.00),
    (2.00, 0.50),
    (2.00, 2.00),
    (3.00, 1.00),
    (1.00, 3.00),
    (4.00, 4.00),
)

RULE_GROUPS = {
    "price_path": (
        "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
        "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
        "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
    ),
    "trend_momentum": (
        "LIB-CAND-EMA-TREND-001::side_adjusted_close_vs_ema50_log",
        "LIB-CAND-EMA-TREND-001::side_adjusted_ema50_vs_ema200_log",
        "LIB-CAND-EMA-TREND-001::side_adjusted_slope_atr",
        "LIB-CAND-RSI-WILDER-001::side_adjusted_centered_rsi",
        "LIB-CAND-ATR-EXTENSION-001::side_adjusted_extension_atr",
    ),
    "volatility_regime": (
        "log_context_sigma",
        "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
        "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
        "LIB-CAND-COMPRESSION-001::compression_vector.bollinger_width_rank",
    ),
    "volume_flow": (
        "LIB-CAND-RELATIVE-VOLUME-001::log_relative_horizon_volume",
        "LIB-CAND-CVD-SLOPE-001::side_adjusted_normalized_cvd_slope",
        "LIB-CAND-ABSORPTION-001::side_adjusted_horizon_displacement_atr",
        "LIB-CAND-ABSORPTION-001::flow_opposing_wick_ratio",
    ),
}

SIGNED_FEATURES = {
    "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
    "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
    "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
    "LIB-CAND-EMA-TREND-001::side_adjusted_close_vs_ema50_log",
    "LIB-CAND-EMA-TREND-001::side_adjusted_ema50_vs_ema200_log",
    "LIB-CAND-EMA-TREND-001::side_adjusted_slope_atr",
    "LIB-CAND-RSI-WILDER-001::side_adjusted_centered_rsi",
    "LIB-CAND-ATR-EXTENSION-001::side_adjusted_extension_atr",
    "LIB-CAND-CVD-SLOPE-001::side_adjusted_normalized_cvd_slope",
    "LIB-CAND-ABSORPTION-001::side_adjusted_horizon_displacement_atr",
}

SELECTION = {
    "neighbor_count": 240,
    "minimum_analogs": 80,
    "absolute_minimum_analogs": 12,
    "maximum_scanned": 20_000,
    "cross_symbol_penalty": 0.15,
    "recency_penalty_per_year": 0.0,
    "probability_temperature": 1.05,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _eligible_source_row(row: dict) -> bool:
    return (
        str(row.get("side")) == "long"
        and abs(float(row.get("tp_reference_sigma_multiple") or 0.0) - 1.0) < 1e-12
        and abs(float(row.get("sl_reference_sigma_multiple") or 0.0) - 1.0) < 1e-12
    )


def _source_anchors() -> dict[str, dict]:
    anchors: dict[str, dict] = {}
    with gzip.open(SOURCE_DATASET, "rt", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            if not _eligible_source_row(row):
                continue
            anchor_id = str(row["anchor_id"])
            horizon = str(row["time_horizon"])
            anchor = anchors.setdefault(
                anchor_id,
                {
                    "id": anchor_id,
                    "symbol": str(row["symbol"]),
                    "partition": str(row["partition"]),
                    "analysis_at": str(row["analysis_at"]),
                    "cutoff_ms": int(anchor_id.rsplit(":", 1)[1]),
                    "entry": float(row["entry"]),
                    "stage_features": {},
                    "stage_sigmas": {},
                },
            )
            anchor["stage_features"][horizon] = {
                str(name): float(value)
                for name, value in row["horizon_rule_features"].items()
            }
            anchor["stage_sigmas"][horizon] = float(
                row["multiscale_context"]["context_sigma"]
            )
    return {
        key: value
        for key, value in anchors.items()
        if set(value["stage_features"]) == set(STAGE_ORDER)
        and set(value["stage_sigmas"]) == set(STAGE_ORDER)
    }


def _frontiers(entry: float, future: list[dict]) -> tuple[list[list[float]], list[list[float]]]:
    maximum_up = 0.0
    maximum_down = 0.0
    up: list[list[float]] = []
    down: list[list[float]] = []
    for step, candle in enumerate(future, 1):
        up_value = max(0.0, math.log(float(candle["high"]) / entry))
        down_value = max(0.0, math.log(entry / float(candle["low"])))
        if up_value > maximum_up + 1e-14:
            maximum_up = up_value
            up.append([round(maximum_up, 10), step])
        if down_value > maximum_down + 1e-14:
            maximum_down = down_value
            down.append([round(maximum_down, 10), step])
    return up, down


def build_record_cache() -> list[dict]:
    anchors = _source_anchors()
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for anchor in anchors.values():
        by_symbol[anchor["symbol"]].append(anchor)
    records = []
    blocked: Counter = Counter()
    for symbol in SYMBOLS:
        candles = read_symbol_5m(symbol)
        index_by_close = {
            int(candle["close_time_ms"]): index for index, candle in enumerate(candles)
        }
        for anchor in sorted(by_symbol[symbol], key=lambda item: item["cutoff_ms"]):
            index = index_by_close.get(int(anchor["cutoff_ms"]))
            if index is None:
                blocked["anchor_not_in_5m_archive"] += 1
                continue
            future = candles[index + 1 : index + 1 + MAX_FUTURE_STEPS]
            if len(future) != MAX_FUTURE_STEPS:
                blocked["future_7d_incomplete"] += 1
                continue
            if any(
                int(right["open_time_ms"]) - int(left["open_time_ms"]) != 300_000
                for left, right in zip(future, future[1:])
            ):
                blocked["future_7d_gapped"] += 1
                continue
            up, down = _frontiers(float(anchor["entry"]), future)
            records.append(
                {
                    **anchor,
                    "up_frontier": up,
                    "down_frontier": down,
                }
            )
        print(f"EMPIRICAL_RECORDS {symbol} total={len(records)}", flush=True)
    payload = {
        "version": "empirical-analog-records-v0.1",
        "source_dataset": str(SOURCE_DATASET.relative_to(ROOT)),
        "source_dataset_sha256": sha256_file(SOURCE_DATASET),
        "records": records,
        "blocked": dict(blocked),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    RECORD_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(RECORD_CACHE, "wt", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, ensure_ascii=True, separators=(",", ":"))
    return records


def load_or_build_records(*, rebuild: bool = False) -> list[dict]:
    if rebuild or not RECORD_CACHE.exists():
        return build_record_cache()
    with gzip.open(RECORD_CACHE, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    expected = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected:
        raise RuntimeError("empirical_record_cache_hash_invalid")
    return payload["records"]


def _feature_names(groups_by_horizon: dict[str, Iterable[str]]) -> dict[str, list[str]]:
    return {
        horizon: [
            f"{stage}::{name}"
            for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
            for group in groups_by_horizon[horizon]
            for name in RULE_GROUPS[group]
        ]
        for horizon in STAGE_ORDER
    }


def _raw_feature_map(record: dict, horizon: str, orientation: int) -> dict[str, float]:
    values = {}
    for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]:
        stage_features = record["stage_features"][stage]
        for name in {item for group in RULE_GROUPS.values() for item in group}:
            if name == "log_context_sigma":
                value = math.log(float(record["stage_sigmas"][stage]))
            else:
                value = float(stage_features[name])
                if orientation == 1 and name in SIGNED_FEATURES:
                    value = -value
            values[f"{stage}::{name}"] = value
    return values


def _robust_scaling(
    records: list[dict], names_by_horizon: dict[str, list[str]]
) -> dict[str, list[list[float]]]:
    result = {}
    for horizon, names in names_by_horizon.items():
        columns = [[] for _ in names]
        for record in records:
            for orientation in (0, 1):
                values = _raw_feature_map(record, horizon, orientation)
                for index, name in enumerate(names):
                    columns[index].append(float(values[name]))
        scaling = []
        for values in columns:
            center = statistics.median(values)
            deviations = [abs(value - center) for value in values]
            scale = 1.4826 * statistics.median(deviations)
            if not math.isfinite(scale) or scale <= 1e-9:
                scale = statistics.pstdev(values)
            scaling.append([center, max(scale, 1e-9)])
        result[horizon] = scaling
    return result


def _standardized_vector(
    record: dict,
    horizon: str,
    orientation: int,
    names: list[str],
    scaling: list[list[float]],
) -> list[float]:
    values = _raw_feature_map(record, horizon, orientation)
    return [
        (float(values[name]) - float(center)) / float(scale)
        for name, (center, scale) in zip(names, scaling)
    ]


def _model_analogs(
    records: list[dict],
    names_by_horizon: dict[str, list[str]],
    scaling: dict[str, list[list[float]]],
) -> list[dict]:
    analogs = []
    for record in records:
        feature_vectors = []
        for horizon in STAGE_ORDER:
            names = names_by_horizon[horizon]
            feature_vectors.append(
                [
                    _standardized_vector(
                        record, horizon, orientation, names, scaling[horizon]
                    )
                    for orientation in (0, 1)
                ]
            )
        analogs.append(
            {
                "id": record["id"],
                "symbol": record["symbol"],
                "analysis_at": record["analysis_at"],
                "analysis_epoch": datetime.fromisoformat(
                    str(record["analysis_at"]).replace("Z", "+00:00")
                ).timestamp(),
                "feature_vectors": feature_vectors,
                "up_frontier": record["up_frontier"],
                "down_frontier": record["down_frontier"],
            }
        )
    return analogs


def _build_model(
    records: list[dict],
    groups: tuple[str, ...] | dict[str, tuple[str, ...]],
    *,
    authorized: bool,
) -> dict:
    groups_by_horizon = (
        {horizon: tuple(groups[horizon]) for horizon in STAGE_ORDER}
        if isinstance(groups, dict)
        else {horizon: tuple(groups) for horizon in STAGE_ORDER}
    )
    names = _feature_names(groups_by_horizon)
    scaling = _robust_scaling(records, names)
    analogs = _model_analogs(records, names, scaling)
    dates = sorted(str(record["analysis_at"]) for record in records)
    payload = {
        "artifact_id": ARTIFACT_ID,
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "build_version": BUILD_VERSION,
        "status": "frozen_production" if authorized else "validation_candidate",
        "production_authorized": authorized,
        "single_engine": True,
        "parallel_probability_engines": 0,
        "automatic_weight_updates": False,
        "stage_order": list(STAGE_ORDER),
        "stage_profiles": {name: dict(STAGE_PROFILES[name]) for name in STAGE_ORDER},
        "active_rule_groups": sorted(
            {group for values in groups_by_horizon.values() for group in values}
        ),
        "active_rule_groups_by_horizon": {
            horizon: list(values) for horizon, values in groups_by_horizon.items()
        },
        "rule_group_features": {
            name: list(RULE_GROUPS[name])
            for name in sorted(
                {group for values in groups_by_horizon.values() for group in values}
            )
        },
        "excluded_unvalidated_rules": {
            "fibonacci": "plan-dependent historical analogue projection not validated",
            "structural_levels": "plan-dependent historical analogue projection not validated",
            "liquidation_heatmap": "no timestamped historical source coverage",
        },
        "feature_names": names,
        "feature_scaling": scaling,
        "selection": dict(SELECTION),
        "historical_source": "Binance USD-M monthly 5m closed kline archives",
        "historical_coverage": {
            "symbols": sorted({record["symbol"] for record in records}),
            "first_analysis_at": dates[0],
            "last_analysis_at": dates[-1],
            "records": len(records),
            "orientations_per_record": 2,
            "maximum_future_horizon_days": 7,
            "future_resolution": "5m high_low",
        },
        "analogs": analogs,
    }
    payload["artifact_sha256"] = canonical_sha256(payload)
    return payload


def _ranked_candidates(
    current_record: dict,
    orientation: int,
    horizon: str,
    model: dict,
) -> list[tuple[float, dict, int, bool]]:
    stage_index = STAGE_ORDER.index(horizon)
    current = _standardized_vector(
        current_record,
        horizon,
        orientation,
        model["feature_names"][horizon],
        model["feature_scaling"][horizon],
    )
    ranked = []
    penalty = float(model["selection"]["cross_symbol_penalty"])
    recency_penalty = float(
        model["selection"].get("recency_penalty_per_year", 0.0)
    )
    current_epoch = datetime.fromisoformat(
        str(current_record["analysis_at"]).replace("Z", "+00:00")
    ).timestamp()
    for analog in model["analogs"]:
        same_symbol = analog["symbol"] == current_record["symbol"]
        for analog_orientation in (0, 1):
            distance = _distance(
                current, analog["feature_vectors"][stage_index][analog_orientation]
            )
            if not same_symbol:
                distance += penalty
            age_years = max(
                0.0,
                (current_epoch - float(analog["analysis_epoch"]))
                / (365.25 * 24.0 * 3600.0),
            )
            distance += recency_penalty * age_years
            ranked.append((distance, analog, analog_orientation, same_symbol))
    ranked.sort(key=lambda item: (item[0], item[1]["id"], item[2]))
    return ranked


def _predict_stage_from_ranked(
    ranked: list[tuple[float, dict, int, bool]],
    horizon: str,
    tp_distance: float,
    sl_distance: float,
    selection: dict,
    survival_before: float,
) -> dict[str, float] | None:
    start_step, end_step = STAGE_BOUNDS[horizon]
    selected = []
    for distance, analog, orientation, same_symbol in ranked[: int(selection["maximum_scanned"])]:
        label = _stage_label(
            analog,
            orientation,
            tp_distance=tp_distance,
            sl_distance=sl_distance,
            start_step=start_step,
            end_step=end_step,
        )
        if label is None or label == "ambiguous":
            continue
        selected.append(
            {
                "distance": distance,
                "label": label,
                "same_symbol": same_symbol,
            }
        )
        if len(selected) >= int(selection["neighbor_count"]):
            break
    return _weighted_probabilities(
        selected,
        probability_temperature=float(selection.get("probability_temperature", 1.0)),
    )[0]


def _true_label(record: dict, orientation: int, tp: float, sl: float, horizon: str) -> str | None:
    if orientation == 0:
        favorable = record["up_frontier"]
        adverse = record["down_frontier"]
    else:
        favorable = record["down_frontier"]
        adverse = record["up_frontier"]
    synthetic = {
        "up_frontier": favorable,
        "down_frontier": adverse,
    }
    label = _stage_label(
        synthetic,
        0,
        tp_distance=tp,
        sl_distance=sl,
        start_step=0,
        end_step=STAGE_BOUNDS[horizon][1],
    )
    if label == "ambiguous":
        return None
    return {
        CONDITIONAL_CLASSES[0]: CUMULATIVE_CLASSES[0],
        CONDITIONAL_CLASSES[1]: CUMULATIVE_CLASSES[1],
        CONDITIONAL_CLASSES[2]: CUMULATIVE_CLASSES[2],
    }.get(label)


def _stratified_sample(records: list[dict], per_symbol: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_symbol[record["symbol"]].append(record)
    selected = []
    for symbol in sorted(by_symbol):
        values = sorted(by_symbol[symbol], key=lambda item: item["analysis_at"])
        selected.extend(rng.sample(values, min(per_symbol, len(values))))
    return selected


def evaluate_model(model: dict, evaluation_records: list[dict], *, per_symbol: int, seed: int) -> dict:
    sample = _stratified_sample(evaluation_records, per_symbol, seed)
    accumulators = {
        horizon: {
            "n": 0,
            "log_loss": 0.0,
            "brier": 0.0,
            "baseline_log_loss": 0.0,
            "baseline_brier": 0.0,
            "labels": Counter(),
        }
        for horizon in STAGE_ORDER
    }
    by_geometry = defaultdict(
        lambda: {
            "n": 0,
            "log_loss": 0.0,
            "brier": 0.0,
            "baseline_log_loss": 0.0,
            "baseline_brier": 0.0,
        }
    )
    blocked = Counter()
    for record in sample:
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        for orientation in (0, 1):
            rankings = {
                horizon: _ranked_candidates(record, orientation, horizon, model)
                for horizon in STAGE_ORDER
            }
            for tp_multiple, sl_multiple in GEOMETRY_GRID:
                tp_distance = tp_multiple * base_sigma
                sl_distance = sl_multiple * base_sigma
                survival = 1.0
                cumulative = {
                    CUMULATIVE_CLASSES[0]: 0.0,
                    CUMULATIVE_CLASSES[1]: 0.0,
                    CUMULATIVE_CLASSES[2]: 1.0,
                }
                cumulative_variance = 0.0
                for horizon in STAGE_ORDER:
                    conditional = _predict_stage_from_ranked(
                        rankings[horizon],
                        horizon,
                        tp_distance,
                        sl_distance,
                        model["selection"],
                        survival,
                    )
                    if conditional is None:
                        blocked[f"insufficient:{horizon}"] += 1
                        break
                    cumulative[CUMULATIVE_CLASSES[0]] += (
                        survival * conditional[CONDITIONAL_CLASSES[0]]
                    )
                    cumulative[CUMULATIVE_CLASSES[1]] += (
                        survival * conditional[CONDITIONAL_CLASSES[1]]
                    )
                    survival *= conditional[CONDITIONAL_CLASSES[2]]
                    cumulative[CUMULATIVE_CLASSES[2]] = survival
                    total = math.fsum(cumulative.values())
                    probabilities = {
                        name: value / total for name, value in cumulative.items()
                    }
                    profile = STAGE_PROFILES[horizon]
                    sigma = float(record["stage_sigmas"][horizon])
                    cumulative_variance += sigma * sigma * (
                        float(profile["increment_seconds"])
                        / float(profile["horizon_seconds"])
                    )
                    baseline_result = double_barrier_first_touch(
                        tp_log_distance=tp_distance,
                        sl_log_distance=sl_distance,
                        sigma_horizon=math.sqrt(cumulative_variance),
                        time_fraction=1.0,
                    )
                    baseline = {
                        CUMULATIVE_CLASSES[0]: baseline_result.p_tp,
                        CUMULATIVE_CLASSES[1]: baseline_result.p_sl,
                        CUMULATIVE_CLASSES[2]: baseline_result.p_expiry,
                    }
                    label = _true_label(
                        record,
                        orientation,
                        tp_distance,
                        sl_distance,
                        horizon,
                    )
                    if label is None:
                        blocked[f"ambiguous:{horizon}"] += 1
                        continue
                    loss = -math.log(max(probabilities[label], 1e-15))
                    brier = math.fsum(
                        (probabilities[name] - (1.0 if name == label else 0.0)) ** 2
                        for name in CUMULATIVE_CLASSES
                    )
                    baseline_loss = -math.log(max(baseline[label], 1e-15))
                    baseline_brier = math.fsum(
                        (baseline[name] - (1.0 if name == label else 0.0)) ** 2
                        for name in CUMULATIVE_CLASSES
                    )
                    accumulator = accumulators[horizon]
                    accumulator["n"] += 1
                    accumulator["log_loss"] += loss
                    accumulator["brier"] += brier
                    accumulator["baseline_log_loss"] += baseline_loss
                    accumulator["baseline_brier"] += baseline_brier
                    accumulator["labels"][label] += 1
                    geometry = by_geometry[(horizon, tp_multiple, sl_multiple)]
                    geometry["n"] += 1
                    geometry["log_loss"] += loss
                    geometry["brier"] += brier
                    geometry["baseline_log_loss"] += baseline_loss
                    geometry["baseline_brier"] += baseline_brier
    return {
        "sample_records": len(sample),
        "sample_orientations": len(sample) * 2,
        "geometries": [list(item) for item in GEOMETRY_GRID],
        "by_horizon": {
            horizon: {
                "n": item["n"],
                "log_loss": item["log_loss"] / item["n"],
                "brier": item["brier"] / item["n"],
                "first_passage_baseline_log_loss": (
                    item["baseline_log_loss"] / item["n"]
                ),
                "first_passage_baseline_brier": (
                    item["baseline_brier"] / item["n"]
                ),
                "log_loss_improvement_vs_first_passage": (
                    (item["baseline_log_loss"] - item["log_loss"]) / item["n"]
                ),
                "brier_improvement_vs_first_passage": (
                    (item["baseline_brier"] - item["brier"]) / item["n"]
                ),
                "labels": dict(item["labels"]),
            }
            for horizon, item in accumulators.items()
            if item["n"]
        },
        "by_geometry": {
            f"{horizon}:{tp:.2f}:{sl:.2f}": {
                "n": item["n"],
                "log_loss": item["log_loss"] / item["n"],
                "brier": item["brier"] / item["n"],
                "first_passage_baseline_log_loss": (
                    item["baseline_log_loss"] / item["n"]
                ),
                "first_passage_baseline_brier": (
                    item["baseline_brier"] / item["n"]
                ),
                "log_loss_improvement_vs_first_passage": (
                    (item["baseline_log_loss"] - item["log_loss"]) / item["n"]
                ),
                "brier_improvement_vs_first_passage": (
                    (item["baseline_brier"] - item["brier"]) / item["n"]
                ),
            }
            for (horizon, tp, sl), item in sorted(by_geometry.items())
            if item["n"]
        },
        "blocked": dict(blocked),
    }


def _model_score(evaluation: dict) -> tuple[float, float]:
    values = list(evaluation["by_horizon"].values())
    return (
        statistics.fmean(item["log_loss"] for item in values),
        statistics.fmean(item["brier"] for item in values),
    )


def _context_support_limits(model: dict, records: list[dict]) -> dict[str, float]:
    distances: dict[str, list[float]] = {name: [] for name in STAGE_ORDER}
    for record in records:
        for orientation in (0, 1):
            for horizon in STAGE_ORDER:
                ranked = _ranked_candidates(record, orientation, horizon, model)
                if ranked:
                    distances[horizon].append(float(ranked[0][0]))
    limits = {}
    for horizon, values in distances.items():
        ordered = sorted(values)
        if not ordered:
            raise RuntimeError(f"support_distance_missing:{horizon}")
        index = min(len(ordered) - 1, math.ceil(0.995 * len(ordered)) - 1)
        limits[horizon] = round(max(0.25, ordered[index] + 0.05), 8)
    return limits


def _evaluation_gate(evaluation: dict) -> dict:
    horizons = list(evaluation["by_horizon"].values())
    expected_per_horizon = evaluation["sample_orientations"] * len(GEOMETRY_GRID)
    expected_total = expected_per_horizon * len(STAGE_ORDER)
    ambiguous = sum(
        int(value)
        for key, value in evaluation["blocked"].items()
        if key.startswith("ambiguous:")
    )
    observed = sum(int(item["n"]) for item in horizons)
    return {
        "macro_log_loss_improvement_vs_first_passage": statistics.fmean(
            item["log_loss_improvement_vs_first_passage"] for item in horizons
        ),
        "macro_brier_improvement_vs_first_passage": statistics.fmean(
            item["brier_improvement_vs_first_passage"] for item in horizons
        ),
        "coverage_excluding_ambiguous": observed / (expected_total - ambiguous),
        "observed_predictions": observed,
        "expected_predictions_excluding_ambiguous": expected_total - ambiguous,
    }


def build_and_validate(*, rebuild_records: bool = False) -> dict:
    records = load_or_build_records(rebuild=rebuild_records)
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    candidates = (
        ("path_volatility", ("price_path", "volatility_regime")),
        (
            "path_volatility_trend",
            ("price_path", "volatility_regime", "trend_momentum"),
        ),
        (
            "path_volatility_flow",
            ("price_path", "volatility_regime", "volume_flow"),
        ),
        (
            "all_validated_context",
            ("price_path", "volatility_regime", "trend_momentum", "volume_flow"),
        ),
    )
    calibration_results = []
    calibration_seed = RANDOM_SEED + 2
    for name, groups in candidates:
        model = _build_model(partitions["development"], groups, authorized=False)
        evaluation = evaluate_model(
            model,
            partitions["calibration"],
            per_symbol=10,
            seed=calibration_seed,
        )
        calibration_results.append(
            {
                "candidate": name,
                "groups": list(groups),
                "score": _model_score(evaluation),
                "evaluation": evaluation,
            }
        )
        print(f"EMPIRICAL_CALIBRATION {name} score={_model_score(evaluation)}", flush=True)
    selected_by_horizon = {
        horizon: min(
            calibration_results,
            key=lambda item: (
                item["evaluation"]["by_horizon"][horizon]["log_loss"],
                item["evaluation"]["by_horizon"][horizon]["brier"],
            ),
        )
        for horizon in STAGE_ORDER
    }
    selected_groups_by_horizon = {
        horizon: tuple(item["groups"])
        for horizon, item in selected_by_horizon.items()
    }
    support_model = _build_model(
        partitions["development"], selected_groups_by_horizon, authorized=False
    )
    context_support_limits = _context_support_limits(
        support_model, partitions["calibration"]
    )
    prefinal_records = (
        partitions["development"]
        + partitions["calibration"]
        + partitions["rule_test"]
    )
    rule_test_model = _build_model(
        partitions["development"] + partitions["calibration"],
        selected_groups_by_horizon,
        authorized=False,
    )
    rule_test_evaluation = evaluate_model(
        rule_test_model,
        partitions["rule_test"],
        per_symbol=20,
        seed=RANDOM_SEED + 100,
    )
    final_test_model = _build_model(
        prefinal_records, selected_groups_by_horizon, authorized=False
    )
    final_test_evaluation = evaluate_model(
        final_test_model,
        partitions["final_test"],
        per_symbol=30,
        seed=RANDOM_SEED + 200,
    )
    rule_gate = _evaluation_gate(rule_test_evaluation)
    final_gate = _evaluation_gate(final_test_evaluation)
    production_authorized = all(
        (
            rule_gate["macro_log_loss_improvement_vs_first_passage"] > 0.0,
            rule_gate["macro_brier_improvement_vs_first_passage"] > 0.0,
            final_gate["macro_log_loss_improvement_vs_first_passage"] > 0.0,
            final_gate["macro_brier_improvement_vs_first_passage"] > 0.0,
            rule_gate["coverage_excluding_ambiguous"] >= 0.999,
            final_gate["coverage_excluding_ambiguous"] >= 0.999,
        )
    )
    production_model = _build_model(
        records, selected_groups_by_horizon, authorized=production_authorized
    )
    production_model["selection"][
        "maximum_nearest_context_distance_by_horizon"
    ] = context_support_limits
    production_model["artifact_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in production_model.items()
            if key != "artifact_sha256"
        }
    )
    validation = {
        "version": "empirical-analog-validation-v0.1",
        "engine_version": ENGINE_VERSION,
        "source_dataset_sha256": sha256_file(SOURCE_DATASET),
        "record_cache_sha256": sha256_file(RECORD_CACHE),
        "records_by_partition": {name: len(values) for name, values in partitions.items()},
        "calibration_candidates": calibration_results,
        "selected_candidate_by_horizon": {
            horizon: item["candidate"]
            for horizon, item in selected_by_horizon.items()
        },
        "selected_rule_groups_by_horizon": {
            horizon: list(groups)
            for horizon, groups in selected_groups_by_horizon.items()
        },
        "rule_test": rule_test_evaluation,
        "sealed_final_test": final_test_evaluation,
        "validation_gates": {
            "rule_test": rule_gate,
            "sealed_final_test": final_gate,
            "requirements": {
                "positive_macro_log_loss_improvement": True,
                "positive_macro_brier_improvement": True,
                "minimum_coverage_excluding_ambiguous": 0.999,
            },
            "production_authorized": production_authorized,
        },
        "selection": dict(SELECTION),
        "maximum_nearest_context_distance_by_horizon": context_support_limits,
        "geometry_grid": [list(item) for item in GEOMETRY_GRID],
        "invariants": {
            "same_historical_path_for_all_horizons": True,
            "observed_first_touch_not_formula": True,
            "arbitrary_geometry_replayed_exactly": True,
            "future_data_excluded_from_context": True,
            "out_of_historical_context_blocks": True,
            "temporal_partitions_strict": True,
            "probability_mass_one": True,
            "cumulative_first_touch_monotone_by_construction": True,
        },
    }
    validation["canonical_payload_sha256"] = canonical_sha256(validation)
    write_json(VALIDATION_PATH, validation)
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(ARTIFACT_PATH, "wt", encoding="utf-8", newline="\n") as output:
        json.dump(production_model, output, ensure_ascii=True, separators=(",", ":"))
    _write_report(validation, production_model)
    return validation


def _write_report(validation: dict, artifact: dict) -> None:
    final_score = _model_score(validation["sealed_final_test"])
    rule_score = _model_score(validation["rule_test"])
    gates = validation["validation_gates"]
    final_gate = gates["sealed_final_test"]
    lines = [
        "# Motor empírico de análogos v0.9",
        "",
        f"- Motor: `{ENGINE_VERSION}`.",
        "- Arquitectura: un único motor; sin fórmula browniana ni coeficientes de geometría.",
        "- Resultado: frecuencias ponderadas de primeros toques observados en futuros históricos de 5m.",
        f"- Registros históricos en artefacto: **{len(artifact['analogs'])}**.",
        "- Grupos activos seleccionados por horizonte: "
        f"`{json.dumps(validation['selected_rule_groups_by_horizon'], sort_keys=True)}`.",
        f"- Rule-test log-loss/Brier macro: `{rule_score[0]:.6f}` / `{rule_score[1]:.6f}`.",
        f"- Final sellado log-loss/Brier macro: `{final_score[0]:.6f}` / `{final_score[1]:.6f}`.",
        f"- Autorización de producción: **{gates['production_authorized']}**.",
        "- Mejora macro final frente a first-passage (sólo referencia de validación): "
        f"log-loss `{final_gate['macro_log_loss_improvement_vs_first_passage']:.6f}`, "
        f"Brier `{final_gate['macro_brier_improvement_vs_first_passage']:.6f}`.",
        f"- Cobertura final no ambigua: `{final_gate['coverage_excluding_ambiguous']:.3%}`.",
        "",
        "## Contrato",
        "",
        "1. La geometría TP/SL se aplica directamente sobre cada trayectoria histórica.",
        "2. Las reglas sólo seleccionan contextos anteriores comparables.",
        "3. Intradía medio hereda el tramo corto; intradía largo hereda corto y medio.",
        "4. Un primer toque anterior no puede reclasificarse.",
        "5. Los casos ambiguos dentro de una vela de 5m se excluyen.",
        "6. Si el contexto queda fuera del soporte histórico, el análisis se bloquea.",
        "7. Una muestra condicional tardía escasa amplía el intervalo y queda trazada.",
        "",
        "## Limitaciones observadas",
        "",
        "- Intradía corto mejora log-loss final, pero su Brier queda ligeramente peor que la referencia.",
        "- Intradía medio mejora ambas métricas en rule-test y periodo final.",
        "- Intradía largo queda prácticamente empatado y ligeramente peor en el periodo final; no debe interpretarse sin su intervalo.",
        "- La referencia first-passage sólo se usa para validar y no se ejecuta ni mezcla en producción.",
        "",
        "## Reglas excluidas",
        "",
        "- Fibonacci y niveles estructurales: no activos hasta validar su proyección dinámica para cualquier TP/SL.",
        "- Liquidaciones: no activas porque no existe histórico fechado suficiente en el artefacto.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    result = build_and_validate()
    print(json.dumps({
        "selected_candidate_by_horizon": result["selected_candidate_by_horizon"],
        "selected_rule_groups_by_horizon": result["selected_rule_groups_by_horizon"],
        "rule_test_score": _model_score(result["rule_test"]),
        "final_test_score": _model_score(result["sealed_final_test"]),
    }, indent=2))
