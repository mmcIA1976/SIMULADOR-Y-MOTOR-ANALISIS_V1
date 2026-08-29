from __future__ import annotations

import hashlib
import json
from pathlib import Path

from m6_predictive_rules import (
    ACTIVE_PREDICTIVE_RULE_IDS,
    FITTED_RULE_IDS,
    PROVISIONAL_RULE_WEIGHTS,
)


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M5_CONTRACT_PATH = AUDIT_DIR / "contrato_implementacion_m5_1_v0_1.json"
CANDIDATE_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
OUTPUT_PATH = AUDIT_DIR / "catalogo_maestro_biblioteca_predictiva_v0_1.json"

LIBRARY_VERSION = "TP-SL-RULE-LIBRARY-v0.1"
HORIZONS = ["intraday_short", "intraday_wide", "short_swing"]
SUPPORTED_PAIRS = ["all_application_pairs"]


SOURCES = {
    "PROJECT_PHASE1_CONTRACT": {
        "title": "Contrato vinculante - Fase 1 del motor de analisis",
        "kind": "project_contract",
        "location": "CONTRATO_FASE_1_MOTOR_ANALISIS.md",
    },
    "PROJECT_M2_GEOMETRY": {
        "title": "M2 - Semantica, geometria e invariantes",
        "kind": "project_contract",
        "location": "auditorias_motor/2026-07-27_M2_semantica_geometria_resultado.md",
    },
    "BINANCE_USDM_API": {
        "title": "Binance USD-M Futures market data",
        "kind": "official_data_definition",
        "url": (
            "https://developers.binance.com/en/docs/derivatives/"
            "usds-margined-futures/market-data/rest-api"
        ),
    },
    "BINANCE_SPOT_API": {
        "title": "Binance Spot market data",
        "kind": "official_data_definition",
        "url": "https://developers.binance.com/docs/binance-spot-api-docs/rest-api",
    },
    "NIST_MAD": {
        "title": "NIST Median Absolute Deviation",
        "kind": "statistical_definition",
        "url": (
            "https://www.itl.nist.gov/div898/software/dataplot/"
            "refman2/auxillar/mad.htm"
        ),
    },
    "NIST_EXPONENTIAL_SMOOTHING": {
        "title": "NIST Single Exponential Smoothing",
        "kind": "statistical_definition",
        "url": "https://www.itl.nist.gov/div898/handbook/pmc/section4/pmc431.htm",
    },
    "WILDER_1978": {
        "title": "Wilder - New Concepts in Technical Trading Systems",
        "kind": "manual_definition",
        "year": 1978,
    },
    "BOLLINGER_2001": {
        "title": "Bollinger on Bollinger Bands",
        "kind": "manual_definition",
        "year": 2001,
    },
    "MOSKOWITZ_OOI_PEDERSEN_2012": {
        "title": "Time Series Momentum",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1016/j.jfineco.2011.11.003",
    },
    "HUDSON_URQUHART_2021": {
        "title": "Technical trading and cryptocurrencies",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1007/s10479-019-03357-1",
    },
    "CORSI_2009": {
        "title": "A Simple Approximate Long-Memory Model of Realized Volatility",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1093/jjfinec/nbp001",
    },
    "OSLER_2000": {
        "title": "Support for Resistance: Technical Analysis and Intraday Exchange Rates",
        "kind": "external_predictive_evidence",
        "url": (
            "https://www.newyorkfed.org/medialibrary/media/research/"
            "epr/00v06n2/0007osle.pdf"
        ),
    },
    "CONT_KUKANOV_STOIKOV_2014": {
        "title": "The Price Impact of Order Book Events",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1093/jjfinec/nbt003",
    },
    "SILANTYEV_2019": {
        "title": "Order flow analysis of cryptocurrency markets",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1007/s42521-019-00007-w",
    },
    "HONG_YOGO_2012": {
        "title": "What does futures market interest tell us about the macroeconomy?",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1016/j.jfineco.2011.05.008",
    },
    "HE_MANELA_ROSS_VON_WACHTER_2022": {
        "title": "Fundamentals of Perpetual Futures",
        "kind": "external_predictive_evidence",
        "url": "https://arxiv.org/abs/2212.06888",
    },
    "TSINASLANIDIS_ET_AL_2022": {
        "title": "Automated Fibonacci retracement evaluation",
        "kind": "external_predictive_evidence",
        "url": "https://doi.org/10.1016/j.eswa.2021.115893",
    },
    "COINGECKO_MARKETS_API": {
        "title": "CoinGecko Coins Markets",
        "kind": "official_data_definition",
        "url": "https://docs.coingecko.com/reference/coins-markets",
    },
    "ALTERNATIVE_ME_FNG": {
        "title": "Alternative.me Crypto Fear and Greed",
        "kind": "official_data_definition",
        "url": "https://alternative.me/crypto/fear-and-greed-index/",
    },
    "HYPERLIQUID_PUBLIC_STATE": {
        "title": "Hyperliquid public clearinghouse state",
        "kind": "official_data_definition",
        "url": "https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint",
    },
    "HYPERPERPS_PUBLIC_HEATMAP": {
        "title": "HyperPerps public Hyperliquid liquidation heatmap",
        "kind": "third_party_public_data_definition",
        "url": "https://trade.hyperperps.app/whales",
    },
}


BASELINE_RULE_IDS = (
    "M4-RULE-HORIZON-SAMPLING-001",
    "M4-RULE-PLAN-GEOMETRY-001",
    "M4-RULE-LOG-RETURNS-001",
    "M4-RULE-REALIZED-VOLATILITY-001",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
)

ACTIVE_ECONOMIC_RULE_IDS = (
    "M4-RULE-QUOTED-SPREAD-001",
    "M4-RULE-DEPTH-SWEEP-001",
)


