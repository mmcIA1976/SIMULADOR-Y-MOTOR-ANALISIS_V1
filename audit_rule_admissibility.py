from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from audit_historical_rule_impact import DIRECT_ABLATION_UNITS
from audit_rule_provenance import SOURCES


ROOT = Path(__file__).resolve().parent
AUDIT_VERSION = "E1.5.1-v0.1"
DEFAULT_MATRIX_PATH = ROOT / "auditorias_motor" / "matriz_admisibilidad_reglas_v0_1.json"
DEFAULT_REPORT_PATH = ROOT / "auditorias_motor" / "informe_admisibilidad_reglas.md"
IMPACT_PATH = ROOT / "auditorias_motor" / "impacto_historico_reglas_v0_1.json"

RELIABILITY_TIERS = {
    "R0_data_definition": "Dato con definicion oficial; no implica poder predictivo.",
    "R1_standard_calculation": "Calculo estandar fiel; no implica senal predictiva.",
    "R2_research_hypothesis": "Hipotesis investigable con respaldo conceptual externo.",
    "R3_internal_provisional": "Indicio interno no independiente y aun insuficiente.",
    "R4_temporally_validated": "Supera validacion temporal independiente.",
    "R5_production_authorized": "Validada, calibrada y autorizada para produccion.",
    "RX_blocked": "Formula actual bloqueada por incoherencia, duplicidad o falta de respaldo.",
}

PREDICTIVE_GATE_NAMES = (
    "bounded_source_claim",
    "implementation_fidelity",
    "mathematical_coherence",
    "complete_trace",
    "incremental_ablation",
    "temporal_holdout",
    "cross_pair_validation",
    "horizon_validation",
    "probability_calibration",
    "sufficient_sample",
)


def gates(
    *,
    bounded_source_claim: bool,
    implementation_fidelity: bool = False,
    mathematical_coherence: bool = False,
    complete_trace: bool = False,
    incremental_ablation: bool = False,
    temporal_holdout: bool = False,
    cross_pair_validation: bool = False,
    horizon_validation: bool = False,
    probability_calibration: bool = False,
    sufficient_sample: bool = False,
) -> dict:
    return {
        "bounded_source_claim": bounded_source_claim,
        "implementation_fidelity": implementation_fidelity,
        "mathematical_coherence": mathematical_coherence,
        "complete_trace": complete_trace,
        "incremental_ablation": incremental_ablation,
        "temporal_holdout": temporal_holdout,
        "cross_pair_validation": cross_pair_validation,
        "horizon_validation": horizon_validation,
        "probability_calibration": probability_calibration,
        "sufficient_sample": sufficient_sample,
    }


def rule(
    *,
    rule_id: str,
    name: str,
    layer: str,
    kind: str,
    formula: str,
    implementation_refs: list[str],
    source_ids: list[str],
    published_support: str,
    transfer_limit: str,
    exact_formula_support: str,
    implementation_fidelity: str,
    predictive_validation: str,
    coherence: str,
    traceability: str,
    reliability_tier: str,
    current_decision: str,
    challenger_admission: str,
    blockers: list[str],
    gate_results: dict,
    horizons: list[str] | None = None,
    pair_scope: str = "all_supported_pairs_unvalidated",
    e1_3_findings: list[str] | None = None,
    e1_4_impact: dict | None = None,
) -> dict:
    return {
        "id": rule_id,
        "name": name,
        "layer": layer,
        "kind": kind,
        "formula": formula,
        "implementation_refs": implementation_refs,
        "source_ids": source_ids,
        "published_support": published_support,
        "transfer_limit": transfer_limit,
        "exact_formula_support": exact_formula_support,
        "implementation_fidelity": implementation_fidelity,
        "predictive_validation": predictive_validation,
        "coherence": coherence,
        "traceability": traceability,
        "reliability_tier": reliability_tier,
        "current_decision": current_decision,
        "challenger_admission": challenger_admission,
        "blockers": blockers,
        "gates": gate_results,
        "horizons": horizons
        or ["intraday_short", "intraday_wide", "short_swing"],
        "pair_scope": pair_scope,
        "e1_3_findings": e1_3_findings or [],
        "e1_4_impact": e1_4_impact,
    }


def load_impact() -> dict:
    return json.loads(IMPACT_PATH.read_text(encoding="utf-8"))


def data_rules() -> list[dict]:
    shared = {
        "kind": "data_definition",
        "exact_formula_support": "official_field_definition",
        "implementation_fidelity": "transport_verified",
        "predictive_validation": "not_applicable_data_only",
        "coherence": "pass_as_data",
        "traceability": "source_and_availability_recorded",
        "reliability_tier": "R0_data_definition",
        "current_decision": "allow_as_input_with_freshness_checks",
        "challenger_admission": "data_allowed_not_predictive",
        "blockers": [],
        "gate_results": gates(
            bounded_source_claim=True,
            implementation_fidelity=True,
            mathematical_coherence=True,
            complete_trace=True,
        ),
        "pair_scope": "provider_supported_pairs",
    }
    definitions = [
        (
            "DATA-PRICE-KLINES",
            "Precio y velas Binance USD-M",
            "market_data",
            "Campos oficiales de ticker y klines.",
            ["market_data.py:get_price", "market_data.py:get_klines", "data_engine.py:parse_klines"],
            ["BINANCE_USDM_API"],
            "Define precio, OHLCV e intervalos.",
            "No acredita ninguna senal, ventana o probabilidad TP/SL.",
        ),
        (
            "DATA-DEPTH-TRADES",
            "Depth y aggTrades Binance USD-M",
            "market_data",
            "Campos oficiales de depth y operaciones agregadas.",
            ["market_data.py:get_depth", "market_data.py:get_agg_trades"],
            ["BINANCE_USDM_API"],
            "Define bids, asks, cantidades, precios y trades.",
            "No valida imbalance top-20, CVD de 500 trades ni sus pesos.",
        ),
        (
            "DATA-DERIVATIVES",
            "Funding, OI y ratios Binance USD-M",
            "market_data",
            "Campos oficiales de funding, open interest y ratios.",
            ["data_engine.py:summarize_derivatives", "analysis_engine.py:derivatives_for_horizon"],
            ["BINANCE_USDM_API"],
            "Define los campos de derivados y sus periodos publicados.",
            "No valida ventanas internas, thresholds, signo predictivo ni pesos.",
        ),
        (
            "DATA-BREADTH",
            "Mercados CoinGecko para breadth",
            "market_data",
            "Variaciones publicadas para el universo consultado.",
            ["data_engine.py:summarize_market_breadth"],
            ["COINGECKO_MARKETS_API"],
            "Define variaciones y datos de los activos devueltos.",
            "No valida top-100, cortes 58/42 ni efecto sobre un par.",
        ),
        (
            "DATA-GLOBAL",
            "Mercado global CoinGecko",
            "market_data",
            "Capitalizacion, volumen y dominancia global.",
            ["data_engine.py:summarize_global_market"],
            ["COINGECKO_GLOBAL_API"],
            "Define agregados del mercado crypto.",
            "No valida interpretacion direccional.",
        ),
        (
            "DATA-SENTIMENT",
            "Fear and Greed de Alternative.me",
            "market_data",
            "Escala y metodologia del indicador externo.",
            ["data_engine.py:summarize_sentiment"],
            ["ALTERNATIVE_FNG"],
            "Define escala, componentes y API.",
            "El proveedor no valida decisiones de trading ni cortes 75/25.",
        ),
        (
            "DATA-LIQUIDATIONS",
            "Mapa Hyperliquid observado",
            "market_data",
            "Posiciones publicas normalizadas como clusters observacionales.",
            ["liquidation_data.py:normalize_heatmap", "analysis_engine.py:build_liquidation_observation"],
            ["INTERNAL_ENGINE_HISTORY"],
            "Permite conservar una observacion versionada del proveedor gratuito.",
            "No es mapa agregado multi-exchange ni tiene poder predictivo validado.",
        ),
    ]
    return [
        rule(
            rule_id=item[0],
            name=item[1],
            layer=item[2],
            formula=item[3],
            implementation_refs=item[4],
            source_ids=item[5],
            published_support=item[6],
            transfer_limit=item[7],
            **shared,
        )
        for item in definitions
    ]


