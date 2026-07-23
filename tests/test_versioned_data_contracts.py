import json
import unittest
from unittest.mock import patch

from app import (
    TradePayload,
    analyze,
    build_structured_learning_evaluation,
    recommendation_version_contract,
    save_learning_evaluation,
    version_info,
)
from versioning import (
    APP_VERSION,
    DATA_CONTRACT_VERSION,
    ENGINE_VERSION,
    LEARNING_SCHEMA_VERSION,
    SCORING_VERSION,
    build_data_contract,
    current_version_contract,
    predictive_features_from_contract,
)


RETROSPECTIVE_KEYS = {
    "activated",
    "analysis_verdict",
    "close_reason",
    "diagnostic_labels",
    "excursion",
    "failure_type",
    "final_pnl",
    "learning_signal",
    "manual_counterfactual",
    "plan_result",
    "post_trade_outcomes",
    "primary_lesson",
    "signal_diagnostics",
    "trigger_price",
    "triggered_at",
    "user_decision_quality",
}


def nested_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(nested_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(item) for item in value))
    return set()


def legacy_operation() -> dict:
    snapshot = {
        "engine_version": ENGINE_VERSION,
        "technical_rating": {"label": "favorable", "score": 70},
        "market_regime": {"name": "tendencia_alcista"},
        "layered_scores": {"direction_score": 62, "confidence_score": 71},
        "fibonacci_context": {"bias": "neutral", "score": 50},
        "entry_order_context": {
            "entry_type": "market",
            "trigger_condition": None,
            "entry_order_type": None,
            "requested_entry": 100,
        },
        "zone_analysis": {"available": False},
        "zone_probability_context": {
            "probability_adjustment": 0,
            "range_probability_adjustment": 0,
            "risk_score_addition": 0,
        },
        "risk_reward_ratio": 2,
        "risk_margin_pct": 10,
        "reward_margin_pct": 20,
    }
    return {
        "id": 9001,
        "user_id": 7,
        "recommendation_id": 8001,
        "recommendation_engine_version": ENGINE_VERSION,
        "symbol": "BTCUSDT",
        "side": "long",
        "time_horizon": "intraday_short",
        "mode": "training",
        "entry": 100,
        "margin": 100,
        "leverage": 2,
        "stop_loss": 95,
        "take_profit": 110,
        "started_at": "2026-07-23T10:00:00+00:00",
        "closed_at": "2026-07-23T11:00:00+00:00",
        "close_reason": "take_profit",
        "final_pnl": 20,
        "recommendation_snapshot_json": json.dumps(snapshot),
        "recommendation_setup_grade": "B",
        "recommendation_risk_level": "medio",
        "recommendation_confidence": "alta",
        "recommendation_training_decision": "simular",
        "recommendation_tp_probability": 0.62,
        "recommendation_sl_probability": 0.32,
        "recommendation_range_probability": 0.06,
    }


