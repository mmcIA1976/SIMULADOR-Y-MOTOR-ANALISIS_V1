import json
import unittest

from analysis_engine import TradeProposal
from app import (
    compact_expired_unselected_analyses,
    insert_analysis_attempt,
)
from versioning import APP_VERSION


class Cursor:
    rowcount = 3


class CaptureDb:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()), tuple(params)))
        return Cursor()


def proposal() -> TradeProposal:
    return TradeProposal(
        symbol="ETHUSDT",
        side="long",
        time_horizon="intraday_wide",
        entry=2000,
        margin=100,
        leverage=2,
        stop_loss=1950,
        take_profit=2100,
        entry_type="market",
    )


class AnalysisAttemptPersistenceTests(unittest.TestCase):
    def test_attempt_row_is_minimal_and_contains_no_market_payload(self):
        db = CaptureDb()

        insert_analysis_attempt(
            db,
            user_id=7,
            proposal=proposal(),
            entry_type="market",
            outcome="blocked",
            duration_ms=812,
            engine_version="TP-SL-EMPIRICAL-ANALOG-v0.9",
            error_code="sequential_data_or_calculation_error",
        )

        query, params = db.queries[0]
        self.assertIn("INSERT INTO analysis_attempts", query)
        self.assertEqual(query.count("?"), len(params))
        self.assertEqual(len(params), 10)
        self.assertNotIn("snapshot", query)
        self.assertNotIn("analysis_json", query)

    def test_only_current_version_expired_unselected_payloads_are_compacted(self):
        db = CaptureDb()

        compacted = compact_expired_unselected_analyses(db)

        query, params = db.queries[0]
        marker = json.loads(params[0])
        self.assertEqual(compacted, 3)
        self.assertIn("operation_id IS NULL", query)
        self.assertIn("INTERVAL '24 hours'", query)
        self.assertEqual(params[1], APP_VERSION)
        self.assertEqual(marker["retention_status"], "expired_unselected_analysis")
        self.assertFalse(marker["learning_eligible"])


if __name__ == "__main__":
    unittest.main()
