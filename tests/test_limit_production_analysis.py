from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app
from analysis_engine import TradeProposal
from limit_production_analysis import (
    LIMIT_PRODUCTION_ENGINE_VERSION,
    LimitProductionAnalysisError,
    analyze_limit_trade,
)
from tests.test_limit_learning_persistence import FakeDb


class InsertCursor:
    lastrowid = 77


class RecommendationDb:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()), tuple(params)))
        return InsertCursor()


def connect_factory(db):
    @contextmanager
    def connect():
        yield db

    return connect


def pending_proposal(
    *,
    side: str = "long",
    trigger_condition: str = "price_lte",
    entry_order_type: str = "limit_pullback",
) -> TradeProposal:
    return TradeProposal(
        symbol="BTCUSDT",
        side=side,
        time_horizon="intraday_short",
        entry=98.0 if side == "long" else 102.0,
        margin=100.0,
        leverage=2.0,
        stop_loss=96.0 if side == "long" else 104.0,
        take_profit=103.0 if side == "long" else 97.0,
        entry_type="pending",
        trigger_condition=trigger_condition,
        entry_order_type=entry_order_type,
    )


def conditional_result() -> dict:
    return {
        "analysis_type": "pre_trade",
        "engine_family": "tp_sl_competing_risks",
        "engine_version": "TP-SL-PROBABILITY-ENGINE-v0.4",
        "tp_probability": 0.55,
        "sl_probability": 0.35,
        "range_probability": 0.10,
        "probability_ranges": {},
        "risk_level": "35.0% SL",
        "setup_grade": "no aplicable",
        "confidence": "calibracion historica",
        "training_decision": "decision del usuario",
        "time_horizon": "intraday_short",
        "parameter_advice": {},
        "reasons": [],
        "alerts": [],
        "plain_summary": "preview",
        "explained_metrics": [],
        "snapshot": {
            "analysis_at": "2026-08-05T12:00:00+00:00",
            "data_cutoff_at": "2026-08-05T12:00:00+00:00",
        },
        "model_trace": {"candidate_version": "m6-test"},
        "_internal_runtime": {
            "run": {
                "horizon_volatility": 0.04,
                "m5_analysis": {"traces": []},
                "observational_rule_traces": {"traces": []},
            },
            "live_context": {},
        },
    }


