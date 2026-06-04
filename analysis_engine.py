from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import data_engine


ENGINE_VERSION = "rules-v0.6-timeframe-weighted"
TIME_HORIZON_PROFILES = {
    "intraday_short": {
        "label": "Intradia corto",
        "duration": "30 min-4 h",
        "max_minutes": 240,
        "primary_timeframes": ["5m", "15m"],
        "confirmation_timeframe": "1h",
        "momentum_timeframe": "5m",
        "volatility_timeframe": "5m",
        "volume_timeframe": "5m",
        "levels_timeframe": "1h",
        "derivatives_period": "5m",
        "trend_weights": {"5m": 1.25, "15m": 1.35, "1h": 1.0, "4h": 0.45, "1d": 0.15},
        "micro_weight": 1.0,
        "derivatives_weight": 0.85,
        "macro_weight": 0.15,
        "htf_penalty_weight": 0.6,
        "funding_weight": 0.35,
        "atr_timeframe": "5m/15m",
        "focus": "flujo inmediato, CVD, order book, RSI corto y zonas intradia",
    },
    "intraday_wide": {
        "label": "Intradia amplio",
        "duration": "4-24 h",
        "max_minutes": 1440,
        "primary_timeframes": ["15m", "1h"],
        "confirmation_timeframe": "4h",
        "momentum_timeframe": "1h",
        "volatility_timeframe": "15m",
        "volume_timeframe": "1h",
        "levels_timeframe": "4h",
        "derivatives_period": "1h",
        "trend_weights": {"5m": 0.35, "15m": 1.1, "1h": 1.35, "4h": 1.0, "1d": 0.35},
        "micro_weight": 0.55,
        "derivatives_weight": 1.0,
        "macro_weight": 0.35,
        "htf_penalty_weight": 1.0,
        "funding_weight": 0.75,
        "atr_timeframe": "15m/1h",
        "focus": "estructura 1h/4h, derivados por 1h, OI/funding y maximos/minimos diarios",
    },
    "short_swing": {
        "label": "Swing corto",
        "duration": "1-7 dias",
        "max_minutes": 10080,
        "primary_timeframes": ["4h", "1d"],
        "confirmation_timeframe": "1w",
        "momentum_timeframe": "4h",
        "volatility_timeframe": "4h",
        "volume_timeframe": "4h",
        "levels_timeframe": "1d",
        "derivatives_period": "1d",
        "trend_weights": {"5m": 0.1, "15m": 0.2, "1h": 0.75, "4h": 1.5, "1d": 1.6},
        "micro_weight": 0.2,
        "derivatives_weight": 1.1,
        "macro_weight": 0.85,
        "htf_penalty_weight": 1.35,
        "funding_weight": 1.25,
        "atr_timeframe": "4h/1d",
        "focus": "estructura 4h/1d, amplitud crypto, sentimiento, funding acumulado y contexto macro",
    },
}


@dataclass(frozen=True)
class TradeProposal:
    symbol: str
    side: str
    time_horizon: str
    entry: float
    margin: float
    leverage: float
    stop_loss: float
    take_profit: float


def pct_from_entry(target: float, entry: float) -> float:
    if entry == 0:
        return 0
    return abs((target - entry) / entry) * 100


def time_horizon_profile(value: str) -> dict:
    return TIME_HORIZON_PROFILES.get(value, TIME_HORIZON_PROFILES["intraday_short"])


def timeframe_for(timeframes: dict, key: str, fallback: str = "5m") -> dict:
    return timeframes.get(key) or timeframes.get(fallback) or next(iter(timeframes.values()))


def derivatives_for_horizon(derivatives: dict, horizon_profile: dict) -> dict:
    period = horizon_profile.get("derivatives_period", "5m")
    by_period = derivatives.get("by_period") or {}
    selected = by_period.get(period) or {}
    return {
        "period": period,
        "open_interest_change_pct": selected.get("open_interest_change_pct", derivatives.get("open_interest_change_5m_window_pct")),
        "global_long_short_ratio": selected.get("global_long_short_ratio", derivatives.get("global_long_short_ratio")),
        "taker_buy_sell_ratio": selected.get("taker_buy_sell_ratio", derivatives.get("taker_buy_sell_ratio")),
        "taker_buy_volume": selected.get("taker_buy_volume", derivatives.get("taker_buy_volume")),
        "taker_sell_volume": selected.get("taker_sell_volume", derivatives.get("taker_sell_volume")),
    }


