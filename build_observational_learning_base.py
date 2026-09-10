from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from typing import Any

import m8_evaluation as m8
from audit_final_rule_utility import (
    AUDIT_VERSION,
    MIN_EFFECTIVE_CLASS_MASS,
    MIN_EFFECTIVE_EPISODES,
    _episode_signal_rows,
    attach_episode_memberships,
    extract_rule_variables,
    fast_soft_auc,
    horizon_cutoffs,
    load_closed_rows,
    load_database_sources,
    prepare_exact_counterfactuals,
    replay_consolidated_cases,
    use_session_pool_for_long_audit,
)
from audit_full_rule_library_closed_operations import (
    STATE_RECORDED,
    STATE_RECONSTRUCTED,
)
from db import close_pool, connect
from observational_learning_base import (
    BASELINE_COHORT_KEY,
    BASE_CONTRACT_VERSION,
    FROZEN_SIGNAL_VARIABLES,
    HISTORICAL_CUTOFF_AT,
    MOVEMENT_RULE_IDS,
    PROBABILITY_WEIGHT,
    RETAINED_RULE_HORIZONS,
    canonical_json,
    ensure_observational_learning_base_tables,
    payload_sha256,
)
from predictive_rule_library import load_rule_library


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materializa y verifica la base compacta de reglas observacionales "
            "sin crear informes ni modificar el motor de probabilidades."
        )
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def _parse_utc(value: Any) -> datetime | None:
    return m8.parse_utc(value)


def _at_or_before(value: Any, cutoff: datetime) -> bool:
    parsed = _parse_utc(value)
    return parsed is not None and parsed <= cutoff


def _probabilities(case: dict) -> dict[str, float]:
    raw = case.get("stored_probabilities")
    raw = raw if isinstance(raw, dict) else {}
    values = {
        name: float(raw[name])
        for name in m8.CLASSES
        if raw.get(name) is not None and math.isfinite(float(raw[name]))
    }
    total = math.fsum(values.values())
    if len(values) != len(m8.CLASSES) or total <= 0:
        return {}
    return {name: value / total for name, value in values.items()}


def _load_linked_snapshots(cutoff: datetime) -> dict[int, dict]:
    try:
        with connect() as db:
            rows = db.execute(
                """
                SELECT r.id, r.snapshot_json
                FROM recommendations r
                JOIN operations o ON o.id = r.operation_id
                WHERE o.status = 'CLOSED' AND r.created_at <= ?
                """,
                (cutoff.isoformat(),),
            ).fetchall()
        return {
            int(row["id"]): json.loads(row["snapshot_json"])
            for row in rows
            if row.get("snapshot_json")
        }
    finally:
        close_pool()


def _load_observation_sources(cutoff: datetime) -> dict[int, dict]:
    try:
        with connect() as db:
            rows = db.execute(
                """
                SELECT checkpoint.recommendation_id, checkpoint.operation_id,
                       checkpoint.checkpoint_code
                FROM operation_observation_checkpoints checkpoint
                WHERE checkpoint.formal_learning_eligible
                  AND checkpoint.recommendation_id IS NOT NULL
                  AND checkpoint.observed_at <= ?
                """,
                (cutoff.isoformat(),),
            ).fetchall()
        return {
            int(row["recommendation_id"]): {
                "operation_id": int(row["operation_id"]),
                "checkpoint_code": str(row["checkpoint_code"]),
            }
            for row in rows
        }
    finally:
        close_pool()


def _mark_observation_sources(cases: list[dict], sources: dict[int, dict]) -> None:
    for case in cases:
        recommendation_id = case.get("recommendation_id")
        source = sources.get(int(recommendation_id)) if recommendation_id else None
        if source is None:
            continue
        case["source_kind"] = "operation_observation_checkpoint"
        case["observation_operation_id"] = source["operation_id"]
        case["observation_checkpoint_code"] = source["checkpoint_code"]


