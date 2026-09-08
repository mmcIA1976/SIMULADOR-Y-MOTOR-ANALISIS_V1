from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from counterfactual_episode_grouping import (
    EPISODE_GROUPING_VERSION,
    build_episode_grouping,
    persist_episode_grouping,
)


def evaluation_row(
    evaluation_id: int,
    start: str,
    end: str,
    *,
    horizon: str = "intraday_short",
    quality: str = "exact",
    status: str = "evaluated",
    symbol: str = "BTCUSDT",
) -> dict:
    return {
        "id": evaluation_id,
        "symbol": symbol,
        "time_horizon": horizon,
        "contract_quality": quality,
        "formal_learning_eligible": quality == "exact",
        "evaluation_status": status,
        "analysis_at": start,
        "evaluation_expires_at": end,
        "result_sha256": f"{evaluation_id:064x}",
    }


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakeDb:
    def __init__(self):
        self.run = None
        self.memberships = {}

    @staticmethod
    def _columns(query: str) -> list[str]:
        body = query.split("(", 1)[1].split(")", 1)[0]
        return [column.strip() for column in body.split(",")]

    def execute(self, query, params):
        compact = " ".join(query.split())
        if compact.startswith(
            "INSERT INTO counterfactual_episode_grouping_runs"
        ):
            if self.run is not None:
                return Cursor([])
            columns = self._columns(query)
            self.run = dict(zip(columns, params))
            self.run["id"] = 1
            return Cursor([{"id": 1}])
        if compact.startswith(
            "SELECT id, source_dataset_sha256, result_sha256"
        ):
            return Cursor([self.run] if self.run else [])
        if compact.startswith(
            "INSERT INTO counterfactual_episode_memberships"
        ):
            columns = self._columns(query)
            inserted = []
            for offset in range(0, len(params), len(columns)):
                values = dict(
                    zip(columns, params[offset : offset + len(columns)])
                )
                key = (values["run_id"], values["evaluation_id"])
                if key not in self.memberships:
                    self.memberships[key] = values
                    inserted.append(
                        {"evaluation_id": values["evaluation_id"]}
                    )
            return Cursor(inserted)
        if compact.startswith("SELECT evaluation_id, membership_sha256"):
            run_id = params[0]
            return Cursor(
                [
                    {
                        "evaluation_id": values["evaluation_id"],
                        "membership_sha256": values["membership_sha256"],
                    }
                    for (member_run_id, _), values in self.memberships.items()
                    if member_run_id == run_id
                ]
            )
        raise AssertionError(f"Unexpected SQL: {compact}")


class CounterfactualEpisodeGroupingTests(unittest.TestCase):
    def test_overlapping_intervals_share_one_weighted_episode(self) -> None:
        rows = [
            evaluation_row(
                1,
                "2026-08-01T10:00:00Z",
                "2026-08-01T14:00:00Z",
            ),
            evaluation_row(
                2,
                "2026-08-01T13:00:00Z",
                "2026-08-01T17:00:00Z",
            ),
            evaluation_row(
                3,
                "2026-08-01T16:00:00Z",
                "2026-08-01T20:00:00Z",
            ),
        ]
        run, memberships = build_episode_grouping(rows)
        self.assertEqual(run["grouping_version"], EPISODE_GROUPING_VERSION)
        self.assertEqual(
            len({row["market_episode_key"] for row in memberships}),
            1,
        )
        self.assertTrue(
            all(row["market_episode_evaluated_size"] == 3 for row in memberships)
        )
        self.assertTrue(
            all(math.isclose(row["market_weight"], 1 / 3) for row in memberships)
        )
        self.assertTrue(
            math.isclose(sum(row["market_weight"] for row in memberships), 1)
        )

    def test_half_open_boundary_starts_a_new_episode(self) -> None:
        rows = [
            evaluation_row(
                1,
                "2026-08-01T10:00:00Z",
                "2026-08-01T14:00:00Z",
            ),
            evaluation_row(
                2,
                "2026-08-01T14:00:00Z",
                "2026-08-01T18:00:00Z",
            ),
        ]
        _, memberships = build_episode_grouping(rows)
        self.assertEqual(
            len({row["market_episode_key"] for row in memberships}),
            2,
        )
        self.assertTrue(all(row["market_weight"] == 1 for row in memberships))

    def test_proxy_and_excluded_rows_do_not_bridge_formal_episodes(self) -> None:
        rows = [
            evaluation_row(
                1,
                "2026-08-01T10:00:00Z",
                "2026-08-01T14:00:00Z",
            ),
            evaluation_row(
                2,
                "2026-08-01T13:00:00Z",
                "2026-08-01T17:00:00Z",
                quality="legacy_upper_bound_proxy",
            ),
            evaluation_row(
                3,
                "2026-08-01T16:00:00Z",
                "2026-08-01T20:00:00Z",
            ),
            evaluation_row(
                4,
                "2026-08-01T19:00:00Z",
                "2026-08-01T23:00:00Z",
                status="excluded",
            ),
        ]
        run, memberships = build_episode_grouping(rows)
        by_id = {row["evaluation_id"]: row for row in memberships}
        self.assertNotEqual(
            by_id[1]["formal_market_episode_key"],
            by_id[3]["formal_market_episode_key"],
        )
        self.assertEqual(by_id[1]["formal_market_weight"], 1)
        self.assertEqual(by_id[3]["formal_market_weight"], 1)
        self.assertIsNone(by_id[2]["formal_market_episode_key"])
        self.assertEqual(by_id[2]["formal_market_weight"], 0)
        self.assertEqual(by_id[4]["market_weight"], 0)
        summary = json.loads(run["summary_json"])
        self.assertEqual(summary["formal_effective_market_episodes"], 2)

    def test_grouping_is_deterministic_for_input_order(self) -> None:
        rows = [
            evaluation_row(
                1,
                "2026-08-01T10:00:00Z",
                "2026-08-01T14:00:00Z",
            ),
            evaluation_row(
                2,
                "2026-08-02T10:00:00Z",
                "2026-08-02T14:00:00Z",
            ),
        ]
        first_run, first_memberships = build_episode_grouping(rows)
        second_run, second_memberships = build_episode_grouping(reversed(rows))
        self.assertEqual(first_run, second_run)
        self.assertEqual(first_memberships, second_memberships)

    def test_persistence_is_batched_idempotent_and_hash_checked(self) -> None:
        run, memberships = build_episode_grouping(
            [
                evaluation_row(
                    1,
                    "2026-08-01T10:00:00Z",
                    "2026-08-01T14:00:00Z",
                ),
                evaluation_row(
                    2,
                    "2026-08-02T10:00:00Z",
                    "2026-08-02T14:00:00Z",
                ),
            ]
        )
        db = FakeDb()
        first = persist_episode_grouping(db, run, memberships, batch_size=1)
        second = persist_episode_grouping(db, run, memberships, batch_size=1)
        self.assertTrue(first["inserted_run"])
        self.assertEqual(first["inserted_memberships"], 2)
        self.assertFalse(second["inserted_run"])
        self.assertEqual(second["inserted_memberships"], 0)
        self.assertEqual(second["already_persisted_memberships"], 2)

    def test_schema_keeps_grouping_append_only_and_fk_indexed(self) -> None:
        schema = (
            Path(__file__).resolve().parents[1] / "supabase" / "schema.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("counterfactual_episode_grouping_runs", schema)
        self.assertIn("counterfactual_episode_memberships", schema)
        self.assertIn("counterfactual_episode_memberships_append_only", schema)
        self.assertIn("idx_counterfactual_episode_evaluation", schema)


if __name__ == "__main__":
    unittest.main()
