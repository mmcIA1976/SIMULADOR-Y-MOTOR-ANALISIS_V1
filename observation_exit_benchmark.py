from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from typing import Any, Iterable

from operation_observation_learning import (
    EXIT_COUNTERFACTUAL_VERSION,
    OBSERVATION_CLOSURE_POLICY_VERSION,
    OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,
    _pnl_at_price,
    observation_checkpoint_view,
    observation_closure_advisory,
    utc_iso,
)
from observational_learning_base import canonical_json, payload_sha256


EXIT_BENCHMARK_CONTRACT_VERSION = "operation-observation-exit-benchmark-v0.1"
EXIT_BENCHMARK_KEY = "lote0-v09-observations-404-429-438-439"
BASELINE_OPERATION_IDS = (404, 429, 438, 439)
EXPECTED_CHECKPOINT_COUNTS = {404: 32, 429: 35, 438: 4, 439: 63}
FORMAL_OPERATION_IDS = (429, 438, 439)
ACTIONABLE_LEVELS = {"protect_candidate", "close_candidate"}

# Filled only after the production source has been repaired and independently
# verified.  Keeping the seal in versioned code detects later source drift
# without copying another dataset into Supabase.
SEALED_DATASET_SHA256 = (
    "c0d90e158da8a102d061e715afd65b8d756570d4c28bfdfd517a760ac6f49ed9"
)
SEALED_METRICS_SHA256 = (
    "12654f8ab2edad0ec0786895bce97196800d4364ef0221c52f3ffe7a23f843ae"
)

OUTCOME_KEYS = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _terminal_outcome(close_reason: Any) -> str:
    reason = str(close_reason or "").strip().lower()
    if reason == "take_profit":
        return OUTCOME_KEYS[0]
    if reason == "stop_loss":
        return OUTCOME_KEYS[1]
    raise ValueError(f"benchmark_terminal_outcome_unsupported:{reason}")


def _geometry_tp_probability(
    *,
    side: str,
    price: float,
    take_profit: float,
    stop_loss: float,
) -> float:
    side = str(side).lower()
    if side == "long":
        if price >= take_profit:
            return 1.0
        if price <= stop_loss:
            return 0.0
    elif side == "short":
        if price <= take_profit:
            return 1.0
        if price >= stop_loss:
            return 0.0
    else:
        raise ValueError(f"benchmark_side_unsupported:{side}")
    target_distance = abs(take_profit - price)
    adverse_distance = abs(price - stop_loss)
    total = target_distance + adverse_distance
    return adverse_distance / total if total > 0.0 else 0.5


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    numerator = math.fsum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    left_variance = math.fsum((value - left_mean) ** 2 for value in left)
    right_variance = math.fsum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_variance * right_variance)
    return numerator / denominator if denominator > 0.0 else None


def probability_metrics(cases: Iterable[dict]) -> dict:
    selected = [case for case in cases if case.get("formal_learning_eligible")]
    if not selected:
        return {
            "cases": 0,
            "multiclass_log_loss": None,
            "multiclass_brier": None,
            "top_class_accuracy": None,
            "tp_geometry_correlation": None,
        }
    log_losses = []
    briers = []
    top_hits = 0
    tp_probabilities = []
    geometry_probabilities = []
    high_tp_wrong = 0
    for case in selected:
        probabilities = case["probabilities"]
        outcome = case["terminal_outcome"]
        true_probability = max(float(probabilities[outcome]), 1e-15)
        log_losses.append(-math.log(true_probability))
        briers.append(
            math.fsum(
                (
                    float(probabilities[key])
                    - (1.0 if key == outcome else 0.0)
                )
                ** 2
                for key in OUTCOME_KEYS
            )
        )
        predicted = max(OUTCOME_KEYS, key=lambda key: probabilities[key])
        top_hits += int(predicted == outcome)
        tp = float(probabilities[OUTCOME_KEYS[0]])
        tp_probabilities.append(tp)
        geometry_probabilities.append(float(case["geometry_tp_probability"]))
        high_tp_wrong += int(tp >= 0.70 and outcome != OUTCOME_KEYS[0])
    count = len(selected)
    return {
        "cases": count,
        "multiclass_log_loss": math.fsum(log_losses) / count,
        "multiclass_brier": math.fsum(briers) / count,
        "top_class_accuracy": top_hits / count,
        "mean_tp_probability": math.fsum(tp_probabilities) / count,
        "tp_geometry_correlation": _pearson(
            tp_probabilities,
            geometry_probabilities,
        ),
        "high_tp_probability_wrong_cases": high_tp_wrong,
    }


