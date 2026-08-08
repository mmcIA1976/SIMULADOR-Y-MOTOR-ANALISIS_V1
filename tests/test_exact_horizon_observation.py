from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import patch

from app import build_observation_result, operation_evaluation_expires_at


class ExactHorizonObservationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """
            CREATE TABLE recommendations (
                id INTEGER PRIMARY KEY,
                operation_id INTEGER,
                snapshot_json TEXT,
                created_at TEXT
            )
            """
        )

    def tearDown(self):
        self.db.close()

    def test_market_deadline_comes_from_original_recommendation(self):
        self.db.execute(
            """
            INSERT INTO recommendations (
                id, operation_id, snapshot_json, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                1,
                293,
                json.dumps(
                    {
                        "evaluation_expires_at": (
                            "2026-08-12T10:15:00+00:00"
                        )
                    }
                ),
                "2026-08-05T10:15:00+00:00",
            ),
        )

        deadline = operation_evaluation_expires_at(
            self.db,
            {
                "id": 293,
                "time_horizon": "short_swing",
                "started_at": "2026-08-05T10:16:00+00:00",
                "triggered_at": None,
            },
        )

        self.assertEqual(
            deadline.isoformat(),
            "2026-08-12T10:15:00+00:00",
        )

    def test_fallback_uses_selected_horizon_not_two_days(self):
        deadline = operation_evaluation_expires_at(
            self.db,
            {
                "id": 294,
                "time_horizon": "intraday_short",
                "started_at": "2026-08-05T10:00:00+00:00",
                "triggered_at": None,
            },
        )

        self.assertEqual(
            deadline.isoformat(),
            "2026-08-05T14:00:00+00:00",
        )

    @patch(
        "app.reconstruct_operation_historical_evidence",
        return_value={
            "status": "complete",
            "first_post_close_plan_touch": {
                "status": "resolved",
                "reason": "stop_loss",
                "price": 95.0,
                "touched_at": "2026-08-05T13:00:00+00:00",
            },
        },
    )
    def test_final_observation_uses_exact_reconstructed_path(self, _rebuild):
        result = build_observation_result(
            None,
            {
                "id": 295,
                "side": "long",
                "entry": 100.0,
                "margin": 100.0,
                "leverage": 2.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "final_pnl": 0.0,
                "close_reason": "manual",
            },
        )

        self.assertEqual(result["result"], "manual_protected")
        self.assertIn("STOP LOSS", result["summary"])


if __name__ == "__main__":
    unittest.main()
