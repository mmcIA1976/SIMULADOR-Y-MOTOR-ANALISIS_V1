from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from challenger_engine import (
    CHALLENGER_VERSION,
    HORIZON_LIMITS_SECONDS,
    evaluate_configured_shadow,
    validate_model_artifact,
)
from db import row_to_dict
from versioning import (
    APP_VERSION,
    CHALLENGER_RUNTIME_VERSION,
    ENGINE_VERSION,
    SCORING_VERSION,
)


APP_DIR = Path(__file__).resolve().parent
ADMISSION_MATRIX_PATH = (
    APP_DIR / "auditorias_motor" / "matriz_admisibilidad_reglas_v0_1.json"
)
RUN_ORIGIN_LIVE = "live_analysis"
PRODUCTION_EFFECT_NONE = "none"


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
    if not isinstance(parsed, dict):
        raise ValueError("expected_json_object")
    return parsed


def blocked_result(code: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "blocked",
        "block_code": code,
        "message": message,
        "challenger_version": CHALLENGER_VERSION,
        "probabilities": None,
        "trace": None,
        "details": details or {},
    }


@lru_cache(maxsize=1)
def load_admission_contract() -> tuple[dict[str, str], str]:
    payload = json.loads(ADMISSION_MATRIX_PATH.read_text(encoding="utf-8"))
    matrix_sha256 = str(payload["matrix_sha256"])
    registry = {
        str(rule["id"]): str(rule["challenger_admission"])
        for rule in payload["rules"]
        if rule.get("id") and rule.get("challenger_admission")
    }
    return registry, matrix_sha256


def fixed_horizon_seconds(time_horizon: str) -> int:
    try:
        return int(HORIZON_LIMITS_SECONDS[time_horizon][1])
    except KeyError as exc:
        raise ValueError("unsupported_time_horizon") from exc


def stamp_pre_trade_horizon(snapshot: dict, time_horizon: str) -> dict:
    analysis_at = datetime.now(timezone.utc).isoformat()
    horizon_seconds = fixed_horizon_seconds(time_horizon)
    snapshot["analysis_at"] = analysis_at
    snapshot["evaluation_horizon_seconds"] = horizon_seconds
    snapshot["evaluation_expires_at"] = datetime.fromtimestamp(
        datetime.fromisoformat(analysis_at).timestamp() + horizon_seconds,
        tz=timezone.utc,
    ).isoformat()
    snapshot["evaluation_horizon_policy"] = "selected_frame_upper_bound_v0.1"
    return {
        "analysis_at": analysis_at,
        "horizon_seconds": horizon_seconds,
        "evaluation_expires_at": snapshot["evaluation_expires_at"],
    }


def build_shadow_plan(proposal: Any, snapshot: dict) -> dict:
    entry_order_context = snapshot.get("entry_order_context")
    return {
        "symbol": str(proposal.symbol).upper(),
        "side": str(proposal.side).lower(),
        "entry": float(proposal.entry),
        "take_profit": float(proposal.take_profit),
        "stop_loss": float(proposal.stop_loss),
        "time_horizon": str(proposal.time_horizon),
        "horizon_seconds": snapshot.get("evaluation_horizon_seconds"),
        "analysis_at": snapshot.get("analysis_at"),
        "entry_order_context": (
            entry_order_context
            if isinstance(entry_order_context, dict)
            else {
                "entry_type": getattr(proposal, "entry_type", "market"),
                "trigger_condition": getattr(
                    proposal,
                    "trigger_condition",
                    None,
                ),
                "entry_order_type": getattr(
                    proposal,
                    "entry_order_type",
                    None,
                ),
                "requested_entry": float(proposal.entry),
            }
        ),
    }


def champion_audit_payload(champion_result: dict) -> dict:
    return {
        "engine_version": champion_result.get("engine_version") or ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "tp_probability": champion_result.get("tp_probability"),
        "sl_probability": champion_result.get("sl_probability"),
        "range_probability": champion_result.get("range_probability"),
        "risk_level": champion_result.get("risk_level"),
        "setup_grade": champion_result.get("setup_grade"),
        "confidence": champion_result.get("confidence"),
        "training_decision": champion_result.get("training_decision"),
    }