def _policy_payload(advisory: dict) -> dict:
    return {
        "policy_version": str(advisory["policy_version"]),
        "level": str(advisory["level"]),
        "current_edge": _finite(advisory.get("current_edge")),
        "edge_change": _finite(advisory.get("edge_change")),
        "model_expected_close_advantage": _finite(
            advisory.get("model_expected_close_advantage")
        ),
        "economic_confirmation_count": int(
            advisory.get("economic_confirmation_count") or 0
        ),
        "adverse_observational_count": int(
            advisory.get("adverse_observational_count") or 0
        ),
        "favorable_observational_count": int(
            advisory.get("favorable_observational_count") or 0
        ),
    }


def _rule_tones(rule_signals: list[dict]) -> list[dict]:
    return sorted(
        [
            {
                "rule_id": str(signal.get("rule_id") or ""),
                "label": str(signal.get("label") or signal.get("rule_id") or ""),
                "tone": str(signal.get("tone") or "neutral"),
            }
            for signal in rule_signals
            if signal.get("category") == "observational"
            and signal.get("rule_id")
        ],
        key=lambda item: item["rule_id"],
    )


def load_observation_source_rows(db) -> list[dict]:
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT checkpoint.*, recommendation.snapshot_json,
                   recommendation.scoring_version,
                   COALESCE(
                       predictive.source_engine_version,
                       recommendation.engine_version
                   ) AS engine_version,
                   predictive.evaluator_version AS predictive_evaluator_version,
                   predictive.analysis_at AS predictive_analysis_at,
                   predictive.data_cutoff_at AS predictive_data_cutoff_at,
                   predictive.evaluation_expires_at,
                   predictive.tp_probability AS canonical_tp_probability,
                   predictive.sl_probability AS canonical_sl_probability,
                   predictive.range_probability AS canonical_range_probability,
                   predictive.source_snapshot_sha256,
                   predictive.result_sha256 AS predictive_result_sha256,
                   exit_eval.evaluator_version AS exit_evaluator_version,
                   exit_eval.actual_final_pnl,
                   exit_eval.pnl_if_closed,
                   exit_eval.time_to_terminal_minutes,
                   exit_eval.evaluation_sha256 AS exit_evaluation_sha256,
                   operation.symbol AS operation_symbol,
                   operation.side AS operation_side,
                   operation.time_horizon AS operation_time_horizon,
                   operation.entry AS operation_entry,
                   operation.take_profit AS operation_take_profit,
                   operation.stop_loss AS operation_stop_loss,
                   operation.margin AS operation_margin,
                   operation.leverage AS operation_leverage,
                   operation.started_at AS operation_started_at,
                   operation.closed_at AS operation_closed_at,
                   operation.close_reason,
                   operation.close_price,
                   operation.final_pnl
            FROM operation_observation_checkpoints checkpoint
            JOIN operation_observation_sessions session
              ON session.id = checkpoint.session_id
            JOIN operations operation ON operation.id = checkpoint.operation_id
            LEFT JOIN recommendations recommendation
              ON recommendation.id = checkpoint.recommendation_id
            LEFT JOIN recommendation_counterfactual_evaluations predictive
              ON predictive.recommendation_id = checkpoint.recommendation_id
             AND predictive.evaluator_version = ?
            LEFT JOIN operation_exit_counterfactuals exit_eval
              ON exit_eval.checkpoint_id = checkpoint.id
             AND exit_eval.evaluator_version = ?
            WHERE checkpoint.operation_id = ANY(?)
              AND operation.status = 'CLOSED'
            ORDER BY checkpoint.operation_id, checkpoint.checkpoint_number
            """,
            (
                OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,
                EXIT_COUNTERFACTUAL_VERSION,
                list(BASELINE_OPERATION_IDS),
            ),
        ).fetchall()
    ]


def _operation_from_row(row: dict) -> dict:
    return {
        "id": int(row["operation_id"]),
        "symbol": str(row["operation_symbol"]),
        "side": str(row["operation_side"]),
        "time_horizon": str(row["operation_time_horizon"]),
        "entry": float(row["operation_entry"]),
        "take_profit": float(row["operation_take_profit"]),
        "stop_loss": float(row["operation_stop_loss"]),
        "margin": float(row["operation_margin"]),
        "leverage": float(row["operation_leverage"]),
        "started_at": str(row["operation_started_at"]),
        "closed_at": str(row["operation_closed_at"]),
        "close_reason": str(row["close_reason"]),
        "close_price": float(row["close_price"]),
        "final_pnl": float(row["final_pnl"]),
    }


def _episode_summary(operation: dict, cases: list[dict]) -> dict:
    actionable = [
        case for case in cases if case["closure_policy"]["level"] in ACTIONABLE_LEVELS
    ]
    first_action = actionable[0] if actionable else None
    best = max(cases, key=lambda case: case["unrealized_pnl"])
    final_pnl = float(operation["final_pnl"])
    policy_pnl = (
        float(first_action["unrealized_pnl"]) if first_action else final_pnl
    )
    best_pnl = float(best["unrealized_pnl"])
    return {
        "operation_id": int(operation["id"]),
        "evidence_tier": (
            "formal_exact"
            if int(operation["id"]) in FORMAL_OPERATION_IDS
            else "diagnostic_reconstructed_partial"
        ),
        "symbol": operation["symbol"],
        "side": operation["side"],
        "time_horizon": operation["time_horizon"],
        "terminal_outcome": _terminal_outcome(operation["close_reason"]),
        "checkpoint_count": len(cases),
        "actual_final_pnl": final_pnl,
        "best_observed_checkpoint": best["checkpoint_code"],
        "best_observed_pnl": best_pnl,
        "first_actionable_checkpoint": (
            first_action["checkpoint_code"] if first_action else None
        ),
        "first_actionable_level": (
            first_action["closure_policy"]["level"] if first_action else None
        ),
        "first_actionable_pnl": (
            float(first_action["unrealized_pnl"]) if first_action else None
        ),
        "first_action_time_to_terminal_minutes": (
            first_action["time_to_terminal_minutes"] if first_action else None
        ),
        "policy_counterfactual_pnl": policy_pnl,
        "policy_improvement_vs_terminal": policy_pnl - final_pnl,
        "profit_capture_ratio": (
            max(0.0, policy_pnl) / best_pnl if best_pnl > 0.0 else None
        ),
        "premature_exit_cost": max(final_pnl - policy_pnl, 0.0),
        "terminal_drawdown_avoided": max(policy_pnl - final_pnl, 0.0),
        "actionable_checkpoint_count": len(actionable),
        "policy_level_counts": dict(
            sorted(Counter(case["closure_policy"]["level"] for case in cases).items())
        ),
    }


def build_observation_exit_baseline(db) -> dict:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in load_observation_source_rows(db):
        grouped[int(row["operation_id"])].append(row)
    actual_counts = {operation_id: len(grouped[operation_id]) for operation_id in BASELINE_OPERATION_IDS}
    if actual_counts != EXPECTED_CHECKPOINT_COUNTS:
        raise RuntimeError(
            "observation_benchmark_checkpoint_count_mismatch:"
            f"{actual_counts}:{EXPECTED_CHECKPOINT_COUNTS}"
        )

    compact_cases = []
    episodes = []
    for operation_id in BASELINE_OPERATION_IDS:
        source_rows = grouped[operation_id]
        operation = _operation_from_row(source_rows[0])
        terminal_pnl = {
            "tp": _pnl_at_price(operation, operation["take_profit"]),
            "sl": _pnl_at_price(operation, operation["stop_loss"]),
        }
        checkpoint_views = []
        operation_cases = []
        expected_number = 1
        previous_number = 0
        for row in source_rows:
            checkpoint_number = int(row["checkpoint_number"])
            if checkpoint_number <= previous_number:
                raise RuntimeError(
                    f"observation_benchmark_sequence_order_invalid:{operation_id}:"
                    f"{checkpoint_number}"
                )
            previous_number = checkpoint_number
            if (
                operation_id in FORMAL_OPERATION_IDS
                and checkpoint_number != expected_number
            ):
                raise RuntimeError(
                    f"observation_benchmark_sequence_gap:{operation_id}:"
                    f"{expected_number}"
                )
            expected_number = checkpoint_number + 1
            exact = bool(row["formal_learning_eligible"])
            if exact and row.get("predictive_evaluator_version") != OBSERVATION_PREDICTIVE_EVALUATOR_VERSION:
                raise RuntimeError(
                    f"observation_benchmark_canonical_prediction_missing:{row['checkpoint_code']}"
                )
            if row.get("exit_evaluator_version") != EXIT_COUNTERFACTUAL_VERSION:
                raise RuntimeError(
                    f"observation_benchmark_exit_evaluation_missing:{row['checkpoint_code']}"
                )
            view = observation_checkpoint_view(row)
            if exact:
                view["tp_probability"] = float(row["canonical_tp_probability"])
                view["sl_probability"] = float(row["canonical_sl_probability"])
                view["range_probability"] = float(row["canonical_range_probability"])
            checkpoint_views.append(view)
            probabilities = {
                OUTCOME_KEYS[0]: _finite(view.get("tp_probability")),
                OUTCOME_KEYS[1]: _finite(view.get("sl_probability")),
                OUTCOME_KEYS[2]: _finite(view.get("range_probability")),
            }
            if exact and any(value is None for value in probabilities.values()):
                raise RuntimeError(
                    f"observation_benchmark_probability_missing:{row['checkpoint_code']}"
                )
            advisory = observation_closure_advisory(
                checkpoint_views,
                terminal_pnl=terminal_pnl,
            )
            case = {
                "checkpoint_id": int(row["id"]),
                "checkpoint_code": str(row["checkpoint_code"]),
                "checkpoint_number": checkpoint_number,
                "operation_id": operation_id,
                "formal_learning_eligible": exact,
                "contract_quality": str(row["contract_quality"]),
                "observed_at": utc_iso(row["observed_at"]),
                "market_price": float(row["market_price"]),
                "unrealized_pnl": float(row["unrealized_pnl"]),
                "remaining_seconds": (
                    int(row["remaining_seconds"])
                    if row.get("remaining_seconds") is not None
                    else None
                ),
                "analysis_horizon_seconds": view.get("analysis_horizon_seconds"),
                "terminal_outcome": _terminal_outcome(operation["close_reason"]),
                "probabilities": probabilities,
                "geometry_tp_probability": _geometry_tp_probability(
                    side=operation["side"],
                    price=float(row["market_price"]),
                    take_profit=operation["take_profit"],
                    stop_loss=operation["stop_loss"],
                ),
                "observational_rule_tones": _rule_tones(view["rule_signals"]),
                "closure_policy": _policy_payload(advisory),
                "time_to_terminal_minutes": _finite(
                    row.get("time_to_terminal_minutes")
                ),
                "source": {
                    "recommendation_id": (
                        int(row["recommendation_id"])
                        if row.get("recommendation_id") is not None
                        else None
                    ),
                    "engine_version": row.get("engine_version"),
                    "scoring_version": row.get("scoring_version"),
                    "predictive_evaluator_version": row.get(
                        "predictive_evaluator_version"
                    ),
                    "predictive_result_sha256": row.get(
                        "predictive_result_sha256"
                    ),
                    "source_snapshot_sha256": row.get(
                        "source_snapshot_sha256"
                    )
                    or row.get("context_sha256"),
                    "exit_evaluator_version": row.get("exit_evaluator_version"),
                    "exit_evaluation_sha256": row.get("exit_evaluation_sha256"),
                },
            }
            case["payload_sha256"] = payload_sha256(case)
            operation_cases.append(case)
            compact_cases.append(case)
        episode = _episode_summary(operation, operation_cases)
        episode["planned_terminal_pnl"] = terminal_pnl
        episodes.append(episode)

    formal_episodes = [
        episode for episode in episodes if episode["evidence_tier"] == "formal_exact"
    ]
    actual_pnl = math.fsum(
        float(episode["actual_final_pnl"]) for episode in formal_episodes
    )
    policy_pnl = math.fsum(
        float(episode["policy_counterfactual_pnl"]) for episode in formal_episodes
    )
    metrics = {
        "probability": probability_metrics(compact_cases),
        "formal_exact_episode_count": len(formal_episodes),
        "diagnostic_episode_count": len(episodes) - len(formal_episodes),
        "formal_actual_terminal_pnl": actual_pnl,
        "formal_policy_counterfactual_pnl": policy_pnl,
        "formal_policy_improvement": policy_pnl - actual_pnl,
    }
    dataset_sha = payload_sha256(
        [case["payload_sha256"] for case in compact_cases]
    )
    metrics_sha = payload_sha256(metrics)
    manifest = {
        "baseline_key": EXIT_BENCHMARK_KEY,
        "contract_version": EXIT_BENCHMARK_CONTRACT_VERSION,
        "operation_ids": list(BASELINE_OPERATION_IDS),
        "formal_operation_ids": list(FORMAL_OPERATION_IDS),
        "canonical_predictive_evaluator_version": (
            OBSERVATION_PREDICTIVE_EVALUATOR_VERSION
        ),
        "exit_evaluator_version": EXIT_COUNTERFACTUAL_VERSION,
        "closure_policy_version": OBSERVATION_CLOSURE_POLICY_VERSION,
        "checkpoint_count": len(compact_cases),
        "formal_checkpoint_count": sum(
            bool(case["formal_learning_eligible"]) for case in compact_cases
        ),
        "dataset_sha256": dataset_sha,
        "metrics_sha256": metrics_sha,
        "storage_policy": "references_existing_immutable_rows_no_database_copy",
    }
    return {
        "manifest": manifest,
        "metrics": metrics,
        "episodes": episodes,
        "cases": compact_cases,
    }


def verify_sealed_baseline(baseline: dict) -> dict:
    manifest = baseline["manifest"]
    errors = []
    if not SEALED_DATASET_SHA256 or not SEALED_METRICS_SHA256:
        errors.append("baseline_not_sealed_in_versioned_code")
    if SEALED_DATASET_SHA256 and manifest["dataset_sha256"] != SEALED_DATASET_SHA256:
        errors.append("dataset_sha256_mismatch")
    if SEALED_METRICS_SHA256 and manifest["metrics_sha256"] != SEALED_METRICS_SHA256:
        errors.append("metrics_sha256_mismatch")
    identity_replay = compare_candidate_replay(
        baseline,
        {
            case["checkpoint_code"]: {
                "probabilities": case["probabilities"],
                "observational_rule_tones": case[
                    "observational_rule_tones"
                ],
            }
            for case in baseline["cases"]
            if case["formal_learning_eligible"]
        },
        candidate_version="v0.9-identity-control",
    )
    nonzero_deltas = {
        key: value
        for key, value in identity_replay[
            "deltas_candidate_minus_baseline"
        ].items()
        if value is not None and abs(float(value)) > 1e-12
    }
    if nonzero_deltas:
        errors.append("identity_probability_replay_mismatch")
    expected_episodes = {
        int(episode["operation_id"]): episode
        for episode in baseline["episodes"]
        if episode["evidence_tier"] == "formal_exact"
    }
    episode_checks = []
    for replayed in identity_replay["episodes"]:
        expected = expected_episodes[int(replayed["operation_id"])]
        fields = (
            "first_actionable_checkpoint",
            "first_actionable_level",
            "first_actionable_pnl",
            "policy_counterfactual_pnl",
        )
        matches = all(replayed[field] == expected[field] for field in fields)
        episode_checks.append(
            {
                "operation_id": int(replayed["operation_id"]),
                "matches": matches,
            }
        )
        if not matches:
            errors.append(
                f"identity_exit_replay_mismatch:{replayed['operation_id']}"
            )
    return {
        "verified": not errors,
        "errors": errors,
        "dataset_sha256": manifest["dataset_sha256"],
        "metrics_sha256": manifest["metrics_sha256"],
        "identity_replay": {
            "probability_deltas": identity_replay[
                "deltas_candidate_minus_baseline"
            ],
            "episode_checks": episode_checks,
        },
    }


def compare_candidate_replay(
    baseline: dict,
    candidate_by_checkpoint: dict[str, dict],
    *,
    candidate_version: str,
) -> dict:
    """Compare a future engine on the same exact checkpoints and exit policy."""
    formal = [
        case for case in baseline["cases"] if case["formal_learning_eligible"]
    ]
    expected_codes = {case["checkpoint_code"] for case in formal}
    supplied_codes = set(candidate_by_checkpoint)
    if supplied_codes != expected_codes:
        raise ValueError(
            "candidate_checkpoint_coverage_mismatch:"
            f"missing={sorted(expected_codes - supplied_codes)}:"
            f"unexpected={sorted(supplied_codes - expected_codes)}"
        )
    candidate_cases = []
    grouped: dict[int, list[dict]] = defaultdict(list)
    for original in formal:
        candidate = candidate_by_checkpoint[original["checkpoint_code"]]
        probabilities = {
            key: float(candidate["probabilities"][key]) for key in OUTCOME_KEYS
        }
        if abs(math.fsum(probabilities.values()) - 1.0) > 1.1e-6:
            raise ValueError(
                f"candidate_probability_mass_invalid:{original['checkpoint_code']}"
            )
        replay = {
            **original,
            "probabilities": probabilities,
            "observational_rule_tones": candidate.get(
                "observational_rule_tones",
                original["observational_rule_tones"],
            ),
        }
        grouped[int(replay["operation_id"])].append(replay)

    candidate_episodes = []
    for operation_id in FORMAL_OPERATION_IDS:
        cases = sorted(
            grouped[operation_id], key=lambda case: case["checkpoint_number"]
        )
        source_episode = next(
            episode
            for episode in baseline["episodes"]
            if int(episode["operation_id"]) == operation_id
        )
        actual_final_pnl = float(source_episode["actual_final_pnl"])
        views = []
        for case in cases:
            signals = [
                {
                    **tone,
                    "category": "observational",
                }
                for tone in case["observational_rule_tones"]
            ]
            views.append(
                {
                    "checkpoint_code": case["checkpoint_code"],
                    "tp_probability": case["probabilities"][OUTCOME_KEYS[0]],
                    "sl_probability": case["probabilities"][OUTCOME_KEYS[1]],
                    "range_probability": case["probabilities"][OUTCOME_KEYS[2]],
                    "unrealized_pnl": case["unrealized_pnl"],
                    "remaining_seconds": case["remaining_seconds"],
                    "analysis_horizon_seconds": case[
                        "analysis_horizon_seconds"
                    ],
                    "rule_signals": signals,
                }
            )
            terminal_pnl = source_episode["planned_terminal_pnl"]
            advisory = observation_closure_advisory(
                views,
                terminal_pnl={
                    "tp": float(terminal_pnl["tp"]),
                    "sl": float(terminal_pnl["sl"]),
                },
            )
            case["closure_policy"] = _policy_payload(advisory)
            candidate_cases.append(case)
        operation_stub = {
            "id": operation_id,
            "symbol": source_episode["symbol"],
            "side": source_episode["side"],
            "time_horizon": source_episode["time_horizon"],
            "close_reason": (
                "take_profit"
                if source_episode["terminal_outcome"] == OUTCOME_KEYS[0]
                else "stop_loss"
            ),
            "final_pnl": actual_final_pnl,
        }
        candidate_episodes.append(_episode_summary(operation_stub, cases))

    candidate_metrics = probability_metrics(candidate_cases)
    baseline_metrics = baseline["metrics"]["probability"]
    return {
        "candidate_version": str(candidate_version),
        "checkpoint_count": len(candidate_cases),
        "closure_policy_version": OBSERVATION_CLOSURE_POLICY_VERSION,
        "baseline_probability_metrics": baseline_metrics,
        "candidate_probability_metrics": candidate_metrics,
        "deltas_candidate_minus_baseline": {
            key: (
                candidate_metrics[key] - baseline_metrics[key]
                if candidate_metrics.get(key) is not None
                and baseline_metrics.get(key) is not None
                else None
            )
            for key in (
                "multiclass_log_loss",
                "multiclass_brier",
                "top_class_accuracy",
                "tp_geometry_correlation",
            )
        },
        "episodes": candidate_episodes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verifica el banco compacto de cierres observacionales del Lote 0."
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Incluye los controles compactos; por defecto sólo imprime el resumen.",
    )
    return parser.parse_args()


def main() -> None:
    from db import close_pool, connect

    args = parse_args()
    try:
        with connect() as db:
            baseline = build_observation_exit_baseline(db)
        output = baseline if args.full else {
            "manifest": baseline["manifest"],
            "verification": verify_sealed_baseline(baseline),
            "metrics": baseline["metrics"],
            "episodes": baseline["episodes"],
        }
        print(canonical_json(output), flush=True)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
