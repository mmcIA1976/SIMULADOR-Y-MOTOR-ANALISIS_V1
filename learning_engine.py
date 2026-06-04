from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from analysis_engine import (
    TradeProposal,
    annotate_expected_value_threshold,
    build_probability_ranges,
    calculate_expected_value,
    decision_from_context,
    grade_from_scores,
    score_to_percent,
)
from db import connect, row_to_dict


MIN_CASES_TO_ADJUST = 30
MIN_CASES_FOR_STRONG_SIGNAL = 100
MAX_ADJUSTMENT = 0.06
MIN_EFFECTIVE_ADJUSTMENT = 0.005
HIGH_SIGNAL_PATTERN_TAGS = {
    "cvd_price_absorption_warning",
    "cvd_price_confirmation",
    "cvd_price_against_plan",
    "price_moves_without_cvd_confirmation",
    "futures_oi_confirmation",
    "futures_oi_contradiction",
    "futures_flow_without_oi_confirmation",
    "futures_taker_against_without_oi_confirmation",
    "derivatives_funding_saturation",
    "derivatives_crowding_risk",
    "derivatives_oi_price_warning",
    "liquidity_heavier_toward_target",
    "liquidity_heavier_toward_stop",
    "microprice_bid_pressure",
    "microprice_ask_pressure",
    "book_slope_bid_dense",
    "book_slope_ask_dense",
    "microstructure_supports_plan",
    "microstructure_against_plan",
    "spot_favorable_futures_against",
    "mixed_signals_contradiction",
    "higher_timeframe_against",
    "stop_inside_recent_noise",
}


@dataclass(frozen=True)
class LearnedCase:
    operation_id: int
    scope: str
    setup_outcome: str
    behavior_outcome: str
    symbol: str
    side: str
    time_horizon: str
    leverage: float
    setup_grade: str | None
    risk_level: str | None
    market_regime: str | None
    technical_label: str | None
    technical_score_bucket: str | None
    direction_score_bucket: str | None
    confidence_score_bucket: str | None
    derivatives_period: str | None
    levels_timeframe: str | None
    pattern_tags: tuple[str, ...]
    post_horizon_label: str | None
    timing_lesson: str | None
    main_failure_axis: str | None
    diagnostic_flags: tuple[str, ...]


def apply_learning_modifier(user_id: int, proposal: TradeProposal, analysis: dict) -> dict:
    cases = load_learned_cases(user_id)
    matching_cases = filter_similar_cases(cases, proposal, analysis)
    setup_cases = [case for case in matching_cases if case.setup_outcome in {"plan_success", "plan_failure"}]
    behavior_cases = [case for case in matching_cases if case.behavior_outcome != "none"]

    failures = sum(1 for case in setup_cases if case.setup_outcome == "plan_failure")
    successes = sum(1 for case in setup_cases if case.setup_outcome == "plan_success")
    pending = sum(1 for case in matching_cases if case.setup_outcome == "pending")
    expired = sum(1 for case in matching_cases if case.setup_outcome == "expired")
    tp_after_horizon = sum(1 for case in matching_cases if case.post_horizon_label == "tp_after_horizon")
    sl_after_horizon = sum(1 for case in matching_cases if case.post_horizon_label == "sl_after_horizon")

    suggested_adjustment = calculate_probability_adjustment(successes, failures)
    adjustment = suggested_adjustment if abs(suggested_adjustment) >= MIN_EFFECTIVE_ADJUSTMENT else 0
    if adjustment:
        apply_calibrated_learning_adjustment(analysis, proposal, adjustment)

    learning_summary = build_learning_summary(
        matching_cases=matching_cases,
        setup_cases=setup_cases,
        behavior_cases=behavior_cases,
        successes=successes,
        failures=failures,
        pending=pending,
        expired=expired,
        tp_after_horizon=tp_after_horizon,
        sl_after_horizon=sl_after_horizon,
        adjustment=adjustment,
        suggested_adjustment=suggested_adjustment,
    )
    analysis["learning_adjustment"] = learning_summary
    analysis["snapshot"]["learning_adjustment"] = learning_summary

    if adjustment < 0:
        analysis["alerts"].append(
            f"Aprendizaje: operaciones similares han fallado mas de lo que sugeria el analisis inicial ({failures}/{len(setup_cases)} planes perdedores)."
        )
    elif adjustment > 0:
        analysis["reasons"].append(
            f"Aprendizaje: operaciones similares han funcionado mejor de lo esperado ({successes}/{len(setup_cases)} planes ganadores)."
        )

    if learning_summary["manual_close_pattern"] != "sin_senal":
        analysis["alerts"].append(learning_summary["manual_close_explanation"])

    if adjustment:
        analysis["plain_summary"] = (
            f"{analysis['plain_summary']} Tras aplicar aprendizaje, la lectura final queda en "
            f"TP {analysis['probability_ranges']['tp']['label']}, SL {analysis['probability_ranges']['sl']['label']} "
            f"y EV {analysis['expected_value']['label']} ({analysis['expected_value']['expected_value_usdt']:+.2f} USDT). "
            f"{learning_summary['plain_text']}"
        )
    else:
        analysis["plain_summary"] = f"{analysis['plain_summary']} {learning_summary['plain_text']}"
    return analysis


