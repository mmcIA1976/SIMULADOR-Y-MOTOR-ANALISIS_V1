import json
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from unittest.mock import patch

import app

from limit_activation_baseline import build_limit_activation_baseline
from limit_learning_persistence import (
    SNAPSHOT_BYTE_BUDGETS,
    build_activation_snapshot_record,
    build_closure_snapshot_record,
)
from limit_lifecycle_runtime import (
    closure_snapshot_values,
    extract_limit_context,
    recalculate_at_activation,
)
from limit_order_contract import LifecycleEvent, build_limit_order_contract
from m7_production_analysis import NewEngineAnalysisError


def contract():
    return build_limit_order_contract(
        analysis_id="limit-lifecycle-test",
        symbol="XRPUSDT",
        side="long",
        time_horizon="intraday_short",
        analysis_at="2026-08-05T10:00:00+00:00",
        current_price=1.10,
        requested_entry=1.05,
        stop_loss=1.00,
        take_profit=1.15,
        trigger_condition="price_lte",
    )


def context():
    limit_contract = contract()
    baseline = build_limit_activation_baseline(
        limit_contract,
        sigma_horizon=0.08,
    )
    return {"contract": limit_contract, "activation_baseline": baseline}


def operation():
    return {
        "id": 286,
        "symbol": "XRPUSDT",
        "side": "long",
        "time_horizon": "intraday_short",
        "entry": 1.05,
        "requested_entry": 1.05,
        "margin": 200.0,
        "leverage": 10.0,
        "stop_loss": 1.00,
        "take_profit": 1.15,
        "triggered_at": "2026-08-05T10:30:00+00:00",
    }


def evaluated_result():
    return {
        "engine_version": "TP-SL-PROBABILITY-ENGINE-v0.4",
        "tp_probability": 0.55,
        "sl_probability": 0.30,
        "range_probability": 0.15,
        "model_trace": {"active_predictive_rule_ids": ["R1", "R2"]},
        "snapshot": {
            "data_cutoff_at": "2026-08-05T10:30:00+00:00",
            "availability": {
                "futures_klines": True,
                "liquidation_heatmap": False,
            },
        },
    }


