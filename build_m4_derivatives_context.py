from __future__ import annotations

import argparse
import hashlib
import json
from math import floor, isfinite, log
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M3_CATALOG_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
M4_RECONCILIATION_PATH = (
    AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json"
)
M4_STRUCTURE_PATH = (
    AUDIT_DIR / "catalogo_regimen_estructura_mtf_m4_3_v0_2.json"
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "catalogo_contexto_derivados_m4_4_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR
    / "2026-07-27_M4_4_orderflow_oi_basis_funding_enmienda_v0_2.md"
)

VERSION = "M4.4-derivatives-context-v0.2"
RULE_VERSION = "0.2"
CROSS_VENUE_MAX_SKEW_MS = 2_000
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = ("intraday_short", "intraday_wide", "short_swing")

SOURCES = (
    {
        "id": "M3-DATA-CONTRACTS",
        "type": "approved_internal_contract",
        "url": None,
        "supported_claim": (
            "Fields, timestamps, retention and absence policy for Binance "
            "Futures and Spot observations."
        ),
        "does_not_support": "Any predictive sign, threshold, weight or score.",
    },
    {
        "id": "M4.2-REACHABILITY",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Exact horizon, closed-window and log-geometry conventions."
        ),
        "does_not_support": "A derivatives-context probability effect.",
    },
    {
        "id": "M4.3-STRUCTURE",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Price displacement and non-additive interaction conventions."
        ),
        "does_not_support": "Price-OI quadrant meanings or weights.",
    },
    {
        "id": "BINANCE-USD-M-MARKET-DATA",
        "type": "official_provider_documentation",
        "url": (
            "https://developers.binance.com/en/docs/catalog/"
            "core-trading-derivatives-trading-usd-s-m-futures/api/"
            "rest-api/market-data"
        ),
        "supported_claim": (
            "Official meanings and availability of aggregate trades, taker "
            "volume, open interest, mark/index prices and funding fields."
        ),
        "does_not_support": (
            "Predictiveness, full-book order flow, complete retention or "
            "universal funding interpretation."
        ),
    },
    {
        "id": "BINANCE-SPOT-MARKET-DATA",
        "type": "official_provider_documentation",
        "url": (
            "https://developers.binance.com/en/docs/catalog/"
            "core-trading-spot-trading/api/rest-api/market"
        ),
        "supported_claim": "Official Spot best bid and ask fields.",
        "does_not_support": (
            "Provider event time for REST bookTicker or basis predictiveness."
        ),
    },
    {
        "id": "CONT-KUKANOV-STOIKOV-2014",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1093/jjfinec/nbt003",
        "supported_claim": (
            "Short-interval price changes in the studied equities were more "
            "robustly related to full order-book event imbalance than to "
            "trade volume or trade imbalance alone."
        ),
        "does_not_support": (
            "Calling Binance taker-trade imbalance OFI, crypto transfer, "
            "project horizons or a TP/SL probability."
        ),
    },
    {
        "id": "HONG-YOGO-2012",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1016/j.jfineco.2011.05.008",
        "supported_claim": (
            "Open-interest changes contained information in the traditional "
            "futures markets and horizons studied by the authors."
        ),
        "does_not_support": (
            "Crypto perpetual intraday transfer, long/short direction from "
            "gross OI, quadrant labels or project weights."
        ),
    },
    {
        "id": "BAUR-DIMPFL-2019",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1002/fut.22004",
        "supported_claim": (
            "Their Bitcoin sample found spot leading the restricted "
            "exchange-traded futures market in price discovery."
        ),
        "does_not_support": (
            "Binance perpetual leadership, basis direction or all crypto "
            "pairs and horizons."
        ),
    },
    {
        "id": "FRINO-ET-AL-2025",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1002/fut.22560",
        "supported_claim": (
            "A later Bitcoin study found futures generally leading spot with "
            "daily variation after accounting for noise."
        ),
        "does_not_support": (
            "A fixed leader, Binance perpetual transfer or a basis signal."
        ),
    },
    {
        "id": "HE-MANELA-ROSS-VON-WACHTER-2022",
        "type": "primary_academic_preprint",
        "url": "https://arxiv.org/abs/2212.06888",
        "supported_claim": (
            "Funding is an anchoring cash-flow mechanism for perpetuals and "
            "spot-perpetual deviations can remain material."
        ),
        "does_not_support": (
            "Funding sign as a standalone return forecast, Binance-specific "
            "thresholds or ignoring trading costs."
        ),
    },
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def positive_number(value: Any, error: str) -> float:
    if not finite_number(value) or float(value) <= 0:
        raise ValueError(error)
    return float(value)


def nonnegative_number(value: Any, error: str) -> float:
    if not finite_number(value) or float(value) < 0:
        raise ValueError(error)
    return float(value)


def sign_descriptor(value: float) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "flat"


