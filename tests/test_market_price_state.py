import inspect
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import market_price_state
import operation_worker


class Cursor:
    def __init__(self, rows=None, rowcount=1):
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class RecordingDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))
        if "SELECT symbol, price" in query:
            return Cursor(self.rows)
        if "SELECT symbol" in query and "watch_until" in query:
            return Cursor(self.rows)
        return Cursor(rowcount=1)


class MarketPriceStateTests(unittest.TestCase):
    def test_worker_publication_is_one_upsert_row_per_symbol(self):
        db = RecordingDb()
        captured = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

        published = market_price_state.publish_market_prices(
            db,
            {"BTCUSDT": 64000.0, "ETHUSDT": 3200.0},
            captured_at=captured,
        )

        self.assertEqual(published, 2)
        inserts = [query for query, _ in db.calls if query.startswith("INSERT")]
        self.assertEqual(len(inserts), 2)
        self.assertTrue(all("ON CONFLICT (symbol) DO UPDATE" in query for query in inserts))
        self.assertTrue(all("price_ticks" not in query for query in inserts))

    def test_quote_freshness_is_based_on_worker_capture_time(self):
        captured = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)
        row = {
            "symbol": "XRPUSDT",
            "price": 1.0653,
            "source": "binance_usdm_futures_ticker_batch",
            "publisher": "operation_worker",
            "captured_at": captured,
        }

        fresh = market_price_state.summarize_market_price(
            row,
            now=captured + timedelta(seconds=20),
        )
        stale = market_price_state.summarize_market_price(
            row,
            now=captured + timedelta(seconds=36),
        )

        self.assertTrue(fresh["fresh"])
        self.assertFalse(stale["fresh"])
        self.assertEqual(fresh["authority"], "operation_worker")

    def test_watch_registration_is_a_bounded_upsert(self):
        db = RecordingDb()
        requested = datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)

        symbol = market_price_state.request_market_price_watch(
            db,
            "ethusdt",
            requested_at=requested,
        )

        self.assertEqual(symbol, "ETHUSDT")
        query, params = db.calls[0]
        self.assertIn("ON CONFLICT (symbol) DO UPDATE", query)
        self.assertEqual(params[0], "ETHUSDT")
        self.assertEqual(
            datetime.fromisoformat(params[1]),
            requested + timedelta(seconds=300),
        )

    def test_worker_batches_all_requested_prices_once(self):
        now_ms = 1_775_383_200_000
        state = operation_worker.WorkerState(last_reconcile_ms=now_ms)
        settings = operation_worker.WorkerSettings(reconcile_seconds=60)
        batch = Mock(
            return_value={"BTCUSDT": 64000.0, "ETHUSDT": 3200.0}
        )

        with patch.object(operation_worker.market_data, "get_prices", batch):
            inputs, reconciled, failures, snapshot = operation_worker.collect_market_inputs(
                {"BTCUSDT": now_ms - 60_000},
                {"ETHUSDT"},
                state,
                settings,
                now_ms,
            )

        batch.assert_called_once_with(
            ["BTCUSDT", "ETHUSDT"],
            allow_stale=False,
        )
        self.assertFalse(reconciled)
        self.assertEqual(failures, 0)
        self.assertEqual(snapshot, {"BTCUSDT": 64000.0, "ETHUSDT": 3200.0})
        self.assertEqual({item.symbol for item in inputs}, {"BTCUSDT", "ETHUSDT"})

    def test_web_price_path_contains_no_direct_binance_price_call(self):
        source = inspect.getsource(__import__("app").price)
        self.assertNotIn("market_data.get_price", source)
        self.assertIn("worker_market_price_snapshot", source)


if __name__ == "__main__":
    unittest.main()
