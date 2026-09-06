from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from versioning import ENGINE_VERSION, LEARNING_EVALUATOR_VERSION


EVALUATOR_VERSION = "observational-shadow-calibration-v0.1"
PROSPECTIVE_COHORT_START_AT = "2026-09-07T00:00:00+00:00"
EMA_RULE_ID = "LIB-CAND-EMA-TREND-001"
EMA_SIGNAL_VERSION = "ema-direction-votes-v0.1"
EMA_CANDIDATE_LOG_ODDS_WEIGHTS = (0.0, 0.10, 0.20, 0.35, 0.50)
TRACE_EVALUATED_STATUSES = {
    "evaluated",
    "evaluated_shadow",
    "evaluated_observation_reconstructed",
}
OUTCOME_CLASS = {
    "plan_success": "tp",
    "plan_would_succeed": "tp",
    "plan_failure": "sl",
    "plan_would_fail": "sl",
    "plan_unresolved": "range",
    "contest_expiry_mark_to_market": "range",
}
PROBABILITY_CLASSES = ("tp", "sl", "range")
HORIZONS = ("intraday_short", "intraday_wide", "short_swing")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _probability_map(row: dict) -> dict[str, float] | None:
    values = {
        "tp": _finite(row.get("tp_probability")),
        "sl": _finite(row.get("sl_probability")),
        "range": _finite(row.get("range_probability")),
    }
    if any(value is None or value < 0.0 for value in values.values()):
        return None
    total = math.fsum(values.values())
    if total <= 0.0:
        return None
    return {name: float(value) / total for name, value in values.items()}


def _observational_rules(row: dict) -> dict:
    structured = _parse_json_object(row.get("structured_json"))
    context = structured.get("analysis_context")
    context = context if isinstance(context, dict) else {}
    predictive = context.get("predictive_rules")
    predictive = predictive if isinstance(predictive, dict) else {}
    rules = predictive.get("observational_rules")
    return rules if isinstance(rules, dict) else {}


def _selected_trace(rule: dict, time_horizon: str) -> dict | None:
    traces = rule.get("stage_traces")
    if not isinstance(traces, list):
        return None
    evaluated = [
        trace
        for trace in traces
        if isinstance(trace, dict)
        and trace.get("status") in TRACE_EVALUATED_STATUSES
    ]
    exact = [
        trace
        for trace in evaluated
        if trace.get("time_horizon") == time_horizon
    ]
    return exact[-1] if exact else None


def ema_alignment_signal(row: dict) -> dict | None:
    rule = _observational_rules(row).get(EMA_RULE_ID)
    if not isinstance(rule, dict):
        return None
    trace = _selected_trace(rule, str(row.get("time_horizon") or ""))
    if trace is None:
        return None
    outputs = trace.get("outputs")
    outputs = outputs if isinstance(outputs, dict) else {}
    component_names = (
        "side_adjusted_close_vs_ema50_log",
        "side_adjusted_ema50_vs_ema200_log",
        "side_adjusted_slope_atr",
    )
    components = {name: _finite(outputs.get(name)) for name in component_names}
    if any(value is None for value in components.values()):
        return None

    def direction(value: float) -> int:
        return 1 if value > 0.0 else -1 if value < 0.0 else 0

    votes = {name: direction(float(value)) for name, value in components.items()}
    score = math.fsum(votes.values()) / len(votes)
    state = (
        "fully_aligned"
        if score == 1.0
        else "fully_opposed"
        if score == -1.0
        else "mixed"
    )
    return {
        "version": EMA_SIGNAL_VERSION,
        "score": score,
        "state": state,
        "components": components,
        "votes": votes,
        "source_trace_sha256": trace.get("trace_sha256"),
    }


