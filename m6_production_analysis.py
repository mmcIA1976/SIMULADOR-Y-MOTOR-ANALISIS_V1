from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from m5_input_assembly import trace_map
from m5_live_inputs import collect_live_rule_context
from m8_evaluation import HORIZON_SECONDS, selected_interval_seconds
from prospective_validation import (
    build_prospective_probability_run,
    load_frozen_candidate,
)
from versioning import ENGINE_VERSION, SCORING_VERSION


ENGINE_FAMILY = "tp_sl_competing_risks"
OWNER_ACTIVATION = "owner_explicit_activation_2026-07-28"


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
        "data_cutoff_policy": "closed_market_data_at_analysis_time_v0.1",
        "evaluation_horizon_seconds": horizon_seconds,
        "evaluation_expires_at": expires_at.isoformat(),
        "evaluation_horizon_policy": "selected_frame_upper_bound_v0.1",
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
    overlay_labels = {
        "M4-RULE-PATH-STRUCTURE-001": "Estructura direccional del horizonte",
        "M4-RULE-CONTINUOUS-REGIME-001": "Regimen continuo",
        "M4-RULE-AGGRESSOR-IMBALANCE-001": "Desequilibrio taker",
        "M4-RULE-OPEN-INTEREST-CHANGE-001": "Variacion de open interest",
        "M4-RULE-PRICE-OI-STATE-001": "Relacion precio y open interest",
        "M4-RULE-SPOT-FUTURES-BASIS-001": "Basis Spot/Futures",
        "M4-RULE-MARK-INDEX-PREMIUM-001": "Prima mark/index",
        "M4-RULE-FUNDING-STATE-001": "Funding",
    }
    overlay = run["m6_result"].get("active_rule_overlay") or {}
    for rule_id, contribution in overlay.get(
        "rule_contributions",
        {},
    ).items():
        signal = float(contribution["signal"])
        if contribution["effect_mode"] == "movement":
            bias = "movimiento"
        elif signal > 0:
            bias = "favorable"
        elif signal < 0:
            bias = "desfavorable"
        else:
            bias = "neutral"
        metrics.append(
            {
                "id": rule_id,
                "label": overlay_labels[rule_id],
                "value": f"{signal:+.4f}",
                "score": round(50 + signal * 50),
                "bias": bias,
                "explanation": (
                    "Efecto sobre TP "
                    f"{contribution['tp_probability_delta'] * 100:+.2f} pp; "
                    "efecto sobre SL "
                    f"{contribution['sl_probability_delta'] * 100:+.2f} pp."
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
    context_loader: Callable[..., dict] = collect_live_rule_context,
    context_market_price: float | None = None,
    include_internal_runtime: bool = False,
    effective_analysis_at: datetime | None = None,
) -> dict:
    if str(getattr(proposal, "entry_type", "market")).lower() != "market":
        raise NewEngineAnalysisError("market_entry_required")

    request_received_at = datetime.now(timezone.utc)
    analysis_cutoff = effective_analysis_at or request_received_at
    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        raise NewEngineAnalysisError("analysis_timestamp_must_be_timezone_aware")
    analysis_cutoff = analysis_cutoff.astimezone(timezone.utc)
    time_horizon = str(proposal.time_horizon)
    try:
        horizon_seconds = int(HORIZON_SECONDS[time_horizon])
        interval_seconds = selected_interval_seconds(
            time_horizon,
            horizon_seconds,
        )
        live_context = context_loader(
            symbol=str(proposal.symbol).upper(),
            horizon_seconds=horizon_seconds,
            interval_seconds=interval_seconds,
            request_cutoff_at=analysis_cutoff.isoformat(),
            market_price=(
                float(context_market_price)
                if context_market_price is not None
                else float(proposal.entry)
            ),
        )
    except Exception as exc:
        raise NewEngineAnalysisError(
            "new_engine_live_context_unavailable",
            {"exception_type": type(exc).__name__},
        ) from exc

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
        run = build_prospective_probability_run(
            proposal,
            snapshot,
            loader=loader,
            analysis_id=analysis_id,
            active_output=True,
            live_context=live_context,
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
    active_predictive_rule_ids = run["feature_snapshot"].get(
        "active_predictive_rule_ids",
        [],
    )
    feature_contributions = _feature_contributions(
        run["feature_snapshot"],
        artifact,
    )
    m5_traces = trace_map(run["m5_analysis"])
    m5_statuses = {
        rule_id: trace["status"]
        for rule_id, trace in m5_traces.items()
    }
    spread_trace = m5_traces.get("M4-RULE-QUOTED-SPREAD-001", {})
    depth_trace = m5_traces.get("M4-RULE-DEPTH-SWEEP-001", {})
    observational_statuses = {
        str(trace.get("rule_id")): trace.get("status")
        for trace in (
            run.get("observational_rule_traces", {}).get("traces", [])
        )
        if isinstance(trace, dict) and trace.get("rule_id")
    }
    snapshot.update(
        {
            **geometry,
            "data_cutoff_at": run["data_cutoff_at"],
            "availability": {
                "futures_price": bool(live_context.get("futures_book")),
                "futures_klines": True,
                "order_book": (
                    spread_trace.get("status") == "evaluated"
                ),
                "entry_depth": (
                    depth_trace.get("status") == "evaluated"
                    and depth_trace.get("outputs", {}).get(
                        "availability_status"
                    )
                    == "available"
                ),
                "futures_trade_flow": (
                    m5_statuses.get("M4-RULE-AGGRESSOR-IMBALANCE-001")
                    == "evaluated"
                ),
                "ticker_24h": False,
                "fibonacci": (
                    observational_statuses.get(
                        "LIB-CAND-FIBONACCI-DISTANCE-001"
                    )
                    == "evaluated_shadow"
                ),
                "structural_levels": (
                    observational_statuses.get(
                        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
                    )
                    == "evaluated_shadow"
                ),
                "funding": (
                    m5_statuses.get("M4-RULE-FUNDING-STATE-001")
                    == "evaluated"
                ),
                "funding_relative": (
                    observational_statuses.get(
                        "LIB-CAND-FUNDING-PERCENTILE-001"
                    )
                    == "evaluated_shadow"
                ),
                "open_interest": (
                    m5_statuses.get("M4-RULE-OPEN-INTEREST-CHANGE-001")
                    == "evaluated"
                ),
                "long_short_ratio": (
                    observational_statuses.get(
                        "LIB-CAND-CROWDING-PERCENTILE-001"
                    )
                    == "evaluated_shadow"
                ),
                "taker_futures_ratio": False,
                "liquidation_heatmap": (
                    observational_statuses.get(
                        "LIB-CAND-LIQUIDATION-ZONE-001"
                    )
                    == "evaluated_shadow"
                ),
                "fear_greed": (
                    observational_statuses.get(
                        "LIB-CAND-SENTIMENT-PERCENTILE-001"
                    )
                    == "evaluated_shadow"
                ),
                "global_crypto_market": False,
                "market_breadth": (
                    observational_statuses.get(
                        "LIB-CAND-BREADTH-001"
                    )
                    == "evaluated_shadow"
                ),
            },
            "source": {
                "probability_market_data": "Binance USD-M closed klines",
                "probability_model": ENGINE_VERSION,
                "structural_fibonacci_observation": (
                    "Binance USD-M closed klines"
                ),
                "funding_positioning_observation": (
                    "Binance USD-M funding and global account ratio"
                ),
                "market_context_observation": (
                    "CoinGecko top markets and Alternative.me Fear & Greed"
                ),
                "liquidation_observation": (
                    "HyperPerps aggregation of Hyperliquid public positions"
                ),
            },
            "new_engine_only": True,
            "legacy_engine_executed": False,
            "execution_economics": {
                "probability_effect": "none_separate_economic_layer",
                "quoted_spread": spread_trace.get("outputs", {}),
                "entry_depth_sweep": depth_trace.get("outputs", {}),
            },
            "feature_snapshot": run["feature_snapshot"],
            "m5_rule_trace": run["m5_analysis"],
            "m5_pre_probability_trace": run[
                "m5_pre_probability_analysis"
            ],
            "m5_rule_statuses": m5_statuses,
            "m5_rule_effects": run["m5_rule_effects"],
            "m6_probability_trace": m6_result,
            "feature_contributions": feature_contributions,
        }
    )
    probability_ranges = _probability_ranges(probabilities)
    result = {
        "analysis_type": "pre_trade",
        "engine_family": ENGINE_FAMILY,
        "engine_version": ENGINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "owner_activation": OWNER_ACTIVATION,
        "production_effect": "served",
        "legacy_engine_executed": False,
        "tp_probability": probabilities["tp"],
        "sl_probability": probabilities["sl"],
        "range_probability": probabilities["range"],
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
                f"El calculo ha aplicado {len(active_predictive_rule_ids)} "
                "reglas predictivas con datos disponibles."
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
            f"dentro de {proposal.time_horizon}, con "
            f"{len(active_predictive_rule_ids)} reglas activas."
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
            "probabilities_before_rule_overlay": m6_result.get(
                "probabilities_before_rule_overlay"
            ),
            "active_predictive_rule_ids": active_predictive_rule_ids,
            "active_rule_overlay": m6_result.get("active_rule_overlay"),
            "feature_contributions": feature_contributions,
            "m5_rule_effects": run["m5_rule_effects"],
            "m5_analysis_trace_sha256": run["m5_analysis"].get(
                "analysis_trace_sha256"
            ),
            "m5_pre_probability_trace_sha256": run[
                "m5_pre_probability_analysis"
            ].get("analysis_trace_sha256"),
            "m6_result_sha256": m6_result.get("result_sha256"),
            "source_data_sha256": run["source_data_sha256"],
            "data_cutoff_at": run["data_cutoff_at"],
            "activation_authority": OWNER_ACTIVATION,
            "production_effect": "served",
        },
    }
    if include_internal_runtime:
        # Transient integration hook for the two-stage LIMIT orchestrator.
        # The caller must remove this data before persistence or API output.
        result["_internal_runtime"] = {
            "run": run,
            "live_context": live_context,
        }
    return result
