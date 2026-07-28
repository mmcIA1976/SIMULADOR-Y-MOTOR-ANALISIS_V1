from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M2_PATH = AUDIT_DIR / "contrato_semantico_m2_v0_1.json"
M4_1_PATH = AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json"
M4_2_PATH = AUDIT_DIR / "catalogo_alcanzabilidad_m4_2_v0_2.json"
M4_3_PATH = AUDIT_DIR / "catalogo_regimen_estructura_mtf_m4_3_v0_2.json"
M4_4_PATH = AUDIT_DIR / "catalogo_contexto_derivados_m4_4_v0_2.json"
M4_5_PATH = AUDIT_DIR / "catalogo_ejecucion_riesgo_m4_5_v0_2.json"
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "catalogo_combinaciones_reconciliacion_m4_6_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_6_combinaciones_reconciliacion_enmienda_v0_2.md"
)

VERSION = "M4.6-combinations-reconciliation-v0.2"
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = ("intraday_short", "intraday_wide", "short_swing")
P0_BLOCKS = (1, 3, 7, 9, 10, 15, 24, 26, 28, 29, 30, 32)

SOURCES = (
    {
        "id": "M2-SEMANTIC-CONTRACT",
        "type": "approved_internal_contract",
        "url": None,
        "supported_claim": (
            "Coherent TP, SL, expiry and pending-entry outcome trees."
        ),
        "does_not_support": "A fitted probability model or decision policy.",
    },
    {
        "id": "M4.1-RECONCILIATION",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "The exact 30-item legacy universe and 17 seed families."
        ),
        "does_not_support": "Legacy points, weights or predictive effects.",
    },
    {
        "id": "M4.2-REACHABILITY",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Exact geometry, volatility scale, reachability and activation "
            "operators."
        ),
        "does_not_support": "Calibrated probabilities.",
    },
    {
        "id": "M4.3-STRUCTURE",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Price-path, MTF, prior-extrema and regime operators and "
            "hypotheses."
        ),
        "does_not_support": "Independent votes or numeric weights.",
    },
    {
        "id": "M4.4-DERIVATIVES",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Aggressor flow, OI, basis, funding and derivatives-context "
            "operators and hypotheses."
        ),
        "does_not_support": "Additive scores or fixed directional signs.",
    },
    {
        "id": "M4.5-EXECUTION-RISK",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Execution, fees, funding cash flow, exposure, payoff and EV "
            "operators separated from market probability."
        ),
        "does_not_support": "A production grade or trading decision.",
    },
    {
        "id": "NIST-INTERACTION-MODELS",
        "type": "official_statistical_handbook",
        "url": (
            "https://www.itl.nist.gov/div898/handbook/pri/section2/"
            "pri243.htm"
        ),
        "supported_claim": (
            "A two-factor interaction can be represented by the product "
            "term x1*x2 alongside main effects."
        ),
        "does_not_support": (
            "Which crypto variables interact, their sign, coefficient or "
            "predictive value."
        ),
    },
    {
        "id": "BIEN-TAYLOR-TIBSHIRANI-2013",
        "type": "primary_statistical_publication",
        "url": "https://doi.org/10.1214/13-AOS1096",
        "supported_claim": (
            "Strong hierarchy retains both main effects when an interaction "
            "term is present."
        ),
        "does_not_support": (
            "The selected project interactions, model family or promotion "
            "threshold."
        ),
    },
)


SEED_TO_RULES = {
    "M4-FAMILY-AGGRESSOR-TRADE-IMBALANCE": [
        "M4-RULE-AGGRESSOR-IMBALANCE-001"
    ],
    "M4-FAMILY-BARRIER-GEOMETRY": ["M4-RULE-PLAN-GEOMETRY-001"],
    "M4-FAMILY-BARRIER-REACHABILITY": [
        "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002"
    ],
    "M4-FAMILY-DEPTH-SLIPPAGE": ["M4-RULE-DEPTH-SWEEP-001"],
    "M4-FAMILY-FUNDING-STATE": ["M4-RULE-FUNDING-STATE-001"],
    "M4-FAMILY-INTERACTION-MATRIX": [],
    "M4-FAMILY-MTF-HIERARCHY": ["M4-RULE-MTF-HIERARCHY-001"],
    "M4-FAMILY-OI-CHANGE": ["M4-RULE-OPEN-INTEREST-CHANGE-001"],
    "M4-FAMILY-PENDING-ACTIVATION": [
        "M4-RULE-PENDING-ACTIVATION-001"
    ],
    "M4-FAMILY-PRICE-OI-STATE": ["M4-RULE-PRICE-OI-STATE-001"],
    "M4-FAMILY-REALIZED-VOLATILITY": [
        "M4-RULE-REALIZED-VOLATILITY-001",
        "M4-RULE-VOLATILITY-RANK-001",
    ],
    "M4-FAMILY-SPREAD": ["M4-RULE-QUOTED-SPREAD-001"],
    "M4-FAMILY-STRUCTURAL-LEVELS": ["M4-RULE-PRIOR-EXTREMA-001"],
    "M4-FAMILY-STRUCTURE-DISPLACEMENT": [
        "M4-RULE-PATH-STRUCTURE-001"
    ],
    "M4-FAMILY-STRUCTURE-SMOOTHER": [
        "M4-RULE-EXPONENTIAL-SMOOTHER-001"
    ],
    "M4-FAMILY-TREND-REGIME": ["M4-RULE-CONTINUOUS-REGIME-001"],
    "M4-FAMILY-VOLATILITY-REGIME": [
        "M4-RULE-VOLATILITY-RANK-001",
        "M4-RULE-CONTINUOUS-REGIME-001",
    ],
}