def transform_rules() -> list[dict]:
    common_blockers = [
        "no_temporal_holdout",
        "no_cross_pair_validation",
        "no_incremental_predictive_validation",
    ]
    return [
        rule(
            rule_id="PLAN-TP-LOG-DISTANCE",
            name="Distancia logaritmica de entrada a TP",
            layer="feature_transform",
            kind="deterministic_plan_calculation",
            formula="long: ln(TP/entry); short: ln(entry/TP)",
            implementation_refs=["challenger_engine.py:derive_plan_features"],
            source_ids=["INTERNAL_ENGINE_SPEC"],
            published_support="Es una transformacion matematica dimensionless del plan.",
            transfer_limit="La identidad no acredita signo, magnitud ni linealidad predictiva.",
            exact_formula_support="financial_identity_only",
            implementation_fidelity="pass",
            predictive_validation="not_validated_as_predictor",
            coherence="pass_positive_and_side_symmetric",
            traceability="raw_and_transformed_values_recorded",
            reliability_tier="R1_standard_calculation",
            current_decision="allow_feature_calculation_only",
            challenger_admission="calculation_allowed_nonpredictive",
            blockers=common_blockers,
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="PLAN-SL-LOG-DISTANCE",
            name="Distancia logaritmica de entrada a SL",
            layer="feature_transform",
            kind="deterministic_plan_calculation",
            formula="long: ln(entry/SL); short: ln(SL/entry)",
            implementation_refs=["challenger_engine.py:derive_plan_features"],
            source_ids=["INTERNAL_ENGINE_SPEC"],
            published_support="Es una transformacion matematica dimensionless del plan.",
            transfer_limit="La identidad no acredita signo, magnitud ni linealidad predictiva.",
            exact_formula_support="financial_identity_only",
            implementation_fidelity="pass",
            predictive_validation="not_validated_as_predictor",
            coherence="pass_positive_and_side_symmetric",
            traceability="raw_and_transformed_values_recorded",
            reliability_tier="R1_standard_calculation",
            current_decision="allow_feature_calculation_only",
            challenger_admission="calculation_allowed_nonpredictive",
            blockers=common_blockers,
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="PLAN-LOG-HORIZON-SECONDS",
            name="Duracion logaritmica del horizonte",
            layer="feature_transform",
            kind="deterministic_plan_calculation",
            formula="ln(horizon_seconds)",
            implementation_refs=["challenger_engine.py:derive_plan_features"],
            source_ids=["INTERNAL_ENGINE_SPEC"],
            published_support="Es una transformacion matematica de la duracion declarada.",
            transfer_limit="No acredita como cambia la alcanzabilidad con el tiempo.",
            exact_formula_support="financial_identity_only",
            implementation_fidelity="pass",
            predictive_validation="not_validated_as_predictor",
            coherence="pass_with_explicit_positive_duration",
            traceability="raw_and_transformed_values_recorded",
            reliability_tier="R1_standard_calculation",
            current_decision="allow_feature_calculation_only",
            challenger_admission="calculation_allowed_nonpredictive",
            blockers=common_blockers,
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="PLAN-SIDE-SIGN",
            name="Codificacion simetrica del lado",
            layer="feature_transform",
            kind="deterministic_plan_calculation",
            formula="long=+1; short=-1",
            implementation_refs=["challenger_engine.py:derive_plan_features"],
            source_ids=["INTERNAL_ENGINE_SPEC"],
            published_support="Es una codificacion reproducible del plan del usuario.",
            transfer_limit="La codificacion no acredita diferencias predictivas entre lados.",
            exact_formula_support="internal_only",
            implementation_fidelity="pass",
            predictive_validation="not_validated_as_predictor",
            coherence="pass",
            traceability="raw_and_transformed_values_recorded",
            reliability_tier="R1_standard_calculation",
            current_decision="allow_feature_calculation_only",
            challenger_admission="calculation_allowed_nonpredictive",
            blockers=common_blockers,
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="IND-EMA-CORE",
            name="EMA estandar con historia suficiente",
            layer="feature_transform",
            kind="standard_calculation",
            formula="EMA_t = alpha*x_t + (1-alpha)*EMA_(t-1), alpha=2/(period+1)",
            implementation_refs=["data_engine.py:ema"],
            source_ids=["CFA_TECHNICAL_ANALYSIS"],
            published_support="La media exponencial es una transformacion tecnica reconocida.",
            transfer_limit="No acredita que stacks EMA predigan TP/SL ni sus pesos.",
            exact_formula_support="standard_formula",
            implementation_fidelity="pass_for_available_history",
            predictive_validation="not_validated_as_predictor",
            coherence="pass_as_feature",
            traceability="feature_value_recorded",
            reliability_tier="R1_standard_calculation",
            current_decision="allow_feature_calculation_only",
            challenger_admission="calculation_allowed_nonpredictive",
            blockers=common_blockers,
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="IND-EMA200-FALLBACK",
            name="Fallback EMA200 con hasta 80 cierres",
            layer="feature_transform",
            kind="implementation_variant",
            formula="if len(closes)<200: ema(closes, min(80,len(closes))) etiquetada ema_200",
            implementation_refs=["data_engine.py:summarize_timeframe"],
            source_ids=["CFA_TECHNICAL_ANALYSIS"],
            published_support="La EMA tiene definicion reconocida.",
            transfer_limit="La fuente no permite llamar EMA200 a una EMA de hasta 80 datos.",
            exact_formula_support="none",
            implementation_fidelity="fail_mislabeled_period",
            predictive_validation="not_validated",
            coherence="semantic_fail",
            traceability="fallback_not_explicit_in_snapshot",
            reliability_tier="RX_blocked",
            current_decision="rename_or_block_when_history_insufficient",
            challenger_admission="blocked_current_implementation",
            blockers=["mislabeled_period", "missing_explicit_availability"],
            gate_results=gates(bounded_source_claim=True),
            e1_3_findings=["E1.3-F15"],
        ),
        rule(
            rule_id="IND-RSI14-CURRENT",
            name="RSI14 variante de media simple",
            layer="feature_transform",
            kind="implementation_variant",
            formula="RSI sobre media simple de los ultimos 14 cambios",
            implementation_refs=["data_engine.py:rsi"],
            source_ids=["WILDER_1978"],
            published_support="Wilder define RSI y su suavizado original.",
            transfer_limit="La implementacion actual no replica todo el suavizado de Wilder.",
            exact_formula_support="implementation_variant",
            implementation_fidelity="fail_against_named_standard",
            predictive_validation="not_validated",
            coherence="calculation_variant",
            traceability="value_recorded_but_variant_not_labeled",
            reliability_tier="RX_blocked",
            current_decision="correct_or_rename_before_research",
            challenger_admission="blocked_current_implementation",
            blockers=["formula_fidelity", *common_blockers],
            gate_results=gates(bounded_source_claim=True, mathematical_coherence=True),
            e1_3_findings=["E1.3-F14"],
        ),
        rule(
            rule_id="IND-ATR14-CURRENT",
            name="ATR14 variante de media simple",
            layer="feature_transform",
            kind="implementation_variant",
            formula="Media simple de true ranges recientes",
            implementation_refs=["data_engine.py:atr"],
            source_ids=["WILDER_1978"],
            published_support="Wilder define true range y ATR.",
            transfer_limit="La implementacion no replica todo el suavizado original.",
            exact_formula_support="implementation_variant",
            implementation_fidelity="fail_against_named_standard",
            predictive_validation="not_validated",
            coherence="calculation_variant",
            traceability="value_recorded_but_variant_not_labeled",
            reliability_tier="RX_blocked",
            current_decision="correct_or_rename_before_research",
            challenger_admission="blocked_current_implementation",
            blockers=["formula_fidelity", *common_blockers],
            gate_results=gates(bounded_source_claim=True, mathematical_coherence=True),
        ),
        rule(
            rule_id="IND-EMA-STACK",
            name="Stack EMA multi-temporalidad",
            layer="feature_transform",
            kind="research_hypothesis",
            formula="bullish/bearish/mixed por orden EMA9, EMA21 y EMA50",
            implementation_refs=["data_engine.py:classify_ema_stack", "analysis_engine.py:trend_score"],
            source_ids=["CFA_TECHNICAL_ANALYSIS", "BROCK_LAKONISHOK_LEBARON"],
            published_support="Las medias y algunas reglas simples merecen investigacion empirica.",
            transfer_limit="No valida este stack, activos crypto, horizontes ni pesos.",
            exact_formula_support="none",
            implementation_fidelity="internal_definition_reproducible",
            predictive_validation="not_validated",
            coherence="duplicated_across_paths",
            traceability="value_recorded_but_multiple_effects",
            reliability_tier="R2_research_hypothesis",
            current_decision="research_single_structural_feature",
            challenger_admission="research_only_not_shadow",
            blockers=["double_counting", *common_blockers],
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=False,
                complete_trace=False,
            ),
            e1_3_findings=["E1.3-F11"],
        ),
        rule(
            rule_id="IND-SUPPORT-RESISTANCE",
            name="Detector interno de soportes y resistencias",
            layer="feature_transform",
            kind="research_hypothesis",
            formula="Cluster de extremos recientes y distancia porcentual al nivel",
            implementation_refs=["data_engine.py:detect_levels", "data_engine.py:cluster_level"],
            source_ids=["OSLER_SUPPORT_RESISTANCE"],
            published_support="Existe evidencia parcial de interrupciones cerca de ciertos niveles en FX.",
            transfer_limit="No valida el detector interno, BTC ni sus umbrales.",
            exact_formula_support="none",
            implementation_fidelity="internal_proxy_reproducible",
            predictive_validation="not_validated",
            coherence="pass_as_candidate_feature",
            traceability="levels_and_distances_recorded",
            reliability_tier="R2_research_hypothesis",
            current_decision="compare_detectors_in_research",
            challenger_admission="research_only_not_shadow",
            blockers=common_blockers,
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="IND-FIBONACCI",
            name="Swing y niveles Fibonacci automaticos",
            layer="feature_transform",
            kind="research_hypothesis",
            formula="Swings internos + retracements 0.236/0.382/0.5/0.618/0.786 y extensiones",
            implementation_refs=["data_engine.py:summarize_fibonacci", "analysis_engine.py:build_fibonacci_trade_context"],
            source_ids=["FIBONACCI_2022"],
            published_support="La fuente evalua identificacion automatica de retrocesos.",
            transfer_limit="No encontro ventaja estadistica y no valida nuestros swings ni pesos.",
            exact_formula_support="none",
            implementation_fidelity="internal_detector_reproducible",
            predictive_validation="external_evidence_non_supportive",
            coherence="duplicated_with_zone_and_calibration",
            traceability="context_recorded_multiple_paths",
            reliability_tier="RX_blocked",
            current_decision="retire_predictive_effect_keep_research_only",
            challenger_admission="blocked_as_predictor",
            blockers=["non_supportive_evidence", "double_counting", *common_blockers],
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                complete_trace=False,
            ),
            e1_3_findings=["E1.3-F12"],
        ),
        rule(
            rule_id="IND-ORDERBOOK-PROXY",
            name="Imbalance estatico top-20",
            layer="feature_transform",
            kind="proxy_hypothesis",
            formula="(bid_notional_top20-ask_notional_top20)/(bid+ask)",
            implementation_refs=["data_engine.py:summarize_order_book"],
            source_ids=["CONT_KUKANOV_STOIKOV"],
            published_support="OFI dinamico en mejor bid/ask mostro relacion de corto plazo con precio.",
            transfer_limit="Top-20 estatico no es el OFI del estudio ni hereda coeficientes.",
            exact_formula_support="none",
            implementation_fidelity="different_proxy",
            predictive_validation="not_validated",
            coherence="pass_as_distinct_proxy",
            traceability="proxy_value_recorded",
            reliability_tier="R2_research_hypothesis",
            current_decision="research_proxy_without_weight",
            challenger_admission="research_only_not_shadow",
            blockers=["proxy_transfer_gap", *common_blockers],
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=False,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="IND-CVD-PROXY",
            name="CVD proxy de 500 aggTrades",
            layer="feature_transform",
            kind="proxy_hypothesis",
            formula="(buy_notional-sell_notional)/(buy+sell) sobre muestra reciente",
            implementation_refs=["data_engine.py:summarize_trade_flow"],
            source_ids=["BINANCE_USDM_API", "CONT_KUKANOV_STOIKOV"],
            published_support="Binance define trades; la literatura permite investigar order flow.",
            transfer_limit="No valida esta ventana, clasificacion ni peso.",
            exact_formula_support="none",
            implementation_fidelity="internal_proxy_reproducible",
            predictive_validation="not_validated",
            coherence="correlated_with_taker_and_orderbook",
            traceability="proxy_value_recorded",
            reliability_tier="R2_research_hypothesis",
            current_decision="research_with_correlation_control",
            challenger_admission="research_only_not_shadow",
            blockers=["correlated_features", *common_blockers],
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                mathematical_coherence=True,
                complete_trace=True,
            ),
        ),
        rule(
            rule_id="IND-PENDING-ZONE",
            name="Zona de entrada pendiente",
            layer="feature_transform",
            kind="internal_composite_hypothesis",
            formula="Confluencia, activacion, sweep, rechazo/ruptura y calidad de camino",
            implementation_refs=[
                "analysis_engine.py:build_zone_analysis",
                "analysis_engine.py:build_target_path_quality",
                "analysis_engine.py:build_zone_probability_context",
            ],
            source_ids=["INTERNAL_ENGINE_HISTORY", "OSLER_SUPPORT_RESISTANCE"],
            published_support="Niveles pueden investigarse; la zona concreta es diseno interno.",
            transfer_limit="No existe fuente para formulas, thresholds ni probabilidades de zona.",
            exact_formula_support="internal_only",
            implementation_fidelity="internal_reproducible",
            predictive_validation="insufficient_internal_sample",
            coherence="reuses_parent_scores",
            traceability="aggregate_outputs_recorded",
            reliability_tier="R3_internal_provisional",
            current_decision="keep_observational_rebuild_as_declared_interaction",
            challenger_admission="blocked_current_formula",
            blockers=["double_counting", "no_incremental_ablation", "small_sample", "no_holdout"],
            gate_results=gates(
                bounded_source_claim=True,
                implementation_fidelity=True,
                complete_trace=False,
            ),
            e1_3_findings=["E1.3-F12", "E1.3-F13"],
        ),
    ]


