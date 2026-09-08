from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

import m8_evaluation as m8


COUNTERFACTUAL_EVALUATOR_VERSION = (
    "recommendation-counterfactual-evaluator-v0.1"
)
COUNTERFACTUAL_SCHEMA_VERSION = (
    "recommendation-counterfactual-evaluation-v0.1"
)
LEGACY_PROXY_EVALUATOR_VERSION = (
    "recommendation-legacy-upper-bound-proxy-evaluator-v0.1"
)
LEGACY_PROXY_SCHEMA_VERSION = (
    "recommendation-legacy-upper-bound-proxy-v0.1"
)
COUNTERFACTUAL_SOURCE = "binance_usdm_futures_klines"
COUNTERFACTUAL_PRODUCTION_EFFECT = "none"
MAX_FEATURE_PAYLOAD_BYTES = 4096
PROBABILITY_MASS_TOLERANCE = 1.1e-6


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _entry_type(snapshot: dict) -> str:
    context = snapshot.get("entry_order_context")
    if isinstance(context, dict) and context.get("entry_type"):
        return str(context["entry_type"]).lower()
    if snapshot.get("entry_type"):
        return str(snapshot["entry_type"]).lower()
    return "market"


def _valid_geometry(side: str, entry: float, take_profit: float, stop_loss: float) -> bool:
    if side == "long":
        return stop_loss < entry < take_profit
    if side == "short":
        return take_profit < entry < stop_loss
    return False