def read_current_shadow_config(db) -> dict:
    row = row_to_dict(
        db.execute(
            """
            SELECT
                id, action, enabled, selected_model_version,
                previous_event_id, previous_model_version,
                rollback_target_event_id, reason, requested_by,
                app_version, code_commit_sha, created_at
            FROM challenger_shadow_config_events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    )
    if row is None:
        return {
            "id": None,
            "action": "implicit_disabled_default",
            "enabled": False,
            "selected_model_version": None,
            "reason": "no_configuration_event",
        }
    row["enabled"] = bool(row.get("enabled"))
    return row


def load_selected_artifact(db, selected_model_version: str | None) -> tuple[dict, dict | None]:
    if not selected_model_version:
        return {}, None
    row = row_to_dict(
        db.execute(
            """
            SELECT model_version, artifact_sha256, artifact_json
            FROM challenger_model_artifacts
            WHERE model_version = ?
            LIMIT 1
            """,
            (selected_model_version,),
        ).fetchone()
    )
    if row is None:
        return {}, None
    artifact = parse_json_object(row["artifact_json"])
    actual_sha256 = sha256_json(artifact)
    if actual_sha256 != row["artifact_sha256"]:
        return {}, blocked_result(
            "artifact_integrity_mismatch",
            "El hash del artefacto seleccionado no coincide con su contenido.",
            {
                "model_version": selected_model_version,
                "stored_sha256": row["artifact_sha256"],
                "actual_sha256": actual_sha256,
            },
        )
    return {selected_model_version: artifact}, None


def run_key_for(
    recommendation_id: int,
    config_event_id: int | None,
    run_origin: str = RUN_ORIGIN_LIVE,
) -> str:
    return sha256_json(
        {
            "recommendation_id": int(recommendation_id),
            "config_event_id": config_event_id,
            "run_origin": run_origin,
            "challenger_runtime_version": CHALLENGER_RUNTIME_VERSION,
        }
    )


def persist_shadow_run(db, record: dict) -> dict:
    existing = row_to_dict(
        db.execute(
            "SELECT id FROM challenger_shadow_runs WHERE run_key = ? LIMIT 1",
            (record["run_key"],),
        ).fetchone()
    )
    if existing is not None:
        return {
            "status": "idempotent_skip",
            "shadow_run_id": int(existing["id"]),
            "run_key": record["run_key"],
        }

    cursor = db.execute(
        """
        INSERT INTO challenger_shadow_runs (
            run_key, recommendation_id, config_event_id, run_origin,
            champion_engine_version, champion_scoring_version,
            champion_result_json, challenger_version, model_version,
            challenger_status, block_code, challenger_result_json,
            comparison_json, plan_contract_json, feature_snapshot_json,
            source_snapshot_sha256, admission_matrix_sha256,
            production_effect, app_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["run_key"],
            record["recommendation_id"],
            record["config_event_id"],
            record["run_origin"],
            record["champion_engine_version"],
            record["champion_scoring_version"],
            canonical_json(record["champion_result"]),
            record["challenger_version"],
            record.get("model_version"),
            record["challenger_status"],
            record.get("block_code"),
            canonical_json(record["challenger_result"]),
            canonical_json(record["comparison"]),
            canonical_json(record["plan_contract"]),
            canonical_json(record["feature_snapshot"]),
            record["source_snapshot_sha256"],
            record["admission_matrix_sha256"],
            PRODUCTION_EFFECT_NONE,
            APP_VERSION,
        ),
    )
    return {
        "status": "recorded",
        "shadow_run_id": int(cursor.lastrowid),
        "run_key": record["run_key"],
        "challenger_status": record["challenger_status"],
        "block_code": record.get("block_code"),
    }


def execute_live_shadow_run(
    db,
    recommendation_id: int,
    proposal: Any,
    champion_result: dict,
) -> dict:
    snapshot = champion_result.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("champion_snapshot_missing")

    config = read_current_shadow_config(db)
    registry, artifact_error = load_selected_artifact(
        db,
        config.get("selected_model_version"),
    )
    admission_registry, matrix_sha256 = load_admission_contract()
    plan = build_shadow_plan(proposal, snapshot)
    feature_snapshot: dict = {}

    if artifact_error is not None and config.get("enabled") is True:
        challenger_result = artifact_error
    else:
        challenger_result = evaluate_configured_shadow(
            plan=plan,
            feature_snapshot=feature_snapshot,
            artifact_registry=registry,
            shadow_config=config,
            admission_registry=admission_registry,
            expected_matrix_sha256=matrix_sha256,
        )

    champion_result_audit = champion_audit_payload(champion_result)
    comparison = {
        "champion": champion_result_audit,
        "challenger": {
            "status": challenger_result.get("status"),
            "block_code": challenger_result.get("block_code"),
            "challenger_version": challenger_result.get("challenger_version"),
            "model_version": challenger_result.get("model_version"),
            "probabilities": challenger_result.get("probabilities"),
        },
        "production_effect": PRODUCTION_EFFECT_NONE,
        "served_output": "champion",
    }
    run_key = run_key_for(
        recommendation_id=recommendation_id,
        config_event_id=config.get("id"),
    )
    record = {
        "run_key": run_key,
        "recommendation_id": int(recommendation_id),
        "config_event_id": config.get("id"),
        "run_origin": RUN_ORIGIN_LIVE,
        "champion_engine_version": champion_result_audit["engine_version"],
        "champion_scoring_version": champion_result_audit["scoring_version"],
        "champion_result": champion_result_audit,
        "challenger_version": challenger_result.get("challenger_version")
        or CHALLENGER_VERSION,
        "model_version": challenger_result.get("model_version")
        or config.get("selected_model_version"),
        "challenger_status": challenger_result.get("status") or "blocked",
        "block_code": challenger_result.get("block_code"),
        "challenger_result": challenger_result,
        "comparison": comparison,
        "plan_contract": plan,
        "feature_snapshot": feature_snapshot,
        "source_snapshot_sha256": sha256_json(snapshot),
        "admission_matrix_sha256": matrix_sha256,
    }
    return persist_shadow_run(db, record)


def build_user_shadow_audit(db, user_id: int, limit: int = 100) -> dict:
    capped_limit = min(max(int(limit), 1), 250)
    config = read_current_shadow_config(db)
    summary = row_to_dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS total_runs,
                COUNT(*) FILTER (
                    WHERE csr.challenger_status = 'shadow_prediction'
                ) AS shadow_predictions,
                COUNT(*) FILTER (
                    WHERE csr.challenger_status = 'blocked'
                ) AS blocked_runs,
                COUNT(*) FILTER (
                    WHERE csr.production_effect <> 'none'
                ) AS production_effect_violations
            FROM challenger_shadow_runs csr
            JOIN recommendations r ON r.id = csr.recommendation_id
            WHERE r.user_id = ?
            """,
            (user_id,),
        ).fetchone()
    ) or {}
    block_rows = db.execute(
        """
        SELECT csr.block_code, COUNT(*) AS cases
        FROM challenger_shadow_runs csr
        JOIN recommendations r ON r.id = csr.recommendation_id
        WHERE r.user_id = ?
          AND csr.challenger_status = 'blocked'
        GROUP BY csr.block_code
        ORDER BY cases DESC, csr.block_code
        """,
        (user_id,),
    ).fetchall()
    recent_rows = db.execute(
        """
        SELECT
            csr.id, csr.recommendation_id, csr.config_event_id,
            csr.run_origin, csr.challenger_status, csr.block_code,
            csr.model_version, csr.champion_result_json,
            csr.challenger_result_json, csr.comparison_json,
            csr.plan_contract_json, csr.production_effect,
            csr.app_version, csr.created_at,
            r.symbol, r.side, r.time_horizon
        FROM challenger_shadow_runs csr
        JOIN recommendations r ON r.id = csr.recommendation_id
        WHERE r.user_id = ?
        ORDER BY csr.id DESC
        LIMIT ?
        """,
        (user_id, capped_limit),
    ).fetchall()
    runs = []
    for raw_row in recent_rows:
        row = row_to_dict(raw_row) or {}
        runs.append(
            {
                "id": row.get("id"),
                "recommendation_id": row.get("recommendation_id"),
                "config_event_id": row.get("config_event_id"),
                "run_origin": row.get("run_origin"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "time_horizon": row.get("time_horizon"),
                "challenger_status": row.get("challenger_status"),
                "block_code": row.get("block_code"),
                "model_version": row.get("model_version"),
                "champion": parse_json_object(
                    row.get("champion_result_json")
                ),
                "challenger": parse_json_object(
                    row.get("challenger_result_json")
                ),
                "comparison": parse_json_object(
                    row.get("comparison_json")
                ),
                "plan": parse_json_object(row.get("plan_contract_json")),
                "production_effect": row.get("production_effect"),
                "app_version": row.get("app_version"),
                "created_at": row.get("created_at"),
            }
        )
    return {
        "runtime_version": CHALLENGER_RUNTIME_VERSION,
        "champion_engine_version": ENGINE_VERSION,
        "champion_scoring_version": SCORING_VERSION,
        "current_config": {
            "event_id": config.get("id"),
            "action": config.get("action"),
            "enabled": bool(config.get("enabled")),
            "selected_model_version": config.get("selected_model_version"),
            "rollback_target_event_id": config.get(
                "rollback_target_event_id"
            ),
            "reason": config.get("reason"),
            "created_at": config.get("created_at"),
        },
        "summary": {
            "total_runs": int(summary.get("total_runs") or 0),
            "shadow_predictions": int(
                summary.get("shadow_predictions") or 0
            ),
            "blocked_runs": int(summary.get("blocked_runs") or 0),
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


def append_config_event(
    db,
    *,
    action: str,
    enabled: bool,
    selected_model_version: str | None,
    previous_event_id: int | None,
    previous_model_version: str | None,
    reason: str,
    requested_by: str,
    rollback_target_event_id: int | None = None,
    code_commit_sha: str | None = None,
) -> int:
    if not reason.strip():
        raise ValueError("reason_required")
    if not requested_by.strip():
        raise ValueError("requested_by_required")
    cursor = db.execute(
        """
        INSERT INTO challenger_shadow_config_events (
            action, enabled, selected_model_version, previous_event_id,
            previous_model_version, rollback_target_event_id, reason,
            requested_by, app_version, code_commit_sha
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            bool(enabled),
            selected_model_version,
            previous_event_id,
            previous_model_version,
            rollback_target_event_id,
            reason.strip(),
            requested_by.strip(),
            APP_VERSION,
            code_commit_sha,
        ),
    )
    return int(cursor.lastrowid)


