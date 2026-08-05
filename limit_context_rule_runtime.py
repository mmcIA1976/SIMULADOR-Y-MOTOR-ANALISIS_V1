from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from limit_activation_baseline import LIMIT_ACTIVATION_MODEL_VERSION
from limit_order_contract import (
    LIMIT_ORDER_ANALYSIS_FAMILY,
    LIMIT_ORDER_CONTRACT_VERSION,
    LIMIT_ORDER_TYPE,
)


RUNTIME_VERSION = "limit-context-rule-runtime-v0.1"
RULE_IDS = (
    "LIMIT-CAND-ACTIVATION-TRAJECTORY-001",
    "LIMIT-CAND-FLOW-DUAL-ROLE-001",
    "LIMIT-CAND-ZONE-STRUCTURE-001",
    "LIMIT-CAND-LIQUIDATION-PATH-001",
)
EVALUATED_STATUSES = {"evaluated", "evaluated_shadow"}


class LimitContextRuleError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LimitContextRuleError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number):
        raise LimitContextRuleError(f"{name}_must_be_finite")
    return number


def _finite_positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0:
        raise LimitContextRuleError(f"{name}_must_be_positive")
    return number


def _finite_non_negative(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number < 0:
        raise LimitContextRuleError(f"{name}_must_be_non_negative")
    return number


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise LimitContextRuleError("side_must_be_long_or_short")


def _relation(value: float) -> str:
    if value > 0:
        return "toward_direction"
    if value < 0:
        return "against_direction"
    return "flat"


def _trace_map(*containers: object) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for container in containers:
        if isinstance(container, list):
            rows = container
        elif isinstance(container, dict):
            rows = container.get("traces", [])
        else:
            rows = []
        for trace in rows:
            if isinstance(trace, dict) and trace.get("rule_id"):
                result[str(trace["rule_id"])] = trace
    return result


def _available_trace(traces: dict[str, dict], rule_id: str) -> dict | None:
    trace = traces.get(rule_id)
    if not trace or trace.get("status") not in EVALUATED_STATUSES:
        return None
    return trace if isinstance(trace.get("outputs"), dict) else None


def _trace(
    *,
    rule_id: str,
    family_id: str,
    parent_rule_ids: list[str],
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    source_payload: object,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": family_id,
        "role": "limit_shadow_descriptor",
        "parent_rule_ids": parent_rule_ids,
        "status": status,
        "reason_codes": reason_codes,
        "formula_ids": [
            f"{rule_id}-FORMULA-01",
            f"{rule_id}-FORMULA-02",
            f"{rule_id}-FORMULA-03",
        ],
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": canonical_sha256(source_payload),
        "executed_at": executed_at,
        "probability_effect": "none_shadow_descriptor",
        "coefficient_status": "not_estimated",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def _blocked_parent_trace(
    *,
    rule_id: str,
    family_id: str,
    required_parent_ids: list[str],
    traces: dict[str, dict],
    executed_at: str,
) -> dict | None:
    missing = [
        rule_id
        for rule_id in required_parent_ids
        if _available_trace(traces, rule_id) is None
    ]
    if not missing:
        return None
    return _trace(
        rule_id=rule_id,
        family_id=family_id,
        parent_rule_ids=required_parent_ids,
        inputs={"missing_or_blocked_parent_rule_ids": missing},
        outputs={},
        status="blocked",
        reason_codes=["parent_rule_unavailable"],
        source_payload={
            parent: traces.get(parent) for parent in required_parent_ids
        },
        executed_at=executed_at,
    )


def _parent_hashes(
    traces: dict[str, dict],
    parent_rule_ids: list[str],
) -> dict[str, str | None]:
    return {
        rule_id: (
            traces.get(rule_id, {}).get("trace_sha256")
            if isinstance(traces.get(rule_id), dict)
            else None
        )
        for rule_id in parent_rule_ids
    }


def _validate_limit_inputs(
    contract: dict,
    activation_baseline: dict,
) -> tuple[dict, float, str]:
    if not isinstance(contract, dict):
        raise LimitContextRuleError("contract_must_be_an_object")
    if contract.get("contract_version") != LIMIT_ORDER_CONTRACT_VERSION:
        raise LimitContextRuleError("limit_contract_version_mismatch")
    if contract.get("analysis_family") != LIMIT_ORDER_ANALYSIS_FAMILY:
        raise LimitContextRuleError("limit_analysis_family_mismatch")
    order = contract.get("order")
    if not isinstance(order, dict):
        raise LimitContextRuleError("limit_order_context_missing")
    if order.get("entry_order_type") != LIMIT_ORDER_TYPE:
        raise LimitContextRuleError("limit_context_supports_pullback_only")
    if not isinstance(activation_baseline, dict):
        raise LimitContextRuleError(
            "activation_baseline_must_be_an_object"
        )
    if (
        activation_baseline.get("model_version")
        != LIMIT_ACTIVATION_MODEL_VERSION
    ):
        raise LimitContextRuleError(
            "activation_baseline_version_mismatch"
        )
    if activation_baseline.get("analysis_id") != contract.get("analysis_id"):
        raise LimitContextRuleError("analysis_id_mismatch")
    probabilities = activation_baseline.get("probabilities")
    if not isinstance(probabilities, dict) or not math.isclose(
        math.fsum(
            _finite(value, "activation_probability")
            for value in probabilities.values()
        ),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise LimitContextRuleError("activation_probability_mass_invalid")
    sigma = _finite_positive(
        activation_baseline.get("inputs", {}).get("sigma_horizon"),
        "sigma_horizon",
    )
    analysis_at = str(
        contract.get("windows", {})
        .get("activation", {})
        .get("starts_at")
        or ""
    )
    if not analysis_at:
        raise LimitContextRuleError("analysis_at_missing")
    return order, sigma, analysis_at


def evaluate_activation_trajectory(
    traces: dict[str, dict],
    *,
    side: str,
    analysis_at: str,
) -> dict:
    required = [
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-MTF-HIERARCHY-001",
    ]
    optional = [
        "M4-RULE-VOLATILITY-RANK-001",
        "LIB-CAND-EMA-TREND-001",
        "LIB-CAND-RSI-WILDER-001",
    ]
    blocked = _blocked_parent_trace(
        rule_id=RULE_IDS[0],
        family_id="FAMILY-LIMIT-ACTIVATION-TRAJECTORY",
        required_parent_ids=required,
        traces=traces,
        executed_at=analysis_at,
    )
    if blocked:
        return blocked
    parent_ids = required + optional
    activation_sign = -_side_sign(side)
    reaction_sign = _side_sign(side)
    try:
        path = traces[required[0]]["outputs"]
        mtf = traces[required[1]]["outputs"]
        signed_path = _finite(
            path["signed_path_efficiency"],
            "signed_path_efficiency",
        )
        displacement = _finite(
            path["log_displacement"],
            "log_displacement",
        )
        efficiencies = mtf["signed_path_efficiencies"]
        activation_mtf = {
            window: activation_sign
            * _finite(efficiencies[window], f"mtf_{window}")
            for window in ("H", "2H", "4H")
        }
        reaction_mtf = {
            window: reaction_sign
            * _finite(efficiencies[window], f"mtf_{window}")
            for window in ("H", "2H", "4H")
        }
    except (KeyError, TypeError, LimitContextRuleError) as exc:
        return _trace(
            rule_id=RULE_IDS[0],
            family_id="FAMILY-LIMIT-ACTIVATION-TRAJECTORY",
            parent_rule_ids=parent_ids,
            inputs={"parent_trace_sha256": _parent_hashes(traces, parent_ids)},
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "trajectory_parent_output_invalid"],
            source_payload={parent: traces.get(parent) for parent in parent_ids},
            executed_at=analysis_at,
        )
    outputs: dict[str, Any] = {
        "activation_direction_sign": activation_sign,
        "reaction_direction_sign": reaction_sign,
        "raw_signed_path_efficiency_h": signed_path,
        "activation_adjusted_path_efficiency_h": (
            activation_sign * signed_path
        ),
        "reaction_adjusted_path_efficiency_h": reaction_sign * signed_path,
        "activation_path_relation": _relation(activation_sign * signed_path),
        "raw_log_displacement_h": displacement,
        "activation_adjusted_log_displacement_h": (
            activation_sign * displacement
        ),
        "reaction_adjusted_log_displacement_h": (
            reaction_sign * displacement
        ),
        "activation_adjusted_mtf_efficiencies": activation_mtf,
        "reaction_adjusted_mtf_efficiencies": reaction_mtf,
        "activation_mtf_toward_count": sum(
            value > 0 for value in activation_mtf.values()
        ),
        "activation_mtf_away_count": sum(
            value < 0 for value in activation_mtf.values()
        ),
        "aggregation_policy": "components_preserved_no_score",
    }
    volatility = _available_trace(traces, optional[0])
    if volatility:
        outputs["volatility_percentile_60"] = volatility["outputs"].get(
            "volatility_percentile"
        )
    ema = _available_trace(traces, optional[1])
    if ema:
        ema_outputs = ema["outputs"]
        slope = _finite(
            ema_outputs.get("ema50_slope_6bars_atr"),
            "ema50_slope_6bars_atr",
        )
        outputs["ema_slope_dual_role"] = {
            "raw": slope,
            "activation_adjusted": activation_sign * slope,
            "reaction_adjusted": reaction_sign * slope,
        }
    rsi = _available_trace(traces, optional[2])
    if rsi:
        centered = _finite(
            rsi["outputs"].get("centered_rsi"),
            "centered_rsi",
        )
        outputs["rsi_dual_role"] = {
            "raw": centered,
            "activation_adjusted": activation_sign * centered,
            "reaction_adjusted": reaction_sign * centered,
        }
    outputs["parent_availability"] = {
        parent: _available_trace(traces, parent) is not None
        for parent in parent_ids
    }
    return _trace(
        rule_id=RULE_IDS[0],
        family_id="FAMILY-LIMIT-ACTIVATION-TRAJECTORY",
        parent_rule_ids=parent_ids,
        inputs={
            "side": str(side).lower(),
            "parent_trace_sha256": _parent_hashes(traces, parent_ids),
        },
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload={parent: traces.get(parent) for parent in parent_ids},
        executed_at=analysis_at,
    )


def _dual_role(value: float, activation_sign: float, reaction_sign: float) -> dict:
    return {
        "raw": value,
        "activation_adjusted": activation_sign * value,
        "reaction_adjusted": reaction_sign * value,
    }


def evaluate_flow_dual_role(
    traces: dict[str, dict],
    *,
    side: str,
    analysis_at: str,
) -> dict:
    parent_ids = [
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
        "LIB-CAND-CVD-SLOPE-001",
        "LIB-CAND-ORDERBOOK-IMBALANCE-001",
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
        "M4-RULE-FUNDING-STATE-001",
        "LIB-CAND-FUNDING-PERCENTILE-001",
        "LIB-CAND-CROWDING-PERCENTILE-001",
    ]
    activation_sign = -_side_sign(side)
    reaction_sign = _side_sign(side)
    directional: dict[str, dict] = {}
    context: dict[str, Any] = {}
    try:
        aggressor = _available_trace(traces, parent_ids[0])
        if aggressor:
            directional["aggressor_imbalance_h"] = _dual_role(
                _finite(aggressor["outputs"].get("ATI_H"), "ATI_H"),
                activation_sign,
                reaction_sign,
            )
        cvd = _available_trace(traces, parent_ids[1])
        if cvd:
            directional["normalized_cvd_slope"] = _dual_role(
                _finite(
                    cvd["outputs"].get("normalized_cvd_slope"),
                    "normalized_cvd_slope",
                ),
                activation_sign,
                reaction_sign,
            )
            directional["terminal_taker_imbalance"] = _dual_role(
                _finite(
                    cvd["outputs"].get("terminal_taker_imbalance"),
                    "terminal_taker_imbalance",
                ),
                activation_sign,
                reaction_sign,
            )
        book = _available_trace(traces, parent_ids[2])
        if book:
            top20 = (
                book["outputs"].get("measures", {}).get("top_20", {})
            )
            directional["current_book_top20_imbalance"] = _dual_role(
                _finite(top20.get("imbalance"), "top20_imbalance"),
                activation_sign,
                reaction_sign,
            )
            context["current_book_spread_fraction"] = _finite(
                book["outputs"].get("spread_fraction"),
                "spread_fraction",
            )
        oi = _available_trace(traces, parent_ids[3])
        if oi:
            context["open_interest_log_change_h"] = _finite(
                oi["outputs"].get("dOI_H"),
                "dOI_H",
            )
        funding = _available_trace(traces, parent_ids[4])
        if funding:
            context["last_funding_rate"] = _finite(
                funding["outputs"].get("last_funding_rate"),
                "last_funding_rate",
            )
        funding_relative = _available_trace(traces, parent_ids[5])
        if funding_relative:
            context["funding_midrank_60"] = _finite(
                funding_relative["outputs"].get("funding_midrank_60"),
                "funding_midrank_60",
            )
        crowding = _available_trace(traces, parent_ids[6])
        if crowding:
            context["centered_crowding_midrank_60"] = _finite(
                crowding["outputs"].get(
                    "centered_crowding_midrank_60"
                ),
                "centered_crowding_midrank_60",
            )
    except (KeyError, TypeError, LimitContextRuleError) as exc:
        return _trace(
            rule_id=RULE_IDS[1],
            family_id="FAMILY-LIMIT-FLOW-DUAL-ROLE",
            parent_rule_ids=parent_ids,
            inputs={"parent_trace_sha256": _parent_hashes(traces, parent_ids)},
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "flow_parent_output_invalid"],
            source_payload={parent: traces.get(parent) for parent in parent_ids},
            executed_at=analysis_at,
        )
    if not directional and not context:
        return _trace(
            rule_id=RULE_IDS[1],
            family_id="FAMILY-LIMIT-FLOW-DUAL-ROLE",
            parent_rule_ids=parent_ids,
            inputs={"parent_trace_sha256": _parent_hashes(traces, parent_ids)},
            outputs={},
            status="blocked",
            reason_codes=["no_flow_or_derivatives_parent_available"],
            source_payload={parent: traces.get(parent) for parent in parent_ids},
            executed_at=analysis_at,
        )
    outputs = {
        "activation_direction_sign": activation_sign,
        "reaction_direction_sign": reaction_sign,
        "directional_components": directional,
        "non_directional_context": context,
        "order_book_semantics": (
            "current_price_snapshot_not_future_entry_zone_liquidity"
        ),
        "aggregation_policy": (
            "raw_components_reoriented_but_never_summed"
        ),
        "parent_availability": {
            parent: _available_trace(traces, parent) is not None
            for parent in parent_ids
        },
    }
    return _trace(
        rule_id=RULE_IDS[1],
        family_id="FAMILY-LIMIT-FLOW-DUAL-ROLE",
        parent_rule_ids=parent_ids,
        inputs={
            "side": str(side).lower(),
            "parent_trace_sha256": _parent_hashes(traces, parent_ids),
        },
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload={parent: traces.get(parent) for parent in parent_ids},
        executed_at=analysis_at,
    )


def _level_summary(level: object) -> dict | None:
    if not isinstance(level, dict):
        return None
    return {
        "type": level.get("type"),
        "price": _finite_positive(level.get("price"), "level_price"),
        "prominence_atr": _finite_non_negative(
            level.get("prominence_atr"),
            "prominence_atr",
        ),
        "distance_sigma_horizon": _finite(
            level.get("distance_sigma_horizon"),
            "distance_sigma_horizon",
        ),
    }


def evaluate_zone_structure(
    traces: dict[str, dict],
    *,
    side: str,
    analysis_at: str,
) -> dict:
    structural_id = "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001"
    fibonacci_id = "LIB-CAND-FIBONACCI-DISTANCE-001"
    parent_ids = [structural_id, fibonacci_id]
    blocked = _blocked_parent_trace(
        rule_id=RULE_IDS[2],
        family_id="FAMILY-LIMIT-ZONE-STRUCTURE",
        required_parent_ids=[structural_id],
        traces=traces,
        executed_at=analysis_at,
    )
    if blocked:
        return blocked
    normalized_side = str(side).lower()
    desired_key = "nearest_support" if normalized_side == "long" else "nearest_resistance"
    desired_type = "support" if normalized_side == "long" else "resistance"
    try:
        structural = traces[structural_id]["outputs"]
        desired_level = _level_summary(structural.get(desired_key))
        outputs: dict[str, Any] = {
            "desired_level_type": desired_type,
            "desired_level": desired_level,
            "zone_has_confirmed_desired_level": desired_level is not None,
            "confirmed_pivot_count": int(
                structural.get("confirmed_pivot_count", 0)
            ),
            "target_path_level_count": int(
                structural.get("target_path_level_count", 0)
            ),
            "adverse_path_level_count": int(
                structural.get("adverse_path_level_count", 0)
            ),
            "strongest_target_path_prominence_atr": structural.get(
                "strongest_target_path_prominence_atr"
            ),
            "strongest_adverse_path_prominence_atr": structural.get(
                "strongest_adverse_path_prominence_atr"
            ),
            "aggregation_policy": "components_preserved_no_zone_score",
        }
        fibonacci = _available_trace(traces, fibonacci_id)
        if fibonacci:
            fib_outputs = fibonacci["outputs"]
            nearest = fib_outputs.get("nearest_to_entry")
            outputs["fibonacci_at_entry"] = (
                {
                    "set": nearest.get("set"),
                    "ratio": nearest.get("ratio"),
                    "price": _finite_positive(
                        nearest.get("price"),
                        "fibonacci_price",
                    ),
                    "absolute_distance_sigma_horizon": _finite_non_negative(
                        nearest.get("absolute_distance_sigma_horizon"),
                        "fibonacci_distance_sigma",
                    ),
                }
                if isinstance(nearest, dict)
                else None
            )
            outputs["entry_retracement_fraction"] = _finite(
                fib_outputs.get("entry_retracement_fraction"),
                "entry_retracement_fraction",
            )
        else:
            outputs["fibonacci_at_entry"] = None
            outputs["entry_retracement_fraction"] = None
        outputs["zone_vector"] = {
            "desired_level_present": desired_level is not None,
            "desired_level_abs_distance_sigma": (
                abs(desired_level["distance_sigma_horizon"])
                if desired_level
                else None
            ),
            "desired_level_prominence_atr": (
                desired_level["prominence_atr"]
                if desired_level
                else None
            ),
            "fibonacci_abs_distance_sigma": (
                outputs["fibonacci_at_entry"][
                    "absolute_distance_sigma_horizon"
                ]
                if outputs["fibonacci_at_entry"]
                else None
            ),
            "target_path_level_count": outputs["target_path_level_count"],
            "adverse_path_level_count": outputs["adverse_path_level_count"],
        }
    except (KeyError, TypeError, ValueError, LimitContextRuleError) as exc:
        return _trace(
            rule_id=RULE_IDS[2],
            family_id="FAMILY-LIMIT-ZONE-STRUCTURE",
            parent_rule_ids=parent_ids,
            inputs={"parent_trace_sha256": _parent_hashes(traces, parent_ids)},
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "zone_parent_output_invalid"],
            source_payload={parent: traces.get(parent) for parent in parent_ids},
            executed_at=analysis_at,
        )
    return _trace(
        rule_id=RULE_IDS[2],
        family_id="FAMILY-LIMIT-ZONE-STRUCTURE",
        parent_rule_ids=parent_ids,
        inputs={
            "side": normalized_side,
            "parent_trace_sha256": _parent_hashes(traces, parent_ids),
        },
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload={parent: traces.get(parent) for parent in parent_ids},
        executed_at=analysis_at,
    )


