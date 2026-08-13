from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from m7_joint_temporal_engine import (
    ENGINE_VERSION,
    HORIZON_LABELS,
    HORIZON_SECONDS,
    SCORING_VERSION,
    load_production_artifact,
)
from m7_production_runtime import build_production_probability_run


# Public production adapter for the frozen v0.7 engine.
ENGINE_FAMILY = "joint_temporal_first_touch"
OWNER_ACTIVATION = "owner_explicit_single_engine_v0.7_2026-08-13"


class NewEngineAnalysisError(RuntimeError):
    def __init__(self, code: str, details: dict | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _analysis_stamp(
    time_horizon: str,
    *,
    request_received_at: datetime,
    effective_analysis_at: datetime | None = None,
) -> dict:
    try:
        horizon_seconds = int(HORIZON_SECONDS[time_horizon])
    except KeyError as exc:
        raise NewEngineAnalysisError("unsupported_time_horizon") from exc
    analysis_at = effective_analysis_at or datetime.now(timezone.utc)
    if analysis_at.tzinfo is None or analysis_at.utcoffset() is None:
        raise NewEngineAnalysisError("analysis_timestamp_must_be_timezone_aware")
    analysis_at = analysis_at.astimezone(timezone.utc)
    expires_at = datetime.fromtimestamp(
        analysis_at.timestamp() + horizon_seconds,
        tz=timezone.utc,
    )
    return {
        "request_received_at": request_received_at.isoformat(),
        "analysis_at": analysis_at.isoformat(),
        "data_cutoff_at": analysis_at.isoformat(),
        "data_cutoff_policy": "closed_1h_market_data_at_analysis_time_v0.7",
        "evaluation_horizon_seconds": horizon_seconds,
        "evaluation_expires_at": expires_at.isoformat(),
        "evaluation_horizon_policy": "single_curve_cumulative_read_v0.7",
    }


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
            "meaning": "estimacion puntual congelada v0.7",
        }
        for name, value in probabilities.items()
    }


def _feature_contributions(feature_snapshot: dict, artifact: dict) -> dict:
    raw_values = feature_snapshot["values"]
    standardized = feature_snapshot["standardized_values"]
    result = {}
    for name, raw_value in raw_values.items():
        value = float(standardized[name])
        coefficient_tp = float(artifact["coefficients"]["tp"][name])
        coefficient_sl = float(artifact["coefficients"]["sl"][name])
        result[name] = {
            "raw_value": float(raw_value),
            "standardized_value": value,
            "tp_coefficient": coefficient_tp,
            "sl_coefficient": coefficient_sl,
            "tp_linear_contribution": value * coefficient_tp,
            "sl_linear_contribution": value * coefficient_sl,
            "predictive": coefficient_tp != 0.0 or coefficient_sl != 0.0,
        }
    return result


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


def _temporal_profile(time_horizon: str, artifact: dict) -> dict:
    return {
        "version": ENGINE_VERSION,
        "role": "only_production_engine",
        "mutation": "frozen",
        "time_horizon": time_horizon,
        "horizon_seconds": HORIZON_SECONDS[time_horizon],
        "horizon_label": HORIZON_LABELS[time_horizon],
        "confidence": "motor temporal v0.7 congelado",
        "method": "single_joint_absorbing_first_touch_curve",
        "coefficient_artifact_id": artifact["artifact_id"],
        "coefficient_artifact_sha256": artifact["artifact_sha256"],
        "common_model_all_horizons": True,
        "horizon_specific_models": False,
        "parallel_probability_engines": 0,
        "automatic_weight_updates": False,
        "production_effect": "served",
    }


