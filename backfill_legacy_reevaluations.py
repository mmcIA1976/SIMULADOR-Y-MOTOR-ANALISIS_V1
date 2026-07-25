from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from db import close_pool, connect, row_to_dict
from legacy_reevaluation import build_legacy_reevaluation, utc_now_iso
from versioning import LEGACY_REEVALUATION_VERSION


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reevalua aprendizaje legacy mediante revisiones append-only.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Inserta revisiones nuevas. Sin esta opcion solo simula.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--operation-id", type=int, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def table_exists(db) -> bool:
    row = db.execute(
        "SELECT to_regclass('public.learning_legacy_reevaluations') AS table_name"
    ).fetchone()
    parsed = row_to_dict(row)
    return bool(parsed and parsed.get("table_name"))


def existing_operation_ids(db) -> set[int]:
    if not table_exists(db):
        return set()
    return {
        int(row_to_dict(row)["operation_id"])
        for row in db.execute(
            """
            SELECT operation_id
            FROM learning_legacy_reevaluations
            WHERE reevaluation_version = ?
            """,
            (LEGACY_REEVALUATION_VERSION,),
        ).fetchall()
    }


def source_integrity(db) -> dict:
    row = row_to_dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS evaluation_rows,
                COUNT(*) FILTER (
                    WHERE learning_schema_version IS NULL
                       OR data_contract_version IS NULL
                ) AS legacy_rows,
                MD5(
                    COALESCE(
                        string_agg(to_jsonb(le)::text, '' ORDER BY le.id),
                        ''
                    )
                ) AS evaluations_md5
            FROM learning_evaluations le
            """
        ).fetchone()
    )
    result = dict(row or {})
    result["legacy_review_rows"] = 0
    if table_exists(db):
        review_row = row_to_dict(
            db.execute(
                """
                SELECT COUNT(*) AS rows
                FROM learning_legacy_reevaluations
                WHERE reevaluation_version = ?
                """,
                (LEGACY_REEVALUATION_VERSION,),
            ).fetchone()
        )
        result["legacy_review_rows"] = int(review_row["rows"])
    return result


def load_candidates(
    operation_ids: list[int],
    limit: int | None,
) -> tuple[list[dict], set[int], dict]:
    filters = [
        "(le.learning_schema_version IS NULL OR le.data_contract_version IS NULL)"
    ]
    params: list = []
    if operation_ids:
        placeholders = ", ".join("?" for _ in operation_ids)
        filters.append(f"le.operation_id IN ({placeholders})")
        params.extend(operation_ids)
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(max(0, limit))
    query = f"""
        SELECT
            to_jsonb(le) AS evaluation_record,
            to_jsonb(o) AS operation_record,
            to_jsonb(r) AS recommendation_record,
            COALESCE(ler.evidence_json, le.evidence_json) AS evidence_record,
            COALESCE(len.metrics_json, le.economic_metrics_json) AS economic_record
        FROM learning_evaluations le
        JOIN operations o ON o.id = le.operation_id
        LEFT JOIN recommendations r ON r.id = le.recommendation_id
        LEFT JOIN learning_evidence_reconstructions ler
          ON ler.operation_id = le.operation_id
         AND ler.reconstruction_version = le.evidence_version
        LEFT JOIN learning_economic_normalizations len
          ON len.operation_id = le.operation_id
         AND len.normalization_version = le.economic_normalization_version
        WHERE {" AND ".join(filters)}
        ORDER BY le.operation_id
        {limit_sql}
    """
    with connect() as db:
        rows = [row_to_dict(row) for row in db.execute(query, params).fetchall()]
        existing = existing_operation_ids(db)
        integrity = source_integrity(db)
    return rows, existing, integrity


def persist_review(db, review: dict) -> bool:
    cursor = db.execute(
        """
        INSERT INTO learning_legacy_reevaluations (
            operation_id,
            evaluation_id,
            reevaluation_version,
            review_schema_version,
            review_status,
            source_engine_version,
            source_learning_schema_version,
            source_data_contract_version,
            source_evaluation_created_at,
            source_evaluation_updated_at,
            source_bundle_sha256,
            original_interpretation_json,
            reevaluated_contract_json,
            missing_fields_json,
            predictive_eligibility_json,
            outcome_class,
            outcome_status,
            reviewed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review["operation_id"],
            review["evaluation_id"],
            review["reevaluation_version"],
            review["review_schema_version"],
            review["review_status"],
            review["source_engine_version"],
            review["source_learning_schema_version"],
            review["source_data_contract_version"],
            review["source_evaluation_created_at"],
            review["source_evaluation_updated_at"],
            review["source_bundle_sha256"],
            json.dumps(review["original_interpretation"], ensure_ascii=True),
            json.dumps(review["reevaluated_contract"], ensure_ascii=True),
            json.dumps(review["missing_fields"], ensure_ascii=True),
            json.dumps(review["predictive_eligibility"], ensure_ascii=True),
            review["outcome_class"],
            review["outcome_status"],
            review["reviewed_at"],
        ),
    )
    return cursor.lastrowid is not None


