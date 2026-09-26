"""Read-only directional inventory for every rule executed by the current engine.

This intentionally does not change forecasts or write a second copy of the
already-persisted pre-trade traces. Scores are versioned hypotheses, not
measured probability contributions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict

from observational_learning_base import (
    BASELINE_COHORT_KEY, PLAN_RESULT_TO_OUTCOME, canonical_json,
    fixed_horizon_outcome_from_evidence, prospective_episode_key,
)
from observational_direction_study import OUTCOMES, TILT_GRID, _episode_loss, _utc_epoch
from operation_observation_learning import observation_rule_signals
from versioning import ENGINE_VERSION
from observational_measurement_scores import absorption_proxy, ABSORPTION_SCORE_VERSION


SCORE_VERSION = "current-rule-direction-v0.2"
SIGNAL_UNIT_THRESHOLDS = {
    "M4-RULE-PATH-STRUCTURE-001": 0.04,
    "M4-RULE-MTF-HIERARCHY-001": 0.04,
    "M4-RULE-AGGRESSOR-IMBALANCE-001": 0.03,
    "LIB-CAND-EMA-TREND-001": 0.20,
    "LIB-CAND-RSI-WILDER-001": 0.12,
    "LIB-CAND-ATR-EXTENSION-001": 0.25,
    "LIB-CAND-CVD-SLOPE-001": 0.025,
    "LIB-CAND-ABSORPTION-001": 0.12,
    "M4-RULE-PRIOR-EXTREMA-001": 0.50,
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": 0.20,
    "LIB-CAND-LIQUIDATION-ZONE-001": 0.35,
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": 0.10,
    "M4-RULE-PRICE-OI-STATE-001": 1.0,
    "M4-RULE-FUNDING-STATE-001": 1.0,
}
CONTEXT_RULES = {
    "M4-RULE-VOLATILITY-RANK-001": "volatility_activity",
    "LIB-CAND-RELATIVE-VOLUME-001": "volume_activity",
    "LIB-CAND-COMPRESSION-001": "compression_state",
    "LIB-CAND-FIBONACCI-DISTANCE-001": "level_asymmetry_not_trend",
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "open_interest_activity",
}
PREDECLARED_PAIRS = (
    ("M4-RULE-PATH-STRUCTURE-001", "M4-RULE-MTF-HIERARCHY-001"),
    ("LIB-CAND-EMA-TREND-001", "LIB-CAND-RSI-WILDER-001"),
    ("LIB-CAND-CVD-SLOPE-001", "M4-RULE-AGGRESSOR-IMBALANCE-001"),
    ("LIB-CAND-ORDERBOOK-IMBALANCE-001", "LIB-CAND-LIQUIDATION-ZONE-001"),
    ("M4-RULE-PRICE-OI-STATE-001", "M4-RULE-FUNDING-STATE-001"),
    ("LIB-CAND-ABSORPTION-001", "M4-RULE-PRICE-OI-STATE-001"),
)
OUTCOME_CLASSES = (
    "tp_first_within_horizon", "sl_first_within_horizon", "neither_barrier_before_expiry",
)

# Scalar inputs used by observation_rule_signals; no candles, book arrays or
# duplicated market snapshots cross the network in the all-closed audit.
AUDIT_METRIC_PATHS = (
    "directional_path_efficiency_h", "directional_path_efficiency_2h",
    "directional_path_efficiency_4h", "volatility_percentile_60", "ATI_H",
    "side_adjusted_slope_atr", "side_adjusted_close_vs_ema50_log",
    "side_adjusted_ema50_vs_ema200_log", "side_adjusted_centered_rsi",
    "side_adjusted_extension_atr", "relative_horizon_volume", "volume_midrank_60",
    "side_adjusted_normalized_cvd_slope", "side_adjusted_terminal_imbalance",
    "favorable_absorption_score", "adverse_absorption_score",
    "side_adjusted_horizon_displacement_atr", "compression_vector.atr_rank",
    "horizon_displacement_atr", "flow_opposing_wick_ratio",
    "dOI_H", "D_H", "last_settled_funding_rate", "settled_funding_rate_per_hour",
    "compression_vector.bollinger_width_rank", "target_extreme_between_entry_and_tp",
    "target_path_level_count", "adverse_path_level_count",
    "nearest_to_take_profit.absolute_distance_sigma_horizon",
    "nearest_to_stop_loss.absolute_distance_sigma_horizon",
    "target_cascade_mass.within_2pct", "adverse_cascade_mass.within_2pct", "sample_size",
    "current_snapshot.side_adjusted_imbalances.top_20",
    "persistence.top_20.side_adjusted_mean",
    "executed_flow.side_adjusted_executed_flow_imbalance",
)
AUDIT_PROJECTION_VERSION = "directional-input-projection-v0.1"


def _finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _bounded_score(value: float) -> int:
    return max(-5, min(5, round(value)))


def _context_score(signal: dict) -> int | None:
    metrics = {metric["key"]: _finite(metric.get("value"))
               for metric in signal.get("metrics") or []}
    rule = signal["rule_id"]
    if rule == "M4-RULE-VOLATILITY-RANK-001":
        rank = metrics.get("volatility_percentile_60")
        return _bounded_score(5 * (2 * rank - 1)) if rank is not None else None
    if rule == "LIB-CAND-RELATIVE-VOLUME-001":
        rank = metrics.get("volume_midrank_60")
        if rank is not None:
            return _bounded_score(5 * (2 * rank - 1))
        ratio = metrics.get("relative_horizon_volume")
        return _bounded_score(5 * math.tanh(math.log(ratio))) if ratio is not None and ratio > 0 else None
    if rule == "LIB-CAND-COMPRESSION-001":
        ranks = [metrics.get(name) for name in (
            "compression_vector.atr_rank", "compression_vector.bollinger_width_rank")]
        usable = [value for value in ranks if value is not None]
        return _bounded_score(5 * (1 - 2 * math.fsum(usable) / len(usable))) if usable else None
    if rule == "LIB-CAND-FIBONACCI-DISTANCE-001":
        target = metrics.get("nearest_to_take_profit.absolute_distance_sigma_horizon")
        stop = metrics.get("nearest_to_stop_loss.absolute_distance_sigma_horizon")
        return _bounded_score(5 * math.tanh(stop - target)) if target is not None and stop is not None else None
    return None


def score_current_signal(signal: dict, *, side: str) -> dict:
    """Give a native-direction score or a separate non-directional context score."""
    rule = signal["rule_id"]
    raw = _finite(signal.get("score"))
    if rule in SIGNAL_UNIT_THRESHOLDS and raw is not None:
        side_score = (-5 if raw < 0 else 0) if rule == "M4-RULE-PRIOR-EXTREMA-001" else \
            _bounded_score(raw / SIGNAL_UNIT_THRESHOLDS[rule])
        direction = side_score if side == "long" else -side_score
        status = "directional_hypothesis"
        context_score = None
    elif rule in CONTEXT_RULES:
        side_score = direction = None
        context_score = _context_score(signal)
        status = "context_not_directional" if context_score is not None else "context_missing"
    else:
        side_score = direction = context_score = None
        status = "missing_or_unsupported_formula"
    output_names = sorted(str(name) for name in signal.get("formula_outputs") or [])
    return {
        "rule_id": rule,
        "formula_role": signal.get("formula_role"),
        "formula_output_count": len(output_names),
        "formula_outputs_sha256": hashlib.sha256(canonical_json(output_names).encode()).hexdigest(),
        "category": signal.get("category"),
        "raw_support_value": raw,
        "trade_side_score": side_score,
        "directional_score": direction,
        "context_score": context_score,
        "context_kind": CONTEXT_RULES.get(rule),
        "status": status,
    }


def score_current_trace_case(case: dict) -> list[dict]:
    traces = case.get("traces") or []
    if isinstance(traces, str):
        traces = json.loads(traces)
    if not isinstance(traces, list):
        return []
    signals = observation_rule_signals({
        "side": case["side"],
        "stage_rule_traces": {case["time_horizon"]: traces},
    })
    scores = [score_current_signal(signal, side=str(case["side"]).lower()) for signal in signals]
    by_rule = {trace.get("rule_id"): trace for trace in traces}
    for row in scores:
        trace = by_rule.get(row["rule_id"], {})
        if row["rule_id"] == "LIB-CAND-ABSORPTION-001":
            evaluation = absorption_proxy(trace.get("outputs") or {}, side=str(case["side"]).lower())
            row.update({"formula_role": ABSORPTION_SCORE_VERSION,
                        "trade_side_score": evaluation["trade_side_score"],
                        "directional_score": evaluation["directional_score"],
                        "raw_support_value": evaluation["raw_trade_support"], "measurement_inputs": evaluation["inputs"],
                        "score_diagnostics": {"factors": evaluation["factors"], "zero_cause": evaluation["zero_cause"]},
                        "status": "directional_hypothesis" if evaluation["reason"] is None else "missing_or_unsupported_formula"})
        elif row["rule_id"] == "M4-RULE-OPEN-INTEREST-CHANGE-001":
            change = _finite((trace.get("outputs") or {}).get("dOI_H"))
            row.update({"context_kind": "open_interest_activity", "context_score":
                        _bounded_score(5*math.tanh(50*abs(change))) if change is not None else None,
                        "status": "context_not_directional" if change is not None else "context_missing"})
        elif row["rule_id"] in {"M4-RULE-PRICE-OI-STATE-001", "M4-RULE-FUNDING-STATE-001"}:
            outputs = trace.get("outputs") or {}
            if row["rule_id"] == "M4-RULE-PRICE-OI-STATE-001":
                price, oi = _finite(outputs.get("D_H")), _finite(outputs.get("dOI_H"))
                direction = 5*((price > 0)-(price < 0))*math.tanh(50*oi) if price is not None and oi is not None else None
            else:
                hourly_rate = _finite(outputs.get("settled_funding_rate_per_hour"))
                direction = -5*math.tanh(hourly_rate*8/0.0005) if hourly_rate is not None else None
            row.update({"directional_score": _bounded_score(direction) if direction is not None else None,
                        "trade_side_score": _bounded_score(direction)*(1 if case["side"] == "long" else -1) if direction is not None else None,
                        "raw_support_value": direction/5*(1 if case["side"] == "long" else -1) if direction is not None else None,
                        "status": "directional_hypothesis" if direction is not None else "missing_or_unsupported_formula"})
        measured_names = {
            "M4-RULE-OPEN-INTEREST-CHANGE-001": ("dOI_H","oi_previous","oi_current"),
            "M4-RULE-PRICE-OI-STATE-001": ("D_H","dOI_H","price_previous","price_current"),
            "M4-RULE-FUNDING-STATE-001": ("last_settled_funding_rate","settled_funding_rate_per_hour","observed_interval_hours"),
        }.get(row["rule_id"])
        if measured_names:
            row["measurement_inputs"] = {key:_finite((trace.get("outputs") or {}).get(key)) for key in measured_names}
        formula_version = trace.get("rule_version")
        measurement_version = trace.get("measurement_contract_version")
        if formula_version or measurement_version or row["rule_id"] == "LIB-CAND-ABSORPTION-001":
            row["formula_role"] = (str(row["formula_role"]) + ":"
                + str(formula_version or "unversioned_formula") + ":"
                + str(measurement_version or "unversioned_measurement"))
        if trace.get("status") in {"blocked", "unavailable", "not_evaluated", "not_configured"}:
            row.update({"directional_score": None,"trade_side_score": None,"context_score": None,
                        "raw_support_value": None,"status": "missing_or_unsupported_formula",
                        "source_reason": "blocked_source_contract"})
    return scores


def score_compact_measurements(case: dict) -> list[dict]:
    """Evaluate new contracts from the compact learning facts, no snapshots.

    Null legacy values deliberately cannot contaminate the sealed historical
    counters. These exact numeric inputs instead form versioned new strata.
    Checkpoint facts remain checkpoint facts; this does not create operations.
    """
    signals = case.get("signals_json") or {}
    if isinstance(signals, str):
        signals = json.loads(signals)
    traces = []
    for rule, item in signals.items():
        measurement = item.get("measurement") if isinstance(item, dict) else None
        if not isinstance(measurement, dict):
            continue
        traces.append({"rule_id": rule, "rule_version": measurement.get("rule_version"),
            "measurement_contract_version": measurement.get("contract_version"),
            "status": measurement.get("status"), "outputs": measurement.get("numeric_inputs") or {},
            "probability_effect": "none_observation_only"})
    return score_current_trace_case({"side": case["side"],"time_horizon": case["time_horizon"],"traces": traces})


def load_compact_measurement_cases(db, *, batch_size=50, max_bytes=2_000_000) -> tuple[list[dict], dict]:
    """Keyset read of exact new measurement fields, never recommendation snapshots.

    Metadata joins use the source checkpoint or matching analysis timestamp;
    they must not substitute a later recommendation about the same operation.
    The caller supplies a repeatable-read, read-only transaction.
    """
    if not 1 <= batch_size <= 200 or max_bytes <= 0:
        raise ValueError("invalid_compact_measurement_read_budget")
    cohort = db.execute("""SELECT id FROM observational_learning_cohorts
        WHERE cohort_key=? AND status='sealed' LIMIT 1""", (BASELINE_COHORT_KEY,)).fetchone()
    if not cohort:
        raise ValueError("sealed_observational_cohort_missing")
    scope = """c.cohort_id=? AND c.source_kind IN ('closed_operation','operation_observation_checkpoint')
        AND EXISTS (SELECT 1 FROM jsonb_each(c.signals_json::jsonb) signal
                    WHERE jsonb_typeof(signal.value->'measurement')='object')"""
    inventory = db.execute(f"""SELECT count(*) AS cases,COALESCE(max(c.id),0) AS max_id
        FROM observational_learning_cases c WHERE {scope}""", (int(cohort["id"]),)).fetchone()
    maximum, expected = int(inventory["max_id"]), int(inventory["cases"])
    query = f"""WITH selected AS (
        SELECT c.*, CASE
          WHEN c.source_kind='closed_operation' AND c.source_reference ~ '^operation:[0-9]+$'
            THEN split_part(c.source_reference,':',2)::bigint
          WHEN c.source_kind='operation_observation_checkpoint' AND c.source_reference ~ '^observation:[0-9]+o[0-9]+$'
            THEN split_part(split_part(c.source_reference,':',2),'o',1)::bigint
          END AS parent_operation_id
        FROM observational_learning_cases c WHERE {scope} AND c.id>? AND c.id<=?
        ORDER BY c.id LIMIT ?
    ) SELECT c.id,c.parent_operation_id AS operation_id,c.source_kind,c.source_reference,
        c.cohort_partition,c.symbol,c.side,c.time_horizon,c.analysis_at,c.evaluation_expires_at,
        c.episode_key,c.probabilities_json,r.engine_version,
        c.probabilities_json::jsonb->>'tp_first_within_horizon' AS tp_probability,
        c.probabilities_json::jsonb->>'sl_first_within_horizon' AS sl_probability,
        c.probabilities_json::jsonb->>'neither_barrier_before_expiry' AS range_probability,
        o.closed_at,le.plan_result,le.evidence_status,le.evidence_quality,le.evidence_coverage_ratio,
        le.evidence_start_at,le.evidence_end_at,le.first_plan_touch_at,le.reconstructed_plan_result,
        exact.outcome_label AS exact_outcome_label,
        (SELECT jsonb_object_agg(signal.key,jsonb_build_object('measurement',signal.value->'measurement'))
           FROM jsonb_each(c.signals_json::jsonb) signal
           WHERE jsonb_typeof(signal.value->'measurement')='object') AS signals_json
        FROM selected c
        LEFT JOIN operations o ON o.id=c.parent_operation_id
        LEFT JOIN operation_observation_checkpoints cp
          ON c.source_kind='operation_observation_checkpoint'
         AND cp.checkpoint_code=split_part(c.source_reference,':',2)
        LEFT JOIN LATERAL (
          SELECT candidate.id,candidate.engine_version FROM recommendations candidate
          WHERE (c.source_kind='operation_observation_checkpoint' AND candidate.id=cp.recommendation_id)
             OR (c.source_kind='closed_operation' AND candidate.operation_id=c.parent_operation_id
                 AND candidate.analysis_type='pre_trade'
                 AND (candidate.snapshot_json::jsonb->>'analysis_at')::timestamptz=c.analysis_at)
          ORDER BY candidate.id DESC LIMIT 1
        ) r ON TRUE
        LEFT JOIN LATERAL (SELECT candidate.* FROM learning_evaluations candidate
          WHERE candidate.operation_id=c.parent_operation_id ORDER BY candidate.id DESC LIMIT 1) le ON TRUE
        LEFT JOIN LATERAL (SELECT e.outcome_label FROM recommendation_counterfactual_evaluations e
          WHERE e.recommendation_id=r.id AND e.contract_quality='exact'
            AND e.formal_learning_eligible AND e.evaluation_status='evaluated'
          ORDER BY e.created_at DESC,e.id DESC LIMIT 1) exact ON TRUE
        ORDER BY c.id"""
    after = batches = received = 0
    rows = []
    if maximum == 0:
        # Also validate the actual projection/joins when a not-yet-deployed
        # contract has no rows. An empty inventory must not hide SQL defects.
        empty = db.execute(query,(int(cohort["id"]),0,0,batch_size)).fetchall()
        if empty:
            raise ValueError("compact_measurement_empty_inventory_mismatch")
    while after < maximum:
        page = [dict(row) for row in db.execute(query, (int(cohort["id"]),after,maximum,batch_size)).fetchall()]
        if not page:
            break
        received += len(canonical_json(page).encode())
        if received > max_bytes:
            raise ValueError("compact_measurement_transfer_budget_exceeded_no_partial_success")
        if any(int(row["id"]) <= after for row in page):
            raise ValueError("compact_measurement_cursor_not_advancing")
        rows.extend(page)
        batches += 1
        after = int(page[-1]["id"])
    if len(rows) != expected or len({row["id"] for row in rows}) != expected:
        raise ValueError("compact_measurement_coverage_mismatch_no_partial_success")
    return rows, {"compact_cases": expected,"batches": batches,"complete_coverage": True,
                  "logical_json_bytes_received": received,"transfer_budget_bytes": max_bytes,
                  "recommendation_snapshots_downloaded": False}


def compact_measurement_report(cases: list[dict], *, acquisition: dict | None = None, include_cases=False) -> dict:
    """Source cohorts and engine baselines stay separate; scores are not weights."""
    groups = defaultdict(list)
    for case in cases:
        groups[(case.get("source_kind") or "unknown",case.get("engine_version") or "unknown")].append(case)
    reports = []
    for (source, engine), members in sorted(groups.items()):
        report = current_engine_summary(members, compact_measurements=True)
        report["source_kind"],report["engine_version"] = source,engine
        report["episode_buckets"] = len({(row["symbol"],row["time_horizon"],row.get("episode_key")) for row in members})
        if source != "closed_operation" or engine == "unknown":
            report["incremental_validation"] = []
            report["inference_status"] = "descriptive_controls_or_unknown_baseline_not_primary_independent_trials"
        if not include_cases:
            del report["operations"]
        reports.append(report)
    return {"scope":"compact_measurements_no_snapshots", "score_version": SCORE_VERSION,
            "cases_read":len(cases),"source_counts":dict(Counter(row.get("source_kind") for row in cases)),
            "groups": reports,"acquisition": acquisition or {},
            "status":"evaluated_descriptively" if cases else "no_new_measurement_contracts_recorded",
            "database_writes":False,"production_effect":"none",
            "limitations":["Scores are unvalidated directional hypotheses, not probability weights.",
                           "An episode bucket is a dependence control, not proof of statistical independence.",
                           "Entry operations and follow-up checkpoints are not pooled as independent trades.",
                           "Coefficient fitting needs later, non-overlapping verified outcomes in every class."]}


def screen_current_incremental(by_episode: dict, summaries: list[dict]) -> list[dict]:
    """Screen each exact formula against stored forecasts in later episodes."""
    results = []
    for formula in summaries:
        if formula["score_kind"] != "directional_hypothesis":
            continue
        symbol, horizon = formula["symbol"], formula["time_horizon"]
        rule, role = formula["rule_id"], formula["formula_role"]
        episodes = []
        for (market_symbol, market_horizon, _), members in by_episode.items():
            if (market_symbol, market_horizon) != (symbol, horizon):
                continue
            eligible = []
            for member in members:
                probabilities = member["probabilities"]
                if (member["outcome"] not in OUTCOMES
                        or any(value is None or not 0 <= value <= 1 for value in probabilities.values())
                        or abs(math.fsum(probabilities.values()) - 1.0) > 0.00001):
                    continue
                selected = [row for row in member["scores"]
                            if row["rule_id"] == rule and row["formula_role"] == role
                            and row["trade_side_score"] is not None]
                if len(selected) != 1:
                    continue
                eligible.append({
                    "score": selected[0]["trade_side_score"],
                    "probabilities": probabilities,
                    "outcome": member["outcome"],
                    "analysis_at": member["analysis_at"],
                    "evaluation_expires_at": member.get("evaluation_expires_at"),
                })
            if eligible:
                episodes.append(eligible)
        episodes.sort(key=lambda members: min(_utc_epoch(row["analysis_at"]) for row in members))
        cutoff = int(len(episodes) * 0.6)
        train_candidates, test = episodes[:cutoff], episodes[cutoff:]
        test_start = min((_utc_epoch(row["analysis_at"]) for members in test for row in members), default=None)
        train = [members for members in train_candidates
                 if test_start is not None and all(
                     row.get("evaluation_expires_at") is not None
                     and _utc_epoch(row["evaluation_expires_at"]) < test_start for row in members)]
        train_classes = {row["outcome"] for members in train for row in members}
        test_classes = {row["outcome"] for members in test for row in members}
        item = {
            "symbol": symbol, "time_horizon": horizon, "rule_id": rule,
            "formula_role": role, "episodes": len(episodes),
            "train_episodes": len(train), "test_episodes": len(test),
            "purged_training_episodes": len(train_candidates)-len(train),
            "purge_policy": "whole_episode_training_expiry_before_first_test_analysis",
            "baseline_brier": None, "candidate_brier": None,
            "brier_improvement": None, "candidate_coefficient": None,
            "production_effect": "none",
        }
        if len(train) < 20 or len(test) < 10:
            item["status"] = "insufficient_independent_episodes"
        elif len({row["score"] for members in train for row in members}) < 2:
            item["status"] = "no_training_score_variation"
        elif train_classes != set(OUTCOMES) or test_classes != set(OUTCOMES):
            item["status"] = "incomplete_three_class_outcomes"
        else:
            candidate = min(TILT_GRID, key=lambda coefficient: (_episode_loss(train, coefficient), abs(coefficient)))
            baseline_loss, candidate_loss = _episode_loss(test, 0.0), _episode_loss(test, candidate)
            item.update({
                "baseline_brier": round(baseline_loss, 6),
                "candidate_brier": round(candidate_loss, 6),
                "brier_improvement": round(baseline_loss - candidate_loss, 6),
                "candidate_coefficient": candidate,
                "status": "out_of_sample_screening_only_not_validated",
            })
        results.append(item)
    return results


def current_engine_summary(cases: list[dict], *, compact_measurements: bool = False) -> dict:
    by_formula: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    by_episode: dict[tuple, list[dict]] = defaultdict(list)
    per_case = []
    for case in cases:
        scores = score_compact_measurements(case) if compact_measurements else score_current_trace_case(case)
        plan_result = str(case.get("plan_result") or "")
        outcome, outcome_status = fixed_horizon_outcome_from_evidence(
            recorded_outcome=PLAN_RESULT_TO_OUTCOME.get(plan_result),
            plan_result=plan_result, analysis_at=case["analysis_at"],
            evaluation_expires_at=case.get("evaluation_expires_at"),
            closed_at=case.get("closed_at"),
            evidence_status=case.get("evidence_status"),
            evidence_quality=case.get("evidence_quality"),
            evidence_coverage_ratio=case.get("evidence_coverage_ratio"),
            evidence_start_at=case.get("evidence_start_at"),
            evidence_end_at=case.get("evidence_end_at"),
            first_plan_touch_at=case.get("first_plan_touch_at"),
            reconstructed_plan_result=case.get("reconstructed_plan_result"),
            exact_outcome=case.get("exact_outcome_label"),
        )
        if case.get("source_kind") == "operation_observation_checkpoint" and not case.get("exact_outcome_label"):
            outcome, outcome_status = None, "checkpoint_exact_counterfactual_missing"
        episode = case.get("episode_key") or prospective_episode_key(
            symbol=case["symbol"], time_horizon=case["time_horizon"], analysis_at=case["analysis_at"])
        bullish = sum(item["directional_score"] > 0 for item in scores
                      if item["directional_score"] is not None)
        bearish = sum(item["directional_score"] < 0 for item in scores
                      if item["directional_score"] is not None)
        per_case.append({
            "operation_id": case["operation_id"], "symbol": case["symbol"],
            "time_horizon": case["time_horizon"],
            "engine_version": case.get("engine_version", ENGINE_VERSION),
            "outcome": outcome,
            "fixed_horizon_outcome_status": outcome_status,
            "bullish_rules": bullish, "bearish_rules": bearish,
            "conflicting_signals": bool(bullish and bearish), "scores": scores,
        })
        by_episode[(case["symbol"], case["time_horizon"], episode)].append(
            {"scores": scores, "outcome": outcome, "side": case["side"],
             "analysis_at": case["analysis_at"],
             "evaluation_expires_at": case.get("evaluation_expires_at"),
             "probabilities": {
                 OUTCOMES[0]: _finite(case.get("tp_probability")),
                 OUTCOMES[1]: _finite(case.get("sl_probability")),
                 OUTCOMES[2]: _finite(case.get("range_probability")),
             }})
        for item in scores:
            key = (case["symbol"], case["time_horizon"], item["rule_id"], item["formula_role"])
            by_formula[key][episode].append({**item, "outcome": outcome})
    summaries = []
    for (symbol, horizon, rule, role), episodes in sorted(by_formula.items()):
        scored = [member for members in episodes.values() for member in members]
        inputs = defaultdict(list)
        for member in scored:
            for name, value in (member.get("measurement_inputs") or {}).items():
                if value is not None:
                    inputs[name].append(value)
        bands: dict[str, list[dict]] = defaultdict(list)
        for members in episodes.values():
            labeled = [member for member in members if member["outcome"] in OUTCOME_CLASSES]
            if not labeled:
                continue
            directional = [member["trade_side_score"] for member in labeled
                           if member["trade_side_score"] is not None]
            contextual = [member["context_score"] for member in labeled
                          if member["context_score"] is not None]
            values = directional or contextual
            if not values:
                continue
            mean_score = math.fsum(values) / len(values)
            band = "strong_positive" if mean_score >= 3 else "strong_negative" if mean_score <= -3 else "middle"
            bands[band].append({label: sum(row["outcome"] == label for row in labeled) / len(labeled)
                                for label in OUTCOME_CLASSES})
        outcome_bands = {
            band: {
                "episodes": len(bands[band]),
                **{label: round(math.fsum(row[label] for row in bands[band]) / len(bands[band]), 4)
                   if bands[band] else None for label in OUTCOME_CLASSES},
            }
            for band in ("strong_negative", "middle", "strong_positive")
        }
        summaries.append({
            "symbol": symbol, "time_horizon": horizon, "rule_id": rule, "formula_role": role,
            "independent_episodes": len(episodes), "raw_cases": len(scored),
            "directional_available": sum(row["directional_score"] is not None for row in scored),
            "context_available": sum(row["context_score"] is not None for row in scored),
            "missing": sum(row["status"] in {"context_missing", "missing_or_unsupported_formula"} for row in scored),
            "tp_cases": sum(row["outcome"] == "tp_first_within_horizon" for row in scored),
            "sl_cases": sum(row["outcome"] == "sl_first_within_horizon" for row in scored),
            "neither_cases": sum(row["outcome"] == "neither_barrier_before_expiry" for row in scored),
            "score_kind": CONTEXT_RULES.get(rule, "directional_hypothesis"
                if rule in SIGNAL_UNIT_THRESHOLDS else "unsupported_formula_contract"),
            "integer_zero_readings": sum(row["trade_side_score"] == 0 for row in scored),
            "raw_value_range": [min(raw_values), max(raw_values)] if (
                raw_values := [row["raw_support_value"] for row in scored if row["raw_support_value"] is not None]
            ) else None,
            "zero_score_causes": dict(Counter(
                (row.get("score_diagnostics") or {}).get("zero_cause")
                for row in scored if (row.get("score_diagnostics") or {}).get("zero_cause"))),
            "numeric_input_summary": {name:{"readings":len(values),"min":min(values),"max":max(values),
                "mean":math.fsum(values)/len(values)} for name,values in sorted(inputs.items())},
            "outcome_by_score_band": outcome_bands,
            "conclusion": "descriptive_only_no_probability_effect",
        })
    pair_results = []
    for left, right in PREDECLARED_PAIRS:
        states: dict[tuple, list[float]] = defaultdict(list)
        for (symbol, horizon, _), members in by_episode.items():
            aligned_by_contract = defaultdict(list)
            for member in members:
                scores = {}
                duplicate_rules = set()
                for row in member["scores"]:
                    if row["directional_score"] is None:
                        continue
                    if row["rule_id"] in scores:
                        duplicate_rules.add(row["rule_id"])
                    scores[row["rule_id"]] = row
                if left in duplicate_rules or right in duplicate_rules:
                    continue
                a_row, b_row = scores.get(left), scores.get(right)
                if a_row is None or b_row is None or member["outcome"] not in OUTCOME_CLASSES:
                    continue
                a, b = a_row["directional_score"],b_row["directional_score"]
                state = "both_bullish" if a >= 3 and b >= 3 else \
                    "both_bearish" if a <= -3 and b <= -3 else \
                    "mixed_or_weak"
                aligned_by_contract[(a_row["formula_role"],b_row["formula_role"],member["side"])].append(
                    (state,member["outcome"]))
            for (a_role,b_role,side), aligned in aligned_by_contract.items():
                unique_states = {row[0] for row in aligned}
                state = next(iter(unique_states)) if len(unique_states) == 1 else "mixed_or_weak"
                tp_share = sum(row[1] == "tp_first_within_horizon" for row in aligned)/len(aligned)
                states[(symbol,horizon,a_role,b_role,side,state)].append(tp_share)
        for (symbol,horizon,a_role,b_role,side,state), shares in sorted(states.items()):
            pair_results.append({
                "left": left, "right": right, "symbol": symbol,
                "left_formula_role": a_role,"right_formula_role": b_role,"side":side,
                "time_horizon": horizon, "state": state, "episodes": len(shares),
                "tp_episode_share": round(math.fsum(shares) / len(shares), 4),
                "status": "descriptive_not_incremental_validation",
            })
    return {
        "score_version": SCORE_VERSION, "engine_version": ENGINE_VERSION,
        "operations_read": len(cases), "rule_formula_summaries": summaries,
        "predeclared_pair_results": pair_results,
        "incremental_validation": screen_current_incremental(by_episode, summaries),
        "operations": per_case,
        "database_writes": False, "production_effect": "none",
    }


def all_closed_summary(cases: list[dict], *, acquisition: dict | None = None) -> dict:
    """Inspect every closure; never silently limit the audit to modern traces."""
    by_version = defaultdict(list)
    excluded = []
    for case in cases:
        reason = None
        if case.get("recommendation_id") is None:
            reason = "no_linked_pretrade_analysis"
        elif not case.get("traces"):
            reason = "no_preserved_rule_traces"
        elif case.get("time_horizon") not in {"intraday_short", "intraday_wide", "short_swing"}:
            reason = "unsupported_time_contract"
        elif str(case.get("side") or "").lower() not in {"long", "short"}:
            reason = "unsupported_side"
        else:
            try:
                _utc_epoch(case["analysis_at"])
            except (KeyError, ValueError, TypeError):
                reason = "missing_or_invalid_analysis_time"
        if reason:
            excluded.append({"operation_id": case["operation_id"],
                             "engine_version": case.get("engine_version"), "reason": reason})
        else:
            by_version[case.get("engine_version") or "unknown"].append(case)
    version_reports = []
    for version, rows in sorted(by_version.items()):
        report = current_engine_summary(rows)
        report["engine_version"] = version
        report["outcome_quality"] = dict(Counter(
            row["fixed_horizon_outcome_status"] for row in report["operations"]))
        report["outcomes"] = dict(Counter(row["outcome"] or "unverified" for row in report["operations"]))
        version_reports.append(report)
    quality = Counter()
    outcomes = Counter()
    for report in version_reports:
        quality.update(report["outcome_quality"])
        outcomes.update(report["outcomes"])
    return {
        "scope": "all_closed_operations_all_users_all_engine_versions",
        "score_version": SCORE_VERSION, "projection_version": AUDIT_PROJECTION_VERSION,
        "closed_operations_inspected": len(cases),
        "operations_with_preserved_traces_and_time": sum(len(rows) for rows in by_version.values()),
        "operations_with_any_directional_score": sum(
            any(score["directional_score"] is not None for score in operation["scores"])
            for report in version_reports for operation in report["operations"]),
        "excluded_from_rule_evaluation": excluded,
        "exclusion_reasons": dict(Counter(row["reason"] for row in excluded)),
        "outcome_quality": dict(quality), "outcomes": dict(outcomes),
        "version_reports": version_reports, "acquisition": acquisition or {},
        "database_writes": False, "production_effect": "none",
        "limitations": [
            "Scores are unvalidated hypotheses, not measured probability weights.",
            "Missing formulas are not reconstructed from legacy proxy indicators.",
            "Versions and formula roles are evaluated separately; no pooled causal claim.",
            "Scalar projection covers directional/context inputs, not every original formula output.",
        ],
    }


def load_all_closed_cases(db, *, batch_size: int = 50, max_bytes: int = 5_000_000) -> tuple[list[dict], dict]:
    """Keyset-paginated scalar projection in an already read-only transaction."""
    if not 1 <= batch_size <= 200:
        raise ValueError("batch_size_must_be_between_1_and_200")
    inventory = dict(db.execute(
        "SELECT count(*) AS operations,COALESCE(max(id),0) AS max_id FROM operations WHERE status='CLOSED'"
    ).fetchone())
    maximum = int(inventory["max_id"])
    cases, after, batches, payload_bytes = [], 0, 0, 0
    query = """
        WITH page AS (
            SELECT o.id AS operation_id,o.symbol,o.side,o.time_horizon,o.closed_at
            FROM operations o WHERE o.status='CLOSED' AND o.id>? AND o.id<=?
            ORDER BY o.id LIMIT ?
        ), selected AS (
            SELECT page.*,r.id AS recommendation_id,r.engine_version,r.created_at AS recommendation_created_at,
                   r.snapshot_json::jsonb AS s,r.tp_probability,r.sl_probability,r.range_probability
            FROM page LEFT JOIN LATERAL (
                SELECT id,engine_version,created_at,snapshot_json,tp_probability,sl_probability,range_probability
                FROM recommendations WHERE operation_id=page.operation_id AND analysis_type='pre_trade'
                ORDER BY id DESC LIMIT 1
            ) r ON TRUE
        )
        SELECT selected.operation_id,selected.symbol,selected.side,selected.time_horizon,
               selected.closed_at,selected.recommendation_id,selected.engine_version,
               selected.s->>'analysis_at' AS analysis_at,
               selected.s->>'evaluation_expires_at' AS evaluation_expires_at,
               selected.tp_probability,selected.sl_probability,selected.range_probability,
               le.plan_result,le.evidence_status,le.evidence_quality,le.evidence_coverage_ratio,
               le.evidence_start_at,le.evidence_end_at,le.first_plan_touch_at,le.reconstructed_plan_result,
               exact.outcome_label AS exact_outcome_label,
               projected.traces
        FROM selected
        LEFT JOIN LATERAL (
            SELECT plan_result,evidence_status,evidence_quality,evidence_coverage_ratio,
                   evidence_start_at,evidence_end_at,first_plan_touch_at,reconstructed_plan_result
            FROM learning_evaluations WHERE operation_id=selected.operation_id ORDER BY id DESC LIMIT 1
        ) le ON TRUE
        LEFT JOIN LATERAL (
            SELECT outcome_label FROM recommendation_counterfactual_evaluations
            WHERE recommendation_id=selected.recommendation_id AND contract_quality='exact'
              AND formal_learning_eligible AND evaluation_status='evaluated'
            ORDER BY created_at DESC,id DESC LIMIT 1
        ) exact ON TRUE
        LEFT JOIN LATERAL (
            SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
                'rule_id',t.trace->'rule_id','status',t.trace->'status',
                'rule_version',t.trace->'rule_version',
                'measurement_contract_version',t.trace->'measurement_contract_version',
                'reason_codes',t.trace->'reason_codes',
                'probability_effect',t.trace->'probability_effect',
                'formula_role',t.trace->'formula_role',
                'active_probability_outputs',t.trace->'active_probability_outputs',
                'observational_outputs',t.trace->'observational_outputs',
                'outputs',metrics.outputs))) AS traces
            FROM jsonb_array_elements(CASE
                WHEN jsonb_typeof(selected.s->'stage_rule_traces'->selected.time_horizon)='array'
                    THEN selected.s->'stage_rule_traces'->selected.time_horizon
                ELSE COALESCE(selected.s->'m5_rule_trace'->'traces','[]'::jsonb)
                     || COALESCE(selected.s->'feature_snapshot'->'observational_rule_traces'->'traces','[]'::jsonb)
                END) WITH ORDINALITY t(trace,ordinal)
            LEFT JOIN LATERAL (
                SELECT jsonb_object_agg(m.path,m.value) AS outputs FROM (
                    SELECT path,COALESCE(t.trace->'outputs'->path,
                        (t.trace->'outputs') #> string_to_array(path,'.')) AS value
                    FROM jsonb_array_elements_text(?::jsonb) AS keys(path)
                ) m WHERE m.value IS NOT NULL AND jsonb_typeof(m.value) IN ('number','boolean')
            ) metrics ON TRUE
        ) projected ON TRUE
        ORDER BY selected.operation_id
    """
    while after < maximum:
        page = [dict(row) for row in db.execute(
            query, (after, maximum, batch_size, canonical_json(AUDIT_METRIC_PATHS))).fetchall()]
        if not page:
            break
        batches += 1
        payload_bytes += len(canonical_json(page).encode())
        if payload_bytes > max_bytes:
            raise ValueError("all_closed_scalar_transfer_budget_exceeded_no_partial_success")
        cases.extend(page)
        after = int(page[-1]["operation_id"])
    if len(cases) != int(inventory["operations"]) or len({row["operation_id"] for row in cases}) != len(cases):
        raise ValueError("all_closed_coverage_mismatch_no_partial_success")
    return cases, {"database_closed_count": int(inventory["operations"]),
                   "maximum_closed_operation_id": maximum,"batches": batches,
                   "logical_json_bytes_received": payload_bytes,
                   "transfer_budget_bytes": max_bytes, "complete_coverage": True}


def compact_closed_report(report: dict) -> dict:
    """Console digest; full per-symbol/formula report remains available via --json."""
    digest = {key: value for key, value in report.items()
              if key not in {"version_reports", "excluded_from_rule_evaluation"}}
    digest["excluded_operation_ids"] = defaultdict(list)
    for row in report["excluded_from_rule_evaluation"]:
        digest["excluded_operation_ids"][row["reason"]].append(row["operation_id"])
    digest["versions"] = []
    digest["rule_bands"] = []
    digest["joint_patterns"] = []
    digest["band_columns"] = ["episodes","tp_first_share","sl_first_share","neither_share"]
    for version in report["version_reports"]:
        digest["versions"].append({
            "engine_version": version["engine_version"],"operations": version["operations_read"],
            "outcomes": version["outcomes"],"outcome_quality": version["outcome_quality"],
            "incremental_screening_status": dict(Counter(
                row["status"] for row in version["incremental_validation"])),
            "rule_ids": sorted({row["rule_id"] for row in version["rule_formula_summaries"]}),
        })
        aggregate = defaultdict(list)
        for row in version["rule_formula_summaries"]:
            aggregate[(row["time_horizon"],row["rule_id"],row["formula_role"],row["score_kind"])].append(row)
        for (horizon,rule,role,kind), rows in sorted(aggregate.items()):
            item = {"engine_version": version["engine_version"],"horizon": horizon,
                    "rule": rule,"role": role,"kind": kind,
                    "readings": sum(row["raw_cases"] for row in rows),
                    "missing": sum(row["missing"] for row in rows),"bands": {}}
            if item["missing"] == item["readings"]:
                continue
            for band in ("strong_negative","middle","strong_positive"):
                selected = [row["outcome_by_score_band"][band] for row in rows]
                n = sum(row["episodes"] for row in selected)
                item["bands"][band] = [n]+[
                    round(math.fsum(row["episodes"] * (row[label] or 0.0)
                                   for row in selected)/n,4) if n else None
                    for label in OUTCOMES]
            digest["rule_bands"].append(item)
        digest["joint_patterns"].extend(
            {"engine_version": version["engine_version"],**row}
            for row in version["predeclared_pair_results"] if row["state"] != "mixed_or_weak")
    digest["pooled_digest_warning"] = "Bands summarize symbols descriptively; incremental tests remain separated by symbol and version."
    return digest


def load_current_engine_cases(db, *, limit: int) -> list[dict]:
    rows = db.execute(
        """SELECT r.operation_id,r.symbol,r.side,r.time_horizon,
                  r.snapshot_json::jsonb->>'analysis_at' AS analysis_at,
                  r.snapshot_json::jsonb->>'evaluation_expires_at' AS evaluation_expires_at,
                  r.snapshot_json::jsonb->'stage_rule_traces'->r.time_horizon AS traces,
                  o.closed_at,le.plan_result,r.tp_probability,r.sl_probability,
                  r.range_probability,le.evidence_status,le.evidence_quality,
                  le.evidence_coverage_ratio,le.evidence_start_at,le.evidence_end_at,
                  le.first_plan_touch_at,le.reconstructed_plan_result
           FROM recommendations r
           JOIN operations o ON o.id=r.operation_id
           LEFT JOIN learning_evaluations le ON le.operation_id=o.id
           WHERE r.engine_version=? AND r.analysis_type='pre_trade'
             AND r.operation_id IS NOT NULL
           ORDER BY r.id DESC LIMIT ?""",
        (ENGINE_VERSION, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only scoring of the current engine's executed rules")
    parser.add_argument("--limit", type=int, default=100, help="Maximum linked pre-trade traces; max 200")
    parser.add_argument("--operation", type=int, help="Print one operation's rule scores")
    parser.add_argument("--json", action="store_true", help="Print full report, including per-operation scores")
    parser.add_argument("--all-closed", action="store_true", help="Inspect every closed operation across all users and engine versions")
    parser.add_argument("--compact-measurements", action="store_true", help="Evaluate new measurement contracts from compact learning facts, no snapshots")
    parser.add_argument("--batch-size", type=int, default=50, help="All-closed keyset page size; max 200")
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error("--limit must be between 1 and 200")
    if args.all_closed and args.compact_measurements:
        parser.error("--all-closed and --compact-measurements are separate read scopes")
    from db import close_pool, connect
    try:
        with connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            if args.compact_measurements:
                cases, acquisition = load_compact_measurement_cases(db, batch_size=args.batch_size)
            elif args.all_closed:
                cases, acquisition = load_all_closed_cases(db, batch_size=args.batch_size)
            else:
                cases = load_current_engine_cases(db, limit=args.limit)
    finally:
        close_pool()
    if args.compact_measurements:
        report = compact_measurement_report(cases, acquisition=acquisition,
                                            include_cases=args.json or args.operation is not None)
        if args.operation is not None:
            print(canonical_json([{"source_kind":group["source_kind"],**case}
                for group in report["groups"] for case in group["operations"]
                if case["operation_id"] == args.operation]))
        else:
            print(canonical_json(report))
        return
    report = all_closed_summary(cases, acquisition=acquisition) if args.all_closed else current_engine_summary(cases)
    if args.all_closed:
        if args.operation is not None:
            matches = [row for version in report["version_reports"] for row in version["operations"]
                       if row["operation_id"] == args.operation]
            print(canonical_json(matches[0] if matches else next(
                (row for row in report["excluded_from_rule_evaluation"] if row["operation_id"] == args.operation),
                {"status": "not_a_closed_operation_in_audit"})))
        else:
            print(canonical_json(report if args.json else compact_closed_report(report)))
        return
    if args.operation is not None:
        matches = [row for row in report["operations"] if row["operation_id"] == args.operation]
        print(canonical_json(matches[0] if matches else {"status": "operation_not_in_bounded_selection"}))
    elif args.json:
        print(canonical_json(report))
    else:
        print(f"{SCORE_VERSION} | {ENGINE_VERSION} | operations={report['operations_read']} | production_effect=none")
        for row in report["rule_formula_summaries"]:
            print(f"{row['symbol']} {row['time_horizon']} {row['rule_id']} [{row['formula_role']}]: "
                  f"episodes={row['independent_episodes']} directional={row['directional_available']} "
                  f"context={row['context_available']} missing={row['missing']}")


if __name__ == "__main__":
    main()
