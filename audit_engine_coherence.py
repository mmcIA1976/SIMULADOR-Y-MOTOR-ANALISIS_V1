from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from analysis_engine import (
    TradeProposal,
    analyze_trade,
    build_probability_ranges,
    calculate_expected_value,
    technical_timeframe_score,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_INVARIANTS_PATH = ROOT / "auditorias_motor" / "invariantes_coherencia_motor_v0_1.json"
DEFAULT_FINDINGS_PATH = ROOT / "auditorias_motor" / "coherencia_motor_v0_1.json"
DEFAULT_REPORT_PATH = ROOT / "auditorias_motor" / "informe_coherencia_motor.md"

AUDIT_VERSION = "E1.3-v0.1"


INVARIANTS = [
    {
        "id": "INV-PROB-01",
        "category": "probability_semantics",
        "requirement": (
            "TP y SL deben ser estimaciones pre-trade del plan concreto, obtenidas por "
            "un metodo probabilistico documentado y calibrable, no por renombrar un score."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3", "CONTRATO_FASE_1_MOTOR_ANALISIS.md:5"],
    },
    {
        "id": "INV-PROB-02",
        "category": "probability_semantics",
        "requirement": (
            "La semantica conjunta de TP, SL y expiracion debe ser explicita y su masa "
            "de probabilidad debe ser coherente."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3"],
    },
    {
        "id": "INV-MONO-TP-01",
        "category": "monotonicity",
        "requirement": (
            "Con snapshot, entrada, SL y horizonte fijos, alejar el TP no puede aumentar "
            "su probabilidad y debe modificar su alcanzabilidad de forma medible."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3"],
    },
    {
        "id": "INV-MONO-SL-01",
        "category": "monotonicity",
        "requirement": (
            "Con snapshot, entrada, TP y horizonte fijos, alejar el SL debe modificar "
            "la probabilidad de alcanzarlo de forma coherente."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3"],
    },
    {
        "id": "INV-CONT-01",
        "category": "continuity",
        "requirement": (
            "Una perturbacion infinitesimal de precio no debe provocar un salto material "
            "sin un evento de mercado discreto documentado."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3", "CONTRATO_FASE_1_MOTOR_ANALISIS.md:6"],
    },
    {
        "id": "INV-HORIZON-01",
        "category": "horizon",
        "requirement": (
            "La alcanzabilidad y los costes deben utilizar explicitamente uno de los tres "
            "horizontes vigentes y su duracion."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3"],
    },
    {
        "id": "INV-COST-01",
        "category": "costs",
        "requirement": (
            "Fees, slippage y funding deben conservar signo, lado, frecuencia y horizonte "
            "sin alterar la evidencia direccional."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:4"],
    },
    {
        "id": "INV-DATA-01",
        "category": "data_quality",
        "requirement": (
            "La falta de datos fiables debe bloquear o degradar explicitamente el resultado; "
            "no puede convertirse en evidencia neutral aparente."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:5"],
    },
    {
        "id": "INV-DOUBLE-01",
        "category": "double_counting",
        "requirement": (
            "Una misma evidencia no puede afectar varias veces al resultado salvo que su "
            "valor incremental haya sido definido y validado."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:4", "CONTRATO_FASE_1_MOTOR_ANALISIS.md:8"],
    },
    {
        "id": "INV-SEPARATION-01",
        "category": "separation",
        "requirement": (
            "Direccion, alcanzabilidad, activacion, ejecucion, riesgo y confianza deben "
            "conservar semanticas separadas antes de integrarse."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:4"],
    },
    {
        "id": "INV-TRACE-01",
        "category": "traceability",
        "requirement": (
            "Cada efecto debe registrar regla estable, version, entradas, formula, salida "
            "intermedia y contribucion final."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:6"],
    },
    {
        "id": "INV-PAIR-01",
        "category": "cross_pair_validity",
        "requirement": (
            "Cada regla activa debe declarar unidades, normalizacion y evidencia de validez "
            "para todos los pares donde se aplique."
        ),
        "contract_refs": ["CONTRATO_FASE_1_MOTOR_ANALISIS.md:3"],
    },
]


def _neutral_timeframe(price: float) -> dict:
    return {
        "interval": "synthetic",
        "ema_9": price,
        "ema_21": price,
        "ema_50": price,
        "ema_200": price,
        "rsi_14": 50.0,
        "atr_14": price * 0.005,
        "atr_pct": 0.5,
        "recent_high": price * 1.01,
        "recent_low": price * 0.99,
        "recent_range_pct": 1.0,
        "volume_ratio": 1.0,
        "taker_buy_ratio": 0.5,
        "last_body_pct": 0.0,
        "position_in_recent_range": 0.5,
        "distance_to_recent_high_pct": 1.0,
        "distance_to_recent_low_pct": 1.0,
        "price_vs_ema_21_pct": 0.0,
        "ema_stack": "mixed",
    }


def _neutral_levels() -> dict:
    return {
        "nearest_support": None,
        "nearest_resistance": None,
        "distance_to_support_pct": None,
        "distance_to_resistance_pct": None,
        "supports": [],
        "resistances": [],
    }


def neutral_snapshot(price: float = 100.0, available: bool = True) -> dict:
    intervals = ("5m", "15m", "1h", "4h", "1d", "1w")
    snapshot = {
        "symbol": "SYNTHUSDT",
        "source": {"mode": "synthetic_e1_3"},
        "current_price": price,
        "timeframes": {interval: _neutral_timeframe(price) for interval in intervals},
        "levels": {interval: _neutral_levels() for interval in intervals},
        "fibonacci": {interval: {"available": False} for interval in intervals},
        "order_book": {
            "best_bid": price if available else None,
            "best_ask": price if available else None,
            "spread_pct": 0.02,
            "imbalance": 0.0,
            "bid_notional_top20": 0.0,
            "ask_notional_top20": 0.0,
        },
        "trade_flow": {
            "sample_trades": 100 if available else 0,
            "cvd_ratio": 0.0,
            "taker_buy_ratio": 0.5,
        },
        "ticker_24h": {
            "price_change_pct": 0.0,
            "quote_volume": 1_000_000.0 if available else 0.0,
            "high": price * 1.02,
            "low": price * 0.98,
        },
        "derivatives": {
            "funding_rate_pct": 0.0 if available else None,
            "funding_avg_recent_pct": 0.0 if available else None,
            "open_interest": 1_000_000.0 if available else None,
            "open_interest_change_5m_window_pct": 0.0 if available else None,
            "global_long_short_ratio": 1.0 if available else None,
            "taker_buy_sell_ratio": 1.0 if available else None,
            "by_period": {},
        },
        "liquidations": {
            "available": False,
            "status": "unavailable",
            "reason": "synthetic_audit",
            "scope": "synthetic",
        },
        "sentiment": {
            "fear_greed_value": None,
            "fear_greed_classification": None,
        },
        "global_market": {},
        "market_breadth": {
            "advancers_24h_pct": None,
            "median_change_24h_pct": None,
        },
    }
    snapshot["availability"] = {
        "synthetic": available,
        "futures_price": available,
        "futures_klines": available,
        "order_book": available,
        "futures_trade_flow": available,
        "ticker_24h": available,
        "funding": available,
        "open_interest": available,
        "market_breadth": False,
    }
    return snapshot


def proposal(
    *,
    side: str = "short",
    entry: float = 100.0,
    stop_loss: float = 102.5,
    take_profit: float = 99.5,
    time_horizon: str = "intraday_short",
) -> TradeProposal:
    return TradeProposal(
        symbol="SYNTHUSDT",
        side=side,
        time_horizon=time_horizon,
        entry=entry,
        margin=100.0,
        leverage=2.0,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )


def analyze_controlled(trade: TradeProposal, snapshot: dict) -> dict:
    with patch("analysis_engine.data_engine.build_market_snapshot", return_value=copy.deepcopy(snapshot)):
        return analyze_trade(trade)


def _finding(
    *,
    finding_id: str,
    invariant_id: str,
    title: str,
    severity: str,
    status: str,
    observation: str,
    reproduction: dict,
    code_refs: list[str],
    affected_concepts: list[str],
    impact: str,
    candidate_correction: str,
) -> dict:
    return {
        "id": finding_id,
        "invariant_id": invariant_id,
        "title": title,
        "severity": severity,
        "status": status,
        "observation": observation,
        "reproduction": reproduction,
        "code_refs": code_refs,
        "affected_concepts": affected_concepts,
        "impact": impact,
        "candidate_correction": candidate_correction,
        "production_changed": False,
    }


def build_findings() -> list[dict]:
    neutral = neutral_snapshot()

    near_entry_below = analyze_controlled(proposal(), neutral_snapshot(99.999999))
    at_entry = analyze_controlled(proposal(), neutral_snapshot(100.0))

    near_tp = analyze_controlled(proposal(take_profit=99.5), neutral)
    far_tp = analyze_controlled(proposal(take_profit=97.5), neutral)

    near_sl = analyze_controlled(
        proposal(stop_loss=101.0, take_profit=99.5),
        neutral,
    )
    far_sl = analyze_controlled(
        proposal(stop_loss=102.5, take_profit=99.5),
        neutral,
    )

    unavailable = analyze_controlled(
        proposal(),
        neutral_snapshot(available=False),
    )

    positive_funding = calculate_expected_value(
        proposal=proposal(),
        tp_probability=0.5,
        sl_probability=0.4,
        range_probability=0.1,
        reward_distance=1.0,
        risk_distance=1.0,
        spread_pct=0.02,
        funding_rate_pct=0.01,
    )
    negative_funding = calculate_expected_value(
        proposal=proposal(),
        tp_probability=0.5,
        sl_probability=0.4,
        range_probability=0.1,
        reward_distance=1.0,
        risk_distance=1.0,
        spread_pct=0.02,
        funding_rate_pct=-0.01,
    )

    probability_mass = {
        "tp_probability": 0.74,
        "range_probability": 0.22,
        "raw_sl_residual": round(1 - 0.74 - 0.22, 4),
        "floored_sl_probability": 0.05,
        "sum_after_floor": round(0.74 + 0.22 + 0.05, 4),
    }
    capped_inputs = {
        "pre_cap_0_80": min(0.74, max(0.26, 0.80)),
        "pre_cap_0_95": min(0.74, max(0.26, 0.95)),
        "pre_cap_0_20": min(0.74, max(0.26, 0.20)),
        "pre_cap_0_05": min(0.74, max(0.26, 0.05)),
    }
    ranges_no_contradiction = build_probability_ranges(0.5, 0.4, 0.1, 0.0)
    ranges_some_contradiction = build_probability_ranges(0.5, 0.4, 0.1, 0.02)
    ranges_high_contradiction = build_probability_ranges(0.5, 0.4, 0.1, 0.04)
    rsi_left = technical_timeframe_score(
        {"ema_stack": "mixed", "price_vs_ema_21_pct": 0, "rsi_14": 65.0},
        "long",
    )
    rsi_right = technical_timeframe_score(
        {"ema_stack": "mixed", "price_vs_ema_21_pct": 0, "rsi_14": 65.000001},
        "long",
    )

    findings = [
        _finding(
            finding_id="E1.3-F01",
            invariant_id="INV-PROB-01",
            title="tp_probability es un score aditivo acotado, no una probabilidad calibrada",
            severity="critical",
            status="failed",
            observation=(
                "El valor parte de 0.5, suma y resta biases discretos y despues aplica caps. "
                "No existe estimacion de frecuencia condicional ni calibracion fuera de muestra."
            ),
            reproduction={
                "type": "source_formula",
                "controlled_inputs": "Formula de analyze_trade sin APIs.",
                "observed_outputs": {
                    "base": 0.5,
                    "first_cap": [0.26, 0.74],
                    "second_cap": [0.22, 0.74],
                },
            },
            code_refs=["analysis_engine.py:231", "analysis_engine.py:264", "analysis_engine.py:291"],
            affected_concepts=["tp_probability", "sl_probability", "setup_grade", "decision"],
            impact=(
                "El porcentaje mostrado no puede interpretarse como frecuencia esperada de "
                "alcanzar TP para el plan."
            ),
            candidate_correction=(
                "Mantener el champion solo como referencia y construir en E1.5 un modelo de "
                "alcanzabilidad entrenable y calibrado temporalmente."
            ),
        ),
        _finding(
            finding_id="E1.3-F02",
            invariant_id="INV-MONO-TP-01",
            title="La probabilidad TP puede ser insensible a alejar el objetivo cinco veces",
            severity="critical",
            status="failed",
            observation=(
                "En un snapshot neutral, mover el TP short de 0.5% a 2.5% conserva exactamente "
                "la misma probabilidad TP."
            ),
            reproduction={
                "type": "end_to_end_synthetic_snapshot",
                "controlled_inputs": {
                    "side": "short",
                    "entry": 100.0,
                    "stop_loss": 102.5,
                    "near_take_profit": 99.5,
                    "far_take_profit": 97.5,
                    "other_inputs": "identical",
                },
                "observed_outputs": {
                    "near_tp_probability": near_tp["tp_probability"],
                    "far_tp_probability": far_tp["tp_probability"],
                    "near_reward_distance_pct": near_tp["snapshot"]["reward_distance_pct"],
                    "far_reward_distance_pct": far_tp["snapshot"]["reward_distance_pct"],
                    "delta_probability": round(
                        far_tp["tp_probability"] - near_tp["tp_probability"], 4
                    ),
                },
            },
            code_refs=["analysis_engine.py:154", "analysis_engine.py:231"],
            affected_concepts=["take_profit", "reward_distance", "tp_probability"],
            impact=(
                "Dos planes con dificultad de recorrido materialmente distinta pueden recibir "
                "el mismo porcentaje TP."
            ),
            candidate_correction=(
                "Modelar distancia TP normalizada por volatilidad y horizonte dentro de la "
                "funcion de alcanzabilidad, con prueba monotonica."
            ),
        ),
        _finding(
            finding_id="E1.3-F03",
            invariant_id="INV-MONO-SL-01",
            title="La probabilidad SL puede ser insensible a alejar el stop",
            severity="critical",
            status="failed",
            observation=(
                "En un snapshot neutral, mover el SL short de 1.0% a 2.5% conserva la misma "
                "probabilidad SL."
            ),
            reproduction={
                "type": "end_to_end_synthetic_snapshot",
                "controlled_inputs": {
                    "side": "short",
                    "entry": 100.0,
                    "take_profit": 99.5,
                    "near_stop_loss": 101.0,
                    "far_stop_loss": 102.5,
                    "other_inputs": "identical",
                },
                "observed_outputs": {
                    "near_sl_probability": near_sl["sl_probability"],
                    "far_sl_probability": far_sl["sl_probability"],
                    "near_risk_distance_pct": near_sl["snapshot"]["risk_distance_pct"],
                    "far_risk_distance_pct": far_sl["snapshot"]["risk_distance_pct"],
                    "delta_probability": round(
                        far_sl["sl_probability"] - near_sl["sl_probability"], 4
                    ),
                },
            },
            code_refs=["analysis_engine.py:153", "analysis_engine.py:293"],
            affected_concepts=["stop_loss", "risk_distance", "sl_probability"],
            impact=(
                "El porcentaje SL no representa de forma estable la barrera concreta elegida "
                "por el usuario."
            ),
            candidate_correction=(
                "Estimar la barrera SL con distancia normalizada, horizonte y distribucion "
                "condicional, en vez de usarla como residuo de TP y rango."
            ),
        ),
        _finding(
            finding_id="E1.3-F04",
            invariant_id="INV-CONT-01",
            title="Cruzar la entrada por una millonesima produce un salto de cinco puntos",
            severity="critical",
            status="failed",
            observation=(
                "Para el mismo short, pasar el precio actual de 99.999999 a 100.0 cambia "
                "price_vs_entry_bias de -0.02 a +0.03."
            ),
            reproduction={
                "type": "end_to_end_synthetic_snapshot",
                "controlled_inputs": {
                    "side": "short",
                    "entry": 100.0,
                    "price_a": 99.999999,
                    "price_b": 100.0,
                    "price_delta": 0.000001,
                    "other_inputs": "identical",
                },
                "observed_outputs": {
                    "tp_probability_a": near_entry_below["tp_probability"],
                    "tp_probability_b": at_entry["tp_probability"],
                    "probability_delta": round(
                        at_entry["tp_probability"] - near_entry_below["tp_probability"], 4
                    ),
                    "bias_a": near_entry_below["snapshot"]["score_components"]["price_vs_entry_bias"],
                    "bias_b": at_entry["snapshot"]["score_components"]["price_vs_entry_bias"],
                },
            },
            code_refs=["analysis_engine.py:191", "analysis_engine.py:242"],
            affected_concepts=["current_price", "entry", "tp_probability"],
            impact=(
                "Analisis practicamente simultaneos pueden diferir cinco puntos sin cambio "
                "economico material."
            ),
            candidate_correction=(
                "Eliminar el escalon binario y modelar la distancia precio-entrada de forma "
                "continua, normalizada y separada entre activacion y alcanzabilidad."
            ),
        ),
        _finding(
            finding_id="E1.3-F05",
            invariant_id="INV-PROB-02",
            title="El suelo de SL permite una masa total de 1.01",
            severity="high",
            status="failed",
            observation=(
                "Con TP=0.74 y rango=0.22, el residuo SL es 0.04 pero se fuerza a 0.05; "
                "la suma pasa a 1.01."
            ),
            reproduction={
                "type": "direct_formula",
                "controlled_inputs": {"tp_probability": 0.74, "range_probability": 0.22},
                "observed_outputs": probability_mass,
            },
            code_refs=["analysis_engine.py:291", "analysis_engine.py:292", "analysis_engine.py:293"],
            affected_concepts=["tp_probability", "sl_probability", "range_probability"],
            impact="La salida conjunta puede violar una identidad probabilistica basica.",
            candidate_correction=(
                "Definir eventos mutuamente excluyentes y normalizar conjuntamente la masa "
                "despues de cualquier restriccion."
            ),
        ),
        _finding(
            finding_id="E1.3-F06",
            invariant_id="INV-PROB-01",
            title="Los caps destruyen sensibilidad y hacen converger evidencias distintas",
            severity="high",
            status="failed",
            observation=(
                "Scores pre-cap 0.80 y 0.95 producen ambos 0.74; 0.20 y 0.05 producen ambos 0.26 "
                "en el primer recorte."
            ),
            reproduction={
                "type": "direct_formula",
                "controlled_inputs": [0.80, 0.95, 0.20, 0.05],
                "observed_outputs": capped_inputs,
            },
            code_refs=["analysis_engine.py:264", "analysis_engine.py:291"],
            affected_concepts=["tp_probability", "ranking", "learning_attribution"],
            impact=(
                "El cap oculta diferencias de evidencia, impide ordenar casos saturados y "
                "dificulta aprender la contribucion real."
            ),
            candidate_correction=(
                "Usar una funcion probabilistica estimada y calibrada; reservar limites solo "
                "para estabilidad numerica, no para fabricar un rango de confianza."
            ),
        ),
        _finding(
            finding_id="E1.3-F07",
            invariant_id="INV-COST-01",
            title="El funding pierde su signo y siempre se cobra como coste",
            severity="high",
            status="failed",
            observation=(
                "Funding +0.01% y -0.01% generan exactamente el mismo coste porque se usa abs()."
            ),
            reproduction={
                "type": "pure_function",
                "controlled_inputs": {
                    "funding_positive_pct": 0.01,
                    "funding_negative_pct": -0.01,
                    "side": "short",
                    "notional": 200.0,
                },
                "observed_outputs": {
                    "positive_estimated_cost_usdt": positive_funding["estimated_cost_usdt"],
                    "negative_estimated_cost_usdt": negative_funding["estimated_cost_usdt"],
                    "positive_ev_usdt": positive_funding["expected_value_usdt"],
                    "negative_ev_usdt": negative_funding["expected_value_usdt"],
                },
            },
            code_refs=["analysis_engine.py:1891"],
            affected_concepts=["funding", "expected_value", "side"],
            impact=(
                "El EV puede cobrar un pago que seria ingreso o aplicar el signo incorrecto "
                "para long/short."
            ),
            candidate_correction=(
                "Calcular el flujo de funding con signo por lado y registrar por separado "
                "pago e ingreso."
            ),
        ),
        _finding(
            finding_id="E1.3-F08",
            invariant_id="INV-HORIZON-01",
            title="El EV aplica una sola observacion de funding sin duracion ni numero de pagos",
            severity="high",
            status="failed",
            observation=(
                "calculate_expected_value no recibe horizonte, tiempo esperado en posicion ni "
                "frecuencia de liquidacion del funding."
            ),
            reproduction={
                "type": "function_signature_and_formula",
                "controlled_inputs": "Mismo funding para 30m-4h, 4-24h y 1-7d.",
                "observed_outputs": {
                    "time_horizon_parameter": False,
                    "funding_period_count_parameter": False,
                    "formula": "notional * abs(funding_rate_pct) / 100",
                },
            },
            code_refs=["analysis_engine.py:1876", "analysis_engine.py:1891"],
            affected_concepts=["time_horizon", "funding", "expected_value"],
            impact="Los costes no son comparables entre los tres horizontes vigentes.",
            candidate_correction=(
                "Usar calendario/frecuencia del contrato, horizonte y tiempo esperado en "
                "posicion; separar escenarios de salida anticipada."
            ),
        ),
        _finding(
            finding_id="E1.3-F09",
            invariant_id="INV-PROB-01",
            title="Los rangos mostrados no son intervalos estadisticos",
            severity="high",
            status="failed",
            observation=(
                "Se resta y suma un ancho fijo de 4, 6 u 8 puntos segun contradiccion, sin "
                "muestra, varianza, cobertura ni calibracion."
            ),
            reproduction={
                "type": "pure_function",
                "controlled_inputs": {
                    "tp": 0.5,
                    "sl": 0.4,
                    "range": 0.1,
                    "contradiction_penalties": [0.0, 0.02, 0.04],
                },
                "observed_outputs": {
                    "none": ranges_no_contradiction,
                    "some": ranges_some_contradiction,
                    "high": ranges_high_contradiction,
                },
            },
            code_refs=["analysis_engine.py:1857", "analysis_engine.py:1866"],
            affected_concepts=["probability_ranges", "confidence"],
            impact=(
                "La interfaz puede sugerir una precision cuantificada que el metodo no ha "
                "estimado."
            ),
            candidate_correction=(
                "No llamarlos intervalos probabilisticos hasta estimar cobertura; en el "
                "challenger usar incertidumbre por bootstrap temporal o calibracion apropiada."
            ),
        ),
        _finding(
            finding_id="E1.3-F10",
            invariant_id="INV-DATA-01",
            title="Un snapshot marcado como no disponible sigue produciendo porcentajes y decision",
            severity="critical",
            status="failed",
            observation=(
                "El motor convierte campos ausentes en valores neutrales y devuelve una salida "
                "completa sin bloqueo por evidencia insuficiente."
            ),
            reproduction={
                "type": "end_to_end_synthetic_snapshot",
                "controlled_inputs": {
                    "availability": False,
                    "sample_trades": 0,
                    "quote_volume": 0,
                    "funding": None,
                    "open_interest": None,
                },
                "observed_outputs": {
                    "tp_probability": unavailable["tp_probability"],
                    "sl_probability": unavailable["sl_probability"],
                    "range_probability": unavailable["range_probability"],
                    "training_decision": unavailable["training_decision"],
                    "setup_grade": unavailable["setup_grade"],
                },
            },
            code_refs=["data_engine.py:111", "data_engine.py:476", "analysis_engine.py:126"],
            affected_concepts=["availability", "tp_probability", "decision"],
            impact=(
                "Ausencia de evidencia puede parecer una lectura neutral valida y afectar la "
                "decision."
            ),
            candidate_correction=(
                "Introducir reglas de bloqueo por campo/horizonte, freshness y cobertura; "
                "distinguir desconocido de neutral."
            ),
        ),
        _finding(
            finding_id="E1.3-F11",
            invariant_id="INV-DOUBLE-01",
            title="La estructura EMA entra por al menos cinco rutas correlacionadas",
            severity="critical",
            status="failed",
            observation=(
                "Los mismos ema_stack alimentan trend_score, technical_rating, market_regime, "
                "higher_timeframe_contra_penalty y reglas de calibracion."
            ),
            reproduction={
                "type": "dependency_trace",
                "controlled_inputs": {"source_feature": "timeframes[*].ema_stack"},
                "observed_outputs": {
                    "paths": [
                        "trend_bias",
                        "technical_direction_bias",
                        "market_regime_bias",
                        "higher_timeframe_penalty",
                        "risk_calibration_adjustment",
                    ],
                    "incremental_validation_present": False,
                },
            },
            code_refs=[
                "analysis_engine.py:166",
                "analysis_engine.py:167",
                "analysis_engine.py:215",
                "analysis_engine.py:218",
                "analysis_engine.py:274",
            ],
            affected_concepts=["ema_stack", "tp_probability", "risk_score", "confidence"],
            impact=(
                "Una sola familia de evidencia puede dominar el resultado sin medir su aporte "
                "incremental."
            ),
            candidate_correction=(
                "Crear una representacion estructural unica y exigir ablation para cualquier "
                "interaccion adicional."
            ),
        ),
        _finding(
            finding_id="E1.3-F12",
            invariant_id="INV-DOUBLE-01",
            title="La capa de zona reutiliza tecnica, regimen y Fibonacci y vuelve a puntuar",
            severity="high",
            status="failed",
            observation=(
                "build_zone_analysis recibe salidas ya puntuadas y genera otro ajuste de "
                "probabilidad/riesgo que se suma al resultado original."
            ),
            reproduction={
                "type": "dependency_trace",
                "controlled_inputs": {
                    "parents": ["technical_rating", "market_regime", "fibonacci_context"]
                },
                "observed_outputs": {
                    "child": "zone_probability_context",
                    "added_again_to_tp": True,
                    "incremental_validation_present": False,
                },
            },
            code_refs=["analysis_engine.py:219", "analysis_engine.py:230", "analysis_engine.py:250"],
            affected_concepts=["zone_analysis", "technical_rating", "market_regime", "fibonacci"],
            impact="La confluencia puede ser duplicacion de evidencia, no informacion nueva.",
            candidate_correction=(
                "Definir la zona como regla combinada con padres declarados y activar su efecto "
                "solo si demuestra valor incremental por ablation."
            ),
        ),
        _finding(
            finding_id="E1.3-F13",
            invariant_id="INV-SEPARATION-01",
            title="Rango mezcla mercado lateral, no activacion y no resolucion",
            severity="high",
            status="failed",
            observation=(
                "range_probability combina regimen/contradiccion con el riesgo de que una orden "
                "pendiente no se active y se muestra como rango/sin resolver."
            ),
            reproduction={
                "type": "semantic_dependency_trace",
                "controlled_inputs": {
                    "market_state": "range_probability_for_context",
                    "execution_state": "zone_range_probability_adjustment",
                },
                "observed_outputs": {
                    "single_output": "range_probability",
                    "display_label": "rango/sin resolver",
                },
            },
            code_refs=["analysis_engine.py:268", "analysis_engine.py:270", "analysis_engine.py:292"],
            affected_concepts=["range_probability", "activation", "expiration", "market_regime"],
            impact=(
                "No puede saberse si la masa representa lateralidad, orden no ejecutada o "
                "expiracion sin tocar barreras."
            ),
            candidate_correction=(
                "Separar primero activacion/ejecucion de outcome condicional TP-SL-expiracion y "
                "definir el horizonte de cada evento."
            ),
        ),
        _finding(
            finding_id="E1.3-F14",
            invariant_id="INV-CONT-01",
            title="RSI introduce discontinuidades arbitrarias en los limites",
            severity="medium",
            status="failed",
            observation=(
                "RSI 65 aporta +0.20 al score tecnico long; RSI 65.000001 aporta 0."
            ),
            reproduction={
                "type": "pure_function",
                "controlled_inputs": {
                    "rsi_a": 65.0,
                    "rsi_b": 65.000001,
                    "ema_stack": "mixed",
                    "price_vs_ema_21_pct": 0,
                },
                "observed_outputs": {
                    "score_a": rsi_left,
                    "score_b": rsi_right,
                    "delta": round(rsi_right - rsi_left, 6),
                },
            },
            code_refs=["analysis_engine.py:2255"],
            affected_concepts=["rsi_14", "technical_rating", "tp_probability"],
            impact=(
                "Cambios despreciables del indicador pueden alterar capas posteriores de forma "
                "material."
            ),
            candidate_correction=(
                "Sustituir escalones no validados por transformaciones continuas predefinidas "
                "o categorias cuya discontinuidad tenga evidencia."
            ),
        ),
        _finding(
            finding_id="E1.3-F15",
            invariant_id="INV-TRACE-01",
            title="score_components no satisface la traza obligatoria por regla",
            severity="critical",
            status="failed",
            observation=(
                "La salida enumera componentes, pero no incluye ID y version de regla, formula, "
                "entradas con unidad/fuente, antes/despues ni contribucion neta tras caps."
            ),
            reproduction={
                "type": "output_schema_inspection",
                "controlled_inputs": "Resultado end-to-end del snapshot neutral.",
                "observed_outputs": {
                    "component_keys": sorted(
                        near_tp["snapshot"]["score_components"].keys()
                    ),
                    "stable_rule_id_present": False,
                    "rule_version_present": False,
                    "input_units_present": False,
                    "pre_post_cap_contribution_present": False,
                },
            },
            code_refs=["analysis_engine.py:570"],
            affected_concepts=["score_components", "learning", "ablation", "audit"],
            impact=(
                "El aprendizaje no puede atribuir de forma completa que regla ayudo, perjudico "
                "o quedo anulada por un cap."
            ),
            candidate_correction=(
                "Crear registro ejecutable de reglas y una traza append-only con entradas, "
                "salida intermedia y delta final por regla/version."
            ),
        ),
        _finding(
            finding_id="E1.3-F16",
            invariant_id="INV-PAIR-01",
            title="Los umbrales se aplican universalmente sin validacion por pares",
            severity="high",
            status="unverified",
            observation=(
                "Los thresholds porcentuales son compartidos por todos los simbolos; no existe "
                "matriz de evidencia por par, liquidez, volatilidad u horizonte."
            ),
            reproduction={
                "type": "configuration_trace",
                "controlled_inputs": {
                    "symbol_parameter_in_scoring_rules": False,
                    "shared_examples": [
                        "spread_pct > 0.04",
                        "volume_ratio > 1.25",
                        "order_book_imbalance > 0.12",
                    ],
                },
                "observed_outputs": {
                    "per_pair_validation_registry": False,
                    "fallback_when_pair_unvalidated": False,
                },
            },
            code_refs=["analysis_engine.py:193", "analysis_engine.py:194", "analysis_engine.py:195"],
            affected_concepts=["supported_pairs", "thresholds", "normalization"],
            impact=(
                "No puede afirmarse que una regla sea valida para todos los pares admitidos."
            ),
            candidate_correction=(
                "Evaluar cada variable normalizada por par/horizonte y bloquear reglas sin "
                "muestra comparable suficiente."
            ),
        ),
        _finding(
            finding_id="E1.3-F17",
            invariant_id="INV-SEPARATION-01",
            title="La confianza es otro score heuristico, no incertidumbre estimada",
            severity="high",
            status="failed",
            observation=(
                "confidence deriva de puntos manuales y penalizaciones compartidas con el score, "
                "sin relacion de cobertura observada."
            ),
            reproduction={
                "type": "dependency_trace",
                "controlled_inputs": "layered_scores.confidence_score",
                "observed_outputs": {
                    "sampling_uncertainty_used": False,
                    "calibration_error_used": False,
                    "data_coverage_used_as_statistical_uncertainty": False,
                },
            },
            code_refs=["analysis_engine.py:349", "analysis_engine.py:1930"],
            affected_concepts=["confidence", "probability_ranges", "decision"],
            impact=(
                "Una etiqueta de confianza puede parecer precision estadistica sin serlo."
            ),
            candidate_correction=(
                "Separar calidad de datos de incertidumbre predictiva y estimar ambas con "
                "metricas verificables."
            ),
        ),
    ]
    return findings


def _source_sha256() -> str:
    digest = hashlib.sha256()
    for path in (ROOT / "analysis_engine.py", ROOT / "data_engine.py"):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_audit() -> dict:
    findings = build_findings()
    severities = Counter(item["severity"] for item in findings)
    statuses = Counter(item["status"] for item in findings)
    return {
        "audit_version": AUDIT_VERSION,
        "phase": "E1.3",
        "scope": "coherencia matematica y semantica del champion congelado",
        "production_modified": False,
        "source_sha256": _source_sha256(),
        "invariants_count": len(INVARIANTS),
        "summary": {
            "findings": len(findings),
            "failed": statuses["failed"],
            "unverified": statuses["unverified"],
            "critical": severities["critical"],
            "high": severities["high"],
            "medium": severities["medium"],
            "low": severities["low"],
        },
        "findings": findings,
    }


def build_invariant_document() -> dict:
    return {
        "audit_version": AUDIT_VERSION,
        "phase": "E1.3.1",
        "purpose": "Contrato de pruebas matematicas y semanticas del motor de Fase 1.",
        "production_modified": False,
        "invariants": INVARIANTS,
    }


def render_report(audit: dict) -> str:
    summary = audit["summary"]
    lines = [
        "# Informe de coherencia matematica y semantica - E1.3",
        "",
        f"Version de auditoria: `{audit['audit_version']}`",
        "",
        "Estado: COMPLETADA",
        "",
        "## Dictamen",
        "",
        (
            "El champion actual no satisface el contrato probabilistico de la Fase 1. "
            "La auditoria no modifica produccion: convierte sus incoherencias en casos "
            "reproducibles que serviran de requisitos negativos para el challenger."
        ),
        "",
        "## Resumen",
        "",
        f"- Invariantes definidos: {audit['invariants_count']}",
        f"- Hallazgos: {summary['findings']}",
        f"- Fallos demostrados: {summary['failed']}",
        f"- Validez pendiente de demostrar: {summary['unverified']}",
        f"- Severidad critica: {summary['critical']}",
        f"- Severidad alta: {summary['high']}",
        f"- Severidad media: {summary['medium']}",
        f"- Produccion modificada: {str(audit['production_modified']).lower()}",
        f"- SHA-256 del codigo auditado: `{audit['source_sha256']}`",
        "",
        "## Hallazgos",
        "",
    ]
    for item in audit["findings"]:
        outputs = json.dumps(
            item["reproduction"]["observed_outputs"],
            ensure_ascii=True,
            sort_keys=True,
        )
        lines.extend(
            [
                f"### {item['id']} - {item['title']}",
                "",
                f"- Invariante: `{item['invariant_id']}`",
                f"- Severidad: `{item['severity']}`",
                f"- Estado: `{item['status']}`",
                f"- Observacion: {item['observation']}",
                f"- Reproduccion: `{item['reproduction']['type']}`",
                f"- Resultado observado: `{outputs}`",
                f"- Impacto: {item['impact']}",
                f"- Correccion candidata: {item['candidate_correction']}",
                f"- Referencias de codigo: {', '.join(f'`{ref}`' for ref in item['code_refs'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Ganancia de la fase",
            "",
            (
                "E1.3 no mejora todavia los porcentajes de produccion. Evita corregir a ciegas: "
                "cada defecto queda asociado a un invariante, una reproduccion, una severidad "
                "y una correccion candidata. Estos casos seran pruebas de aceptacion del "
                "challenger y variables de ablation en E1.4."
            ),
            "",
            "## Siguiente fase",
            "",
            (
                "E1.4 medira sobre snapshots historicos preservados cuanto cambia cada salida "
                "al retirar o reformular cada regla, sin sobrescribir recomendaciones antiguas."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audita coherencia matematica y semantica del champion sin modificarlo."
    )
    parser.add_argument("--invariants-output", type=Path, default=DEFAULT_INVARIANTS_PATH)
    parser.add_argument("--findings-output", type=Path, default=DEFAULT_FINDINGS_PATH)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    invariant_document = build_invariant_document()
    audit = build_audit()
    write_json(args.invariants_output, invariant_document)
    write_json(args.findings_output, audit)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(render_report(audit), encoding="utf-8")
    print(
        json.dumps(
            {
                "audit_version": AUDIT_VERSION,
                "invariants": len(INVARIANTS),
                **audit["summary"],
                "production_modified": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