def _normalized_clusters(
    rows: object,
    *,
    expected_position_side: str,
) -> list[dict]:
    if not isinstance(rows, list):
        raise LimitContextRuleError("liquidation_clusters_must_be_a_list")
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise LimitContextRuleError("liquidation_cluster_must_be_an_object")
        if str(row.get("position_side")) != expected_position_side:
            raise LimitContextRuleError("liquidation_position_side_mismatch")
        wallets = row.get("wallet_count")
        if wallets is not None:
            wallets = int(wallets)
            if wallets < 0:
                raise LimitContextRuleError("wallet_count_must_be_non_negative")
        result.append(
            {
                "position_side": expected_position_side,
                "price": _finite_positive(
                    row.get("price"),
                    f"liquidation_price_{index}",
                ),
                "notional_usd": _finite_non_negative(
                    row.get("notional_usd"),
                    f"liquidation_notional_{index}",
                ),
                "wallet_count": wallets,
            }
        )
    return result


def _liquidation_summary(
    rows: list[dict],
    *,
    entry: float,
    sigma_horizon: float,
) -> dict:
    nearest = (
        min(rows, key=lambda row: abs(math.log(row["price"] / entry)))
        if rows
        else None
    )
    return {
        "cluster_count": len(rows),
        "visible_notional_usd": math.fsum(
            row["notional_usd"] for row in rows
        ),
        "known_wallet_count": sum(
            int(row["wallet_count"])
            for row in rows
            if row["wallet_count"] is not None
        ),
        "nearest_to_entry": (
            {
                "position_side": nearest["position_side"],
                "price": nearest["price"],
                "notional_usd": nearest["notional_usd"],
                "distance_from_entry_abs_log_sigma": (
                    abs(math.log(nearest["price"] / entry))
                    / sigma_horizon
                ),
            }
            if nearest
            else None
        ),
    }