class VersionedDataContractTests(unittest.TestCase):
    class CaptureDb:
        def __init__(self):
            self.query = ""
            self.params = ()

        def execute(self, query, params):
            self.query = query
            self.params = params
            return type("Cursor", (), {"lastrowid": 42})()

    class DbContext:
        def __init__(self, db):
            self.db = db

        def __enter__(self):
            return self.db

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def test_versions_are_independent_and_publicly_auditable(self):
        versions = current_version_contract()
        public = version_info()

        self.assertEqual(versions["app_version"], APP_VERSION)
        self.assertEqual(versions["engine_version"], ENGINE_VERSION)
        self.assertEqual(versions["scoring_version"], SCORING_VERSION)
        self.assertEqual(versions["learning_schema_version"], LEARNING_SCHEMA_VERSION)
        self.assertNotEqual(versions["app_version"], versions["scoring_version"])
        self.assertEqual(public["data_contract_version"], DATA_CONTRACT_VERSION)
        self.assertIn("deployment", public)

    def test_predictive_reader_exposes_only_pre_trade_features(self):
        contract = build_data_contract(
            pre_trade_features={"market_regime": "trend", "score": 60},
            post_trade_outcomes={"final_pnl": -10},
            diagnostic_labels={"analysis_verdict": "failed"},
        )

        features = predictive_features_from_contract(contract)

        self.assertEqual(features, {"market_regime": "trend", "score": 60})
        self.assertFalse(RETROSPECTIVE_KEYS & nested_keys(features))
        features["score"] = 0
        self.assertEqual(contract["pre_trade_features"]["score"], 60)

    def test_learning_contract_separates_pre_trade_outcomes_and_labels(self):
        evaluation = build_structured_learning_evaluation(
            legacy_operation(),
            [{"price": 110, "captured_at": "2026-07-23T11:00:00+00:00"}],
        )
        structured = json.loads(evaluation["structured_json"])

        self.assertIn("pre_trade_features", structured)
        self.assertIn("post_trade_outcomes", structured)
        self.assertIn("diagnostic_labels", structured)
        self.assertFalse(RETROSPECTIVE_KEYS & nested_keys(structured["pre_trade_features"]))
        self.assertEqual(structured["post_trade_outcomes"]["plan_result"], "plan_success")
        self.assertEqual(
            structured["diagnostic_labels"]["analysis_verdict"],
            evaluation["analysis_verdict"],
        )

    def test_legacy_record_remains_readable_without_fake_app_or_source_version(self):
        operation = legacy_operation()
        snapshot = json.loads(operation["recommendation_snapshot_json"])

        versions = recommendation_version_contract(operation, snapshot)
        evaluation = build_structured_learning_evaluation(operation, [])

        self.assertEqual(versions["scoring_version"], SCORING_VERSION)
        self.assertIsNone(versions["app_version"])
        self.assertIsNone(versions["data_source_version"])
        self.assertEqual(evaluation["scoring_version"], SCORING_VERSION)
        self.assertEqual(evaluation["learning_schema_version"], LEARNING_SCHEMA_VERSION)

    def test_app_versions_share_cohort_when_scoring_is_unchanged(self):
        snapshot = {
            "version_contract": {
                "app_version": "app-v0.12.1",
                "engine_version": ENGINE_VERSION,
                "scoring_version": SCORING_VERSION,
            }
        }
        first = recommendation_version_contract({}, snapshot)
        second = recommendation_version_contract(
            {"recommendation_app_version": APP_VERSION},
            snapshot,
        )

        self.assertNotEqual(first["app_version"], second["app_version"])
        self.assertEqual(first["scoring_version"], second["scoring_version"])

    def test_learning_insert_keeps_columns_and_parameters_aligned(self):
        evaluation = build_structured_learning_evaluation(legacy_operation(), [])
        db = self.CaptureDb()

        save_learning_evaluation(db, evaluation)

        values_clause = db.query.split("ON CONFLICT", 1)[0]
        self.assertEqual(values_clause.count("?"), len(db.params))
        self.assertEqual(len(db.params), 44)

    @patch("app.analyze_trade")
    @patch("app.current_user", return_value={"id": 7})
    def test_new_analysis_persists_versioned_pre_trade_contract(self, current_user, analyze_trade):
        analyze_trade.return_value = {
            "analysis_type": "pre_trade",
            "tp_probability": 0.6,
            "sl_probability": 0.34,
            "range_probability": 0.06,
            "risk_level": "medio",
            "setup_grade": "B",
            "confidence": "alta",
            "training_decision": "simular",
            "parameter_advice": {},
            "reasons": [],
            "alerts": [],
            "snapshot": {"market_regime": {"name": "tendencia_alcista"}},
        }
        db = self.CaptureDb()
        payload = TradePayload(
            symbol="BTCUSDT",
            side="long",
            time_horizon="intraday_short",
            entry=100,
            margin=100,
            leverage=2,
            stop_loss=95,
            take_profit=110,
        )

        with patch("app.connect", return_value=self.DbContext(db)):
            result = analyze(payload, "session")

        self.assertEqual(result["recommendation_id"], 42)
        self.assertEqual(result["version_contract"]["scoring_version"], SCORING_VERSION)
        self.assertIsNone(result["data_contract"]["post_trade_outcomes"])
        self.assertIsNone(result["data_contract"]["diagnostic_labels"])
        self.assertNotIn("data_contract", result["data_contract"]["pre_trade_features"])
        self.assertEqual(db.query.count("?"), len(db.params))
        self.assertEqual(len(db.params), 24)


if __name__ == "__main__":
    unittest.main()
