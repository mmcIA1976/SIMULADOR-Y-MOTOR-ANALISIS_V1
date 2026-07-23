import unittest

from learning_evidence import (
    apply_evidence_to_structured,
    build_historical_evidence,
)


MINUTE = 60_000


def kline(minute: int, open_price: float, high: float, low: float, close: float) -> list:
    open_time = minute * MINUTE
    return [
        open_time,
        str(open_price),
        str(high),
        str(low),
        str(close),
        "100",
        open_time + MINUTE - 1,
        "0",
        "0",
        "0",
        "0",
        "0",
    ]


def operation(side: str = "long", **overrides) -> dict:
    payload = {
        "id": 1,
        "symbol": "BTCUSDT",
        "side": side,
        "entry": 100,
        "margin": 100,
        "leverage": 2,
        "stop_loss": 95 if side == "long" else 105,
        "take_profit": 110 if side == "long" else 90,
        "started_at": "1970-01-01T00:00:00+00:00",
        "closed_at": "1970-01-01T00:02:59.999000+00:00",
        "close_reason": "take_profit",
        "observation_status": "PLAN_EXECUTED",
        "observation_until": None,
        "observation_result": None,
    }
    payload.update(overrides)
    return payload


class LearningEvidenceTests(unittest.TestCase):
    def test_long_excursion_uses_highs_and_lows_during_trade(self):
        evidence = build_historical_evidence(
            operation(),
            [
                kline(0, 100, 105, 98, 104),
                kline(1, 104, 111, 97, 109),
                kline(2, 109, 112, 99, 110),
            ],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(evidence["quality"], "complete_1m")
        self.assertEqual(evidence["trade_excursion"]["max_favorable_pct"], 12.0)
        self.assertEqual(evidence["trade_excursion"]["max_adverse_pct"], -3.0)
        self.assertEqual(evidence["first_plan_touch"]["reason"], "take_profit")
        self.assertEqual(evidence["reconstructed_plan_result"], "plan_success")

    def test_short_excursion_reverses_favorable_and_adverse_directions(self):
        evidence = build_historical_evidence(
            operation(side="short", close_reason="stop_loss"),
            [
                kline(0, 100, 103, 96, 99),
                kline(1, 99, 106, 89, 104),
                kline(2, 104, 105, 97, 100),
            ],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(evidence["trade_excursion"]["max_favorable_pct"], 11.0)
        self.assertEqual(evidence["trade_excursion"]["max_adverse_pct"], -6.0)
        self.assertEqual(evidence["first_plan_touch"]["status"], "ambiguous_same_candle")

    def test_same_candle_is_ambiguous_when_historical_trades_are_unavailable(self):
        evidence = build_historical_evidence(
            operation(closed_at="1970-01-01T00:00:59.999000+00:00"),
            [kline(0, 100, 111, 94, 100)],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(evidence["path_resolution"], "ambiguous_same_candle")
        self.assertIsNone(evidence["first_plan_touch"]["reason"])
        self.assertFalse(evidence["first_plan_touch"]["aggregate_trades_available"])

    def test_recent_aggregate_trades_resolve_same_candle_order(self):
        def trades(start_ms, end_ms):
            return [
                {"T": start_ms + 10_000, "p": "94", "q": "1"},
                {"T": start_ms + 20_000, "p": "111", "q": "1"},
            ]

        evidence = build_historical_evidence(
            operation(closed_at="1970-01-01T00:00:59.999000+00:00"),
            [kline(0, 100, 111, 94, 100)],
            trade_loader=trades,
            now_ms=MINUTE,
        )

        self.assertEqual(evidence["path_resolution"], "resolved")
        self.assertEqual(evidence["first_plan_touch"]["reason"], "stop_loss")
        self.assertEqual(evidence["first_plan_touch"]["time_precision"], "aggregate_trade")

    def test_partial_boundary_candle_is_not_presented_as_certain_touch(self):
        evidence = build_historical_evidence(
            operation(
                started_at="1970-01-01T00:00:30+00:00",
                closed_at="1970-01-01T00:00:59.999000+00:00",
            ),
            [kline(0, 100, 104, 94, 100)],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(evidence["quality"], "complete_1m_with_boundary_approximation")
        self.assertEqual(evidence["path_resolution"], "ambiguous_boundary_candle")

    def test_manual_observation_has_separate_post_close_path(self):
        evidence = build_historical_evidence(
            operation(
                closed_at="1970-01-01T00:01:00+00:00",
                close_reason="manual",
                observation_status="OBSERVATION_CLOSED",
                observation_until="1970-01-01T00:03:59.999000+00:00",
                observation_result="manual_left_profit",
            ),
            [
                kline(0, 100, 104, 98, 102),
                kline(1, 102, 106, 99, 104),
                kline(2, 104, 111, 103, 110),
                kline(3, 110, 112, 108, 111),
            ],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(evidence["candle_count"], 4)
        self.assertEqual(evidence["first_post_close_plan_touch"]["reason"], "take_profit")
        self.assertEqual(evidence["recorded_result_consistency"], "consistent")
        self.assertEqual(evidence["reconstructed_plan_result"], "plan_would_succeed")
        self.assertEqual(evidence["post_close_excursion"]["max_favorable_pct"], 12.0)

    def test_kline_exit_evidence_uses_candle_close_as_effective_boundary(self):
        evidence = build_historical_evidence(
            operation(
                closed_at="1970-01-01T00:01:00+00:00",
                exit_evidence_json=(
                    '{"source":"binance_usdm_futures_1m_kline",'
                    '"market_data":{"close_time":"1970-01-01T00:01:59.999000+00:00"}}'
                ),
            ),
            [
                kline(0, 100, 104, 98, 102),
                kline(1, 102, 111, 99, 110),
            ],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(
            evidence["requested_window"]["closed_at"],
            "1970-01-01T00:01:59.999000+00:00",
        )
        self.assertEqual(evidence["first_plan_touch"]["reason"], "take_profit")

    def test_incomplete_candle_coverage_is_marked_partial(self):
        evidence = build_historical_evidence(
            operation(closed_at="1970-01-01T00:04:59.999000+00:00"),
            [kline(0, 100, 101, 99, 100), kline(4, 100, 102, 98, 101)],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        self.assertEqual(evidence["expected_candle_count"], 5)
        self.assertEqual(evidence["coverage_ratio"], 0.4)
        self.assertEqual(evidence["quality"], "partial_1m")

    def test_structured_update_preserves_legacy_excursion_and_is_repeatable(self):
        structured = {
            "analysis_verdict": "analysis_supported",
            "excursion": {"max_favorable_pct": 1},
        }
        evidence = build_historical_evidence(
            operation(),
            [
                kline(0, 100, 105, 98, 104),
                kline(1, 104, 109, 97, 108),
                kline(2, 108, 110, 99, 109),
            ],
            now_ms=10 * 24 * 60 * MINUTE,
        )

        first = apply_evidence_to_structured(structured, evidence)
        second = apply_evidence_to_structured(first, evidence)

        self.assertEqual(first["legacy_tick_excursion"], {"max_favorable_pct": 1})
        self.assertEqual(second["legacy_tick_excursion"], {"max_favorable_pct": 1})
        self.assertEqual(first["analysis_verdict"], "analysis_supported")
        self.assertEqual(first["excursion"], second["excursion"])


if __name__ == "__main__":
    unittest.main()