class LimitProductionAnalysisTests(unittest.TestCase):
    def test_two_stage_result_keeps_activation_separate_from_conditional_tp(self):
        analyzer_calls = []
        liquidation_loader = object()
        order_book_loader = object()

        def analyzer(proposal, **kwargs):
            analyzer_calls.append((proposal, kwargs))
            return conditional_result()

        result = analyze_limit_trade(
            pending_proposal(),
            price_loader=lambda *_args, **_kwargs: 100.0,
            conditional_analyzer=analyzer,
            context_loader=liquidation_loader,
            order_book_observation_loader=order_book_loader,
        )

        self.assertEqual(
            result["engine_version"],
            LIMIT_PRODUCTION_ENGINE_VERSION,
        )
        self.assertEqual(result["engine_family"], "pending_limit_two_stage")
        self.assertEqual(result["tp_probability"], 0.55)
        tree = result["limit_analysis"]["probability_tree"]
        activation = tree["activation"]["activated_by_expiry"]
        self.assertNotEqual(activation, result["tp_probability"])
        self.assertAlmostEqual(
            tree["overall"]["activation_then_tp_first"],
            activation * 0.55,
        )
        self.assertEqual(
            result["probability_semantics"]["visible_tp_sl_range_cards"],
            "conditional_after_activation",
        )
        self.assertNotIn("_internal_runtime", result)
        analyzed_proposal, kwargs = analyzer_calls[0]
        self.assertEqual(analyzed_proposal.entry_type, "market")
        self.assertEqual(analyzed_proposal.entry, 98.0)
        self.assertIs(kwargs["context_loader"], liquidation_loader)
        self.assertIs(
            kwargs["order_book_observation_loader"],
            order_book_loader,
        )
        self.assertEqual(kwargs["context_market_price"], 100.0)
        self.assertTrue(kwargs["include_internal_runtime"])

    def test_stop_order_is_rejected_before_running_market_analysis(self):
        with self.assertRaisesRegex(
            LimitProductionAnalysisError,
            "limit_pullback_required",
        ):
            analyze_limit_trade(
                pending_proposal(
                    trigger_condition="price_gte",
                    entry_order_type="stop_breakout",
                ),
                price_loader=lambda *_args, **_kwargs: 100.0,
                conditional_analyzer=lambda *_args, **_kwargs: self.fail(
                    "conditional analyzer must not run"
                ),
            )

    def test_selected_operation_persists_one_compact_placement_only(self):
        result = analyze_limit_trade(
            pending_proposal(),
            price_loader=lambda *_args, **_kwargs: 100.0,
            conditional_analyzer=lambda *_args, **_kwargs: conditional_result(),
        )
        recommendation = {
            "id": 20,
            "analysis_json": json.dumps(result),
        }
        db = FakeDb()

        first = app.persist_selected_limit_placement(
            db,
            recommendation,
            operation_id=10,
        )
        second = app.persist_selected_limit_placement(
            db,
            recommendation,
            operation_id=10,
        )

        self.assertEqual(first["status"], "recorded")
        self.assertEqual(second["status"], "idempotent_skip")
        self.assertEqual(len(db.rows), 1)
        self.assertEqual(db.rows[0]["snapshot_type"], "placement")
        self.assertLessEqual(db.rows[0]["payload_bytes"], 3584)
        self.assertNotIn("candles", db.rows[0]["payload_json"])
        self.assertNotIn("order_book", db.rows[0]["payload_json"])

    def test_api_analyze_routes_limit_without_creating_learning_snapshot(self):
        result = analyze_limit_trade(
            pending_proposal(),
            price_loader=lambda *_args, **_kwargs: 100.0,
            conditional_analyzer=lambda *_args, **_kwargs: conditional_result(),
        )
        db = RecommendationDb()
        payload = app.TradePayload(
            symbol="BTCUSDT",
            side="long",
            time_horizon="intraday_short",
            entry_type="pending",
            trigger_condition="price_lte",
            entry=98,
            margin=100,
            leverage=2,
            stop_loss=96,
            take_profit=103,
        )

        with (
            patch.object(app, "current_user", return_value={"id": 7}),
            patch.object(app, "analyze_limit_trade", return_value=result) as analyze,
            patch.object(app, "connect", connect_factory(db)),
        ):
            response = app.analyze(payload, session_token="token")

        self.assertEqual(response["recommendation_id"], 77)
        analyze.assert_called_once()
        self.assertEqual(len(db.queries), 3)
        recommendation_query = next(
            item for item in db.queries if "INSERT INTO recommendations" in item[0]
        )
        attempt_query = next(
            item for item in db.queries if "INSERT INTO analysis_attempts" in item[0]
        )
        self.assertNotIn(
            "limit_learning_snapshots",
            " ".join(query for query, _params in db.queries),
        )
        self.assertIn(LIMIT_PRODUCTION_ENGINE_VERSION, recommendation_query[1])
        self.assertIn("completed", attempt_query[1])

    def test_api_rejects_stop_order_before_any_limit_analysis(self):
        payload = app.TradePayload(
            symbol="BTCUSDT",
            side="long",
            time_horizon="intraday_short",
            entry_type="pending",
            trigger_condition="price_gte",
            entry=102,
            margin=100,
            leverage=2,
            stop_loss=96,
            take_profit=103,
        )

        with (
            patch.object(app, "current_user", return_value={"id": 7}),
            patch.object(app, "analyze_limit_trade") as analyze,
            self.assertRaises(app.HTTPException) as raised,
        ):
            app.analyze(payload, session_token="token")

        self.assertEqual(raised.exception.status_code, 400)
        analyze.assert_not_called()

    def test_frontend_labels_limit_probabilities_as_conditional(self):
        html = Path("index.html").read_text(encoding="utf-8")
        javascript = Path("app.js").read_text(encoding="utf-8")

        self.assertIn('id="tpProbabilityLabel"', html)
        self.assertIn('id="slProbabilityLabel"', html)
        self.assertIn('id="rangeProbabilityLabel"', html)
        self.assertIn('analysis.engine_family === "pending_limit_two_stage"', javascript)
        self.assertIn('isLimitTwoStage ? "TP si activa"', javascript)
        self.assertIn('isLimitTwoStage ? "SL si activa"', javascript)
        self.assertIn('isLimitTwoStage ? "Sin barrera si activa"', javascript)
        self.assertIn("syncLimitTriggerForSide", javascript)


if __name__ == "__main__":
    unittest.main()