def run(args: argparse.Namespace) -> dict:
    rows, existing_ids, integrity_before = load_candidates(
        args.operation_id,
        args.limit,
    )
    reviewed_at = utc_now_iso()
    result = {
        "mode": "apply" if args.apply else "dry_run",
        "reevaluation_version": LEGACY_REEVALUATION_VERSION,
        "legacy_candidates": len(rows),
        "processed": 0,
        "applied": 0,
        "skipped_idempotent": 0,
        "errors": 0,
        "review_status_counts": Counter(),
        "outcome_counts": Counter(),
        "outcome_status_counts": Counter(),
        "predictive_eligibility_counts": Counter(),
        "missing_field_counts": Counter(),
        "source_integrity_before": integrity_before,
        "operations": [],
    }
    reviews = []
    for case in rows:
        evaluation = case.get("evaluation_record") or {}
        operation_id = int(evaluation["operation_id"])
        if operation_id in existing_ids:
            result["skipped_idempotent"] += 1
            continue
        try:
            review = build_legacy_reevaluation(case, reviewed_at=reviewed_at)
            reviews.append(review)
            result["processed"] += 1
            result["review_status_counts"][review["review_status"]] += 1
            result["outcome_counts"][review["outcome_class"]] += 1
            result["outcome_status_counts"][review["outcome_status"]] += 1
            eligibility = (
                "eligible"
                if review["predictive_eligibility"]["eligible"]
                else "not_eligible"
            )
            result["predictive_eligibility_counts"][eligibility] += 1
            for missing in review["missing_fields"]:
                result["missing_field_counts"][missing["path"]] += 1
            result["operations"].append(
                {
                    "operation_id": review["operation_id"],
                    "evaluation_id": review["evaluation_id"],
                    "source_engine_version": review["source_engine_version"],
                    "review_status": review["review_status"],
                    "outcome_class": review["outcome_class"],
                    "outcome_status": review["outcome_status"],
                    "missing_fields": len(review["missing_fields"]),
                    "source_bundle_sha256": review["source_bundle_sha256"],
                }
            )
        except Exception as exc:
            result["errors"] += 1
            result["operations"].append(
                {"operation_id": operation_id, "error": str(exc)}
            )

    reconciled = (
        result["processed"]
        + result["skipped_idempotent"]
        + result["errors"]
    )
    result["reconciled"] = reconciled == result["legacy_candidates"]
    if args.apply:
        if result["errors"]:
            raise RuntimeError(
                "Aplicacion cancelada: existen errores en el dry-build interno."
            )
        with connect() as db:
            if not table_exists(db):
                raise RuntimeError(
                    "Falta learning_legacy_reevaluations; aplique primero la migracion."
                )
            for review in reviews:
                if persist_review(db, review):
                    result["applied"] += 1
            result["source_integrity_after"] = source_integrity(db)
    else:
        result["source_integrity_after"] = integrity_before
    result["source_evaluations_unchanged"] = (
        result["source_integrity_before"]["evaluation_rows"]
        == result["source_integrity_after"]["evaluation_rows"]
        and result["source_integrity_before"]["evaluations_md5"]
        == result["source_integrity_after"]["evaluations_md5"]
    )

    for key in (
        "review_status_counts",
        "outcome_counts",
        "outcome_status_counts",
        "predictive_eligibility_counts",
        "missing_field_counts",
    ):
        result[key] = dict(result[key])
    return result


def main() -> None:
    args = parse_args()
    try:
        result = run(args)
    finally:
        close_pool()
    payload = json.dumps(result, ensure_ascii=True, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    if not args.quiet:
        print(payload)


if __name__ == "__main__":
    main()
