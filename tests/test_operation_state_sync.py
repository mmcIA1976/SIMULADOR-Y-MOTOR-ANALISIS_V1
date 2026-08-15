import sqlite3
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Response

import app


def create_operations_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE operations (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            entry REAL,
            triggered_at TEXT,
            trigger_price REAL,
            closed_at TEXT,
            close_price REAL,
            close_reason TEXT,
            final_pnl REAL,
            observation_status TEXT,
            observation_until TEXT
        );

        INSERT INTO operations (id, user_id, status, entry)
        VALUES (1, 7, 'OPEN', 100.0);

        INSERT INTO operations (
            id, user_id, status, entry, closed_at, close_price,
            close_reason, final_pnl, observation_status
        ) VALUES (
            2, 7, 'CLOSED', 101.0, '2026-08-04T17:02:17+00:00',
            99.0, 'stop_loss', -2.0, 'PLAN_EXECUTED'
        );

        INSERT INTO operations (id, user_id, status, entry)
        VALUES (3, 8, 'OPEN', 102.0);

        INSERT INTO operations (id, user_id, status, entry)
        VALUES (4, 7, 'CLOSED', 103.0);
        """
    )
    return db


@contextmanager
def use_db(db):
    yield db


class OperationStateSnapshotTests(unittest.TestCase):
    def test_id_parser_deduplicates_and_rejects_invalid_values(self):
        self.assertEqual(app.parse_operation_status_snapshot_ids("2, 1,2"), [2, 1])

        with self.assertRaises(HTTPException) as invalid:
            app.parse_operation_status_snapshot_ids("2,nope")
        self.assertEqual(invalid.exception.status_code, 400)

        with self.assertRaises(HTTPException) as excessive:
            app.parse_operation_status_snapshot_ids(
                ",".join(str(value) for value in range(1, app.OPERATION_STATUS_SNAPSHOT_MAX_IDS + 2))
            )
        self.assertEqual(excessive.exception.status_code, 400)

    def test_snapshot_returns_active_and_requested_rows_for_current_user_only(self):
        db = create_operations_db()
        changes_before = db.total_changes

        with patch("app.current_user", return_value={"id": 7}), patch(
            "app.connect", side_effect=lambda: use_db(db)
        ):
            response = Response()
            result = app.operation_status_snapshot(
                response=response,
                ids="2,2",
                session_token="session",
            )

        self.assertEqual([row["id"] for row in result["operations"]], [2, 1])
        self.assertEqual(result["operations"][0]["status"], "CLOSED")
        self.assertEqual(result["operations"][0]["close_reason"], "stop_loss")
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(db.total_changes, changes_before)
        db.close()

    def test_frontend_polls_snapshot_without_calling_web_exit_processing(self):
        app_js = (Path(__file__).resolve().parents[1] / "app.js").read_text(encoding="utf-8")

        self.assertIn("/api/operations/status-snapshot", app_js)
        self.assertIn("window.setInterval(syncOperationStates, OPERATION_STATE_SYNC_INTERVAL_MS)", app_js)
        self.assertIn("cacheBust: true", app_js)
        self.assertIn("_sync=${Date.now()}", app_js)
        self.assertIn('data.operation_processing === "web"', app_js)

    def test_index_disables_cache_and_versions_operation_sync_asset(self):
        response = app.index()

        self.assertEqual(response.headers.get("cache-control"), "no-store")
        index_html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertIn("/static/app.js?v=20260815-empirical-analysis-panel", index_html)


if __name__ == "__main__":
    unittest.main()
