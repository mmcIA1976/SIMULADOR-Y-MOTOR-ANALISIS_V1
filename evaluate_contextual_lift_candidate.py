from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from audit_empirical_active_rules import (
    LABEL_CODE,
    _conditional_label_matrices,
    _conditional_probabilities,
    _load_numpy,
    _query_vector_for_schema,
    _rank_indices,
    _standardized_training_matrix_for_schema,
)
from build_empirical_temporal_engine import (
    GEOMETRY_GRID,
    RULE_GROUPS,
    SELECTION,
    _frontiers,
    _raw_feature_map,
    _stratified_sample,
    _true_label,
    load_or_build_records,
)
from empirical_temporal_engine import (
    CONDITIONAL_CLASSES,
    CUMULATIVE_CLASSES,
    STAGE_BOUNDS,
    _stage_label,
    canonical_sha256,
)
from multiscale_feature_runtime import (
    STAGE_ORDER,
    STAGE_PROFILES,
    _base_rule_context,
    _closed_material,
)
from phase1_controlled_replay import (
    BASE_INTERVAL_MS,
    SYMBOLS,
    aggregate_candles,
    read_symbol_5m,
)


ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "outputs" / "contextual_lift_candidate_evaluation.json"
CANDIDATE_VERSION = "geometry-context-separation-candidate-v0.3"
HYBRID_VERSION = "geometry-context-separation-candidate-v0.4"

# These are the probability-bearing rules in v0.10.  Absolute volatility is
# deliberately kept outside this list: it defines the exposure/geometry
# baseline and therefore cannot be presented as directional evidence.
RULE_COMPONENTS = OrderedDict(
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
        (
            "LIB-CAND-EMA-TREND-001",
            (
                "LIB-CAND-EMA-TREND-001::side_adjusted_close_vs_ema50_log",
                "LIB-CAND-EMA-TREND-001::side_adjusted_ema50_vs_ema200_log",
                "LIB-CAND-EMA-TREND-001::side_adjusted_slope_atr",
            ),
        ),
        (
            "LIB-CAND-RSI-WILDER-001",
            ("LIB-CAND-RSI-WILDER-001::side_adjusted_centered_rsi",),
        ),
        (
            "LIB-CAND-ATR-EXTENSION-001",
            ("LIB-CAND-ATR-EXTENSION-001::side_adjusted_extension_atr",),
        ),
        (
            "LIB-CAND-RELATIVE-VOLUME-001",
            ("LIB-CAND-RELATIVE-VOLUME-001::log_relative_horizon_volume",),
        ),
        (
            "LIB-CAND-CVD-SLOPE-001",
            ("LIB-CAND-CVD-SLOPE-001::side_adjusted_normalized_cvd_slope",),
        ),
        (
            "LIB-CAND-ABSORPTION-001",
            (
                "LIB-CAND-ABSORPTION-001::side_adjusted_horizon_displacement_atr",
                "LIB-CAND-ABSORPTION-001::flow_opposing_wick_ratio",
            ),
        ),
    )
)

DIRECTIONS = {0: "long", 1: "short"}
SELECTION_SAMPLE_PER_SYMBOL = 40
VALIDATION_SAMPLE_PER_SYMBOL = 30
LIFT_GRID = tuple(index / 20.0 for index in range(21))
FRESH_START = datetime(2026, 7, 25, 23, 59, 59, 999000, tzinfo=timezone.utc)
FRESH_END = datetime(2026, 8, 24, 23, 59, 59, 999000, tzinfo=timezone.utc)


def _production_feature_names(horizon: str) -> list[str]:
    """Return the exact v0.10 coordinates, without importing its artifact."""

    inherited = STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
    names = [
        f"{stage}::{feature}"
        for stage in inherited
        for feature in (
            *RULE_GROUPS["price_path"],
            *RULE_GROUPS["volatility_regime"],
        )
    ]
    if horizon == "intraday_short":
        names.append(
            "intraday_short::LIB-CAND-EMA-TREND-001::"
            "side_adjusted_ema50_vs_ema200_log"
        )
    return names


def _all_feature_names(horizon: str) -> list[str]:
    """Return every historically reconstructable contextual coordinate."""

    inherited = STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
    return [
        f"{stage}::{feature}"
        for stage in inherited
        for feature in dict.fromkeys(
            feature for features in RULE_GROUPS.values() for feature in features
        )
    ]


