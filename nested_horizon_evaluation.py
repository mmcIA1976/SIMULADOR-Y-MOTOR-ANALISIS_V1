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

from phase1_controlled_replay import (
    AUDIT_DIR,
    BASE_INTERVAL_MS,
    BASE_INTERVAL_SECONDS,
    CLASSES,
    DATA_DIR,
    GEOMETRIES,
    HORIZONS,
    RANDOM_SEED,
    RULE_FEATURES,
    SYMBOLS,
    _base_rule_context,
    _baseline_probabilities,
    _closed_material,
    _complete_future,
    _opposite_side_base_context,
    _outcome,
    _rule_features_for_plan,
    _structural_basis,
    add_hash,
    aggregate_candles,
    canonical_json,
    iso_ms,
    partition_for_ms,
    read_symbol_5m,
    sha256_file,
    write_json,
)


ROOT = Path(__file__).resolve().parent
NESTED_DATASET_PATH = DATA_DIR / "nested_horizon_cases_v0_1.jsonl.gz"
NESTED_MANIFEST_PATH = AUDIT_DIR / "horizon_nested_cohort_v0_1.json"
NESTED_VALIDATION_PATH = AUDIT_DIR / "horizon_nested_cohort_validation_v0_1.json"
PROTOCOL_PATH = AUDIT_DIR / "horizon_value_protocol_v0_1.json"
RESULT_PATH = AUDIT_DIR / "horizon_value_evaluation_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-08-13_valor_incremental_horizonte.md"
CANDIDATE_PATH = AUDIT_DIR / "candidato_motor_horizonte_unico_v0_1.json"

VERSION = "nested-horizon-cohort-v0.1"
EVALUATION_VERSION = "single-engine-horizon-value-v0.1"
REFERENCE_HORIZON = "intraday_wide"
REFERENCE_SECONDS = int(HORIZONS[REFERENCE_HORIZON]["seconds"])
MAX_HORIZON_SECONDS = max(int(item["seconds"]) for item in HORIZONS.values())
ANCHOR_STEP_SECONDS = 24 * 60 * 60
BOOTSTRAP_SAMPLES = 2000
FIT_CASES_PER_HORIZON = 4000
FIT_ITERATIONS = 80
RIDGE_CANDIDATES = (0.1, 1.0, 10.0)


CANONICAL_RULE_FEATURES = (
    ("M4-RULE-PATH-STRUCTURE-001", "directional_path_efficiency_h"),
    ("M4-RULE-MTF-HIERARCHY-001", "directional_path_efficiency_2h"),
    ("M4-RULE-MTF-HIERARCHY-001", "directional_path_efficiency_4h"),
    ("M4-RULE-VOLATILITY-RANK-001", "volatility_percentile_60"),
    ("M4-RULE-PRIOR-EXTREMA-001", "target_extreme_between_entry_and_tp"),
    ("LIB-CAND-EMA-TREND-001", "side_adjusted_close_vs_ema50_log"),
    ("LIB-CAND-EMA-TREND-001", "side_adjusted_ema50_vs_ema200_log"),
    ("LIB-CAND-EMA-TREND-001", "side_adjusted_slope_atr"),
    ("LIB-CAND-RSI-WILDER-001", "side_adjusted_centered_rsi"),
    ("LIB-CAND-ATR-EXTENSION-001", "side_adjusted_extension_atr"),
    ("LIB-CAND-RELATIVE-VOLUME-001", "log_relative_horizon_volume"),
    ("LIB-CAND-CVD-SLOPE-001", "side_adjusted_normalized_cvd_slope"),
    ("LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001", "target_path_level_count"),
    ("LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001", "adverse_path_level_count"),
    (
        "LIB-CAND-FIBONACCI-DISTANCE-001",
        "nearest_to_take_profit.absolute_distance_sigma_horizon",
    ),
    (
        "LIB-CAND-FIBONACCI-DISTANCE-001",
        "nearest_to_stop_loss.absolute_distance_sigma_horizon",
    ),
    ("LIB-CAND-COMPRESSION-001", "compression_vector.atr_rank"),
    (
        "LIB-CAND-COMPRESSION-001",
        "compression_vector.bollinger_width_rank",
    ),
    (
        "LIB-CAND-ABSORPTION-001",
        "side_adjusted_horizon_displacement_atr",
    ),
    ("LIB-CAND-ABSORPTION-001", "flow_opposing_wick_ratio"),
)


def feature_key(rule_id: str, name: str) -> str:
    return f"{rule_id}::{name}"


def flatten_rule_features(features: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
        feature_key(rule_id, name): float(features[rule_id][name])
        for rule_id, name in CANONICAL_RULE_FEATURES
    }


def week_cluster(timestamp_ms: int) -> str:
    moment = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    monday = moment.date().toordinal() - moment.weekday()
    return f"utc_week_monday_ordinal:{monday}"


