from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from db import close_pool, connect, row_to_dict


ENGINE_PATTERN = "rules-v0.12%"
AUDIT_VERSION = "heatmap-historical-preservation-v0.1"


def parse_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def timestamp_text(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def build_audit(db) -> dict:
    rows = db.execute(
        """
        SELECT
            r.id AS recommendation_id,
            r.user_id,
            r.operation_id,
            r.engine_version,
            r.created_at AS recommendation_created_at,
            r.snapshot_json,
            o.status AS operation_status,
            o.close_reason,
            o.closed_at,
            le.reconstructed_plan_result
        FROM recommendations r
        LEFT JOIN operations o ON o.id = r.operation_id
        LEFT JOIN learning_evaluations le ON le.operation_id = o.id
        WHERE r.engine_version LIKE ?
        ORDER BY r.id ASC
        """,
        (ENGINE_PATTERN,),
    ).fetchall()
    cases = []
    for raw in rows:
        row = row_to_dict(raw)
        snapshot = parse_object(row.get("snapshot_json"))
        observation = snapshot.get("liquidation_observation")
        observation_present = isinstance(observation, dict)
        observation_available = (
            observation_present and bool(observation.get("available"))
        )
        operation_status = row.get("operation_status")
        plan_result = row.get("reconstructed_plan_result")
        resolved = plan_result in {
            "plan_success",
            "plan_failure",
            "plan_would_succeed",
            "plan_would_fail",
        } or row.get("close_reason") in {"take_profit", "stop_loss"}
        cases.append(
            {
                "recommendation_id": int(row["recommendation_id"]),
                "user_id": int(row["user_id"]),
                "operation_id": (
                    int(row["operation_id"])
                    if row.get("operation_id") is not None
                    else None
                ),
                "engine_version": row.get("engine_version"),
                "recommendation_created_at": timestamp_text(
                    row.get("recommendation_created_at")
                ),
                "operation_status": operation_status,
                "close_reason": row.get("close_reason"),
                "closed_at": timestamp_text(row.get("closed_at")),
                "reconstructed_plan_result": plan_result,
                "resolved": resolved,
                "liquidation_observation_present": observation_present,
                "liquidation_observation_available": observation_available,
                "liquidation_status": (
                    observation.get("status")
                    if observation_present
                    else "missing"
                ),
                "liquidation_trace": (
                    {
                        "provider": observation.get("provider"),
                        "scope": observation.get("scope"),
                        "schema": observation.get("schema"),
                        "as_of": observation.get("as_of"),
                        "age_seconds": observation.get("age_seconds"),
                        "map_read": observation.get("map_read"),
                        "adverse_squeeze_risk": observation.get(
                            "adverse_squeeze_risk"
                        ),
                        "adverse_to_target_mass_ratio_2pct": observation.get(
                            "adverse_to_target_mass_ratio_2pct"
                        ),
                    }
                    if observation_present
                    else None
                ),
            }
        )
    available = [
        case
        for case in cases
        if case["liquidation_observation_available"]
    ]
    payload = {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_pattern": ENGINE_PATTERN,
        "summary": {
            "recommendations": len(cases),
            "linked_operations": sum(
                case["operation_id"] is not None for case in cases
            ),
            "unlinked_analyses": sum(
                case["operation_id"] is None for case in cases
            ),
            "closed_operations": sum(
                case["operation_status"] == "CLOSED" for case in cases
            ),
            "open_operations": sum(
                case["operation_status"] == "OPEN" for case in cases
            ),
            "observations_present": sum(
                case["liquidation_observation_present"] for case in cases
            ),
            "observations_available": len(available),
            "available_linked_operations": sum(
                case["operation_id"] is not None for case in available
            ),
            "available_closed_operations": sum(
                case["operation_status"] == "CLOSED" for case in available
            ),
            "available_resolved_cases": sum(
                case["resolved"] for case in available
            ),
        },
        "cases": cases,
    }
    payload["audit_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        with connect() as db:
            payload = build_audit(db)
    finally:
        close_pool()
    if args.output:
        args.output.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload["summary"], ensure_ascii=True))


if __name__ == "__main__":
    main()