def _overlay_recorded_stage_traces(cases: list[dict], snapshots: dict[int, dict]) -> None:
    for case in cases:
        recommendation_id = case.get("recommendation_id")
        snapshot = snapshots.get(int(recommendation_id)) if recommendation_id else None
        if not isinstance(snapshot, dict):
            continue
        horizon = str(case["time_horizon"])
        stages = snapshot.get("stage_rule_traces")
        traces = stages.get(horizon) if isinstance(stages, dict) else None
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            rule_id = str(trace.get("rule_id") or "")
            status = str(trace.get("status") or "")
            outputs = trace.get("outputs")
            if (
                rule_id not in RETAINED_RULE_HORIZONS
                or status not in {"evaluated", "evaluated_shadow"}
                or not isinstance(outputs, dict)
                or not outputs
            ):
                continue
            case["rules"][rule_id] = {
                "state": STATE_RECORDED,
                "runtime_status": status,
                "source": "stored_exact_pretrade_stage_trace",
                "reason": None,
                "outputs": outputs,
            }


def _frozen_signal_value(case: dict, rule_id: str) -> float | None:
    item = case["rules"].get(rule_id) or {}
    if item.get("state") not in {STATE_RECORDED, STATE_RECONSTRUCTED}:
        return None
    outputs = item.get("outputs") if isinstance(item.get("outputs"), dict) else {}
    direction = 1.0 if case["side"] == "long" else -1.0
    variable = FROZEN_SIGNAL_VARIABLES[rule_id]
    if not variable.startswith("__"):
        value: Any = outputs
        for part in variable.split("."):
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
    if rule_id == "M4-RULE-AGGRESSOR-IMBALANCE-001":
        raw = outputs.get("ATI_H")
        return direction * float(raw) if raw is not None else None
    if rule_id == "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001":
        target = outputs.get("target_path_level_count")
        adverse = outputs.get("adverse_path_level_count")
        if target is not None and adverse is not None:
            return float(adverse) - float(target)
        return None
    if rule_id == "LIB-CAND-FIBONACCI-DISTANCE-001":
        target = (outputs.get("nearest_to_take_profit") or {}).get(
            "absolute_distance_sigma_horizon"
        )
        stop = (outputs.get("nearest_to_stop_loss") or {}).get(
            "absolute_distance_sigma_horizon"
        )
        if target is None:
            target = outputs.get(
                "nearest_to_take_profit.absolute_distance_sigma_horizon"
            )
        if stop is None:
            stop = outputs.get(
                "nearest_to_stop_loss.absolute_distance_sigma_horizon"
            )
        if target is not None and stop is not None:
            return float(stop) - float(target)
        return None
    if rule_id == "M4-RULE-CONTINUOUS-REGIME-001":
        signed = outputs.get("signed_path_efficiency")
        directional = outputs.get("directional_path_efficiency_h")
        percentile = outputs.get(
            "volatility_percentile",
            outputs.get("volatility_percentile_60"),
        )
        if percentile is None:
            return None
        if directional is not None:
            return float(directional) * (2.0 * float(percentile) - 1.0)
        if signed is not None:
            return direction * float(signed) * (2.0 * float(percentile) - 1.0)
        return None
    if rule_id == "M4-RULE-PRIOR-EXTREMA-001":
        raw = outputs.get("target_extreme_between_entry_and_tp")
        return float(raw) if raw is not None else None
    if rule_id == "M4-RULE-OPEN-INTEREST-CHANGE-001":
        raw = outputs.get("dOI_H", outputs.get("dOI_H_proxy"))
        return math.tanh(50.0 * abs(float(raw))) if raw is not None else None
    if rule_id == "M4-RULE-PRICE-OI-STATE-001":
        displacement = outputs.get("D_H")
        oi_change = outputs.get("dOI_H")
        if displacement is None or oi_change is None:
            return None
        price_sign = 1.0 if float(displacement) > 0 else -1.0 if float(displacement) < 0 else 0.0
        return direction * price_sign * math.tanh(50.0 * float(oi_change))
    if rule_id == "M4-RULE-FUNDING-STATE-001":
        raw = outputs.get("last_funding_rate", outputs.get("last_funding_rate_proxy"))
        return -direction * math.tanh(float(raw) / 0.0005) if raw is not None else None
    return None