ACTIVE_METADATA = {
    "M4-RULE-PATH-STRUCTURE-001": {
        "family_id": "FAMILY-PRICE-PATH",
        "role": "standalone",
        "source_ids": [
            "MOSKOWITZ_OOI_PEDERSEN_2012",
            "HUDSON_URQUHART_2021",
        ],
        "hypothesis": (
            "Side-aligned signed path efficiency may condition which barrier "
            "is reached first."
        ),
        "probability_formula": (
            "signal=clip(side*SE_H,-1,1); "
            "log_w_tp+=0.12*signal; log_w_sl-=0.12*signal"
        ),
        "shared_evidence": ["M4-RULE-CONTINUOUS-REGIME-001"],
    },
    "M4-RULE-PRIOR-EXTREMA-001": {
        "family_id": "FAMILY-STRUCTURAL-LEVELS",
        "role": "standalone",
        "source_ids": ["OSLER_2000"],
        "hypothesis": (
            "A prior extreme between entry and TP may alter first-barrier "
            "probability."
        ),
        "probability_formula": "fitted competing-risk covariate",
        "shared_evidence": [],
    },
    "M4-RULE-VOLATILITY-RANK-001": {
        "family_id": "FAMILY-VOLATILITY",
        "role": "standalone",
        "source_ids": ["CORSI_2009"],
        "hypothesis": (
            "Within-pair volatility rank may alter TP, SL and expiry hazards."
        ),
        "probability_formula": "fitted competing-risk covariate",
        "shared_evidence": ["M4-RULE-CONTINUOUS-REGIME-001"],
    },
    "M4-RULE-MTF-HIERARCHY-001": {
        "family_id": "FAMILY-PRICE-PATH",
        "role": "group",
        "source_ids": [
            "MOSKOWITZ_OOI_PEDERSEN_2012",
            "HUDSON_URQUHART_2021",
        ],
        "hypothesis": (
            "Side-aligned path efficiencies at 2H and 4H may add information "
            "beyond the exact-horizon path."
        ),
        "probability_formula": "two fitted competing-risk covariates",
        "shared_evidence": ["M4-RULE-PATH-STRUCTURE-001"],
    },
    "M4-RULE-CONTINUOUS-REGIME-001": {
        "family_id": "FAMILY-PRICE-PATH-X-VOLATILITY",
        "role": "interaction",
        "source_ids": ["CORSI_2009", "HUDSON_URQUHART_2021"],
        "hypothesis": (
            "The effect of signed path efficiency may vary with volatility "
            "rank."
        ),
        "probability_formula": (
            "signal=clip(side*SE_H*(2*q_RV-1),-1,1); "
            "log_w_tp+=0.08*signal; log_w_sl-=0.08*signal"
        ),
        "parent_rule_ids": [
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-VOLATILITY-RANK-001",
        ],
        "shared_evidence": [
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-VOLATILITY-RANK-001",
        ],
    },
    "M4-RULE-AGGRESSOR-IMBALANCE-001": {
        "family_id": "FAMILY-EXECUTED-FLOW",
        "role": "standalone",
        "source_ids": ["CONT_KUKANOV_STOIKOV_2014", "SILANTYEV_2019"],
        "hypothesis": (
            "Side-aligned executed taker imbalance may condition short-horizon "
            "first-barrier behavior."
        ),
        "probability_formula": (
            "signal=clip(side*ATI_H,-1,1); "
            "log_w_tp+=0.12*signal; log_w_sl-=0.12*signal"
        ),
        "shared_evidence": [],
    },
    "M4-RULE-OPEN-INTEREST-CHANGE-001": {
        "family_id": "FAMILY-OPEN-INTEREST",
        "role": "standalone",
        "source_ids": ["BINANCE_USDM_API", "HONG_YOGO_2012"],
        "hypothesis": (
            "Absolute open-interest change may indicate movement activity "
            "without identifying direction."
        ),
        "probability_formula": (
            "signal=tanh(50*abs(dOI_H)); log_w_tp+=0.06*signal; "
            "log_w_sl+=0.06*signal; log_w_expiry-=0.06*signal"
        ),
        "shared_evidence": ["M4-RULE-PRICE-OI-STATE-001"],
    },
    "M4-RULE-PRICE-OI-STATE-001": {
        "family_id": "FAMILY-PRICE-X-OPEN-INTEREST",
        "role": "interaction",
        "source_ids": ["BINANCE_USDM_API", "HONG_YOGO_2012"],
        "hypothesis": (
            "The joint state of price displacement and open-interest change "
            "may condition barrier direction."
        ),
        "probability_formula": (
            "signal=clip(side*sign(D_H)*tanh(50*dOI_H),-1,1); "
            "log_w_tp+=0.10*signal; log_w_sl-=0.10*signal"
        ),
        "parent_rule_ids": ["M4-RULE-OPEN-INTEREST-CHANGE-001"],
        "shared_evidence": ["M4-RULE-OPEN-INTEREST-CHANGE-001"],
    },
    "M4-RULE-SPOT-FUTURES-BASIS-001": {
        "family_id": "FAMILY-PERPETUAL-DISLOCATION",
        "role": "standalone",
        "source_ids": [
            "BINANCE_USDM_API",
            "BINANCE_SPOT_API",
            "HE_MANELA_ROSS_VON_WACHTER_2022",
        ],
        "hypothesis": (
            "Synchronized spot-futures basis may condition first-barrier "
            "behavior."
        ),
        "probability_formula": (
            "signal=-side*tanh(100*b_mid); "
            "log_w_tp+=0.06*signal; log_w_sl-=0.06*signal"
        ),
        "shared_evidence": [
            "M4-RULE-MARK-INDEX-PREMIUM-001",
            "M4-RULE-FUNDING-STATE-001",
        ],
    },
    "M4-RULE-MARK-INDEX-PREMIUM-001": {
        "family_id": "FAMILY-PERPETUAL-DISLOCATION",
        "role": "standalone",
        "source_ids": [
            "BINANCE_USDM_API",
            "HE_MANELA_ROSS_VON_WACHTER_2022",
        ],
        "hypothesis": (
            "Synchronized mark-index premium may condition first-barrier "
            "behavior."
        ),
        "probability_formula": (
            "signal=-side*tanh(200*mark_index_log_premium); "
            "log_w_tp+=0.06*signal; log_w_sl-=0.06*signal"
        ),
        "shared_evidence": [
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            "M4-RULE-FUNDING-STATE-001",
        ],
    },
    "M4-RULE-FUNDING-STATE-001": {
        "family_id": "FAMILY-PERPETUAL-DISLOCATION",
        "role": "standalone",
        "source_ids": [
            "BINANCE_USDM_API",
            "HE_MANELA_ROSS_VON_WACHTER_2022",
        ],
        "hypothesis": (
            "Funding state relative to the proposed side may condition "
            "first-barrier behavior."
        ),
        "probability_formula": (
            "signal=-side*tanh(last_funding_rate/0.0005); "
            "log_w_tp+=0.08*signal; log_w_sl-=0.08*signal"
        ),
        "shared_evidence": [
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            "M4-RULE-MARK-INDEX-PREMIUM-001",
        ],
    },
}


