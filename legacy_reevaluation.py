from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from versioning import LEGACY_REEVALUATION_VERSION, scoring_version_for_legacy_engine


LEGACY_REVIEW_SCHEMA_VERSION = "legacy-review-schema-v0.1"
NOT_AVAILABLE = "not_available"

OUTCOME_MAP = {
    "plan_success": ("tp_first", "observed_during_operation"),
    "plan_failure": ("sl_first", "observed_during_operation"),
    "plan_unresolved": ("expiry_unresolved", "observed_through_horizon"),
    "plan_would_succeed": ("tp_first", "observed_after_manual_close"),
    "plan_would_fail": ("sl_first", "observed_after_manual_close"),
    "contest_expiry_mark_to_market": (
        "expiry_unresolved",
        "contest_expiry_mark_to_market",
    ),
    "ambiguous_same_candle": ("ambiguous", "unresolved_intracandle_order"),
}

RETROSPECTIVE_KEYS = {
    "analysis_verdict",
    "close_price",
    "close_reason",
    "closed_at",
    "diagnostic_labels",
    "economic_metrics",
    "failure_type",
    "final_pnl",
    "first_plan_touch",
    "first_post_close_touch",
    "learning_signal",
    "max_adverse_pct",
    "max_favorable_pct",
    "plan_result",
    "post_trade_outcomes",
    "primary_lesson",
    "r_multiple",
    "reconstructed_plan_result",
    "user_decision_quality",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return deepcopy(value)
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def json_ready(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def canonical_json(value: Any) -> str:
    return json.dumps(
        json_ready(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def unavailable(reason: str, source: str | None = None) -> dict:
    result = {"status": NOT_AVAILABLE, "reason": reason}
    if source:
        result["source_checked"] = source
    return result


def recorded(
    value: Any,
    *,
    path: str,
    source: str,
    missing_fields: list[dict],
    reason: str = "not_recorded_in_legacy_source",
) -> Any:
    if value is not None and value != "":
        return json_ready(value)
    marker = unavailable(reason, source)
    missing_fields.append({"path": path, **marker})
    return marker


def nested(source: dict, *keys: str) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def source_records(case: dict) -> tuple[dict, dict, dict, dict, dict]:
    evaluation = parse_json_object(case.get("evaluation_record"))
    operation = parse_json_object(case.get("operation_record"))
    recommendation = parse_json_object(case.get("recommendation_record"))
    evidence = parse_json_object(case.get("evidence_record"))
    economics = parse_json_object(case.get("economic_record"))
    return evaluation, operation, recommendation, evidence, economics


def legacy_original_interpretation(
    evaluation: dict,
    recommendation: dict,
) -> dict:
    fields = (
        "operation_id",
        "plan_result",
        "analysis_verdict",
        "primary_lesson",
        "failure_type",
        "user_decision_quality",
        "setup_grade",
        "risk_level",
        "confidence",
        "training_decision",
        "tp_probability",
        "sl_probability",
        "range_probability",
        "technical_label",
        "technical_score",
        "market_regime",
        "direction_score",
        "confidence_score",
        "risk_reward_ratio",
        "risk_margin_pct",
        "reward_margin_pct",
        "leverage_bucket",
        "created_at",
    )
    return {
        "source_state": "learning_evaluation_after_evidence_and_economic_enrichment",
        "interpretation_fields": {
            key: json_ready(evaluation.get(key))
            for key in fields
        },
        "recorded_versions": {
            "app_version": evaluation.get("app_version"),
            "engine_version": recommendation.get("engine_version"),
            "scoring_version": evaluation.get("scoring_version"),
            "learning_evaluator_version": evaluation.get(
                "learning_evaluator_version"
            ),
            "learning_schema_version": evaluation.get("learning_schema_version"),
            "data_source_version": evaluation.get("data_source_version"),
            "data_contract_version": evaluation.get("data_contract_version"),
        },
        "legacy_structured_json": parse_json_object(
            evaluation.get("structured_json")
        ),
    }


def build_pre_trade_features(
    evaluation: dict,
    operation: dict,
    recommendation: dict,
    missing_fields: list[dict],
) -> dict:
    snapshot = parse_json_object(recommendation.get("snapshot_json"))
    technical = (
        snapshot.get("technical_rating")
        if isinstance(snapshot.get("technical_rating"), dict)
        else {}
    )
    regime = (
        snapshot.get("market_regime")
        if isinstance(snapshot.get("market_regime"), dict)
        else {}
    )
    scores = (
        snapshot.get("layered_scores")
        if isinstance(snapshot.get("layered_scores"), dict)
        else {}
    )
    entry_context = (
        snapshot.get("entry_order_context")
        if isinstance(snapshot.get("entry_order_context"), dict)
        else {}
    )
    engine_version = recommendation.get("engine_version")
    inferred_scoring = scoring_version_for_legacy_engine(engine_version)

    return {
        "provenance": {
            "recommendation_id": recommendation.get("id"),
            "recommendation_created_at": recommendation.get("created_at"),
            "engine_version": recorded(
                engine_version,
                path="pre_trade_features.provenance.engine_version",
                source="recommendations.engine_version",
                missing_fields=missing_fields,
            ),
            "recorded_app_version": recorded(
                recommendation.get("app_version"),
                path="pre_trade_features.provenance.recorded_app_version",
                source="recommendations.app_version",
                missing_fields=missing_fields,
            ),
            "recorded_scoring_version": recorded(
                recommendation.get("scoring_version"),
                path="pre_trade_features.provenance.recorded_scoring_version",
                source="recommendations.scoring_version",
                missing_fields=missing_fields,
            ),
            "inferred_scoring_cohort": (
                {
                    "status": "inferred_compatibility_only",
                    "value": inferred_scoring,
                    "basis": "engine_version_prefix",
                }
                if inferred_scoring
                else unavailable("engine_version_does_not_map_to_known_scoring")
            ),
            "recorded_data_source_version": recorded(
                recommendation.get("data_source_version"),
                path="pre_trade_features.provenance.recorded_data_source_version",
                source="recommendations.data_source_version",
                missing_fields=missing_fields,
            ),
        },
        "trade_plan": {
            "symbol": recorded(
                operation.get("symbol"),
                path="pre_trade_features.trade_plan.symbol",
                source="operations.symbol",
                missing_fields=missing_fields,
            ),
            "side": recorded(
                operation.get("side"),
                path="pre_trade_features.trade_plan.side",
                source="operations.side",
                missing_fields=missing_fields,
            ),
            "entry": recorded(
                operation.get("entry"),
                path="pre_trade_features.trade_plan.entry",
                source="operations.entry",
                missing_fields=missing_fields,
            ),
            "stop_loss": recorded(
                operation.get("stop_loss"),
                path="pre_trade_features.trade_plan.stop_loss",
                source="operations.stop_loss",
                missing_fields=missing_fields,
            ),
            "take_profit": recorded(
                operation.get("take_profit"),
                path="pre_trade_features.trade_plan.take_profit",
                source="operations.take_profit",
                missing_fields=missing_fields,
            ),
            "margin": recorded(
                operation.get("margin"),
                path="pre_trade_features.trade_plan.margin",
                source="operations.margin",
                missing_fields=missing_fields,
            ),
            "leverage": recorded(
                operation.get("leverage"),
                path="pre_trade_features.trade_plan.leverage",
                source="operations.leverage",
                missing_fields=missing_fields,
            ),
            "time_horizon": recorded(
                snapshot.get("time_horizon"),
                path="pre_trade_features.trade_plan.time_horizon",
                source="recommendations.snapshot_json.time_horizon",
                missing_fields=missing_fields,
                reason="not_recorded_in_pre_trade_snapshot",
            ),
            "horizon_seconds": recorded(
                None,
                path="pre_trade_features.trade_plan.horizon_seconds",
                source="legacy_pre_trade_sources",
                missing_fields=missing_fields,
                reason="concrete_duration_not_recorded_pre_trade",
            ),
        },
        "entry_order_context": {
            "entry_type": recorded(
                entry_context.get("entry_type"),
                path="pre_trade_features.entry_order_context.entry_type",
                source="recommendations.snapshot_json.entry_order_context",
                missing_fields=missing_fields,
            ),
            "trigger_condition": recorded(
                entry_context.get("trigger_condition"),
                path="pre_trade_features.entry_order_context.trigger_condition",
                source="recommendations.snapshot_json.entry_order_context",
                missing_fields=missing_fields,
            ),
            "entry_order_type": recorded(
                entry_context.get("entry_order_type"),
                path="pre_trade_features.entry_order_context.entry_order_type",
                source="recommendations.snapshot_json.entry_order_context",
                missing_fields=missing_fields,
            ),
            "requested_entry": recorded(
                entry_context.get("requested_entry"),
                path="pre_trade_features.entry_order_context.requested_entry",
                source="recommendations.snapshot_json.entry_order_context",
                missing_fields=missing_fields,
            ),
        },
        "analysis_context": {
            "tp_score_legacy": recorded(
                recommendation.get("tp_probability"),
                path="pre_trade_features.analysis_context.tp_score_legacy",
                source="recommendations.tp_probability",
                missing_fields=missing_fields,
            ),
            "sl_score_legacy": recorded(
                recommendation.get("sl_probability"),
                path="pre_trade_features.analysis_context.sl_score_legacy",
                source="recommendations.sl_probability",
                missing_fields=missing_fields,
            ),
            "range_score_legacy": recorded(
                recommendation.get("range_probability"),
                path="pre_trade_features.analysis_context.range_score_legacy",
                source="recommendations.range_probability",
                missing_fields=missing_fields,
            ),
            "probability_semantics": "uncalibrated_legacy_heuristic",
            "setup_grade": recorded(
                recommendation.get("setup_grade"),
                path="pre_trade_features.analysis_context.setup_grade",
                source="recommendations.setup_grade",
                missing_fields=missing_fields,
            ),
            "risk_level": recorded(
                recommendation.get("risk_level"),
                path="pre_trade_features.analysis_context.risk_level",
                source="recommendations.risk_level",
                missing_fields=missing_fields,
            ),
            "confidence": recorded(
                recommendation.get("confidence"),
                path="pre_trade_features.analysis_context.confidence",
                source="recommendations.confidence",
                missing_fields=missing_fields,
            ),
            "training_decision": recorded(
                recommendation.get("training_decision"),
                path="pre_trade_features.analysis_context.training_decision",
                source="recommendations.training_decision",
                missing_fields=missing_fields,
            ),
            "technical_label": recorded(
                technical.get("label"),
                path="pre_trade_features.analysis_context.technical_label",
                source="recommendations.snapshot_json.technical_rating",
                missing_fields=missing_fields,
            ),
            "technical_score": recorded(
                technical.get("score"),
                path="pre_trade_features.analysis_context.technical_score",
                source="recommendations.snapshot_json.technical_rating",
                missing_fields=missing_fields,
            ),
            "market_regime": recorded(
                regime.get("name"),
                path="pre_trade_features.analysis_context.market_regime",
                source="recommendations.snapshot_json.market_regime",
                missing_fields=missing_fields,
            ),
            "direction_score": recorded(
                scores.get("direction_score"),
                path="pre_trade_features.analysis_context.direction_score",
                source="recommendations.snapshot_json.layered_scores",
                missing_fields=missing_fields,
            ),
            "confidence_score": recorded(
                scores.get("confidence_score"),
                path="pre_trade_features.analysis_context.confidence_score",
                source="recommendations.snapshot_json.layered_scores",
                missing_fields=missing_fields,
            ),
            "risk_reward_ratio": recorded(
                snapshot.get("risk_reward_ratio"),
                path="pre_trade_features.analysis_context.risk_reward_ratio",
                source="recommendations.snapshot_json.risk_reward_ratio",
                missing_fields=missing_fields,
            ),
        },
    }


def modern_outcome(
    reconstructed_result: Any,
    evidence_quality: Any,
) -> dict:
    mapped = OUTCOME_MAP.get(str(reconstructed_result))
    if not mapped:
        return {
            "class": "unknown",
            "observation_path": "unknown",
            "status": "excluded",
            "reason": "unmapped_reconstructed_result",
        }
    outcome_class, path = mapped
    if outcome_class == "ambiguous":
        return {
            "class": outcome_class,
            "observation_path": path,
            "status": "excluded",
            "reason": "ambiguous_first_touch",
        }
    if not str(evidence_quality or "").startswith("complete"):
        return {
            "class": outcome_class,
            "observation_path": path,
            "status": "excluded",
            "reason": "incomplete_historical_evidence",
        }
    return {
        "class": outcome_class,
        "observation_path": path,
        "status": "descriptive_only",
        "reason": "legacy_case_without_concrete_pre_trade_horizon_duration",
    }


def build_post_trade_outcomes(
    evaluation: dict,
    operation: dict,
    evidence: dict,
    economics: dict,
    missing_fields: list[dict],
) -> tuple[dict, dict]:
    reconstructed = evaluation.get("reconstructed_plan_result")
    outcome = modern_outcome(reconstructed, evaluation.get("evidence_quality"))
    return (
        {
            "legacy_plan_result": recorded(
                evaluation.get("plan_result"),
                path="post_trade_outcomes.legacy_plan_result",
                source="learning_evaluations.plan_result",
                missing_fields=missing_fields,
            ),
            "reconstructed_plan_result": recorded(
                reconstructed,
                path="post_trade_outcomes.reconstructed_plan_result",
                source="learning_evaluations.reconstructed_plan_result",
                missing_fields=missing_fields,
            ),
            "plan_result_consistency": recorded(
                evaluation.get("plan_result_consistency"),
                path="post_trade_outcomes.plan_result_consistency",
                source="learning_evaluations.plan_result_consistency",
                missing_fields=missing_fields,
            ),
            "modern_outcome": outcome,
            "close_reason": recorded(
                operation.get("close_reason"),
                path="post_trade_outcomes.close_reason",
                source="operations.close_reason",
                missing_fields=missing_fields,
            ),
            "closed_at": recorded(
                operation.get("closed_at"),
                path="post_trade_outcomes.closed_at",
                source="operations.closed_at",
                missing_fields=missing_fields,
            ),
            "evidence": {
                "version": evaluation.get("evidence_version"),
                "source": evaluation.get("evidence_source"),
                "quality": evaluation.get("evidence_quality"),
                "path_resolution": evaluation.get("evidence_path_resolution"),
                "coverage_ratio": evaluation.get("evidence_coverage_ratio"),
                "first_plan_touch": evaluation.get("first_plan_touch"),
                "first_plan_touch_at": evaluation.get("first_plan_touch_at"),
                "audit_sha256": sha256_json(evidence) if evidence else None,
            },
            "excursion": {
                "max_favorable_pct": evaluation.get("max_favorable_pct"),
                "max_adverse_pct": evaluation.get("max_adverse_pct"),
                "max_favorable_pnl": evaluation.get("max_favorable_pnl"),
                "max_adverse_pnl": evaluation.get("max_adverse_pnl"),
            },
            "economics": {
                "version": evaluation.get("economic_normalization_version"),
                "status": evaluation.get("economic_normalization_status"),
                "exclusion_reason": evaluation.get("economic_exclusion_reason"),
                "closure_type": evaluation.get("closure_type"),
                "initial_risk_amount": evaluation.get("initial_risk_amount"),
                "unleveraged_return_pct": evaluation.get(
                    "unleveraged_return_pct"
                ),
                "margin_return_pct": evaluation.get("margin_return_pct"),
                "r_multiple": evaluation.get("r_multiple"),
                "economic_plan_outcome": evaluation.get(
                    "economic_plan_outcome"
                ),
                "final_pnl_secondary": evaluation.get("economic_final_pnl"),
                "audit_sha256": sha256_json(economics) if economics else None,
            },
        },
        outcome,
    )


def build_diagnostic_labels(
    evaluation: dict,
    outcome: dict,
) -> dict:
    return {
        "retrospective_only": True,
        "legacy_labels_preserved": {
            "analysis_verdict": evaluation.get("analysis_verdict"),
            "primary_lesson": evaluation.get("primary_lesson"),
            "failure_type": evaluation.get("failure_type"),
            "user_decision_quality": evaluation.get("user_decision_quality"),
        },
        "modern_taxonomy": {
            "outcome_class": outcome["class"],
            "outcome_status": outcome["status"],
            "exclusion_reason": (
                outcome["reason"] if outcome["status"] == "excluded" else None
            ),
        },
    }


def contains_retrospective_key(value: Any) -> list[str]:
    found = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else key
                if key in RETROSPECTIVE_KEYS:
                    found.append(child_path)
                walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]")

    walk(value, "")
    return sorted(set(found))


def build_legacy_reevaluation(
    case: dict,
    *,
    reviewed_at: str,
) -> dict:
    evaluation, operation, recommendation, evidence, economics = source_records(case)
    missing_fields: list[dict] = []
    original = legacy_original_interpretation(evaluation, recommendation)
    pre_trade = build_pre_trade_features(
        evaluation,
        operation,
        recommendation,
        missing_fields,
    )
    post_trade, outcome = build_post_trade_outcomes(
        evaluation,
        operation,
        evidence,
        economics,
        missing_fields,
    )
    diagnostics = build_diagnostic_labels(evaluation, outcome)
    leakage_paths = contains_retrospective_key(pre_trade)
    if leakage_paths:
        raise ValueError(
            f"Fuga retrospectiva en pre_trade_features: {leakage_paths}"
        )

    predictive_eligibility = {
        "eligible": False,
        "reason": "concrete_pre_trade_horizon_duration_not_recorded",
        "allowed_use": "descriptive_learning_and_hypothesis_generation",
    }
    review_status = (
        "reviewed_excluded"
        if outcome["status"] == "excluded"
        else "reviewed_descriptive_only"
    )
    contract = {
        "version": LEGACY_REVIEW_SCHEMA_VERSION,
        "pre_trade_features": pre_trade,
        "post_trade_outcomes": post_trade,
        "diagnostic_labels": diagnostics,
    }
    source_bundle = {
        "evaluation_record": evaluation,
        "operation_record": operation,
        "recommendation_record": recommendation,
        "evidence_record": evidence,
        "economic_record": economics,
    }
    return {
        "operation_id": int(evaluation["operation_id"]),
        "evaluation_id": int(evaluation["id"]),
        "reevaluation_version": LEGACY_REEVALUATION_VERSION,
        "review_schema_version": LEGACY_REVIEW_SCHEMA_VERSION,
        "review_status": review_status,
        "source_engine_version": recommendation.get("engine_version"),
        "source_learning_schema_version": evaluation.get(
            "learning_schema_version"
        ),
        "source_data_contract_version": evaluation.get("data_contract_version"),
        "source_evaluation_created_at": evaluation.get("created_at"),
        "source_evaluation_updated_at": evaluation.get("updated_at"),
        "source_bundle_sha256": sha256_json(source_bundle),
        "original_interpretation": original,
        "reevaluated_contract": contract,
        "missing_fields": sorted(missing_fields, key=lambda item: item["path"]),
        "predictive_eligibility": predictive_eligibility,
        "outcome_class": outcome["class"],
        "outcome_status": outcome["status"],
        "reviewed_at": reviewed_at,
    }
