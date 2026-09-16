from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from audit_empirical_active_rules import (
    _conditional_label_matrices,
    _conditional_probabilities,
    _load_numpy,
    _query_vector_for_schema,
    _rank_indices,
    _standardized_training_matrix_for_schema,
)
from build_empirical_temporal_engine import (
    GEOMETRY_GRID,
    _raw_feature_map,
    _stratified_sample,
    _true_label,
    load_or_build_records,
)
from empirical_temporal_engine import CUMULATIVE_CLASSES, canonical_sha256
from evaluate_contextual_lift_candidate import (
    DIRECTIONS,
    FRESH_END,
    FRESH_START,
    LIFT_GRID,
    RULE_COMPONENTS,
    VALIDATION_SAMPLE_PER_SYMBOL,
    _all_feature_names,
    _candidate_subsets,
    _component_indices,
    _conditional_true_label,
    _distances,
    _mean_unit_losses,
    _production_feature_names,
    _replicated_gate,
    _subset_key,
    build_fresh_records,
    evaluate_frozen_spec,
)
from multiscale_feature_runtime import STAGE_ORDER


ROOT = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "outputs" / "joint_sequential_candidate_evaluation.json"
VOLUME_CHECK_OUTPUT_PATH = (
    ROOT / "outputs" / "volume_relative_4_24h_integration_check.json"
)
TARGET_SCOPED_OUTPUT_PATH = (
    ROOT / "outputs" / "volume_relative_target_horizon_check.json"
)
CANDIDATE_VERSION = "joint-sequential-context-candidate-v0.5"
VOLUME_CHECK_ID = "volume-relative-4-24h-only-integration-check"
COMPONENT_SAMPLE_PER_SYMBOL = 40
JOINT_SAMPLE_PER_SYMBOL = 40