def apply_conditional_tp_sl_weight(
    probabilities: dict[str, float],
    *,
    signal: float,
    log_odds_weight: float,
) -> dict[str, float]:
    """Move probability only between TP and SL; keep range unchanged."""
    base = {name: float(probabilities[name]) for name in PROBABILITY_CLASSES}
    total = math.fsum(base.values())
    if abs(total - 1.0) > 1e-8 or any(value < 0.0 for value in base.values()):
        raise ValueError("invalid_probability_map")
    resolution = base["tp"] + base["sl"]
    if resolution <= 0.0 or not math.isfinite(float(signal)):
        return dict(base)
    clipped_signal = max(-1.0, min(1.0, float(signal)))
    if float(log_odds_weight) == 0.0 or clipped_signal == 0.0:
        return dict(base)
    conditional_tp = min(
        1.0 - 1e-12,
        max(1e-12, base["tp"] / resolution),
    )
    logit = math.log(conditional_tp / (1.0 - conditional_tp))
    adjusted_conditional_tp = 1.0 / (
        1.0 + math.exp(-(logit + float(log_odds_weight) * clipped_signal))
    )
    result = {
        "tp": resolution * adjusted_conditional_tp,
        "sl": resolution * (1.0 - adjusted_conditional_tp),
        "range": base["range"],
    }
    result["range"] += 1.0 - math.fsum(result.values())
    return result


def _calibration_error(
    outcomes_and_probabilities: list[tuple[str, dict[str, float]]],
    *,
    bins: int = 10,
) -> float | None:
    if not outcomes_and_probabilities:
        return None
    per_class = []
    for class_name in PROBABILITY_CLASSES:
        error = 0.0
        for bucket in range(bins):
            low = bucket / bins
            high = (bucket + 1) / bins
            selected = [
                (outcome, probabilities[class_name])
                for outcome, probabilities in outcomes_and_probabilities
                if low <= probabilities[class_name] < high
                or (bucket == bins - 1 and probabilities[class_name] == 1.0)
            ]
            if not selected:
                continue
            mean_probability = math.fsum(value for _, value in selected) / len(
                selected
            )
            observed_rate = sum(
                outcome == class_name for outcome, _ in selected
            ) / len(selected)
            error += (
                len(selected)
                / len(outcomes_and_probabilities)
                * abs(mean_probability - observed_rate)
            )
        per_class.append(error)
    return math.fsum(per_class) / len(per_class)


def probability_metrics(
    cases: list[dict],
    probability_loader: Callable[[dict], dict[str, float]],
) -> dict:
    evaluated = []
    for case in cases:
        probabilities = probability_loader(case)
        if not isinstance(probabilities, dict):
            continue
        outcome = case["outcome"]
        evaluated.append((outcome, probabilities))
    if not evaluated:
        return {
            "cases": 0,
            "outcomes": {},
            "log_loss": None,
            "multiclass_brier": None,
            "top_class_accuracy": None,
            "calibration_error": None,
            "resolved_binary_log_loss": None,
            "resolved_binary_brier": None,
        }
    count = len(evaluated)
    log_loss = -math.fsum(
        math.log(max(probabilities[outcome], 1e-15))
        for outcome, probabilities in evaluated
    ) / count
    brier = math.fsum(
        math.fsum(
            (
                probabilities[class_name]
                - (1.0 if outcome == class_name else 0.0)
            )
            ** 2
            for class_name in PROBABILITY_CLASSES
        )
        for outcome, probabilities in evaluated
    ) / count
    accuracy = sum(
        max(probabilities, key=probabilities.get) == outcome
        for outcome, probabilities in evaluated
    ) / count
    resolved = [
        (outcome, probabilities)
        for outcome, probabilities in evaluated
        if outcome in {"tp", "sl"}
        and probabilities["tp"] + probabilities["sl"] > 0.0
    ]
    if resolved:
        conditional = [
            (
                outcome,
                probabilities["tp"]
                / (probabilities["tp"] + probabilities["sl"]),
            )
            for outcome, probabilities in resolved
        ]
        binary_log_loss = -math.fsum(
            math.log(max(q_tp if outcome == "tp" else 1.0 - q_tp, 1e-15))
            for outcome, q_tp in conditional
        ) / len(conditional)
        binary_brier = math.fsum(
            (q_tp - (1.0 if outcome == "tp" else 0.0)) ** 2
            for outcome, q_tp in conditional
        ) / len(conditional)
    else:
        binary_log_loss = binary_brier = None
    return {
        "cases": count,
        "outcomes": dict(Counter(outcome for outcome, _ in evaluated)),
        "log_loss": log_loss,
        "multiclass_brier": brier,
        "top_class_accuracy": accuracy,
        "calibration_error": _calibration_error(evaluated),
        "resolved_binary_log_loss": binary_log_loss,
        "resolved_binary_brier": binary_brier,
    }


