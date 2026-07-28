from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import audit_m8_inventory as m8  # noqa: E402


def synthetic_row(index: int) -> dict:
    analysis_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=index
    )
    return {
        "analysis_at": analysis_at,
        "symbol": "BTCUSDT",
        "side": "long",
        "time_horizon": "intraday_short",
        "operation_time_horizon": "intraday_short",
        "engine_version": "legacy",
        "snapshot_json": '{"snapshot": true}',
        "analysis_json": '{"analysis": true}',
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "entry_type": "market",
        "started_at": analysis_at.isoformat(),
        "operation_created_at": analysis_at,
    }


class M82InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = json.loads(
            m8.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )

    def test_sql_never_selects_outcomes_pnl_or_legacy_probabilities(self) -> None:
        m8.assert_queries_are_outcome_blind()
        sql = f"{m8.SQL_TOTALS}\n{m8.SQL_METADATA_ROWS}".lower()
        for token in m8.FORBIDDEN_OUTCOME_TOKENS:
            self.assertNotIn(token, sql)

    def test_synthetic_inventory_freezes_cuts_from_dates_only(self) -> None:
        rows = [synthetic_row(index) for index in range(10)]
        inventory = m8.build_inventory(
            totals={
                "operations_total": 10,
                "recommendations_total": 10,
                "linked_recommendations_total": 10,
            },
            rows=rows,
            captured_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
        )
        cuts = inventory["chronological_cuts"]
        self.assertEqual(cuts["status"], "frozen_from_analysis_dates_only")
        self.assertFalse(cuts["selection_uses_outcomes"])
        self.assertFalse(cuts["selection_uses_pnl"])
        self.assertFalse(cuts["selection_uses_probabilities"])
        self.assertEqual(
            sum(inventory["partition_counts_before_outcomes"].values()),
            10,
        )

    def test_invalid_geometry_is_structurally_excluded(self) -> None:
        row = synthetic_row(0)
        row["take_profit"] = 90
        reasons = m8.structural_reasons(row)
        self.assertIn("invalid_or_missing_plan_geometry", reasons)

    def test_non_market_entry_is_excluded(self) -> None:
        row = synthetic_row(0)
        row["entry_type"] = "pending"
        self.assertIn("non_market_entry", m8.structural_reasons(row))

    def test_live_snapshot_preserves_outcome_embargo(self) -> None:
        embargo = self.snapshot["outcome_embargo"]
        self.assertEqual(embargo["outcome_columns_selected"], [])
        self.assertEqual(
            embargo["legacy_probability_columns_selected"],
            [],
        )
        self.assertFalse(embargo["performance_evaluated"])
        self.assertFalse(embargo["pnl_read"])

    def test_live_snapshot_has_all_36_coverage_cells(self) -> None:
        coverage = self.snapshot["coverage"]
        self.assertEqual(len(coverage), 36)
        self.assertEqual(
            len(
                {
                    (
                        item["symbol"],
                        item["side"],
                        item["time_horizon"],
                    )
                    for item in coverage
                }
            ),
            36,
        )

    def test_canonical_snapshot_hash_is_valid(self) -> None:
        payload = dict(self.snapshot)
        stored = payload.pop("canonical_payload_sha256")
        self.assertEqual(stored, m8.sha256_text(m8.canonical_json(payload)))

    def test_production_and_m9_remain_closed(self) -> None:
        boundaries = self.snapshot["boundaries"]
        self.assertEqual(boundaries["production_effect"], "none")
        self.assertFalse(boundaries["m8_closed"])
        self.assertFalse(boundaries["m9_started"])

    def test_stored_snapshot_and_report_are_internally_reproducible(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "audit_m8_inventory.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
