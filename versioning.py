from __future__ import annotations

from copy import deepcopy


APP_VERSION = "app-v0.22.1-engine-naming"
APP_SEMVER = "0.22.1"
ENGINE_VERSION = "TP-SL-PROBABILITY-ENGINE-v0.4"
SCORING_VERSION = "calibrated-plus-active-rules-v0.4"
LEARNING_EVALUATOR_VERSION = "learning-v0.3-rule-attribution"
LEARNING_SCHEMA_VERSION = "learning-schema-v0.6-rule-attribution"
DATA_SOURCE_VERSION = "data-sources-v0.13-binance-public-m5-context"
DATA_CONTRACT_VERSION = "data-contract-v0.7-active-rule-attribution"
EVIDENCE_RECONSTRUCTION_VERSION = "evidence-v0.1-binance-usdm-1m"
ECONOMIC_NORMALIZATION_VERSION = "economics-v0.1-risk-normalized"
LEGACY_REEVALUATION_VERSION = "legacy-review-v0.1-modern-taxonomy"
CHALLENGER_RUNTIME_VERSION = "inactive-history-only"
PROSPECTIVE_RUNTIME_VERSION = "active-predictive-rules-production-v0.4"


def current_version_contract() -> dict:
    return {
        "app_version": APP_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "learning_evaluator_version": LEARNING_EVALUATOR_VERSION,
        "learning_schema_version": LEARNING_SCHEMA_VERSION,
        "data_source_version": DATA_SOURCE_VERSION,
        "data_contract_version": DATA_CONTRACT_VERSION,
        "evidence_reconstruction_version": EVIDENCE_RECONSTRUCTION_VERSION,
        "economic_normalization_version": ECONOMIC_NORMALIZATION_VERSION,
        "legacy_reevaluation_version": LEGACY_REEVALUATION_VERSION,
        "challenger_runtime_version": CHALLENGER_RUNTIME_VERSION,
        "prospective_runtime_version": PROSPECTIVE_RUNTIME_VERSION,
    }


def build_data_contract(
    pre_trade_features: dict,
    post_trade_outcomes: dict | None = None,
    diagnostic_labels: dict | None = None,
) -> dict:
    return {
        "version": DATA_CONTRACT_VERSION,
        "pre_trade_features": deepcopy(pre_trade_features),
        "post_trade_outcomes": deepcopy(post_trade_outcomes),
        "diagnostic_labels": deepcopy(diagnostic_labels),
    }


def predictive_features_from_contract(data_contract: dict) -> dict:
    features = data_contract.get("pre_trade_features")
    if not isinstance(features, dict):
        raise ValueError("El contrato no contiene pre_trade_features validas")
    return deepcopy(features)


def scoring_version_for_legacy_engine(engine_version: str | None) -> str | None:
    if not engine_version:
        return None
    if engine_version == ENGINE_VERSION:
        return SCORING_VERSION
    if engine_version.startswith("rules-v0.12") or engine_version.startswith("rules-v0.11"):
        return "scoring-v0.11-underweighted-risk-cluster"
    return f"legacy-engine:{engine_version}"
