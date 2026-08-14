from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Callable

import market_data
from limit_activation_baseline import (
    LimitActivationBaselineError,
    build_limit_activation_baseline,
)
from limit_context_rule_runtime import (
    RULE_IDS as LIMIT_CONTEXT_RULE_IDS,
    RUNTIME_VERSION as LIMIT_CONTEXT_RUNTIME_VERSION,
    canonical_sha256 as limit_context_sha256,
)
from limit_order_contract import (
    LIMIT_ORDER_ANALYSIS_FAMILY,
    LimitOrderContractError,
    build_limit_order_contract,
    compose_limit_probability_tree,
)
from sequential_production_analysis import NewEngineAnalysisError, analyze_trade
from empirical_temporal_engine import ENGINE_VERSION


# LIMIT is an entry lifecycle around the same v0.9 TP/SL engine, not a second
# probability engine or a separately versioned analysis result.
LIMIT_PRODUCTION_ENGINE_VERSION = ENGINE_VERSION


class LimitProductionAnalysisError(RuntimeError):
    def __init__(
        self,
        code: str,
        details: dict | None = None,
        *,
        status_code: int = 503,
    ):
        super().__init__(code)
        self.code = code
        self.details = details or {}
        self.status_code = status_code


def _probability_label(value: float) -> str:
    if 0.0 < value < 0.001:
        return "<0.1%"
    if 0.999 < value < 1.0:
        return ">99.9%"
    return f"{value * 100:.1f}%"


def _conditional_probabilities(result: dict) -> dict[str, float]:
    return {
        "tp_first_within_outcome_horizon": float(result["tp_probability"]),
        "sl_first_within_outcome_horizon": float(result["sl_probability"]),
        "neither_barrier_before_outcome_expiry": float(
            result["range_probability"]
        ),
    }


