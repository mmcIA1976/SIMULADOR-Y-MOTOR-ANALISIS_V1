import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import app
import market_data


class CursorResult:
    def __init__(self, *, row=None, rows=None, lastrowid=None, rowcount=1):
        self.row = row
        self.rows = rows or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class CreateOperationDb:
    def __init__(self):
        self.operation_params = None
        self.tick_params = None

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT COUNT(*) AS count FROM operations"):
            return CursorResult(row={"count": 0})
        if normalized.startswith("INSERT INTO operations"):
            self.operation_params = tuple(params)
            return CursorResult(lastrowid=901)
        if normalized.startswith("INSERT INTO price_ticks"):
            self.tick_params = tuple(params)
            return CursorResult(lastrowid=1901)
        raise AssertionError(f"Unexpected SQL: {normalized}")


def connect_factory_for(db):
    @contextmanager
    def factory():
        yield db

    return factory


class MarketPriceTickTests(unittest.TestCase):
    def test_market_operation_uses_fresh_binance_fill_and_records_entry_tick(self):
        db = CreateOperationDb()
        payload = app.CreateOperationPayload(
            symbol="XRPUSDT",
            side="long",
            time_horizon="intraday_short",
            entry_type="market",
            entry=1.07,
            margin=200,
            leverage=10,
            stop_loss=1.0623,
            take_profit=1.0768,
            mode="training",
        )

        with (
            patch.object(app, "current_user", return_value={"id": 3}),
            patch.object(app.market_data, "get_price", return_value=1.0653) as get_price,
            patch.object(app, "connect", connect_factory_for(db)),
            patch.object(app, "ensure_training_wallet_funded"),
            patch.object(
                app,
                "sync_user_cash_balance",
                return_value={"training": {"cash_balance": 1000.0}},
            ),
            patch.object(app, "record_wallet_event"),
        ):
            result = app.create_operation(payload, session_token="token")

        get_price.assert_called_once_with("XRPUSDT", force_refresh=True)
        self.assertEqual(result["entry"], 1.0653)
        self.assertEqual(result["requested_entry"], 1.07)
        self.assertEqual(db.operation_params[4], 1.0653)
        self.assertEqual(db.operation_params[14], 1.07)
        self.assertEqual(db.tick_params[0], 901)
        self.assertEqual(db.tick_params[2], 1.0653)
        self.assertEqual(db.tick_params[3], "market_entry_binance_usdm_futures")
        self.assertEqual(db.tick_params[4], result["started_at"])

    def test_market_operation_is_rejected_if_live_fill_invalidates_plan(self):
        payload = app.CreateOperationPayload(
            symbol="XRPUSDT",
            side="long",
            time_horizon="intraday_short",
            entry_type="market",
            entry=1.07,
            margin=200,
            leverage=10,
            stop_loss=1.0623,
            take_profit=1.0768,
            mode="training",
        )

        with (
            patch.object(app, "current_user", return_value={"id": 3}),
            patch.object(app.market_data, "get_price", return_value=1.08),
            self.assertRaises(app.HTTPException) as raised,
        ):
            app.create_operation(payload, session_token="token")

        self.assertEqual(raised.exception.status_code, 409)

    def test_force_refresh_bypasses_a_recent_price_cache(self):
        cached = {
            "price": 1.07,
            "captured_at": "2026-08-05T10:00:00+00:00",
            "captured_at_ms": market_data._now_ms(),
            "source": "test",
        }
        with (
            patch.dict(market_data._price_cache, {"XRPUSDT": cached}, clear=True),
            patch.object(
                market_data,
                "get_futures_json",
                return_value={"symbol": "XRPUSDT", "price": "1.06530000"},
            ) as loader,
        ):
            self.assertEqual(market_data.get_price("XRPUSDT"), 1.07)
            self.assertEqual(market_data.get_price("XRPUSDT", force_refresh=True), 1.0653)

        loader.assert_called_once()

    def test_periodic_ticks_keep_xrp_and_inj_decimals_and_deduplicate_interval(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE operations (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE price_ticks (
                id INTEGER PRIMARY KEY,
                operation_id INTEGER,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                source TEXT NOT NULL,
                captured_at TEXT NOT NULL
            );
            INSERT INTO operations (id, symbol, status) VALUES
                (1, 'XRPUSDT', 'OPEN'),
                (2, 'INJUSDT', 'OPEN'),
                (3, 'XRPUSDT', 'CLOSED');
            INSERT INTO price_ticks (operation_id, symbol, price, source, captured_at) VALUES
                (1, 'XRPUSDT', 1.0653, 'market_entry', '2026-08-05T10:00:00+00:00'),
                (2, 'INJUSDT', 12.345, 'market_entry', '2026-08-05T10:00:00+00:00');
            """
        )

        before_interval = app.record_periodic_active_operation_ticks(
            db,
            "XRPUSDT",
            1.0654,
            "2026-08-05T10:01:59+00:00",
        )
        xrp_inserted = app.record_periodic_active_operation_ticks(
            db,
            "XRPUSDT",
            1.0654,
            "2026-08-05T10:02:00+00:00",
        )
        inj_inserted = app.record_periodic_active_operation_ticks(
            db,
            "INJUSDT",
            12.347,
            "2026-08-05T10:02:00+00:00",
        )
        repeated = app.record_periodic_active_operation_ticks(
            db,
            "XRPUSDT",
            1.0655,
            "2026-08-05T10:02:00+00:00",
        )

        self.assertEqual(before_interval, 0)
        self.assertEqual(xrp_inserted, 1)
        self.assertEqual(inj_inserted, 1)
        self.assertEqual(repeated, 0)
        rows = db.execute(
            "SELECT operation_id, price, source FROM price_ticks ORDER BY id"
        ).fetchall()
        self.assertEqual(float(rows[-2]["price"]), 1.0654)
        self.assertEqual(float(rows[-1]["price"]), 12.347)
        self.assertEqual(rows[-2]["source"], "operation_worker_120s")
        self.assertEqual(rows[-1]["source"], "operation_worker_120s")
        self.assertFalse(any(row["operation_id"] == 3 for row in rows))
        db.close()


if __name__ == "__main__":
    unittest.main()
