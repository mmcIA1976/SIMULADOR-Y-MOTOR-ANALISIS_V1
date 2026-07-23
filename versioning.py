from __future__ import annotations

from copy import deepcopy


APP_VERSION = "app-v0.13.0-data-contracts"
APP_SEMVER = "0.13.0"
ENGINE_VERSION = "rules-v0.12.1-liquidations-readable"
SCORING_VERSION = "scoring-v0.11-underweighted-risk-cluster"
LEARNING_EVALUATOR_VERSION = "learning-v0.2-underweighted-risk"
LEARNING_SCHEMA_VERSION = "learning-schema-v0.3-pre-post-diagnostics"
DATA_SOURCE_VERSION = "data-sources-v0.12.1-binance-hyperperps"
DATA_CONTRACT_VERSION = "data-contract-v0.1"


def current_version_contract() -> dict:
    return {
        "app_version": APP_VERSION,
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "learning_evaluator_version": LEARNING_EVALUATOR_VERSION,
        "learning_schema_version": LEARNING_SCHEMA_VERSION,
        "data_source_version": DATA_SOURCE_VERSION,
        "data_contract_version": DATA_CONTRACT_VERSION,
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
    if engine_version.startswith("rules-v0.12") or engine_version.startswith("rules-v0.11"):
        return SCORING_VERSION
    return f"legacy-engine:{engine_version}"