def disable_shadow(
    db,
    *,
    reason: str,
    requested_by: str,
    code_commit_sha: str | None = None,
) -> int:
    current = read_current_shadow_config(db)
    return append_config_event(
        db,
        action="kill_switch_disable",
        enabled=False,
        selected_model_version=current.get("selected_model_version"),
        previous_event_id=current.get("id"),
        previous_model_version=current.get("selected_model_version"),
        reason=reason,
        requested_by=requested_by,
        code_commit_sha=code_commit_sha,
    )


def select_shadow_model(
    db,
    *,
    model_version: str,
    reason: str,
    requested_by: str,
    code_commit_sha: str | None = None,
) -> int:
    artifact_row = row_to_dict(
        db.execute(
            """
            SELECT model_version, deployment_state
            FROM challenger_model_artifacts
            WHERE model_version = ?
            LIMIT 1
            """,
            (model_version,),
        ).fetchone()
    )
    if artifact_row is None:
        raise ValueError("model_not_registered")
    if artifact_row.get("deployment_state") != "shadow":
        raise ValueError("model_not_shadow_approved")
    current = read_current_shadow_config(db)
    return append_config_event(
        db,
        action="select_shadow_model",
        enabled=True,
        selected_model_version=model_version,
        previous_event_id=current.get("id"),
        previous_model_version=current.get("selected_model_version"),
        reason=reason,
        requested_by=requested_by,
        code_commit_sha=code_commit_sha,
    )


