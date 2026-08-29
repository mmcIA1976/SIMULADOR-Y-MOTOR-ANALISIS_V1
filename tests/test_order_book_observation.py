from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import operation_worker
import app
from analysis_engine import TradeProposal
from microstructure_rule_runtime import (
    evaluate_order_book,
    evaluate_order_book_dynamics,
)
from order_book_observation import OrderBookObservationTracker
from order_book_observation_state import (
    publish_order_book_observations,
    summarize_order_book_observation,
)
from sequential_production_analysis import attach_order_book_observation


def depth(
    captured_at_ms: int,
    *,
    bid_wall: int | None = None,
    ask_wall: int | None = None,
    bid_scale: float = 1.0,
    ask_scale: float = 1.0,
) -> dict:
    bids = []
    asks = []
    for index in range(30):
        bid_quantity = 10.0 * bid_scale
        ask_quantity = 10.0 * ask_scale
        if index == bid_wall:
            bid_quantity = 80.0 * bid_scale
        if index == ask_wall:
            ask_quantity = 80.0 * ask_scale
        bids.append([str(99.99 - index * 0.01), str(bid_quantity)])
        asks.append([str(100.01 + index * 0.01), str(ask_quantity)])
    return {
        "lastUpdateId": captured_at_ms,
        "receivedAt": captured_at_ms,
        "bids": bids,
        "asks": asks,
    }


def trades(timestamp_ms: int, *, buy: float = 0.0, sell: float = 0.0) -> list[dict]:
    rows = []
    if buy:
        rows.append({"a": timestamp_ms, "p": "100.02", "q": str(buy), "T": timestamp_ms, "m": False})
    if sell:
        rows.append({"a": timestamp_ms + 1, "p": "99.98", "q": str(sell), "T": timestamp_ms, "m": True})
    return rows


def ready_observation() -> dict:
    tracker = OrderBookObservationTracker(window_seconds=60, minimum_samples=3)
    tracker.observe(
        "BTCUSDT",
        depth(100_000, ask_wall=2),
        trades(99_500, buy=2),
        captured_at_ms=100_000,
    )
    tracker.observe(
        "BTCUSDT",
        depth(110_000, bid_wall=2, bid_scale=1.2),
        trades(105_000, buy=40, sell=2),
        captured_at_ms=110_000,
    )
    return tracker.observe(
        "BTCUSDT",
        depth(120_000, bid_wall=2, ask_scale=1.4),
        trades(115_000, buy=3, sell=25),
        captured_at_ms=120_000,
    )


class Cursor:
    def __init__(self, rows=None, rowcount=1):
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.rows[0] if self.rows else None


class RecordingDb:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))
        return Cursor(rowcount=1)