DIRECT_METADATA = {
    "trend_bias": (
        "Tendencia EMA multi-TF",
        "analysis_engine.py:trend_score",
        "EMA stacks ponderados; cortes +/-0.2 y +/-0.55; efecto +0.10/+0.05/-0.05/-0.09",
        ["CFA_TECHNICAL_ANALYSIS", "BROCK_LAKONISHOK_LEBARON"],
        "family_evidence_only",
        "duplicated",
        "rebuild_single_feature",
        ["E1.3-F11"],
    ),
    "technical_direction_bias": (
        "Rating tecnico direccional",
        [
            "analysis_engine.py:build_technical_rating",
            "analysis_engine.py:technical_timeframe_score",
        ],
        "Score EMA+precio/EMA+RSI; cortes +/-0.15 y +/-0.45; efecto +0.035/+0.015/-0.02/-0.04",
        ["CFA_TECHNICAL_ANALYSIS", "WILDER_1978"],
        "definitions_only",
        "duplicated",
        "rebuild_without_manual_points",
        ["E1.3-F11", "E1.3-F14"],
    ),
    "price_vs_entry_bias": (
        "Precio actual frente a entrada",
        "analysis_engine.py:analyze_trade",
        "Long: +0.03 si price<=entry, si no -0.02; short simetrico",
        ["INTERNAL_ENGINE_HISTORY"],
        "none",
        "incoherent_discontinuity",
        "retire_current_formula",
        ["E1.3-F04"],
    ),
    "volume_bias": (
        "Ratio de volumen",
        "analysis_engine.py:analyze_trade",
        "+0.025 si volume_ratio>1.25; -0.015 si <0.65; ponderado por micro_weight",
        ["BINANCE_USDM_API"],
        "data_only",
        "threshold_discontinuity",
        "research_continuous_transform",
        ["E1.3-F14"],
    ),
    "order_book_bias": (
        "Imbalance order book",
        "analysis_engine.py:analyze_trade",
        "Umbral +/-0.12; efecto +/-0.016 por lado y micro_weight",
        ["CONT_KUKANOV_STOIKOV", "BINANCE_USDM_API"],
        "different_proxy",
        "correlated_proxy",
        "research_without_current_threshold",
        [],
    ),
    "momentum_bias": (
        "Momentum RSI",
        "analysis_engine.py:analyze_trade",
        "Bandas RSI discretas por lado; efecto +0.02 o -0.025 por micro_weight",
        ["WILDER_1978"],
        "indicator_definition_only",
        "implementation_variant_and_discontinuous",
        "retire_current_thresholds",
        ["E1.3-F14"],
    ),
    "market_regime_bias": (
        "Sesgo de regimen",
        [
            "analysis_engine.py:classify_market_regime",
            "analysis_engine.py:market_regime_direction_bias",
        ],
        "Efectos 0.024/-0.028/-0.018 con multiplicador por horizonte",
        ["CFA_TECHNICAL_ANALYSIS", "INTERNAL_ENGINE_HISTORY"],
        "concept_only",
        "duplicated",
        "rebuild_regime_as_single_context",
        ["E1.3-F11"],
    ),
    "fibonacci_probability_adjustment": (
        "Ajuste Fibonacci",
        "analysis_engine.py:build_fibonacci_trade_context",
        "Ajuste actual 0 para favorable y negativo para contextos adversos",
        ["FIBONACCI_2022"],
        "non_supportive_external_evidence",
        "duplicated",
        "retire_predictive_adjustment",
        ["E1.3-F12"],
    ),
    "zone_probability_adjustment": (
        "Ajuste de zona pendiente",
        "analysis_engine.py:build_zone_probability_context",
        "Ajustes discretos de zona hasta +0.025/-0.035",
        ["INTERNAL_V09_AUDIT", "INTERNAL_ENGINE_HISTORY"],
        "small_internal_sample",
        "duplicated_composite",
        "rebuild_as_preregistered_interaction",
        ["E1.3-F12"],
    ),
    "taker_flow_bias": (
        "Ratio taker buy/sell",
        "analysis_engine.py:taker_flow_score",
        "Umbrales 1.12/0.88; efecto +/-0.02 por lado y derivatives_weight",
        ["BINANCE_USDM_API", "CONT_KUKANOV_STOIKOV"],
        "data_and_family_only",
        "correlated_proxy",
        "research_continuous_feature",
        [],
    ),
    "cvd_bias": (
        "CVD proxy",
        "analysis_engine.py:cvd_flow_score",
        "Umbral +/-0.12; efecto +/-0.018 por lado y micro_weight",
        ["BINANCE_USDM_API", "CONT_KUKANOV_STOIKOV"],
        "different_proxy",
        "correlated_proxy",
        "research_with_correlation_control",
        [],
    ),
    "oi_trend_bias": (
        "Tendencia precio-OI",
        "analysis_engine.py:open_interest_trend_score",
        "OI change >=0.2 y signo precio 24h; efecto +/-0.02",
        ["BINANCE_USDM_API"],
        "data_only",
        "unvalidated_interpretation",
        "research_by_horizon",
        [],
    ),
    "breadth_bias": (
        "Breadth crypto",
        "analysis_engine.py:market_breadth_score",
        "Advancers 58/42 y mediana; efecto +/-0.02 por macro_weight",
        ["COINGECKO_MARKETS_API"],
        "data_only",
        "unvalidated_universe_and_thresholds",
        "research_or_retire",
        [],
    ),
    "volatility_penalty": (
        "SL frente a volatilidad",
        "analysis_engine.py:analyze_trade",
        "0.07 si risk_distance < max(range,ATR)*0.35",
        ["WILDER_1978"],
        "atr_definition_only",
        "unvalidated_threshold",
        "replace_with_barrier_model",
        [],
    ),
    "liquidity_penalty": (
        "Penalizacion de spread",
        "analysis_engine.py:analyze_trade",
        "0.03 si spread_pct>0.04",
        ["BINANCE_USDM_API"],
        "data_only",
        "unvalidated_threshold",
        "model_execution_separately",
        [],
    ),
    "overextension_penalty": (
        "Extension frente a EMA21",
        "analysis_engine.py:analyze_trade",
        "0.025 si abs(price_vs_ema21)>max(0.5,ATR*1.8)",
        ["CFA_TECHNICAL_ANALYSIS", "WILDER_1978"],
        "definitions_only",
        "unvalidated_combination",
        "research_continuous_interaction",
        [],
    ),
    "funding_penalty": (
        "Funding extremo por lado",
        "analysis_engine.py:funding_context_penalty",
        "0.025 si long funding>0.03 o short funding<-0.03",
        ["BINANCE_USDM_API"],
        "data_only",
        "unvalidated_threshold",
        "research_by_contract_and_horizon",
        [],
    ),
    "funding_relative_penalty": (
        "Funding frente a media",
        "analysis_engine.py:funding_relative_context_penalty",
        "Thresholds internos de funding actual frente a media reciente",
        ["BINANCE_USDM_API"],
        "data_only",
        "unvalidated_window_and_threshold",
        "research_by_contract_and_horizon",
        [],
    ),
    "crowding_penalty": (
        "Crowding long/short",
        "analysis_engine.py:crowding_penalty_score",
        "0.015 si long ratio>2.0 o short ratio<0.5",
        ["BINANCE_USDM_API"],
        "data_only",
        "unvalidated_threshold",
        "research_by_pair",
        [],
    ),
    "level_penalty": (
        "Barrera de soporte/resistencia",
        "analysis_engine.py:level_risk_penalty",
        "0.025 si nivel queda antes de max(0.25,35% del reward)",
        ["OSLER_SUPPORT_RESISTANCE"],
        "family_evidence_only",
        "unvalidated_detector_and_threshold",
        "compare_level_models",
        [],
    ),
    "sentiment_penalty": (
        "Sentimiento extremo",
        "analysis_engine.py:sentiment_extreme_penalty",
        "0.015 con FearGreed >=75 para long o <=25 para short",
        ["ALTERNATIVE_FNG"],
        "provider_methodology_only",
        "unvalidated_threshold",
        "research_or_retire",
        [],
    ),
    "higher_timeframe_penalty": (
        "Contradiccion HTF",
        "analysis_engine.py:higher_timeframe_contra_penalty",
        "Penalizacion discreta por estructura 4h/1d contraria y horizonte",
        ["CFA_TECHNICAL_ANALYSIS"],
        "concept_only",
        "duplicated",
        "merge_into_single_structure_feature",
        ["E1.3-F11"],
    ),
    "technical_entry_timing_penalty": (
        "Timing tecnico",
        "analysis_engine.py:build_technical_rating",
        "0.02 por RSI extremo y extension frente a EMA/ATR",
        ["WILDER_1978", "CFA_TECHNICAL_ANALYSIS"],
        "definitions_only",
        "unvalidated_combination",
        "research_continuous_interaction",
        [],
    ),
    "technical_barrier_penalty": (
        "Barrera tecnica al TP",
        "analysis_engine.py:build_technical_rating",
        "0.025 si barrera<55% reward; 0.012 si <85%",
        ["OSLER_SUPPORT_RESISTANCE"],
        "family_evidence_only",
        "unvalidated_thresholds",
        "compare_barrier_models",
        [],
    ),
    "oi_context_penalty": (
        "Contexto precio-OI",
        "analysis_engine.py:oi_price_context_penalty",
        "Penalizacion discreta por combinaciones de precio y OI",
        ["BINANCE_USDM_API"],
        "data_only",
        "unvalidated_interpretation",
        "research_by_horizon",
        [],
    ),
    "contradiction_penalty": (
        "Penalizacion por contradicciones",
        "analysis_engine.py:combined_contradiction_penalty",
        "Cuenta contradicciones y aplica 0.018/0.032/0.045",
        ["INTERNAL_ENGINE_HISTORY"],
        "none",
        "composite_double_count_risk",
        "replace_with_explicit_interactions",
        ["E1.3-F13"],
    ),
    "risk_calibration_tp_adjustment": (
        "Ajuste TP agregado de calibracion",
        "analysis_engine.py:build_risk_calibration_context",
        "Suma de gates con floor agregado -0.16",
        ["INTERNAL_V09_AUDIT", "INTERNAL_ENGINE_HISTORY"],
        "small_internal_sample",
        "aggregate_not_attributable",
        "decompose_and_revalidate",
        ["E1.3-F15"],
    ),
    "zone_range_probability_adjustment": (
        "Ajuste rango por no activacion",
        "analysis_engine.py:build_zone_probability_context",
        "Aumenta range_probability por baja activacion pendiente",
        ["INTERNAL_ENGINE_HISTORY"],
        "none",
        "semantic_mixing",
        "separate_activation_from_outcome",
        ["E1.3-F13"],
    ),
    "risk_calibration_range_adjustment": (
        "Ajuste rango de calibracion",
        "analysis_engine.py:build_risk_calibration_context",
        "Ajuste agregado de rango; actualmente no activado en cohorte E1.4",
        ["INTERNAL_ENGINE_HISTORY"],
        "none",
        "aggregate_not_attributable",
        "remove_until_defined",
        ["E1.3-F13", "E1.3-F15"],
    ),
}