def _component_indices(names: list[str]) -> tuple[list[int], dict[str, list[int]]]:
    exposure = [
        index for index, name in enumerate(names) if name.endswith("::log_context_sigma")
    ]
    if not exposure:
        raise ValueError("context_sigma_coordinate_missing")
    components: dict[str, list[int]] = {}
    for rule_id, suffixes in RULE_COMPONENTS.items():
        indices = [
            index
            for index, name in enumerate(names)
            if any(name.endswith(f"::{suffix}") for suffix in suffixes)
        ]
        if indices:
            components[rule_id] = indices
    return exposure, components


def _mean_clipped_square(np, matrix, query, indices: list[int]):
    difference = matrix[:, indices] - query[indices]
    return np.minimum(36.0, difference * difference).mean(axis=1)


def _distances(
    np,
    *,
    prepared: dict,
    query,
    symbol: str,
    active_components: Iterable[str],
    coordinate_equal: bool = False,
    coordinate_indices: list[int] | None = None,
):
    difference = prepared["matrix"] - query
    coordinate_squared = np.minimum(36.0, difference * difference)
    if coordinate_equal:
        indices = coordinate_indices or list(range(len(prepared["names"])))
        squared = coordinate_squared[:, indices].mean(axis=1)
    else:
        exposure, component_indices = _component_indices(prepared["names"])
        group_distances = [_mean_clipped_square(np, prepared["matrix"], query, exposure)]
        for component in active_components:
            indices = component_indices.get(component)
            if not indices:
                raise ValueError(f"candidate_component_unavailable:{component}")
            group_distances.append(
                _mean_clipped_square(np, prepared["matrix"], query, indices)
            )
        squared = sum(group_distances) / len(group_distances)
    symbol_penalty = np.where(
        prepared["symbols"] == str(symbol),
        0.0,
        float(SELECTION["cross_symbol_penalty"]),
    )
    return np.sqrt(squared) + symbol_penalty


def blend_probabilities(
    baseline: Iterable[float], context: Iterable[float], context_weight: float
) -> tuple[float, float, float]:
    weight = float(context_weight)
    if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:
        raise ValueError("context_weight_out_of_bounds")
    left = [float(value) for value in baseline]
    right = [float(value) for value in context]
    if len(left) != 3 or len(right) != 3:
        raise ValueError("probability_triplet_required")
    values = [
        (1.0 - weight) * baseline_value + weight * context_value
        for baseline_value, context_value in zip(left, right)
    ]
    total = math.fsum(values)
    if total <= 0.0 or any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("blended_probability_invalid")
    normalized = tuple(value / total for value in values)
    return normalized  # type: ignore[return-value]


def candidate_stage_probabilities(
    *,
    exposure: Iterable[float],
    production: Iterable[float],
    context: Iterable[float],
    context_weight: float,
    blend_base: str = "exposure",
) -> tuple[float, float, float]:
    """Apply contextual lift to an explicit, auditable reference model."""

    if blend_base == "exposure":
        baseline = exposure
    elif blend_base == "v0_10":
        baseline = production
    else:
        raise ValueError(f"unsupported_blend_base:{blend_base}")
    return blend_probabilities(baseline, context, context_weight)


def _loss(probabilities: Iterable[float], label_index: int) -> tuple[float, float]:
    values = [float(value) for value in probabilities]
    return (
        -math.log(max(values[label_index], 1e-15)),
        math.fsum(
            (value - (1.0 if index == label_index else 0.0)) ** 2
            for index, value in enumerate(values)
        ),
    )


def _subset_key(components: Iterable[str]) -> str:
    values = tuple(components)
    return "+".join(values) if values else "exposure_only"