def aggressor_trade_imbalance(
    trades: list[dict],
    *,
    window_start_ms: int,
    window_end_ms: int,
    coverage_complete: bool,
) -> dict:
    if (
        not isinstance(window_start_ms, int)
        or isinstance(window_start_ms, bool)
        or not isinstance(window_end_ms, int)
        or isinstance(window_end_ms, bool)
        or window_start_ms < 0
        or window_start_ms >= window_end_ms
    ):
        raise ValueError("invalid_event_window")
    if coverage_complete is not True:
        raise ValueError("incomplete_event_window")
    if not trades:
        raise ValueError("empty_trade_window")

    buy_taker_quote = 0.0
    sell_taker_quote = 0.0
    previous_id = None
    previous_time = None
    for trade in trades:
        trade_id = trade.get("aggregate_trade_id")
        event_time = trade.get("time_ms")
        buyer_is_maker = trade.get("buyer_is_maker")
        if (
            not isinstance(trade_id, int)
            or isinstance(trade_id, bool)
            or not isinstance(event_time, int)
            or isinstance(event_time, bool)
            or not isinstance(buyer_is_maker, bool)
        ):
            raise ValueError("invalid_trade_metadata")
        if not window_start_ms < event_time <= window_end_ms:
            raise ValueError("trade_outside_exact_window")
        if previous_id is not None and trade_id <= previous_id:
            raise ValueError("trade_ids_not_strictly_increasing")
        if previous_time is not None and event_time < previous_time:
            raise ValueError("trade_times_not_ordered")
        price = positive_number(trade.get("price"), "invalid_trade_price")
        quantity = positive_number(
            trade.get("quantity"),
            "invalid_trade_quantity",
        )
        quote_notional = price * quantity
        if buyer_is_maker:
            sell_taker_quote += quote_notional
        else:
            buy_taker_quote += quote_notional
        previous_id = trade_id
        previous_time = event_time

    total_quote = buy_taker_quote + sell_taker_quote
    if total_quote <= 0:
        raise ValueError("zero_trade_activity")
    imbalance = (buy_taker_quote - sell_taker_quote) / total_quote
    return {
        "window_start_ms": window_start_ms,
        "window_end_ms": window_end_ms,
        "coverage_start_ms": window_start_ms,
        "coverage_end_ms": window_end_ms,
        "ati_source": "binance_usdm_aggTrades",
        "activity_unit": "quote_asset",
        "aggregation_method": "sum_price_times_quantity_by_taker_side",
        "source_retention_status": (
            "provider_limited_local_archive_required_beyond_retention"
        ),
        "trade_count": len(trades),
        "buy_taker_quote": buy_taker_quote,
        "sell_taker_quote": sell_taker_quote,
        "total_executed_quote": total_quote,
        "aggressor_trade_imbalance": imbalance,
        "direction_descriptor": sign_descriptor(imbalance),
        "full_order_flow_imbalance": None,
        "prediction": None,
    }


def periodic_taker_imbalance(
    periods: list[dict],
    *,
    window_start_ms: int,
    window_end_ms: int,
    period_ms: int,
) -> dict:
    if (
        not isinstance(period_ms, int)
        or isinstance(period_ms, bool)
        or period_ms <= 0
        or window_start_ms < 0
        or window_start_ms >= window_end_ms
        or (window_end_ms - window_start_ms) % period_ms
    ):
        raise ValueError("invalid_period_grid")
    expected_timestamps = list(
        range(
            window_start_ms + period_ms,
            window_end_ms + 1,
            period_ms,
        )
    )
    if len(periods) != len(expected_timestamps):
        raise ValueError("incomplete_period_window")
    actual_timestamps = [period.get("timestamp_ms") for period in periods]
    if actual_timestamps != expected_timestamps:
        raise ValueError("period_gap_or_misalignment")

    buy_volume = 0.0
    sell_volume = 0.0
    for period in periods:
        buy_volume += nonnegative_number(
            period.get("buy_volume"),
            "invalid_buy_volume",
        )
        sell_volume += nonnegative_number(
            period.get("sell_volume"),
            "invalid_sell_volume",
        )
    total_volume = buy_volume + sell_volume
    if total_volume <= 0:
        raise ValueError("zero_taker_activity")
    imbalance = (buy_volume - sell_volume) / total_volume
    return {
        "window_start_ms": window_start_ms,
        "window_end_ms": window_end_ms,
        "coverage_start_ms": window_start_ms,
        "coverage_end_ms": window_end_ms,
        "ati_source": "binance_usdm_periodic_taker_volume",
        "activity_unit": "base_asset",
        "aggregation_method": "sum_buy_sell_volume_on_exact_period_grid",
        "source_retention_status": (
            "provider_limited_local_archive_required_beyond_retention"
        ),
        "period_ms": period_ms,
        "period_count": len(periods),
        "buy_taker_volume": buy_volume,
        "sell_taker_volume": sell_volume,
        "total_taker_volume": total_volume,
        "aggressor_trade_imbalance": imbalance,
        "direction_descriptor": sign_descriptor(imbalance),
        "full_order_flow_imbalance": None,
        "prediction": None,
    }


def reconcile_aggressor_measures(
    event_measure: dict | None,
    periodic_measure: dict | None,
) -> dict:
    available = [
        ("event_trade", event_measure),
        ("periodic_taker", periodic_measure),
    ]
    available = [
        (name, value)
        for name, value in available
        if value is not None
    ]
    if not available:
        raise ValueError("no_aggressor_measure")
    values = {}
    source_metadata = {}
    for name, measure in available:
        value = measure.get("aggressor_trade_imbalance")
        if not finite_number(value) or not -1 <= float(value) <= 1:
            raise ValueError("invalid_aggressor_measure")
        values[name] = float(value)
        source_metadata[name] = {
            "ati_source": measure.get("ati_source"),
            "activity_unit": measure.get("activity_unit"),
            "coverage_start_ms": measure.get("coverage_start_ms"),
            "coverage_end_ms": measure.get("coverage_end_ms"),
            "aggregation_method": measure.get("aggregation_method"),
            "source_retention_status": measure.get(
                "source_retention_status"
            ),
        }
    if len(values) == 1:
        consistency = "single_source_only"
        difference = None
    else:
        event_value = values["event_trade"]
        periodic_value = values["periodic_taker"]
        difference = event_value - periodic_value
        signs = {sign_descriptor(event_value), sign_descriptor(periodic_value)}
        consistency = (
            "same_sign"
            if len(signs) == 1
            else "flat_involved"
            if "flat" in signs
            else "opposite_sign"
        )
    return {
        "source_values": values,
        "source_metadata": source_metadata,
        "signed_difference": difference,
        "consistency_descriptor": consistency,
        "combined_value": None,
        "probability_effect": None,
    }


