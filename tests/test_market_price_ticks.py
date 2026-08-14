import unittest
import inspect
from contextlib import contextmanager
from pathlib import Path
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
            patch.object(
                app,
                "require_fresh_worker_market_price",
                return_value={
                    "price": 1.0653,
                    "captured_at": "2026-08-05T10:00:00+00:00",
                },
            ) as get_price,
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

        get_price.assert_called_once_with("XRPUSDT")
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
            patch.object(
                app,
                "require_fresh_worker_market_price",
                return_value={
                    "price": 1.08,
                    "captured_at": "2026-08-05T10:00:00+00:00",
                },
            ),
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

    def test_binance_history_is_reconstructed_every_120_seconds_without_storage(self):
        def kline(open_time_ms, close_price):
            return [
                open_time_ms,
                str(close_price),
                str(close_price),
                str(close_price),
                str(close_price),
                "10",
                open_time_ms + 59_999,
            ]

        klines = [
            kline(0, 1.0653),
            kline(60_000, 1.0654),
            kline(120_000, 1.0655),
            kline(180_000, 1.0656),
            kline(240_000, 1.0657),
        ]

        points = app.sampled_market_history_points(
            klines,
            sample_seconds=120,
            now_ms=239_999,
        )

        self.assertEqual([point["price"] for point in points], [1.0654, 1.0656])
        self.assertTrue(
            all(point["source"] == "binance_usdm_futures_120s_reconstructed" for point in points)
        )

    def test_price_poll_never_persists_periodic_chart_ticks(self):
        self.assertNotIn("INSERT INTO price_ticks", inspect.getsource(app.price))

    def test_closed_operation_history_uses_its_close_time(self):
        with patch.object(app.market_data, "get_klines", return_value=[]) as get_klines:
            result = app.market_history(
                symbol="XRPUSDT",
                minutes=480,
                sample_seconds=120,
                end_time_ms=1_775_383_200_000,
            )

        get_klines.assert_called_once_with(
            "XRPUSDT",
            "1m",
            480,
            end_time_ms=1_775_383_200_000,
        )
        self.assertEqual(result["end_time_ms"], 1_775_383_200_000)

    def test_frontend_labels_chart_points_as_displayed_not_stored(self):
        project_dir = Path(__file__).resolve().parents[1]
        index_html = (project_dir / "index.html").read_text(encoding="utf-8")
        app_js = (project_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn("Puntos mostrados", index_html)
        self.assertNotIn("Registros guardados", index_html)
        self.assertIn("sample_seconds=120", app_js)
        self.assertIn("Precio vivo publicado por el worker", app_js)


if __name__ == "__main__":
    unittest.main()
