from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
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
HORIZON_SECONDS = {
    "intraday_short": 4 * 60 * 60,
    "intraday_wide": 24 * 60 * 60,
    "short_swing": 7 * 24 * 60 * 60,
}
MIN_EFFECTIVE_EPISODES = 50
MIN_EFFECTIVE_TP_SL_MASS = 10.0


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


def _parse_utc(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _probabilities_match(
    left: dict,
    right: dict,
    tolerance: float = 1.1e-6,
) -> bool:
    return all(
        abs(float(left[name]) - float(right[name])) <= tolerance
        for name in CLASSES
    )


def _losses(probabilities: dict[str, float], outcome: str) -> tuple[float, float]:
    log_loss = -math.log(max(1e-15, probabilities[outcome]))
    brier = math.fsum(
        (
            probabilities[name]
            - (1.0 if name == outcome else 0.0)
        )
        ** 2
        for name in CLASSES
    )
    return log_loss, brier


def _episode_hash(
    symbol: str,
    horizon: str,
    first_at: datetime,
    last_at: datetime,
    operation_ids: list[int],
) -> str:
    identity = json.dumps(
        {
            "symbol": symbol,
            "time_horizon": horizon,
            "first_analysis_at": first_at.isoformat(),
            "last_expiry_at": last_at.isoformat(),
            "operation_ids": sorted(operation_ids),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _attach_independent_episode_keys(cases: list[dict]) -> list[dict]:
    """Collapse overlapping plans for one symbol/horizon into one evidence unit."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    missing_timing = []
    for case in cases:
        analysis_at = _parse_utc(case.get("analysis_at"))
        expiry_at = _parse_utc(case.get("evaluation_expires_at"))
        if analysis_at is None or expiry_at is None or expiry_at <= analysis_at:
            missing_timing.append(case)
            continue
        grouped[(case["symbol"], case["time_horizon"])].append(
            {
                **case,
                "analysis_at": analysis_at,
                "evaluation_expires_at": expiry_at,
            }
        )

    attached = []
    for (symbol, horizon), members in sorted(grouped.items()):
        ordered = sorted(
            members,
            key=lambda item: (
                item["analysis_at"],
                item["evaluation_expires_at"],
                item["operation_id"],
            ),
        )
        component: list[dict] = []
        component_end: datetime | None = None

        def flush() -> None:
            nonlocal component, component_end
            if not component:
                return
            first_at = min(item["analysis_at"] for item in component)
            last_at = max(item["evaluation_expires_at"] for item in component)
            episode_key = _episode_hash(
                symbol,
                horizon,
                first_at,
                last_at,
                [item["operation_id"] for item in component],
            )
            attached.extend(
                {**item, "episode_key": episode_key}
                for item in component
            )
            component = []
            component_end = None

        for item in ordered:
            if component_end is not None and item["analysis_at"] >= component_end:
                flush()
            component.append(item)
            if (
                component_end is None
                or item["evaluation_expires_at"] > component_end
            ):
                component_end = item["evaluation_expires_at"]
        flush()

    attached.extend(
        {
            **case,
            "episode_key": f"operation:{case['operation_id']}",
            "episode_grouping_fallback": "missing_analysis_or_expiry",
        }
        for case in missing_timing
    )
    return attached


def _episode_comparison(
    cases: list[dict],
    *,
    left_key: str,
    right_key: str,
    left_label: str,
    right_label: str,
    delta_label: str,
) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        grouped[str(case["episode_key"])].append(case)
    episodes = []
    for episode_key, members in grouped.items():
        member_metrics = []
        for member in members:
            left_log, left_brier = _losses(member[left_key], member["outcome"])
            right_log, right_brier = _losses(member[right_key], member["outcome"])
            member_metrics.append(
                {
                    "left_log": left_log,
                    "left_brier": left_brier,
                    "right_log": right_log,
                    "right_brier": right_brier,
                }
            )
        size = len(member_metrics)
        outcomes = Counter(member["outcome"] for member in members)
        episodes.append(
            {
                "episode_key": episode_key,
                "raw_cases": size,
                "left_log": math.fsum(
                    item["left_log"] for item in member_metrics
                )
                / size,
                "left_brier": math.fsum(
                    item["left_brier"] for item in member_metrics
                )
                / size,
                "right_log": math.fsum(
                    item["right_log"] for item in member_metrics
                )
                / size,
                "right_brier": math.fsum(
                    item["right_brier"] for item in member_metrics
                )
                / size,
                "outcome_shares": {
                    name: outcomes[name] / size for name in CLASSES
                },
            }
        )

    count = len(episodes)
    if not episodes:
        return {
            "raw_cases": 0,
            "effective_episodes": 0,
            left_label: {"n": 0, "brier_3c": None, "log_loss_3c": None},
            right_label: {"n": 0, "brier_3c": None, "log_loss_3c": None},
            delta_label: {"brier_3c": None, "log_loss_3c": None},
            "effective_outcome_mass": {name: 0.0 for name in CLASSES},
        }

    def mean(key: str) -> float:
        return math.fsum(item[key] for item in episodes) / count

    left = {
        "n": count,
        "brier_3c": mean("left_brier"),
        "log_loss_3c": mean("left_log"),
    }
    right = {
        "n": count,
        "brier_3c": mean("right_brier"),
        "log_loss_3c": mean("right_log"),
    }
    return {
        "raw_cases": len(cases),
        "effective_episodes": count,
        left_label: left,
        right_label: right,
        delta_label: {
            "brier_3c": right["brier_3c"] - left["brier_3c"],
            "log_loss_3c": right["log_loss_3c"] - left["log_loss_3c"],
        },
        "effective_outcome_mass": {
            name: math.fsum(
                item["outcome_shares"][name] for item in episodes
            )
            for name in CLASSES
        },
    }


def _native_rule_ablation(cases: list[dict]) -> dict:
    by_rule_horizon: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for case in cases:
        for rule_id, probabilities in case.get(
            "native_rule_ablations",
            {},
        ).items():
            by_rule_horizon[(rule_id, case["time_horizon"])].append(
                {
                    **case,
                    "without_rule": probabilities,
                }
            )

    results: dict[str, dict] = defaultdict(dict)
    for (rule_id, horizon), members in sorted(by_rule_horizon.items()):
        comparison = _episode_comparison(
            members,
            left_key="champion",
            right_key="without_rule",
            left_label="full_model",
            right_label="without_rule",
            delta_label="without_rule_minus_full",
        )
        mass = comparison["effective_outcome_mass"]
        formal_gate = (
            comparison["effective_episodes"] >= MIN_EFFECTIVE_EPISODES
            and mass[CLASSES[0]] >= MIN_EFFECTIVE_TP_SL_MASS
            and mass[CLASSES[1]] >= MIN_EFFECTIVE_TP_SL_MASS
        )
        comparison.update(
            {
                "formal_gate": formal_gate,
                "evidence_status": (
                    "ready_for_formal_review"
                    if formal_gate
                    else "insufficient_effective_evidence"
                ),
                "additional_effective_episodes_needed": max(
                    0,
                    MIN_EFFECTIVE_EPISODES
                    - comparison["effective_episodes"],
                ),
                "interpretation": (
                    "positive_delta_means_the_rule_improved_the_metric"
                ),
            }
        )
        results[rule_id][horizon] = comparison
    return {
        "source": "stored_m6_probability_trace.fitted_rule_ablation",
        "operation_link_required": True,
        "counterfactual_operations": 0,
        "synthetic_operations": 0,
        "minimum_effective_episodes": MIN_EFFECTIVE_EPISODES,
        "minimum_effective_tp_sl_mass": MIN_EFFECTIVE_TP_SL_MASS,
        "rules": dict(results),
    }


def evaluate_champion_shadow_rows(rows: Iterable[dict]) -> dict:
    exact_cases = []
    shadow_cases = []
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
        if champion is None:
            exclusions["champion_probabilities_invalid"] += 1
            continue
        snapshot = _json_object(row.get("snapshot_json"))
        trace = snapshot.get("m6_probability_trace") or {}
        traced_champion = _probabilities(trace.get("probabilities") or {})
        if (
            traced_champion is not None
            and not _probabilities_match(champion, traced_champion)
        ):
            exclusions["stored_probability_contract_mismatch"] += 1
            continue
        analysis_at = _parse_utc(row.get("analysis_at"))
        horizon = str(row.get("time_horizon") or "")
        evaluation_expires_at = _parse_utc(
            snapshot.get("evaluation_expires_at")
        )
        if (
            evaluation_expires_at is None
            and analysis_at is not None
            and horizon in HORIZON_SECONDS
        ):
            evaluation_expires_at = analysis_at + timedelta(
                seconds=HORIZON_SECONDS[horizon]
            )
        fitted = trace.get("fitted_rule_ablation")
        fitted = fitted if isinstance(fitted, dict) else {}
        native_rule_ablations = {}
        for rule_id, item in fitted.items():
            item = item if isinstance(item, dict) else {}
            without = _probabilities(
                item.get("probabilities_without_rule") or {}
            )
            if without is not None:
                native_rule_ablations[str(rule_id)] = without
        base_case = {
            "operation_id": int(row["operation_id"]),
            "symbol": str(row.get("symbol") or "UNKNOWN").upper(),
            "time_horizon": horizon,
            "analysis_at": analysis_at,
            "evaluation_expires_at": evaluation_expires_at,
            "outcome": outcome,
            "champion": champion,
            "native_rule_ablations": native_rule_ablations,
        }
        exact_cases.append(base_case)
        challenger = _probabilities(
            (trace.get("shadow_challenger") or {}).get(
                "probabilities"
            )
            or {}
        )
        if challenger is None:
            exclusions["shadow_probabilities_missing_or_invalid"] += 1
            continue
        shadow_cases.append({**base_case, "challenger": challenger})

    exact_cases = _attach_independent_episode_keys(exact_cases)
    episode_key_by_operation = {
        case["operation_id"]: case["episode_key"] for case in exact_cases
    }
    shadow_cases = [
        {
            **case,
            "episode_key": episode_key_by_operation[case["operation_id"]],
        }
        for case in shadow_cases
    ]

    by_horizon_cases: dict[str, list[dict]] = defaultdict(list)
    for case in shadow_cases:
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
    overall = _comparison(shadow_cases)
    deltas = overall["challenger_minus_champion"]
    observed_improvement = bool(shadow_cases) and all(
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
            if shadow_cases and overall["champion"][name]
            else None
        )
        for name in ("brier_3c", "log_loss_3c")
    }
    overall_metric_gate = bool(shadow_cases) and all(
        relative_improvement[name]
        >= forward["minimum_relative_improvement"]
        for name in ("brier_3c", "log_loss_3c")
    )
    horizon_regression_gate = bool(shadow_cases) and all(
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
    if not shadow_cases:
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
        "eligible_cases": len(shadow_cases),
        "excluded_cases": sum(exclusions.values()),
        "exclusion_reasons": dict(exclusions),
        "resolved_cases_by_horizon": horizon_counts,
        "overall": overall,
        "by_horizon": {
            horizon: _comparison(by_horizon_cases[horizon])
            for horizon in horizons
        },
        "independent_episode_comparison": _episode_comparison(
            shadow_cases,
            left_key="champion",
            right_key="challenger",
            left_label="champion",
            right_label="challenger",
            delta_label="challenger_minus_champion",
        ),
        "independent_episode_by_horizon": {
            horizon: _episode_comparison(
                by_horizon_cases[horizon],
                left_key="champion",
                right_key="challenger",
                left_label="champion",
                right_label="challenger",
                delta_label="challenger_minus_champion",
            )
            for horizon in horizons
        },
        "native_rule_ablation": _native_rule_ablation(exact_cases),
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
    return evaluate_champion_shadow_rows(
        _select_champion_shadow_rows(db, user_id=user_id)
    )


def build_global_champion_shadow_learning_audit(db) -> dict:
    """Read-only audit across users without exposing user identifiers."""
    return evaluate_champion_shadow_rows(
        _select_champion_shadow_rows(db, user_id=None)
    )


def _select_champion_shadow_rows(db, *, user_id: int | None) -> list[dict]:
    user_filter = "AND o.user_id = ?" if user_id is not None else ""
    params = (
        (ENGINE_VERSION, user_id)
        if user_id is not None
        else (ENGINE_VERSION,)
    )
    return db.execute(
        f"""
        SELECT
            o.id AS operation_id,
            o.symbol,
            o.time_horizon,
            r.created_at AS analysis_at,
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
        JOIN LATERAL (
            SELECT candidate.*
            FROM learning_evaluations candidate
            WHERE candidate.operation_id = o.id
            ORDER BY candidate.updated_at DESC, candidate.id DESC
            LIMIT 1
        ) le ON TRUE
        WHERE o.status = 'CLOSED'
          {user_filter}
          AND COALESCE(o.observation_status, '') != 'OBSERVING'
          AND LEFT(COALESCE(le.evidence_quality, ''), 8) = 'complete'
        ORDER BY o.id
        """,
        params,
    ).fetchall()