def open_interest_change(
    previous_open_interest: float,
    current_open_interest: float,
    *,
    previous_timestamp_ms: int,
    current_timestamp_ms: int,
    horizon_seconds: int,
) -> dict:
    previous = positive_number(
        previous_open_interest,
        "invalid_previous_open_interest",
    )
    current = positive_number(
        current_open_interest,
        "invalid_current_open_interest",
    )
    if (
        not isinstance(previous_timestamp_ms, int)
        or isinstance(previous_timestamp_ms, bool)
        or not isinstance(current_timestamp_ms, int)
        or isinstance(current_timestamp_ms, bool)
        or previous_timestamp_ms < 0
        or current_timestamp_ms <= previous_timestamp_ms
        or not isinstance(horizon_seconds, int)
        or isinstance(horizon_seconds, bool)
        or horizon_seconds <= 0
    ):
        raise ValueError("invalid_open_interest_endpoint_time")
    actual_separation_ms = current_timestamp_ms - previous_timestamp_ms
    expected_separation_ms = horizon_seconds * 1000
    if actual_separation_ms != expected_separation_ms:
        raise ValueError("open_interest_endpoint_misalignment")
    change = log(current / previous)
    return {
        "previous_timestamp_ms": previous_timestamp_ms,
        "current_timestamp_ms": current_timestamp_ms,
        "horizon_seconds": horizon_seconds,
        "actual_separation_seconds": actual_separation_ms / 1000,
        "alignment_error_seconds": 0.0,
        "previous_open_interest": previous,
        "current_open_interest": current,
        "log_open_interest_change": change,
        "direction_descriptor": sign_descriptor(change),
        "long_short_direction": None,
        "prediction": None,
    }


def price_open_interest_state(
    log_price_displacement: float,
    log_open_interest_change: float,
) -> dict:
    if not finite_number(log_price_displacement):
        raise ValueError("invalid_price_displacement")
    if not finite_number(log_open_interest_change):
        raise ValueError("invalid_open_interest_change")
    price_value = float(log_price_displacement)
    oi_value = float(log_open_interest_change)
    return {
        "log_price_displacement": price_value,
        "log_open_interest_change": oi_value,
        "price_sign": sign_descriptor(price_value),
        "open_interest_sign": sign_descriptor(oi_value),
        "state_descriptor": (
            f"price_{sign_descriptor(price_value)}"
            f"__oi_{sign_descriptor(oi_value)}"
        ),
        "positioning_label": None,
        "aggregate_score": None,
        "probability_effect": None,
    }


def _validated_book(
    bid: float,
    ask: float,
    prefix: str,
) -> tuple[float, float]:
    parsed_bid = positive_number(bid, f"invalid_{prefix}_bid")
    parsed_ask = positive_number(ask, f"invalid_{prefix}_ask")
    if parsed_bid > parsed_ask:
        raise ValueError(f"crossed_{prefix}_book")
    return parsed_bid, parsed_ask


def spot_futures_basis(
    *,
    futures_bid: float,
    futures_ask: float,
    spot_bid: float,
    spot_ask: float,
    futures_received_at_ms: int,
    spot_received_at_ms: int,
) -> dict:
    futures_bid_value, futures_ask_value = _validated_book(
        futures_bid,
        futures_ask,
        "futures",
    )
    spot_bid_value, spot_ask_value = _validated_book(
        spot_bid,
        spot_ask,
        "spot",
    )
    if (
        not isinstance(futures_received_at_ms, int)
        or isinstance(futures_received_at_ms, bool)
        or not isinstance(spot_received_at_ms, int)
        or isinstance(spot_received_at_ms, bool)
        or futures_received_at_ms < 0
        or spot_received_at_ms < 0
    ):
        raise ValueError("invalid_capture_time")
    capture_skew_ms = abs(
        futures_received_at_ms - spot_received_at_ms
    )
    if capture_skew_ms > CROSS_VENUE_MAX_SKEW_MS:
        raise ValueError("cross_venue_capture_skew")

    futures_mid = (futures_bid_value + futures_ask_value) / 2
    spot_mid = (spot_bid_value + spot_ask_value) / 2
    lower_executable_basis = log(futures_bid_value / spot_ask_value)
    upper_executable_basis = log(futures_ask_value / spot_bid_value)
    return {
        "futures_mid": futures_mid,
        "spot_mid": spot_mid,
        "mid_log_basis": log(futures_mid / spot_mid),
        "sell_futures_buy_spot_log_basis": lower_executable_basis,
        "buy_futures_sell_spot_log_basis": upper_executable_basis,
        "capture_skew_ms": capture_skew_ms,
        "capture_time_basis": "local_receive_time",
        "market_timestamp_synchronized": False,
        "basis_capture_uncertainty_status": (
            "receive_time_bounded_not_market_synchronized"
        ),
        "capture_limit_status": "within_provisional_policy",
        "fees_included": False,
        "price_leadership": None,
        "prediction": None,
    }


def mark_index_premium(mark_price: float, index_price: float) -> dict:
    mark = positive_number(mark_price, "invalid_mark_price")
    index = positive_number(index_price, "invalid_index_price")
    premium = log(mark / index)
    return {
        "mark_price": mark,
        "index_price": index,
        "mark_index_log_premium": premium,
        "direction_descriptor": sign_descriptor(premium),
        "binance_spot_basis": None,
        "prediction": None,
    }


def funding_state(
    *,
    last_funding_rate: float,
    funding_interval_hours: int,
    next_funding_time_ms: int,
    analysis_at_ms: int,
    horizon_seconds: int,
    historical_events: list[dict],
) -> dict:
    if not finite_number(last_funding_rate):
        raise ValueError("invalid_last_funding_rate")
    if (
        not isinstance(funding_interval_hours, int)
        or isinstance(funding_interval_hours, bool)
        or funding_interval_hours <= 0
    ):
        raise ValueError("invalid_funding_interval")
    if (
        not isinstance(next_funding_time_ms, int)
        or isinstance(next_funding_time_ms, bool)
        or not isinstance(analysis_at_ms, int)
        or isinstance(analysis_at_ms, bool)
        or analysis_at_ms < 0
        or next_funding_time_ms < analysis_at_ms
    ):
        raise ValueError("invalid_next_funding_time")
    if (
        not isinstance(horizon_seconds, int)
        or isinstance(horizon_seconds, bool)
        or horizon_seconds <= 0
    ):
        raise ValueError("invalid_horizon_seconds")

    history_start_ms = analysis_at_ms - horizon_seconds * 1000
    previous_time = None
    rates = []
    for event in historical_events:
        event_time = event.get("funding_time_ms")
        rate = event.get("funding_rate")
        if (
            not isinstance(event_time, int)
            or isinstance(event_time, bool)
            or event_time < 0
            or not history_start_ms < event_time <= analysis_at_ms
            or (previous_time is not None and event_time <= previous_time)
        ):
            raise ValueError("invalid_historical_funding_time")
        if not finite_number(rate):
            raise ValueError("invalid_historical_funding_rate")
        rates.append(float(rate))
        previous_time = event_time

    expiry_ms = analysis_at_ms + horizon_seconds * 1000
    interval_ms = funding_interval_hours * 3_600_000
    scheduled_events_under_current_config = (
        0
        if next_funding_time_ms > expiry_ms
        else 1 + floor((expiry_ms - next_funding_time_ms) / interval_ms)
    )
    horizon_hours = horizon_seconds / 3600
    return {
        "last_funding_rate": float(last_funding_rate),
        "funding_interval_hours": funding_interval_hours,
        "linearized_last_funding_rate_per_hour": (
            float(last_funding_rate) / funding_interval_hours
        ),
        "next_funding_in_seconds": (
            next_funding_time_ms - analysis_at_ms
        ) / 1000,
        "scheduled_events_under_current_config": (
            scheduled_events_under_current_config
        ),
        "historical_event_count": len(rates),
        "previous_horizon_funding_load": sum(rates),
        "previous_horizon_funding_load_per_hour": (
            sum(rates) / horizon_hours
        ),
        "future_funding_rate_assumption": None,
        "projected_funding_cost": None,
        "directional_prediction": None,
    }


