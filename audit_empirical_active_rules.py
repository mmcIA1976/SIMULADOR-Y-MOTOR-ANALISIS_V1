from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import statistics
from collections import OrderedDict, defaultdict
from itertools import combinations
from pathlib import Path

from build_empirical_temporal_engine import (
    GEOMETRY_GRID,
    PARTITIONS,
    RANDOM_SEED,
    SELECTION,
    SIGNED_FEATURES,
    _raw_feature_map,
    _robust_scaling,
    _stratified_sample,
    _true_label,
    load_or_build_records,
)
from empirical_temporal_engine import (
    CONDITIONAL_CLASSES,
    CUMULATIVE_CLASSES,
    ENGINE_VERSION,
    STAGE_BOUNDS,
    _stage_label,
)
from multiscale_feature_runtime import STAGE_ORDER, STAGE_PROFILES
from sequential_first_touch_math import double_barrier_first_touch


ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = (
    ROOT
    / "auditorias_motor"
    / "empirical_active_rule_attribution_v0_2.json"
)
AUDIT_VERSION = "empirical-active-rule-attribution-v0.2"

# The four catalogued rules that currently define historical similarity, plus
# context_sigma.  The latter is evaluated explicitly because it changes the
# neighbors even though v0.9 did not expose it as an independently catalogued
# rule.
ACTIVE_COMPONENTS = OrderedDict(
    (
        (
            "M4-RULE-PATH-STRUCTURE-001",
            ("M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",),
        ),
        (
            "M4-RULE-MTF-HIERARCHY-001",
            (
                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
            ),
        ),
        (
            "M4-RULE-VOLATILITY-RANK-001",
            ("M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",),
        ),
        (
            "LIB-CAND-COMPRESSION-001",
            (
                "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
                "LIB-CAND-COMPRESSION-001::compression_vector.bollinger_width_rank",
            ),
        ),
        ("INTERNAL-CONTEXT-SIGMA", ("log_context_sigma",)),
    )
)

ACTIVE_FAMILIES = {
    "price_path": (
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-MTF-HIERARCHY-001",
    ),
    "volatility_context": (
        "M4-RULE-VOLATILITY-RANK-001",
        "LIB-CAND-COMPRESSION-001",
        "INTERNAL-CONTEXT-SIGMA",
    ),
}

# Atomic coordinates used by the production distance.  Keeping these separate
# from ACTIVE_COMPONENTS is important: the current model gives one distance
# dimension to every item below, so a two-coordinate rule has twice the raw
# representation capacity of a one-coordinate rule before any evidence-based
# weighting is learned.
ATOMIC_FEATURES = OrderedDict(
    (
        (
            "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
            {
                "rule_id": "M4-RULE-PATH-STRUCTURE-001",
                "formula": "side * sum(log_returns_H) / sum(abs(log_returns_H))",
                "expected_range": [-1.0, 1.0],
                "meaning": "directional efficiency of the price path over H",
            },
        ),
        (
            "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
            {
                "rule_id": "M4-RULE-MTF-HIERARCHY-001",
                "formula": "side * sum(log_returns_2H) / sum(abs(log_returns_2H))",
                "expected_range": [-1.0, 1.0],
                "meaning": "directional efficiency of the price path over 2H",
            },
        ),
        (
            "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
            {
                "rule_id": "M4-RULE-MTF-HIERARCHY-001",
                "formula": "side * sum(log_returns_4H) / sum(abs(log_returns_4H))",
                "expected_range": [-1.0, 1.0],
                "meaning": "directional efficiency of the price path over 4H",
            },
        ),
        (
            "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
            {
                "rule_id": "M4-RULE-VOLATILITY-RANK-001",
                "formula": "midrank(current_realized_variance, previous_60_H_windows)",
                "expected_range": [0.0, 1.0],
                "meaning": "relative volatility regime",
            },
        ),
        (
            "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
            {
                "rule_id": "LIB-CAND-COMPRESSION-001",
                "formula": "midrank(ATR14/price, previous_60_H-spaced anchors)",
                "expected_range": [0.0, 1.0],
                "meaning": "relative ATR expansion or compression",
            },
        ),
        (
            "LIB-CAND-COMPRESSION-001::compression_vector.bollinger_width_rank",
            {
                "rule_id": "LIB-CAND-COMPRESSION-001",
                "formula": "midrank(Bollinger20_2sigma_width/price, previous_60_H-spaced anchors)",
                "expected_range": [0.0, 1.0],
                "meaning": "relative Bollinger-band expansion or compression",
            },
        ),
        (
            "log_context_sigma",
            {
                "rule_id": "INTERNAL-CONTEXT-SIGMA",
                "formula": "log(realized_sigma_for_stage_horizon)",
                "expected_range": None,
                "meaning": "absolute volatility scale used as an uncatalogued context coordinate",
            },
        ),
    )
)

DIRECT_BIN_COUNT = 5