def _augment_frozen_signal_rows(cases: list[dict], rows: list[dict]) -> None:
    existing = {
        (int(row["case_id"]), row["rule_id"], row["variable"]) for row in rows
    }
    for case in cases:
        if not case.get("episode_key"):
            continue
        label = (case.get("outcome") or {}).get("label")
        if label not in m8.CLASSES:
            continue
        for rule_id, horizons in RETAINED_RULE_HORIZONS.items():
            if case["time_horizon"] not in horizons:
                continue
            variable = FROZEN_SIGNAL_VARIABLES[rule_id]
            key = (int(case["case_id"]), rule_id, variable)
            if key in existing:
                continue
            value = _frozen_signal_value(case, rule_id)
            if value is None:
                continue
            rows.append(
                {
                    "case_id": case["case_id"],
                    "rule_id": rule_id,
                    "variable": variable,
                    "time_horizon": case["time_horizon"],
                    "analysis_at": case["analysis_at"],
                    "episode_key": case["episode_key"],
                    "outcome_label": label,
                    "value": float(value),
                    "source": "exact_pretrade_trace_semantic_signal",
                }
            )
            existing.add(key)


def _fixed_spec_and_metric(
    variable_rows: list[dict],
    *,
    rule_id: str,
    horizon: str,
    cutoff: datetime | None,
) -> tuple[dict, dict]:
    selected_variable = FROZEN_SIGNAL_VARIABLES[rule_id]
    selected_rows = [
        row
        for row in variable_rows
        if row["rule_id"] == rule_id
        and row["time_horizon"] == horizon
        and row["variable"] == selected_variable
    ]
    if not selected_rows:
        raise RuntimeError(f"retained_rule_signal_missing:{rule_id}:{horizon}")
    target = "movement" if rule_id in MOVEMENT_RULE_IDS else "directional"
    episodes = _episode_signal_rows(selected_rows, target)
    early = [
        row for row in episodes
        if cutoff is not None and _parse_utc(row["analysis_at"]) <= cutoff
    ]
    latest = [
        row for row in episodes
        if cutoff is not None and _parse_utc(row["analysis_at"]) > cutoff
    ]
    full_auc = fast_soft_auc(
        [row["signal"] for row in episodes],
        [row["positive_share"] for row in episodes],
    )
    early_auc = fast_soft_auc(
        [row["signal"] for row in early],
        [row["positive_share"] for row in early],
    )
    latest_auc = fast_soft_auc(
        [row["signal"] for row in latest],
        [row["positive_share"] for row in latest],
    )
    positive_mass = math.fsum(row["positive_share"] for row in episodes)
    negative_mass = len(episodes) - positive_mass
    formal_gate = (
        len(episodes) >= MIN_EFFECTIVE_EPISODES
        and positive_mass >= MIN_EFFECTIVE_CLASS_MASS
        and negative_mass >= MIN_EFFECTIVE_CLASS_MASS
    )
    metric = {
        "rule_id": rule_id,
        "time_horizon": horizon,
        "target": target,
        "selected_variable": selected_variable,
        "variable_source": selected_rows[0]["source"],
        "selection_method": "frozen_semantic_signal_no_historical_optimization",
        "orientation": "direct",
        "candidate_variables_considered": 1,
        "raw_cases": sum(row["raw_cases"] for row in episodes),
        "effective_episodes": len(episodes),
        "effective_positive_mass": positive_mass,
        "effective_negative_mass": negative_mass,
        "early_70_percent_auc": early_auc,
        "full_auc": full_auc,
        "latest_30_percent": {
            "episodes": len(latest),
            "auc": latest_auc,
            "bootstrap_95ci": None,
            "permutation_p": None,
            "fdr_bh": None,
        },
        "permutation_p": None,
        "fdr_bh": None,
        "formal_gate": formal_gate,
        "additional_effective_episodes_needed": max(
            0, MIN_EFFECTIVE_EPISODES - len(episodes)
        ),
        "evidence_status": (
            "historical_association_not_promoted"
            if formal_gate
            else "insufficient_effective_evidence"
        ),
    }
    return {
        "variable": selected_variable,
        "source": selected_rows[0]["source"],
        "target": target,
        "orientation": 1,
        "episodes": episodes,
    }, metric