def derivatives_context_vector(
    *,
    aggressor_imbalance: float,
    log_open_interest_change: float,
    mid_log_basis: float,
    linearized_last_funding_rate_per_hour: float,
) -> dict:
    values = {
        "aggressor_imbalance": aggressor_imbalance,
        "log_open_interest_change": log_open_interest_change,
        "mid_log_basis": mid_log_basis,
        "linearized_last_funding_rate_per_hour": (
            linearized_last_funding_rate_per_hour
        ),
    }
    if any(not finite_number(value) for value in values.values()):
        raise ValueError("invalid_derivatives_context_component")
    if not -1 <= float(aggressor_imbalance) <= 1:
        raise ValueError("invalid_aggressor_imbalance")
    return {
        **{key: float(value) for key, value in values.items()},
        "crowding_label": None,
        "aggregate_score": None,
        "probability_effect": None,
    }


def rule_card(
    rule_id: str,
    name: str,
    *,
    blocks: list[int],
    objective: str,
    data_ids: list[str],
    formula: list[str],
    source_support: list[dict],
    unsupported: list[str],
    hypothesis: dict | None,
    expected_relation: str,
    related: list[str],
    double_counting: str,
    missing: str,
    invariants: list[str],
    trace: list[str],
    refutation: list[str],
    provider: str = "Binance USD-M",
    markets: list[str] | None = None,
    time_rule: str = (
        "M3-compliant data only; exact windows end at or before analysis_at"
    ),
    lifecycle_status: str = "documented_candidate_no_predictive_weight",
) -> dict:
    if markets is None:
        markets = ["Binance USD-M perpetual"]
    return {
        "id": rule_id,
        "version": RULE_VERSION,
        "name": name,
        "analytical_blocks": blocks,
        "concrete_objective": objective,
        "rule_type": "deterministic_measure_with_separate_hypothesis",
        "raw_data_and_provider": {
            "provider": provider,
            "m3_data_contract_ids": data_ids,
        },
        "market_symbol_timestamp_unit_freshness": {
            "markets": markets,
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "time_rule": time_rule,
            "normalized_units": "log_ratio_or_dimensionless_ratio",
        },
        "exact_transformation_and_formula": formula,
        "cross_pair_normalization": (
            "Natural-log changes and bounded ratios; raw activity is not "
            "compared across pairs."
        ),
        "applicable_horizons": list(HORIZONS),
        "activation_conditions": [
            "complete M3-compliant observations",
            "exact horizon or explicitly identified current snapshot",
            "same formula for every supported pair",
        ],
        "non_application_conditions": [
            "missing, stale, future, gapped or incomplete data",
            "provider retention cannot cover the exact window",
        ],
        "source_and_exact_supported_claim": source_support,
        "claims_not_supported_by_source": unsupported,
        "separate_predictive_hypothesis": hypothesis,
        "expected_relation_to_tp_sl_or_expiry": expected_relation,
        "related_rules": related,
        "double_counting_control": double_counting,
        "missing_data_behavior": missing,
        "unit_tests_limits_and_invariants": invariants,
        "trace_output": trace,
        "refutation_suspension_or_withdrawal": refutation,
        "lifecycle_status": lifecycle_status,
        "direct_probability_effect_authorized": False,
        "numeric_weight_authorized": False,
        "production_authorized": False,
    }


