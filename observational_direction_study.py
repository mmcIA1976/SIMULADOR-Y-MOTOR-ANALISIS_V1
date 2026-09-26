"""Read-only, outcome-blind directional scoring of compact observational facts.

Scores describe the *hypothesis* expressed by a rule, not its proven accuracy or
an adjustment to the production probabilities.  The scale is frozen from the
sealed historical cohort's signal distribution, without looking at outcomes.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone

from observational_learning_base import (
    BASELINE_COHORT_KEY,
    FROZEN_SIGNAL_VARIABLES,
    MOVEMENT_RULE_IDS,
    RETAINED_RULE_HORIZONS,
    canonical_json,
    fixed_horizon_outcome_from_evidence,
    load_closed_operation_label_metadata,
    parse_json_object,
)


SCORE_VERSION = "observational-direction-score-v0.1"
MIN_REFERENCE_EPISODES = 10
STRONG_SCORE = 3

# These are hypotheses fixed before examining a scored case's outcome.  A
# target-side score is converted back to native market direction using side.
# For movement-only rules a bullish/bearish score would be fabricated, so they
# receive an activity score instead and directional_score=None.
NEUTRAL_VALUES = {
    "LIB-CAND-LIQUIDATION-ZONE-001": 0.5,
}
FIXED_SCALES = {
    "LIB-CAND-LIQUIDATION-ZONE-001": 0.5,  # bounded fraction [0, 1]
    "M4-RULE-PRIOR-EXTREMA-001": 1.0,    # binary presence
    "M4-RULE-PRICE-OI-STATE-001": 1.0,   # bounded tanh product
    "M4-RULE-FUNDING-STATE-001": 1.0,    # bounded tanh
    "M4-RULE-OPEN-INTEREST-CHANGE-001": 1.0,  # bounded activity tanh
}
ALIASES = {
    # The compact baseline selected ATI_H for both rules.  This is not an
    # independent measurement of the full absorption vector.
    "LIB-CAND-ABSORPTION-001": "M4-RULE-AGGRESSOR-IMBALANCE-001",
}
CONTEXT_RULE_IDS = {
    # Relative proximity to Fibonacci levels has no established price-trend sign.
    "LIB-CAND-FIBONACCI-DISTANCE-001",
}
ADVERSE_SIGN_RULE_IDS = {
    # A previous extreme between entry and TP is an obstacle, not support.
    "M4-RULE-PRIOR-EXTREMA-001",
}
PREDECLARED_PAIRS = (
    ("LIB-CAND-EMA-TREND-001", "LIB-CAND-CVD-SLOPE-001"),
    ("LIB-CAND-EMA-TREND-001", "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"),
    ("LIB-CAND-CVD-SLOPE-001", "LIB-CAND-LIQUIDATION-ZONE-001"),
)
OUTCOMES = ("tp_first_within_horizon", "sl_first_within_horizon", "neither_barrier_before_expiry")
TILT_GRID = (-1.0, -0.5, 0.0, 0.5, 1.0)


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    location = (len(ordered) - 1) * fraction
    lower = math.floor(location)
    upper = math.ceil(location)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (location - lower)


def fit_outcome_blind_scales(cases: list[dict]) -> dict[tuple[str, str], dict]:
    """Use one mean per historical episode; never inspect its result label."""
    grouped: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for case in cases:
        if case.get("cohort_partition") != "historical" or not case.get("episode_key"):
            continue
        signals = parse_json_object(case.get("signals_json"))
        for rule_id, signal in signals.items():
            if case.get("time_horizon") not in RETAINED_RULE_HORIZONS.get(rule_id, ()):
                continue
            if not isinstance(signal, dict) or signal.get("variable") != FROZEN_SIGNAL_VARIABLES[rule_id]:
                continue
            value = _finite(signal.get("value"))
            if value is not None:
                grouped[(rule_id, case["time_horizon"], case["episode_key"])].append(value)
    by_rule: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (rule_id, horizon, _), values in grouped.items():
        by_rule[(rule_id, horizon)].append(math.fsum(values) / len(values))
    result = {}
    for rule_id, horizons in RETAINED_RULE_HORIZONS.items():
        for horizon in horizons:
            values = by_rule.get((rule_id, horizon), [])
            neutral = NEUTRAL_VALUES.get(rule_id, 0.0)
            fixed = FIXED_SCALES.get(rule_id)
            empirical = (
                _percentile([abs(value - neutral) for value in values], 0.9)
                if len(values) >= MIN_REFERENCE_EPISODES else None
            )
            scale = fixed if fixed is not None else empirical
            result[(rule_id, horizon)] = {
                "neutral": neutral,
                "scale": scale if scale is not None and scale > 0 else None,
                "reference_episodes": len(values),
                "scale_source": "semantic_bound" if fixed is not None else "historical_episode_p90_absolute",
            }
    return result


def score_case(case: dict, scales: dict[tuple[str, str], dict]) -> dict[str, dict]:
    """Return native bullish(+)/bearish(-) scores, never probability weights."""
    side = str(case.get("side") or "").lower()
    if side not in {"long", "short"}:
        raise ValueError("side_must_be_long_or_short")
    side_sign = 1 if side == "long" else -1
    horizon = str(case.get("time_horizon") or "")
    signals = parse_json_object(case.get("signals_json"))
    result = {}
    for rule_id, horizons in RETAINED_RULE_HORIZONS.items():
        if horizon not in horizons:
            continue
        reference = scales.get((rule_id, horizon), {})
        signal = signals.get(rule_id)
        value = _finite(signal.get("value")) if isinstance(signal, dict) else None
        variable = signal.get("variable") if isinstance(signal, dict) else None
        scale = _finite(reference.get("scale"))
        record = {
            "rule_id": rule_id,
            "variable": variable,
            "raw_value": value,
            "directional_score": None,
            "trade_side_score": None,
            "activity_score": None,
            "context_score": None,
            "duplicate_of": ALIASES.get(rule_id),
            "status": "missing_signal" if value is None else "uncalibrated_scale" if not scale else "scored",
        }
        if value is not None and variable != FROZEN_SIGNAL_VARIABLES[rule_id]:
            record["status"] = "variable_contract_mismatch"
            result[rule_id] = record
            continue
        if value is not None and scale:
            polarity = -1 if rule_id in ADVERSE_SIGN_RULE_IDS else 1
            centered = polarity * (value - float(reference["neutral"])) / scale
            bounded = max(-5, min(5, round(5 * centered)))
            if rule_id in MOVEMENT_RULE_IDS:
                record["activity_score"] = bounded
                record["status"] = "activity_only_not_directional"
            elif rule_id in CONTEXT_RULE_IDS:
                record["context_score"] = bounded
                record["status"] = "level_asymmetry_not_directional"
            else:
                record["trade_side_score"] = bounded
                record["directional_score"] = side_sign * bounded
        result[rule_id] = record
    return result


def consensus_from_scores(scores: dict[str, dict]) -> dict:
    """Unweighted descriptive vote; aliases and movement-only rules never vote."""
    independent = [row for row in scores.values()
                   if row["duplicate_of"] is None and row["directional_score"] is not None]
    values = [row["directional_score"] for row in independent]
    bullish = sum(value > 0 for value in values)
    bearish = sum(value < 0 for value in values)
    return {
        "evaluated_independent_rules": len(values),
        "bullish_rules": bullish,
        "bearish_rules": bearish,
        "neutral_rules": sum(value == 0 for value in values),
        "score_mean": round(math.fsum(values) / len(values), 4) if values else None,
        "conflicting_signals": bool(bullish and bearish),
        "status": "descriptive_no_probability_effect" if values else "no_directional_rules_available",
    }


def _episode_groups(scored: list[dict], *, source_kind: str) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in scored:
        case = item["case"]
        if (case.get("source_kind") != source_kind or not case.get("episode_key")
                or (source_kind == "closed_operation" and "study_outcome_label" in case
                    and case["study_outcome_label"] is None)):
            continue
        groups[(case["cohort_partition"], case["time_horizon"], case["episode_key"])].append(item)
    return groups


def _tilted_probabilities(base: dict, side_score: float, coefficient: float) -> dict:
    """Offline candidate only: preserve three-class probability mass."""
    shift = coefficient * side_score / 5.0
    weights = {
        OUTCOMES[0]: base[OUTCOMES[0]] * math.exp(shift),
        OUTCOMES[1]: base[OUTCOMES[1]] * math.exp(-shift),
        OUTCOMES[2]: base[OUTCOMES[2]],
    }
    total = math.fsum(weights.values())
    return {label: value / total for label, value in weights.items()}


def _brier(probabilities: dict, outcome: str) -> float:
    return math.fsum((probabilities[label] - (1.0 if label == outcome else 0.0)) ** 2
                     for label in OUTCOMES) / 3.0


def _utc_epoch(value: str) -> float:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def _episode_loss(episodes: list[list[dict]], coefficient: float) -> float:
    losses = []
    for members in episodes:
        losses.append(math.fsum(
            _brier(_tilted_probabilities(row["probabilities"], row["score"], coefficient), row["outcome"])
            for row in members
        ) / len(members))
    return math.fsum(losses) / len(losses)


def incremental_validation(cases: list[dict], scales: dict) -> list[dict]:
    """Chronological, episode-grouped screening against stored engine forecasts.

    No coefficient is applied in production. Incomplete three-class cohorts are
    reported as not evaluable, rather than selecting a flattering subset.
    """
    grouped: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for case in cases:
        if case.get("cohort_partition") != "prospective" or case.get("source_kind") != "closed_operation":
            continue
        if "study_outcome_label" in case and case["study_outcome_label"] is None:
            continue
        version = case.get("engine_version")
        outcome_label = case.get("study_outcome_label", case.get("outcome_label"))
        if not version or not case.get("episode_key") or outcome_label not in OUTCOMES:
            continue
        probabilities = parse_json_object(case.get("probabilities_json"))
        values = {label: _finite(probabilities.get(label)) for label in OUTCOMES}
        if any(value is None or value < 0 or value > 1 for value in values.values()):
            continue
        if abs(math.fsum(values.values()) - 1.0) > 0.00001:
            continue
        for rule_id, score in score_case(case, scales).items():
            if score["duplicate_of"] or score["trade_side_score"] is None:
                continue
            key = (rule_id, case["symbol"], case["time_horizon"], version)
            grouped[key][case["episode_key"]].append({
                "analysis_at": str(case["analysis_at"]),
                "probabilities": values,
                "score": score["trade_side_score"],
                "outcome": outcome_label,
            })
    results = []
    for (rule_id, symbol, horizon, version), by_episode in sorted(grouped.items()):
        ordered = sorted(by_episode.values(), key=lambda members: min(_utc_epoch(row["analysis_at"]) for row in members))
        cutoff = int(len(ordered) * 0.6)
        train, test = ordered[:cutoff], ordered[cutoff + 1:]  # purge one adjacent horizon bucket
        train_classes = {row["outcome"] for members in train for row in members}
        test_classes = {row["outcome"] for members in test for row in members}
        record = {
            "rule_id": rule_id, "symbol": symbol, "time_horizon": horizon,
            "engine_version": version, "episodes": len(ordered),
            "train_episodes": len(train), "test_episodes": len(test),
            "train_outcomes": sorted(train_classes), "test_outcomes": sorted(test_classes),
            "baseline_brier": None, "candidate_brier": None,
            "brier_improvement": None, "candidate_coefficient": None,
            "production_effect": "none",
        }
        if len(train) < 20 or len(test) < 10:
            record["status"] = "insufficient_independent_episodes"
        elif train_classes != set(OUTCOMES) or test_classes != set(OUTCOMES):
            record["status"] = "incomplete_three_class_outcomes"
        else:
            candidate = min(TILT_GRID, key=lambda coefficient: (_episode_loss(train, coefficient), abs(coefficient)))
            baseline_loss = _episode_loss(test, 0.0)
            candidate_loss = _episode_loss(test, candidate)
            record.update({
                "baseline_brier": round(baseline_loss, 6),
                "candidate_brier": round(candidate_loss, 6),
                "brier_improvement": round(baseline_loss - candidate_loss, 6),
                "candidate_coefficient": candidate,
                "status": "out_of_sample_screening_only_not_validated",
            })
        results.append(record)
    return results


def build_study(cases: list[dict], *, cohort_sha256: str) -> dict:
    scales = fit_outcome_blind_scales(cases)
    scored = [{"case": case, "scores": score_case(case, scales)} for case in cases]
    primary = _episode_groups(scored, source_kind="closed_operation")
    observation = _episode_groups(scored, source_kind="operation_observation_checkpoint")
    summaries = []
    for rule_id, horizons in RETAINED_RULE_HORIZONS.items():
        for horizon in horizons:
            for partition in ("historical", "prospective"):
                episodes = []
                all_outcome_episodes = []
                raw_cases = 0
                missing = 0
                for (part, h, _), members in primary.items():
                    if part != partition or h != horizon:
                        continue
                    readings = [m["scores"][rule_id] for m in members]
                    movement = rule_id in MOVEMENT_RULE_IDS
                    contextual = rule_id in CONTEXT_RULE_IDS
                    score_key = "activity_score" if movement else "context_score" if contextual else "trade_side_score"
                    usable = [r[score_key] for r in readings if r[score_key] is not None]
                    raw_cases += len(readings)
                    missing += sum(r["status"] in {"missing_signal", "uncalibrated_scale", "variable_contract_mismatch"} for r in readings)
                    if not usable:
                        continue
                    outcomes = [m["case"].get("study_outcome_label", m["case"]["outcome_label"])
                                for m in members]
                    all_outcome_episodes.append({
                        "score": math.fsum(usable) / len(usable),
                        "tp_share": sum(o == "tp_first_within_horizon" for o in outcomes) / len(outcomes),
                        "sl_share": sum(o == "sl_first_within_horizon" for o in outcomes) / len(outcomes),
                        "neither_share": sum(o == "neither_barrier_before_expiry" for o in outcomes) / len(outcomes),
                    })
                    relevant = outcomes if movement else [o for o in outcomes if o in {"tp_first_within_horizon", "sl_first_within_horizon"}]
                    if not relevant:
                        continue
                    episodes.append({
                        "score": math.fsum(usable) / len(usable),
                        "target_share": sum(
                            o != "neither_barrier_before_expiry" if movement else o == "tp_first_within_horizon"
                            for o in relevant
                        ) / len(relevant),
                    })
                bands = {}
                outcome_bands = {}
                for label, predicate in (
                    ("strong_against_trade", lambda s: s <= -STRONG_SCORE),
                    ("weak_against_trade", lambda s: -STRONG_SCORE < s < 0),
                    ("neutral", lambda s: s == 0),
                    ("weak_for_trade", lambda s: 0 < s < STRONG_SCORE),
                    ("strong_for_trade", lambda s: s >= STRONG_SCORE),
                ):
                    selected = [e for e in episodes if predicate(e["score"])]
                    bands[label] = {
                        "episodes": len(selected),
                        "target_episode_share": round(math.fsum(e["target_share"] for e in selected) / len(selected), 4) if selected else None,
                    }
                    all_selected = [e for e in all_outcome_episodes if predicate(e["score"])]
                    outcome_bands[label] = {
                        "episodes": len(all_selected),
                        **{
                            f"{outcome}_share": round(math.fsum(e[f"{outcome}_share"] for e in all_selected) / len(all_selected), 4)
                            if all_selected else None
                            for outcome in ("tp", "sl", "neither")
                        },
                    }
                strong_wrong_mass = math.fsum(
                    (1.0 - e["target_share"]) if e["score"] >= STRONG_SCORE else e["target_share"]
                    for e in episodes if abs(e["score"]) >= STRONG_SCORE
                )
                positive_mass = math.fsum(e["target_share"] for e in episodes)
                negative_mass = len(episodes) - positive_mass
                summaries.append({
                    "rule_id": rule_id,
                    "time_horizon": horizon,
                    "partition": partition,
                    "mode": "activity_only" if rule_id in MOVEMENT_RULE_IDS else
                        "context_only" if rule_id in CONTEXT_RULE_IDS else "directional_support",
                    "target": "barrier_touched" if movement else "tp_first_given_touch",
                    "duplicate_of": ALIASES.get(rule_id),
                    "source_kind": "closed_operation",
                    "raw_cases": raw_cases,
                    "missing_or_uncalibrated": missing,
                    "effective_episodes": len(episodes),
                    "episodes_with_three_class_outcome": len(all_outcome_episodes),
                    "positive_episode_mass": round(positive_mass, 4),
                    "negative_episode_mass": round(negative_mass, 4),
                    "strong_wrong_episode_mass": round(strong_wrong_mass, 4),
                    "score_bands": bands,
                    "three_class_outcome_bands": outcome_bands,
                    "evaluability": "no_comparable_values" if not episodes else
                        "single_outcome_class" if positive_mass == 0 or negative_mass == 0 else
                        "descriptive_not_validated",
                    "conclusion": "descriptive_only_no_probability_effect",
                })
    pair_results = []
    for left, right in PREDECLARED_PAIRS:
        if ALIASES.get(left) == right or ALIASES.get(right) == left:
            continue
        for partition in ("historical", "prospective"):
            aligned = []
            for (part, _, _), members in primary.items():
                if part != partition:
                    continue
                pair = [(m["scores"].get(left), m["scores"].get(right),
                         m["case"].get("study_outcome_label", m["case"]["outcome_label"]),
                         m["case"]["side"]) for m in members]
                pair = [(a["directional_score"], b["directional_score"], outcome, side)
                        for a, b, outcome, side in pair
                        if a and b and a["directional_score"] is not None and b["directional_score"] is not None]
                if not pair:
                    continue
                a = math.fsum(p[0] for p in pair) / len(pair)
                b = math.fsum(p[1] for p in pair) / len(pair)
                if not (a > 0 and b > 0 or a < 0 and b < 0):
                    continue
                outcomes = [p for p in pair if p[2] in {"tp_first_within_horizon", "sl_first_within_horizon"}]
                if outcomes:
                    aligned.append(("bullish" if a > 0 else "bearish",
                                    min(abs(a), abs(b)),
                                    sum((outcome == "tp_first_within_horizon") == (side == "long")
                                        for _, _, outcome, side in outcomes) / len(outcomes)))
            for state in ("bullish", "bearish"):
                selected = [(strength, share) for label, strength, share in aligned if label == state]
                pair_results.append({
                    "left": left, "right": right, "partition": partition, "state": state,
                    "episodes": len(selected),
                    "strong_both_episodes": sum(strength >= STRONG_SCORE for strength, _ in selected),
                    "price_up_episode_share": round(math.fsum(share for _, share in selected) / len(selected), 4) if selected else None,
                    "status": "descriptive_not_joint_incremental_value" if len(selected) >= 10 else "insufficient_independent_episodes",
                })
    consensus_results = []
    for partition in ("historical", "prospective"):
        for horizon in ("intraday_short", "intraday_wide", "short_swing"):
            by_state: dict[str, list[float]] = defaultdict(list)
            for (part, h, _), members in primary.items():
                if part != partition or h != horizon:
                    continue
                readings = [(consensus_from_scores(m["scores"]), m["case"]) for m in members]
                readings = [(vote, case) for vote, case in readings
                            if case.get("study_outcome_label", case["outcome_label"])
                            in {"tp_first_within_horizon", "sl_first_within_horizon"}]
                if not readings:
                    continue
                avg_bullish = math.fsum(vote["bullish_rules"] for vote, _ in readings) / len(readings)
                avg_bearish = math.fsum(vote["bearish_rules"] for vote, _ in readings) / len(readings)
                if avg_bullish >= 2 and avg_bearish == 0:
                    state = "multiple_bullish_no_bearish"
                elif avg_bearish >= 2 and avg_bullish == 0:
                    state = "multiple_bearish_no_bullish"
                elif avg_bullish > 0 and avg_bearish > 0:
                    state = "conflicting"
                else:
                    state = "weak_or_unavailable"
                up_share = sum(
                    (case.get("study_outcome_label", case["outcome_label"]) == "tp_first_within_horizon")
                    == (case["side"] == "long")
                    for _, case in readings
                ) / len(readings)
                by_state[state].append(up_share)
            for state in ("multiple_bullish_no_bearish", "multiple_bearish_no_bullish",
                          "conflicting", "weak_or_unavailable"):
                shares = by_state[state]
                consensus_results.append({
                    "partition": partition, "time_horizon": horizon, "state": state,
                    "episodes": len(shares),
                    "price_up_episode_share": round(math.fsum(shares) / len(shares), 4) if shares else None,
                    "status": "descriptive_not_validated" if len(shares) >= 10 else "insufficient_independent_episodes",
                })
    return {
        "score_version": SCORE_VERSION,
        "retained_rule_count": len(RETAINED_RULE_HORIZONS),
        "retained_rule_horizon_count": sum(len(horizons) for horizons in RETAINED_RULE_HORIZONS.values()),
        "reference_cohort": BASELINE_COHORT_KEY,
        "reference_cohort_sha256": cohort_sha256,
        "scale_contract": [
            {"rule_id": rule_id, "time_horizon": horizon, **value}
            for (rule_id, horizon), value in sorted(scales.items())
        ],
        "direction_semantics": "positive_is_bullish_native_market_direction_not_probability",
        "null_semantics": "missing_or_nondirectional_is_not_neutral_zero",
        "production_effect": "none",
        "database_writes": False,
        "primary_case_source": "closed_operation_only",
        "observation_control_counts": {
            "historical": sum(len(v) for k, v in observation.items() if k[0] == "historical"),
            "prospective": sum(len(v) for k, v in observation.items() if k[0] == "prospective"),
        },
        "excluded_late_close_labels": {
            partition: sum(case.get("cohort_partition") == partition
                           and case.get("fixed_horizon_label_status") == "late_close_label_not_verified"
                           for case in cases)
            for partition in ("historical", "prospective")
        },
        "reconstructed_no_touch_from_existing_1m_evidence": {
            partition: sum(case.get("cohort_partition") == partition
                           and case.get("fixed_horizon_label_status") == "reconstructed_1m_no_touch"
                           and case.get("outcome_label") != "neither_barrier_before_expiry"
                           for case in cases)
            for partition in ("historical", "prospective")
        },
        "fixed_horizon_label_status_counts": {
            partition: dict(sorted(Counter(
                case.get("fixed_horizon_label_status", "not_annotated")
                for case in cases if case.get("cohort_partition") == partition
                and case.get("source_kind") == "closed_operation"
            ).items()))
            for partition in ("historical", "prospective")
        },
        "prospective_verified_outcomes_by_horizon": {
            horizon: dict(sorted(Counter(
                case.get("study_outcome_label", case["outcome_label"])
                for case in cases if case.get("cohort_partition") == "prospective"
                and case.get("source_kind") == "closed_operation"
                and case.get("time_horizon") == horizon
                and case.get("study_outcome_label", case["outcome_label"]) in OUTCOMES
            ).items()))
            for horizon in ("intraday_short", "intraday_wide", "short_swing")
        },
        "rule_results": summaries,
        "predeclared_pair_results": pair_results,
        "consensus_results": consensus_results,
        "incremental_validation": incremental_validation(cases, scales),
        "limitations": [
            "Scores are hypotheses scaled without outcomes, not learned probabilities.",
            "The compact base has selected scalar variables, not every output of each full rule.",
            "TP/SL labels cannot grade native direction when neither barrier is touched; fixed-horizon return is not stored here.",
            "Closed-operation cases condition on closure and may underrepresent no-touch outcomes.",
            "Only comparable closed-operation episodes enter the primary score bands; controls are counted separately.",
            "A pair's co-occurrence is not proof of incremental interaction.",
            "Mixed engine versions and formula histories require separate strata before out-of-sample validation.",
            "The candidate probability tilt exists only in this offline test and has no production effect.",
        ],
    }


def load_compact_facts(db) -> tuple[str, list[dict]]:
    cohort = db.execute(
        "SELECT id,compact_dataset_sha256 FROM observational_learning_cohorts WHERE cohort_key=? AND status='sealed' LIMIT 1",
        (BASELINE_COHORT_KEY,),
    ).fetchone()
    if cohort is None:
        raise RuntimeError("sealed_observational_cohort_missing")
    rows = db.execute(
        """SELECT cohort_partition,source_kind,source_reference,symbol,side,time_horizon,
                  analysis_at,evaluation_expires_at,outcome_label,episode_key,signals_json,probabilities_json
           FROM observational_learning_cases WHERE cohort_id=? ORDER BY analysis_at,id""",
        (int(cohort["id"]),),
    ).fetchall()
    cases = [dict(row) for row in rows]
    # Only compact identifiers are read; avoid fetching recommendation snapshots.
    metadata_by_operation = load_closed_operation_label_metadata(
        db, int(cohort["id"]), include_historical=True,
    )
    for case in cases:
        reference = str(case.get("source_reference") or "")
        operation_id = reference.removeprefix("operation:") if reference.startswith("operation:") else ""
        metadata = metadata_by_operation.get(int(operation_id), {}) if operation_id.isdigit() else {}
        case["engine_version"] = metadata.get("engine_version")
        closed_at = metadata.get("closed_at")
        expires_at = case.get("evaluation_expires_at")
        if case.get("source_kind") != "closed_operation":
            case["fixed_horizon_label_status"] = "independent_or_non_operation_source"
            continue
        if not metadata:
            case["fixed_horizon_label_status"] = "operation_metadata_missing"
            case["study_outcome_label"] = None
        else:
            label, status = fixed_horizon_outcome_from_evidence(
                recorded_outcome=case["outcome_label"],
                plan_result=metadata.get("plan_result"),
                analysis_at=case["analysis_at"],
                evaluation_expires_at=expires_at,
                closed_at=closed_at,
                exact_outcome=metadata.get("exact_outcome_label"),
                evidence_status=metadata.get("evidence_status"),
                evidence_quality=metadata.get("evidence_quality"),
                evidence_coverage_ratio=metadata.get("evidence_coverage_ratio"),
                evidence_start_at=metadata.get("evidence_start_at"),
                evidence_end_at=metadata.get("evidence_end_at"),
                first_plan_touch_at=metadata.get("first_plan_touch_at"),
                reconstructed_plan_result=metadata.get("reconstructed_plan_result"),
            )
            case["fixed_horizon_label_status"] = status
            case["study_outcome_label"] = label
    return str(cohort["compact_dataset_sha256"]), cases


def current_execution_coverage(db, engine_version: str) -> dict:
    """Server-side counts only; no raw snapshots cross the database connection."""
    rows = db.execute(
        """SELECT r.time_horizon, trace.value->>'rule_id' AS rule_id,
                  trace.value->>'status' AS status, COUNT(*) AS n
           FROM recommendations r
           CROSS JOIN LATERAL jsonb_array_elements(
               r.snapshot_json::jsonb->'stage_rule_traces'->r.time_horizon
           ) AS trace(value)
           WHERE r.engine_version=? AND r.analysis_type='pre_trade'
             AND r.operation_id IS NOT NULL
           GROUP BY r.time_horizon,trace.value->>'rule_id',trace.value->>'status'
           ORDER BY r.time_horizon,rule_id,status""",
        (engine_version,),
    ).fetchall()
    facts = [dict(row) for row in rows]
    executed = {row["rule_id"] for row in facts if row["status"] in {
        "evaluated", "evaluated_shadow", "partially_evaluated_shadow"}}
    return {
        "engine_version": engine_version,
        "executed_rule_count": len(executed),
        "executed_not_in_frozen_compact_cohort": sorted(executed - set(RETAINED_RULE_HORIZONS)),
        "frozen_not_executed_in_current_engine": sorted(set(RETAINED_RULE_HORIZONS) - executed),
        "rule_horizon_status_counts": facts,
        "database_writes": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only observational direction study")
    parser.add_argument("--json", action="store_true", help="Print the full versioned report")
    parser.add_argument("--source-reference", help="Show -5..+5 scores for one compact case, e.g. operation:529")
    parser.add_argument("--coverage", action="store_true", help="Count current executed rules without fetching snapshots")
    args = parser.parse_args()
    from db import close_pool, connect
    from versioning import ENGINE_VERSION
    try:
        with connect() as db:
            if args.coverage:
                coverage = current_execution_coverage(db, ENGINE_VERSION)
            else:
                sha, rows = load_compact_facts(db)
    finally:
        close_pool()
    if args.coverage:
        print(canonical_json(coverage))
        return
    report = build_study(rows, cohort_sha256=sha)
    if args.source_reference:
        selected = [row for row in rows if row["source_reference"] == args.source_reference]
        if not selected:
            raise SystemExit(f"No compact case found: {args.source_reference}")
        scales = fit_outcome_blind_scales(rows)
        for row in selected:
            print(canonical_json({
                "score_version": SCORE_VERSION,
                "source_reference": row["source_reference"],
                "time_horizon": row["time_horizon"],
                "side": row["side"],
                "recorded_outcome_label": row["outcome_label"],
                "fixed_horizon_label_status": row["fixed_horizon_label_status"],
                "fixed_horizon_outcome_label": row.get("study_outcome_label", row["outcome_label"]),
                "scores": score_case(row, scales),
                "consensus": consensus_from_scores(score_case(row, scales)),
                "production_effect": "none",
            }))
        return
    if args.json:
        print(canonical_json(report))
    else:
        print(f"{report['score_version']} | reference={sha[:12]} | "
              f"rules={report['retained_rule_count']} | "
              f"rule_horizons={report['retained_rule_horizon_count']} | production_effect=none")
        for item in report["rule_results"]:
            if item["partition"] != "prospective":
                continue
            bands = item["score_bands"]
            positive = bands["strong_for_trade"]
            negative = bands["strong_against_trade"]
            three = item["three_class_outcome_bands"]["strong_for_trade"]
            print(f"{item['time_horizon']} {item['rule_id']} ({item['mode']}): cases={item['raw_cases']} "
                  f"episodes={item['effective_episodes']} missing={item['missing_or_uncalibrated']} "
                  f"high_score={positive['episodes']} outcome={positive['target_episode_share']} "
                  f"three_class_high=({three['tp_share']},{three['sl_share']},{three['neither_share']}) "
                  f"low_score={negative['episodes']} outcome={negative['target_episode_share']} "
                  f"strong_wrong_mass={item['strong_wrong_episode_mass']} "
                  f"evaluability={item['evaluability']}")
        print("Predeclared joint patterns, prospective closed-operation episodes:")
        for item in report["predeclared_pair_results"]:
            if item["partition"] == "prospective":
                print(f"{item['left']} + {item['right']} {item['state']}: "
                      f"episodes={item['episodes']} both_strong={item['strong_both_episodes']} "
                      f"price_up_share={item['price_up_episode_share']} "
                      f"status={item['status']}")
        print("Native bullish/bearish consensus, prospective closed-operation episodes:")
        for item in report["consensus_results"]:
            if item["partition"] == "prospective":
                print(f"{item['time_horizon']} {item['state']}: episodes={item['episodes']} "
                      f"price_up_share={item['price_up_episode_share']} status={item['status']}")
        validation_counts = Counter(item["status"] for item in report["incremental_validation"])
        print(f"Out-of-sample three-class screening by symbol/horizon/engine: {dict(sorted(validation_counts.items()))}")
        print(f"Prospective fixed-horizon label quality: {report['fixed_horizon_label_status_counts']['prospective']}")
        print(f"Prospective verified outcomes: {report['prospective_verified_outcomes_by_horizon']}")
        print("No probability weight was calculated or changed.")


if __name__ == "__main__":
    main()
