from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import market_data
from db import row_to_dict
from m5_engine import ENGINE_VERSION as M5_ENGINE_VERSION
from m5_engine import run_internal_analysis
from m5_input_assembly import (
    build_rule_inputs,
    candidate_features_from_m5,
    rule_effect_registry,
    trace_map,
)
from m6_active_engine import ACTIVE_ENGINE_VERSION
from m6_active_engine import run_internal_probability_analysis
from m6_predictive_rules import (
    ACTIVE_EVIDENCE_FAMILIES,
    ACTIVE_PREDICTIVE_RULE_IDS,
    FITTED_RULE_FEATURES,
    FITTED_RULE_IDS,
    apply_provisional_rule_overlay,
    build_provisional_rule_signals,
)
from m8_evaluation import (
    fetch_klines_range,
    normalize_kline,
    parse_utc,
    selected_interval_seconds,
)
from microstructure_rule_runtime import evaluate_microstructure_rule_family
from technical_rule_runtime import evaluate_technical_rule_family
from versioning import APP_VERSION, PROSPECTIVE_RUNTIME_VERSION


PRODUCTION_EFFECT_NONE = "none"
PRODUCTION_EFFECT_SERVED = "served"
ENABLED_ENV = "M6_PROSPECTIVE_VALIDATION_ENABLED"
CANDIDATE_PATH = (
    Path(__file__).resolve().parent
    / "auditorias_motor"
    / "candidato_m6_v0_2_sin_path_h.json"
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def prospective_validation_enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@lru_cache(maxsize=1)
def load_frozen_candidate() -> dict:
    payload = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    expected = payload.get("canonical_payload_sha256")
    actual = sha256_json(
        {
            key: value
            for key, value in payload.items()
            if key != "canonical_payload_sha256"
        }
    )
    if expected != actual:
        raise ValueError("frozen_candidate_payload_hash_mismatch")
    artifact = payload["coefficient_artifact"]
    expected_artifact = artifact.get("artifact_sha256")
    actual_artifact = sha256_json(
        {
            key: value
            for key, value in artifact.items()
            if key != "artifact_sha256"
        }
    )
    if expected_artifact != actual_artifact:
        raise ValueError("frozen_candidate_artifact_hash_mismatch")
    return payload


def standardized_candidate_features(
    raw_values: dict[str, float],
    artifact: dict,
) -> dict[str, float]:
    scaling = artifact["feature_standardization"]
    values = {"intercept": 1.0}
    for name, scale in scaling.items():
        raw = float(raw_values[name])
        values[name] = (
            raw - float(scale["mean"])
        ) / float(scale["scale"])
    return values


def temperature_calibration(
    probabilities: dict[str, float],
    temperature: float,
) -> dict[str, float]:
    weights = {
        name: math.exp(
            math.log(max(1e-15, float(probability))) / temperature
        )
        for name, probability in probabilities.items()
    }
    total = math.fsum(weights.values())
    return {name: value / total for name, value in weights.items()}


def _blocked_payload(
    *,
    analysis_id: str,
    plan: dict,
    code: str,
    details: dict | None = None,
) -> dict:
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "analysis_id": analysis_id,
        "status": "blocked",
        "block_code": code,
        "plan": plan,
        "feature_snapshot": {},
        "m5_analysis": None,
        "m6_result": None,
        "data_cutoff_at": None,
        "source_data_sha256": sha256_json({}),
        "details": details or {},
        "production_effect": PRODUCTION_EFFECT_NONE,
    }