def direct_scoring_rules(impact: dict) -> list[dict]:
    results = []
    for key in DIRECT_ABLATION_UNITS:
        metadata = DIRECT_METADATA[key]
        evidence = impact["units"].get(key)
        concept_support = metadata[4]
        coherence = metadata[5]
        internal = key.startswith("risk_calibration") or key.startswith("zone_")
        results.append(
            rule(
                rule_id=f"SCORE-{key.upper()}",
                name=metadata[0],
                layer="predictive_score",
                kind="active_predictive_adjustment",
                formula=metadata[2],
                implementation_refs=[
                    *(
                        metadata[1]
                        if isinstance(metadata[1], list)
                        else [metadata[1]]
                    ),
                    "analysis_engine.py:analyze_trade",
                ],
                source_ids=metadata[3],
                published_support=concept_support,
                transfer_limit="Ninguna fuente valida el threshold y peso exactos actuales.",
                exact_formula_support=(
                    "internal_provisional" if internal else "none"
                ),
                implementation_fidelity="reproducible_internal_formula",
                predictive_validation=(
                    "insufficient_internal_sample" if internal else "not_validated"
                ),
                coherence=coherence,
                traceability=(
                    "aggregate_only"
                    if key.startswith("risk_calibration")
                    else "component_recorded_without_stable_rule_version"
                ),
                reliability_tier=(
                    "R3_internal_provisional" if internal else "RX_blocked"
                ),
                current_decision=metadata[6],
                challenger_admission="blocked_current_formula",
                blockers=[
                    "exact_weight_without_external_support",
                    "no_temporal_holdout",
                    "no_cross_pair_validation",
                    "no_probability_calibration",
                ],
                gate_results=gates(
                    bounded_source_claim=bool(metadata[3]),
                    implementation_fidelity=True,
                    mathematical_coherence=coherence
                    not in {
                        "incoherent_discontinuity",
                        "semantic_mixing",
                        "duplicated",
                        "duplicated_composite",
                    },
                    complete_trace=False,
                    incremental_ablation=evidence is not None,
                ),
                e1_3_findings=metadata[7],
                e1_4_impact=evidence,
            )
        )
    return results