def analyze_trade(proposal: TradeProposal) -> dict:
    horizon_profile = time_horizon_profile(proposal.time_horizon)
    market_snapshot = data_engine.build_market_snapshot(proposal.symbol)
    current_price = market_snapshot["current_price"]
    tf_5m = market_snapshot["timeframes"]["5m"]
    tf_1h = market_snapshot["timeframes"]["1h"]
    order_book = market_snapshot["order_book"]
    trade_flow = market_snapshot["trade_flow"]
    ticker_24h = market_snapshot["ticker_24h"]
    derivatives = market_snapshot["derivatives"]
    levels = market_snapshot["levels"]
    sentiment = market_snapshot["sentiment"]
    global_market = market_snapshot["global_market"]
    market_breadth = market_snapshot["market_breadth"]
    momentum_tf_key = horizon_profile["momentum_timeframe"]
    volatility_tf_key = horizon_profile["volatility_timeframe"]
    volume_tf_key = horizon_profile["volume_timeframe"]
    levels_tf_key = horizon_profile["levels_timeframe"]
    tf_momentum = timeframe_for(market_snapshot["timeframes"], momentum_tf_key)
    tf_volatility = timeframe_for(market_snapshot["timeframes"], volatility_tf_key)
    tf_volume = timeframe_for(market_snapshot["timeframes"], volume_tf_key)
    levels_for_horizon = levels.get(levels_tf_key, levels.get("1h", {}))
    derivatives_horizon = derivatives_for_horizon(derivatives, horizon_profile)

    recent_range_pct = tf_volatility["recent_range_pct"]
    volume_ratio = tf_volume["volume_ratio"]
    atr_pct = tf_volatility["atr_pct"]
    order_book_imbalance = order_book["imbalance"]
    spread_pct = order_book["spread_pct"]
    microprice_bias_pct = order_book.get("microprice_bias_pct", 0)
    slope_imbalance = (order_book.get("book_slope") or {}).get("slope_imbalance", 0)
    rsi_signal = tf_momentum["rsi_14"]
    funding_rate_pct = derivatives.get("funding_rate_pct")
    taker_buy_sell_ratio = derivatives_horizon.get("taker_buy_sell_ratio")
    global_long_short_ratio = derivatives_horizon.get("global_long_short_ratio")
    open_interest_change_pct = derivatives_horizon.get("open_interest_change_pct")

    risk_distance = pct_from_entry(proposal.stop_loss, proposal.entry)
    reward_distance = pct_from_entry(proposal.take_profit, proposal.entry)
    rr_ratio = reward_distance / max(risk_distance, 0.000001)
    leverage_penalty = max(0, proposal.leverage - 5) * 0.018

    micro_weight = horizon_profile["micro_weight"]
    derivatives_weight = horizon_profile["derivatives_weight"]
    macro_weight = horizon_profile["macro_weight"]
    funding_weight = horizon_profile["funding_weight"]
    trend_bias = trend_score(proposal.side, market_snapshot["timeframes"], proposal.time_horizon)
    technical_rating = build_technical_rating(
        proposal=proposal,
        timeframes=market_snapshot["timeframes"],
        levels=levels,
        horizon_profile=horizon_profile,
        reward_distance=reward_distance,
        atr_pct=atr_pct,
    )
    if proposal.side == "long":
        price_vs_entry_bias = 0.03 if current_price <= proposal.entry else -0.02
        order_book_bias = (0.025 if order_book_imbalance > 0.12 else -0.025 if order_book_imbalance < -0.12 else 0) * micro_weight
        microstructure_bias = microstructure_score(proposal.side, microprice_bias_pct, slope_imbalance) * micro_weight
        momentum_bias = (-0.025 if rsi_signal > 72 else 0.02 if 45 <= rsi_signal <= 62 else 0) * micro_weight
    else:
        price_vs_entry_bias = 0.03 if current_price >= proposal.entry else -0.02
        order_book_bias = (0.025 if order_book_imbalance < -0.12 else -0.025 if order_book_imbalance > 0.12 else 0) * micro_weight
        microstructure_bias = microstructure_score(proposal.side, microprice_bias_pct, slope_imbalance) * micro_weight
        momentum_bias = (-0.025 if rsi_signal < 28 else 0.02 if 38 <= rsi_signal <= 55 else 0) * micro_weight

    volatility_penalty = 0.07 if risk_distance < max(recent_range_pct, atr_pct) * 0.35 else 0
    volume_bias = (0.025 if volume_ratio > 1.25 else -0.015 if volume_ratio < 0.65 else 0) * max(0.5, micro_weight)
    liquidity_penalty = 0.03 if spread_pct > 0.04 else 0
    overextension_penalty = 0.025 if abs(tf_momentum["price_vs_ema_21_pct"]) > max(0.5, atr_pct * 1.8) else 0
    funding_penalty = funding_context_penalty(proposal.side, funding_rate_pct) * funding_weight
    taker_flow_bias = taker_flow_score(proposal.side, taker_buy_sell_ratio) * derivatives_weight
    crowding_penalty = crowding_penalty_score(proposal.side, global_long_short_ratio) * derivatives_weight
    cvd_bias = cvd_flow_score(proposal.side, trade_flow.get("cvd_ratio")) * micro_weight
    level_penalty = level_risk_penalty(proposal, levels_for_horizon)
    sentiment_penalty = sentiment_extreme_penalty(proposal.side, sentiment.get("fear_greed_value")) * max(0.25, macro_weight)
    oi_trend_bias = open_interest_trend_score(proposal.side, ticker_24h["price_change_pct"], open_interest_change_pct) * derivatives_weight
    breadth_bias = market_breadth_score(proposal.side, market_breadth.get("advancers_24h_pct"), market_breadth.get("median_change_24h_pct")) * max(0.5, macro_weight)
    funding_relative_penalty = funding_relative_context_penalty(proposal.side, funding_rate_pct, derivatives.get("funding_avg_recent_pct")) * funding_weight
    htf_penalty = higher_timeframe_contra_penalty(proposal.side, market_snapshot["timeframes"], proposal.time_horizon)
    oi_context_penalty = oi_price_context_penalty(proposal.side, ticker_24h["price_change_pct"], open_interest_change_pct) * derivatives_weight
    contradiction_penalty = combined_contradiction_penalty(
        proposal.side,
        cvd_bias,
        taker_flow_bias,
        oi_context_penalty,
        level_penalty,
        htf_penalty,
    )
    market_regime = classify_market_regime(market_snapshot["timeframes"], recent_range_pct, atr_pct, proposal.side)

    tp_probability = (
        0.5
        + trend_bias
        + technical_rating["direction_bias"]
        + price_vs_entry_bias
        + volume_bias
        + order_book_bias
        + microstructure_bias
        + momentum_bias
        + taker_flow_bias
        + cvd_bias
        + oi_trend_bias
        + breadth_bias
        - volatility_penalty
        - leverage_penalty
        - liquidity_penalty
        - overextension_penalty
        - funding_penalty
        - funding_relative_penalty
        - crowding_penalty
        - level_penalty
        - sentiment_penalty
        - htf_penalty
        - technical_rating["entry_timing_penalty"]
        - technical_rating["barrier_penalty"]
        - oi_context_penalty
        - contradiction_penalty
    )
    tp_probability = min(0.74, max(0.26, tp_probability))
    range_probability = range_probability_for_context(recent_range_pct, contradiction_penalty, market_regime)
    sl_probability = max(0.05, 1 - tp_probability - range_probability)
    probability_ranges = build_probability_ranges(tp_probability, sl_probability, range_probability, contradiction_penalty)
    margin_risk_pct = risk_distance * proposal.leverage
    margin_reward_pct = reward_distance * proposal.leverage
    expected_value = calculate_expected_value(
        proposal=proposal,
        tp_probability=tp_probability,
        sl_probability=sl_probability,
        range_probability=range_probability,
        reward_distance=reward_distance,
        risk_distance=risk_distance,
        spread_pct=spread_pct,
        funding_rate_pct=funding_rate_pct,
        time_horizon=proposal.time_horizon,
    )
    break_even_probability = 1 / (1 + rr_ratio) if rr_ratio > 0 else 1
    layered_scores = build_layered_scores(
        tp_probability=tp_probability,
        rr_ratio=rr_ratio,
        margin_risk_pct=margin_risk_pct,
        volatility_penalty=volatility_penalty,
        level_penalty=level_penalty,
        liquidity_penalty=liquidity_penalty,
        spread_pct=spread_pct,
        contradiction_penalty=contradiction_penalty,
        htf_penalty=htf_penalty,
        taker_flow_bias=taker_flow_bias,
        cvd_bias=cvd_bias,
        technical_rating=technical_rating,
        expected_value=expected_value,
    )

    risk_score = (
        (0.25 if proposal.leverage >= 8 else 0.08 if proposal.leverage >= 5 else 0)
        + (0.2 if risk_distance < max(recent_range_pct, atr_pct) * 0.35 else 0)
        + (0.12 if rr_ratio < 1.2 else 0)
        + (0.08 if recent_range_pct > 2.5 else 0)
        + (0.06 if spread_pct > 0.04 else 0)
        + (0.05 if overextension_penalty else 0)
        + (0.06 if funding_penalty else 0)
        + (0.04 if funding_relative_penalty else 0)
        + (0.04 if crowding_penalty else 0)
        + (0.05 if level_penalty else 0)
        + (0.03 if sentiment_penalty else 0)
        + (0.07 if htf_penalty else 0)
        + (0.05 if technical_rating["entry_timing_penalty"] else 0)
        + (0.05 if technical_rating["barrier_penalty"] else 0)
        + (0.08 if contradiction_penalty >= 0.03 else 0)
    )
    if risk_score >= 0.42:
        risk_level = "alto"
    elif risk_score >= 0.24:
        risk_level = "medio-alto"
    elif risk_score >= 0.12:
        risk_level = "medio"
    else:
        risk_level = "bajo"

    setup_grade = grade_from_scores(tp_probability, risk_score, layered_scores["expected_value_score"])
    confidence = confidence_from_score(layered_scores["confidence_score"])
    expected_value = annotate_expected_value_threshold(expected_value, risk_level, confidence)

    reasons: list[str] = []
    alerts: list[str] = []
    horizon_label = f"{horizon_profile['label']} ({horizon_profile['duration']})"
    reasons.append(
        f"Marco temporal elegido: {horizon_label}. Pesan mas {', '.join(horizon_profile['primary_timeframes'])} y confirma {horizon_profile['confirmation_timeframe']}."
    )
    if trend_bias > 0:
        reasons.append("La tendencia ponderada por horizonte acompana la direccion propuesta.")
    elif trend_bias < 0:
        reasons.append("La tendencia ponderada por horizonte va contra la direccion propuesta.")
    else:
        reasons.append("La tendencia ponderada por horizonte esta mixta y no ofrece ventaja clara.")
    if rr_ratio >= 1.5:
        reasons.append("La relacion riesgo/beneficio es razonable para entrenamiento.")
    else:
        reasons.append("La relacion riesgo/beneficio es ajustada.")
    if volatility_penalty:
        alerts.append("El stop parece cerca respecto a la volatilidad/ATR reciente.")
    if proposal.leverage >= 8:
        alerts.append("Apalancamiento agresivo: x8-x10 aumenta el riesgo de barrido.")
    if volume_bias > 0:
        reasons.append("El volumen reciente esta por encima de su media corta.")
    if order_book_bias > 0:
        reasons.append("El order book cercano favorece ligeramente la direccion propuesta.")
    elif order_book_bias < 0:
        alerts.append("El order book cercano va contra la direccion propuesta.")
    if microstructure_bias > 0:
        reasons.append("Microestructura: microprice/book slope acompanan ligeramente la direccion.")
    elif microstructure_bias < 0:
        alerts.append("Microestructura: microprice/book slope contradicen ligeramente la direccion.")
    if liquidity_penalty:
        alerts.append("El spread es elevado para una entrada limpia.")
    if overextension_penalty:
        alerts.append("El precio esta extendido respecto a EMA 21 en 5m.")
    if funding_penalty:
        alerts.append("Funding/posicionamiento de derivados potencialmente caro o saturado para esta direccion.")
    if funding_relative_penalty:
        alerts.append("El funding actual esta elevado frente a su media reciente; posible saturacion de posicionamiento.")
    if taker_flow_bias > 0:
        reasons.append("El flujo taker de derivados acompana la direccion propuesta.")
    elif taker_flow_bias < 0:
        alerts.append("El flujo taker de derivados va contra la direccion propuesta.")
    if cvd_bias > 0:
        reasons.append("El CVD spot reciente acompana la direccion propuesta.")
    elif cvd_bias < 0:
        alerts.append("El CVD spot reciente va contra la direccion propuesta.")
    if level_penalty:
        alerts.append("La operacion esta cerca de una zona tecnica que puede limitar el recorrido o barrer el stop.")
    if sentiment_penalty:
        alerts.append("El sentimiento de mercado esta extremo y aumenta el riesgo de entrada tardia.")
    if oi_trend_bias > 0:
        reasons.append("El cambio reciente de open interest acompana la lectura direccional.")
    elif oi_trend_bias < 0:
        alerts.append("El cambio reciente de open interest no acompana la direccion propuesta.")
    if oi_context_penalty:
        alerts.append("Precio y open interest muestran menor conviccion: posible movimiento por cierre de posiciones, no por entrada nueva.")
    if breadth_bias > 0:
        reasons.append("La amplitud del mercado crypto acompana la direccion propuesta.")
    elif breadth_bias < 0:
        alerts.append("La amplitud del mercado crypto va contra la direccion propuesta.")
    if htf_penalty:
        alerts.append("La temporalidad 4h contradice la direccion propuesta y reduce la confianza estructural.")
    if technical_rating["direction_bias"] > 0:
        reasons.append("La capa tecnica ponderada por temporalidad confirma parcialmente la direccion.")
    elif technical_rating["direction_bias"] < 0:
        alerts.append("La capa tecnica ponderada por temporalidad contradice la direccion.")
    if technical_rating["entry_timing_penalty"]:
        alerts.append("El timing tecnico sugiere entrada tardia o extendida para el marco temporal elegido.")
    if technical_rating["barrier_penalty"]:
        alerts.append("El objetivo queda condicionado por una barrera tecnica cercana antes del TP.")
    if contradiction_penalty:
        alerts.append("Hay contradiccion combinada entre capas: el motor reduce confianza antes de aumentar probabilidad.")
    if expected_value["expected_value_pct_margin"] < expected_value["minimum_required_pct_margin"]:
        alerts.append("La EV neta positiva no alcanza el umbral minimo exigido para este riesgo/confianza.")

    suggested_leverage = min(proposal.leverage, 5) if risk_score >= 0.24 else proposal.leverage
    parameter_advice = {
        "entry": {"action": "mantener", "suggested_value": proposal.entry, "reason": "Primera version: no hay senal suficiente para modificar entrada."},
        "stop_loss": {"action": "revisar" if volatility_penalty else "mantener", "suggested_value": proposal.stop_loss, "reason": "Se evalua contra volatilidad reciente."},
        "take_profit": {"action": "mantener", "suggested_value": proposal.take_profit, "reason": "Objetivo usado para calcular relacion riesgo/beneficio."},
        "leverage": {"action": "reducir" if suggested_leverage < proposal.leverage else "mantener", "suggested_value": suggested_leverage, "reason": "Se penaliza apalancamiento alto con riesgo medio-alto o alto."},
    }

    decision = decision_from_context(setup_grade, risk_level, confidence, expected_value)
    invalidation_rules = build_invalidation_rules(proposal, market_regime, levels_for_horizon, taker_flow_bias, cvd_bias)
    plan_liquidity = build_plan_liquidity_profile(proposal, order_book)
    cvd_price_profile = build_cvd_price_profile(proposal.side, trade_flow)
    derivatives_profile = build_derivatives_profile(
        side=proposal.side,
        price_change_24h_pct=ticker_24h["price_change_pct"],
        derivatives=derivatives,
        derivatives_horizon=derivatives_horizon,
        taker_flow_bias=taker_flow_bias,
        oi_trend_bias=oi_trend_bias,
        funding_penalty=funding_penalty,
        funding_relative_penalty=funding_relative_penalty,
        crowding_penalty=crowding_penalty,
        oi_context_penalty=oi_context_penalty,
    )
    pattern_tags = build_pattern_tags(
        proposal=proposal,
        market_regime=market_regime,
        technical_rating=technical_rating,
        risk_distance=risk_distance,
        reward_distance=reward_distance,
        atr_pct=atr_pct,
        recent_range_pct=recent_range_pct,
        order_book_imbalance=order_book_imbalance,
        microprice_bias_pct=microprice_bias_pct,
        slope_imbalance=slope_imbalance,
        microstructure_bias=microstructure_bias,
        cvd_bias=cvd_bias,
        taker_flow_bias=taker_flow_bias,
        funding_penalty=funding_penalty,
        funding_relative_penalty=funding_relative_penalty,
        level_penalty=level_penalty,
        htf_penalty=htf_penalty,
        oi_context_penalty=oi_context_penalty,
        contradiction_penalty=contradiction_penalty,
        plan_liquidity=plan_liquidity,
        cvd_price_profile=cvd_price_profile,
        derivatives_profile=derivatives_profile,
    )
    feature_audit = build_feature_audit(
        proposal=proposal,
        market_snapshot=market_snapshot,
        horizon_profile=horizon_profile,
        derivatives_horizon=derivatives_horizon,
        tf_momentum=tf_momentum,
        tf_volatility=tf_volatility,
        tf_volume=tf_volume,
        levels_for_horizon=levels_for_horizon,
        technical_rating=technical_rating,
        market_regime=market_regime,
        layered_scores=layered_scores,
        expected_value=expected_value,
        pattern_tags=pattern_tags,
        plan_liquidity=plan_liquidity,
        cvd_price_profile=cvd_price_profile,
        derivatives_profile=derivatives_profile,
        score_components={
            "trend_bias": trend_bias,
            "technical_direction_bias": technical_rating["direction_bias"],
            "price_vs_entry_bias": price_vs_entry_bias,
            "volume_bias": volume_bias,
            "order_book_bias": order_book_bias,
            "microstructure_bias": microstructure_bias,
            "momentum_bias": momentum_bias,
            "taker_flow_bias": taker_flow_bias,
            "cvd_bias": cvd_bias,
            "oi_trend_bias": oi_trend_bias,
            "breadth_bias": breadth_bias,
            "volatility_penalty": volatility_penalty,
            "leverage_penalty": leverage_penalty,
            "liquidity_penalty": liquidity_penalty,
            "overextension_penalty": overextension_penalty,
            "funding_penalty": funding_penalty,
            "funding_relative_penalty": funding_relative_penalty,
            "crowding_penalty": crowding_penalty,
            "level_penalty": level_penalty,
            "sentiment_penalty": sentiment_penalty,
            "higher_timeframe_penalty": htf_penalty,
            "oi_context_penalty": oi_context_penalty,
            "contradiction_penalty": contradiction_penalty,
        },
    )
    plain_summary = build_plain_summary(
        proposal=proposal,
        tp_probability=tp_probability,
        sl_probability=sl_probability,
        range_probability=range_probability,
        probability_ranges=probability_ranges,
        expected_value=expected_value,
        layered_scores=layered_scores,
        market_regime=market_regime,
        margin_risk_pct=margin_risk_pct,
        margin_reward_pct=margin_reward_pct,
        break_even_probability=break_even_probability,
        risk_level=risk_level,
        setup_grade=setup_grade,
        rr_ratio=rr_ratio,
        recent_range_pct=recent_range_pct,
        atr_pct=atr_pct,
        trend_bias=trend_bias,
        order_book_imbalance=order_book_imbalance,
        rsi_signal=rsi_signal,
        rsi_timeframe=momentum_tf_key,
        funding_rate_pct=funding_rate_pct,
        taker_buy_sell_ratio=taker_buy_sell_ratio,
        cvd_ratio=trade_flow.get("cvd_ratio"),
        fear_greed_value=sentiment.get("fear_greed_value"),
        suggested_leverage=suggested_leverage,
        decision=decision,
        horizon_profile=horizon_profile,
        technical_rating=technical_rating,
    )
    explained_metrics = build_explained_metrics(
        timeframes=market_snapshot["timeframes"],
        levels=levels,
        tf_5m=tf_5m,
        tf_1h=tf_1h,
        order_book=order_book,
        trade_flow=trade_flow,
        ticker_24h=ticker_24h,
        derivatives=derivatives,
        sentiment=sentiment,
        global_market=global_market,
        market_breadth=market_breadth,
        rr_ratio=rr_ratio,
        proposal=proposal,
        horizon_profile=horizon_profile,
        risk_distance=risk_distance,
        reward_distance=reward_distance,
        technical_rating=technical_rating,
        tf_momentum=tf_momentum,
        tf_volatility=tf_volatility,
    )
    explained_metrics = build_score_metrics(layered_scores, expected_value, market_regime, probability_ranges) + explained_metrics

    return {
        "analysis_type": "pre_trade",
        "engine_version": ENGINE_VERSION,
        "time_horizon": proposal.time_horizon,
        "tp_probability": round(tp_probability, 4),
        "sl_probability": round(sl_probability, 4),
        "range_probability": round(range_probability, 4),
        "risk_level": risk_level,
        "setup_grade": setup_grade,
        "confidence": confidence,
        "training_decision": decision,
        "probability_ranges": probability_ranges,
        "expected_value": expected_value,
        "layered_scores": layered_scores,
        "market_regime": market_regime,
        "technical_rating": technical_rating,
        "feature_audit": feature_audit,
        "pattern_tags": pattern_tags,
        "invalidation_rules": invalidation_rules,
        "plain_summary": plain_summary,
        "explained_metrics": explained_metrics,
        "parameter_advice": parameter_advice,
        "reasons": reasons[:5],
        "alerts": alerts,
        "snapshot": {
            **market_snapshot,
            "time_horizon": proposal.time_horizon,
            "time_horizon_profile": horizon_profile,
            "recent_range_pct": recent_range_pct,
            "atr_pct": atr_pct,
            "volume_ratio": volume_ratio,
            "analysis_timeframes": {
                "momentum": momentum_tf_key,
                "volatility": volatility_tf_key,
                "volume": volume_tf_key,
                "levels": levels_tf_key,
                "derivatives_period": derivatives_horizon["period"],
            },
            "risk_distance_pct": risk_distance,
            "reward_distance_pct": reward_distance,
            "risk_score": risk_score,
            "margin_risk_pct": margin_risk_pct,
            "margin_reward_pct": margin_reward_pct,
            "risk_reward_ratio": rr_ratio,
            "break_even_probability": break_even_probability,
            "probability_ranges": probability_ranges,
            "expected_value": expected_value,
            "layered_scores": layered_scores,
            "market_regime": market_regime,
            "technical_rating": technical_rating,
            "feature_audit": feature_audit,
            "pattern_tags": pattern_tags,
            "plan_liquidity": plan_liquidity,
            "cvd_price_profile": cvd_price_profile,
            "derivatives_profile": derivatives_profile,
            "invalidation_rules": invalidation_rules,
            "score_components": {
                "trend_bias": trend_bias,
                "technical_direction_bias": technical_rating["direction_bias"],
                "technical_entry_timing_penalty": technical_rating["entry_timing_penalty"],
                "technical_barrier_penalty": technical_rating["barrier_penalty"],
                "technical_alignment_score": technical_rating["score"],
                "rsi_timeframe": momentum_tf_key,
                "volatility_timeframe": volatility_tf_key,
                "levels_timeframe": levels_tf_key,
                "derivatives_period": derivatives_horizon["period"],
                "price_vs_entry_bias": price_vs_entry_bias,
                "rr_bias": 0,
                "volume_bias": volume_bias,
                "order_book_bias": order_book_bias,
                "microstructure_bias": microstructure_bias,
                "momentum_bias": momentum_bias,
                "taker_flow_bias": taker_flow_bias,
                "cvd_bias": cvd_bias,
                "oi_trend_bias": oi_trend_bias,
                "breadth_bias": breadth_bias,
                "volatility_penalty": volatility_penalty,
                "leverage_penalty": leverage_penalty,
                "liquidity_penalty": liquidity_penalty,
                "overextension_penalty": overextension_penalty,
                "funding_penalty": funding_penalty,
                "funding_relative_penalty": funding_relative_penalty,
                "crowding_penalty": crowding_penalty,
                "level_penalty": level_penalty,
                "sentiment_penalty": sentiment_penalty,
                "higher_timeframe_penalty": htf_penalty,
                "oi_context_penalty": oi_context_penalty,
                "contradiction_penalty": contradiction_penalty,
            },
        },
    }