def build_rules() -> list[dict]:
    common_limits = [
        "No source supplies a project probability, score, threshold or weight.",
        "Evidence from another asset, venue or horizon is not transferred.",
    ]
    return [
        rule_card(
            "M4-RULE-AGGRESSOR-IMBALANCE-001",
            "Desequilibrio de operaciones agresoras ejecutadas",
            blocks=[7],
            objective=(
                "Measure buyer-taker versus seller-taker executed volume over "
                "one exact window without calling it full order flow."
            ),
            data_ids=["M3-DATA-005", "M3-DATA-007", "M3-DATA-015"],
            formula=[
                "B_H=sum(p_i*q_i where buyer_is_maker=false)",
                "S_H=sum(p_i*q_i where buyer_is_maker=true)",
                "ATI_H=(B_H-S_H)/(B_H+S_H)",
                "periodic alternative=(sum(buyVol)-sum(sellVol))/total",
            ],
            source_support=[
                {
                    "source_id": "BINANCE-USD-M-MARKET-DATA",
                    "level": "definition",
                    "claim": "Trade side, price, quantity and taker volumes.",
                },
                {
                    "source_id": "CONT-KUKANOV-STOIKOV-2014",
                    "level": "transfer_limit",
                    "claim": (
                        "Trade imbalance is weaker than full order-book event "
                        "imbalance in the studied equity data."
                    ),
                },
            ],
            unsupported=[
                *common_limits,
                "ATI_H is not OFI or CVD.",
                "Limit orders and cancellations are absent.",
                "Event and periodic measures cannot be added or averaged.",
            ],
            hypothesis={
                "id": "M4-HYP-FLOW-001",
                "status": "proposed_unverified",
                "statement": (
                    "Side-aligned ATI_H may condition first-barrier behavior "
                    "after controlling for path, volatility and activity."
                ),
            },
            expected_relation="Unknown; no direct TP/SL effect.",
            related=["M4-RULE-DERIVATIVES-CONTEXT-001"],
            double_counting=(
                "aggTrades, taker endpoint and kline taker volume are "
                "alternative measurements of one evidence family."
            ),
            missing="Rule unavailable; no zero or neutral imbalance.",
            invariants=[
                "-1<=ATI_H<=1",
                "exact complete window",
                "buyer-maker means seller taker",
                "source alternatives are not averaged",
            ],
            trace=[
                "window_start_ms",
                "window_end_ms",
                "coverage_start_ms",
                "coverage_end_ms",
                "ati_source",
                "activity_unit",
                "aggregation_method",
                "source_retention_status",
                "buy_taker_volume",
                "sell_taker_volume",
                "total_activity",
                "ATI_H",
                "coverage_complete",
                "prediction",
            ],
            refutation=[
                "Retire if no stable incremental value after full controls.",
                "A true OFI rule requires book-event capture and a new card.",
            ],
        ),
        rule_card(
            "M4-RULE-OPEN-INTEREST-CHANGE-001",
            "Cambio logaritmico de open interest",
            blocks=[9],
            objective=(
                "Measure the change in outstanding contract quantity over the "
                "same exact horizon without inferring long/short direction."
            ),
            data_ids=["M3-DATA-013", "M3-DATA-014"],
            formula=[
                "dOI_H=ln(OI_t/OI_(t-H))",
                "current_timestamp_ms-previous_timestamp_ms=H*1000",
            ],
            source_support=[
                {
                    "source_id": "BINANCE-USD-M-MARKET-DATA",
                    "level": "definition",
                    "claim": "Current and historical total open interest.",
                },
                {
                    "source_id": "HONG-YOGO-2012",
                    "level": "external_predictive_evidence",
                    "claim": (
                        "OI changes carried information in traditional "
                        "futures samples."
                    ),
                },
            ],
            unsupported=[
                *common_limits,
                "Gross OI does not identify net long or net short pressure.",
                "OI value is not substituted for contract quantity.",
            ],
            hypothesis={
                "id": "M4-HYP-OI-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "dOI_H may alter the conditional value of price-path and "
                    "aggressor-flow observations."
                ),
            },
            expected_relation="Context only; no standalone direction.",
            related=["M4-RULE-PRICE-OI-STATE-001"],
            double_counting=(
                "Current OI and historical OI form one endpoint change."
            ),
            missing="Rule unavailable; no assumed unchanged OI.",
            invariants=[
                "OI_t>0 and OI_(t-H)>0",
                "exact endpoint separation H",
                "dimensionless log change",
                "long_short_direction is null",
            ],
            trace=[
                "previous_timestamp_ms",
                "current_timestamp_ms",
                "horizon_seconds",
                "actual_separation_seconds",
                "alignment_error_seconds",
                "previous_open_interest",
                "current_open_interest",
                "dOI_H",
                "long_short_direction",
            ],
            refutation=[
                "Retire hypothesis if unstable by pair or horizon.",
                "Reject any implementation that labels OI rise as longs.",
            ],
        ),
        rule_card(
            "M4-RULE-PRICE-OI-STATE-001",
            "Estado conjunto precio y open interest",
            blocks=[1, 9],
            objective=(
                "Preserve the joint continuous state (D_H,dOI_H) without "
                "legacy quadrant narratives or duplicate points."
            ),
            data_ids=["M3-DATA-005", "M3-DATA-013", "M3-DATA-014"],
            formula=["POI_H=(D_H,dOI_H)"],
            source_support=[
                {
                    "source_id": "HONG-YOGO-2012",
                    "level": "transfer_limit",
                    "claim": "OI may contain information beyond futures price.",
                },
                {
                    "source_id": "M4.3-STRUCTURE",
                    "level": "internal_definition",
                    "claim": "D_H is the exact-H log price displacement.",
                },
            ],
            unsupported=[
                *common_limits,
                "No quadrant means new longs, new shorts, covering or exit.",
                "The vector adds no evidence beyond its components.",
            ],
            hypothesis={
                "id": "M4-HYP-PRICE-OI-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "The joint continuous state may condition first-passage "
                    "behavior beyond price displacement alone."
                ),
            },
            expected_relation="Unknown interaction; no quadrant score.",
            related=[
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
            ],
            double_counting=(
                "References D_H and dOI_H; cannot be added as a third signal."
            ),
            missing="Vector unavailable if either component is unavailable.",
            invariants=[
                "continuous values preserved",
                "positioning_label is null",
                "aggregate_score is null",
            ],
            trace=[
                "D_H",
                "dOI_H",
                "price_sign",
                "oi_sign",
                "state_descriptor",
                "positioning_label",
                "probability_effect",
            ],
            refutation=[
                "Retire interaction if no incremental conditional value.",
                "Any semantic quadrant requires separately verified evidence.",
            ],
        ),
        rule_card(
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            "Intervalo observable spot-Futures",
            blocks=[15],
            objective=(
                "Measure receive-time-bounded midpoint and executable quote "
                "ratios between Binance Spot and USD-M perpetual."
            ),
            data_ids=["M3-DATA-008", "M3-DATA-016", "M3-DATA-017"],
            formula=[
                "mid_F=(F_bid+F_ask)/2; mid_S=(S_bid+S_ask)/2",
                "b_mid=ln(mid_F/mid_S)",
                "b_sellF_buyS=ln(F_bid/S_ask)",
                "b_buyF_sellS=ln(F_ask/S_bid)",
            ],
            source_support=[
                {
                    "source_id": "BINANCE-SPOT-MARKET-DATA",
                    "level": "definition",
                    "claim": "Spot best bid and ask.",
                },
                {
                    "source_id": "BAUR-DIMPFL-2019",
                    "level": "external_predictive_evidence",
                    "claim": "Spot led futures in their Bitcoin sample.",
                },
                {
                    "source_id": "FRINO-ET-AL-2025",
                    "level": "external_predictive_evidence",
                    "claim": (
                        "Futures generally led spot in a later sample, with "
                        "daily variation."
                    ),
                },
            ],
            unsupported=[
                *common_limits,
                "No market is assigned permanent price leadership.",
                "The raw interval excludes fees, latency and fill uncertainty.",
            ],
            hypothesis={
                "id": "M4-HYP-BASIS-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "Basis magnitude and sign may condition price discovery "
                    "when combined with flow, OI and freshness."
                ),
            },
            expected_relation="Unknown; no automatic convergence direction.",
            related=["M4-RULE-MARK-INDEX-PREMIUM-001"],
            double_counting=(
                "Midpoint and executable bounds are one basis observation."
            ),
            missing="Block basis; mark-index premium is not a silent substitute.",
            invariants=[
                "bid<=ask on both venues",
                "capture skew<=2000ms",
                "capture times are local receive times, not synchronized market times",
                "log ratios are scale invariant",
                "price_leadership is null",
            ],
            trace=[
                "four_quotes",
                "futures_received_at_ms",
                "spot_received_at_ms",
                "capture_skew_ms",
                "capture_time_basis",
                "market_timestamp_synchronized",
                "basis_capture_uncertainty_status",
                "capture_limit_status",
                "b_mid",
                "executable_basis_bounds",
                "fees_included",
            ],
            refutation=[
                "Retire if capture uncertainty dominates observed basis.",
                "Price leadership requires a separate time-series model.",
            ],
            provider="Binance USD-M and Binance Spot",
            markets=["Binance USD-M perpetual", "Binance Spot"],
            time_rule=(
                "M3-compliant receive times only; cross-venue receive-time "
                "skew is bounded by a provisional project policy"
            ),
        ),
        rule_card(
            "M4-RULE-MARK-INDEX-PREMIUM-001",
            "Prima sincronizada mark-index",
            blocks=[10, 15],
            objective=(
                "Measure the same-timestamp USD-M mark-to-index log ratio "
                "without presenting the index as Binance Spot."
            ),
            data_ids=["M3-DATA-010"],
            formula=["b_mark_index=ln(markPrice/indexPrice)"],
            source_support=[
                {
                    "source_id": "BINANCE-USD-M-MARKET-DATA",
                    "level": "definition",
                    "claim": "Mark price, index price and provider time.",
                },
                {
                    "source_id": "HE-MANELA-ROSS-VON-WACHTER-2022",
                    "level": "technical_foundation",
                    "claim": "Perpetual prices can deviate from spot anchors.",
                },
            ],
            unsupported=[
                *common_limits,
                "Index price is not Binance Spot bookTicker.",
                "Premium sign is not a return forecast.",
            ],
            hypothesis={
                "id": "M4-HYP-PREMIUM-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "The synchronized mark-index premium may improve basis "
                    "context when cross-venue capture is noisy."
                ),
            },
            expected_relation="Context only; no convergence assumption.",
            related=["M4-RULE-SPOT-FUTURES-BASIS-001"],
            double_counting=(
                "Cross-venue basis and mark-index premium share one family "
                "and cannot both receive independent effects."
            ),
            missing="Rule unavailable; no zero premium.",
            invariants=[
                "markPrice>0 and indexPrice>0",
                "same provider timestamp",
                "binance_spot_basis is null",
            ],
            trace=[
                "provider_time",
                "mark_price",
                "index_price",
                "mark_index_log_premium",
                "binance_spot_basis",
            ],
            refutation=[
                "Retire hypothesis if it adds no value beyond actual basis.",
            ],
        ),
        rule_card(
            "M4-RULE-FUNDING-STATE-001",
            "Estado temporal y carga realizada de funding",
            blocks=[10],
            objective=(
                "Normalize the current rate by its configured interval and "
                "record realized prior-H funding without forecasting rates."
            ),
            data_ids=["M3-DATA-010", "M3-DATA-011", "M3-DATA-012"],
            formula=[
                "linearized_f_last_hour=lastFundingRate/fundingIntervalHours",
                "L_prev(H)=sum(f_j where t-H<fundingTime_j<=t)",
                "L_prev_hour(H)=L_prev(H)/H_hours",
                "N_schedule=count configured event times within future H",
            ],
            source_support=[
                {
                    "source_id": "BINANCE-USD-M-MARKET-DATA",
                    "level": "definition",
                    "claim": (
                        "Funding rate, funding time, next time and adjusted "
                        "interval configuration."
                    ),
                },
                {
                    "source_id": "HE-MANELA-ROSS-VON-WACHTER-2022",
                    "level": "technical_foundation",
                    "claim": "Funding is an anchoring cash-flow mechanism.",
                },
            ],
            unsupported=[
                *common_limits,
                "Last observed funding is not the next funding rate.",
                "Historical average is not a future rate.",
                "Scheduled events do not imply a projected funding cost.",
            ],
            hypothesis={
                "id": "M4-HYP-FUNDING-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "Funding state may condition basis and positioning "
                    "interactions but has no standalone price direction."
                ),
            },
            expected_relation="No direct TP/SL effect; economic cost is M4.5.",
            related=[
                "M4-RULE-SPOT-FUTURES-BASIS-001",
                "M4-RULE-DERIVATIVES-CONTEXT-001",
            ],
            double_counting=(
                "Current, normalized and historical funding describe one "
                "funding family."
            ),
            missing="Funding context unavailable; never assume zero.",
            invariants=[
                "fundingIntervalHours>0",
                "funding events ordered and <=analysis_at",
                "future_funding_rate_assumption is null",
                "projected_funding_cost is null",
            ],
            trace=[
                "last_funding_rate",
                "interval_hours",
                "linearized_last_funding_rate_per_hour",
                "next_funding_time",
                "scheduled_events_under_current_config",
                "previous_horizon_funding_load",
                "projected_funding_cost",
            ],
            refutation=[
                "Retire interaction if no stable independent value.",
                "Projected cost requires M4.5 execution assumptions.",
            ],
        ),
        rule_card(
            "M4-RULE-DERIVATIVES-CONTEXT-001",
            "Vector continuo de contexto de derivados",
            blocks=[7, 9, 10, 15],
            objective=(
                "Expose flow, OI, basis and funding jointly without crowding "
                "labels, votes or additive scores."
            ),
            data_ids=[
                "M3-DATA-007",
                "M3-DATA-008",
                "M3-DATA-010",
                "M3-DATA-012",
                "M3-DATA-014",
                "M3-DATA-016",
                "M3-DATA-017",
            ],
            formula=[
                "DC_H=(ATI_H,dOI_H,b_mid,linearized_f_last_hour)"
            ],
            source_support=[
                {
                    "source_id": "M4.3-STRUCTURE",
                    "level": "internal_methodology",
                    "claim": (
                        "Interaction vectors reference atomic components "
                        "without adding them as separate evidence."
                    ),
                },
                {
                    "source_id": "M3-DATA-CONTRACTS",
                    "level": "data_foundation",
                    "claim": "Every component has a separate data contract.",
                },
            ],
            unsupported=[
                *common_limits,
                "The vector is not a crowding index.",
                "No component has a numeric coefficient.",
            ],
            hypothesis={
                "id": "M4-HYP-DERIVATIVES-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "Joint derivatives state may contain conditional value "
                    "not present in any marginal observation."
                ),
            },
            expected_relation="Unknown interaction; no direct probability.",
            related=[
                "M4-RULE-AGGRESSOR-IMBALANCE-001",
                "M4-RULE-OPEN-INTEREST-CHANGE-001",
                "M4-RULE-SPOT-FUTURES-BASIS-001",
                "M4-RULE-FUNDING-STATE-001",
            ],
            double_counting=(
                "The vector references four atomic families and adds no fifth "
                "piece of evidence."
            ),
            missing="Vector unavailable if any required component is absent.",
            invariants=[
                "ATI_H in [-1,1]",
                "all components continuous",
                "crowding_label is null",
                "aggregate_score is null",
            ],
            trace=[
                "ATI_H",
                "dOI_H",
                "b_mid",
                "linearized_f_last_hour",
                "crowding_label",
                "aggregate_score",
                "probability_effect",
            ],
            refutation=[
                "Retire interaction if no incremental validated value.",
                "Any coefficient requires M6 and independent validation.",
            ],
        ),
    ]