def _probabilities(row: dict) -> dict | None:
    values = {
        m8.CLASSES[0]: _safe_float(row.get("tp_probability")),
        m8.CLASSES[1]: _safe_float(row.get("sl_probability")),
        m8.CLASSES[2]: _safe_float(row.get("range_probability")),
    }
    if any(value is None or value < 0 or value > 1 for value in values.values()):
        return None
    if not math.isclose(
        math.fsum(values.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_MASS_TOLERANCE,
    ):
        return None
    return values


def normalize_unlinked_recommendation(
    raw: dict,
    *,
    captured_at: datetime,
) -> tuple[dict | None, str | None]:
    """Build an exact, pre-trade-only contract for offline evaluation.

    A rejection code is returned instead of guessing missing plan fields. The
    legacy-plan recovery promised for the next batch is intentionally kept out
    of this exact-contract evaluator.
    """
    if raw.get("operation_id") is not None:
        return None, "operation_already_linked"
    snapshot = m8.parse_json_object(raw.get("snapshot_json"))
    if not snapshot:
        return None, "snapshot_missing_or_invalid"
    if _entry_type(snapshot) != "market":
        return None, "entry_type_not_market"

    symbol = str(raw.get("symbol") or snapshot.get("symbol") or "").upper()
    side = str(raw.get("side") or snapshot.get("side") or "").lower()
    time_horizon = str(
        raw.get("time_horizon") or snapshot.get("time_horizon") or ""
    )
    if not symbol or side not in {"long", "short"}:
        return None, "identity_invalid"
    if time_horizon not in m8.HORIZON_SECONDS:
        return None, "time_horizon_unsupported"

    analysis_at = m8.parse_utc(snapshot.get("analysis_at"))
    data_cutoff_at = m8.parse_utc(snapshot.get("data_cutoff_at"))
    evaluation_expires_at = m8.parse_utc(
        snapshot.get("evaluation_expires_at")
    )
    try:
        horizon_seconds = int(snapshot.get("evaluation_horizon_seconds"))
    except (TypeError, ValueError):
        horizon_seconds = 0
    if analysis_at is None:
        return None, "analysis_at_missing"
    if data_cutoff_at is None:
        return None, "data_cutoff_at_missing"
    if data_cutoff_at > analysis_at:
        return None, "data_cutoff_after_analysis"
    if evaluation_expires_at is None or horizon_seconds <= 0:
        return None, "exact_expiry_missing"
    expected_expiry = analysis_at + timedelta(seconds=horizon_seconds)
    if abs((evaluation_expires_at - expected_expiry).total_seconds()) > 1:
        return None, "expiry_contract_mismatch"
    resolved_horizon = m8.resolve_horizon(snapshot, time_horizon)
    if not resolved_horizon.get("formal_eligible"):
        return None, "exact_horizon_not_formal"
    if evaluation_expires_at > captured_at:
        return None, "not_matured"

    entry = _safe_float(snapshot.get("entry"))
    take_profit = _safe_float(snapshot.get("take_profit"))
    stop_loss = _safe_float(snapshot.get("stop_loss"))
    if entry is None or take_profit is None or stop_loss is None:
        return None, "plan_levels_missing"
    if min(entry, take_profit, stop_loss) <= 0:
        return None, "plan_levels_non_positive"
    if not _valid_geometry(side, entry, take_profit, stop_loss):
        return None, "plan_geometry_invalid"
    probabilities = _probabilities(raw)
    if probabilities is None:
        return None, "probabilities_invalid"

    recommendation_id = raw.get("recommendation_id", raw.get("id"))
    try:
        recommendation_id = int(recommendation_id)
        user_id = int(raw["user_id"])
    except (KeyError, TypeError, ValueError):
        return None, "database_identity_invalid"
    source_snapshot_sha256 = m8.payload_sha256(snapshot)
    return {
        "recommendation_id": recommendation_id,
        "operation_id": None,
        "user_id": user_id,
        "symbol": symbol,
        "side": side,
        "time_horizon": time_horizon,
        "engine_version": str(raw.get("engine_version") or "unknown"),
        "scoring_version": raw.get("scoring_version"),
        "analysis_at": _iso_utc(analysis_at),
        "data_cutoff_at": _iso_utc(data_cutoff_at),
        "expiry_at": _iso_utc(evaluation_expires_at),
        "horizon_seconds": horizon_seconds,
        "horizon_status": resolved_horizon["status"],
        "entry": entry,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "stored_probabilities": probabilities,
        "source_snapshot_sha256": source_snapshot_sha256,
        "evaluator_version": COUNTERFACTUAL_EVALUATOR_VERSION,
        "schema_version": COUNTERFACTUAL_SCHEMA_VERSION,
        "contract_quality": "exact",
        "formal_learning_eligible": True,
        "analysis_at_source": "snapshot.analysis_at",
        "data_cutoff_source": "snapshot.data_cutoff_at",
        "plan_source": "snapshot.explicit_levels",
        "horizon_source": "snapshot.evaluation_horizon_seconds",
        "_snapshot": snapshot,
    }, None


def normalize_legacy_market_recommendation(
    raw: dict,
    *,
    captured_at: datetime,
) -> tuple[dict | None, str | None]:
    """Recover a legacy market plan without presenting it as exact time data."""
    if raw.get("operation_id") is not None:
        return None, "operation_already_linked"
    snapshot = m8.parse_json_object(raw.get("snapshot_json"))
    if not snapshot:
        return None, "snapshot_missing_or_invalid"
    if _entry_type(snapshot) != "market":
        return None, "entry_type_not_market"
    if m8.parse_utc(snapshot.get("analysis_at")) is not None:
        return None, "not_legacy_missing_analysis_at"

    symbol = str(raw.get("symbol") or snapshot.get("symbol") or "").upper()
    side = str(raw.get("side") or snapshot.get("side") or "").lower()
    time_horizon = str(
        raw.get("time_horizon") or snapshot.get("time_horizon") or ""
    )
    if not symbol or side not in {"long", "short"}:
        return None, "identity_invalid"
    if time_horizon not in m8.HORIZON_SECONDS:
        return None, "time_horizon_unsupported"

    analysis_at = m8.parse_utc(raw.get("created_at"))
    if analysis_at is None:
        return None, "created_at_proxy_missing"
    horizon = m8.resolve_horizon(snapshot, time_horizon)
    horizon_seconds = horizon.get("seconds")
    if horizon_seconds is None or horizon.get("formal_eligible"):
        return None, "legacy_upper_bound_unavailable"
    evaluation_expires_at = analysis_at + timedelta(
        seconds=int(horizon_seconds)
    )
    if evaluation_expires_at > captured_at:
        return None, "not_matured"

    context = snapshot.get("entry_order_context")
    if not isinstance(context, dict):
        return None, "legacy_requested_entry_missing"
    entry = _safe_float(context.get("requested_entry"))
    risk_pct = _safe_float(snapshot.get("risk_distance_pct"))
    reward_pct = _safe_float(snapshot.get("reward_distance_pct"))
    stored_rr = _safe_float(snapshot.get("risk_reward_ratio"))
    if entry is None or entry <= 0:
        return None, "legacy_requested_entry_missing"
    if (
        risk_pct is None
        or reward_pct is None
        or risk_pct <= 0
        or reward_pct <= 0
        or stored_rr is None
    ):
        return None, "legacy_plan_distances_missing"
    expected_rr = reward_pct / risk_pct
    if not math.isclose(
        stored_rr,
        expected_rr,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        return None, "legacy_risk_reward_inconsistent"

    if side == "long":
        take_profit = entry * (1 + reward_pct / 100)
        stop_loss = entry * (1 - risk_pct / 100)
    else:
        take_profit = entry * (1 - reward_pct / 100)
        stop_loss = entry * (1 + risk_pct / 100)
    if not _valid_geometry(side, entry, take_profit, stop_loss):
        return None, "plan_geometry_invalid"
    probabilities = _probabilities(raw)
    if probabilities is None:
        return None, "probabilities_invalid"

    recommendation_id = raw.get("recommendation_id", raw.get("id"))
    try:
        recommendation_id = int(recommendation_id)
        user_id = int(raw["user_id"])
    except (KeyError, TypeError, ValueError):
        return None, "database_identity_invalid"
    source_snapshot_sha256 = m8.payload_sha256(snapshot)
    return {
        "recommendation_id": recommendation_id,
        "operation_id": None,
        "user_id": user_id,
        "symbol": symbol,
        "side": side,
        "time_horizon": time_horizon,
        "engine_version": str(raw.get("engine_version") or "unknown"),
        "scoring_version": raw.get("scoring_version"),
        "analysis_at": _iso_utc(analysis_at),
        "data_cutoff_at": _iso_utc(analysis_at),
        "expiry_at": _iso_utc(evaluation_expires_at),
        "horizon_seconds": int(horizon_seconds),
        "horizon_status": horizon["status"],
        "entry": entry,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "stored_probabilities": probabilities,
        "source_snapshot_sha256": source_snapshot_sha256,
        "evaluator_version": LEGACY_PROXY_EVALUATOR_VERSION,
        "schema_version": LEGACY_PROXY_SCHEMA_VERSION,
        "contract_quality": "legacy_upper_bound_proxy",
        "formal_learning_eligible": False,
        "analysis_at_source": "recommendations.created_at_proxy",
        "data_cutoff_source": (
            "legacy_snapshot_precedes_created_at_without_source_timestamps"
        ),
        "plan_source": (
            "snapshot.requested_entry_plus_risk_reward_distances"
        ),
        "horizon_source": horizon["source"],
        "_snapshot": snapshot,
    }, None


def evaluate_counterfactual_records(
    records: list[dict],
    *,
    captured_at: datetime,
    pretrade_enricher: Callable[..., list[dict]] = m8.enrich_pretrade_features,
    outcome_enricher: Callable[..., list[dict]] = m8.enrich_outcomes,
) -> list[dict]:
    if not records:
        return records
    pretrade_enricher(records)
    outcome_enricher(records, captured_at=captured_at)
    return records


def build_counterfactual_payload(record: dict) -> dict:
    pretrade = record.get("pretrade")
    outcome = record.get("outcome")
    if not isinstance(pretrade, dict) or not isinstance(outcome, dict):
        raise ValueError("counterfactual_record_not_enriched")
    pretrade_status = str(pretrade.get("status") or "missing")
    outcome_status = str(outcome.get("status") or "missing")
    outcome_label = outcome.get("label")
    if outcome_status != "resolved" or outcome_label not in m8.CLASSES:
        evaluation_status = "excluded"
        exclusion_code = f"outcome_{outcome_status}"
        outcome_label = None
    else:
        evaluation_status = "evaluated"
        exclusion_code = None

    feature_values = (
        pretrade.get("feature_values")
        if isinstance(pretrade.get("feature_values"), dict)
        else {}
    )
    feature_values_json = m8.canonical_json(feature_values)
    feature_payload_bytes = len(feature_values_json.encode("utf-8"))
    if feature_payload_bytes > MAX_FEATURE_PAYLOAD_BYTES:
        raise ValueError("counterfactual_feature_payload_too_large")
    evaluator_version = str(
        record.get("evaluator_version")
        or COUNTERFACTUAL_EVALUATOR_VERSION
    )
    schema_version = str(
        record.get("schema_version") or COUNTERFACTUAL_SCHEMA_VERSION
    )
    contract_quality = str(record.get("contract_quality") or "exact")
    formal_learning_eligible = bool(
        record.get("formal_learning_eligible", True)
    )
    analysis_at_source = str(
        record.get("analysis_at_source") or "snapshot.analysis_at"
    )
    data_cutoff_source = str(
        record.get("data_cutoff_source") or "snapshot.data_cutoff_at"
    )
    plan_source = str(
        record.get("plan_source") or "snapshot.explicit_levels"
    )
    horizon_source = str(
        record.get("horizon_source")
        or "snapshot.evaluation_horizon_seconds"
    )
    run_key = m8.payload_sha256(
        {
            "recommendation_id": int(record["recommendation_id"]),
            "evaluator_version": evaluator_version,
            "source_snapshot_sha256": record["source_snapshot_sha256"],
        }
    )
    result_identity = {
        "run_key": run_key,
        "pretrade_status": pretrade_status,
        "feature_values": feature_values,
        "outcome_status": outcome_status,
        "outcome_label": outcome_label,
        "first_touch_at": outcome.get("first_touch_at"),
        "coverage_ratio": outcome.get("coverage_ratio"),
        "market_sha256": outcome.get("market_sha256"),
    }
    if contract_quality != "exact":
        result_identity["contract_provenance"] = {
            "contract_quality": contract_quality,
            "formal_learning_eligible": formal_learning_eligible,
            "analysis_at_source": analysis_at_source,
            "data_cutoff_source": data_cutoff_source,
            "plan_source": plan_source,
            "horizon_source": horizon_source,
        }
    result_hash = m8.payload_sha256(result_identity)
    probabilities = record["stored_probabilities"]
    return {
        "run_key": run_key,
        "recommendation_id": int(record["recommendation_id"]),
        "user_id": int(record["user_id"]),
        "evaluator_version": evaluator_version,
        "schema_version": schema_version,
        "contract_quality": contract_quality,
        "formal_learning_eligible": formal_learning_eligible,
        "analysis_at_source": analysis_at_source,
        "data_cutoff_source": data_cutoff_source,
        "plan_source": plan_source,
        "horizon_source": horizon_source,
        "source_engine_version": record["engine_version"],
        "source_scoring_version": record.get("scoring_version"),
        "symbol": record["symbol"],
        "side": record["side"],
        "time_horizon": record["time_horizon"],
        "analysis_at": record["analysis_at"],
        "data_cutoff_at": record["data_cutoff_at"],
        "evaluation_expires_at": record["expiry_at"],
        "horizon_seconds": int(record["horizon_seconds"]),
        "entry": float(record["entry"]),
        "take_profit": float(record["take_profit"]),
        "stop_loss": float(record["stop_loss"]),
        "tp_probability": probabilities[m8.CLASSES[0]],
        "sl_probability": probabilities[m8.CLASSES[1]],
        "range_probability": probabilities[m8.CLASSES[2]],
        "evaluation_status": evaluation_status,
        "exclusion_code": exclusion_code,
        "pretrade_status": pretrade_status,
        "pretrade_interval": pretrade.get("interval"),
        "feature_values_json": feature_values_json,
        "feature_payload_bytes": feature_payload_bytes,
        "outcome_status": outcome_status,
        "outcome_label": outcome_label,
        "first_touch_at": outcome.get("first_touch_at"),
        "coverage_ratio": outcome.get("coverage_ratio"),
        "candle_count": outcome.get("candle_count"),
        "expected_candle_count": outcome.get("expected_candle_count"),
        "market_sha256": outcome.get("market_sha256"),
        "source_snapshot_sha256": record["source_snapshot_sha256"],
        "result_sha256": result_hash,
        "evidence_source": COUNTERFACTUAL_SOURCE,
        "production_effect": COUNTERFACTUAL_PRODUCTION_EFFECT,
    }


def summarize_counterfactual_run(
    *,
    raw_count: int,
    records: Iterable[dict],
    rejection_codes: Counter,
    payloads: Iterable[dict],
    fetch_errors: Iterable[dict] = (),
) -> dict:
    records = list(records)
    payloads = list(payloads)
    fetch_errors = list(fetch_errors)
    evaluator_versions = sorted(
        {payload["evaluator_version"] for payload in payloads}
    )
    schema_versions = sorted(
        {payload["schema_version"] for payload in payloads}
    )
    return {
        "evaluator_version": (
            evaluator_versions[0]
            if len(evaluator_versions) == 1
            else evaluator_versions or COUNTERFACTUAL_EVALUATOR_VERSION
        ),
        "schema_version": (
            schema_versions[0]
            if len(schema_versions) == 1
            else schema_versions or COUNTERFACTUAL_SCHEMA_VERSION
        ),
        "production_effect": COUNTERFACTUAL_PRODUCTION_EFFECT,
        "raw_recommendations": int(raw_count),
        "accepted_contracts": len(records),
        "exact_contract_matured": sum(
            record.get("contract_quality", "exact") == "exact"
            for record in records
        ),
        "formal_learning_eligible": sum(
            record.get("formal_learning_eligible", True) is True
            for record in records
        ),
        "legacy_proxy_contracts": sum(
            record.get("contract_quality") == "legacy_upper_bound_proxy"
            for record in records
        ),
        "contract_rejections": sum(rejection_codes.values()),
        "contract_rejection_codes": dict(sorted(rejection_codes.items())),
        "evaluated": sum(
            payload["evaluation_status"] == "evaluated"
            for payload in payloads
        ),
        "pretrade_features_reconstructed": sum(
            payload["pretrade_status"] == "evaluated"
            for payload in payloads
        ),
        "excluded_after_market_reconstruction": sum(
            payload["evaluation_status"] == "excluded"
            for payload in payloads
        ),
        "market_reconstruction_exclusion_codes": dict(
            Counter(
                payload["exclusion_code"]
                for payload in payloads
                if payload.get("exclusion_code")
            )
        ),
        "outcome_labels": dict(
            Counter(
                payload["outcome_label"]
                for payload in payloads
                if payload.get("outcome_label")
            )
        ),
        "fetch_error_groups": fetch_errors,
        "compact_payload_bytes": sum(
            payload["feature_payload_bytes"] for payload in payloads
        ),
    }


def persist_counterfactual_payload(db, payload: dict) -> bool:
    columns = tuple(payload)
    placeholders = ", ".join("?" for _ in columns)
    cursor = db.execute(
        f"""
        INSERT INTO recommendation_counterfactual_evaluations (
            {", ".join(columns)}
        ) VALUES ({placeholders})
        ON CONFLICT (recommendation_id, evaluator_version) DO NOTHING
        RETURNING id
        """,
        tuple(payload[column] for column in columns),
    )
    inserted = cursor.fetchone()
    if inserted:
        return True
    existing = db.execute(
        """
        SELECT run_key, source_snapshot_sha256, result_sha256
        FROM recommendation_counterfactual_evaluations
        WHERE recommendation_id = ? AND evaluator_version = ?
        LIMIT 1
        """,
        (
            payload["recommendation_id"],
            payload["evaluator_version"],
        ),
    ).fetchone()
    if not existing:
        raise RuntimeError("counterfactual_conflict_without_existing_row")
    if (
        existing["run_key"] != payload["run_key"]
        or existing["source_snapshot_sha256"]
        != payload["source_snapshot_sha256"]
        or existing["result_sha256"] != payload["result_sha256"]
    ):
        raise RuntimeError("counterfactual_existing_result_mismatch")
    return False