class LimitLifecycleRuntimeTests(unittest.TestCase):
    def test_extracts_only_the_supported_pullback_contract(self):
        limit_context = extract_limit_context(
            {
                "limit_analysis": {
                    "contract": contract(),
                    "activation_baseline": {"status": "evaluated"},
                }
            }
        )

        self.assertIsNotNone(limit_context)
        self.assertEqual(
            limit_context["contract"]["order"]["entry_order_type"],
            "limit_pullback",
        )
        self.assertIsNone(extract_limit_context({"engine_family": "market"}))

    def test_historical_activation_uses_the_real_cutoff_without_live_context(self):
        analyzer = Mock(return_value=evaluated_result())
        evidence = {
            "source": "binance_usdm_futures_1m_kline",
            "market_data": {"low": 1.049, "high": 1.08},
        }

        values = recalculate_at_activation(
            operation(),
            context(),
            activated_at="2026-08-05T10:30:00+00:00",
            activation_evidence=evidence,
            analyzer=analyzer,
            now=datetime(2026, 8, 5, 11, 0, tzinfo=timezone.utc),
        )

        kwargs = analyzer.call_args.kwargs
        self.assertEqual(
            kwargs["effective_analysis_at"],
            datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(kwargs["context_loader"](), {})
        self.assertEqual(values["trigger_observed_price"], 1.049)
        self.assertEqual(values["simulated_fill_price"], 1.05)
        self.assertEqual(
            values["post_activation_feature_vector"]["mode"],
            "historical_reconstruction",
        )

    def test_live_activation_keeps_live_context_and_compacts_m6(self):
        analyzer = Mock(return_value=evaluated_result())
        activation_time = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)

        values = recalculate_at_activation(
            operation(),
            context(),
            activated_at=activation_time,
            activation_evidence={
                "source": "binance_usdm_futures_ticker",
                "market_data": {"price": 1.0499},
            },
            analyzer=analyzer,
            now=activation_time,
        )

        self.assertNotIn("context_loader", analyzer.call_args.kwargs)
        self.assertEqual(values["post_activation_feature_vector"]["tp"], 0.55)
        self.assertEqual(values["post_activation_feature_vector"]["active_rules"], 2)
        record = build_activation_snapshot_record(
            context()["contract"],
            values,
            operation_id=286,
            recommendation_id=99,
        )
        self.assertLessEqual(record["payload_bytes"], SNAPSHOT_BYTE_BUDGETS["activation"])
        self.assertNotIn("klines", json.loads(record["payload_json"]))

    def test_m6_failure_is_recorded_as_blocked_but_does_not_cancel_activation(self):
        def blocked(*_args, **_kwargs):
            raise NewEngineAnalysisError("insufficient_pretrade_history")

        activation_time = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
        values = recalculate_at_activation(
            operation(),
            context(),
            activated_at=activation_time,
            activation_evidence={"source": "ticker", "market_data": {"price": 1.05}},
            analyzer=blocked,
            now=activation_time,
        )

        self.assertEqual(values["post_activation_feature_vector"]["status"], "blocked")
        self.assertEqual(
            values["post_activation_feature_vector"]["code"],
            "insufficient_pretrade_history",
        )

    def test_closure_labels_tp_sl_expiry_and_manual_distinctly(self):
        kline = [
            int(datetime(2026, 8, 5, 10, 31, tzinfo=timezone.utc).timestamp() * 1000),
            "1.05",
            "1.12",
            "1.02",
            "1.10",
            "10",
            int(datetime(2026, 8, 5, 10, 31, 59, tzinfo=timezone.utc).timestamp() * 1000),
        ]
        expected = {
            LifecycleEvent.TAKE_PROFIT.value: "activation_then_tp_first",
            LifecycleEvent.STOP_LOSS.value: "activation_then_sl_first",
            LifecycleEvent.OUTCOME_EXPIRED.value: "activation_then_neither_barrier",
            LifecycleEvent.MANUAL_CLOSE.value: "censored_after_activation",
        }
        for event, label in expected.items():
            with self.subTest(event=event):
                values = closure_snapshot_values(
                    operation(),
                    context(),
                    closed_at="2026-08-05T11:00:00+00:00",
                    terminal_event=event,
                    evidence_source="test",
                    close_price=1.10,
                    pnl=10.0,
                    market_klines=[kline],
                )
                self.assertEqual(values["learning_label"], label)
                self.assertGreater(values["mfe_pct"], 0)
                self.assertLess(values["mae_pct"], 0)
                record = build_closure_snapshot_record(
                    context()["contract"],
                    values,
                    operation_id=286,
                    recommendation_id=99,
                )
                self.assertLessEqual(record["payload_bytes"], SNAPSHOT_BYTE_BUDGETS["closure"])

    def test_transition_inside_a_candle_prefers_exact_aggregate_trade_time(self):
        pending = {
            **operation(),
            "created_at": "2026-08-05T10:00:00+00:00",
            "entry_type": "pending",
            "entry_order_type": "limit_pullback",
            "trigger_condition": "price_lte",
        }
        open_ms = int(datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
        kline = [open_ms, "1.06", "1.07", "1.04", "1.05", "10", open_ms + 59_999]
        trade_time = open_ms + 23_456
        with patch.object(
            app.market_data,
            "get_agg_trades",
            return_value=[{"p": "1.0498", "q": "50", "T": trade_time}],
        ):
            trigger = app.triggered_entry_from_market_klines(pending, [kline])

        self.assertEqual(trigger[1], app.iso_from_ms(trade_time))
        self.assertEqual(
            trigger[2]["source"],
            "binance_usdm_futures_agg_trade",
        )

    def test_worker_path_persists_exactly_placement_activation_and_closure(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.executescript(
            """
            CREATE TABLE operations (
                id INTEGER PRIMARY KEY, user_id INTEGER, symbol TEXT, side TEXT,
                time_horizon TEXT, entry REAL, requested_entry REAL, margin REAL,
                leverage REAL, stop_loss REAL, take_profit REAL, status TEXT,
                created_at TEXT, started_at TEXT, triggered_at TEXT, trigger_price REAL,
                activation_evidence_json TEXT, mode TEXT, contest_season_id INTEGER,
                entry_type TEXT, entry_order_type TEXT, trigger_condition TEXT,
                closed_at TEXT, close_price REAL, close_reason TEXT, final_pnl REAL,
                observation_status TEXT, observation_until TEXT, closing_note TEXT,
                learning_outcome TEXT, learning_summary TEXT, exit_evidence_json TEXT
            );
            CREATE TABLE recommendations (
                id INTEGER PRIMARY KEY, operation_id INTEGER, analysis_json TEXT,
                created_at TEXT
            );
            CREATE TABLE price_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, operation_id INTEGER,
                symbol TEXT, price REAL, source TEXT, captured_at TEXT
            );
            CREATE TABLE limit_learning_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER, recommendation_id INTEGER, analysis_id TEXT,
                snapshot_type TEXT, snapshot_schema_version TEXT, event_at TEXT,
                selected_case_day TEXT, daily_slot INTEGER, symbol TEXT, side TEXT,
                time_horizon TEXT, learning_label TEXT, payload_sha256 TEXT,
                payload_bytes INTEGER, payload_json TEXT, production_effect TEXT,
                UNIQUE(operation_id, snapshot_type)
            );
            INSERT INTO operations (
                id, user_id, symbol, side, time_horizon, entry, requested_entry,
                margin, leverage, stop_loss, take_profit, status, created_at,
                mode, entry_type, entry_order_type, trigger_condition
            ) VALUES (
                286, 7, 'XRPUSDT', 'long', 'intraday_short', 1.05, 1.05,
                200, 10, 1.00, 1.15, 'PENDING_ENTRY',
                '2026-08-05T10:00:00+00:00', 'training', 'pending',
                'limit_pullback', 'price_lte'
            );
            """
        )
        limit_context = context()
        analysis_payload = {
            "limit_analysis": {
                "contract": limit_context["contract"],
                "activation_baseline": limit_context["activation_baseline"],
            }
        }
        db.execute(
            "INSERT INTO recommendations (id, operation_id, analysis_json, created_at) VALUES (?, ?, ?, ?)",
            (99, 286, json.dumps(analysis_payload), "2026-08-05T10:00:00+00:00"),
        )
        db.execute(
            """
            INSERT INTO limit_learning_snapshots (
                operation_id, recommendation_id, analysis_id, snapshot_type,
                snapshot_schema_version, event_at, selected_case_day, daily_slot,
                symbol, side, time_horizon, learning_label, payload_sha256,
                payload_bytes, payload_json, production_effect
            ) VALUES (?, ?, ?, 'placement', ?, ?, ?, 1, ?, ?, ?, NULL, ?, ?, ?, 'none')
            """,
            (
                286,
                99,
                "limit-lifecycle-test",
                "limit-learning-snapshot-v0.1",
                "2026-08-05T10:00:00+00:00",
                "2026-08-05",
                "XRPUSDT",
                "long",
                "intraday_short",
                "a" * 64,
                2,
                "{}",
            ),
        )
        open_ms = int(datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
        activation_kline = [
            open_ms,
            "1.06",
            "1.07",
            "1.049",
            "1.05",
            "10",
            open_ms + 59_999,
        ]
        activation_values = recalculate_at_activation(
            operation(),
            limit_context,
            activated_at="2026-08-05T10:30:00+00:00",
            activation_evidence={
                "source": "binance_usdm_futures_1m_kline",
                "market_data": {"low": 1.049},
            },
            analyzer=Mock(return_value=evaluated_result()),
            now=datetime(2026, 8, 5, 11, 0, tzinfo=timezone.utc),
        )
        with (
            patch.object(app, "recalculate_at_activation", return_value=activation_values),
            patch.object(app, "triggered_entry_from_trades", return_value=None),
            patch.object(
                app,
                "sync_user_cash_balance",
                return_value={"training": {"cash_balance": 800.0}},
            ),
            patch.object(app, "record_wallet_event"),
        ):
            activated = app.activate_triggered_pending_operations(
                db,
                "XRPUSDT",
                1.06,
                market_klines=[activation_kline],
            )

        self.assertIn(286, activated)
        self.assertEqual(
            db.execute("SELECT status FROM operations WHERE id = 286").fetchone()["status"],
            "OPEN",
        )
        with (
            patch.object(
                app,
                "triggered_exit_from_market_path",
                return_value=(
                    "take_profit",
                    1.15,
                    "2026-08-05T11:00:00+00:00",
                    {"source": "test_market_path"},
                ),
            ),
            patch.object(app, "record_compact_exit_tick"),
            patch.object(app, "record_exit_window_ticks"),
            patch.object(
                app,
                "sync_user_cash_balance",
                return_value={"training": {"cash_balance": 1010.0}},
            ),
            patch.object(app, "record_wallet_event"),
        ):
            closed = app.close_triggered_open_operations(
                db,
                "XRPUSDT",
                1.15,
                market_klines=[activation_kline],
                persist_exit_window=False,
            )

        self.assertIn(286, closed)
        snapshots = db.execute(
            "SELECT snapshot_type, payload_bytes FROM limit_learning_snapshots ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [row["snapshot_type"] for row in snapshots],
            ["placement", "activation", "closure"],
        )
        self.assertLessEqual(snapshots[1]["payload_bytes"], 1280)
        self.assertLessEqual(snapshots[2]["payload_bytes"], 1024)
        self.assertEqual(
            db.execute("SELECT status FROM operations WHERE id = 286").fetchone()["status"],
            "CLOSED",
        )
        db.close()


if __name__ == "__main__":
    unittest.main()
