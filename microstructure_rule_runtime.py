from __future__ import annotations

import hashlib
import json
import math
from statistics import median


RUNTIME_VERSION = "microstructure-rule-runtime-v0.1"
RULE_IDS = (
    "LIB-CAND-RELATIVE-VOLUME-001",
    "LIB-CAND-CVD-SLOPE-001",
    "LIB-CAND-ORDERBOOK-IMBALANCE-001",
)
BOOK_BANDS_BPS = (10, 20, 50)
BOOK_TOP_LEVELS = (5, 20)


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite_non_negative(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name}_must_be_finite_and_non_negative")
    return number


def _finite_positive(value, name: str) -> float:
    number = _finite_non_negative(value, name)
    if number <= 0:
        raise ValueError(f"{name}_must_be_positive")
    return number


def _side_sign(side: str) -> float:
    normalized = str(side).lower()
    if normalized == "long":
        return 1.0
    if normalized == "short":
        return -1.0
    raise ValueError("side_must_be_long_or_short")


def _trace(
    *,
    rule_id: str,
    family_id: str,
    role: str,
    parent_rule_ids: list[str],
    formula_ids: list[str],
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    source_data_sha256: str | None,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": rule_id,
        "rule_version": "0.1",
        "family_id": family_id,
        "role": role,
        "parent_rule_ids": parent_rule_ids,
        "status": status,
        "reason_codes": reason_codes,
        "formula_ids": formula_ids,
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": source_data_sha256,
        "executed_at": executed_at,
        "probability_effect": "none_shadow_observation",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def empirical_midrank(value: float, reference: list[float]) -> float:
    if not reference:
        raise ValueError("reference_required")
    below = sum(item < value for item in reference)
    equal = sum(item == value for item in reference)
    return (below + 0.5 * equal) / len(reference)


def evaluate_relative_volume(
    candles: list[dict],
    *,
    return_count: int,
    analysis_at: str,
    source_data_sha256: str,
) -> dict:
    required = 61 * int(return_count)
    inputs = {
        "return_count_per_horizon": int(return_count),
        "required_closed_candles": required,
        "observed_closed_candles": len(candles),
        "volume_unit": (
            "quote_asset"
            if candles and candles[-1].get("quote_volume") is not None
            else "base_asset"
        ),
    }
    if len(candles) < required:
        return _trace(
            rule_id="LIB-CAND-RELATIVE-VOLUME-001",
            family_id="FAMILY-VOLUME",
            role="standalone",
            parent_rule_ids=[],
            formula_ids=[
                "LIB-CAND-RELATIVE-VOLUME-001-FORMULA-01",
                "LIB-CAND-RELATIVE-VOLUME-001-FORMULA-02",
                "LIB-CAND-RELATIVE-VOLUME-001-FORMULA-03",
            ],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["insufficient_60_horizon_volume_history"],
            source_data_sha256=source_data_sha256,
            executed_at=analysis_at,
        )
    selected = candles[-required:]
    volume_key = (
        "quote_volume"
        if all(row.get("quote_volume") is not None for row in selected)
        else "volume"
    )
    horizon_volumes = []
    for start in range(0, required, return_count):
        horizon_volumes.append(
            math.fsum(
                _finite_non_negative(
                    row[volume_key],
                    f"{volume_key}_{start + offset}",
                )
                for offset, row in enumerate(
                    selected[start : start + return_count]
                )
            )
        )
    reference = horizon_volumes[:-1]
    current = horizon_volumes[-1]
    reference_median = median(reference)
    if reference_median <= 0:
        status = "blocked"
        reasons = ["zero_reference_volume_median"]
        outputs = {}
    else:
        status = "evaluated_shadow"
        reasons = []
        relative = current / reference_median
        outputs = {
            "volume_key": volume_key,
            "current_horizon_volume": current,
            "reference_horizon_count": len(reference),
            "reference_median_horizon_volume": reference_median,
            "relative_horizon_volume": relative,
            "volume_midrank_60": empirical_midrank(current, reference),
            "log_relative_horizon_volume": math.log(relative)
            if relative > 0
            else None,
        }
    return _trace(
        rule_id="LIB-CAND-RELATIVE-VOLUME-001",
        family_id="FAMILY-VOLUME",
        role="standalone",
        parent_rule_ids=[],
        formula_ids=[
            "LIB-CAND-RELATIVE-VOLUME-001-FORMULA-01",
            "LIB-CAND-RELATIVE-VOLUME-001-FORMULA-02",
            "LIB-CAND-RELATIVE-VOLUME-001-FORMULA-03",
        ],
        inputs=inputs,
        outputs=outputs,
        status=status,
        reason_codes=reasons,
        source_data_sha256=source_data_sha256,
        executed_at=analysis_at,
    )


def theil_sen_slope(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("at_least_two_values_required")
    slopes = [
        (values[right] - values[left]) / (right - left)
        for left in range(len(values) - 1)
        for right in range(left + 1, len(values))
    ]
    return median(slopes)


def _periodic_taker_rows(
    current_bars: list[dict],
    live_context: dict,
    interval_seconds: int,
) -> tuple[list[dict], str]:
    if not current_bars:
        return [], "none"
    interval_ms = int(interval_seconds) * 1000
    expected_start = int(current_bars[0]["open_time_ms"])
    expected_end = int(current_bars[-1]["close_time_ms"])
    rows = []
    for raw in live_context.get("taker_history", []):
        try:
            timestamp = int(raw["timestamp"])
            buy = _finite_non_negative(raw["buyVol"], "buyVol")
            sell = _finite_non_negative(raw["sellVol"], "sellVol")
        except (KeyError, TypeError, ValueError):
            continue
        if expected_start - 1 <= timestamp <= expected_end:
            rows.append(
                {
                    "timestamp": timestamp,
                    "buy": buy,
                    "sell": sell,
                }
            )
    rows.sort(key=lambda item: item["timestamp"])
    timestamps = [row["timestamp"] for row in rows]
    if (
        len(rows) == len(current_bars)
        and abs(timestamps[0] - expected_start) <= 1
        and all(
            right - left == interval_ms
            for left, right in zip(timestamps, timestamps[1:])
        )
    ):
        return rows, "binance_taker_buy_sell_ratio_history"
    fallback = []
    for row in current_bars:
        quote = row.get("quote_volume")
        taker_buy = row.get("taker_buy_quote_volume")
        if quote is None or taker_buy is None:
            return [], "none"
        buy = _finite_non_negative(taker_buy, "taker_buy_quote_volume")
        total = _finite_non_negative(quote, "quote_volume")
        fallback.append(
            {
                "timestamp": int(row["open_time_ms"]),
                "buy": buy,
                "sell": max(total - buy, 0.0),
            }
        )
    return fallback, "closed_kline_taker_quote_volume"


def evaluate_cvd(
    current_bars: list[dict],
    live_context: dict,
    *,
    side: str,
    interval_seconds: int,
    analysis_at: str,
) -> dict:
    rows, source = _periodic_taker_rows(
        current_bars,
        live_context,
        interval_seconds,
    )
    inputs = {
        "expected_periods": len(current_bars),
        "observed_periods": len(rows),
        "interval_seconds": int(interval_seconds),
        "source": source,
    }
    if not rows:
        return _trace(
            rule_id="LIB-CAND-CVD-SLOPE-001",
            family_id="FAMILY-EXECUTED-FLOW",
            role="group",
            parent_rule_ids=["M4-RULE-AGGRESSOR-IMBALANCE-001"],
            formula_ids=[
                "LIB-CAND-CVD-SLOPE-001-FORMULA-01",
                "LIB-CAND-CVD-SLOPE-001-FORMULA-02",
                "LIB-CAND-CVD-SLOPE-001-FORMULA-03",
                "LIB-CAND-CVD-SLOPE-001-FORMULA-04",
            ],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["exact_taker_window_unavailable"],
            source_data_sha256=None,
            executed_at=analysis_at,
        )
    deltas = [row["buy"] - row["sell"] for row in rows]
    totals = [row["buy"] + row["sell"] for row in rows]
    cvd = []
    running = 0.0
    for delta in deltas:
        running += delta
        cvd.append(running)
    total_activity = math.fsum(totals)
    raw_slope = theil_sen_slope(cvd)
    normalized_slope = (
        raw_slope / (total_activity / len(rows))
        if total_activity > 0
        else 0.0
    )
    terminal_imbalance = (
        math.fsum(deltas) / total_activity
        if total_activity > 0
        else 0.0
    )
    source_sha = canonical_sha256(rows)
    return _trace(
        rule_id="LIB-CAND-CVD-SLOPE-001",
        family_id="FAMILY-EXECUTED-FLOW",
        role="group",
        parent_rule_ids=["M4-RULE-AGGRESSOR-IMBALANCE-001"],
        formula_ids=[
            "LIB-CAND-CVD-SLOPE-001-FORMULA-01",
            "LIB-CAND-CVD-SLOPE-001-FORMULA-02",
            "LIB-CAND-CVD-SLOPE-001-FORMULA-03",
            "LIB-CAND-CVD-SLOPE-001-FORMULA-04",
        ],
        inputs=inputs,
        outputs={
            "terminal_cvd": cvd[-1],
            "theil_sen_cvd_slope_per_period": raw_slope,
            "normalized_cvd_slope": normalized_slope,
            "terminal_taker_imbalance": terminal_imbalance,
            "side_adjusted_normalized_cvd_slope": (
                _side_sign(side) * normalized_slope
            ),
            "side_adjusted_terminal_imbalance": (
                _side_sign(side) * terminal_imbalance
            ),
        },
        status="evaluated_shadow",
        reason_codes=[],
        source_data_sha256=source_sha,
        executed_at=analysis_at,
    )


def _normalize_book_side(
    rows: list,
    *,
    descending: bool,
    name: str,
) -> list[tuple[float, float]]:
    normalized = []
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            price = _finite_positive(row[0], f"{name}_price_{index}")
            quantity = _finite_non_negative(
                row[1],
                f"{name}_quantity_{index}",
            )
        except (TypeError, ValueError):
            continue
        normalized.append((price, quantity))
    return sorted(normalized, reverse=descending)


def _notional_imbalance(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> dict:
    bid_notional = math.fsum(price * quantity for price, quantity in bids)
    ask_notional = math.fsum(price * quantity for price, quantity in asks)
    total = bid_notional + ask_notional
    return {
        "bid_notional": bid_notional,
        "ask_notional": ask_notional,
        "imbalance": (
            (bid_notional - ask_notional) / total
            if total > 0
            else None
        ),
    }


def evaluate_order_book(
    live_context: dict,
    *,
    side: str,
    analysis_at: str,
) -> dict:
    observation = live_context.get("order_book_observation")
    if isinstance(observation, dict):
        current = observation.get("current_snapshot") or {}
        measures = current.get("measures") or {}
        inputs = {
            "captured_at_ms": observation.get("captured_at_ms"),
            "captured_at": observation.get("captured_at"),
            "age_seconds": observation.get("age_seconds"),
            "sample_count": observation.get("sample_count"),
            "window_observed_seconds": observation.get("window_observed_seconds"),
            "summary_sha256": observation.get("summary_sha256"),
        }
        if (
            not observation.get("available")
            or not current.get("mid_price")
            or not isinstance(measures, dict)
        ):
            reason = (
                observation.get("state_reason")
                or observation.get("reason")
                or "fresh_worker_order_book_observation_unavailable"
            )
            return _trace(
                rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
                family_id="FAMILY-ORDER-BOOK",
                role="standalone",
                parent_rule_ids=[],
                formula_ids=[
                    "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-01",
                    "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-02",
                ],
                inputs=inputs,
                outputs={},
                status="blocked",
                reason_codes=[str(reason)],
                source_data_sha256=observation.get("summary_sha256"),
                executed_at=analysis_at,
            )
        side_sign = _side_sign(side)
        side_adjusted = {
            name: (
                side_sign * float(value["imbalance"])
                if isinstance(value, dict) and value.get("imbalance") is not None
                else None
            )
            for name, value in measures.items()
        }
        return _trace(
            rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
            family_id="FAMILY-ORDER-BOOK",
            role="standalone",
            parent_rule_ids=[],
            formula_ids=[
                "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-01",
                "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-02",
            ],
            inputs=inputs,
            outputs={
                "mid_price": float(current["mid_price"]),
                "spread_fraction": current.get("spread_fraction"),
                "measures": measures,
                "side_adjusted_imbalances": side_adjusted,
            },
            status=(
                "evaluated_shadow"
                if observation.get("status") == "ready"
                else "partially_evaluated_shadow"
            ),
            reason_codes=(
                []
                if observation.get("status") == "ready"
                else [str(observation.get("reason") or "insufficient_dynamic_samples")]
            ),
            source_data_sha256=observation.get("summary_sha256"),
            executed_at=analysis_at,
        )

    depth = live_context.get("depth") or {}
    bids = _normalize_book_side(
        depth.get("bids", []),
        descending=True,
        name="bid",
    )
    asks = _normalize_book_side(
        depth.get("asks", []),
        descending=False,
        name="ask",
    )
    inputs = {
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "captured_at_ms": live_context.get("captured_at_ms"),
        "bands_bps": list(BOOK_BANDS_BPS),
        "top_levels": list(BOOK_TOP_LEVELS),
    }
    if not bids or not asks or bids[0][0] >= asks[0][0]:
        return _trace(
            rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
            family_id="FAMILY-ORDER-BOOK",
            role="standalone",
            parent_rule_ids=[],
            formula_ids=[
                "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-01",
                "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-02",
            ],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["valid_uncrossed_depth_snapshot_unavailable"],
            source_data_sha256=None,
            executed_at=analysis_at,
        )
    mid = (bids[0][0] + asks[0][0]) / 2.0
    measures = {}
    for level_count in BOOK_TOP_LEVELS:
        measures[f"top_{level_count}"] = _notional_imbalance(
            bids[:level_count],
            asks[:level_count],
        )
    for band_bps in BOOK_BANDS_BPS:
        fraction = band_bps / 10_000.0
        measures[f"within_{band_bps}bps"] = _notional_imbalance(
            [
                row
                for row in bids
                if row[0] >= mid * (1.0 - fraction)
            ],
            [
                row
                for row in asks
                if row[0] <= mid * (1.0 + fraction)
            ],
        )
    outputs = {
        "mid_price": mid,
        "spread_fraction": (asks[0][0] - bids[0][0]) / mid,
        "measures": measures,
        "side_adjusted_imbalances": {
            name: (
                _side_sign(side) * value["imbalance"]
                if value["imbalance"] is not None
                else None
            )
            for name, value in measures.items()
        },
    }
    source_payload = {
        "bids": bids,
        "asks": asks,
        "captured_at_ms": live_context.get("captured_at_ms"),
    }
    return _trace(
        rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
        family_id="FAMILY-ORDER-BOOK",
        role="standalone",
        parent_rule_ids=[],
        formula_ids=[
            "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-01",
            "LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-02",
        ],
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_data_sha256=canonical_sha256(source_payload),
        executed_at=analysis_at,
    )


def evaluate_order_book_dynamics(
    observation: dict | None,
    *,
    side: str,
    analysis_at: str,
) -> dict:
    context = observation if isinstance(observation, dict) else {}
    inputs = {
        "contract_version": context.get("contract_version"),
        "captured_at_ms": context.get("captured_at_ms"),
        "captured_at": context.get("captured_at"),
        "age_seconds": context.get("age_seconds"),
        "sample_count": context.get("sample_count"),
        "minimum_samples": context.get("minimum_samples"),
        "window_target_seconds": context.get("window_target_seconds"),
        "window_observed_seconds": context.get("window_observed_seconds"),
        "summary_sha256": context.get("summary_sha256"),
    }
    if not context.get("available"):
        reason = (
            context.get("state_reason")
            or context.get("reason")
            or "fresh_worker_order_book_dynamics_unavailable"
        )
        return _trace(
            rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
            family_id="FAMILY-ORDER-BOOK",
            role="standalone",
            parent_rule_ids=[],
            formula_ids=[
                f"LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-{index:02d}"
                for index in range(1, 9)
            ],
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[str(reason)],
            source_data_sha256=context.get("summary_sha256"),
            executed_at=analysis_at,
        )

    direction = _side_sign(side)
    current = context.get("current_snapshot") or {}
    current_measures = current.get("measures") or {}
    current_side_adjusted = {
        name: (
            direction * float(value["imbalance"])
            if isinstance(value, dict) and value.get("imbalance") is not None
            else None
        )
        for name, value in current_measures.items()
    }
    persistence = {}
    for name, raw in (context.get("persistence") or {}).items():
        if not isinstance(raw, dict):
            continue
        persistence[name] = {
            **raw,
            "side_adjusted_current": (
                direction * float(raw["current"])
                if raw.get("current") is not None
                else None
            ),
            "side_adjusted_mean": (
                direction * float(raw["mean"])
                if raw.get("mean") is not None
                else None
            ),
            "side_adjusted_slope_per_minute": (
                direction * float(raw["slope_per_minute"])
                if raw.get("slope_per_minute") is not None
                else None
            ),
        }
    walls = context.get("walls") or {}
    wall_candidates = []
    for raw in walls.get("current_candidates", []):
        if not isinstance(raw, dict):
            continue
        wall_side = str(raw.get("side") or "")
        favorable = (
            (str(side).lower() == "long" and wall_side == "bid")
            or (str(side).lower() == "short" and wall_side == "ask")
        )
        wall_candidates.append({**raw, "relationship_to_trade": "favorable" if favorable else "adverse"})
    flow = context.get("executed_flow") or {}
    absorption = context.get("absorption") or {}
    outputs = {
        "current_snapshot": {
            **current,
            "side_adjusted_imbalances": current_side_adjusted,
        },
        "persistence": persistence,
        "walls": {
            **walls,
            "current_candidates": wall_candidates,
        },
        "change_activity": context.get("change_activity") or {},
        "executed_flow": {
            **flow,
            "side_adjusted_executed_flow_imbalance": (
                direction * float(flow["executed_flow_imbalance"])
                if flow.get("executed_flow_imbalance") is not None
                else None
            ),
        },
        "absorption": {
            **absorption,
            "favorable_absorption_score": (
                absorption.get("bid_absorption_score")
                if str(side).lower() == "long"
                else absorption.get("ask_absorption_score")
            ),
            "adverse_absorption_score": (
                absorption.get("ask_absorption_score")
                if str(side).lower() == "long"
                else absorption.get("bid_absorption_score")
            ),
        },
        "raw_depth_persisted": bool(context.get("raw_depth_persisted")),
        "raw_trades_persisted": bool(context.get("raw_trades_persisted")),
    }
    ready = context.get("status") == "ready"
    return _trace(
        rule_id="LIB-CAND-ORDERBOOK-IMBALANCE-001",
        family_id="FAMILY-ORDER-BOOK",
        role="standalone",
        parent_rule_ids=[],
        formula_ids=[
            f"LIB-CAND-ORDERBOOK-IMBALANCE-001-FORMULA-{index:02d}"
            for index in range(1, 9)
        ],
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow" if ready else "partially_evaluated_shadow",
        reason_codes=[] if ready else [str(context.get("reason") or "insufficient_dynamic_samples")],
        source_data_sha256=context.get("summary_sha256"),
        executed_at=analysis_at,
    )


def evaluate_microstructure_rule_family(
    *,
    selected_candles: list[dict],
    current_bars: list[dict],
    live_context: dict | None,
    return_count: int,
    interval_seconds: int,
    side: str,
    analysis_at: str,
    source_data_sha256: str,
) -> dict:
    context = live_context or {}
    traces = [
        evaluate_relative_volume(
            selected_candles,
            return_count=return_count,
            analysis_at=analysis_at,
            source_data_sha256=source_data_sha256,
        ),
        evaluate_cvd(
            current_bars,
            context,
            side=side,
            interval_seconds=interval_seconds,
            analysis_at=analysis_at,
        ),
        evaluate_order_book(
            context,
            side=side,
            analysis_at=analysis_at,
        ),
    ]
    evaluated = sum(
        trace["status"] == "evaluated_shadow" for trace in traces
    )
    result = {
        "runtime_version": RUNTIME_VERSION,
        "status": (
            "evaluated_shadow"
            if evaluated == len(traces)
            else "partially_evaluated_shadow"
            if evaluated
            else "blocked"
        ),
        "analysis_at": analysis_at,
        "rule_ids": list(RULE_IDS),
        "evaluated_rule_count": evaluated,
        "traces": traces,
    }
    result["runtime_trace_sha256"] = canonical_sha256(result)
    return result
