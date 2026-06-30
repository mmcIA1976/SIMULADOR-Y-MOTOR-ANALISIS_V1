from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from analysis_engine import TradeProposal
from db import connect, row_to_dict


MIN_CASES_TO_ADJUST = 30
MIN_CASES_FOR_STRONG_SIGNAL = 100
MAX_ADJUSTMENT = 0.06
MANUAL_CLOSE_REASONS = {"manual", "cut_loss", "take_partial", "emotion", "invalidated"}


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
    fibonacci_bias: str | None
    fibonacci_entry_zone: str | None
    fibonacci_score_bucket: str | None
    entry_order_type: str | None
    zone_reaction_bias: str | None
    zone_sweep_risk: str | None
    zone_confluence_bucket: str | None
    zone_probability_adjustment_bucket: str | None
    derivatives_period: str | None
    levels_timeframe: str | None


def apply_learning_modifier(user_id: int, proposal: TradeProposal, analysis: dict) -> dict:
    cases = load_learned_cases(user_id)
    matching_cases = filter_similar_cases(cases, proposal, analysis)
    setup_cases = [case for case in matching_cases if case.setup_outcome in {"plan_success", "plan_failure"}]
    behavior_cases = [case for case in matching_cases if case.behavior_outcome != "none"]

    failures = sum(1 for case in setup_cases if case.setup_outcome == "plan_failure")
    successes = sum(1 for case in setup_cases if case.setup_outcome == "plan_success")
    pending = sum(1 for case in matching_cases if case.setup_outcome == "pending")

    suggested_adjustment = calculate_probability_adjustment(successes, failures)
    adjustment = 0
    if adjustment:
        tp_probability = clamp_probability(analysis["tp_probability"] + adjustment)
        range_probability = analysis["range_probability"]
        sl_probability = max(0.05, 1 - tp_probability - range_probability)
        analysis["tp_probability"] = round(tp_probability, 4)
        analysis["sl_probability"] = round(sl_probability, 4)
        analysis["setup_grade"] = grade_from_probability(tp_probability)
        analysis["training_decision"] = decision_from_grade_and_risk(analysis["setup_grade"], analysis["risk_level"])

    learning_summary = build_learning_summary(
        matching_cases=matching_cases,
        setup_cases=setup_cases,
        behavior_cases=behavior_cases,
        successes=successes,
        failures=failures,
        pending=pending,
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

    analysis["plain_summary"] = f"{analysis['plain_summary']} {learning_summary['plain_text']}"
    return analysis


def load_learned_cases(user_id: int) -> list[LearnedCase]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT
                o.id, o.user_id, o.symbol, o.side, o.time_horizon, o.leverage, o.stop_loss, o.take_profit,
                o.status, o.closed_at, o.close_reason, o.final_pnl, o.observation_status,
                r.setup_grade, r.risk_level, r.snapshot_json
            FROM operations o
            LEFT JOIN recommendations r ON r.id = (
                SELECT r2.id
                FROM recommendations r2
                WHERE r2.operation_id = o.id
                ORDER BY r2.created_at DESC, r2.id DESC
                LIMIT 1
            )
            WHERE o.status = 'CLOSED'
            ORDER BY o.closed_at DESC, o.id DESC
            LIMIT 250
            """
        ).fetchall()
        cases = []
        for row in rows:
            operation = row_to_dict(row)
            ticks = []
            if operation["close_reason"] in MANUAL_CLOSE_REASONS:
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

    if close_reason == "take_profit":
        setup_outcome = "plan_success"
    elif close_reason == "stop_loss":
        setup_outcome = "plan_failure"
    elif close_reason in MANUAL_CLOSE_REASONS:
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
        fibonacci_bias=pattern["fibonacci_bias"],
        fibonacci_entry_zone=pattern["fibonacci_entry_zone"],
        fibonacci_score_bucket=pattern["fibonacci_score_bucket"],
        entry_order_type=pattern["entry_order_type"],
        zone_reaction_bias=pattern["zone_reaction_bias"],
        zone_sweep_risk=pattern["zone_sweep_risk"],
        zone_confluence_bucket=pattern["zone_confluence_bucket"],
        zone_probability_adjustment_bucket=pattern["zone_probability_adjustment_bucket"],
        derivatives_period=pattern["derivatives_period"],
        levels_timeframe=pattern["levels_timeframe"],
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
    fibonacci = snapshot.get("fibonacci_context") if isinstance(snapshot.get("fibonacci_context"), dict) else {}
    entry_context = snapshot.get("entry_order_context") if isinstance(snapshot.get("entry_order_context"), dict) else {}
    zone = snapshot.get("zone_analysis") if isinstance(snapshot.get("zone_analysis"), dict) else {}
    zone_probability = snapshot.get("zone_probability_context") if isinstance(snapshot.get("zone_probability_context"), dict) else {}
    timeframes = snapshot.get("analysis_timeframes") if isinstance(snapshot.get("analysis_timeframes"), dict) else {}
    return {
        "market_regime": regime.get("name"),
        "technical_label": technical.get("label"),
        "technical_score_bucket": score_bucket(technical.get("score")),
        "direction_score_bucket": score_bucket(scores.get("direction_score")),
        "confidence_score_bucket": score_bucket(scores.get("confidence_score")),
        "fibonacci_bias": fibonacci.get("bias"),
        "fibonacci_entry_zone": fibonacci.get("entry_zone"),
        "fibonacci_score_bucket": score_bucket(fibonacci.get("score")),
        "entry_order_type": zone.get("entry_order_type") or entry_context.get("entry_order_type"),
        "zone_reaction_bias": zone.get("reaction_bias"),
        "zone_sweep_risk": zone.get("liquidity_sweep_risk"),
        "zone_confluence_bucket": score_bucket(zone.get("zone_confluence_score")),
        "zone_probability_adjustment_bucket": signed_bucket(zone_probability.get("probability_adjustment")),
        "derivatives_period": timeframes.get("derivatives_period"),
        "levels_timeframe": timeframes.get("levels"),
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


def signed_bucket(value: object) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0.003:
        return "positivo"
    if number < -0.003:
        return "negativo"
    return "neutral"


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
    for case in cases:
        if case.symbol != proposal.symbol or case.side != proposal.side:
            continue
        if case.time_horizon != proposal.time_horizon:
            continue
        if abs(case.leverage - proposal.leverage) > 3:
            continue
        if case.risk_level and case.risk_level != analysis["risk_level"]:
            continue
        pattern = pattern_from_snapshot(analysis.get("snapshot", {}))
        if pattern["technical_label"] and case.technical_label and pattern["technical_label"] != case.technical_label:
            continue
        if pattern["derivatives_period"] and case.derivatives_period and pattern["derivatives_period"] != case.derivatives_period:
            continue
        if pattern["levels_timeframe"] and case.levels_timeframe and pattern["levels_timeframe"] != case.levels_timeframe:
            continue
        if pattern["market_regime"] and case.market_regime and pattern["market_regime"] != case.market_regime:
            continue
        if pattern["fibonacci_bias"] and case.fibonacci_bias and pattern["fibonacci_bias"] != case.fibonacci_bias:
            continue
        if pattern["fibonacci_entry_zone"] and case.fibonacci_entry_zone and pattern["fibonacci_entry_zone"] != case.fibonacci_entry_zone:
            continue
        if pattern["entry_order_type"] and case.entry_order_type and pattern["entry_order_type"] != case.entry_order_type:
            continue
        if pattern["zone_reaction_bias"] and case.zone_reaction_bias and pattern["zone_reaction_bias"] != case.zone_reaction_bias:
            continue
        if pattern["zone_sweep_risk"] and case.zone_sweep_risk and pattern["zone_sweep_risk"] != case.zone_sweep_risk:
            continue
        if pattern["zone_confluence_bucket"] and case.zone_confluence_bucket and pattern["zone_confluence_bucket"] != case.zone_confluence_bucket:
            continue
        if pattern["zone_probability_adjustment_bucket"] and case.zone_probability_adjustment_bucket and pattern["zone_probability_adjustment_bucket"] != case.zone_probability_adjustment_bucket:
            continue
        similar.append(case)
    return similar


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
    elif suggested_adjustment < 0:
        plain_text = (
            f"Aprendizaje: en {len(setup_cases)} operaciones similares resueltas, {failures} terminaron contra el plan; "
            f"se sugiere revisar a la baja la probabilidad, pero no se modifica automaticamente."
        )
    elif suggested_adjustment > 0:
        plain_text = (
            f"Aprendizaje: en {len(setup_cases)} operaciones similares resueltas, {successes} terminaron a favor del plan; "
            f"se sugiere revisar al alza la probabilidad, pero no se modifica automaticamente."
        )
    else:
        plain_text = "Aprendizaje descriptivo: los casos similares no justifican ajuste; el motor no modifica pesos automaticamente."

    return {
        "engine": "learning-descriptive-v0.2",
        "matching_cases": len(matching_cases),
        "resolved_plan_cases": len(setup_cases),
        "plan_successes": successes,
        "plan_failures": failures,
        "pending_cases": pending,
        "minimum_cases_to_adjust": MIN_CASES_TO_ADJUST,
        "tp_probability_delta": round(adjustment, 4),
        "suggested_tp_probability_delta": round(suggested_adjustment, 4),
        "mode": "descriptivo_sin_ajuste_automatico",
        "manual_close_pattern": manual_pattern,
        "manual_close_favorable": manual_favorable,
        "manual_close_unfavorable": manual_unfavorable,
        "manual_close_pending": manual_pending,
        "manual_close_explanation": manual_explanation,
        "pattern_breakdown": build_pattern_breakdown(matching_cases),
        "plain_text": plain_text,
    }


def build_pattern_breakdown(cases: list[LearnedCase]) -> dict:
    resolved = [case for case in cases if case.setup_outcome in {"plan_success", "plan_failure"}]
    if not resolved:
        return {
            "available": False,
            "message": "Aun no hay patron temporal resuelto suficiente.",
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
        "fibonacci_biases": frequency([case.fibonacci_bias for case in resolved]),
        "fibonacci_entry_zones": frequency([case.fibonacci_entry_zone for case in resolved]),
        "entry_order_types": frequency([case.entry_order_type for case in resolved]),
        "zone_reaction_biases": frequency([case.zone_reaction_bias for case in resolved]),
        "zone_sweep_risks": frequency([case.zone_sweep_risk for case in resolved]),
        "zone_confluence_buckets": frequency([case.zone_confluence_bucket for case in resolved]),
        "zone_probability_adjustment_buckets": frequency([case.zone_probability_adjustment_bucket for case in resolved]),
        "derivatives_periods": frequency([case.derivatives_period for case in resolved]),
        "levels_timeframes": frequency([case.levels_timeframe for case in resolved]),
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


def grade_from_probability(tp_probability: float) -> str:
    if tp_probability >= 0.64:
        return "A"
    if tp_probability >= 0.54:
        return "B"
    if tp_probability >= 0.46:
        return "C"
    return "D"


def decision_from_grade_and_risk(setup_grade: str, risk_level: str) -> str:
    if setup_grade in {"A", "B"} and risk_level != "alto":
        return "simular"
    if setup_grade == "C":
        return "simular con ajustes"
    return "observar"
