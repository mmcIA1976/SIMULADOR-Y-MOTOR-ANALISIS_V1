import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app
import operation_worker
from operation_worker_status import (
    add_transition_coverage,
    get_worker_status_row,
    summarize_worker_status,
    upsert_worker_status,
)


def create_status_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE operation_worker_state (
            worker_name TEXT PRIMARY KEY,
            lifecycle_status TEXT NOT NULL,
            app_version TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            dry_run BOOLEAN NOT NULL,
            persist_exit_window BOOLEAN NOT NULL,
            poll_seconds REAL NOT NULL,
            reconcile_seconds REAL NOT NULL,
            heartbeat_seconds REAL NOT NULL,
            started_at TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL,
            last_cycle_at TEXT,
            last_success_at TEXT,
            last_reconcile_at TEXT,
            cycle_count INTEGER NOT NULL,
            active_symbols INTEGER NOT NULL,
            market_symbols INTEGER NOT NULL,
            last_cycle_activated INTEGER NOT NULL,
            last_cycle_closed INTEGER NOT NULL,
            last_cycle_finalized INTEGER NOT NULL,
            last_cycle_failures INTEGER NOT NULL,
            last_error TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )
    return db


def status_payload(db, *, lifecycle_status="running", dry_run=False, heartbeat_at=None, result=None):
    heartbeat_at = heartbeat_at or datetime.now(timezone.utc).isoformat()
    upsert_worker_status(
        db,
        lifecycle_status=lifecycle_status,
        app_version="test-app",
        engine_version="test-engine",
        dry_run=dry_run,
        persist_exit_window=False,
        poll_seconds=10,
        reconcile_seconds=60,
        heartbeat_seconds=60,
        started_at="2026-08-03T10:00:00+00:00",
        heartbeat_at=heartbeat_at,
        result=result,
    )


class OperationWorkerStatusTests(unittest.TestCase):
    def test_observer_failure_does_not_remove_fresh_exit_coverage(self):
        db = create_status_db()
        status_payload(db, result={
            "cycle": 5, "failures": 0,
            "observation_scheduler_status": "degraded",
            "observation_scheduler_last_error": "ValueError:observation_compact_snapshot_too_large",
        })
        row = get_worker_status_row(db)
        status = add_transition_coverage(summarize_worker_status(row), False)
        self.assertFalse(status["healthy"])
        self.assertTrue(status["transitions_healthy"])
        self.assertEqual(status["signal_state"], "degraded")
        self.assertEqual(status["observation_signal_state"], "degraded")
        self.assertEqual(status["transition_owner"], "worker")
        self.assertEqual(status["transition_coverage"], "covered")
        self.assertEqual(status["last_error"], "ValueError:observation_compact_snapshot_too_large")
        for updates in (
            {"lifecycle_status": "degraded"},
            {"last_cycle_failures": 1},
            {"lifecycle_status": "stopped"},
            {"dry_run": True},
            {"last_heartbeat_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()},
        ):
            with self.subTest(updates=updates):
                failed = add_transition_coverage(summarize_worker_status({**row, **updates}), False)
                self.assertEqual(failed["transition_coverage"], "unprotected")
        status_payload(db, result={"cycle": 6, "failures": 0, "observation_scheduler_status": "ready"})
        recovered = summarize_worker_status(get_worker_status_row(db))
        self.assertTrue(recovered["healthy"])
        self.assertIsNone(recovered["observation_last_error"])
        self.assertIsNone(recovered["last_error"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM operation_worker_state").fetchone()[0], 1)
        db.close()

    def test_heartbeat_upsert_keeps_exactly_one_row(self):
        db = create_status_db()
        status_payload(db, lifecycle_status="starting", dry_run=True)
        status_payload(
            db,
            lifecycle_status="running",
            dry_run=True,
            result={
                "cycle": 2,
                "active_symbols": 3,
                "market_symbols": 3,
                "activated": 0,
                "closed": 0,
                "finalized_observations": 0,
                "failures": 0,
                "reconciled": True,
            },
        )

        row = db.execute("SELECT * FROM operation_worker_state").fetchone()
        count = db.execute("SELECT COUNT(*) AS count FROM operation_worker_state").fetchone()["count"]

        self.assertEqual(count, 1)
        self.assertEqual(row["cycle_count"], 2)
        self.assertEqual(row["active_symbols"], 3)
        self.assertEqual(row["lifecycle_status"], "running")
        db.close()

    def test_failed_cycle_does_not_advance_success_or_reconciliation(self):
        db = create_status_db()
        success = "2026-09-21T10:00:00+00:00"
        status_payload(db, heartbeat_at=success, result={"cycle": 1, "failures": 0, "reconciled": True})
        status_payload(db, lifecycle_status="degraded", heartbeat_at="2026-09-21T10:01:00+00:00", result={"cycle": 2, "failures": 1, "reconciled": True})
        row = get_worker_status_row(db)
        self.assertEqual(row["last_success_at"], success)
        self.assertEqual(row["last_reconcile_at"], success)
        db.close()

    def test_status_becomes_stale_after_three_heartbeat_intervals(self):
        db = create_status_db()
        now = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
        status_payload(
            db,
            heartbeat_at=(now - timedelta(seconds=181)).isoformat(),
            result={"cycle": 1, "failures": 0},
        )

        status = summarize_worker_status(get_worker_status_row(db), now=now)

        self.assertEqual(status["signal_state"], "stale")
        self.assertFalse(status["healthy"])
        self.assertEqual(status["stale_after_seconds"], 180)
        db.close()

    def test_transition_coverage_detects_safe_handoff_and_dual_processing(self):
        ready = {"healthy": True, "dry_run": False}
        dry_run = {"healthy": True, "dry_run": True}

        worker_owner = add_transition_coverage(ready, web_refresh_enabled=False)
        dual_owner = add_transition_coverage(ready, web_refresh_enabled=True)
        uncovered = add_transition_coverage(dry_run, web_refresh_enabled=False)

        self.assertEqual(worker_owner["transition_owner"], "worker")
        self.assertEqual(worker_owner["transition_coverage"], "covered")
        self.assertEqual(dual_owner["transition_owner"], "dual")
        self.assertEqual(dual_owner["transition_coverage"], "warning")
        self.assertEqual(uncovered["transition_owner"], "none")
        self.assertEqual(uncovered["transition_coverage"], "unprotected")

    def test_api_reports_dry_run_worker_while_web_retains_transitions(self):
        db = create_status_db()
        status_payload(
            db,
            dry_run=True,
            result={"cycle": 4, "active_symbols": 2, "failures": 0},
        )

        @contextmanager
        def connect_factory():
            yield db

        with (
            patch.object(app, "connect", connect_factory),
            patch.object(app, "WEB_OPERATION_REFRESH_ENABLED", True),
        ):
            status = app.operation_worker_status()

        self.assertEqual(status["signal_state"], "dry_run")
        self.assertEqual(status["transition_owner"], "web")
        self.assertEqual(status["transition_coverage"], "covered")
        db.close()

    def test_status_publication_failure_does_not_stop_worker(self):
        @contextmanager
        def unavailable_connection():
            raise RuntimeError("database unavailable")
            yield

        published = operation_worker.publish_runtime_status(
            operation_worker.WorkerSettings(dry_run=True),
            "2026-08-03T10:00:00+00:00",
            "degraded",
            connect_factory=unavailable_connection,
        )

        self.assertFalse(published)


if __name__ == "__main__":
    unittest.main()
