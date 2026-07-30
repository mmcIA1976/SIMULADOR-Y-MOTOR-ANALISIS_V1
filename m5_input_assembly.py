from __future__ import annotations

import math
from typing import Any

from data_quality_gate import validate_pretrade_candles
from m8_evaluation import (
    PROFILE_INTERVALS_SECONDS,
    kline_fingerprint,
    parse_utc,
    payload_sha256,
    selected_interval_seconds,
)


RULE_IDS = (
    "M4-RULE-HORIZON-SAMPLING-001",
    "M4-RULE-PLAN-GEOMETRY-001",
    "M4-RULE-LOG-RETURNS-001",
    "M4-RULE-REALIZED-VOLATILITY-001",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
    "M4-RULE-PENDING-ACTIVATION-001",
    "M4-RULE-EXPONENTIAL-SMOOTHER-001",
    "M4-RULE-PATH-STRUCTURE-001",
    "M4-RULE-PRIOR-EXTREMA-001",
    "M4-RULE-VOLATILITY-RANK-001",
    "M4-RULE-MTF-HIERARCHY-001",
    "M4-RULE-CONTINUOUS-REGIME-001",
    "M4-RULE-AGGRESSOR-IMBALANCE-001",
    "M4-RULE-OPEN-INTEREST-CHANGE-001",
    "M4-RULE-PRICE-OI-STATE-001",
    "M4-RULE-SPOT-FUTURES-BASIS-001",
    "M4-RULE-MARK-INDEX-PREMIUM-001",
    "M4-RULE-FUNDING-STATE-001",
    "M4-RULE-DERIVATIVES-CONTEXT-001",
    "M4-RULE-QUOTED-SPREAD-001",
    "M4-RULE-DEPTH-SWEEP-001",
    "M4-RULE-FEE-SCENARIOS-001",
    "M4-RULE-FUNDING-CASHFLOW-001",
    "M4-RULE-PLAN-EXPOSURE-001",
    "M4-RULE-NET-PAYOFFS-001",
    "M4-RULE-EXPECTED-VALUE-001",
    "M4-RULE-EVALUATION-READINESS-001",
)


def _returns(closes: list[float]) -> list[float]:
    return [
        math.log(current / previous)
        for previous, current in zip(closes, closes[1:])
    ]


def _signed_efficiency(values: list[float]) -> float:
    displacement = math.fsum(values)
    variation = math.fsum(abs(value) for value in values)
    return displacement / variation if variation > 0 else 0.0


def _closed_material(plan: dict, candles: list[dict]) -> dict:
    analysis_at = parse_utc(plan["analysis_at"])
    if analysis_at is None:
        raise ValueError("analysis_timestamp_invalid")
    analysis_ms = int(analysis_at.timestamp() * 1000)
    interval_seconds = selected_interval_seconds(
        plan["time_horizon"],
        int(plan["horizon_seconds"]),
    )
    return_count = int(plan["horizon_seconds"]) // interval_seconds
    required_returns = 61 * return_count
    data_quality = validate_pretrade_candles(
        candles,
        analysis_at=plan["analysis_at"],
        analysis_at_ms=analysis_ms,
        interval_seconds=interval_seconds,
        required_candle_count=required_returns + 1,
    )
    selected = data_quality.pop("selected_candles")
    closes = [float(row["close"]) for row in selected]
    returns = _returns(closes)
    current_returns = returns[-return_count:]
    current_bars = selected[-return_count:]
    reference_variances = [
        math.fsum(
            value * value
            for value in returns[index : index + return_count]
        )
        for index in range(0, 60 * return_count, return_count)
    ]
    return {
        "analysis_ms": analysis_ms,
        "interval_seconds": interval_seconds,
        "return_count": return_count,
        "selected": selected,
        "current_bars": current_bars,
        "current_returns": current_returns,
        "current_variance": math.fsum(
            value * value for value in current_returns
        ),
        "reference_variances": reference_variances,
        "signed_efficiencies": {
            "H": _signed_efficiency(returns[-return_count:]),
            "2H": _signed_efficiency(returns[-2 * return_count :]),
            "4H": _signed_efficiency(returns[-4 * return_count :]),
        },
        "data_cutoff_at_ms": int(selected[-1]["close_time_ms"]),
        "data_sha256": kline_fingerprint(selected),
        "data_quality": data_quality,
    }