def build_compact_baseline() -> dict:
    cutoff = datetime.fromisoformat(HISTORICAL_CUTOFF_AT)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    use_session_pool_for_long_audit()
    print("OBS_BASE_STAGE=load_sources", flush=True)
    stored, unlinked = load_database_sources()
    stored = [row for row in stored if _at_or_before(row.get("analysis_at"), cutoff)]
    unlinked = [row for row in unlinked if _at_or_before(row.get("created_at"), cutoff)]
    counterfactuals, counterfactual_inventory = prepare_exact_counterfactuals(
        stored,
        unlinked,
        captured_at=cutoff,
    )
    counterfactuals = [
        row for row in counterfactuals if _at_or_before(row.get("analysis_at"), cutoff)
    ]
    closed = [
        row
        for row in load_closed_rows()
        if _at_or_before(row.get("analysis_at"), cutoff)
    ]
    print(
        f"OBS_BASE_STAGE=replay:closed={len(closed)}:counterfactuals={len(counterfactuals)}",
        flush=True,
    )
    cases, cohort_inventory = replay_consolidated_cases(closed, counterfactuals)
    _mark_observation_sources(cases, _load_observation_sources(cutoff))
    cases, episode_summary = attach_episode_memberships(cases)
    _overlay_recorded_stage_traces(cases, _load_linked_snapshots(cutoff))
    library = load_rule_library()
    library_rules = {rule["rule_id"]: rule for rule in library["rules"]}
    variable_rows, coverage = extract_rule_variables(cases, library_rules)
    _augment_frozen_signal_rows(cases, variable_rows)
    cutoffs = horizon_cutoffs(cases)
    retained_pairs = [
        (rule_id, horizon)
        for rule_id, horizons in RETAINED_RULE_HORIZONS.items()
        for horizon in horizons
    ]
    selected_specs = {}
    hypotheses = []
    for rule_id, horizon in retained_pairs:
        selected, metric = _fixed_spec_and_metric(
            variable_rows,
            rule_id=rule_id,
            horizon=horizon,
            cutoff=cutoffs.get(horizon),
        )
        selected_specs[(rule_id, horizon)] = selected
        hypotheses.append(metric)
    hypothesis_lookup = {
        (row["rule_id"], row["time_horizon"]): row for row in hypotheses
    }

    variable_lookup = {
        (int(row["case_id"]), row["rule_id"], row["variable"]): row
        for row in variable_rows
    }
    formal_cases = [
        case
        for case in cases
        if case.get("episode_key")
        and (case.get("outcome") or {}).get("label") in m8.CLASSES
    ]
    compact_cases = []
    for case in formal_cases:
        horizon = str(case["time_horizon"])
        signals = {}
        expected = []
        for rule_id, retained_horizons in RETAINED_RULE_HORIZONS.items():
            if horizon not in retained_horizons:
                continue
            expected.append(rule_id)
            selected = selected_specs[(rule_id, horizon)]
            variable = selected["variable"]
            variable_row = variable_lookup.get(
                (int(case["case_id"]), rule_id, variable)
            )
            if variable_row is None:
                continue
            signals[rule_id] = {
                "value": float(variable_row["value"]),
                "variable": variable,
                "source": variable_row["source"],
            }
        identity = {
            "source_kind": str(case["source_kind"]),
            "source_id": int(case["source_id"]),
            "recommendation_id": case.get("recommendation_id"),
            "analysis_at": str(case["analysis_at"]),
            "outcome_label": case["outcome"]["label"],
            "contract_version": BASE_CONTRACT_VERSION,
        }
        source_identity_sha = payload_sha256(identity)
        compact = {
            "case_key": source_identity_sha,
            "source_kind": str(case["source_kind"]),
            "source_reference": (
                f"operation:{int(case['source_id'])}"
                if case["source_kind"] == "closed_operation"
                else (
                    f"observation:{case['observation_checkpoint_code']}"
                    if case["source_kind"] == "operation_observation_checkpoint"
                    else f"recommendation:{int(case['source_id'])}"
                )
            ),
            "symbol": str(case["symbol"]),
            "side": str(case["side"]),
            "time_horizon": horizon,
            "analysis_at": str(case["analysis_at"]),
            "evaluation_expires_at": str(case["expiry_at"]),
            "outcome_label": case["outcome"]["label"],
            "episode_key": str(case["episode_key"]),
            "episode_weight": float(case["episode_weight"]),
            "probabilities": _probabilities(case),
            "signals": signals,
            "missing_rule_ids": sorted(set(expected) - set(signals)),
            "source_identity_sha256": source_identity_sha,
            "contract_version": BASE_CONTRACT_VERSION,
        }
        compact["payload_sha256"] = payload_sha256(compact)
        compact_cases.append(compact)

    rule_baselines = []
    for rule_id, horizon in retained_pairs:
        metric = hypothesis_lookup[(rule_id, horizon)]
        metadata = library_rules[rule_id]
        formula_contract = {
            "rule_id": rule_id,
            "rule_version": metadata.get("version"),
            "formula_ids": metadata.get("formula_ids") or [],
            "selected_variable": metric["selected_variable"],
            "variable_source": metric["variable_source"],
            "target": metric["target"],
            "orientation": metric["orientation"],
            "catalog_sha256": library["catalog_sha256"],
        }
        continuation = {
            "automatic_probability_effect": "none",
            "minimum_effective_episodes": MIN_EFFECTIVE_EPISODES,
            "minimum_effective_class_mass": MIN_EFFECTIVE_CLASS_MASS,
            "additional_effective_episodes_needed_at_cutoff": metric[
                "additional_effective_episodes_needed"
            ],
            "next_review": "manual_after_new_independent_episode_mass",
            "future_formula_mismatch_policy": "store_missing_not_proxy",
            "prospective_independence_unit": (
                "fixed_nonoverlapping_bucket_by_symbol_and_horizon"
            ),
            "prospective_episode_weight_at_review": (
                "one_divided_by_comparable_cases_in_episode"
            ),
        }
        rule_baselines.append(
            {
                "rule_id": rule_id,
                "time_horizon": horizon,
                "target": "movement" if rule_id in MOVEMENT_RULE_IDS else "directional",
                "selected_variable": metric["selected_variable"],
                "orientation": metric["orientation"],
                "formula_contract": formula_contract,
                "formula_contract_sha256": payload_sha256(formula_contract),
                "historical_metrics": metric,
                "continuation": continuation,
            }
        )

    deterministic_audit = {
        "audit_version": AUDIT_VERSION,
        "library_version": library["library_version"],
        "catalog_sha256": library["catalog_sha256"],
        "historical_cutoff_at": HISTORICAL_CUTOFF_AT,
        "protocol": {
            "independent_unit": "overlapping_episode_by_symbol_and_horizon",
            "minimum_effective_episodes": MIN_EFFECTIVE_EPISODES,
            "minimum_effective_class_mass": MIN_EFFECTIVE_CLASS_MASS,
            "temporal_validation": "fixed_semantic_signal_earliest_70_percent_vs_latest_30_percent",
            "historical_metric": "descriptive_soft_auc_only",
            "confirmatory_tests_at_cutoff": "not_run_for_frozen_semantic_signals",
            "future_confirmatory_requirements": (
                "independent prospective episodes, temporal holdout, bootstrap interval, "
                "permutation test and multiple-testing correction"
            ),
            "automatic_weight_change": False,
        },
        "cohort": {
            **cohort_inventory,
            "counterfactual_inventory": counterfactual_inventory,
            "variable_rows_evaluated": len(variable_rows),
        },
        "episodes": episode_summary,
        "retained_rule_metrics": [row["historical_metrics"] for row in rule_baselines],
        "coverage": {
            rule_id: coverage[rule_id] for rule_id in RETAINED_RULE_HORIZONS
        },
    }
    deterministic_audit["audit_sha256"] = payload_sha256(deterministic_audit)
    compact_dataset_sha = payload_sha256(
        sorted(case["payload_sha256"] for case in compact_cases)
    )
    return {
        "audit": deterministic_audit,
        "cases": compact_cases,
        "rule_baselines": rule_baselines,
        "compact_dataset_sha256": compact_dataset_sha,
    }


