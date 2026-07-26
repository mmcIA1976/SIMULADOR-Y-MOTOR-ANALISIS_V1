from __future__ import annotations

import json
from datetime import datetime, timezone

from analysis_engine import TradeProposal
from db import close_pool, connect, row_to_dict
from shadow_runtime import execute_live_shadow_run, fixed_horizon_seconds
from versioning import (
    APP_VERSION,
    DATA_CONTRACT_VERSION,
    DATA_SOURCE_VERSION,
    ENGINE_VERSION,
    LEARNING_SCHEMA_VERSION,
    SCORING_VERSION,
)


def canary_result() -> dict:
    return {
        "analysis_type": "transactional_shadow_canary",
        "engine_version": ENGINE_VERSION,
        "tp_probability": 0.5,
        "sl_probability": 0.45,
        "range_probability": 0.05,
        "risk_level": "canary",
        "setup_grade": "N/A",
        "confidence": "canary",
        "training_decision": "canary",
        "parameter_advice": {},
        "reasons": [],
        "alerts": [],
        "snapshot": {
            "analysis_at": datetime.now(timezone.utc).isoformat(),
            "evaluation_horizon_seconds": fixed_horizon_seconds(
                "intraday_short"
            ),
            "evaluation_horizon_policy": "selected_frame_upper_bound_v0.1",
            "canary": True,
        },
    }


def main() -> int:
    proposal = TradeProposal(
        symbol="BTCUSDT",
        side="long",
        time_horizon="intraday_short",
        entry=100.0,
        margin=100.0,
        leverage=1.0,
        stop_loss=99.0,
        take_profit=102.0,
    )
    result = canary_result()
    run_key = None
    recommendation_id = None
    observed = None
    with connect() as db:
        try:
            user = row_to_dict(
                db.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
            )
            if user is None:
                raise RuntimeError("canary_requires_existing_user")
            cursor = db.execute(
                """
                INSERT INTO recommendations (
                    operation_id, user_id, analysis_type, symbol, side,
                    tp_probability, sl_probability, range_probability,
                    risk_level, setup_grade, confidence, training_decision,
                    time_horizon, parameter_advice_json, reasons_json,
                    alerts_json, snapshot_json, analysis_json, engine_version,
                    app_version, scoring_version, learning_schema_version,
                    data_source_version, data_contract_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None,
                    user["id"],
                    result["analysis_type"],
                    proposal.symbol,
                    proposal.side,
                    result["tp_probability"],
                    result["sl_probability"],
                    result["range_probability"],
                    result["risk_level"],
                    result["setup_grade"],
                    result["confidence"],
                    result["training_decision"],
                    proposal.time_horizon,
                    "{}",
                    "[]",
                    "[]",
                    json.dumps(result["snapshot"]),
                    json.dumps(result),
                    ENGINE_VERSION,
                    APP_VERSION,
                    SCORING_VERSION,
                    LEARNING_SCHEMA_VERSION,
                    DATA_SOURCE_VERSION,
                    DATA_CONTRACT_VERSION,
                ),
            )
            recommendation_id = int(cursor.lastrowid)
            audit = execute_live_shadow_run(
                db,
                recommendation_id,
                proposal,
                result,
            )
            run_key = audit["run_key"]
            observed = row_to_dict(
                db.execute(
                    """
                    SELECT challenger_status, block_code, production_effect
                    FROM challenger_shadow_runs
                    WHERE run_key = ?
                    """,
                    (run_key,),
                ).fetchone()
            )
        finally:
            db.rollback()

    with connect() as db:
        persisted_run = db.execute(
            "SELECT COUNT(*) AS count FROM challenger_shadow_runs WHERE run_key = ?",
            (run_key,),
        ).fetchone()["count"]
        persisted_recommendation = db.execute(
            "SELECT COUNT(*) AS count FROM recommendations WHERE id = ?",
            (recommendation_id,),
        ).fetchone()["count"]

    output = {
        "transactional_canary": observed,
        "persisted_run_rows": int(persisted_run),
        "persisted_recommendation_rows": int(persisted_recommendation),
        "rollback_verified": (
            int(persisted_run) == 0 and int(persisted_recommendation) == 0
        ),
    }
    print(json.dumps(output, ensure_ascii=True, indent=2))
    close_pool()
    return 0 if output["rollback_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