def _explained_metrics(run: dict, probability_result: dict) -> list[dict]:
    plan = probability_result["plan"]
    selected = probability_result["probabilities"]
    sigma = float(run["reference_sigma_24h"])
    return [
        {
            "id": "reference_realized_volatility_24h",
            "label": "Volatilidad realizada de referencia (24 h)",
            "value": f"{sigma * 100:.3f}%",
            "score": None,
            "bias": "resolucion",
            "explanation": (
                "Determina la velocidad esperada de llegada a cualquiera de "
                "las dos barreras; no favorece por si sola TP ni SL."
            ),
        },
        {
            "id": "tp_log_distance",
            "label": "Distancia logaritmica hasta TP",
            "value": f"{float(plan['tp_log_distance']) * 100:.3f}%",
            "score": None,
            "bias": "geometria",
            "explanation": "Distancia del plan usada por la carrera de primer toque.",
        },
        {
            "id": "sl_log_distance",
            "label": "Distancia logaritmica hasta SL",
            "value": f"{float(plan['sl_log_distance']) * 100:.3f}%",
            "score": None,
            "bias": "geometria",
            "explanation": "Distancia del plan usada por la carrera de primer toque.",
        },
        {
            "id": "temporal_resolution_probability",
            "label": "Probabilidad de resolver antes del vencimiento",
            "value": _probability_label(
                selected["tp_first_within_horizon"]
                + selected["sl_first_within_horizon"]
            ),
            "score": round(
                100
                * (
                    selected["tp_first_within_horizon"]
                    + selected["sl_first_within_horizon"]
                )
            ),
            "bias": "tiempo",
            "explanation": (
                "Lectura acumulada de la misma curva temporal; no es una "
                "prediccion independiente para este marco."
            ),
        },
    ]


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

    request_received_at = datetime.now(timezone.utc)
    analysis_cutoff = effective_analysis_at or request_received_at
    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        raise NewEngineAnalysisError("analysis_timestamp_must_be_timezone_aware")
    analysis_cutoff = analysis_cutoff.astimezone(timezone.utc)
    time_horizon = str(proposal.time_horizon)
    if time_horizon not in HORIZON_SECONDS:
        raise NewEngineAnalysisError("unsupported_time_horizon")
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
            effective_analysis_at=analysis_cutoff,
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
            "m7_data_or_calculation_error",
            {"exception_type": type(exc).__name__},
        ) from exc
    if run.get("status") != "evaluated":
        raise NewEngineAnalysisError(
            str(run.get("block_code") or "m7_blocked"),
            run.get("details") or {},
        )
    if run.get("analysis_engine_execution_count") != 1 or run.get(
        "executed_analysis_engines"
    ) != [ENGINE_VERSION]:
        raise NewEngineAnalysisError("single_engine_runtime_contract_violated")

    probability_result = run["probability_result"]
    artifact = load_production_artifact()
    classes = probability_result["probabilities"]
    probabilities = {
        "tp": float(classes["tp_first_within_horizon"]),
        "sl": float(classes["sl_first_within_horizon"]),
        "range": float(classes["neither_barrier_before_expiry"]),
    }
    mass_error = abs(math.fsum(probabilities.values()) - 1.0)
    if mass_error > 1e-12:
        raise NewEngineAnalysisError(
            "m7_probability_mass_invalid",
            {"mass_error": mass_error},
        )
    decision_probabilities = probability_result["decision_probabilities"]
    temporal_profile = _temporal_profile(time_horizon, artifact)
    feature_contributions = _feature_contributions(
        run["feature_snapshot"],
        artifact,
    )
    geometry = _geometry(proposal)
    snapshot.update(
        {
            **geometry,
            "data_cutoff_at": run["data_cutoff_at"],
            "availability": {
                "futures_price": False,
                "futures_klines": True,
                "order_book": False,
                "entry_depth": False,
                "futures_trade_flow": False,
                "ticker_24h": False,
                "fibonacci": False,
                "structural_levels": False,
                "funding": False,
                "funding_relative": False,
                "open_interest": False,
                "long_short_ratio": False,
                "taker_futures_ratio": False,
                "liquidation_heatmap": False,
                "fear_greed": False,
                "global_crypto_market": False,
                "market_breadth": False,
            },
            "source": {
                "probability_market_data": "Binance USD-M closed 1h klines",
                "probability_model": ENGINE_VERSION,
            },
            "new_engine_only": True,
            "legacy_engine_executed": False,
            "analysis_engine_execution_count": 1,
            "executed_analysis_engines": [ENGINE_VERSION],
            "feature_snapshot": run["feature_snapshot"],
            "probability_trace": probability_result,
            "temporal_profile": temporal_profile,
            "decision_probabilities": decision_probabilities,
            "feature_contributions": feature_contributions,
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
        "training_decision": "decision del usuario",
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
                "4 h, 24 h y 7 dias son lecturas de una unica curva "
                "absorbente; no se ejecutan modelos por marco."
            ),
        ],
        "alerts": [
            (
                "Los pesos direccionales candidatos no superaron la prueba "
                "final y permanecen congelados a cero."
            ),
            (
                "La probabilidad no incorpora costes, deslizamiento ni "
                "garantiza rentabilidad."
            ),
        ],
        "plain_summary": (
            "Motor unico v0.7: probabilidad de TP antes que SL dentro de "
            f"{HORIZON_LABELS[time_horizon]}: "
            f"{_probability_label(probabilities['tp'])}."
        ),
        "explained_metrics": _explained_metrics(run, probability_result),
        "snapshot": snapshot,
        "model_trace": {
            "engine_version": ENGINE_VERSION,
            "single_engine": True,
            "parallel_probability_engines_executed": 0,
            "coefficient_artifact_id": artifact["artifact_id"],
            "coefficient_artifact_sha256": artifact["artifact_sha256"],
            "temporal_profile": temporal_profile,
            "probability_curve": probability_result["probability_curve"],
            "selected_probabilities": probability_result["probabilities"],
            "decision_probabilities": decision_probabilities,
            "feature_contributions": feature_contributions,
            "probability_result_sha256": probability_result["result_sha256"],
            "source_data_sha256": run["source_data_sha256"],
            "data_cutoff_at": run["data_cutoff_at"],
            "activation_authority": OWNER_ACTIVATION,
            "production_effect": "served",
        },
    }
    if include_internal_runtime:
        result["_internal_runtime"] = {
            "run": run,
            "live_context": {},
        }
    return result


__all__ = (
    "ENGINE_FAMILY",
    "NewEngineAnalysisError",
    "analyze_trade",
)
