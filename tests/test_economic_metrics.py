import unittest
from datetime import datetime, timezone

from app import save_learning_economic_audit
from backfill_economic_metrics import apply_metrics_to_structured
from economic_metrics import (
    economic_plan_outcome,
    maximum_cumulative_drawdown,
    normalize_operation_economics,
    signal_pattern_read,
    summarize_economic_cases,
)


def operation(side: str = "long", **overrides) -> dict:
    payload = {
        "id": 1,
        "side": side,
        "entry": 100,
        "margin": 100,
        "leverage": 10,
        "stop_loss": 95 if side == "long" else 105,
        "take_profit": 110 if side == "long" else 90,
        "close_reason": "take_profit",
        "final_pnl": 100,
        "closed_at": "2026-01-01T00:00:00+00:00",
        "plan_result": "plan_success",
    }
    payload.update(overrides)
    return payload


class EconomicMetricsTests(unittest.TestCase):
    def test_long_metrics_use_initial_stop_risk(self):
        metrics = normalize_operation_economics(operation(), normalized_at="now")

        self.assertEqual(metrics["status"], "included")
        self.assertEqual(metrics["notional_amount"], 1000)
        self.assertEqual(metrics["initial_risk_pct"], 5)
        self.assertEqual(metrics["initial_risk_amount"], 50)
        self.assertEqual(metrics["unleveraged_return_pct"], 10)
        self.assertEqual(metrics["margin_return_pct"], 100)
        self.assertEqual(metrics["r_multiple"], 2)

    def test_short_metrics_use_adverse_stop_direction(self):
        metrics = normalize_operation_economics(
            operation(side="short", final_pnl=-50, plan_result="plan_failure"),
            normalized_at="now",
        )

        self.assertEqual(metrics["initial_risk_amount"], 50)
        self.assertEqual(metrics["r_multiple"], -1)
        self.assertEqual(metrics["economic_plan_outcome"], "stop_loss")

    def test_r_multiple_is_independent_of_margin_and_leverage_when_pnl_scales(self):
        first = normalize_operation_economics(
            operation(margin=100, leverage=10, final_pnl=100),
            normalized_at="now",
        )
        second = normalize_operation_economics(
            operation(margin=20, leverage=2, final_pnl=4),
            normalized_at="now",
        )

        self.assertEqual(first["r_multiple"], second["r_multiple"])
        self.assertEqual(
            first["unleveraged_return_pct"],
            second["unleveraged_return_pct"],
        )

    def test_invalid_initial_risk_is_excluded_with_reason(self):
        metrics = normalize_operation_economics(
            operation(stop_loss=105),
            normalized_at="now",
        )

        self.assertEqual(metrics["status"], "excluded")
        self.assertEqual(metrics["exclusion_reason"], "stop_not_adverse_to_long")
        self.assertIsNone(metrics["r_multiple"])

    def test_plan_outcome_uses_tp_sl_taxonomy(self):
        self.assertEqual(economic_plan_outcome("plan_would_succeed"), "take_profit")
        self.assertEqual(economic_plan_outcome("plan_failure"), "stop_loss")
        self.assertEqual(economic_plan_outcome("ambiguous_same_candle"), "ambiguous")
        self.assertEqual(
            economic_plan_outcome("contest_expiry_mark_to_market"),
            "mark_to_market",
        )

    def test_cumulative_drawdown_is_measured_on_r_curve(self):
        self.assertEqual(maximum_cumulative_drawdown([1, -0.5, -1, 2, -0.25]), 1.5)

    def test_summary_prioritizes_normalized_metrics_and_keeps_pnl_secondary(self):
        cases = []
        for index, r_value in enumerate([1.0, -0.5, -1.0], start=1):
            cases.append(
                {
                    "operation_id": index,
                    "closed_at": f"2026-01-0{index}T00:00:00+00:00",
                    "economic_normalization_status": "included",
                    "economic_exclusion_reason": None,
                    "r_multiple": r_value,
                    "unleveraged_return_pct": r_value * 2,
                    "margin_return_pct": r_value * 10,
                    "economic_plan_outcome": "take_profit" if r_value > 0 else "stop_loss",
                    "final_pnl": r_value * 50,
                }
            )

        summary = summarize_economic_cases(cases)

        self.assertEqual(summary["economic_metric_role"], "primary")
        self.assertEqual(summary["pnl_metric_role"], "secondary")
        self.assertEqual(summary["normalized_cases"], 3)
        self.assertEqual(summary["avg_r_multiple"], round(-0.5 / 3, 8))
        self.assertEqual(summary["max_cumulative_r_drawdown"], 1.5)
        self.assertEqual(summary["total_pnl"], -25)

    def test_economic_pnl_overrides_stale_legacy_pnl_only_in_summary(self):
        summary = summarize_economic_cases(
            [
                {
                    "operation_id": 81,
                    "economic_normalization_status": "included",
                    "r_multiple": 4,
                    "economic_final_pnl": 147.5291,
                    "final_pnl": -36.5448,
                }
            ]
        )

        self.assertEqual(summary["total_pnl"], 147.5291)

    def test_structured_backfill_keeps_economics_out_of_pre_trade_features(self):
        structured = {
            "pre_trade_features": {"score": 60},
            "post_trade_outcomes": {"final_pnl": 10},
        }
        metrics = normalize_operation_economics(operation(), normalized_at="now")

        updated = apply_metrics_to_structured(structured, metrics)

        self.assertNotIn("economic_metrics", updated["pre_trade_features"])
        self.assertEqual(updated["economic_metrics"], metrics)
        self.assertEqual(updated["post_trade_outcomes"]["economic_metrics"], metrics)

    def test_audit_serializes_existing_database_timestamps(self):
        class Cursor:
            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Db:
            def __init__(self):
                self.params = None

            def execute(self, query, params=()):
                if "SELECT id FROM learning_evaluations" in query:
                    return Cursor({"id": 9})
                self.params = params
                return Cursor()

        db = Db()
        metrics = normalize_operation_economics(operation(), normalized_at="now")

        save_learning_economic_audit(
            db,
            1,
            metrics,
            before_payload={
                "economic_normalized_at": datetime(2026, 7, 24, tzinfo=timezone.utc)
            },
            after_payload={"r_multiple": 2},
        )

        self.assertIn("2026-07-24", db.params[5])

    def test_signal_pattern_does_not_require_absolute_pnl(self):
        self.assertEqual(signal_pattern_read(1, 3, -0.4), "observed_risk_pattern")
        self.assertEqual(signal_pattern_read(3, 1, 0.2), "observed_winner_pattern")
        self.assertEqual(signal_pattern_read(1, 3, None), "observed_risk_pattern")


if __name__ == "__main__":
    unittest.main()