SAMPLE_PER_SYMBOL = {
    "calibration": 10,
    "rule_test": 20,
    "final_test": 30,
}
FIT_PARTITIONS = {
    "calibration": ("development",),
    "rule_test": ("development", "calibration"),
    "final_test": ("development", "calibration", "rule_test"),
}
DIRECTIONS = {0: "long", 1: "short"}
LABEL_CODE = {
    CONDITIONAL_CLASSES[0]: 0,
    CONDITIONAL_CLASSES[1]: 1,
    CONDITIONAL_CLASSES[2]: 2,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _variant_name(component_ids: tuple[str, ...]) -> str:
    ordered = tuple(item for item in ACTIVE_COMPONENTS if item in component_ids)
    total = len(ACTIVE_COMPONENTS)
    if not ordered:
        return "geometry"
    if len(ordered) == total:
        return "full"
    if len(ordered) == 1:
        return f"only::{ordered[0]}"
    if len(ordered) == 2:
        return f"pair::{ordered[0]}+{ordered[1]}"
    if len(ordered) == total - 1:
        missing = next(item for item in ACTIVE_COMPONENTS if item not in ordered)
        return f"without::{missing}"
    return "subset::" + "+".join(ordered)


def component_variants(*, include_pairs: bool = True) -> OrderedDict[str, tuple[str, ...]]:
    component_ids = tuple(ACTIVE_COMPONENTS)
    variants: OrderedDict[str, tuple[str, ...]] = OrderedDict()
    sizes = range(1, len(component_ids) + 1) if include_pairs else (1, len(component_ids) - 1, len(component_ids))
    for size in sizes:
        for selected in combinations(component_ids, size):
            variants[_variant_name(selected)] = selected
    return variants


def expanded_feature_names(horizon: str) -> list[str]:
    stages = STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
    return [
        f"{stage}::{feature}"
        for stage in stages
        for features in ACTIVE_COMPONENTS.values()
        for feature in features
    ]


def expanded_component_indices(horizon: str) -> dict[str, list[int]]:
    names = expanded_feature_names(horizon)
    result = {}
    for component_id, features in ACTIVE_COMPONENTS.items():
        suffixes = {f"::{feature}" for feature in features}
        result[component_id] = [
            index
            for index, name in enumerate(names)
            if any(name.endswith(suffix) for suffix in suffixes)
        ]
    if set(index for values in result.values() for index in values) != set(range(len(names))):
        raise RuntimeError(f"active_component_feature_partition_invalid:{horizon}")
    return result


def expanded_atomic_indices(horizon: str) -> dict[str, int]:
    names = expanded_feature_names(horizon)
    result = {name: index for index, name in enumerate(names)}
    if len(result) != len(names):
        raise RuntimeError(f"active_atomic_feature_duplicate:{horizon}")
    expected_suffixes = set(ATOMIC_FEATURES)
    actual_suffixes = {name.split("::", 1)[1] for name in names}
    if actual_suffixes != expected_suffixes:
        raise RuntimeError(f"active_atomic_feature_schema_invalid:{horizon}")
    return result


def _atomic_variant_name(feature_name: str) -> str:
    return f"without_feature::{feature_name}"


def classify_replication(
    rule_test_delta: dict,
    final_test_delta: dict,
    *,
    minimum_units: int = 50,
) -> str:
    if min(
        int(rule_test_delta.get("independent_units") or 0),
        int(final_test_delta.get("independent_units") or 0),
    ) < minimum_units:
        return "insufficient_evidence"
    values = (
        float(rule_test_delta["log_loss"]),
        float(rule_test_delta["brier"]),
        float(final_test_delta["log_loss"]),
        float(final_test_delta["brier"]),
    )
    intervals = (
        rule_test_delta["log_loss_ci95"],
        rule_test_delta["brier_ci95"],
        final_test_delta["log_loss_ci95"],
        final_test_delta["brier_ci95"],
    )
    if all(value > 0.0 for value in values):
        if all(float(interval[0]) > 0.0 for interval in intervals):
            return "helpful_confirmed"
        return "helpful_consistent_but_uncertain"
    if all(value < 0.0 for value in values):
        if all(float(interval[1]) < 0.0 for interval in intervals):
            return "harmful_confirmed"
        return "harmful_consistent_but_uncertain"
    return "mixed_or_unstable"


def _paired_summary(left: list[tuple[float, float]], right: list[tuple[float, float]]) -> dict:
    if len(left) != len(right):
        raise RuntimeError("paired_metric_length_mismatch")
    if not left:
        return {
            "independent_units": 0,
            "log_loss": None,
            "brier": None,
            "log_loss_ci95": None,
            "brier_ci95": None,
        }

    # Positive means that `right` improves on `left`: loss(left)-loss(right).
    return _delta_summary(
        [a[0] - b[0] for a, b in zip(left, right)],
        [a[1] - b[1] for a, b in zip(left, right)],
    )


def _delta_summary(log_deltas: list[float], brier_deltas: list[float]) -> dict:
    if len(log_deltas) != len(brier_deltas):
        raise RuntimeError("delta_metric_length_mismatch")
    if not log_deltas:
        return {
            "independent_units": 0,
            "log_loss": None,
            "brier": None,
            "log_loss_ci95": None,
            "brier_ci95": None,
        }

    def interval(values: list[float]) -> list[float]:
        mean = statistics.fmean(values)
        if len(values) < 2:
            return [mean, mean]
        error = statistics.stdev(values) / math.sqrt(len(values))
        return [mean - 1.96 * error, mean + 1.96 * error]

    return {
        "independent_units": len(log_deltas),
        "log_loss": statistics.fmean(log_deltas),
        "brier": statistics.fmean(brier_deltas),
        "log_loss_ci95": interval(log_deltas),
        "brier_ci95": interval(brier_deltas),
    }


def _metrics(units: list[tuple[float, float]], prediction_count: int) -> dict:
    if not units:
        return {
            "independent_units": 0,
            "predictions": 0,
            "log_loss": None,
            "brier": None,
        }
    return {
        "independent_units": len(units),
        "predictions": int(prediction_count),
        "log_loss": statistics.fmean(value[0] for value in units),
        "brier": statistics.fmean(value[1] for value in units),
    }


def _load_numpy():
    try:
        import numpy  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "numpy_required_for_offline_attribution; use the bundled Codex Python runtime"
        ) from exc
    return numpy


def _standardized_training_matrix(np, records: list[dict], horizon: str):
    names = expanded_feature_names(horizon)
    scaling = _robust_scaling(records, {horizon: names})[horizon]
    rows = []
    symbols = []
    analog_records = []
    orientations = []
    frontiers = []
    for record in records:
        values_by_orientation = (
            _raw_feature_map(record, horizon, 0),
            _raw_feature_map(record, horizon, 1),
        )
        for orientation, values in enumerate(values_by_orientation):
            rows.append(
                [
                    (float(values[name]) - float(center)) / float(scale)
                    for name, (center, scale) in zip(names, scaling)
                ]
            )
            symbols.append(str(record["symbol"]))
            analog_records.append(record)
            orientations.append(orientation)
            favorable = (
                record["up_frontier"] if orientation == 0 else record["down_frontier"]
            )
            adverse = (
                record["down_frontier"] if orientation == 0 else record["up_frontier"]
            )
            frontiers.append(
                (
                    tuple(float(item[0]) for item in favorable),
                    tuple(int(item[1]) for item in favorable),
                    tuple(float(item[0]) for item in adverse),
                    tuple(int(item[1]) for item in adverse),
                )
            )
    return {
        "names": names,
        "scaling": scaling,
        "matrix": np.asarray(rows, dtype=np.float64),
        "symbols": np.asarray(symbols, dtype=object),
        "records": analog_records,
        "orientations": orientations,
        "frontiers": frontiers,
        "component_indices": expanded_component_indices(horizon),
    }


def _query_vector(np, record: dict, orientation: int, horizon: str, prepared: dict):
    values = _raw_feature_map(record, horizon, orientation)
    return np.asarray(
        [
            (float(values[name]) - float(center)) / float(scale)
            for name, (center, scale) in zip(
                prepared["names"], prepared["scaling"]
            )
        ],
        dtype=np.float64,
    )


