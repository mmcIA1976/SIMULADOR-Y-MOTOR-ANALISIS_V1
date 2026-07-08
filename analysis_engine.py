from __future__ import annotations

from dataclasses import dataclass

import data_engine


ENGINE_VERSION = "rules-v0.11-underweighted-risk-cluster"
ENGINE_AUDIT_REFERENCE = {
    "date": "2026-07-08",
    "sample_size": 98,
    "resolved_sample_size": 93,
    "current_engine_resolved_sample_size": 3,
    "baseline": {
        "learning_v0_2_resolved_cases": "93",
        "risk_underweighted_cases": "7.53%",
        "analysis_warned_but_underweighted_risk_cases": "3",
        "extreme_fib_extreme_sentiment_failures": "3/3",
        "extreme_fib_extreme_sentiment_avg_pnl": "-53.7174",
        "extreme_fibonacci_risk_failure_rate": "80.0%",
        "cvd_against_plan_failure_rate": "58.8%",
    },
    "intent": "v0.11 convierte la auditoria learning-v0.2 en un freno conservador por cluster: penaliza Fibonacci extremo con sentimiento extremo y deja trazabilidad sin bloquear automaticamente.",
}
TIME_HORIZON_PROFILES = {
    "intraday_short": {
        "label": "Intradia corto",
        "duration": "30 min-4 h",
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
    },
    "intraday_wide": {
        "label": "Intradia amplio",
        "duration": "4-24 h",
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
    },
    "short_swing": {
        "label": "Swing corto",
        "duration": "1-7 dias",
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
    entry_type: str = "market"
    trigger_condition: str | None = None
    entry_order_type: str | None = None


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
    fibonacci = market_snapshot.get("fibonacci", {})
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
    fibonacci_for_horizon = (
        fibonacci.get(levels_tf_key)
        or fibonacci.get(horizon_profile["primary_timeframes"][0])
        or fibonacci.get("1h", {})
    )
    derivatives_horizon = derivatives_for_horizon(derivatives, horizon_profile)

    recent_range_pct = tf_volatility["recent_range_pct"]
    volume_ratio = tf_volume["volume_ratio"]
    atr_pct = tf_volatility["atr_pct"]
    order_book_imbalance = order_book["imbalance"]
    spread_pct = order_book["spread_pct"]
    rsi_signal = tf_momentum["rsi_14"]
    funding_rate_pct = derivatives.get("funding_rate_pct")
    taker_buy_sell_ratio = derivatives_horizon.get("taker_buy_sell_ratio")
    global_long_short_ratio = derivatives_horizon.get("global_long_short_ratio")
    open_interest_change_pct = derivatives_horizon.get("open_interest_change_pct")

    risk_distance = pct_from_entry(proposal.stop_loss, proposal.entry)
    reward_distance = pct_from_entry(proposal.take_profit, proposal.entry)
    rr_ratio = reward_distance / max(risk_distance, 0.000001)

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
        order_book_bias = (0.016 if order_book_imbalance > 0.12 else -0.016 if order_book_imbalance < -0.12 else 0) * micro_weight
        momentum_bias = (-0.025 if rsi_signal > 72 else 0.02 if 45 <= rsi_signal <= 62 else 0) * micro_weight
    else:
        price_vs_entry_bias = 0.03 if current_price >= proposal.entry else -0.02
        order_book_bias = (0.016 if order_book_imbalance < -0.12 else -0.016 if order_book_imbalance > 0.12 else 0) * micro_weight
        momentum_bias = (-0.025 if rsi_signal < 28 else 0.02 if 38 <= rsi_signal <= 55 else 0) * micro_weight

    volatility_penalty = 0.07 if risk_distance < max(recent_range_pct, atr_pct) * 0.35 else 0
    volume_bias = (0.025 if volume_ratio > 1.25 else -0.015 if volume_ratio < 0.65 else 0) * max(0.5, micro_weight)
    liquidity_penalty = 0.03 if spread_pct > 0.04 else 0
    overextension_penalty = 0.025 if abs(tf_momentum["price_vs_ema_21_pct"]) > max(0.5, atr_pct * 1.8) else 0
    funding_penalty = funding_context_penalty(proposal.side, funding_rate_pct) * funding_weight
    taker_flow_bias = taker_flow_score(proposal.side, taker_buy_sell_ratio) * derivatives_weight
    crowding_penalty = crowding_penalty_score(proposal.side, global_long_short_ratio)
    cvd_bias = cvd_flow_score(proposal.side, trade_flow.get("cvd_ratio")) * micro_weight
    level_penalty = level_risk_penalty(proposal, levels_for_horizon)
    fibonacci_context = build_fibonacci_trade_context(proposal, fibonacci_for_horizon, levels_for_horizon, atr_pct)
    sentiment_penalty = sentiment_extreme_penalty(proposal.side, sentiment.get("fear_greed_value"))
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
    regime_bias = market_regime_direction_bias(proposal.side, market_regime, proposal.time_horizon)
    zone_analysis = build_zone_analysis(
        proposal=proposal,
        current_price=current_price,
        levels_for_horizon=levels_for_horizon,
        fibonacci_context=fibonacci_context,
        market_regime=market_regime,
        technical_rating=technical_rating,
        atr_pct=atr_pct,
        recent_range_pct=recent_range_pct,
        order_book_imbalance=order_book_imbalance,
        taker_buy_sell_ratio=taker_buy_sell_ratio,
        cvd_ratio=trade_flow.get("cvd_ratio"),
        open_interest_change_pct=open_interest_change_pct,
        volume_ratio=volume_ratio,
    )
    zone_probability_context = build_zone_probability_context(zone_analysis)

    tp_probability = (
        0.5
        + trend_bias
        + technical_rating["direction_bias"]
        + price_vs_entry_bias
        + volume_bias
        + order_book_bias
        + momentum_bias
        + regime_bias
        + fibonacci_context["probability_adjustment"]
        + zone_probability_context["probability_adjustment"]
        + taker_flow_bias
        + cvd_bias
        + oi_trend_bias
        + breadth_bias
        - volatility_penalty
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
    range_probability = min(
        0.2,
        range_probability_for_context(recent_range_pct, contradiction_penalty, market_regime)
        + zone_probability_context["range_probability_adjustment"],
    )
    sl_probability = max(0.05, 1 - tp_probability - range_probability)
    risk_calibration_context = build_risk_calibration_context(
        proposal=proposal,
        tp_probability=tp_probability,
        sl_probability=sl_probability,
        rr_ratio=rr_ratio,
        risk_distance=risk_distance,
        reward_distance=reward_distance,
        technical_rating=technical_rating,
        timeframes=market_snapshot["timeframes"],
        ticker_24h=ticker_24h,
        zone_analysis=zone_analysis,
        zone_probability_context=zone_probability_context,
        fibonacci_context=fibonacci_context,
        sentiment_penalty=sentiment_penalty,
        cvd_bias=cvd_bias,
        rsi_signal=rsi_signal,
    )
    tp_probability = min(0.74, max(0.22, tp_probability + risk_calibration_context["tp_probability_adjustment"]))
    range_probability = min(0.22, max(0.04, range_probability + risk_calibration_context["range_probability_adjustment"]))
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
    )
    break_even_probability = 1 / (1 + rr_ratio) if rr_ratio > 0 else 1
    layered_scores = build_layered_scores(
        tp_probability=tp_probability,
        rr_ratio=rr_ratio,
        price_risk_pct=risk_distance,
        volatility_penalty=volatility_penalty,
        level_penalty=level_penalty,
        liquidity_penalty=liquidity_penalty,
        spread_pct=spread_pct,
        contradiction_penalty=contradiction_penalty,
        htf_penalty=htf_penalty,
        regime_bias=regime_bias,
        taker_flow_bias=taker_flow_bias,
        cvd_bias=cvd_bias,
        technical_rating=technical_rating,
        expected_value=expected_value,
        fibonacci_context=fibonacci_context,
        risk_calibration_context=risk_calibration_context,
    )

    risk_score = (
        (0.2 if risk_distance < max(recent_range_pct, atr_pct) * 0.35 else 0)
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
        + fibonacci_context["risk_score_addition"]
        + zone_probability_context["risk_score_addition"]
        + risk_calibration_context["risk_score_addition"]
        + (0.08 if contradiction_penalty >= 0.03 else 0)
    )
    risk_score = min(1.0, max(0.0, risk_score))
    if risk_score >= 0.42:
        risk_level = "alto"
    elif risk_score >= 0.24:
        risk_level = "medio-alto"
    elif risk_score >= 0.12:
        risk_level = "medio"
    else:
        risk_level = "bajo"

    setup_grade = cap_grade(
        grade_from_scores(tp_probability, risk_score, layered_scores["expected_value_score"]),
        risk_calibration_context.get("grade_cap"),
    )
    confidence = confidence_from_score(layered_scores["confidence_score"])

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
    if volume_bias > 0:
        reasons.append("El volumen reciente esta por encima de su media corta.")
    if order_book_bias > 0:
        reasons.append("El order book cercano favorece ligeramente la direccion propuesta.")
    elif order_book_bias < 0:
        alerts.append("El order book cercano va contra la direccion propuesta.")
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
        reasons.append("El CVD Futures reciente acompana la direccion propuesta.")
    elif cvd_bias < 0:
        alerts.append("El CVD Futures reciente va contra la direccion propuesta.")
    if level_penalty:
        alerts.append("La operacion esta cerca de una zona tecnica que puede limitar el recorrido o barrer el stop.")
    if fibonacci_context["bias"] == "favorable":
        reasons.append(f"Fibonacci aporta confluencia: {fibonacci_context['summary']}")
    elif fibonacci_context["bias"] in {"desfavorable", "alerta"}:
        alerts.append(f"Fibonacci advierte riesgo de diseno: {fibonacci_context['summary']}")
    if zone_probability_context["probability_adjustment"] > 0:
        reasons.append(f"La orden pendiente mejora por zona: {zone_analysis.get('zone_summary')}")
    elif zone_probability_context["probability_adjustment"] < 0:
        alerts.append(f"La orden pendiente pierde calidad por zona: {zone_analysis.get('zone_summary')}")
    if zone_probability_context["range_probability_adjustment"] > 0:
        alerts.append("La orden pendiente puede quedar sin activarse; aumenta el escenario de rango/no ejecucion.")
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
    reasons.extend(risk_calibration_context["reasons"])
    alerts.extend(risk_calibration_context["alerts"])

    suggested_leverage = proposal.leverage
    parameter_advice = {
        "entry": {"action": "mantener", "suggested_value": proposal.entry, "reason": "Primera version: no hay senal suficiente para modificar entrada."},
        "stop_loss": {"action": "revisar" if volatility_penalty else "mantener", "suggested_value": proposal.stop_loss, "reason": "Se evalua contra volatilidad reciente."},
        "take_profit": {"action": "mantener", "suggested_value": proposal.take_profit, "reason": "Objetivo usado para calcular relacion riesgo/beneficio."},
        "leverage": {"action": "mantener", "suggested_value": suggested_leverage, "reason": "El apalancamiento se registra como exposicion monetaria, pero no condiciona la lectura de mercado ni la recomendacion."},
    }

    decision = decision_from_context(setup_grade, risk_level, confidence, expected_value, risk_calibration_context)
    invalidation_rules = build_invalidation_rules(proposal, market_regime, levels_for_horizon, taker_flow_bias, cvd_bias)
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
    explained_metrics = build_score_metrics(layered_scores, expected_value, market_regime, probability_ranges) + [
        build_fibonacci_metric(fibonacci_context),
        build_zone_analysis_metric(zone_analysis),
        build_risk_calibration_metric(risk_calibration_context),
    ] + explained_metrics

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
        "audit_reference": ENGINE_AUDIT_REFERENCE,
        "probability_ranges": probability_ranges,
        "expected_value": expected_value,
        "layered_scores": layered_scores,
        "market_regime": market_regime,
        "technical_rating": technical_rating,
        "fibonacci_context": fibonacci_context,
        "zone_analysis": zone_analysis,
        "zone_probability_context": zone_probability_context,
        "risk_calibration_context": risk_calibration_context,
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
            "margin_risk_pct": margin_risk_pct,
            "margin_reward_pct": margin_reward_pct,
            "risk_reward_ratio": rr_ratio,
            "break_even_probability": break_even_probability,
            "probability_ranges": probability_ranges,
            "expected_value": expected_value,
            "layered_scores": layered_scores,
            "market_regime": market_regime,
            "technical_rating": technical_rating,
            "fibonacci_context": fibonacci_context,
            "zone_analysis": zone_analysis,
            "zone_probability_context": zone_probability_context,
            "risk_calibration_context": risk_calibration_context,
            "invalidation_rules": invalidation_rules,
            "engine_version": ENGINE_VERSION,
            "audit_reference": ENGINE_AUDIT_REFERENCE,
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
                "momentum_bias": momentum_bias,
                "market_regime_bias": regime_bias,
                "fibonacci_probability_adjustment": fibonacci_context["probability_adjustment"],
                "fibonacci_confluence_score": fibonacci_context["score"],
                "zone_probability_adjustment": zone_probability_context["probability_adjustment"],
                "zone_range_probability_adjustment": zone_probability_context["range_probability_adjustment"],
                "zone_risk_score_addition": zone_probability_context["risk_score_addition"],
                "risk_calibration_tp_adjustment": risk_calibration_context["tp_probability_adjustment"],
                "risk_calibration_range_adjustment": risk_calibration_context["range_probability_adjustment"],
                "risk_calibration_score_addition": risk_calibration_context["risk_score_addition"],
                "risk_calibration_flags": risk_calibration_context["flags"],
                "zone_confluence_score": zone_analysis.get("zone_confluence_score"),
                "zone_activation_probability": zone_analysis.get("activation_probability"),
                "taker_flow_bias": taker_flow_bias,
                "cvd_bias": cvd_bias,
                "oi_trend_bias": oi_trend_bias,
                "breadth_bias": breadth_bias,
                "volatility_penalty": volatility_penalty,
                "leverage_penalty": 0,
                "leverage_policy": "neutral_for_market_analysis",
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


def build_fibonacci_trade_context(proposal: TradeProposal, fibonacci_data: dict, levels_for_horizon: dict, atr_pct: float) -> dict:
    if not fibonacci_data or not fibonacci_data.get("available"):
        return {
            "available": False,
            "bias": "neutral",
            "score": 50,
            "probability_adjustment": 0,
            "risk_score_addition": 0,
            "execution_risk_addition": 0,
            "entry_zone": "sin_datos",
            "target_zone": "sin_datos",
            "stop_zone": "sin_datos",
            "summary": "sin swing Fibonacci valido para este horizonte",
            "source": fibonacci_data,
        }

    swing = fibonacci_data.get("swing") or {}
    swing_direction = swing.get("direction")
    continuation_direction = "up" if proposal.side == "long" else "down"
    aligned = swing_direction == continuation_direction
    retracements = fibonacci_data.get("retracements") or {}
    extensions = fibonacci_data.get("extensions") or {}
    tolerance_pct = max(0.18, min(0.7, atr_pct * 0.65))
    entry_level = nearest_named_price(proposal.entry, retracements)
    target_level = nearest_named_price(proposal.take_profit, extensions)
    stop_level = nearest_named_price(proposal.stop_loss, retracements)
    entry_zone = classify_trade_price_against_fibs(proposal.entry, fibonacci_data)
    target_zone = classify_trade_price_against_fibs(proposal.take_profit, fibonacci_data)
    stop_zone = classify_trade_price_against_fibs(proposal.stop_loss, fibonacci_data)
    score = 50
    notes = []

    if aligned:
        score += 10
        notes.append("impulso del horizonte acompana la direccion")
    else:
        score -= 14
        notes.append("impulso Fibonacci contradice la direccion")

    if entry_zone == "golden_zone":
        score += 14
        notes.append("entrada en zona 0.5-0.618")
    elif entry_zone == "retroceso_superficial":
        score += 6
        notes.append("entrada en retroceso superficial")
    elif entry_zone in {"extension", "ruptura_o_retroceso_muy_superficial"}:
        score -= 8
        notes.append("entrada tardia o muy extendida")
    elif entry_zone in {"retroceso_extremo", "estructura_rota"}:
        score -= 12
        notes.append("retroceso profundo que amenaza estructura")

    if entry_level and entry_level["distance_pct"] <= tolerance_pct:
        score += 4
    if target_level and target_level["distance_pct"] <= max(tolerance_pct, 0.35):
        score += 5
        notes.append(f"TP cerca de extension {target_level['ratio']}")
    elif target_zone == "extension":
        score -= 5
        notes.append("TP exige extension sin nivel cercano")

    if stop_level and stop_level["distance_pct"] <= tolerance_pct:
        score -= 4
        notes.append("SL demasiado cerca de nivel Fib activo")

    if fibonacci_level_confluence(proposal, levels_for_horizon, tolerance_pct):
        score += 6
        notes.append("confluencia con soporte/resistencia ya detectado")

    score = min(88, max(18, round(score)))
    if score >= 68:
        bias = "favorable"
        probability_adjustment = 0
        risk_score_addition = 0
        execution_risk_addition = -4
    elif score <= 38:
        bias = "desfavorable"
        probability_adjustment = -0.02 if not aligned else -0.01
        risk_score_addition = 0.04
        execution_risk_addition = 8
    elif score <= 46:
        bias = "alerta"
        probability_adjustment = -0.01
        risk_score_addition = 0.02
        execution_risk_addition = 5
    else:
        bias = "neutral"
        probability_adjustment = 0
        risk_score_addition = 0
        execution_risk_addition = 0

    return {
        "available": True,
        "bias": bias,
        "score": score,
        "probability_adjustment": probability_adjustment,
        "risk_score_addition": risk_score_addition,
        "execution_risk_addition": execution_risk_addition,
        "entry_zone": entry_zone,
        "target_zone": target_zone,
        "stop_zone": stop_zone,
        "nearest_entry_level": entry_level,
        "nearest_target_extension": target_level,
        "nearest_stop_level": stop_level,
        "tolerance_pct": round(tolerance_pct, 4),
        "summary": "; ".join(notes[:4]) if notes else "Fibonacci sin confluencia decisiva",
        "source": fibonacci_data,
    }


def build_risk_calibration_context(
    proposal: TradeProposal,
    tp_probability: float,
    sl_probability: float,
    rr_ratio: float,
    risk_distance: float,
    reward_distance: float,
    technical_rating: dict,
    timeframes: dict,
    ticker_24h: dict,
    zone_analysis: dict,
    zone_probability_context: dict,
    fibonacci_context: dict,
    sentiment_penalty: float = 0.0,
    cvd_bias: float = 0.0,
    rsi_signal: float | None = None,
) -> dict:
    flags: list[str] = []
    reasons: list[str] = []
    alerts: list[str] = []
    tp_adjustment = 0.0
    range_adjustment = 0.0
    risk_addition = 0.0
    quality_penalty = 0
    confidence_penalty = 0
    expected_value_penalty = 0
    execution_risk_addition = 0
    force_observar = False
    grade_cap: str | None = None

    def add_gate(
        flag: str,
        alert: str,
        tp_delta: float = 0.0,
        risk_delta: float = 0.0,
        quality_delta: int = 0,
        confidence_delta: int = 0,
        ev_delta: int = 0,
        execution_delta: int = 0,
        cap: str | None = None,
        force: bool = False,
    ) -> None:
        nonlocal tp_adjustment, risk_addition, quality_penalty, confidence_penalty
        nonlocal expected_value_penalty, execution_risk_addition, force_observar, grade_cap
        flags.append(flag)
        alerts.append(alert)
        tp_adjustment += tp_delta
        risk_addition += risk_delta
        quality_penalty += quality_delta
        confidence_penalty += confidence_delta
        expected_value_penalty += ev_delta
        execution_risk_addition += execution_delta
        force_observar = force_observar or force
        grade_cap = stricter_grade_cap(grade_cap, cap)

    if sl_probability >= 0.55:
        add_gate(
            "sl_probability_gte_55",
            "Calibracion v0.10: SL estimado >=55%, zona historicamente debil; se endurece decision.",
            tp_delta=-0.045,
            risk_delta=0.10,
            quality_delta=12,
            confidence_delta=10,
            ev_delta=10,
            execution_delta=10,
            cap="D",
            force=True,
        )
    elif sl_probability >= 0.50:
        add_gate(
            "sl_probability_gte_50",
            "Calibracion v0.10: SL estimado >=50%, se reduce optimismo antes de simular.",
            tp_delta=-0.025,
            risk_delta=0.06,
            quality_delta=8,
            confidence_delta=6,
            ev_delta=6,
            execution_delta=6,
            cap="C",
        )

    if tp_probability < 0.40:
        add_gate(
            "direction_score_lt_40",
            "Calibracion v0.10: direccion probable por debajo de 40/100, grupo historicamente fragil.",
            tp_delta=-0.025,
            risk_delta=0.07,
            quality_delta=8,
            confidence_delta=8,
            ev_delta=6,
            execution_delta=6,
            cap="D",
            force=True,
        )

    if technical_rating.get("score", 50) < 40:
        add_gate(
            "technical_score_lt_40",
            "Calibracion v0.10: rating tecnico <40/100, se trata como filtro de riesgo.",
            tp_delta=-0.02,
            risk_delta=0.07,
            quality_delta=8,
            confidence_delta=8,
            ev_delta=6,
            execution_delta=6,
            cap="C",
        )

    ambitious_target = reward_distance >= 3.0
    if rr_ratio >= 3.0:
        add_gate(
            "rr_ratio_gte_3",
            "Calibracion v0.10: R/R >=3 no se premia por si solo; historicamente fallo cuando el TP quedaba lejano.",
            tp_delta=-0.035 if ambitious_target else -0.02,
            risk_delta=0.08,
            quality_delta=15,
            confidence_delta=5,
            ev_delta=12,
            execution_delta=8,
            cap="C",
        )
    if ambitious_target:
        add_gate(
            "reward_distance_gte_3",
            "Calibracion v0.10: TP >=3% desde entrada, se exige mas confirmacion antes de considerarlo fiable.",
            tp_delta=-0.025,
            risk_delta=0.07,
            quality_delta=10,
            confidence_delta=4,
            ev_delta=10,
            execution_delta=6,
            cap="C",
        )

    if risk_distance < 0.25:
        add_gate(
            "risk_distance_lt_0_25",
            "Calibracion v0.10: SL <0.25% queda expuesto a ruido y barridas.",
            tp_delta=-0.025,
            risk_delta=0.10,
            quality_delta=10,
            confidence_delta=6,
            ev_delta=8,
            execution_delta=12,
            cap="C",
        )
    elif risk_distance >= 3.0:
        add_gate(
            "risk_distance_gte_3",
            "Calibracion v0.10: SL >=3% aumenta dano esperado y baja calidad operativa.",
            risk_delta=0.08,
            quality_delta=10,
            confidence_delta=4,
            ev_delta=8,
            execution_delta=6,
            cap="C",
        )

    price_change_pct = ticker_24h.get("price_change_pct")
    if side_signed_contra(proposal.side, price_change_pct, threshold=0.25):
        add_gate(
            "ticker_24h_contra_side",
            "Calibracion v0.10: movimiento 24h del activo va contra el lado propuesto.",
            tp_delta=-0.025,
            risk_delta=0.05,
            quality_delta=6,
            confidence_delta=6,
            ev_delta=4,
            execution_delta=4,
            cap="C",
        )

    if timeframe_contra_side(proposal.side, timeframes.get("15m", {}), require_stack=True):
        add_gate(
            "ema_stack_15m_contra_side",
            "Calibracion v0.10: stack EMA 15m contrario al lado propuesto.",
            tp_delta=-0.02,
            risk_delta=0.04,
            quality_delta=6,
            confidence_delta=6,
            ev_delta=4,
            execution_delta=4,
            cap="C",
        )
    if timeframe_contra_side(proposal.side, timeframes.get("1h", {}), require_stack=False):
        add_gate(
            "price_vs_ema_1h_contra_side",
            "Calibracion v0.10: precio vs EMA21 1h contrario al lado propuesto.",
            tp_delta=-0.02,
            risk_delta=0.04,
            quality_delta=6,
            confidence_delta=6,
            ev_delta=4,
            execution_delta=4,
            cap="C",
        )

    zone_adjustment = zone_probability_context.get("probability_adjustment", 0)
    if zone_adjustment < 0:
        add_gate(
            "pending_zone_negative_adjustment",
            "Calibracion v0.10: zona pendiente con ajuste negativo se degrada por alta tasa historica de fallo.",
            tp_delta=-0.015,
            risk_delta=0.04,
            quality_delta=6,
            confidence_delta=5,
            ev_delta=4,
            execution_delta=4,
            cap="C",
        )
    if zone_analysis.get("entry_order_type") == "stop_breakdown":
        add_gate(
            "pending_stop_breakdown",
            "Calibracion v0.10: stop_breakdown queda bajo vigilancia estricta hasta tener muestra positiva.",
            tp_delta=-0.03,
            risk_delta=0.08,
            quality_delta=10,
            confidence_delta=8,
            ev_delta=8,
            execution_delta=8,
            cap="D",
            force=True,
        )
    if zone_analysis.get("liquidity_sweep_risk") == "alto":
        add_gate(
            "pending_liquidity_sweep_high",
            "Calibracion v0.10: riesgo alto de barrida en entrada pendiente.",
            tp_delta=-0.02,
            risk_delta=0.05,
            quality_delta=7,
            confidence_delta=6,
            ev_delta=5,
            execution_delta=6,
            cap="C",
        )
    if zone_analysis.get("reaction_bias") == "falsa_ruptura_riesgo":
        add_gate(
            "pending_false_breakout_risk",
            "Calibracion v0.10: sesgo de falsa ruptura historicamente fragil.",
            tp_delta=-0.02,
            risk_delta=0.05,
            quality_delta=7,
            confidence_delta=6,
            ev_delta=5,
            execution_delta=6,
            cap="C",
        )

    fibonacci_score = fibonacci_context.get("score", 50)
    extreme_fibonacci = (
        fibonacci_context.get("bias") == "desfavorable"
        and (
            fibonacci_score < 30
            or fibonacci_context.get("entry_zone") == "retroceso_extremo"
        )
    )
    extreme_sentiment = sentiment_penalty >= 0.01
    cvd_contra = cvd_bias < -0.005
    rsi_extreme = rsi_extreme_against_entry(proposal.side, rsi_signal)
    material_risk_count = sum(1 for active in (extreme_fibonacci, extreme_sentiment, cvd_contra) if active)
    if extreme_fibonacci and extreme_sentiment:
        add_gate(
            "extreme_fib_extreme_sentiment_cluster",
            "Calibracion v0.11: Fibonacci extremo + sentimiento extremo fue un cluster perdedor en auditoria learning-v0.2; se reduce sobreconfianza.",
            tp_delta=-0.035,
            risk_delta=0.08,
            quality_delta=12,
            confidence_delta=10,
            ev_delta=9,
            execution_delta=8,
            cap="C",
        )
        if cvd_contra:
            add_gate(
                "extreme_fib_sentiment_cvd_contra",
                "Calibracion v0.11: el cluster anterior aparece ademas con CVD contrario al plan; se anade freno incremental.",
                tp_delta=-0.015,
                risk_delta=0.03,
                quality_delta=4,
                confidence_delta=5,
                ev_delta=4,
                execution_delta=4,
                cap="C",
            )
    if rsi_extreme and material_risk_count >= 2:
        add_gate(
            "rsi_extreme_multi_risk_cluster",
            "Calibracion v0.11: RSI extremo contra la entrada se combina con otros riesgos materiales; se trata como agravante contextual, no como filtro aislado.",
            tp_delta=-0.012,
            risk_delta=0.025,
            quality_delta=4,
            confidence_delta=4,
            ev_delta=3,
            execution_delta=4,
            cap="C",
        )
        if extreme_fibonacci and extreme_sentiment:
            add_gate(
                "rsi_extreme_with_fib_sentiment_cluster",
                "Calibracion v0.11: RSI extremo refuerza el cluster Fibonacci extremo + sentimiento extremo detectado en fallos historicos.",
                tp_delta=-0.008,
                risk_delta=0.015,
                quality_delta=3,
                confidence_delta=3,
                ev_delta=2,
                execution_delta=3,
                cap="C",
            )

    if fibonacci_context.get("bias") == "favorable":
        reasons.append("Calibracion v0.10: Fibonacci favorable se conserva como contexto, sin bonus directo de probabilidad.")

    return {
        "version": ENGINE_VERSION,
        "source_audit": "auditorias_aprendizaje/2026-07-06_operaciones_cerradas_184_auditoria_profunda_motor_v0_9.md + HISTORIAL_CAMBIOS_MOTOR_ANALISIS.md fase v0.11 2026-07-08",
        "flags": flags,
        "tp_probability_adjustment": round(max(-0.16, tp_adjustment), 4),
        "range_probability_adjustment": round(range_adjustment, 4),
        "risk_score_addition": round(min(0.28, risk_addition), 4),
        "quality_score_penalty": min(35, quality_penalty),
        "confidence_score_penalty": min(28, confidence_penalty),
        "expected_value_score_penalty": min(30, expected_value_penalty),
        "execution_risk_score_addition": min(32, execution_risk_addition),
        "grade_cap": grade_cap,
        "force_observar": force_observar,
        "reasons": reasons,
        "alerts": alerts,
    }


def side_signed_contra(side: str, value: float | None, threshold: float) -> bool:
    if value is None:
        return False
    return (side == "long" and value <= -threshold) or (side == "short" and value >= threshold)


def timeframe_contra_side(side: str, timeframe: dict, require_stack: bool) -> bool:
    if not timeframe:
        return False
    ema_stack = timeframe.get("ema_stack")
    price_vs_ema = timeframe.get("price_vs_ema_21_pct")
    if require_stack:
        return (side == "long" and ema_stack == "bearish") or (side == "short" and ema_stack == "bullish")
    if price_vs_ema is None:
        return False
    return side_signed_contra(side, price_vs_ema, threshold=0.08)


def rsi_extreme_against_entry(side: str, rsi_value: float | None) -> bool:
    if rsi_value is None:
        return False
    return (side == "short" and rsi_value <= 30) or (side == "long" and rsi_value >= 70)


def stricter_grade_cap(current: str | None, candidate: str | None) -> str | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return candidate if order[candidate] > order[current] else current


def cap_grade(grade: str, cap: str | None) -> str:
    if cap is None:
        return grade
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return cap if order[grade] < order[cap] else grade


def nearest_named_price(price: float, levels: dict[str, float]) -> dict | None:
    if not levels:
        return None
    ratio, level_price = min(levels.items(), key=lambda item: abs(float(item[1]) - price))
    return {
        "ratio": ratio,
        "price": level_price,
        "distance_pct": round(abs((price - float(level_price)) / max(abs(float(level_price)), 0.000001)) * 100, 4),
    }


def classify_trade_price_against_fibs(price: float, fibonacci_data: dict) -> str:
    swing = fibonacci_data.get("swing") or {}
    start_price = float(swing.get("start_price") or 0)
    end_price = float(swing.get("end_price") or 0)
    direction = swing.get("direction")
    move = abs(end_price - start_price)
    if move <= 0:
        return "sin_rango"
    retracement = (end_price - price) / move if direction == "up" else (price - end_price) / move
    if retracement < -0.03:
        return "extension"
    if retracement < 0.236:
        return "ruptura_o_retroceso_muy_superficial"
    if retracement < 0.382:
        return "retroceso_superficial"
    if retracement <= 0.618:
        return "golden_zone"
    if retracement <= 0.786:
        return "retroceso_profundo"
    if retracement <= 1.0:
        return "retroceso_extremo"
    return "estructura_rota"


def fibonacci_level_confluence(proposal: TradeProposal, levels_for_horizon: dict, tolerance_pct: float) -> bool:
    if proposal.side == "long":
        support = levels_for_horizon.get("nearest_support")
        if not support:
            return False
        return abs((proposal.entry - float(support)) / max(abs(float(support)), 0.000001)) * 100 <= tolerance_pct
    resistance = levels_for_horizon.get("nearest_resistance")
    if not resistance:
        return False
    return abs((proposal.entry - float(resistance)) / max(abs(float(resistance)), 0.000001)) * 100 <= tolerance_pct


def build_zone_analysis(
    proposal: TradeProposal,
    current_price: float,
    levels_for_horizon: dict,
    fibonacci_context: dict,
    market_regime: dict,
    technical_rating: dict,
    atr_pct: float,
    recent_range_pct: float,
    order_book_imbalance: float,
    taker_buy_sell_ratio: float | None,
    cvd_ratio: float | None,
    open_interest_change_pct: float | None,
    volume_ratio: float,
) -> dict:
    entry_type = (proposal.entry_type or "market").lower()
    trigger_condition = proposal.trigger_condition
    order_type = proposal.entry_order_type or classify_entry_order_type(proposal.side, trigger_condition)
    if entry_type != "pending":
        return {
            "available": False,
            "entry_type": entry_type,
            "entry_order_type": order_type,
            "entry_zone_type": "market_entry",
            "zone_confluence_score": 50,
            "activation_probability": None,
            "reaction_bias": "no_aplica",
            "rejection_probability": None,
            "breakout_probability": None,
            "liquidity_sweep_risk": "no_aplica",
            "pullback_quality": None,
            "breakout_quality": None,
            "invalidation_quality": None,
            "target_path_quality": None,
            "zone_summary": "Entrada a mercado: no requiere analisis de activacion pendiente.",
            "zone_reasons": [],
            "zone_alerts": [],
        }

    direction_to_trigger = "up" if trigger_condition == "price_gte" else "down"
    distance_to_activation_pct = pct_between(current_price, proposal.entry)
    atr_units_to_activation = distance_to_activation_pct / max(atr_pct, 0.000001)
    range_units_to_activation = distance_to_activation_pct / max(recent_range_pct, 0.000001)
    tolerance_pct = max(0.18, min(0.75, atr_pct * 0.8))
    support = levels_for_horizon.get("nearest_support")
    resistance = levels_for_horizon.get("nearest_resistance")
    support_distance = pct_between(proposal.entry, float(support)) if support is not None else None
    resistance_distance = pct_between(proposal.entry, float(resistance)) if resistance is not None else None
    desired_level = "support" if order_type == "limit_pullback" and proposal.side == "long" else "resistance" if order_type == "limit_pullback" else "resistance" if order_type == "stop_breakout" else "support" if order_type == "stop_breakdown" else None
    desired_level_distance = support_distance if desired_level == "support" else resistance_distance if desired_level == "resistance" else None

    confluence_score = 50
    reasons: list[str] = []
    alerts: list[str] = []

    fib_bias = fibonacci_context.get("bias", "neutral")
    if fib_bias == "favorable":
        confluence_score += 14
        reasons.append("Fibonacci acompana la zona de entrada.")
    elif fib_bias in {"desfavorable", "alerta"}:
        confluence_score -= 10
        alerts.append("Fibonacci advierte que la zona no es limpia.")

    if desired_level_distance is not None:
        if desired_level_distance <= tolerance_pct:
            confluence_score += 13
            reasons.append(f"La entrada coincide con {desired_level} relevante del horizonte.")
        elif desired_level_distance <= max(tolerance_pct * 1.8, 0.55):
            confluence_score += 6
            reasons.append(f"La entrada queda cerca de {desired_level} relevante.")
        else:
            confluence_score -= 5
            alerts.append(f"La entrada no queda apoyada por {desired_level} cercano.")
    else:
        alerts.append("No hay soporte/resistencia cercano suficiente para validar la zona.")

    technical_score = technical_rating.get("score", 50)
    if technical_score >= 62:
        confluence_score += 8
        reasons.append("El rating tecnico general acompana el plan.")
    elif technical_score <= 42:
        confluence_score -= 8
        alerts.append("El rating tecnico general contradice el plan.")

    regime_name = market_regime.get("name")
    if (proposal.side == "long" and regime_name == "tendencia_alcista") or (proposal.side == "short" and regime_name == "tendencia_bajista"):
        confluence_score += 8
        reasons.append("El regimen dominante acompana la direccion despues de la activacion.")
    elif regime_name == "rebote_contra_tendencia":
        confluence_score -= 7
        alerts.append("La orden depende de un rebote contra estructura superior.")

    activation_probability = 0.5
    if distance_to_activation_pct <= atr_pct * 0.75:
        activation_probability += 0.18
    elif distance_to_activation_pct <= atr_pct * 1.5:
        activation_probability += 0.1
    elif distance_to_activation_pct > max(recent_range_pct, atr_pct * 2.5):
        activation_probability -= 0.16
    if direction_to_trigger == "up":
        activation_probability += 0.06 if regime_name == "tendencia_alcista" else -0.06 if regime_name == "tendencia_bajista" else 0
    else:
        activation_probability += 0.06 if regime_name == "tendencia_bajista" else -0.06 if regime_name == "tendencia_alcista" else 0
    if volume_ratio >= 1.25:
        activation_probability += 0.04
    activation_probability = clamp_float(activation_probability, 0.05, 0.9)

    risk_distance_pct = pct_from_entry(proposal.stop_loss, proposal.entry)
    reward_distance_pct = pct_from_entry(proposal.take_profit, proposal.entry)
    stop_noise_threshold = max(atr_pct, recent_range_pct * 0.35)
    sweep_score = 45
    if risk_distance_pct < stop_noise_threshold:
        sweep_score += 28
        alerts.append("El SL queda dentro del ruido normal de la zona; aumenta riesgo de barrida.")
    elif risk_distance_pct < stop_noise_threshold * 1.6:
        sweep_score += 12
    else:
        sweep_score -= 8
        reasons.append("El SL deja algo de margen frente al ruido normal.")

    if order_type == "limit_pullback":
        if proposal.side == "long" and order_book_imbalance < -0.12:
            sweep_score += 8
        if proposal.side == "short" and order_book_imbalance > 0.12:
            sweep_score += 8
    sweep_score = round(clamp_float(sweep_score, 5, 95))
    liquidity_sweep_risk = "alto" if sweep_score >= 68 else "medio" if sweep_score >= 42 else "bajo"

    if order_type == "limit_pullback":
        rejection_probability = clamp_float(0.34 + (confluence_score - 50) / 130 - (sweep_score - 45) / 220, 0.1, 0.82)
        breakout_probability = clamp_float(0.28 + (sweep_score - 45) / 180 - (confluence_score - 50) / 170, 0.08, 0.78)
        reaction_bias = "rebote_probable" if rejection_probability >= 0.54 else "zona_de_barrida" if liquidity_sweep_risk == "alto" else "reaccion_incierta"
        pullback_quality = round(clamp_float(confluence_score - max(0, sweep_score - 50) * 0.35, 0, 100))
        breakout_quality = None
    else:
        breakout_probability = clamp_float(0.35 + (technical_score - 50) / 140 + (volume_ratio - 1) * 0.08 - (sweep_score - 45) / 260, 0.1, 0.84)
        rejection_probability = clamp_float(0.3 + (sweep_score - 45) / 180 - (technical_score - 50) / 180, 0.08, 0.78)
        reaction_bias = "ruptura_probable" if breakout_probability >= 0.54 else "falsa_ruptura_riesgo" if liquidity_sweep_risk == "alto" else "ruptura_incierta"
        breakout_quality = round(clamp_float(confluence_score + (volume_ratio - 1) * 12 - max(0, sweep_score - 50) * 0.25, 0, 100))
        pullback_quality = None

    invalidation_quality = round(clamp_float(58 + risk_distance_pct * 5 - sweep_score * 0.32 + (8 if fib_bias == "favorable" else -6 if fib_bias in {"desfavorable", "alerta"} else 0), 0, 100))
    target_path_quality = build_target_path_quality(proposal, levels_for_horizon, reward_distance_pct, atr_pct)
    confluence_score = round(clamp_float(confluence_score, 0, 100))

    if target_path_quality <= 40:
        alerts.append("El camino al TP tiene una barrera tecnica relevante antes del objetivo.")
    elif target_path_quality >= 66:
        reasons.append("El camino al TP no muestra una barrera inmediata dominante.")

    if taker_buy_sell_ratio is not None:
        if (proposal.side == "long" and taker_buy_sell_ratio >= 1.15) or (proposal.side == "short" and taker_buy_sell_ratio <= 0.85):
            reasons.append("El flujo taker de futuros acompana la reaccion esperada.")
        elif (proposal.side == "long" and taker_buy_sell_ratio <= 0.85) or (proposal.side == "short" and taker_buy_sell_ratio >= 1.15):
            alerts.append("El flujo taker de futuros contradice la reaccion esperada.")
    if cvd_ratio is not None and abs(cvd_ratio) >= 0.12:
        if (proposal.side == "long" and cvd_ratio > 0) or (proposal.side == "short" and cvd_ratio < 0):
            reasons.append("El CVD Futures acompana la direccion posterior a la activacion.")
        else:
            alerts.append("El CVD Futures contradice la direccion posterior a la activacion.")
    if open_interest_change_pct is not None and abs(open_interest_change_pct) >= 1.2:
        reasons.append("El open interest muestra actividad suficiente para vigilar reaccion real de la zona.")

    entry_zone_type = {
        "limit_pullback": "support_pullback_zone" if proposal.side == "long" else "resistance_pullback_zone",
        "stop_breakout": "resistance_breakout_zone",
        "stop_breakdown": "support_breakdown_zone",
    }.get(order_type, "pending_zone")
    zone_summary = (
        f"{entry_zone_type}: activacion a {distance_to_activation_pct:.2f}% "
        f"({atr_units_to_activation:.2f} ATR), confluencia {confluence_score}/100, "
        f"riesgo de barrida {liquidity_sweep_risk}."
    )
    return {
        "available": True,
        "entry_type": entry_type,
        "trigger_condition": trigger_condition,
        "entry_order_type": order_type,
        "entry_zone_type": entry_zone_type,
        "distance_to_activation_pct": round(distance_to_activation_pct, 4),
        "atr_units_to_activation": round(atr_units_to_activation, 4),
        "range_units_to_activation": round(range_units_to_activation, 4),
        "zone_confluence_score": confluence_score,
        "activation_probability": round(activation_probability, 4),
        "reaction_bias": reaction_bias,
        "rejection_probability": round(rejection_probability, 4),
        "breakout_probability": round(breakout_probability, 4),
        "liquidity_sweep_risk": liquidity_sweep_risk,
        "liquidity_sweep_score": sweep_score,
        "pullback_quality": pullback_quality,
        "breakout_quality": breakout_quality,
        "invalidation_quality": invalidation_quality,
        "target_path_quality": target_path_quality,
        "nearest_support": support,
        "nearest_resistance": resistance,
        "desired_level": desired_level,
        "desired_level_distance_pct": round(desired_level_distance, 4) if desired_level_distance is not None else None,
        "zone_summary": zone_summary,
        "zone_reasons": reasons[:6],
        "zone_alerts": alerts[:6],
    }


def build_zone_probability_context(zone_analysis: dict) -> dict:
    if not zone_analysis.get("available"):
        return {
            "probability_adjustment": 0,
            "range_probability_adjustment": 0,
            "risk_score_addition": 0,
            "summary": "sin ajuste: entrada a mercado o zona no disponible",
            "reasons": [],
        }

    confluence = float(zone_analysis.get("zone_confluence_score") or 50)
    activation_probability = zone_analysis.get("activation_probability")
    activation = float(activation_probability) if activation_probability is not None else 0.5
    target_path = float(zone_analysis.get("target_path_quality") or 50)
    invalidation = float(zone_analysis.get("invalidation_quality") or 50)
    sweep_risk = zone_analysis.get("liquidity_sweep_risk")
    reaction_bias = zone_analysis.get("reaction_bias")
    order_type = zone_analysis.get("entry_order_type")

    adjustment = 0.0
    risk_addition = 0.0
    range_adjustment = 0.0
    reasons: list[str] = []

    if order_type == "limit_pullback":
        if reaction_bias == "rebote_probable" and confluence >= 65 and sweep_risk != "alto":
            adjustment += 0.018
            reasons.append("pullback en zona con reaccion probable")
        elif reaction_bias == "zona_de_barrida" or sweep_risk == "alto":
            adjustment -= 0.025
            risk_addition += 0.035
            reasons.append("pullback con riesgo de barrida")
    elif order_type in {"stop_breakout", "stop_breakdown"}:
        if reaction_bias == "ruptura_probable" and confluence >= 60 and target_path >= 55:
            adjustment += 0.014
            reasons.append("ruptura con zona y camino aceptables")
        elif reaction_bias == "falsa_ruptura_riesgo" or sweep_risk == "alto":
            adjustment -= 0.025
            risk_addition += 0.035
            reasons.append("ruptura con riesgo de falsa activacion")

    if confluence >= 78 and target_path >= 62 and invalidation >= 52 and sweep_risk != "alto":
        adjustment += 0.007
        reasons.append("confluencia, invalidacion y TP alineados")
    if confluence <= 42:
        adjustment -= 0.012
        risk_addition += 0.012
        reasons.append("confluencia de zona debil")
    if target_path <= 40:
        adjustment -= 0.012
        risk_addition += 0.01
        reasons.append("barrera tecnica antes del TP")
    if invalidation <= 38:
        adjustment -= 0.012
        risk_addition += 0.012
        reasons.append("invalidacion poco robusta")

    if activation < 0.28:
        range_adjustment += 0.04
        reasons.append("activacion poco probable")
    elif activation < 0.42:
        range_adjustment += 0.02
        reasons.append("activacion incierta")
    elif activation > 0.72 and sweep_risk == "alto":
        risk_addition += 0.01
        reasons.append("activacion probable pero con riesgo de barrida")

    adjustment = round(clamp_float(adjustment, -0.035, 0.025), 4)
    range_adjustment = round(clamp_float(range_adjustment, 0, 0.04), 4)
    risk_addition = round(clamp_float(risk_addition, 0, 0.06), 4)
    return {
        "probability_adjustment": adjustment,
        "range_probability_adjustment": range_adjustment,
        "risk_score_addition": risk_addition,
        "summary": "; ".join(reasons) if reasons else "zona pendiente sin ajuste decisivo",
        "reasons": reasons,
    }


def classify_entry_order_type(side: str, trigger_condition: str | None) -> str | None:
    if trigger_condition == "price_lte":
        return "limit_pullback" if side == "long" else "stop_breakdown"
    if trigger_condition == "price_gte":
        return "stop_breakout" if side == "long" else "limit_pullback"
    return None


def build_target_path_quality(proposal: TradeProposal, levels_for_horizon: dict, reward_distance_pct: float, atr_pct: float) -> int:
    if reward_distance_pct <= 0:
        return 0
    tolerance = max(0.12, atr_pct * 0.45)
    if proposal.side == "long":
        barrier = levels_for_horizon.get("nearest_resistance")
        if barrier is None:
            return 60
        barrier = float(barrier)
        if proposal.entry < barrier < proposal.take_profit:
            barrier_distance = pct_from_entry(barrier, proposal.entry)
            return round(clamp_float(35 + score_to_percent(barrier_distance, 0, reward_distance_pct) * 0.25, 15, 55))
        if pct_between(proposal.take_profit, barrier) <= tolerance:
            return 70
        return 62
    barrier = levels_for_horizon.get("nearest_support")
    if barrier is None:
        return 60
    barrier = float(barrier)
    if proposal.take_profit < barrier < proposal.entry:
        barrier_distance = pct_from_entry(barrier, proposal.entry)
        return round(clamp_float(35 + score_to_percent(barrier_distance, 0, reward_distance_pct) * 0.25, 15, 55))
    if pct_between(proposal.take_profit, barrier) <= tolerance:
        return 70
    return 62


def pct_between(price_a: float, price_b: float) -> float:
    return abs((float(price_a) - float(price_b)) / max(abs(float(price_b)), 0.000001)) * 100


def clamp_float(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def build_fibonacci_metric(fibonacci_context: dict) -> dict:
    bias = fibonacci_context.get("bias", "neutral")
    return {
        "key": "fibonacci_confluence",
        "label": "Fibonacci confluencia",
        "value": f"{fibonacci_context.get('score', 50)}/100",
        "score": fibonacci_context.get("score", 50),
        "bias": "favorable" if bias == "favorable" else "desfavorable" if bias in {"desfavorable", "alerta"} else "contexto",
        "source": "Binance Futures klines · swings automaticos",
        "explanation": fibonacci_context.get("summary") or "Evalua retrocesos/extensiones como zonas de entrada, objetivo e invalidacion; no funciona como senal aislada.",
    }


def build_risk_calibration_metric(risk_calibration_context: dict) -> dict:
    flags = risk_calibration_context.get("flags") or []
    adjustment = risk_calibration_context.get("tp_probability_adjustment", 0)
    risk_addition = risk_calibration_context.get("risk_score_addition", 0)
    if flags:
        value = f"{len(flags)} frenos · TP {adjustment:+.1%} · riesgo +{risk_addition:.2f}"
        score = max(0, 100 - len(flags) * 10 - round(risk_addition * 100))
        bias = "desfavorable"
        explanation = "Aplica frenos versionados derivados de auditoria: " + ", ".join(flags[:5])
    else:
        value = "sin frenos activos"
        score = 82
        bias = "neutral"
        explanation = "No activa clusters de riesgo historicamente fragiles auditados para esta version."
    return {
        "key": "risk_calibration",
        "label": "Calibracion de riesgo",
        "value": value,
        "score": score,
        "bias": bias,
        "source": ENGINE_VERSION,
        "explanation": explanation,
    }


def build_zone_analysis_metric(zone_analysis: dict) -> dict:
    if not zone_analysis.get("available"):
        return {
            "key": "pending_zone_analysis",
            "label": "Zona orden pendiente",
            "value": "no aplica",
            "score": 50,
            "bias": "contexto",
            "source": "Analisis interno de ejecucion",
            "explanation": zone_analysis.get("zone_summary", "La entrada a mercado no requiere activacion por zona."),
        }
    score = zone_analysis.get("zone_confluence_score", 50)
    activation = zone_analysis.get("activation_probability")
    value = f"{score}/100"
    if activation is not None:
        value += f" · activacion {activation:.0%}"
    return {
        "key": "pending_zone_analysis",
        "label": "Zona orden pendiente",
        "value": value,
        "score": score,
        "bias": "favorable" if score >= 65 else "alerta" if score <= 42 else "contexto",
        "source": "Soporte/resistencia, Fibonacci, ATR, flujo y regimen",
        "explanation": zone_analysis.get("zone_summary") or "Evalua si la orden pendiente espera una zona defendible, una ruptura limpia o una zona de barrida probable.",
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


def market_regime_direction_bias(side: str, market_regime: dict, time_horizon: str) -> float:
    """Small directional adjustment from the audited regime layer.

    The 2026-06-07 audit showed market regime was one of the most reliable
    predictors. Keep the adjustment modest so it confirms structure without
    overwhelming live flow or invalidation risks.
    """
    name = market_regime.get("name")
    profile = time_horizon_profile(time_horizon)
    weight = 0.85 if time_horizon == "intraday_short" else 1.0 if time_horizon == "intraday_wide" else 1.15
    if name == "tendencia_alcista":
        return (0.024 if side == "long" else -0.028) * weight
    if name == "tendencia_bajista":
        return (0.024 if side == "short" else -0.028) * weight
    if name == "rebote_contra_tendencia":
        return -0.018 * profile["htf_penalty_weight"]
    return 0


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
) -> dict:
    notional = proposal.margin * proposal.leverage
    gross_win = notional * (reward_distance / 100)
    gross_loss = notional * (risk_distance / 100)
    fee_rate_round_trip = 0.0008
    slippage_rate_round_trip = max(spread_pct / 100, 0.0002)
    funding_cost = notional * abs(funding_rate_pct or 0) / 100
    estimated_cost = notional * (fee_rate_round_trip + slippage_rate_round_trip) + funding_cost
    net_win = gross_win - estimated_cost
    net_loss = gross_loss + estimated_cost
    expected_value_usdt = tp_probability * net_win - sl_probability * net_loss - range_probability * estimated_cost
    return {
        "notional": round(notional, 4),
        "gross_win_usdt": round(gross_win, 4),
        "gross_loss_usdt": round(gross_loss, 4),
        "estimated_cost_usdt": round(estimated_cost, 4),
        "net_win_usdt": round(net_win, 4),
        "net_loss_usdt": round(net_loss, 4),
        "expected_value_usdt": round(expected_value_usdt, 4),
        "expected_value_pct_margin": round((expected_value_usdt / proposal.margin) * 100, 4) if proposal.margin else 0,
        "expected_value_pct_notional": round((expected_value_usdt / notional) * 100, 4) if notional else 0,
        "label": "positiva" if expected_value_usdt > 0 else "negativa" if expected_value_usdt < 0 else "neutral",
    }


def build_layered_scores(
    tp_probability: float,
    rr_ratio: float,
    price_risk_pct: float,
    volatility_penalty: float,
    level_penalty: float,
    liquidity_penalty: float,
    spread_pct: float,
    contradiction_penalty: float,
    htf_penalty: float,
    regime_bias: float,
    taker_flow_bias: float,
    cvd_bias: float,
    technical_rating: dict,
    expected_value: dict,
    fibonacci_context: dict,
    risk_calibration_context: dict | None = None,
) -> dict:
    risk_calibration_context = risk_calibration_context or {}
    direction_score = round(tp_probability * 100)
    risk_design_penalty = min(22, price_risk_pct * 4.5)
    ev_design_score = score_to_percent(expected_value.get("expected_value_pct_notional", 0), -0.8, 1.2)
    quality_score = round(
        min(
            100,
            max(
                0,
                42
                + score_to_percent(rr_ratio, 0.8, 3.2) * 0.16
                + ev_design_score * 0.22
                + (fibonacci_context.get("score", 50) - 50) * 0.12
                - risk_design_penalty,
            ),
        )
    )
    quality_score = max(0, quality_score - risk_calibration_context.get("quality_score_penalty", 0))
    execution_risk_score = round(
        min(
            100,
            max(
                0,
                30
                + volatility_penalty * 220
                + level_penalty * 300
                + fibonacci_context.get("execution_risk_addition", 0)
                + liquidity_penalty * 250
                + risk_calibration_context.get("execution_risk_score_addition", 0)
                + score_to_percent(spread_pct, 0, 0.08) * 0.35,
            ),
        )
    )
    alignment = 70
    if contradiction_penalty:
        alignment -= round(contradiction_penalty * 700)
    if htf_penalty:
        alignment -= 12
    alignment += round(regime_bias * 420)
    if taker_flow_bias * cvd_bias < 0:
        alignment -= 12
    alignment += round(technical_rating.get("confidence_adjustment", 0))
    alignment -= risk_calibration_context.get("confidence_score_penalty", 0)
    confidence_score = min(95, max(15, alignment))
    ev_score = max(
        0,
        score_to_percent(expected_value.get("expected_value_pct_notional", 0), -1.0, 1.6)
        - risk_calibration_context.get("expected_value_score_penalty", 0),
    )
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


def decision_from_context(
    setup_grade: str,
    risk_level: str,
    confidence: str,
    expected_value: dict,
    risk_calibration_context: dict | None = None,
) -> str:
    risk_calibration_context = risk_calibration_context or {}
    if risk_calibration_context.get("force_observar"):
        return "observar"
    if expected_value["expected_value_usdt"] < 0:
        return "observar"
    if setup_grade in {"A", "B"} and risk_level != "alto" and confidence in {"alta", "media"}:
        return "simular"
    if setup_grade in {"B", "C"} and risk_level != "alto":
        return "simular con tamano prudente"
    return "observar"


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
        rules.append("Invalidar si el CVD Futures se mantiene contra la direccion propuesta.")
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
            "source": ENGINE_VERSION,
            "explanation": "Estima direccion sin premiar el ratio riesgo/beneficio. El R/R se usa en esperanza matematica, no para inflar probabilidad.",
        },
        {
            "key": "expected_value",
            "label": "Esperanza matematica",
            "value": f"{expected_value['label']} · {expected_value['expected_value_usdt']:+.2f} USDT",
            "score": layered_scores["expected_value_score"],
            "bias": "favorable" if expected_value["expected_value_usdt"] > 0 else "desfavorable",
            "source": "Probabilidad, R/R, comisiones, spread, slippage y funding estimados",
            "explanation": "Calcula si la operacion compensa economicamente despues de costes aproximados. Puede ser positiva aunque la probabilidad no sea alta.",
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
        return 0.018 if cvd_ratio > 0.12 else -0.018 if cvd_ratio < -0.12 else 0
    return 0.018 if cvd_ratio < -0.12 else -0.018 if cvd_ratio > 0.12 else 0


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
        f"Apalancamiento x{proposal.leverage:g}: solo afecta exposicion/PnL; no modifica la probabilidad ni la recomendacion del setup."
    )
    technical_text = (
        f"La capa tecnica queda {technical_rating['label']} ({technical_rating['score']}/100): "
        f"aporta {technical_rating['direction_bias']:+.1%} a la direccion, "
        f"penaliza timing {technical_rating['entry_timing_penalty']:.1%} y barreras {technical_rating['barrier_penalty']:.1%}."
    )
    return (
        f"Lectura {direction} para {horizon_profile['label']} ({horizon_profile['duration']}): setup {setup_grade} con riesgo {risk_level}. "
        f"El motor {ENGINE_VERSION} estima TP en rango {probability_ranges['tp']['label']}, SL {probability_ranges['sl']['label']} y rango/sin resolver {probability_ranges['range']['label']}; "
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
        f"en Futures, CVD reciente {format_optional_number(cvd_ratio)}. "
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
            "explanation": f"Define que datos pesan mas en este analisis. Principales: {', '.join(horizon_profile['primary_timeframes'])}; confirmacion: {horizon_profile['confirmation_timeframe']}.",
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
            "source": "Binance Futures velas 5m, 15m, 1h, 4h, 1d y 1w",
            "explanation": "Compara EMAs en varios marcos temporales. Cuantos mas marcos acompanan, mas solida es la direccion; si varios van en contra, la entrada queda penalizada.",
        },
        {
            "key": "momentum",
            "label": f"Momentum RSI {tf_momentum.get('interval', horizon_profile.get('momentum_timeframe', '5m'))}",
            "value": f"{rsi_value:.1f}",
            "score": min(100, max(0, momentum_score)),
            "bias": "favorable" if 38 <= rsi_value <= 62 else "alerta" if rsi_value > 72 or rsi_value < 28 else "neutral",
            "source": f"Binance Futures velas {tf_momentum.get('interval', horizon_profile.get('momentum_timeframe', '5m'))}",
            "explanation": "El RSI mide velocidad del movimiento. Muy alto puede indicar compra extendida; muy bajo puede indicar venta extendida. No decide solo, ayuda a evitar entradas tarde.",
        },
        {
            "key": "volatility",
            "label": f"Volatilidad ATR {tf_volatility.get('interval', horizon_profile.get('volatility_timeframe', '5m'))}",
            "value": f"{tf_volatility['atr_pct']:.2f}%",
            "score": min(100, max(0, volatility_score)),
            "bias": "favorable" if volatility_score >= 60 else "alerta",
            "source": f"Binance Futures velas {tf_volatility.get('interval', horizon_profile.get('volatility_timeframe', '5m'))}",
            "explanation": "El ATR aproxima el movimiento normal reciente. Si el stop queda dentro de ese ruido, puede saltar aunque la idea no sea necesariamente mala.",
        },
        {
            "key": "order_book",
            "label": "Order book cercano",
            "value": f"{order_book['imbalance']:+.2f}",
            "score": min(100, max(0, imbalance_score)),
            "bias": "favorable" if (proposal.side == "long" and order_book["imbalance"] > 0.12) or (proposal.side == "short" and order_book["imbalance"] < -0.12) else "desfavorable" if abs(order_book["imbalance"]) > 0.12 else "neutral",
            "source": "Binance Futures order book top 20 niveles",
            "explanation": "Compara liquidez cercana en compras y ventas. No predice por si solo, pero muestra si la presion inmediata acompana o dificulta la entrada.",
        },
        {
            "key": "spread",
            "label": "Spread",
            "value": f"{order_book['spread_pct']:.4f}%",
            "score": min(100, max(0, liquidity_score)),
            "bias": "favorable" if liquidity_score >= 70 else "alerta",
            "source": "Binance Futures order book",
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
            "score": 50,
            "bias": "neutral",
            "source": "Parametros del usuario",
            "explanation": "El apalancamiento solo escala ganancia o perdida sobre margen. No modifica probabilidad, setup ni recomendacion del analisis.",
        },
        {
            "key": "levels",
            "label": "Soporte/resistencia 1h",
            "value": f"{level_distance:.2f}%" if level_distance is not None else "no disponible",
            "score": min(100, max(0, level_score)),
            "bias": "alerta" if level_score <= 35 else "neutral" if level_score <= 60 else "favorable",
            "source": "Binance Futures velas 1h",
            "explanation": "Detecta el nivel tecnico cercano mas relevante. Para longs importa la resistencia superior; para shorts, el soporte inferior. Si esta demasiado cerca, limita recorrido.",
        },
        {
            "key": "cvd_futures",
            "label": "CVD Futures reciente",
            "value": format_optional_number(cvd_ratio),
            "score": min(100, max(0, cvd_score)),
            "bias": "favorable" if cvd_score >= 60 else "desfavorable" if cvd_score <= 40 else "neutral",
            "source": "Binance Futures aggregate trades",
            "explanation": "Aproxima compras agresivas menos ventas agresivas. Si el CVD acompana la direccion, hay flujo real; si contradice, la entrada tiene menos confirmacion.",
        },
        {
            "key": "market_24h",
            "label": "Movimiento 24h",
            "value": f"{ticker_24h['price_change_pct']:+.2f}%",
            "score": score_to_percent(ticker_24h["price_change_pct"], -5, 5),
            "bias": "contexto",
            "source": "Binance Futures ticker 24h",
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
