from __future__ import annotations

import argparse
import json
from pathlib import Path

from counterfactual_episode_grouping import (
    build_episode_grouping,
    persist_episode_grouping,
)
from db import close_pool, connect


SQL_SOURCE_ROWS = """
SELECT
    id,
    symbol,
    time_horizon,
    contract_quality,
    formal_learning_eligible,
    evaluation_status,
    analysis_at,
    evaluation_expires_at,
    result_sha256
FROM recommendation_counterfactual_evaluations
ORDER BY id
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Agrupa evaluaciones contrafactuales solapadas y reparte su "
            "peso estadistico sin eliminar ningun caso."
        )
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help=(
            "Guarda una foto append-only compacta; por defecto solo "
            "muestra el resultado."
        ),
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_source_rows() -> list[dict]:
    try:
        with connect() as db:
            return [
                dict(row)
                for row in db.execute(SQL_SOURCE_ROWS).fetchall()
            ]
    finally:
        close_pool()


def main() -> None:
    args = parse_args()
    source_rows = load_source_rows()
    run, memberships = build_episode_grouping(source_rows)
    report = json.loads(run["summary_json"])
    report.update(
        {
            "mode": "persist" if args.persist else "dry_run",
            "run_key": run["run_key"],
            "source_dataset_sha256": run["source_dataset_sha256"],
            "result_sha256": run["result_sha256"],
            "summary_bytes": run["summary_bytes"],
            "persistence": {
                "inserted_run": False,
                "inserted_memberships": 0,
                "already_persisted_memberships": 0,
            },
        }
    )
    if args.persist:
        try:
            with connect() as db:
                report["persistence"] = persist_episode_grouping(
                    db,
                    run,
                    memberships,
                )
        finally:
            close_pool()

    encoded = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
