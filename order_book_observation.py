from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from statistics import median, pstdev
from typing import Any


CONTRACT_VERSION = "order-book-dynamics-v0.1"
SOURCE = "binance_usdm_depth_100_and_aggtrades"
MEASURE_KEYS = ("top_5", "top_20", "within_10bps", "within_20bps", "within_50bps")
SIGN_THRESHOLD = 0.02
WALL_MULTIPLE = 3.0
ABSORPTION_SCORE_THRESHOLD = 0.20
ABSORPTION_FOLLOW_THROUGH_BPS = 5.0
MINIMUM_DYNAMIC_SPAN_SECONDS = 15.0


class OrderBookObservationError(ValueError):
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
        raise OrderBookObservationError(f"{name}_invalid") from exc
    if not math.isfinite(number):
        raise OrderBookObservationError(f"{name}_nonfinite")
    return number


def _normalized_side(rows: Any, *, descending: bool, name: str) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    if not isinstance(rows, list):
        return normalized
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        try:
            price = _finite(row[0], f"{name}_price_{index}")
            quantity = _finite(row[1], f"{name}_quantity_{index}")
        except OrderBookObservationError:
            continue
        if price > 0 and quantity >= 0:
            normalized.append((price, price * quantity))
    return sorted(normalized, key=lambda item: item[0], reverse=descending)


