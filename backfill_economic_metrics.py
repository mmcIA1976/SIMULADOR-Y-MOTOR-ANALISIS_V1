from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from app import save_learning_economic_audit
from db import close_pool, connect, row_to_dict
from economic_metrics import (
    group_economic_cases,
    normalize_operation_economics,
    summarize_economic_cases,
)
from versioning import (
    ECONOMIC_NORMALIZATION_VERSION,
    scoring_version_for_legacy_engine,
)


ECONOMIC_COLUMNS = (
    "economic_normalization_version",
    "economic_normalization_status",
    "economic_exclusion_reason",
    "economic_normalized_at",
    "closure_type",
    "notional_amount",
    "initial_risk_pct",
    "initial_risk_amount",
    "unleveraged_return_pct",
    "margin_return_pct",
    "r_multiple",
    "economic_plan_outcome",
    "economic_final_pnl",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normaliza las metricas economicas del aprendizaje.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persiste resultados. Sin esta opcion solo simula.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recalcula una version ya aplicada.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--operation-id", type=int, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def load_candidates(operation_ids: list[int], limit: int | None) -> list[dict]:
    filters = [
        "o.status = 'CLOSED'",
        "COALESCE(o.observation_status, '') != 'OBSERVING'",
    ]
    params: list = []
    if operation_ids:
        placeholders = ", ".join("?" for _ in operation_ids)
        filters.append(f"o.id IN ({placeholders})")
        params.extend(operation_ids)
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(max(0, limit))
    query = f"""
        SELECT
            o.*,
            le.id AS evaluation_id,
            le.plan_result AS evaluation_plan_result,
            le.reconstructed_plan_result AS evaluation_reconstructed_plan_result,
            le.scoring_version AS evaluation_scoring_version,
            r.engine_version AS recommendation_engine_version,
            le.structured_json AS evaluation_structured_json,
            le.economic_normalization_version,
            le.economic_normalization_status,
            le.economic_exclusion_reason,
            le.economic_normalized_at,
            le.closure_type,
            le.notional_amount,
            le.initial_risk_pct,
            le.initial_risk_amount,
            le.unleveraged_return_pct,
            le.margin_return_pct,
            le.r_multiple,
            le.economic_plan_outcome,
            le.economic_final_pnl
        FROM operations o
        JOIN learning_evaluations le ON le.operation_id = o.id
        LEFT JOIN recommendations r ON r.id = le.recommendation_id
        WHERE {" AND ".join(filters)}
        ORDER BY o.closed_at ASC, o.id ASC
        {limit_sql}
    """
    with connect() as db:
        return [row_to_dict(row) for row in db.execute(query, params).fetchall()]


def parse_structured(raw: str | None) -> dict:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def before_payload(operation: dict) -> dict:
    return {key: operation.get(key) for key in ECONOMIC_COLUMNS}


def after_payload(metrics: dict) -> dict:
    return {
        "economic_normalization_version": metrics["version"],
        "economic_normalization_status": metrics["status"],
        "economic_exclusion_reason": metrics.get("exclusion_reason"),
        "economic_normalized_at": metrics["normalized_at"],
        "closure_type": metrics["closure_type"],
        "notional_amount": metrics.get("notional_amount"),
        "initial_risk_pct": metrics.get("initial_risk_pct"),
        "initial_risk_amount": metrics.get("initial_risk_amount"),
        "unleveraged_return_pct": metrics.get("unleveraged_return_pct"),
        "margin_return_pct": metrics.get("margin_return_pct"),
        "r_multiple": metrics.get("r_multiple"),
        "economic_plan_outcome": metrics["economic_plan_outcome"],
        "economic_final_pnl": metrics.get("final_pnl_secondary"),
    }


def apply_metrics_to_structured(structured: dict, metrics: dict) -> dict:
    updated = json.loads(json.dumps(structured))
    updated["economic_metrics"] = metrics
    post_trade = updated.get("post_trade_outcomes")
    if isinstance(post_trade, dict):
        post_trade["economic_metrics"] = metrics
    return updated


def persist_normalization(
    operation: dict,
    metrics: dict,
    before: dict,
    after: dict,
) -> None:
    structured = apply_metrics_to_structured(
        parse_structured(operation.get("evaluation_structured_json")),
        metrics,
    )
    with connect() as db:
        db.execute(
            """
            UPDATE learning_evaluations
            SET economic_normalization_version = ?,
                economic_normalization_status = ?,
                economic_exclusion_reason = ?,
                economic_normalized_at = ?,
                closure_type = ?,
                notional_amount = ?,
                initial_risk_pct = ?,
                initial_risk_amount = ?,
                unleveraged_return_pct = ?,
                margin_return_pct = ?,
                r_multiple = ?,
                economic_plan_outcome = ?,
                economic_final_pnl = ?,
                economic_metrics_json = ?,
                structured_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ?
            """,
            (
                metrics["version"],
                metrics["status"],
                metrics.get("exclusion_reason"),
                metrics["normalized_at"],
                metrics["closure_type"],
                metrics.get("notional_amount"),
                metrics.get("initial_risk_pct"),
                metrics.get("initial_risk_amount"),
                metrics.get("unleveraged_return_pct"),
                metrics.get("margin_return_pct"),
                metrics.get("r_multiple"),
                metrics["economic_plan_outcome"],
                metrics.get("final_pnl_secondary"),
                json.dumps(metrics, ensure_ascii=True),
                json.dumps(structured, ensure_ascii=True),
                operation["id"],
            ),
        )
        save_learning_economic_audit(
            db,
            int(operation["id"]),
            metrics,
            before_payload=before,
            after_payload=after,
        )


def audit_case(operation: dict, metrics: dict) -> dict:
    case = {
        "operation_id": int(operation["id"]),
        "user_id": int(operation["user_id"]),
        "mode": operation.get("mode") or "training",
        "symbol": operation.get("symbol"),
        "side": operation.get("side"),
        "time_horizon": operation.get("time_horizon"),
        "scoring_version": (
            operation.get("evaluation_scoring_version")
            or scoring_version_for_legacy_engine(
                operation.get("recommendation_engine_version")
            )
            or "unknown"
        ),
        "close_reason": operation.get("close_reason"),
        "closed_at": operation.get("closed_at"),
        "final_pnl": round(float(operation.get("final_pnl") or 0), 4),
        "plan_result": operation.get("evaluation_plan_result"),
        "reconstructed_plan_result": operation.get(
            "evaluation_reconstructed_plan_result"
        ),
        "economic_normalization_version": metrics["version"],
        "economic_normalization_status": metrics["status"],
        "economic_exclusion_reason": metrics.get("exclusion_reason"),
        "closure_type": metrics["closure_type"],
        "initial_risk_amount": metrics.get("initial_risk_amount"),
        "unleveraged_return_pct": metrics.get("unleveraged_return_pct"),
        "margin_return_pct": metrics.get("margin_return_pct"),
        "r_multiple": metrics.get("r_multiple"),
        "economic_plan_outcome": metrics["economic_plan_outcome"],
        "economic_final_pnl": metrics.get("final_pnl_secondary"),
    }
    return case


def run(args: argparse.Namespace) -> dict:
    candidates = load_candidates(args.operation_id, args.limit)
    result = {
        "mode": "apply" if args.apply else "dry_run",
        "normalization_version": ECONOMIC_NORMALIZATION_VERSION,
        "candidate_operations": len(candidates),
        "processed": 0,
        "applied": 0,
        "skipped_idempotent": 0,
        "errors": 0,
        "status_counts": Counter(),
        "exclusion_counts": Counter(),
        "closure_type_counts": Counter(),
        "outcome_counts": Counter(),
        "operations": [],
    }
    for operation in candidates:
        if (
            operation.get("economic_normalization_version")
            == ECONOMIC_NORMALIZATION_VERSION
            and not args.force
        ):
            result["skipped_idempotent"] += 1
            continue
        try:
            effective_plan_result = (
                operation.get("evaluation_reconstructed_plan_result")
                or operation.get("evaluation_plan_result")
            )
            metrics = normalize_operation_economics(
                operation,
                effective_plan_result=effective_plan_result,
            )
            before = before_payload(operation)
            after = after_payload(metrics)
            case = audit_case(operation, metrics)
            case["before"] = before
            case["after"] = after
            result["processed"] += 1
            result["status_counts"][metrics["status"]] += 1
            if metrics.get("exclusion_reason"):
                result["exclusion_counts"][metrics["exclusion_reason"]] += 1
            result["closure_type_counts"][metrics["closure_type"]] += 1
            result["outcome_counts"][metrics["economic_plan_outcome"]] += 1
            if args.apply:
                persist_normalization(operation, metrics, before, after)
                result["applied"] += 1
            result["operations"].append(case)
        except Exception as exc:
            result["errors"] += 1
            result["operations"].append(
                {
                    "operation_id": int(operation["id"]),
                    "error": str(exc),
                }
            )

    for key in (
        "status_counts",
        "exclusion_counts",
        "closure_type_counts",
        "outcome_counts",
    ):
        result[key] = dict(result[key])

    comparable_cases = [
        case
        for case in result["operations"]
        if case.get("economic_normalization_status")
    ]
    result["economic_summary"] = summarize_economic_cases(comparable_cases)
    result["cohorts"] = {
        key: group_economic_cases(comparable_cases, key)
        for key in (
            "mode",
            "closure_type",
            "user_id",
            "side",
            "time_horizon",
            "scoring_version",
        )
    }
    return result


def main() -> None:
    args = parse_args()
    try:
        result = run(args)
    finally:
        close_pool()
    rendered = json.dumps(result, indent=2, ensure_ascii=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not args.quiet:
        print(rendered)


if __name__ == "__main__":
    main()