def build_plan(proposal: Any, snapshot: dict) -> dict:
    analysis_at = str(snapshot["analysis_at"])
    horizon_seconds = int(snapshot["evaluation_horizon_seconds"])
    expires_at = snapshot.get("evaluation_expires_at")
    if not expires_at:
        parsed = datetime.fromisoformat(analysis_at.replace("Z", "+00:00"))
        expires_at = datetime.fromtimestamp(
            parsed.timestamp() + horizon_seconds,
            tz=timezone.utc,
        ).isoformat()
    return {
        "symbol": str(proposal.symbol).upper(),
        "side": str(proposal.side).lower(),
        "entry": float(proposal.entry),
        "margin": float(proposal.margin),
        "leverage": float(proposal.leverage),
        "take_profit": float(proposal.take_profit),
        "stop_loss": float(proposal.stop_loss),
        "entry_type": str(getattr(proposal, "entry_type", "market")).lower(),
        "time_horizon": str(proposal.time_horizon),
        "horizon_seconds": horizon_seconds,
        "analysis_at": analysis_at,
        "evaluation_expires_at": str(expires_at),
    }


def build_prospective_probability_run(
    proposal: Any,
    snapshot: dict,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
    analysis_id: str,
    active_output: bool = False,
    live_context: dict | None = None,
) -> dict:
    plan = build_plan(proposal, snapshot)
    if plan["entry_type"] != "market":
        return _blocked_payload(
            analysis_id=analysis_id,
            plan=plan,
            code="m5_market_entry_required",
        )
    analysis_at = parse_utc(plan["analysis_at"])
    if analysis_at is None:
        return _blocked_payload(
            analysis_id=analysis_id,
            plan=plan,
            code="analysis_timestamp_invalid",
        )

    interval_seconds = selected_interval_seconds(
        plan["time_horizon"],
        plan["horizon_seconds"],
    )
    return_count = plan["horizon_seconds"] // interval_seconds
    required_returns = 61 * return_count
    analysis_ms = int(analysis_at.timestamp() * 1000)
    start_ms = analysis_ms - (required_returns + 2) * interval_seconds * 1000
    raw = fetch_klines_range(
        plan["symbol"],
        {
            60: "1m",
            180: "3m",
            300: "5m",
            900: "15m",
            1800: "30m",
            3600: "1h",
            7200: "2h",
            14400: "4h",
            21600: "6h",
            28800: "8h",
            43200: "12h",
            86400: "1d",
        }[interval_seconds],
        start_ms,
        analysis_ms,
        loader=loader,
    )
    candles = [normalize_kline(row) for row in raw]
    try:
        rule_inputs, material, source_observations = build_rule_inputs(
            plan=plan,
            candles=candles,
            live_context=live_context,
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return _blocked_payload(
            analysis_id=analysis_id,
            plan=plan,
            code=str(exc) or "m5_input_assembly_blocked",
            details={"exception_type": type(exc).__name__},
        )

    m5_pre_probability = run_internal_analysis(
        analysis_id=f"{analysis_id}:m5-pre-probability",
        rule_inputs=rule_inputs,
        source_observations=source_observations,
        executed_at=plan["analysis_at"],
    )
    technical_rule_observations = evaluate_technical_rule_family(
        material["selected"],
        side=plan["side"],
        analysis_at=plan["analysis_at"],
        interval_seconds=material["interval_seconds"],
        source_data_sha256=material["data_sha256"],
    )
    microstructure_rule_observations = evaluate_microstructure_rule_family(
        selected_candles=material["selected"],
        current_bars=material["current_bars"],
        live_context=live_context,
        return_count=material["return_count"],
        interval_seconds=material["interval_seconds"],
        side=plan["side"],
        analysis_at=plan["analysis_at"],
        source_data_sha256=material["data_sha256"],
    )
    observational_traces = (
        technical_rule_observations["traces"]
        + microstructure_rule_observations["traces"]
    )
    evaluated_observational_count = sum(
        trace["status"] == "evaluated_shadow"
        for trace in observational_traces
    )
    observational_rule_observations = {
        "runtime_version": "observational-rule-runtime-v0.2",
        "status": (
            "evaluated_shadow"
            if evaluated_observational_count == len(observational_traces)
            else "partially_evaluated_shadow"
            if evaluated_observational_count
            else "blocked"
        ),
        "analysis_at": plan["analysis_at"],
        "evaluated_rule_count": evaluated_observational_count,
        "runtimes": [
            technical_rule_observations,
            microstructure_rule_observations,
        ],
        "traces": observational_traces,
    }
    observational_rule_observations["runtime_trace_sha256"] = sha256_json(
        observational_rule_observations
    )
    try:
        feature_values = candidate_features_from_m5(
            m5_pre_probability,
            side=plan["side"],
        )
    except ValueError as exc:
        return _blocked_payload(
            analysis_id=analysis_id,
            plan=plan,
            code="m5_candidate_source_rules_unavailable",
            details={
                "message": str(exc),
                "m5_status_counts": m5_pre_probability["status_counts"],
            },
        )
    data_cutoff_at = datetime.fromtimestamp(
        material["data_cutoff_at_ms"] / 1000,
        tz=timezone.utc,
    ).isoformat()
    feature_snapshot = {
        "status": "evaluated",
        "values": feature_values,
        "interval_seconds": material["interval_seconds"],
        "return_count_per_horizon": material["return_count"],
        "data_cutoff_at": data_cutoff_at,
        "pretrade_candle_sha256": material["data_sha256"],
        "source_rule_ids": {
            "directional_path_efficiency_h": (
                "M4-RULE-PATH-STRUCTURE-001"
            ),
            "directional_path_efficiency_2h": (
                "M4-RULE-MTF-HIERARCHY-001"
            ),
            "directional_path_efficiency_4h": (
                "M4-RULE-MTF-HIERARCHY-001"
            ),
            "volatility_percentile_60": (
                "M4-RULE-VOLATILITY-RANK-001"
            ),
            "target_extreme_between_entry_and_tp": (
                "M4-RULE-PRIOR-EXTREMA-001"
            ),
        },
        "source_m5_analysis_id": m5_pre_probability["analysis_id"],
        "source_m5_trace_sha256": m5_pre_probability[
            "analysis_trace_sha256"
        ],
        "observational_rule_traces": observational_rule_observations,
    }
    candidate_payload = load_frozen_candidate()
    artifact = candidate_payload["coefficient_artifact"]
    standardized_values = standardized_candidate_features(
        feature_values,
        artifact,
    )
    core_m6_result = run_internal_probability_analysis(
        analysis_id=f"{analysis_id}:m6",
        m5_analysis=m5_pre_probability,
        feature_snapshot=standardized_values,
        coefficient_artifact=artifact,
        executed_at=plan["analysis_at"],
    )
    evaluated = (
        core_m6_result.get("status") == "evaluated_internal_only"
    )
    if evaluated:
        production_effect = (
            PRODUCTION_EFFECT_SERVED
            if active_output
            else PRODUCTION_EFFECT_NONE
        )
        temperature = float(artifact["calibration"]["temperature"])
        calibrated_before_overlay = temperature_calibration(
            core_m6_result["probabilities"],
            temperature,
        )
        provisional_signals = build_provisional_rule_signals(
            m5_pre_probability,
            side=plan["side"],
        )
        rule_overlay = apply_provisional_rule_overlay(
            calibrated_before_overlay,
            provisional_signals,
        )
        calibrated = rule_overlay["probabilities_after"]

        def probabilities_without_rule_ids(
            removed_rule_ids: set[str],
        ) -> dict[str, float]:
            removed_fitted = removed_rule_ids & set(FITTED_RULE_FEATURES)
            if removed_fitted:
                ablated_features = dict(standardized_values)
                for removed_rule_id in removed_fitted:
                    for feature_name in FITTED_RULE_FEATURES[
                        removed_rule_id
                    ]:
                        ablated_features[feature_name] = 0.0
                ablated_core = run_internal_probability_analysis(
                    analysis_id=(
                        f"{analysis_id}:m6:ablate:"
                        + ",".join(sorted(removed_rule_ids))
                    ),
                    m5_analysis=m5_pre_probability,
                    feature_snapshot=ablated_features,
                    coefficient_artifact=artifact,
                    executed_at=plan["analysis_at"],
                )
                if (
                    ablated_core.get("status")
                    != "evaluated_internal_only"
                ):
                    raise RuntimeError(
                        "fitted_rule_ablation_failed:"
                        + ",".join(sorted(removed_rule_ids))
                    )
                ablated_before_overlay = temperature_calibration(
                    ablated_core["probabilities"],
                    temperature,
                )
            else:
                ablated_before_overlay = calibrated_before_overlay
            ablated_signals = {
                **provisional_signals,
                "active": {
                    rule_id: value
                    for rule_id, value in provisional_signals[
                        "active"
                    ].items()
                    if rule_id not in removed_rule_ids
                },
            }
            return apply_provisional_rule_overlay(
                ablated_before_overlay,
                ablated_signals,
            )["probabilities_after"]

        fitted_rule_ablation = {}
        for rule_id, feature_names in FITTED_RULE_FEATURES.items():
            probabilities_without = probabilities_without_rule_ids(
                {rule_id}
            )
            fitted_rule_ablation[rule_id] = {
                "feature_names": list(feature_names),
                "standardized_values_removed": {
                    feature_name: standardized_values[feature_name]
                    for feature_name in feature_names
                },
                "probabilities_without_rule": probabilities_without,
                "ablation_probability_delta": {
                    name: calibrated[name] - probabilities_without[name]
                    for name in calibrated
                },
            }
        evidence_family_ablation = {}
        for family_id, family_rule_ids in (
            ACTIVE_EVIDENCE_FAMILIES.items()
        ):
            active_family_rule_ids = [
                rule_id
                for rule_id in family_rule_ids
                if rule_id in ACTIVE_PREDICTIVE_RULE_IDS
            ]
            probabilities_without = probabilities_without_rule_ids(
                set(active_family_rule_ids)
            )
            evidence_family_ablation[family_id] = {
                "rule_ids": active_family_rule_ids,
                "probabilities_without_family": probabilities_without,
                "ablation_probability_delta": {
                    name: calibrated[name] - probabilities_without[name]
                    for name in calibrated
                },
            }
        m6_result = {
            "engine_version": core_m6_result["engine_version"],
            "candidate_version": candidate_payload["version"],
            "coefficient_artifact_id": artifact["id"],
            "coefficient_artifact_sha256": artifact["artifact_sha256"],
            "status": (
                "evaluated_active"
                if active_output
                else "evaluated_internal_only"
            ),
            "block_code": None,
            "probabilities": calibrated,
            "raw_probabilities": core_m6_result["probabilities"],
            "probabilities_before_rule_overlay": calibrated_before_overlay,
            "active_rule_overlay": rule_overlay,
            "fitted_rule_ablation": fitted_rule_ablation,
            "evidence_family_ablation": evidence_family_ablation,
            "calibration": artifact["calibration"],
            "core_result": core_m6_result,
            "production_effect": production_effect,
        }
        m6_result["result_sha256"] = sha256_json(m6_result)
    else:
        m6_result = core_m6_result

    pre_traces = trace_map(m5_pre_probability)
    readiness_statuses = {
        "market_probabilities": "available" if evaluated else "blocked",
        "entry_execution": (
            "available"
            if pre_traces.get("M4-RULE-DEPTH-SWEEP-001", {}).get("status")
            == "evaluated"
            else "blocked"
        ),
        "exit_execution": "blocked",
        "fees": (
            "available"
            if pre_traces.get("M4-RULE-FEE-SCENARIOS-001", {}).get("status")
            == "evaluated"
            else "blocked"
        ),
        "funding": (
            "available"
            if pre_traces.get("M4-RULE-FUNDING-CASHFLOW-001", {}).get(
                "status"
            )
            == "evaluated"
            else "blocked"
        ),
        "payoffs": (
            "available"
            if pre_traces.get("M4-RULE-NET-PAYOFFS-001", {}).get("status")
            == "evaluated"
            else "blocked"
        ),
        "account_risk": "blocked",
    }
    final_inputs, _, final_sources = build_rule_inputs(
        plan=plan,
        candles=candles,
        live_context=live_context,
        probabilities=(
            m6_result.get("probabilities")
            if evaluated
            else None
        ),
        readiness_statuses=readiness_statuses,
    )
    m5_analysis = run_internal_analysis(
        analysis_id=f"{analysis_id}:m5-final",
        rule_inputs=final_inputs,
        source_observations=final_sources,
        executed_at=plan["analysis_at"],
    )
    rule_effects = rule_effect_registry(
        m5_analysis,
        coefficient_artifact=artifact,
    )
    if evaluated:
        family_by_rule = {
            rule_id: family_id
            for family_id, rule_ids in ACTIVE_EVIDENCE_FAMILIES.items()
            for rule_id in rule_ids
        }
        for rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
            family_id = family_by_rule[rule_id]
            rule_effects[rule_id].update(
                {
                    "family_id": family_id,
                    "family_ablation": m6_result[
                        "evidence_family_ablation"
                    ][family_id],
                }
            )
        for rule_id, ablation in m6_result[
            "fitted_rule_ablation"
        ].items():
            rule_effects[rule_id].update(
                {
                    "ablation_probabilities_without_rule": ablation[
                        "probabilities_without_rule"
                    ],
                    "ablation_probability_delta": ablation[
                        "ablation_probability_delta"
                    ],
                }
            )
        for rule_id, contribution in rule_overlay[
            "rule_contributions"
        ].items():
            rule_effects[rule_id].update(
                {
                    "probability_effect": "provisional_rule_contribution",
                    "probability_effect_reason": (
                        "owner_authorized_active_rule_with_live_data"
                    ),
                    "provisional_weight": contribution["weight"],
                    "signal": contribution["signal"],
                    "effect_mode": contribution["effect_mode"],
                    "signal_formula": contribution["signal_formula"],
                    "tp_log_effect": contribution["tp_log_effect"],
                    "sl_log_effect": contribution["sl_log_effect"],
                    "expiry_log_effect": contribution[
                        "expiry_log_effect"
                    ],
                    "tp_probability_delta": contribution[
                        "tp_probability_delta"
                    ],
                    "sl_probability_delta": contribution[
                        "sl_probability_delta"
                    ],
                    "ablation_probabilities_without_rule": contribution[
                        "ablation_probabilities_without_rule"
                    ],
                    "ablation_probability_delta": contribution[
                        "ablation_probability_delta"
                    ],
                }
            )
        rule_effects["M4-RULE-DERIVATIVES-CONTEXT-001"].update(
            {
                "probability_effect": "complementary_container",
                "probability_effect_reason": (
                    "duplicate_container_not_an_independent_rule"
                ),
            }
        )
    feature_snapshot["standardized_candidate_values"] = standardized_values
    feature_snapshot["coefficient_artifact_id"] = artifact["id"]
    feature_snapshot["m5_rule_effects"] = rule_effects
    feature_snapshot["active_predictive_rule_ids"] = [
        rule_id
        for rule_id in ACTIVE_PREDICTIVE_RULE_IDS
        if (
            rule_id in FITTED_RULE_IDS
            and rule_effects[rule_id]["probability_effect"]
            == "fitted_competing_risk_covariate"
        )
        or rule_id in rule_overlay["active_rule_ids"]
    ] if evaluated else []
    feature_snapshot["active_rule_overlay"] = (
        rule_overlay if evaluated else None
    )
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "analysis_id": analysis_id,
        "status": "evaluated" if evaluated else "blocked",
        "block_code": None if evaluated else m6_result.get("block_code"),
        "plan": plan,
        "feature_snapshot": feature_snapshot,
        "m5_analysis": m5_analysis,
        "m5_pre_probability_analysis": m5_pre_probability,
        "m5_rule_effects": rule_effects,
        "observational_rule_traces": observational_rule_observations,
        "m6_result": m6_result,
        "data_cutoff_at": data_cutoff_at,
        "source_data_sha256": material["data_sha256"],
        "details": {
            "candidate": artifact["id"],
            "candidate_version": candidate_payload["version"],
            "removed_predictive_features": candidate_payload[
                "selection"
            ]["removed_feature"],
            "active_predictive_rule_ids": feature_snapshot[
                "active_predictive_rule_ids"
            ],
            "visible_to_user": active_output,
            "owner_authorized": active_output,
        },
        "production_effect": (
            PRODUCTION_EFFECT_SERVED
            if active_output and evaluated
            else PRODUCTION_EFFECT_NONE
        ),
    }


