from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from typing import Iterable

from db import row_to_dict
from engine_stability_policy import stability_policy_snapshot
from versioning import ENGINE_VERSION


CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)
TOUCH_CLASS = {
    "take_profit": CLASSES[0],
    "stop_loss": CLASSES[1],
    "no_plan_touch": CLASSES[2],
}


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _probabilities(values: dict) -> dict[str, float] | None:
    try:
        result = {name: float(values[name]) for name in CLASSES}
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(value) or value <= 0 for value in result.values()):
        return None
    total = math.fsum(result.values())
    if abs(total - 1.0) > 1e-9:
        return None
    return result


def _metrics(cases: list[dict], key: str) -> dict:
    if not cases:
        return {"n": 0, "brier_3c": None, "log_loss_3c": None}
    brier = []
    log_loss = []
    for case in cases:
        probabilities = case[key]
        actual = case["outcome"]
        brier.append(
            sum(
                (probabilities[name] - (1.0 if name == actual else 0.0))
                ** 2
                for name in CLASSES
            )
        )
        log_loss.append(-math.log(max(1e-15, probabilities[actual])))
    return {
        "n": len(cases),
        "brier_3c": math.fsum(brier) / len(brier),
        "log_loss_3c": math.fsum(log_loss) / len(log_loss),
    }


def _comparison(cases: list[dict]) -> dict:
    champion = _metrics(cases, "champion")
    challenger = _metrics(cases, "challenger")
    if not cases:
        delta = {"brier_3c": None, "log_loss_3c": None}
    else:
        delta = {
            name: challenger[name] - champion[name]
            for name in ("brier_3c", "log_loss_3c")
        }
    return {
        "champion": champion,
        "challenger": challenger,
        "challenger_minus_champion": delta,
    }


def evaluate_champion_shadow_rows(rows: Iterable[dict]) -> dict:
    cases = []
    exclusions = Counter()
    for raw in rows:
        row = row_to_dict(raw) or {}
        outcome = TOUCH_CLASS.get(str(row.get("first_plan_touch") or ""))
        if outcome is None:
            exclusions["outcome_not_exact_or_ambiguous"] += 1
            continue
        champion = _probabilities(
            {
                CLASSES[0]: row.get("tp_probability"),
                CLASSES[1]: row.get("sl_probability"),
                CLASSES[2]: row.get("range_probability"),
            }
        )
        snapshot = _json_object(row.get("snapshot_json"))
        trace = snapshot.get("m6_probability_trace") or {}
        challenger = _probabilities(
            (trace.get("shadow_challenger") or {}).get(
                "probabilities"
            )
            or {}
        )
        if champion is None:
            exclusions["champion_probabilities_invalid"] += 1
            continue
        if challenger is None:
            exclusions["shadow_probabilities_missing_or_invalid"] += 1
            continue
        cases.append(
            {
                "operation_id": int(row["operation_id"]),
                "time_horizon": str(row["time_horizon"]),
                "outcome": outcome,
                "champion": champion,
                "challenger": challenger,
            }
        )

    by_horizon_cases: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        by_horizon_cases[case["time_horizon"]].append(case)
    policy = stability_policy_snapshot()
    forward = policy["forward_evaluation"]
    horizons = ("intraday_short", "intraday_wide", "short_swing")
    horizon_counts = {
        horizon: len(by_horizon_cases[horizon]) for horizon in horizons
    }
    interim_ready = all(
        count >= forward["interim_resolved_cases_per_horizon"]
        for count in horizon_counts.values()
    )
    promotion_sample_ready = all(
        count >= forward["promotion_review_resolved_cases_per_horizon"]
        for count in horizon_counts.values()
    )
    overall = _comparison(cases)
    deltas = overall["challenger_minus_champion"]
    observed_improvement = bool(cases) and all(
        deltas[name] is not None and deltas[name] < 0
        for name in ("brier_3c", "log_loss_3c")
    )
    relative_improvement = {
        name: (
            (
                overall["champion"][name]
                - overall["challenger"][name]
            )
            / overall["champion"][name]
            if cases and overall["champion"][name]
            else None
        )
        for name in ("brier_3c", "log_loss_3c")
    }
    overall_metric_gate = bool(cases) and all(
        relative_improvement[name]
        >= forward["minimum_relative_improvement"]
        for name in ("brier_3c", "log_loss_3c")
    )
    horizon_regression_gate = bool(cases) and all(
        comparison["champion"][name] is not None
        and comparison["challenger"][name]
        <= comparison["champion"][name]
        * (1.0 + forward["maximum_relative_regression_per_horizon"])
        for comparison in (
            _comparison(by_horizon_cases[horizon])
            for horizon in horizons
        )
        for name in ("brier_3c", "log_loss_3c")
    )
    metric_gates_passed = overall_metric_gate and horizon_regression_gate
    if not cases:
        judgement = "collecting_no_resolved_exact_cases"
    elif not interim_ready:
        judgement = "collecting_below_interim_sample"
    elif observed_improvement:
        judgement = "preliminary_evidence_of_improvement"
    else:
        judgement = "no_observed_improvement_over_champion"
    return {
        "policy": policy,
        "engine_version": ENGINE_VERSION,
        "eligible_cases": len(cases),
        "excluded_cases": sum(exclusions.values()),
        "exclusion_reasons": dict(exclusions),
        "resolved_cases_by_horizon": horizon_counts,
        "overall": overall,
        "by_horizon": {
            horizon: _comparison(by_horizon_cases[horizon])
            for horizon in horizons
        },
        "learning_judgement": judgement,
        "interim_ready": interim_ready,
        "promotion_sample_ready": promotion_sample_ready,
        "observed_improvement_on_both_primary_metrics": (
            observed_improvement
        ),
        "relative_improvement": relative_improvement,
        "overall_metric_gate": overall_metric_gate,
        "horizon_regression_gate": horizon_regression_gate,
        "metric_gates_passed": metric_gates_passed,
        "automatic_promotion": False,
        "next_gate": (
            "owner_review_and_calendar_block_bootstrap"
            if promotion_sample_ready and metric_gates_passed
            else "continue_collecting_without_mutating_champion"
        ),
    }


def build_champion_shadow_learning_audit(db, user_id: int) -> dict:
    rows = db.execute(
        """
        SELECT
            o.id AS operation_id,
            o.time_horizon,
            r.tp_probability,
            r.sl_probability,
            r.range_probability,
            r.snapshot_json,
            le.first_plan_touch
        FROM operations o
        JOIN LATERAL (
            SELECT candidate.*
            FROM recommendations candidate
            WHERE candidate.operation_id = o.id
              AND candidate.engine_version = ?
            ORDER BY candidate.created_at DESC, candidate.id DESC
            LIMIT 1
        ) r ON TRUE
        JOIN learning_evaluations le ON le.operation_id = o.id
        WHERE o.user_id = ?
          AND o.status = 'CLOSED'
          AND COALESCE(o.observation_status, '') != 'OBSERVING'
          AND COALESCE(le.evidence_quality, '') LIKE 'complete%'
        ORDER BY o.id
        """,
        (ENGINE_VERSION, user_id),
    ).fetchall()
    return evaluate_champion_shadow_rows(rows)
