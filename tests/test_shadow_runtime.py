from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import persist_live_shadow_safely
from challenger_engine import MODEL_SCHEMA_VERSION
from shadow_runtime import (
    build_user_shadow_audit,
    canonical_json,
    disable_shadow,
    execute_live_shadow_run,
    fixed_horizon_seconds,
    rollback_shadow,
    select_shadow_model,
    sha256_json,
)


ANALYSIS_AT = "2026-07-26T12:00:00+00:00"


class Cursor:
    def __init__(self, row=None, rows=None, lastrowid=None):
        self.row = row
        self.rows = rows or []
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class RuntimeDb:
    def __init__(self, config, artifact=None, existing_run=None):
        self.config = config
        self.artifact = artifact
        self.existing_run = existing_run
        self.shadow_insert_params = None

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        if (
            "FROM challenger_shadow_config_events" in normalized
            and "ORDER BY id DESC" in normalized
        ):
            return Cursor(row=self.config)
        if (
            "FROM challenger_model_artifacts" in normalized
            and "artifact_sha256" in normalized
        ):
            if self.artifact is None:
                return Cursor(row=None)
            return Cursor(
                row={
                    "model_version": self.artifact["model_version"],
                    "artifact_sha256": sha256_json(self.artifact),
                    "artifact_json": canonical_json(self.artifact),
                }
            )
        if "SELECT id FROM challenger_shadow_runs" in normalized:
            return Cursor(row=self.existing_run)
        if "INSERT INTO challenger_shadow_runs" in normalized:
            self.shadow_insert_params = params
            return Cursor(lastrowid=91)
        raise AssertionError(f"Unexpected query: {normalized}")


class QueueDb:
    def __init__(self, rows):
        self.rows = list(rows)
        self.inserts = []

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT"):
            if not self.rows:
                raise AssertionError(f"No queued row for: {normalized}")
            return Cursor(row=self.rows.pop(0))
        if normalized.startswith("INSERT INTO challenger_shadow_config_events"):
            self.inserts.append(params)
            return Cursor(lastrowid=77)
        raise AssertionError(f"Unexpected query: {normalized}")


class AuditDb:
    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        if (
            "FROM challenger_shadow_config_events" in normalized
            and "ORDER BY id DESC" in normalized
        ):
            return Cursor(
                row={
                    "id": 3,
                    "action": "rollback",
                    "enabled": False,
                    "selected_model_version": None,
                    "rollback_target_event_id": 1,
                    "reason": "rollback test",
                }
            )
        if "COUNT(*) AS total_runs" in normalized:
            return Cursor(
                row={
                    "total_runs": 1,
                    "shadow_predictions": 0,
                    "blocked_runs": 1,
                    "production_effect_violations": 0,
                }
            )
        if "GROUP BY csr.block_code" in normalized:
            return Cursor(rows=[{"block_code": "shadow_disabled", "cases": 1}])
        if "ORDER BY csr.id DESC" in normalized:
            return Cursor(
                rows=[
                    {
                        "id": 8,
                        "recommendation_id": 700,
                        "config_event_id": 3,
                        "run_origin": "live_analysis",
                        "challenger_status": "blocked",
                        "block_code": "shadow_disabled",
                        "model_version": None,
                        "champion_result_json": '{"tp_probability":0.6}',
                        "challenger_result_json": (
                            '{"status":"blocked","probabilities":null}'
                        ),
                        "comparison_json": (
                            '{"served_output":"champion",'
                            '"production_effect":"none"}'
                        ),
                        "plan_contract_json": (
                            '{"time_horizon":"intraday_short"}'
                        ),
                        "production_effect": "none",
                        "app_version": "app-test",
                        "created_at": ANALYSIS_AT,
                        "symbol": "BTCUSDT",
                        "side": "long",
                        "time_horizon": "intraday_short",
                    }
                ]
            )
        raise AssertionError(f"Unexpected query: {normalized}")


def proposal(time_horizon="intraday_short"):
    return SimpleNamespace(
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        take_profit=102.0,
        stop_loss=99.0,
        time_horizon=time_horizon,
    )


def champion_result(time_horizon="intraday_short"):
    return {
        "engine_version": "rules-v0.12.1-liquidations-readable",
        "tp_probability": 0.61,
        "sl_probability": 0.33,
        "range_probability": 0.06,
        "risk_level": "medio",
        "setup_grade": "B",
        "confidence": "alta",
        "training_decision": "simular",
        "snapshot": {
            "analysis_at": ANALYSIS_AT,
            "evaluation_horizon_seconds": fixed_horizon_seconds(time_horizon),
            "market_regime": {"name": "range"},
        },
    }


