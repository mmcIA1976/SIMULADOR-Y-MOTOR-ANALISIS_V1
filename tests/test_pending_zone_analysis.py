import json
import unittest

from analysis_engine import (
    TradeProposal,
    build_fibonacci_trade_context,
    build_risk_calibration_context,
    build_zone_analysis,
    build_zone_probability_context,
)
from app import (
    build_structured_learning_evaluation,
    group_pending_zone_cases,
    pending_zone_case_from_evaluation,
    summarize_pending_zone_cases,
)


class PendingZoneAnalysisTests(unittest.TestCase):
    def test_favorable_limit_pullback_gets_small_positive_adjustment(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_wide",
            entry=67000,
            margin=100,
            leverage=2,
            stop_loss=68000,
            take_profit=66500,
            entry_type="pending",
            trigger_condition="price_gte",
            entry_order_type="limit_pullback",
        )
        zone = build_zone_analysis(
            proposal=proposal,
            current_price=66600,
            levels_for_horizon={"nearest_support": 66450, "nearest_resistance": 67020},
            fibonacci_context={"bias": "favorable"},
            market_regime={"name": "tendencia_bajista"},
            technical_rating={"score": 66},
            atr_pct=0.42,
            recent_range_pct=1.15,
            order_book_imbalance=0.05,
            taker_buy_sell_ratio=0.82,
            cvd_ratio=-0.16,
            open_interest_change_pct=1.4,
            volume_ratio=1.3,
        )
        context = build_zone_probability_context(zone)

        self.assertEqual(zone["entry_order_type"], "limit_pullback")
        self.assertEqual(zone["entry_zone_type"], "resistance_pullback_zone")
        self.assertGreaterEqual(zone["zone_confluence_score"], 65)
        self.assertEqual(context["probability_adjustment"], 0.025)
        self.assertEqual(context["range_probability_adjustment"], 0)
        self.assertEqual(context["risk_score_addition"], 0)

    def test_bad_pending_zone_penalizes_probability_and_adds_risk(self):
        zone = {
            "available": True,
            "entry_order_type": "limit_pullback",
            "reaction_bias": "zona_de_barrida",
            "zone_confluence_score": 36,
            "activation_probability": 0.74,
            "target_path_quality": 35,
            "invalidation_quality": 34,
            "liquidity_sweep_risk": "alto",
        }
        context = build_zone_probability_context(zone)

        self.assertEqual(context["probability_adjustment"], -0.035)
        self.assertEqual(context["risk_score_addition"], 0.06)
        self.assertIn("riesgo de barrida", context["summary"])

    def test_low_activation_probability_increases_range_not_direction_penalty(self):
        zone = {
            "available": True,
            "entry_order_type": "stop_breakout",
            "reaction_bias": "ruptura_incierta",
            "zone_confluence_score": 55,
            "activation_probability": 0.22,
            "target_path_quality": 58,
            "invalidation_quality": 55,
            "liquidity_sweep_risk": "medio",
        }
        context = build_zone_probability_context(zone)

        self.assertEqual(context["probability_adjustment"], 0)
        self.assertEqual(context["range_probability_adjustment"], 0.04)
        self.assertEqual(context["risk_score_addition"], 0)

    def test_risk_calibration_forces_observe_on_historically_weak_cluster(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="long",
            time_horizon="intraday_short",
            entry=100,
            margin=100,
            leverage=3,
            stop_loss=99.9,
            take_profit=104,
            entry_type="pending",
            trigger_condition="price_lte",
            entry_order_type="stop_breakdown",
        )
        context = build_risk_calibration_context(
            proposal=proposal,
            tp_probability=0.39,
            sl_probability=0.55,
            rr_ratio=40,
            risk_distance=0.1,
            reward_distance=4.0,
            technical_rating={"score": 34},
            timeframes={
                "15m": {"ema_stack": "bearish", "price_vs_ema_21_pct": -0.2},
                "1h": {"ema_stack": "bearish", "price_vs_ema_21_pct": -0.3},
            },
            ticker_24h={"price_change_pct": -1.2},
            zone_analysis={
                "available": True,
                "entry_order_type": "stop_breakdown",
                "reaction_bias": "falsa_ruptura_riesgo",
                "liquidity_sweep_risk": "alto",
            },
            zone_probability_context={"probability_adjustment": -0.035},
            fibonacci_context={"bias": "favorable"},
        )

        self.assertTrue(context["force_observar"])
        self.assertEqual(context["grade_cap"], "D")
        self.assertLess(context["tp_probability_adjustment"], -0.1)
        self.assertGreaterEqual(context["risk_score_addition"], 0.2)
        self.assertIn("sl_probability_gte_55", context["flags"])
        self.assertIn("pending_stop_breakdown", context["flags"])

    def test_favorable_fibonacci_no_longer_adds_probability_bonus(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="long",
            time_horizon="intraday_wide",
            entry=110,
            margin=100,
            leverage=2,
            stop_loss=104,
            take_profit=125,
        )
        context = build_fibonacci_trade_context(
            proposal=proposal,
            fibonacci_data={
                "available": True,
                "swing": {"direction": "up", "start_price": 100, "end_price": 120},
                "retracements": {"0.5": 110, "0.618": 107.64},
                "extensions": {"1.272": 125.44},
            },
            levels_for_horizon={"nearest_support": 110.2},
            atr_pct=0.4,
        )

        self.assertEqual(context["bias"], "favorable")
        self.assertEqual(context["probability_adjustment"], 0)


