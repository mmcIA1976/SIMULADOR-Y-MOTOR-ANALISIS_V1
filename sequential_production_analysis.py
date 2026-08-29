from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from liquidation_rule_runtime import (
    RULE_ID as LIQUIDATION_RULE_ID,
    evaluate_liquidation_rule_family,
)
from microstructure_rule_runtime import (
    evaluate_order_book_dynamics,
)
from multiscale_feature_runtime import STAGE_ORDER, STAGE_PROFILES
from sequential_production_runtime import build_production_probability_run
from empirical_temporal_engine import (
    ENGINE_VERSION,
    SCORING_VERSION,
    load_production_artifact,
)


ENGINE_FAMILY = "empirical_multiscale_first_touch"
OWNER_ACTIVATION = "owner_explicit_empirical_multiscale_v0.9_2026-08-14"
STRUCTURAL_LEVEL_RULE_ID = "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
FIBONACCI_RULE_ID = "LIB-CAND-FIBONACCI-DISTANCE-001"
AVAILABLE_TRACE_STATUSES = {
    "evaluated",
    "evaluated_shadow",
    "partially_evaluated_shadow",
}
HORIZON_LABELS = {
    "intraday_short": "Intradía corto · hasta 4 h",
    "intraday_wide": "Intradía medio · hasta 24 h",
    "short_swing": "Intradía largo · hasta 7 días",
}
HORIZON_VALIDATION_NOTES = {
    "intraday_short": (
        "Mejora log-loss fuera de muestra; Brier final ligeramente peor que la referencia."
    ),
    "intraday_wide": (
        "Mejora log-loss y Brier fuera de muestra en rule-test y periodo final."
    ),
    "short_swing": (
        "Validación final prácticamente equivalente a la referencia; use el intervalo del 95%."
    ),
}


