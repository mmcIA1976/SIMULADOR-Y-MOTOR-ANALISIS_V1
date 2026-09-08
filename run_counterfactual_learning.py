from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from counterfactual_learning import (
    build_counterfactual_payload,
    evaluate_counterfactual_records,
    normalize_legacy_market_recommendation,
    normalize_unlinked_recommendation,
    persist_counterfactual_payload,
    summarize_counterfactual_run,
)
from db import close_pool, connect


SQL_CANDIDATES = """
SELECT
    r.id AS recommendation_id,
    r.operation_id,
    r.user_id,
    r.symbol,
    r.side,
    r.time_horizon,
    r.tp_probability,
    r.sl_probability,
    r.range_probability,
    r.engine_version,
    r.scoring_version,
    r.snapshot_json,
    r.created_at
FROM recommendations r
WHERE r.operation_id IS NULL
{filters}
ORDER BY r.created_at, r.id
LIMIT ?
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evalua recomendaciones sin operacion mediante evidencia "
            "historica posterior, sin afectar produccion."
        )
    )
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--engine-version")
    parser.add_argument(
        "--contract-mode",
        choices=("exact", "legacy_proxy"),
        default="exact",
        help=(
            "exact usa solo contratos temporales formales; legacy_proxy "
            "evalua planes antiguos con horizonte superior y sin peso formal."
        ),
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persiste resultados compactos; por defecto solo muestra dry-run.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def evaluate_by_market_group(
    records: list[dict],
    *,
    captured_at: datetime,
) -> tuple[list[dict], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in records:
        grouped[(record["symbol"], record["time_horizon"])].append(record)
    completed: list[dict] = []
    errors: list[dict] = []
    for (symbol, horizon), members in grouped.items():
        try:
            evaluate_counterfactual_records(
                members,
                captured_at=captured_at,
            )
        except Exception as exc:
            errors.append(
                {
                    "symbol": symbol,
                    "time_horizon": horizon,
                    "recommendations": len(members),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                }
            )
            continue
        completed.extend(members)
    return completed, errors


def load_candidate_rows(
    *,
    limit: int,
    user_id: int | None,
    engine_version: str | None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if user_id is not None:
        clauses.append("r.user_id = ?")
        params.append(user_id)
    if engine_version is not None:
        clauses.append("r.engine_version = ?")
        params.append(engine_version)
    filters = "".join(f"\n  AND {clause}" for clause in clauses)
    params.append(limit)
    try:
        with connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    SQL_CANDIDATES.format(filters=filters),
                    tuple(params),
                ).fetchall()
            ]
    finally:
        close_pool()


def main() -> None:
    args = parse_args()
    if args.limit < 1 or args.limit > 5000:
        raise SystemExit("--limit debe estar entre 1 y 5000")
    captured_at = datetime.now(timezone.utc)
    raw_rows = load_candidate_rows(
        limit=args.limit,
        user_id=args.user_id,
        engine_version=args.engine_version,
    )

    rejection_codes: Counter = Counter()
    exact_records = []
    normalizer = (
        normalize_unlinked_recommendation
        if args.contract_mode == "exact"
        else normalize_legacy_market_recommendation
    )
    for row in raw_rows:
        record, rejection = normalizer(
            row,
            captured_at=captured_at,
        )
        if rejection:
            rejection_codes[rejection] += 1
        elif record:
            exact_records.append(record)

    completed, fetch_errors = evaluate_by_market_group(
        exact_records,
        captured_at=captured_at,
    )
    payloads = [build_counterfactual_payload(row) for row in completed]
    summary = summarize_counterfactual_run(
        raw_count=len(raw_rows),
        records=exact_records,
        rejection_codes=rejection_codes,
        payloads=payloads,
        fetch_errors=fetch_errors,
    )
    summary["mode"] = "persist" if args.persist else "dry_run"
    summary["captured_at"] = captured_at.isoformat()
    summary["requested_limit"] = args.limit
    summary["user_id_filter"] = args.user_id
    summary["engine_version_filter"] = args.engine_version
    summary["contract_mode"] = args.contract_mode
    summary["persisted"] = 0
    summary["already_persisted"] = 0
    if args.persist:
        with connect() as db:
            for payload in payloads:
                if persist_counterfactual_payload(db, payload):
                    summary["persisted"] += 1
                else:
                    summary["already_persisted"] += 1
        close_pool()

    encoded = json.dumps(summary, indent=2, ensure_ascii=False, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
