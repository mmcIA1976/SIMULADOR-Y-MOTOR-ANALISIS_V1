from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from m8_evaluation import HORIZON_SECONDS
from prospective_validation import (
    build_prospective_probability_run,
    load_frozen_candidate,
)


ENGINE_FAMILY = "m6_calibrated_competing_risks"
ENGINE_VERSION = "M6-CANDIDATE-NO-H-RIDGE-10-v0.2"
SCORING_VERSION = "M6-calibrated-competing-risks-v0.2"
OWNER_ACTIVATION = "owner_explicit_activation_2026-07-28"


class NewEngineAnalysisError(RuntimeError):
    def __init__(self, code: str, details: dict | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


def _analysis_stamp(time_horizon: str) -> dict:
    try:
        horizon_seconds = int(HORIZON_SECONDS[time_horizon])
    except KeyError as exc:
        raise NewEngineAnalysisError("unsupported_time_horizon") from exc
    analysis_at = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(
        analysis_at.timestamp() + horizon_seconds,
        tz=timezone.utc,
    )
    return {
        "analysis_at": analysis_at.isoformat(),
        "data_cutoff_at": analysis_at.isoformat(),
        "data_cutoff_policy": "closed_market_data_at_analysis_time_v0.1",
        "evaluation_horizon_seconds": horizon_seconds,
        "evaluation_expires_at": expires_at.isoformat(),
        "evaluation_horizon_policy": "selected_frame_upper_bound_v0.1",
    }


def _probability_label(value: float) -> str:
    return f"{value * 100:.1f}%"


def _probability_ranges(probabilities: dict[str, float]) -> dict:
    return {
        name: {
            "low": value,
            "high": value,
            "label": _probability_label(value),
            "meaning": "estimacion puntual calibrada",
        }
        for name, value in probabilities.items()
    }


def _feature_contributions(
    feature_snapshot: dict,
    artifact: dict,
) -> dict:
    raw_values = feature_snapshot["values"]
    standardized = feature_snapshot["standardized_candidate_values"]
    result = {}
    for name, value in standardized.items():
        if name == "intercept":
            continue
        coefficient_tp = float(artifact["coefficients"]["tp"][name])
        coefficient_sl = float(artifact["coefficients"]["sl"][name])
        result[name] = {
            "raw_value": float(raw_values[name]),
            "standardized_value": float(value),
            "tp_coefficient": coefficient_tp,
            "sl_coefficient": coefficient_sl,
            "tp_linear_contribution": float(value) * coefficient_tp,
            "sl_linear_contribution": float(value) * coefficient_sl,
            "predictive": coefficient_tp != 0.0 or coefficient_sl != 0.0,
        }
    result["intercept"] = {
        "raw_value": 1.0,
        "standardized_value": 1.0,
        "tp_coefficient": float(artifact["coefficients"]["tp"]["intercept"]),
        "sl_coefficient": float(artifact["coefficients"]["sl"]["intercept"]),
        "tp_linear_contribution": float(
            artifact["coefficients"]["tp"]["intercept"]
        ),
        "sl_linear_contribution": float(
            artifact["coefficients"]["sl"]["intercept"]
        ),
        "predictive": True,
    }
    return result


def _explained_metrics(run: dict) -> list[dict]:
    values = run["feature_snapshot"]["values"]
    contributions = _feature_contributions(
        run["feature_snapshot"],
        load_frozen_candidate()["coefficient_artifact"],
    )
    labels = {
        "directional_path_efficiency_h": "Eficiencia direccional del horizonte",
        "directional_path_efficiency_2h": "Eficiencia direccional en 2 horizontes",
        "directional_path_efficiency_4h": "Eficiencia direccional en 4 horizontes",
        "volatility_percentile_60": "Percentil de volatilidad",
        "target_extreme_between_entry_and_tp": "Extremo previo entre entrada y TP",
    }
    metrics = []
    for name, label in labels.items():
        contribution = contributions[name]
        metrics.append(
            {
                "id": name,
                "label": label,
                "value": f"{float(values[name]):.4f}",
                "score": 50,
                "bias": "contexto",
                "explanation": (
                    "Contribucion lineal TP "
                    f"{contribution['tp_linear_contribution']:+.4f}; "
                    "contribucion lineal SL "
                    f"{contribution['sl_linear_contribution']:+.4f}."
                ),
                "trace": contribution,
            }
        )
    return metrics


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


def analyze_trade(
    proposal: Any,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
) -> dict:
    if str(getattr(proposal, "entry_type", "market")).lower() != "market":
        raise NewEngineAnalysisError("market_entry_required")

    snapshot = {
        "symbol": str(proposal.symbol).upper(),
        "side": str(proposal.side).lower(),
        "time_horizon": str(proposal.time_horizon),
        "entry": float(proposal.entry),
        "take_profit": float(proposal.take_profit),
        "stop_loss": float(proposal.stop_loss),
        **_analysis_stamp(str(proposal.time_horizon)),
    }
    analysis_id = (
        f"live-{snapshot['symbol']}-"
        f"{snapshot['analysis_at'].replace(':', '').replace('+', '_')}"
    )
    try:
        run = build_prospective_probability_run(
            proposal,
            snapshot,
            loader=loader,
            analysis_id=analysis_id,
            active_output=True,
        )
    except Exception as exc:
        raise NewEngineAnalysisError(
            "new_engine_data_or_calculation_error",
            {"exception_type": type(exc).__name__},
        ) from exc
    if run.get("status") != "evaluated":
        raise NewEngineAnalysisError(
            str(run.get("block_code") or "new_engine_blocked"),
            run.get("details") or {},
        )

    candidate = load_frozen_candidate()
    artifact = candidate["coefficient_artifact"]
    m6_result = run["m6_result"]
    classes = m6_result["probabilities"]
    probabilities = {
        "tp": float(classes["tp_first_within_horizon"]),
        "sl": float(classes["sl_first_within_horizon"]),
        "range": float(classes["neither_barrier_before_expiry"]),
    }
    mass_error = abs(math.fsum(probabilities.values()) - 1.0)
    if mass_error > 1e-12:
        raise NewEngineAnalysisError(
            "new_engine_probability_mass_invalid",
            {"mass_error": mass_error},
        )

    artifact = candidate["coefficient_artifact"]
    geometry = _geometry(proposal)
    feature_contributions = _feature_contributions(
        run["feature_snapshot"],
        artifact,
    )
    snapshot.update(
        {
            **geometry,
            "availability": {
                "futures_price": False,
                "futures_klines": True,
                "order_book": False,
                "futures_trade_flow": False,
                "ticker_24h": False,
                "fibonacci": False,
                "funding": False,
                "open_interest": False,
                "long_short_ratio": False,
                "taker_futures_ratio": False,
                "liquidation_heatmap": False,
                "fear_greed": False,
                "global_crypto_market": False,
            },
            "source": {
                "probability_market_data": "Binance USD-M closed klines",
                "probability_model": ENGINE_VERSION,
            },
            "new_engine_only": True,
            "legacy_engine_executed": False,
            "feature_snapshot": run["feature_snapshot"],
            "m5_rule_trace": run["m5_analysis"],
            "m6_probability_trace": m6_result,
            "feature_contributions": feature_contributions,
        }
    )
    probability_ranges = _probability_ranges(probabilities)
    return {
        "analysis_type": "pre_trade",
        "engine_family": ENGINE_FAMILY,
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "owner_activation": OWNER_ACTIVATION,
        "production_effect": "served",
        "legacy_engine_executed": False,
        "tp_probability": round(probabilities["tp"], 6),
        "sl_probability": round(probabilities["sl"], 6),
        "range_probability": round(probabilities["range"], 6),
        "probability_ranges": probability_ranges,
        "risk_level": f"{probabilities['sl'] * 100:.1f}% SL",
        "setup_grade": "no aplicable",
        "confidence": "calibracion historica",
        "training_decision": "decision del usuario",
        "time_horizon": str(proposal.time_horizon),
        "parameter_advice": {},
        "reasons": [
            (
                "TP primero dentro del horizonte: "
                f"{_probability_label(probabilities['tp'])}."
            ),
            (
                "SL primero dentro del horizonte: "
                f"{_probability_label(probabilities['sl'])}."
            ),
            (
                "Ninguna barrera antes del vencimiento: "
                f"{_probability_label(probabilities['range'])}."
            ),
            (
                "El calculo usa geometria TP/SL, volatilidad realizada y "
                "eficiencia direccional obtenidas de velas cerradas."
            ),
        ],
        "alerts": [
            (
                "La probabilidad no incorpora costes, deslizamiento ni garantiza "
                "rentabilidad."
            )
        ],
        "plain_summary": (
            f"Nuevo motor: TP {_probability_label(probabilities['tp'])}, "
            f"SL {_probability_label(probabilities['sl'])} y "
            f"sin toque {_probability_label(probabilities['range'])} "
            f"dentro de {proposal.time_horizon}."
        ),
        "explained_metrics": _explained_metrics(run),
        "snapshot": snapshot,
        "model_trace": {
            "candidate_version": candidate["version"],
            "coefficient_artifact_id": artifact["id"],
            "coefficient_artifact_sha256": artifact["artifact_sha256"],
            "calibration": artifact["calibration"],
            "raw_probabilities": m6_result["raw_probabilities"],
            "calibrated_probabilities": m6_result["probabilities"],
            "feature_contributions": feature_contributions,
            "m5_analysis_trace_sha256": run["m5_analysis"].get(
                "analysis_trace_sha256"
            ),
            "m6_result_sha256": m6_result.get("result_sha256"),
            "source_data_sha256": run["source_data_sha256"],
            "data_cutoff_at": run["data_cutoff_at"],
            "activation_authority": OWNER_ACTIVATION,
            "production_effect": "served",
        },
    }