def apply_calibrated_learning_adjustment(analysis: dict, proposal: TradeProposal, adjustment: float) -> None:
    snapshot = analysis.get("snapshot", {})
    score_components = snapshot.get("score_components") if isinstance(snapshot.get("score_components"), dict) else {}
    layered_scores = dict(analysis.get("layered_scores", {}))
    range_probability = float(analysis.get("range_probability", 0.08))
    tp_probability = clamp_probability(float(analysis["tp_probability"]) + adjustment)
    sl_probability = max(0.05, 1 - tp_probability - range_probability)
    contradiction_penalty = float(score_components.get("contradiction_penalty") or 0)
    risk_distance = float(snapshot.get("risk_distance_pct") or 0)
    reward_distance = float(snapshot.get("reward_distance_pct") or 0)
    spread_pct = float((snapshot.get("order_book") or {}).get("spread_pct") or 0)
    funding_rate_pct = (snapshot.get("derivatives") or {}).get("funding_rate_pct")
    probability_ranges = build_probability_ranges(tp_probability, sl_probability, range_probability, contradiction_penalty)
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
    expected_value = annotate_expected_value_threshold(expected_value, analysis["risk_level"], analysis.get("confidence", "media-baja"))
    layered_scores["direction_score"] = round(tp_probability * 100)
    layered_scores["expected_value_score"] = score_to_percent(expected_value["expected_value_pct_margin"], -8, 12)
    risk_score = safe_float(snapshot.get("risk_score"), risk_score_from_level(analysis["risk_level"]))
    setup_grade = grade_from_scores(tp_probability, risk_score, layered_scores["expected_value_score"])
    confidence = analysis.get("confidence", "media-baja")
    training_decision = decision_from_context(setup_grade, analysis["risk_level"], confidence, expected_value)

    analysis["tp_probability"] = round(tp_probability, 4)
    analysis["sl_probability"] = round(sl_probability, 4)
    analysis["probability_ranges"] = probability_ranges
    analysis["expected_value"] = expected_value
    analysis["layered_scores"] = layered_scores
    analysis["setup_grade"] = setup_grade
    analysis["training_decision"] = training_decision
    analysis["snapshot"]["tp_probability"] = round(tp_probability, 4)
    analysis["snapshot"]["sl_probability"] = round(sl_probability, 4)
    analysis["snapshot"]["probability_ranges"] = probability_ranges
    analysis["snapshot"]["expected_value"] = expected_value
    analysis["snapshot"]["layered_scores"] = layered_scores