class OrderBookObservationTests(unittest.TestCase):
    def test_tracker_builds_compact_dynamic_evidence(self):
        summary = ready_observation()

        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["sample_count"], 3)
        self.assertIn("top_5", summary["persistence"])
        self.assertGreaterEqual(
            summary["persistence"]["top_5"]["sign_flip_count"],
            0,
        )
        activity = summary["change_activity"]
        self.assertEqual(activity["transition_count"], 2)
        self.assertGreater(activity["ask_removed_notional"], 0)
        self.assertGreater(activity["execution_confirmed_ask_removal"], 0)
        self.assertEqual(
            activity["unmatched_removal_semantics"],
            "cancellation_like_or_unobserved_execution_not_proven_cancel",
        )
        self.assertIn("current_candidates", summary["walls"])
        self.assertIn("executed_flow_imbalance", summary["executed_flow"])
        self.assertIn("ask_absorption_score", summary["absorption"])
        self.assertFalse(summary["raw_depth_persisted"])
        self.assertFalse(summary["raw_trades_persisted"])
        self.assertNotIn("bids", summary)
        self.assertNotIn("asks", summary)
        self.assertLess(len(json.dumps(summary)), 16_000)

    def test_dynamic_and_static_rules_remain_probability_neutral(self):
        observation = ready_observation()
        static = evaluate_order_book(
            {"order_book_observation": observation},
            side="long",
            analysis_at="2026-08-29T12:00:00+00:00",
        )
        dynamic_long = evaluate_order_book_dynamics(
            observation,
            side="long",
            analysis_at="2026-08-29T12:00:00+00:00",
        )
        dynamic_short = evaluate_order_book_dynamics(
            observation,
            side="short",
            analysis_at="2026-08-29T12:00:00+00:00",
        )

        self.assertEqual(static["status"], "evaluated_shadow")
        self.assertEqual(dynamic_long["status"], "evaluated_shadow")
        self.assertEqual(static["probability_effect"], "none_shadow_observation")
        self.assertEqual(dynamic_long["probability_effect"], "none_shadow_observation")
        long_value = dynamic_long["outputs"]["persistence"]["top_5"]["side_adjusted_mean"]
        short_value = dynamic_short["outputs"]["persistence"]["top_5"]["side_adjusted_mean"]
        self.assertAlmostEqual(long_value, -short_value)

    def test_attachment_replaces_blocked_trace_once_per_stage(self):
        probability = {"served": "unchanged"}
        run = {
            "stage_contexts": {
                "intraday_short": {"context_sigma": 0.02},
                "intraday_wide": {"context_sigma": 0.04},
            },
            "stage_rule_traces": {
                "intraday_short": [
                    {"rule_id": "LIB-CAND-ORDERBOOK-IMBALANCE-001", "status": "blocked"}
                ],
                "intraday_wide": [
                    {"rule_id": "LIB-CAND-ORDERBOOK-IMBALANCE-001", "status": "blocked"}
                ],
            },
            "probability_result": probability,
            "details": {"stage_order": ["intraday_short", "intraday_wide"]},
        }
        proposal = TradeProposal(
            "BTCUSDT", "long", "intraday_wide", 100.0, 200.0, 10.0, 97.0, 103.0
        )
        calls = []

        def loader(symbol):
            calls.append(symbol)
            return ready_observation()

        live_context, summary = attach_order_book_observation(
            run,
            proposal,
            observation_loader=loader,
            analysis_at="2026-08-29T12:00:00+00:00",
        )

        self.assertEqual(calls, ["BTCUSDT"])
        self.assertIs(run["probability_result"], probability)
        self.assertTrue(summary["available"])
        self.assertFalse(
            live_context["order_book_observation"]["raw_depth_persisted"]
        )
        for horizon in ("intraday_short", "intraday_wide"):
            traces_by_id = {
                trace["rule_id"]: trace
                for trace in run["stage_rule_traces"][horizon]
            }
            self.assertEqual(
                traces_by_id["LIB-CAND-ORDERBOOK-IMBALANCE-001"]["status"],
                "evaluated_shadow",
            )

        learning = app.v09_predictive_rule_learning_snapshot(
            {
                "stage_rule_traces": run["stage_rule_traces"],
                "probability_trace": {
                    "stage_traces": [
                        {
                            "time_horizon": "intraday_short",
                            "active_rule_groups": ["price_path"],
                            "current_feature_values": {
                                "intraday_short::M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h": 0.2
                            },
                        }
                    ]
                },
            },
            plan_result="plan_success",
        )
        self.assertIn(
            "LIB-CAND-ORDERBOOK-IMBALANCE-001",
            learning["observational_rule_ids"],
        )
        self.assertEqual(
            learning["observational_rules"]["LIB-CAND-ORDERBOOK-IMBALANCE-001"][
                "probability_effect"
            ],
            "none_observation_only",
        )

    def test_worker_collects_depth_and_trades_for_requested_symbol(self):
        state = operation_worker.WorkerState(
            order_book_tracker=OrderBookObservationTracker(
                window_seconds=60,
                minimum_samples=2,
            )
        )
        depth_loader = Mock(side_effect=lambda _symbol, _limit: depth(100_000))
        trade_loader = Mock(return_value=trades(99_500, buy=1))

        result, failures = operation_worker.collect_order_book_observations(
            state,
            {"BTCUSDT"},
            100_000,
            depth_loader=depth_loader,
            trade_loader=trade_loader,
        )

        self.assertEqual(failures, 0)
        self.assertIn("BTCUSDT", result)
        depth_loader.assert_called_once_with("BTCUSDT", 100)
        self.assertEqual(trade_loader.call_args.args, ("BTCUSDT", 1000))
        self.assertEqual(trade_loader.call_args.kwargs["end_time_ms"], 100_000)

    def test_database_publication_replaces_one_row_and_freshness_is_explicit(self):
        summary = ready_observation()
        db = RecordingDb()
        published = publish_order_book_observations(db, {"BTCUSDT": summary})

        self.assertEqual(published, 1)
        query, params = db.calls[0]
        self.assertIn("ON CONFLICT (symbol) DO UPDATE", query)
        self.assertNotIn("INSERT INTO price_ticks", query)
        self.assertEqual(params[0], "BTCUSDT")
        captured = datetime.fromtimestamp(summary["captured_at_ms"] / 1000, tz=timezone.utc)
        row = {
            "symbol": "BTCUSDT",
            "summary_json": summary,
            "source": summary["source"],
            "publisher": "operation_worker",
            "captured_at": captured,
        }
        fresh = summarize_order_book_observation(
            row,
            now=captured + timedelta(seconds=20),
        )
        stale = summarize_order_book_observation(
            row,
            now=captured + timedelta(seconds=50),
        )
        self.assertTrue(fresh["available"])
        self.assertFalse(stale["available"])
        self.assertEqual(stale["state_reason"], "worker_order_book_observation_stale")


if __name__ == "__main__":
    unittest.main()
