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
    OBSERVATION_STORAGE_PROFILE,
    _probability_triplet,
    build_observation_terminal_counterfactual_payload,
    compact_observation_snapshot,
    canonical_json,
    checkpoint_code,
    observation_interval_minutes,
    observation_closure_advisory,
    observation_next_due_at,
    observation_rule_signals,
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

    def test_paused_observation_never_becomes_due(self) -> None:
        self.assertFalse(
            observation_session_is_due(
                {
                    "status": "paused",
                    "operation_status": "OPEN",
                    "planned_interval_minutes": 5,
                    "stored_checkpoint_count": 4,
                    "last_checkpoint_at": "2026-09-08T10:00:00+00:00",
                },
                now="2026-09-08T12:00:00+00:00",
            )
        )

    def test_monitor_exposes_quantitative_observational_rule_without_weight(self) -> None:
        signals = observation_rule_signals(
            {
                "side": "long",
                "stage_rule_traces": {
                    "intraday_short": [
                        {
                            "rule_id": "LIB-CAND-EMA-TREND-001",
                            "status": "evaluated_shadow",
                            "probability_effect": "none_observation_only",
                            "outputs": {
                                "side_adjusted_slope_atr": -0.35,
                                "side_adjusted_close_vs_ema50_log": -0.01,
                                "side_adjusted_ema50_vs_ema200_log": -0.006,
                            },
                        }
                    ]
                },
            }
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["category"], "observational")
        self.assertEqual(signals[0]["tone"], "adverse")
        self.assertEqual(len(signals[0]["metrics"]), 3)

    def test_side_adjusted_primary_path_is_not_inverted_twice_for_short(self) -> None:
        signals = observation_rule_signals(
            {
                "side": "short",
                "stage_rule_traces": {
                    "intraday_short": [
                        {
                            "rule_id": "M4-RULE-PATH-STRUCTURE-001",
                            "status": "evaluated",
                            "probability_effect": "analog_distance_input",
                            "outputs": {"directional_path_efficiency_h": 0.25},
                        }
                    ]
                },
            }
        )
        self.assertEqual(signals[0]["category"], "principal")
        self.assertEqual(signals[0]["tone"], "favorable")
        self.assertEqual(signals[0]["score"], 0.25)

    def test_absorption_displacement_alone_is_context_not_fake_absorption(self) -> None:
        signals = observation_rule_signals(
            {
                "side": "long",
                "stage_rule_traces": {
                    "intraday_short": [
                        {
                            "rule_id": "LIB-CAND-ABSORPTION-001",
                            "status": "evaluated_shadow",
                            "probability_effect": "none_observation_only",
                            "outputs": {
                                "side_adjusted_horizon_displacement_atr": 1.8,
                            },
                        }
                    ]
                },
            }
        )
        self.assertEqual(signals[0]["tone"], "context")
        self.assertIsNone(signals[0]["score"])

    def test_compact_snapshot_keeps_evaluable_outputs_and_drops_raw_arrays(self) -> None:
        snapshot = {
            "analysis_at": "2026-09-08T10:00:00+00:00",
            "data_cutoff_at": "2026-09-08T09:59:59+00:00",
            "evaluation_horizon_seconds": 14400,
            "symbol": "BTCUSDT",
            "side": "long",
            "time_horizon": "intraday_short",
            "entry": 100.0,
            "take_profit": 102.0,
            "stop_loss": 99.0,
            "probability_trace": {
                "stage_traces": [
                    {
                        "stage_id": "stage_0_4h",
                        "time_horizon": "intraday_short",
                        "interval": "5m",
                        "current_feature_values": {"path": 0.4},
                        "ranked_candidates": [{"x": index} for index in range(500)],
                    }
                ]
            },
            "stage_rule_traces": {
                "intraday_short": [
                    {
                        "rule_id": "LIB-CAND-EMA-TREND-001",
                        "status": "evaluated_shadow",
                        "probability_effect": "none_observation_only",
                        "inputs": {"candles": list(range(1000))},
                        "outputs": {
                            "side_adjusted_slope_atr": 0.4,
                            "walls": [{"price": index} for index in range(1000)],
                        },
                    }
                ]
            },
        }
        compact = compact_observation_snapshot(snapshot)
        encoded = json.dumps(compact)
        self.assertEqual(compact["storage_profile"], OBSERVATION_STORAGE_PROFILE)
        self.assertNotIn("ranked_candidates", encoded)
        self.assertNotIn("walls", encoded)
        self.assertNotIn("inputs", encoded)
        self.assertEqual(
            compact["stage_rule_traces"]["intraday_short"][0]["outputs"]
            ["side_adjusted_slope_atr"],
            0.4,
        )
        self.assertLess(len(encoded.encode("utf-8")), 10_000)

    def test_terminal_event_resolves_observation_before_full_horizon_matures(self) -> None:
        snapshot = compact_observation_snapshot(
            {
                "analysis_at": "2026-09-08T10:00:00+00:00",
                "data_cutoff_at": "2026-09-08T09:59:59+00:00",
                "evaluation_horizon_seconds": 86400,
                "symbol": "BTCUSDT",
                "side": "short",
                "time_horizon": "intraday_wide",
                "entry": 100.0,
                "take_profit": 95.0,
                "stop_loss": 103.0,
                "probability_trace": {
                    "stage_traces": [
                        {
                            "time_horizon": "intraday_wide",
                            "interval": "1h",
                            "current_feature_values": {"path": 0.2},
                        }
                    ]
                },
                "stage_rule_traces": {},
            }
        )
        payload = build_observation_terminal_counterfactual_payload(
            operation={
                "id": 429,
                "user_id": 2,
                "symbol": "BTCUSDT",
                "side": "short",
                "time_horizon": "intraday_wide",
                "take_profit": 95.0,
                "stop_loss": 103.0,
                "close_reason": "stop_loss",
                "close_price": 103.0,
                "closed_at": "2026-09-08T11:00:00+00:00",
            },
            checkpoint={
                "recommendation_id": 1400,
                "observed_at": "2026-09-08T10:00:00+00:00",
                "market_price": 100.0,
                "tp_probability": 0.70,
                "sl_probability": 0.25,
                "range_probability": 0.05,
                "engine_version": "test",
            },
            snapshot=snapshot,
        )
        self.assertEqual(payload["evaluation_status"], "evaluated")
        self.assertEqual(payload["outcome_label"], "sl_first_within_horizon")
        self.assertEqual(
            payload["evaluation_expires_at"],
            "2026-09-09T10:00:00+00:00",
        )
        self.assertEqual(payload["evidence_source"], "operation_terminal_event")

    def test_close_candidate_requires_persistent_primary_risk_and_confirmation(self) -> None:
        checkpoints = []
        for number, tp, sl in (
            (1, 0.42, 0.38),
            (2, 0.32, 0.48),
            (3, 0.25, 0.57),
            (4, 0.20, 0.64),
        ):
            checkpoints.append(
                {
                    "checkpoint_code": f"500o{number}",
                    "tp_probability": tp,
                    "sl_probability": sl,
                    "range_probability": 1 - tp - sl,
                    "unrealized_pnl": -12.0,
                    "remaining_seconds": 3600,
                    "analysis_horizon_seconds": 14400,
                    "rule_signals": [
                        {
                            "category": "observational",
                            "tone": "adverse",
                            "label": "Alineación con EMA",
                        },
                        {
                            "category": "observational",
                            "tone": "adverse",
                            "label": "Persistencia del flujo ejecutado",
                        },
                    ],
                }
            )
        advisory = observation_closure_advisory(checkpoints)
        self.assertEqual(advisory["level"], "close_candidate")
        self.assertEqual(advisory["production_effect"], "none")
        self.assertGreaterEqual(len(advisory["reasons"]), 3)

    def test_profit_protection_requires_three_positive_economic_confirmations(self) -> None:
        checkpoints = [
            {
                "checkpoint_code": f"600o{number}",
                "tp_probability": 0.35,
                "sl_probability": 0.60,
                "range_probability": 0.05,
                "unrealized_pnl": pnl,
                "rule_signals": [],
            }
            for number, pnl in ((1, 4.0), (2, 5.0), (3, 6.0))
        ]
        advisory = observation_closure_advisory(
            checkpoints,
            terminal_pnl={"tp": 12.0, "sl": -10.0},
        )
        self.assertEqual(advisory["level"], "protect_candidate")
        self.assertEqual(advisory["economic_confirmation_count"], 3)
        self.assertGreater(advisory["model_expected_close_advantage"], 0.0)

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
        monitor_migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20260908_operation_observation_monitor.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("operation_observation_session_events", monitor_migration)
        self.assertIn("status IN ('active', 'paused'", monitor_migration)
        self.assertIn("ENABLE ROW LEVEL SECURITY", monitor_migration)

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
            "operation-observation-contract-v0.4",
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
        self.assertIn('id="observationMonitor"', html)
        self.assertIn('id="pauseObservationButton"', html)
        self.assertIn('id="resumeObservationButton"', html)
        self.assertIn('id="stopObservationButton"', html)
        self.assertGreater(html.index('id="observationMonitor"'), html.index('id="tradeChart"'))
        self.assertNotIn('id="recordObservationButton"', html)
        for interval in OBSERVATION_INTERVAL_CHOICES:
            self.assertIn(f'<option value="{interval}"', html)
        self.assertIn("changeObservationInterval", javascript)
        self.assertIn("renderObservationMonitor", javascript)
        self.assertIn("changeObservationState", javascript)
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