def validate_rules(rules: list[dict]) -> None:
    ids = [rule["id"] for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_rule_id")
    source_ids = {source["id"] for source in SOURCES}
    for rule in rules:
        used = {
            item["source_id"]
            for item in rule["source_and_exact_supported_claim"]
        }
        if not used.issubset(source_ids):
            raise ValueError(f"unknown_source:{rule['id']}")
        if (
            rule["direct_probability_effect_authorized"]
            or rule["numeric_weight_authorized"]
            or rule["production_authorized"]
        ):
            raise ValueError(f"unauthorized_effect:{rule['id']}")
        if not rule["exact_transformation_and_formula"]:
            raise ValueError(f"missing_formula:{rule['id']}")
        if not rule["claims_not_supported_by_source"]:
            raise ValueError(f"missing_transfer_limit:{rule['id']}")


def build_catalog() -> dict:
    m3 = read_json(M3_CATALOG_PATH)
    reconciliation = read_json(M4_RECONCILIATION_PATH)
    structure = read_json(M4_STRUCTURE_PATH)
    if m3["status"] != "completed_owner_approved":
        raise ValueError("m3_not_approved")
    if reconciliation["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_1_not_completed")
    if structure["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_3_not_completed")
    if structure["scope"]["m4_next_subphase"] != "M4.4":
        raise ValueError("m4_3_does_not_lead_to_m4_4")

    rules = build_rules()
    validate_rules(rules)
    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.4",
        "status": "completed_internal_milestone_m4_still_in_progress",
        "date": "2026-07-27",
        "scope": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "p0_blocks": [7, 9, 10, 15],
            "rules": len(rules),
            "direct_probability_effects": 0,
            "numeric_weights": 0,
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m5_started": False,
            "m4_next_subphase": "M4.5",
        },
        "operational_policies": {
            "exact_window": (
                "Every flow and OI change uses exact H; unavailable provider "
                "retention blocks unless an immutable local archive exists."
            ),
            "event_trade_retention": (
                "aggTrades REST covers at most the provider window documented "
                "by M3; no last-N replacement."
            ),
            "cross_venue_max_skew_ms": CROSS_VENUE_MAX_SKEW_MS,
            "spot_timestamp_quality": (
                "receive-time bounded and explicitly not market-time "
                "synchronized because Spot REST bookTicker has no provider "
                "event timestamp"
            ),
            "funding_projection_allowed": False,
            "market_leadership_label_allowed": False,
            "oi_positioning_label_allowed": False,
            "full_ofi_label_allowed": False,
            "classification": (
                "project operational policies, not published optima"
            ),
        },
        "policy_decision_records": [
            {
                "id": "M4-POLICY-CROSS-VENUE-MAX-RECEIVE-SKEW-001",
                "parameter": "cross_venue_max_receive_skew_ms",
                "value": CROSS_VENUE_MAX_SKEW_MS,
                "status": "provisional_project_policy_not_published_optimum",
                "rationale": (
                    "Bound asynchronous REST receive-time separation while "
                    "preserving the distinction from market synchronization."
                ),
                "tradeoff": (
                    "A tighter limit rejects more observations; a wider limit "
                    "admits more temporal basis uncertainty."
                ),
                "future_test": (
                    "Estimate basis stability and missingness sensitivity by "
                    "pair, horizon and receive-time skew before activation."
                ),
            }
        ],
        "amendment": {
            "supersedes_version": "M4.4-derivatives-context-v0.1",
            "reason": (
                "Add exact source/unit/coverage metadata, enforce exact OI "
                "endpoint separation, qualify receive-time basis uncertainty, "
                "and remove misleading funding and provider labels."
            ),
            "production_effect": False,
        },
        "sources": list(SOURCES),
        "rules": rules,
        "preregistered_hypotheses": [
            rule["separate_predictive_hypothesis"]
            for rule in rules
            if rule["separate_predictive_hypothesis"] is not None
        ],
        "evidence_families": [
            {
                "id": "M4-EVIDENCE-EXECUTED-AGGRESSOR-FLOW",
                "members": ["M4-RULE-AGGRESSOR-IMBALANCE-001"],
                "alternative_sources": [
                    "aggTrades",
                    "periodic taker volume",
                    "closed-kline taker volume",
                ],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-OPEN-INTEREST",
                "members": [
                    "M4-RULE-OPEN-INTEREST-CHANGE-001",
                    "M4-RULE-PRICE-OI-STATE-001",
                ],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-BASIS",
                "members": [
                    "M4-RULE-SPOT-FUTURES-BASIS-001",
                    "M4-RULE-MARK-INDEX-PREMIUM-001",
                ],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-FUNDING",
                "members": ["M4-RULE-FUNDING-STATE-001"],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-DERIVATIVES-CONTEXT",
                "members": ["M4-RULE-DERIVATIVES-CONTEXT-001"],
                "references_atomic_families": [
                    "M4-EVIDENCE-EXECUTED-AGGRESSOR-FLOW",
                    "M4-EVIDENCE-OPEN-INTEREST",
                    "M4-EVIDENCE-BASIS",
                    "M4-EVIDENCE-FUNDING",
                ],
                "additive_members_allowed": False,
            },
        ],
        "supersedes_current_elements": {
            "IND-CVD-PROXY": (
                "Renamed as executed aggressor imbalance; it is not CVD/OFI."
            ),
            "SCORE-TAKER_FLOW_BIAS": (
                "Legacy points replaced by exact-window descriptor."
            ),
            "SCORE-CVD_BIAS": (
                "Merged into the same aggressor evidence family."
            ),
            "SCORE-OI_TREND_BIAS": (
                "Replaced by dOI_H and an unweighted joint vector."
            ),
            "SCORE-OI_CONTEXT_PENALTY": (
                "Merged into the same OI family without quadrant labels."
            ),
            "SCORE-FUNDING_PENALTY": (
                "Replaced by interval-normalized funding state."
            ),
            "SCORE-FUNDING_RELATIVE_PENALTY": (
                "Merged into funding state; no threshold or penalty survives."
            ),
            "P0-BLOCK-SPOT-FUTURES": (
                "Defined as receive-time-bounded quotes with explicit temporal "
                "uncertainty; no market-time synchronization is claimed."
            ),
        },
        "summary": {
            "rules": len(rules),
            "hypotheses": sum(
                1
                for rule in rules
                if rule["separate_predictive_hypothesis"] is not None
            ),
            "evidence_families": 5,
            "rules_with_probability_effect": 0,
            "rules_with_numeric_weight": 0,
            "production_modified": False,
        },
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in (
                ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
                M3_CATALOG_PATH,
                M4_RECONCILIATION_PATH,
                M4_STRUCTURE_PATH,
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "operational_policies": payload["operational_policies"],
                "policy_decision_records": payload[
                    "policy_decision_records"
                ],
                "sources": payload["sources"],
                "rules": payload["rules"],
                "evidence_families": payload["evidence_families"],
                "supersedes_current_elements": payload[
                    "supersedes_current_elements"
                ],
            }
        )
    )
    return payload


