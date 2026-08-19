from __future__ import annotations

from copy import deepcopy


APP_VERSION = "app-v0.33.2-explained-analysis-blocks"
APP_SEMVER = "0.33.2"
ENGINE_VERSION = "TP-SL-EMPIRICAL-ANALOG-v0.9"
SCORING_VERSION = "historical-analog-first-touch-v0.9"
LEARNING_EVALUATOR_VERSION = "learning-v0.14-exact-horizon"
LEARNING_SCHEMA_VERSION = "learning-schema-v0.18-limit-lifecycle"
DATA_SOURCE_VERSION = "data-sources-v0.26-worker-price-authority"
DATA_CONTRACT_VERSION = "data-contract-v0.26-worker-price-authority-v0.9"
EVIDENCE_RECONSTRUCTION_VERSION = "evidence-v0.2-exact-horizon-binance-usdm-1m"
ECONOMIC_NORMALIZATION_VERSION = "economics-v0.1-risk-normalized"
LEGACY_REEVALUATION_VERSION = "legacy-review-v0.1-modern-taxonomy"
# Retained only so historical offline audit modules remain readable. It is not
# exported by current_version_contract and is not imported by the application.
CHALLENGER_RUNTIME_VERSION = "retired-offline-only-v0.7"
PROSPECTIVE_RUNTIME_VERSION = "empirical-analog-runtime-v0.9"


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
