from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from db import close_pool, connect, row_to_dict


AUDIT_VERSION = "fibonacci-historical-preservation-v0.1"
LEGACY_ENGINES = (
    "rules-v0.7-fibonacci-confluence",
    "rules-v0.8-leverage-neutral-analysis",
    "rules-v0.9-pending-zone-adjusted",
    "rules-v0.10-risk-gated-calibration",
    "rules-v0.11-underweighted-risk-cluster",
    "rules-v0.12-liquidations-observation",
    "rules-v0.12.1-liquidations-readable",
)


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


def timestamp_text(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_audit(db) -> dict:
    placeholders = ",".join("?" for _ in LEGACY_ENGINES)
    rows = db.execute(
        f"""
        SELECT
            r.id AS recommendation_id,
            r.engine_version,
            r.operation_id,
            r.created_at AS recommendation_created_at,
            r.snapshot_json,
            o.status AS operation_status,
            o.close_reason,
            o.closed_at
        FROM recommendations r
        LEFT JOIN operations o ON o.id = r.operation_id
        WHERE r.engine_version IN ({placeholders})
        ORDER BY r.id ASC
        """,
        LEGACY_ENGINES,
    ).fetchall()
    cases = []
    for raw in rows:
        row = row_to_dict(raw)
        snapshot = parse_object(row.get("snapshot_json"))
        fibonacci = snapshot.get("fibonacci_context")
        available = (
            isinstance(fibonacci, dict)
            and bool(fibonacci.get("available"))
        )
        cases.append(
            {
                "recommendation_id": int(row["recommendation_id"]),
                "engine_version": row.get("engine_version"),
                "operation_id": (
                    int(row["operation_id"])
                    if row.get("operation_id") is not None
                    else None
                ),
                "recommendation_created_at": timestamp_text(
                    row.get("recommendation_created_at")
                ),
                "operation_status": row.get("operation_status"),
                "close_reason": row.get("close_reason"),
                "closed_at": timestamp_text(row.get("closed_at")),
                "legacy_fibonacci_available": available,
                "legacy_bias": (
                    fibonacci.get("bias") if available else None
                ),
                "legacy_score": (
                    fibonacci.get("score") if available else None
                ),
                "legacy_entry_zone": (
                    fibonacci.get("entry_zone") if available else None
                ),
                "legacy_probability_adjustment": (
                    fibonacci.get("probability_adjustment")
                    if available
                    else None
                ),
            }
        )
    summary = {
        "recommendations": len(cases),
        "observations_available": sum(
            item["legacy_fibonacci_available"] for item in cases
        ),
        "linked_operations": sum(
            item["operation_id"] is not None for item in cases
        ),
        "closed_operations": sum(
            item["operation_status"] == "CLOSED" for item in cases
        ),
    }
    payload = {
        "audit_version": AUDIT_VERSION,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "legacy_engines": list(LEGACY_ENGINES),
        "summary": summary,
        "reuse_policy": (
            "Preserve case identity only. Recompute the new structural and "
            "Fibonacci observations from pre-trade closed klines. Never reuse "
            "legacy scores, labels or probability adjustments."
        ),
        "cases": cases,
    }
    payload["audit_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=(
            "auditorias_motor/fibonacci_historical_cases_v0_1.json"
        ),
    )
    args = parser.parse_args()
    try:
        with connect() as db:
            payload = build_audit(db)
    finally:
        close_pool()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "path": str(output.resolve()),
                "summary": payload["summary"],
                "audit_sha256": payload["audit_sha256"],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