CALIBRATION_DEFINITIONS = [
    ("sl_probability_gte_55", "SL estimado >=55%", "sl_probability>=0.55", "-0.045 TP; +0.10 risk; cap D; force", "circular_heuristic_input"),
    ("sl_probability_gte_50", "SL estimado >=50%", "0.50<=sl_probability<0.55", "-0.025 TP; +0.06 risk; cap C", "circular_heuristic_input"),
    ("direction_score_lt_40", "TP estimado <40%", "tp_probability<0.40", "-0.025 TP; +0.07 risk; cap D; force", "circular_heuristic_input"),
    ("technical_score_lt_40", "Rating tecnico <40", "technical_rating.score<40", "-0.020 TP; +0.07 risk; cap C", "duplicate_technical_path"),
    ("rr_ratio_gte_3", "R/R >=3", "risk_reward_ratio>=3", "-0.035 TP if reward>=3% else -0.020; +0.08 risk; cap C", "unsupported_threshold"),
    ("reward_distance_gte_3", "TP distante >=3%", "reward_distance>=3", "-0.025 TP; +0.07 risk; cap C", "unsupported_threshold"),
    ("risk_distance_lt_0_25", "SL <0.25%", "risk_distance<0.25", "-0.025 TP; +0.10 risk; cap C", "unsupported_threshold"),
    ("risk_distance_gte_3", "SL >=3%", "risk_distance>=3", "+0.08 risk; cap C", "unsupported_threshold"),
    ("ticker_24h_contra_side", "Ticker 24h contrario", "side_signed_contra(price_change_24h,0.25)", "-0.025 TP; +0.05 risk; cap C", "unsupported_interpretation"),
    ("ema_stack_15m_contra_side", "EMA stack 15m contrario", "timeframe_contra_side(15m,require_stack=True)", "-0.020 TP; +0.04 risk; cap C", "duplicate_ema_path"),
    ("price_vs_ema_1h_contra_side", "Precio vs EMA21 1h contrario", "timeframe_contra_side(1h,threshold=0.08)", "-0.020 TP; +0.04 risk; cap C", "duplicate_ema_path"),
    ("pending_zone_negative_adjustment", "Zona pendiente negativa", "zone_probability_adjustment<0", "-0.015 TP; +0.04 risk; cap C", "duplicate_zone_path"),
    ("pending_stop_breakdown", "Orden stop breakdown", "entry_order_type=='stop_breakdown'", "-0.030 TP; +0.08 risk; cap D; force", "small_internal_sample"),
    ("pending_liquidity_sweep_high", "Sweep risk alto", "liquidity_sweep_risk=='alto'", "-0.020 TP; +0.05 risk; cap C", "small_internal_sample"),
    ("pending_false_breakout_risk", "Riesgo de falsa ruptura", "reaction_bias=='falsa_ruptura_riesgo'", "-0.020 TP; +0.05 risk; cap C", "small_internal_sample"),
    ("extreme_fib_extreme_sentiment_cluster", "Fibonacci extremo + sentimiento", "extreme_fibonacci and extreme_sentiment", "-0.035 TP; +0.08 risk; cap C", "three_case_cluster"),
    ("extreme_fib_sentiment_cvd_contra", "Cluster anterior + CVD contrario", "extreme_fibonacci and extreme_sentiment and cvd_contra", "-0.015 TP; +0.03 risk; cap C", "tiny_subgroup"),
    ("rsi_extreme_multi_risk_cluster", "RSI extremo + dos riesgos", "rsi_extreme and material_risk_count>=2", "-0.012 TP; +0.025 risk; cap C", "tiny_subgroup"),
    ("rsi_extreme_with_fib_sentiment_cluster", "RSI + Fibonacci + sentimiento", "rsi_extreme and extreme_fibonacci and extreme_sentiment", "-0.008 TP; +0.015 risk; cap C", "tiny_subgroup"),
]