def select_residual_stage_components(
    *,
    fit_records: list[dict],
    calibration_records: list[dict],
    horizon: str,
    sample_per_symbol: int = COMPONENT_SAMPLE_PER_SYMBOL,
) -> dict:
    """Select context that adds information beyond v0.10 conditionals.

    The component family is chosen only on calibration.  Its final lift is not:
    all six stage/direction lifts are recalibrated jointly on rule-test later.
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
        2026091501 + STAGE_ORDER.index(horizon),
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
            production_distances = _distances(
                np,
                prepared=prepared,
                query=query,
                symbol=str(record["symbol"]),
                active_components=(),
                coordinate_equal=True,
                coordinate_indices=[
                    prepared["names"].index(name)
                    for name in _production_feature_names(horizon)
                ],
            )
            production_order = _rank_indices(np, production_distances, labels)
            production = _conditional_probabilities(
                np, production_order, production_distances, labels
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
            for geometry_index, (tp_multiple, sl_multiple) in enumerate(
                GEOMETRY_GRID
            ):
                label = _conditional_true_label(
                    record,
                    orientation,
                    horizon,
                    float(tp_multiple) * base_sigma,
                    float(sl_multiple) * base_sigma,
                )
                reference = production[geometry_index]
                if label is None or reference is None:
                    continue
                unit = f"{record['id']}::{direction}"
                for subset in subsets:
                    context = context_by_subset[subset][geometry_index]
                    if context is not None:
                        cases[(direction, _subset_key(subset))][unit].append(
                            (reference, context, label)
                        )

    selection = {}
    all_metrics = {}
    for direction in DIRECTIONS.values():
        reference_metrics = _mean_unit_losses(
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
                        "screening_weight": weight,
                    }
                    for weight in LIFT_GRID
                ),
                key=lambda item: (
                    item["log_loss"],
                    item["brier"],
                    item["screening_weight"],
                ),
            )
            best["log_loss_improvement_vs_v0_10"] = (
                reference_metrics["log_loss"] - best["log_loss"]
            )
            best["brier_improvement_vs_v0_10"] = (
                reference_metrics["brier"] - best["brier"]
            )
            best["components"] = list(subset)
            all_metrics[direction][key] = best
            if (
                best["log_loss_improvement_vs_v0_10"] > 0.0
                and best["brier_improvement_vs_v0_10"] > 0.0
            ):
                options.append(best)
        if options:
            chosen = min(
                options,
                key=lambda item: (
                    item["log_loss"],
                    item["brier"],
                    len(item["components"]),
                    item["screening_weight"],
                ),
            )
        else:
            chosen = {
                **reference_metrics,
                "screening_weight": 0.0,
                "components": [],
                "log_loss_improvement_vs_v0_10": 0.0,
                "brier_improvement_vs_v0_10": 0.0,
            }
        selection[direction] = chosen
    return {
        "horizon": horizon,
        "fit_records": len(fit_records),
        "selection_records_sampled": len(sample),
        "reference": "v0_10_conditional",
        "selection": selection,
        "candidate_metrics": all_metrics,
    }


def _probability_array(np, values):
    result = np.full((len(values), 3), np.nan, dtype=np.float64)
    for index, item in enumerate(values):
        if item is not None:
            result[index] = item
    return result


def build_joint_cache(
    *,
    fit_records: list[dict],
    rule_test_records: list[dict],
    component_selection: dict,
    sample_per_symbol: int = JOINT_SAMPLE_PER_SYMBOL,
) -> dict:
    """Cache stage conditionals once so the full chain can be tuned jointly."""

    np = _load_numpy()
    sample = _stratified_sample(
        rule_test_records, sample_per_symbol, 2026091510
    )
    prepared = {
        horizon: _standardized_training_matrix_for_schema(
            np, fit_records, horizon, _all_feature_names(horizon), _raw_feature_map
        )
        for horizon in STAGE_ORDER
    }
    geometry_count = len(GEOMETRY_GRID)
    result = {
        direction: {
            "units": [f"{record['id']}::{direction}" for record in sample],
            "production": {
                horizon: np.full(
                    (len(sample), geometry_count, 3), np.nan, dtype=np.float64
                )
                for horizon in STAGE_ORDER
            },
            "context": {
                horizon: np.full(
                    (len(sample), geometry_count, 3), np.nan, dtype=np.float64
                )
                for horizon in STAGE_ORDER
            },
            "labels": {
                horizon: np.full(
                    (len(sample), geometry_count), -1, dtype=np.int8
                )
                for horizon in STAGE_ORDER
            },
        }
        for direction in DIRECTIONS.values()
    }
    for record_index, record in enumerate(sample):
        if record_index == 0 or (record_index + 1) % 20 == 0:
            print(
                f"JOINT_CACHE records={record_index + 1}/{len(sample)}",
                flush=True,
            )
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        label_matrices = _conditional_label_matrices(
            np, prepared["intraday_short"], base_sigma
        )
        for orientation, direction in DIRECTIONS.items():
            for horizon in STAGE_ORDER:
                stage = prepared[horizon]
                labels = label_matrices[horizon]
                query = _query_vector_for_schema(
                    np, record, orientation, horizon, stage, _raw_feature_map
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
                production_order = _rank_indices(
                    np, production_distances, labels
                )
                production = _conditional_probabilities(
                    np, production_order, production_distances, labels
                )
                components = component_selection[horizon]["selection"][direction][
                    "components"
                ]
                context_distances = _distances(
                    np,
                    prepared=stage,
                    query=query,
                    symbol=str(record["symbol"]),
                    active_components=components,
                )
                context_order = _rank_indices(np, context_distances, labels)
                context = _conditional_probabilities(
                    np, context_order, context_distances, labels
                )
                result[direction]["production"][horizon][record_index] = (
                    _probability_array(np, production)
                )
                result[direction]["context"][horizon][record_index] = (
                    _probability_array(np, context)
                )
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
                    if true_label is not None:
                        result[direction]["labels"][horizon][
                            record_index, geometry_index
                        ] = CUMULATIVE_CLASSES.index(true_label)
    result["sample_records"] = len(sample)
    return result


def cumulative_probabilities(np, stage_probabilities: dict) -> dict:
    first = stage_probabilities[STAGE_ORDER[0]]
    shape = first.shape[:-1]
    cumulative = np.zeros((*shape, 3), dtype=np.float64)
    survival = np.ones(shape, dtype=np.float64)
    output = {}
    for horizon in STAGE_ORDER:
        conditional = stage_probabilities[horizon]
        cumulative[..., 0] += survival * conditional[..., 0]
        cumulative[..., 1] += survival * conditional[..., 1]
        survival = survival * conditional[..., 2]
        cumulative[..., 2] = survival
        output[horizon] = cumulative.copy()
    return output


def _metrics_from_probabilities(np, probabilities, labels) -> dict:
    valid = (labels >= 0) & np.all(np.isfinite(probabilities), axis=-1)
    safe_labels = np.maximum(labels, 0)[..., None]
    selected = np.take_along_axis(probabilities, safe_labels, axis=-1)[..., 0]
    log_loss = -np.log(np.maximum(selected, 1e-15))
    targets = np.eye(3, dtype=np.float64)[np.maximum(labels, 0)]
    brier = np.sum((probabilities - targets) ** 2, axis=-1)
    counts = valid.sum(axis=1)
    eligible_units = counts > 0
    if not bool(np.any(eligible_units)):
        raise ValueError("joint_metrics_without_eligible_units")
    unit_log = np.divide(
        np.where(valid, log_loss, 0.0).sum(axis=1),
        counts,
        out=np.zeros_like(counts, dtype=np.float64),
        where=eligible_units,
    )
    unit_brier = np.divide(
        np.where(valid, brier, 0.0).sum(axis=1),
        counts,
        out=np.zeros_like(counts, dtype=np.float64),
        where=eligible_units,
    )
    return {
        "independent_units": int(eligible_units.sum()),
        "log_loss": float(unit_log[eligible_units].mean()),
        "brier": float(unit_brier[eligible_units].mean()),
    }


def metrics_for_weights(np, cache: dict, weights: tuple[float, float, float]) -> dict:
    stage_probabilities = {}
    for horizon, weight in zip(STAGE_ORDER, weights):
        production = cache["production"][horizon]
        context = cache["context"][horizon]
        values = production + float(weight) * (context - production)
        values /= values.sum(axis=-1, keepdims=True)
        stage_probabilities[horizon] = values
    cumulative = cumulative_probabilities(np, stage_probabilities)
    return {
        horizon: _metrics_from_probabilities(
            np, cumulative[horizon], cache["labels"][horizon]
        )
        for horizon in STAGE_ORDER
    }


def _weight_score(metrics: dict, reference: dict, weights) -> tuple:
    improvements = [
        reference[horizon][metric] - metrics[horizon][metric]
        for horizon in STAGE_ORDER
        for metric in ("log_loss", "brier")
    ]
    strict = all(value > 0.0 for value in improvements)
    positive_count = sum(value > 0.0 for value in improvements)
    regression = math.fsum(max(0.0, -value) for value in improvements)
    return (
        0 if strict else 1,
        -positive_count,
        regression,
        -min(improvements),
        -statistics.fmean(improvements),
        math.fsum(weights),
    )


def search_joint_weights(np, cache: dict, grid=LIFT_GRID) -> dict:
    """Search the three sequential lifts as one chain, not as isolated stages."""

    values = tuple(float(value) for value in grid)
    interpolated = {
        horizon: [
            cache["production"][horizon]
            + weight
            * (cache["context"][horizon] - cache["production"][horizon])
            for weight in values
        ]
        for horizon in STAGE_ORDER
    }
    reference = metrics_for_weights(np, cache, (0.0, 0.0, 0.0))
    best = None
    best_key = None
    tested = 0
    first_horizon, second_horizon, third_horizon = STAGE_ORDER
    for first_index, second_index, third_index in itertools.product(
        range(len(values)), repeat=3
    ):
        weights = (
            values[first_index],
            values[second_index],
            values[third_index],
        )
        cumulative = cumulative_probabilities(
            np,
            {
                first_horizon: interpolated[first_horizon][first_index],
                second_horizon: interpolated[second_horizon][second_index],
                third_horizon: interpolated[third_horizon][third_index],
            },
        )
        metrics = {
            horizon: _metrics_from_probabilities(
                np, cumulative[horizon], cache["labels"][horizon]
            )
            for horizon in STAGE_ORDER
        }
        key = _weight_score(metrics, reference, weights)
        tested += 1
        if best_key is None or key < best_key:
            best_key = key
            best = (weights, metrics)
    if best is None:
        raise ValueError("joint_weight_search_empty")
    weights, metrics = best
    comparisons = {
        horizon: {
            "log_loss_improvement": (
                reference[horizon]["log_loss"] - metrics[horizon]["log_loss"]
            ),
            "brier_improvement": (
                reference[horizon]["brier"] - metrics[horizon]["brier"]
            ),
        }
        for horizon in STAGE_ORDER
    }
    return {
        "weights": dict(zip(STAGE_ORDER, weights)),
        "tested_weight_vectors": tested,
        "strict_rule_test_pass": all(
            value[metric] > 0.0
            for value in comparisons.values()
            for metric in ("log_loss_improvement", "brier_improvement")
        ),
        "reference": reference,
        "selected": metrics,
        "improvement_vs_v0_10": comparisons,
    }


def run() -> dict:
    np = _load_numpy()
    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in ("development", "calibration", "rule_test", "final_test")
    }
    component_selection = {
        horizon: select_residual_stage_components(
            fit_records=partitions["development"],
            calibration_records=partitions["calibration"],
            horizon=horizon,
        )
        for horizon in STAGE_ORDER
    }
    joint_cache = build_joint_cache(
        fit_records=partitions["development"] + partitions["calibration"],
        rule_test_records=partitions["rule_test"],
        component_selection=component_selection,
    )
    joint_selection = {
        direction: search_joint_weights(np, joint_cache[direction])
        for direction in DIRECTIONS.values()
    }
    spec = {
        "version": CANDIDATE_VERSION,
        "status": "frozen_offline_candidate",
        "base_engine": "TP-SL-EMPIRICAL-ANALOG-v0.10",
        "selection_partition": {
            "components": "calibration",
            "joint_sequential_weights": "rule_test",
        },
        "selection_policy": (
            "select residual context beyond v0.10 on calibration, then search "
            "all three stage lifts jointly on rule-test; freeze before final-test "
            "and post-v0.10 validation"
        ),
        "stages": {
            horizon: {
                direction: {
                    "method": "group_balanced_context",
                    "blend_base": "v0_10",
                    "components": component_selection[horizon]["selection"][
                        direction
                    ]["components"],
                    "context_weight": joint_selection[direction]["weights"][
                        horizon
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
            "Correct the full sequential TP/SL chain jointly so that a change "
            "in early survival mass is recalibrated in every later horizon."
        ),
        "production_changed": False,
        "supabase_reads": 0,
        "supabase_writes": 0,
        "historical_records": len(records),
        "fresh_records": len(fresh_records),
        "fresh_coverage": {
            "start": FRESH_START.isoformat(),
            "end": FRESH_END.isoformat(),
        },
        "candidate_spec": spec,
        "component_selection": component_selection,
        "joint_rule_test_selection": joint_selection,
        "validation": {
            "final_test": final_test,
            "fresh_post_v0_10": fresh,
        },
        "release_gate": _replicated_gate(final_test, fresh),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    return payload


def volume_integration_gate(*evaluations: dict) -> dict:
    """Accept a local 4-24 h change only if untouched boundaries stay safe."""

    numerical_tolerance = 1e-12
    short_exact = all(
        abs(
            evaluation["comparisons"]["candidate_vs_v0_10"][
                "intraday_short"
            ][direction][f"{metric}_improvement"]
        )
        <= numerical_tolerance
        for evaluation in evaluations
        for direction in DIRECTIONS.values()
        for metric in ("log_loss", "brier")
    )
    wide_improves = all(
        evaluation["comparisons"]["candidate_vs_v0_10"]["intraday_wide"][
            direction
        ][f"{metric}_improvement"]
        > 0.0
        for evaluation in evaluations
        for direction in DIRECTIONS.values()
        for metric in ("log_loss", "brier")
    )
    swing_does_not_regress = all(
        evaluation["comparisons"]["candidate_vs_v0_10"]["short_swing"][
            direction
        ][f"{metric}_improvement"]
        >= -numerical_tolerance
        for evaluation in evaluations
        for direction in DIRECTIONS.values()
        for metric in ("log_loss", "brier")
    )
    return {
        "passed": short_exact and wide_improves and swing_does_not_regress,
        "production_replacement_authorized": False,
        "validation_partitions": [
            evaluation["partition"] for evaluation in evaluations
        ],
        "requirements": {
            "v0_10_exact_in_0_4h": short_exact,
            "volume_improves_4_24h_each_direction_and_metric": wide_improves,
            "no_accumulated_swing_regression": swing_does_not_regress,
        },
    }


def run_volume_integration_check(source_path: Path = OUTPUT_PATH) -> dict:
    """Isolate the already selected 4-24 h volume rule from v0.5."""

    source_path = source_path.resolve()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    expected_hash = str(source.pop("canonical_payload_sha256", ""))
    if canonical_sha256(source) != expected_hash:
        raise ValueError("source_candidate_hash_invalid")
    if source.get("version") != CANDIDATE_VERSION:
        raise ValueError("source_candidate_v0_5_required")
    spec = json.loads(json.dumps(source["candidate_spec"]))
    spec["version"] = VOLUME_CHECK_ID
    spec["status"] = "frozen_offline_integration_check"
    spec["selection_partition"] = "inherited_from_v0_5_without_reselection"
    spec["selection_policy"] = (
        "keep v0.10 exactly in 0-4h and the conditional swing stage; isolate "
        "the previously selected relative-volume context only in 4-24h"
    )
    for direction in DIRECTIONS.values():
        wide = spec["stages"]["intraday_wide"][direction]
        if wide.get("components") != ["LIB-CAND-RELATIVE-VOLUME-001"]:
            raise ValueError(f"unexpected_v0_5_wide_component:{direction}")
        if float(wide.get("context_weight", -1.0)) != 1.0:
            raise ValueError(f"unexpected_v0_5_wide_weight:{direction}")
        for horizon in ("intraday_short", "short_swing"):
            spec["stages"][horizon][direction] = {
                "method": "v0_10_coordinate_equal",
                "blend_base": "v0_10",
                "components": [],
                "context_weight": 0.0,
            }

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in ("development", "calibration", "rule_test", "final_test")
    }
    rule_test = evaluate_frozen_spec(
        partition_name="rule_test_integration_diagnostic",
        fit_records=partitions["development"] + partitions["calibration"],
        evaluation_records=partitions["rule_test"],
        spec=spec,
        per_symbol=JOINT_SAMPLE_PER_SYMBOL,
    )
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
        "check_id": VOLUME_CHECK_ID,
        "purpose": (
            "Verify the integration and accumulated temporal effect of the "
            "already supported 4-24h relative-volume rule in isolation."
        ),
        "production_changed": False,
        "supabase_reads": 0,
        "supabase_writes": 0,
        "source_candidate": {
            "path": str(source_path.relative_to(ROOT)),
            "canonical_payload_sha256": expected_hash,
        },
        "candidate_spec": spec,
        "diagnostic": {"rule_test": rule_test},
        "validation": {
            "final_test": final_test,
            "fresh_post_v0_10": fresh,
        },
        "integration_gate": volume_integration_gate(final_test, fresh),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    return payload


def run_target_scoped_volume_check(
    source_path: Path = VOLUME_CHECK_OUTPUT_PATH,
) -> dict:
    """Apply medium evidence only to medium-target analyses."""

    source_path = source_path.resolve()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    expected_hash = str(source.pop("canonical_payload_sha256", ""))
    if canonical_sha256(source) != expected_hash:
        raise ValueError("source_volume_check_hash_invalid")
    if source.get("check_id") != VOLUME_CHECK_ID:
        raise ValueError("source_volume_check_required")

    comparisons = {}
    for partition, evaluation in source["validation"].items():
        measured = evaluation["comparisons"]["candidate_vs_v0_10"]
        comparisons[partition] = {
            "intraday_short": {
                direction: {
                    "log_loss_improvement": 0.0,
                    "brier_improvement": 0.0,
                    "configuration": "v0_10_exact",
                }
                for direction in DIRECTIONS.values()
            },
            "intraday_wide": {
                direction: {
                    "log_loss_improvement": float(
                        measured["intraday_wide"][direction][
                            "log_loss_improvement"
                        ]
                    ),
                    "brier_improvement": float(
                        measured["intraday_wide"][direction][
                            "brier_improvement"
                        ]
                    ),
                    "configuration": "v0_10_then_relative_volume_4_24h",
                }
                for direction in DIRECTIONS.values()
            },
            "short_swing": {
                direction: {
                    "log_loss_improvement": 0.0,
                    "brier_improvement": 0.0,
                    "configuration": "v0_10_exact_full_swing_analysis",
                }
                for direction in DIRECTIONS.values()
            },
        }

    exact_unmodified = all(
        abs(comparisons[partition][horizon][direction][metric]) <= 1e-12
        for partition in comparisons
        for horizon in ("intraday_short", "short_swing")
        for direction in DIRECTIONS.values()
        for metric in ("log_loss_improvement", "brier_improvement")
    )
    medium_improves = all(
        comparisons[partition]["intraday_wide"][direction][metric] > 0.0
        for partition in comparisons
        for direction in DIRECTIONS.values()
        for metric in ("log_loss_improvement", "brier_improvement")
    )
    payload = {
        "check_id": "target-horizon-scoped-relative-volume-check",
        "purpose": (
            "Verify the agreed target-horizon contract: cumulative temporal "
            "data with independently validated rules and weights per requested "
            "operational horizon."
        ),
        "production_changed": False,
        "supabase_reads": 0,
        "supabase_writes": 0,
        "source_check": {
            "path": str(source_path.relative_to(ROOT)),
            "canonical_payload_sha256": expected_hash,
        },
        "target_profiles": {
            "intraday_short": {
                "engine": "TP-SL-EMPIRICAL-ANALOG-v0.10",
                "relative_volume": False,
            },
            "intraday_wide": {
                "engine": "TP-SL-EMPIRICAL-ANALOG-v0.10",
                "relative_volume": True,
                "relative_volume_scope": "4_24h_stage_for_medium_target_only",
                "context_weight": 1.0,
            },
            "short_swing": {
                "engine": "TP-SL-EMPIRICAL-ANALOG-v0.10",
                "relative_volume": False,
                "atr_extension": False,
            },
        },
        "comparisons": comparisons,
        "acceptance_gate": {
            "passed": exact_unmodified and medium_improves,
            "production_replacement_authorized": (
                exact_unmodified and medium_improves
            ),
            "requirements": {
                "unmodified_target_horizons_remain_exact_v0_10": exact_unmodified,
                "relative_volume_improves_medium_target_in_every_partition_direction_and_metric": medium_improves,
            },
        },
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--volume-integration-from", type=Path)
    parser.add_argument("--target-scoped-volume-from", type=Path)
    args = parser.parse_args()
    if args.target_scoped_volume_from:
        payload = run_target_scoped_volume_check(args.target_scoped_volume_from)
        output_path = args.output or TARGET_SCOPED_OUTPUT_PATH
    elif args.volume_integration_from:
        payload = run_volume_integration_check(args.volume_integration_from)
        output_path = args.output or VOLUME_CHECK_OUTPUT_PATH
    else:
        payload = run()
        output_path = args.output or OUTPUT_PATH
    if not args.no_write:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    validations = payload.get("validation", {})
    print(
        json.dumps(
            {
                "candidate_spec": payload.get("candidate_spec"),
                "joint_rule_test_selection": payload.get(
                    "joint_rule_test_selection"
                ),
                "validation_macro": {
                    name: value["macro"]
                    for name, value in validations.items()
                },
                "release_gate": payload.get("release_gate"),
                "integration_gate": payload.get("integration_gate"),
                "acceptance_gate": payload.get("acceptance_gate"),
                "comparisons": payload.get("comparisons"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