def _periodic_taker_input(
    material: dict,
    live_context: dict,
) -> dict:
    interval_ms = material["interval_seconds"] * 1000
    expected_count = int(material["return_count"])
    expected_start = int(material["current_bars"][0]["open_time_ms"])
    expected_end = int(material["current_bars"][-1]["close_time_ms"])
    normalized = []
    for raw in live_context.get("taker_history", []):
        try:
            timestamp = int(raw["timestamp"])
            buy = float(raw["buyVol"])
            sell = float(raw["sellVol"])
        except (KeyError, TypeError, ValueError):
            continue
        if expected_start - 1 <= timestamp <= expected_end:
            normalized.append((timestamp, buy, sell))
    normalized.sort()
    timestamps = [item[0] for item in normalized]
    continuous = (
        len(normalized) == expected_count
        and abs(timestamps[0] - expected_start) <= 1
        and all(
            right - left == interval_ms
            for left, right in zip(timestamps, timestamps[1:])
        )
    )
    if continuous:
        periods = [
            {"buy_volume": buy, "sell_volume": sell}
            for _, buy, sell in normalized
        ]
        coverage_start = timestamps[0]
        coverage_end = timestamps[-1] + interval_ms
        return {
            "ati_source": "periodic",
            "periods": periods,
            "activity_unit": "base_asset_volume",
            "window_start_ms": coverage_start,
            "window_end_ms": coverage_end,
            "coverage_start_ms": coverage_start,
            "coverage_end_ms": coverage_end,
        }

    candle_periods = []
    for row in material["current_bars"]:
        quote = row.get("quote_volume")
        taker_buy = row.get("taker_buy_quote_volume")
        if quote is None or taker_buy is None:
            candle_periods = []
            break
        candle_periods.append(
            {
                "buy_volume": float(taker_buy),
                "sell_volume": max(float(quote) - float(taker_buy), 0.0),
            }
        )
    return {
        "ati_source": "periodic",
        "periods": candle_periods,
        "activity_unit": "quote_asset_volume_from_closed_klines",
        "window_start_ms": expected_start,
        "window_end_ms": expected_end,
        "coverage_start_ms": expected_start if candle_periods else 0,
        "coverage_end_ms": expected_end if candle_periods else 0,
    }


