import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import app
import operation_worker


class RowsCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RowcountCursor:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class ActiveSymbolsDb:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if "GROUP BY symbol" in query:
            return RowsCursor(self.rows)
        raise AssertionError(f"Unexpected SQL in worker orchestration test: {query}")


class StaleCloseDb:
    def __init__(self, operation):
        self.operation = operation

    def execute(self, query, params=None):
        if "SELECT * FROM operations" in query:
            return RowsCursor([self.operation])
        if "UPDATE operations" in query:
            return RowcountCursor(0)
        raise AssertionError(f"Unexpected SQL in stale close test: {query}")


class ListOperationsReadOnlyDb:
    def __init__(self, operation):
        self.operation = operation

    def execute(self, query, params=None):
        if "SELECT * FROM operations WHERE user_id" in query:
            return RowsCursor([self.operation])
        if "SELECT DISTINCT ON (operation_id)" in query:
            return RowsCursor([])
        if "FROM price_ticks" in query:
            return RowsCursor([])
        raise AssertionError(f"Unexpected write or query in operations GET: {query}")


def connect_factory_for(db):
    @contextmanager
    def factory():
        yield db

    return factory


class OperationWorkerTests(unittest.TestCase):
    def test_environment_defaults_worker_to_dry_run(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = operation_worker.WorkerSettings.from_env()

        self.assertTrue(settings.dry_run)
        self.assertFalse(settings.persist_exit_window)

    def test_dry_run_collects_market_data_without_processing_operations(self):
        db = ActiveSymbolsDb(
            [{"symbol": "BTCUSDT", "scan_start": "2026-08-03T10:00:00+00:00"}]
        )
        settings = operation_worker.WorkerSettings(dry_run=True)

        with (
            patch.object(operation_worker, "refresh_symbol_active_operations") as refresh,
            patch.object(operation_worker, "finalize_due_observations") as finalize,
        ):
            result = operation_worker.run_worker_cycle(
                operation_worker.WorkerState(),
                settings,
                connect_factory=connect_factory_for(db),
                price_loader=Mock(return_value=64000.0),
                kline_loader=Mock(return_value=[]),
                now_ms=1_775_383_200_000,
            )

        refresh.assert_not_called()
        finalize.assert_not_called()
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["persisted_price_samples"], 0)

    def test_worker_cycle_reads_prices_and_persists_periodic_samples(self):
        db = ActiveSymbolsDb(
            [
                {"symbol": "BTCUSDT", "scan_start": "2026-08-03T10:00:00+00:00"},
                {"symbol": "ETHUSDT", "scan_start": "2026-08-03T10:00:00+00:00"},
            ]
        )
        prices = {"BTCUSDT": 64000.0, "ETHUSDT": 3200.0}
        price_loader = Mock(side_effect=lambda symbol: prices[symbol])
        kline_loader = Mock(return_value=[])
        settings = operation_worker.WorkerSettings(
            poll_seconds=10,
            reconcile_seconds=60,
            persist_exit_window=False,
        )
        state = operation_worker.WorkerState()

        with (
            patch.object(operation_worker, "refresh_symbol_active_operations", return_value=({}, {})) as refresh,
            patch.object(operation_worker, "finalize_due_observations", return_value=[]),
            patch.object(operation_worker, "record_periodic_active_operation_ticks", return_value=1) as record_samples,
        ):
            result = operation_worker.run_worker_cycle(
                state,
                settings,
                connect_factory=connect_factory_for(db),
                price_loader=price_loader,
                kline_loader=kline_loader,
                now_ms=1_775_383_200_000,
            )

        self.assertEqual(price_loader.call_count, 2)
        self.assertEqual(kline_loader.call_count, 2)
        self.assertEqual(refresh.call_count, 2)
        for call in refresh.call_args_list:
            self.assertEqual(call.kwargs["market_klines"], [])
            self.assertFalse(call.kwargs["persist_exit_window"])
        self.assertEqual(result["persisted_price_samples"], 2)
        self.assertEqual(result["failures"], 0)
        self.assertEqual(record_samples.call_count, 2)
        for call in record_samples.call_args_list:
            self.assertEqual(call.kwargs["minimum_interval_seconds"], 120.0)
        self.assertEqual(result["active_symbols"], 2)
        self.assertTrue(result["reconciled"])

    def test_ordinary_cycle_skips_historical_download(self):
        db = ActiveSymbolsDb(
            [{"symbol": "BTCUSDT", "scan_start": "2026-08-03T10:00:00+00:00"}]
        )
        settings = operation_worker.WorkerSettings(reconcile_seconds=60, persist_exit_window=False)
        now_ms = 1_775_383_200_000
        state = operation_worker.WorkerState(last_reconcile_ms=now_ms - 10_000)
        kline_loader = Mock(side_effect=AssertionError("klines should not be fetched"))

        with (
            patch.object(operation_worker, "refresh_symbol_active_operations", return_value=({}, {})) as refresh,
            patch.object(operation_worker, "record_periodic_active_operation_ticks", return_value=0) as record_samples,
        ):
            result = operation_worker.run_worker_cycle(
                state,
                settings,
                connect_factory=connect_factory_for(db),
                price_loader=Mock(return_value=64000.0),
                kline_loader=kline_loader,
                now_ms=now_ms,
            )

        kline_loader.assert_not_called()
        self.assertEqual(refresh.call_args.kwargs["market_klines"], [])
        self.assertFalse(result["reconciled"])
        self.assertEqual(result["persisted_price_samples"], 0)
        self.assertEqual(result["failures"], 0)
        record_samples.assert_called_once()

    def test_failed_reconciliation_does_not_advance_market_cursor(self):
        db = ActiveSymbolsDb(
            [{"symbol": "BTCUSDT", "scan_start": "2026-08-03T10:00:00+00:00"}]
        )
        settings = operation_worker.WorkerSettings(reconcile_seconds=60)
        state = operation_worker.WorkerState(last_reconcile_ms=1_775_383_000_000)
        now_ms = 1_775_383_200_000

        with patch.object(operation_worker, "finalize_due_observations", return_value=[]):
            result = operation_worker.run_worker_cycle(
                state,
                settings,
                connect_factory=connect_factory_for(db),
                price_loader=Mock(side_effect=RuntimeError("provider unavailable")),
                kline_loader=Mock(return_value=[]),
                now_ms=now_ms,
            )

        self.assertEqual(result["failures"], 1)
        self.assertEqual(state.last_reconcile_ms, 1_775_383_000_000)

    def test_web_price_poll_is_read_only_when_worker_owns_transitions(self):
        with (
            patch.object(app, "WEB_OPERATION_REFRESH_ENABLED", False),
            patch.object(app.market_data, "get_price", return_value=64000.0),
            patch.object(app, "connect") as connect_mock,
        ):
            result = app.price(symbol="BTCUSDT", record=True, session_token=None)

        connect_mock.assert_not_called()
        self.assertEqual(result["operation_processing"], "worker")
        self.assertEqual(result["operation_ids"], [])
        self.assertEqual(result["closed_operations"], [])

    def test_worker_close_uses_one_compact_tick_instead_of_dense_window(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE operations (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                closed_at TEXT,
                close_price REAL,
                close_reason TEXT,
                final_pnl REAL,
                observation_status TEXT,
                observation_until TEXT,
                closing_note TEXT,
                learning_outcome TEXT,
                learning_summary TEXT,
                exit_evidence_json TEXT,
                contest_season_id INTEGER
            );
            INSERT INTO operations (
                id, user_id, symbol, side, status, mode, entry, stop_loss, take_profit
            ) VALUES (1, 7, 'BTCUSDT', 'long', 'OPEN', 'training', 100, 90, 110);
            """
        )
        compact_tick = Mock()
        dense_window = Mock()

        with (
            patch.object(
                app,
                "triggered_exit_from_market_path",
                return_value=(
                    "take_profit",
                    110.0,
                    "2026-08-03T10:15:00+00:00",
                    {"source": "test_market_path"},
                ),
            ),
            patch.object(app, "approximate_pnl", return_value=10.0),
            patch.object(app, "record_compact_exit_tick", compact_tick),
            patch.object(app, "record_exit_window_ticks", dense_window),
            patch.object(
                app,
                "sync_user_cash_balance",
                return_value={"training": {"cash_balance": 1010.0}},
            ),
            patch.object(app, "record_wallet_event"),
        ):
            result = app.close_triggered_open_operations(
                db,
                "BTCUSDT",
                110.0,
                market_klines=[],
                persist_exit_window=False,
            )

        self.assertIn(1, result)
        compact_tick.assert_called_once()
        dense_window.assert_not_called()
        row = db.execute("SELECT status, close_reason FROM operations WHERE id = 1").fetchone()
        self.assertEqual(row["status"], "CLOSED")
        self.assertEqual(row["close_reason"], "take_profit")
        db.close()

    def test_stale_close_candidate_does_not_repeat_side_effects(self):
        operation = {
            "id": 1,
            "user_id": 7,
            "symbol": "BTCUSDT",
            "side": "long",
            "status": "OPEN",
            "mode": "training",
            "entry": 100.0,
            "margin": 100.0,
            "leverage": 1.0,
            "stop_loss": 90.0,
            "take_profit": 110.0,
            "contest_season_id": None,
        }
        db = StaleCloseDb(operation)

        with (
            patch.object(
                app,
                "triggered_exit_from_market_path",
                return_value=(
                    "take_profit",
                    110.0,
                    "2026-08-03T10:15:00+00:00",
                    {"source": "test_market_path"},
                ),
            ),
            patch.object(app, "approximate_pnl", return_value=10.0),
            patch.object(app, "record_compact_exit_tick") as compact_tick,
            patch.object(app, "record_exit_window_ticks") as dense_window,
            patch.object(app, "sync_user_cash_balance") as sync_balance,
            patch.object(app, "record_wallet_event") as wallet_event,
        ):
            result = app.close_triggered_open_operations(
                db,
                "BTCUSDT",
                110.0,
                market_klines=[],
                persist_exit_window=False,
            )

        self.assertEqual(result, {})
        compact_tick.assert_not_called()
        dense_window.assert_not_called()
        sync_balance.assert_not_called()
        wallet_event.assert_not_called()

    def test_ticks_get_does_not_synthesize_historical_exit_data(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE operations (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                close_reason TEXT,
                close_price REAL,
                closed_at TEXT,
                closing_note TEXT,
                exit_evidence_json TEXT
            );
            CREATE TABLE price_ticks (
                id INTEGER PRIMARY KEY,
                operation_id INTEGER,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                source TEXT NOT NULL,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO operations (
                id, user_id, symbol, status, close_reason, close_price,
                exit_evidence_json
            ) VALUES (
                1, 7, 'BTCUSDT', 'CLOSED', 'stop_loss', 90,
                '{"source":"test_market_path"}'
            );
            """
        )

        with (
            patch.object(app, "current_user", return_value={"id": 7}),
            patch.object(app, "connect", connect_factory_for(db)),
        ):
            result = app.operation_ticks(1, limit=20, session_token="test-token")

        tick_count = db.execute("SELECT COUNT(*) AS count FROM price_ticks").fetchone()["count"]
        self.assertEqual(result["ticks"], [])
        self.assertEqual(tick_count, 0)
        db.close()

    def test_operations_get_does_not_backfill_historical_exit_data(self):
        operation = {
            "id": 1,
            "user_id": 7,
            "symbol": "BTCUSDT",
            "status": "CLOSED",
            "close_reason": "stop_loss",
            "close_price": 90.0,
            "closed_at": None,
            "closing_note": None,
            "exit_evidence_json": '{"source":"test_market_path"}',
            "activation_evidence_json": None,
        }
        db = ListOperationsReadOnlyDb(operation)

        with (
            patch.object(app, "current_user", return_value={"id": 7}),
            patch.object(app, "connect", connect_factory_for(db)),
            patch.object(app, "finalize_due_observations"),
            patch.object(app, "refresh_learning_conclusions"),
        ):
            result = app.list_operations(session_token="test-token")

        self.assertEqual(len(result["operations"]), 1)
        self.assertEqual(result["operations"][0]["ticks"], [])

    def test_shared_symbol_klines_before_operation_start_are_ignored(self):
        operation = {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry": 100.0,
            "stop_loss": 90.0,
            "take_profit": 110.0,
            "started_at": "2026-08-03T10:05:00+00:00",
            "created_at": "2026-08-03T10:05:00+00:00",
        }
        old_open_ms = int(datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
        old_kline = [old_open_ms, "100", "111", "99", "110", "1", old_open_ms + 59_999]

        trigger = app.triggered_exit_from_market_klines(operation, 100.0, [old_kline])

        self.assertIsNone(trigger)


if __name__ == "__main__":
    unittest.main()
