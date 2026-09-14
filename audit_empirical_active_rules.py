from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import statistics
from collections import Counter, OrderedDict, defaultdict
from itertools import combinations
from pathlib import Path

from build_empirical_temporal_engine import (
    GEOMETRY_GRID,
    PARTITIONS,
    RANDOM_SEED,
    RULE_GROUPS,
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


def _stage_feature(stage: str, feature_suffix: str) -> str:
    return f"{stage}::{feature_suffix}"


TARGETED_INTERACTIONS = OrderedDict(
    (
        (
            "intraday_short",
            OrderedDict(
                (
                    (
                        "sigma_x_volatility_rank",
                        (
                            _stage_feature("intraday_short", "log_context_sigma"),
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
                            ),
                        ),
                    ),
                    (
                        "sigma_x_atr_rank",
                        (
                            _stage_feature("intraday_short", "log_context_sigma"),
                            _stage_feature(
                                "intraday_short",
                                "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
                            ),
                        ),
                    ),
                    (
                        "path_h_x_path_2h",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
                            ),
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                        ),
                    ),
                    (
                        "path_2h_x_path_4h",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
                            ),
                        ),
                    ),
                )
            ),
        ),
        (
            "intraday_wide",
            OrderedDict(
                (
                    (
                        "sigma_transition_short_to_wide",
                        (
                            _stage_feature("intraday_short", "log_context_sigma"),
                            _stage_feature("intraday_wide", "log_context_sigma"),
                        ),
                    ),
                    (
                        "volatility_rank_transition_short_to_wide",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
                            ),
                            _stage_feature(
                                "intraday_wide",
                                "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
                            ),
                        ),
                    ),
                    (
                        "path_transition_short_to_wide",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
                            ),
                            _stage_feature(
                                "intraday_wide",
                                "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
                            ),
                        ),
                    ),
                    (
                        "inherited_2h_x_wide_path",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                            _stage_feature(
                                "intraday_wide",
                                "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
                            ),
                        ),
                    ),
                    (
                        "wide_sigma_x_bollinger_rank",
                        (
                            _stage_feature("intraday_wide", "log_context_sigma"),
                            _stage_feature(
                                "intraday_wide",
                                "LIB-CAND-COMPRESSION-001::compression_vector.bollinger_width_rank",
                            ),
                        ),
                    ),
                    (
                        "wide_path_2h_x_path_4h",
                        (
                            _stage_feature(
                                "intraday_wide",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                            _stage_feature(
                                "intraday_wide",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
                            ),
                        ),
                    ),
                )
            ),
        ),
        (
            "short_swing",
            OrderedDict(
                (
                    (
                        "sigma_transition_wide_to_swing",
                        (
                            _stage_feature("intraday_wide", "log_context_sigma"),
                            _stage_feature("short_swing", "log_context_sigma"),
                        ),
                    ),
                    (
                        "volatility_rank_transition_wide_to_swing",
                        (
                            _stage_feature(
                                "intraday_wide",
                                "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
                            ),
                            _stage_feature(
                                "short_swing",
                                "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60",
                            ),
                        ),
                    ),
                    (
                        "inherited_2h_x_swing_2h",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                            _stage_feature(
                                "short_swing",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                        ),
                    ),
                    (
                        "inherited_path_2h_x_path_4h",
                        (
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                            _stage_feature(
                                "intraday_short",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
                            ),
                        ),
                    ),
                    (
                        "swing_path_h_x_path_2h",
                        (
                            _stage_feature(
                                "short_swing",
                                "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
                            ),
                            _stage_feature(
                                "short_swing",
                                "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                            ),
                        ),
                    ),
                    (
                        "atr_rank_transition_short_to_swing",
                        (
                            _stage_feature(
                                "intraday_short",
                                "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
                            ),
                            _stage_feature(
                                "short_swing",
                                "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
                            ),
                        ),
                    ),
                )
            ),
        ),
    )
)


def candidate_feature_sets() -> OrderedDict[str, dict[str, tuple[str, ...]]]:
    full = {
        horizon: tuple(expanded_feature_names(horizon)) for horizon in STAGE_ORDER
    }
    short_atr = _stage_feature(
        "intraday_short",
        "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
    )
    swing_atr = _stage_feature(
        "short_swing",
        "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank",
    )
    swing_path_2h = _stage_feature(
        "short_swing",
        "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
    )

    def excluding(*excluded: str) -> dict[str, tuple[str, ...]]:
        blocked = set(excluded)
        return {
            horizon: tuple(name for name in names if name not in blocked)
            for horizon, names in full.items()
        }

    return OrderedDict(
        (
            ("v0_9_full", full),
            ("remove_short_atr", excluding(short_atr)),
            (
                "remove_short_and_swing_atr",
                excluding(short_atr, swing_atr),
            ),
            (
                "evidence_pruned",
                excluding(short_atr, swing_atr, swing_path_2h),
            ),
            (
                "remove_all_atr_and_swing_path_2h",
                {
                    horizon: tuple(
                        name
                        for name in names
                        if "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank"
                        not in name
                        and name != swing_path_2h
                    )
                    for horizon, names in full.items()
                },
            ),
        )
    )


DERIVED_PATH_FEATURES = OrderedDict(
    (
        (
            "DERIVED-PATH::directional_multiscale_mean",
            {
                "formula": "mean(efficiency_H, efficiency_2H, efficiency_4H)",
                "meaning": "combined direction and strength across all three scales",
                "signed": True,
            },
        ),
        (
            "DERIVED-PATH::directional_alignment_vote",
            {
                "formula": "mean(sign(efficiency_H), sign(efficiency_2H), sign(efficiency_4H))",
                "meaning": "fraction and direction of aligned temporal scales",
                "signed": True,
            },
        ),
        (
            "DERIVED-PATH::directional_recent_acceleration",
            {
                "formula": "efficiency_H - mean(efficiency_2H, efficiency_4H)",
                "meaning": "recent directional impulse relative to its wider background",
                "signed": True,
            },
        ),
        (
            "DERIVED-PATH::cross_scale_dispersion",
            {
                "formula": "population_stdev(efficiency_H, efficiency_2H, efficiency_4H)",
                "meaning": "temporal disagreement independent of trade side",
                "signed": False,
            },
        ),
        (
            "DERIVED-PATH::directional_consistent_strength",
            {
                "formula": "signed_min_abs_efficiency_when_all_three_scales_agree_else_zero",
                "meaning": "strict multiscale alignment with weakest-link strength",
                "signed": True,
            },
        ),
    )
)


