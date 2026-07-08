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
    build_learning_conclusion,
    build_structured_learning_evaluation,
    group_pending_zone_cases,
    group_signal_effectiveness,
    group_signal_pairs,
    group_underweighted_risk_cases,
    learning_summary_needs_refresh,
    pending_zone_case_from_evaluation,
    summarize_pending_zone_cases,
    summarize_underweighted_risk_cases,
    underweighted_risk_case_from_evaluation,
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

    def test_risk_calibration_penalizes_extreme_fibonacci_sentiment_cluster(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_wide",
            entry=61649.9,
            margin=400,
            leverage=10,
            stop_loss=62150,
            take_profit=60950,
        )
        context = build_risk_calibration_context(
            proposal=proposal,
            tp_probability=0.6109,
            sl_probability=0.3291,
            rr_ratio=1.39952,
            risk_distance=0.8114,
            reward_distance=1.1352,
            technical_rating={"score": 80},
            timeframes={
                "15m": {"ema_stack": "bearish", "price_vs_ema_21_pct": -0.54},
                "1h": {"ema_stack": "bearish", "price_vs_ema_21_pct": -1.38},
            },
            ticker_24h={"price_change_pct": -2.96},
            zone_analysis={"available": False},
            zone_probability_context={"probability_adjustment": 0, "risk_score_addition": 0},
            fibonacci_context={"bias": "desfavorable", "score": 24, "entry_zone": "retroceso_extremo"},
            sentiment_penalty=0.015,
            cvd_bias=-0.0099,
            rsi_signal=22.5,
        )

        self.assertIn("extreme_fib_extreme_sentiment_cluster", context["flags"])
        self.assertIn("extreme_fib_sentiment_cvd_contra", context["flags"])
        self.assertIn("rsi_extreme_multi_risk_cluster", context["flags"])
        self.assertIn("rsi_extreme_with_fib_sentiment_cluster", context["flags"])
        self.assertEqual(context["grade_cap"], "C")
        self.assertFalse(context["force_observar"])
        self.assertLessEqual(context["tp_probability_adjustment"], -0.07)
        self.assertGreaterEqual(context["risk_score_addition"], 0.15)
        self.assertGreaterEqual(context["confidence_score_penalty"], 22)

    def test_risk_calibration_does_not_penalize_non_extreme_fibonacci_sentiment_alone(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_wide",
            entry=61649.9,
            margin=400,
            leverage=10,
            stop_loss=62150,
            take_profit=60950,
        )
        context = build_risk_calibration_context(
            proposal=proposal,
            tp_probability=0.6109,
            sl_probability=0.3291,
            rr_ratio=1.39952,
            risk_distance=0.8114,
            reward_distance=1.1352,
            technical_rating={"score": 80},
            timeframes={
                "15m": {"ema_stack": "bearish", "price_vs_ema_21_pct": -0.54},
                "1h": {"ema_stack": "bearish", "price_vs_ema_21_pct": -1.38},
            },
            ticker_24h={"price_change_pct": -2.96},
            zone_analysis={"available": False},
            zone_probability_context={"probability_adjustment": 0, "risk_score_addition": 0},
            fibonacci_context={"bias": "desfavorable", "score": 38, "entry_zone": "retroceso_profundo"},
            sentiment_penalty=0.015,
            cvd_bias=0,
            rsi_signal=22.5,
        )

        self.assertNotIn("extreme_fib_extreme_sentiment_cluster", context["flags"])
        self.assertNotIn("extreme_fib_sentiment_cvd_contra", context["flags"])
        self.assertNotIn("rsi_extreme_multi_risk_cluster", context["flags"])

    def test_risk_calibration_does_not_penalize_isolated_extreme_rsi(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_wide",
            entry=61649.9,
            margin=400,
            leverage=10,
            stop_loss=62150,
            take_profit=60950,
        )
        context = build_risk_calibration_context(
            proposal=proposal,
            tp_probability=0.6109,
            sl_probability=0.3291,
            rr_ratio=1.39952,
            risk_distance=0.8114,
            reward_distance=1.1352,
            technical_rating={"score": 80},
            timeframes={
                "15m": {"ema_stack": "bearish", "price_vs_ema_21_pct": -0.54},
                "1h": {"ema_stack": "bearish", "price_vs_ema_21_pct": -1.38},
            },
            ticker_24h={"price_change_pct": -2.96},
            zone_analysis={"available": False},
            zone_probability_context={"probability_adjustment": 0, "risk_score_addition": 0},
            fibonacci_context={"bias": "neutral", "score": 50, "entry_zone": "sin_zona"},
            sentiment_penalty=0,
            cvd_bias=0,
            rsi_signal=22.5,
        )

        self.assertNotIn("rsi_extreme_multi_risk_cluster", context["flags"])

    def test_risk_calibration_penalizes_rsi_with_sentiment_and_cvd_cluster(self):
        proposal = TradeProposal(
            symbol="BTCUSDT",
            side="short",
            time_horizon="intraday_wide",
            entry=61649.9,
            margin=400,
            leverage=10,
            stop_loss=62150,
            take_profit=60950,
        )
        context = build_risk_calibration_context(
            proposal=proposal,
            tp_probability=0.6109,
            sl_probability=0.3291,
            rr_ratio=1.39952,
            risk_distance=0.8114,
            reward_distance=1.1352,
            technical_rating={"score": 80},
            timeframes={
                "15m": {"ema_stack": "bearish", "price_vs_ema_21_pct": -0.54},
                "1h": {"ema_stack": "bearish", "price_vs_ema_21_pct": -1.38},
            },
            ticker_24h={"price_change_pct": -2.96},
            zone_analysis={"available": False},
            zone_probability_context={"probability_adjustment": 0, "risk_score_addition": 0},
            fibonacci_context={"bias": "desfavorable", "score": 38, "entry_zone": "retroceso_profundo"},
            sentiment_penalty=0.015,
            cvd_bias=-0.0099,
            rsi_signal=22.5,
        )

        self.assertIn("rsi_extreme_multi_risk_cluster", context["flags"])
        self.assertNotIn("rsi_extreme_with_fib_sentiment_cluster", context["flags"])

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
    def test_structured_learning_marks_overconfident_warned_failure_as_underweighted_risk(self):
        operation = self._overconfident_market_failure_operation()
        evaluation = build_structured_learning_evaluation(
            operation,
            [
                {"price": 61649.9, "captured_at": "2026-07-08T15:21:38+00:00"},
                {"price": 62150.0, "captured_at": "2026-07-08T17:20:00+00:00"},
            ],
        )
        structured = json.loads(evaluation["structured_json"])
        signal = structured["learning_signal"]
        diagnostics = structured["signal_diagnostics"]

        self.assertEqual(evaluation["analysis_verdict"], "analysis_warned_but_underweighted_risk")
        self.assertEqual(signal["category"], "investigate_underweighted_detected_risk")
        self.assertEqual(signal["decision_quality"], "risk_underweighted")
        self.assertEqual(diagnostics["warning_detection_quality"], "detected_multiple_material_warnings")
        self.assertIn(
            "confidence_quality_mismatch",
            {item["code"] for item in diagnostics["internal_inconsistencies"]},
        )
        self.assertIn(
            "extreme_fibonacci_risk",
            {item["code"] for item in diagnostics["opposing_signals"]},
        )

    def test_learning_conclusion_names_underweighted_risk_instead_of_simple_warning(self):
        conclusion = build_learning_conclusion(self._overconfident_market_failure_operation())

        self.assertEqual(conclusion["outcome"], "plan_failure")
        self.assertIn("riesgo detectado pero subponderado", conclusion["summary"])
        self.assertIn("Lectura previa", conclusion["summary"])
        self.assertIn("Error probable", conclusion["summary"])
        self.assertIn("Senales que apoyaban", conclusion["summary"])
        self.assertIn("Senales que contradecian", conclusion["summary"])
        self.assertIn("Incoherencias internas", conclusion["summary"])
        self.assertIn("RSI", conclusion["summary"])
        self.assertIn("CVD", conclusion["summary"])
        self.assertNotIn("este caso debe reforzar esas senales de riesgo", conclusion["summary"])

    def test_old_learning_summary_marker_is_refreshed(self):
        old_summary = (
            "Aprendizaje: el plan de BTC/USDT en SHORT fallo y alcanzo STOP LOSS. "
            "El analisis previo ya contenia advertencias (Fibonacci desfavorable); "
            "este caso debe reforzar esas senales de riesgo."
        )
        new_summary = build_learning_conclusion(self._overconfident_market_failure_operation())["summary"]

        self.assertTrue(learning_summary_needs_refresh(old_summary))
        self.assertFalse(learning_summary_needs_refresh(new_summary))

    def test_underweighted_risk_audit_case_and_summary(self):
        risky_evaluation = build_structured_learning_evaluation(
            self._overconfident_market_failure_operation(),
            [{"price": 62150.0, "captured_at": "2026-07-08T17:20:00+00:00"}],
        )
        supported_evaluation = build_structured_learning_evaluation(
            self._operation_with_snapshot(
                plan_result="take_profit",
                zone_delta=0.025,
                sweep_risk="medio",
                reaction_bias="rebote_probable",
            ),
            [{"price": 66500, "captured_at": "2026-06-15T11:00:00+00:00"}],
        )
        cases = [
            underweighted_risk_case_from_evaluation(risky_evaluation, engine_version="rules-v0.10-risk-gated-calibration"),
            underweighted_risk_case_from_evaluation(supported_evaluation, engine_version="rules-v0.10-risk-gated-calibration"),
        ]
        summary = summarize_underweighted_risk_cases(cases)
        decision_groups = group_underweighted_risk_cases(cases, "decision_quality")

        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["risk_underweighted_cases"], 1)
        self.assertEqual(summary["risk_underweighted_failures"], 1)
        self.assertEqual(summary["risk_underweighted_failure_rate"], 1.0)
        self.assertEqual(
            {group["name"]: group["cases"] for group in decision_groups},
            {"risk_underweighted": 1, "decision_consistent_with_detected_risk": 1},
        )

    def test_signal_effectiveness_separates_candidate_filters_from_winner_signals(self):
        cases = [
            {
                "operation_id": 1,
                "success": False,
                "failure": True,
                "final_pnl": -20,
                "decision_quality": "risk_underweighted",
                "opposing_signal_codes": ["cvd_against_plan", "extreme_fibonacci_risk"],
                "internal_inconsistency_codes": ["confidence_quality_mismatch"],
            },
            {
                "operation_id": 2,
                "success": False,
                "failure": True,
                "final_pnl": -30,
                "decision_quality": "risk_underweighted",
                "opposing_signal_codes": ["cvd_against_plan"],
                "internal_inconsistency_codes": ["confidence_quality_mismatch"],
            },
            {
                "operation_id": 3,
                "success": False,
                "failure": True,
                "final_pnl": -10,
                "decision_quality": "decision_consistent_with_detected_risk",
                "opposing_signal_codes": ["cvd_against_plan"],
                "internal_inconsistency_codes": [],
            },
            {
                "operation_id": 4,
                "success": True,
                "failure": False,
                "final_pnl": 80,
                "decision_quality": "risk_underweighted",
                "opposing_signal_codes": ["extreme_fibonacci_risk"],
                "internal_inconsistency_codes": ["confidence_quality_mismatch"],
            },
        ]
        opposing = {item["name"]: item for item in group_signal_effectiveness(cases, "opposing_signal_codes")}
        pairs = {item["name"]: item for item in group_signal_pairs(cases, ["opposing_signal_codes", "internal_inconsistency_codes"])}

        self.assertEqual(opposing["cvd_against_plan"]["learning_read"], "candidate_risk_filter")
        self.assertEqual(opposing["cvd_against_plan"]["failures"], 3)
        self.assertEqual(opposing["extreme_fibonacci_risk"]["learning_read"], "sample_too_small")
        self.assertIn("confidence_quality_mismatch + cvd_against_plan", pairs)
        self.assertEqual(
            pairs["confidence_quality_mismatch + cvd_against_plan"]["learning_read"],
            "sample_too_small",
        )

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

    def _overconfident_market_failure_operation(self) -> dict:
        snapshot = self._snapshot(zone_delta=0)
        snapshot.update(
            {
                "technical_rating": {
                    "label": "favorable",
                    "score": 80,
                    "barrier_penalty": 0.025,
                    "primary_rsi": 25.59,
                },
                "market_regime": {"name": "tendencia_bajista"},
                "layered_scores": {
                    "direction_score": 61,
                    "operation_quality_score": 52,
                    "execution_risk_score": 38,
                    "confidence_score": 82,
                    "expected_value_score": 51,
                },
                "fibonacci_context": {
                    "available": True,
                    "bias": "desfavorable",
                    "score": 24,
                    "entry_zone": "retroceso_extremo",
                    "target_zone": "estructura_rota",
                    "stop_zone": "retroceso_profundo",
                    "probability_adjustment": -0.02,
                },
                "score_components": {
                    "rsi_timeframe": "1h",
                    "cvd_bias": -0.0099,
                    "taker_flow_bias": -0.006,
                    "sentiment_penalty": 0.015,
                    "overextension_penalty": 0.025,
                },
                "timeframes": {"1h": {"rsi_14": 22.5}},
                "expected_value": {"expected_value_usdt": 12.82},
                "risk_reward_ratio": 1.39952,
                "risk_margin_pct": None,
                "reward_margin_pct": None,
                "entry_order_context": {
                    "entry_type": "market",
                    "trigger_condition": None,
                    "entry_order_type": None,
                    "requested_entry": 61649.9,
                },
                "zone_analysis": {"available": False, "entry_zone_type": "market_entry"},
                "zone_probability_context": {
                    "probability_adjustment": 0,
                    "range_probability_adjustment": 0,
                    "risk_score_addition": 0,
                    "summary": "sin ajuste: entrada a mercado o zona no disponible",
                },
            }
        )
        return {
            "id": 204,
            "user_id": 3,
            "recommendation_id": 714,
            "symbol": "BTCUSDT",
            "side": "short",
            "time_horizon": "intraday_wide",
            "mode": "contest",
            "close_reason": "stop_loss",
            "final_pnl": -32.4477,
            "entry": 61649.9,
            "margin": 400,
            "leverage": 10,
            "stop_loss": 62150,
            "take_profit": 60950,
            "started_at": "2026-07-08T15:21:38+00:00",
            "closed_at": "2026-07-08T17:20:00+00:00",
            "recommendation_snapshot_json": json.dumps(snapshot),
            "recommendation_tp_probability": 0.6109,
            "recommendation_sl_probability": 0.3291,
            "recommendation_range_probability": 0.06,
            "recommendation_setup_grade": "B",
            "recommendation_confidence": "alta",
            "recommendation_training_decision": "simular",
            "recommendation_risk_level": "medio",
        }

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