def build_pattern_tags(
    proposal: TradeProposal,
    market_regime: dict,
    technical_rating: dict,
    risk_distance: float,
    reward_distance: float,
    atr_pct: float,
    recent_range_pct: float,
    order_book_imbalance: float,
    microprice_bias_pct: float | None,
    slope_imbalance: float | None,
    microstructure_bias: float,
    cvd_bias: float,
    taker_flow_bias: float,
    funding_penalty: float,
    funding_relative_penalty: float,
    level_penalty: float,
    htf_penalty: float,
    oi_context_penalty: float,
    contradiction_penalty: float,
    plan_liquidity: dict,
    cvd_price_profile: dict,
    derivatives_profile: dict,
) -> list[str]:
    tags: list[str] = []
    if market_regime.get("name"):
        tags.append(f"regime:{market_regime['name']}")
    if technical_rating.get("label"):
        tags.append(f"technical:{technical_rating['label']}")
    if cvd_bias > 0 and taker_flow_bias < 0:
        tags.append("spot_favorable_futures_against")
    if cvd_bias < 0 and taker_flow_bias > 0:
        tags.append("spot_against_futures_favorable")
    if cvd_bias > 0:
        tags.append("cvd_supports_plan")
    elif cvd_bias < 0:
        tags.append("cvd_against_plan")
    if taker_flow_bias > 0:
        tags.append("futures_taker_supports_plan")
    elif taker_flow_bias < 0:
        tags.append("futures_taker_against_plan")
    if htf_penalty:
        tags.append("higher_timeframe_against")
    if level_penalty:
        tags.append("technical_barrier_near")
    if oi_context_penalty:
        tags.append("open_interest_price_warning")
    if funding_penalty or funding_relative_penalty:
        tags.append("funding_saturation_warning")
    if contradiction_penalty:
        tags.append("mixed_signals_contradiction")
    if risk_distance < max(recent_range_pct, atr_pct) * 0.35:
        tags.append("stop_inside_recent_noise")
    if reward_distance > 0 and risk_distance > 0 and reward_distance / risk_distance >= 2:
        tags.append("asymmetric_reward_plan")
    if proposal.leverage >= 8:
        tags.append("high_leverage")
    elif proposal.leverage >= 5:
        tags.append("medium_leverage")
    if proposal.side == "long" and order_book_imbalance > 0.12:
        tags.append("order_book_supports_long")
    elif proposal.side == "short" and order_book_imbalance < -0.12:
        tags.append("order_book_supports_short")
    elif abs(order_book_imbalance) > 0.12:
        tags.append("order_book_against_plan")
    if microprice_bias_pct is not None:
        if microprice_bias_pct > 0.005:
            tags.append("microprice_bid_pressure")
        elif microprice_bias_pct < -0.005:
            tags.append("microprice_ask_pressure")
    if slope_imbalance is not None:
        if slope_imbalance > 0.12:
            tags.append("book_slope_bid_dense")
        elif slope_imbalance < -0.12:
            tags.append("book_slope_ask_dense")
    if microstructure_bias > 0:
        tags.append("microstructure_supports_plan")
    elif microstructure_bias < 0:
        tags.append("microstructure_against_plan")
    if plan_liquidity.get("target_path_notional", 0) > plan_liquidity.get("stop_path_notional", 0) * 1.8:
        tags.append("liquidity_heavier_toward_target")
    if plan_liquidity.get("stop_path_notional", 0) > plan_liquidity.get("target_path_notional", 0) * 1.8:
        tags.append("liquidity_heavier_toward_stop")
    cvd_pattern = cvd_price_profile.get("pattern")
    if cvd_pattern:
        tags.append(cvd_pattern)
    derivatives_pattern = derivatives_profile.get("pattern")
    if derivatives_pattern:
        tags.append(derivatives_pattern)
    for warning in derivatives_profile.get("warnings", []):
        tags.append(warning)
    return tags