CANDIDATE_CONTEXT_FEATURES = OrderedDict(
    (
        (
            "LIB-CAND-EMA-TREND-001::side_adjusted_close_vs_ema50_log",
            {
                "formula": "trade_side * log(close / EMA50)",
                "family": "trend_momentum",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-EMA-TREND-001::side_adjusted_ema50_vs_ema200_log",
            {
                "formula": "trade_side * log(EMA50 / EMA200)",
                "family": "trend_momentum",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-EMA-TREND-001::side_adjusted_slope_atr",
            {
                "formula": "trade_side * (EMA50_now - EMA50_6_bars_ago) / ATR14",
                "family": "trend_momentum",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-RSI-WILDER-001::side_adjusted_centered_rsi",
            {
                "formula": "trade_side * (RSI14 - 50) / 50",
                "family": "trend_momentum",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-ATR-EXTENSION-001::side_adjusted_extension_atr",
            {
                "formula": "trade_side * (close - EMA20) / ATR14",
                "family": "trend_momentum",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-RELATIVE-VOLUME-001::log_relative_horizon_volume",
            {
                "formula": "log(current_horizon_volume / prior_horizon_volume)",
                "family": "volume_flow",
                "signed": False,
            },
        ),
        (
            "LIB-CAND-CVD-SLOPE-001::side_adjusted_normalized_cvd_slope",
            {
                "formula": "trade_side * normalized_CVD_slope",
                "family": "volume_flow",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-ABSORPTION-001::side_adjusted_horizon_displacement_atr",
            {
                "formula": "trade_side * horizon_price_displacement / ATR14",
                "family": "volume_flow",
                "signed": True,
            },
        ),
        (
            "LIB-CAND-ABSORPTION-001::flow_opposing_wick_ratio",
            {
                "formula": "opposing_wick_flow / total_flow",
                "family": "volume_flow",
                "signed": False,
            },
        ),
    )
)


def expanded_candidate_context_feature_names(horizon: str) -> list[str]:
    return [
        _stage_feature(stage, feature)
        for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
        for feature in CANDIDATE_CONTEXT_FEATURES
    ]


def _candidate_context_feature_map(
    record: dict,
    horizon: str,
    orientation: int,
) -> dict[str, float]:
    raw = _raw_feature_map(record, horizon, orientation)
    names = expanded_candidate_context_feature_names(horizon)
    return {name: float(raw[name]) for name in names}


def candidate_context_coverage(records: list[dict]) -> dict:
    result = {}
    for horizon in STAGE_ORDER:
        names = expanded_candidate_context_feature_names(horizon)
        valid = Counter()
        for record in records:
            for orientation in DIRECTIONS:
                values = _candidate_context_feature_map(record, horizon, orientation)
                for name in names:
                    if math.isfinite(values[name]):
                        valid[name] += 1
        expected = len(records) * len(DIRECTIONS)
        result[horizon] = {
            name: {
                "available_orientations": valid[name],
                "expected_orientations": expected,
                "coverage_fraction": valid[name] / expected if expected else 0.0,
            }
            for name in names
        }
    return result


CONFIRMED_SHORT_EMA_CROSS = _stage_feature(
    "intraday_short",
    "LIB-CAND-EMA-TREND-001::side_adjusted_ema50_vs_ema200_log",
)


def confirmed_short_ema_candidate_sets() -> OrderedDict[
    str, dict[str, tuple[str, ...]]
]:
    baseline = candidate_feature_sets()["evidence_pruned"]
    candidate = {horizon: tuple(names) for horizon, names in baseline.items()}
    candidate["intraday_short"] = (
        *candidate["intraday_short"],
        CONFIRMED_SHORT_EMA_CROSS,
    )
    return OrderedDict(
        (
            ("evidence_pruned_active", baseline),
            ("evidence_pruned_plus_confirmed_short_ema_cross", candidate),
        )
    )


def production_baseline_ema_candidate_sets() -> OrderedDict[
    str, dict[str, tuple[str, ...]]
]:
    production = candidate_feature_sets()["v0_9_full"]
    production_plus = {
        horizon: tuple(names) for horizon, names in production.items()
    }
    production_plus["intraday_short"] = (
        *production_plus["intraday_short"],
        CONFIRMED_SHORT_EMA_CROSS,
    )
    pruned_plus = confirmed_short_ema_candidate_sets()[
        "evidence_pruned_plus_confirmed_short_ema_cross"
    ]
    return OrderedDict(
        (
            ("v0_9_production", production),
            ("v0_9_plus_confirmed_short_ema_cross", production_plus),
            ("evidence_pruned_plus_confirmed_short_ema_cross", pruned_plus),
        )
    )


def expanded_derived_feature_names(horizon: str) -> list[str]:
    return [
        f"{stage}::{feature}"
        for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]
        for feature in DERIVED_PATH_FEATURES
    ]


def _derived_feature_map(
    record: dict,
    horizon: str,
    orientation: int,
) -> dict[str, float]:
    result = {}
    for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]:
        raw = _raw_feature_map(record, stage, orientation)
        path_h = float(
            raw[
                _stage_feature(
                    stage,
                    "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
                )
            ]
        )
        path_2h = float(
            raw[
                _stage_feature(
                    stage,
                    "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
                )
            ]
        )
        path_4h = float(
            raw[
                _stage_feature(
                    stage,
                    "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
                )
            ]
        )
        values = (path_h, path_2h, path_4h)
        signs = tuple(1.0 if value > 0 else -1.0 if value < 0 else 0.0 for value in values)
        if all(value > 0 for value in values):
            consistent_strength = min(abs(value) for value in values)
        elif all(value < 0 for value in values):
            consistent_strength = -min(abs(value) for value in values)
        else:
            consistent_strength = 0.0
        stage_values = {
            "DERIVED-PATH::directional_multiscale_mean": statistics.fmean(values),
            "DERIVED-PATH::directional_alignment_vote": statistics.fmean(signs),
            "DERIVED-PATH::directional_recent_acceleration": path_h
            - statistics.fmean((path_2h, path_4h)),
            "DERIVED-PATH::cross_scale_dispersion": statistics.pstdev(values),
            "DERIVED-PATH::directional_consistent_strength": consistent_strength,
        }
        result.update(
            {_stage_feature(stage, name): value for name, value in stage_values.items()}
        )
    return result


def semantic_derived_feature_audit(records: list[dict]) -> dict:
    result = {}
    for stage in STAGE_ORDER:
        result[stage] = {}
        long_maps = [_derived_feature_map(record, stage, 0) for record in records]
        short_maps = [_derived_feature_map(record, stage, 1) for record in records]
        for feature_name, contract in DERIVED_PATH_FEATURES.items():
            expanded = _stage_feature(stage, feature_name)
            long_values = [values[expanded] for values in long_maps]
            short_values = [values[expanded] for values in short_maps]
            expected = (
                [-value for value in long_values]
                if contract["signed"]
                else list(long_values)
            )
            transform_error = max(
                (abs(actual - wanted) for actual, wanted in zip(short_values, expected)),
                default=0.0,
            )
            result[stage][feature_name] = {
                "contract": contract,
                "long_profile": _profile(long_values),
                "short_profile": _profile(short_values),
                "maximum_side_transform_error": transform_error,
                "semantic_contract_passed": transform_error <= 1e-12,
            }
    return result


def _combined_context_feature_map(
    record: dict,
    horizon: str,
    orientation: int,
) -> dict[str, float]:
    return {
        **_raw_feature_map(record, horizon, orientation),
        **_derived_feature_map(record, horizon, orientation),
    }


def derived_context_candidate_sets() -> OrderedDict[str, dict[str, tuple[str, ...]]]:
    pruned = candidate_feature_sets()["evidence_pruned"]
    volatility_suffix = (
        "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60"
    )
    atr_suffix = "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank"
    bollinger_suffix = (
        "LIB-CAND-COMPRESSION-001::compression_vector.bollinger_width_rank"
    )

    def replacement(*derived_suffixes: str) -> dict[str, tuple[str, ...]]:
        result = {}
        for horizon in STAGE_ORDER:
            names = []
            for stage in STAGE_ORDER[: STAGE_ORDER.index(horizon) + 1]:
                names.extend(
                    (
                        _stage_feature(stage, volatility_suffix),
                        _stage_feature(stage, bollinger_suffix),
                        _stage_feature(stage, "log_context_sigma"),
                    )
                )
                if stage == "intraday_wide":
                    names.append(_stage_feature(stage, atr_suffix))
                names.extend(
                    _stage_feature(stage, suffix) for suffix in derived_suffixes
                )
            result[horizon] = tuple(names)
        return result

    vote = replacement("DERIVED-PATH::directional_alignment_vote")
    vote_and_strength = replacement(
        "DERIVED-PATH::directional_alignment_vote",
        "DERIVED-PATH::directional_consistent_strength",
    )
    swing_inherited = {
        horizon: tuple(names) for horizon, names in vote_and_strength.items()
    }
    swing_inherited["short_swing"] = (
        *swing_inherited["short_swing"],
        _stage_feature(
            "intraday_short",
            "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
        ),
        _stage_feature(
            "intraday_short",
            "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
        ),
    )
    return OrderedDict(
        (
            ("evidence_pruned_active", pruned),
            ("alignment_vote_replacement", vote),
            ("alignment_vote_and_strength", vote_and_strength),
            ("alignment_with_swing_inherited_hierarchy", swing_inherited),
        )
    )

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


def _standardized_training_matrix_for_schema(
    np,
    records: list[dict],
    horizon: str,
    names: list[str],
    feature_map_factory,
):
    maps = [
        feature_map_factory(record, horizon, orientation)
        for record in records
        for orientation in (0, 1)
    ]
    columns = [[float(values[name]) for values in maps] for name in names]
    scaling = []
    for values in columns:
        center = statistics.median(values)
        scale = 1.4826 * statistics.median(
            abs(value - center) for value in values
        )
        if not math.isfinite(scale) or scale <= 1e-9:
            scale = statistics.pstdev(values)
        scaling.append([center, max(scale, 1e-9)])
    rows = [
        [
            (float(values[name]) - float(center)) / float(scale)
            for name, (center, scale) in zip(names, scaling)
        ]
        for values in maps
    ]
    symbols = []
    analog_records = []
    orientations = []
    frontiers = []
    for record in records:
        for orientation in (0, 1):
            symbols.append(str(record["symbol"]))
            analog_records.append(record)
            orientations.append(orientation)
            favorable = (
                record["up_frontier"]
                if orientation == 0
                else record["down_frontier"]
            )
            adverse = (
                record["down_frontier"]
                if orientation == 0
                else record["up_frontier"]
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


def _query_vector_for_schema(
    np,
    record: dict,
    orientation: int,
    horizon: str,
    prepared: dict,
    feature_map_factory,
):
    values = feature_map_factory(record, horizon, orientation)
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
    feature_names_factory=expanded_feature_names,
    feature_map_factory=_raw_feature_map,
    feature_space: str = "production_atomic_coordinates",
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
        features = feature_names_factory(horizon)
        models[horizon] = {}
        profile_counts[horizon] = {}
        for orientation, direction in DIRECTIONS.items():
            fit_maps = [
                feature_map_factory(record, horizon, orientation)
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
            features = feature_names_factory(horizon)
            for orientation, direction in DIRECTIONS.items():
                feature_map = feature_map_factory(record, horizon, orientation)
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
        for feature in feature_names_factory(horizon):
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
        "feature_space": feature_space,
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


def evaluate_full_atomic_partition(
    *,
    partition_name: str,
    fit_records: list[dict],
    evaluation_records: list[dict],
) -> dict:
    """Confirm every exact coordinate on the complete sealed partition.

    This deliberately omits grouped coalitions and Shapley calculations.  It
    computes only the production vector and its 21 possible one-coordinate
    ablations, making an exhaustive held-out confirmation feasible without
    changing the model or sampling the evaluation partition.
    """

    np = _load_numpy()
    prepared = {
        horizon: _standardized_training_matrix(np, fit_records, horizon)
        for horizon in STAGE_ORDER
    }
    atomic_features = tuple(expanded_feature_names(STAGE_ORDER[-1]))
    variants = ("full", *(_atomic_variant_name(name) for name in atomic_features))
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
    symmetric_geometries = {
        index
        for index, (tp_multiple, sl_multiple) in enumerate(GEOMETRY_GRID)
        if float(tp_multiple) == float(sl_multiple)
    }

    for record_index, record in enumerate(evaluation_records, 1):
        if (
            record_index == 1
            or record_index % 50 == 0
            or record_index == len(evaluation_records)
        ):
            print(
                f"FULL_ATOMIC_PROGRESS partition={partition_name} "
                f"records={record_index}/{len(evaluation_records)}",
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
                name: np.tile(
                    np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
                    (len(GEOMETRY_GRID), 1),
                )
                for name in variants
            }
            survival = {
                name: np.ones(len(GEOMETRY_GRID), dtype=np.float64)
                for name in variants
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
                differences = stage["matrix"] - query
                coordinate_squared = np.minimum(36.0, differences * differences)
                full_squared = coordinate_squared.sum(axis=1)
                symbol_penalty = np.where(
                    stage["symbols"] == str(record["symbol"]),
                    0.0,
                    float(SELECTION["cross_symbol_penalty"]),
                )
                labels = label_matrices[horizon]
                full_distances = (
                    np.sqrt(full_squared / len(stage["names"])) + symbol_penalty
                )
                full_order = _rank_indices(np, full_distances, labels)
                full_conditional = _conditional_probabilities(
                    np, full_order, full_distances, labels
                )
                accumulate("full", full_conditional)

                atomic_indices = expanded_atomic_indices(horizon)
                for feature_name in atomic_features:
                    variant_name = _atomic_variant_name(feature_name)
                    feature_index = atomic_indices.get(feature_name)
                    if feature_index is None:
                        conditional = full_conditional
                    else:
                        squared = np.maximum(
                            0.0,
                            full_squared - coordinate_squared[:, feature_index],
                        )
                        distances = (
                            np.sqrt(squared / (len(stage["names"]) - 1))
                            + symbol_penalty
                        )
                        order = _rank_indices(np, distances, labels)
                        conditional = _conditional_probabilities(
                            np, order, distances, labels
                        )
                    accumulate(variant_name, conditional)

                relevant_variants = (
                    "full",
                    *(
                        _atomic_variant_name(feature)
                        for feature in expanded_feature_names(horizon)
                    ),
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
                    if true_label is None:
                        continue
                    label_index = CUMULATIVE_CLASSES.index(true_label)
                    unit_key = f"{record['id']}::{direction}"
                    for variant_name in relevant_variants:
                        values = cumulative[variant_name][geometry_index]
                        probabilities = values / float(values.sum())
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
                        )

        for horizon in STAGE_ORDER:
            relevant_variants = (
                "full",
                *(
                    _atomic_variant_name(feature)
                    for feature in expanded_feature_names(horizon)
                ),
            )
            for variant_name in relevant_variants:
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
    for (variant, horizon, direction, unit_key), (
        log_sum,
        brier_sum,
        count,
    ) in unit_sums.items():
        unit_metrics[(variant, horizon, direction)][unit_key] = (
            log_sum / count,
            brier_sum / count,
        )

    result = {}
    for horizon in STAGE_ORDER:
        result[horizon] = {}
        for feature_name in expanded_feature_names(horizon):
            result[horizon][feature_name] = {}
            without_name = _atomic_variant_name(feature_name)
            for direction in DIRECTIONS.values():
                full_map = unit_metrics[("full", horizon, direction)]
                without_map = unit_metrics[(without_name, horizon, direction)]
                shared = sorted(set(full_map) & set(without_map))
                full_direction = directional_counts[("full", horizon)]
                without_direction = directional_counts[(without_name, horizon)]
                result[horizon][feature_name][direction] = {
                    "marginal_in_full": _paired_summary(
                        [without_map[key] for key in shared],
                        [full_map[key] for key in shared],
                    ),
                    "predictions": prediction_counts[
                        ("full", horizon, direction)
                    ],
                    "directional_selection": {
                        "full_accuracy": (
                            full_direction["correct_score"]
                            / full_direction["eligible_pairs"]
                            if full_direction["eligible_pairs"]
                            else None
                        ),
                        "without_feature_accuracy": (
                            without_direction["correct_score"]
                            / without_direction["eligible_pairs"]
                            if without_direction["eligible_pairs"]
                            else None
                        ),
                        "eligible_pairs": full_direction["eligible_pairs"],
                    },
                }
    return {
        "partition": partition_name,
        "fit_records": len(fit_records),
        "evaluation_records": len(evaluation_records),
        "sampling": "none_complete_sealed_partition",
        "results": result,
    }


def _interaction_variant_name(target_horizon: str, interaction_id: str) -> str:
    return f"without_interaction::{target_horizon}::{interaction_id}"


def evaluate_targeted_interaction_partition(
    *,
    partition_name: str,
    fit_records: list[dict],
    evaluation_records: list[dict],
) -> dict:
    """Measure predeclared two-coordinate interactions on a sealed partition."""

    np = _load_numpy()
    prepared = {
        horizon: _standardized_training_matrix(np, fit_records, horizon)
        for horizon in STAGE_ORDER
    }
    interaction_variants = OrderedDict(
        (
            _interaction_variant_name(target_horizon, interaction_id),
            (target_horizon, interaction_id, features),
        )
        for target_horizon, interactions in TARGETED_INTERACTIONS.items()
        for interaction_id, features in interactions.items()
    )
    variants = ("full", *interaction_variants)
    unit_sums = defaultdict(lambda: [0.0, 0.0, 0])
    prediction_counts = defaultdict(int)

    for record_index, record in enumerate(evaluation_records, 1):
        if (
            record_index == 1
            or record_index % 50 == 0
            or record_index == len(evaluation_records)
        ):
            print(
                f"INTERACTION_PROGRESS partition={partition_name} "
                f"records={record_index}/{len(evaluation_records)}",
                flush=True,
            )
        base_sigma = float(record["stage_sigmas"]["intraday_short"])
        label_matrices = _conditional_label_matrices(
            np, prepared["intraday_short"], base_sigma
        )
        for orientation in (0, 1):
            direction = DIRECTIONS[orientation]
            cumulative = {
                name: np.tile(
                    np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
                    (len(GEOMETRY_GRID), 1),
                )
                for name in variants
            }
            survival = {
                name: np.ones(len(GEOMETRY_GRID), dtype=np.float64)
                for name in variants
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
                differences = stage["matrix"] - query
                coordinate_squared = np.minimum(36.0, differences * differences)
                full_squared = coordinate_squared.sum(axis=1)
                symbol_penalty = np.where(
                    stage["symbols"] == str(record["symbol"]),
                    0.0,
                    float(SELECTION["cross_symbol_penalty"]),
                )
                labels = label_matrices[horizon]
                full_distances = (
                    np.sqrt(full_squared / len(stage["names"])) + symbol_penalty
                )
                full_order = _rank_indices(np, full_distances, labels)
                full_conditional = _conditional_probabilities(
                    np, full_order, full_distances, labels
                )
                accumulate("full", full_conditional)
                atomic_indices = expanded_atomic_indices(horizon)
                conditional_cache = {(): full_conditional}

                for variant_name, (
                    target_horizon,
                    _interaction_id,
                    feature_names,
                ) in interaction_variants.items():
                    if STAGE_ORDER.index(target_horizon) < STAGE_ORDER.index(horizon):
                        continue
                    removed_indices = tuple(
                        sorted(
                            atomic_indices[feature]
                            for feature in feature_names
                            if feature in atomic_indices
                        )
                    )
                    conditional = conditional_cache.get(removed_indices)
                    if conditional is None:
                        squared = np.maximum(
                            0.0,
                            full_squared
                            - coordinate_squared[:, removed_indices].sum(axis=1),
                        )
                        dimensions = len(stage["names"]) - len(removed_indices)
                        distances = np.sqrt(squared / dimensions) + symbol_penalty
                        order = _rank_indices(np, distances, labels)
                        conditional = _conditional_probabilities(
                            np, order, distances, labels
                        )
                        conditional_cache[removed_indices] = conditional
                    accumulate(variant_name, conditional)

                for interaction_id in TARGETED_INTERACTIONS[horizon]:
                    variant_name = _interaction_variant_name(
                        horizon, interaction_id
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
                        if true_label is None:
                            continue
                        label_index = CUMULATIVE_CLASSES.index(true_label)
                        unit_key = f"{record['id']}::{direction}"
                        for selected_variant in ("full", variant_name):
                            values = cumulative[selected_variant][geometry_index]
                            probabilities = values / float(values.sum())
                            predicted_loss = _loss(probabilities, label_index)
                            key = (
                                selected_variant,
                                horizon,
                                direction,
                                unit_key,
                            )
                            unit_sums[key][0] += predicted_loss[0]
                            unit_sums[key][1] += predicted_loss[1]
                            unit_sums[key][2] += 1
                            prediction_counts[
                                (selected_variant, horizon, direction)
                            ] += 1

    unit_metrics = defaultdict(dict)
    for (variant, horizon, direction, unit_key), (
        log_sum,
        brier_sum,
        count,
    ) in unit_sums.items():
        unit_metrics[(variant, horizon, direction)][unit_key] = (
            log_sum / count,
            brier_sum / count,
        )

    result = {}
    for horizon, interactions in TARGETED_INTERACTIONS.items():
        result[horizon] = {}
        for interaction_id, features in interactions.items():
            result[horizon][interaction_id] = {
                "features": list(features),
            }
            variant_name = _interaction_variant_name(horizon, interaction_id)
            for direction in DIRECTIONS.values():
                full_map = unit_metrics[("full", horizon, direction)]
                without_map = unit_metrics[(variant_name, horizon, direction)]
                shared = sorted(set(full_map) & set(without_map))
                result[horizon][interaction_id][direction] = {
                    "joint_marginal_in_full": _paired_summary(
                        [without_map[key] for key in shared],
                        [full_map[key] for key in shared],
                    ),
                    "predictions": prediction_counts[
                        ("full", horizon, direction)
                    ],
                }
    return {
        "partition": partition_name,
        "fit_records": len(fit_records),
        "evaluation_records": len(evaluation_records),
        "sampling": "none_complete_sealed_partition",
        "results": result,
    }


def evaluate_candidate_feature_sets_partition(
    *,
    partition_name: str,
    fit_records: list[dict],
    evaluation_records: list[dict],
    candidates: OrderedDict[str, dict[str, tuple[str, ...]]] | None = None,
    feature_map_factory=_raw_feature_map,
    baseline_candidate: str = "v0_9_full",
    feature_space: str = "production_atomic_coordinates",
) -> dict:
    """Compare predeclared nested feature sets with unchanged v0.9 math."""

    np = _load_numpy()
    candidates = candidates or candidate_feature_sets()
    if baseline_candidate not in candidates:
        raise ValueError("candidate_baseline_missing")
    names_by_horizon = {}
    for horizon in STAGE_ORDER:
        names_by_horizon[horizon] = list(
            dict.fromkeys(
                name
                for values in candidates.values()
                for name in values[horizon]
            )
        )
    prepared = {
        horizon: _standardized_training_matrix_for_schema(
            np,
            fit_records,
            horizon,
            names_by_horizon[horizon],
            feature_map_factory,
        )
        for horizon in STAGE_ORDER
    }
    unit_sums = defaultdict(lambda: [0.0, 0.0, 0])
    unit_symbols = {}
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
    directional_counts_by_symbol = defaultdict(
        lambda: {
            "eligible_pairs": 0,
            "correct_score": 0.0,
            "ties": 0,
            "chosen_long": 0,
            "actual_long": 0,
        }
    )
    symmetric_geometries = {
        index
        for index, (tp_multiple, sl_multiple) in enumerate(GEOMETRY_GRID)
        if float(tp_multiple) == float(sl_multiple)
    }

    for record_index, record in enumerate(evaluation_records, 1):
        if (
            record_index == 1
            or record_index % 100 == 0
            or record_index == len(evaluation_records)
        ):
            print(
                f"CANDIDATE_PROGRESS partition={partition_name} "
                f"records={record_index}/{len(evaluation_records)}",
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
                name: np.tile(
                    np.asarray([0.0, 0.0, 1.0], dtype=np.float64),
                    (len(GEOMETRY_GRID), 1),
                )
                for name in candidates
            }
            survival = {
                name: np.ones(len(GEOMETRY_GRID), dtype=np.float64)
                for name in candidates
            }
            for horizon in STAGE_ORDER:
                stage = prepared[horizon]
                query = _query_vector_for_schema(
                    np,
                    record,
                    orientation,
                    horizon,
                    stage,
                    feature_map_factory,
                )
                differences = stage["matrix"] - query
                coordinate_squared = np.minimum(36.0, differences * differences)
                symbol_penalty = np.where(
                    stage["symbols"] == str(record["symbol"]),
                    0.0,
                    float(SELECTION["cross_symbol_penalty"]),
                )
                labels = label_matrices[horizon]
                name_to_index = {
                    name: index for index, name in enumerate(stage["names"])
                }
                conditional_cache = {}
                for candidate_name, names_by_horizon in candidates.items():
                    selected_indices = tuple(
                        name_to_index[name]
                        for name in names_by_horizon[horizon]
                    )
                    conditional = conditional_cache.get(selected_indices)
                    if conditional is None:
                        squared = coordinate_squared[:, selected_indices].sum(axis=1)
                        distances = (
                            np.sqrt(squared / len(selected_indices)) + symbol_penalty
                        )
                        order = _rank_indices(np, distances, labels)
                        conditional = _conditional_probabilities(
                            np, order, distances, labels
                        )
                        conditional_cache[selected_indices] = conditional
                    for geometry_index, probabilities in enumerate(conditional):
                        if probabilities is None:
                            continue
                        previous_survival = survival[candidate_name][geometry_index]
                        cumulative[candidate_name][geometry_index, 0] += (
                            previous_survival * probabilities[0]
                        )
                        cumulative[candidate_name][geometry_index, 1] += (
                            previous_survival * probabilities[1]
                        )
                        survival[candidate_name][geometry_index] *= probabilities[2]
                        cumulative[candidate_name][geometry_index, 2] = survival[
                            candidate_name
                        ][geometry_index]

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
                    unit_symbols[unit_key] = str(record["symbol"])
                    for candidate_name in candidates:
                        values = cumulative[candidate_name][geometry_index]
                        probabilities = values / float(values.sum())
                        predicted_loss = _loss(probabilities, label_index)
                        key = (candidate_name, horizon, direction, unit_key)
                        unit_sums[key][0] += predicted_loss[0]
                        unit_sums[key][1] += predicted_loss[1]
                        unit_sums[key][2] += 1
                        prediction_counts[(candidate_name, horizon, direction)] += 1
                        direction_observations[
                            (candidate_name, horizon, geometry_index, orientation)
                        ] = (
                            float(probabilities[0] - probabilities[1]),
                            label_index,
                        )

        for candidate_name in candidates:
            for horizon in STAGE_ORDER:
                for geometry_index in symmetric_geometries:
                    long_item = direction_observations.get(
                        (candidate_name, horizon, geometry_index, 0)
                    )
                    short_item = direction_observations.get(
                        (candidate_name, horizon, geometry_index, 1)
                    )
                    if not long_item or not short_item:
                        continue
                    long_label = int(long_item[1])
                    short_label = int(short_item[1])
                    if {long_label, short_label} != {0, 1}:
                        continue
                    actual_long = long_label == 0
                    long_score = float(long_item[0])
                    short_score = float(short_item[0])
                    for counts in (
                        directional_counts[(candidate_name, horizon)],
                        directional_counts_by_symbol[
                            (candidate_name, horizon, str(record["symbol"]))
                        ],
                    ):
                        counts["eligible_pairs"] += 1
                        counts["actual_long"] += int(actual_long)
                        if abs(long_score - short_score) <= 1e-15:
                            counts["ties"] += 1
                            counts["correct_score"] += 0.5
                        else:
                            chosen_long = long_score > short_score
                            counts["chosen_long"] += int(chosen_long)
                            counts["correct_score"] += float(
                                chosen_long == actual_long
                            )

    unit_metrics = defaultdict(dict)
    for (candidate_name, horizon, direction, unit_key), (
        log_sum,
        brier_sum,
        count,
    ) in unit_sums.items():
        unit_metrics[(candidate_name, horizon, direction)][unit_key] = (
            log_sum / count,
            brier_sum / count,
        )

    summaries = {}
    comparisons = {}
    symbol_comparisons = {}
    symbols = sorted({str(record["symbol"]) for record in evaluation_records})
    for candidate_name in candidates:
        summaries[candidate_name] = {}
        if candidate_name != baseline_candidate:
            comparisons[candidate_name] = {}
            symbol_comparisons[candidate_name] = {}
        for horizon in STAGE_ORDER:
            summaries[candidate_name][horizon] = {}
            if candidate_name != baseline_candidate:
                comparisons[candidate_name][horizon] = {}
                symbol_comparisons[candidate_name][horizon] = {}
            for direction in DIRECTIONS.values():
                values = list(
                    unit_metrics[(candidate_name, horizon, direction)].values()
                )
                counts = directional_counts[(candidate_name, horizon)]
                eligible = counts["eligible_pairs"]
                summaries[candidate_name][horizon][direction] = {
                    **_metrics(
                        values,
                        prediction_counts[(candidate_name, horizon, direction)],
                    ),
                    "directional_accuracy": (
                        counts["correct_score"] / eligible if eligible else None
                    ),
                    "chosen_long_rate": (
                        counts["chosen_long"] / (eligible - counts["ties"])
                        if eligible > counts["ties"]
                        else None
                    ),
                }
                if candidate_name == baseline_candidate:
                    continue
                full_map = unit_metrics[(baseline_candidate, horizon, direction)]
                candidate_map = unit_metrics[(candidate_name, horizon, direction)]
                shared = sorted(set(full_map) & set(candidate_map))
                comparisons[candidate_name][horizon][direction] = {
                    "candidate_vs_baseline": _paired_summary(
                        [full_map[key] for key in shared],
                        [candidate_map[key] for key in shared],
                    ),
                    "directional_accuracy_delta": (
                        summaries[candidate_name][horizon][direction][
                            "directional_accuracy"
                        ]
                        - summaries[baseline_candidate][horizon][direction][
                            "directional_accuracy"
                        ]
                    ),
                }
                symbol_comparisons[candidate_name][horizon][direction] = {}
                for symbol in symbols:
                    symbol_shared = [
                        key for key in shared if unit_symbols[key] == symbol
                    ]
                    baseline_direction = directional_counts_by_symbol[
                        (baseline_candidate, horizon, symbol)
                    ]
                    candidate_direction = directional_counts_by_symbol[
                        (candidate_name, horizon, symbol)
                    ]
                    baseline_eligible = baseline_direction["eligible_pairs"]
                    candidate_eligible = candidate_direction["eligible_pairs"]
                    directional_delta = None
                    if baseline_eligible and candidate_eligible:
                        directional_delta = (
                            candidate_direction["correct_score"] / candidate_eligible
                            - baseline_direction["correct_score"] / baseline_eligible
                        )
                    symbol_comparisons[candidate_name][horizon][direction][symbol] = {
                        "candidate_vs_baseline": _paired_summary(
                            [full_map[key] for key in symbol_shared],
                            [candidate_map[key] for key in symbol_shared],
                        ),
                        "directional_accuracy_delta": directional_delta,
                    }
    return {
        "partition": partition_name,
        "feature_space": feature_space,
        "baseline_candidate": baseline_candidate,
        "fit_records": len(fit_records),
        "evaluation_records": len(evaluation_records),
        "sampling": "none_complete_sealed_partition",
        "feature_sets": {
            name: {horizon: list(features) for horizon, features in values.items()}
            for name, values in candidates.items()
        },
        "summaries": summaries,
        "comparisons": comparisons,
        "symbol_comparisons": symbol_comparisons,
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


def _direct_replication_matrix(
    direct_results: dict,
    feature_names_factory=expanded_feature_names,
) -> dict:
    result = {}
    for horizon in STAGE_ORDER:
        result[horizon] = {}
        for feature_name in feature_names_factory(horizon):
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


def _full_atomic_replication_matrix(full_results: dict) -> dict:
    result = {}
    for horizon in STAGE_ORDER:
        result[horizon] = {}
        for feature_name in expanded_feature_names(horizon):
            result[horizon][feature_name] = {}
            for direction in DIRECTIONS.values():
                rule_delta = full_results["rule_test"]["results"][horizon][
                    feature_name
                ][direction]["marginal_in_full"]
                final_delta = full_results["final_test"]["results"][horizon][
                    feature_name
                ][direction]["marginal_in_full"]
                result[horizon][feature_name][direction] = {
                    "status": classify_replication(
                        rule_delta, final_delta, minimum_units=200
                    ),
                    "rule_test": rule_delta,
                    "final_test": final_delta,
                    "interpretation": (
                        "positive values mean the complete v0.9 vector predicts "
                        "better than the same vector with this coordinate removed"
                    ),
                }
    return result


def _targeted_interaction_replication_matrix(
    interaction_results: dict,
    atomic_replication: dict,
) -> dict:
    result = {}
    for horizon, interactions in TARGETED_INTERACTIONS.items():
        result[horizon] = {}
        for interaction_id, features in interactions.items():
            result[horizon][interaction_id] = {"features": list(features)}
            for direction in DIRECTIONS.values():
                joint = {
                    partition_name: interaction_results[partition_name]["results"][
                        horizon
                    ][interaction_id][direction]["joint_marginal_in_full"]
                    for partition_name in ("rule_test", "final_test")
                }
                singles = {
                    feature: atomic_replication[horizon][feature][direction]
                    for feature in features
                }
                comparison = {}
                excess_values = []
                for partition_name in ("rule_test", "final_test"):
                    pair_delta = joint[partition_name]
                    first_delta = singles[features[0]][partition_name]
                    second_delta = singles[features[1]][partition_name]
                    comparison[partition_name] = {
                        "joint_marginal": pair_delta,
                        "incremental_over_best_single": {
                            metric: pair_delta[metric]
                            - max(first_delta[metric], second_delta[metric])
                            for metric in ("log_loss", "brier")
                        },
                        "excess_over_additive": {
                            metric: pair_delta[metric]
                            - first_delta[metric]
                            - second_delta[metric]
                            for metric in ("log_loss", "brier")
                        },
                    }
                    excess_values.extend(
                        comparison[partition_name]["excess_over_additive"].values()
                    )
                if all(value > 0.0 for value in excess_values):
                    interaction_status = "positive_interaction_consistent"
                elif all(value < 0.0 for value in excess_values):
                    interaction_status = "redundant_or_antagonistic_consistent"
                else:
                    interaction_status = "mixed_interaction"
                result[horizon][interaction_id][direction] = {
                    "joint_status": classify_replication(
                        joint["rule_test"],
                        joint["final_test"],
                        minimum_units=200,
                    ),
                    "interaction_status": interaction_status,
                    **comparison,
                }
    return result


def _candidate_replication_matrix(
    candidate_results: dict,
    candidates: OrderedDict[str, dict[str, tuple[str, ...]]] | None = None,
    baseline_candidate: str = "v0_9_full",
) -> dict:
    result = {}
    candidates = candidates or candidate_feature_sets()
    for candidate_name in candidates:
        if candidate_name == baseline_candidate:
            continue
        result[candidate_name] = {}
        macro = {
            partition_name: {"log_loss": [], "brier": [], "directional": []}
            for partition_name in ("rule_test", "final_test")
        }
        for horizon in STAGE_ORDER:
            result[candidate_name][horizon] = {}
            for direction in DIRECTIONS.values():
                rule_delta = candidate_results["rule_test"]["comparisons"][
                    candidate_name
                ][horizon][direction]
                final_delta = candidate_results["final_test"]["comparisons"][
                    candidate_name
                ][horizon][direction]
                result[candidate_name][horizon][direction] = {
                    "status": classify_replication(
                        rule_delta["candidate_vs_baseline"],
                        final_delta["candidate_vs_baseline"],
                        minimum_units=200,
                    ),
                    "rule_test": rule_delta,
                    "final_test": final_delta,
                }
                for partition_name, values in (
                    ("rule_test", rule_delta),
                    ("final_test", final_delta),
                ):
                    macro[partition_name]["log_loss"].append(
                        values["candidate_vs_baseline"]["log_loss"]
                    )
                    macro[partition_name]["brier"].append(
                        values["candidate_vs_baseline"]["brier"]
                    )
                    macro[partition_name]["directional"].append(
                        values["directional_accuracy_delta"]
                    )
        result[candidate_name]["macro"] = {
            partition_name: {
                metric: statistics.fmean(values)
                for metric, values in metrics.items()
            }
            for partition_name, metrics in macro.items()
        }
    return result


def _candidate_symbol_replication_matrix(
    candidate_results: dict,
    candidates: OrderedDict[str, dict[str, tuple[str, ...]]],
    *,
    baseline_candidate: str,
) -> dict:
    result = {}
    for candidate_name in candidates:
        if candidate_name == baseline_candidate:
            continue
        result[candidate_name] = {}
        for horizon in STAGE_ORDER:
            result[candidate_name][horizon] = {}
            for direction in DIRECTIONS.values():
                result[candidate_name][horizon][direction] = {}
                symbols = sorted(
                    candidate_results["rule_test"]["symbol_comparisons"][
                        candidate_name
                    ][horizon][direction]
                )
                for symbol in symbols:
                    rule_delta = candidate_results["rule_test"][
                        "symbol_comparisons"
                    ][candidate_name][horizon][direction][symbol]
                    final_delta = candidate_results["final_test"][
                        "symbol_comparisons"
                    ][candidate_name][horizon][direction][symbol]
                    result[candidate_name][horizon][direction][symbol] = {
                        "status": classify_replication(
                            rule_delta["candidate_vs_baseline"],
                            final_delta["candidate_vs_baseline"],
                            minimum_units=150,
                        ),
                        "rule_test": rule_delta,
                        "final_test": final_delta,
                    }
    return result


def candidate_symbol_robustness_summary(symbol_matrix: dict) -> dict:
    result = {}
    for candidate_name, horizons in symbol_matrix.items():
        cells = [
            cell
            for directions in horizons.values()
            for symbols in directions.values()
            for cell in symbols.values()
        ]
        positive_calibration = sum(
            all(
                cell[partition]["candidate_vs_baseline"][metric] > 0.0
                for partition in ("rule_test", "final_test")
                for metric in ("log_loss", "brier")
            )
            for cell in cells
        )
        positive_directional = sum(
            all(
                cell[partition]["directional_accuracy_delta"] is not None
                and cell[partition]["directional_accuracy_delta"] > 0.0
                for partition in ("rule_test", "final_test")
            )
            for cell in cells
        )
        result[candidate_name] = {
            "cells": len(cells),
            "status_counts": dict(
                sorted(Counter(cell["status"] for cell in cells).items())
            ),
            "positive_calibration_in_both_partitions": positive_calibration,
            "positive_directional_accuracy_in_both_partitions": positive_directional,
            "harmful_confirmed_cells": sum(
                cell["status"] == "harmful_confirmed" for cell in cells
            ),
        }
    return result


def select_stable_candidate(
    *,
    candidates: OrderedDict[str, dict[str, tuple[str, ...]]],
    baseline_candidate: str,
    release_decisions: dict,
    symbol_robustness: dict,
) -> dict:
    baseline_coordinates = {
        name for values in candidates[baseline_candidate].values() for name in values
    }
    ranking = []
    for candidate_name, decision in release_decisions.items():
        candidate_coordinates = {
            name for values in candidates[candidate_name].values() for name in values
        }
        status_counts = symbol_robustness[candidate_name]["status_counts"]
        item = {
            "candidate": candidate_name,
            "eligible": decision["decision"] == "eligible_for_production_review",
            "harmful_confirmed_symbol_cells": int(
                symbol_robustness[candidate_name]["harmful_confirmed_cells"]
            ),
            "harmful_consistent_symbol_cells": int(
                status_counts.get("harmful_consistent_but_uncertain", 0)
            ),
            "unique_coordinate_changes": len(
                baseline_coordinates.symmetric_difference(candidate_coordinates)
            ),
        }
        item["stability_rank"] = [
            0 if item["eligible"] else 1,
            item["harmful_confirmed_symbol_cells"],
            item["harmful_consistent_symbol_cells"],
            item["unique_coordinate_changes"],
            candidate_name,
        ]
        ranking.append(item)
    ranking.sort(key=lambda item: item["stability_rank"])
    selected = ranking[0] if ranking and ranking[0]["eligible"] else None
    return {
        "policy": (
            "among globally eligible candidates, minimize confirmed then consistent "
            "per-symbol harm and finally minimize the number of changed coordinates"
        ),
        "ranking": ranking,
        "selected_candidate": selected["candidate"] if selected else None,
        "production_authorized": False,
        "authorization_state": "selected_for_candidate_build_and_runtime_verification",
    }


HELPFUL_REPLICATION_STATUSES = frozenset(
    {"helpful_confirmed", "helpful_consistent_but_uncertain"}
)


def candidate_release_decisions(replication_matrix: dict) -> dict:
    """Apply the same explicit release gate to every global feature candidate.

    A global replacement is deliberately rejected when it regresses any
    horizon/side cell, either calibration metric in either sealed partition,
    or LONG/SHORT selection accuracy in either sealed partition. The gate is
    stricter than exploratory ranking because the candidate would affect every
    production analysis rather than one isolated horizon.
    """

    decisions = {}
    for candidate_name, candidate in replication_matrix.items():
        cells = [
            candidate[horizon][direction]
            for horizon in STAGE_ORDER
            for direction in DIRECTIONS.values()
        ]
        statuses = [cell["status"] for cell in cells]
        macro = candidate["macro"]
        all_cells_helpful = all(
            status in HELPFUL_REPLICATION_STATUSES for status in statuses
        )
        calibration_positive = all(
            macro[partition][metric] > 0.0
            for partition in ("rule_test", "final_test")
            for metric in ("log_loss", "brier")
        )
        directional_positive = all(
            macro[partition]["directional"] > 0.0
            for partition in ("rule_test", "final_test")
        )
        failed_gates = []
        if not all_cells_helpful:
            failed_gates.append("horizon_side_replication")
        if not calibration_positive:
            failed_gates.append("sealed_partition_calibration")
        if not directional_positive:
            failed_gates.append("long_short_selection_accuracy")
        eligible = not failed_gates
        decisions[candidate_name] = {
            "decision": (
                "eligible_for_production_review"
                if eligible
                else "reject_as_global_replacement"
            ),
            "failed_gates": failed_gates,
            "gates": {
                "all_six_horizon_side_cells_helpful": all_cells_helpful,
                "log_loss_and_brier_positive_in_both_sealed_partitions": (
                    calibration_positive
                ),
                "long_short_selection_accuracy_positive_in_both_sealed_partitions": (
                    directional_positive
                ),
            },
            "status_counts": dict(sorted(Counter(statuses).items())),
        }
    return decisions


def atomic_rule_evidence_inventory(replication_matrix: dict) -> dict:
    """List every atomic coordinate result without averaging horizons away."""

    inventory = defaultdict(list)
    for horizon, features in replication_matrix.items():
        for feature_name, directions in features.items():
            for direction, result in directions.items():
                inventory[result["status"]].append(
                    {
                        "evaluated_horizon": horizon,
                        "feature": feature_name,
                        "side": direction,
                    }
                )
    return {
        status: sorted(
            rows,
            key=lambda row: (
                STAGE_ORDER.index(row["evaluated_horizon"]),
                row["feature"],
                row["side"],
            ),
        )
        for status, rows in sorted(inventory.items())
    }


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


def run_full_confirmation(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if payload.get("version") != AUDIT_VERSION:
        raise RuntimeError("base_attribution_artifact_version_mismatch")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    full_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        full_results[partition_name] = evaluate_full_atomic_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
        )
    payload["full_sample_atomic_confirmation"] = {
        "purpose": (
            "exhaustive leave-one-coordinate-out confirmation on every record "
            "of both sealed chronological evaluation partitions"
        ),
        "production_changed": False,
        "partitions": full_results,
        "replication_matrix": _full_atomic_replication_matrix(full_results),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_targeted_interactions(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    confirmation = payload.get("full_sample_atomic_confirmation")
    if not isinstance(confirmation, dict):
        raise RuntimeError("full_atomic_confirmation_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    interaction_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        interaction_results[partition_name] = evaluate_targeted_interaction_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
        )
    payload["targeted_interaction_confirmation"] = {
        "purpose": (
            "predeclared economic and temporal interactions tested exhaustively "
            "after individual feature confirmation"
        ),
        "selection_policy": (
            "pairs were declared from semantic roles and temporal transitions, "
            "not selected from their interaction result"
        ),
        "production_changed": False,
        "partitions": interaction_results,
        "replication_matrix": _targeted_interaction_replication_matrix(
            interaction_results,
            confirmation["replication_matrix"],
        ),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_candidate_comparison(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "targeted_interaction_confirmation" not in payload:
        raise RuntimeError("targeted_interaction_confirmation_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    candidate_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        candidate_results[partition_name] = evaluate_candidate_feature_sets_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
        )
    payload["retrospective_candidate_comparison"] = {
        "purpose": (
            "compare evidence-pruned nested feature sets with v0.9 while "
            "leaving every other probability calculation unchanged"
        ),
        "status": "retrospective_diagnostic_not_production_authorization",
        "production_changed": False,
        "partitions": candidate_results,
        "replication_matrix": _candidate_replication_matrix(candidate_results),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_derived_feature_audit(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "retrospective_candidate_comparison" not in payload:
        raise RuntimeError("retrospective_candidate_comparison_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    direct_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        print(
            f"DERIVED_DIRECT_PROGRESS partition={partition_name} "
            f"records={len(partitions[partition_name])}",
            flush=True,
        )
        direct_results[partition_name] = evaluate_direct_feature_relationships(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
            feature_names_factory=expanded_derived_feature_names,
            feature_map_factory=_derived_feature_map,
            feature_space="derived_multiscale_path_candidates",
        )
    payload["derived_path_feature_audit"] = {
        "purpose": (
            "test interpretable reformulations of the existing H/2H/4H path "
            "inputs directly before allowing them to define analog similarity"
        ),
        "status": "offline_candidates_not_active_rules",
        "production_changed": False,
        "feature_contracts": DERIVED_PATH_FEATURES,
        "semantic_audit": semantic_derived_feature_audit(records),
        "partitions": direct_results,
        "replication_matrix": _direct_replication_matrix(
            direct_results,
            feature_names_factory=expanded_derived_feature_names,
        ),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_derived_context_comparison(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "derived_path_feature_audit" not in payload:
        raise RuntimeError("derived_path_feature_audit_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    candidates = derived_context_candidate_sets()
    candidate_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        candidate_results[partition_name] = evaluate_candidate_feature_sets_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
            candidates=candidates,
            feature_map_factory=_combined_context_feature_map,
            baseline_candidate="evidence_pruned_active",
            feature_space="active_context_with_derived_multiscale_path",
        )
    payload["derived_context_candidate_comparison"] = {
        "purpose": (
            "test whether interpretable multiscale path reformulations improve "
            "historical similarity over the evidence-pruned active vector"
        ),
        "status": "retrospective_diagnostic_not_production_authorization",
        "production_changed": False,
        "partitions": candidate_results,
        "replication_matrix": _candidate_replication_matrix(
            candidate_results,
            candidates=candidates,
            baseline_candidate="evidence_pruned_active",
        ),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_finalize_decisions(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "full_sample_atomic_confirmation" not in payload:
        raise RuntimeError("full_sample_atomic_confirmation_required")
    if "derived_context_candidate_comparison" not in payload:
        raise RuntimeError("derived_context_candidate_comparison_required")

    derived_matrix = payload["derived_context_candidate_comparison"][
        "replication_matrix"
    ]
    release_decisions = candidate_release_decisions(derived_matrix)
    eligible_candidates = sorted(
        candidate_name
        for candidate_name, decision in release_decisions.items()
        if decision["decision"] == "eligible_for_production_review"
    )
    payload["active_rule_decision_record"] = {
        "purpose": (
            "turn the completed atomic, interaction and candidate audits into "
            "an explicit reproducible decision without changing production"
        ),
        "production_engine_before": ENGINE_VERSION,
        "production_engine_after": ENGINE_VERSION,
        "production_changed": False,
        "release_gate": {
            "scope": "global_feature_vector_replacement",
            "requirements": [
                "helpful replication in every horizon and side",
                "positive log-loss and Brier deltas in rule_test and final_test",
                "positive LONG/SHORT selection accuracy delta in both partitions",
            ],
        },
        "candidate_decisions": release_decisions,
        "eligible_candidates": eligible_candidates,
        "selected_candidate": eligible_candidates[0] if len(eligible_candidates) == 1 else None,
        "conclusion": (
            "candidate_ready_for_separate_production_review"
            if eligible_candidates
            else "no_derived_candidate_authorized_keep_v0_9_unchanged"
        ),
        "atomic_rule_evidence_by_horizon_and_side": atomic_rule_evidence_inventory(
            payload["full_sample_atomic_confirmation"]["replication_matrix"]
        ),
        "next_evidence_step": (
            "test new directional candidates independently per horizon and side; "
            "do not replace the global active vector from these rejected candidates"
        ),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_candidate_context_screen(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "active_rule_decision_record" not in payload:
        raise RuntimeError("active_rule_decision_record_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    direct_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        print(
            f"CANDIDATE_CONTEXT_PROGRESS partition={partition_name} "
            f"records={len(partitions[partition_name])}",
            flush=True,
        )
        direct_results[partition_name] = evaluate_direct_feature_relationships(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
            feature_names_factory=expanded_candidate_context_feature_names,
            feature_map_factory=_candidate_context_feature_map,
            feature_space="historically_complete_non_active_context_candidates",
        )
    payload["candidate_context_direct_screen"] = {
        "purpose": (
            "screen already-recorded trend, momentum, volume and flow formulas "
            "independently by source stage, evaluated horizon and trade side"
        ),
        "status": "offline_direct_screen_not_active_rules",
        "production_changed": False,
        "feature_contracts": CANDIDATE_CONTEXT_FEATURES,
        "coverage": candidate_context_coverage(records),
        "partitions": direct_results,
        "replication_matrix": _direct_replication_matrix(
            direct_results,
            feature_names_factory=expanded_candidate_context_feature_names,
        ),
        "next_gate": (
            "only helpful replicated cells may enter a separately tested analog "
            "candidate for that same horizon and side"
        ),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_confirmed_ema_candidate(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "candidate_context_direct_screen" not in payload:
        raise RuntimeError("candidate_context_direct_screen_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    candidates = confirmed_short_ema_candidate_sets()
    candidate_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        candidate_results[partition_name] = evaluate_candidate_feature_sets_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
            candidates=candidates,
            feature_map_factory=_raw_feature_map,
            baseline_candidate="evidence_pruned_active",
            feature_space="evidence_pruned_plus_confirmed_short_ema_cross",
        )
    replication_matrix = _candidate_replication_matrix(
        candidate_results,
        candidates=candidates,
        baseline_candidate="evidence_pruned_active",
    )
    payload["confirmed_short_ema_analog_candidate"] = {
        "purpose": (
            "test whether the independently confirmed 0-4h EMA50/EMA200 signal "
            "improves analog selection when added only to the 0-4h conditional stage"
        ),
        "status": "retrospective_diagnostic_not_production_authorization",
        "production_changed": False,
        "baseline_candidate": "evidence_pruned_active",
        "candidate_feature": CONFIRMED_SHORT_EMA_CROSS,
        "candidate_scope": (
            "intraday_short conditional stage only; wider results inherit its "
            "effect through sequential survival but do not reuse it in later-stage distance"
        ),
        "partitions": candidate_results,
        "replication_matrix": replication_matrix,
        "release_decisions": candidate_release_decisions(replication_matrix),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_integrated_candidate_vs_production(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    if "confirmed_short_ema_analog_candidate" not in payload:
        raise RuntimeError("confirmed_short_ema_analog_candidate_required")

    records = load_or_build_records()
    partitions = {
        name: [record for record in records if record["partition"] == name]
        for name in PARTITIONS
    }
    candidates = production_baseline_ema_candidate_sets()
    candidate_results = {}
    for partition_name in ("rule_test", "final_test"):
        fit_records = [
            record
            for fit_partition in FIT_PARTITIONS[partition_name]
            for record in partitions[fit_partition]
        ]
        candidate_results[partition_name] = evaluate_candidate_feature_sets_partition(
            partition_name=partition_name,
            fit_records=fit_records,
            evaluation_records=partitions[partition_name],
            candidates=candidates,
            feature_map_factory=_raw_feature_map,
            baseline_candidate="v0_9_production",
            feature_space="integrated_short_ema_candidates_vs_v0_9",
        )
    replication_matrix = _candidate_replication_matrix(
        candidate_results,
        candidates=candidates,
        baseline_candidate="v0_9_production",
    )
    symbol_replication_matrix = _candidate_symbol_replication_matrix(
        candidate_results,
        candidates,
        baseline_candidate="v0_9_production",
    )
    release_decisions = candidate_release_decisions(replication_matrix)
    symbol_robustness = candidate_symbol_robustness_summary(
        symbol_replication_matrix
    )
    payload["integrated_candidate_vs_production"] = {
        "purpose": (
            "compare the confirmed short-stage EMA signal alone and combined "
            "with evidence-based pruning against the unchanged v0.9 production vector"
        ),
        "status": "retrospective_diagnostic_not_production_authorization",
        "production_changed": False,
        "baseline_candidate": "v0_9_production",
        "partitions": candidate_results,
        "replication_matrix": replication_matrix,
        "release_decisions": release_decisions,
        "symbol_replication_matrix": symbol_replication_matrix,
        "symbol_robustness_summary": symbol_robustness,
        "stable_candidate_selection": select_stable_candidate(
            candidates=candidates,
            baseline_candidate="v0_9_production",
            release_decisions=release_decisions,
            symbol_robustness=symbol_robustness,
        ),
    }
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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


def run_finalize_stable_candidate(*, output_path: Path = OUTPUT_PATH) -> dict:
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    expected_hash = payload.pop("canonical_payload_sha256")
    if canonical_sha256(payload) != expected_hash:
        raise RuntimeError("base_attribution_artifact_hash_invalid")
    section = payload.get("integrated_candidate_vs_production")
    if not isinstance(section, dict):
        raise RuntimeError("integrated_candidate_vs_production_required")
    candidates = production_baseline_ema_candidate_sets()
    section["stable_candidate_selection"] = select_stable_candidate(
        candidates=candidates,
        baseline_candidate="v0_9_production",
        release_decisions=section["release_decisions"],
        symbol_robustness=section["symbol_robustness_summary"],
    )
    payload["canonical_payload_sha256"] = canonical_sha256(payload)
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
    parser.add_argument(
        "--full-confirmation",
        action="store_true",
        help="append exhaustive atomic ablations to an existing v0.2 artifact",
    )
    parser.add_argument(
        "--targeted-interactions",
        action="store_true",
        help="append exhaustive predeclared interaction tests to a confirmed artifact",
    )
    parser.add_argument(
        "--candidate-comparison",
        action="store_true",
        help="append exhaustive retrospective comparison of evidence-pruned vectors",
    )
    parser.add_argument(
        "--derived-features",
        action="store_true",
        help="append direct tests of interpretable multiscale path reformulations",
    )
    parser.add_argument(
        "--derived-context-candidates",
        action="store_true",
        help="append analog comparisons using derived multiscale path candidates",
    )
    parser.add_argument(
        "--finalize-decisions",
        action="store_true",
        help="append deterministic release decisions to the completed audit artifact",
    )
    parser.add_argument(
        "--candidate-context-screen",
        action="store_true",
        help="append direct tests of recorded trend, momentum, volume and flow candidates",
    )
    parser.add_argument(
        "--confirmed-ema-candidate",
        action="store_true",
        help="append an analog test of the confirmed 0-4h EMA50/EMA200 signal",
    )
    parser.add_argument(
        "--integrated-candidate-vs-production",
        action="store_true",
        help="compare EMA and pruned+EMA candidates directly with v0.9 production",
    )
    parser.add_argument(
        "--finalize-stable-candidate",
        action="store_true",
        help="append the stability-first candidate selection without recomputing audits",
    )
    args = parser.parse_args()
    append_modes = sum(
        int(value)
        for value in (
            args.full_confirmation,
            args.targeted_interactions,
            args.candidate_comparison,
            args.derived_features,
            args.derived_context_candidates,
            args.finalize_decisions,
            args.candidate_context_screen,
            args.confirmed_ema_candidate,
            args.integrated_candidate_vs_production,
            args.finalize_stable_candidate,
        )
    )
    if append_modes > 1:
        parser.error("choose only one append mode")
    if args.full_confirmation:
        payload = run_full_confirmation(output_path=args.output)
    elif args.targeted_interactions:
        payload = run_targeted_interactions(output_path=args.output)
    elif args.candidate_comparison:
        payload = run_candidate_comparison(output_path=args.output)
    elif args.derived_features:
        payload = run_derived_feature_audit(output_path=args.output)
    elif args.derived_context_candidates:
        payload = run_derived_context_comparison(output_path=args.output)
    elif args.finalize_decisions:
        payload = run_finalize_decisions(output_path=args.output)
    elif args.candidate_context_screen:
        payload = run_candidate_context_screen(output_path=args.output)
    elif args.confirmed_ema_candidate:
        payload = run_confirmed_ema_candidate(output_path=args.output)
    elif args.integrated_candidate_vs_production:
        payload = run_integrated_candidate_vs_production(output_path=args.output)
    elif args.finalize_stable_candidate:
        payload = run_finalize_stable_candidate(output_path=args.output)
    else:
        payload = run_audit(output_path=args.output)
    print(
        "ATTRIBUTION_COMPLETE "
        f"sha256={payload['canonical_payload_sha256']} output={args.output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