def render_report(catalog: dict) -> str:
    lines = [
        "# M4.4 - Order flow, OI, basis y funding",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADA INTERNAMENTE; M4 SIGUE EN CURSO",
        "",
        "## 1. Resultado",
        "",
        f"- {catalog['summary']['rules']} fichas formales.",
        f"- {catalog['summary']['hypotheses']} hipotesis separadas.",
        "- 0 probabilidades, puntos, pesos o efectos productivos.",
        "- Produccion y aprendizaje permanecen congelados.",
        "",
        "## 2. Formulas",
        "",
        "- Agresion ejecutada: `ATI_H=(B_H-S_H)/(B_H+S_H)`.",
        "- OI: `dOI_H=ln(OI_t/OI_(t-H))`.",
        "- Estado precio-OI: `(D_H,dOI_H)` sin narrativa de cuadrantes.",
        "- Basis: tres razones logaritmicas con quotes limitados por tiempo de recepcion.",
        "- Prima mark-index: `ln(markPrice/indexPrice)`.",
        "- Funding: tasa observada linealizada por hora y carga realizada del H anterior.",
        "- Contexto: `(ATI_H,dOI_H,b_mid,linearized_f_last_hour)` sin score.",
        "",
        "## 3. Decisiones criticas",
        "",
        "- Taker imbalance no se denomina OFI ni CVD.",
        "- OI no identifica por si solo largos o cortos.",
        "- Spot o Futures no reciben liderazgo permanente.",
        "- La ultima tasa de funding no se trata como la tasa futura.",
        "- Medidas alternativas de una familia no se suman ni promedian.",
        "- Retencion insuficiente bloquea; no se sustituye por last-N.",
        "",
        "## 4. Reglas",
        "",
        "| ID | Probabilidad | Peso | Produccion |",
        "|---|---|---|---|",
    ]
    for rule in catalog["rules"]:
        lines.append(f"| `{rule['id']}` | no | no | no |")
    lines.extend(
        [
            "",
            "## 5. Limites de transferencia",
            "",
            "- La evidencia OFI publicada incluye libro, altas y cancelaciones.",
            "- La evidencia OI publicada procede de futuros tradicionales.",
            "- Los estudios spot-futuros no establecen un lider fijo.",
            "- El funding ancla el perpetuo, pero no predice direccion solo.",
            "- Las seis parejas y tres horizontes requieren validacion propia.",
            "",
            "## 6. Siguiente paso",
            "",
            "`M4.5`: ejecucion, costes, riesgo y evaluacion. Debera separar",
            "probabilidad de mercado de viabilidad economica de la operacion.",
            "",
            "SHA-256 del payload canonico (politicas, fuentes, reglas, "
            "familias y sustituciones): "
            f"`{catalog['canonical_payload_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            raise SystemExit(f"Generated artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    catalog = build_catalog()
    report = render_report(catalog)
    write_or_check(
        args.output,
        json.dumps(catalog, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, report, args.check)


if __name__ == "__main__":
    main()