def calibration_rules(impact: dict) -> list[dict]:
    frequencies = impact.get("risk_calibration_flags", {})
    results = []
    for flag, name, condition, effect, problem in CALIBRATION_DEFINITIONS:
        results.append(
            rule(
                rule_id=f"GATE-{flag.upper()}",
                name=name,
                layer="risk_calibration",
                kind="internal_empirical_gate",
                formula=f"IF {condition} THEN {effect}",
                implementation_refs=[
                    "analysis_engine.py:build_risk_calibration_context",
                    (
                        "analysis_engine.py:side_signed_contra"
                        if flag == "ticker_24h_contra_side"
                        else "analysis_engine.py:timeframe_contra_side"
                        if flag in {
                            "ema_stack_15m_contra_side",
                            "price_vs_ema_1h_contra_side",
                        }
                        else "analysis_engine.py:rsi_extreme_against_entry"
                        if flag.startswith("rsi_extreme")
                        else "analysis_engine.py:build_risk_calibration_context"
                    ),
                ],
                source_ids=["INTERNAL_V09_AUDIT", "INTERNAL_ENGINE_HISTORY"],
                published_support="Origen interno documentado; no hay validacion externa del gate exacto.",
                transfer_limit="Muestra retrospectiva, versiones mezcladas y subgrupos pequenos.",
                exact_formula_support="internal_provisional",
                implementation_fidelity="reproducible_internal_formula",
                predictive_validation="insufficient_internal_sample",
                coherence=problem,
                traceability="flag_recorded_effect_aggregated",
                reliability_tier="R3_internal_provisional",
                current_decision="keep_champion_frozen_do_not_transfer",
                challenger_admission="blocked_current_gate",
                blockers=[
                    problem,
                    "per_flag_effect_not_preserved_after_caps",
                    "no_temporal_holdout",
                    "no_cross_pair_validation",
                    "insufficient_sample",
                ],
                gate_results=gates(
                    bounded_source_claim=True,
                    implementation_fidelity=True,
                    mathematical_coherence=problem
                    not in {
                        "circular_heuristic_input",
                        "duplicate_technical_path",
                        "duplicate_ema_path",
                        "duplicate_zone_path",
                    },
                    complete_trace=False,
                    incremental_ablation=False,
                ),
                e1_3_findings=["E1.3-F11", "E1.3-F12", "E1.3-F15"],
                e1_4_impact={
                    "activation_count": int(frequencies.get(flag, 0)),
                    "individual_ablation_available": False,
                },
            )
        )
    return results