def evaluate_liquidation_path(
    liquidation_context: dict | None,
    *,
    order: dict,
    sigma_horizon: float,
    analysis_at: str,
) -> dict:
    context = liquidation_context or {}
    inputs = {
        "provider": context.get("provider"),
        "scope": context.get("scope"),
        "status": context.get("status"),
        "reason": context.get("reason"),
        "age_seconds": context.get("age_seconds"),
        "symbol": order.get("symbol"),
    }
    if not context or not context.get("available"):
        return _trace(
            rule_id=RULE_IDS[3],
            family_id="FAMILY-LIMIT-LIQUIDATION-PATH",
            parent_rule_ids=["LIB-CAND-LIQUIDATION-ZONE-001"],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[
                str(
                    context.get("reason")
                    or context.get("status")
                    or "liquidation_context_unavailable"
                )
            ],
            source_payload=context,
            executed_at=analysis_at,
        )
    side = str(order.get("side")).lower()
    current = _finite_positive(order.get("current_price"), "current_price")
    entry = _finite_positive(order.get("requested_entry"), "requested_entry")
    stop = _finite_positive(order.get("stop_loss"), "stop_loss")
    target = _finite_positive(order.get("take_profit"), "take_profit")
    try:
        longs = _normalized_clusters(
            context.get("clusters_below", []),
            expected_position_side="long",
        )
        shorts = _normalized_clusters(
            context.get("clusters_above", []),
            expected_position_side="short",
        )
        if side == "long":
            approach = [row for row in longs if entry <= row["price"] <= current]
            overshoot = [row for row in longs if stop <= row["price"] < entry]
            post_target = [row for row in shorts if entry < row["price"] <= target]
            approach_position_side = "long"
            target_position_side = "short"
        elif side == "short":
            approach = [row for row in shorts if current <= row["price"] <= entry]
            overshoot = [row for row in shorts if entry < row["price"] <= stop]
            post_target = [row for row in longs if target <= row["price"] < entry]
            approach_position_side = "short"
            target_position_side = "long"
        else:
            raise LimitContextRuleError("side_must_be_long_or_short")
    except (TypeError, ValueError, LimitContextRuleError) as exc:
        return _trace(
            rule_id=RULE_IDS[3],
            family_id="FAMILY-LIMIT-LIQUIDATION-PATH",
            parent_rule_ids=["LIB-CAND-LIQUIDATION-ZONE-001"],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "invalid_liquidation_context"],
            source_payload=context,
            executed_at=analysis_at,
        )
    approach_summary = _liquidation_summary(
        approach,
        entry=entry,
        sigma_horizon=sigma_horizon,
    )
    overshoot_summary = _liquidation_summary(
        overshoot,
        entry=entry,
        sigma_horizon=sigma_horizon,
    )
    target_summary = _liquidation_summary(
        post_target,
        entry=entry,
        sigma_horizon=sigma_horizon,
    )
    post_mass = (
        overshoot_summary["visible_notional_usd"]
        + target_summary["visible_notional_usd"]
    )
    outputs = {
        "provider": context.get("provider"),
        "scope": context.get("scope"),
        "schema": context.get("schema"),
        "as_of": context.get("as_of"),
        "age_seconds": context.get("age_seconds"),
        "approach_position_side": approach_position_side,
        "post_activation_target_position_side": target_position_side,
        "approach_path": approach_summary,
        "overshoot_path_entry_to_sl": overshoot_summary,
        "post_activation_target_path": target_summary,
        "target_fraction_of_visible_post_activation_mass": (
            target_summary["visible_notional_usd"] / post_mass
            if post_mass > 0
            else None
        ),
        "interpretation_policy": (
            "visible_mass_descriptor_not_causal_attraction_or_probability"
        ),
        "aggregation_policy": "compact_summaries_no_raw_heatmap_persistence",
    }
    return _trace(
        rule_id=RULE_IDS[3],
        family_id="FAMILY-LIMIT-LIQUIDATION-PATH",
        parent_rule_ids=["LIB-CAND-LIQUIDATION-ZONE-001"],
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload=context,
        executed_at=analysis_at,
    )