def rollback_shadow(
    db,
    *,
    reason: str,
    requested_by: str,
    code_commit_sha: str | None = None,
) -> int:
    current = read_current_shadow_config(db)
    target_event_id = current.get("previous_event_id")
    if target_event_id is None:
        raise ValueError("rollback_target_absent")
    target = row_to_dict(
        db.execute(
            """
            SELECT id, enabled, selected_model_version
            FROM challenger_shadow_config_events
            WHERE id = ?
            LIMIT 1
            """,
            (target_event_id,),
        ).fetchone()
    )
    if target is None:
        raise ValueError("rollback_target_not_found")
    return append_config_event(
        db,
        action="rollback",
        enabled=bool(target.get("enabled")),
        selected_model_version=target.get("selected_model_version"),
        previous_event_id=current.get("id"),
        previous_model_version=current.get("selected_model_version"),
        rollback_target_event_id=int(target["id"]),
        reason=reason,
        requested_by=requested_by,
        code_commit_sha=code_commit_sha,
    )


def register_model_artifact(
    db,
    artifact: dict,
    *,
    reason: str,
    registered_by: str,
) -> int:
    if not reason.strip():
        raise ValueError("reason_required")
    if not registered_by.strip():
        raise ValueError("registered_by_required")
    admission_registry, matrix_sha256 = load_admission_contract()
    horizons = artifact.get("supported_horizons") or []
    symbols = artifact.get("supported_symbols") or []
    if not horizons or not symbols:
        raise ValueError("model_scope_missing")
    horizon = str(horizons[0])
    plan = {
        "symbol": str(symbols[0]),
        "side": "long",
        "entry": 100.0,
        "take_profit": 101.0,
        "stop_loss": 99.0,
        "time_horizon": horizon,
        "horizon_seconds": fixed_horizon_seconds(horizon),
        "analysis_at": datetime.now(timezone.utc).isoformat(),
    }
    validation_error = validate_model_artifact(
        artifact,
        plan,
        admission_registry,
        matrix_sha256,
    )
    if validation_error is not None:
        raise ValueError(
            f"invalid_model_artifact:{validation_error.get('block_code')}"
        )
    artifact_sha256 = sha256_json(artifact)
    cursor = db.execute(
        """
        INSERT INTO challenger_model_artifacts (
            model_version, schema_version, deployment_state,
            artifact_sha256, artifact_json, registration_reason,
            registered_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artifact["model_version"],
            artifact["schema_version"],
            artifact["deployment_state"],
            artifact_sha256,
            canonical_json(artifact),
            reason.strip(),
            registered_by.strip(),
        ),
    )
    return int(cursor.lastrowid)