class NewEngineAnalysisError(RuntimeError):
    def __init__(self, code: str, details: dict | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _probability_label(value: float) -> str:
    if 0.0 < value < 0.001:
        return "<0.1%"
    if 0.999 < value < 1.0:
        return ">99.9%"
    return f"{value * 100:.1f}%"


def _probability_ranges(probability_result: dict) -> dict:
    source = probability_result["probability_ranges_95pct"]
    mapping = {
        "tp": "tp_first_within_horizon",
        "sl": "sl_first_within_horizon",
        "range": "neither_barrier_before_expiry",
    }
    return {
        name: {
            **source[class_name],
            "label": (
                f"{_probability_label(float(source[class_name]['low']))}–"
                f"{_probability_label(float(source[class_name]['high']))}"
            ),
            "meaning": "intervalo empírico de incertidumbre del 95%",
        }
        for name, class_name in mapping.items()
    }


def _geometry(proposal: Any) -> dict:
    entry = float(proposal.entry)
    tp_move = abs(float(proposal.take_profit) / entry - 1.0)
    sl_move = abs(float(proposal.stop_loss) / entry - 1.0)
    leverage = float(proposal.leverage)
    return {
        "risk_reward_ratio": tp_move / sl_move if sl_move > 0 else None,
        "margin_risk_pct": sl_move * leverage * 100.0,
        "margin_reward_pct": tp_move * leverage * 100.0,
        "tp_distance_pct": tp_move * 100.0,
        "sl_distance_pct": sl_move * 100.0,
    }


def attach_liquidation_observation(
    run: dict,
    proposal: Any,
    *,
    context_loader: Callable[..., dict] | None,
    context_market_price: float | None,
    analysis_at: str,
) -> tuple[dict, dict]:
    """Attach one compact, probability-neutral heatmap trace per stage.

    The provider is queried once.  Its immutable pre-trade observation is then
    interpreted against each cumulative horizon using that stage's volatility.
    Missing, stale and unsupported observations remain explicit blocked traces
    and never block or alter the served empirical probabilities.
    """
    try:
        market_price = float(context_market_price)
    except (TypeError, ValueError, OverflowError):
        market_price = float(proposal.entry)
    if not math.isfinite(market_price) or market_price <= 0:
        market_price = float(proposal.entry)

    provider_requested = context_loader is not None
    if context_loader is None:
        context = {
            "available": False,
            "status": "not_configured",
            "reason": "liquidation_context_loader_not_configured",
        }
    else:
        try:
            loaded = context_loader(
                str(proposal.symbol).upper(),
                market_price,
            )
            context = loaded if isinstance(loaded, dict) else {
                "available": False,
                "status": "unavailable",
                "reason": "invalid_liquidation_context_payload",
            }
        except Exception as exc:
            context = {
                "available": False,
                "status": "unavailable",
                "reason": "liquidation_context_request_failed",
                "error_type": type(exc).__name__,
            }

    live_context = {"liquidation_context": context}
    stage_contexts = run.get("stage_contexts") or {}
    stage_order = list(
        (run.get("details") or {}).get("stage_order")
        or stage_contexts
    )
    traces_by_stage = run.setdefault("stage_rule_traces", {})
    statuses = {}
    for horizon in stage_order:
        stage_context = stage_contexts.get(horizon) or {}
        result = evaluate_liquidation_rule_family(
            live_context,
            side=str(proposal.side).lower(),
            entry=float(proposal.entry),
            take_profit=float(proposal.take_profit),
            stop_loss=float(proposal.stop_loss),
            sigma_horizon=stage_context.get("context_sigma"),
            analysis_at=analysis_at,
            include_cluster_details=False,
        )
        trace = result["traces"][0]
        traces_by_stage.setdefault(horizon, []).append(trace)
        statuses[horizon] = trace.get("status")

    available = any(status == "evaluated_shadow" for status in statuses.values())
    summary = {
        "contract_version": "liquidation-observation-v0.1",
        "rule_id": LIQUIDATION_RULE_ID,
        "status": "evaluated_observation" if available else "unavailable_observation",
        "available": available,
        "provider": context.get("provider"),
        "scope": context.get("scope"),
        "provider_status": context.get("status"),
        "provider_reason": context.get("reason"),
        "as_of": context.get("as_of"),
        "age_seconds": context.get("age_seconds"),
        "supported_provider_symbols": ["BTC", "ETH", "SOL"],
        "provider_query_count": 1 if provider_requested else 0,
        "queried_once": provider_requested,
        "stored_payload": "compact_rule_outputs_without_cluster_arrays",
        "stage_statuses": statuses,
        "probability_effect": "none_observation_only",
    }
    return live_context, summary


def attach_order_book_observation(
    run: dict,
    proposal: Any,
    *,
    observation_loader: Callable[[str], dict | None] | None,
    analysis_at: str,
) -> tuple[dict, dict]:
    """Replace the placeholder book trace with one prospective worker snapshot."""
    provider_requested = observation_loader is not None
    if observation_loader is None:
        observation = {
            "available": False,
            "status": "not_configured",
            "reason": "order_book_observation_loader_not_configured",
        }
    else:
        try:
            loaded = observation_loader(str(proposal.symbol).upper())
            observation = loaded if isinstance(loaded, dict) else {
                "available": False,
                "status": "unavailable",
                "reason": "worker_order_book_observation_missing",
            }
        except Exception as exc:
            observation = {
                "available": False,
                "status": "unavailable",
                "reason": "worker_order_book_observation_request_failed",
                "error_type": type(exc).__name__,
            }

    stage_contexts = run.get("stage_contexts") or {}
    stage_order = list((run.get("details") or {}).get("stage_order") or stage_contexts)
    traces_by_stage = run.setdefault("stage_rule_traces", {})
    statuses: dict[str, dict[str, str | None]] = {}
    for horizon in stage_order:
        dynamic_trace = evaluate_order_book_dynamics(
            observation,
            side=str(proposal.side).lower(),
            analysis_at=analysis_at,
        )
        stage_traces = traces_by_stage.setdefault(horizon, [])
        stage_traces[:] = [
            trace
            for trace in stage_traces
            if str(trace.get("rule_id") or "")
            not in {
                "LIB-CAND-ORDERBOOK-IMBALANCE-001",
            }
        ]
        dynamic_trace["time_horizon_relevance"] = (
            "primary_microstructure"
            if horizon == "intraday_short"
            else "prospective_context_only"
        )
        stage_traces.append(dynamic_trace)
        statuses[horizon] = {
            "order_book": dynamic_trace.get("status"),
        }

    available = any(
        values.get("order_book") in {"evaluated_shadow", "partially_evaluated_shadow"}
        for values in statuses.values()
    )
    summary = {
        "contract_version": "order-book-observation-attachment-v0.1",
        "rule_ids": ["LIB-CAND-ORDERBOOK-IMBALANCE-001"],
        "status": "evaluated_observation" if available else "unavailable_observation",
        "available": available,
        "provider": observation.get("source"),
        "provider_status": observation.get("status"),
        "provider_reason": observation.get("state_reason") or observation.get("reason"),
        "captured_at": observation.get("captured_at"),
        "age_seconds": observation.get("age_seconds"),
        "sample_count": observation.get("sample_count"),
        "window_observed_seconds": observation.get("window_observed_seconds"),
        "provider_query_count": 1 if provider_requested else 0,
        "queried_once": provider_requested,
        "stored_payload": "compact_dynamics_without_raw_depth_or_trades",
        "stage_statuses": statuses,
        "probability_effect": "none_observation_only",
    }
    return {"order_book_observation": observation}, summary


def _temporal_profile(time_horizon: str, artifact: dict, stages: list[str]) -> dict:
    return {
        "version": ENGINE_VERSION,
        "role": "only_production_engine",
        "mutation": "frozen",
        "time_horizon": time_horizon,
        "horizon_seconds": STAGE_PROFILES[time_horizon]["horizon_seconds"],
        "horizon_label": HORIZON_LABELS[time_horizon],
        "confidence": "estimación empírica con intervalo del 95%",
        "validation_note": HORIZON_VALIDATION_NOTES[time_horizon],
        "method": "historical_analog_exact_first_touch",
        "artifact_id": artifact["artifact_id"],
        "artifact_sha256": artifact["artifact_sha256"],
        "single_engine": True,
        "parallel_probability_engines": 0,
        "executed_stages": stages,
        "stage_inheritance": {
            horizon: list(STAGE_ORDER[: index + 1])
            for index, horizon in enumerate(stages)
        },
        "later_stages_only_receive_survivors": True,
        "automatic_weight_updates": False,
        "production_effect": "served",
    }


def _analysis_stamp(
    time_horizon: str,
    *,
    request_received_at: datetime,
    effective_analysis_at: datetime | None,
) -> dict:
    analysis_at = effective_analysis_at or datetime.now(timezone.utc)
    if analysis_at.tzinfo is None or analysis_at.utcoffset() is None:
        raise NewEngineAnalysisError("analysis_timestamp_must_be_timezone_aware")
    analysis_at = analysis_at.astimezone(timezone.utc)
    horizon_seconds = int(STAGE_PROFILES[time_horizon]["horizon_seconds"])
    expires_at = datetime.fromtimestamp(
        analysis_at.timestamp() + horizon_seconds, tz=timezone.utc
    )
    return {
        "request_received_at": request_received_at.isoformat(),
        "analysis_at": analysis_at.isoformat(),
        "data_cutoff_at": analysis_at.isoformat(),
        "data_cutoff_policy": "closed_multiscale_market_data_at_analysis_time_v0.9",
        "evaluation_horizon_seconds": horizon_seconds,
        "evaluation_expires_at": expires_at.isoformat(),
        "evaluation_horizon_policy": "nested_conditional_stage_read_v0.9",
    }


def _rule_available_in_all_stages(
    stage_rule_traces: dict,
    stages: list[str],
    rule_id: str,
) -> bool:
    """Report availability only when the rule produced data in every stage."""
    if not stages:
        return False
    for horizon in stages:
        traces = stage_rule_traces.get(horizon) or []
        matching = next(
            (
                trace
                for trace in traces
                if isinstance(trace, dict)
                and str(trace.get("rule_id") or "") == rule_id
            ),
            None,
        )
        if (
            matching is None
            or matching.get("status") not in AVAILABLE_TRACE_STATUSES
            or not isinstance(matching.get("outputs"), dict)
            or not matching["outputs"]
        ):
            return False
    return True


def _analysis_availability(
    run: dict,
    proposal: Any,
    stages: list[str],
    *,
    liquidation_available: bool,
    order_book_available: bool,
) -> dict[str, bool]:
    """Build the public source summary from the evidence actually produced."""
    stage_contexts = run.get("stage_contexts") or {}
    stage_rule_traces = run.get("stage_rule_traces") or {}
    try:
        entry = float(proposal.entry)
        futures_price_available = math.isfinite(entry) and entry > 0
    except (TypeError, ValueError, OverflowError):
        futures_price_available = False
    futures_klines_available = bool(stages) and all(
        horizon in stage_contexts for horizon in stages
    )
    return {
        "futures_price": futures_price_available,
        "futures_klines": futures_klines_available,
        "multiscale_5m": "intraday_short" in stages,
        "multiscale_1h": "intraday_wide" in stages,
        "multiscale_6h": "short_swing" in stages,
        "fibonacci": _rule_available_in_all_stages(
            stage_rule_traces,
            stages,
            FIBONACCI_RULE_ID,
        ),
        "structural_levels": _rule_available_in_all_stages(
            stage_rule_traces,
            stages,
            STRUCTURAL_LEVEL_RULE_ID,
        ),
        "liquidation_heatmap": bool(liquidation_available),
        "order_book_dynamics": bool(order_book_available),
    }


def _explained_metrics(probability_result: dict) -> list[dict]:
    metrics = []
    for trace in probability_result["stage_traces"]:
        conditional = trace["conditional_probabilities"]
        metrics.append(
            {
                "id": trace["stage_id"],
                "label": f"Tramo {trace['label']} ({trace['interval']})",
                "value": (
                    f"TP {conditional['tp_first_in_stage'] * 100:.1f}% · "
                    f"SL {conditional['sl_first_in_stage'] * 100:.1f}% · "
                    f"n efectivo {trace['effective_sample_size']:.0f}"
                ),
                "score": None,
                "bias": "tramo_condicional",
                "explanation": (
                    f"{trace['selected_analogs']} trayectorias históricas "
                    "comparables; el tramo se aplica sólo a la masa que no "
                    "alcanzó TP ni SL anteriormente."
                ),
            }
        )
    return metrics


def analyze_trade(
    proposal: Any,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
    context_loader: Callable[..., dict] | None = None,
    context_market_price: float | None = None,
    order_book_observation_loader: Callable[[str], dict | None] | None = None,
    include_internal_runtime: bool = False,
    effective_analysis_at: datetime | None = None,
) -> dict:
    if str(getattr(proposal, "entry_type", "market")).lower() != "market":
        raise NewEngineAnalysisError("market_entry_required")
    time_horizon = str(proposal.time_horizon)
    if time_horizon not in STAGE_PROFILES:
        raise NewEngineAnalysisError("unsupported_time_horizon")
    request_received_at = datetime.now(timezone.utc)
    snapshot = {
        "symbol": str(proposal.symbol).upper(),
        "side": str(proposal.side).lower(),
        "time_horizon": time_horizon,
        "entry": float(proposal.entry),
        "take_profit": float(proposal.take_profit),
        "stop_loss": float(proposal.stop_loss),
        **_analysis_stamp(
            time_horizon,
            request_received_at=request_received_at,
            effective_analysis_at=effective_analysis_at or request_received_at,
        ),
    }
    analysis_id = (
        f"live-{snapshot['symbol']}-"
        f"{snapshot['analysis_at'].replace(':', '').replace('+', '_')}"
    )
    try:
        run = build_production_probability_run(
            proposal,
            snapshot,
            loader=loader,
            analysis_id=analysis_id,
        )
    except Exception as exc:
        raise NewEngineAnalysisError(
            "sequential_data_or_calculation_error",
            {"exception_type": type(exc).__name__},
        ) from exc
    if run.get("status") != "evaluated":
        raise NewEngineAnalysisError(
            str(run.get("block_code") or "sequential_analysis_blocked"),
            run.get("details") or {},
        )
    if run.get("analysis_engine_execution_count") != 1 or run.get(
        "executed_analysis_engines"
    ) != [ENGINE_VERSION]:
        raise NewEngineAnalysisError("single_engine_runtime_contract_violated")
    liquidation_live_context, liquidation_observation = attach_liquidation_observation(
        run,
        proposal,
        context_loader=context_loader,
        context_market_price=context_market_price,
        analysis_at=snapshot["analysis_at"],
    )
    order_book_live_context, order_book_observation = attach_order_book_observation(
        run,
        proposal,
        observation_loader=order_book_observation_loader,
        analysis_at=snapshot["analysis_at"],
    )
    live_context = {**liquidation_live_context, **order_book_live_context}
    probability_result = run["probability_result"]
    classes = probability_result["probabilities"]
    probabilities = {
        "tp": float(classes["tp_first_within_horizon"]),
        "sl": float(classes["sl_first_within_horizon"]),
        "range": float(classes["neither_barrier_before_expiry"]),
    }
    if abs(math.fsum(probabilities.values()) - 1.0) > 1e-12:
        raise NewEngineAnalysisError("sequential_probability_mass_invalid")
    artifact = load_production_artifact()
    stages = probability_result["executed_stages"]
    temporal_profile = _temporal_profile(time_horizon, artifact, stages)
    decision_probabilities = probability_result["decision_probabilities"]
    availability = _analysis_availability(
        run,
        proposal,
        stages,
        liquidation_available=liquidation_observation["available"],
        order_book_available=order_book_observation["available"],
    )
    snapshot.update(
        {
            **_geometry(proposal),
            "data_cutoff_at": run["data_cutoff_at"],
            "availability": availability,
            "source": {
                "entry_price": "validated trade-plan entry price",
                "probability_market_data": (
                    "Binance USD-M closed 5m/1h/6h klines according to stage"
                ),
                "probability_model": ENGINE_VERSION,
                "structural_observation": (
                    "confirmed pivots derived independently for each stage"
                ),
                "fibonacci_observation": (
                    "completed pivot swings derived independently for each stage"
                ),
                "liquidation_observation": (
                    liquidation_observation.get("provider")
                    or liquidation_observation.get("provider_reason")
                    or "unavailable"
                ),
                "order_book_observation": (
                    order_book_observation.get("provider")
                    or order_book_observation.get("provider_reason")
                    or "unavailable"
                ),
            },
            "new_engine_only": True,
            "legacy_engine_executed": False,
            "analysis_engine_execution_count": 1,
            "executed_analysis_engines": [ENGINE_VERSION],
            "stage_contexts": run["stage_contexts"],
            "stage_rule_traces": run["stage_rule_traces"],
            "liquidation_observation": liquidation_observation,
            "order_book_observation": order_book_observation,
            "probability_trace": probability_result,
            "temporal_profile": temporal_profile,
            "decision_probabilities": decision_probabilities,
        }
    )
    result = {
        "analysis_type": "pre_trade",
        "engine_family": ENGINE_FAMILY,
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "owner_activation": OWNER_ACTIVATION,
        "production_effect": "served",
        "legacy_engine_executed": False,
        "analysis_engine_execution_count": 1,
        "executed_analysis_engines": [ENGINE_VERSION],
        "tp_probability": probabilities["tp"],
        "sl_probability": probabilities["sl"],
        "range_probability": probabilities["range"],
        "tp_before_sl_within_horizon_probability": probabilities["tp"],
        "probability_ranges": _probability_ranges(probability_result),
        "risk_level": f"{probabilities['sl'] * 100:.1f}% SL",
        "setup_grade": "no aplicable",
        "confidence": temporal_profile["confidence"],
        "horizon_calibration": temporal_profile,
        "training_decision": "decisión del usuario",
        "time_horizon": time_horizon,
        "parameter_advice": {},
        "reasons": [
            (
                "Probabilidad acumulada de TP antes que SL: "
                f"{_probability_label(probabilities['tp'])}."
            ),
            (
                "Probabilidad acumulada de SL antes que TP: "
                f"{_probability_label(probabilities['sl'])}."
            ),
            (
                "Ninguna barrera antes del vencimiento: "
                f"{_probability_label(probabilities['range'])}."
            ),
            (
                "El análisis reproduce TP y SL sobre trayectorias históricas "
                "comparables y encadena "
                f"{len(stages)} tramo(s) sin reclasificar primeros toques."
            ),
        ],
        "alerts": [
            "La estimación expresa frecuencia histórica condicionada, no certeza futura.",
            HORIZON_VALIDATION_NOTES[time_horizon],
            "Mapas de liquidaciones y dinámica del libro se registran como observación y no alteran las probabilidades v0.9; Fibonacci y niveles estructurales tampoco puntúan.",
            "La probabilidad no incorpora costes ni garantiza rentabilidad.",
        ],
        "plain_summary": (
            "Motor empírico multiescala v0.9: probabilidad de TP antes "
            f"que SL en {HORIZON_LABELS[time_horizon]}: "
            f"{_probability_label(probabilities['tp'])}."
        ),
        "explained_metrics": _explained_metrics(probability_result),
        "snapshot": snapshot,
        "model_trace": {
            "engine_version": ENGINE_VERSION,
            "single_engine": True,
            "parallel_probability_engines_executed": 0,
            "artifact_id": artifact["artifact_id"],
            "artifact_sha256": artifact["artifact_sha256"],
            "temporal_profile": temporal_profile,
            "stage_traces": probability_result["stage_traces"],
            "probability_curve": probability_result["probability_curve"],
            "selected_probabilities": probability_result["probabilities"],
            "decision_probabilities": decision_probabilities,
            "probability_result_sha256": probability_result["result_sha256"],
            "source_data_sha256": run["source_data_sha256"],
            "source_data_sha256_by_stage": run[
                "source_data_sha256_by_stage"
            ],
            "data_cutoff_at": run["data_cutoff_at"],
            "activation_authority": OWNER_ACTIVATION,
            "production_effect": "served",
        },
    }
    if include_internal_runtime:
        result["_internal_runtime"] = {
            "run": run,
            "live_context": live_context,
        }
    return result


__all__ = (
    "ENGINE_FAMILY",
    "HORIZON_LABELS",
    "NewEngineAnalysisError",
    "_analysis_availability",
    "attach_liquidation_observation",
    "attach_order_book_observation",
    "analyze_trade",
)
