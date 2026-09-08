from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

import m8_evaluation as m8


EPISODE_GROUPING_VERSION = "counterfactual-overlap-components-v0.1"
EPISODE_GROUPING_PRODUCTION_EFFECT = "none"
MAX_GROUPING_SUMMARY_BYTES = 16_384
MEMBERSHIP_BATCH_SIZE = 200


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _validated_rows(rows: Iterable[dict]) -> list[dict]:
    normalized = []
    seen_ids: set[int] = set()
    for source in rows:
        row = dict(source)
        try:
            evaluation_id = int(row["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("episode_evaluation_id_invalid") from exc
        if evaluation_id in seen_ids:
            raise ValueError("episode_evaluation_id_duplicated")
        seen_ids.add(evaluation_id)

        analysis_at = m8.parse_utc(row.get("analysis_at"))
        expires_at = m8.parse_utc(row.get("evaluation_expires_at"))
        if analysis_at is None or expires_at is None or expires_at <= analysis_at:
            raise ValueError("episode_interval_invalid")
        symbol = str(row.get("symbol") or "").upper()
        time_horizon = str(row.get("time_horizon") or "")
        evaluation_status = str(row.get("evaluation_status") or "")
        contract_quality = str(row.get("contract_quality") or "")
        if not symbol or time_horizon not in m8.HORIZON_SECONDS:
            raise ValueError("episode_identity_invalid")
        if evaluation_status not in {"evaluated", "excluded"}:
            raise ValueError("episode_evaluation_status_invalid")
        if contract_quality not in {"exact", "legacy_upper_bound_proxy"}:
            raise ValueError("episode_contract_quality_invalid")
        formal_learning_eligible = bool(row.get("formal_learning_eligible"))
        if formal_learning_eligible != (contract_quality == "exact"):
            raise ValueError("episode_formal_contract_mismatch")
        result_sha256 = str(row.get("result_sha256") or "")
        if len(result_sha256) != 64:
            raise ValueError("episode_result_sha256_invalid")

        normalized.append(
            {
                "id": evaluation_id,
                "symbol": symbol,
                "time_horizon": time_horizon,
                "contract_quality": contract_quality,
                "formal_learning_eligible": formal_learning_eligible,
                "evaluation_status": evaluation_status,
                "analysis_at": analysis_at,
                "evaluation_expires_at": expires_at,
                "result_sha256": result_sha256,
            }
        )
    return sorted(normalized, key=lambda row: row["id"])


def _episode_components(
    rows: list[dict],
    *,
    scope: str,
) -> tuple[dict[int, dict], list[dict]]:
    if scope not in {"market", "horizon"}:
        raise ValueError("episode_scope_invalid")
    grouped: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in rows:
        group_key = (row["symbol"],)
        if scope == "horizon":
            group_key += (row["time_horizon"],)
        grouped[group_key].append(row)

    assignments: dict[int, dict] = {}
    components: list[dict] = []
    for group_key, members in sorted(grouped.items()):
        ordered = sorted(
            members,
            key=lambda row: (
                row["analysis_at"],
                row["evaluation_expires_at"],
                row["id"],
            ),
        )
        current: list[dict] = []
        component_end: datetime | None = None

        def flush_component() -> None:
            nonlocal current, component_end
            if not current:
                return
            first_at = min(row["analysis_at"] for row in current)
            last_at = max(row["evaluation_expires_at"] for row in current)
            member_ids = sorted(row["id"] for row in current)
            episode_key = m8.payload_sha256(
                {
                    "grouping_version": EPISODE_GROUPING_VERSION,
                    "scope": scope,
                    "group": list(group_key),
                    "first_analysis_at": _iso_utc(first_at),
                    "last_expiry_at": _iso_utc(last_at),
                    "evaluation_ids": member_ids,
                }
            )
            evaluated = sum(
                row["evaluation_status"] == "evaluated" for row in current
            )
            formal = sum(
                row["evaluation_status"] == "evaluated"
                and row["formal_learning_eligible"]
                for row in current
            )
            component = {
                "episode_key": episode_key,
                "scope": scope,
                "group": group_key,
                "first_analysis_at": first_at,
                "last_expiry_at": last_at,
                "size": len(current),
                "evaluated_size": evaluated,
                "formal_size": formal,
                "evaluation_ids": member_ids,
            }
            components.append(component)
            for row in current:
                assignments[row["id"]] = component
            current = []
            component_end = None

        for row in ordered:
            # The intervals are half-open: an analysis starting exactly when
            # the previous one expires does not share future market evidence.
            if component_end is not None and row["analysis_at"] >= component_end:
                flush_component()
            current.append(row)
            if component_end is None or row["evaluation_expires_at"] > component_end:
                component_end = row["evaluation_expires_at"]
        flush_component()
    return assignments, components


def _weight(eligible: bool, denominator: int) -> float:
    if not eligible:
        return 0.0
    if denominator < 1:
        raise ValueError("episode_weight_denominator_invalid")
    return 1.0 / denominator


def _count_distinct(memberships: list[dict], key: str, eligible_key: str) -> int:
    return len(
        {
            row[key]
            for row in memberships
            if bool(row[eligible_key])
        }
    )


def _horizon_summary(memberships: list[dict]) -> dict:
    output = {}
    for horizon in m8.HORIZON_SECONDS:
        members = [
            row for row in memberships if row["time_horizon"] == horizon
        ]
        evaluated = [row for row in members if row["eligible_for_metrics"]]
        formal = [row for row in members if row["formal_metric_eligible"]]
        output[horizon] = {
            "raw_cases": len(members),
            "evaluated_cases": len(evaluated),
            "formal_cases": len(formal),
            "effective_horizon_episodes": len(
                {row["horizon_episode_key"] for row in evaluated}
            ),
            "formal_effective_horizon_episodes": len(
                {row["formal_horizon_episode_key"] for row in formal}
            ),
            "calendar_blocks_utc": len(
                {row["calendar_block_utc"] for row in evaluated}
            ),
            "formal_calendar_blocks_utc": len(
                {row["calendar_block_utc"] for row in formal}
            ),
        }
    return output


def build_episode_grouping(rows: Iterable[dict]) -> tuple[dict, list[dict]]:
    """Create an immutable dependency snapshot without discarding analyses."""
    normalized = _validated_rows(rows)
    if not normalized:
        raise ValueError("episode_source_dataset_empty")
    dataset_identity = [
        {
            "evaluation_id": row["id"],
            "result_sha256": row["result_sha256"],
            "symbol": row["symbol"],
            "time_horizon": row["time_horizon"],
            "contract_quality": row["contract_quality"],
            "formal_learning_eligible": row["formal_learning_eligible"],
            "evaluation_status": row["evaluation_status"],
            "analysis_at": _iso_utc(row["analysis_at"]),
            "evaluation_expires_at": _iso_utc(
                row["evaluation_expires_at"]
            ),
        }
        for row in normalized
    ]
    source_dataset_sha256 = m8.payload_sha256(dataset_identity)
    run_key = m8.payload_sha256(
        {
            "grouping_version": EPISODE_GROUPING_VERSION,
            "source_dataset_sha256": source_dataset_sha256,
        }
    )
    evaluated_rows = [
        row for row in normalized if row["evaluation_status"] == "evaluated"
    ]
    excluded_rows = [
        row for row in normalized if row["evaluation_status"] == "excluded"
    ]
    formal_rows = [
        row for row in evaluated_rows if row["formal_learning_eligible"]
    ]
    market_assignments, market_components = _episode_components(
        evaluated_rows,
        scope="market",
    )
    horizon_assignments, horizon_components = _episode_components(
        evaluated_rows,
        scope="horizon",
    )
    excluded_market_assignments, excluded_market_components = (
        _episode_components(excluded_rows, scope="market")
    )
    excluded_horizon_assignments, excluded_horizon_components = (
        _episode_components(excluded_rows, scope="horizon")
    )
    market_assignments.update(excluded_market_assignments)
    horizon_assignments.update(excluded_horizon_assignments)
    market_components.extend(excluded_market_components)
    horizon_components.extend(excluded_horizon_components)
    formal_market_assignments, formal_market_components = _episode_components(
        formal_rows,
        scope="market",
    )
    formal_horizon_assignments, formal_horizon_components = (
        _episode_components(formal_rows, scope="horizon")
    )

    memberships = []
    for row in normalized:
        market = market_assignments[row["id"]]
        horizon = horizon_assignments[row["id"]]
        eligible = row["evaluation_status"] == "evaluated"
        formal = eligible and row["formal_learning_eligible"]
        formal_market = (
            formal_market_assignments[row["id"]] if formal else None
        )
        formal_horizon = (
            formal_horizon_assignments[row["id"]] if formal else None
        )
        membership = {
            "run_key": run_key,
            "evaluation_id": row["id"],
            "symbol": row["symbol"],
            "time_horizon": row["time_horizon"],
            "contract_quality": row["contract_quality"],
            "evaluation_status": row["evaluation_status"],
            "formal_learning_eligible": row["formal_learning_eligible"],
            "eligible_for_metrics": eligible,
            "formal_metric_eligible": formal,
            "calendar_block_utc": row["analysis_at"].date().isoformat(),
            "market_episode_key": market["episode_key"],
            "horizon_episode_key": horizon["episode_key"],
            "formal_market_episode_key": (
                formal_market["episode_key"] if formal_market else None
            ),
            "formal_horizon_episode_key": (
                formal_horizon["episode_key"] if formal_horizon else None
            ),
            "market_episode_size": market["size"],
            "market_episode_evaluated_size": market["evaluated_size"],
            "market_episode_formal_size": (
                formal_market["size"] if formal_market else 0
            ),
            "horizon_episode_size": horizon["size"],
            "horizon_episode_evaluated_size": horizon["evaluated_size"],
            "horizon_episode_formal_size": (
                formal_horizon["size"] if formal_horizon else 0
            ),
            "market_weight": _weight(eligible, market["evaluated_size"]),
            "horizon_weight": _weight(eligible, horizon["evaluated_size"]),
            "formal_market_weight": _weight(
                formal,
                formal_market["size"] if formal_market else 0,
            ),
            "formal_horizon_weight": _weight(
                formal,
                formal_horizon["size"] if formal_horizon else 0,
            ),
            "production_effect": EPISODE_GROUPING_PRODUCTION_EFFECT,
        }
        membership["membership_sha256"] = m8.payload_sha256(membership)
        memberships.append(membership)

    evaluated_count = sum(row["eligible_for_metrics"] for row in memberships)
    formal_count = sum(row["formal_metric_eligible"] for row in memberships)
    summary = {
        "grouping_version": EPISODE_GROUPING_VERSION,
        "production_effect": EPISODE_GROUPING_PRODUCTION_EFFECT,
        "source_rows": len(memberships),
        "evaluated_cases": evaluated_count,
        "formal_evaluated_cases": formal_count,
        "excluded_cases": len(memberships) - evaluated_count,
        "market_episodes": len(market_components),
        "horizon_episodes": len(horizon_components),
        "calendar_blocks_utc": len(
            {row["calendar_block_utc"] for row in memberships}
        ),
        "effective_market_episodes": _count_distinct(
            memberships, "market_episode_key", "eligible_for_metrics"
        ),
        "formal_effective_market_episodes": _count_distinct(
            memberships, "formal_market_episode_key", "formal_metric_eligible"
        ),
        "effective_horizon_episodes": _count_distinct(
            memberships, "horizon_episode_key", "eligible_for_metrics"
        ),
        "formal_effective_horizon_episodes": _count_distinct(
            memberships,
            "formal_horizon_episode_key",
            "formal_metric_eligible",
        ),
        "evaluated_calendar_blocks_utc": len(
            {
                row["calendar_block_utc"]
                for row in memberships
                if row["eligible_for_metrics"]
            }
        ),
        "formal_calendar_blocks_utc": len(
            {
                row["calendar_block_utc"]
                for row in memberships
                if row["formal_metric_eligible"]
            }
        ),
        "largest_market_episode": max(
            component["size"] for component in market_components
        ),
        "largest_horizon_episode": max(
            component["size"] for component in horizon_components
        ),
        "by_horizon": _horizon_summary(memberships),
        "method": {
            "intervals": "half_open_[analysis_at,evaluation_expires_at)",
            "overlap": "transitive_connected_components",
            "market_scope": "symbol",
            "horizon_scope": "symbol+time_horizon",
            "calendar_block": "analysis_day_utc",
            "weighting": "each_episode_sums_to_one",
            "formal_filter": "exact_contract_and_evaluated_only",
            "formal_episodes": (
                "recomputed_without_proxy_or_excluded_bridges"
            ),
        },
    }
    summary_json = m8.canonical_json(summary)
    summary_bytes = len(summary_json.encode("utf-8"))
    if summary_bytes > MAX_GROUPING_SUMMARY_BYTES:
        raise ValueError("episode_summary_payload_too_large")
    run = {
        "run_key": run_key,
        "grouping_version": EPISODE_GROUPING_VERSION,
        "source_dataset_sha256": source_dataset_sha256,
        "source_row_count": len(memberships),
        "evaluated_row_count": evaluated_count,
        "formal_evaluated_row_count": formal_count,
        "market_episode_count": len(market_components),
        "horizon_episode_count": len(horizon_components),
        "calendar_block_count": summary["calendar_blocks_utc"],
        "summary_json": summary_json,
        "summary_bytes": summary_bytes,
        "production_effect": EPISODE_GROUPING_PRODUCTION_EFFECT,
    }
    run["result_sha256"] = m8.payload_sha256(
        {
            **run,
            "membership_sha256": [
                row["membership_sha256"] for row in memberships
            ],
        }
    )
    return run, memberships


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if isinstance(row, dict):
        return row[key]
    return row[index]


def persist_episode_grouping(
    db,
    run: dict,
    memberships: list[dict],
    *,
    batch_size: int = MEMBERSHIP_BATCH_SIZE,
) -> dict:
    if batch_size < 1:
        raise ValueError("episode_batch_size_invalid")
    run_columns = (
        "run_key",
        "grouping_version",
        "source_dataset_sha256",
        "source_row_count",
        "evaluated_row_count",
        "formal_evaluated_row_count",
        "market_episode_count",
        "horizon_episode_count",
        "calendar_block_count",
        "summary_json",
        "summary_bytes",
        "result_sha256",
        "production_effect",
    )
    cursor = db.execute(
        f"""
        INSERT INTO counterfactual_episode_grouping_runs (
            {', '.join(run_columns)}
        ) VALUES ({', '.join('?' for _ in run_columns)})
        ON CONFLICT (run_key) DO NOTHING
        RETURNING id
        """,
        tuple(run[column] for column in run_columns),
    )
    inserted = cursor.fetchone()
    inserted_run = inserted is not None
    if inserted_run:
        run_id = int(_row_value(inserted, "id"))
    else:
        existing = db.execute(
            """
            SELECT id, source_dataset_sha256, result_sha256
            FROM counterfactual_episode_grouping_runs
            WHERE run_key = ?
            """,
            (run["run_key"],),
        ).fetchone()
        if existing is None:
            raise RuntimeError("episode_run_conflict_without_existing_row")
        if (
            _row_value(existing, "source_dataset_sha256", 1)
            != run["source_dataset_sha256"]
            or _row_value(existing, "result_sha256", 2)
            != run["result_sha256"]
        ):
            raise RuntimeError("episode_existing_run_mismatch")
        run_id = int(_row_value(existing, "id"))

    member_columns = (
        "run_id",
        "evaluation_id",
        "symbol",
        "time_horizon",
        "contract_quality",
        "evaluation_status",
        "formal_learning_eligible",
        "eligible_for_metrics",
        "formal_metric_eligible",
        "calendar_block_utc",
        "market_episode_key",
        "horizon_episode_key",
        "formal_market_episode_key",
        "formal_horizon_episode_key",
        "market_episode_size",
        "market_episode_evaluated_size",
        "market_episode_formal_size",
        "horizon_episode_size",
        "horizon_episode_evaluated_size",
        "horizon_episode_formal_size",
        "market_weight",
        "horizon_weight",
        "formal_market_weight",
        "formal_horizon_weight",
        "membership_sha256",
        "production_effect",
    )
    inserted_memberships = 0
    for offset in range(0, len(memberships), batch_size):
        batch = memberships[offset : offset + batch_size]
        row_placeholder = f"({', '.join('?' for _ in member_columns)})"
        params = []
        for membership in batch:
            values = {**membership, "run_id": run_id}
            params.extend(values[column] for column in member_columns)
        cursor = db.execute(
            f"""
            INSERT INTO counterfactual_episode_memberships (
                {', '.join(member_columns)}
            ) VALUES {', '.join(row_placeholder for _ in batch)}
            ON CONFLICT (run_id, evaluation_id) DO NOTHING
            RETURNING evaluation_id
            """,
            tuple(params),
        )
        inserted_memberships += len(cursor.fetchall())

    existing_memberships = db.execute(
        """
        SELECT evaluation_id, membership_sha256
        FROM counterfactual_episode_memberships
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchall()
    actual_hashes = {
        int(_row_value(row, "evaluation_id")): _row_value(
            row, "membership_sha256", 1
        )
        for row in existing_memberships
    }
    expected_hashes = {
        row["evaluation_id"]: row["membership_sha256"]
        for row in memberships
    }
    if actual_hashes != expected_hashes:
        raise RuntimeError("episode_existing_memberships_mismatch")
    if not math.isclose(
        math.fsum(row["horizon_weight"] for row in memberships),
        float(
            len(
                {
                    row["horizon_episode_key"]
                    for row in memberships
                    if row["eligible_for_metrics"]
                }
            )
        ),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise RuntimeError("episode_weight_sum_invalid")
    return {
        "run_id": run_id,
        "inserted_run": inserted_run,
        "inserted_memberships": inserted_memberships,
        "already_persisted_memberships": (
            len(memberships) - inserted_memberships
        ),
    }