def _candidate_subsets(available: Iterable[str]) -> list[tuple[str, ...]]:
    values = tuple(available)
    candidates = [
        combination
        for count in range(min(2, len(values)) + 1)
        for combination in itertools.combinations(values, count)
    ]
    families = (
        (
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-MTF-HIERARCHY-001",
            "LIB-CAND-EMA-TREND-001",
        ),
        (
            "LIB-CAND-EMA-TREND-001",
            "LIB-CAND-RSI-WILDER-001",
            "LIB-CAND-ATR-EXTENSION-001",
        ),
        (
            "M4-RULE-VOLATILITY-RANK-001",
            "LIB-CAND-COMPRESSION-001",
        ),
        (
            "LIB-CAND-RELATIVE-VOLUME-001",
            "LIB-CAND-CVD-SLOPE-001",
            "LIB-CAND-ABSORPTION-001",
        ),
        (
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-MTF-HIERARCHY-001",
            "LIB-CAND-EMA-TREND-001",
            "LIB-CAND-RSI-WILDER-001",
            "LIB-CAND-ATR-EXTENSION-001",
        ),
        (
            "LIB-CAND-EMA-TREND-001",
            "LIB-CAND-RSI-WILDER-001",
            "LIB-CAND-ATR-EXTENSION-001",
            "LIB-CAND-RELATIVE-VOLUME-001",
            "LIB-CAND-CVD-SLOPE-001",
            "LIB-CAND-ABSORPTION-001",
        ),
        values,
    )
    available_set = set(values)
    for family in families:
        if set(family).issubset(available_set) and family not in candidates:
            candidates.append(family)
    return candidates


def _conditional_true_label(
    record: dict,
    orientation: int,
    horizon: str,
    tp_distance: float,
    sl_distance: float,
) -> int | None:
    label = _stage_label(
        record,
        orientation,
        tp_distance=tp_distance,
        sl_distance=sl_distance,
        start_step=STAGE_BOUNDS[horizon][0],
        end_step=STAGE_BOUNDS[horizon][1],
    )
    if label in {None, "ambiguous"}:
        return None
    return LABEL_CODE[label]


def _mean_unit_losses(cases: dict[str, list[tuple]], context_weight: float) -> dict:
    units = []
    predictions = 0
    for rows in cases.values():
        losses = [
            _loss(blend_probabilities(base, context, context_weight), label)
            for base, context, label in rows
        ]
        if not losses:
            continue
        units.append(
            (
                statistics.fmean(item[0] for item in losses),
                statistics.fmean(item[1] for item in losses),
            )
        )
        predictions += len(losses)
    return {
        "independent_units": len(units),
        "predictions": predictions,
        "log_loss": statistics.fmean(item[0] for item in units),
        "brier": statistics.fmean(item[1] for item in units),
    }


def select_stage_components(
    *,
    fit_records: list[dict],
    calibration_records: list[dict],
    horizon: str,
    sample_per_symbol: int = SELECTION_SAMPLE_PER_SYMBOL,
) -> dict:
    """Select rule groups and lift using calibration only.

    Each rule gets one distance share regardless of how many coordinates its
    formula emits.  That removes v0.10's accidental extra influence for rules
    with two outputs.
    """

    np = _load_numpy()
    names = _all_feature_names(horizon)
    prepared = _standardized_training_matrix_for_schema(
        np, fit_records, horizon, names, _raw_feature_map
    )
    _, component_indices = _component_indices(names)
    subsets = _candidate_subsets(component_indices)
    sample = _stratified_sample(
        calibration_records,
        sample_per_symbol,
        2026091401 + STAGE_ORDER.index(horizon),
    )
    cases = {
        (DIRECTIONS[orientation], _subset_key(subset)): defaultdict(list)
        for orientation in (0, 1)
        for subset in subsets
    }
    for record in sample:
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        labels = _conditional_label_matrices(np, prepared, base_sigma)[horizon]
        for orientation in (0, 1):
            direction = DIRECTIONS[orientation]
            query = _query_vector_for_schema(
                np, record, orientation, horizon, prepared, _raw_feature_map
            )
            baseline_distances = _distances(
                np,
                prepared=prepared,
                query=query,
                symbol=str(record["symbol"]),
                active_components=(),
            )
            baseline_order = _rank_indices(np, baseline_distances, labels)
            baseline = _conditional_probabilities(
                np, baseline_order, baseline_distances, labels
            )
            context_by_subset = {}
            for subset in subsets:
                distances = _distances(
                    np,
                    prepared=prepared,
                    query=query,
                    symbol=str(record["symbol"]),
                    active_components=subset,
                )
                order = _rank_indices(np, distances, labels)
                context_by_subset[subset] = _conditional_probabilities(
                    np, order, distances, labels
                )
            for geometry_index, (tp_multiple, sl_multiple) in enumerate(GEOMETRY_GRID):
                label = _conditional_true_label(
                    record,
                    orientation,
                    horizon,
                    float(tp_multiple) * base_sigma,
                    float(sl_multiple) * base_sigma,
                )
                if label is None or baseline[geometry_index] is None:
                    continue
                unit = f"{record['id']}::{direction}"
                for subset in subsets:
                    context = context_by_subset[subset][geometry_index]
                    if context is not None:
                        cases[(direction, _subset_key(subset))][unit].append(
                            (baseline[geometry_index], context, label)
                        )

    selection = {}
    all_metrics = {}
    for direction in DIRECTIONS.values():
        baseline_metrics = _mean_unit_losses(
            cases[(direction, "exposure_only")], 0.0
        )
        options = []
        all_metrics[direction] = {}
        for subset in subsets:
            key = _subset_key(subset)
            best = min(
                (
                    {
                        **_mean_unit_losses(cases[(direction, key)], weight),
                        "context_weight": weight,
                    }
                    for weight in LIFT_GRID
                ),
                key=lambda item: (
                    item["log_loss"],
                    item["brier"],
                    item["context_weight"],
                ),
            )
            best["log_loss_improvement_vs_exposure"] = (
                baseline_metrics["log_loss"] - best["log_loss"]
            )
            best["brier_improvement_vs_exposure"] = (
                baseline_metrics["brier"] - best["brier"]
            )
            best["components"] = list(subset)
            all_metrics[direction][key] = best
            if (
                best["log_loss_improvement_vs_exposure"] > 0.0
                and best["brier_improvement_vs_exposure"] > 0.0
            ):
                options.append(best)
        if options:
            chosen = min(
                options,
                key=lambda item: (
                    item["log_loss"],
                    item["brier"],
                    len(item["components"]),
                    item["context_weight"],
                ),
            )
        else:
            chosen = {
                **baseline_metrics,
                "context_weight": 0.0,
                "components": [],
                "log_loss_improvement_vs_exposure": 0.0,
                "brier_improvement_vs_exposure": 0.0,
            }
        selection[direction] = chosen
    return {
        "horizon": horizon,
        "fit_records": len(fit_records),
        "selection_records_sampled": len(sample),
        "selection": selection,
        "candidate_metrics": all_metrics,
    }


