from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from db import close_pool, connect, row_to_dict


AUDIT_VERSION = "market-context-historical-preservation-v0.1"


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


def _legacy_context(snapshot: dict) -> tuple[dict, dict]:
    breadth = snapshot.get("market_breadth")
    sentiment = snapshot.get("sentiment")
    if not isinstance(breadth, dict):
        breadth = {}
    if not isinstance(sentiment, dict):
        sentiment = {}
    return breadth, sentiment


def build_audit(db) -> dict:
    rows = db.execute(
        """
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
        ORDER BY r.id ASC
        """
    ).fetchall()
    cases = []
    for raw in rows:
        row = row_to_dict(raw)
        snapshot = parse_object(row.get("snapshot_json"))
        breadth, sentiment = _legacy_context(snapshot)
        breadth_available = any(
            breadth.get(key) is not None
            for key in (
                "advancers_1h_pct",
                "advancers_24h_pct",
                "advancers_7d_pct",
            )
        )
        sentiment_available = (
            sentiment.get("fear_greed_value") is not None
        )
        if not breadth_available and not sentiment_available:
            continue
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
                "legacy_breadth_available": breadth_available,
                "legacy_breadth": breadth if breadth_available else None,
                "legacy_sentiment_available": sentiment_available,
                "legacy_sentiment": (
                    sentiment if sentiment_available else None
                ),
            }
        )
    payload = {
        "audit_version": AUDIT_VERSION,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "recommendations_with_any_context": len(cases),
            "breadth_observations_available": sum(
                case["legacy_breadth_available"] for case in cases
            ),
            "sentiment_observations_available": sum(
                case["legacy_sentiment_available"] for case in cases
            ),
            "linked_operations": sum(
                case["operation_id"] is not None for case in cases
            ),
            "closed_operations": sum(
                case["operation_status"] == "CLOSED" for case in cases
            ),
        },
        "reuse_policy": (
            "Preserve identity and raw legacy values only. Do not reuse old "
            "58/42 or 75/25 labels, points or probability adjustments. "
            "Legacy breadth lacks the complete constituent snapshot and "
            "legacy sentiment lacks the 60-day reference window, so neither "
            "is numerically comparable with the new rules."
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
            "auditorias_motor/"
            "market_context_historical_cases_v0_1.json"
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