def _conditional_label_matrices(np, prepared: dict, base_sigma: float):
    multiples = sorted(
        {float(value) for geometry in GEOMETRY_GRID for value in geometry}
    )
    multiple_index = {value: index for index, value in enumerate(multiples)}
    infinity = 10**9
    favorable_steps = np.full(
        (len(prepared["frontiers"]), len(multiples)),
        infinity,
        dtype=np.int32,
    )
    adverse_steps = np.full_like(favorable_steps, infinity)
    thresholds = [multiple * float(base_sigma) for multiple in multiples]
    for row_index, (fav_levels, fav_steps, adv_levels, adv_steps) in enumerate(
        prepared["frontiers"]
    ):
        for threshold_index, threshold in enumerate(thresholds):
            fav_index = bisect.bisect_left(fav_levels, threshold)
            if fav_index < len(fav_steps):
                favorable_steps[row_index, threshold_index] = fav_steps[fav_index]
            adv_index = bisect.bisect_left(adv_levels, threshold)
            if adv_index < len(adv_steps):
                adverse_steps[row_index, threshold_index] = adv_steps[adv_index]

    result = {}
    for horizon in STAGE_ORDER:
        start_step, end_step = STAGE_BOUNDS[horizon]
        matrix = np.full(
            (len(GEOMETRY_GRID), len(prepared["frontiers"])),
            -1,
            dtype=np.int8,
        )
        for geometry_index, (tp_multiple, sl_multiple) in enumerate(GEOMETRY_GRID):
            tp_steps = favorable_steps[:, multiple_index[float(tp_multiple)]]
            sl_steps = adverse_steps[:, multiple_index[float(sl_multiple)]]
            first_steps = np.minimum(tp_steps, sl_steps)
            surviving = first_steps > int(start_step)
            unresolved = surviving & (first_steps > int(end_step))
            resolved = surviving & ~unresolved & (tp_steps != sl_steps)
            matrix[geometry_index, unresolved] = LABEL_CODE[CONDITIONAL_CLASSES[2]]
            matrix[geometry_index, resolved & (tp_steps == first_steps)] = LABEL_CODE[
                CONDITIONAL_CLASSES[0]
            ]
            matrix[geometry_index, resolved & (sl_steps == first_steps)] = LABEL_CODE[
                CONDITIONAL_CLASSES[1]
            ]
        result[horizon] = matrix
    return result


def _rank_indices(np, distances, labels):
    total = int(distances.shape[0])
    candidate_count = min(total, max(1024, int(SELECTION["neighbor_count"]) * 4))
    while True:
        if candidate_count >= total:
            indices = np.argsort(distances, kind="stable")
        else:
            partial = np.argpartition(distances, candidate_count - 1)[:candidate_count]
            indices = partial[np.argsort(distances[partial], kind="stable")]
        enough = all(
            int(np.count_nonzero(row[indices] >= 0)) >= int(SELECTION["neighbor_count"])
            for row in labels
        )
        if enough or candidate_count >= total:
            return indices
        candidate_count = min(total, candidate_count * 2)


def _conditional_probabilities(np, ordered_indices, distances, labels):
    result = []
    target = int(SELECTION["neighbor_count"])
    temperature = float(SELECTION["probability_temperature"])
    for label_row in labels:
        eligible = ordered_indices[label_row[ordered_indices] >= 0][:target]
        if not len(eligible):
            result.append(None)
            continue
        chosen_distances = distances[eligible]
        bandwidth = max(0.25, float(chosen_distances[-1]))
        weights = np.exp(-0.5 * (chosen_distances / bandwidth) ** 2)
        counts = np.bincount(
            label_row[eligible],
            weights=weights,
            minlength=3,
        ).astype(np.float64)
        probabilities = (counts + 0.5) / (float(counts.sum()) + 1.5)
        probabilities = probabilities ** (1.0 / temperature)
        probabilities /= probabilities.sum()
        result.append(probabilities)
    return result


def _geometry_baseline(record: dict, horizon: str, tp_multiple: float, sl_multiple: float):
    cumulative_variance = 0.0
    for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]:
        profile = STAGE_PROFILES[stage]
        sigma = float(record["stage_sigmas"][stage])
        cumulative_variance += sigma * sigma * (
            float(profile["increment_seconds"]) / float(profile["horizon_seconds"])
        )
    base_sigma = float(record["stage_sigmas"]["intraday_short"])
    result = double_barrier_first_touch(
        tp_log_distance=float(tp_multiple) * base_sigma,
        sl_log_distance=float(sl_multiple) * base_sigma,
        sigma_horizon=math.sqrt(cumulative_variance),
        time_fraction=1.0,
    )
    return (float(result.p_tp), float(result.p_sl), float(result.p_expiry))


def _loss(probabilities, label_index: int) -> tuple[float, float]:
    values = [float(value) for value in probabilities]
    return (
        -math.log(max(values[label_index], 1e-15)),
        math.fsum(
            (value - (1.0 if index == label_index else 0.0)) ** 2
            for index, value in enumerate(values)
        ),
    )


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile_values_empty")
    position = (len(ordered) - 1) * float(probability)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _quantile_boundaries(values: list[float], bin_count: int = DIRECT_BIN_COUNT) -> list[float]:
    boundaries = [
        _quantile(values, index / bin_count) for index in range(1, bin_count)
    ]
    # Repeated ranks are common. Removing duplicate boundaries avoids creating
    # empty bins while keeping the transformation deterministic.
    return list(dict.fromkeys(boundaries))


def _smoothed_probabilities(counts) -> tuple[float, float, float]:
    values = [float(value) for value in counts]
    denominator = math.fsum(values) + 1.5
    return tuple((value + 0.5) / denominator for value in values)


def _profile(values: list[float]) -> dict:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "finite": 0}
    return {
        "count": len(values),
        "finite": len(finite),
        "minimum": min(finite),
        "p05": _quantile(finite, 0.05),
        "median": _quantile(finite, 0.50),
        "p95": _quantile(finite, 0.95),
        "maximum": max(finite),
        "unique": len(set(finite)),
    }