def _accumulate(cumulative, survival, conditional) -> None:
    for geometry_index, probabilities in enumerate(conditional):
        if probabilities is None:
            continue
        entering = survival[geometry_index]
        cumulative[geometry_index, 0] += entering * probabilities[0]
        cumulative[geometry_index, 1] += entering * probabilities[1]
        survival[geometry_index] *= probabilities[2]
        cumulative[geometry_index, 2] = survival[geometry_index]


def evaluate_frozen_spec(
    *,
    partition_name: str,
    fit_records: list[dict],
    evaluation_records: list[dict],
    spec: dict,
    per_symbol: int | None,
) -> dict:
    np = _load_numpy()
    sample = (
        _stratified_sample(
            evaluation_records,
            per_symbol,
            2026091410 + len(partition_name),
        )
        if per_symbol is not None
        else list(evaluation_records)
    )
    prepared = {
        horizon: _standardized_training_matrix_for_schema(
            np,
            fit_records,
            horizon,
            _all_feature_names(horizon),
            _raw_feature_map,
        )
        for horizon in STAGE_ORDER
    }
    unit_losses = defaultdict(lambda: [0.0, 0.0, 0])
    direction_counts = defaultdict(Counter)
    symmetric = {
        index
        for index, geometry in enumerate(GEOMETRY_GRID)
        if float(geometry[0]) == float(geometry[1])
    }
    for record_index, record in enumerate(sample, 1):
        if record_index == 1 or record_index % 20 == 0 or record_index == len(sample):
            print(
                f"CONTEXT_LIFT_EVAL partition={partition_name} "
                f"records={record_index}/{len(sample)}",
                flush=True,
            )
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        label_matrices = _conditional_label_matrices(
            np, prepared["intraday_short"], base_sigma
        )
        direction_observations = {}
        for orientation in (0, 1):
            direction = DIRECTIONS[orientation]
            cumulative = {
                model: np.tile(
                    np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
                    (len(GEOMETRY_GRID), 1),
                )
                for model in ("exposure", "v0_10", "candidate")
            }
            survival = {
                model: np.ones(len(GEOMETRY_GRID), dtype=np.float64)
                for model in cumulative
            }
            for horizon in STAGE_ORDER:
                stage = prepared[horizon]
                labels = label_matrices[horizon]
                query = _query_vector_for_schema(
                    np, record, orientation, horizon, stage, _raw_feature_map
                )
                baseline_distances = _distances(
                    np,
                    prepared=stage,
                    query=query,
                    symbol=str(record["symbol"]),
                    active_components=(),
                )
                baseline_order = _rank_indices(np, baseline_distances, labels)
                baseline = _conditional_probabilities(
                    np, baseline_order, baseline_distances, labels
                )
                production_distances = _distances(
                    np,
                    prepared=stage,
                    query=query,
                    symbol=str(record["symbol"]),
                    active_components=(),
                    coordinate_equal=True,
                    coordinate_indices=[
                        stage["names"].index(name)
                        for name in _production_feature_names(horizon)
                    ],
                )
                production_order = _rank_indices(np, production_distances, labels)
                production = _conditional_probabilities(
                    np, production_order, production_distances, labels
                )
                selected = spec["stages"][horizon][direction]
                if selected.get("method") == "v0_10_coordinate_equal":
                    raw_candidate = production
                else:
                    candidate_distances = _distances(
                        np,
                        prepared=stage,
                        query=query,
                        symbol=str(record["symbol"]),
                        active_components=selected["components"],
                    )
                    candidate_order = _rank_indices(
                        np, candidate_distances, labels
                    )
                    raw_candidate = _conditional_probabilities(
                        np, candidate_order, candidate_distances, labels
                    )
                candidate = [
                    (
                        candidate_stage_probabilities(
                            exposure=base,
                            production=production_item,
                            context=context,
                            context_weight=selected["context_weight"],
                            blend_base=selected.get("blend_base", "exposure"),
                        )
                        if base is not None
                        and production_item is not None
                        and context is not None
                        else None
                    )
                    for base, production_item, context in zip(
                        baseline, production, raw_candidate
                    )
                ]
                _accumulate(cumulative["exposure"], survival["exposure"], baseline)
                _accumulate(cumulative["v0_10"], survival["v0_10"], production)
                _accumulate(cumulative["candidate"], survival["candidate"], candidate)

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
                    unit = f"{record['id']}::{direction}"
                    for model, values in cumulative.items():
                        probabilities = values[geometry_index]
                        probabilities = probabilities / probabilities.sum()
                        log_loss, brier = _loss(probabilities, label_index)
                        bucket = unit_losses[(model, horizon, direction, unit)]
                        bucket[0] += log_loss
                        bucket[1] += brier
                        bucket[2] += 1
                        direction_observations[
                            (model, horizon, geometry_index, orientation)
                        ] = (float(probabilities[0] - probabilities[1]), label_index)

        for model in ("exposure", "v0_10", "candidate"):
            for horizon in STAGE_ORDER:
                for geometry_index in symmetric:
                    long_item = direction_observations.get(
                        (model, horizon, geometry_index, 0)
                    )
                    short_item = direction_observations.get(
                        (model, horizon, geometry_index, 1)
                    )
                    if not long_item or not short_item:
                        continue
                    if {long_item[1], short_item[1]} != {0, 1}:
                        continue
                    counts = direction_counts[(model, horizon)]
                    counts["eligible"] += 1
                    actual_long = long_item[1] == 0
                    counts["actual_long"] += int(actual_long)
                    if abs(long_item[0] - short_item[0]) <= 1e-15:
                        counts["ties"] += 1
                        counts["correct_twice"] += 1
                    else:
                        chosen_long = long_item[0] > short_item[0]
                        counts["chosen_long"] += int(chosen_long)
                        counts["correct_twice"] += 2 * int(chosen_long == actual_long)

    summaries = {}
    unit_maps = defaultdict(dict)
    for (model, horizon, direction, unit), values in unit_losses.items():
        if values[2]:
            unit_maps[(model, horizon, direction)][unit] = (
                values[0] / values[2],
                values[1] / values[2],
            )
    for model in ("exposure", "v0_10", "candidate"):
        summaries[model] = {}
        for horizon in STAGE_ORDER:
            summaries[model][horizon] = {}
            for direction in DIRECTIONS.values():
                values = list(unit_maps[(model, horizon, direction)].values())
                counts = direction_counts[(model, horizon)]
                eligible = counts["eligible"]
                summaries[model][horizon][direction] = {
                    "independent_units": len(values),
                    "log_loss": statistics.fmean(item[0] for item in values),
                    "brier": statistics.fmean(item[1] for item in values),
                    "directional_accuracy": (
                        counts["correct_twice"] / (2 * eligible) if eligible else None
                    ),
                    "chosen_long_rate": (
                        counts["chosen_long"] / (eligible - counts["ties"])
                        if eligible > counts["ties"]
                        else None
                    ),
                    "actual_long_rate": (
                        counts["actual_long"] / eligible if eligible else None
                    ),
                }

    comparisons = {}
    for reference in ("exposure", "v0_10"):
        key = f"candidate_vs_{reference}"
        comparisons[key] = {}
        for horizon in STAGE_ORDER:
            comparisons[key][horizon] = {}
            for direction in DIRECTIONS.values():
                left = summaries[reference][horizon][direction]
                right = summaries["candidate"][horizon][direction]
                comparisons[key][horizon][direction] = {
                    "log_loss_improvement": left["log_loss"] - right["log_loss"],
                    "brier_improvement": left["brier"] - right["brier"],
                    "directional_accuracy_delta": (
                        right["directional_accuracy"] - left["directional_accuracy"]
                    ),
                    "chosen_long_rate_delta": (
                        right["chosen_long_rate"] - left["chosen_long_rate"]
                        if right["chosen_long_rate"] is not None
                        and left["chosen_long_rate"] is not None
                        else None
                    ),
                }
    macro = {}
    for reference in ("exposure", "v0_10"):
        cells = [
            comparisons[f"candidate_vs_{reference}"][horizon][direction]
            for horizon in STAGE_ORDER
            for direction in DIRECTIONS.values()
        ]
        macro[f"candidate_vs_{reference}"] = {
            "log_loss_improvement": statistics.fmean(
                item["log_loss_improvement"] for item in cells
            ),
            "brier_improvement": statistics.fmean(
                item["brier_improvement"] for item in cells
            ),
            "cells_improving_both": sum(
                item["log_loss_improvement"] > 0.0
                and item["brier_improvement"] > 0.0
                for item in cells
            ),
            "cells": len(cells),
        }
    return {
        "partition": partition_name,
        "fit_records": len(fit_records),
        "evaluation_records": len(sample),
        "summaries": summaries,
        "comparisons": comparisons,
        "macro": macro,
    }