def plan_only_artifact(matrix_sha):
    features = [
        {
            "feature_id": "PLAN-TP-LOG-DISTANCE",
            "rule_id": "PLAN-TP-LOG-DISTANCE",
            "plan_dependencies": ["PLAN-TP-LOG-DISTANCE"],
            "unit": "log_return",
            "center": 0.02,
            "scale": 0.01,
            "max_age_seconds": 0,
        },
        {
            "feature_id": "PLAN-SL-LOG-DISTANCE",
            "rule_id": "PLAN-SL-LOG-DISTANCE",
            "plan_dependencies": ["PLAN-SL-LOG-DISTANCE"],
            "unit": "log_return",
            "center": 0.01,
            "scale": 0.01,
            "max_age_seconds": 0,
        },
        {
            "feature_id": "PLAN-LOG-HORIZON-SECONDS",
            "rule_id": "PLAN-LOG-HORIZON-SECONDS",
            "plan_dependencies": ["PLAN-LOG-HORIZON-SECONDS"],
            "unit": "log_seconds",
            "center": 9.5,
            "scale": 1.0,
            "max_age_seconds": 0,
        },
    ]
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "model_version": "model-shadow-test-v1",
        "dataset_id": "dataset-shadow-test-v1",
        "code_sha256": "code-test-sha",
        "training_cutoff_at": "2026-07-25T00:00:00+00:00",
        "deployment_state": "shadow",
        "admission_matrix_sha256": matrix_sha,
        "supported_horizons": ["intraday_short"],
        "supported_symbols": ["BTCUSDT"],
        "features": features,
        "intercepts": {
            "tp_first": 0.0,
            "sl_first": 0.0,
            "expiry_unresolved": 0.0,
        },
        "coefficients": {
            "tp_first": {
                "PLAN-TP-LOG-DISTANCE": -1.0,
                "PLAN-SL-LOG-DISTANCE": 0.5,
                "PLAN-LOG-HORIZON-SECONDS": 0.4,
            },
            "sl_first": {
                "PLAN-TP-LOG-DISTANCE": 0.5,
                "PLAN-SL-LOG-DISTANCE": -1.0,
                "PLAN-LOG-HORIZON-SECONDS": 0.3,
            },
            "expiry_unresolved": {
                "PLAN-TP-LOG-DISTANCE": 0.3,
                "PLAN-SL-LOG-DISTANCE": 0.3,
                "PLAN-LOG-HORIZON-SECONDS": -0.5,
            },
        },
        "calibration": {
            "method": "multinomial_temperature",
            "temperature": 1.0,
            "validation_report_id": "validation-test-v1",
        },
    }