def semantic_feature_audit(records: list[dict]) -> dict:
    result = {}
    for stage in STAGE_ORDER:
        result[stage] = {}
        long_maps = [_raw_feature_map(record, stage, 0) for record in records]
        short_maps = [_raw_feature_map(record, stage, 1) for record in records]
        for feature_suffix, contract in ATOMIC_FEATURES.items():
            expanded = f"{stage}::{feature_suffix}"
            long_values = [values[expanded] for values in long_maps]
            short_values = [values[expanded] for values in short_maps]
            expected = (
                [-value for value in long_values]
                if feature_suffix in SIGNED_FEATURES
                else list(long_values)
            )
            transform_error = max(
                (abs(actual - wanted) for actual, wanted in zip(short_values, expected)),
                default=0.0,
            )
            expected_range = contract["expected_range"]
            range_violations = 0
            if expected_range is not None:
                lower, upper = expected_range
                range_violations = sum(
                    value < lower - 1e-12 or value > upper + 1e-12
                    for value in (*long_values, *short_values)
                )
            result[stage][feature_suffix] = {
                "contract": contract,
                "long_profile": _profile(long_values),
                "short_profile": _profile(short_values),
                "side_transform": (
                    "short_equals_negative_long"
                    if feature_suffix in SIGNED_FEATURES
                    else "short_equals_long"
                ),
                "maximum_side_transform_error": transform_error,
                "expected_range_violations": range_violations,
                "semantic_contract_passed": (
                    transform_error <= 1e-12 and range_violations == 0
                ),
            }
    return result


def evaluate_direct_feature_relationships(
    *,
    partition_name: str,
    fit_records: list[dict],
    evaluation_records: list[dict],
) -> dict:
    """Measure each coordinate without nearest-neighbour selection.

    The diagnostic model learns geometry-conditioned outcome frequencies in
    chronological training-only quintiles of one feature.  Its held-out loss is
    compared with the same empirical geometry frequencies without that feature.
    This does not make the diagnostic model a production candidate; it answers
    the narrower question of whether the raw calculation contains repeatable
    outcome information before it is used to define similarity.
    """

    baseline_units = defaultdict(lambda: [0.0, 0.0, 0])
    feature_units = defaultdict(lambda: [0.0, 0.0, 0])
    prediction_counts = defaultdict(int)
    models = {}
    profile_counts = {}

    for horizon in STAGE_ORDER:
        features = expanded_feature_names(horizon)
        models[horizon] = {}
        profile_counts[horizon] = {}
        for orientation, direction in DIRECTIONS.items():
            fit_maps = [
                _raw_feature_map(record, horizon, orientation)
                for record in fit_records
            ]
            boundaries = {
                feature: _quantile_boundaries(
                    [float(values[feature]) for values in fit_maps]
                )
                for feature in features
            }
            baseline_counts = [[0, 0, 0] for _ in GEOMETRY_GRID]
            binned_counts = {
                feature: [
                    [
                        [0, 0, 0]
                        for _ in range(len(boundaries[feature]) + 1)
                    ]
                    for _ in GEOMETRY_GRID
                ]
                for feature in features
            }
            for record, feature_map in zip(fit_records, fit_maps):
                base_sigma = float(record["stage_sigmas"]["intraday_short"])
                feature_bins = {
                    feature: bisect.bisect_right(
                        boundaries[feature], float(feature_map[feature])
                    )
                    for feature in features
                }
                for geometry_index, (tp_multiple, sl_multiple) in enumerate(
                    GEOMETRY_GRID
                ):
                    label = _true_label(
                        record,
                        orientation,
                        float(tp_multiple) * base_sigma,
                        float(sl_multiple) * base_sigma,
                        horizon,
                    )
                    if label is None:
                        continue
                    label_index = CUMULATIVE_CLASSES.index(label)
                    baseline_counts[geometry_index][label_index] += 1
                    for feature in features:
                        binned_counts[feature][geometry_index][
                            feature_bins[feature]
                        ][label_index] += 1

            models[horizon][direction] = {
                "boundaries": boundaries,
                "baseline_probabilities": [
                    _smoothed_probabilities(counts) for counts in baseline_counts
                ],
                "feature_probabilities": {
                    feature: [
                        [_smoothed_probabilities(counts) for counts in geometry]
                        for geometry in feature_geometries
                    ]
                    for feature, feature_geometries in binned_counts.items()
                },
            }
            profile_counts[horizon][direction] = {
                feature: [
                    [0, 0, 0] for _ in range(len(boundaries[feature]) + 1)
                ]
                for feature in features
            }

    for record in evaluation_records:
        unit_id = str(record["id"])
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        for horizon in STAGE_ORDER:
            features = expanded_feature_names(horizon)
            for orientation, direction in DIRECTIONS.items():
                feature_map = _raw_feature_map(record, horizon, orientation)
                model = models[horizon][direction]
                feature_bins = {
                    feature: bisect.bisect_right(
                        model["boundaries"][feature], float(feature_map[feature])
                    )
                    for feature in features
                }
                for geometry_index, (tp_multiple, sl_multiple) in enumerate(
                    GEOMETRY_GRID
                ):
                    label = _true_label(
                        record,
                        orientation,
                        float(tp_multiple) * base_sigma,
                        float(sl_multiple) * base_sigma,
                        horizon,
                    )
                    if label is None:
                        continue
                    label_index = CUMULATIVE_CLASSES.index(label)
                    baseline_loss = _loss(
                        model["baseline_probabilities"][geometry_index], label_index
                    )
                    baseline_key = (horizon, direction, unit_id)
                    baseline_units[baseline_key][0] += baseline_loss[0]
                    baseline_units[baseline_key][1] += baseline_loss[1]
                    baseline_units[baseline_key][2] += 1
                    for feature in features:
                        bin_index = feature_bins[feature]
                        probabilities = model["feature_probabilities"][feature][
                            geometry_index
                        ][bin_index]
                        predicted_loss = _loss(probabilities, label_index)
                        key = (horizon, feature, direction, unit_id)
                        feature_units[key][0] += predicted_loss[0]
                        feature_units[key][1] += predicted_loss[1]
                        feature_units[key][2] += 1
                        prediction_counts[(horizon, feature, direction)] += 1
                        profile_counts[horizon][direction][feature][bin_index][
                            label_index
                        ] += 1

    result = {}
    for horizon in STAGE_ORDER:
        result[horizon] = {}
        for feature in expanded_feature_names(horizon):
            result[horizon][feature] = {}
            for direction in DIRECTIONS.values():
                baseline_map = {
                    unit_id: (log_sum / count, brier_sum / count)
                    for (item_horizon, item_direction, unit_id), (
                        log_sum,
                        brier_sum,
                        count,
                    ) in baseline_units.items()
                    if item_horizon == horizon and item_direction == direction
                }
                feature_map = {
                    unit_id: (log_sum / count, brier_sum / count)
                    for (
                        item_horizon,
                        item_feature,
                        item_direction,
                        unit_id,
                    ), (log_sum, brier_sum, count) in feature_units.items()
                    if item_horizon == horizon
                    and item_feature == feature
                    and item_direction == direction
                }
                shared = sorted(set(baseline_map) & set(feature_map))
                bin_profiles = []
                boundaries = models[horizon][direction]["boundaries"][feature]
                for index, counts in enumerate(
                    profile_counts[horizon][direction][feature]
                ):
                    total = sum(counts)
                    bin_profiles.append(
                        {
                            "bin": index,
                            "lower_exclusive": (
                                boundaries[index - 1] if index else None
                            ),
                            "upper_inclusive": (
                                boundaries[index] if index < len(boundaries) else None
                            ),
                            "outcome_predictions": total,
                            "outcome_counts": {
                                label: int(counts[label_index])
                                for label_index, label in enumerate(CUMULATIVE_CLASSES)
                            },
                            "outcome_rates": {
                                label: (
                                    float(counts[label_index]) / total if total else None
                                )
                                for label_index, label in enumerate(CUMULATIVE_CLASSES)
                            },
                        }
                    )
                result[horizon][feature][direction] = {
                    "direct_vs_empirical_geometry": _paired_summary(
                        [baseline_map[key] for key in shared],
                        [feature_map[key] for key in shared],
                    ),
                    "predictions": prediction_counts[(horizon, feature, direction)],
                    "training_boundaries": boundaries,
                    "held_out_bin_profiles": bin_profiles,
                }
    return {
        "partition": partition_name,
        "fit_records": len(fit_records),
        "evaluation_records": len(evaluation_records),
        "bin_count_target": DIRECT_BIN_COUNT,
        "smoothing": "Jeffreys Dirichlet prior 0.5 per outcome class",
        "baseline": "training-only empirical outcome rate by horizon, side and TP/SL geometry",
        "results": result,
    }