def safe_float(value: object, fallback: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def risk_score_from_level(risk_level: str | None) -> float:
    if risk_level == "alto":
        return 0.42
    if risk_level == "medio-alto":
        return 0.24
    if risk_level == "medio":
        return 0.12
    return 0.08


def load_learned_cases(user_id: int) -> list[LearnedCase]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT
                o.id, o.user_id, o.symbol, o.side, o.time_horizon, o.leverage, o.stop_loss, o.take_profit,
                o.status, o.closed_at, o.close_reason, o.final_pnl, o.observation_status,
                r.setup_grade, r.risk_level, r.snapshot_json,
                le.plan_result AS evaluation_plan_result,
                le.structured_json AS evaluation_structured_json
            FROM operations o
            LEFT JOIN recommendations r ON r.id = (
                SELECT r2.id
                FROM recommendations r2
                WHERE r2.operation_id = o.id
                ORDER BY r2.created_at DESC, r2.id DESC
                LIMIT 1
            )
            LEFT JOIN learning_evaluations le ON le.operation_id = o.id
            WHERE o.status = 'CLOSED'
            ORDER BY o.closed_at DESC, o.id DESC
            LIMIT 250
            """
        ).fetchall()
        cases = []
        for row in rows:
            operation = row_to_dict(row)
            ticks = db.execute(
                """
                SELECT price, captured_at
                FROM price_ticks
                WHERE operation_id = ? AND captured_at >= COALESCE(?, captured_at)
                ORDER BY captured_at ASC
                """,
                (operation["id"], operation["closed_at"]),
            ).fetchall()
            cases.append(
                build_case(
                    operation=operation,
                    ticks=[row_to_dict(tick) for tick in ticks],
                    scope="usuario" if operation["user_id"] == user_id else "global",
                )
            )
    return cases


def build_case(operation: dict, ticks: list[dict], scope: str) -> LearnedCase:
    close_reason = operation["close_reason"]
    setup_outcome = "pending"
    behavior_outcome = "none"
    evaluation_plan_result = operation.get("evaluation_plan_result")
    structured = parse_snapshot(operation.get("evaluation_structured_json"))
    post_horizon = structured.get("post_horizon_outcome") if isinstance(structured.get("post_horizon_outcome"), dict) else {}
    post_horizon_label = post_horizon.get("label")
    timing_lesson = structured.get("timing_lesson") if isinstance(structured.get("timing_lesson"), str) else None
    diagnostics = structured.get("engine_diagnostics") if isinstance(structured.get("engine_diagnostics"), dict) else {}
    diagnostic_flags = diagnostics.get("diagnostic_flags") if isinstance(diagnostics.get("diagnostic_flags"), list) else []

    if evaluation_plan_result in {"plan_success", "plan_failure", "plan_expired", "manual_before_resolution", "plan_unresolved"}:
        if evaluation_plan_result == "plan_success":
            setup_outcome = "plan_success"
        elif evaluation_plan_result == "plan_failure":
            setup_outcome = "plan_failure"
        elif evaluation_plan_result == "plan_expired":
            setup_outcome = "expired"
        elif evaluation_plan_result == "manual_before_resolution":
            setup_outcome = "pending"
            behavior_outcome = "manual_pending"
        else:
            setup_outcome = "pending"
    elif close_reason == "take_profit":
        setup_outcome = "plan_success"
    elif close_reason == "stop_loss":
        setup_outcome = "plan_failure"
    elif close_reason in {"manual", "cut_loss", "take_partial", "emotion", "invalidated"}:
        counterfactual = counterfactual_plan_result(operation, ticks)
        setup_outcome = counterfactual
        if counterfactual == "plan_failure":
            behavior_outcome = "manual_favorable"
        elif counterfactual == "plan_success":
            behavior_outcome = "manual_unfavorable"
        else:
            behavior_outcome = "manual_pending"
    snapshot = parse_snapshot(operation.get("snapshot_json"))
    pattern = pattern_from_snapshot(snapshot)

    return LearnedCase(
        operation_id=int(operation["id"]),
        scope=scope,
        setup_outcome=setup_outcome,
        behavior_outcome=behavior_outcome,
        symbol=operation["symbol"],
        side=operation["side"],
        time_horizon=operation.get("time_horizon") or "intraday_short",
        leverage=float(operation["leverage"]),
        setup_grade=operation["setup_grade"],
        risk_level=operation["risk_level"],
        market_regime=pattern["market_regime"],
        technical_label=pattern["technical_label"],
        technical_score_bucket=pattern["technical_score_bucket"],
        direction_score_bucket=pattern["direction_score_bucket"],
        confidence_score_bucket=pattern["confidence_score_bucket"],
        derivatives_period=pattern["derivatives_period"],
        levels_timeframe=pattern["levels_timeframe"],
        pattern_tags=tuple(pattern["pattern_tags"]),
        post_horizon_label=post_horizon_label,
        timing_lesson=timing_lesson,
        main_failure_axis=diagnostics.get("main_failure_axis"),
        diagnostic_flags=tuple(str(flag) for flag in diagnostic_flags if flag),
    )


def parse_snapshot(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def pattern_from_snapshot(snapshot: dict) -> dict:
    technical = snapshot.get("technical_rating") if isinstance(snapshot.get("technical_rating"), dict) else {}
    scores = snapshot.get("layered_scores") if isinstance(snapshot.get("layered_scores"), dict) else {}
    regime = snapshot.get("market_regime") if isinstance(snapshot.get("market_regime"), dict) else {}
    timeframes = snapshot.get("analysis_timeframes") if isinstance(snapshot.get("analysis_timeframes"), dict) else {}
    raw_tags = snapshot.get("pattern_tags") if isinstance(snapshot.get("pattern_tags"), list) else []
    pattern_tags = tuple(sorted({str(tag) for tag in raw_tags if tag}))
    return {
        "market_regime": regime.get("name"),
        "technical_label": technical.get("label"),
        "technical_score_bucket": score_bucket(technical.get("score")),
        "direction_score_bucket": score_bucket(scores.get("direction_score")),
        "confidence_score_bucket": score_bucket(scores.get("confidence_score")),
        "derivatives_period": timeframes.get("derivatives_period"),
        "levels_timeframe": timeframes.get("levels"),
        "pattern_tags": pattern_tags,
    }


def score_bucket(value: object) -> str | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score >= 65:
        return "alto"
    if score <= 40:
        return "bajo"
    return "medio"


def counterfactual_plan_result(operation: dict, ticks: list[dict]) -> str:
    for tick in ticks:
        price = float(tick["price"])
        if operation["side"] == "long":
            if price <= float(operation["stop_loss"]):
                return "plan_failure"
            if price >= float(operation["take_profit"]):
                return "plan_success"
        else:
            if price >= float(operation["stop_loss"]):
                return "plan_failure"
            if price <= float(operation["take_profit"]):
                return "plan_success"
    return "pending"


def filter_similar_cases(cases: Iterable[LearnedCase], proposal: TradeProposal, analysis: dict) -> list[LearnedCase]:
    similar = []
    pattern = pattern_from_snapshot(analysis.get("snapshot", {}))
    current_high_signal_tags = high_signal_tags(pattern["pattern_tags"])
    for case in cases:
        if case.symbol != proposal.symbol or case.side != proposal.side:
            continue
        if case.time_horizon != proposal.time_horizon:
            continue
        if abs(case.leverage - proposal.leverage) > 3:
            continue
        if case.risk_level and case.risk_level != analysis["risk_level"]:
            continue
        if pattern["technical_label"] and case.technical_label and pattern["technical_label"] != case.technical_label:
            continue
        if pattern["derivatives_period"] and case.derivatives_period and pattern["derivatives_period"] != case.derivatives_period:
            continue
        if pattern["levels_timeframe"] and case.levels_timeframe and pattern["levels_timeframe"] != case.levels_timeframe:
            continue
        if pattern["market_regime"] and case.market_regime and pattern["market_regime"] != case.market_regime:
            continue
        case_high_signal_tags = high_signal_tags(case.pattern_tags)
        if current_high_signal_tags and case_high_signal_tags and not current_high_signal_tags.intersection(case_high_signal_tags):
            continue
        similar.append(case)
    return similar


def high_signal_tags(tags: Iterable[str]) -> set[str]:
    return {tag for tag in tags if tag in HIGH_SIGNAL_PATTERN_TAGS}


def calculate_probability_adjustment(successes: int, failures: int) -> float:
    total = successes + failures
    if total < MIN_CASES_TO_ADJUST:
        return 0
    observed_success_rate = successes / total
    raw_adjustment = (observed_success_rate - 0.5) * 0.12
    confidence_scale = min(1, total / MIN_CASES_FOR_STRONG_SIGNAL)
    return max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, raw_adjustment * confidence_scale))


def build_learning_summary(
    matching_cases: list[LearnedCase],
    setup_cases: list[LearnedCase],
    behavior_cases: list[LearnedCase],
    successes: int,
    failures: int,
    pending: int,
    expired: int,
    tp_after_horizon: int,
    sl_after_horizon: int,
    adjustment: float,
    suggested_adjustment: float,
) -> dict:
    manual_favorable = sum(1 for case in behavior_cases if case.behavior_outcome == "manual_favorable")
    manual_unfavorable = sum(1 for case in behavior_cases if case.behavior_outcome == "manual_unfavorable")
    manual_pending = sum(1 for case in behavior_cases if case.behavior_outcome == "manual_pending")

    if manual_pending and not manual_unfavorable:
        manual_pattern = "pendiente"
        manual_explanation = "Aprendizaje emocional: hay cierres manuales todavia pendientes de validar contra el plan original."
    elif manual_favorable > manual_unfavorable:
        manual_pattern = "proteccion_util"
        manual_explanation = "Aprendizaje emocional: algunos cierres manuales evitaron un resultado peor que mantener el plan."
    elif manual_unfavorable > manual_favorable:
        manual_pattern = "salida_prematura"
        manual_explanation = "Aprendizaje emocional: algunos cierres manuales salieron peor que mantener el plan."
    else:
        manual_pattern = "sin_senal"
        manual_explanation = ""

    if len(setup_cases) == 0:
        plain_text = "Aprendizaje: aun no hay suficientes operaciones resueltas similares para modificar la probabilidad."
    elif len(setup_cases) < MIN_CASES_TO_ADJUST:
        plain_text = (
            f"Aprendizaje prudente: hay {len(setup_cases)} operaciones similares resueltas "
            f"({successes} ganadoras / {failures} perdedoras), pero se necesitan al menos "
            f"{MIN_CASES_TO_ADJUST} antes de modificar probabilidades."
        )
    elif adjustment < 0:
        plain_text = (
            f"Aprendizaje: en {len(setup_cases)} operaciones similares resueltas, {failures} terminaron contra el plan; "
            f"se calibra prudentemente la probabilidad a la baja."
        )
    elif adjustment > 0:
        plain_text = (
            f"Aprendizaje: en {len(setup_cases)} operaciones similares resueltas, {successes} terminaron a favor del plan; "
            f"se calibra prudentemente la probabilidad al alza."
        )
    elif suggested_adjustment:
        plain_text = "Aprendizaje calibrado: hay muestra suficiente, pero el ajuste sugerido es demasiado pequeno para modificar la probabilidad."
    else:
        plain_text = "Aprendizaje calibrado: hay muestra suficiente, pero el resultado historico no justifica mover la probabilidad."

    timing_text = build_timing_summary(tp_after_horizon, sl_after_horizon)
    if timing_text:
        plain_text = f"{plain_text} {timing_text}"

    return {
        "engine": "learning-calibration-v0.4",
        "matching_cases": len(matching_cases),
        "resolved_plan_cases": len(setup_cases),
        "plan_successes": successes,
        "plan_failures": failures,
        "pending_cases": pending,
        "expired_cases": expired,
        "tp_after_horizon_cases": tp_after_horizon,
        "sl_after_horizon_cases": sl_after_horizon,
        "minimum_cases_to_adjust": MIN_CASES_TO_ADJUST,
        "tp_probability_delta": round(adjustment, 4),
        "suggested_tp_probability_delta": round(suggested_adjustment, 4),
        "mode": "calibracion_prudente" if adjustment else "descriptivo_sin_ajuste",
        "calibration_applied": bool(adjustment),
        "manual_close_pattern": manual_pattern,
        "manual_close_favorable": manual_favorable,
        "manual_close_unfavorable": manual_unfavorable,
        "manual_close_pending": manual_pending,
        "manual_close_explanation": manual_explanation,
        "pattern_breakdown": build_pattern_breakdown(matching_cases),
        "plain_text": plain_text,
    }


def build_timing_summary(tp_after_horizon: int, sl_after_horizon: int) -> str:
    if tp_after_horizon and sl_after_horizon:
        return (
            f"Timing: {tp_after_horizon} casos similares llegaron a TP despues del horizonte y "
            f"{sl_after_horizon} llegaron a SL despues; conservar como senal de ajuste temporal, no de probabilidad directa."
        )
    if tp_after_horizon:
        return (
            f"Timing: {tp_after_horizon} casos similares llegaron a TP despues del horizonte; "
            "posible direccion correcta con ventana temporal corta."
        )
    if sl_after_horizon:
        return (
            f"Timing: {sl_after_horizon} casos similares llegaron a SL despues del horizonte; "
            "posible riesgo tardio o plan demasiado largo."
        )
    return ""


def build_pattern_breakdown(cases: list[LearnedCase]) -> dict:
    resolved = [case for case in cases if case.setup_outcome in {"plan_success", "plan_failure"}]
    expired = [case for case in cases if case.setup_outcome == "expired"]
    post_horizon_cases = [case for case in cases if case.post_horizon_label]
    if not resolved:
        return {
            "available": False,
            "message": "Aun no hay patron temporal resuelto suficiente.",
            "expired_cases": len(expired),
            "post_horizon_outcomes": frequency([case.post_horizon_label for case in post_horizon_cases]),
            "main_failure_axes": frequency([case.main_failure_axis for case in cases]),
            "diagnostic_flags": frequency([flag for case in cases for flag in case.diagnostic_flags]),
        }
    successes = sum(1 for case in resolved if case.setup_outcome == "plan_success")
    failures = sum(1 for case in resolved if case.setup_outcome == "plan_failure")
    return {
        "available": True,
        "resolved_cases": len(resolved),
        "successes": successes,
        "failures": failures,
        "success_rate": round(successes / len(resolved), 4),
        "technical_labels": frequency([case.technical_label for case in resolved]),
        "market_regimes": frequency([case.market_regime for case in resolved]),
        "derivatives_periods": frequency([case.derivatives_period for case in resolved]),
        "levels_timeframes": frequency([case.levels_timeframe for case in resolved]),
        "pattern_tags": frequency([tag for case in resolved for tag in case.pattern_tags]),
        "high_signal_pattern_tags": frequency([tag for case in resolved for tag in high_signal_tags(case.pattern_tags)]),
        "expired_cases": len(expired),
        "post_horizon_outcomes": frequency([case.post_horizon_label for case in post_horizon_cases]),
        "timing_lessons": frequency([case.timing_lesson for case in post_horizon_cases]),
        "main_failure_axes": frequency([case.main_failure_axis for case in cases]),
        "diagnostic_flags": frequency([flag for case in cases for flag in case.diagnostic_flags]),
    }


def frequency(values: list[str | None]) -> dict:
    result: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        result[value] = result.get(value, 0) + 1
    return result


def clamp_probability(value: float) -> float:
    return min(0.78, max(0.22, value))