def _insert_payload(db, payload: dict) -> int:
    audit = payload["audit"]
    protocol = audit["protocol"]
    source_case_counts = {
        source_kind: sum(
            case["source_kind"] == source_kind for case in payload["cases"]
        )
        for source_kind in sorted(
            {case["source_kind"] for case in payload["cases"]}
        )
    }
    summary = {
        "retained_rule_count": len(RETAINED_RULE_HORIZONS),
        "retained_rule_horizon_contracts": len(payload["rule_baselines"]),
        "historical_outcomes": {
            label: sum(case["outcome_label"] == label for case in payload["cases"])
            for label in m8.CLASSES
        },
        "historical_source_cases": source_case_counts,
        "probability_weight": PROBABILITY_WEIGHT,
        "raw_history_dependency_after_verification": "none",
    }
    existing = db.execute(
        "SELECT * FROM observational_learning_cohorts WHERE cohort_key = ?",
        (BASELINE_COHORT_KEY,),
    ).fetchone()
    if existing is None:
        cursor = db.execute(
            """
            INSERT INTO observational_learning_cohorts (
                cohort_key, contract_version, historical_cutoff_at, status,
                audit_version, audit_sha256, rule_catalog_sha256,
                source_dataset_sha256, protocol_json, summary_json
            )
            VALUES (?, ?, ?, 'building', ?, ?, ?, ?, ?, ?)
            """,
            (
                BASELINE_COHORT_KEY,
                BASE_CONTRACT_VERSION,
                HISTORICAL_CUTOFF_AT,
                audit["audit_version"],
                audit["audit_sha256"],
                audit["catalog_sha256"],
                audit["episodes"]["source_dataset_sha256"],
                canonical_json(protocol),
                canonical_json(summary),
            ),
        )
        cohort_id = int(cursor.lastrowid)
    else:
        cohort_id = int(existing["id"])
        if str(existing["audit_sha256"]) != audit["audit_sha256"]:
            raise RuntimeError("sealed_cohort_audit_hash_mismatch")

    for item in payload["rule_baselines"]:
        db.execute(
            """
            INSERT INTO observational_rule_baselines (
                cohort_id, rule_id, time_horizon, target, selected_variable,
                orientation, lifecycle_status, probability_weight,
                formula_contract_json, formula_contract_sha256,
                historical_metrics_json, continuation_json
            )
            VALUES (?, ?, ?, ?, ?, ?, 'observational', 0, ?, ?, ?, ?)
            ON CONFLICT (cohort_id, rule_id, time_horizon) DO NOTHING
            """,
            (
                cohort_id,
                item["rule_id"],
                item["time_horizon"],
                item["target"],
                item["selected_variable"],
                item["orientation"],
                canonical_json(item["formula_contract"]),
                item["formula_contract_sha256"],
                canonical_json(item["historical_metrics"]),
                canonical_json(item["continuation"]),
            ),
        )
    for case in payload["cases"]:
        db.execute(
            """
            INSERT INTO observational_learning_cases (
                cohort_id, case_key, cohort_partition, source_kind,
                source_reference, symbol, side, time_horizon, analysis_at,
                evaluation_expires_at, outcome_label, episode_key,
                episode_weight, probabilities_json, signals_json,
                signal_count, missing_rule_ids_json, contract_version,
                source_identity_sha256, payload_sha256
            )
            VALUES (?, ?, 'historical', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (case_key) DO NOTHING
            """,
            (
                cohort_id,
                case["case_key"],
                case["source_kind"],
                case["source_reference"],
                case["symbol"],
                case["side"],
                case["time_horizon"],
                case["analysis_at"],
                case["evaluation_expires_at"],
                case["outcome_label"],
                case["episode_key"],
                case["episode_weight"],
                canonical_json(case["probabilities"]),
                canonical_json(case["signals"]),
                len(case["signals"]),
                canonical_json(case["missing_rule_ids"]),
                BASE_CONTRACT_VERSION,
                case["source_identity_sha256"],
                case["payload_sha256"],
            ),
        )
    return cohort_id