def evaluate_partition(
    *,
    partition_name: str,
    fit_records: list[dict],
    evaluation_records: list[dict],
    variants: OrderedDict[str, tuple[str, ...]],
) -> dict:
    np = _load_numpy()
    sample = _stratified_sample(
        evaluation_records,
        SAMPLE_PER_SYMBOL[partition_name],
        RANDOM_SEED
        + {"calibration": 2, "rule_test": 100, "final_test": 200}[partition_name],
    )
    prepared = {
        horizon: _standardized_training_matrix(np, fit_records, horizon)
        for horizon in STAGE_ORDER
    }
    atomic_features = tuple(expanded_feature_names(STAGE_ORDER[-1]))
    atomic_variants = OrderedDict(
        (_atomic_variant_name(feature), feature) for feature in atomic_features
    )
    evaluated_variant_names = (*variants, *atomic_variants)
    unit_sums = defaultdict(lambda: [0.0, 0.0, 0])
    prediction_counts = defaultdict(int)
    directional_counts = defaultdict(
        lambda: {
            "eligible_pairs": 0,
            "correct_score": 0.0,
            "ties": 0,
            "chosen_long": 0,
            "actual_long": 0,
        }
    )
    total_queries = len(sample) * 2
    for record_index, record in enumerate(sample, 1):
        if record_index == 1 or record_index % 10 == 0 or record_index == len(sample):
            print(
                f"ATTRIBUTION_PROGRESS partition={partition_name} records={record_index}/{len(sample)}",
                flush=True,
            )
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        label_matrices = _conditional_label_matrices(
            np,
            prepared["intraday_short"],
            base_sigma,
        )
        direction_observations = {}
        for orientation in (0, 1):
            direction = DIRECTIONS[orientation]
            cumulative = {
                name: np.tile(
                    np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
                    (len(GEOMETRY_GRID), 1),
                )
                for name in evaluated_variant_names
            }
            survival = {
                name: np.ones(len(GEOMETRY_GRID), dtype=np.float64)
                for name in evaluated_variant_names
            }

            def accumulate(variant_name: str, conditional) -> None:
                for geometry_index, probabilities in enumerate(conditional):
                    if probabilities is None:
                        continue
                    previous_survival = survival[variant_name][geometry_index]
                    cumulative[variant_name][geometry_index, 0] += (
                        previous_survival * probabilities[0]
                    )
                    cumulative[variant_name][geometry_index, 1] += (
                        previous_survival * probabilities[1]
                    )
                    survival[variant_name][geometry_index] *= probabilities[2]
                    cumulative[variant_name][geometry_index, 2] = survival[
                        variant_name
                    ][geometry_index]

            for horizon in STAGE_ORDER:
                stage = prepared[horizon]
                query = _query_vector(np, record, orientation, horizon, stage)
                component_sums = {}
                for component_id, indices in stage["component_indices"].items():
                    differences = stage["matrix"][:, indices] - query[indices]
                    component_sums[component_id] = np.minimum(
                        36.0, differences * differences
                    ).sum(axis=1)
                symbol_penalty = np.where(
                    stage["symbols"] == str(record["symbol"]),
                    0.0,
                    float(SELECTION["cross_symbol_penalty"]),
                )
                labels = label_matrices[horizon]
                full_conditional = None
                for variant_name, component_ids in variants.items():
                    squared = sum(component_sums[name] for name in component_ids)
                    dimensions = sum(
                        len(stage["component_indices"][name]) for name in component_ids
                    )
                    distances = np.sqrt(squared / dimensions) + symbol_penalty
                    order = _rank_indices(np, distances, labels)
                    conditional = _conditional_probabilities(
                        np, order, distances, labels
                    )
                    accumulate(variant_name, conditional)
                    if variant_name == "full":
                        full_conditional = conditional

                if full_conditional is None:
                    raise RuntimeError("full_variant_missing")
                full_squared = sum(component_sums.values())
                full_dimensions = len(stage["names"])
                atomic_indices = expanded_atomic_indices(horizon)
                for variant_name, feature_name in atomic_variants.items():
                    feature_index = atomic_indices.get(feature_name)
                    if feature_index is None:
                        # The feature belongs to a later temporal stage. Until
                        # that stage is reached, this ablation is identical to
                        # the full production context.
                        conditional = full_conditional
                    else:
                        differences = (
                            stage["matrix"][:, feature_index] - query[feature_index]
                        )
                        feature_squared = np.minimum(36.0, differences * differences)
                        squared = np.maximum(0.0, full_squared - feature_squared)
                        dimensions = full_dimensions - 1
                        distances = np.sqrt(squared / dimensions) + symbol_penalty
                        order = _rank_indices(np, distances, labels)
                        conditional = _conditional_probabilities(
                            np, order, distances, labels
                        )
                    accumulate(variant_name, conditional)

                for geometry_index, (tp_multiple, sl_multiple) in enumerate(
                    GEOMETRY_GRID
                ):
                    true_label = _true_label(
                        record,
                        orientation,
                        float(tp_multiple) * base_sigma,
                        float(sl_multiple) * base_sigma,
                        horizon,
                    )
                    if true_label is None:
                        continue
                    label_index = CUMULATIVE_CLASSES.index(true_label)
                    unit_key = f"{record['id']}::{direction}"
                    baseline_probabilities = _geometry_baseline(
                        record,
                        horizon,
                        tp_multiple,
                        sl_multiple,
                    )
                    baseline_loss = _loss(baseline_probabilities, label_index)
                    baseline_key = ("geometry", horizon, direction, unit_key)
                    unit_sums[baseline_key][0] += baseline_loss[0]
                    unit_sums[baseline_key][1] += baseline_loss[1]
                    unit_sums[baseline_key][2] += 1
                    prediction_counts[("geometry", horizon, direction)] += 1
                    direction_observations[
                        ("geometry", horizon, geometry_index, orientation)
                    ] = (
                        baseline_probabilities[0] - baseline_probabilities[1],
                        label_index,
                        baseline_loss,
                    )
                    for variant_name in evaluated_variant_names:
                        values = cumulative[variant_name][geometry_index]
                        total = float(values.sum())
                        probabilities = values / total
                        predicted_loss = _loss(probabilities, label_index)
                        key = (variant_name, horizon, direction, unit_key)
                        unit_sums[key][0] += predicted_loss[0]
                        unit_sums[key][1] += predicted_loss[1]
                        unit_sums[key][2] += 1
                        prediction_counts[(variant_name, horizon, direction)] += 1
                        direction_observations[
                            (variant_name, horizon, geometry_index, orientation)
                        ] = (
                            float(probabilities[0] - probabilities[1]),
                            label_index,
                            predicted_loss,
                        )

        symmetric_geometries = {
            index
            for index, (tp_multiple, sl_multiple) in enumerate(GEOMETRY_GRID)
            if float(tp_multiple) == float(sl_multiple)
        }
        for variant_name in ("geometry", *evaluated_variant_names):
            for horizon in STAGE_ORDER:
                for geometry_index in symmetric_geometries:
                    long_item = direction_observations.get(
                        (variant_name, horizon, geometry_index, 0)
                    )
                    short_item = direction_observations.get(
                        (variant_name, horizon, geometry_index, 1)
                    )
                    if not long_item or not short_item:
                        continue
                    long_label = int(long_item[1])
                    short_label = int(short_item[1])
                    if {long_label, short_label} != {0, 1}:
                        continue
                    counts = directional_counts[(variant_name, horizon)]
                    counts["eligible_pairs"] += 1
                    actual_long = long_label == 0
                    counts["actual_long"] += int(actual_long)
                    long_score = float(long_item[0])
                    short_score = float(short_item[0])
                    if abs(long_score - short_score) <= 1e-15:
                        counts["ties"] += 1
                        counts["correct_score"] += 0.5
                    else:
                        chosen_long = long_score > short_score
                        counts["chosen_long"] += int(chosen_long)
                        counts["correct_score"] += float(chosen_long == actual_long)

    unit_metrics = defaultdict(dict)
    for (variant, horizon, direction, unit_key), (log_sum, brier_sum, count) in unit_sums.items():
        unit_metrics[(variant, horizon, direction)][unit_key] = (
            log_sum / count,
            brier_sum / count,
        )

    summaries = {}
    for variant in ("geometry", *variants):
        summaries[variant] = {}
        for horizon in STAGE_ORDER:
            summaries[variant][horizon] = {}
            for direction in DIRECTIONS.values():
                values = list(unit_metrics[(variant, horizon, direction)].values())
                summaries[variant][horizon][direction] = _metrics(
                    values,
                    prediction_counts[(variant, horizon, direction)],
                )

    directional_selection = {}
    for variant in ("geometry", *evaluated_variant_names):
        directional_selection[variant] = {}
        for horizon in STAGE_ORDER:
            counts = directional_counts[(variant, horizon)]
            eligible = int(counts["eligible_pairs"])
            directional_selection[variant][horizon] = {
                **counts,
                "accuracy": (
                    float(counts["correct_score"]) / eligible if eligible else None
                ),
                "chosen_long_rate": (
                    float(counts["chosen_long"]) / (eligible - int(counts["ties"]))
                    if eligible > int(counts["ties"])
                    else None
                ),
                "actual_long_rate": (
                    float(counts["actual_long"]) / eligible if eligible else None
                ),
            }

    def paired(left_variant: str, right_variant: str, horizon: str, direction: str):
        left_map = unit_metrics[(left_variant, horizon, direction)]
        right_map = unit_metrics[(right_variant, horizon, direction)]
        shared = sorted(set(left_map) & set(right_map))
        return _paired_summary(
            [left_map[key] for key in shared],
            [right_map[key] for key in shared],
        )

    individual = {}
    for component_id in ACTIVE_COMPONENTS:
        individual[component_id] = {}
        for horizon in STAGE_ORDER:
            individual[component_id][horizon] = {}
            for direction in DIRECTIONS.values():
                individual[component_id][horizon][direction] = {
                    "standalone_vs_geometry": paired(
                        "geometry", f"only::{component_id}", horizon, direction
                    ),
                    "marginal_in_full": paired(
                        f"without::{component_id}", "full", horizon, direction
                    ),
                }

    atomic_feature_marginal = {}
    for horizon in STAGE_ORDER:
        atomic_feature_marginal[horizon] = {}
        for feature_name in expanded_feature_names(horizon):
            atomic_feature_marginal[horizon][feature_name] = {}
            variant_name = _atomic_variant_name(feature_name)
            for direction in DIRECTIONS.values():
                atomic_feature_marginal[horizon][feature_name][direction] = {
                    "marginal_in_full": paired(
                        variant_name, "full", horizon, direction
                    ),
                    "directional_selection": {
                        "full_accuracy": directional_selection["full"][horizon][
                            "accuracy"
                        ],
                        "without_feature_accuracy": directional_selection[
                            variant_name
                        ][horizon]["accuracy"],
                    },
                }

    shapley = {}
    all_components = tuple(ACTIVE_COMPONENTS)
    factorial = math.factorial
    denominator = factorial(len(all_components))
    for component_id in all_components:
        shapley[component_id] = {}
        others = tuple(item for item in all_components if item != component_id)
        for horizon in STAGE_ORDER:
            shapley[component_id][horizon] = {}
            for direction in DIRECTIONS.values():
                common_units = set(
                    unit_metrics[("geometry", horizon, direction)]
                )
                for variant_name in variants:
                    common_units &= set(
                        unit_metrics[(variant_name, horizon, direction)]
                    )
                log_values = []
                brier_values = []
                for unit_key in sorted(common_units):
                    log_contribution = 0.0
                    brier_contribution = 0.0
                    for size in range(len(others) + 1):
                        weight = (
                            factorial(size)
                            * factorial(len(all_components) - size - 1)
                            / denominator
                        )
                        for coalition in combinations(others, size):
                            left_name = _variant_name(tuple(coalition))
                            right_name = _variant_name(
                                tuple(coalition) + (component_id,)
                            )
                            left_metric = unit_metrics[
                                (left_name, horizon, direction)
                            ][unit_key]
                            right_metric = unit_metrics[
                                (right_name, horizon, direction)
                            ][unit_key]
                            log_contribution += weight * (
                                left_metric[0] - right_metric[0]
                            )
                            brier_contribution += weight * (
                                left_metric[1] - right_metric[1]
                            )
                    log_values.append(log_contribution)
                    brier_values.append(brier_contribution)
                shapley[component_id][horizon][direction] = _delta_summary(
                    log_values,
                    brier_values,
                )

    interactions = {}
    for left, right in combinations(ACTIVE_COMPONENTS, 2):
        pair_name = f"pair::{left}+{right}"
        interactions[f"{left}+{right}"] = {}
        for horizon in STAGE_ORDER:
            interactions[f"{left}+{right}"][horizon] = {}
            for direction in DIRECTIONS.values():
                pair_gain = paired("geometry", pair_name, horizon, direction)
                left_gain = paired(
                    "geometry", f"only::{left}", horizon, direction
                )
                right_gain = paired(
                    "geometry", f"only::{right}", horizon, direction
                )
                interactions[f"{left}+{right}"][horizon][direction] = {
                    "pair_vs_geometry": pair_gain,
                    "pair_vs_left_only": paired(
                        f"only::{left}", pair_name, horizon, direction
                    ),
                    "pair_vs_right_only": paired(
                        f"only::{right}", pair_name, horizon, direction
                    ),
                    "incremental_over_best_single": {
                        "independent_units": pair_gain["independent_units"],
                        "log_loss": pair_gain["log_loss"]
                        - max(left_gain["log_loss"], right_gain["log_loss"]),
                        "brier": pair_gain["brier"]
                        - max(left_gain["brier"], right_gain["brier"]),
                    },
                    "excess_over_additive": {
                        "independent_units": pair_gain["independent_units"],
                        "log_loss": pair_gain["log_loss"]
                        - left_gain["log_loss"]
                        - right_gain["log_loss"],
                        "brier": pair_gain["brier"]
                        - left_gain["brier"]
                        - right_gain["brier"],
                    },
                }

    family_interaction = {}
    left_family, right_family = tuple(ACTIVE_FAMILIES)
    left_name = _variant_name(ACTIVE_FAMILIES[left_family])
    right_name = _variant_name(ACTIVE_FAMILIES[right_family])
    for horizon in STAGE_ORDER:
        family_interaction[horizon] = {}
        for direction in DIRECTIONS.values():
            maps = {
                name: unit_metrics[(name, horizon, direction)]
                for name in ("geometry", left_name, right_name, "full")
            }
            shared = sorted(set.intersection(*(set(value) for value in maps.values())))
            log_excess = []
            brier_excess = []
            for unit_key in shared:
                geometry_metric = maps["geometry"][unit_key]
                left_metric = maps[left_name][unit_key]
                right_metric = maps[right_name][unit_key]
                full_metric = maps["full"][unit_key]
                # v(full)-v(left)-v(right), where v(S)=loss(geometry)-loss(S).
                log_excess.append(
                    left_metric[0]
                    + right_metric[0]
                    - full_metric[0]
                    - geometry_metric[0]
                )
                brier_excess.append(
                    left_metric[1]
                    + right_metric[1]
                    - full_metric[1]
                    - geometry_metric[1]
                )
            family_interaction[horizon][direction] = {
                "joint_vs_price_path_family": paired(
                    left_name, "full", horizon, direction
                ),
                "joint_vs_volatility_context_family": paired(
                    right_name, "full", horizon, direction
                ),
                "interaction_excess_over_additive": _delta_summary(
                    log_excess, brier_excess
                ),
            }

    return {
        "fit_records": len(fit_records),
        "evaluation_records_available": len(evaluation_records),
        "sample_records": len(sample),
        "sample_orientations": total_queries,
        "summaries": summaries,
        "directional_selection": directional_selection,
        "individual": individual,
        "atomic_feature_marginal": atomic_feature_marginal,
        "shapley_attribution": shapley,
        "interactions": interactions,
        "family_interaction": family_interaction,
    }


