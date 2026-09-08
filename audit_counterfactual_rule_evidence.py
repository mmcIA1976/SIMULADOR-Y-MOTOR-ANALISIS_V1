from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import m8_evaluation as m8
from audit_full_rule_library_closed_operations import (
    MOVEMENT_RULE_IDS,
    flatten_numeric,
    variable_eligibility,
)
from db import close_pool, connect
from predictive_rule_library import load_rule_library


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DEFAULT_OUTPUT = AUDIT_DIR / "counterfactual_rule_evidence_v0_1.json"
DEFAULT_REPORT = (
    AUDIT_DIR / "2026-08-12_counterfactual_rule_evidence.md"
)

AUDIT_VERSION = "counterfactual-rule-evidence-v0.1"
MIN_EFFECTIVE_EPISODES = 50
MIN_EFFECTIVE_CLASS_MASS = 10.0
BOOTSTRAP_SAMPLES = 2000
PERMUTATION_SAMPLES = 2000
RANDOM_SEED = 20260812
FDR_THRESHOLD = 0.10
CLASSES = m8.CLASSES


SQL_SOURCE = """
WITH selected_run AS (
    SELECT id, run_key, grouping_version, source_dataset_sha256
    FROM counterfactual_episode_grouping_runs
    WHERE (?::text IS NULL OR run_key = ?::text)
    ORDER BY id DESC
    LIMIT 1
)
SELECT
    selected_run.id AS grouping_run_id,
    selected_run.run_key AS grouping_run_key,
    selected_run.grouping_version,
    selected_run.source_dataset_sha256,
    membership.membership_sha256,
    membership.calendar_block_utc,
    membership.formal_market_episode_key,
    membership.formal_horizon_episode_key,
    membership.formal_market_weight,
    membership.formal_horizon_weight,
    evaluation.id AS evaluation_id,
    evaluation.recommendation_id,
    evaluation.source_engine_version,
    evaluation.source_scoring_version,
    evaluation.symbol,
    evaluation.side,
    evaluation.time_horizon,
    evaluation.analysis_at,
    evaluation.evaluation_expires_at,
    evaluation.outcome_label,
    evaluation.tp_probability,
    evaluation.sl_probability,
    evaluation.range_probability,
    evaluation.source_snapshot_sha256,
    evaluation.result_sha256,
    recommendation.snapshot_json
FROM selected_run
JOIN counterfactual_episode_memberships membership
  ON membership.run_id = selected_run.id
JOIN recommendation_counterfactual_evaluations evaluation
  ON evaluation.id = membership.evaluation_id
JOIN recommendations recommendation
  ON recommendation.id = evaluation.recommendation_id
WHERE membership.formal_metric_eligible
ORDER BY evaluation.analysis_at, evaluation.id
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audita reglas activas y observadas contra resultados exactos, "
            "ponderando cada episodio de mercado como una observacion."
        )
    )
    parser.add_argument("--grouping-run-key")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalized_probabilities(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    probabilities = {}
    for name in CLASSES:
        number = _finite(value.get(name))
        if number is None or number < 0:
            return None
        probabilities[name] = number
    total = math.fsum(probabilities.values())
    if total <= 0:
        return None
    return {name: value / total for name, value in probabilities.items()}


def _probabilities_match(left: dict, right: dict, tolerance: float = 1.1e-6) -> bool:
    return all(abs(float(left[name]) - float(right[name])) <= tolerance for name in CLASSES)


def _iter_rule_traces(container: Any) -> Iterable[dict]:
    if not isinstance(container, dict):
        return
    for item in container.get("traces") or []:
        if not isinstance(item, dict):
            continue
        if item.get("rule_id"):
            yield item
        yield from _iter_rule_traces(item)


def load_rows(grouping_run_key: str | None = None) -> list[dict]:
    try:
        with connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    SQL_SOURCE,
                    (grouping_run_key, grouping_run_key),
                ).fetchall()
            ]
    finally:
        close_pool()


def normalize_rows(rows: Iterable[dict]) -> list[dict]:
    normalized = []
    run_keys = set()
    evaluation_ids = set()
    for raw in rows:
        row = dict(raw)
        run_keys.add(str(row.get("grouping_run_key") or ""))
        evaluation_id = int(row["evaluation_id"])
        if evaluation_id in evaluation_ids:
            raise ValueError("rule_audit_duplicate_evaluation")
        evaluation_ids.add(evaluation_id)
        analysis_at = m8.parse_utc(row.get("analysis_at"))
        if analysis_at is None:
            raise ValueError("rule_audit_analysis_at_invalid")
        horizon = str(row.get("time_horizon") or "")
        if horizon not in m8.HORIZON_SECONDS:
            raise ValueError("rule_audit_horizon_invalid")
        label = str(row.get("outcome_label") or "")
        if label not in CLASSES:
            raise ValueError("rule_audit_outcome_invalid")
        episode_key = str(row.get("formal_horizon_episode_key") or "")
        if len(episode_key) != 64:
            raise ValueError("rule_audit_episode_key_invalid")
        stored = _normalized_probabilities(
            {
                CLASSES[0]: row.get("tp_probability"),
                CLASSES[1]: row.get("sl_probability"),
                CLASSES[2]: row.get("range_probability"),
            }
        )
        if stored is None:
            raise ValueError("rule_audit_stored_probabilities_invalid")
        snapshot = _json_object(row.get("snapshot_json"))
        if not snapshot:
            raise ValueError("rule_audit_snapshot_invalid")
        normalized.append(
            {
                **row,
                "evaluation_id": evaluation_id,
                "analysis_at": analysis_at,
                "time_horizon": horizon,
                "outcome_label": label,
                "episode_key": episode_key,
                "stored_probabilities": stored,
                "snapshot": snapshot,
            }
        )
    if not normalized:
        raise ValueError("rule_audit_source_empty")
    if len(run_keys) != 1 or "" in run_keys:
        raise ValueError("rule_audit_grouping_run_mismatch")
    return sorted(
        normalized,
        key=lambda row: (row["analysis_at"], row["evaluation_id"]),
    )


def source_identity(rows: list[dict], catalog_sha256: str) -> dict:
    first = rows[0]
    identity = {
        "audit_version": AUDIT_VERSION,
        "grouping_run_key": first["grouping_run_key"],
        "grouping_version": first["grouping_version"],
        "grouping_source_dataset_sha256": first[
            "source_dataset_sha256"
        ],
        "catalog_sha256": catalog_sha256,
        "evaluations": [
            {
                "evaluation_id": row["evaluation_id"],
                "result_sha256": row["result_sha256"],
                "membership_sha256": row["membership_sha256"],
                "source_snapshot_sha256": row[
                    "source_snapshot_sha256"
                ],
            }
            for row in rows
        ],
    }
    identity["source_sha256"] = m8.payload_sha256(identity)
    return identity


def _episode_groups(rows: Iterable[dict]) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["episode_key"]].append(row)
    return sorted(
        grouped.values(),
        key=lambda members: (
            min(row["analysis_at"] for row in members),
            members[0]["episode_key"],
        ),
    )


def _episode_class_mass(rows: Iterable[dict], target: str) -> dict:
    masses = {"positive": 0.0, "negative": 0.0}
    for members in _episode_groups(rows):
        if target == "movement":
            selected = members
            positive = sum(row["outcome_label"] != CLASSES[2] for row in selected)
        else:
            selected = [row for row in members if row["outcome_label"] in CLASSES[:2]]
            positive = sum(row["outcome_label"] == CLASSES[0] for row in selected)
        if not selected:
            continue
        share = positive / len(selected)
        masses["positive"] += share
        masses["negative"] += 1.0 - share
    return masses


def _weighted_probability_metrics(rows: list[dict], probability_key: str) -> dict:
    episodes = _episode_groups(rows)
    if not episodes:
        return {"raw_cases": 0, "effective_episodes": 0}
    log_total = 0.0
    brier_total = 0.0
    outcome_mass = Counter()
    for members in episodes:
        weight = 1.0 / len(members)
        for row in members:
            probabilities = row[probability_key]
            label = row["outcome_label"]
            log_total += weight * -math.log(max(probabilities[label], 1e-15))
            brier_total += weight * math.fsum(
                (
                    probabilities[name]
                    - (1.0 if name == label else 0.0)
                )
                ** 2
                for name in CLASSES
            )
            outcome_mass[label] += weight
    effective = len(episodes)
    return {
        "raw_cases": sum(len(members) for members in episodes),
        "effective_episodes": effective,
        "log_loss": log_total / effective,
        "multiclass_brier": brier_total / effective,
        "effective_outcome_mass": dict(outcome_mass),
    }


def _probability_contract(row: dict, trace: dict) -> dict:
    calibration = trace.get("calibration")
    calibration = calibration if isinstance(calibration, dict) else {}
    overlay = trace.get("active_rule_overlay")
    overlay = overlay if isinstance(overlay, dict) else {}
    contract = {
        "source_engine_version": row["source_engine_version"],
        "source_scoring_version": row.get("source_scoring_version"),
        "candidate_version": trace.get("candidate_version"),
        "coefficient_artifact_id": trace.get("coefficient_artifact_id"),
        "calibration_version": calibration.get("version"),
        "temperature": calibration.get("temperature"),
        "overlay_version": overlay.get("version"),
    }
    contract["contract_key"] = m8.payload_sha256(contract)
    return contract


def extract_ablation_rows(rows: list[dict]) -> tuple[list[dict], Counter]:
    extracted = []
    exclusions: Counter = Counter()
    for row in rows:
        trace = row["snapshot"].get("m6_probability_trace")
        if not isinstance(trace, dict):
            exclusions["m6_probability_trace_missing"] += 1
            continue
        full = _normalized_probabilities(trace.get("probabilities"))
        if full is None:
            exclusions["full_probabilities_missing"] += 1
            continue
        if not _probabilities_match(full, row["stored_probabilities"]):
            exclusions["stored_probability_contract_mismatch"] += 1
            continue
        contract = _probability_contract(row, trace)
        fitted = trace.get("fitted_rule_ablation")
        if isinstance(fitted, dict):
            for rule_id, item in fitted.items():
                item = item if isinstance(item, dict) else {}
                without = _normalized_probabilities(
                    item.get("probabilities_without_rule")
                )
                if without is None:
                    exclusions["fitted_ablation_missing_or_invalid"] += 1
                    continue
                extracted.append(
                    {
                        **row,
                        "rule_id": str(rule_id),
                        "ablation_source": "fitted_rule_ablation",
                        "probability_contract": contract,
                        "full_probabilities": full,
                        "without_probabilities": without,
                    }
                )
        overlay = trace.get("active_rule_overlay")
        if not isinstance(overlay, dict):
            continue
        contributions = overlay.get("rule_contributions")
        contributions = contributions if isinstance(contributions, dict) else {}
        overlay_after = _normalized_probabilities(
            overlay.get("probabilities_after")
        )
        if overlay_after is not None and not _probabilities_match(full, overlay_after):
            exclusions["overlay_full_probability_mismatch"] += 1
            continue
        for rule_id, item in contributions.items():
            item = item if isinstance(item, dict) else {}
            without = _normalized_probabilities(
                item.get("ablation_probabilities_without_rule")
            )
            if without is None:
                exclusions["legacy_overlay_ablation_not_recorded"] += 1
                continue
            extracted.append(
                {
                    **row,
                    "rule_id": str(rule_id),
                    "ablation_source": "active_rule_overlay",
                    "probability_contract": contract,
                    "full_probabilities": full,
                    "without_probabilities": without,
                }
            )
    return extracted, exclusions


def extract_shadow_bundle_rows(rows: list[dict]) -> tuple[list[dict], Counter]:
    extracted = []
    exclusions: Counter = Counter()
    for row in rows:
        trace = row["snapshot"].get("m6_probability_trace")
        if not isinstance(trace, dict):
            continue
        shadow = trace.get("shadow_challenger")
        if not isinstance(shadow, dict):
            continue
        if shadow.get("status") != "evaluated_shadow":
            exclusions[str(shadow.get("block_code") or "shadow_blocked")] += 1
            continue
        champion = _normalized_probabilities(trace.get("probabilities"))
        challenger = _normalized_probabilities(shadow.get("probabilities"))
        if champion is None or challenger is None:
            exclusions["shadow_probabilities_missing_or_invalid"] += 1
            continue
        if not _probabilities_match(champion, row["stored_probabilities"]):
            exclusions["shadow_champion_contract_mismatch"] += 1
            continue
        contract = {
            "champion": _probability_contract(row, trace),
            "shadow_version": shadow.get("version"),
            "shadow_coefficient_artifact_id": shadow.get(
                "coefficient_artifact_id"
            ),
            "shadow_calibration_version": shadow.get("calibration_version"),
            "shadow_temperature": shadow.get("temperature"),
            "active_rule_ids": sorted(shadow.get("active_rule_ids") or []),
        }
        contract["contract_key"] = m8.payload_sha256(contract)
        extracted.append(
            {
                **row,
                "shadow_contract": contract,
                "champion_probabilities": champion,
                "challenger_probabilities": challenger,
            }
        )
    return extracted, exclusions


def summarize_shadow_bundles(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["time_horizon"],
                row["shadow_contract"]["contract_key"],
            )
        ].append(row)
    output = []
    for (horizon, _), members in sorted(grouped.items()):
        champion = _weighted_probability_metrics(
            members, "champion_probabilities"
        )
        challenger = _weighted_probability_metrics(
            members, "challenger_probabilities"
        )
        effective = champion["effective_episodes"]
        masses = _episode_class_mass(members, "directional")
        sufficient = (
            effective >= MIN_EFFECTIVE_EPISODES
            and masses["positive"] >= MIN_EFFECTIVE_CLASS_MASS
            and masses["negative"] >= MIN_EFFECTIVE_CLASS_MASS
        )
        output.append(
            {
                "time_horizon": horizon,
                "shadow_contract": members[0]["shadow_contract"],
                "raw_cases": champion["raw_cases"],
                "effective_episodes": effective,
                "champion": champion,
                "challenger": challenger,
                "delta_challenger_vs_champion": {
                    "log_loss_improvement": (
                        champion["log_loss"] - challenger["log_loss"]
                    ),
                    "brier_improvement": (
                        champion["multiclass_brier"]
                        - challenger["multiclass_brier"]
                    ),
                },
                "governance_status": (
                    "eligible_for_formal_review"
                    if sufficient
                    else "insufficient_effective_independent_evidence"
                ),
                "additional_effective_episodes_needed": max(
                    0, MIN_EFFECTIVE_EPISODES - effective
                ),
                "production_change_authorized": False,
            }
        )
    return output


def summarize_ablations(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (
            row["rule_id"],
            row["ablation_source"],
            row["time_horizon"],
            row["probability_contract"]["contract_key"],
        )
        grouped[key].append(row)
    output = []
    for (rule_id, source, horizon, _), members in sorted(grouped.items()):
        full = _weighted_probability_metrics(members, "full_probabilities")
        without = _weighted_probability_metrics(members, "without_probabilities")
        effective = full["effective_episodes"]
        masses = _episode_class_mass(members, "directional")
        sufficient = (
            effective >= MIN_EFFECTIVE_EPISODES
            and masses["positive"] >= MIN_EFFECTIVE_CLASS_MASS
            and masses["negative"] >= MIN_EFFECTIVE_CLASS_MASS
        )
        output.append(
            {
                "rule_id": rule_id,
                "ablation_source": source,
                "time_horizon": horizon,
                "probability_contract": members[0]["probability_contract"],
                "raw_cases": full["raw_cases"],
                "effective_episodes": effective,
                "effective_tp_mass": masses["positive"],
                "effective_sl_mass": masses["negative"],
                "full": full,
                "without_rule": without,
                "delta_full_minus_without": {
                    "log_loss_improvement": (
                        without["log_loss"] - full["log_loss"]
                    ),
                    "brier_improvement": (
                        without["multiclass_brier"]
                        - full["multiclass_brier"]
                    ),
                },
                "governance_status": (
                    "eligible_for_formal_review"
                    if sufficient
                    else "insufficient_effective_independent_evidence"
                ),
                "additional_effective_episodes_needed": max(
                    0, MIN_EFFECTIVE_EPISODES - effective
                ),
                "production_change_authorized": False,
            }
        )
    return output


def _trace_contract(trace: dict) -> dict:
    contract = {
        "rule_version": trace.get("rule_version"),
        "runtime_version": trace.get("runtime_version"),
        "formula_ids": list(trace.get("formula_ids") or []),
        "probability_effect": trace.get("probability_effect"),
    }
    contract["trace_contract_key"] = m8.payload_sha256(contract)
    return contract


def extract_observational_rows(
    rows: list[dict],
    library_rules: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    traces = []
    coverage = []
    for row in rows:
        feature_snapshot = row["snapshot"].get("feature_snapshot")
        feature_snapshot = feature_snapshot if isinstance(feature_snapshot, dict) else {}
        container = feature_snapshot.get("observational_rule_traces")
        seen: set[str] = set()
        for trace in _iter_rule_traces(container):
            rule_id = str(trace.get("rule_id") or "")
            metadata = library_rules.get(rule_id)
            if not metadata or metadata.get("lifecycle_status") != "implemented_shadow":
                continue
            if rule_id in seen:
                raise ValueError("rule_audit_duplicate_observational_trace")
            seen.add(rule_id)
            status = str(trace.get("status") or "unknown")
            coverage.append(
                {
                    **row,
                    "rule_id": rule_id,
                    "trace_status": status,
                    "trace_contract": _trace_contract(trace),
                }
            )
            if status != "evaluated_shadow":
                continue
            for variable, value in flatten_numeric(trace.get("outputs") or {}).items():
                eligible, reason = variable_eligibility(variable, metadata)
                traces.append(
                    {
                        **row,
                        "rule_id": rule_id,
                        "variable": variable,
                        "value": value,
                        "eligible_for_association": eligible,
                        "eligibility_reason": reason,
                        "trace_contract": _trace_contract(trace),
                    }
                )
    return traces, coverage


def soft_auc(signals: list[float], positive_shares: list[float]) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for left, (left_signal, left_positive) in enumerate(zip(signals, positive_shares)):
        for right, (right_signal, right_positive) in enumerate(zip(signals, positive_shares)):
            if left == right:
                continue
            pair_weight = left_positive * (1.0 - right_positive)
            if pair_weight <= 0:
                continue
            denominator += pair_weight
            if left_signal > right_signal:
                numerator += pair_weight
            elif left_signal == right_signal:
                numerator += 0.5 * pair_weight
    return numerator / denominator if denominator > 0 else None


def _episode_signal_rows(rows: list[dict], target: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if target == "directional" and row["outcome_label"] == CLASSES[2]:
            continue
        grouped[row["episode_key"]].append(row)
    result = []
    for key, members in grouped.items():
        if not members:
            continue
        if target == "movement":
            positive = sum(row["outcome_label"] != CLASSES[2] for row in members)
        else:
            positive = sum(row["outcome_label"] == CLASSES[0] for row in members)
        result.append(
            {
                "episode_key": key,
                "analysis_at": min(row["analysis_at"] for row in members),
                "signal": math.fsum(row["value"] for row in members) / len(members),
                "positive_share": positive / len(members),
                "raw_cases": len(members),
            }
        )
    return sorted(result, key=lambda item: (item["analysis_at"], item["episode_key"]))


def _percentile_interval(values: list[float]) -> list[float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return [
        ordered[int(0.025 * (len(ordered) - 1))],
        ordered[int(0.975 * (len(ordered) - 1))],
    ]


def evaluate_episode_association(
    rows: list[dict],
    *,
    target: str,
    seed: int,
) -> dict:
    episodes = _episode_signal_rows(rows, target)
    signals = [item["signal"] for item in episodes]
    shares = [item["positive_share"] for item in episodes]
    positive_mass = math.fsum(shares)
    negative_mass = len(shares) - positive_mass
    auc = soft_auc(signals, shares) if len(set(signals)) > 1 else None
    split = max(1, int(len(episodes) * 0.7))
    early = soft_auc(signals[:split], shares[:split])
    latest = soft_auc(signals[split:], shares[split:])
    sufficient = (
        len(episodes) >= MIN_EFFECTIVE_EPISODES
        and positive_mass >= MIN_EFFECTIVE_CLASS_MASS
        and negative_mass >= MIN_EFFECTIVE_CLASS_MASS
        and auc is not None
    )
    result = {
        "target": target,
        "raw_cases": sum(item["raw_cases"] for item in episodes),
        "effective_episodes": len(episodes),
        "effective_positive_mass": positive_mass,
        "effective_negative_mass": negative_mass,
        "episode_soft_auc": auc,
        "early_70_percent_auc": early,
        "latest_30_percent_auc": latest,
        "bootstrap_95ci": None,
        "permutation_p": None,
        "fdr_bh": None,
        "evidence_status": "insufficient_effective_independent_evidence",
        "additional_effective_episodes_needed": max(
            0, MIN_EFFECTIVE_EPISODES - len(episodes)
        ),
    }
    if not sufficient:
        return result

    rng = random.Random(seed)
    bootstrap = []
    indices = list(range(len(episodes)))
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [rng.choice(indices) for _ in indices]
        estimate = soft_auc(
            [signals[index] for index in sampled],
            [shares[index] for index in sampled],
        )
        if estimate is not None:
            bootstrap.append(estimate)
    shuffled = list(shares)
    extreme = 0
    target_distance = abs(auc - 0.5)
    for _ in range(PERMUTATION_SAMPLES):
        rng.shuffle(shuffled)
        estimate = soft_auc(signals, shuffled)
        if estimate is not None and abs(estimate - 0.5) >= target_distance:
            extreme += 1
    result.update(
        {
            "bootstrap_95ci": _percentile_interval(bootstrap),
            "permutation_p": (extreme + 1) / (PERMUTATION_SAMPLES + 1),
            "evidence_status": "quantified_pending_fdr",
        }
    )
    return result


def _bh_adjust(metrics: list[dict]) -> None:
    eligible = [item for item in metrics if item.get("permutation_p") is not None]
    ordered = sorted(eligible, key=lambda item: item["permutation_p"])
    running = 1.0
    for index in range(len(ordered) - 1, -1, -1):
        rank = index + 1
        adjusted = min(
            running,
            ordered[index]["permutation_p"] * len(ordered) / rank,
        )
        ordered[index]["fdr_bh"] = adjusted
        running = adjusted


def summarize_observations(
    variable_rows: list[dict],
    coverage_rows: list[dict],
    library_rules: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    coverage_groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in coverage_rows:
        key = (
            row["rule_id"],
            row["time_horizon"],
            row["trace_contract"]["trace_contract_key"],
        )
        coverage_groups[key].append(row)
    coverage = []
    for (rule_id, horizon, _), members in sorted(coverage_groups.items()):
        evaluated = [row for row in members if row["trace_status"] == "evaluated_shadow"]
        coverage.append(
            {
                "rule_id": rule_id,
                "rule_name": library_rules[rule_id]["name"],
                "time_horizon": horizon,
                "trace_contract": members[0]["trace_contract"],
                "traced_cases": len(members),
                "evaluated_cases": len(evaluated),
                "blocked_cases": len(members) - len(evaluated),
                "evaluated_effective_episodes": len(
                    {row["episode_key"] for row in evaluated}
                ),
                "additional_effective_episodes_needed": max(
                    0,
                    MIN_EFFECTIVE_EPISODES
                    - len({row["episode_key"] for row in evaluated}),
                ),
            }
        )

    variable_groups: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in variable_rows:
        if not row["eligible_for_association"]:
            continue
        key = (
            row["rule_id"],
            row["variable"],
            row["time_horizon"],
            row["trace_contract"]["trace_contract_key"],
        )
        variable_groups[key].append(row)
    metrics = []
    for index, ((rule_id, variable, horizon, _), members) in enumerate(sorted(variable_groups.items())):
        target = "movement" if rule_id in MOVEMENT_RULE_IDS else "directional"
        metric = evaluate_episode_association(
            members,
            target=target,
            seed=RANDOM_SEED + index * 17,
        )
        metric.update(
            {
                "rule_id": rule_id,
                "rule_name": library_rules[rule_id]["name"],
                "variable": variable,
                "time_horizon": horizon,
                "trace_contract": members[0]["trace_contract"],
            }
        )
        metrics.append(metric)
    _bh_adjust(metrics)
    for metric in metrics:
        if metric["evidence_status"] != "quantified_pending_fdr":
            continue
        ci = metric["bootstrap_95ci"]
        auc = metric["episode_soft_auc"]
        early = metric["early_70_percent_auc"]
        latest = metric["latest_30_percent_auc"]
        stable = (
            auc is not None
            and early is not None
            and latest is not None
            and (auc - 0.5) * (early - 0.5) > 0
            and (auc - 0.5) * (latest - 0.5) > 0
        )
        significant = (
            metric["fdr_bh"] is not None
            and metric["fdr_bh"] <= FDR_THRESHOLD
            and ci is not None
            and not (ci[0] <= 0.5 <= ci[1])
        )
        if significant and stable:
            metric["evidence_status"] = (
                "historically_supported_not_independent_validation"
                if auc > 0.5
                else "historically_contradicted_not_independent_validation"
            )
        elif auc is not None and abs(auc - 0.5) < 0.05:
            metric["evidence_status"] = "no_clear_episode_separation"
        else:
            metric["evidence_status"] = "inconclusive_or_temporally_unstable"
    metrics_by_slice: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for metric in metrics:
        metrics_by_slice[
            (
                metric["rule_id"],
                metric["time_horizon"],
                metric["trace_contract"]["trace_contract_key"],
            )
        ].append(metric)
    for item in coverage:
        slice_metrics = metrics_by_slice.get(
            (
                item["rule_id"],
                item["time_horizon"],
                item["trace_contract"]["trace_contract_key"],
            ),
            [],
        )
        max_raw = max(
            (metric["raw_cases"] for metric in slice_metrics),
            default=0,
        )
        max_effective = max(
            (metric["effective_episodes"] for metric in slice_metrics),
            default=0,
        )
        item.update(
            {
                "eligible_association_variables": len(slice_metrics),
                "max_variable_raw_cases": max_raw,
                "max_variable_effective_episodes": max_effective,
                "additional_variable_episodes_needed": max(
                    0, MIN_EFFECTIVE_EPISODES - max_effective
                ),
            }
        )
    return coverage, metrics


def _horizon_inventory(rows: list[dict]) -> dict:
    output = {}
    for horizon in m8.HORIZON_SECONDS:
        members = [row for row in rows if row["time_horizon"] == horizon]
        episodes = len({row["episode_key"] for row in members})
        output[horizon] = {
            "raw_cases": len(members),
            "effective_episodes": episodes,
            "raw_outcomes": dict(Counter(row["outcome_label"] for row in members)),
            "effective_directional_class_mass": _episode_class_mass(
                members, "directional"
            ),
            "additional_effective_episodes_needed": max(
                0, MIN_EFFECTIVE_EPISODES - episodes
            ),
            "formal_review_ready": episodes >= MIN_EFFECTIVE_EPISODES,
        }
    return output


def _current_runtime_state(rows: list[dict]) -> dict:
    current_engine = rows[-1]["source_engine_version"]
    current = [
        row for row in rows if row["source_engine_version"] == current_engine
    ]
    fitted_ids = set()
    shadow_ids = set()
    observed_ids = set()
    for row in current:
        trace = row["snapshot"].get("m6_probability_trace")
        trace = trace if isinstance(trace, dict) else {}
        fitted = trace.get("fitted_rule_ablation")
        if isinstance(fitted, dict):
            fitted_ids.update(str(rule_id) for rule_id in fitted)
        shadow = trace.get("shadow_challenger")
        if isinstance(shadow, dict) and shadow.get("status") == "evaluated_shadow":
            shadow_ids.update(str(rule_id) for rule_id in shadow.get("active_rule_ids") or [])
        feature = row["snapshot"].get("feature_snapshot")
        feature = feature if isinstance(feature, dict) else {}
        for item in _iter_rule_traces(feature.get("observational_rule_traces")):
            if item.get("status") == "evaluated_shadow" and item.get("rule_id"):
                observed_ids.add(str(item["rule_id"]))
    return {
        "source_engine_version": current_engine,
        "exact_cases": len(current),
        "effective_horizon_episodes": len(
            {row["episode_key"] for row in current}
        ),
        "by_horizon": {
            horizon: {
                "exact_cases": len(
                    [row for row in current if row["time_horizon"] == horizon]
                ),
                "effective_episodes": len(
                    {
                        row["episode_key"]
                        for row in current
                        if row["time_horizon"] == horizon
                    }
                ),
            }
            for horizon in m8.HORIZON_SECONDS
        },
        "production_fitted_rule_ids": sorted(fitted_ids),
        "shadow_challenger_rule_ids": sorted(shadow_ids),
        "observational_rule_ids": sorted(observed_ids),
    }


def build_report(payload: dict) -> str:
    horizon = payload["dataset"]["by_horizon"]
    coverage = payload["observational_rules"]["coverage"]
    ablations = payload["active_rules"]["ablation_slices"]
    metrics = payload["observational_rules"]["association_metrics"]
    shadow_bundles = payload["current_shadow_challenger"]["comparison_slices"]
    runtime = payload["current_runtime_state"]
    eligible_metrics = [
        item for item in metrics
        if item["evidence_status"] != "insufficient_effective_independent_evidence"
    ]
    lines = [
        "# Evidencia contrafactual de reglas por episodio y horizonte",
        "",
        f"- Version: `{payload['audit_version']}`.",
        f"- Biblioteca: `{payload['library_version']}`.",
        f"- Cohorte: **{payload['dataset']['formal_exact_cases']} casos exactos**.",
        f"- Episodios independientes por horizonte: **{payload['dataset']['effective_horizon_episodes']}**.",
        "- Efecto sobre produccion: **ninguno**.",
        "",
        "## Resultado ejecutivo",
        "",
        (
            "Ninguna regla alcanza todavia los 50 episodios independientes "
            "exigidos por el protocolo. Por tanto, esta ejecucion cuantifica "
            "cobertura y deltas descriptivos, pero no autoriza cambiar pesos, "
            "promocionar reglas ni afirmar validez predictiva."
        ),
        "",
        "| Horizonte | Casos exactos | Episodios efectivos | Faltan para 50 |",
        "|---|---:|---:|---:|",
    ]
    for name, item in horizon.items():
        lines.append(
            f"| `{name}` | {item['raw_cases']} | {item['effective_episodes']} | "
            f"{item['additional_effective_episodes_needed']} |"
        )
    lines.extend(
        [
        "",
        "## Estado del motor actual",
        "",
        f"- Contrato servido: `{runtime['source_engine_version']}`.",
        (
            "- Reglas ajustadas del campeon con ablacion individual: "
            + ", ".join(f"`{item}`" for item in runtime["production_fitted_rule_ids"])
            + "."
        ),
        (
            "- Reglas provisionales del challenger en sombra: "
            + ", ".join(f"`{item}`" for item in runtime["shadow_challenger_rule_ids"])
            + "."
        ),
        (
            f"- Candidatas puramente observacionales: "
            f"**{len(runtime['observational_rule_ids'])}**."
        ),
        (
            "- Cobertura exacta del contrato actual: "
            + ", ".join(
                f"`{horizon}` {item['exact_cases']} casos/"
                f"{item['effective_episodes']} episodios"
                for horizon, item in runtime["by_horizon"].items()
            )
            + "."
        ),
        "",
        "## Reglas activas",
            "",
            (
                "Las ablaciones se mantienen separadas por version completa "
                "del contrato probabilistico. No se mezclan motores antiguos "
                "con el campeon actual."
            ),
            "",
            "| Regla | Horizonte | Contrato | Casos | Episodios | Delta log-loss | Delta Brier | Estado |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in ablations:
        delta = item["delta_full_minus_without"]
        lines.append(
            f"| `{item['rule_id']}` | `{item['time_horizon']}` | "
            f"`{item['probability_contract']['contract_key'][:10]}` | "
            f"{item['raw_cases']} | {item['effective_episodes']} | "
            f"{delta['log_loss_improvement']:+.6f} | "
            f"{delta['brier_improvement']:+.6f} | "
            f"{item['governance_status']} |"
        )
    lines.extend(
        [
            "",
            "## Challenger actual como conjunto",
            "",
            (
                "El snapshot actual permite comparar el paquete completo del "
                "challenger con el campeon, pero no atribuir retrospectivamente "
                "su resultado a cada una de las ocho reglas por separado."
            ),
            "",
            "| Horizonte | Casos | Episodios | Delta log-loss | Delta Brier | Estado |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in shadow_bundles:
        delta = item["delta_challenger_vs_champion"]
        lines.append(
            f"| `{item['time_horizon']}` | {item['raw_cases']} | "
            f"{item['effective_episodes']} | "
            f"{delta['log_loss_improvement']:+.6f} | "
            f"{delta['brier_improvement']:+.6f} | "
            f"{item['governance_status']} |"
        )
    lines.extend(
        [
            "",
            "## Reglas en observacion",
            "",
            (
                "Las trazas se estudian como asociaciones por episodio; no se "
                "les inventa un peso probabilistico retrospectivo."
            ),
            "",
            "| Regla | Horizonte | Trazas/episodios | Variable comparable: casos/episodios | Faltan para 50 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for item in coverage:
        lines.append(
            f"| `{item['rule_id']}` | `{item['time_horizon']}` | "
            f"{item['evaluated_cases']}/{item['evaluated_effective_episodes']} | "
            f"{item['max_variable_raw_cases']}/"
            f"{item['max_variable_effective_episodes']} | "
            f"{item['additional_variable_episodes_needed']} |"
        )
    lines.extend(
        [
            "",
            "## Inferencia",
            "",
            f"- Comparaciones que superan los minimos: **{len(eligible_metrics)}**.",
            f"- Reglas autorizadas para cambiar produccion: **0**.",
            "- Los resultados negativos e insuficientes quedan conservados.",
            "",
            "## Criterio aplicado",
            "",
            (
                "Cada episodio solapado cuenta como una unidad. Para cada "
                "variable se promedia la senal dentro del episodio y se "
                "conserva la proporcion de outcomes positivos. Solo al llegar "
                "a 50 episodios, 10 unidades efectivas positivas y 10 negativas "
                "se ejecutan bootstrap de 2.000 remuestreos, permutacion de "
                "2.000 iteraciones, corte temporal 70/30 y correccion "
                "Benjamini-Hochberg."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def run(rows: list[dict]) -> dict:
    normalized = normalize_rows(rows)
    library = load_rule_library()
    library_rules = {rule["rule_id"]: rule for rule in library["rules"]}
    identity = source_identity(normalized, library["catalog_sha256"])
    ablation_rows, ablation_exclusions = extract_ablation_rows(normalized)
    ablation_summary = summarize_ablations(ablation_rows)
    shadow_rows, shadow_exclusions = extract_shadow_bundle_rows(normalized)
    shadow_summary = summarize_shadow_bundles(shadow_rows)
    observation_rows, coverage_rows = extract_observational_rows(
        normalized,
        library_rules,
    )
    coverage, association_metrics = summarize_observations(
        observation_rows,
        coverage_rows,
        library_rules,
    )
    horizon_inventory = _horizon_inventory(normalized)
    deterministic = {
        "audit_version": AUDIT_VERSION,
        "production_effect": "none",
        "library_version": library["library_version"],
        "catalog_sha256": library["catalog_sha256"],
        "source": identity,
        "protocol": {
            "independent_unit": "overlapping_market_episode_by_symbol_and_horizon",
            "minimum_effective_episodes": MIN_EFFECTIVE_EPISODES,
            "minimum_effective_positive_mass": MIN_EFFECTIVE_CLASS_MASS,
            "minimum_effective_negative_mass": MIN_EFFECTIVE_CLASS_MASS,
            "temporal_split": "earliest_70_percent_vs_latest_30_percent_by_episode",
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "permutation_samples": PERMUTATION_SAMPLES,
            "multiple_testing": "Benjamini-Hochberg",
            "fdr_threshold": FDR_THRESHOLD,
            "automatic_promotion": False,
        },
        "dataset": {
            "formal_exact_cases": len(normalized),
            "effective_horizon_episodes": sum(
                item["effective_episodes"] for item in horizon_inventory.values()
            ),
            "by_horizon": horizon_inventory,
        },
        "current_runtime_state": _current_runtime_state(normalized),
        "active_rules": {
            "ablation_rows": len(ablation_rows),
            "exclusions": dict(sorted(ablation_exclusions.items())),
            "ablation_slices": ablation_summary,
        },
        "current_shadow_challenger": {
            "comparison_rows": len(shadow_rows),
            "exclusions": dict(sorted(shadow_exclusions.items())),
            "comparison_slices": shadow_summary,
        },
        "observational_rules": {
            "coverage": coverage,
            "association_metrics": association_metrics,
        },
        "decision": {
            "formal_rule_evaluations_ready": sum(
                item["evidence_status"]
                != "insufficient_effective_independent_evidence"
                for item in association_metrics
            ),
            "production_rule_changes_authorized": 0,
            "reason": "minimum_independent_episode_count_not_reached",
        },
    }
    deterministic["audit_sha256"] = m8.payload_sha256(deterministic)
    return {
        **deterministic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    args = parse_args()
    rows = load_rows(args.grouping_run_key)
    payload = run(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(build_report(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "audit_version": payload["audit_version"],
                "audit_sha256": payload["audit_sha256"],
                "formal_exact_cases": payload["dataset"]["formal_exact_cases"],
                "effective_horizon_episodes": payload["dataset"][
                    "effective_horizon_episodes"
                ],
                "ablation_slices": len(
                    payload["active_rules"]["ablation_slices"]
                ),
                "observational_coverage_slices": len(
                    payload["observational_rules"]["coverage"]
                ),
                "association_metrics": len(
                    payload["observational_rules"]["association_metrics"]
                ),
                "formal_rule_evaluations_ready": payload["decision"][
                    "formal_rule_evaluations_ready"
                ],
                "output": str(args.output),
                "report": str(args.report),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