def _metric_delta(baseline: dict, candidate: dict) -> dict:
    def improvement(name: str) -> float | None:
        left = baseline.get(name)
        right = candidate.get(name)
        if left is None or right is None:
            return None
        return float(left) - float(right)

    accuracy = None
    if baseline.get("top_class_accuracy") is not None and candidate.get(
        "top_class_accuracy"
    ) is not None:
        accuracy = (
            float(candidate["top_class_accuracy"])
            - float(baseline["top_class_accuracy"])
        )
    return {
        "log_loss_improvement": improvement("log_loss"),
        "brier_improvement": improvement("multiclass_brier"),
        "calibration_error_improvement": improvement("calibration_error"),
        "resolved_binary_log_loss_improvement": improvement(
            "resolved_binary_log_loss"
        ),
        "resolved_binary_brier_improvement": improvement(
            "resolved_binary_brier"
        ),
        "top_class_accuracy_change": accuracy,
    }


def _effect_distribution(cases: list[dict], weight: float) -> dict:
    deltas = []
    aligned = []
    opposed = []
    for case in cases:
        adjusted = apply_conditional_tp_sl_weight(
            case["probabilities"],
            signal=case["signal"]["score"],
            log_odds_weight=weight,
        )
        delta = (adjusted["tp"] - case["probabilities"]["tp"]) * 100.0
        deltas.append(delta)
        if case["signal"]["state"] == "fully_aligned":
            aligned.append(delta)
        elif case["signal"]["state"] == "fully_opposed":
            opposed.append(delta)
    return {
        "mean_absolute_tp_shift_percentage_points": (
            math.fsum(abs(value) for value in deltas) / len(deltas)
            if deltas
            else None
        ),
        "maximum_absolute_tp_shift_percentage_points": (
            max((abs(value) for value in deltas), default=None)
        ),
        "fully_aligned_mean_tp_shift_percentage_points": (
            math.fsum(aligned) / len(aligned) if aligned else None
        ),
        "fully_opposed_mean_tp_shift_percentage_points": (
            math.fsum(opposed) / len(opposed) if opposed else None
        ),
    }


def _candidate_report(cases: list[dict], weight: float) -> dict:
    baseline = probability_metrics(cases, lambda case: case["probabilities"])
    candidate = probability_metrics(
        cases,
        lambda case: apply_conditional_tp_sl_weight(
            case["probabilities"],
            signal=case["signal"]["score"],
            log_odds_weight=weight,
        ),
    )
    by_horizon = {}
    for horizon in HORIZONS:
        selected = [case for case in cases if case["time_horizon"] == horizon]
        horizon_baseline = probability_metrics(
            selected,
            lambda case: case["probabilities"],
        )
        horizon_candidate = probability_metrics(
            selected,
            lambda case: apply_conditional_tp_sl_weight(
                case["probabilities"],
                signal=case["signal"]["score"],
                log_odds_weight=weight,
            ),
        )
        by_horizon[horizon] = {
            "baseline": horizon_baseline,
            "candidate": horizon_candidate,
            "delta_vs_baseline": _metric_delta(
                horizon_baseline,
                horizon_candidate,
            ),
        }
    return {
        "candidate_id": f"{EMA_SIGNAL_VERSION}:logodds:{weight:.2f}",
        "log_odds_weight": weight,
        "baseline": baseline,
        "candidate": candidate,
        "delta_vs_baseline": _metric_delta(baseline, candidate),
        "probability_effect": _effect_distribution(cases, weight),
        "by_horizon": by_horizon,
    }