def _replication_matrix(partition_results: dict) -> dict:
    result = {}
    for component_id in ACTIVE_COMPONENTS:
        result[component_id] = {}
        for horizon in STAGE_ORDER:
            result[component_id][horizon] = {}
            for direction in DIRECTIONS.values():
                rule_delta = partition_results["rule_test"]["individual"][
                    component_id
                ][horizon][direction]["marginal_in_full"]
                final_delta = partition_results["final_test"]["individual"][
                    component_id
                ][horizon][direction]["marginal_in_full"]
                rule_shapley = partition_results["rule_test"][
                    "shapley_attribution"
                ][component_id][horizon][direction]
                final_shapley = partition_results["final_test"][
                    "shapley_attribution"
                ][component_id][horizon][direction]
                result[component_id][horizon][direction] = {
                    "status": classify_replication(rule_delta, final_delta),
                    "shapley_status": classify_replication(
                        rule_shapley, final_shapley
                    ),
                    "rule_test": rule_delta,
                    "final_test": final_delta,
                    "rule_test_shapley": rule_shapley,
                    "final_test_shapley": final_shapley,
                }
            without_name = f"without::{component_id}"
            only_name = f"only::{component_id}"
            for partition_name in ("rule_test", "final_test"):
                directional = partition_results[partition_name][
                    "directional_selection"
                ]
                result[component_id][horizon][
                    "directional_selection"
                ] = result[component_id][horizon].get(
                    "directional_selection", {}
                )
                result[component_id][horizon]["directional_selection"][
                    partition_name
                ] = {
                    "full_accuracy": directional["full"][horizon]["accuracy"],
                    "without_rule_accuracy": directional[without_name][horizon][
                        "accuracy"
                    ],
                    "marginal_accuracy_delta": (
                        directional["full"][horizon]["accuracy"]
                        - directional[without_name][horizon]["accuracy"]
                    ),
                    "only_rule_accuracy": directional[only_name][horizon]["accuracy"],
                    "geometry_accuracy": directional["geometry"][horizon]["accuracy"],
                }
    return result