def _imbalance(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> dict[str, float | None]:
    bid_notional = math.fsum(item[1] for item in bids)
    ask_notional = math.fsum(item[1] for item in asks)
    total = bid_notional + ask_notional
    return {
        "bid_notional": round(bid_notional, 2),
        "ask_notional": round(ask_notional, 2),
        "imbalance": round((bid_notional - ask_notional) / total, 8) if total > 0 else None,
    }


def _measurements(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    mid_price: float,
) -> dict[str, dict[str, float | None]]:
    result = {
        "top_5": _imbalance(bids[:5], asks[:5]),
        "top_20": _imbalance(bids[:20], asks[:20]),
    }
    for band_bps in (10, 20, 50):
        fraction = band_bps / 10_000.0
        result[f"within_{band_bps}bps"] = _imbalance(
            [row for row in bids if row[0] >= mid_price * (1.0 - fraction)],
            [row for row in asks if row[0] <= mid_price * (1.0 + fraction)],
        )
    return result


def _wall_candidates(
    levels: list[tuple[float, float]],
    *,
    side: str,
    mid_price: float,
) -> list[dict]:
    band = [
        row
        for row in levels
        if abs((row[0] - mid_price) / mid_price) <= 0.005
    ]
    positive = [notional for _price, notional in band if notional > 0]
    if not positive:
        return []
    baseline = median(positive)
    if baseline <= 0:
        return []
    candidates = []
    for price, notional in band:
        multiple = notional / baseline
        if multiple < WALL_MULTIPLE:
            continue
        candidates.append(
            {
                "side": side,
                "price": round(price, 8),
                "notional": round(notional, 2),
                "distance_bps": round((price - mid_price) / mid_price * 10_000, 4),
                "median_level_multiple": round(multiple, 4),
            }
        )
    return sorted(
        candidates,
        key=lambda item: item["notional"],
        reverse=True,
    )[:5]


def normalize_depth_snapshot(
    symbol: str,
    depth: dict,
    *,
    captured_at_ms: int,
) -> dict:
    if not isinstance(depth, dict):
        raise OrderBookObservationError("depth_payload_invalid")
    bids = _normalized_side(depth.get("bids"), descending=True, name="bid")
    asks = _normalized_side(depth.get("asks"), descending=False, name="ask")
    if not bids or not asks:
        raise OrderBookObservationError("depth_sides_unavailable")
    if bids[0][0] >= asks[0][0]:
        raise OrderBookObservationError("depth_book_crossed")
    provider_received_at = depth.get("receivedAt")
    try:
        received_at_ms = int(provider_received_at or captured_at_ms)
    except (TypeError, ValueError, OverflowError):
        received_at_ms = int(captured_at_ms)
    mid_price = (bids[0][0] + asks[0][0]) / 2.0
    measures = _measurements(bids, asks, mid_price)
    walls = {
        "bid": _wall_candidates(bids, side="bid", mid_price=mid_price),
        "ask": _wall_candidates(asks, side="ask", mid_price=mid_price),
    }
    fingerprint = canonical_sha256(
        {
            "symbol": str(symbol).upper(),
            "captured_at_ms": received_at_ms,
            "bids": bids,
            "asks": asks,
        }
    )
    return {
        "symbol": str(symbol).upper(),
        "captured_at_ms": received_at_ms,
        "mid_price": mid_price,
        "spread_fraction": (asks[0][0] - bids[0][0]) / mid_price,
        "measures": measures,
        "walls": walls,
        "bids": bids,
        "asks": asks,
        "visible_notional": math.fsum(item[1] for item in bids + asks),
        "source_data_sha256": fingerprint,
    }


def summarize_executed_trades(
    trades: Any,
    *,
    start_time_ms: int,
    end_time_ms: int,
) -> dict:
    buy_notional = 0.0
    sell_notional = 0.0
    accepted = 0
    rows = trades if isinstance(trades, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            timestamp = int(row.get("T") or row.get("time") or row.get("timestamp"))
            price = _finite(row.get("p") or row.get("price"), "trade_price")
            quantity = _finite(row.get("q") or row.get("qty") or row.get("quantity"), "trade_quantity")
        except (OrderBookObservationError, TypeError, ValueError, OverflowError):
            continue
        if timestamp < int(start_time_ms) or timestamp > int(end_time_ms):
            continue
        if price <= 0 or quantity < 0:
            continue
        notional = price * quantity
        if bool(row.get("m", row.get("isBuyerMaker", False))):
            sell_notional += notional
        else:
            buy_notional += notional
        accepted += 1
    total = buy_notional + sell_notional
    return {
        "buy_taker_notional": round(buy_notional, 2),
        "sell_taker_notional": round(sell_notional, 2),
        "executed_flow_imbalance": round((buy_notional - sell_notional) / total, 8) if total > 0 else None,
        "trade_rows": accepted,
        "provider_rows": len(rows),
        "possibly_truncated": len(rows) >= 1000,
    }


def _level_map(rows: list[tuple[float, float]]) -> dict[float, float]:
    return {round(price, 8): notional for price, notional in rows}


def _side_changes(
    previous: list[tuple[float, float]],
    current: list[tuple[float, float]],
) -> tuple[float, float]:
    before = _level_map(previous)
    after = _level_map(current)
    additions = removals = 0.0
    for price in set(before).union(after):
        delta = after.get(price, 0.0) - before.get(price, 0.0)
        if delta >= 0:
            additions += delta
        else:
            removals -= delta
    return additions, removals


def _wall_keys(sample: dict) -> set[tuple[str, float]]:
    return {
        (str(item["side"]), float(item["price"]))
        for side in ("bid", "ask")
        for item in sample["walls"][side]
    }


def _change_event(previous: dict, current: dict, flow: dict) -> dict:
    elapsed_seconds = max(
        (int(current["captured_at_ms"]) - int(previous["captured_at_ms"])) / 1000.0,
        0.001,
    )
    bid_added, bid_removed = _side_changes(previous["bids"], current["bids"])
    ask_added, ask_removed = _side_changes(previous["asks"], current["asks"])
    buy_flow = float(flow.get("buy_taker_notional") or 0.0)
    sell_flow = float(flow.get("sell_taker_notional") or 0.0)
    confirmed_bid_execution = min(bid_removed, sell_flow)
    confirmed_ask_execution = min(ask_removed, buy_flow)
    unmatched_bid_removal = max(0.0, bid_removed - confirmed_bid_execution)
    unmatched_ask_removal = max(0.0, ask_removed - confirmed_ask_execution)
    modified = bid_added + ask_added + bid_removed + ask_removed
    visible_reference = max(
        (float(previous["visible_notional"]) + float(current["visible_notional"])) / 2.0,
        1.0,
    )
    before_walls = _wall_keys(previous)
    after_walls = _wall_keys(current)
    return {
        "elapsed_seconds": elapsed_seconds,
        "bid_added_notional": bid_added,
        "ask_added_notional": ask_added,
        "bid_removed_notional": bid_removed,
        "ask_removed_notional": ask_removed,
        "execution_confirmed_bid_removal": confirmed_bid_execution,
        "execution_confirmed_ask_removal": confirmed_ask_execution,
        "unmatched_bid_removal": unmatched_bid_removal,
        "unmatched_ask_removal": unmatched_ask_removal,
        "modification_notional_per_second": modified / elapsed_seconds,
        "modification_fraction_per_second": modified / visible_reference / elapsed_seconds,
        "wall_appearances": sorted(after_walls - before_walls),
        "wall_disappearances": sorted(before_walls - after_walls),
    }


def _sign(value: float) -> int:
    if value > SIGN_THRESHOLD:
        return 1
    if value < -SIGN_THRESHOLD:
        return -1
    return 0


def _persistence(values: list[float], captured_at_ms: list[int]) -> dict:
    signs = [_sign(value) for value in values]
    non_neutral = [value for value in signs if value]
    sign_flips = sum(left != right for left, right in zip(non_neutral, non_neutral[1:]))
    elapsed_minutes = max(
        (captured_at_ms[-1] - captured_at_ms[0]) / 60_000.0,
        1 / 60,
    )
    return {
        "current": round(values[-1], 8),
        "mean": round(math.fsum(values) / len(values), 8),
        "median": round(median(values), 8),
        "stddev": round(pstdev(values), 8) if len(values) > 1 else 0.0,
        "minimum": round(min(values), 8),
        "maximum": round(max(values), 8),
        "positive_fraction": round(signs.count(1) / len(signs), 8),
        "negative_fraction": round(signs.count(-1) / len(signs), 8),
        "neutral_fraction": round(signs.count(0) / len(signs), 8),
        "sign_flip_count": sign_flips,
        "slope_per_minute": round((values[-1] - values[0]) / elapsed_minutes, 8),
        "sign_threshold": SIGN_THRESHOLD,
    }


def _sum_events(samples: list[dict]) -> dict:
    events = [sample.get("change") for sample in samples if sample.get("change")]
    numeric_keys = (
        "bid_added_notional",
        "ask_added_notional",
        "bid_removed_notional",
        "ask_removed_notional",
        "execution_confirmed_bid_removal",
        "execution_confirmed_ask_removal",
        "unmatched_bid_removal",
        "unmatched_ask_removal",
    )
    totals = {
        key: math.fsum(float(event.get(key) or 0.0) for event in events)
        for key in numeric_keys
    }
    removed = totals["bid_removed_notional"] + totals["ask_removed_notional"]
    unmatched = totals["unmatched_bid_removal"] + totals["unmatched_ask_removal"]
    velocities = [float(event["modification_fraction_per_second"]) for event in events]
    return {
        **{key: round(value, 2) for key, value in totals.items()},
        "unmatched_removal_fraction": round(unmatched / removed, 8) if removed > 0 else None,
        "unmatched_removal_semantics": "cancellation_like_or_unobserved_execution_not_proven_cancel",
        "mean_modification_fraction_per_second": round(math.fsum(velocities) / len(velocities), 10) if velocities else None,
        "maximum_modification_fraction_per_second": round(max(velocities), 10) if velocities else None,
        "wall_appearance_count": sum(len(event["wall_appearances"]) for event in events),
        "wall_disappearance_count": sum(len(event["wall_disappearances"]) for event in events),
        "transition_count": len(events),
    }


def _wall_summary(samples: list[dict]) -> dict:
    current = samples[-1]
    sample_keys = [_wall_keys(sample) for sample in samples]
    current_candidates = []
    for side in ("bid", "ask"):
        for item in current["walls"][side]:
            key = (side, float(item["price"]))
            persistence = sum(key in keys for keys in sample_keys) / len(sample_keys)
            current_candidates.append(
                {
                    **item,
                    "persistence_fraction": round(persistence, 8),
                    "observed_samples": sum(key in keys for keys in sample_keys),
                }
            )
    return {
        "definition": f"level_notional_at_least_{WALL_MULTIPLE:g}x_side_median_within_50bps",
        "current_candidates": current_candidates,
    }


def _flow_summary(samples: list[dict]) -> dict:
    buy = math.fsum(float(sample["flow"].get("buy_taker_notional") or 0.0) for sample in samples)
    sell = math.fsum(float(sample["flow"].get("sell_taker_notional") or 0.0) for sample in samples)
    total = buy + sell
    return {
        "buy_taker_notional": round(buy, 2),
        "sell_taker_notional": round(sell, 2),
        "executed_flow_imbalance": round((buy - sell) / total, 8) if total > 0 else None,
        "trade_rows": sum(int(sample["flow"].get("trade_rows") or 0) for sample in samples),
        "possibly_truncated": any(bool(sample["flow"].get("possibly_truncated")) for sample in samples),
    }


def _absorption_summary(samples: list[dict], activity: dict, flow: dict) -> dict:
    first_price = float(samples[0]["mid_price"])
    current_price = float(samples[-1]["mid_price"])
    price_change_bps = (current_price - first_price) / first_price * 10_000
    flow_imbalance = float(flow.get("executed_flow_imbalance") or 0.0)
    no_upward_follow_through = max(
        0.0,
        1.0 - max(price_change_bps, 0.0) / ABSORPTION_FOLLOW_THROUGH_BPS,
    )
    no_downward_follow_through = max(
        0.0,
        1.0 - max(-price_change_bps, 0.0) / ABSORPTION_FOLLOW_THROUGH_BPS,
    )
    ask_removed = float(activity.get("ask_removed_notional") or 0.0)
    bid_removed = float(activity.get("bid_removed_notional") or 0.0)
    ask_confirmed = float(activity.get("execution_confirmed_ask_removal") or 0.0)
    bid_confirmed = float(activity.get("execution_confirmed_bid_removal") or 0.0)
    ask_execution_share = min(1.0, ask_confirmed / ask_removed) if ask_removed > 0 else 0.0
    bid_execution_share = min(1.0, bid_confirmed / bid_removed) if bid_removed > 0 else 0.0
    ask_score = max(flow_imbalance, 0.0) * ask_execution_share * no_upward_follow_through
    bid_score = max(-flow_imbalance, 0.0) * bid_execution_share * no_downward_follow_through
    if ask_score >= ABSORPTION_SCORE_THRESHOLD and ask_score > bid_score:
        candidate = "ask_absorption_candidate"
    elif bid_score >= ABSORPTION_SCORE_THRESHOLD and bid_score > ask_score:
        candidate = "bid_absorption_candidate"
    else:
        candidate = "none"
    return {
        "price_change_bps": round(price_change_bps, 8),
        "executed_flow_imbalance": flow.get("executed_flow_imbalance"),
        "ask_absorption_score": round(ask_score, 8),
        "bid_absorption_score": round(bid_score, 8),
        "candidate": candidate,
        "score_threshold": ABSORPTION_SCORE_THRESHOLD,
        "follow_through_reference_bps": ABSORPTION_FOLLOW_THROUGH_BPS,
        "semantics": "executed_flow_against_visible_removal_without_directional_follow_through",
    }


class OrderBookObservationTracker:
    def __init__(self, *, window_seconds: int = 60, minimum_samples: int = 3):
        self.window_seconds = max(int(window_seconds), 20)
        self.minimum_samples = max(int(minimum_samples), 2)
        self._samples: dict[str, deque[dict]] = {}

    def trade_start_time_ms(self, symbol: str, now_ms: int) -> int:
        samples = self._samples.get(str(symbol).upper())
        if samples:
            return int(samples[-1]["captured_at_ms"]) + 1
        return int(now_ms) - self.window_seconds * 1000

    def observe(
        self,
        symbol: str,
        depth: dict,
        trades: list[dict],
        *,
        captured_at_ms: int,
    ) -> dict:
        normalized_symbol = str(symbol).upper()
        sample = normalize_depth_snapshot(
            normalized_symbol,
            depth,
            captured_at_ms=captured_at_ms,
        )
        samples = self._samples.setdefault(normalized_symbol, deque())
        previous = samples[-1] if samples else None
        flow_start = (
            int(previous["captured_at_ms"]) + 1
            if previous
            else int(sample["captured_at_ms"]) - self.window_seconds * 1000
        )
        sample["flow"] = summarize_executed_trades(
            trades,
            start_time_ms=flow_start,
            end_time_ms=int(sample["captured_at_ms"]),
        )
        sample["change"] = _change_event(previous, sample, sample["flow"]) if previous else None
        samples.append(sample)
        cutoff = int(sample["captured_at_ms"]) - self.window_seconds * 1000
        while samples and int(samples[0]["captured_at_ms"]) < cutoff:
            samples.popleft()
        return self._summary(normalized_symbol, list(samples))

    def _summary(self, symbol: str, samples: list[dict]) -> dict:
        captured_at_ms = [int(sample["captured_at_ms"]) for sample in samples]
        persistence = {}
        for key in MEASURE_KEYS:
            values = [
                float(sample["measures"][key]["imbalance"])
                for sample in samples
                if sample["measures"][key]["imbalance"] is not None
            ]
            if values:
                persistence[key] = _persistence(values, captured_at_ms[-len(values):])
        activity = _sum_events(samples)
        flow = _flow_summary(samples)
        span_seconds = max(0.0, (captured_at_ms[-1] - captured_at_ms[0]) / 1000.0)
        quality_status = (
            "ready"
            if (
                len(samples) >= self.minimum_samples
                and span_seconds >= MINIMUM_DYNAMIC_SPAN_SECONDS
            )
            else "partial"
        )
        payload = {
            "contract_version": CONTRACT_VERSION,
            "available": True,
            "status": quality_status,
            "reason": None if quality_status == "ready" else "insufficient_dynamic_samples",
            "symbol": symbol,
            "source": SOURCE,
            "captured_at_ms": captured_at_ms[-1],
            "window_started_at_ms": captured_at_ms[0],
            "window_target_seconds": self.window_seconds,
            "window_observed_seconds": round(span_seconds, 3),
            "sample_count": len(samples),
            "minimum_samples": self.minimum_samples,
            "minimum_window_observed_seconds": MINIMUM_DYNAMIC_SPAN_SECONDS,
            "current_snapshot": {
                "mid_price": round(float(samples[-1]["mid_price"]), 8),
                "spread_fraction": round(float(samples[-1]["spread_fraction"]), 10),
                "measures": samples[-1]["measures"],
                "source_data_sha256": samples[-1]["source_data_sha256"],
            },
            "persistence": persistence,
            "walls": _wall_summary(samples),
            "change_activity": activity,
            "executed_flow": flow,
            "absorption": _absorption_summary(samples, activity, flow),
            "raw_depth_persisted": False,
            "raw_trades_persisted": False,
            "probability_effect": "none_observation_only",
        }
        payload["summary_sha256"] = canonical_sha256(payload)
        return payload


__all__ = (
    "CONTRACT_VERSION",
    "MEASURE_KEYS",
    "OrderBookObservationError",
    "OrderBookObservationTracker",
    "SOURCE",
    "normalize_depth_snapshot",
    "summarize_executed_trades",
)
