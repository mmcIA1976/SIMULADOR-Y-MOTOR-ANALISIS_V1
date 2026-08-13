from __future__ import annotations

import math
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from analysis_engine import TradeProposal
from multiscale_feature_runtime import (
    FLAT_FEATURE_NAMES,
    STAGE_PROFILES,
    build_stage_context,
    required_candle_count,
)
from sequential_production_runtime import build_production_probability_run
from sequential_temporal_engine import ENGINE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def synthetic_candles(horizon: str) -> tuple[list[dict], datetime]:
    profile = STAGE_PROFILES[horizon]
    interval_ms = int(profile["interval_seconds"]) * 1000
    count = required_candle_count(horizon)
    base_ms = 1_700_000_000_000 - (1_700_000_000_000 % interval_ms)
    candles = []
    previous = 100.0
    for index in range(count):
        wave = 0.018 * math.sin(index / 6.0) + 0.011 * math.sin(index / 19.0)
        close = 100.0 * math.exp(0.000025 * index + wave)
        opened = previous
        high = max(opened, close) * (1.0015 + 0.0003 * (index % 3))
        low = min(opened, close) * (0.9985 - 0.0002 * (index % 2))
        quote = 1_000_000.0 * (1.0 + 0.2 * math.sin(index / 13.0))
        buy_fraction = 0.5 + 0.12 * math.sin(index / 9.0)
        open_ms = base_ms + index * interval_ms
        candles.append(
            {
                "open_time_ms": open_ms,
                "open": opened,
                "high": high,
                "low": low,
                "close": close,
                "volume": quote / close,
                "quote_volume": quote,
                "taker_buy_base_volume": quote * buy_fraction / close,
                "taker_buy_quote_volume": quote * buy_fraction,
                "close_time_ms": open_ms + interval_ms - 1,
            }
        )
        previous = close
    analysis_at = datetime.fromtimestamp(
        (base_ms + count * interval_ms) / 1000,
        tz=timezone.utc,
    )
    return candles, analysis_at


class SequentialProductionContractTests(unittest.TestCase):
    def test_each_stage_builds_its_own_complete_closed_data_context(self):
        for horizon, profile in STAGE_PROFILES.items():
            with self.subTest(horizon=horizon):
                candles, analysis_at = synthetic_candles(horizon)
                context = build_stage_context(
                    {
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "entry": 110.0,
                        "take_profit": 115.0,
                        "stop_loss": 105.0,
                        "time_horizon": horizon,
                        "horizon_seconds": profile["horizon_seconds"],
                        "analysis_at": analysis_at.isoformat(),
                    },
                    candles,
                )
                self.assertEqual(context["interval"], profile["interval"])
                self.assertEqual(
                    context["required_candle_count"], len(candles)
                )
                self.assertEqual(
                    set(context["feature_values"]), set(FLAT_FEATURE_NAMES)
                )
                self.assertTrue(
                    all(
                        math.isfinite(value)
                        for value in context["feature_values"].values()
                    )
                )

    @patch("sequential_production_runtime.build_stage_context")
    def test_medium_requests_only_short_and_medium_and_executes_one_engine(
        self, stage_builder
    ):
        stage_builder.side_effect = lambda plan, _candles: {
            "stage_id": STAGE_PROFILES[plan["time_horizon"]]["stage_id"],
            "context_sigma": 0.03,
            "feature_values": {name: 0.0 for name in FLAT_FEATURE_NAMES},
            "data_cutoff_at_ms": 1_699_999_999_999,
            "source_data_sha256": f"sha-{plan['time_horizon']}",
            "rule_traces": [],
        }
        requested_intervals = []

        def loader(_symbol, interval, _limit, **_kwargs):
            requested_intervals.append(interval)
            return []

        proposal = TradeProposal(
            "BTCUSDT", "long", "intraday_wide", 100.0, 200.0, 10.0,
            95.0, 108.0, "market"
        )
        snapshot = {
            "analysis_at": "2023-11-14T22:13:20+00:00",
            "evaluation_expires_at": "2023-11-15T22:13:20+00:00",
        }
        run = build_production_probability_run(
            proposal,
            snapshot,
            loader=loader,
            analysis_id="contract-test",
        )
        self.assertEqual(run["status"], "evaluated")
        self.assertEqual(requested_intervals, ["5m", "1h"])
        self.assertEqual(run["analysis_engine_execution_count"], 1)
        self.assertEqual(run["executed_analysis_engines"], [ENGINE_VERSION])
        self.assertEqual(
            run["probability_result"]["executed_stages"],
            ["intraday_short", "intraday_wide"],
        )

    def test_application_import_does_not_load_previous_probability_engines(self):
        command = (
            "import sys, app; "
            "print(','.join(sorted(name for name in sys.modules "
            "if name.startswith(('m6_', 'm7_', 'm8_')))))"
        )
        process = subprocess.run(
            [sys.executable, "-c", command],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