def _atomic_replication_matrix(partition_results: dict) -> dict:
    result = {}
    for horizon in STAGE_ORDER:
        result[horizon] = {}
        for feature_name in expanded_feature_names(horizon):
            result[horizon][feature_name] = {}
            for direction in DIRECTIONS.values():
                rule_delta = partition_results["rule_test"][
                    "atomic_feature_marginal"
                ][horizon][feature_name][direction]["marginal_in_full"]
                final_delta = partition_results["final_test"][
                    "atomic_feature_marginal"
                ][horizon][feature_name][direction]["marginal_in_full"]
                result[horizon][feature_name][direction] = {
                    "status": classify_replication(rule_delta, final_delta),
                    "rule_test": rule_delta,
                    "final_test": final_delta,
                    "interpretation": (
                        "positive values mean the full similarity vector predicts better "
                        "than the same vector with this exact coordinate removed"
                    ),
                }
    return result


def _direct_replication_matrix(direct_results: dict) -> dict:
    result = {}
    for horizon in STAGE_ORDER:
        result[horizon] = {}
        for feature_name in expanded_feature_names(horizon):
            result[horizon][feature_name] = {}
            for direction in DIRECTIONS.values():
                rule_delta = direct_results["rule_test"]["results"][horizon][
                    feature_name
                ][direction]["direct_vs_empirical_geometry"]
                final_delta = direct_results["final_test"]["results"][horizon][
                    feature_name
                ][direction]["direct_vs_empirical_geometry"]
                result[horizon][feature_name][direction] = {
                    "status": classify_replication(
                        rule_delta, final_delta, minimum_units=200
                    ),
                    "rule_test": rule_delta,
                    "final_test": final_delta,
                    "interpretation": (
                        "positive values mean the feature quintile predicts outcomes "
                        "better than historical geometry frequencies without analog selection"
                    ),
                }
    return result