def output_rules() -> list[dict]:
    definitions = [
        ("OUT-TP-ADDITIVE", "TP score aditivo", "0.5 + biases - penalties", "analysis_engine.py:analyze_trade", "incoherent_probability_semantics", ["E1.3-F01"]),
        ("OUT-TP-CAPS", "Caps TP", "clamp 0.26..0.74 y despues 0.22..0.74", "analysis_engine.py:analyze_trade", "saturation", ["E1.3-F06"]),
        ("OUT-RANGE", "Probabilidad de rango", "0.12/0.10/0.08/0.06 + ajustes; cap 0.04..0.22", "analysis_engine.py:range_probability_for_context", "mixed_semantics", ["E1.3-F13"]),
        ("OUT-SL-RESIDUAL", "SL residual", "max(0.05,1-TP-range)", "analysis_engine.py:analyze_trade", "normalization_fail", ["E1.3-F03", "E1.3-F05"]),
        ("OUT-PROBABILITY-BANDS", "Bandas de probabilidad", "ancho 0.04/0.06/0.08 por contradiccion", "analysis_engine.py:build_probability_ranges", "not_statistical_interval", ["E1.3-F09"]),
        ("OUT-EV-COST", "Esperanza matematica", "TP*net_win-SL*net_loss-range*cost", "analysis_engine.py:calculate_expected_value", "valid_identity_invalid_inputs", ["E1.3-F01"]),
        ("OUT-FEE", "Fee round-trip fija", "notional*0.0008", "analysis_engine.py:calculate_expected_value", "unsupported_universal_cost", []),
        ("OUT-SLIPPAGE", "Slippage minimo", "max(spread_pct/100,0.0002)", "analysis_engine.py:calculate_expected_value", "unsupported_execution_model", []),
        ("OUT-FUNDING-COST", "Coste funding absoluto", "notional*abs(funding_rate_pct)/100 una vez", "analysis_engine.py:calculate_expected_value", "wrong_sign_and_horizon", ["E1.3-F07", "E1.3-F08"]),
        ("OUT-RISK-SCORE", "Risk score agregado", "Suma manual de flags y cortes 0.12/0.24/0.42", "analysis_engine.py:analyze_trade", "unsupported_score", []),
        ("OUT-GRADE", "Grado A/B/C/D", "Cortes TP, risk_score y expected_value_score + cap", "analysis_engine.py:grade_from_scores", "unsupported_governance_thresholds", []),
        ("OUT-CONFIDENCE", "Confianza textual", "Cortes 76/61/46 sobre confidence_score", "analysis_engine.py:confidence_from_score", "not_statistical_uncertainty", ["E1.3-F17"]),
        ("OUT-DECISION", "Decision simular/observar", "Reglas por grade, risk, confidence, EV y force", "analysis_engine.py:decision_from_context", "unsupported_policy", []),
        ("OUT-LAYERED-SCORES", "Scores por capas", "Transformaciones manuales 0..100 de direccion/calidad/riesgo/confianza/EV", "analysis_engine.py:build_layered_scores", "heuristic_relabeling", ["E1.3-F17"]),
        ("OUT-HORIZON-FALLBACK", "Fallback de horizonte", "Valor desconocido usa intraday_short", "analysis_engine.py:time_horizon_profile", "silent_semantic_fallback", []),
        ("OUT-MISSING-DATA", "Defaults neutrales por falta de datos", "RSI=50, EMA=precio y multiples None->0", "data_engine.py:summarize_timeframe", "unknown_presented_as_neutral", ["E1.3-F10"]),
        ("OUT-RISK-CAL-METRIC", "Metrica visual de calibracion", "100-len(flags)*10-risk_addition", "analysis_engine.py:build_risk_calibration_metric", "presentation_only_heuristic", []),
    ]
    rules = []
    for rule_id, name, formula, ref, coherence, findings in definitions:
        identity_only = rule_id == "OUT-EV-COST"
        presentation_only = rule_id == "OUT-RISK-CAL-METRIC"
        rules.append(
            rule(
                rule_id=rule_id,
                name=name,
                layer="output_and_policy",
                kind=(
                    "financial_identity"
                    if identity_only
                    else "presentation_rule"
                    if presentation_only
                    else "output_transformation"
                ),
                formula=formula,
                implementation_refs=[
                    ref,
                    "analysis_engine.py:cap_grade"
                    if rule_id == "OUT-GRADE"
                    else ref,
                    *(
                        ["analysis_engine.py:stricter_grade_cap"]
                        if rule_id == "OUT-GRADE"
                        else []
                    ),
                ],
                source_ids=(
                    ["INTERNAL_ENGINE_SPEC"]
                    if not identity_only
                    else ["INTERNAL_ENGINE_SPEC", "GNEITING_RAFTERY_2007"]
                ),
                published_support=(
                    "La identidad de valor esperado es valida si probabilidades y costes lo son."
                    if identity_only
                    else "Diseno interno; sin fuente para parametros exactos."
                ),
                transfer_limit=(
                    "TP/SL no calibrados y costes simplificados invalidan su uso decisional."
                    if identity_only
                    else "No acredita probabilidad, calibracion ni rentabilidad."
                ),
                exact_formula_support=(
                    "financial_identity_only" if identity_only else "none"
                ),
                implementation_fidelity="reproducible_internal_formula",
                predictive_validation="not_validated",
                coherence=coherence,
                traceability=(
                    "presentation_only"
                    if presentation_only
                    else "aggregate_output_recorded"
                ),
                reliability_tier=(
                    "R1_standard_calculation"
                    if identity_only
                    else "RX_blocked"
                ),
                current_decision=(
                    "keep_identity_rebuild_inputs"
                    if identity_only
                    else "presentation_only"
                    if presentation_only
                    else "replace_in_challenger"
                ),
                challenger_admission=(
                    "calculation_allowed_nonpredictive"
                    if identity_only
                    else "presentation_only"
                    if presentation_only
                    else "blocked_current_formula"
                ),
                blockers=(
                    ["uncalibrated_probabilities", "incomplete_cost_model"]
                    if identity_only
                    else []
                    if presentation_only
                    else [
                        coherence,
                        "no_temporal_holdout",
                        "no_probability_calibration",
                    ]
                ),
                gate_results=gates(
                    bounded_source_claim=identity_only,
                    implementation_fidelity=True,
                    mathematical_coherence=identity_only or presentation_only,
                    complete_trace=presentation_only,
                ),
                e1_3_findings=findings,
            )
        )
    return rules


def extract_calibration_flags() -> set[str]:
    source = (ROOT / "analysis_engine.py").read_text(encoding="utf-8")
    return set(re.findall(r'add_gate\(\s*"([^"]+)"', source))


