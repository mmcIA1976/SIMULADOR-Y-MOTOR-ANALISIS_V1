from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Callable

from m5_runtime import (
    RuleBlocked,
    RuleDeferred,
    RuleNotApplicable,
    RuleTrace,
    require_choice,
    require_finite,
    require_mapping,
    require_non_negative,
    require_positive,
    require_sequence,
    require_timestamp_ms,
    run_rule,
)


ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = (
    ROOT / "auditorias_motor" / "contrato_implementacion_m5_1_v0_1.json"
)
RULES_VERSION = "M5-rules-v0.1"


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def side_sign(value: object) -> int:
    return 1 if require_choice(value, "side", {"long", "short"}) == "long" else -1


def sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def parent_output(dependencies: dict[str, RuleTrace], rule_id: str) -> dict:
    try:
        return dependencies[rule_id].outputs
    except KeyError as exc:
        raise RuleBlocked(
            "missing_dependency",
            f"required dependency {rule_id} is absent",
        ) from exc


def horizon_sampling(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    horizon = int(require_positive(inputs.get("horizon_seconds"), "horizon_seconds"))
    intervals = sorted(
        {
            int(require_positive(value, "profile_interval"))
            for value in require_sequence(
                inputs.get("profile_intervals_seconds"),
                "profile_intervals_seconds",
            )
        }
    )
    valid = [
        interval
        for interval in intervals
        if horizon % interval == 0 and horizon // interval >= 24
    ]
    if not valid:
        raise RuleNotApplicable(
            "no_exact_supported_interval",
            "no interval divides the horizon with at least 24 returns",
        )
    interval = max(valid)
    return {
        "time_horizon": str(inputs.get("time_horizon") or "custom"),
        "horizon_seconds": horizon,
        "interval": str(inputs.get("interval_labels", {}).get(str(interval), interval)),
        "interval_seconds": interval,
        "returns_per_horizon": horizon // interval,
        "selection_policy": "largest_exact_divisor_with_minimum_24_returns",
    }


def plan_geometry(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    direction = side_sign(inputs.get("side"))
    entry = require_positive(inputs.get("entry"), "entry")
    take_profit = require_positive(inputs.get("take_profit"), "take_profit")
    stop_loss = require_positive(inputs.get("stop_loss"), "stop_loss")
    tp_distance = direction * math.log(take_profit / entry)
    sl_distance = -direction * math.log(stop_loss / entry)
    if tp_distance <= 0 or sl_distance <= 0:
        raise RuleNotApplicable(
            "invalid_barrier_order",
            "TP and SL must be on their directional sides of entry",
        )
    return {
        "side_sign": direction,
        "entry": entry,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "tp_log_distance": tp_distance,
        "sl_log_distance": sl_distance,
    }


def log_returns(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    closes = require_sequence(inputs.get("closes"), "closes", minimum=2)
    interval_seconds = int(
        require_positive(inputs.get("interval_seconds"), "interval_seconds")
    )
    values = []
    times = []
    for index, item in enumerate(closes):
        row = require_mapping(item, f"closes_{index}")
        if row.get("closed") is not True:
            raise RuleBlocked("open_kline", "all klines must be closed")
        values.append(require_positive(row.get("close"), f"close_{index}"))
        times.append(require_timestamp_ms(row.get("close_time"), f"close_time_{index}"))
    expected_gap = interval_seconds * 1000
    if any(right - left != expected_gap for left, right in zip(times, times[1:])):
        raise RuleBlocked("gapped_klines", "closed klines must be consecutive")
    returns = [
        math.log(current / previous)
        for previous, current in zip(values, values[1:])
    ]
    return {
        "close_count": len(values),
        "return_count": len(returns),
        "first_close_time": times[0],
        "last_close_time": times[-1],
        "return_series": returns,
        "return_series_hash": canonical_hash(returns),
    }


def realized_volatility(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    returns_output = parent_output(
        dependencies,
        "M4-RULE-LOG-RETURNS-001",
    )
    sampling = parent_output(
        dependencies,
        "M4-RULE-HORIZON-SAMPLING-001",
    )
    returns = require_sequence(
        returns_output.get("return_series"),
        "return_series",
        minimum=24,
    )
    required_count = int(sampling["returns_per_horizon"])
    if len(returns) != required_count:
        raise RuleBlocked(
            "inexact_previous_horizon",
            "return count must equal the selected exact horizon",
        )
    variance = sum(require_finite(value, "return") ** 2 for value in returns)
    volatility = math.sqrt(variance)
    return {
        "interval": sampling["interval"],
        "horizon_seconds": sampling["horizon_seconds"],
        "return_count": len(returns),
        "window_start_close_time": returns_output["first_close_time"],
        "window_end_close_time": returns_output["last_close_time"],
        "realized_variance": variance,
        "realized_volatility": volatility,
        "forecast_status": "previous_horizon_observation_not_forecast",
    }


def normalized_barrier_geometry(
    inputs: dict,
    dependencies: dict[str, RuleTrace],
) -> dict:
    geometry = parent_output(
        dependencies,
        "M4-RULE-PLAN-GEOMETRY-001",
    )
    volatility = parent_output(
        dependencies,
        "M4-RULE-REALIZED-VOLATILITY-001",
    )
    sigma = require_positive(
        volatility.get("realized_volatility"),
        "sigma_prev_horizon",
    )
    d_tp = require_positive(geometry.get("tp_log_distance"), "tp_log_distance")
    d_sl = require_positive(geometry.get("sl_log_distance"), "sl_log_distance")
    return {
        "tp_log_distance": d_tp,
        "sl_log_distance": d_sl,
        "sigma_prev_horizon": sigma,
        "z_tp": d_tp / sigma,
        "z_sl": d_sl / sigma,
        "distance_balance_log_ratio": math.log(d_tp / d_sl),
    }


def pending_activation(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    entry_type = require_choice(
        inputs.get("entry_type", "market"),
        "entry_type",
        {"market", "limit", "stop_market", "stop_limit"},
    )
    entry = require_positive(inputs.get("entry"), "entry")
    current = require_positive(inputs.get("current_price", entry), "current_price")
    if entry_type != "market":
        raise RuleDeferred(
            "pending_order_branch_deferred",
            "M5 currently admits only MARKET entries",
        )
    return {
        "entry_type": "market",
        "trigger_condition": None,
        "entry_order_type": "market",
        "current_price": current,
        "entry": entry,
        "entry_log_distance": 0.0,
        "z_entry": 0.0,
        "activation_status": "immediate_market",
    }


def exponential_smoother(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    if inputs.get("alpha") is None:
        raise RuleNotApplicable(
            "alpha_not_approved",
            "M4 does not approve a smoothing alpha or EMA period",
        )
    values = [
        require_finite(value, "smoother_value")
        for value in require_sequence(inputs.get("values"), "values")
    ]
    alpha = require_positive(inputs.get("alpha"), "alpha")
    if alpha > 1:
        raise RuleBlocked("invalid_alpha", "alpha must be <= 1")
    smoothed = values[0]
    for value in values[1:]:
        smoothed = alpha * value + (1 - alpha) * smoothed
    return {
        "alpha": alpha,
        "initialization": values[0],
        "input_count": len(values),
        "smoothed_value": smoothed,
        "smoothed_series_last": smoothed,
    }


def path_structure(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    returns = require_sequence(
        parent_output(
            dependencies,
            "M4-RULE-LOG-RETURNS-001",
        ).get("return_series"),
        "return_series",
    )
    displacement = sum(require_finite(value, "return") for value in returns)
    variation = sum(abs(require_finite(value, "return")) for value in returns)
    if variation == 0:
        efficiency = 0.0
        signed_efficiency = 0.0
        descriptor = "flat"
        flat = True
    else:
        efficiency = abs(displacement) / variation
        signed_efficiency = displacement / variation
        descriptor = "positive" if displacement > 0 else "negative"
        flat = False
    return {
        "window_seconds": int(
            require_positive(inputs.get("window_seconds"), "window_seconds")
        ),
        "return_count": len(returns),
        "log_displacement": displacement,
        "total_log_variation": variation,
        "path_efficiency": efficiency,
        "signed_path_efficiency": signed_efficiency,
        "direction_descriptor": descriptor,
        "flat_path": flat,
    }


def prior_extrema(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    bars = require_sequence(inputs.get("bars"), "bars")
    highs = [
        require_positive(require_mapping(row, "bar").get("high"), "high")
        for row in bars
    ]
    lows = [
        require_positive(require_mapping(row, "bar").get("low"), "low")
        for row in bars
    ]
    direction = side_sign(inputs.get("side"))
    entry = require_positive(inputs.get("entry"), "entry")
    tp = require_positive(inputs.get("take_profit"), "take_profit")
    prior_high = max(highs)
    prior_low = min(lows)
    target = prior_high if direction == 1 else prior_low
    adverse = prior_low if direction == 1 else prior_high
    between = entry < target < tp if direction == 1 else tp < target < entry
    return {
        "prior_high": prior_high,
        "prior_low": prior_low,
        "target_side_extreme": target,
        "adverse_side_extreme": adverse,
        "target_extreme_between_entry_and_tp": between,
        "target_extreme_log_distance": abs(math.log(target / entry)),
        "barrier_effect": "observed_level_only_no_probability_effect",
    }


def volatility_rank(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    current = require_non_negative(
        inputs.get("current_realized_variance"),
        "current_realized_variance",
    )
    reference = [
        require_non_negative(value, "reference_variance")
        for value in require_sequence(
            inputs.get("reference_variances"),
            "reference_variances",
            minimum=60,
        )
    ]
    if len(reference) != 60:
        raise RuleBlocked(
            "reference_window_count_not_60",
            "volatility rank requires exactly 60 prior windows",
        )
    below = sum(value < current for value in reference)
    equal = sum(value == current for value in reference)
    return {
        "current_realized_variance": current,
        "reference_window_count": 60,
        "reference_cutoff": inputs.get("reference_cutoff"),
        "volatility_percentile": (below + 0.5 * equal) / 60,
        "ranking_method": "midrank_60_strictly_prior_non_overlapping_windows",
    }


def mtf_hierarchy(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    efficiencies = require_mapping(
        inputs.get("signed_path_efficiencies"),
        "signed_path_efficiencies",
    )
    required = ("H", "2H", "4H")
    if set(efficiencies) != set(required):
        raise RuleBlocked(
            "incomplete_mtf_windows",
            "exact H, 2H and 4H windows are required",
        )
    values = {key: require_finite(efficiencies[key], key) for key in required}
    signs = {key: sign(value) for key, value in values.items()}
    unique = set(signs.values())
    if unique == {1}:
        agreement = "all_positive"
    elif unique == {-1}:
        agreement = "all_negative"
    elif 0 in unique:
        agreement = "flat_present"
    else:
        agreement = "mixed"
    return {
        "window_multipliers": {"H": 1, "2H": 2, "4H": 4},
        "signed_path_efficiencies": values,
        "direction_signs": signs,
        "agreement_descriptor": agreement,
    }


def continuous_regime(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    rank = parent_output(
        dependencies,
        "M4-RULE-VOLATILITY-RANK-001",
    )
    path = parent_output(
        dependencies,
        "M4-RULE-PATH-STRUCTURE-001",
    )
    return {
        "volatility_percentile": require_finite(
            rank.get("volatility_percentile"),
            "volatility_percentile",
        ),
        "signed_path_efficiency": require_finite(
            path.get("signed_path_efficiency"),
            "signed_path_efficiency",
        ),
    }


def aggressor_imbalance(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    source = require_choice(
        inputs.get("ati_source", "trades"),
        "ati_source",
        {"trades", "periodic"},
    )
    buy = 0.0
    sell = 0.0
    if source == "trades":
        for row in require_sequence(inputs.get("trades"), "trades"):
            trade = require_mapping(row, "trade")
            activity = require_positive(trade.get("price"), "trade_price") * require_positive(
                trade.get("quantity"),
                "trade_quantity",
            )
            if trade.get("buyer_is_maker") is True:
                sell += activity
            elif trade.get("buyer_is_maker") is False:
                buy += activity
            else:
                raise RuleBlocked(
                    "invalid_maker_flag",
                    "buyer_is_maker must be boolean",
                )
        unit = "quote_notional"
        method = "executed_trade_sum"
    else:
        for row in require_sequence(inputs.get("periods"), "periods"):
            period = require_mapping(row, "period")
            buy += require_non_negative(period.get("buy_volume"), "buy_volume")
            sell += require_non_negative(period.get("sell_volume"), "sell_volume")
        unit = str(inputs.get("activity_unit") or "provider_volume")
        method = "periodic_volume_sum"
    total = buy + sell
    if total <= 0:
        raise RuleBlocked("zero_activity", "aggressor activity must be positive")
    start = require_timestamp_ms(inputs.get("window_start_ms"), "window_start_ms")
    end = require_timestamp_ms(inputs.get("window_end_ms"), "window_end_ms")
    coverage_start = require_timestamp_ms(
        inputs.get("coverage_start_ms"),
        "coverage_start_ms",
    )
    coverage_end = require_timestamp_ms(
        inputs.get("coverage_end_ms"),
        "coverage_end_ms",
    )
    complete = coverage_start <= start and coverage_end >= end
    if end <= start or not complete:
        raise RuleBlocked(
            "incomplete_window_coverage",
            "coverage must include the exact requested horizon",
        )
    return {
        "window_start_ms": start,
        "window_end_ms": end,
        "coverage_start_ms": coverage_start,
        "coverage_end_ms": coverage_end,
        "ati_source": source,
        "activity_unit": unit,
        "aggregation_method": method,
        "source_retention_status": "sufficient",
        "buy_taker_volume": buy,
        "sell_taker_volume": sell,
        "total_activity": total,
        "ATI_H": (buy - sell) / total,
        "coverage_complete": True,
    }


def open_interest_change(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    previous_time = require_timestamp_ms(
        inputs.get("previous_timestamp_ms"),
        "previous_timestamp_ms",
    )
    current_time = require_timestamp_ms(
        inputs.get("current_timestamp_ms"),
        "current_timestamp_ms",
    )
    horizon = int(require_positive(inputs.get("horizon_seconds"), "horizon_seconds"))
    actual = (current_time - previous_time) / 1000
    error = actual - horizon
    if error != 0:
        raise RuleBlocked(
            "open_interest_alignment_error",
            "open interest observations must be separated by exact H",
        )
    previous = require_positive(
        inputs.get("previous_open_interest"),
        "previous_open_interest",
    )
    current = require_positive(
        inputs.get("current_open_interest"),
        "current_open_interest",
    )
    change = math.log(current / previous)
    return {
        "previous_timestamp_ms": previous_time,
        "current_timestamp_ms": current_time,
        "horizon_seconds": horizon,
        "actual_separation_seconds": actual,
        "alignment_error_seconds": error,
        "previous_open_interest": previous,
        "current_open_interest": current,
        "dOI_H": change,
        "long_short_direction": sign(change),
    }


def price_oi_state(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    path = parent_output(dependencies, "M4-RULE-PATH-STRUCTURE-001")
    oi = parent_output(dependencies, "M4-RULE-OPEN-INTEREST-CHANGE-001")
    displacement = require_finite(path.get("log_displacement"), "D_H")
    change = require_finite(oi.get("dOI_H"), "dOI_H")
    return {
        "D_H": displacement,
        "dOI_H": change,
        "price_sign": sign(displacement),
        "oi_sign": sign(change),
        "state_descriptor": f"price_{sign(displacement)}_oi_{sign(change)}",
    }


def spot_futures_basis(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    if str(inputs.get("spot_symbol_status", "")).upper() != "TRADING":
        raise RuleBlocked(
            "spot_symbol_not_trading",
            "spot exchange metadata must confirm a TRADING symbol",
        )
    f_bid = require_positive(inputs.get("futures_bid"), "futures_bid")
    f_ask = require_positive(inputs.get("futures_ask"), "futures_ask")
    s_bid = require_positive(inputs.get("spot_bid"), "spot_bid")
    s_ask = require_positive(inputs.get("spot_ask"), "spot_ask")
    if f_ask < f_bid or s_ask < s_bid:
        raise RuleBlocked("crossed_book", "best ask must be >= best bid")
    futures_time = require_timestamp_ms(
        inputs.get("futures_received_at_ms"),
        "futures_received_at_ms",
    )
    spot_time = require_timestamp_ms(
        inputs.get("spot_received_at_ms"),
        "spot_received_at_ms",
    )
    skew = abs(futures_time - spot_time)
    limit = inputs.get("capture_limit_ms")
    limit_status = "not_declared"
    if limit is not None:
        maximum = require_non_negative(limit, "capture_limit_ms")
        limit_status = "within_limit" if skew <= maximum else "outside_limit"
        if skew > maximum:
            raise RuleBlocked(
                "basis_capture_skew_exceeded",
                "spot and futures quotes exceed the declared capture limit",
            )
    f_mid = (f_bid + f_ask) / 2
    s_mid = (s_bid + s_ask) / 2
    return {
        "four_quotes": {
            "futures_bid": f_bid,
            "futures_ask": f_ask,
            "spot_bid": s_bid,
            "spot_ask": s_ask,
        },
        "futures_received_at_ms": futures_time,
        "spot_received_at_ms": spot_time,
        "capture_skew_ms": skew,
        "capture_time_basis": "local_receive_time",
        "market_timestamp_synchronized": skew == 0,
        "basis_capture_uncertainty_status": (
            "simultaneous" if skew == 0 else "non_simultaneous"
        ),
        "capture_limit_status": limit_status,
        "spot_symbol_status": "TRADING",
        "b_mid": math.log(f_mid / s_mid),
        "executable_basis_bounds": {
            "sell_futures_buy_spot": math.log(f_bid / s_ask),
            "buy_futures_sell_spot": math.log(f_ask / s_bid),
        },
        "fees_included": False,
    }


def mark_index_premium(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    mark = require_positive(inputs.get("mark_price"), "mark_price")
    index = require_positive(inputs.get("index_price"), "index_price")
    return {
        "provider_time": require_timestamp_ms(
            inputs.get("provider_time"),
            "provider_time",
        ),
        "mark_price": mark,
        "index_price": index,
        "mark_index_log_premium": math.log(mark / index),
        "binance_spot_basis": False,
    }


def funding_state(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    rate = require_finite(inputs.get("last_funding_rate"), "last_funding_rate")
    interval_hours = require_positive(
        inputs.get("funding_interval_hours"),
        "funding_interval_hours",
    )
    now = require_timestamp_ms(inputs.get("current_time_ms"), "current_time_ms")
    horizon_seconds = int(
        require_positive(inputs.get("horizon_seconds"), "horizon_seconds")
    )
    start = now - horizon_seconds * 1000
    previous_load = 0.0
    for row in inputs.get("previous_events", []):
        event = require_mapping(row, "previous_event")
        event_time = require_timestamp_ms(event.get("time_ms"), "event_time_ms")
        event_rate = require_finite(event.get("rate"), "event_rate")
        if start < event_time <= now:
            previous_load += event_rate
    end = now + horizon_seconds * 1000
    scheduled = [
        require_timestamp_ms(value, "scheduled_time_ms")
        for value in inputs.get("scheduled_event_times_ms", [])
    ]
    future_count = sum(now < value <= end for value in scheduled)
    next_time = min((value for value in scheduled if value > now), default=None)
    return {
        "last_funding_rate": rate,
        "interval_hours": interval_hours,
        "linearized_last_funding_rate_per_hour": rate / interval_hours,
        "next_funding_time": next_time,
        "scheduled_events_under_current_config": future_count,
        "previous_horizon_funding_load": previous_load,
        "previous_horizon_funding_load_per_hour": (
            previous_load / (horizon_seconds / 3600)
        ),
        "projected_funding_cost": None,
        "projection_status": "not_computed_no_future_rate_assumption",
    }


def derivatives_context(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    ati = parent_output(
        dependencies,
        "M4-RULE-AGGRESSOR-IMBALANCE-001",
    )
    oi = parent_output(
        dependencies,
        "M4-RULE-OPEN-INTEREST-CHANGE-001",
    )
    funding = parent_output(
        dependencies,
        "M4-RULE-FUNDING-STATE-001",
    )
    basis_source = require_choice(
        inputs.get("basis_source"),
        "basis_source",
        {"spot_futures", "mark_index"},
    )
    if basis_source == "spot_futures":
        basis = parent_output(
            dependencies,
            "M4-RULE-SPOT-FUTURES-BASIS-001",
        )["b_mid"]
    else:
        basis = parent_output(
            dependencies,
            "M4-RULE-MARK-INDEX-PREMIUM-001",
        )["mark_index_log_premium"]
    return {
        "ATI_H": require_finite(ati.get("ATI_H"), "ATI_H"),
        "dOI_H": require_finite(oi.get("dOI_H"), "dOI_H"),
        "b_mid": require_finite(basis, "basis"),
        "basis_source": basis_source,
        "linearized_f_last_hour": require_finite(
            funding.get("linearized_last_funding_rate_per_hour"),
            "linearized_f_last_hour",
        ),
    }


def quoted_spread(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    bid = require_positive(inputs.get("best_bid"), "best_bid")
    ask = require_positive(inputs.get("best_ask"), "best_ask")
    if ask < bid:
        raise RuleBlocked("crossed_book", "best ask must be >= best bid")
    receive_time = require_timestamp_ms(
        inputs.get("receive_time"),
        "receive_time",
    )
    mid = (bid + ask) / 2
    spread = ask - bid
    return {
        "best_bid": bid,
        "best_ask": ask,
        "receive_time": receive_time,
        "mid": mid,
        "spread_quote": spread,
        "spread_fraction_mid": spread / mid,
        "availability_status": "available",
    }


def depth_sweep(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    order_side = require_choice(inputs.get("side"), "side", {"buy", "sell"})
    requested = require_positive(inputs.get("base_quantity"), "base_quantity")
    arrival_mid = require_positive(inputs.get("arrival_mid"), "arrival_mid")
    levels = require_sequence(
        inputs.get("asks" if order_side == "buy" else "bids"),
        "book_levels",
    )
    normalized = []
    for row in levels:
        level = require_mapping(row, "book_level")
        normalized.append(
            (
                require_positive(level.get("price"), "level_price"),
                require_positive(level.get("quantity"), "level_quantity"),
            )
        )
    prices = [price for price, quantity in normalized]
    if order_side == "buy" and prices != sorted(prices):
        raise RuleBlocked("invalid_ask_order", "asks must be ascending")
    if order_side == "sell" and prices != sorted(prices, reverse=True):
        raise RuleBlocked("invalid_bid_order", "bids must be descending")
    remaining = requested
    filled = 0.0
    quote = 0.0
    for price, available in normalized:
        take = min(remaining, available)
        quote += price * take
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    fill_ratio = filled / requested
    if filled <= 0:
        raise RuleBlocked("no_visible_fill", "visible book cannot fill any quantity")
    vwap = quote / filled
    direction = 1 if order_side == "buy" else -1
    shortfall_quote = direction * (quote - arrival_mid * filled)
    output = {
        "side": order_side,
        "requested_quantity": requested,
        "filled_quantity": filled,
        "fill_ratio": fill_ratio,
        "vwap_filled": vwap,
        "implementation_shortfall_filled_quote": shortfall_quote,
        "implementation_shortfall_filled_fraction": (
            shortfall_quote / (arrival_mid * filled)
        ),
        "complete_vwap": vwap if math.isclose(fill_ratio, 1.0) else None,
        "availability_status": (
            "available" if math.isclose(fill_ratio, 1.0) else "partial_fill"
        ),
    }
    if not math.isclose(fill_ratio, 1.0):
        raise RuleBlocked(
            "incomplete_visible_depth",
            "complete execution cost requires fill ratio one",
        )
    return output


def fee_scenarios(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    notional = require_non_negative(inputs.get("notional"), "notional")
    rates = require_mapping(inputs.get("commission_rates"), "commission_rates")
    allowed = set(inputs.get("allowed_roles", rates.keys()))
    if not allowed or not allowed.issubset({"maker", "taker", "rpi"}):
        raise RuleBlocked("invalid_liquidity_roles", "unknown liquidity role")
    missing = allowed.difference(rates)
    if missing:
        raise RuleBlocked("missing_commission_rate", "authenticated rate missing")
    fees = {
        role: notional * require_non_negative(rates[role], f"{role}_rate")
        for role in sorted(allowed)
    }
    observed = bool(inputs.get("observed_execution", False))
    exact = (
        observed
        and len(allowed) == 1
        and bool(inputs.get("fee_asset"))
        and bool(inputs.get("executed_notional", notional) == notional)
    )
    return {
        "notional": notional,
        "fee_by_role": fees,
        "fee_lower": min(fees.values()),
        "fee_upper": max(fees.values()),
        "exact": exact,
        "scenario_status": "observed_exact" if exact else "pretrade_scenario",
    }


def funding_cashflow(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    position_sign = side_sign(inputs.get("side"))
    quantity = require_positive(inputs.get("base_quantity"), "base_quantity")
    events = inputs.get("events")
    if events == [] and int(inputs.get("scheduled_event_count", 0)) == 0:
        return {
            "position_sign": position_sign,
            "base_quantity": quantity,
            "event_cashflows": [],
            "cashflow_total": 0.0,
            "scenario_status": "not_applicable_no_scheduled_event",
        }
    if events == []:
        raise RuleDeferred(
            "future_funding_rate_unknown",
            "scheduled funding exists but its future rate and mark are unknown",
        )
    events = require_sequence(events, "events")
    cashflows = []
    for row in events:
        event = require_mapping(row, "funding_event")
        mark = require_positive(event.get("mark_price"), "event_mark_price")
        rate = require_finite(event.get("funding_rate"), "event_funding_rate")
        cashflows.append(-position_sign * quantity * mark * rate)
    return {
        "position_sign": position_sign,
        "base_quantity": quantity,
        "event_cashflows": cashflows,
        "cashflow_total": sum(cashflows),
        "scenario_status": str(
            inputs.get("scenario_status") or "observed_events"
        ),
    }


def plan_exposure(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    direction = side_sign(inputs.get("side"))
    entry = require_positive(inputs.get("entry"), "entry")
    tp = require_positive(inputs.get("take_profit"), "take_profit")
    sl = require_positive(inputs.get("stop_loss"), "stop_loss")
    margin = require_positive(inputs.get("margin"), "margin")
    leverage = require_positive(inputs.get("leverage"), "leverage")
    notional = margin * leverage
    quantity = notional / entry

    def pnl(price: float) -> float:
        return direction * quantity * (price - entry)

    reward = pnl(tp)
    risk = -pnl(sl)
    if reward <= 0 or risk <= 0:
        raise RuleBlocked(
            "invalid_exposure_geometry",
            "gross reward and risk must both be positive",
        )
    return {
        "direction": direction,
        "notional": notional,
        "quantity": quantity,
        "gross_pnl_by_outcome": {
            "tp": reward,
            "sl": -risk,
            "expiry_entry": 0.0,
        },
        "gross_reward": reward,
        "gross_risk": risk,
        "gross_RR": reward / risk,
        "risk_fraction_margin": risk / margin,
    }


def net_payoffs(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    gross = require_mapping(inputs.get("gross_price_pnl"), "gross_price_pnl")
    fees = require_mapping(inputs.get("fee_cost"), "fee_cost")
    shortfall = require_mapping(
        inputs.get("execution_shortfall_cost"),
        "execution_shortfall_cost",
    )
    funding = require_mapping(inputs.get("funding_cashflow"), "funding_cashflow")
    keys = set(gross)
    if not keys or set(fees) != keys or set(shortfall) != keys or set(funding) != keys:
        raise RuleBlocked(
            "payoff_outcome_key_mismatch",
            "all payoff components must use identical outcome keys",
        )
    payoffs = {
        key: (
            require_finite(gross[key], f"gross_{key}")
            - require_non_negative(fees[key], f"fee_{key}")
            - require_non_negative(shortfall[key], f"shortfall_{key}")
            + require_finite(funding[key], f"funding_{key}")
        )
        for key in sorted(keys)
    }
    if "no_entry" in keys and payoffs["no_entry"] != 0:
        raise RuleBlocked(
            "invalid_no_entry_cashflow",
            "no-entry direct trading cashflow must be zero",
        )
    return {
        "outcomes": sorted(keys),
        "net_payoff_by_outcome": payoffs,
        "availability_status": "available",
    }


def expected_value(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    if not inputs.get("m6_probabilities_authorized", False):
        raise RuleDeferred(
            "m6_probabilities_unavailable",
            "expected value cannot be evaluated before M6",
        )
    probabilities = require_mapping(inputs.get("probabilities"), "probabilities")
    payoffs = require_mapping(inputs.get("net_payoffs"), "net_payoffs")
    if set(probabilities) != set(payoffs) or not probabilities:
        raise RuleBlocked(
            "expected_value_key_mismatch",
            "probabilities and payoffs must have identical outcomes",
        )
    normalized = {
        key: require_non_negative(probabilities[key], f"probability_{key}")
        for key in probabilities
    }
    if not math.isclose(sum(normalized.values()), 1.0, abs_tol=1e-12):
        raise RuleBlocked(
            "probability_mass_not_one",
            "probabilities must sum exactly to one within tolerance",
        )
    value = sum(
        normalized[key] * require_finite(payoffs[key], f"payoff_{key}")
        for key in normalized
    )
    return {
        "probabilities": normalized,
        "net_payoffs": payoffs,
        "probability_mass": sum(normalized.values()),
        "expected_value": value,
    }


def evaluation_readiness(inputs: dict, dependencies: dict[str, RuleTrace]) -> dict:
    statuses = require_mapping(inputs.get("statuses"), "statuses")
    required = {
        "market_probabilities",
        "entry_execution",
        "exit_execution",
        "fees",
        "funding",
        "payoffs",
        "account_risk",
    }
    if set(statuses) != required:
        raise RuleBlocked(
            "readiness_status_key_mismatch",
            "readiness requires the exact status contract",
        )
    allowed = {"available", "not_applicable", "blocked"}
    if any(value not in allowed for value in statuses.values()):
        raise RuleBlocked("invalid_readiness_status", "unknown readiness status")
    economic_keys = required - {"account_risk"}
    economic_ready = all(
        statuses[key] in {"available", "not_applicable"}
        for key in economic_keys
    )
    return {
        "economic_ready": economic_ready,
        "account_risk_ready": statuses["account_risk"] == "available",
        "decision_authorized": False,
        "statuses": statuses,
    }


EVALUATORS: dict[str, Callable[[dict, dict[str, RuleTrace]], dict]] = {
    "M4-RULE-HORIZON-SAMPLING-001": horizon_sampling,
    "M4-RULE-PLAN-GEOMETRY-001": plan_geometry,
    "M4-RULE-LOG-RETURNS-001": log_returns,
    "M4-RULE-REALIZED-VOLATILITY-001": realized_volatility,
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": normalized_barrier_geometry,
    "M4-RULE-PENDING-ACTIVATION-001": pending_activation,
    "M4-RULE-EXPONENTIAL-SMOOTHER-001": exponential_smoother,
    "M4-RULE-PATH-STRUCTURE-001": path_structure,
    "M4-RULE-PRIOR-EXTREMA-001": prior_extrema,
    "M4-RULE-VOLATILITY-RANK-001": volatility_rank,
    "M4-RULE-MTF-HIERARCHY-001": mtf_hierarchy,
    "M4-RULE-CONTINUOUS-REGIME-001": continuous_regime,
    "M4-RULE-AGGRESSOR-IMBALANCE-001": aggressor_imbalance,
    "M4-RULE-OPEN-INTEREST-CHANGE-001": open_interest_change,
    "M4-RULE-PRICE-OI-STATE-001": price_oi_state,
    "M4-RULE-SPOT-FUTURES-BASIS-001": spot_futures_basis,
    "M4-RULE-MARK-INDEX-PREMIUM-001": mark_index_premium,
    "M4-RULE-FUNDING-STATE-001": funding_state,
    "M4-RULE-DERIVATIVES-CONTEXT-001": derivatives_context,
    "M4-RULE-QUOTED-SPREAD-001": quoted_spread,
    "M4-RULE-DEPTH-SWEEP-001": depth_sweep,
    "M4-RULE-FEE-SCENARIOS-001": fee_scenarios,
    "M4-RULE-FUNDING-CASHFLOW-001": funding_cashflow,
    "M4-RULE-PLAN-EXPOSURE-001": plan_exposure,
    "M4-RULE-NET-PAYOFFS-001": net_payoffs,
    "M4-RULE-EXPECTED-VALUE-001": expected_value,
    "M4-RULE-EVALUATION-READINESS-001": evaluation_readiness,
}


@lru_cache(maxsize=1)
def rule_specs() -> dict[str, dict]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    specs = {rule["rule_id"]: rule for rule in contract["rules"]}
    if set(specs) != set(EVALUATORS):
        raise ValueError("m5_evaluator_registry_not_exact")
    return specs


def execute_rule(
    rule_id: str,
    *,
    analysis_id: str,
    inputs: dict,
    dependencies: dict[str, RuleTrace] | None = None,
    source_observations: tuple[dict, ...] = (),
    executed_at: str | None = None,
) -> RuleTrace:
    try:
        spec = rule_specs()[rule_id]
        evaluator = EVALUATORS[rule_id]
    except KeyError as exc:
        raise ValueError(f"unknown_m5_rule:{rule_id}") from exc
    return run_rule(
        analysis_id=analysis_id,
        rule_id=rule_id,
        canonical_family=spec["canonical_family"],
        formula_ids=tuple(item["id"] for item in spec["formulas"]),
        inputs=inputs,
        evaluator=evaluator,
        dependencies=dependencies,
        source_observations=source_observations,
        executed_at=executed_at,
    )
