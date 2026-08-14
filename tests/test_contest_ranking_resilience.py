import inspect
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app
import market_data


def connect_factory_for(*databases):
    remaining = iter(databases)

    @contextmanager
    def factory():
        yield next(remaining)

    return factory


class ContestRankingResilienceTests(unittest.TestCase):
    def setUp(self):
        market_data._price_cache.clear()

    def tearDown(self):
        market_data._price_cache.clear()

    def test_batch_price_loader_uses_one_request_for_all_symbols(self):
        payload = [
            {"symbol": "BTCUSDT", "price": "64001.5"},
            {"symbol": "ETHUSDT", "price": "3200.25"},
            {"symbol": "XRPUSDT", "price": "0.62"},
        ]

        with patch.object(market_data, "get_futures_json", return_value=payload) as loader:
            prices = market_data.get_prices(["ethusdt", "BTCUSDT", "BTCUSDT"])

        loader.assert_called_once_with(
            market_data.BINANCE_USDM_ALL_PRICES_PATH,
            timeout_seconds=market_data.RANKING_PRICE_TIMEOUT_SECONDS,
            max_host_attempts=market_data.RANKING_PRICE_MAX_HOST_ATTEMPTS,
        )
        self.assertEqual(prices, {"BTCUSDT": 64001.5, "ETHUSDT": 3200.25})

    def test_batch_price_loader_falls_back_to_stale_memory_cache(self):
        market_data._remember_price("BTCUSDT", 63950.0)

        with (
            patch.object(market_data, "PRICE_CACHE_TTL_SECONDS", -1),
            patch.object(market_data, "get_futures_json", side_effect=RuntimeError("temporary")),
        ):
            prices = market_data.get_prices(["BTCUSDT"])

        self.assertEqual(prices, {"BTCUSDT": 63950.0})

    def test_execution_batch_never_republishes_stale_memory_as_fresh(self):
        market_data._remember_price("BTCUSDT", 63950.0)

        with (
            patch.object(market_data, "PRICE_CACHE_TTL_SECONDS", -1),
            patch.object(
                market_data,
                "get_futures_json",
                side_effect=RuntimeError("temporary"),
            ),
        ):
            prices = market_data.get_prices(
                ["BTCUSDT"],
                allow_stale=False,
            )

        self.assertEqual(prices, {})

    def test_current_contest_skips_web_transitions_and_reuses_one_price_snapshot(self):
        season = {"id": 4, "code": "2026-08", "starting_balance": 1000}
        entry = {"id": 9, "user_id": 7, "season_id": 4}
        portfolio = {
            "contest": {
                "starting_balance": 1000,
                "cash_balance": 800,
                "closed_pnl": 0,
                "total_equity_without_unrealized": 1000,
            }
        }
        prices = {"BTCUSDT": 64000.0, "ETHUSDT": 3200.0}
        leaderboard = [{"user_id": 7, "rank": 1}]
        first_db = object()
        second_db = object()

        with (
            patch.object(app, "WEB_OPERATION_REFRESH_ENABLED", False),
            patch.object(app, "current_user", return_value={"id": 7}),
            patch.object(app, "connect", connect_factory_for(first_db, second_db)),
            patch.object(app, "ensure_current_contest_season", return_value=season),
            patch.object(app, "refresh_contest_active_operations") as refresh_operations,
            patch.object(app, "contest_open_price_symbols", return_value=["BTCUSDT", "ETHUSDT"]),
            patch.object(app, "latest_recorded_prices_for_symbols", return_value={}),
            patch.object(app, "live_prices_for_symbols", return_value=prices) as load_prices,
            patch.object(app, "get_contest_entry", return_value=entry),
            patch.object(app, "calculate_portfolio_from_db", return_value=portfolio),
            patch.object(app, "contest_leaderboard", return_value=leaderboard) as build_leaderboard,
            patch.object(app, "contest_history", return_value=[]),
            patch.object(app, "apply_contest_unrealized_to_portfolio") as apply_unrealized,
        ):
            result = app.contest_current(session_token="token")

        refresh_operations.assert_not_called()
        load_prices.assert_called_once_with(["BTCUSDT", "ETHUSDT"])
        build_leaderboard.assert_called_once_with(second_db, 4, live_prices=prices)
        apply_unrealized.assert_called_once_with(
            second_db,
            portfolio["contest"],
            7,
            4,
            live_prices=prices,
        )
        self.assertEqual(result["leaderboard"], leaderboard)
        self.assertEqual(result["active_refresh"], {"activated_operations": [], "closed_operations": []})

    def test_frontend_preserves_last_ranking_on_transient_failure(self):
        source = Path(app.__file__).with_name("app.js").read_text(encoding="utf-8")
        start = source.index("async function loadContest()")
        end = source.index("function setContestRefreshStatus", start)
        load_contest_source = source[start:end]

        catch_start = load_contest_source.index("} catch (error) {")
        catch_source = load_contest_source[catch_start:]
        self.assertNotIn("contestState = null", catch_source)
        self.assertIn("Se conserva el ultimo ranking valido", catch_source)
        self.assertIn("if (contestLoadInFlight)", load_contest_source)

    def test_leaderboard_does_not_download_full_analysis_json(self):
        source = inspect.getsource(app.contest_leaderboard)

        self.assertNotIn("analysis_json", source)
        self.assertIn("recommendation_tp_probability", source)


if __name__ == "__main__":
    unittest.main()