def verify_compact_baseline(db, cohort_id: int, payload: dict) -> dict:
    rows = [
        dict(row)
        for row in db.execute(
            """
            SELECT case_key, time_horizon, analysis_at, outcome_label,
                   episode_key, payload_sha256, signals_json
            FROM observational_learning_cases
            WHERE cohort_id = ? AND cohort_partition = 'historical'
            ORDER BY case_key
            """,
            (cohort_id,),
        ).fetchall()
    ]
    stored_dataset_sha = payload_sha256(sorted(row["payload_sha256"] for row in rows))
    if len(rows) != len(payload["cases"]):
        raise RuntimeError(
            f"compact_case_count_mismatch:{len(rows)}:{len(payload['cases'])}"
        )
    if stored_dataset_sha != payload["compact_dataset_sha256"]:
        raise RuntimeError("compact_dataset_hash_mismatch")
    baselines = [
        dict(row)
        for row in db.execute(
            """
            SELECT rule_id, time_horizon, target, selected_variable,
                   orientation, historical_metrics_json
            FROM observational_rule_baselines
            WHERE cohort_id = ?
            ORDER BY rule_id, time_horizon
            """,
            (cohort_id,),
        ).fetchall()
    ]
    if len(baselines) != len(payload["rule_baselines"]):
        raise RuntimeError("compact_baseline_count_mismatch")
    checks = []
    for baseline in baselines:
        source_rows = []
        for row in rows:
            if row["time_horizon"] != baseline["time_horizon"]:
                continue
            signals = json.loads(row["signals_json"])
            signal = signals.get(baseline["rule_id"])
            if not isinstance(signal, dict) or signal.get("value") is None:
                continue
            source_rows.append(
                {
                    "episode_key": row["episode_key"],
                    "analysis_at": row["analysis_at"],
                    "outcome_label": row["outcome_label"],
                    "value": float(signal["value"]),
                }
            )
        episodes = _episode_signal_rows(source_rows, baseline["target"])
        orientation = 1 if baseline["orientation"] == "direct" else -1
        auc = fast_soft_auc(
            [orientation * row["signal"] for row in episodes],
            [row["positive_share"] for row in episodes],
        )
        expected = json.loads(baseline["historical_metrics_json"])
        reproduced_raw_cases = sum(row["raw_cases"] for row in episodes)
        if reproduced_raw_cases != int(expected["raw_cases"]):
            raise RuntimeError(
                f"compact_raw_case_reproduction_failed:{baseline['rule_id']}:{baseline['time_horizon']}"
            )
        if len(episodes) != int(expected["effective_episodes"]):
            raise RuntimeError(
                f"compact_episode_reproduction_failed:{baseline['rule_id']}:{baseline['time_horizon']}"
            )
        expected_auc = expected.get("full_auc")
        if (auc is None) != (expected_auc is None) or (
            auc is not None and abs(auc - float(expected_auc)) > 1e-12
        ):
            raise RuntimeError(
                f"compact_auc_reproduction_failed:{baseline['rule_id']}:{baseline['time_horizon']}"
            )
        checks.append(
            {
                "rule_id": baseline["rule_id"],
                "time_horizon": baseline["time_horizon"],
                "raw_cases": reproduced_raw_cases,
                "effective_episodes": len(episodes),
                "full_auc": auc,
                "matches_historical_audit": True,
            }
        )
    episode_count = len({row["episode_key"] for row in rows})
    db.execute(
        """
        UPDATE observational_learning_cohorts
        SET status = 'sealed', compact_dataset_sha256 = ?,
            historical_case_count = ?, historical_episode_count = ?,
            verified_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (stored_dataset_sha, len(rows), episode_count, cohort_id),
    )
    return {
        "cohort_id": cohort_id,
        "status": "sealed",
        "historical_cases": len(rows),
        "historical_episodes": episode_count,
        "rule_horizon_contracts": len(checks),
        "compact_dataset_sha256": stored_dataset_sha,
        "all_metrics_reproduced": True,
        "checks": checks,
    }


def main() -> None:
    args = parse_args()
    payload = build_compact_baseline()
    print(
        canonical_json(
            {
                "status": "built_in_memory",
                "historical_cases": len(payload["cases"]),
                "historical_episodes": payload["audit"]["episodes"][
                    "effective_horizon_episodes"
                ],
                "source_cases": {
                    source_kind: sum(
                        case["source_kind"] == source_kind
                        for case in payload["cases"]
                    )
                    for source_kind in sorted(
                        {case["source_kind"] for case in payload["cases"]}
                    )
                },
                "rule_horizon_contracts": len(payload["rule_baselines"]),
                "audit_sha256": payload["audit"]["audit_sha256"],
                "compact_dataset_sha256": payload["compact_dataset_sha256"],
            }
        ),
        flush=True,
    )
    if not args.apply:
        return
    try:
        with connect() as db:
            ensure_observational_learning_base_tables(db)
            cohort_id = _insert_payload(db, payload)
            verification = verify_compact_baseline(db, cohort_id, payload)
        print(canonical_json(verification), flush=True)
    finally:
        close_pool()


if __name__ == "__main__":
    main()