def persist_prospective_run(db, recommendation_id: int, payload: dict) -> dict:
    run_key = sha256_json(
        {
            "recommendation_id": int(recommendation_id),
            "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        }
    )
    existing = row_to_dict(
        db.execute(
            "SELECT id FROM m6_prospective_runs WHERE run_key = ? LIMIT 1",
            (run_key,),
        ).fetchone()
    )
    if existing is not None:
        return {
            "status": "idempotent_skip",
            "run_id": int(existing["id"]),
            "run_key": run_key,
            "production_effect": PRODUCTION_EFFECT_NONE,
        }
    plan = payload["plan"]
    cursor = db.execute(
        """
        INSERT INTO m6_prospective_runs (
            run_key, recommendation_id, runtime_version, m5_engine_version,
            m6_engine_version, run_status, block_code, analysis_at,
            data_cutoff_at, evaluation_expires_at, horizon_seconds,
            plan_contract_json, feature_snapshot_json, m5_trace_json,
            probability_result_json, source_data_sha256, production_effect,
            app_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_key,
            int(recommendation_id),
            PROSPECTIVE_RUNTIME_VERSION,
            M5_ENGINE_VERSION,
            ACTIVE_ENGINE_VERSION,
            payload["status"],
            payload.get("block_code"),
            plan["analysis_at"],
            payload.get("data_cutoff_at"),
            plan["evaluation_expires_at"],
            plan["horizon_seconds"],
            canonical_json(plan),
            canonical_json(payload.get("feature_snapshot") or {}),
            canonical_json(payload.get("m5_analysis") or {}),
            canonical_json(payload.get("m6_result") or {}),
            payload["source_data_sha256"],
            PRODUCTION_EFFECT_NONE,
            APP_VERSION,
        ),
    )
    return {
        "status": "recorded",
        "run_id": int(cursor.lastrowid),
        "run_key": run_key,
        "run_status": payload["status"],
        "block_code": payload.get("block_code"),
        "production_effect": PRODUCTION_EFFECT_NONE,
    }


def execute_prospective_validation(
    db,
    recommendation_id: int,
    proposal: Any,
    champion_result: dict,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
) -> dict:
    if not prospective_validation_enabled():
        return {
            "status": "disabled",
            "kill_switch": ENABLED_ENV,
            "production_effect": PRODUCTION_EFFECT_NONE,
        }
    snapshot = champion_result.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("champion_snapshot_missing")
    analysis_id = f"prospective-recommendation-{int(recommendation_id)}"
    try:
        payload = build_prospective_probability_run(
            proposal,
            snapshot,
            loader=loader,
            analysis_id=analysis_id,
        )
    except Exception as exc:
        payload = _blocked_payload(
            analysis_id=analysis_id,
            plan=build_plan(proposal, snapshot),
            code="prospective_data_or_engine_error",
            details={"exception_type": type(exc).__name__},
        )
    return persist_prospective_run(db, recommendation_id, payload)


def build_user_prospective_audit(db, user_id: int, limit: int = 100) -> dict:
    capped_limit = min(max(int(limit), 1), 250)
    summary = row_to_dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS total_runs,
                COUNT(*) FILTER (WHERE mpr.run_status = 'evaluated')
                    AS evaluated_runs,
                COUNT(*) FILTER (WHERE mpr.run_status = 'blocked')
                    AS blocked_runs,
                COUNT(*) FILTER (
                    WHERE mpr.run_status = 'evaluated'
                      AND mpr.evaluation_expires_at <= CURRENT_TIMESTAMP
                ) AS matured_evaluated_runs,
                COUNT(*) FILTER (WHERE mpr.production_effect <> 'none')
                    AS production_effect_violations
            FROM m6_prospective_runs mpr
            JOIN recommendations r ON r.id = mpr.recommendation_id
            WHERE r.user_id = ?
            """,
            (user_id,),
        ).fetchone()
    ) or {}
    block_rows = db.execute(
        """
        SELECT mpr.block_code, COUNT(*) AS cases
        FROM m6_prospective_runs mpr
        JOIN recommendations r ON r.id = mpr.recommendation_id
        WHERE r.user_id = ? AND mpr.run_status = 'blocked'
        GROUP BY mpr.block_code
        ORDER BY cases DESC, mpr.block_code
        """,
        (user_id,),
    ).fetchall()
    rows = db.execute(
        """
        SELECT
            mpr.id, mpr.recommendation_id, mpr.runtime_version,
            mpr.m5_engine_version, mpr.m6_engine_version, mpr.run_status,
            mpr.block_code, mpr.analysis_at, mpr.data_cutoff_at,
            mpr.evaluation_expires_at, mpr.horizon_seconds,
            mpr.plan_contract_json, mpr.feature_snapshot_json,
            mpr.probability_result_json, mpr.source_data_sha256,
            mpr.production_effect, mpr.app_version, mpr.created_at,
            r.symbol, r.side, r.time_horizon
        FROM m6_prospective_runs mpr
        JOIN recommendations r ON r.id = mpr.recommendation_id
        WHERE r.user_id = ?
        ORDER BY mpr.id DESC
        LIMIT ?
        """,
        (user_id, capped_limit),
    ).fetchall()
    runs = []
    for raw in rows:
        row = row_to_dict(raw) or {}
        probability = parse_json_object(row.get("probability_result_json"))
        runs.append(
            {
                "id": row.get("id"),
                "recommendation_id": row.get("recommendation_id"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "time_horizon": row.get("time_horizon"),
                "run_status": row.get("run_status"),
                "block_code": row.get("block_code"),
                "analysis_at": row.get("analysis_at"),
                "data_cutoff_at": row.get("data_cutoff_at"),
                "evaluation_expires_at": row.get("evaluation_expires_at"),
                "horizon_seconds": row.get("horizon_seconds"),
                "probabilities": probability.get("probabilities"),
                "probability_trace_sha256": probability.get("result_sha256"),
                "feature_snapshot": parse_json_object(
                    row.get("feature_snapshot_json")
                ),
                "source_data_sha256": row.get("source_data_sha256"),
                "production_effect": row.get("production_effect"),
                "runtime_version": row.get("runtime_version"),
                "m5_engine_version": row.get("m5_engine_version"),
                "m6_engine_version": row.get("m6_engine_version"),
                "app_version": row.get("app_version"),
                "created_at": row.get("created_at"),
            }
        )
    return {
        "runtime_version": PROSPECTIVE_RUNTIME_VERSION,
        "enabled": prospective_validation_enabled(),
        "kill_switch": ENABLED_ENV,
        "purpose": "new_independent_temporal_evidence_for_m8",
        "production_effect": PRODUCTION_EFFECT_NONE,
        "visible_probability_output": False,
        "m9_authorized": False,
        "summary": {
            "total_runs": int(summary.get("total_runs") or 0),
            "evaluated_runs": int(summary.get("evaluated_runs") or 0),
            "blocked_runs": int(summary.get("blocked_runs") or 0),
            "matured_evaluated_runs": int(
                summary.get("matured_evaluated_runs") or 0
            ),
            "production_effect_violations": int(
                summary.get("production_effect_violations") or 0
            ),
            "block_counts": {
                str((row_to_dict(row) or {}).get("block_code") or "unknown"):
                int((row_to_dict(row) or {}).get("cases") or 0)
                for row in block_rows
            },
        },
        "runs": runs,
    }