def build_fresh_records(
    start: datetime = FRESH_START, end: datetime = FRESH_END
) -> list[dict]:
    expected_suffixes = {
        feature
        for features in RULE_GROUPS.values()
        for feature in features
        if feature != "log_context_sigma"
    }
    records = []
    for symbol in SYMBOLS:
        base = read_symbol_5m(symbol)
        base_index = {
            int(row["close_time_ms"]): index for index, row in enumerate(base)
        }
        aggregated = {
            horizon: aggregate_candles(
                base, int(STAGE_PROFILES[horizon]["interval_seconds"])
            )
            for horizon in STAGE_ORDER
        }
        indexes = {
            horizon: {
                int(row["close_time_ms"]): index
                for index, row in enumerate(aggregated[horizon])
            }
            for horizon in STAGE_ORDER
        }
        moment = start
        while moment <= end:
            cutoff_ms = int(moment.timestamp() * 1000)
            base_position = base_index.get(cutoff_ms)
            if base_position is None:
                moment += timedelta(days=1)
                continue
            future = base[base_position + 1 : base_position + 1 + 7 * 24 * 12]
            if len(future) != 7 * 24 * 12 or any(
                int(right["open_time_ms"]) - int(left["open_time_ms"])
                != BASE_INTERVAL_MS
                for left, right in zip(future, future[1:])
            ):
                moment += timedelta(days=1)
                continue
            entry = float(base[base_position]["close"])
            stage_features = {}
            stage_sigmas = {}
            valid = True
            for horizon in STAGE_ORDER:
                index = indexes[horizon].get(cutoff_ms)
                if index is None:
                    valid = False
                    break
                profile = STAGE_PROFILES[horizon]
                return_count = int(profile["horizon_seconds"]) // int(
                    profile["interval_seconds"]
                )
                required = 61 * return_count + 1
                if index + 1 < required:
                    valid = False
                    break
                candles = aggregated[horizon][index - required + 1 : index + 1]
                plan = {
                    "symbol": symbol,
                    "side": "long",
                    "entry": entry,
                    "take_profit": entry * 1.01,
                    "stop_loss": entry * 0.99,
                    "entry_type": "market",
                    "margin": 100.0,
                    "leverage": 1.0,
                    "time_horizon": horizon,
                    "horizon_seconds": profile["horizon_seconds"],
                    "analysis_at": moment.isoformat(),
                }
                try:
                    material = _closed_material(plan, candles)
                    features, _ = _base_rule_context(plan, material)
                except (KeyError, ValueError, ArithmeticError):
                    valid = False
                    break
                flat = {
                    f"{rule_id}::{name}": float(value)
                    for rule_id, outputs in features.items()
                    for name, value in outputs.items()
                    if isinstance(value, (int, float)) and math.isfinite(float(value))
                }
                if not expected_suffixes.issubset(flat):
                    valid = False
                    break
                stage_features[horizon] = flat
                stage_sigmas[horizon] = math.sqrt(
                    float(material["current_variance"])
                )
            if valid:
                up, down = _frontiers(entry, future)
                records.append(
                    {
                        "id": f"fresh:{symbol}:{cutoff_ms}",
                        "symbol": symbol,
                        "partition": "fresh_post_v0_10",
                        "analysis_at": moment.isoformat(),
                        "cutoff_ms": cutoff_ms,
                        "entry": entry,
                        "stage_features": stage_features,
                        "stage_sigmas": stage_sigmas,
                        "up_frontier": up,
                        "down_frontier": down,
                    }
                )
            moment += timedelta(days=1)
        print(f"FRESH_RECORDS symbol={symbol} total={len(records)}", flush=True)
    return records


