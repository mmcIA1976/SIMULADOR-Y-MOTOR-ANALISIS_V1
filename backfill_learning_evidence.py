from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from app import reconstruct_operation_historical_evidence, save_learning_evidence_audit
from db import close_pool, connect, row_to_dict
from learning_evidence import apply_evidence_to_structured
from versioning import EVIDENCE_RECONSTRUCTION_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstruye evidencia historica de aprendizaje.")
    parser.add_argument("--apply", action="store_true", help="Persiste resultados. Sin esta opcion solo simula.")
    parser.add_argument("--force", action="store_true", help="Recalcula una version ya aplicada.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--operation-id", type=int, action="append", default=[])
    parser.add_argument("--sleep-ms", type=int, default=75)
    parser.add_argument("--output", type=Path)
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
            le.max_favorable_pct AS evaluation_max_favorable_pct,
            le.max_adverse_pct AS evaluation_max_adverse_pct,
            le.max_favorable_pnl AS evaluation_max_favorable_pnl,
            le.max_adverse_pnl AS evaluation_max_adverse_pnl,
            le.plan_result AS evaluation_plan_result,
            le.analysis_verdict AS evaluation_analysis_verdict,
            le.failure_type AS evaluation_failure_type,
            le.structured_json AS evaluation_structured_json,
            le.evidence_version AS evaluation_evidence_version
        FROM operations o
        JOIN learning_evaluations le ON le.operation_id = o.id
        WHERE {" AND ".join(filters)}
        ORDER BY o.id
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


def touch_label(value) -> str | None:
    if not isinstance(value, dict):
        return None
    return value.get("reason") or value.get("status")


def changed_value(before, after, tolerance: float = 0.00005) -> bool:
    if before is None or after is None:
        return before != after
    try:
        return abs(float(before) - float(after)) > tolerance
    except (TypeError, ValueError):
        return before != after


def reconstruction_record(operation: dict, evidence: dict) -> tuple[dict, dict, str]:
    before = {
        "max_favorable_pct": operation.get("evaluation_max_favorable_pct"),
        "max_adverse_pct": operation.get("evaluation_max_adverse_pct"),
        "max_favorable_pnl": operation.get("evaluation_max_favorable_pnl"),
        "max_adverse_pnl": operation.get("evaluation_max_adverse_pnl"),
        "plan_result": operation.get("evaluation_plan_result"),
        "analysis_verdict": operation.get("evaluation_analysis_verdict"),
        "failure_type": operation.get("evaluation_failure_type"),
    }
    authoritative = str(evidence.get("quality") or "").startswith("complete")
    excursion = evidence.get("trade_excursion") if authoritative else None
    after = {
        **before,
        "max_favorable_pct": (
            excursion.get("max_favorable_pct") if isinstance(excursion, dict) else before["max_favorable_pct"]
        ),
        "max_adverse_pct": (
            excursion.get("max_adverse_pct") if isinstance(excursion, dict) else before["max_adverse_pct"]
        ),
        "max_favorable_pnl": (
            excursion.get("max_favorable_pnl") if isinstance(excursion, dict) else before["max_favorable_pnl"]
        ),
        "max_adverse_pnl": (
            excursion.get("max_adverse_pnl") if isinstance(excursion, dict) else before["max_adverse_pnl"]
        ),
        "reconstructed_plan_result": evidence.get("reconstructed_plan_result"),
    }
    metric_keys = (
        "max_favorable_pct",
        "max_adverse_pct",
        "max_favorable_pnl",
        "max_adverse_pnl",
    )
    changed = [key for key in metric_keys if changed_value(before[key], after[key])]
    return before, after, "changed" if changed else "unchanged"


def persist_reconstruction(
    operation: dict,
    evidence: dict,
    before: dict,
    after: dict,
) -> None:
    structured = apply_evidence_to_structured(
        parse_structured(operation.get("evaluation_structured_json")),
        evidence,
    )
    requested_window = evidence.get("requested_window") or {}
    first_touch = evidence.get("first_plan_touch") or {}
    first_post_close = evidence.get("first_post_close_plan_touch") or {}
    reconstructed_result = evidence.get("reconstructed_plan_result")
    plan_result_consistency = (
        "ambiguous"
        if reconstructed_result == "ambiguous_same_candle"
        else "consistent"
        if reconstructed_result == before.get("plan_result")
        else "mismatch"
        if reconstructed_result
        else None
    )
    with connect() as db:
        db.execute(
            """
            UPDATE learning_evaluations
            SET max_favorable_pct = ?,
                max_adverse_pct = ?,
                max_favorable_pnl = ?,
                max_adverse_pnl = ?,
                evidence_version = ?,
                evidence_source = ?,
                evidence_quality = ?,
                evidence_status = ?,
                evidence_path_resolution = ?,
                evidence_start_at = ?,
                evidence_end_at = ?,
                evidence_candle_count = ?,
                evidence_expected_candles = ?,
                evidence_coverage_ratio = ?,
                first_plan_touch = ?,
                first_plan_touch_at = ?,
                first_post_close_touch = ?,
                first_post_close_touch_at = ?,
                reconstructed_plan_result = ?,
                plan_result_consistency = ?,
                evidence_reconstructed_at = ?,
                evidence_json = ?,
                structured_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE operation_id = ?
            """,
            (
                after["max_favorable_pct"],
                after["max_adverse_pct"],
                after["max_favorable_pnl"],
                after["max_adverse_pnl"],
                evidence.get("version"),
                evidence.get("source"),
                evidence.get("quality"),
                evidence.get("status"),
                evidence.get("path_resolution"),
                requested_window.get("started_at"),
                requested_window.get("plan_end_at"),
                evidence.get("candle_count"),
                evidence.get("expected_candle_count"),
                evidence.get("coverage_ratio"),
                touch_label(first_touch),
                first_touch.get("touched_at"),
                touch_label(first_post_close),
                first_post_close.get("touched_at"),
                reconstructed_result,
                plan_result_consistency,
                evidence.get("reconstructed_at"),
                json.dumps(evidence, ensure_ascii=True),
                json.dumps(structured, ensure_ascii=True),
                operation["id"],
            ),
        )
        save_learning_evidence_audit(
            db,
            int(operation["id"]),
            evidence,
            before_payload=before,
            after_payload=after,
        )