def _cohort_report(cases: list[dict]) -> dict:
    split = max(1, int(len(cases) * 0.70)) if cases else 0
    early = cases[:split]
    latest = cases[split:]
    state_counts = Counter(case["signal"]["state"] for case in cases)
    state_outcomes: dict[str, Counter] = {}
    for case in cases:
        state_outcomes.setdefault(case["signal"]["state"], Counter())[
            case["outcome"]
        ] += 1
    return {
        "cases": len(cases),
        "outcomes": dict(Counter(case["outcome"] for case in cases)),
        "signal_states": dict(state_counts),
        "signal_state_outcomes": {
            state: dict(outcomes) for state, outcomes in state_outcomes.items()
        },
        "candidates": [
            _candidate_report(cases, weight)
            for weight in EMA_CANDIDATE_LOG_ODDS_WEIGHTS
        ],
        "chronological_stability": {
            "early_70_percent": {
                "cases": len(early),
                "candidates": [
                    _candidate_report(early, weight)
                    for weight in EMA_CANDIDATE_LOG_ODDS_WEIGHTS
                ],
            },
            "latest_30_percent": {
                "cases": len(latest),
                "candidates": [
                    _candidate_report(latest, weight)
                    for weight in EMA_CANDIDATE_LOG_ODDS_WEIGHTS
                ],
            },
        },
    }


def _validation_gate(cases: list[dict]) -> dict:
    outcomes = Counter(case["outcome"] for case in cases)
    by_horizon = Counter(case["time_horizon"] for case in cases)
    sanity_ready = len(cases) >= 30
    weight_review_ready = (
        len(cases) >= 75
        and outcomes["tp"] >= 10
        and outcomes["sl"] >= 10
        and all(by_horizon[horizon] >= 50 for horizon in HORIZONS)
    )
    return {
        "status": (
            "manual_weight_review_ready"
            if weight_review_ready
            else "sanity_review_only"
            if sanity_ready
            else "collecting"
        ),
        "automatic_promotion": False,
        "sanity_review": {
            "minimum_cases": 30,
            "current_cases": len(cases),
            "ready": sanity_ready,
        },
        "manual_weight_review": {
            "minimum_total_cases": 75,
            "minimum_tp": 10,
            "minimum_sl": 10,
            "minimum_cases_per_horizon": 50,
            "current_total_cases": len(cases),
            "current_tp": outcomes["tp"],
            "current_sl": outcomes["sl"],
            "current_cases_per_horizon": {
                horizon: by_horizon[horizon] for horizon in HORIZONS
            },
            "ready": weight_review_ready,
        },
        "decision_policy": (
            "Manual review only. A candidate must improve log-loss, Brier and "
            "calibration prospectively, remain directionally stable by horizon "
            "and show incremental value over the production baseline."
        ),
    }


def _rule_inventory(rows: list[dict]) -> list[dict]:
    inventory: dict[str, Counter] = {}
    for row in rows:
        direct_resolved = row.get("plan_result") in {
            "plan_success",
            "plan_failure",
        }
        for rule_id, rule in _observational_rules(row).items():
            if not isinstance(rule, dict):
                continue
            counter = inventory.setdefault(str(rule_id), Counter())
            counter["present_cases"] += 1
            traces = rule.get("stage_traces")
            traces = traces if isinstance(traces, list) else []
            evaluated = any(
                isinstance(trace, dict)
                and trace.get("status") in TRACE_EVALUATED_STATUSES
                for trace in traces
            )
            counter["evaluated_cases" if evaluated else "blocked_cases"] += 1
            if evaluated and direct_resolved:
                counter["direct_tp_sl_cases"] += 1
    return [
        {"rule_id": rule_id, **dict(counts)}
        for rule_id, counts in sorted(inventory.items())
    ]


def _normalized_cases(rows: list[dict]) -> list[dict]:
    cases = []
    for row in rows:
        outcome = OUTCOME_CLASS.get(str(row.get("plan_result") or ""))
        probabilities = _probability_map(row)
        signal = ema_alignment_signal(row)
        analysis_at = _parse_utc(row.get("analysis_at"))
        if outcome is None or probabilities is None or signal is None or analysis_at is None:
            continue
        cases.append(
            {
                "operation_id": int(row["operation_id"]),
                "analysis_at": analysis_at,
                "time_horizon": str(row.get("time_horizon") or ""),
                "side": str(row.get("side") or ""),
                "symbol": str(row.get("symbol") or ""),
                "outcome": outcome,
                "probabilities": probabilities,
                "signal": signal,
            }
        )
    return sorted(cases, key=lambda case: (case["analysis_at"], case["operation_id"]))