class ShadowRuntimeTests(unittest.TestCase):
    def test_fixed_deadlines_preserve_the_three_product_frames(self):
        self.assertEqual(fixed_horizon_seconds("intraday_short"), 4 * 60 * 60)
        self.assertEqual(fixed_horizon_seconds("intraday_wide"), 24 * 60 * 60)
        self.assertEqual(fixed_horizon_seconds("short_swing"), 7 * 24 * 60 * 60)

    def test_disabled_shadow_records_block_without_changing_champion(self):
        champion = champion_result()
        original = json.loads(json.dumps(champion))
        db = RuntimeDb(
            config={
                "id": 1,
                "action": "initialize_disabled",
                "enabled": False,
                "selected_model_version": None,
            }
        )

        audit = execute_live_shadow_run(db, 501, proposal(), champion)

        self.assertEqual(audit["status"], "recorded")
        self.assertEqual(audit["block_code"], "shadow_disabled")
        self.assertEqual(champion, original)
        self.assertIsNotNone(db.shadow_insert_params)
        challenger = json.loads(db.shadow_insert_params[11])
        comparison = json.loads(db.shadow_insert_params[12])
        plan = json.loads(db.shadow_insert_params[13])
        self.assertIsNone(challenger["probabilities"])
        self.assertEqual(comparison["served_output"], "champion")
        self.assertEqual(comparison["production_effect"], "none")
        self.assertEqual(
            plan["entry_order_context"]["entry_type"],
            "market",
        )
        self.assertEqual(db.shadow_insert_params[17], "none")

    def test_enabled_registered_artifact_produces_shadow_prediction_only(self):
        matrix = json.loads(
            Path(
                "auditorias_motor/matriz_admisibilidad_reglas_v0_1.json"
            ).read_text(encoding="utf-8")
        )
        artifact = plan_only_artifact(matrix["matrix_sha256"])
        db = RuntimeDb(
            config={
                "id": 2,
                "action": "select_shadow_model",
                "enabled": True,
                "selected_model_version": artifact["model_version"],
            },
            artifact=artifact,
        )

        audit = execute_live_shadow_run(
            db,
            502,
            proposal(),
            champion_result(),
        )

        self.assertEqual(audit["challenger_status"], "shadow_prediction")
        challenger = json.loads(db.shadow_insert_params[11])
        self.assertAlmostEqual(sum(challenger["probabilities"].values()), 1.0)
        self.assertEqual(
            challenger["trace"]["production_effect"],
            "none",
        )

    def test_same_recommendation_and_config_is_idempotent(self):
        db = RuntimeDb(
            config={
                "id": 1,
                "enabled": False,
                "selected_model_version": None,
            },
            existing_run={"id": 44},
        )

        audit = execute_live_shadow_run(
            db,
            503,
            proposal(),
            champion_result(),
        )

        self.assertEqual(audit["status"], "idempotent_skip")
        self.assertEqual(audit["shadow_run_id"], 44)
        self.assertIsNone(db.shadow_insert_params)

    def test_kill_switch_event_preserves_previous_selection(self):
        db = QueueDb(
            [
                {
                    "id": 12,
                    "enabled": True,
                    "selected_model_version": "model-v2",
                }
            ]
        )

        event_id = disable_shadow(
            db,
            reason="incidente",
            requested_by="auditor",
            code_commit_sha="abc123",
        )

        self.assertEqual(event_id, 77)
        params = db.inserts[0]
        self.assertEqual(params[0], "kill_switch_disable")
        self.assertFalse(params[1])
        self.assertEqual(params[2], "model-v2")
        self.assertEqual(params[3], 12)

    def test_select_requires_registered_shadow_artifact(self):
        db = QueueDb(
            [
                {
                    "model_version": "model-v2",
                    "deployment_state": "shadow",
                },
                {
                    "id": 12,
                    "enabled": False,
                    "selected_model_version": "model-v1",
                },
            ]
        )

        select_shadow_model(
            db,
            model_version="model-v2",
            reason="aprobacion humana",
            requested_by="auditor",
        )

        params = db.inserts[0]
        self.assertEqual(params[0], "select_shadow_model")
        self.assertTrue(params[1])
        self.assertEqual(params[2], "model-v2")
        self.assertEqual(params[4], "model-v1")

    def test_rollback_copies_exact_previous_state_as_new_event(self):
        db = QueueDb(
            [
                {
                    "id": 20,
                    "enabled": False,
                    "selected_model_version": "model-v2",
                    "previous_event_id": 19,
                },
                {
                    "id": 19,
                    "enabled": True,
                    "selected_model_version": "model-v1",
                },
            ]
        )

        rollback_shadow(
            db,
            reason="volver al estado anterior",
            requested_by="auditor",
        )

        params = db.inserts[0]
        self.assertEqual(params[0], "rollback")
        self.assertTrue(params[1])
        self.assertEqual(params[2], "model-v1")
        self.assertEqual(params[3], 20)
        self.assertEqual(params[5], 19)

    def test_shadow_failure_rolls_back_only_savepoint(self):
        class SavepointDb:
            def __init__(self):
                self.queries = []

            def execute(self, query, params=None):
                self.queries.append(" ".join(query.split()))
                return Cursor()

        db = SavepointDb()
        with patch(
            "app.execute_live_shadow_run",
            side_effect=RuntimeError("shadow failed"),
        ), patch("app.logger.exception"):
            result = persist_live_shadow_safely(
                    db,
                    504,
                    proposal(),
                    champion_result(),
                )

        self.assertEqual(result["status"], "technical_error_isolated")
        self.assertEqual(
            db.queries,
            [
                "SAVEPOINT challenger_shadow_run",
                "ROLLBACK TO SAVEPOINT challenger_shadow_run",
                "RELEASE SAVEPOINT challenger_shadow_run",
            ],
        )

    def test_authenticated_audit_separates_champion_and_challenger(self):
        report = build_user_shadow_audit(AuditDb(), user_id=7, limit=500)

        self.assertFalse(report["current_config"]["enabled"])
        self.assertEqual(report["summary"]["total_runs"], 1)
        self.assertEqual(
            report["summary"]["block_counts"],
            {"shadow_disabled": 1},
        )
        self.assertEqual(report["runs"][0]["champion"]["tp_probability"], 0.6)
        self.assertIsNone(
            report["runs"][0]["challenger"]["probabilities"]
        )
        self.assertEqual(
            report["runs"][0]["comparison"]["served_output"],
            "champion",
        )

    def test_schema_keeps_shadow_tables_private_and_append_only(self):
        schema = Path("supabase/schema.sql").read_text(encoding="utf-8")
        for table in (
            "challenger_model_artifacts",
            "challenger_shadow_config_events",
            "challenger_shadow_runs",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", schema)
            self.assertIn(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY", schema)
        self.assertIn("challenger_shadow_runs_no_update", schema)
        self.assertIn("challenger_shadow_runs_no_delete", schema)
        self.assertIn("CHECK(production_effect = 'none')", schema)


if __name__ == "__main__":
    unittest.main()