def run(args: argparse.Namespace) -> dict:
    candidates = load_candidates(args.operation_id, args.limit)
    result = {
        "mode": "apply" if args.apply else "dry_run",
        "reconstruction_version": EVIDENCE_RECONSTRUCTION_VERSION,
        "candidate_operations": len(candidates),
        "processed": 0,
        "applied": 0,
        "skipped_idempotent": 0,
        "errors": 0,
        "quality_counts": Counter(),
        "status_counts": Counter(),
        "path_resolution_counts": Counter(),
        "consistency_counts": Counter(),
        "evaluation_consistency_counts": Counter(),
        "metric_change_counts": Counter(),
        "operations": [],
    }
    for operation in candidates:
        if operation.get("evaluation_evidence_version") == EVIDENCE_RECONSTRUCTION_VERSION and not args.force:
            result["skipped_idempotent"] += 1
            continue
        try:
            evidence = reconstruct_operation_historical_evidence(operation)
            before, after, metric_status = reconstruction_record(operation, evidence)
            changes = [
                key
                for key in (
                    "max_favorable_pct",
                    "max_adverse_pct",
                    "max_favorable_pnl",
                    "max_adverse_pnl",
                )
                if changed_value(before[key], after[key])
            ]
            record = {
                "operation_id": int(operation["id"]),
                "symbol": operation["symbol"],
                "side": operation["side"],
                "close_reason": operation.get("close_reason"),
                "quality": evidence.get("quality"),
                "status": evidence.get("status"),
                "path_resolution": evidence.get("path_resolution"),
                "recorded_result_consistency": evidence.get("recorded_result_consistency"),
                "reconstructed_plan_result": evidence.get("reconstructed_plan_result"),
                "evaluation_plan_result_consistency": (
                    "ambiguous"
                    if evidence.get("reconstructed_plan_result") == "ambiguous_same_candle"
                    else "consistent"
                    if evidence.get("reconstructed_plan_result") == before.get("plan_result")
                    else "mismatch"
                ),
                "candle_count": evidence.get("candle_count"),
                "expected_candle_count": evidence.get("expected_candle_count"),
                "coverage_ratio": evidence.get("coverage_ratio"),
                "metric_status": metric_status,
                "changed_metrics": changes,
                "before": before,
                "after": after,
                "first_plan_touch": evidence.get("first_plan_touch"),
                "first_post_close_plan_touch": evidence.get("first_post_close_plan_touch"),
                "error": evidence.get("error") or evidence.get("fetch_error"),
            }
            result["processed"] += 1
            result["quality_counts"][str(evidence.get("quality"))] += 1
            result["status_counts"][str(evidence.get("status"))] += 1
            result["path_resolution_counts"][str(evidence.get("path_resolution"))] += 1
            result["consistency_counts"][str(evidence.get("recorded_result_consistency"))] += 1
            result["evaluation_consistency_counts"][record["evaluation_plan_result_consistency"]] += 1
            result["metric_change_counts"][metric_status] += 1
            result["operations"].append(record)
            if args.apply:
                persist_reconstruction(operation, evidence, before, after)
                result["applied"] += 1
        except Exception as exc:
            result["errors"] += 1
            result["operations"].append({
                "operation_id": int(operation["id"]),
                "symbol": operation.get("symbol"),
                "error": str(exc),
            })
        if args.sleep_ms > 0:
            time.sleep(args.sleep_ms / 1000)

    for key in (
        "quality_counts",
        "status_counts",
        "path_resolution_counts",
        "consistency_counts",
        "evaluation_consistency_counts",
        "metric_change_counts",
    ):
        result[key] = dict(result[key])
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
    print(rendered)


if __name__ == "__main__":
    main()