SEED_TO_HYPOTHESES = {
    "M4-FAMILY-AGGRESSOR-TRADE-IMBALANCE": ["M4-HYP-FLOW-001"],
    "M4-FAMILY-BARRIER-REACHABILITY": [
        "M4-HYP-REACH-001",
        "M4-HYP-REACH-002",
    ],
    "M4-FAMILY-FUNDING-STATE": ["M4-HYP-FUNDING-001"],
    "M4-FAMILY-MTF-HIERARCHY": ["M4-HYP-MTF-001"],
    "M4-FAMILY-OI-CHANGE": ["M4-HYP-OI-001"],
    "M4-FAMILY-PENDING-ACTIVATION": ["M4-HYP-PENDING-001"],
    "M4-FAMILY-PRICE-OI-STATE": ["M4-HYP-PRICE-OI-001"],
    "M4-FAMILY-REALIZED-VOLATILITY": [
        "M4-HYP-REACH-001",
        "M4-HYP-REGIME-001",
        "M4-HYP-REGIME-002",
    ],
    "M4-FAMILY-STRUCTURAL-LEVELS": ["M4-HYP-LEVEL-001"],
    "M4-FAMILY-STRUCTURE-DISPLACEMENT": ["M4-HYP-STRUCTURE-001"],
    "M4-FAMILY-TREND-REGIME": ["M4-HYP-REGIME-002"],
    "M4-FAMILY-VOLATILITY-REGIME": [
        "M4-HYP-REGIME-001",
        "M4-HYP-REGIME-002",
    ],
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_feature_slots() -> list[dict]:
    return [
        {
            "id": "M4-SLOT-REACHABILITY",
            "layer": "market_probability_input",
            "rules": [
                "M4-RULE-PLAN-GEOMETRY-001",
                "M4-RULE-REALIZED-VOLATILITY-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            ],
            "canonical_values": ["z_TP", "z_SL", "b=ln(d_TP/d_SL)"],
            "excluded_as_extra_votes": [
                "d_TP",
                "d_SL",
                "sigma_prev_H",
            ],
            "reason": "They are exact parents of the canonical values.",
        },
        {
            "id": "M4-SLOT-PENDING-ACTIVATION",
            "layer": "market_probability_tree",
            "rules": ["M4-RULE-PENDING-ACTIVATION-001"],
            "canonical_values": ["entry_mode", "z_entry"],
            "excluded_as_extra_votes": [
                "price_vs_entry_points",
                "zone_points",
            ],
            "reason": "Activation is a separate branch, not TP probability.",
        },
        {
            "id": "M4-SLOT-PATH-STRUCTURE",
            "layer": "market_probability_input",
            "rules": [
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-MTF-HIERARCHY-001",
            ],
            "canonical_values": ["SE_H", "SE_2H", "SE_4H"],
            "excluded_as_extra_votes": [
                "E_H=abs(SE_H)",
                "sign labels",
                "MTF agreement label",
            ],
            "reason": "All excluded values are deterministic transforms.",
        },
        {
            "id": "M4-SLOT-PRICE-DISPLACEMENT",
            "layer": "market_interaction_main_effect",
            "rules": [
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-PRICE-OI-STATE-001",
            ],
            "canonical_values": ["D_H"],
            "excluded_as_extra_votes": [
                "D_H copied from POI_H",
                "price displacement points",
            ],
            "reason": "The identical D_H value is supplied once to interactions.",
        },
        {
            "id": "M4-SLOT-PRIOR-EXTREMA",
            "layer": "market_probability_input",
            "rules": ["M4-RULE-PRIOR-EXTREMA-001"],
            "canonical_values": ["target_extreme_between"],
            "excluded_as_extra_votes": [
                "support_label",
                "resistance_label",
                "barrier_points",
            ],
            "reason": "Only the exact prior-H geometric descriptor survives.",
        },
        {
            "id": "M4-SLOT-VOLATILITY-REGIME",
            "layer": "market_interaction_context",
            "rules": [
                "M4-RULE-VOLATILITY-RANK-001",
                "M4-RULE-CONTINUOUS-REGIME-001",
            ],
            "canonical_values": ["q_RV"],
            "excluded_as_extra_votes": [
                "continuous_regime_vector_as_new_signal",
                "volatility_category_points",
            ],
            "reason": "SE_H already belongs to path structure.",
        },
        {
            "id": "M4-SLOT-AGGRESSOR-FLOW",
            "layer": "market_probability_input",
            "rules": ["M4-RULE-AGGRESSOR-IMBALANCE-001"],
            "canonical_values": ["ATI_H"],
            "excluded_as_extra_votes": [
                "CVD proxy",
                "taker bias points",
                "multiple source copies",
            ],
            "reason": "aggTrades, periodic and kline sources are alternatives.",
        },
        {
            "id": "M4-SLOT-OPEN-INTEREST",
            "layer": "market_interaction_context",
            "rules": [
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                "M4-RULE-PRICE-OI-STATE-001",
            ],
            "canonical_values": ["dOI_H"],
            "excluded_as_extra_votes": [
                "POI_H container",
                "OI trend points",
                "OI context points",
            ],
            "reason": "D_H is supplied once by the price-path interaction.",
        },
        {
            "id": "M4-SLOT-BASIS",
            "layer": "market_interaction_context",
            "rules": [
                "M4-RULE-SPOT-FUTURES-BASIS-001",
                "M4-RULE-MARK-INDEX-PREMIUM-001",
            ],
            "canonical_values": [
                "basis_mode=cross_venue:b_mid",
                "basis_mode=mark_index:b_mark_index",
            ],
            "excluded_as_extra_votes": [
                "simultaneous basis modes",
                "executable basis copies as direction votes",
            ],
            "reason": "The two modes are alternatives, never additive votes.",
        },
        {
            "id": "M4-SLOT-FUNDING-STATE",
            "layer": "market_interaction_context",
            "rules": ["M4-RULE-FUNDING-STATE-001"],
            "canonical_values": ["f_last_hour", "L_prev_hour_H"],
            "excluded_as_extra_votes": [
                "funding absolute penalty",
                "funding relative penalty",
            ],
            "reason": "Current and prior realized state stay inside one slot.",
        },
        {
            "id": "M4-SLOT-CURRENT-EXECUTION",
            "layer": "execution_economics",
            "rules": [
                "M4-RULE-QUOTED-SPREAD-001",
                "M4-RULE-DEPTH-SWEEP-001",
            ],
            "canonical_values": [
                "complete sweep: implementation_shortfall",
                "incomplete sweep: unavailable cost plus fill_ratio",
            ],
            "excluded_as_extra_votes": [
                "spread added again to midpoint shortfall",
                "liquidity probability penalty",
            ],
            "reason": "Midpoint shortfall already includes quoted spread.",
        },
        {
            "id": "M4-SLOT-FEES",
            "layer": "execution_economics",
            "rules": ["M4-RULE-FEE-SCENARIOS-001"],
            "canonical_values": ["fee_by_outcome_and_execution_role"],
            "excluded_as_extra_votes": ["universal round_trip_fee"],
            "reason": "Each leg has its own notional and liquidity role.",
        },
        {
            "id": "M4-SLOT-FUNDING-CASHFLOW",
            "layer": "execution_economics",
            "rules": ["M4-RULE-FUNDING-CASHFLOW-001"],
            "canonical_values": ["signed_cashflow_by_realized_or_scenario_event"],
            "excluded_as_extra_votes": ["funding market-direction vote"],
            "reason": "Economic cash flow is not a predictive feature.",
        },
        {
            "id": "M4-SLOT-EXPOSURE",
            "layer": "exposure_risk",
            "rules": ["M4-RULE-PLAN-EXPOSURE-001"],
            "canonical_values": [
                "quantity",
                "gross_reward",
                "gross_risk",
                "risk_fraction_margin",
            ],
            "excluded_as_extra_votes": [
                "risk score",
                "leverage probability effect",
            ],
            "reason": "Exposure scales money, not market path probability.",
        },
        {
            "id": "M4-SLOT-ECONOMIC-EVALUATION",
            "layer": "economic_evaluation",
            "rules": [
                "M4-RULE-NET-PAYOFFS-001",
                "M4-RULE-EXPECTED-VALUE-001",
                "M4-RULE-EVALUATION-READINESS-001",
            ],
            "canonical_values": [
                "net_payoff_by_outcome",
                "EV_when_complete",
                "readiness_statuses",
            ],
            "excluded_as_extra_votes": [
                "grade",
                "confidence score",
                "decision label",
            ],
            "reason": "These are dependent stages, not independent evidence.",
        },
    ]


def build_relation_matrix() -> list[dict]:
    return [
        {
            "id": "M4-REL-001",
            "left": "d_TP,d_SL,sigma_prev_H",
            "right": "z_TP,z_SL,b",
            "relation": "exact_dependency",
            "policy": "use canonical reachability slot; no additive votes",
        },
        {
            "id": "M4-REL-002",
            "left": "E_H",
            "right": "SE_H",
            "relation": "exact_redundancy",
            "policy": "exclude E_H because E_H=abs(SE_H)",
        },
        {
            "id": "M4-REL-003",
            "left": "MTF agreement label",
            "right": "SE_H,SE_2H,SE_4H",
            "relation": "deterministic_redundancy",
            "policy": "retain continuous tuple only",
        },
        {
            "id": "M4-REL-004",
            "left": "R_t=(q_RV,SE_H)",
            "right": "q_RV plus path SE_H",
            "relation": "container_redundancy",
            "policy": "supply q_RV once and SE_H once",
        },
        {
            "id": "M4-REL-005",
            "left": "POI_H=(D_H,dOI_H)",
            "right": "D_H plus dOI_H",
            "relation": "container_redundancy",
            "policy": "supply each value once",
        },
        {
            "id": "M4-REL-006",
            "left": "ATI data sources",
            "right": "ATI_H",
            "relation": "alternative_measurement_sources",
            "policy": "choose one compliant source; never sum copies",
        },
        {
            "id": "M4-REL-007",
            "left": "cross-venue basis",
            "right": "mark-index premium",
            "relation": "alternative_basis_modes",
            "policy": "one basis mode per candidate model",
        },
        {
            "id": "M4-REL-008",
            "left": "DC_H composite",
            "right": "ATI_H,dOI_H,basis,funding",
            "relation": "container_redundancy",
            "policy": "use composite or atoms, never both",
        },
        {
            "id": "M4-REL-009",
            "left": "quoted spread",
            "right": "implementation shortfall from midpoint",
            "relation": "overlapping_execution_cost",
            "policy": "do not add spread when complete shortfall exists",
        },
        {
            "id": "M4-REL-010",
            "left": "funding state",
            "right": "funding cash flow",
            "relation": "shared_raw_data_separate_layers",
            "policy": "state may enter interaction; cash flow enters payoff only",
        },
        {
            "id": "M4-REL-011",
            "left": "entry activation",
            "right": "conditional TP,SL,expiry",
            "relation": "probability_tree_dependency",
            "policy": "compose branches; never add activation to TP",
        },
        {
            "id": "M4-REL-012",
            "left": "market probabilities",
            "right": "execution,exposure,payoffs",
            "relation": "separate_layers",
            "policy": "economic inputs cannot change market probability",
        },
        {
            "id": "M4-REL-013",
            "left": "interaction x_i*x_j",
            "right": "main effects x_i,x_j",
            "relation": "strong_hierarchy",
            "policy": "an interaction requires both main effects",
        },
        {
            "id": "M4-REL-014",
            "left": "legacy contradiction count",
            "right": "preregistered interactions",
            "relation": "replacement",
            "policy": "retire count; preserve exact state and interactions",
        },
        {
            "id": "M4-REL-015",
            "left": "RV_prev_H,sigma_prev_H",
            "right": "q_RV",
            "relation": "shared_raw_history_different_roles",
            "policy": (
                "absolute scale may build reachability and rank may condition "
                "interactions; neither is an additive vote"
            ),
        },
        {
            "id": "M4-REL-016",
            "left": "D_H from path structure",
            "right": "D_H inside POI_H",
            "relation": "exact_redundancy",
            "policy": "use M4-SLOT-PRICE-DISPLACEMENT once",
        },
    ]


def combination(
    *,
    combination_id: str,
    name: str,
    layer: str,
    parent_slots: list[str],
    parent_rules: list[str],
    parent_hypotheses: list[str],
    operator: list[str],
    exclusions: list[str],
    conditions: list[str],
    null_statement: str,
) -> dict:
    return {
        "id": combination_id,
        "version": "0.1",
        "name": name,
        "status": "preregistered_unverified",
        "layer": layer,
        "symbols": list(SYMBOLS),
        "horizons": list(HORIZONS),
        "parent_slots": parent_slots,
        "parent_rules": parent_rules,
        "parent_hypotheses": parent_hypotheses,
        "operator_and_order": operator,
        "mutually_exclusive_or_duplicate_inputs": exclusions,
        "activation_and_block_conditions": conditions,
        "source_and_exact_supported_claim": [
            {
                "source_id": "M4.1-RECONCILIATION",
                "claim": (
                    "Legacy evidence families and effects must be reconciled "
                    "without inheriting points."
                ),
            },
            {
                "source_id": "NIST-INTERACTION-MODELS",
                "claim": (
                    "Declared product terms are explicit two-factor "
                    "interaction operators."
                ),
            },
            {
                "source_id": "BIEN-TAYLOR-TIBSHIRANI-2013",
                "claim": "Interaction terms retain both main effects.",
            },
        ],
        "claims_not_supported_by_source": [
            "That this combination predicts crypto outcomes.",
            "Any coefficient, sign, threshold or probability improvement.",
        ],
        "double_counting_control": exclusions,
        "missing_data_behavior": (
            "Block the combination when a required parent is unavailable; "
            "do not replace it with zero or a neutral value."
        ),
        "trace_output": [
            "combination id and version",
            "selected basis and measurement modes",
            "canonical parent slot ids",
            "main and interaction term ids after deduplication",
            "blocked or available status with reason",
        ],
        "expected_incremental_effect": (
            "unknown sign and magnitude; candidate incremental information "
            "only if later independent validation rejects the null"
        ),
        "null_or_refutation_statement": null_statement,
        "refutation_suspension_or_withdrawal": (
            "Reject promotion if later independent validation does not "
            "satisfy the preregistered M8 improvement and calibration gates; "
            "suspend on contract or source-semantic failure."
        ),
        "lifecycle_status": "preregistered_unverified_not_implemented",
        "direct_probability_effect_authorized": False,
        "numeric_weight_authorized": False,
        "production_authorized": False,
        "m6_model_authorized": False,
    }


def build_combinations() -> list[dict]:
    return [
        combination(
            combination_id="M4-COMB-REACHABILITY-BASE-001",
            name="Base geometrica de primera barrera",
            layer="market_probability_candidate",
            parent_slots=["M4-SLOT-REACHABILITY"],
            parent_rules=[
                "M4-RULE-HORIZON-SAMPLING-001",
                "M4-RULE-PLAN-GEOMETRY-001",
                "M4-RULE-LOG-RETURNS-001",
                "M4-RULE-REALIZED-VOLATILITY-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            ],
            parent_hypotheses=["M4-HYP-REACH-001", "M4-HYP-REACH-002"],
            operator=["X_reach=(z_TP,z_SL,b)"],
            exclusions=["raw parents cannot be extra votes"],
            conditions=["valid geometry", "complete previous H", "sigma>0"],
            null_statement=(
                "Reachability adds no calibrated first-barrier information "
                "beyond horizon and outcome base rates."
            ),
        ),
        combination(
            combination_id="M4-COMB-PENDING-TREE-001",
            name="Arbol de activacion y resultado condicionado",
            layer="market_probability_tree",
            parent_slots=[
                "M4-SLOT-PENDING-ACTIVATION",
                "M4-SLOT-REACHABILITY",
            ],
            parent_rules=[
                "M4-RULE-PENDING-ACTIVATION-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            ],
            parent_hypotheses=["M4-HYP-PENDING-001"],
            operator=[
                "market: P(no_entry)=0",
                "pending: P(no_entry)=1-P(activate)",
                "P(k)=P(activate)*P(k|activate), k in TP,SL,expiry",
            ],
            exclusions=["market and pending modes are mutually exclusive"],
            conditions=[
                "entry mode immutable",
                "pending trigger valid and unsatisfied at analysis time",
            ],
            null_statement=(
                "z_entry adds no activation information beyond the pending "
                "base rate and horizon."
            ),
        ),
        combination(
            combination_id="M4-COMB-STRUCTURE-001",
            name="Estructura MTF, extremo previo y regimen",
            layer="market_probability_candidate",
            parent_slots=[
                "M4-SLOT-PATH-STRUCTURE",
                "M4-SLOT-PRIOR-EXTREMA",
                "M4-SLOT-VOLATILITY-REGIME",
            ],
            parent_rules=[
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-MTF-HIERARCHY-001",
                "M4-RULE-PRIOR-EXTREMA-001",
                "M4-RULE-VOLATILITY-RANK-001",
                "M4-RULE-CONTINUOUS-REGIME-001",
            ],
            parent_hypotheses=[
                "M4-HYP-STRUCTURE-001",
                "M4-HYP-LEVEL-001",
                "M4-HYP-MTF-001",
                "M4-HYP-REGIME-001",
                "M4-HYP-REGIME-002",
            ],
            operator=[
                "main=(SE_H,SE_2H,SE_4H,target_extreme_between,q_RV)",
                "interaction=(q_RV*SE_H)",
                "X_structure=main||interaction",
            ],
            exclusions=[
                "E_H excluded because E_H=abs(SE_H)",
                "MTF agreement label excluded",
                "continuous regime container excluded",
                "EMA smoother excluded until alpha is separately approved",
            ],
            conditions=[
                "all windows closed and aligned",
                "60 prior non-overlapping H volatility windows",
                "strong hierarchy retains q_RV and SE_H",
            ],
            null_statement=(
                "X_structure adds no out-of-sample information beyond "
                "X_reach."
            ),
        ),
        combination(
            combination_id="M4-COMB-FLOW-001",
            name="Flujo agresor condicionado por estructura",
            layer="market_probability_candidate",
            parent_slots=[
                "M4-SLOT-REACHABILITY",
                "M4-SLOT-PATH-STRUCTURE",
                "M4-SLOT-VOLATILITY-REGIME",
                "M4-SLOT-AGGRESSOR-FLOW",
            ],
            parent_rules=[
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-VOLATILITY-RANK-001",
            ],
            parent_hypotheses=["M4-HYP-FLOW-001"],
            operator=[
                "main=(ATI_H,SE_H,q_RV)",
                "interactions=(ATI_H*SE_H,ATI_H*q_RV)",
            ],
            exclusions=["one ATI source only"],
            conditions=[
                "complete exact-H flow coverage",
                "strong hierarchy retains all main effects",
            ],
            null_statement=(
                "ATI_H and its preregistered interactions add no "
                "out-of-sample information beyond controls."
            ),
        ),
        combination(
            combination_id="M4-COMB-PRICE-OI-001",
            name="Estado continuo precio-OI",
            layer="market_probability_candidate",
            parent_slots=[
                "M4-SLOT-PRICE-DISPLACEMENT",
                "M4-SLOT-PATH-STRUCTURE",
                "M4-SLOT-OPEN-INTEREST",
                "M4-SLOT-AGGRESSOR-FLOW",
            ],
            parent_rules=[
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                "M4-RULE-PRICE-OI-STATE-001",
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
            ],
            parent_hypotheses=[
                "M4-HYP-OI-001",
                "M4-HYP-PRICE-OI-001",
            ],
            operator=[
                "main=(D_H,dOI_H,ATI_H)",
                "interactions=(D_H*dOI_H,ATI_H*dOI_H)",
            ],
            exclusions=[
                "POI_H container is not an extra input",
                "OI cannot be split into long and short labels",
            ],
            conditions=[
                "exact-H OI endpoints",
                "complete flow if ATI interaction is evaluated",
                "strong hierarchy retains all main effects",
            ],
            null_statement=(
                "dOI_H and its preregistered interactions add no "
                "out-of-sample information beyond price and flow."
            ),
        ),
        combination(
            combination_id="M4-COMB-DERIVATIVES-001",
            name="Contexto conjunto de derivados",
            layer="market_probability_candidate",
            parent_slots=[
                "M4-SLOT-AGGRESSOR-FLOW",
                "M4-SLOT-OPEN-INTEREST",
                "M4-SLOT-BASIS",
                "M4-SLOT-FUNDING-STATE",
            ],
            parent_rules=[
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                "M4-RULE-DERIVATIVES-CONTEXT-001",
                "M4-RULE-SPOT-FUTURES-BASIS-001",
                "M4-RULE-MARK-INDEX-PREMIUM-001",
                "M4-RULE-FUNDING-STATE-001",
            ],
            parent_hypotheses=[
                "M4-HYP-OI-001",
                "M4-HYP-BASIS-001",
                "M4-HYP-PREMIUM-001",
                "M4-HYP-FUNDING-001",
                "M4-HYP-DERIVATIVES-001",
            ],
            operator=[
                "main=(ATI_H,dOI_H,basis_value,f_last_hour)",
                "interactions=(ATI_H*dOI_H,basis_value*ATI_H,"
                "basis_value*dOI_H,basis_value*f_last_hour)",
                "X_derivatives=main||interactions",
            ],
            exclusions=[
                "exactly one basis_mode",
                "DC_H container cannot be added beside its atoms",
                "funding cash flow cannot enter this predictive vector",
            ],
            conditions=[
                "synchronized and fresh observations",
                "strong hierarchy retains all interaction main effects",
            ],
            null_statement=(
                "X_derivatives adds no out-of-sample information beyond "
                "the corresponding marginal controls."
            ),
        ),
        combination(
            combination_id="M4-COMB-FULL-MARKET-001",
            name="Candidato completo de estado de mercado",
            layer="market_probability_candidate",
            parent_slots=[
                "M4-SLOT-REACHABILITY",
                "M4-SLOT-PATH-STRUCTURE",
                "M4-SLOT-PRICE-DISPLACEMENT",
                "M4-SLOT-PRIOR-EXTREMA",
                "M4-SLOT-VOLATILITY-REGIME",
                "M4-SLOT-AGGRESSOR-FLOW",
                "M4-SLOT-OPEN-INTEREST",
                "M4-SLOT-BASIS",
                "M4-SLOT-FUNDING-STATE",
            ],
            parent_rules=[
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-MTF-HIERARCHY-001",
                "M4-RULE-PRIOR-EXTREMA-001",
                "M4-RULE-VOLATILITY-RANK-001",
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                "M4-RULE-PRICE-OI-STATE-001",
                "M4-RULE-SPOT-FUTURES-BASIS-001",
                "M4-RULE-MARK-INDEX-PREMIUM-001",
                "M4-RULE-FUNDING-STATE-001",
                "M4-RULE-DERIVATIVES-CONTEXT-001",
            ],
            parent_hypotheses=[
                "M4-HYP-STRUCTURE-001",
                "M4-HYP-LEVEL-001",
                "M4-HYP-MTF-001",
                "M4-HYP-REGIME-001",
                "M4-HYP-REGIME-002",
                "M4-HYP-FLOW-001",
                "M4-HYP-OI-001",
                "M4-HYP-PRICE-OI-001",
                "M4-HYP-BASIS-001",
                "M4-HYP-PREMIUM-001",
                "M4-HYP-FUNDING-001",
                "M4-HYP-DERIVATIVES-001",
            ],
            operator=[
                "X_full=ordered_unique(X_reach||X_structure||X_flow||"
                "X_price_oi||X_derivatives)",
                "ordered_unique removes every repeated main or interaction "
                "term by canonical term id",
            ],
            exclusions=[
                "no composite beside its atomic members",
                "no label beside its continuous parents",
                "no economic or execution feature",
            ],
            conditions=[
                "all selected slots available under M3 contracts",
                "missing required input blocks the candidate; no neutral fill",
            ],
            null_statement=(
                "The full candidate has no independently validated "
                "probabilistic improvement over the nested candidates."
            ),
        ),
        combination(
            combination_id="M4-COMB-ECONOMIC-EVALUATION-001",
            name="Composicion economica posterior a probabilidad",
            layer="economic_evaluation",
            parent_slots=[
                "M4-SLOT-CURRENT-EXECUTION",
                "M4-SLOT-FEES",
                "M4-SLOT-FUNDING-CASHFLOW",
                "M4-SLOT-EXPOSURE",
                "M4-SLOT-ECONOMIC-EVALUATION",
            ],
            parent_rules=[
                "M4-RULE-DEPTH-SWEEP-001",
                "M4-RULE-FEE-SCENARIOS-001",
                "M4-RULE-FUNDING-CASHFLOW-001",
                "M4-RULE-PLAN-EXPOSURE-001",
                "M4-RULE-NET-PAYOFFS-001",
                "M4-RULE-EXPECTED-VALUE-001",
            ],
            parent_hypotheses=[],
            operator=[
                "payoff_k=gross_k-fee_k-IS_k+funding_k",
                "EV=sum(P_k*payoff_k)",
                "economic evaluation occurs after market probabilities",
            ],
            exclusions=[
                "execution and leverage cannot enter market probability",
                "spread is not added when midpoint shortfall exists",
                "one cost cannot be copied across all outcomes",
            ],
            conditions=[
                "M6 coherent probabilities",
                "complete payoff components per outcome",
                "account risk remains separately required for decisions",
            ],
            null_statement=(
                "Not a predictive hypothesis; unavailable inputs block the "
                "economic result."
            ),
        ),
    ]


def build_legacy_reconciliation(
    rows: list[dict],
    known_rule_ids: set[str],
    known_hypothesis_ids: set[str],
) -> list[dict]:
    special = {
        "IND-EMA200-FALLBACK": (
            "retired_without_replacement",
            "Fallback period has no approved technical or predictive basis.",
        ),
        "SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT": (
            "deferred_to_m10",
            "Parent block remains P1 and cannot enter the P0 core.",
        ),
        "SCORE-TECHNICAL_ENTRY_TIMING_PENALTY": (
            "retired_without_replacement",
            "Opaque aggregate cannot be traced to one formal observation.",
        ),
        "SCORE-RISK_CALIBRATION_TP_ADJUSTMENT": (
            "retired_without_replacement",
            "Learning-derived adjustment remains excluded from M4.",
        ),
        "SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT": (
            "retired_without_replacement",
            "Learning-derived adjustment remains excluded from M4.",
        ),
        "SCORE-CONTRADICTION_PENALTY": (
            "replaced_by_preregistered_combinations",
            "Contradiction counts are replaced by preserved states and exact "
            "interaction terms.",
        ),
    }
    result = []
    for row in rows:
        rule_ids = sorted(
            {
                rule_id
                for family_id in row["target_rule_families"]
                for rule_id in SEED_TO_RULES[family_id]
            }
        )
        hypothesis_ids = sorted(
            {
                hypothesis_id
                for family_id in row["target_rule_families"]
                for hypothesis_id in SEED_TO_HYPOTHESES.get(family_id, [])
            }
        )
        if not set(rule_ids).issubset(known_rule_ids):
            raise ValueError(f"unknown_reconciled_rule:{row['current_rule_id']}")
        if not set(hypothesis_ids).issubset(known_hypothesis_ids):
            raise ValueError(
                f"unknown_reconciled_hypothesis:{row['current_rule_id']}"
            )
        if row["current_rule_id"] in special:
            final_status, reason = special[row["current_rule_id"]]
        elif rule_ids:
            final_status = "reconciled_to_formal_cards_without_legacy_effect"
            reason = (
                "Legacy points are retired; listed cards and hypotheses "
                "preserve only auditable definitions or candidates."
            )
        else:
            raise ValueError(f"unreconciled_legacy_row:{row['current_rule_id']}")
        result.append(
            {
                "current_rule_id": row["current_rule_id"],
                "m4_1_disposition": row["disposition"],
                "seed_families": row["target_rule_families"],
                "formal_rule_ids": rule_ids,
                "formal_hypothesis_ids": hypothesis_ids,
                "final_status": final_status,
                "reason": reason,
                "legacy_points_or_weights_authorized": False,
                "production_modified": False,
            }
        )
    return result


def build_block_coverage() -> list[dict]:
    return [
        {
            "block": 1,
            "name": "Estructura del precio",
            "rules": [
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-PRIOR-EXTREMA-001",
            ],
        },
        {
            "block": 3,
            "name": "Multi-timeframe",
            "rules": ["M4-RULE-MTF-HIERARCHY-001"],
        },
        {
            "block": 7,
            "name": "Order flow",
            "rules": ["M4-RULE-AGGRESSOR-IMBALANCE-001"],
        },
        {
            "block": 9,
            "name": "Open interest",
            "rules": [
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                "M4-RULE-PRICE-OI-STATE-001",
            ],
        },
        {
            "block": 10,
            "name": "Funding",
            "rules": [
                "M4-RULE-FUNDING-STATE-001",
                "M4-RULE-FUNDING-CASHFLOW-001",
            ],
        },
        {
            "block": 15,
            "name": "Spot contra futuros",
            "rules": [
                "M4-RULE-SPOT-FUTURES-BASIS-001",
                "M4-RULE-MARK-INDEX-PREMIUM-001",
            ],
        },
        {
            "block": 24,
            "name": "Regimen",
            "rules": [
                "M4-RULE-VOLATILITY-RANK-001",
                "M4-RULE-CONTINUOUS-REGIME-001",
            ],
        },
        {
            "block": 26,
            "name": "Estadistica, volatilidad y alcanzabilidad",
            "rules": [
                "M4-RULE-HORIZON-SAMPLING-001",
                "M4-RULE-LOG-RETURNS-001",
                "M4-RULE-REALIZED-VOLATILITY-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            ],
        },
        {
            "block": 28,
            "name": "Probabilidad TP/SL",
            "rules": [
                "M4-RULE-PLAN-GEOMETRY-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
                "M4-RULE-PENDING-ACTIVATION-001",
            ],
            "status": "inputs_defined_probability_integration_waits_for_m6",
        },
        {
            "block": 29,
            "name": "Ejecucion y costes",
            "rules": [
                "M4-RULE-QUOTED-SPREAD-001",
                "M4-RULE-DEPTH-SWEEP-001",
                "M4-RULE-FEE-SCENARIOS-001",
                "M4-RULE-FUNDING-CASHFLOW-001",
            ],
        },
        {
            "block": 30,
            "name": "Gestion de riesgo",
            "rules": [
                "M4-RULE-PLAN-EXPOSURE-001",
                "M4-RULE-EVALUATION-READINESS-001",
            ],
            "status": "plan_risk_defined_account_risk_blocked",
        },
        {
            "block": 32,
            "name": "Evaluacion del rendimiento",
            "rules": [
                "M4-RULE-NET-PAYOFFS-001",
                "M4-RULE-EXPECTED-VALUE-001",
            ],
            "status": "operator_defined_ev_waits_for_m6_and_complete_costs",
        },
    ]


def validate_combinations(
    combinations: list[dict],
    slot_ids: set[str],
    known_rule_ids: set[str],
    known_hypothesis_ids: set[str],
) -> None:
    ids = [item["id"] for item in combinations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_combination_id")
    source_ids = {source["id"] for source in SOURCES}
    for item in combinations:
        if not set(item["parent_slots"]).issubset(slot_ids):
            raise ValueError(f"unknown_slot:{item['id']}")
        if not set(item["parent_rules"]).issubset(known_rule_ids):
            raise ValueError(f"unknown_rule:{item['id']}")
        if not set(item["parent_hypotheses"]).issubset(known_hypothesis_ids):
            raise ValueError(f"unknown_hypothesis:{item['id']}")
        if (
            item["direct_probability_effect_authorized"]
            or item["numeric_weight_authorized"]
            or item["production_authorized"]
            or item["m6_model_authorized"]
        ):
            raise ValueError(f"unauthorized_combination:{item['id']}")
        if not item["operator_and_order"]:
            raise ValueError(f"missing_operator:{item['id']}")
        if not item["mutually_exclusive_or_duplicate_inputs"]:
            raise ValueError(f"missing_exclusions:{item['id']}")
        if not item["null_or_refutation_statement"]:
            raise ValueError(f"missing_null:{item['id']}")
        used_sources = {
            source["source_id"]
            for source in item["source_and_exact_supported_claim"]
        }
        if not used_sources.issubset(source_ids):
            raise ValueError(f"unknown_combination_source:{item['id']}")
        for field in (
            "claims_not_supported_by_source",
            "double_counting_control",
            "missing_data_behavior",
            "trace_output",
            "refutation_suspension_or_withdrawal",
            "lifecycle_status",
        ):
            if not item[field]:
                raise ValueError(f"missing_{field}:{item['id']}")


def build_catalog() -> dict:
    m2 = read_json(M2_PATH)
    m4_1 = read_json(M4_1_PATH)
    subcatalogs = [
        read_json(M4_2_PATH),
        read_json(M4_3_PATH),
        read_json(M4_4_PATH),
        read_json(M4_5_PATH),
    ]
    if m4_1["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_1_not_completed")
    expected_next = ("M4.3", "M4.4", "M4.5", "M4.6")
    for subcatalog, next_phase in zip(subcatalogs, expected_next):
        if subcatalog["status"] != (
            "completed_internal_milestone_m4_still_in_progress"
        ):
            raise ValueError(f"{subcatalog['subphase']}_not_completed")
        if subcatalog["scope"]["m4_next_subphase"] != next_phase:
            raise ValueError(f"{subcatalog['subphase']}_next_invalid")

    all_rules = [
        {
            "id": rule["id"],
            "source_subphase": subcatalog["subphase"],
            "direct_probability_effect_authorized": rule[
                "direct_probability_effect_authorized"
            ],
            "numeric_weight_authorized": rule["numeric_weight_authorized"],
            "production_authorized": rule["production_authorized"],
        }
        for subcatalog in subcatalogs
        for rule in subcatalog["rules"]
    ]
    rule_ids = [rule["id"] for rule in all_rules]
    if len(rule_ids) != 27 or len(rule_ids) != len(set(rule_ids)):
        raise ValueError("formal_rule_universe_must_be_27_unique")
    if any(
        rule["direct_probability_effect_authorized"]
        or rule["numeric_weight_authorized"]
        or rule["production_authorized"]
        for rule in all_rules
    ):
        raise ValueError("upstream_unauthorized_effect")

    all_hypotheses = [
        hypothesis
        for subcatalog in subcatalogs
        for hypothesis in subcatalog["preregistered_hypotheses"]
    ]
    hypothesis_ids = [item["id"] for item in all_hypotheses]
    if len(hypothesis_ids) != 15 or len(hypothesis_ids) != len(
        set(hypothesis_ids)
    ):
        raise ValueError("hypothesis_universe_must_be_15_unique")

    seed_ids = {
        item["family_id"] for item in m4_1["target_family_seed_registry"]
    }
    if seed_ids != set(SEED_TO_RULES):
        raise ValueError("seed_mapping_not_exact")

    slots = build_feature_slots()
    slot_ids = {slot["id"] for slot in slots}
    combinations = build_combinations()
    validate_combinations(
        combinations,
        slot_ids,
        set(rule_ids),
        set(hypothesis_ids),
    )
    reconciliation = build_legacy_reconciliation(
        m4_1["rows"],
        set(rule_ids),
        set(hypothesis_ids),
    )
    if len(reconciliation) != 30:
        raise ValueError("legacy_reconciliation_must_be_30")
    block_coverage = build_block_coverage()
    if {item["block"] for item in block_coverage} != set(P0_BLOCKS):
        raise ValueError("p0_block_coverage_not_exact")
    if any(
        not set(item["rules"]).issubset(set(rule_ids))
        for item in block_coverage
    ):
        raise ValueError("p0_block_unknown_rule")

    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.6",
        "status": "completed_internal_milestone_m4_still_in_progress",
        "date": "2026-07-27",
        "scope": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "p0_blocks": list(P0_BLOCKS),
            "upstream_formal_rules": len(all_rules),
            "upstream_hypotheses": len(all_hypotheses),
            "feature_slots": len(slots),
            "relations": 16,
            "preregistered_combinations": len(combinations),
            "legacy_elements_reconciled": len(reconciliation),
            "direct_probability_effects": 0,
            "numeric_weights": 0,
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m5_started": False,
            "m4_next_subphase": "M4.7",
        },
        "governance_contract": {
            "one_canonical_value_per_slot": True,
            "labels_beside_continuous_parents_allowed": False,
            "containers_beside_atomic_members_allowed": False,
            "alternative_sources_additive_allowed": False,
            "strong_hierarchy_required_for_interactions": True,
            "missing_feature_neutral_imputation_allowed": False,
            "execution_or_exposure_in_market_probability_allowed": False,
            "combination_search_after_results_allowed": False,
            "probability_model_defined": False,
            "weights_defined": False,
            "promotion_threshold_defined": False,
        },
        "amendment": {
            "supersedes_version": "M4.6-combinations-reconciliation-v0.1",
            "reason": (
                "Propagate amended M4.2-M4.5 contracts and the renamed "
                "normalized barrier geometry rule without changing any "
                "predictive authorization."
            ),
            "production_effect": False,
        },
        "sources": list(SOURCES),
        "upstream_rules": all_rules,
        "upstream_hypotheses": all_hypotheses,
        "feature_slots": slots,
        "relation_matrix": build_relation_matrix(),
        "preregistered_combinations": combinations,
        "legacy_reconciliation": reconciliation,
        "p0_block_coverage": block_coverage,
        "unresolved_for_later_phases": [
            {
                "item": "probability_link_and_calibration",
                "phase": "M6",
                "reason": "M4 defines inputs and combinations, not coefficients.",
            },
            {
                "item": "software_implementation",
                "phase": "M5",
                "reason": "Production remains frozen through M4.",
            },
            {
                "item": "mathematical_and_software_verification",
                "phase": "M7",
                "reason": "Requires the implemented M5-M6 candidate.",
            },
            {
                "item": "independent_empirical_validation",
                "phase": "M8",
                "reason": "Requires preregistered metrics and temporal holdout.",
            },
            {
                "item": "account_liquidation_and_risk_policy",
                "phase": "M5_or_later",
                "reason": (
                    "Equity, margin mode and maintenance brackets are not in "
                    "the approved P0 data contract."
                ),
            },
            {
                "item": "grade_and_decision_policy",
                "phase": "after_M8",
                "reason": "No validated governance thresholds exist.",
            },
        ],
        "summary": {
            "rules_reconciled": len(all_rules),
            "hypotheses_reconciled": len(all_hypotheses),
            "legacy_reconciled": len(reconciliation),
            "seed_families_reconciled": len(seed_ids),
            "p0_blocks_reconciled": len(block_coverage),
            "combinations_preregistered": len(combinations),
            "unresolved_legacy_elements": sum(
                1
                for row in reconciliation
                if row["final_status"] not in {
                    "reconciled_to_formal_cards_without_legacy_effect",
                    "retired_without_replacement",
                    "deferred_to_m10",
                    "replaced_by_preregistered_combinations",
                }
            ),
            "probability_effects_authorized": 0,
            "weights_authorized": 0,
            "production_modified": False,
        },
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in (
                ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
                M2_PATH,
                M4_1_PATH,
                M4_2_PATH,
                M4_3_PATH,
                M4_4_PATH,
                M4_5_PATH,
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "governance_contract": payload["governance_contract"],
                "sources": payload["sources"],
                "feature_slots": payload["feature_slots"],
                "relation_matrix": payload["relation_matrix"],
                "preregistered_combinations": payload[
                    "preregistered_combinations"
                ],
                "legacy_reconciliation": payload["legacy_reconciliation"],
                "p0_block_coverage": payload["p0_block_coverage"],
                "unresolved_for_later_phases": payload[
                    "unresolved_for_later_phases"
                ],
            }
        )
    )
    return payload


def render_report(catalog: dict) -> str:
    lines = [
        "# M4.6 - Combinaciones, doble conteo y reconciliacion final",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADA INTERNAMENTE; M4 SIGUE EN CURSO",
        "",
        "## 1. Universo reconciliado",
        "",
        f"- {catalog['summary']['rules_reconciled']}/27 reglas formales.",
        f"- {catalog['summary']['hypotheses_reconciled']}/15 hipotesis.",
        f"- {catalog['summary']['legacy_reconciled']}/30 elementos antiguos.",
        f"- {catalog['summary']['seed_families_reconciled']}/17 familias semilla.",
        f"- {catalog['summary']['p0_blocks_reconciled']}/12 bloques P0.",
        f"- {catalog['summary']['combinations_preregistered']} combinaciones.",
        "- 0 probabilidades, pesos, puntos o efectos productivos.",
        "",
        "## 2. Regla contra doble conteo",
        "",
        "Cada dato ocupa un unico slot canonico. No pueden sumarse:",
        "",
        "- valores derivados junto a sus padres como votos independientes;",
        "- etiquetas junto a los valores continuos que las producen;",
        "- un vector contenedor junto a sus componentes;",
        "- fuentes alternativas de la misma medida;",
        "- spread y shortfall desde midpoint para la misma ejecucion;",
        "- variables economicas o de exposicion a la probabilidad de mercado.",
        "",
        "## 3. Interacciones",
        "",
        "- Toda interaccion `x_i*x_j` conserva `x_i` y `x_j`.",
        "- El signo y magnitud de cualquier efecto siguen desconocidos.",
        "- Las combinaciones quedan fijadas antes de observar resultados.",
        "- M6 debera definir el modelo probabilistico y sus coeficientes.",
        "- M8 debera contrastar cada incremento en datos independientes.",
        "",
        "## 4. Combinaciones prerregistradas",
        "",
        "| ID | Capa | Estado |",
        "|---|---|---|",
    ]
    for item in catalog["preregistered_combinations"]:
        lines.append(
            f"| `{item['id']}` | {item['layer']} | "
            "no verificada, sin peso |"
        )
    lines.extend(
        [
            "",
            "## 5. Sustitucion de contradicciones",
            "",
            "El antiguo `SCORE-CONTRADICTION_PENALTY` queda retirado. Un",
            "estado mixto se conserva como dato; solo las interacciones",
            "prerregistradas pueden estudiar si una variable condiciona a otra.",
            "",
            "## 6. Pendiente",
            "",
        ]
    )
    for item in catalog["unresolved_for_later_phases"]:
        lines.append(
            f"- `{item['item']}` -> {item['phase']}: {item['reason']}"
        )
    lines.extend(
        [
            "",
            "## 7. Siguiente paso",
            "",
            "`M4.7`: reproducibilidad completa y revision del propietario.",
            "M4 no se cierra sin aprobacion expresa.",
            "",
            "SHA-256 del payload canonico de gobierno y reconciliacion: "
            f"`{catalog['canonical_payload_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            raise SystemExit(f"Generated artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    catalog = build_catalog()
    write_or_check(
        args.output,
        json.dumps(catalog, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(catalog), args.check)


if __name__ == "__main__":
    main()
