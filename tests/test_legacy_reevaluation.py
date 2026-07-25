from __future__ import annotations

import json
import unittest
from pathlib import Path

from legacy_reevaluation import (
    LEGACY_REVIEW_SCHEMA_VERSION,
    build_legacy_reevaluation,
    contains_retrospective_key,
)
from versioning import LEGACY_REEVALUATION_VERSION


ROOT = Path(__file__).resolve().parents[1]
REVIEWED_AT = "2026-07-25T18:00:00+00:00"


def legacy_case(
    *,
    reconstructed_result: str = "plan_success",
    legacy_result: str = "plan_success",
    snapshot_overrides: dict | None = None,
) -> dict:
    snapshot = {
        "time_horizon": "intraday_wide",
        "technical_rating": {"label": "bullish", "score": 64},
        "market_regime": {"name": "trend"},
        "layered_scores": {"direction_score": 61, "confidence_score": 58},
        "risk_reward_ratio": 2.0,
        "entry_order_context": {
            "entry_type": "market",
            "trigger_condition": "immediate",
            "entry_order_type": "market",
            "requested_entry": 100.0,
        },
    }
    snapshot.update(snapshot_overrides or {})
    evaluation = {
        "id": 7,
        "operation_id": 11,
        "plan_result": legacy_result,
        "analysis_verdict": "analysis_success",
        "primary_lesson": "legacy lesson",
        "failure_type": None,
        "user_decision_quality": "followed_plan",
        "setup_grade": "B",
        "risk_level": "medium",
        "confidence": "medium",
        "training_decision": "observe",
        "tp_probability": 0.57,
        "sl_probability": 0.33,
        "range_probability": 0.10,
        "technical_label": "bullish",
        "technical_score": 64,
        "market_regime": "trend",
        "direction_score": 61,
        "confidence_score": 58,
        "risk_reward_ratio": 2.0,
        "risk_margin_pct": 1.0,
        "reward_margin_pct": 2.0,
        "leverage_bucket": "medium",
        "app_version": None,
        "scoring_version": None,
        "learning_evaluator_version": None,
        "learning_schema_version": None,
        "data_source_version": None,
        "data_contract_version": None,
        "evidence_version": "evidence-v0.1-binance-usdm-1m",
        "evidence_source": "binance_usdm_1m_klines",
        "evidence_quality": "complete",
        "evidence_path_resolution": "resolved",
        "evidence_coverage_ratio": 1.0,
        "first_plan_touch": "take_profit",
        "first_plan_touch_at": "2026-06-01T11:00:00+00:00",
        "reconstructed_plan_result": reconstructed_result,
        "plan_result_consistency": (
            "consistent"
            if reconstructed_result == legacy_result
            else "ambiguous"
            if reconstructed_result == "ambiguous_same_candle"
            else "mismatch"
        ),
        "max_favorable_pct": 2.1,
        "max_adverse_pct": 0.4,
        "max_favorable_pnl": 21.0,
        "max_adverse_pnl": 4.0,
        "economic_normalization_version": "economics-v0.1-risk-normalized",
        "economic_normalization_status": "included",
        "economic_exclusion_reason": None,
        "closure_type": "take_profit",
        "initial_risk_amount": 10.0,
        "unleveraged_return_pct": 2.0,
        "margin_return_pct": 20.0,
        "r_multiple": 2.0,
        "economic_plan_outcome": "tp",
        "economic_final_pnl": 20.0,
        "structured_json": json.dumps(
            {
                "operation_id": 11,
                "plan_result": legacy_result,
                "analysis_verdict": "analysis_success",
            }
        ),
        "created_at": "2026-06-01T10:00:00+00:00",
        "updated_at": "2026-07-24T10:00:00+00:00",
    }
    operation = {
        "id": 11,
        "user_id": 3,
        "symbol": "BTCUSDT",
        "side": "long",
        "entry": 100.0,
        "margin": 100.0,
        "leverage": 10.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "close_reason": "take_profit",
        "closed_at": "2026-06-01T11:00:00+00:00",
    }
    recommendation = {
        "id": 5,
        "engine_version": "rules-v0.9-pending-zone-adjusted",
        "app_version": None,
        "scoring_version": None,
        "data_source_version": None,
        "tp_probability": 0.57,
        "sl_probability": 0.33,
        "range_probability": 0.10,
        "setup_grade": "B",
        "risk_level": "medium",
        "confidence": "medium",
        "training_decision": "observe",
        "snapshot_json": json.dumps(snapshot),
        "created_at": "2026-06-01T09:59:00+00:00",
    }
    return {
        "evaluation_record": evaluation,
        "operation_record": operation,
        "recommendation_record": recommendation,
        "evidence_record": {
            "quality": "complete",
            "reconstructed_plan_result": reconstructed_result,
        },
        "economic_record": {
            "status": "included",
            "r_multiple": 2.0,
        },
    }


