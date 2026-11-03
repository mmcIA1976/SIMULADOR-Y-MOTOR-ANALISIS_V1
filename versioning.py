from __future__ import annotations

from copy import deepcopy
from analysis_engine_selection import ENGINE_VERSION, SCORING_VERSION, RUNTIME_VERSION, SCORING_BY_ENGINE, LAB4, LAB4_MODEL_SHA


APP_VERSION = "app-v0.40.25-compatible-scan-audit-history"
APP_SEMVER = "0.40.25"
LEGACY_LEARNING_EVALUATOR_VERSION = "learning-v0.17-v11-target-horizon-attribution"
LAB4_LEARNING_EVALUATOR_VERSION = "learning-v0.18-lab4-attribution-and-time-scope"


def learning_evaluator_version_for_engine(engine_version):
    return (LAB4_LEARNING_EVALUATOR_VERSION if engine_version == LAB4
            else LEGACY_LEARNING_EVALUATOR_VERSION)


LEARNING_EVALUATOR_VERSION = learning_evaluator_version_for_engine(ENGINE_VERSION)
LEARNING_SCHEMA_VERSION = "learning-schema-v0.22-target-horizon-attribution"
DATA_SOURCE_VERSION = "data-sources-v0.28-worker-order-book-dynamics"
DATA_CONTRACT_VERSION = "data-contract-v0.34-single-engine-inference"
EVIDENCE_RECONSTRUCTION_VERSION = "evidence-v0.3-terminal-confirmed-boundaries"
ECONOMIC_NORMALIZATION_VERSION = "economics-v0.1-risk-normalized"
LEGACY_REEVALUATION_VERSION = "legacy-review-v0.1-modern-taxonomy"
# Retained only so historical offline audit modules remain readable. It is not
# exported by current_version_contract and is not imported by the application.
CHALLENGER_RUNTIME_VERSION = "retired-offline-only-v0.7"
PROSPECTIVE_RUNTIME_VERSION = RUNTIME_VERSION


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
        **({'model_sha256': LAB4_MODEL_SHA} if ENGINE_VERSION == LAB4 else {}),
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
    if engine_version in SCORING_BY_ENGINE:
        return SCORING_BY_ENGINE[engine_version]
    if engine_version == "TP-SL-EMPIRICAL-ANALOG-v0.10":
        return "historical-analog-first-touch-v0.10"
    if engine_version == "TP-SL-EMPIRICAL-ANALOG-v0.9":
        return "historical-analog-first-touch-v0.9"
    if engine_version.startswith("rules-v0.12") or engine_version.startswith("rules-v0.11"):
        return "scoring-v0.11-underweighted-risk-cluster"
    return f"legacy-engine:{engine_version}"