def build_derivatives_profile(
    side: str,
    price_change_24h_pct: float,
    derivatives: dict,
    derivatives_horizon: dict,
    taker_flow_bias: float,
    oi_trend_bias: float,
    funding_penalty: float,
    funding_relative_penalty: float,
    crowding_penalty: float,
    oi_context_penalty: float,
) -> dict:
    desired_direction = 1 if side == "long" else -1
    price_direction = 1 if price_change_24h_pct > 0.5 else -1 if price_change_24h_pct < -0.5 else 0
    taker_direction = 1 if taker_flow_bias > 0 else -1 if taker_flow_bias < 0 else 0
    oi_direction = 1 if oi_trend_bias > 0 else -1 if oi_trend_bias < 0 else 0
    open_interest_change_pct = derivatives_horizon.get("open_interest_change_pct")
    oi_change_direction = (
        1 if open_interest_change_pct is not None and open_interest_change_pct > 0.2
        else -1 if open_interest_change_pct is not None and open_interest_change_pct < -0.2
        else 0
    )
    warnings = []
    if funding_penalty or funding_relative_penalty:
        warnings.append("derivatives_funding_saturation")
    if crowding_penalty:
        warnings.append("derivatives_crowding_risk")
    if oi_context_penalty:
        warnings.append("derivatives_oi_price_warning")

    pattern = None
    reason = "Derivados sin lectura compuesta fuerte."
    if taker_direction == 1 and oi_direction == 1:
        pattern = "futures_oi_confirmation"
        reason = "El flujo taker de futuros y el OI acompanan la direccion propuesta."
    elif taker_direction == -1 and oi_change_direction == 1:
        pattern = "futures_oi_contradiction"
        reason = "El flujo taker de futuros contradice la operacion con OI creciente; posible presion nueva contra el plan."
    elif taker_direction == 1 and oi_change_direction <= 0:
        pattern = "futures_flow_without_oi_confirmation"
        reason = "El flujo taker acompana, pero el OI no confirma nueva exposicion."
    elif taker_direction == -1:
        pattern = "futures_taker_against_without_oi_confirmation"
        reason = "El flujo taker de futuros va contra el plan, aunque el OI no confirma presion fuerte."
    elif oi_context_penalty:
        pattern = "oi_price_divergence_warning"
        reason = "Precio y OI sugieren posible movimiento por cierre de posiciones, no conviccion nueva."

    return {
        "schema_version": "derivatives-composite-v0.1",
        "pattern": pattern,
        "reason": reason,
        "warnings": warnings,
        "period": derivatives_horizon.get("period"),
        "desired_direction": desired_direction,
        "price_change_24h_pct": price_change_24h_pct,
        "price_direction": price_direction,
        "taker_buy_sell_ratio": derivatives_horizon.get("taker_buy_sell_ratio"),
        "taker_direction": taker_direction,
        "open_interest": derivatives.get("open_interest"),
        "open_interest_change_pct": open_interest_change_pct,
        "oi_change_direction": oi_change_direction,
        "oi_direction_from_score": oi_direction,
        "funding_rate_pct": derivatives.get("funding_rate_pct"),
        "funding_avg_recent_pct": derivatives.get("funding_avg_recent_pct"),
        "global_long_short_ratio": derivatives_horizon.get("global_long_short_ratio"),
    }


def build_cvd_price_profile(side: str, trade_flow: dict) -> dict:
    cvd_ratio = trade_flow.get("cvd_ratio")
    price_change_pct = trade_flow.get("price_change_pct")
    sample_trades = trade_flow.get("sample_trades", 0)
    if cvd_ratio is None or price_change_pct is None:
        return {
            "schema_version": "cvd-price-v0.1",
            "pattern": None,
            "reason": "Datos insuficientes para comparar CVD y reaccion del precio.",
            "sample_trades": sample_trades,
        }
    flow_direction = 1 if cvd_ratio > 0.12 else -1 if cvd_ratio < -0.12 else 0
    price_direction = 1 if price_change_pct > 0.03 else -1 if price_change_pct < -0.03 else 0
    desired_direction = 1 if side == "long" else -1
    pattern = None
    reason = "CVD y precio no ofrecen una lectura fuerte."
    if flow_direction == desired_direction and price_direction == desired_direction:
        pattern = "cvd_price_confirmation"
        reason = "El flujo agresivo spot y el precio acompanan la direccion propuesta."
    elif flow_direction == desired_direction and price_direction == 0:
        pattern = "cvd_price_absorption_warning"
        reason = "El flujo agresivo acompana, pero el precio no avanza; posible absorcion."
    elif flow_direction == desired_direction and price_direction == -desired_direction:
        pattern = "cvd_price_absorption_warning"
        reason = "El flujo agresivo acompana, pero el precio reacciona en contra; posible absorcion fuerte."
    elif flow_direction == -desired_direction:
        pattern = "cvd_price_against_plan"
        reason = "El flujo agresivo spot va contra la direccion propuesta."
    elif price_direction == desired_direction:
        pattern = "price_moves_without_cvd_confirmation"
        reason = "El precio acompana, pero el CVD no confirma con claridad."
    return {
        "schema_version": "cvd-price-v0.1",
        "pattern": pattern,
        "reason": reason,
        "sample_trades": sample_trades,
        "cvd_ratio": cvd_ratio,
        "price_change_pct": price_change_pct,
        "flow_direction": flow_direction,
        "price_direction": price_direction,
        "desired_direction": desired_direction,
        "first_price": trade_flow.get("first_price"),
        "last_price": trade_flow.get("last_price"),
        "first_trade_time": trade_flow.get("first_trade_time"),
        "last_trade_time": trade_flow.get("last_trade_time"),
    }


def build_plan_liquidity_profile(proposal: TradeProposal, order_book: dict) -> dict:
    bids = order_book.get("bids") if isinstance(order_book.get("bids"), list) else []
    asks = order_book.get("asks") if isinstance(order_book.get("asks"), list) else []
    if proposal.side == "long":
        stop_levels = levels_between(bids, proposal.stop_loss, proposal.entry)
        target_levels = levels_between(asks, proposal.entry, proposal.take_profit)
    else:
        stop_levels = levels_between(asks, proposal.entry, proposal.stop_loss)
        target_levels = levels_between(bids, proposal.take_profit, proposal.entry)
    stop_notional = sum(float(level.get("notional") or 0) for level in stop_levels)
    target_notional = sum(float(level.get("notional") or 0) for level in target_levels)
    total = stop_notional + target_notional
    return {
        "schema_version": "plan-liquidity-v0.1",
        "side": proposal.side,
        "stop_path_notional": stop_notional,
        "target_path_notional": target_notional,
        "stop_path_levels": len(stop_levels),
        "target_path_levels": len(target_levels),
        "target_vs_stop_liquidity_ratio": target_notional / max(stop_notional, 0.000001),
        "stop_vs_target_liquidity_ratio": stop_notional / max(target_notional, 0.000001),
        "dominant_path": "target" if target_notional > stop_notional else "stop" if stop_notional > target_notional else "balanced",
        "coverage_notional": total,
    }


def levels_between(levels: list[dict], low: float, high: float) -> list[dict]:
    lower = min(low, high)
    upper = max(low, high)
    return [
        level for level in levels
        if lower <= float(level.get("price") or 0) <= upper
    ]


def build_feature_audit(
    proposal: TradeProposal,
    market_snapshot: dict,
    horizon_profile: dict,
    derivatives_horizon: dict,
    tf_momentum: dict,
    tf_volatility: dict,
    tf_volume: dict,
    levels_for_horizon: dict,
    technical_rating: dict,
    market_regime: dict,
    layered_scores: dict,
    expected_value: dict,
    pattern_tags: list[str],
    plan_liquidity: dict,
    cvd_price_profile: dict,
    derivatives_profile: dict,
    score_components: dict,
) -> dict:
    availability = market_snapshot.get("availability", {})
    usable = [key for key, value in availability.items() if value]
    missing = [key for key, value in availability.items() if not value]
    total = len(availability) or 1
    data_quality = {
        "usable_features": usable,
        "missing_features": missing,
        "coverage_pct": round((len(usable) / total) * 100, 2),
        "source_map": market_snapshot.get("source", {}),
    }
    order_book = market_snapshot.get("order_book", {})
    trade_flow = market_snapshot.get("trade_flow", {})
    derivatives = market_snapshot.get("derivatives", {})
    ticker_24h = market_snapshot.get("ticker_24h", {})
    market_breadth = market_snapshot.get("market_breadth", {})
    sentiment = market_snapshot.get("sentiment", {})
    global_market = market_snapshot.get("global_market", {})
    return {
        "schema_version": "feature-capture-v0.1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "proposal": {
            "symbol": proposal.symbol,
            "side": proposal.side,
            "time_horizon": proposal.time_horizon,
            "entry": proposal.entry,
            "margin": proposal.margin,
            "leverage": proposal.leverage,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
        },
        "time_horizon_profile": {
            "label": horizon_profile.get("label"),
            "duration": horizon_profile.get("duration"),
            "max_minutes": horizon_profile.get("max_minutes"),
            "focus": horizon_profile.get("focus"),
            "primary_timeframes": horizon_profile.get("primary_timeframes"),
            "confirmation_timeframe": horizon_profile.get("confirmation_timeframe"),
            "momentum_timeframe": horizon_profile.get("momentum_timeframe"),
            "volatility_timeframe": horizon_profile.get("volatility_timeframe"),
            "levels_timeframe": horizon_profile.get("levels_timeframe"),
            "derivatives_period": derivatives_horizon.get("period"),
            "trend_weights": horizon_profile.get("trend_weights"),
            "micro_weight": horizon_profile.get("micro_weight"),
            "derivatives_weight": horizon_profile.get("derivatives_weight"),
            "macro_weight": horizon_profile.get("macro_weight"),
            "funding_weight": horizon_profile.get("funding_weight"),
        },
        "data_quality": data_quality,
        "selected_market_state": {
            "current_price": market_snapshot.get("current_price"),
            "ticker_24h": {
                "price_change_pct": ticker_24h.get("price_change_pct"),
                "quote_volume": ticker_24h.get("quote_volume"),
                "high": ticker_24h.get("high"),
                "low": ticker_24h.get("low"),
            },
            "momentum": {
                "interval": tf_momentum.get("interval"),
                "rsi_14": tf_momentum.get("rsi_14"),
                "price_vs_ema_21_pct": tf_momentum.get("price_vs_ema_21_pct"),
                "ema_stack": tf_momentum.get("ema_stack"),
            },
            "volatility": {
                "interval": tf_volatility.get("interval"),
                "atr_pct": tf_volatility.get("atr_pct"),
                "recent_range_pct": tf_volatility.get("recent_range_pct"),
                "position_in_recent_range": tf_volatility.get("position_in_recent_range"),
            },
            "volume": {
                "interval": tf_volume.get("interval"),
                "volume_ratio": tf_volume.get("volume_ratio"),
                "taker_buy_ratio": tf_volume.get("taker_buy_ratio"),
            },
            "levels": {
                "nearest_support": levels_for_horizon.get("nearest_support"),
                "nearest_resistance": levels_for_horizon.get("nearest_resistance"),
                "distance_to_support_pct": levels_for_horizon.get("distance_to_support_pct"),
                "distance_to_resistance_pct": levels_for_horizon.get("distance_to_resistance_pct"),
            },
            "order_book": {
                "imbalance": order_book.get("imbalance"),
                "microprice": order_book.get("microprice"),
                "microprice_bias_pct": order_book.get("microprice_bias_pct"),
                "book_slope": order_book.get("book_slope"),
                "spread_pct": order_book.get("spread_pct"),
                "bid_notional_top20": order_book.get("bid_notional_top20"),
                "ask_notional_top20": order_book.get("ask_notional_top20"),
                "levels_count": order_book.get("levels_count"),
                "depth_bands": order_book.get("depth_bands"),
                "plan_liquidity": plan_liquidity,
            },
            "spot_flow": {
                "sample_trades": trade_flow.get("sample_trades"),
                "first_trade_time": trade_flow.get("first_trade_time"),
                "last_trade_time": trade_flow.get("last_trade_time"),
                "first_price": trade_flow.get("first_price"),
                "last_price": trade_flow.get("last_price"),
                "price_change_pct": trade_flow.get("price_change_pct"),
                "buy_ratio": trade_flow.get("buy_ratio"),
                "sell_ratio": trade_flow.get("sell_ratio"),
                "cvd_notional": trade_flow.get("cvd_notional"),
                "cvd_ratio": trade_flow.get("cvd_ratio"),
                "cvd_price_profile": cvd_price_profile,
            },
            "derivatives": {
                "period": derivatives_horizon.get("period"),
                "funding_rate_pct": derivatives.get("funding_rate_pct"),
                "funding_avg_recent_pct": derivatives.get("funding_avg_recent_pct"),
                "open_interest": derivatives.get("open_interest"),
                "open_interest_change_pct": derivatives_horizon.get("open_interest_change_pct"),
                "global_long_short_ratio": derivatives_horizon.get("global_long_short_ratio"),
                "taker_buy_sell_ratio": derivatives_horizon.get("taker_buy_sell_ratio"),
                "taker_buy_volume": derivatives_horizon.get("taker_buy_volume"),
                "taker_sell_volume": derivatives_horizon.get("taker_sell_volume"),
                "derivatives_profile": derivatives_profile,
            },
            "context": {
                "fear_greed_value": sentiment.get("fear_greed_value"),
                "fear_greed_classification": sentiment.get("fear_greed_classification"),
                "btc_dominance_pct": global_market.get("btc_dominance_pct"),
                "advancers_24h_pct": market_breadth.get("advancers_24h_pct"),
                "median_change_24h_pct": market_breadth.get("median_change_24h_pct"),
            },
        },
        "analysis_outputs": {
            "market_regime": market_regime.get("name"),
            "technical_label": technical_rating.get("label"),
            "technical_score": technical_rating.get("score"),
            "layered_scores": layered_scores,
            "expected_value": expected_value,
            "pattern_tags": pattern_tags,
        },
        "score_components": score_components,
    }


