import unittest

from analysis_engine import (
    TradeProposal,
    build_liquidation_metric,
    build_liquidation_observation,
)
from liquidation_data import normalize_heatmap


def heatmap_payload(updated_at: int = 1_000_000) -> dict:
    return {
        "_meta": {
            "schema": "hyperperps.whale-heatmap.v4",
            "as_of": "1970-01-01T00:16:40Z",
            "age_seconds": 0,
            "stale": False,
        },
        "updated_at": updated_at,
        "spot_at_compute": 100,
        "sample_size": 2500,
        "longs": [
            {"price": 98, "notional_usd": 3_000_000, "wallet_count": 12, "distance_pct": -2},
            {"price": 99, "notional_usd": 2_000_000, "wallet_count": 8, "distance_pct": -1},
        ],
        "shorts": [
            {"price": 102, "notional_usd": 4_000_000, "wallet_count": 15, "distance_pct": 2},
        ],
        "cascade_mass": {
            "long": {"within_1pct": 2_000_000, "within_2pct": 5_000_000, "within_5pct": 8_000_000},
            "short": {"within_1pct": 1_000_000, "within_2pct": 10_000_000, "within_5pct": 14_000_000},
        },
        "net_oi_skew": 0.08,
        "crowd_leverage": {"long_avg": 18.2, "short_avg": 21.4},
    }


class LiquidationContextTests(unittest.TestCase):
    def test_normalizes_fresh_clusters_and_cascade_mass(self):
        context = normalize_heatmap(
            heatmap_payload(),
            "BTCUSDT",
            100.2,
            now_ms=1_120_000,
            max_age_seconds=600,
        )

        self.assertTrue(context["available"])
        self.assertEqual(context["status"], "available")
        self.assertEqual(context["scope"], "hyperliquid")
        self.assertEqual(context["sample_size"], 2500)
        self.assertEqual(context["clusters_below"][0]["position_side"], "long")
        self.assertEqual(context["clusters_above"][0]["position_side"], "short")
        self.assertEqual(context["short_to_long_mass_ratio_2pct"], 2.0)
        self.assertEqual(context["dominant_liquidation_side_2pct"], "shorts_above")

    def test_rejects_stale_provider_data_but_keeps_it_auditable(self):
        context = normalize_heatmap(
            heatmap_payload(),
            "BTCUSDT",
            100,
            now_ms=1_700_001,
            max_age_seconds=600,
        )

        self.assertFalse(context["available"])
        self.assertTrue(context["stale"])
        self.assertEqual(context["status"], "stale")
        self.assertTrue(context["clusters_above"])
        self.assertTrue(context["clusters_below"])

    def test_rejects_reference_price_far_from_binance_market(self):
        context = normalize_heatmap(
            heatmap_payload(),
            "BTCUSDT",
            90,
            now_ms=1_100_000,
            max_age_seconds=600,
        )

        self.assertFalse(context["available"])
        self.assertEqual(context["status"], "price_mismatch")

    def test_unsupported_symbol_returns_structured_context(self):
        context = normalize_heatmap({}, "XRPUSDT", 1, now_ms=1_000_000)

        self.assertFalse(context["available"])
        self.assertEqual(context["status"], "unsupported")
        self.assertEqual(context["reason"], "symbol_not_supported_by_provider")

    def test_short_observation_compares_tp_and_sl_without_scoring(self):
        context = normalize_heatmap(
            heatmap_payload(),
            "BTCUSDT",
            100,
            now_ms=1_100_000,
            max_age_seconds=600,
        )
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_short",
            entry=100,
            margin=100,
            leverage=2,
            stop_loss=102,
            take_profit=98,
        )

        observation = build_liquidation_observation(proposal, context, atr_pct=0.5)
        metric = build_liquidation_metric(observation, context)

        self.assertTrue(observation["available"])
        self.assertFalse(observation["affects_scoring"])
        self.assertEqual(observation["target_liquidation_side"], "longs_below")
        self.assertEqual(observation["adverse_liquidation_side"], "shorts_above")
        self.assertEqual(observation["tp_alignment"], "coincide")
        self.assertEqual(observation["sl_cluster_proximity"], "coincide")
        self.assertEqual(observation["target_cascade_mass_2pct"], 5_000_000)
        self.assertEqual(observation["adverse_cascade_mass_2pct"], 10_000_000)
        self.assertEqual(observation["adverse_to_target_mass_ratio_2pct"], 2.0)
        self.assertEqual(observation["map_read"], "desfavorable")
        self.assertEqual(observation["adverse_squeeze_risk"], "medio")
        self.assertEqual(observation["target_read"], "favorable")
        self.assertEqual(observation["sl_read"], "peligroso")
        self.assertEqual(observation["dominant_adverse_cluster_before_sl"]["price"], 102)
        self.assertEqual(metric["score"], 25)
        self.assertEqual(metric["bias"], "desfavorable")

    def test_high_adverse_ratio_is_reported_as_high_squeeze_risk(self):
        payload = heatmap_payload()
        payload["cascade_mass"]["short"]["within_2pct"] = 30_000_000
        context = normalize_heatmap(
            payload,
            "BTCUSDT",
            100,
            now_ms=1_100_000,
            max_age_seconds=600,
        )
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_short",
            entry=100,
            margin=100,
            leverage=2,
            stop_loss=103,
            take_profit=98,
        )

        observation = build_liquidation_observation(proposal, context, atr_pct=0.5)

        self.assertEqual(observation["adverse_to_target_mass_ratio_2pct"], 6.0)
        self.assertEqual(observation["map_read"], "desfavorable")
        self.assertEqual(observation["adverse_squeeze_risk"], "alto")
        self.assertIn("masa adversa 6.0x", observation["summary"])


if __name__ == "__main__":
    unittest.main()