def build_observational_shadow_report_from_rows(
    rows: list[dict],
    *,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(timezone.utc)
    if generated.tzinfo is None or generated.utcoffset() is None:
        generated = generated.replace(tzinfo=timezone.utc)
    cohort_start = _parse_utc(PROSPECTIVE_COHORT_START_AT)
    cases = _normalized_cases(rows)
    discovery = [case for case in cases if case["analysis_at"] < cohort_start]
    prospective = [case for case in cases if case["analysis_at"] >= cohort_start]
    return {
        "evaluator_version": EVALUATOR_VERSION,
        "generated_at": generated.astimezone(timezone.utc).isoformat(),
        "scope": {
            "engine_version": ENGINE_VERSION,
            "learning_evaluator_version": LEARNING_EVALUATOR_VERSION,
            "users": "all",
            "closed_operations_only": True,
        },
        "production_isolation": {
            "production_effect": "none",
            "changes_served_probabilities": False,
            "changes_bot_decisions": False,
            "runs_additional_analysis_engine": False,
            "database_writes": False,
            "raw_market_data_duplicated": False,
            "calculation": "on_demand_from_immutable_learning_evidence",
        },
        "rule_inventory": _rule_inventory(rows),
        "experiments": [
            {
                "experiment_id": "ema-conditional-tp-sl-calibration-v0.1",
                "rule_id": EMA_RULE_ID,
                "signal_version": EMA_SIGNAL_VERSION,
                "status": "prospective_collection",
                "candidate_log_odds_weights": list(
                    EMA_CANDIDATE_LOG_ODDS_WEIGHTS
                ),
                "probability_contract": {
                    "adjusted_mass": "tp_vs_sl_within_existing_resolution_mass",
                    "range_probability": "unchanged",
                    "probability_sum": 1.0,
                },
                "cohorts": {
                    "discovery": {
                        "policy": "analysis_at_before_prospective_start",
                        "report": _cohort_report(discovery),
                    },
                    "prospective": {
                        "starts_at": PROSPECTIVE_COHORT_START_AT,
                        "policy": "frozen_candidates_no_retuning_inside_cohort",
                        "report": _cohort_report(prospective),
                        "validation_gate": _validation_gate(prospective),
                    },
                },
            }
        ],
        "manual_governance": {
            "automatic_rule_promotion": False,
            "automatic_weight_selection": False,
            "automatic_production_update": False,
            "review_required": True,
        },
    }


def build_observational_shadow_report(db) -> dict:
    rows = [
        dict(row)
        for row in db.execute(
            """
            SELECT
                le.operation_id,
                le.plan_result,
                le.time_horizon,
                le.side,
                le.tp_probability,
                le.sl_probability,
                le.range_probability,
                le.structured_json,
                r.symbol,
                r.created_at AS analysis_at
            FROM learning_evaluations le
            JOIN recommendations r ON r.id = le.recommendation_id
            JOIN operations o ON o.id = le.operation_id
            WHERE o.status = 'CLOSED'
              AND r.engine_version = ?
              AND le.learning_evaluator_version = ?
            ORDER BY r.created_at ASC, le.operation_id ASC
            """,
            (ENGINE_VERSION, LEARNING_EVALUATOR_VERSION),
        ).fetchall()
    ]
    return build_observational_shadow_report_from_rows(rows)


__all__ = (
    "EMA_CANDIDATE_LOG_ODDS_WEIGHTS",
    "EMA_RULE_ID",
    "EVALUATOR_VERSION",
    "PROSPECTIVE_COHORT_START_AT",
    "apply_conditional_tp_sl_weight",
    "build_observational_shadow_report",
    "build_observational_shadow_report_from_rows",
    "ema_alignment_signal",
    "probability_metrics",
)
