from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prospective_validation import (
    ENABLED_ENV,
    build_prospective_probability_run,
    load_frozen_candidate,
    prospective_validation_enabled,
)


ANALYSIS_AT = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
HOUR_MS = 3_600_000


def proposal(entry_type: str = "market"):
    return SimpleNamespace(
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        take_profit=103.0,
        stop_loss=98.0,
        entry_type=entry_type,
        time_horizon="intraday_wide",
    )


def snapshot() -> dict:
    return {
        "analysis_at": ANALYSIS_AT.isoformat(),
        "evaluation_horizon_seconds": 24 * 60 * 60,
        "evaluation_expires_at": (
            ANALYSIS_AT + timedelta(days=1)
        ).isoformat(),
    }


def raw_candles() -> list[list]:
    count = 61 * 24 + 1
    final_close_ms = int(ANALYSIS_AT.timestamp() * 1000)
    first_close_ms = final_close_ms - (count - 1) * HOUR_MS
    rows = []
    for index in range(count):
        close_time = first_close_ms + index * HOUR_MS
        close = 100.0 + 0.01 * ((index % 17) - 8) + index * 0.0005
        rows.append(
            [
                close_time - HOUR_MS + 1,
                str(close - 0.02),
                str(close + 0.08),
                str(close - 0.08),
                str(close),
                "10",
                close_time,
            ]
        )
    return rows


def paged_loader(rows: list[list]):
    def loader(
        symbol,
        interval,
        limit,
        start_time_ms=None,
        end_time_ms=None,
    ):
        selected = [
            row
            for row in rows
            if (start_time_ms is None or row[0] >= start_time_ms)
            and (end_time_ms is None or row[0] <= end_time_ms)
        ]
        return selected[:limit]

    return loader


class ProspectiveValidationTests(unittest.TestCase):
    def test_complete_closed_history_runs_m5_and_remediated_m6(self):
        result = build_prospective_probability_run(
            proposal(),
            snapshot(),
            loader=paged_loader(raw_candles()),
            analysis_id="prospective-test",
        )

        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["production_effect"], "none")
        self.assertEqual(
            result["m6_result"]["engine_version"],
            "M6-R1-internal-probability-engine-v0.1",
        )
        self.assertEqual(
            result["m6_result"]["coefficient_artifact_id"],
            "M6-CANDIDATE-NO-H-RIDGE-10-v0.2",
        )
        self.assertAlmostEqual(
            sum(result["m6_result"]["probabilities"].values()),
            1.0,
            places=12,
        )
        self.assertLessEqual(
            datetime.fromisoformat(result["data_cutoff_at"]),
            ANALYSIS_AT,
        )
        self.assertEqual(
            result["feature_snapshot"]["return_count_per_horizon"],
            24,
        )
        artifact = load_frozen_candidate()["coefficient_artifact"]
        self.assertEqual(
            artifact["coefficients"]["tp"][
                "directional_path_efficiency_h"
            ],
            0.0,
        )
        self.assertEqual(
            artifact["coefficients"]["sl"][
                "directional_path_efficiency_h"
            ],
            0.0,
        )
        required = {
            "M4-RULE-HORIZON-SAMPLING-001",
            "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
        }
        statuses = {
            trace["rule_id"]: trace["status"]
            for trace in result["m5_analysis"]["traces"]
        }
        self.assertTrue(all(statuses[rule_id] == "evaluated" for rule_id in required))

    def test_pending_entry_is_recorded_as_blocked(self):
        result = build_prospective_probability_run(
            proposal("pending"),
            snapshot(),
            loader=lambda *args, **kwargs: self.fail("loader must not run"),
            analysis_id="pending-test",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["block_code"], "m5_market_entry_required")
        self.assertIsNone(result["m6_result"])

    def test_environment_kill_switch_is_explicit(self):
        with patch.dict(os.environ, {ENABLED_ENV: "false"}):
            self.assertFalse(prospective_validation_enabled())
        with patch.dict(os.environ, {ENABLED_ENV: "true"}):
            self.assertTrue(prospective_validation_enabled())

    def test_schema_is_private_and_append_only(self):
        schema = Path("supabase/schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS m6_prospective_runs", schema)
        self.assertIn("m6_prospective_runs_no_update", schema)
        self.assertIn("m6_prospective_runs_no_delete", schema)
        self.assertIn(
            "REVOKE ALL PRIVILEGES ON TABLE public.m6_prospective_runs "
            "FROM anon, authenticated",
            schema,
        )


if __name__ == "__main__":
    unittest.main()