def _open_interest_input(material: dict, live_context: dict) -> dict:
    horizon_ms = int(live_context["horizon_seconds"]) * 1000
    cutoff = material["data_cutoff_at_ms"]
    rows = []
    for raw in live_context.get("open_interest_history", []):
        try:
            rows.append(
                (
                    int(raw["timestamp"]),
                    float(raw["sumOpenInterest"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    rows = sorted(
        (timestamp, value)
        for timestamp, value in rows
        if timestamp <= cutoff and value > 0
    )
    if not rows:
        return {}
    current_time, current_value = rows[-1]
    previous_target = current_time - horizon_ms
    previous = next(
        (
            (timestamp, value)
            for timestamp, value in rows
            if timestamp == previous_target
        ),
        None,
    )
    if previous is None:
        return {}
    return {
        "previous_timestamp_ms": previous[0],
        "current_timestamp_ms": current_time,
        "horizon_seconds": int(live_context["horizon_seconds"]),
        "previous_open_interest": previous[1],
        "current_open_interest": current_value,
    }


def _funding_interval_hours(live_context: dict) -> float | None:
    info = live_context.get("funding_info") or {}
    try:
        value = float(info["fundingIntervalHours"])
        if value > 0:
            return value
    except (KeyError, TypeError, ValueError):
        pass
    times = sorted(
        {
            int(row["fundingTime"])
            for row in live_context.get("funding_history", [])
            if isinstance(row, dict) and row.get("fundingTime") is not None
        }
    )
    gaps = [
        (right - left) / 3_600_000
        for left, right in zip(times, times[1:])
        if right > left
    ]
    if gaps and all(math.isclose(gap, gaps[-1]) for gap in gaps[-3:]):
        return gaps[-1]
    return None


def _funding_inputs(material: dict, live_context: dict) -> tuple[dict, dict]:
    snapshot = live_context.get("funding_snapshot") or {}
    interval_hours = _funding_interval_hours(live_context)
    if interval_hours is None:
        return {}, {}
    now_ms = int(material["data_cutoff_at_ms"])
    horizon_ms = int(live_context["horizon_seconds"]) * 1000
    previous_events = []
    for raw in live_context.get("funding_history", []):
        try:
            previous_events.append(
                {
                    "time_ms": int(raw["fundingTime"]),
                    "rate": float(raw["fundingRate"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    try:
        next_funding = int(snapshot["nextFundingTime"])
        last_rate = float(snapshot["lastFundingRate"])
    except (KeyError, TypeError, ValueError):
        return {}, {}
    interval_ms = int(interval_hours * 3_600_000)
    scheduled = []
    cursor = next_funding
    while cursor <= now_ms + horizon_ms and interval_ms > 0:
        if cursor > now_ms:
            scheduled.append(cursor)
        cursor += interval_ms
    state = {
        "last_funding_rate": last_rate,
        "funding_interval_hours": interval_hours,
        "current_time_ms": now_ms,
        "horizon_seconds": int(live_context["horizon_seconds"]),
        "previous_events": previous_events,
        "scheduled_event_times_ms": scheduled,
    }
    return state, {
        "scheduled_event_count": len(scheduled),
        "events": [],
    }


def _book_inputs(
    plan: dict,
    live_context: dict,
) -> tuple[dict, dict, dict]:
    futures_book = live_context.get("futures_book") or {}
    spot_book = live_context.get("spot_book") or {}
    try:
        f_bid = float(futures_book["bidPrice"])
        f_ask = float(futures_book["askPrice"])
        f_received = int(futures_book["receivedAt"])
    except (KeyError, TypeError, ValueError):
        f_bid = f_ask = 0.0
        f_received = 0
    try:
        s_bid = float(spot_book["bidPrice"])
        s_ask = float(spot_book["askPrice"])
        s_received = int(spot_book["receivedAt"])
    except (KeyError, TypeError, ValueError):
        s_bid = s_ask = 0.0
        s_received = 0
    spot_status = None
    for item in (live_context.get("spot_info") or {}).get("symbols", []):
        if (
            isinstance(item, dict)
            and str(item.get("symbol", "")).upper()
            == str(plan["symbol"]).upper()
        ):
            spot_status = str(item.get("status") or "").upper()
            break
    basis = {
        "futures_bid": f_bid,
        "futures_ask": f_ask,
        "spot_bid": s_bid,
        "spot_ask": s_ask,
        "futures_received_at_ms": f_received,
        "spot_received_at_ms": s_received,
        "spot_symbol_status": spot_status,
    }
    spread = {
        "best_bid": f_bid,
        "best_ask": f_ask,
        "receive_time": f_received,
        "capture_time": int(live_context.get("captured_at_ms") or f_received),
        "max_age_ms": 30_000,
    }
    depth = live_context.get("depth") or {}
    entry = float(plan["entry"])
    margin = float(plan["margin"])
    leverage = float(plan["leverage"])
    return basis, spread, {
        "side": "buy" if plan["side"] == "long" else "sell",
        "base_quantity": margin * leverage / entry,
        "arrival_mid": (f_bid + f_ask) / 2 if f_bid and f_ask else 0.0,
        "receive_time": int(
            depth.get("receivedAt")
            or live_context.get("captured_at_ms")
            or f_received
        ),
        "capture_time": int(
            live_context.get("captured_at_ms")
            or depth.get("receivedAt")
            or f_received
        ),
        "max_age_ms": 30_000,
        "bids": [
            {"price": float(row[0]), "quantity": float(row[1])}
            for row in depth.get("bids", [])
            if isinstance(row, (list, tuple)) and len(row) >= 2
        ],
        "asks": [
            {"price": float(row[0]), "quantity": float(row[1])}
            for row in depth.get("asks", [])
            if isinstance(row, (list, tuple)) and len(row) >= 2
        ],
    }


def _mark_index_input(live_context: dict) -> dict:
    snapshot = live_context.get("funding_snapshot") or {}
    try:
        provider_time = int(snapshot["time"])
    except (KeyError, TypeError, ValueError):
        provider_time = int(live_context.get("captured_at_ms") or 0)
    return {
        "mark_price": snapshot.get("markPrice"),
        "index_price": snapshot.get("indexPrice"),
        "provider_time": provider_time,
    }


def _default_readiness(probability_status: str = "blocked") -> dict:
    return {
        "market_probabilities": probability_status,
        "entry_execution": "blocked",
        "exit_execution": "blocked",
        "fees": "blocked",
        "funding": "blocked",
        "payoffs": "blocked",
        "account_risk": "blocked",
    }


def build_rule_inputs(
    *,
    plan: dict,
    candles: list[dict],
    live_context: dict | None,
    probabilities: dict[str, float] | None = None,
    readiness_statuses: dict[str, str] | None = None,
    prevalidated_material: dict | None = None,
) -> tuple[dict[str, dict], dict, dict[str, tuple[dict, ...]]]:
    if prevalidated_material is not None:
        quality = prevalidated_material.get("data_quality", {})
        if (
            quality.get("status") != "valid"
            or quality.get("validation_pass_count") != 1
            or not quality.get("report_sha256")
        ):
            raise ValueError("prevalidated_material_quality_invalid")
        material = prevalidated_material
    else:
        material = _closed_material(plan, candles)
    current = material["current_bars"]
    interval_seconds = material["interval_seconds"]
    closes = [
        {
            "close": row["close"],
            "close_time": row["close_time_ms"],
            "closed": True,
        }
        for row in material["selected"][-(material["return_count"] + 1) :]
    ]
    bars = [
        {"high": row["high"], "low": row["low"]}
        for row in current
    ]
    context = live_context or {
        "horizon_seconds": int(plan["horizon_seconds"]),
        "interval_seconds": interval_seconds,
    }
    basis, spread, depth = _book_inputs(plan, context)
    funding_state, funding_cashflow = _funding_inputs(material, context)
    mark_index = _mark_index_input(context)
    oi = _open_interest_input(material, context)
    taker = _periodic_taker_input(material, context)
    notional = float(plan["margin"]) * float(plan["leverage"])
    quantity = notional / float(plan["entry"])
    rules = {
        "M4-RULE-HORIZON-SAMPLING-001": {
            "time_horizon": plan["time_horizon"],
            "horizon_seconds": plan["horizon_seconds"],
            "profile_intervals_seconds": list(
                PROFILE_INTERVALS_SECONDS[plan["time_horizon"]]
            ),
        },
        "M4-RULE-PLAN-GEOMETRY-001": {
            "side": plan["side"],
            "entry": plan["entry"],
            "take_profit": plan["take_profit"],
            "stop_loss": plan["stop_loss"],
        },
        "M4-RULE-LOG-RETURNS-001": {
            "interval_seconds": interval_seconds,
            "closes": closes,
            "prevalidated_data_quality": {
                "status": material["data_quality"]["status"],
                "validation_pass_count": material["data_quality"][
                    "validation_pass_count"
                ],
                "report_sha256": material["data_quality"]["report_sha256"],
                "source_data_sha256": material["data_quality"][
                    "source_data_sha256"
                ],
                "interval_seconds": interval_seconds,
            },
        },
        "M4-RULE-REALIZED-VOLATILITY-001": {},
        "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": {},
        "M4-RULE-PENDING-ACTIVATION-001": {
            "entry_type": plan["entry_type"],
            "entry": plan["entry"],
            "current_price": plan["entry"],
        },
        "M4-RULE-EXPONENTIAL-SMOOTHER-001": {
            "values": material["current_returns"],
            "alpha": None,
        },
        "M4-RULE-PATH-STRUCTURE-001": {
            "window_seconds": plan["horizon_seconds"],
        },
        "M4-RULE-PRIOR-EXTREMA-001": {
            "bars": bars,
            "side": plan["side"],
            "entry": plan["entry"],
            "take_profit": plan["take_profit"],
        },
        "M4-RULE-VOLATILITY-RANK-001": {
            "current_realized_variance": material["current_variance"],
            "reference_variances": material["reference_variances"],
            "reference_cutoff": material["data_cutoff_at_ms"],
        },
        "M4-RULE-MTF-HIERARCHY-001": {
            "signed_path_efficiencies": material["signed_efficiencies"],
        },
        "M4-RULE-CONTINUOUS-REGIME-001": {},
        "M4-RULE-AGGRESSOR-IMBALANCE-001": taker,
        "M4-RULE-OPEN-INTEREST-CHANGE-001": oi,
        "M4-RULE-PRICE-OI-STATE-001": {},
        "M4-RULE-SPOT-FUTURES-BASIS-001": basis,
        "M4-RULE-MARK-INDEX-PREMIUM-001": mark_index,
        "M4-RULE-FUNDING-STATE-001": funding_state,
        "M4-RULE-DERIVATIVES-CONTEXT-001": {
            "basis_source": (
                "spot_futures"
                if all(basis.get(key) for key in (
                    "futures_bid",
                    "futures_ask",
                    "spot_bid",
                    "spot_ask",
                ))
                else "mark_index"
            ),
        },
        "M4-RULE-QUOTED-SPREAD-001": spread,
        "M4-RULE-DEPTH-SWEEP-001": depth,
        "M4-RULE-FEE-SCENARIOS-001": {
            "notional": notional,
            "commission_rates": {},
            "allowed_roles": ["taker"],
            "observed_execution": False,
        },
        "M4-RULE-FUNDING-CASHFLOW-001": {
            "side": plan["side"],
            "base_quantity": quantity,
            **funding_cashflow,
        },
        "M4-RULE-PLAN-EXPOSURE-001": {
            "side": plan["side"],
            "entry": plan["entry"],
            "take_profit": plan["take_profit"],
            "stop_loss": plan["stop_loss"],
            "margin": plan["margin"],
            "leverage": plan["leverage"],
        },
        "M4-RULE-NET-PAYOFFS-001": {},
        "M4-RULE-EXPECTED-VALUE-001": {
            "m6_probabilities_authorized": probabilities is not None,
            "probabilities": probabilities or {},
            "net_payoffs": {},
        },
        "M4-RULE-EVALUATION-READINESS-001": {
            "statuses": readiness_statuses or _default_readiness(
                "available" if probabilities is not None else "blocked"
            ),
        },
    }
    if set(rules) != set(RULE_IDS):
        raise ValueError("m5_rule_input_coverage_invalid")

    candle_observation = (
        {
            "provider": "binance_usdm_futures",
            "dataset": "closed_klines",
            "data_cutoff_at_ms": material["data_cutoff_at_ms"],
            "interval_seconds": interval_seconds,
            "source_sha256": material["data_sha256"],
        },
    )
    live_observation = (
        {
            "provider": "binance_public_market_data",
            "dataset": "m5_live_context",
            "request_cutoff_at": context.get("request_cutoff_at"),
            "captured_at_ms": context.get("captured_at_ms"),
            "source_sha256": payload_sha256(context),
        },
    )
    source_observations = {
        rule_id: candle_observation
        for rule_id in (
            "M4-RULE-HORIZON-SAMPLING-001",
            "M4-RULE-LOG-RETURNS-001",
            "M4-RULE-REALIZED-VOLATILITY-001",
            "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-PRIOR-EXTREMA-001",
            "M4-RULE-VOLATILITY-RANK-001",
            "M4-RULE-MTF-HIERARCHY-001",
            "M4-RULE-CONTINUOUS-REGIME-001",
        )
    }
    for rule_id in (
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
        "M4-RULE-PRICE-OI-STATE-001",
        "M4-RULE-SPOT-FUTURES-BASIS-001",
        "M4-RULE-MARK-INDEX-PREMIUM-001",
        "M4-RULE-FUNDING-STATE-001",
        "M4-RULE-DERIVATIVES-CONTEXT-001",
        "M4-RULE-QUOTED-SPREAD-001",
        "M4-RULE-DEPTH-SWEEP-001",
    ):
        source_observations[rule_id] = live_observation
    return rules, material, source_observations


def trace_map(m5_analysis: dict) -> dict[str, dict]:
    return {
        trace["rule_id"]: trace
        for trace in m5_analysis.get("traces", [])
        if isinstance(trace, dict) and trace.get("rule_id")
    }


def candidate_features_from_m5(
    m5_analysis: dict,
    *,
    side: str,
) -> dict[str, float]:
    traces = trace_map(m5_analysis)
    required = {
        "M4-RULE-PATH-STRUCTURE-001",
        "M4-RULE-PRIOR-EXTREMA-001",
        "M4-RULE-VOLATILITY-RANK-001",
        "M4-RULE-MTF-HIERARCHY-001",
    }
    unavailable = sorted(
        rule_id
        for rule_id in required
        if traces.get(rule_id, {}).get("status") != "evaluated"
    )
    if unavailable:
        raise ValueError(
            "candidate_source_rules_unavailable:" + ",".join(unavailable)
        )
    direction = 1.0 if str(side).lower() == "long" else -1.0
    path = traces["M4-RULE-PATH-STRUCTURE-001"]["outputs"]
    extrema = traces["M4-RULE-PRIOR-EXTREMA-001"]["outputs"]
    rank = traces["M4-RULE-VOLATILITY-RANK-001"]["outputs"]
    mtf = traces["M4-RULE-MTF-HIERARCHY-001"]["outputs"][
        "signed_path_efficiencies"
    ]
    return {
        "directional_path_efficiency_h": (
            direction * float(path["signed_path_efficiency"])
        ),
        "directional_path_efficiency_2h": direction * float(mtf["2H"]),
        "directional_path_efficiency_4h": direction * float(mtf["4H"]),
        "volatility_percentile_60": float(rank["volatility_percentile"]),
        "target_extreme_between_entry_and_tp": (
            1.0
            if extrema["target_extreme_between_entry_and_tp"]
            else 0.0
        ),
    }


def rule_effect_registry(
    m5_analysis: dict,
    *,
    coefficient_artifact: dict,
) -> dict[str, dict]:
    traces = trace_map(m5_analysis)
    baseline_rules = {
        "M4-RULE-HORIZON-SAMPLING-001",
        "M4-RULE-PLAN-GEOMETRY-001",
        "M4-RULE-LOG-RETURNS-001",
        "M4-RULE-REALIZED-VOLATILITY-001",
        "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
    }
    feature_rules = {
        "M4-RULE-PATH-STRUCTURE-001": [
            "directional_path_efficiency_h"
        ],
        "M4-RULE-PRIOR-EXTREMA-001": [
            "target_extreme_between_entry_and_tp"
        ],
        "M4-RULE-VOLATILITY-RANK-001": [
            "volatility_percentile_60"
        ],
        "M4-RULE-MTF-HIERARCHY-001": [
            "directional_path_efficiency_2h",
            "directional_path_efficiency_4h",
        ],
    }
    candidate_without_coefficients = {
        "M4-RULE-CONTINUOUS-REGIME-001",
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
        "M4-RULE-PRICE-OI-STATE-001",
        "M4-RULE-SPOT-FUTURES-BASIS-001",
        "M4-RULE-MARK-INDEX-PREMIUM-001",
        "M4-RULE-FUNDING-STATE-001",
        "M4-RULE-DERIVATIVES-CONTEXT-001",
    }
    economic_rules = {
        "M4-RULE-QUOTED-SPREAD-001",
        "M4-RULE-DEPTH-SWEEP-001",
        "M4-RULE-FEE-SCENARIOS-001",
        "M4-RULE-FUNDING-CASHFLOW-001",
        "M4-RULE-PLAN-EXPOSURE-001",
        "M4-RULE-NET-PAYOFFS-001",
        "M4-RULE-EXPECTED-VALUE-001",
        "M4-RULE-EVALUATION-READINESS-001",
    }
    result = {}
    for rule_id in RULE_IDS:
        trace = traces.get(rule_id, {})
        item = {
            "rule_status": trace.get("status", "missing"),
            "reason_codes": trace.get("reason_codes", ()),
            "probability_effect": "none",
            "probability_effect_reason": None,
            "features": [],
        }
        if rule_id in baseline_rules:
            item["probability_effect"] = "baseline_input"
            item["probability_effect_reason"] = (
                "double_barrier_geometry_or_volatility"
            )
        elif rule_id in feature_rules:
            item["features"] = feature_rules[rule_id]
            coefficients = {
                name: {
                    "tp": float(
                        coefficient_artifact["coefficients"]["tp"][name]
                    ),
                    "sl": float(
                        coefficient_artifact["coefficients"]["sl"][name]
                    ),
                }
                for name in feature_rules[rule_id]
            }
            item["coefficients"] = coefficients
            active = any(
                value["tp"] != 0.0 or value["sl"] != 0.0
                for value in coefficients.values()
            )
            item["probability_effect"] = (
                "fitted_competing_risk_covariate"
                if active
                else "zero"
            )
            item["probability_effect_reason"] = (
                "estimated_candidate_coefficient"
                if active
                else "fitted_coefficients_are_zero"
            )
        elif rule_id in candidate_without_coefficients:
            item["probability_effect"] = "zero"
            item["probability_effect_reason"] = (
                "no_validated_coefficient_in_active_artifact"
            )
        elif rule_id in economic_rules:
            item["probability_effect"] = "separate_economic_layer"
            item["probability_effect_reason"] = (
                "contract_forbids_changing_physical_market_probability"
            )
        elif rule_id == "M4-RULE-PENDING-ACTIVATION-001":
            item["probability_effect"] = "applicability_gate"
            item["probability_effect_reason"] = "market_entry_only"
        elif rule_id == "M4-RULE-EXPONENTIAL-SMOOTHER-001":
            item["probability_effect"] = "none"
            item["probability_effect_reason"] = "no_alpha_approved"
        result[rule_id] = item
    return result