class PendingZoneLearningTests(unittest.TestCase):
    def test_structured_learning_classifies_warned_zone_failure(self):
        operation = self._operation_with_snapshot(
            plan_result="stop_loss",
            zone_delta=-0.035,
            sweep_risk="alto",
            reaction_bias="zona_de_barrida",
        )
        evaluation = build_structured_learning_evaluation(
            operation,
            [{"price": 68000, "captured_at": "2026-06-15T11:00:00+00:00"}],
        )
        structured = json.loads(evaluation["structured_json"])

        self.assertEqual(evaluation["failure_type"], "pending_zone_liquidity_sweep")
        self.assertEqual(
            structured["analysis_context"]["zone_learning"]["category"],
            "reinforce_warned_pending_zone_risk",
        )
        self.assertTrue(structured["pending_entry_context"]["activated"])

    def test_pending_zone_audit_groups_cases_by_adjustment_bucket(self):
        cases = [
            pending_zone_case_from_evaluation(
                self._evaluation_row(1, "plan_success", 12.5, 0.025, "reinforce_favorable_pending_zone")
            ),
            pending_zone_case_from_evaluation(
                self._evaluation_row(2, "plan_failure", -9.0, -0.035, "reinforce_warned_pending_zone_risk")
            ),
        ]
        summary = summarize_pending_zone_cases(cases)
        groups = group_pending_zone_cases(cases, "probability_adjustment_bucket")

        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["success_rate"], 0.5)
        self.assertEqual(summary["activation_rate"], 1.0)
        self.assertEqual({group["name"] for group in groups}, {"positivo", "negativo"})

    def _operation_with_snapshot(self, plan_result: str, zone_delta: float, sweep_risk: str, reaction_bias: str) -> dict:
        close_reason = "stop_loss" if plan_result == "stop_loss" else "take_profit"
        return {
            "id": 999,
            "user_id": 1,
            "recommendation_id": 123,
            "symbol": "BTCUSDT",
            "side": "short",
            "time_horizon": "intraday_wide",
            "mode": "training",
            "close_reason": close_reason,
            "final_pnl": -10 if close_reason == "stop_loss" else 10,
            "entry": 67000,
            "margin": 100,
            "leverage": 2,
            "stop_loss": 68000,
            "take_profit": 66500,
            "started_at": "2026-06-15T10:00:00+00:00",
            "closed_at": "2026-06-15T11:00:00+00:00",
            "triggered_at": "2026-06-15T10:10:00+00:00",
            "trigger_price": 67000,
            "recommendation_snapshot_json": json.dumps(
                self._snapshot(zone_delta=zone_delta, sweep_risk=sweep_risk, reaction_bias=reaction_bias)
            ),
            "recommendation_tp_probability": 0.48,
            "recommendation_sl_probability": 0.42,
            "recommendation_range_probability": 0.10,
            "recommendation_setup_grade": "C",
            "recommendation_confidence": "media",
            "recommendation_training_decision": "simular con tamano prudente",
            "recommendation_risk_level": "medio-alto",
        }

    def _evaluation_row(self, operation_id: int, plan_result: str, pnl: float, zone_delta: float, category: str) -> dict:
        return {
            "operation_id": operation_id,
            "symbol": "BTCUSDT",
            "side": "short",
            "time_horizon": "intraday_wide",
            "final_pnl": pnl,
            "plan_result": plan_result,
            "analysis_verdict": "analysis_supported_success" if pnl > 0 else "analysis_warned_risk",
            "structured_json": json.dumps(
                {
                    "pending_entry_context": {"activated": True, "entry_order_type": "limit_pullback"},
                    "analysis_context": {
                        "zone": self._snapshot(zone_delta=zone_delta)["zone_analysis"],
                        "zone_learning": {"category": category},
                    },
                }
            ),
        }

    def _snapshot(
        self,
        zone_delta: float,
        sweep_risk: str = "medio",
        reaction_bias: str = "rebote_probable",
    ) -> dict:
        return {
            "technical_rating": {"label": "favorable", "score": 64},
            "market_regime": {"name": "tendencia_bajista"},
            "layered_scores": {"direction_score": 58, "confidence_score": 66},
            "fibonacci_context": {
                "bias": "neutral",
                "score": 52,
                "entry_zone": "retroceso_superficial",
                "target_zone": "sin_datos",
                "stop_zone": "sin_datos",
                "probability_adjustment": 0,
            },
            "risk_reward_ratio": 1.5,
            "risk_margin_pct": 4.0,
            "reward_margin_pct": 6.0,
            "entry_order_context": {
                "entry_type": "pending",
                "trigger_condition": "price_gte",
                "entry_order_type": "limit_pullback",
                "requested_entry": 67000,
            },
            "zone_analysis": {
                "available": True,
                "entry_order_type": "limit_pullback",
                "entry_zone_type": "resistance_pullback_zone",
                "reaction_bias": reaction_bias,
                "liquidity_sweep_risk": sweep_risk,
                "zone_confluence_score": 80 if zone_delta > 0 else 36,
                "activation_probability": 0.62,
                "invalidation_quality": 60 if zone_delta > 0 else 34,
                "target_path_quality": 70 if zone_delta > 0 else 35,
                "probability_adjustment": zone_delta,
                "risk_score_addition": 0 if zone_delta > 0 else 0.06,
                "range_probability_adjustment": 0,
            },
            "zone_probability_context": {
                "probability_adjustment": zone_delta,
                "range_probability_adjustment": 0,
                "risk_score_addition": 0 if zone_delta > 0 else 0.06,
                "summary": "zona test",
            },
        }


if __name__ == "__main__":
    unittest.main()