def evaluate_limit_context_rule_family(
    contract: dict,
    activation_baseline: dict,
    *,
    m5_analysis: dict | None,
    observational_traces: list[dict] | dict | None,
    liquidation_context: dict | None = None,
) -> dict:
    order, sigma_horizon, analysis_at = _validate_limit_inputs(
        contract,
        activation_baseline,
    )
    traces = _trace_map(m5_analysis or {}, observational_traces or [])
    results = [
        evaluate_activation_trajectory(
            traces,
            side=str(order["side"]),
            analysis_at=analysis_at,
        ),
        evaluate_flow_dual_role(
            traces,
            side=str(order["side"]),
            analysis_at=analysis_at,
        ),
        evaluate_zone_structure(
            traces,
            side=str(order["side"]),
            analysis_at=analysis_at,
        ),
        evaluate_liquidation_path(
            liquidation_context,
            order=order,
            sigma_horizon=sigma_horizon,
            analysis_at=analysis_at,
        ),
    ]
    evaluated_count = sum(
        trace["status"] == "evaluated_shadow" for trace in results
    )
    payload = {
        "runtime_version": RUNTIME_VERSION,
        "analysis_id": contract.get("analysis_id"),
        "contract_version": contract.get("contract_version"),
        "activation_model_version": activation_baseline.get(
            "model_version"
        ),
        "production_effect": "none_shadow_descriptors",
        "status": (
            "evaluated_shadow"
            if evaluated_count == len(results)
            else "partially_evaluated_shadow"
            if evaluated_count
            else "blocked"
        ),
        "rule_ids": list(RULE_IDS),
        "evaluated_rule_count": evaluated_count,
        "blocked_rule_count": len(results) - evaluated_count,
        "traces": results,
        "double_counting_policy": {
            "probability_effect": "none",
            "component_aggregation": "forbidden_until_coefficients_validated",
            "dual_role_signals": (
                "same_raw_signal_reoriented_for_activation_and_reaction"
            ),
        },
    }
    payload["runtime_trace_sha256"] = canonical_sha256(payload)
    return payload


__all__ = (
    "RULE_IDS",
    "RUNTIME_VERSION",
    "LimitContextRuleError",
    "canonical_sha256",
    "evaluate_activation_trajectory",
    "evaluate_flow_dual_role",
    "evaluate_limit_context_rule_family",
    "evaluate_liquidation_path",
    "evaluate_zone_structure",
)