def funding_relative_context_penalty(side: str, funding_rate_pct: float | None, funding_avg_recent_pct: float | None) -> float:
    if funding_rate_pct is None or funding_avg_recent_pct is None:
        return 0
    if abs(funding_avg_recent_pct) < 0.000001:
        return 0
    relative_multiple = abs(funding_rate_pct) / max(abs(funding_avg_recent_pct), 0.000001)
    if side == "long" and funding_rate_pct > 0 and relative_multiple >= 1.8:
        return 0.01
    if side == "short" and funding_rate_pct < 0 and relative_multiple >= 1.8:
        return 0.01
    return 0


def higher_timeframe_contra_penalty(side: str, timeframes: dict, time_horizon: str) -> float:
    profile = time_horizon_profile(time_horizon)
    confirmation = profile["confirmation_timeframe"]
    tf_key = confirmation if confirmation in timeframes else "4h"
    stack = timeframes.get(tf_key, {}).get("ema_stack")
    base = 0.018 * profile["htf_penalty_weight"]
    if side == "long" and stack == "bearish":
        return base
    if side == "short" and stack == "bullish":
        return base
    return 0


def oi_price_context_penalty(side: str, price_change_24h_pct: float, open_interest_change_pct: float | None) -> float:
    if open_interest_change_pct is None:
        return 0
    if side == "long" and price_change_24h_pct > 0.5 and open_interest_change_pct < -0.2:
        return 0.012
    if side == "short" and price_change_24h_pct < -0.5 and open_interest_change_pct < -0.2:
        return 0.012
    return 0


def combined_contradiction_penalty(
    side: str,
    cvd_bias: float,
    taker_flow_bias: float,
    oi_context_penalty: float,
    level_penalty: float,
    htf_penalty: float,
) -> float:
    contradictions = 0
    if cvd_bias > 0 and taker_flow_bias < 0:
        contradictions += 1
    if cvd_bias < 0 and taker_flow_bias > 0:
        contradictions += 1
    if oi_context_penalty:
        contradictions += 1
    if level_penalty:
        contradictions += 1
    if htf_penalty:
        contradictions += 1
    if contradictions >= 4:
        return 0.045
    if contradictions == 3:
        return 0.032
    if contradictions == 2:
        return 0.018
    return 0


def classify_market_regime(timeframes: dict, recent_range_pct: float, atr_pct: float, side: str) -> dict:
    stacks = {key: value.get("ema_stack") for key, value in timeframes.items()}
    bullish = sum(1 for value in stacks.values() if value == "bullish")
    bearish = sum(1 for value in stacks.values() if value == "bearish")
    if recent_range_pct < 0.45 and atr_pct < 0.08:
        name = "compresion"
        description = "Rango corto estrecho con volatilidad reducida; puede preceder a ruptura o falso movimiento."
    elif bullish >= 3:
        name = "tendencia_alcista"
        description = "Varias temporalidades mantienen estructura alcista."
    elif bearish >= 3:
        name = "tendencia_bajista"
        description = "Varias temporalidades mantienen estructura bajista."
    elif timeframes.get("4h", {}).get("ema_stack") == ("bearish" if side == "long" else "bullish"):
        name = "rebote_contra_tendencia"
        description = "La idea opera un rebote de corto plazo contra una estructura 4h contraria."
    else:
        name = "mixto"
        description = "Las temporalidades no ofrecen una estructura dominante."
    return {
        "name": name,
        "description": description,
        "timeframe_stacks": stacks,
    }


def range_probability_for_context(recent_range_pct: float, contradiction_penalty: float, market_regime: dict) -> float:
    if market_regime["name"] in {"compresion", "mixto"}:
        return 0.12
    if contradiction_penalty >= 0.03:
        return 0.1
    return 0.08 if recent_range_pct < 1.2 else 0.06


def build_probability_ranges(tp_probability: float, sl_probability: float, range_probability: float, contradiction_penalty: float) -> dict:
    width = 0.04 if contradiction_penalty == 0 else 0.06 if contradiction_penalty < 0.03 else 0.08
    return {
        "tp": probability_range(tp_probability, width),
        "sl": probability_range(sl_probability, width),
        "range": probability_range(range_probability, min(width, 0.05)),
    }


def probability_range(value: float, width: float) -> dict:
    low = max(0.01, value - width / 2)
    high = min(0.99, value + width / 2)
    return {
        "low": round(low, 4),
        "high": round(high, 4),
        "label": f"{low:.0%}-{high:.0%}",
    }


def calculate_expected_value(
    proposal: TradeProposal,
    tp_probability: float,
    sl_probability: float,
    range_probability: float,
    reward_distance: float,
    risk_distance: float,
    spread_pct: float,
    funding_rate_pct: float | None,
    time_horizon: str | None = None,
) -> dict:
    notional = proposal.margin * proposal.leverage
    gross_win = notional * (reward_distance / 100)
    gross_loss = notional * (risk_distance / 100)
    cost_model = estimate_trade_costs(
        notional=notional,
        spread_pct=spread_pct,
        funding_rate_pct=funding_rate_pct,
        time_horizon=time_horizon or proposal.time_horizon,
    )
    estimated_cost = cost_model["total_cost_usdt"]
    net_win = gross_win - estimated_cost
    net_loss = gross_loss + estimated_cost
    expected_value_usdt = tp_probability * net_win - sl_probability * net_loss - range_probability * estimated_cost
    return {
        "schema_version": "ev-net-costs-v0.2",
        "notional": round(notional, 4),
        "gross_win_usdt": round(gross_win, 4),
        "gross_loss_usdt": round(gross_loss, 4),
        "estimated_cost_usdt": round(estimated_cost, 4),
        "cost_model": cost_model,
        "net_win_usdt": round(net_win, 4),
        "net_loss_usdt": round(net_loss, 4),
        "expected_value_usdt": round(expected_value_usdt, 4),
        "expected_value_pct_margin": round((expected_value_usdt / proposal.margin) * 100, 4) if proposal.margin else 0,
        "label": "positiva" if expected_value_usdt > 0 else "negativa" if expected_value_usdt < 0 else "neutral",
    }


def estimate_trade_costs(
    notional: float,
    spread_pct: float,
    funding_rate_pct: float | None,
    time_horizon: str | None,
) -> dict:
    profile = time_horizon_profile(time_horizon or "intraday_short")
    expected_minutes = expected_holding_minutes(time_horizon or "intraday_short", int(profile.get("max_minutes") or 240))
    fee_rate_entry = 0.0004
    fee_rate_exit = 0.0004
    spread_cross_rate = max(spread_pct / 100, 0)
    slippage_rate = estimate_slippage_rate(spread_pct=spread_pct, time_horizon=time_horizon or "intraday_short")
    funding_periods = expected_minutes / 480
    funding_rate = abs(funding_rate_pct or 0) / 100
    fee_cost = notional * (fee_rate_entry + fee_rate_exit)
    spread_cost = notional * spread_cross_rate
    slippage_cost = notional * slippage_rate
    funding_cost = notional * funding_rate * funding_periods
    total = fee_cost + spread_cost + slippage_cost + funding_cost
    return {
        "schema_version": "trade-costs-v0.2",
        "time_horizon": time_horizon or "intraday_short",
        "expected_minutes": round(expected_minutes, 2),
        "funding_periods_8h": round(funding_periods, 4),
        "fee_rate_round_trip": round(fee_rate_entry + fee_rate_exit, 6),
        "spread_pct": round(spread_pct, 6),
        "spread_cross_rate": round(spread_cross_rate, 6),
        "slippage_rate_round_trip": round(slippage_rate, 6),
        "funding_rate_pct": funding_rate_pct,
        "fee_cost_usdt": round(fee_cost, 4),
        "spread_cost_usdt": round(spread_cost, 4),
        "slippage_cost_usdt": round(slippage_cost, 4),
        "funding_cost_usdt": round(funding_cost, 4),
        "total_cost_usdt": round(total, 4),
    }


def expected_holding_minutes(time_horizon: str, max_minutes: int) -> float:
    if time_horizon == "intraday_short":
        return min(max_minutes, 120)
    if time_horizon == "intraday_wide":
        return min(max_minutes, 720)
    if time_horizon == "short_swing":
        return min(max_minutes, 4320)
    return max_minutes * 0.5


def estimate_slippage_rate(spread_pct: float, time_horizon: str) -> float:
    base = max(spread_pct / 100, 0.00015)
    if time_horizon == "intraday_short":
        multiplier = 1.15
    elif time_horizon == "intraday_wide":
        multiplier = 0.9
    else:
        multiplier = 0.75
    return min(0.004, max(0.00015, base * multiplier))


