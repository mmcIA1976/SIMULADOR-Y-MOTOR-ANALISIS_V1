import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import market_data
from binance_request_budget import (
    BinanceDeferred, MemoryBudgetStore, RequestBudget,
    critical_market_requests, exchange_state, request_weight,
)


class BinanceRequestBudgetTests(unittest.TestCase):
    def setUp(self):
        market_data._endpoint_host_retry_at.clear()
        market_data._endpoint_preferred_bases.clear()
        market_data._kline_page_cache.clear()

    def tearDown(self):
        self.setUp()

    def test_deferred_window_is_bounded_and_telemetry_attributes_the_header(self):
        now = [120.0]
        guard = RequestBudget(MemoryBudgetStore(), clock=lambda: now[0])
        url = "https://fapi.binance.com/fapi/v1/depth?limit=20"
        guard.acquire(url)
        guard.observe({"X-MBX-USED-WEIGHT-1M": "2300"}, url=url)
        with self.assertRaises(BinanceDeferred) as blocked:
            guard.acquire(url)
        self.assertEqual(blocked.exception.retry_after_seconds, 62)
        self.assertEqual(guard.status()["endpoint_counts"]["depth"], {"requests": 1, "weight": 2})
        self.assertEqual(guard.status()["last_observed_endpoint"], "/fapi/v1/depth")
        now[0] = 182.0
        guard.acquire(url)
        self.assertEqual(guard.status()["endpoint_counts"]["depth"]["requests"], 1)

    def test_closed_complete_pages_are_reused_without_mutating_cached_rows(self):
        rows = [[index * 60_000, "100", "101", "99", "100", "1", (index + 1) * 60_000 - 1]
                for index in range(3)]
        with patch.object(market_data, "_now_ms", return_value=300_000), patch.object(
            market_data, "get_futures_json", return_value=rows) as loader:
            first = market_data.get_klines("BTCUSDT", "1m", 3, 0, 200_000)
            second = market_data.get_klines("BTCUSDT", "1m", 3, 0, 250_000)
            second[0][4] = "poisoned"
            third = market_data.get_klines("BTCUSDT", "1m", 3, 0, 250_000)
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(first[0][4], "100")
        self.assertEqual(third[0][4], "100")

    def test_open_partial_or_gapped_pages_are_never_cached(self):
        rows = [[index * 60_000, "100", "101", "99", "100", "1", (index + 1) * 60_000 - 1]
                for index in range(3)]
        for payload, now, end in ((rows, 150_000, 200_000), (rows[:2], 300_000, 200_000),
                                  ([rows[0], rows[2], rows[2]], 300_000, 200_000),
                                  (rows, 300_000, 100_000)):
            with self.subTest(now=now, end=end, count=len(payload)), patch.object(
                market_data, "_now_ms", return_value=now), patch.object(
                market_data, "get_futures_json", return_value=payload) as loader:
                market_data.get_klines("BTCUSDT", "1m", 3, 0, end)
                market_data.get_klines("BTCUSDT", "1m", 3, 0, end)
                self.assertEqual(loader.call_count, 2)

    def test_endpoint_failure_cooldown_does_not_block_prices(self):
        response = io.BytesIO(b'{"price":"100"}')
        response.headers = {}
        with patch.object(market_data, "_futures_request", side_effect=RuntimeError("unavailable")) as loader:
            self.assertIsNone(market_data.get_futures_json_optional("/fapi/v1/depth?symbol=BTCUSDT"))
            self.assertIsNone(market_data.get_futures_json_optional("/fapi/v1/depth?symbol=ETHUSDT"))
            self.assertEqual(loader.call_count, 4)  # Each failed host is skipped on the second pair.
        with patch.object(market_data, "_futures_request", return_value=response):
            self.assertEqual(market_data.get_futures_json("/fapi/v1/ticker/price?symbol=BTCUSDT"), {"price": "100"})

    def test_429_stops_host_failover_and_survives_new_process(self):
        now = [1_790_182_000.0]
        shared = MemoryBudgetStore()
        first = RequestBudget(shared, clock=lambda: now[0])
        previous_preferred = market_data._preferred_futures_base_url
        response = HTTPError(
            "https://fapi.binance.com/fapi/v1/ticker/price", 429,
            "Too Many Requests", {"Retry-After": "90"},
            io.BytesIO(b'{"code":-1003,"msg":"Too many requests"}'),
        )
        with patch.object(market_data, "budget", first), patch.object(
            market_data.urllib.request, "urlopen", side_effect=response
        ) as upstream:
            with self.assertRaises(BinanceDeferred):
                market_data.get_futures_json("/fapi/v1/ticker/price?symbol=BTCUSDT")
            self.assertEqual(upstream.call_count, 1)
            self.assertGreaterEqual(first.status()["blocked_until_ms"], int((now[0] + 90) * 1000))
        market_data._preferred_futures_base_url = previous_preferred

        restarted = RequestBudget(shared, clock=lambda: now[0])
        with self.assertRaises(BinanceDeferred), patch.object(
            market_data.urllib.request, "urlopen"
        ) as upstream:
            with patch.object(market_data, "budget", restarted):
                market_data.get_json(market_data.BINANCE_FUNDING_URL.format(symbol="BTCUSDT"))
        upstream.assert_not_called()

    def test_optional_quota_preserves_critical_reserve(self):
        now = [1_790_182_000.0]
        guard = RequestBudget(MemoryBudgetStore(), clock=lambda: now[0])
        url = "https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&limit=1000"
        count = 0
        while True:
            try:
                guard.acquire(url)
                count += 1
            except BinanceDeferred:
                break
        self.assertGreater(count, 0)
        self.assertLessEqual(count, 60)
        with critical_market_requests():
            guard.acquire("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT")

    def test_external_weight_header_restricts_optional_first(self):
        now = [1_790_182_000.0]
        guard = RequestBudget(MemoryBudgetStore(), clock=lambda: now[0])
        guard.observe({"X-MBX-USED-WEIGHT-1M": "1300"})
        url = "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
        with self.assertRaises(BinanceDeferred):
            guard.acquire(url)
        with critical_market_requests():
            guard.acquire(url)

    def test_shared_atomic_window_resets_without_history(self):
        row = dict(minute=-1, weight=0, requests=0, observed=0,
                   blocked_until=0.0, reason="")
        row, granted = exchange_state(row, now=100.0, weight=50, requests=5)
        self.assertTrue(granted)
        self.assertEqual(row["weight"], 50)
        row, granted = exchange_state(row, now=161.0, weight=50, requests=5)
        self.assertTrue(granted)
        self.assertEqual(row["weight"], 50)
        self.assertEqual(row["requests"], 5)

    def test_endpoint_costs_are_conservative(self):
        self.assertEqual(request_weight("https://fapi.binance.com/fapi/v1/aggTrades?limit=1000"), 20)
        self.assertEqual(request_weight("https://fapi.binance.com/fapi/v1/depth?limit=100"), 5)
        self.assertEqual(request_weight("https://fapi.binance.com/fapi/v1/klines?limit=1000"), 5)

    def test_official_web_edge_is_treated_as_futures_market_data(self):
        self.assertTrue(market_data._is_binance_futures_url(
            "https://www.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
        ))


if __name__ == "__main__":
    unittest.main()