def validate_shapley_additivity(partition_results: dict) -> float:
    maximum_error = 0.0
    for partition in partition_results.values():
        for horizon in STAGE_ORDER:
            for direction in DIRECTIONS.values():
                for metric in ("log_loss", "brier"):
                    attributed = math.fsum(
                        partition["shapley_attribution"][component_id][horizon][
                            direction
                        ][metric]
                        for component_id in ACTIVE_COMPONENTS
                    )
                    full_gain = (
                        partition["summaries"]["geometry"][horizon][direction][
                            metric
                        ]
                        - partition["summaries"]["full"][horizon][direction][metric]
                    )
                    maximum_error = max(
                        maximum_error,
                        abs(attributed - full_gain),
                    )
    return maximum_error


def run_audit(*, output_path: Path = OUTPUT_PATH) -> dict:
    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    variants = component_variants(include_pairs=True)
    partition_results = {}
    for partition_name in SAMPLE_PER_SYMBOL:
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        partition_results[partition_name] = evaluate_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
            variants=variants,
        )
    direct_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        print(
            f"DIRECT_FEATURE_PROGRESS partition={partition_name} "
            f"records={len(partitions[partition_name])}",
            flush=True,
        )
        direct_results[partition_name] = evaluate_direct_feature_relationships(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
        )
    semantic_audit = semantic_feature_audit(records)
    payload = {
        "version": AUDIT_VERSION,
        "engine_version": ENGINE_VERSION,
        "purpose": (
            "Attribution of each active v0.9 rule and pair interaction by "
            "horizon and direction without changing production probabilities."
        ),
        "production_changed": False,
        "observational_rules_included": False,
        "record_cache_sha256": sha256_file(
            ROOT
            / "data"
            / "phase1_controlled_replay"
            / "empirical_analog_records_v0_1.json.gz"
        ),
        "records_by_partition": {
            name: len(values) for name, values in partitions.items()
        },
        "active_components": {
            name: list(features) for name, features in ACTIVE_COMPONENTS.items()
        },
        "atomic_feature_contracts": ATOMIC_FEATURES,
        "implicit_equal_coordinate_share_by_horizon": {
            horizon: {
                "coordinate_count": len(expanded_feature_names(horizon)),
                "share_per_coordinate": 1.0 / len(expanded_feature_names(horizon)),
                "warning": (
                    "this is the current unlearned distance geometry, not an "
                    "evidence-based probability weight"
                ),
            }
            for horizon in STAGE_ORDER
        },
        "active_families": {
            name: list(components) for name, components in ACTIVE_FAMILIES.items()
        },
        "variants_evaluated": {
            name: list(components) for name, components in variants.items()
        },
        "metric_contract": {
            "positive_delta": "right_model_reduces_loss_vs_left_model",
            "marginal_in_full": "loss(without_rule)-loss(full)",
            "atomic_marginal_in_full": "loss(without_exact_stage_coordinate)-loss(full)",
            "standalone_vs_geometry": "loss(geometry)-loss(only_rule)",
            "direct_feature_test": (
                "training-only feature quintiles versus training-only empirical "
                "geometry frequencies; nearest-neighbour selection is not used"
            ),
            "independent_unit": "historical_anchor_and_direction_averaged_over_geometries",
            "interaction_incremental": "pair_gain_minus_best_single_gain",
            "shapley": (
                "mean marginal loss reduction across every possible coalition; "
                "component Shapley values sum to the full model gain"
            ),
            "automatic_weight_changes": False,
        },
        "partitions": partition_results,
        "replication_matrix": _replication_matrix(partition_results),
        "atomic_replication_matrix": _atomic_replication_matrix(partition_results),
        "direct_feature_relationships": direct_results,
        "direct_replication_matrix": _direct_replication_matrix(direct_results),
        "semantic_feature_audit": semantic_audit,
    }
    shapley_error = validate_shapley_additivity(partition_results)
    if shapley_error > 1e-12:
        raise RuntimeError(f"shapley_additivity_failed:{shapley_error}")
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit individual and pairwise contribution of v0.9 active rules."
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    payload = run_audit(output_path=args.output)
    print(
        "ATTRIBUTION_COMPLETE "
        f"sha256={payload['canonical_payload_sha256']} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