def build_layered_scores(
    tp_probability: float,
    rr_ratio: float,
    margin_risk_pct: float,
    volatility_penalty: float,
    level_penalty: float,
    liquidity_penalty: float,
    spread_pct: float,
    contradiction_penalty: float,
    htf_penalty: float,
    taker_flow_bias: float,
    cvd_bias: float,
    technical_rating: dict,
    expected_value: dict,
) -> dict:
    direction_score = round(tp_probability * 100)
    quality_score = round(
        min(100, max(0, 50 + score_to_percent(rr_ratio, 0.8, 3.2) * 0.35 - min(25, margin_risk_pct * 1.2)))
    )
    execution_risk_score = round(
        min(100, max(0, 30 + volatility_penalty * 220 + level_penalty * 300 + liquidity_penalty * 250 + score_to_percent(spread_pct, 0, 0.08) * 0.35))
    )
    alignment = 70
    if contradiction_penalty:
        alignment -= round(contradiction_penalty * 700)
    if htf_penalty:
        alignment -= 12
    if taker_flow_bias * cvd_bias < 0:
        alignment -= 12
    alignment += round(technical_rating.get("confidence_adjustment", 0))
    confidence_score = min(95, max(15, alignment))
    ev_score = score_to_percent(expected_value["expected_value_pct_margin"], -8, 12)
    return {
        "direction_score": direction_score,
        "operation_quality_score": quality_score,
        "execution_risk_score": execution_risk_score,
        "confidence_score": confidence_score,
        "expected_value_score": ev_score,
    }


def grade_from_scores(tp_probability: float, risk_score: float, expected_value_score: int) -> str:
    if tp_probability >= 0.62 and risk_score < 0.2 and expected_value_score >= 58:
        return "A"
    if tp_probability >= 0.52 and risk_score < 0.36 and expected_value_score >= 50:
        return "B"
    if tp_probability >= 0.44 and expected_value_score >= 42:
        return "C"
    return "D"


def confidence_from_score(score: int) -> str:
    if score >= 76:
        return "alta"
    if score >= 61:
        return "media"
    if score >= 46:
        return "media-baja"
    return "baja"


def decision_from_context(setup_grade: str, risk_level: str, confidence: str, expected_value: dict) -> str:
    if expected_value["expected_value_usdt"] < 0:
        return "observar"
    minimum_ev = expected_value.get("minimum_required_pct_margin")
    if minimum_ev is None:
        minimum_ev = minimum_ev_pct_margin(risk_level, confidence)
    if expected_value["expected_value_pct_margin"] < minimum_ev:
        return "observar"
    if setup_grade in {"A", "B"} and risk_level != "alto" and confidence in {"alta", "media"}:
        return "simular"
    if setup_grade in {"B", "C"} and risk_level != "alto":
        return "simular con tamano prudente"
    return "observar"


def annotate_expected_value_threshold(expected_value: dict, risk_level: str, confidence: str) -> dict:
    annotated = dict(expected_value)
    minimum = minimum_ev_pct_margin(risk_level, confidence)
    ev_pct = float(annotated.get("expected_value_pct_margin") or 0)
    annotated["minimum_required_pct_margin"] = minimum
    annotated["passes_minimum_threshold"] = ev_pct >= minimum
    annotated["threshold_reason"] = (
        "EV suficiente para el riesgo/confianza del setup."
        if ev_pct >= minimum
        else "EV insuficiente para compensar riesgo, costes e incertidumbre."
    )
    return annotated


def minimum_ev_pct_margin(risk_level: str | None, confidence: str | None) -> float:
    if risk_level == "alto":
        base = 3.0
    elif risk_level == "medio-alto":
        base = 2.0
    elif risk_level == "medio":
        base = 1.0
    else:
        base = 0.5
    if confidence in {"baja", "media-baja"}:
        base += 0.5
    elif confidence == "alta":
        base -= 0.25
    return round(max(0.25, base), 2)


def build_invalidation_rules(proposal: TradeProposal, market_regime: dict, levels_1h: dict, taker_flow_bias: float, cvd_bias: float) -> list[str]:
    direction = "long" if proposal.side == "long" else "short"
    rules = []
    rules.append("Invalidar si el precio pierde la zona de entrada con vela fuerte y volumen creciente." if direction == "long" else "Invalidar si el precio recupera la zona de entrada con vela fuerte y volumen creciente.")
    if direction == "long":
        rules.append("Vigilar perdida de soporte intradia o rechazo claro antes del objetivo.")
    else:
        rules.append("Vigilar recuperacion de resistencia intradia o rechazo bajista fallido.")
    if taker_flow_bias < 0:
        rules.append("Invalidar o reducir si el flujo taker de futuros sigue agresivamente contra la operacion.")
    if cvd_bias < 0:
        rules.append("Invalidar si el CVD spot se mantiene contra la direccion propuesta.")
    if market_regime["name"] == "rebote_contra_tendencia":
        rules.append("Al ser rebote contra estructura 4h, exigir avance rapido; si se estanca, baja la calidad del setup.")
    return rules[:5]


def build_score_metrics(layered_scores: dict, expected_value: dict, market_regime: dict, probability_ranges: dict) -> list[dict]:
    return [
        {
            "key": "direction_score",
            "label": "Direccion probable",
            "value": f"{probability_ranges['tp']['label']} TP",
            "score": layered_scores["direction_score"],
            "bias": "favorable" if layered_scores["direction_score"] >= 55 else "desfavorable" if layered_scores["direction_score"] <= 45 else "neutral",
            "source": "Motor v0.5 por capas",
            "explanation": "Estima direccion sin premiar el ratio riesgo/beneficio. El R/R se usa en esperanza matematica, no para inflar probabilidad.",
        },
        {
            "key": "expected_value",
            "label": "Esperanza matematica",
            "value": f"{expected_value['label']} · {expected_value['expected_value_usdt']:+.2f} USDT · umbral {expected_value.get('minimum_required_pct_margin', 0):.2f}%",
            "score": layered_scores["expected_value_score"],
            "bias": "favorable" if expected_value.get("passes_minimum_threshold") else "desfavorable",
            "source": "Probabilidad, R/R, comisiones, spread, slippage y funding estimados",
            "explanation": "Calcula si la operacion compensa economicamente despues de costes aproximados y exige una EV minima segun riesgo y confianza.",
        },
        {
            "key": "market_regime",
            "label": "Regimen de mercado",
            "value": market_regime["name"].replace("_", " "),
            "score": layered_scores["confidence_score"],
            "bias": "contexto",
            "source": "EMAs multi-temporalidad, rango y ATR",
            "explanation": market_regime["description"],
        },
    ]


def funding_context_penalty(side: str, funding_rate_pct: float | None) -> float:
    if funding_rate_pct is None:
        return 0
    if side == "long" and funding_rate_pct > 0.03:
        return 0.025
    if side == "short" and funding_rate_pct < -0.03:
        return 0.025
    return 0


def taker_flow_score(side: str, taker_buy_sell_ratio: float | None) -> float:
    if not taker_buy_sell_ratio:
        return 0
    if side == "long":
        return 0.02 if taker_buy_sell_ratio > 1.12 else -0.02 if taker_buy_sell_ratio < 0.88 else 0
    return 0.02 if taker_buy_sell_ratio < 0.88 else -0.02 if taker_buy_sell_ratio > 1.12 else 0


def crowding_penalty_score(side: str, global_long_short_ratio: float | None) -> float:
    if not global_long_short_ratio:
        return 0
    if side == "long" and global_long_short_ratio > 2.0:
        return 0.015
    if side == "short" and global_long_short_ratio < 0.5:
        return 0.015
    return 0


def cvd_flow_score(side: str, cvd_ratio: float | None) -> float:
    if cvd_ratio is None:
        return 0
    if side == "long":
        return 0.025 if cvd_ratio > 0.12 else -0.025 if cvd_ratio < -0.12 else 0
    return 0.025 if cvd_ratio < -0.12 else -0.025 if cvd_ratio > 0.12 else 0


def microstructure_score(side: str, microprice_bias_pct: float | None, slope_imbalance: float | None) -> float:
    microprice_bias = float(microprice_bias_pct or 0)
    slope_bias = float(slope_imbalance or 0)
    raw = 0.0
    if microprice_bias > 0.005:
        raw += 0.01
    elif microprice_bias < -0.005:
        raw -= 0.01
    if slope_bias > 0.12:
        raw += 0.01
    elif slope_bias < -0.12:
        raw -= 0.01
    if side == "short":
        raw *= -1
    return max(-0.018, min(0.018, raw))


def level_risk_penalty(proposal: TradeProposal, levels_for_horizon: dict) -> float:
    if proposal.side == "long":
        distance_to_resistance = levels_for_horizon.get("distance_to_resistance_pct")
        reward_distance = pct_from_entry(proposal.take_profit, proposal.entry)
        if distance_to_resistance is not None and distance_to_resistance < max(0.25, reward_distance * 0.35):
            return 0.025
    else:
        distance_to_support = levels_for_horizon.get("distance_to_support_pct")
        reward_distance = pct_from_entry(proposal.take_profit, proposal.entry)
        if distance_to_support is not None and distance_to_support < max(0.25, reward_distance * 0.35):
            return 0.025
    return 0


def sentiment_extreme_penalty(side: str, fear_greed_value: int | None) -> float:
    if fear_greed_value is None:
        return 0
    if side == "long" and fear_greed_value >= 75:
        return 0.015
    if side == "short" and fear_greed_value <= 25:
        return 0.015
    return 0


def open_interest_trend_score(side: str, price_change_24h_pct: float, open_interest_change_pct: float | None) -> float:
    if open_interest_change_pct is None:
        return 0
    price_direction = 1 if price_change_24h_pct > 0 else -1 if price_change_24h_pct < 0 else 0
    if open_interest_change_pct < 0.2 or price_direction == 0:
        return 0
    directional_pressure = price_direction if side == "long" else -price_direction
    return 0.02 if directional_pressure > 0 else -0.02


def market_breadth_score(side: str, advancers_24h_pct: float | None, median_change_24h_pct: float | None) -> float:
    if advancers_24h_pct is None or median_change_24h_pct is None:
        return 0
    bullish_breadth = advancers_24h_pct >= 58 and median_change_24h_pct > 0
    bearish_breadth = advancers_24h_pct <= 42 and median_change_24h_pct < 0
    if side == "long":
        return 0.02 if bullish_breadth else -0.02 if bearish_breadth else 0
    return 0.02 if bearish_breadth else -0.02 if bullish_breadth else 0


def trend_score(side: str, timeframes: dict, time_horizon: str) -> float:
    def one_timeframe_score(tf: dict) -> int:
        if tf["ema_stack"] == "bullish":
            return 1
        if tf["ema_stack"] == "bearish":
            return -1
        return 0

    weights = time_horizon_profile(time_horizon)["trend_weights"]
    raw_score = sum(one_timeframe_score(timeframes[interval]) * weight for interval, weight in weights.items() if interval in timeframes)
    if side == "short":
        raw_score *= -1
    max_abs = sum(weight for interval, weight in weights.items() if interval in timeframes) or 1
    normalized = raw_score / max_abs
    if normalized >= 0.55:
        return 0.1
    if normalized >= 0.2:
        return 0.05
    if normalized <= -0.55:
        return -0.09
    if normalized <= -0.2:
        return -0.05
    return 0