def _replicated_gate(*evaluations: dict) -> dict:
    versus_production = [
        evaluation["macro"]["candidate_vs_v0_10"]
        for evaluation in evaluations
    ]
    versus_exposure = [
        evaluation["macro"]["candidate_vs_exposure"]
        for evaluation in evaluations
    ]
    cells = [
        evaluation["comparisons"]["candidate_vs_v0_10"][horizon][direction]
        for evaluation in evaluations
        for horizon in STAGE_ORDER
        for direction in DIRECTIONS.values()
    ]
    no_large_cell_regression = all(
        item["log_loss_improvement"] >= -0.005
        and item["brier_improvement"] >= -0.005
        for item in cells
    )
    def improves_every_horizon(reference: str, metric: str) -> bool:
        return all(
            statistics.fmean(
                evaluation["comparisons"][f"candidate_vs_{reference}"][horizon][
                    direction
                ][f"{metric}_improvement"]
                for direction in DIRECTIONS.values()
            )
            > 0.0
            for evaluation in evaluations
            for horizon in STAGE_ORDER
        )

    beats_v0_10_log = improves_every_horizon("v0_10", "log_loss")
    beats_v0_10_brier = improves_every_horizon("v0_10", "brier")
    beats_exposure_log = improves_every_horizon("exposure", "log_loss")
    beats_exposure_brier = improves_every_horizon("exposure", "brier")
    passed = all(
        (
            beats_v0_10_log,
            beats_v0_10_brier,
            beats_exposure_log,
            beats_exposure_brier,
            no_large_cell_regression,
        )
    )
    return {
        "passed": passed,
        "production_replacement_authorized": False,
        "validation_partitions": [item["partition"] for item in evaluations],
        "requirements": {
            "beats_v0_10_log_loss_in_every_horizon_and_partition": beats_v0_10_log,
            "beats_v0_10_brier_in_every_horizon_and_partition": beats_v0_10_brier,
            "beats_exposure_log_loss_in_every_horizon_and_partition": beats_exposure_log,
            "beats_exposure_brier_in_every_horizon_and_partition": beats_exposure_brier,
            "no_cell_regression_beyond_0_005": no_large_cell_regression,
        },
        "reason": (
            "candidate_passed_offline_gate_but_requires_explicit_release_step"
            if passed
            else "candidate_failed_offline_gate_v0_10_remains_production"
        ),
    }