class LegacyReevaluationTests(unittest.TestCase):
    def test_contract_separates_pre_post_and_diagnostics_without_leakage(self):
        review = build_legacy_reevaluation(
            legacy_case(),
            reviewed_at=REVIEWED_AT,
        )
        contract = review["reevaluated_contract"]
        self.assertEqual(contract["version"], LEGACY_REVIEW_SCHEMA_VERSION)
        self.assertEqual(
            set(contract),
            {
                "version",
                "pre_trade_features",
                "post_trade_outcomes",
                "diagnostic_labels",
            },
        )
        self.assertEqual(
            contains_retrospective_key(contract["pre_trade_features"]),
            [],
        )

    def test_legacy_scores_are_not_called_calibrated_probabilities(self):
        review = build_legacy_reevaluation(
            legacy_case(),
            reviewed_at=REVIEWED_AT,
        )
        context = review["reevaluated_contract"]["pre_trade_features"][
            "analysis_context"
        ]
        self.assertEqual(context["tp_score_legacy"], 0.57)
        self.assertEqual(
            context["probability_semantics"],
            "uncalibrated_legacy_heuristic",
        )

    def test_missing_horizon_is_not_replaced_by_operation_default(self):
        case = legacy_case(snapshot_overrides={"time_horizon": None})
        case["operation_record"]["time_horizon"] = "intraday_short"
        review = build_legacy_reevaluation(case, reviewed_at=REVIEWED_AT)
        plan = review["reevaluated_contract"]["pre_trade_features"]["trade_plan"]
        self.assertEqual(plan["time_horizon"]["status"], "not_available")
        self.assertEqual(
            plan["horizon_seconds"]["reason"],
            "concrete_duration_not_recorded_pre_trade",
        )

    def test_legacy_and_reconstructed_results_are_both_preserved(self):
        review = build_legacy_reevaluation(
            legacy_case(
                reconstructed_result="plan_unresolved",
                legacy_result="plan_failure",
            ),
            reviewed_at=REVIEWED_AT,
        )
        post = review["reevaluated_contract"]["post_trade_outcomes"]
        self.assertEqual(post["legacy_plan_result"], "plan_failure")
        self.assertEqual(post["reconstructed_plan_result"], "plan_unresolved")
        self.assertEqual(post["plan_result_consistency"], "mismatch")
        self.assertEqual(post["modern_outcome"]["class"], "expiry_unresolved")

    def test_ambiguous_first_touch_is_excluded(self):
        review = build_legacy_reevaluation(
            legacy_case(
                reconstructed_result="ambiguous_same_candle",
                legacy_result="plan_failure",
            ),
            reviewed_at=REVIEWED_AT,
        )
        self.assertEqual(review["review_status"], "reviewed_excluded")
        self.assertEqual(review["outcome_class"], "ambiguous")
        self.assertEqual(review["outcome_status"], "excluded")

    def test_legacy_cases_are_descriptive_not_challenger_training_data(self):
        review = build_legacy_reevaluation(
            legacy_case(),
            reviewed_at=REVIEWED_AT,
        )
        self.assertFalse(review["predictive_eligibility"]["eligible"])
        self.assertEqual(
            review["predictive_eligibility"]["reason"],
            "concrete_pre_trade_horizon_duration_not_recorded",
        )

    def test_source_hash_is_deterministic_and_independent_of_review_time(self):
        first = build_legacy_reevaluation(
            legacy_case(),
            reviewed_at=REVIEWED_AT,
        )
        second = build_legacy_reevaluation(
            legacy_case(),
            reviewed_at="2026-07-26T18:00:00+00:00",
        )
        self.assertEqual(
            first["source_bundle_sha256"],
            second["source_bundle_sha256"],
        )
        self.assertEqual(
            first["reevaluation_version"],
            LEGACY_REEVALUATION_VERSION,
        )

    def test_schema_enforces_private_append_only_table(self):
        schema = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS learning_legacy_reevaluations",
            schema,
        )
        self.assertIn(
            "UNIQUE(operation_id, reevaluation_version)",
            schema,
        )
        self.assertIn(
            "ALTER TABLE public.learning_legacy_reevaluations ENABLE ROW LEVEL SECURITY",
            schema,
        )
        self.assertIn(
            "REVOKE ALL PRIVILEGES ON TABLE public.learning_legacy_reevaluations FROM anon, authenticated",
            schema,
        )
        self.assertIn("learning_legacy_reevaluations_no_update", schema)
        self.assertIn("learning_legacy_reevaluations_no_delete", schema)

    def test_backfill_uses_prechecked_idempotency_compatible_with_rules(self):
        script = (ROOT / "backfill_legacy_reevaluations.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("existing_operation_ids", script)
        self.assertNotIn("ON CONFLICT (operation_id, reevaluation_version)", script)


if __name__ == "__main__":
    unittest.main()