def build_technical_rating(
    proposal: TradeProposal,
    timeframes: dict,
    levels: dict,
    horizon_profile: dict,
    reward_distance: float,
    atr_pct: float,
) -> dict:
    weights = horizon_profile["trend_weights"]
    raw = 0.0
    max_abs = 0.0
    components = {}
    for interval, weight in weights.items():
        tf = timeframes.get(interval)
        if not tf:
            continue
        score = technical_timeframe_score(tf, proposal.side)
        components[interval] = round(score, 3)
        raw += score * weight
        max_abs += weight
    normalized = raw / max_abs if max_abs else 0.0
    direction_bias = 0.0
    if normalized >= 0.45:
        direction_bias = 0.035
    elif normalized >= 0.15:
        direction_bias = 0.015
    elif normalized <= -0.45:
        direction_bias = -0.04
    elif normalized <= -0.15:
        direction_bias = -0.02

    primary_tf = timeframes.get(horizon_profile["primary_timeframes"][0], {})
    rsi_value = primary_tf.get("rsi_14", 50)
    price_vs_ema = primary_tf.get("price_vs_ema_21_pct", 0)
    stretch_threshold = max(0.45, atr_pct * 1.7)
    entry_timing_penalty = 0.0
    if proposal.side == "long" and rsi_value >= 72 and price_vs_ema > stretch_threshold:
        entry_timing_penalty = 0.02
    if proposal.side == "short" and rsi_value <= 28 and price_vs_ema < -stretch_threshold:
        entry_timing_penalty = 0.02

    level_key = horizon_profile.get("levels_timeframe", "1h")
    level_data = levels.get(level_key, levels.get("1h", {}))
    barrier_distance = (
        level_data.get("distance_to_resistance_pct")
        if proposal.side == "long"
        else level_data.get("distance_to_support_pct")
    )
    barrier_penalty = 0.0
    if barrier_distance is not None and reward_distance > 0:
        if barrier_distance < reward_distance * 0.55:
            barrier_penalty = 0.025
        elif barrier_distance < reward_distance * 0.85:
            barrier_penalty = 0.012

    score = round(min(100, max(0, 50 + normalized * 50)))
    confidence_adjustment = 6 if normalized >= 0.45 else 3 if normalized >= 0.15 else -8 if normalized <= -0.45 else -4 if normalized <= -0.15 else 0
    confidence_adjustment -= 4 if entry_timing_penalty else 0
    confidence_adjustment -= 4 if barrier_penalty else 0
    return {
        "score": score,
        "normalized": round(normalized, 4),
        "components": components,
        "direction_bias": direction_bias,
        "entry_timing_penalty": entry_timing_penalty,
        "barrier_penalty": barrier_penalty,
        "barrier_distance_pct": barrier_distance,
        "primary_rsi": rsi_value,
        "primary_price_vs_ema_21_pct": price_vs_ema,
        "confidence_adjustment": confidence_adjustment,
        "label": "favorable" if score >= 60 else "desfavorable" if score <= 40 else "neutral",
    }


def technical_timeframe_score(tf: dict, side: str) -> float:
    score = 0.0
    ema_stack = tf.get("ema_stack")
    if ema_stack == "bullish":
        score += 0.55
    elif ema_stack == "bearish":
        score -= 0.55

    price_vs_ema = tf.get("price_vs_ema_21_pct", 0)
    if price_vs_ema > 0.08:
        score += 0.25
    elif price_vs_ema < -0.08:
        score -= 0.25

    rsi_value = tf.get("rsi_14", 50)
    if 45 <= rsi_value <= 65:
        score += 0.2
    elif rsi_value > 75:
        score -= 0.25
    elif rsi_value < 25:
        score += 0.1
    elif 35 <= rsi_value < 45:
        score += 0.05

    if side == "short":
        score *= -1
    return max(-1.0, min(1.0, score))


def build_plain_summary(
    proposal: TradeProposal,
    tp_probability: float,
    sl_probability: float,
    range_probability: float,
    probability_ranges: dict,
    expected_value: dict,
    layered_scores: dict,
    market_regime: dict,
    margin_risk_pct: float,
    margin_reward_pct: float,
    break_even_probability: float,
    risk_level: str,
    setup_grade: str,
    rr_ratio: float,
    recent_range_pct: float,
    atr_pct: float,
    trend_bias: float,
    order_book_imbalance: float,
    rsi_signal: float,
    rsi_timeframe: str,
    funding_rate_pct: float | None,
    taker_buy_sell_ratio: float | None,
    cvd_ratio: float | None,
    fear_greed_value: int | None,
    suggested_leverage: float,
    decision: str,
    horizon_profile: dict,
    technical_rating: dict,
) -> str:
    direction = "alcista" if proposal.side == "long" else "bajista"
    trend_text = (
        "la tendencia corta acompana la idea"
        if trend_bias > 0
        else "la tendencia corta va contra la idea"
        if trend_bias < 0
        else "la tendencia corta no da una ventaja clara"
    )
    leverage_text = (
        f"El apalancamiento x{proposal.leverage:g} es agresivo para este contexto; el motor lo bajaria a x{suggested_leverage:g}."
        if suggested_leverage < proposal.leverage
        else f"El apalancamiento x{proposal.leverage:g} no activa una reduccion automatica en esta lectura."
    )
    technical_text = (
        f"La capa tecnica queda {technical_rating['label']} ({technical_rating['score']}/100): "
        f"aporta {technical_rating['direction_bias']:+.1%} a la direccion, "
        f"penaliza timing {technical_rating['entry_timing_penalty']:.1%} y barreras {technical_rating['barrier_penalty']:.1%}."
    )
    return (
        f"Lectura {direction} para {horizon_profile['label']} ({horizon_profile['duration']}): setup {setup_grade} con riesgo {risk_level}. "
        f"El motor v0.5 estima TP en rango {probability_ranges['tp']['label']}, SL {probability_ranges['sl']['label']} y rango/sin resolver {probability_ranges['range']['label']}; "
        f"los decimales internos se guardan solo para entrenamiento. "
        f"La probabilidad direccional se separa de la esperanza matematica, que ahora sale {expected_value['label']} ({expected_value['expected_value_usdt']:+.2f} USDT estimados). "
        f"La clave es que {trend_text}, mientras la relacion beneficio/riesgo es {rr_ratio:.2f} y el break-even aproximado es {break_even_probability:.0%}. "
        f"Sobre el margen, el riesgo al SL equivale a {margin_risk_pct:.2f}% y la recompensa al TP a {margin_reward_pct:.2f}%. "
        f"Scores: direccion {layered_scores['direction_score']}/100, calidad {layered_scores['operation_quality_score']}/100, riesgo ejecucion {layered_scores['execution_risk_score']}/100, confianza {layered_scores['confidence_score']}/100. "
        f"Regimen detectado: {market_regime['name'].replace('_', ' ')}. "
        f"Temporalidades clave: {', '.join(horizon_profile['primary_timeframes'])}; confirmacion {horizon_profile['confirmation_timeframe']}. "
        f"{technical_text} "
        f"La volatilidad del marco elegido ronda {recent_range_pct:.2f}% y el ATR equivale a {atr_pct:.2f}%. "
        f"El RSI {rsi_timeframe} esta en {rsi_signal:.1f} y el imbalance del order book es {order_book_imbalance:+.2f}. "
        f"En derivados, funding {format_optional_pct(funding_rate_pct)} y taker buy/sell {format_optional_number(taker_buy_sell_ratio)}; "
        f"en spot, CVD reciente {format_optional_number(cvd_ratio)}. "
        f"Sentimiento Fear & Greed: {format_optional_number(fear_greed_value)}. "
        f"{leverage_text} Decision de entrenamiento: {decision}."
    )


def format_optional_pct(value: float | None) -> str:
    return "no disponible" if value is None else f"{value:+.4f}%"


def format_optional_number(value: float | None) -> str:
    return "no disponible" if value is None else f"{value:.2f}"


def score_to_percent(value: float, low: float, high: float) -> int:
    if high == low:
        return 50
    normalized = (value - low) / (high - low)
    return round(min(1, max(0, normalized)) * 100)


