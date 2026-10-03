"""Exercise the real creation SQL and compact LIMIT persistence, without network."""
from __future__ import annotations

import json
import sqlite3
import unittest
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import app
from limit_learning_persistence import SNAPSHOT_BYTE_BUDGETS
from limit_production_analysis import analyze_limit_trade
from tests.test_limit_production_analysis import conditional_result, pending_proposal


def operation_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE recommendations (
            id INTEGER PRIMARY KEY, user_id INTEGER, operation_id INTEGER,
            analysis_type TEXT, symbol TEXT, side TEXT, time_horizon TEXT,
            analysis_json TEXT, created_at TEXT
        );
        CREATE TABLE operations (
            id INTEGER PRIMARY KEY, user_id INTEGER, symbol TEXT, side TEXT,
            time_horizon TEXT, entry REAL, margin REAL, leverage REAL,
            stop_loss REAL, take_profit REAL, status TEXT, started_at TEXT,
            mode TEXT, contest_season_id INTEGER, entry_type TEXT,
            requested_entry REAL, trigger_condition TEXT, entry_order_type TEXT
        );
        CREATE TABLE price_ticks (
            operation_id INTEGER, symbol TEXT, price REAL, source TEXT,
            captured_at TEXT
        );
        CREATE TABLE limit_learning_snapshots (
            id INTEGER PRIMARY KEY, operation_id INTEGER,
            recommendation_id INTEGER, analysis_id TEXT, snapshot_type TEXT,
            snapshot_schema_version TEXT, event_at TEXT, selected_case_day TEXT,
            daily_slot INTEGER, symbol TEXT, side TEXT, time_horizon TEXT,
            learning_label TEXT, payload_sha256 TEXT, payload_bytes INTEGER,
            payload_json TEXT, production_effect TEXT,
            UNIQUE(operation_id, snapshot_type)
        );
    """)
    return db


@contextmanager
def creation_environment(db):
    @contextmanager
    def connect():
        with db:
            yield db

    with ExitStack() as stack:
        stack.enter_context(patch.object(app, "current_user", return_value={"id": 7}))
        stack.enter_context(patch.object(app, "connect", connect))
        stack.enter_context(patch.object(app, "ensure_training_wallet_funded"))
        stack.enter_context(patch.object(app, "sync_user_cash_balance", return_value={
            "training": {"cash_balance": 1000}, "contest": {"cash_balance": 1000},
        }))
        stack.enter_context(patch.object(app, "ensure_current_contest_season", return_value={"id": 1}))
        stack.enter_context(patch.object(app, "get_contest_entry", return_value={"id": 7}))
        wallet = stack.enter_context(patch.object(app, "record_wallet_event"))
        quote = stack.enter_context(patch.object(app, "require_fresh_worker_market_price", return_value={
            "price": 100, "captured_at": "2026-08-05T12:00:00+00:00",
        }))
        yield wallet, quote


def seed_analysis(db, *, side="long", analysis_type="pre_trade_limit", **overrides):
    proposal = pending_proposal(side=side, trigger_condition="price_lte" if side == "long" else "price_gte")
    result = analyze_limit_trade(
        proposal,
        price_loader=lambda *_args, **_kwargs: 100,
        conditional_analyzer=lambda *_args, **_kwargs: conditional_result(),
    )
    result["entry_order_context"] = {
        "entry_type": "pending", "trigger_condition": proposal.trigger_condition,
        "entry_order_type": "limit_pullback", "requested_entry": proposal.entry,
    }
    values = dict(id=20, user_id=7, operation_id=None, analysis_type=analysis_type,
                  symbol=proposal.symbol, side=proposal.side, time_horizon=proposal.time_horizon,
                  analysis_json=json.dumps(result), created_at="2026-08-05T12:00:00+00:00")
    values.update(overrides)
    db.execute("""
        INSERT INTO recommendations VALUES (
            :id, :user_id, :operation_id, :analysis_type, :symbol, :side,
            :time_horizon, :analysis_json, :created_at
        )
    """, values)
    db.commit()
    return app.CreateOperationPayload(**proposal.__dict__, recommendation_id=20, mode="training")


class LimitOperationCreationTests(unittest.TestCase):
    def test_limit_creation_links_real_analysis_and_one_compact_placement(self):
        for side in ("long", "short"):
            for mode in ("training", "contest"):
                with self.subTest(side=side, mode=mode), operation_db() as db:
                    payload = seed_analysis(db, side=side)
                    payload.mode = mode
                    with creation_environment(db) as (wallet, quote):
                        result = app.create_operation(payload, session_token="token")
                    self.assertEqual(result["status"], "PENDING_ENTRY")
                    self.assertIsNone(result["started_at"])
                    self.assertEqual(result["entry"], payload.entry)
                    self.assertEqual(db.execute("SELECT operation_id FROM recommendations").fetchone()[0], result["id"])
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM price_ticks").fetchone()[0], 0)
                    snapshots = db.execute("SELECT * FROM limit_learning_snapshots").fetchall()
                    self.assertEqual(len(snapshots), 1)
                    self.assertEqual(snapshots[0]["snapshot_type"], "placement")
                    self.assertEqual(snapshots[0]["recommendation_id"], 20)
                    self.assertLessEqual(snapshots[0]["payload_bytes"], SNAPSHOT_BYTE_BUDGETS["placement"])
                    self.assertEqual(app._opening_recommendation_id(db, result["id"]), 20)
                    self.assertEqual(app.load_limit_operation_context(db, {
                        "id": result["id"], "entry_order_type": "limit_pullback",
                    })["recommendation_id"], 20)
                    wallet.assert_called_once()
                    self.assertEqual(wallet.call_args.kwargs["amount"], -payload.margin)
                    quote.assert_not_called()

    def test_invalid_references_are_rejected_without_creating_an_order(self):
        references = [
            {"analysis_type": "pre_trade"},
            {"analysis_type": "operation_observation"},
            {"user_id": 8},
            {"operation_id": 99},
            {"id": 21},
        ]
        for reference in references:
            with self.subTest(reference=reference), operation_db() as db:
                payload = seed_analysis(db, **reference)
                with creation_environment(db) as (wallet, _), self.assertRaises(app.HTTPException) as error:
                    app.create_operation(payload, session_token="token")
                self.assertEqual(error.exception.status_code, 400)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM limit_learning_snapshots").fetchone()[0], 0)
                wallet.assert_not_called()

    def test_changed_plan_identity_or_activation_is_still_rejected(self):
        changes = [
            ("symbol", "ETHUSDT"), ("side", "short"),
            ("time_horizon", "short_swing"),
        ]
        for key, value in changes:
            with self.subTest(key=key), operation_db() as db:
                payload = seed_analysis(db)
                db.execute(f"UPDATE recommendations SET {key}=?", (value,))
                db.commit()
                with creation_environment(db), self.assertRaises(app.HTTPException) as error:
                    app.create_operation(payload, session_token="token")
                self.assertEqual(error.exception.status_code, 400)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)
        for key, value in [("entry_type", "market"), ("trigger_condition", "price_gte"),
                           ("entry_order_type", "stop_breakout"), ("requested_entry", 99)]:
            with self.subTest(key=key), operation_db() as db:
                payload = seed_analysis(db)
                stored = json.loads(db.execute("SELECT analysis_json FROM recommendations").fetchone()[0])
                stored["entry_order_context"][key] = value
                db.execute("UPDATE recommendations SET analysis_json=?", (json.dumps(stored),))
                db.commit()
                with creation_environment(db), self.assertRaises(app.HTTPException) as error:
                    app.create_operation(payload, session_token="token")
                self.assertEqual(error.exception.status_code, 400)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)

    def test_failed_compact_persistence_rolls_back_order_and_analysis_link(self):
        with operation_db() as db:
            payload = seed_analysis(db)
            stored = json.loads(db.execute("SELECT analysis_json FROM recommendations").fetchone()[0])
            stored.pop("limit_analysis")
            db.execute("UPDATE recommendations SET analysis_json=?", (json.dumps(stored),))
            db.commit()
            with creation_environment(db) as (wallet, _), self.assertRaises(app.HTTPException) as error:
                app.create_operation(payload, session_token="token")
            self.assertEqual(error.exception.status_code, 500)
            self.assertEqual(error.exception.detail["code"], "limit_analysis_payload_missing")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)
            self.assertIsNone(db.execute("SELECT operation_id FROM recommendations").fetchone()[0])
            wallet.assert_not_called()

    def test_market_creation_still_requires_market_analysis_and_records_quote(self):
        for analysis_type in ("pre_trade", "pre_trade_limit", "operation_observation"):
            with self.subTest(analysis_type=analysis_type), operation_db() as db:
                payload = seed_analysis(db, analysis_type=analysis_type)
                payload.entry_type = "market"
                payload.trigger_condition = None
                stored = {"entry_order_context": {"entry_type": "market"}}
                db.execute("UPDATE recommendations SET analysis_json=?", (json.dumps(stored),))
                db.commit()
                with creation_environment(db):
                    if analysis_type == "pre_trade":
                        result = app.create_operation(payload, session_token="token")
                        self.assertEqual(result["status"], "OPEN")
                        self.assertEqual(result["entry"], 100)
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM price_ticks").fetchone()[0], 1)
                    else:
                        with self.assertRaises(app.HTTPException) as error:
                            app.create_operation(payload, session_token="token")
                        self.assertEqual(error.exception.status_code, 400)
                        self.assertEqual(db.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM limit_learning_snapshots").fetchone()[0], 0)

    def test_later_observations_do_not_replace_the_opening_limit_contract(self):
        with operation_db() as db:
            payload = seed_analysis(db)
            with creation_environment(db):
                result = app.create_operation(payload, session_token="token")
            seed_analysis(db, id=21, operation_id=result["id"],
                          analysis_type="operation_observation", analysis_json="{}",
                          created_at="2026-08-05T13:00:00+00:00")
            self.assertEqual(app._opening_recommendation_id(db, result["id"]), 20)
            loaded = app.load_limit_operation_context(db, {
                "id": result["id"], "entry_order_type": "limit_pullback",
            })
            self.assertEqual(loaded["recommendation_id"], 20)
            self.assertEqual(loaded["contract"]["order"]["requested_entry"], payload.entry)

    def test_legacy_linked_limit_contract_is_still_readable(self):
        with operation_db() as db:
            seed_analysis(db, analysis_type="pre_trade", operation_id=99)
            self.assertEqual(app._opening_recommendation_id(db, 99), 20)
            loaded = app.load_limit_operation_context(db, {
                "id": 99, "entry_order_type": "limit_pullback",
            })
            self.assertEqual(loaded["recommendation_id"], 20)


if __name__ == "__main__":
    unittest.main()