def build_protocol() -> dict:
    payload = add_hash(
        {
            "version": "single-engine-horizon-value-protocol-v0.1",
            "question": (
                "Does limiting the same trade plan to the selected duration "
                "improve TP-first versus SL-first versus expiry probabilities?"
            ),
            "single_engine": True,
            "independent_engines_by_frame": False,
            "same_plan_contract": [
                "same symbol",
                "same analysis timestamp",
                "same side",
                "same entry",
                "same take profit",
                "same stop loss",
            ],
            "only_changed_plan_input": "horizon_seconds",
            "horizon_seconds": {
                name: int(profile["seconds"])
                for name, profile in HORIZONS.items()
            },
            "models": {
                "horizon_blind_physics": (
                    "first-passage with fixed 24h reference volatility for every row"
                ),
                "horizon_aware_physics": (
                    "same volatility rate scaled by sqrt(selected_seconds / 24h)"
                ),
                "horizon_blind_rules": (
                    "blind physics plus one shared coefficient vector over fixed 24h rule context"
                ),
                "horizon_aware_rules": (
                    "aware physics plus the same coefficient schema over selected-duration context"
                ),
                "horizon_aware_interactions": (
                    "aware rules plus continuous log-duration interactions in one model"
                ),
            },
            "primary_metric": "macro_horizon_log_loss_3c",
            "secondary_metric": "macro_horizon_brier_3c",
            "paired_inference_block": "UTC calendar week shared by all symbols and horizons",
            "selection": (
                "ridge on calibration; choose eligible time-aware candidate on rule_test; "
                "open final_test once after freezing"
            ),
            "candidate_gate": [
                "positive mean log-loss and Brier improvement on calibration",
                "positive mean log-loss and Brier improvement on rule_test",
                "final weekly-bootstrap 95% lower bounds above zero against blind counterpart",
                "final mean log-loss and Brier not worse in any selected horizon",
            ],
            "partitions": {
                "development_end": "2024-12-31T23:59:59+00:00",
                "calibration_end": "2025-06-30T23:59:59+00:00",
                "rule_test_end": "2025-12-31T23:59:59+00:00",
                "final_end": "2026-07-31T23:59:59+00:00",
            },
            "automatic_weight_updates": False,
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(PROTOCOL_PATH, payload)
    return payload


def _shell(symbol: str, horizon: str, anchor: dict) -> dict:
    profile = HORIZONS[horizon]
    entry = float(anchor["close"])
    return {
        "symbol": symbol,
        "side": "long",
        "entry": entry,
        "take_profit": entry * 1.001,
        "stop_loss": entry * 0.999,
        "entry_type": "market",
        "margin": 100.0,
        "leverage": 1.0,
        "time_horizon": horizon,
        "horizon_seconds": int(profile["seconds"]),
        "analysis_at": iso_ms(int(anchor["close_time_ms"])),
    }


def _material_at(
    *,
    symbol: str,
    horizon: str,
    candles: list[dict],
    index: int,
) -> tuple[dict, dict]:
    anchor = candles[index]
    shell = _shell(symbol, horizon, anchor)
    profile = HORIZONS[horizon]
    return_count = int(profile["seconds"]) // int(profile["interval_seconds"])
    required_returns = 61 * return_count
    material = _closed_material(
        shell,
        candles[index - required_returns : index + 1],
    )
    return shell, material


def _context_by_side(shell: dict, material: dict) -> dict[str, dict]:
    sigma = math.sqrt(float(material["current_variance"]))
    long_context = _base_rule_context(
        shell=shell,
        side="long",
        sigma=sigma,
        material=material,
    )
    return {
        "long": long_context,
        "short": _opposite_side_base_context(long_context),
    }


def _plan(
    *,
    shell: dict,
    plan_group_id: str,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
) -> dict:
    return {
        **shell,
        "plan_id": f"{plan_group_id}:{shell['time_horizon']}",
        "side": side,
        "entry": entry,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
    }


def nested_outcomes(
    *,
    future: list[dict],
    side: str,
    take_profit: float,
    stop_loss: float,
) -> dict[str, dict] | None:
    outcomes = {}
    for horizon, profile in HORIZONS.items():
        candle_count = int(profile["seconds"]) // BASE_INTERVAL_SECONDS
        outcome = _outcome(
            future=future[:candle_count],
            side=side,
            take_profit=take_profit,
            stop_loss=stop_loss,
        )
        if outcome["status"] != "resolved":
            return None
        outcomes[horizon] = outcome
    ordered = sorted(HORIZONS, key=lambda name: int(HORIZONS[name]["seconds"]))
    resolved_label = None
    for horizon in ordered:
        label = outcomes[horizon]["label"]
        if resolved_label is not None and label != resolved_label:
            raise ValueError("nested_first_touch_invariant_failed")
        if label != CLASSES[2]:
            resolved_label = label
    return outcomes


def build_nested_dataset(*, symbols: Iterable[str] = SYMBOLS) -> dict:
    build_protocol()
    NESTED_DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    counters: Counter = Counter()
    by_horizon: Counter = Counter()
    by_partition: Counter = Counter()
    by_symbol: Counter = Counter()
    label_counts: Counter = Counter()
    rule_coverage: Counter = Counter()
    group_hash = hashlib.sha256()
    with gzip.open(NESTED_DATASET_PATH, "wt", encoding="utf-8", newline="\n") as output:
        for symbol in symbols:
            base = read_symbol_5m(symbol)
            base_by_open = {int(row["open_time_ms"]): row for row in base}
            aggregated = {
                horizon: aggregate_candles(
                    base, int(profile["interval_seconds"])
                )
                for horizon, profile in HORIZONS.items()
            }
            index_by_cutoff = {
                horizon: {
                    int(row["close_time_ms"]): index
                    for index, row in enumerate(candles)
                }
                for horizon, candles in aggregated.items()
            }
            reference = aggregated[REFERENCE_HORIZON]
            for reference_index, reference_anchor in enumerate(reference):
                cutoff_ms = int(reference_anchor["close_time_ms"])
                if (cutoff_ms + 1) % (ANCHOR_STEP_SECONDS * 1000) != 0:
                    continue
                partition = partition_for_ms(cutoff_ms)
                if partition is None:
                    continue
                try:
                    indexed = {
                        horizon: index_by_cutoff[horizon][cutoff_ms]
                        for horizon in HORIZONS
                    }
                except KeyError:
                    counters["blocked_anchor_alignment"] += 1
                    continue
                shells = {}
                materials = {}
                contexts = {}
                structures = {}
                try:
                    for horizon in HORIZONS:
                        shell, material = _material_at(
                            symbol=symbol,
                            horizon=horizon,
                            candles=aggregated[horizon],
                            index=indexed[horizon],
                        )
                        shells[horizon] = shell
                        materials[horizon] = material
                        contexts[horizon] = _context_by_side(shell, material)
                        structures[horizon] = _structural_basis(material)
                except (ValueError, ArithmeticError, KeyError):
                    counters["blocked_pretrade"] += 1
                    continue
                reference_sigma = math.sqrt(
                    float(materials[REFERENCE_HORIZON]["current_variance"])
                )
                if not math.isfinite(reference_sigma) or reference_sigma <= 0:
                    counters["blocked_reference_sigma"] += 1
                    continue
                future = _complete_future(
                    base_by_open,
                    cutoff_ms=cutoff_ms,
                    horizon_seconds=MAX_HORIZON_SECONDS,
                )
                if future is None:
                    counters["blocked_future_coverage"] += 1
                    continue
                entry = float(reference_anchor["close"])
                anchor_id = f"{symbol}:{cutoff_ms}"
                counters["anchors"] += 1
                for side in ("long", "short"):
                    direction = 1.0 if side == "long" else -1.0
                    for tp_multiple, sl_multiple in GEOMETRIES:
                        take_profit = entry * math.exp(
                            direction * tp_multiple * reference_sigma
                        )
                        stop_loss = entry * math.exp(
                            -direction * sl_multiple * reference_sigma
                        )
                        group_id = (
                            f"{anchor_id}:{side}:{tp_multiple:.2f}:{sl_multiple:.2f}"
                        )
                        outcomes = nested_outcomes(
                            future=future,
                            side=side,
                            take_profit=take_profit,
                            stop_loss=stop_loss,
                        )
                        if outcomes is None:
                            counters["ambiguous_plan_groups"] += 1
                            continue
                        plans = {
                            horizon: _plan(
                                shell=shells[horizon],
                                plan_group_id=group_id,
                                side=side,
                                entry=entry,
                                take_profit=take_profit,
                                stop_loss=stop_loss,
                            )
                            for horizon in HORIZONS
                        }
                        try:
                            horizon_features = {
                                horizon: flatten_rule_features(
                                    _rule_features_for_plan(
                                        plan=plans[horizon],
                                        material=materials[horizon],
                                        base_context=contexts[horizon][side],
                                        structural_basis=structures[horizon],
                                    )
                                )
                                for horizon in HORIZONS
                            }
                        except (ValueError, ArithmeticError, KeyError):
                            counters["blocked_rule_evaluation"] += 1
                            continue
                        common_features = horizon_features[REFERENCE_HORIZON]
                        group_hash.update((group_id + "\n").encode("utf-8"))
                        counters["plan_groups"] += 1
                        for horizon, profile in HORIZONS.items():
                            seconds = int(profile["seconds"])
                            aware_sigma = reference_sigma * math.sqrt(
                                seconds / REFERENCE_SECONDS
                            )
                            record = {
                                "version": VERSION,
                                "case_id": f"{group_id}:{horizon}",
                                "plan_group_id": group_id,
                                "anchor_id": anchor_id,
                                "inference_cluster_id": week_cluster(cutoff_ms),
                                "partition": partition,
                                "symbol": symbol,
                                "side": side,
                                "time_horizon": horizon,
                                "horizon_seconds": seconds,
                                "analysis_at": iso_ms(cutoff_ms),
                                "entry": entry,
                                "take_profit": take_profit,
                                "stop_loss": stop_loss,
                                "tp_reference_sigma_multiple": tp_multiple,
                                "sl_reference_sigma_multiple": sl_multiple,
                                "reference_sigma_24h": reference_sigma,
                                "horizon_aware_sigma": aware_sigma,
                                "horizon_blind_probabilities": _baseline_probabilities(
                                    side=side,
                                    entry=entry,
                                    take_profit=take_profit,
                                    stop_loss=stop_loss,
                                    sigma=reference_sigma,
                                ),
                                "horizon_aware_probabilities": _baseline_probabilities(
                                    side=side,
                                    entry=entry,
                                    take_profit=take_profit,
                                    stop_loss=stop_loss,
                                    sigma=aware_sigma,
                                ),
                                "common_rule_features": common_features,
                                "horizon_rule_features": horizon_features[horizon],
                                "outcome": outcomes[horizon],
                            }
                            output.write(canonical_json(record) + "\n")
                            counters["cases"] += 1
                            by_horizon[horizon] += 1
                            by_partition[partition] += 1
                            by_symbol[symbol] += 1
                            label_counts[(horizon, outcomes[horizon]["label"])] += 1
                            for name in horizon_features[horizon]:
                                rule_coverage[name] += 1
            print(
                f"NESTED_DATASET {symbol} anchors={counters['anchors']} "
                f"groups={counters['plan_groups']} cases={counters['cases']}",
                flush=True,
            )
    manifest = add_hash(
        {
            "version": VERSION,
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "dataset_path": str(NESTED_DATASET_PATH.relative_to(ROOT)),
            "dataset_sha256": sha256_file(NESTED_DATASET_PATH),
            "plan_group_set_sha256": group_hash.hexdigest(),
            "same_plan_across_horizons": True,
            "reference_volatility_horizon": REFERENCE_HORIZON,
            "reference_volatility_seconds": REFERENCE_SECONDS,
            "anchor_step_seconds": ANCHOR_STEP_SECONDS,
            "symbols": list(symbols),
            "horizon_seconds": {
                name: int(profile["seconds"])
                for name, profile in HORIZONS.items()
            },
            "counts": dict(counters),
            "cases_by_horizon": dict(by_horizon),
            "cases_by_partition": dict(by_partition),
            "cases_by_symbol": dict(by_symbol),
            "labels_by_horizon": {
                f"{horizon}:{label}": value
                for (horizon, label), value in label_counts.items()
            },
            "rule_feature_coverage": dict(rule_coverage),
            "nested_first_touch_invariant": True,
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(NESTED_MANIFEST_PATH, manifest)
    return manifest


def iter_nested_dataset(
    path: Path = NESTED_DATASET_PATH,
) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def validate_nested_dataset() -> dict:
    counters: Counter = Counter()
    current_group_id = None
    current_rows: list[dict] = []

    def validate_group(rows: list[dict]) -> None:
        if not rows:
            return
        counters["plan_groups"] += 1
        if len(rows) != len(HORIZONS):
            counters["invalid_group_size"] += 1
            return
        if {row["time_horizon"] for row in rows} != set(HORIZONS):
            counters["invalid_horizon_set"] += 1
        invariant_fields = (
            "symbol",
            "analysis_at",
            "side",
            "entry",
            "take_profit",
            "stop_loss",
            "plan_group_id",
        )
        for field in invariant_fields:
            if len({canonical_json(row[field]) for row in rows}) != 1:
                counters[f"mismatched_{field}"] += 1
        blind = rows[0]["horizon_blind_probabilities"]
        if any(row["horizon_blind_probabilities"] != blind for row in rows[1:]):
            counters["mismatched_blind_probabilities"] += 1
        ordered = sorted(rows, key=lambda row: int(row["horizon_seconds"]))
        expiry_probabilities = [
            row["horizon_aware_probabilities"][CLASSES[2]] for row in ordered
        ]
        if any(
            right > left + 1e-12
            for left, right in zip(expiry_probabilities, expiry_probabilities[1:])
        ):
            counters["aware_expiry_not_monotonic"] += 1
        resolved = None
        for row in ordered:
            label = row["outcome"]["label"]
            if resolved is not None and label != resolved:
                counters["nested_first_touch_violation"] += 1
            if label != CLASSES[2]:
                resolved = label
            for probability_field in (
                "horizon_blind_probabilities",
                "horizon_aware_probabilities",
            ):
                probabilities = row[probability_field]
                if abs(math.fsum(probabilities.values()) - 1.0) > 1e-12:
                    counters["probability_mass_violation"] += 1
        counters["cases"] += len(rows)

    for row in iter_nested_dataset():
        group_id = row["plan_group_id"]
        if current_group_id is not None and group_id != current_group_id:
            validate_group(current_rows)
            current_rows = []
        current_group_id = group_id
        current_rows.append(row)
    validate_group(current_rows)
    error_counts = {
        name: value
        for name, value in counters.items()
        if name not in {"plan_groups", "cases"} and value
    }
    payload = add_hash(
        {
            "version": "nested-horizon-cohort-validation-v0.1",
            "dataset_sha256": sha256_file(NESTED_DATASET_PATH),
            "plan_groups": counters["plan_groups"],
            "cases": counters["cases"],
            "error_counts": error_counts,
            "valid": not error_counts,
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(NESTED_VALIDATION_PATH, payload)
    return payload


MODEL_SPECS = {
    "horizon_blind_core": {
        "offset": "horizon_blind_probabilities",
        "feature_source": None,
        "duration_interactions": False,
    },
    "horizon_aware_core": {
        "offset": "horizon_aware_probabilities",
        "feature_source": None,
        "duration_interactions": False,
    },
    "horizon_blind_rules": {
        "offset": "horizon_blind_probabilities",
        "feature_source": "common_rule_features",
        "duration_interactions": False,
    },
    "horizon_aware_rules": {
        "offset": "horizon_aware_probabilities",
        "feature_source": "horizon_rule_features",
        "duration_interactions": False,
    },
    "horizon_aware_interactions": {
        "offset": "horizon_aware_probabilities",
        "feature_source": "horizon_rule_features",
        "duration_interactions": True,
    },
}


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def raw_model_features(row: dict, spec_name: str) -> dict[str, float]:
    spec = MODEL_SPECS[spec_name]
    result = {"intercept": 1.0}
    source_name = spec["feature_source"]
    if source_name is not None:
        source = row[source_name]
        result.update({name: float(value) for name, value in source.items()})
    if spec["duration_interactions"]:
        duration = math.log(float(row["horizon_seconds"]) / REFERENCE_SECONDS)
        result["log_duration_ratio"] = duration
        result["log_duration_ratio_squared"] = duration * duration
        source = row[source_name]
        for name, value in source.items():
            result[f"{name}::x_log_duration"] = float(value) * duration
            result[f"{name}::x_log_duration_squared"] = (
                float(value) * duration * duration
            )
    return result


def sample_rows(
    partitions: set[str],
    *,
    per_horizon: int = FIT_CASES_PER_HORIZON,
) -> list[dict]:
    heaps: dict[str, list[tuple[int, str, dict]]] = {
        horizon: [] for horizon in HORIZONS
    }
    for row in iter_nested_dataset():
        if row["partition"] not in partitions:
            continue
        horizon = row["time_horizon"]
        score = int.from_bytes(
            hashlib.sha256(
                f"{RANDOM_SEED}:{row['plan_group_id']}".encode("utf-8")
            ).digest()[:8],
            "big",
        )
        item = (-score, row["case_id"], row)
        heap = heaps[horizon]
        if len(heap) < per_horizon:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    return [
        item[2]
        for horizon in HORIZONS
        for item in sorted(heaps[horizon], reverse=True)
    ]


def fit_scaling(rows: list[dict], spec_name: str) -> dict[str, dict[str, float]]:
    raw = [raw_model_features(row, spec_name) for row in rows]
    names = tuple(raw[0])
    result = {}
    for name in names:
        if name == "intercept":
            continue
        values = [item[name] for item in raw]
        mean = _mean(values)
        variance = _mean([(value - mean) ** 2 for value in values])
        result[name] = {
            "mean": mean,
            "scale": max(math.sqrt(variance), 1e-12),
        }
    return result


def standardized_features(
    row: dict,
    spec_name: str,
    scaling: dict[str, dict[str, float]],
) -> dict[str, float]:
    raw = raw_model_features(row, spec_name)
    return {
        name: (
            value
            if name == "intercept"
            else (value - scaling[name]["mean"]) / scaling[name]["scale"]
        )
        for name, value in raw.items()
    }


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    maximum = max(logits.values())
    weights = {name: math.exp(value - maximum) for name, value in logits.items()}
    total = math.fsum(weights.values())
    return {name: value / total for name, value in weights.items()}


def predict_model(
    row: dict,
    model: dict,
) -> dict[str, float]:
    spec = MODEL_SPECS[model["spec_name"]]
    base = row[spec["offset"]]
    features = standardized_features(
        row, model["spec_name"], model["scaling"]
    )
    logits = {
        name: math.log(max(float(base[name]), 1e-15)) for name in CLASSES
    }
    for cause in CLASSES[:2]:
        logits[cause] += math.fsum(
            float(model["coefficients"][cause].get(name, 0.0)) * value
            for name, value in features.items()
        )
    return _softmax(logits)


def fit_model(
    rows: list[dict],
    *,
    spec_name: str,
    ridge: float,
    scaling: dict[str, dict[str, float]],
) -> dict:
    compiled = [
        (
            row[MODEL_SPECS[spec_name]["offset"]],
            row["outcome"]["label"],
            standardized_features(row, spec_name, scaling),
        )
        for row in rows
    ]
    names = tuple(compiled[0][2])
    coefficients = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    first = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    second = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    row_count = len(compiled)
    for iteration in range(1, FIT_ITERATIONS + 1):
        gradients = {
            cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
        }
        for base, label, features in compiled:
            logits = {
                name: math.log(max(float(base[name]), 1e-15))
                for name in CLASSES
            }
            for cause in CLASSES[:2]:
                logits[cause] += math.fsum(
                    coefficients[cause][name] * value
                    for name, value in features.items()
                )
            probabilities = _softmax(logits)
            for cause in CLASSES[:2]:
                residual = probabilities[cause] - (
                    1.0 if label == cause else 0.0
                )
                for name, value in features.items():
                    gradients[cause][name] += residual * value / row_count
        for cause in CLASSES[:2]:
            for name in names:
                if name != "intercept":
                    gradients[cause][name] += (
                        ridge * coefficients[cause][name] / row_count
                    )
                gradient = max(-10.0, min(10.0, gradients[cause][name]))
                first[cause][name] = 0.9 * first[cause][name] + 0.1 * gradient
                second[cause][name] = (
                    0.999 * second[cause][name] + 0.001 * gradient * gradient
                )
                corrected_first = first[cause][name] / (1.0 - 0.9**iteration)
                corrected_second = second[cause][name] / (
                    1.0 - 0.999**iteration
                )
                coefficients[cause][name] -= 0.03 * corrected_first / (
                    math.sqrt(corrected_second) + 1e-8
                )
    return {
        "spec_name": spec_name,
        "ridge": ridge,
        "scaling": scaling,
        "coefficients": coefficients,
        "fit_case_count": row_count,
    }


def zero_model(spec_name: str) -> dict:
    return {
        "spec_name": spec_name,
        "ridge": None,
        "scaling": {},
        "coefficients": {cause: {"intercept": 0.0} for cause in CLASSES[:2]},
        "fit_case_count": 0,
    }


def _losses(label: str, probabilities: dict[str, float]) -> tuple[float, float]:
    log_loss = -math.log(max(probabilities[label], 1e-15))
    brier = math.fsum(
        (probabilities[name] - (1.0 if name == label else 0.0)) ** 2
        for name in CLASSES
    )
    return log_loss, brier


def evaluate_model(model: dict, partition: str) -> dict:
    sums = {horizon: [0, 0.0, 0.0, Counter()] for horizon in HORIZONS}
    for row in iter_nested_dataset():
        if row["partition"] != partition:
            continue
        probabilities = predict_model(row, model)
        label = row["outcome"]["label"]
        log_loss, brier = _losses(label, probabilities)
        accumulator = sums[row["time_horizon"]]
        accumulator[0] += 1
        accumulator[1] += log_loss
        accumulator[2] += brier
        accumulator[3][label] += 1
    by_horizon = {
        horizon: {
            "n": values[0],
            "log_loss_3c": values[1] / values[0],
            "brier_3c": values[2] / values[0],
            "class_counts": dict(values[3]),
        }
        for horizon, values in sums.items()
    }
    return {
        "macro_horizon_log_loss_3c": _mean(
            [item["log_loss_3c"] for item in by_horizon.values()]
        ),
        "macro_horizon_brier_3c": _mean(
            [item["brier_3c"] for item in by_horizon.values()]
        ),
        "by_horizon": by_horizon,
    }


def paired_comparison(
    left: dict,
    right: dict,
    partition: str,
    *,
    seed: int,
) -> dict:
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in iter_nested_dataset():
        if row["partition"] != partition:
            continue
        label = row["outcome"]["label"]
        left_losses = _losses(label, predict_model(row, left))
        right_losses = _losses(label, predict_model(row, right))
        key = (row["inference_cluster_id"], row["time_horizon"])
        accumulator = grouped.setdefault(key, [0.0, 0.0, 0])
        accumulator[0] += right_losses[0] - left_losses[0]
        accumulator[1] += right_losses[1] - left_losses[1]
        accumulator[2] += 1
    by_week: dict[str, dict[str, tuple[float, float]]] = {}
    horizon_values: dict[str, list[tuple[float, float]]] = {
        horizon: [] for horizon in HORIZONS
    }
    for (week, horizon), values in grouped.items():
        pair = (values[0] / values[2], values[1] / values[2])
        by_week.setdefault(week, {})[horizon] = pair
        horizon_values[horizon].append(pair)
    weekly = []
    for week in sorted(by_week):
        values = by_week[week]
        if set(values) != set(HORIZONS):
            continue
        weekly.append(
            (
                _mean([values[horizon][0] for horizon in HORIZONS]),
                _mean([values[horizon][1] for horizon in HORIZONS]),
            )
        )
    result = {
        "complete_utc_weeks": len(weekly),
        "mean_macro_log_loss_improvement": _mean([item[0] for item in weekly]),
        "mean_macro_brier_improvement": _mean([item[1] for item in weekly]),
        "log_loss_weekly_bootstrap_95ci": None,
        "brier_weekly_bootstrap_95ci": None,
        "by_horizon": {
            horizon: {
                "time_blocks": len(values),
                "mean_log_loss_improvement": _mean(
                    [item[0] for item in values]
                ),
                "mean_brier_improvement": _mean(
                    [item[1] for item in values]
                ),
            }
            for horizon, values in horizon_values.items()
        },
    }
    if len(weekly) < 10:
        return result
    rng = random.Random(seed)
    indices = list(range(len(weekly)))
    log_samples = []
    brier_samples = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [weekly[rng.choice(indices)] for _ in indices]
        log_samples.append(_mean([item[0] for item in sample]))
        brier_samples.append(_mean([item[1] for item in sample]))
    result["log_loss_weekly_bootstrap_95ci"] = [
        _percentile(log_samples, 0.025),
        _percentile(log_samples, 0.975),
    ]
    result["brier_weekly_bootstrap_95ci"] = [
        _percentile(brier_samples, 0.025),
        _percentile(brier_samples, 0.975),
    ]
    return result


def positive_mean(comparison: dict) -> bool:
    return (
        comparison["mean_macro_log_loss_improvement"] > 0
        and comparison["mean_macro_brier_improvement"] > 0
    )


def final_gate_passed(comparison: dict) -> bool:
    log_ci = comparison["log_loss_weekly_bootstrap_95ci"]
    brier_ci = comparison["brier_weekly_bootstrap_95ci"]
    return (
        log_ci is not None
        and brier_ci is not None
        and log_ci[0] > 0
        and brier_ci[0] > 0
        and all(
            item["mean_log_loss_improvement"] >= 0
            and item["mean_brier_improvement"] >= 0
            for item in comparison["by_horizon"].values()
        )
    )


def uniform_incremental_gate_passed(comparison: dict) -> bool:
    """Require a rule layer to improve the proper time-aware core everywhere."""
    return final_gate_passed(comparison)


def select_ridge(
    *,
    spec_name: str,
    development_rows: list[dict],
) -> tuple[dict, list[dict]]:
    scaling = fit_scaling(development_rows, spec_name)
    candidates = []
    for ridge in RIDGE_CANDIDATES:
        model = fit_model(
            development_rows,
            spec_name=spec_name,
            ridge=ridge,
            scaling=scaling,
        )
        candidates.append(
            {
                "ridge": ridge,
                "model": model,
                "calibration": evaluate_model(model, "calibration"),
            }
        )
    selected = min(
        candidates,
        key=lambda item: (
            item["calibration"]["macro_horizon_log_loss_3c"],
            item["calibration"]["macro_horizon_brier_3c"],
            item["ridge"],
        ),
    )
    return selected, candidates


def evaluate_horizon_value() -> dict:
    protocol = build_protocol()
    manifest = json.loads(NESTED_MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["dataset_sha256"] != sha256_file(NESTED_DATASET_PATH):
        raise ValueError("nested_dataset_hash_mismatch")
    validation = validate_nested_dataset()
    if not validation["valid"]:
        raise ValueError("nested_dataset_invariants_failed")
    development_rows = sample_rows({"development"})
    selected_models = {}
    ridge_audits = {}
    for spec_name in MODEL_SPECS:
        selected, candidates = select_ridge(
            spec_name=spec_name,
            development_rows=development_rows,
        )
        selected_models[spec_name] = selected["model"]
        ridge_audits[spec_name] = {
            "selected_ridge": selected["ridge"],
            "calibration_by_ridge": [
                {
                    "ridge": item["ridge"],
                    "metrics": item["calibration"],
                }
                for item in candidates
            ],
        }
        print(
            f"HORIZON_MODEL {spec_name} ridge={selected['ridge']}",
            flush=True,
        )
    physics = {
        partition: paired_comparison(
            zero_model("horizon_aware_core"),
            zero_model("horizon_blind_core"),
            partition,
            seed=RANDOM_SEED + index,
        )
        for index, partition in enumerate(("calibration", "rule_test"), 1)
    }
    counterpart = {
        "horizon_aware_core": "horizon_blind_core",
        "horizon_aware_rules": "horizon_blind_rules",
        "horizon_aware_interactions": "horizon_blind_rules",
    }
    comparisons = {}
    eligible = []
    rule_test_metrics = {}
    for index, spec_name in enumerate(MODEL_SPECS):
        rule_test_metrics[spec_name] = evaluate_model(
            selected_models[spec_name], "rule_test"
        )
        if spec_name not in counterpart:
            continue
        right_name = counterpart[spec_name]
        calibration = paired_comparison(
            selected_models[spec_name],
            selected_models[right_name],
            "calibration",
            seed=RANDOM_SEED + 100 + index,
        )
        rule_test = paired_comparison(
            selected_models[spec_name],
            selected_models[right_name],
            "rule_test",
            seed=RANDOM_SEED + 200 + index,
        )
        comparisons[spec_name] = {
            "counterpart": right_name,
            "calibration": calibration,
            "rule_test": rule_test,
        }
        if positive_mean(calibration) and positive_mean(rule_test):
            eligible.append(spec_name)
    selected_candidate_name = (
        min(
            eligible,
            key=lambda name: (
                rule_test_metrics[name]["macro_horizon_log_loss_3c"],
                rule_test_metrics[name]["macro_horizon_brier_3c"],
                name,
            ),
        )
        if eligible
        else None
    )
    final_payload = None
    candidate_artifact = None
    if selected_candidate_name is not None:
        right_name = counterpart[selected_candidate_name]
        prefinal_rows = sample_rows(
            {"development", "calibration", "rule_test"}
        )
        selected_ridge = selected_models[selected_candidate_name]["ridge"]
        right_ridge = selected_models[right_name]["ridge"]
        final_candidate = fit_model(
            prefinal_rows,
            spec_name=selected_candidate_name,
            ridge=selected_ridge,
            scaling=fit_scaling(prefinal_rows, selected_candidate_name),
        )
        final_counterpart = fit_model(
            prefinal_rows,
            spec_name=right_name,
            ridge=right_ridge,
            scaling=fit_scaling(prefinal_rows, right_name),
        )
        final_comparison = paired_comparison(
            final_candidate,
            final_counterpart,
            "final_test",
            seed=RANDOM_SEED + 999,
        )
        final_metrics = evaluate_model(final_candidate, "final_test")
        candidate_vs_blind_gate_passed = final_gate_passed(final_comparison)
        final_horizon_physics_comparison = paired_comparison(
            zero_model("horizon_aware_core"),
            zero_model("horizon_blind_core"),
            "final_test",
            seed=RANDOM_SEED + 1600,
        )
        horizon_gate_passed = final_gate_passed(
            final_horizon_physics_comparison
        )
        diagnostic_models = {
            "horizon_aware_core": fit_model(
                prefinal_rows,
                spec_name="horizon_aware_core",
                ridge=selected_models["horizon_aware_core"]["ridge"],
                scaling=fit_scaling(prefinal_rows, "horizon_aware_core"),
            ),
            "horizon_aware_rules": fit_model(
                prefinal_rows,
                spec_name="horizon_aware_rules",
                ridge=selected_models["horizon_aware_rules"]["ridge"],
                scaling=fit_scaling(prefinal_rows, "horizon_aware_rules"),
            ),
        }
        incremental_rule_diagnostics = {
            name: {
                "metrics": evaluate_model(model, "final_test"),
                "candidate_comparison": paired_comparison(
                    final_candidate,
                    model,
                    "final_test",
                    seed=RANDOM_SEED + 1700 + index,
                ),
            }
            for index, (name, model) in enumerate(diagnostic_models.items())
        }
        rule_layer_gate_passed = uniform_incremental_gate_passed(
            incremental_rule_diagnostics["horizon_aware_core"][
                "candidate_comparison"
            ]
        )
        final_payload = {
            "selected_candidate": selected_candidate_name,
            "counterpart": right_name,
            "candidate_metrics": final_metrics,
            "comparison": final_comparison,
            "candidate_vs_blind_gate_passed": candidate_vs_blind_gate_passed,
            "horizon_physics_comparison": final_horizon_physics_comparison,
            "horizon_gate_passed": horizon_gate_passed,
            "post_selection_rule_diagnostics": incremental_rule_diagnostics,
            "rule_layer_uniform_gate_passed": rule_layer_gate_passed,
        }
        candidate_artifact = add_hash(
            {
                "version": "single-engine-horizon-candidate-v0.1",
                "status": (
                    "historically_qualified_for_prospective_shadow_only"
                    if horizon_gate_passed
                    and candidate_vs_blind_gate_passed
                    and not rule_layer_gate_passed
                    else "historically_qualified_local_candidate"
                    if horizon_gate_passed
                    and candidate_vs_blind_gate_passed
                    and rule_layer_gate_passed
                    else "rejected_at_sealed_final_gate"
                ),
                "single_engine": True,
                "spec_name": selected_candidate_name,
                "counterpart": right_name,
                "ridge": selected_ridge,
                "scaling": final_candidate["scaling"],
                "coefficients": final_candidate["coefficients"],
                "feature_source": MODEL_SPECS[selected_candidate_name][
                    "feature_source"
                ],
                "offset": MODEL_SPECS[selected_candidate_name]["offset"],
                "duration_interactions": MODEL_SPECS[
                    selected_candidate_name
                ]["duration_interactions"],
                "protocol_sha256": protocol["canonical_payload_sha256"],
                "dataset_sha256": manifest["dataset_sha256"],
                "production_authorized": False,
                "production_effect": "none",
                "automatic_weight_updates": False,
                "candidate_vs_blind_gate_passed": candidate_vs_blind_gate_passed,
                "horizon_gate_passed": horizon_gate_passed,
                "rule_layer_uniform_gate_passed": rule_layer_gate_passed,
            }
        )
        write_json(CANDIDATE_PATH, candidate_artifact)
    decision = (
        "horizon_value_demonstrated_rule_layer_ready_for_prospective_shadow_only"
        if final_payload
        and final_payload["horizon_gate_passed"]
        and final_payload["candidate_vs_blind_gate_passed"]
        and not final_payload["rule_layer_uniform_gate_passed"]
        else "horizon_and_rule_layer_demonstrated_candidate_ready_for_prospective_shadow"
        if final_payload
        and final_payload["horizon_gate_passed"]
        and final_payload["candidate_vs_blind_gate_passed"]
        and final_payload["rule_layer_uniform_gate_passed"]
        else "horizon_value_not_sufficient_for_engine_change"
    )
    payload = add_hash(
        {
            "version": EVALUATION_VERSION,
            "protocol_sha256": protocol["canonical_payload_sha256"],
            "manifest_sha256": manifest["canonical_payload_sha256"],
            "dataset_validation_sha256": validation[
                "canonical_payload_sha256"
            ],
            "dataset_sha256": manifest["dataset_sha256"],
            "single_engine": True,
            "development_fit_cases": len(development_rows),
            "ridge_audits": ridge_audits,
            "physics_horizon_value": physics,
            "rule_test_metrics": rule_test_metrics,
            "time_aware_comparisons": comparisons,
            "eligible_time_aware_candidates": eligible,
            "selected_candidate": selected_candidate_name,
            "sealed_final": final_payload,
            "candidate_artifact_sha256": (
                candidate_artifact["canonical_payload_sha256"]
                if candidate_artifact is not None
                else None
            ),
            "decision": decision,
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(RESULT_PATH, payload)
    write_horizon_report(payload)
    return payload


def write_horizon_report(payload: dict) -> None:
    lines = [
        "# Valor incremental del horizonte en un motor único",
        "",
        f"- Decisión: **`{payload['decision']}`**.",
        "- Motores independientes por marco: **no**.",
        "- Cambio en producción: **ninguno**.",
        "",
        "## Comparación física: mismo plan, sólo cambia el tiempo",
        "",
        "| Partición | Δ log-loss | IC95% semanal | Δ Brier | IC95% semanal |",
        "|---|---:|---|---:|---|",
    ]
    for partition, item in payload["physics_horizon_value"].items():
        lines.append(
            f"| `{partition}` | "
            f"{item['mean_macro_log_loss_improvement']:.6f} | "
            f"`{item['log_loss_weekly_bootstrap_95ci']}` | "
            f"{item['mean_macro_brier_improvement']:.6f} | "
            f"`{item['brier_weekly_bootstrap_95ci']}` |"
        )
    lines.extend(
        [
            "",
            "## Modelos con reglas",
            "",
            "| Candidato temporal | Comparador sin horizonte | Calibración positiva | Selección positiva |",
            "|---|---|---|---|",
        ]
    )
    for name, item in payload["time_aware_comparisons"].items():
        lines.append(
            f"| `{name}` | `{item['counterpart']}` | "
            f"{positive_mean(item['calibration'])} | "
            f"{positive_mean(item['rule_test'])} |"
        )
    sealed = payload.get("sealed_final")
    if sealed:
        lines.extend(
            [
                "",
                "## Puerta final sellada",
                "",
                f"- Candidato: `{sealed['selected_candidate']}`.",
                f"- Comparador: `{sealed['counterpart']}`.",
                "- Núcleo temporal frente al núcleo ciego: "
                f"**{sealed['horizon_gate_passed']}**.",
                "- Candidato completo frente al comparador ciego: "
                f"**{sealed['candidate_vs_blind_gate_passed']}**.",
                "- Reglas frente al núcleo temporal en todos los horizontes: "
                f"**{sealed['rule_layer_uniform_gate_passed']}**.",
                f"- Δ log-loss: {sealed['comparison']['mean_macro_log_loss_improvement']:.6f}.",
                f"- Δ Brier: {sealed['comparison']['mean_macro_brier_improvement']:.6f}.",
                "",
                "## Diagnóstico incremental posterior a la selección",
                "",
                "Este diagnóstico no reabre la selección: comprueba si las reglas "
                "aportan más que usar correctamente la duración.",
                "",
                "| Comparador temporal | Δ log-loss | IC95% | Δ Brier | IC95% |",
                "|---|---:|---|---:|---|",
            ]
        )
        for name, diagnostic in sealed[
            "post_selection_rule_diagnostics"
        ].items():
            comparison = diagnostic["candidate_comparison"]
            lines.append(
                f"| `{name}` | "
                f"{comparison['mean_macro_log_loss_improvement']:.6f} | "
                f"`{comparison['log_loss_weekly_bootstrap_95ci']}` | "
                f"{comparison['mean_macro_brier_improvement']:.6f} | "
                f"`{comparison['brier_weekly_bootstrap_95ci']}` |"
            )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