def build_explained_metrics(
    timeframes: dict,
    levels: dict,
    tf_5m: dict,
    tf_1h: dict,
    order_book: dict,
    trade_flow: dict,
    ticker_24h: dict,
    derivatives: dict,
    sentiment: dict,
    global_market: dict,
    market_breadth: dict,
    rr_ratio: float,
    proposal: TradeProposal,
    horizon_profile: dict,
    risk_distance: float,
    reward_distance: float,
    technical_rating: dict | None = None,
    tf_momentum: dict | None = None,
    tf_volatility: dict | None = None,
) -> list[dict]:
    tf_momentum = tf_momentum or tf_5m
    tf_volatility = tf_volatility or tf_5m
    levels_for_horizon = levels.get(horizon_profile.get("levels_timeframe", "1h"), levels.get("1h", {}))
    derivatives_horizon = derivatives_for_horizon(derivatives, horizon_profile)
    technical_rating = technical_rating or build_technical_rating(
        proposal=proposal,
        timeframes=timeframes,
        levels=levels,
        horizon_profile=horizon_profile,
        reward_distance=reward_distance,
        atr_pct=tf_volatility.get("atr_pct", 0),
    )
    trend_score_value = multi_tf_display_score(timeframes, proposal.side)
    if proposal.side == "short":
        trend_score_value = 100 - trend_score_value

    rsi_value = tf_momentum["rsi_14"]
    momentum_score = 100 - abs(50 - rsi_value) * 2
    liquidity_score = 100 - score_to_percent(order_book["spread_pct"], 0, 0.08)
    imbalance_score = score_to_percent(order_book["imbalance"], -0.5, 0.5)
    rr_score = score_to_percent(rr_ratio, 0.5, 3.0)
    volatility_score = 100 - score_to_percent(tf_volatility["atr_pct"], 0.02, 0.6)
    leverage_score = 100 - score_to_percent(proposal.leverage, 1, 10)
    funding_rate_pct = derivatives.get("funding_rate_pct")
    taker_buy_sell_ratio = derivatives_horizon.get("taker_buy_sell_ratio")
    long_short_ratio = derivatives_horizon.get("global_long_short_ratio")
    cvd_ratio = trade_flow.get("cvd_ratio")
    fear_greed_value = sentiment.get("fear_greed_value")
    btc_dominance = global_market.get("btc_dominance_pct")
    advancers_24h = market_breadth.get("advancers_24h_pct")
    median_24h = market_breadth.get("median_change_24h_pct")
    oi_change = derivatives_horizon.get("open_interest_change_pct")
    funding_avg = derivatives.get("funding_avg_recent_pct")
    levels_1h = levels_for_horizon
    funding_score = 100 - score_to_percent(abs(funding_rate_pct or 0), 0, 0.06)
    taker_score = score_to_percent(taker_buy_sell_ratio or 1, 0.65, 1.35)
    if proposal.side == "short":
        taker_score = 100 - taker_score
    crowding_score = 100 - score_to_percent(long_short_ratio or 1, 0.5, 2.5) if proposal.side == "long" else score_to_percent(long_short_ratio or 1, 0.5, 2.5)
    cvd_score = score_to_percent(cvd_ratio or 0, -0.35, 0.35)
    if proposal.side == "short":
        cvd_score = 100 - cvd_score
    resistance_distance = levels_1h.get("distance_to_resistance_pct")
    support_distance = levels_1h.get("distance_to_support_pct")
    level_distance = resistance_distance if proposal.side == "long" else support_distance
    level_score = score_to_percent(level_distance or 0, 0, 2.5)

    return [
        {
            "key": "time_horizon",
            "label": "Marco temporal",
            "value": f"{horizon_profile['label']} · {horizon_profile['duration']}",
            "score": 60,
            "bias": "contexto",
            "source": "Seleccion del usuario",
            "explanation": f"Define que datos pesan mas en este analisis. Foco: {horizon_profile.get('focus')}. Principales: {', '.join(horizon_profile['primary_timeframes'])}; confirmacion: {horizon_profile['confirmation_timeframe']}.",
        },
        {
            "key": "technical_rating",
            "label": "Rating tecnico",
            "value": f"{technical_rating['label']} · {technical_rating['score']}/100",
            "score": technical_rating["score"],
            "bias": "favorable" if technical_rating["score"] >= 60 else "desfavorable" if technical_rating["score"] <= 40 else "neutral",
            "source": "EMAs, RSI, distancia a EMA21 y barreras tecnicas por marco temporal",
            "explanation": "Resume solo datos tecnicos que pueden cambiar la decision: alineacion temporal, entrada tardia y obstaculos antes del TP. No premia el R/R ni sustituye al flujo real.",
        },
        {
            "key": "trend",
            "label": "Tendencia multi-TF",
            "value": " / ".join(f"{key}:{timeframes[key]['ema_stack']}" for key in ("5m", "15m", "1h", "4h", "1d", "1w") if key in timeframes),
            "score": min(100, max(0, trend_score_value)),
            "bias": "favorable" if trend_score_value >= 60 else "desfavorable" if trend_score_value <= 40 else "neutral",
            "source": "Binance velas spot 5m, 15m, 1h, 4h, 1d y 1w",
            "explanation": "Compara EMAs en varios marcos temporales. Cuantos mas marcos acompanan, mas solida es la direccion; si varios van en contra, la entrada queda penalizada.",
        },
        {
            "key": "momentum",
            "label": f"Momentum RSI {tf_momentum.get('interval', horizon_profile.get('momentum_timeframe', '5m'))}",
            "value": f"{rsi_value:.1f}",
            "score": min(100, max(0, momentum_score)),
            "bias": "favorable" if 38 <= rsi_value <= 62 else "alerta" if rsi_value > 72 or rsi_value < 28 else "neutral",
            "source": f"Binance velas spot {tf_momentum.get('interval', horizon_profile.get('momentum_timeframe', '5m'))}",
            "explanation": "El RSI mide velocidad del movimiento. Muy alto puede indicar compra extendida; muy bajo puede indicar venta extendida. No decide solo, ayuda a evitar entradas tarde.",
        },
        {
            "key": "volatility",
            "label": f"Volatilidad ATR {tf_volatility.get('interval', horizon_profile.get('volatility_timeframe', '5m'))}",
            "value": f"{tf_volatility['atr_pct']:.2f}%",
            "score": min(100, max(0, volatility_score)),
            "bias": "favorable" if volatility_score >= 60 else "alerta",
            "source": f"Binance velas spot {tf_volatility.get('interval', horizon_profile.get('volatility_timeframe', '5m'))}",
            "explanation": "El ATR aproxima el movimiento normal reciente. Si el stop queda dentro de ese ruido, puede saltar aunque la idea no sea necesariamente mala.",
        },
        {
            "key": "order_book",
            "label": "Order book cercano",
            "value": f"{order_book['imbalance']:+.2f}",
            "score": min(100, max(0, imbalance_score)),
            "bias": "favorable" if (proposal.side == "long" and order_book["imbalance"] > 0.12) or (proposal.side == "short" and order_book["imbalance"] < -0.12) else "desfavorable" if abs(order_book["imbalance"]) > 0.12 else "neutral",
            "source": "Binance order book spot top 20 y bandas top 100",
            "explanation": "Compara liquidez cercana en compras y ventas. No predice por si solo, pero muestra si la presion inmediata acompana o dificulta la entrada.",
        },
        {
            "key": "spread",
            "label": "Spread",
            "value": f"{order_book['spread_pct']:.4f}%",
            "score": min(100, max(0, liquidity_score)),
            "bias": "favorable" if liquidity_score >= 70 else "alerta",
            "source": "Binance order book spot",
            "explanation": "Mide la diferencia entre mejor comprador y mejor vendedor. Cuanto menor es, mas limpia suele ser la ejecucion simulada.",
        },
        {
            "key": "risk_reward",
            "label": "Riesgo/beneficio",
            "value": f"{rr_ratio:.2f}",
            "score": min(100, max(0, rr_score)),
            "bias": "favorable" if rr_ratio >= 1.5 else "alerta",
            "source": "Parametros del usuario",
            "explanation": f"Compara distancia a TP ({reward_distance:.2f}%) contra distancia a SL ({risk_distance:.2f}%). Un ratio alto ayuda, pero no compensa una mala probabilidad.",
        },
        {
            "key": "leverage",
            "label": "Apalancamiento",
            "value": f"x{proposal.leverage:g}",
            "score": min(100, max(0, leverage_score)),
            "bias": "alerta" if proposal.leverage >= 8 else "neutral" if proposal.leverage >= 5 else "favorable",
            "source": "Parametros del usuario",
            "explanation": "A mayor apalancamiento, menor margen de error. El sistema lo penaliza porque aumenta el impacto de movimientos normales contra la posicion.",
        },
        {
            "key": "levels",
            "label": "Soporte/resistencia 1h",
            "value": f"{level_distance:.2f}%" if level_distance is not None else "no disponible",
            "score": min(100, max(0, level_score)),
            "bias": "alerta" if level_score <= 35 else "neutral" if level_score <= 60 else "favorable",
            "source": "Binance velas spot 1h",
            "explanation": "Detecta el nivel tecnico cercano mas relevante. Para longs importa la resistencia superior; para shorts, el soporte inferior. Si esta demasiado cerca, limita recorrido.",
        },
        {
            "key": "cvd_spot",
            "label": "CVD spot reciente",
            "value": format_optional_number(cvd_ratio),
            "score": min(100, max(0, cvd_score)),
            "bias": "favorable" if cvd_score >= 60 else "desfavorable" if cvd_score <= 40 else "neutral",
            "source": "Binance spot aggregate trades",
            "explanation": "Aproxima compras agresivas menos ventas agresivas. Si el CVD acompana la direccion, hay flujo real; si contradice, la entrada tiene menos confirmacion.",
        },
        {
            "key": "market_24h",
            "label": "Movimiento 24h",
            "value": f"{ticker_24h['price_change_pct']:+.2f}%",
            "score": score_to_percent(ticker_24h["price_change_pct"], -5, 5),
            "bias": "contexto",
            "source": "Binance ticker 24h spot",
            "explanation": "Da contexto general del dia. Sirve para saber si la operacion se plantea en un mercado fuerte, debil o lateral.",
        },
        {
            "key": "fear_greed",
            "label": "Fear & Greed",
            "value": f"{fear_greed_value} · {sentiment.get('fear_greed_classification')}" if fear_greed_value is not None else "no disponible",
            "score": fear_greed_value if fear_greed_value is not None else 50,
            "bias": "alerta" if (proposal.side == "long" and (fear_greed_value or 50) >= 75) or (proposal.side == "short" and (fear_greed_value or 50) <= 25) else "contexto",
            "source": "Alternative.me Fear & Greed Index",
            "explanation": "Mide sentimiento general crypto. Extremos de miedo o codicia no son senales automaticas, pero aumentan el riesgo de operar tarde o perseguir precio.",
        },
        {
            "key": "global_crypto",
            "label": "Dominancia BTC",
            "value": f"{btc_dominance:.2f}%" if btc_dominance is not None else "no disponible",
            "score": score_to_percent(btc_dominance or 50, 35, 65),
            "bias": "contexto",
            "source": "CoinGecko global market",
            "explanation": "Resume el peso de BTC dentro del mercado crypto. Ayuda a interpretar si el dinero se concentra en BTC o rota hacia otros activos.",
        },
        {
            "key": "market_breadth",
            "label": "Amplitud crypto top 100",
            "value": f"{advancers_24h:.1f}% suben · mediana {median_24h:+.2f}%" if advancers_24h is not None and median_24h is not None else "no disponible",
            "score": score_to_percent(advancers_24h or 50, 20, 80),
            "bias": "favorable" if (proposal.side == "long" and (advancers_24h or 50) >= 58) or (proposal.side == "short" and (advancers_24h or 50) <= 42) else "desfavorable" if (proposal.side == "long" and (advancers_24h or 50) <= 42) or (proposal.side == "short" and (advancers_24h or 50) >= 58) else "contexto",
            "source": "CoinGecko top markets",
            "explanation": "Mide si el mercado crypto acompana al activo. Si la mayoria del top 100 sube, los longs tienen mejor viento de fondo; si la mayoria cae, ocurre lo contrario.",
        },
        {
            "key": "open_interest_trend",
            "label": "Cambio Open Interest",
            "value": f"{oi_change:+.2f}%" if oi_change is not None else "no disponible",
            "score": score_to_percent(abs(oi_change or 0), 0, 3),
            "bias": "contexto",
            "source": f"Binance Futures openInterestHist {derivatives_horizon['period']}",
            "explanation": "Indica si entra o sale posicionamiento apalancado. OI creciendo con precio direccional puede confirmar presion; OI creciendo contra la idea aumenta riesgo.",
        },
        {
            "key": "funding",
            "label": "Funding futuros",
            "value": f"{format_optional_pct(funding_rate_pct)} · media {format_optional_pct(funding_avg)}",
            "score": min(100, max(0, funding_score)),
            "bias": "alerta" if (proposal.side == "long" and (funding_rate_pct or 0) > 0.03) or (proposal.side == "short" and (funding_rate_pct or 0) < -0.03) else "neutral",
            "source": "Binance USD-M Futures premiumIndex",
            "explanation": "Indica el coste o incentivo de mantener posiciones en futuros perpetuos. Funding extremo puede senalar saturacion y entradas tardias.",
        },
        {
            "key": "taker_flow",
            "label": "Delta taker futuros",
            "value": format_optional_number(taker_buy_sell_ratio),
            "score": min(100, max(0, taker_score)),
            "bias": "favorable" if taker_score >= 60 else "desfavorable" if taker_score <= 40 else "neutral",
            "source": f"Binance Futures taker long/short ratio {derivatives_horizon['period']}",
            "explanation": "Compara volumen comprador agresivo contra vendedor agresivo en futuros. Ayuda a detectar si el flujo inmediato confirma o contradice la direccion.",
        },
        {
            "key": "crowding",
            "label": "Ratio long/short",
            "value": format_optional_number(long_short_ratio),
            "score": min(100, max(0, crowding_score)),
            "bias": "alerta" if crowding_score <= 35 else "neutral",
            "source": f"Binance Futures global long/short account ratio {derivatives_horizon['period']}",
            "explanation": "Mide si las cuentas estan muy cargadas hacia long o short. Cuando un lado esta saturado, aumenta el riesgo de barridos o squeezes.",
        },
    ]


def multi_tf_display_score(timeframes: dict, side: str) -> int:
    weights = {"5m": 0.55, "15m": 0.75, "1h": 1.0, "4h": 1.15, "1d": 1.0, "1w": 0.65}
    max_abs = sum(weights.values())
    raw = 0.0
    for interval, weight in weights.items():
        if interval not in timeframes:
            continue
        stack = timeframes[interval]["ema_stack"]
        raw += weight if stack == "bullish" else -weight if stack == "bearish" else 0
    if side == "short":
        raw *= -1
    return round(50 + (raw / max_abs) * 50)
