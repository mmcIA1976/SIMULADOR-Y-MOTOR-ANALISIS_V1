from __future__ import annotations

import unittest

from m5_live_inputs import collect_live_rule_context


class FakeMarketDataClient:
    def __init__(self) -> None:
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name, args))

    def get_depth(self, symbol, limit):
        self._record("depth", symbol, limit)
        return {"bids": [["100", "2"]], "asks": [["101", "3"]]}

    def get_futures_book_ticker(self, symbol):
        self._record("futures_book", symbol)
        return {"bidPrice": "100", "askPrice": "101"}

    def get_spot_book_ticker(self, symbol):
        self._record("spot_book", symbol)
        return {"bidPrice": "99", "askPrice": "100"}

    def get_spot_exchange_info(self, symbol):
        self._record("spot_info", symbol)
        return {"symbols": [{"symbol": symbol, "status": "TRADING"}]}

    def get_funding_snapshot(self, symbol):
        self._record("funding_snapshot", symbol)
        return {"lastFundingRate": "0.0001"}

    def get_funding_info(self, symbol):
        self._record("funding_info", symbol)
        return {"symbol": symbol, "fundingIntervalHours": 8}

    def get_funding_history(self, symbol, limit, start_ms, end_ms):
        self._record(
            "funding_history",
            symbol,
            limit,
            start_ms,
            end_ms,
        )
        return [{"fundingTime": end_ms - 1, "fundingRate": "0.0001"}]

    def get_open_interest_history(
        self,
        symbol,
        interval,
        limit,
        start_ms,
        end_ms,
    ):
        self._record(
            "open_interest_history",
            symbol,
            interval,
            limit,
            start_ms,
            end_ms,
        )
        return [{"timestamp": start_ms}, {"timestamp": end_ms}]

    def get_taker_long_short_ratio_history(
        self,
        symbol,
        interval,
        limit,
        start_ms,
        end_ms,
    ):
        self._record(
            "taker_history",
            symbol,
            interval,
            limit,
            start_ms,
            end_ms,
        )
        return [{"timestamp": start_ms}, {"timestamp": end_ms}]

    def get_global_long_short_ratio_history(
        self,
        symbol,
        interval,
        limit,
        start_ms,
        end_ms,
    ):
        self._record(
            "global_long_short_history",
            symbol,
            interval,
            limit,
            start_ms,
            end_ms,
        )
        return [{"timestamp": end_ms}]

    def get_top_crypto_assets(self, limit):
        self._record("market_breadth_assets", limit)
        return [{"id": "bitcoin"}]

    def get_fear_greed_history(self, limit):
        self._record("fear_greed_history", limit)
        return [{"value": "50"}]

    def get_liquidation_context(self, symbol, market_price):
        self._record("liquidation_context", symbol, market_price)
        return {
            "available": True,
            "symbol": symbol,
            "market_price": market_price,
        }


class M5LiveInputsTests(unittest.TestCase):
    def test_collects_every_public_context_source_with_one_cutoff(self):
        client = FakeMarketDataClient()
        context = collect_live_rule_context(
            symbol="btcusdt",
            horizon_seconds=3_600,
            interval_seconds=300,
            request_cutoff_at="2026-07-28T12:00:00+00:00",
            client=client,
            market_price=100.0,
            now_ms=lambda: 1_000,
        )

        self.assertEqual(context["symbol"], "BTCUSDT")
        self.assertEqual(context["interval"], "5m")
        self.assertEqual(context["captured_at_ms"], 1_000)
        self.assertEqual(len(client.calls), 13)
        self.assertEqual(
            {name for name, _ in client.calls},
            {
                "depth",
                "futures_book",
                "spot_book",
                "spot_info",
                "funding_snapshot",
                "funding_info",
                "funding_history",
                "open_interest_history",
                "taker_history",
                "global_long_short_history",
                "market_breadth_assets",
                "fear_greed_history",
                "liquidation_context",
            },
        )
        for name, args in client.calls:
            if name in {
                "funding_history",
                "open_interest_history",
                "taker_history",
                "global_long_short_history",
            }:
                if args[-2] is not None:
                    self.assertLess(args[-2], args[-1])
                self.assertEqual(args[-1], context["request_cutoff_ms"])
        funding_call = next(
            args for name, args in client.calls
            if name == "funding_history"
        )
        crowding_call = next(
            args for name, args in client.calls
            if name == "global_long_short_history"
        )
        self.assertEqual(funding_call[1], 60)
        self.assertEqual(crowding_call[2], 61)
        self.assertIsNone(funding_call[-2])
        self.assertIsNone(crowding_call[-2])
        self.assertEqual(context["market_breadth_assets"][0]["id"], "bitcoin")
        self.assertEqual(context["fear_greed_history"][0]["value"], "50")
        self.assertEqual(
            context["liquidation_context"]["market_price"],
            100.0,
        )

    def test_failed_source_is_blocking_input_instead_of_invented_value(self):
        client = FakeMarketDataClient()

        def fail(_symbol):
            raise RuntimeError("provider unavailable")

        client.get_funding_snapshot = fail
        context = collect_live_rule_context(
            symbol="BTCUSDT",
            horizon_seconds=3_600,
            interval_seconds=300,
            request_cutoff_at="2026-07-28T12:00:00Z",
            client=client,
            now_ms=lambda: 1_000,
        )

        self.assertEqual(context["funding_snapshot"], {})
        self.assertEqual(context["funding_info"]["fundingIntervalHours"], 8)


if __name__ == "__main__":
    unittest.main()