def run() -> dict:
    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in ("development", "calibration", "rule_test", "final_test")
    }
    stage_selection = {
        horizon: select_stage_components(
            fit_records=partitions["development"],
            calibration_records=(
                partitions["calibration"] + partitions["rule_test"]
            ),
            horizon=horizon,
        )
        for horizon in STAGE_ORDER
    }
    spec = {
        "version": CANDIDATE_VERSION,
        "status": "frozen_offline_candidate",
        "base_engine": "TP-SL-EMPIRICAL-ANALOG-v0.10",
        "selection_partition": "calibration_plus_rule_test",
        "selection_policy": (
            "exposure_only_baseline_plus_group_balanced_rule_distance; "
            "context lift must persist across calibration and rule-test history, "
            "then remains frozen for final-test and post-v0.10 validation"
        ),
        "stages": {
            horizon: {
                direction: {
                    "method": "group_balanced_context",
                    "components": stage_selection[horizon]["selection"][direction][
                        "components"
                    ],
                    "context_weight": stage_selection[horizon]["selection"][direction][
                        "context_weight"
                    ],
                }
                for direction in DIRECTIONS.values()
            }
            for horizon in STAGE_ORDER
        },
    }
    final_test = evaluate_frozen_spec(
        partition_name="final_test",
        fit_records=(
            partitions["development"]
            + partitions["calibration"]
            + partitions["rule_test"]
        ),
        evaluation_records=partitions["final_test"],
        spec=spec,
        per_symbol=VALIDATION_SAMPLE_PER_SYMBOL,
    )
    fresh_records = build_fresh_records()
    fresh = evaluate_frozen_spec(
        partition_name="fresh_post_v0_10",
        fit_records=records,
        evaluation_records=fresh_records,
        spec=spec,
        per_symbol=None,
    )
    payload = {
        "version": CANDIDATE_VERSION,
        "purpose": (
            "Measure rule context separately from TP/SL geometry and prevent "
            "unsupported contextual lift from dominating production probability."
        ),
        "production_changed": False,
        "supabase_reads": 0,
        "supabase_writes": 0,
        "historical_records": len(records),
        "fresh_records": len(fresh_records),
        "fresh_coverage": {
            "start": FRESH_START.isoformat(),
            "end": FRESH_END.isoformat(),
            "symbols": list(SYMBOLS),
        },
        "candidate_spec": spec,
        "calibration_selection": stage_selection,
        "validation": {
            "final_test": final_test,
            "fresh_post_v0_10": fresh,
        },
        "release_gate": _replicated_gate(final_test, fresh),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    return payload


def run_hybrid(source_path: Path = OUTPUT_PATH) -> dict:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    expected_hash = str(source.pop("canonical_payload_sha256", ""))
    if canonical_sha256(source) != expected_hash:
        raise ValueError("source_candidate_hash_invalid")
    if source.get("version") != CANDIDATE_VERSION:
        raise ValueError("source_candidate_v0_3_required")
    spec = json.loads(json.dumps(source["candidate_spec"]))
    spec["version"] = HYBRID_VERSION
    spec["status"] = "frozen_offline_hybrid_candidate"
    spec["selection_partition"] = "v0_3_short_stage_plus_v0_10_later_stages"
    spec["selection_policy"] = (
        "retain the replicated v0.3 0-4h contextual improvement; keep the "
        "unchanged v0.10 conditional estimator in later stages"
    )
    for horizon in ("intraday_wide", "short_swing"):
        for direction in DIRECTIONS.values():
            spec["stages"][horizon][direction] = {
                "method": "v0_10_coordinate_equal",
                "components": [],
                "context_weight": 1.0,
            }
    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in ("development", "calibration", "rule_test", "final_test")
    }
    final_test = evaluate_frozen_spec(
        partition_name="final_test",
        fit_records=(
            partitions["development"]
            + partitions["calibration"]
            + partitions["rule_test"]
        ),
        evaluation_records=partitions["final_test"],
        spec=spec,
        per_symbol=VALIDATION_SAMPLE_PER_SYMBOL,
    )
    fresh_records = build_fresh_records()
    fresh = evaluate_frozen_spec(
        partition_name="fresh_post_v0_10",
        fit_records=records,
        evaluation_records=fresh_records,
        spec=spec,
        per_symbol=None,
    )
    payload = {
        "version": HYBRID_VERSION,
        "purpose": (
            "Test whether the robust 0-4h contextual improvement can replace "
            "only that stage while preserving v0.10 in later stages."
        ),
        "production_changed": False,
        "supabase_reads": 0,
        "supabase_writes": 0,
        "source_candidate": {
            "path": str(source_path.relative_to(ROOT)),
            "canonical_payload_sha256": expected_hash,
        },
        "candidate_spec": spec,
        "validation": {
            "final_test": final_test,
            "fresh_post_v0_10": fresh,
        },
        "release_gate": _replicated_gate(final_test, fresh),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--hybrid-from", type=Path)
    args = parser.parse_args()
    payload = run_hybrid(args.hybrid_from) if args.hybrid_from else run()
    if not args.no_write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    summary = {
        "candidate_spec": payload["candidate_spec"],
        "validation_macro": {
            name: evaluation["macro"]
            for name, evaluation in payload["validation"].items()
        },
        "release_gate": payload["release_gate"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
