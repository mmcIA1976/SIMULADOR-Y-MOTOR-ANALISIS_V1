from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backfill_operation_404_observation import (
    CHECKPOINTS,
    EXIT_REFERENCES,
    REPORTED_CHECKPOINTS,
    probability_values,
)
from operation_observation_learning import (
    OBSERVATION_ANALYSIS_TYPE,
    OBSERVATION_CONTRACT_VERSION,
    OBSERVATION_INTERVAL_CHOICES,
    _probability_triplet,
    canonical_json,
    checkpoint_code,
    observation_interval_minutes,
    observation_next_due_at,
    observation_session_is_due,
    payload_sha256,
)
from db import runtime_database_bootstrap_enabled
from app import compact_observation_analysis_payload


ROOT = Path(__file__).resolve().parents[1]


class OperationObservationLearningTests(unittest.TestCase):
    def test_checkpoint_identity_is_stable_and_unambiguous(self) -> None:
        self.assertEqual(checkpoint_code(404, 1), "404o1")
        self.assertEqual(checkpoint_code(450, 27), "450o27")
        with self.assertRaises(ValueError):
            checkpoint_code(404, 0)

    def test_json_hash_is_deterministic(self) -> None:
        left = {"operation": 404, "signals": {"ema": 1, "book": -1}}
        right = {"signals": {"book": -1, "ema": 1}, "operation": 404}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(payload_sha256(left), payload_sha256(right))

    def test_probability_contract_accepts_reconstructed_rounding(self) -> None:
        tp, sl, unresolved = probability_values(50.2, 49.7)
        normalized = _probability_triplet(tp, sl, unresolved)
        self.assertAlmostEqual(sum(normalized), 1.0)
        with self.assertRaises(ValueError):
            _probability_triplet(0.5, None, 0.5)

    def test_live_observation_interval_choices_are_exact(self) -> None:
        self.assertEqual(
            OBSERVATION_INTERVAL_CHOICES,
            (5, 10, 15, 20, 30, 40, 60),
        )
        for interval in OBSERVATION_INTERVAL_CHOICES:
            self.assertEqual(observation_interval_minutes(interval), interval)
        for invalid in (0, 6, 90, None):
            with self.assertRaises(ValueError):
                observation_interval_minutes(invalid)

    def test_first_control_is_immediate_then_respects_selected_interval(self) -> None:
        started_at = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
        new_session = {
            "status": "active",
            "operation_status": "OPEN",
            "planned_interval_minutes": 20,
            "stored_checkpoint_count": 0,
            "started_at": started_at.isoformat(),
        }
        self.assertEqual(observation_next_due_at(new_session), started_at)
        self.assertTrue(
            observation_session_is_due(new_session, now=started_at)
        )

        observed_session = {
            **new_session,
            "stored_checkpoint_count": 1,
            "last_checkpoint_at": started_at.isoformat(),
        }
        self.assertFalse(
            observation_session_is_due(
                observed_session,
                now=started_at + timedelta(minutes=19, seconds=59),
            )
        )
        self.assertTrue(
            observation_session_is_due(
                observed_session,
                now=started_at + timedelta(minutes=20),
            )
        )

    def test_observation_stops_as_soon_as_operation_is_closed(self) -> None:
        session = {
            "status": "active",
            "operation_status": "CLOSED",
            "planned_interval_minutes": 5,
            "stored_checkpoint_count": 0,
            "started_at": "2026-09-08T10:00:00+00:00",
        }
        self.assertFalse(
            observation_session_is_due(
                session,
                now="2026-09-08T12:00:00+00:00",
            )
        )

    def test_observation_storage_does_not_duplicate_full_snapshot(self) -> None:
        compact = compact_observation_analysis_payload(
            {
                "snapshot": {"large_rule_trace": "x" * 100_000},
                "tp_probability": 0.4,
                "sl_probability": 0.3,
                "range_probability": 0.3,
                "engine_version": "test-engine",
                "observation_context": {"source_operation_id": 404},
            }
        )
        self.assertNotIn("snapshot", compact)
        self.assertEqual(
            compact["snapshot_location"],
            "recommendations.snapshot_json",
        )
        self.assertLess(len(json.dumps(compact).encode("utf-8")), 4_096)

    def test_operation_404_reconstruction_never_claims_missing_evidence(self) -> None:
        self.assertEqual(REPORTED_CHECKPOINTS, 47)
        self.assertEqual(len(CHECKPOINTS), 32)
        self.assertEqual(CHECKPOINTS[0][0], 16)
        self.assertEqual(CHECKPOINTS[-1][0], 47)
        self.assertTrue(all(row[1] for row in CHECKPOINTS))
        self.assertEqual(
            [row[0] for row in CHECKPOINTS if row[-1]],
            [25, 32, 43],
        )
        self.assertEqual(sorted(EXIT_REFERENCES), [25, 32, 33, 35, 39, 43, 44, 45, 46])

    def test_schema_and_migration_preserve_exact_vs_reconstructed_contract(self) -> None:
        schema = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
        migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20260908_operation_observation_learning.sql"
        ).read_text(encoding="utf-8")
        for sql in (schema, migration):
            self.assertIn("operation_observation_sessions", sql)
            self.assertIn("operation_observation_checkpoints", sql)
            self.assertIn("operation_exit_counterfactuals", sql)
            self.assertIn("formal_learning_eligible", sql)
            self.assertIn("reconstructed_partial", sql)
            self.assertIn("operation_observation_fact_is_append_only", sql)
            self.assertIn("production_effect = 'none'", sql)

    def test_application_keeps_observations_out_of_trade_creation(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            'WHERE operation_id = ? AND analysis_type = \'pre_trade\'',
            source,
        )
        self.assertIn("AND analysis_type = 'pre_trade'", source)
        self.assertIn(
            "AND analysis_type <> 'operation_observation'",
            source,
        )
        self.assertIn(
            '@app.post("/api/operations/{operation_id}/observation-checkpoints")',
            source,
        )
        self.assertEqual(OBSERVATION_ANALYSIS_TYPE, "operation_observation")
        self.assertEqual(
            OBSERVATION_CONTRACT_VERSION,
            "operation-observation-contract-v0.2",
        )
        self.assertIn(
            'OBSERVATION_OPERATOR_USERNAME = "mauriciomc"',
            source,
        )
        self.assertGreaterEqual(
            source.count("require_observation_operator(user)"),
            4,
        )

    def test_database_bootstrap_releases_relation_locks_before_indexes(self) -> None:
        source = (ROOT / "db.py").read_text(encoding="utf-8")
        update = (
            "UPDATE recommendations SET time_horizon = 'intraday_short' "
            "WHERE time_horizon IS NULL OR time_horizon = ''"
        )
        update_position = source.index(update)
        commit_position = source.index("db.commit()", update_position)
        index_position = source.index("create_indexes(db)", update_position)
        self.assertLess(commit_position, index_position)

    def test_railway_runtime_verifies_schema_without_running_ddl(self) -> None:
        with patch.dict(
            os.environ,
            {"RAILWAY_ENVIRONMENT": "production"},
            clear=False,
        ):
            os.environ.pop("DB_BOOTSTRAP_ON_STARTUP", None)
            self.assertFalse(runtime_database_bootstrap_enabled())
        with patch.dict(
            os.environ,
            {
                "RAILWAY_ENVIRONMENT": "production",
                "DB_BOOTSTRAP_ON_STARTUP": "true",
            },
            clear=False,
        ):
            self.assertTrue(runtime_database_bootstrap_enabled())

    def test_frontend_exposes_automatic_observation_schedule(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        worker = (ROOT / "operation_worker.py").read_text(encoding="utf-8")
        self.assertIn('id="startObservationButton"', html)
        self.assertIn('id="observationInterval"', html)
        self.assertNotIn('id="recordObservationButton"', html)
        for interval in OBSERVATION_INTERVAL_CHOICES:
            self.assertIn(f'<option value="{interval}"', html)
        self.assertIn("changeObservationInterval", javascript)
        self.assertNotIn("recordObservationCheckpoint", javascript)
        self.assertIn("run_observation_scheduler_loop", worker)
        self.assertIn("record_operation_observation_checkpoint", worker)
        self.assertIn(
            'const OBSERVATION_OPERATOR_USERNAME = "mauriciomc";',
            javascript,
        )
        self.assertIn("canManageOperationObservations()", javascript)


if __name__ == "__main__":
    unittest.main()