def predictive_function_ids() -> set[str]:
    matrix = json.loads(
        (ROOT / "auditorias_motor" / "matriz_procedencia_funciones_v0_1.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        item["stable_id"]
        for item in matrix["functions"]
        if item["role"] in {
            "predictive_or_decision_rule",
            "internal_empirical_risk_gate",
        }
    }


def build_matrix() -> dict:
    impact = load_impact()
    rules = (
        data_rules()
        + transform_rules()
        + direct_scoring_rules(impact)
        + calibration_rules(impact)
        + output_rules()
    )
    ids = [item["id"] for item in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("La matriz contiene IDs de regla duplicados.")

    linked_functions = {
        ref
        for item in rules
        for ref in item["implementation_refs"]
    }
    required_functions = predictive_function_ids()
    missing_functions = sorted(required_functions - linked_functions)
    calibration_flags = extract_calibration_flags()
    declared_flags = {item[0] for item in CALIBRATION_DEFINITIONS}
    missing_flags = sorted(calibration_flags - declared_flags)
    direct_keys = {
        item["id"].removeprefix("SCORE-").lower()
        for item in rules
        if item["id"].startswith("SCORE-")
    }
    missing_direct_units = sorted(set(DIRECT_ABLATION_UNITS) - direct_keys)

    admissions = Counter(item["challenger_admission"] for item in rules)
    tiers = Counter(item["reliability_tier"] for item in rules)
    exact_support = Counter(item["exact_formula_support"] for item in rules)
    layers = Counter(item["layer"] for item in rules)
    predictive = [
        item
        for item in rules
        if item["kind"]
        in {
            "active_predictive_adjustment",
            "internal_empirical_gate",
            "output_transformation",
            "internal_composite_hypothesis",
            "research_hypothesis",
            "proxy_hypothesis",
        }
    ]
    validated_predictive = [
        item
        for item in predictive
        if item["reliability_tier"] in {"R4_temporally_validated", "R5_production_authorized"}
    ]
    coverage = {
        "direct_ablation_units_expected": len(DIRECT_ABLATION_UNITS),
        "direct_ablation_units_missing": missing_direct_units,
        "calibration_flags_expected": len(calibration_flags),
        "calibration_flags_missing": missing_flags,
        "predictive_functions_expected": len(required_functions),
        "predictive_functions_missing": missing_functions,
    }
    if missing_direct_units or missing_flags or missing_functions:
        raise ValueError(f"Cobertura incompleta: {coverage}")

    payload = {
        "audit_version": AUDIT_VERSION,
        "purpose": (
            "Separar definicion de dato, formula estandar, hipotesis, parametro "
            "exacto y validacion predictiva antes de admitir reglas al challenger."
        ),
        "production_modified": False,
        "source_taxonomy": {
            key: {
                "title": value["title"],
                "kind": value["kind"],
                "supports": value["supports"],
                "does_not_support": value["does_not_support"],
            }
            for key, value in sorted(SOURCES.items())
        },
        "reliability_tiers": RELIABILITY_TIERS,
        "mandatory_predictive_gates": list(PREDICTIVE_GATE_NAMES),
        "coverage": coverage,
        "summary": {
            "rules": len(rules),
            "predictive_or_decisional_rules": len(predictive),
            "temporally_validated_predictive_rules": len(validated_predictive),
            "production_authorized_predictive_rules": sum(
                1
                for item in predictive
                if item["reliability_tier"] == "R5_production_authorized"
            ),
            "by_admission": dict(sorted(admissions.items())),
            "by_reliability_tier": dict(sorted(tiers.items())),
            "by_exact_formula_support": dict(sorted(exact_support.items())),
            "by_layer": dict(sorted(layers.items())),
        },
        "rules": rules,
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    payload["matrix_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def render_report(matrix: dict) -> str:
    summary = matrix["summary"]
    admissions = summary["by_admission"]
    tiers = summary["by_reliability_tier"]
    lines = [
        "# Matriz de admisibilidad predictiva - E1.5.1",
        "",
        f"Version: `{matrix['audit_version']}`",
        "",
        "Estado: COMPLETADA",
        "",
        "## Respuesta principal",
        "",
        (
            "Actualmente no existe ninguna regla predictiva del champion que haya "
            "superado validacion temporal independiente, calibracion y validacion "
            "entre pares. Por tanto, ninguna formula predictiva actual queda "
            "autorizada para trasladarse automaticamente al challenger."
        ),
        "",
        (
            "Esto no invalida los datos ni las formulas tecnicas estandar. La matriz "
            "separa expresamente poder calcular una variable de poder utilizarla "
            "como predictor de TP/SL."
        ),
        "",
        "## Conteos",
        "",
        f"- Reglas exactas registradas: {summary['rules']}.",
        f"- Reglas predictivas o decisionales: {summary['predictive_or_decisional_rules']}.",
        f"- Predictivas validadas temporalmente: {summary['temporally_validated_predictive_rules']}.",
        f"- Predictivas autorizadas en produccion: {summary['production_authorized_predictive_rules']}.",
        f"- Datos permitidos sin inferencia predictiva: {admissions.get('data_allowed_not_predictive', 0)}.",
        f"- Calculos permitidos sin inferencia predictiva: {admissions.get('calculation_allowed_nonpredictive', 0)}.",
        f"- Formulas actuales bloqueadas: {sum(value for key, value in admissions.items() if key.startswith('blocked_'))}.",
        f"- Hipotesis solo para investigacion: {admissions.get('research_only_not_shadow', 0)}.",
        "",
        "## Escalera de fiabilidad",
        "",
    ]
    for tier, description in RELIABILITY_TIERS.items():
        lines.append(f"- `{tier}`: {description} Casos actuales: {tiers.get(tier, 0)}.")
    lines.extend(
        [
            "",
            "## Criterio de admision",
            "",
            (
                "Una regla predictiva solo puede entrar en sombra cuando tiene "
                "afirmacion de fuente acotada, implementacion fiel, coherencia, "
                "traza completa, ablation incremental, holdout temporal, validacion "
                "por pares y horizontes, calibracion y muestra suficiente."
            ),
            "",
            "Ninguna costumbre de trading sustituye estos gates.",
            "",
            "## Clasificacion por familia",
            "",
            "### Datos",
            "",
            (
                "Precio, velas, depth, trades, funding, OI y ratios tienen definicion "
                "oficial. Se admiten como datos con controles de disponibilidad y "
                "frescura. Sus proveedores no respaldan interpretaciones predictivas."
            ),
            "",
            "### Calculos tecnicos",
            "",
            (
                "Las distancias TP/SL, duracion y lado del plan tienen transformaciones "
                "deterministas y la EMA estandar puede calcularse como feature descriptiva. "
                "Ninguna queda autorizada como predictor por ese hecho. RSI y ATR "
                "actuales son variantes no etiquetadas y quedan bloqueados hasta "
                "corregirse o renombrarse. EMA200 fallback queda bloqueada."
            ),
            "",
            "### Hipotesis investigables",
            "",
            (
                "Tendencia, niveles y order flow tienen respaldo suficiente para "
                "formular experimentos. No tienen respaldo para los thresholds y "
                "pesos actuales, por lo que aun no entran en sombra."
            ),
            "",
            "### Reglas bloqueadas",
            "",
            (
                "Todos los pesos del score, los 19 gates de calibracion y las "
                "transformaciones TP/SL actuales quedan bloqueados. Precio-entrada, "
                "caps, SL residual, bandas de probabilidad, confianza y defaults por "
                "datos ausentes tienen ademas fallos de coherencia demostrados."
            ),
            "",
            "### Evidencia interna",
            "",
            (
                "Los gates v0.10/v0.11 permanecen como evidencia provisional del "
                "champion congelado. La traza historica guarda flags pero agrega sus "
                "efectos, de modo que ningun gate individual puede considerarse "
                "validado."
            ),
            "",
            "## Cobertura automatica",
            "",
            f"- Contribuciones E1.4 cubiertas: {matrix['coverage']['direct_ablation_units_expected']}.",
            f"- Gates de calibracion cubiertos: {matrix['coverage']['calibration_flags_expected']}.",
            f"- Funciones predictivas/decisionales E1.2 cubiertas: {matrix['coverage']['predictive_functions_expected']}.",
            f"- SHA-256: `{matrix['matrix_sha256']}`.",
            "",
            "## Siguiente paso",
            "",
            (
                "E1.5.3-E1.5.5 definen el challenger desde cero usando solo datos "
                "admitidos y features calculables. Las hipotesis R2/R3 se incorporaran "
                "una por una como experimentos preregistrados, nunca como pesos heredados."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera la matriz de admisibilidad predictiva regla por regla."
    )
    parser.add_argument("--matrix-output", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    matrix = build_matrix()
    args.matrix_output.parent.mkdir(parents=True, exist_ok=True)
    args.matrix_output.write_text(
        json.dumps(matrix, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report_output.write_text(render_report(matrix), encoding="utf-8")
    print(
        json.dumps(
            {
                "audit_version": AUDIT_VERSION,
                **matrix["summary"],
                "matrix_sha256": matrix["matrix_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
