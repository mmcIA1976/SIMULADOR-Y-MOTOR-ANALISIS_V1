from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from multiscale_feature_runtime import STAGE_ORDER, STAGE_PROFILES
from sequential_production_runtime import build_production_probability_run
from sequential_temporal_engine import (
    ENGINE_VERSION,
    SCORING_VERSION,
    load_production_artifact,
)


ENGINE_FAMILY = "sequential_multiscale_first_touch"
OWNER_ACTIVATION = "owner_explicit_sequential_multiscale_v0.8_2026-08-13"
HORIZON_LABELS = {
    "intraday_short": "Intradía corto · hasta 4 h",
    "intraday_wide": "Intradía medio · hasta 24 h",
    "short_swing": "Intradía largo · hasta 7 días",
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


def _probability_ranges(probabilities: dict[str, float]) -> dict:
    return {
        name: {
            "low": value,
            "high": value,
            "label": _probability_label(value),
            "meaning": "estimación puntual congelada v0.8",
        }
        for name, value in probabilities.items()
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


def _temporal_profile(time_horizon: str, artifact: dict, stages: list[str]) -> dict:
    return {
        "version": ENGINE_VERSION,
        "role": "only_production_engine",
        "mutation": "frozen",
        "time_horizon": time_horizon,
        "horizon_seconds": STAGE_PROFILES[time_horizon]["horizon_seconds"],
        "horizon_label": HORIZON_LABELS[time_horizon],
        "confidence": "motor secuencial multiescala v0.8 congelado",
        "method": "conditional_multiscale_first_touch_stages",
        "coefficient_artifact_id": artifact["artifact_id"],
        "coefficient_artifact_sha256": artifact["artifact_sha256"],
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
        "data_cutoff_policy": "closed_multiscale_market_data_at_analysis_time_v0.8",
        "evaluation_horizon_seconds": horizon_seconds,
        "evaluation_expires_at": expires_at.isoformat(),
        "evaluation_horizon_policy": "nested_conditional_stage_read_v0.8",
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
                    f"SL {conditional['sl_first_in_stage'] * 100:.1f}%"
                ),
                "score": None,
                "bias": "tramo_condicional",
                "explanation": (
                    "Se aplica únicamente a la probabilidad que no alcanzó "
                    "TP ni SL en los tramos anteriores."
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
    include_internal_runtime: bool = False,
    effective_analysis_at: datetime | None = None,
) -> dict:
    del context_loader, context_market_price
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
    snapshot.update(
        {
            **_geometry(proposal),
            "data_cutoff_at": run["data_cutoff_at"],
            "availability": {
                "futures_price": False,
                "futures_klines": True,
                "multiscale_5m": "intraday_short" in stages,
                "multiscale_1h": "intraday_wide" in stages,
                "multiscale_6h": "short_swing" in stages,
                "fibonacci": True,
                "structural_levels": True,
                "liquidation_heatmap": False,
            },
            "source": {
                "probability_market_data": (
                    "Binance USD-M closed 5m/1h/6h klines according to stage"
                ),
                "probability_model": ENGINE_VERSION,
            },
            "new_engine_only": True,
            "legacy_engine_executed": False,
            "analysis_engine_execution_count": 1,
            "executed_analysis_engines": [ENGINE_VERSION],
            "stage_contexts": run["stage_contexts"],
            "stage_rule_traces": run["stage_rule_traces"],
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
        "probability_ranges": _probability_ranges(probabilities),
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
                "El análisis encadena "
                f"{len(stages)} tramo(s) con datos propios y conserva los "
                "primeros toques anteriores."
            ),
        ],
        "alerts": [
            (
                "Las reglas del tramo 24 h-7 d no modifican la dirección: "
                "su peso fue rechazado fuera de muestra; el tramo mantiene "
                "la dinámica multiescala de resolución."
            )
            if time_horizon == "short_swing"
            else "Sin alertas metodológicas adicionales para el tramo seleccionado.",
            "La probabilidad no incorpora costes ni garantiza rentabilidad.",
        ],
        "plain_summary": (
            "Motor secuencial multiescala v0.8: probabilidad de TP antes "
            f"que SL en {HORIZON_LABELS[time_horizon]}: "
            f"{_probability_label(probabilities['tp'])}."
        ),
        "explained_metrics": _explained_metrics(probability_result),
        "snapshot": snapshot,
        "model_trace": {
            "engine_version": ENGINE_VERSION,
            "single_engine": True,
            "parallel_probability_engines_executed": 0,
            "coefficient_artifact_id": artifact["artifact_id"],
            "coefficient_artifact_sha256": artifact["artifact_sha256"],
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
        result["_internal_runtime"] = {"run": run, "live_context": {}}
    return result


__all__ = (
    "ENGINE_FAMILY",
    "HORIZON_LABELS",
    "NewEngineAnalysisError",
    "analyze_trade",
)
