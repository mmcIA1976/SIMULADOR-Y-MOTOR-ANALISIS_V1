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


if __name__ == "__main__":
    unittest.main()