BASELINE_METADATA = {
    rule_id: {
        "family_id": (
            "FAMILY-PLAN-GEOMETRY"
            if rule_id in {
                "M4-RULE-HORIZON-SAMPLING-001",
                "M4-RULE-PLAN-GEOMETRY-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            }
            else "FAMILY-REALIZED-VOLATILITY"
        ),
        "source_ids": [
            "PROJECT_M2_GEOMETRY",
            "BINANCE_USDM_API",
        ],
    }
    for rule_id in BASELINE_RULE_IDS
}


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def source_claims(source_ids: list[str], hypothesis: str) -> dict:
    return {
        "source_ids": source_ids,
        "supported_claim": (
            "Sources support data definitions, indicator construction or the "
            "general research family only."
        ),
        "unsupported_claim": (
            "Sources do not establish this project's exact sign, threshold, "
            "weight, TP effect, SL effect or cross-pair validity."
        ),
        "project_hypothesis": hypothesis,
    }


def inputs_from_spec(spec: dict) -> list[dict]:
    provider = spec.get("input_contract", {}).get("provider")
    if not provider:
        provider = spec.get("raw_data_and_provider", {}).get("provider")
    return [
        {
            "contract": spec.get("input_contract", {}),
            "provider": provider or "declared_by_m5_contract",
            "unit_policy": spec.get(
                "market_time_unit_freshness",
                {},
            ),
        }
    ]


def runtime_rule(spec: dict, metadata: dict, coefficient_artifact: dict) -> dict:
    rule_id = spec["rule_id"]
    fitted = rule_id in FITTED_RULE_IDS
    provisional = rule_id in PROVISIONAL_RULE_WEIGHTS
    parameters = []
    if fitted:
        feature_names = {
            "M4-RULE-PRIOR-EXTREMA-001": [
                "target_extreme_between_entry_and_tp"
            ],
            "M4-RULE-VOLATILITY-RANK-001": [
                "volatility_percentile_60"
            ],
            "M4-RULE-MTF-HIERARCHY-001": [
                "directional_path_efficiency_2h",
                "directional_path_efficiency_4h",
            ],
        }[rule_id]
        for feature in feature_names:
            parameters.append(
                {
                    "name": feature,
                    "origin": "historical_fit",
                    "status": "fitted_provisional",
                    "tp": coefficient_artifact["coefficients"]["tp"][feature],
                    "sl": coefficient_artifact["coefficients"]["sl"][feature],
                }
            )
    if provisional:
        parameters.append(
            {
                "name": "log_effect_weight",
                "origin": "project_hypothesis",
                "status": "unvalidated_provisional",
                "value": PROVISIONAL_RULE_WEIGHTS[rule_id],
            }
        )
    return {
        "rule_id": rule_id,
        "version": str(spec["rule_version"]),
        "name": spec["name"],
        "family_id": metadata["family_id"],
        "role": metadata["role"],
        "lifecycle_status": "active_provisional",
        "origin": "current_probability_engine",
        "objective": spec.get("name"),
        "applicable_pairs": SUPPORTED_PAIRS,
        "applicable_horizons": HORIZONS,
        "inputs": inputs_from_spec(spec),
        "formula_ids": [item["id"] for item in spec.get("formulas", [])],
        "deterministic_formulas": [
            item["expression"] for item in spec.get("formulas", [])
        ],
        "probability_integration_formula": metadata["probability_formula"],
        "normalization": spec.get(
            "market_time_unit_freshness",
            {},
        ),
        "activation_conditions": spec.get("activation_conditions", []),
        "non_application_conditions": spec.get(
            "non_application_conditions",
            [],
        ),
        "missing_data_behavior": spec.get("missing_data_behavior"),
        "evidence": source_claims(
            metadata["source_ids"],
            metadata["hypothesis"],
        ),
        "expected_probability_effect": {
            "mode": (
                "fitted_competing_risk_covariate"
                if fitted
                else "provisional_log_effect"
            ),
            "tp": "recorded_per_analysis",
            "sl": "recorded_per_analysis",
            "expiry": "recorded_per_analysis",
        },
        "interactions": {
            "parent_rule_ids": metadata.get("parent_rule_ids", []),
            "shared_evidence_rule_ids": metadata.get(
                "shared_evidence",
                [],
            ),
            "double_counting_control": (
                "family ablation required before learned promotion"
            ),
        },
        "parameters": parameters,
        "trace_contract": {
            "required_outputs": spec.get("required_trace_outputs", []),
            "requires_source_hash": True,
            "requires_probability_ablation": True,
            "requires_family_ablation": True,
        },
        "learning_contract": {
            "outcomes": ["TP_FIRST", "SL_FIRST", "EXPIRY"],
            "segment_by": ["pair", "side", "horizon", "regime"],
            "may_self_modify_production": False,
        },
        "refutation_or_retirement": (
            "Suspend or restrict when temporal out-of-sample evidence shows no "
            "stable incremental value after family controls."
        ),
    }


def baseline_rule(spec: dict, metadata: dict) -> dict:
    return {
        "rule_id": spec["rule_id"],
        "version": str(spec["rule_version"]),
        "name": spec["name"],
        "family_id": metadata["family_id"],
        "role": "baseline",
        "lifecycle_status": "active_deterministic",
        "origin": "current_probability_engine",
        "objective": spec["name"],
        "applicable_pairs": SUPPORTED_PAIRS,
        "applicable_horizons": HORIZONS,
        "inputs": inputs_from_spec(spec),
        "formula_ids": [item["id"] for item in spec.get("formulas", [])],
        "deterministic_formulas": [
            item["expression"] for item in spec.get("formulas", [])
        ],
        "probability_integration_formula": (
            "required input to the double-barrier baseline"
        ),
        "normalization": spec.get("market_time_unit_freshness", {}),
        "activation_conditions": spec.get("activation_conditions", []),
        "non_application_conditions": spec.get(
            "non_application_conditions",
            [],
        ),
        "missing_data_behavior": spec.get("missing_data_behavior"),
        "evidence": source_claims(
            metadata["source_ids"],
            "This deterministic operator is required to define the plan and "
            "baseline; its predictive adequacy remains testable.",
        ),
        "expected_probability_effect": {
            "mode": "baseline_input",
            "tp": "structural",
            "sl": "structural",
            "expiry": "structural",
        },
        "interactions": {
            "parent_rule_ids": list(spec.get("dependencies", [])),
            "shared_evidence_rule_ids": [],
            "double_counting_control": "not an additive signal",
        },
        "parameters": [],
        "trace_contract": {
            "required_outputs": spec.get("required_trace_outputs", []),
            "requires_source_hash": True,
            "requires_probability_ablation": False,
            "requires_family_ablation": False,
        },
        "learning_contract": {
            "outcomes": ["TP_FIRST", "SL_FIRST", "EXPIRY"],
            "segment_by": ["pair", "side", "horizon"],
            "may_self_modify_production": False,
        },
        "refutation_or_retirement": (
            "Replace only with an approved baseline that preserves geometry, "
            "mass, symmetry and monotonicity invariants."
        ),
    }


def candidate(
    *,
    rule_id: str,
    name: str,
    family_id: str,
    role: str,
    formulas: list[str],
    inputs: list[str],
    source_ids: list[str],
    hypothesis: str,
    parents: list[str] | None = None,
    status: str = "proposed",
    missing_data_behavior: str = "not_evaluated",
    historical_evidence: dict | None = None,
    provider: str = "must_be_approved_before_implementation",
) -> dict:
    return {
        "rule_id": rule_id,
        "version": "0.1",
        "name": name,
        "family_id": family_id,
        "role": role,
        "lifecycle_status": status,
        "origin": "2026-07-29_external_rule_review_and_86_crosswalk",
        "objective": hypothesis,
        "applicable_pairs": SUPPORTED_PAIRS,
        "applicable_horizons": HORIZONS,
        "inputs": [
            {
                "names": inputs,
                "provider": provider,
                "unit_policy": "dimensionless_or_within_pair_normalized",
            }
        ],
        "formula_ids": [f"{rule_id}-FORMULA-{index:02d}" for index in range(1, len(formulas) + 1)],
        "deterministic_formulas": formulas,
        "probability_integration_formula": "none_until_implemented_and_approved",
        "normalization": (
            "Rolling empirical percentile or robust z-score computed only "
            "from observations available at analysis_at; MAD=0 blocks robust z."
        ),
        "activation_conditions": [
            "all declared inputs complete, fresh and pre-trade",
            "formula valid for the selected pair and horizon",
        ],
        "non_application_conditions": [
            "missing, stale, future, gapped or semantically incompatible data"
        ],
        "missing_data_behavior": missing_data_behavior,
        "evidence": source_claims(source_ids, hypothesis),
        "expected_probability_effect": {
            "mode": "hypothesis_not_active",
            "tp": "to_be_estimated",
            "sl": "to_be_estimated",
            "expiry": "to_be_estimated",
        },
        "interactions": {
            "parent_rule_ids": parents or [],
            "shared_evidence_rule_ids": [],
            "double_counting_control": "declare family and test family ablation",
        },
        "parameters": [
            {
                "name": "all_thresholds_and_effect_sizes",
                "origin": "not_assigned",
                "status": "must_be_preregistered_then_estimated",
            }
        ],
        "trace_contract": {
            "required_outputs": [
                "raw_inputs",
                "normalized_signal",
                "activation_status",
                "formula_branch",
            ],
            "requires_source_hash": True,
            "requires_probability_ablation": True,
            "requires_family_ablation": True,
        },
        "learning_contract": {
            "outcomes": ["TP_FIRST", "SL_FIRST", "EXPIRY"],
            "segment_by": ["pair", "side", "horizon", "regime"],
            "may_self_modify_production": False,
        },
        "historical_evidence": historical_evidence or {
            "status": "not_evaluated"
        },
        "refutation_or_retirement": (
            "Retire, restrict or reformulate when independent temporal evidence "
            "shows no stable incremental value."
        ),
    }


def blocking_data_quality_gate(
    *,
    rule_id: str,
    name: str,
    formulas: list[str],
    inputs: list[str],
    required_outputs: list[str],
    parameters: list[dict],
) -> dict:
    rule = candidate(
        rule_id=rule_id,
        name=name,
        family_id="FAMILY-DATA-QUALITY",
        role="blocking",
        formulas=formulas,
        inputs=inputs,
        source_ids=["PROJECT_PHASE1_CONTRACT", "BINANCE_USDM_API"],
        hypothesis=(
            "Deterministic input-validity gate; it has no directional or "
            "first-barrier hypothesis."
        ),
        status="active_blocking",
        missing_data_behavior="block_analysis_and_record_exact_reason",
        provider="binance_usdm_closed_klines",
    )
    rule.update(
        {
            "origin": "project_phase1_data_contract",
            "probability_integration_formula": (
                "none; invalid input blocks analysis before probability"
            ),
            "normalization": (
                "No statistical normalization. Compare timestamps and candle "
                "grid against the selected interval and analysis_at."
            ),
            "activation_conditions": [
                "run exactly once during pre-trade input assembly"
            ],
            "non_application_conditions": [],
            "expected_probability_effect": {
                "mode": "blocking_gate_not_predictive",
                "tp": "none",
                "sl": "none",
                "expiry": "none",
            },
            "interactions": {
                "parent_rule_ids": [],
                "shared_evidence_rule_ids": [],
                "double_counting_control": (
                    "single validation report reused by every dependent rule"
                ),
            },
            "parameters": parameters,
            "trace_contract": {
                "required_outputs": required_outputs,
                "requires_source_hash": True,
                "requires_probability_ablation": False,
                "requires_family_ablation": False,
            },
            "learning_contract": {
                "outcomes": [],
                "segment_by": ["pair", "horizon", "provider"],
                "may_self_modify_production": False,
            },
            "refutation_or_retirement": (
                "Replace only with a stricter approved data contract; never "
                "convert data quality into directional evidence."
            ),
        }
    )
    return rule


def active_economic_rule(
    spec: dict,
    *,
    provider: str,
    superseded_candidate_rule_id: str,
) -> dict:
    rule_id = spec["rule_id"]
    return {
        "rule_id": rule_id,
        "version": str(spec["rule_version"]),
        "name": spec["name"],
        "family_id": "FAMILY-EXECUTION",
        "role": "economic",
        "lifecycle_status": "active_economic",
        "origin": "current_execution_economic_runtime",
        "objective": (
            "Measure current executability and entry cost without changing "
            "physical TP, SL or expiry probabilities."
        ),
        "applicable_pairs": SUPPORTED_PAIRS,
        "applicable_horizons": HORIZONS,
        "inputs": [
            {
                "contract": spec["input_contract"],
                "provider": provider,
                "unit_policy": spec["market_time_unit_freshness"],
            }
        ],
        "formula_ids": [
            item["id"] for item in spec.get("formulas", [])
        ],
        "deterministic_formulas": [
            item["expression"] for item in spec.get("formulas", [])
        ],
        "probability_integration_formula": (
            "none; result belongs to the separate execution-economic layer"
        ),
        "normalization": (
            "Quote prices and costs stay in quote asset; base quantity stays "
            "in base asset; fractions are dimensionless."
        ),
        "activation_conditions": spec["activation_conditions"],
        "non_application_conditions": spec[
            "non_application_conditions"
        ],
        "missing_data_behavior": spec["missing_data_behavior"],
        "evidence": source_claims(
            ["PROJECT_PHASE1_CONTRACT", "BINANCE_USDM_API"],
            (
                "Current spread and visible-depth sweep measure execution "
                "conditions, not future market direction."
            ),
        ),
        "expected_probability_effect": {
            "mode": "execution_economic_only",
            "tp": "none",
            "sl": "none",
            "expiry": "none",
        },
        "interactions": {
            "parent_rule_ids": list(spec.get("dependencies", [])),
            "shared_evidence_rule_ids": [],
            "double_counting_control": (
                "implementation shortfall from midpoint already contains "
                "half-spread; spread must not be added again"
            ),
        },
        "parameters": [
            {
                "name": "realtime_snapshot_max_age_ms",
                "value": 30_000,
                "origin": "project_phase1_data_contract",
                "status": "active_deterministic_policy",
            }
        ],
        "trace_contract": {
            "required_outputs": spec["required_trace_outputs"],
            "requires_source_hash": True,
            "requires_probability_ablation": False,
            "requires_family_ablation": False,
        },
        "learning_contract": {
            "outcomes": [],
            "segment_by": ["pair", "side", "planned_notional"],
            "may_self_modify_production": False,
        },
        "superseded_candidate_rule_ids": [
            superseded_candidate_rule_id
        ],
        "historical_evidence": {
            "status": "not_a_predictive_rule"
        },
        "refutation_or_retirement": (
            "Replace only with a more complete execution model that preserves "
            "snapshot timestamps, partial coverage and no double counting."
        ),
    }


def candidate_rules() -> list[dict]:
    return [
        candidate(
            rule_id="LIB-CAND-EMA-TREND-001",
            name="EMA trend state and normalized slope",
            family_id="FAMILY-TREND",
            role="contextual",
            formulas=[
                "EMA_t=alpha*C_t+(1-alpha)*EMA_(t-1); alpha=2/(n+1)",
                "slope_ema50=(EMA50_t-EMA50_(t-k))/ATR14",
                "state=(close>EMA50, EMA50>EMA200, slope_ema50)",
            ],
            inputs=["closed_ohlc"],
            source_ids=[
                "NIST_EXPONENTIAL_SMOOTHING",
                "HUDSON_URQUHART_2021",
            ],
            hypothesis=(
                "Continuous EMA alignment and normalized slope may condition "
                "first-barrier behavior."
            ),
            status="implemented_shadow",
            provider="binance_usdm_closed_klines",
        ),
        candidate(
            rule_id="LIB-CAND-RSI-WILDER-001",
            name="Wilder RSI state",
            family_id="FAMILY-MOMENTUM",
            role="contextual",
            formulas=[
                "RS=wilders_average(gains,n)/wilders_average(losses,n)",
                "RSI=100-100/(1+RS)",
            ],
            inputs=["closed_ohlc"],
            source_ids=["WILDER_1978", "HUDSON_URQUHART_2021"],
            hypothesis=(
                "Continuous RSI may have regime-dependent incremental value "
                "without fixed overbought or oversold points."
            ),
            status="implemented_shadow",
            provider="binance_usdm_closed_klines",
        ),
        candidate(
            rule_id="LIB-CAND-ATR-EXTENSION-001",
            name="ATR-normalized extension from EMA",
            family_id="FAMILY-TREND-X-VOLATILITY",
            role="interaction",
            formulas=[
                "extension=(close-EMA20)/ATR14",
            ],
            inputs=["closed_ohlc"],
            source_ids=["WILDER_1978", "NIST_EXPONENTIAL_SMOOTHING"],
            hypothesis=(
                "Side-aligned extension from a smoothed price reference may "
                "condition continuation versus reversion."
            ),
            parents=["LIB-CAND-EMA-TREND-001"],
            status="implemented_shadow",
            provider="binance_usdm_closed_klines",
        ),
        candidate(
            rule_id="LIB-CAND-RELATIVE-VOLUME-001",
            name="Exact-horizon relative volume",
            family_id="FAMILY-VOLUME",
            role="standalone",
            formulas=[
                "V_H=sum(volume_i over the exact prior horizon H)",
                "relative_volume_H=V_H/median(previous_60_non_overlapping_V_H)",
                "volume_midrank_60=(count(V_j<V_H)+0.5*count(V_j=V_H))/60",
            ],
            inputs=["closed_kline_volume", "exact_horizon"],
            source_ids=["BINANCE_USDM_API", "NIST_MAD"],
            hypothesis=(
                "Volume relative to 60 preceding comparable horizons may "
                "condition movement intensity and first-barrier timing."
            ),
            status="implemented_shadow",
            provider="binance_usdm_closed_klines",
        ),
        candidate(
            rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
            name="Normalized visible order-book imbalance",
            family_id="FAMILY-ORDER-BOOK",
            role="standalone",
            formulas=[
                "obi_D=(bid_notional_D-ask_notional_D)/(bid_notional_D+ask_notional_D)",
                "D in {top5,top20,10bps,20bps,50bps}",
                "persistence_D=stats(obi_D over the bounded rolling window)",
                "sign_flips_D=count(non_neutral_sign_t != non_neutral_sign_t-1)",
                "modification_velocity=(added_notional+removed_notional)/(visible_notional*delta_t)",
                "wall=level_notional>=3*median_side_level_notional within 50bps",
                "unmatched_removal=max(visible_removal-opposite_aggressor_execution,0)",
                "absorption=executed_opposing_flow*confirmed_visible_removal*missing_price_follow_through",
            ],
            inputs=["timestamped_depth_snapshot"],
            source_ids=["BINANCE_USDM_API", "CONT_KUKANOV_STOIKOV_2014"],
            hypothesis=(
                "Persistent visible-depth imbalance, wall survival and "
                "executed-flow-confirmed changes at declared depth D may "
                "condition short-horizon first-barrier behavior."
            ),
            status="implemented_shadow",
            provider=(
                "operation_worker_rolling_binance_usdm_depth_and_aggtrades"
            ),
        ),
        candidate(
            rule_id="LIB-CAND-CVD-SLOPE-001",
            name="Exact-window executed-flow accumulation",
            family_id="FAMILY-EXECUTED-FLOW",
            role="group",
            formulas=[
                "delta_i=buy_taker_volume_i-sell_taker_volume_i",
                "CVD_t=cumsum(delta_i over exact horizon H)",
                "cvd_slope=TheilSenSlope(CVD_t)",
                "normalized_cvd_slope=cvd_slope/mean(total_taker_volume_i)",
            ],
            inputs=[
                "periodic_taker_buy_sell_volume",
                "closed_kline_taker_quote_volume_fallback",
            ],
            source_ids=["BINANCE_USDM_API", "SILANTYEV_2019"],
            hypothesis=(
                "The trajectory of executed signed flow may add information "
                "beyond its terminal imbalance."
            ),
            parents=["M4-RULE-AGGRESSOR-IMBALANCE-001"],
            status="implemented_shadow",
            provider=(
                "binance_usdm_taker_buy_sell_history_or_closed_klines"
            ),
        ),
        candidate(
            rule_id="LIB-CAND-BREADTH-001",
            name="Cross-crypto breadth state",
            family_id="FAMILY-MARKET-CONTEXT",
            role="contextual",
            formulas=[
                (
                    "U_t=first_100_assets_ordered_by_"
                    "current_market_cap_desc"
                ),
                (
                    "breadth_w=count(return_i_w>0)/"
                    "count(valid_return_i_w), w in {1h,24h,7d}"
                ),
                "median_return_w=median(valid_return_i_w)",
            ],
            inputs=[
                "coingecko_top_100_constituent_ids",
                "constituent_returns_1h_24h_7d",
                "constituent_update_timestamps",
                "plan_side",
            ],
            source_ids=["COINGECKO_MARKETS_API"],
            hypothesis=(
                "Cross-crypto breadth may condition a pair's first-barrier "
                "probability after pair-specific controls."
            ),
            status="implemented_shadow",
            provider="coingecko_coins_markets_top_100",
            historical_evidence={
                "status": "legacy_values_preserved_not_comparable",
                "artifact": (
                    "auditorias_motor/"
                    "market_context_historical_cases_v0_1.json"
                ),
                "artifact_sha256": (
                    "d1a49379ae1e5072881a3caa1e1ee67"
                    "b141b3343affb3110bec5abee3d12f672"
                ),
                "legacy_observations_available": 718,
                "reuse_policy": (
                    "preserve_identity_and_raw_values_only; "
                    "legacy_snapshot_lacks_full_constituent_universe"
                ),
            },
        ),
        candidate(
            rule_id="LIB-CAND-FIBONACCI-DISTANCE-001",
            name="Fibonacci level distance and confluence",
            family_id="FAMILY-STRUCTURAL-LEVELS",
            role="contextual",
            formulas=[
                "swing=last_two_opposing_confirmed_pivots_in_alternating_series",
                "retracement_r=start+direction*(1-r)*abs(end-start)",
                "extension_r=start+direction*r*abs(end-start)",
                "distance_sigma=abs(log(fib_level/plan_price))/sigma_h",
                "confluence_sigma=abs(log(pivot_price/fib_level))/sigma_h",
            ],
            inputs=["objective_swing_points", "plan", "volatility"],
            source_ids=["BINANCE_USDM_API", "TSINASLANIDIS_ET_AL_2022"],
            hypothesis=(
                "Distance and confluence with reproducible Fibonacci levels "
                "may condition barrier behavior; no intrinsic bonus is assumed."
            ),
            parents=["LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"],
            status="implemented_shadow",
            provider="binance_usdm_closed_klines",
            historical_evidence={
                "status": "available_legacy_formula_not_comparable",
                "legacy_recommendations": 669,
                "legacy_observations_available": 666,
                "legacy_linked_operations": 163,
                "legacy_closed_operations": 154,
                "artifact": (
                    "auditorias_motor/"
                    "fibonacci_historical_cases_v0_1.json"
                ),
                "artifact_sha256": (
                    "05f5e7b73785520c0a31a4a083a4f3d6"
                    "b09b19e11083bfb6ec23a7386730a2cb"
                ),
                "reuse_policy": (
                    "recompute_new_rule_from_pretrade_klines; "
                    "do_not_reuse_legacy_scores_or_probability_adjustments"
                ),
            },
        ),
        candidate(
            rule_id="LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
            name="Distance to reproducible structural levels",
            family_id="FAMILY-STRUCTURAL-LEVELS",
            role="contextual",
            formulas=[
                "pivot_high_i=unique_max(high[i-3:i+4])",
                "pivot_low_i=unique_min(low[i-3:i+4])",
                "prominence_atr=min(left_excursion,right_excursion)/ATR14",
                "level_distance_sigma=log(level_price/entry)/sigma_h",
            ],
            inputs=["closed_ohlc", "plan", "volatility"],
            source_ids=["BINANCE_USDM_API", "OSLER_2000"],
            hypothesis=(
                "The distance and prominence of prior levels between entry "
                "and a barrier may condition first passage."
            ),
            status="implemented_shadow",
            provider="binance_usdm_closed_klines",
        ),
        candidate(
            rule_id="LIB-CAND-FUNDING-PERCENTILE-001",
            name="Funding relative to its own history",
            family_id="FAMILY-PERPETUAL-DISLOCATION",
            role="contextual",
            formulas=[
                (
                    "funding_midrank_60=("
                    "count(r_i<current)+0.5*count(r_i=current))/60"
                ),
                (
                    "funding_robust_z_60="
                    "(current-median(r_i))/(1.4826*MAD(r_i))"
                ),
                "plan_side_funding_cost_rate=side_sign*current_rate",
            ],
            inputs=[
                "current_premium_index_funding_rate",
                "last_60_strictly_prior_settled_funding_rates",
                "plan_side",
            ],
            source_ids=[
                "BINANCE_USDM_API",
                "NIST_MAD",
                "HE_MANELA_ROSS_VON_WACHTER_2022",
            ],
            hypothesis=(
                "Funding relative to its pair-specific history may be more "
                "informative than an absolute funding threshold."
            ),
            parents=["M4-RULE-FUNDING-STATE-001"],
            status="implemented_shadow",
            provider=(
                "binance_usdm_premium_index_and_funding_history"
            ),
        ),
        candidate(
            rule_id="LIB-CAND-CROWDING-PERCENTILE-001",
            name="Positioning crowding percentile",
            family_id="FAMILY-POSITIONING",
            role="contextual",
            formulas=[
                "log_ratio_t=log(long_account_count/short_account_count)",
                (
                    "crowding_midrank_60=("
                    "count(log_ratio_i<current)+"
                    "0.5*count(log_ratio_i=current))/60"
                ),
                (
                    "plan_side_crowding_midrank="
                    "p_long if side=long else 1-p_long"
                ),
            ],
            inputs=[
                "current_global_long_short_account_ratio",
                "60_strictly_prior_contiguous_ratio_periods",
                "plan_side",
            ],
            source_ids=["BINANCE_USDM_API", "NIST_MAD"],
            hypothesis=(
                "Extreme positioning relative to pair history may condition "
                "barrier behavior without identifying future direction alone."
            ),
            status="implemented_shadow",
            provider=(
                "binance_usdm_global_long_short_account_ratio_history"
            ),
        ),
        candidate(
            rule_id="LIB-CAND-SENTIMENT-PERCENTILE-001",
            name="External sentiment percentile",
            family_id="FAMILY-MARKET-CONTEXT",
            role="contextual",
            formulas=[
                (
                    "sentiment_midrank_60=("
                    "count(v_i<current)+0.5*count(v_i=current))/60"
                ),
                (
                    "sentiment_robust_z_60="
                    "(current-median(v_i))/(1.4826*MAD(v_i))"
                ),
                (
                    "plan_side_alignment="
                    "side_sign*(current_value-50)/50"
                ),
            ],
            inputs=[
                "current_fear_greed_value",
                "60_strictly_prior_daily_values",
                "provider_timestamps",
                "plan_side",
            ],
            source_ids=["ALTERNATIVE_ME_FNG", "NIST_MAD"],
            hypothesis=(
                "External sentiment extremes may have context-dependent "
                "incremental value."
            ),
            status="implemented_shadow",
            provider="alternative_me_fear_greed_history",
            historical_evidence={
                "status": "legacy_values_preserved_reconstruction_required",
                "artifact": (
                    "auditorias_motor/"
                    "market_context_historical_cases_v0_1.json"
                ),
                "artifact_sha256": (
                    "d1a49379ae1e5072881a3caa1e1ee67"
                    "b141b3343affb3110bec5abee3d12f672"
                ),
                "legacy_observations_available": 874,
                "reuse_policy": (
                    "preserve_identity_and_raw_value; reconstruct_60_day_"
                    "reference_before_retrospective_comparison"
                ),
            },
        ),
        candidate(
            rule_id="LIB-CAND-COMPRESSION-001",
            name="Volatility-volume compression state",
            family_id="FAMILY-VOLATILITY-X-VOLUME",
            role="interaction",
            formulas=[
                (
                    "atr_rank_60=midrank("
                    "ATR14_t/close_t,previous_60_horizon_endpoints)"
                ),
                (
                    "bb_width_20_2sigma="
                    "4*population_std(close_20)/SMA20"
                ),
                (
                    "compression_vector=(atr_rank_60,"
                    "bb_width_midrank_60,relative_volume,volume_midrank_60)"
                ),
            ],
            inputs=["closed_ohlcv"],
            source_ids=[
                "WILDER_1978",
                "BOLLINGER_2001",
                "CORSI_2009",
            ],
            hypothesis=(
                "Jointly low volatility, band width and relative volume may "
                "condition expiry and subsequent barrier hazards."
            ),
            parents=[
                "M4-RULE-VOLATILITY-RANK-001",
                "LIB-CAND-RELATIVE-VOLUME-001",
            ],
            status="implemented_shadow",
            provider="derived_from_traced_closed_klines_and_parent_rules",
        ),
        candidate(
            rule_id="LIB-CAND-SHOCK-001",
            name="Market shock state",
            family_id="FAMILY-EVENT-RISK",
            role="interaction",
            formulas=[
                "return_robust_z=(return-median)/(1.4826*MAD)",
                "shock_vector=(abs(return_z),atr_rank,spread_rank,liquidation_z)",
            ],
            inputs=[
                "closed_ohlc",
                "spread_history",
                "realized_liquidation_history",
            ],
            source_ids=["NIST_MAD", "BINANCE_USDM_API"],
            hypothesis=(
                "Extreme joint return, volatility, spread and realized "
                "liquidation conditions may alter all competing hazards."
            ),
            status="data_blocked",
            missing_data_behavior=(
                "blocked until a reliable realized-liquidation series exists"
            ),
        ),
        candidate(
            rule_id="LIB-CAND-ABSORPTION-001",
            name="Flow-volume-price absorption interaction",
            family_id="FAMILY-EXECUTED-FLOW-X-PRICE",
            role="interaction",
            formulas=[
                "upper_wick=max(H_H-max(O_H,C_H),0)/(H_H-L_H)",
                "lower_wick=max(min(O_H,C_H)-L_H,0)/(H_H-L_H)",
                (
                    "absorption_vector=(ATI_H,relative_volume,"
                    "log(C_H/O_H)/(ATR14/C_H),flow_opposing_wick_ratio)"
                ),
            ],
            inputs=["closed_ohlcv", "timestamped_aggregate_trades"],
            source_ids=["SILANTYEV_2019", "WILDER_1978"],
            hypothesis=(
                "Strong aggressive flow with weak displacement and an adverse "
                "wick may condition continuation versus reversal."
            ),
            parents=[
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                "LIB-CAND-RELATIVE-VOLUME-001",
            ],
            status="implemented_shadow",
            provider="derived_from_traced_flow_volume_and_closed_klines",
        ),
        candidate(
            rule_id="LIB-CAND-PULLBACK-CONTEXT-001",
            name="Trend pullback context",
            family_id="FAMILY-TREND-X-STRUCTURE-X-FLOW",
            role="interaction",
            formulas=[
                (
                    "pullback_vector=(side_adjusted_ema50_vs_ema200,"
                    "side_adjusted_ema50_slope_atr,"
                    "side_adjusted_extension_atr,relative_volume,"
                    "volume_midrank_60,side_adjusted_ATI_H,"
                    "target_path_level_count,adverse_path_level_count)"
                ),
            ],
            inputs=["closed_ohlcv", "timestamped_aggregate_trades", "plan"],
            source_ids=[
                "NIST_EXPONENTIAL_SMOOTHING",
                "WILDER_1978",
                "SILANTYEV_2019",
            ],
            hypothesis=(
                "A user-proposed plan aligned with a reproducible pullback "
                "context may have different first-barrier behavior."
            ),
            parents=[
                "LIB-CAND-EMA-TREND-001",
                "LIB-CAND-ATR-EXTENSION-001",
                "LIB-CAND-RELATIVE-VOLUME-001",
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
            ],
            status="implemented_shadow",
            provider="composition_of_traced_parent_rules",
        ),
        candidate(
            rule_id="LIB-CAND-LIQUIDATION-ZONE-001",
            name="Observed liquidation-zone distance and mass",
            family_id="FAMILY-LIQUIDATION-OBSERVATION",
            role="contextual",
            formulas=[
                (
                    "distance_from_entry_log_sigma="
                    "log(cluster_price/entry)/sigma_h"
                ),
                (
                    "path_mass_b=sum(notional_j for clusters_j "
                    "between entry and barrier_b)"
                ),
                (
                    "target_path_mass_fraction="
                    "target_path_mass/(target_path_mass+adverse_path_mass)"
                ),
                (
                    "distance_to_barrier_abs_log_sigma="
                    "abs(log(cluster_price/barrier_price))/sigma_h"
                ),
            ],
            inputs=[
                "timestamped_hyperperps_clusters",
                "provider_sample_size",
                "provider_cascade_mass",
                "plan",
                "horizon_volatility",
            ],
            source_ids=[
                "HYPERPERPS_PUBLIC_HEATMAP",
                "HYPERLIQUID_PUBLIC_STATE",
            ],
            hypothesis=(
                "Distance and observed mass of liquidation estimates may "
                "condition barrier behavior; no multi-exchange claim is made."
            ),
            status="implemented_shadow",
            provider=(
                "hyperperps_aggregation_of_hyperliquid_public_positions"
            ),
            historical_evidence={
                "status": "preserved_legacy_test",
                "audit_version": "heatmap-historical-preservation-v0.1",
                "artifact": (
                    "auditorias_motor/heatmap_historical_cases_v0_1.json"
                ),
                "recommendations": 107,
                "observations_available": 104,
                "linked_closed_resolved_operations": 24,
                "minimum_originally_planned": 30,
                "artifact_sha256": (
                    "243101dbf49d380baa123d085113429d4"
                    "aaf63451a7b180b80ad61c721f3f7c4"
                ),
                "reuse_policy": (
                    "preserve_case_identity_only; do_not_reuse_legacy_"
                    "map_read_risk_labels_scores_or_probability_adjustments"
                ),
            },
        ),
        blocking_data_quality_gate(
            rule_id="LIB-CAND-DATA-FRESHNESS-001",
            name="Pre-trade closed-candle freshness gate",
            formulas=[
                "age_ms=analysis_at-latest_closed_candle_timestamp",
                "freshness_limit_ms=selected_interval_ms+60000",
                "fresh=0<=age_ms<=freshness_limit_ms",
            ],
            inputs=[
                "timestamped_closed_klines",
                "analysis_at",
                "selected_interval",
            ],
            required_outputs=[
                "latest_closed_candle_ms",
                "analysis_at_ms",
                "age_ms",
                "freshness_limit_ms",
                "fresh",
            ],
            parameters=[
                {
                    "name": "period_release_grace_ms",
                    "value": 60_000,
                    "origin": "project_phase1_data_contract",
                    "status": "active_deterministic_policy",
                }
            ],
        ),
        blocking_data_quality_gate(
            rule_id="LIB-CAND-CANDLE-INTEGRITY-001",
            name="Closed-candle integrity gate",
            formulas=[
                "missing_count=expected_intervals-observed_unique_intervals",
                "duplicate_count=observations-unique_intervals",
                "gap_count=count(delta_close_time!=selected_interval_ms)",
                (
                    "valid_ohlc=finite_positive_prices and volume>=0 and "
                    "high>=max(open,close) and low<=min(open,close)"
                ),
            ],
            inputs=["timestamped_closed_klines"],
            required_outputs=[
                "required_candle_count",
                "observed_closed_candle_count",
                "missing_count",
                "duplicate_count",
                "gap_count",
                "invalid_ohlc_count",
                "integrity_valid",
            ],
            parameters=[],
        ),
        candidate(
            rule_id="LIB-CAND-CROSS-VENUE-DIVERGENCE-001",
            name="Synchronized cross-venue price divergence gate",
            family_id="FAMILY-DATA-QUALITY",
            role="blocking",
            formulas=[
                "deviation=abs(exchange_price-median_synced_prices)/median_synced_prices",
            ],
            inputs=["synchronized_cross_venue_prices"],
            source_ids=["PROJECT_PHASE1_CONTRACT"],
            hypothesis=(
                "This gate detects a potentially anomalous execution-venue "
                "price and has no directional hypothesis."
            ),
            status="data_blocked",
        ),
    ]


def build_catalog() -> dict:
    m5 = load_json(M5_CONTRACT_PATH)
    candidate_payload = load_json(CANDIDATE_PATH)
    artifact = candidate_payload["coefficient_artifact"]
    specs = {item["rule_id"]: item for item in m5["rules"]}
    rules = [
        baseline_rule(specs[rule_id], BASELINE_METADATA[rule_id])
        for rule_id in BASELINE_RULE_IDS
    ]
    rules.extend(
        runtime_rule(specs[rule_id], ACTIVE_METADATA[rule_id], artifact)
        for rule_id in ACTIVE_PREDICTIVE_RULE_IDS
    )
    rules.extend(
        [
            active_economic_rule(
                specs["M4-RULE-QUOTED-SPREAD-001"],
                provider="binance_usdm_book_ticker",
                superseded_candidate_rule_id=(
                    "LIB-CAND-SPREAD-EXECUTION-001"
                ),
            ),
            active_economic_rule(
                specs["M4-RULE-DEPTH-SWEEP-001"],
                provider="binance_usdm_visible_depth_snapshot",
                superseded_candidate_rule_id=(
                    "LIB-CAND-DEPTH-COVERAGE-001"
                ),
            ),
        ]
    )
    rules.extend(candidate_rules())
    payload = {
        "library_version": LIBRARY_VERSION,
        "status": "master_contract_v0_1",
        "purpose": (
            "Auditable rule library for Phase 1 TP/SL/expiry probability."
        ),
        "governance": {
            "probability_production_changes": "none",
            "new_candidate_weights_authorized": False,
            "learning_may_self_modify_production": False,
            "current_active_predictive_rule_ids": list(
                ACTIVE_PREDICTIVE_RULE_IDS
            ),
            "baseline_rule_ids": list(BASELINE_RULE_IDS),
            "active_economic_rule_ids": list(
                ACTIVE_ECONOMIC_RULE_IDS
            ),
            "data_quality_gate_ids": [
                "LIB-CAND-DATA-FRESHNESS-001",
                "LIB-CAND-CANDLE-INTEGRITY-001",
            ],
        },
        "sources": SOURCES,
        "rules": rules,
        "summary": {
            "rules": len(rules),
            "active_baseline": len(BASELINE_RULE_IDS),
            "active_predictive": len(ACTIVE_PREDICTIVE_RULE_IDS),
            "active_data_quality_gates": 2,
            "active_economic": len(ACTIVE_ECONOMIC_RULE_IDS),
            "implemented_observational": sum(
                rule["lifecycle_status"] == "implemented_shadow"
                for rule in rules
            ),
            "data_blocked": sum(
                rule["lifecycle_status"] == "data_blocked"
                for rule in rules
            ),
        },
    }
    payload["catalog_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    payload = build_catalog()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "path": str(OUTPUT_PATH),
                "summary": payload["summary"],
                "catalog_sha256": payload["catalog_sha256"],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