def analyze_limit_trade(
    proposal: Any,
    *,
    price_loader: Callable[..., float] = market_data.get_price,
    conditional_analyzer: Callable[..., dict] = analyze_trade,
) -> dict:
    if str(getattr(proposal, "entry_type", "market")).lower() != "pending":
        raise LimitProductionAnalysisError(
            "pending_entry_required",
            status_code=400,
        )
    if str(getattr(proposal, "entry_order_type", "")) != "limit_pullback":
        raise LimitProductionAnalysisError(
            "limit_pullback_required",
            {
                "entry_order_type": getattr(
                    proposal,
                    "entry_order_type",
                    None,
                )
            },
            status_code=400,
        )

    try:
        current_price = float(
            price_loader(str(proposal.symbol).upper(), force_refresh=True)
        )
    except Exception as exc:
        raise LimitProductionAnalysisError(
            "limit_current_price_unavailable",
            {"exception_type": type(exc).__name__},
        ) from exc

    conditional_proposal = replace(
        proposal,
        entry_type="market",
        trigger_condition=None,
        entry_order_type=None,
    )
    try:
        conditional_result = conditional_analyzer(
            conditional_proposal,
            context_market_price=current_price,
            include_internal_runtime=True,
        )
    except NewEngineAnalysisError as exc:
        raise LimitProductionAnalysisError(
            f"limit_conditional_{exc.code}",
            exc.details,
        ) from exc
    except Exception as exc:
        raise LimitProductionAnalysisError(
            "limit_conditional_preview_failed",
            {"exception_type": type(exc).__name__},
        ) from exc

    internal = conditional_result.pop("_internal_runtime", None)
    if not isinstance(internal, dict) or not isinstance(
        internal.get("run"),
        dict,
    ):
        raise LimitProductionAnalysisError(
            "limit_conditional_runtime_missing",
        )
    run = internal["run"]
    live_context = internal.get("live_context") or {}
    sigma_horizon = run.get("horizon_volatility")
    if sigma_horizon is None:
        raise LimitProductionAnalysisError(
            "limit_horizon_volatility_missing",
        )

    analysis_at = (
        conditional_result.get("snapshot", {}).get("analysis_at")
        or datetime.now(timezone.utc).isoformat()
    )
    analysis_id = (
        f"live-limit-{str(proposal.symbol).upper()}-"
        f"{analysis_at.replace(':', '').replace('+', '_')}"
    )
    try:
        contract = build_limit_order_contract(
            analysis_id=analysis_id,
            symbol=proposal.symbol,
            side=proposal.side,
            time_horizon=proposal.time_horizon,
            analysis_at=analysis_at,
            current_price=current_price,
            requested_entry=proposal.entry,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit,
            trigger_condition=proposal.trigger_condition,
        )
        activation_baseline = build_limit_activation_baseline(
            contract,
            sigma_horizon=float(sigma_horizon),
        )
        context_runtime = {
            "runtime_version": LIMIT_CONTEXT_RUNTIME_VERSION,
            "analysis_id": contract.get("analysis_id"),
            "contract_version": contract.get("contract_version"),
            "activation_model_version": activation_baseline.get(
                "model_version"
            ),
            "production_effect": "none_disabled",
            "status": "not_executed",
            "evaluated_rule_count": 0,
            "blocked_rule_count": len(LIMIT_CONTEXT_RULE_IDS),
            "reason": "single_production_probability_engine_policy",
            "rule_ids": list(LIMIT_CONTEXT_RULE_IDS),
            "traces": [
                {
                    "rule_id": rule_id,
                    "status": "blocked",
                    "reason_codes": ["disabled_single_engine_policy"],
                    "outputs": {},
                }
                for rule_id in LIMIT_CONTEXT_RULE_IDS
            ],
        }
        context_runtime["runtime_trace_sha256"] = limit_context_sha256(
            context_runtime
        )
        probability_tree = compose_limit_probability_tree(
            activation_baseline["probabilities"]["activated_by_expiry"],
            _conditional_probabilities(conditional_result),
        )
    except LimitOrderContractError as exc:
        raise LimitProductionAnalysisError(
            str(exc),
            status_code=400,
        ) from exc
    except LimitActivationBaselineError as exc:
        raise LimitProductionAnalysisError(
            "limit_two_stage_calculation_failed",
            {
                "reason": str(exc),
                "exception_type": type(exc).__name__,
            },
        ) from exc

    p_activation = probability_tree["activation"]["activated_by_expiry"]
    conditional = probability_tree["conditional_after_activation"]
    overall = probability_tree["overall"]
    evaluated_descriptors = int(context_runtime["evaluated_rule_count"])
    horizon_label = str(proposal.time_horizon)

    conditional_result.update(
        {
            "analysis_type": "pre_trade_limit",
            "engine_family": LIMIT_ORDER_ANALYSIS_FAMILY,
            "engine_version": LIMIT_PRODUCTION_ENGINE_VERSION,
            "risk_level": (
                f"{conditional['sl_first_within_outcome_horizon'] * 100:.1f}% "
                "SL si activa"
            ),
            "setup_grade": "LIMIT en dos etapas",
            "confidence": (
                "v0.9 empírico condicional; activación base no calibrada"
            ),
            "training_decision": "decision del usuario",
            "reasons": [
                (
                    "Activacion estimada antes del vencimiento: "
                    f"{_probability_label(p_activation)}."
                ),
                (
                    "Si la orden activa, TP primero: "
                    f"{_probability_label(conditional['tp_first_within_outcome_horizon'])}."
                ),
                (
                    "Si la orden activa, SL primero: "
                    f"{_probability_label(conditional['sl_first_within_outcome_horizon'])}."
                ),
                "No se ejecutan reglas LIMIT observacionales en paralelo.",
            ],
            "alerts": [
                (
                    "La activacion es una referencia first-passage aun no "
                    "calibrada con el historial LIMIT cerrado."
                ),
                (
                    "TP/SL es una vista condicional calculada al colocar la "
                    "orden y se recalculara con datos frescos cuando active."
                ),
                (
                    "Las probabilidades no incorporan costes, deslizamiento "
                    "ni garantizan rentabilidad."
                ),
            ],
            "plain_summary": (
                "Orden LIMIT en dos etapas: activacion base "
                f"{_probability_label(p_activation)}; si activa, TP "
                f"{_probability_label(conditional['tp_first_within_outcome_horizon'])}, "
                f"SL {_probability_label(conditional['sl_first_within_outcome_horizon'])} "
                "y ninguna barrera "
                f"{_probability_label(conditional['neither_barrier_before_outcome_expiry'])} "
                f"dentro de {horizon_label}."
            ),
            "probability_semantics": {
                "visible_tp_sl_range_cards": "conditional_after_activation",
                "activation_probability_is_not_tp_probability": True,
                "conditional_preview_recomputed_at_actual_activation": True,
                "overall_reference_is_not_empirically_calibrated": True,
            },
            "limit_analysis": {
                "contract": contract,
                "activation_baseline": activation_baseline,
                "context_runtime": context_runtime,
                "probability_tree": probability_tree,
                "conditional_engine_version": conditional_result.get(
                    "model_trace",
                    {},
                ).get("engine_version"),
                "conditional_preview_stage": "placement",
                "conditional_recompute_policy": "rerun_at_actual_activation",
            },
        }
    )
    snapshot = conditional_result.setdefault("snapshot", {})
    snapshot.update(
        {
            "entry": float(proposal.entry),
            "current_market_price": current_price,
            "requested_entry": float(proposal.entry),
            "entry_type": "pending",
            "trigger_condition": proposal.trigger_condition,
            "entry_order_type": "limit_pullback",
            "limit_analysis_id": analysis_id,
            "limit_contract_version": contract["contract_version"],
            "activation_expires_at": contract["windows"]["activation"][
                "expires_at"
            ],
            "activation_probability_baseline": p_activation,
            "conditional_preview_at_placement": True,
        }
    )
    conditional_result.setdefault("explained_metrics", []).insert(
        0,
        {
            "id": "limit_activation_first_passage",
            "label": "Probabilidad base de activacion LIMIT",
            "value": _probability_label(p_activation),
            "score": round(p_activation * 100),
            "bias": "contexto",
            "explanation": (
                "Referencia por distancia, volatilidad y tiempo; todavia no "
                "calibrada con casos LIMIT cerrados."
            ),
            "source": "first-passage LIMIT v0.1",
        },
    )
    return conditional_result


__all__ = (
    "LIMIT_PRODUCTION_ENGINE_VERSION",
    "LimitProductionAnalysisError",
    "analyze_limit_trade",
)
