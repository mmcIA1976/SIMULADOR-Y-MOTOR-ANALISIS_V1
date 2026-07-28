from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import market_data
from m6_competing_risks import (
    adjusted_interval_hazards,
    apply_competing_risk_evidence,
    build_baseline_intervals,
    canonical_sha256,
)
from m6_first_passage import double_barrier_first_passage


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)
HORIZON_SECONDS = {
    "intraday_short": 4 * 60 * 60,
    "intraday_wide": 24 * 60 * 60,
    "short_swing": 7 * 24 * 60 * 60,
}
PROFILE_INTERVALS_SECONDS = {
    "intraday_short": (60, 180, 300, 900),
    "intraday_wide": (300, 900, 1800, 3600),
    "short_swing": (3600, 7200, 14400, 21600, 28800, 43200, 86400),
}
BINANCE_INTERVALS = {
    60: "1m",
    180: "3m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    7200: "2h",
    14400: "4h",
    21600: "6h",
    28800: "8h",
    43200: "12h",
    86400: "1d",
}
FEATURE_NAMES = (
    "directional_path_efficiency_h",
    "directional_path_efficiency_2h",
    "directional_path_efficiency_4h",
    "volatility_percentile_60",
    "target_extreme_between_entry_and_tp",
)
FIT_FEATURE_NAMES = ("intercept",) + FEATURE_NAMES
RIDGE_CANDIDATES = (0.1, 1.0, 10.0)
TEMPERATURE_CANDIDATES = (0.75, 1.0, 1.25, 1.5)
ONE_MINUTE_MS = 60_000


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def selected_interval_seconds(horizon: str, horizon_seconds: int) -> int:
    candidates = [
        interval
        for interval in PROFILE_INTERVALS_SECONDS[horizon]
        if horizon_seconds % interval == 0
        and horizon_seconds // interval >= 24
    ]
    if not candidates:
        raise ValueError("no_exact_supported_interval")
    return max(candidates)


def resolve_horizon(snapshot: dict, time_horizon: str) -> dict:
    expected = HORIZON_SECONDS.get(time_horizon)
    if expected is None:
        return {
            "status": "invalid",
            "seconds": None,
            "source": "unsupported_horizon",
            "formal_eligible": False,
        }
    stored = snapshot.get("evaluation_horizon_seconds")
    try:
        stored_seconds = int(stored)
    except (TypeError, ValueError):
        stored_seconds = None
    if stored_seconds is not None:
        lower = {
            "intraday_short": 30 * 60,
            "intraday_wide": 4 * 60 * 60,
            "short_swing": 24 * 60 * 60,
        }[time_horizon]
        if lower <= stored_seconds <= expected:
            return {
                "status": "stored_exact",
                "seconds": stored_seconds,
                "source": "snapshot.evaluation_horizon_seconds",
                "formal_eligible": True,
            }
        return {
            "status": "invalid",
            "seconds": None,
            "source": "stored_horizon_outside_frame",
            "formal_eligible": False,
        }
    return {
        "status": "policy_reconstructed",
        "seconds": expected,
        "source": "frozen_selected_frame_upper_bound_v0.1",
        "formal_eligible": False,
    }


def partition_for_analysis(analysis_at: datetime, cuts: dict) -> str:
    day = analysis_at.date()
    if day <= date.fromisoformat(cuts["development_end"]):
        return "development"
    if day <= date.fromisoformat(cuts["calibration_end"]):
        return "calibration"
    return "final_test"


def normalize_candidate_rows(rows: Iterable[dict], cuts: dict) -> list[dict]:
    normalized = []
    for raw in rows:
        snapshot = parse_json_object(raw.get("snapshot_json"))
        analysis = parse_json_object(raw.get("analysis_json"))
        if not snapshot or not analysis:
            continue
        analysis_at = parse_utc(raw.get("analysis_at"))
        if analysis_at is None:
            continue
        horizon = resolve_horizon(snapshot, str(raw.get("time_horizon")))
        if horizon["seconds"] is None:
            continue
        expiry = analysis_at + timedelta(seconds=horizon["seconds"])
        normalized.append(
            {
                "recommendation_id": int(raw["recommendation_id"]),
                "operation_id": int(raw["operation_id"]),
                "analysis_at": iso_utc(analysis_at),
                "analysis_day_utc": analysis_at.date().isoformat(),
                "expiry_at": iso_utc(expiry),
                "partition": partition_for_analysis(analysis_at, cuts),
                "symbol": str(raw["symbol"]).upper(),
                "side": str(raw["side"]).lower(),
                "time_horizon": str(raw["time_horizon"]),
                "horizon_seconds": int(horizon["seconds"]),
                "horizon_status": horizon["status"],
                "horizon_source": horizon["source"],
                "formal_eligible_horizon": horizon["formal_eligible"],
                "entry": float(raw["entry"]),
                "take_profit": float(raw["take_profit"]),
                "stop_loss": float(raw["stop_loss"]),
                "engine_version": str(raw.get("engine_version") or ""),
                "snapshot_sha256": payload_sha256(snapshot),
                "_snapshot": snapshot,
            }
        )
    return normalized


def fetch_klines_range(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
) -> list[list]:
    rows: dict[int, list] = {}
    cursor = int(start_ms)
    while cursor <= end_ms:
        batch = loader(
            symbol,
            interval,
            1500,
            start_time_ms=cursor,
            end_time_ms=end_ms,
        )
        if not batch:
            break
        for raw in batch:
            if not isinstance(raw, (list, tuple)) or len(raw) < 7:
                continue
            rows[int(raw[0])] = list(raw)
        next_cursor = int(batch[-1][0]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("non_advancing_kline_cursor")
        cursor = next_cursor
        if len(batch) < 1500:
            break
    return [rows[key] for key in sorted(rows)]


def merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((int(start), int(end)) for start, end in ranges)
    merged: list[list[int]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1] + ONE_MINUTE_MS:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def normalize_kline(raw: list) -> dict:
    normalized = {
        "open_time_ms": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "close_time_ms": int(raw[6]),
    }
    if len(raw) > 7:
        normalized["quote_volume"] = float(raw[7])
    if len(raw) > 9:
        normalized["taker_buy_base_volume"] = float(raw[9])
    if len(raw) > 10:
        normalized["taker_buy_quote_volume"] = float(raw[10])
    return normalized


def kline_fingerprint(candles: list[dict]) -> str | None:
    if not candles:
        return None
    return payload_sha256(
        [
            [
                row["open_time_ms"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                row["close_time_ms"],
            ]
            for row in candles
        ]
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


def midrank_percentile(current: float, reference: list[float]) -> float:
    below = sum(value < current for value in reference)
    equal = sum(value == current for value in reference)
    return (below + 0.5 * equal) / len(reference)


def derive_pretrade_features(record: dict, candles: list[dict]) -> dict:
    analysis_ms = int(parse_utc(record["analysis_at"]).timestamp() * 1000)
    closed = [row for row in candles if row["close_time_ms"] <= analysis_ms]
    interval_seconds = selected_interval_seconds(
        record["time_horizon"],
        record["horizon_seconds"],
    )
    return_count = record["horizon_seconds"] // interval_seconds
    required_returns = 61 * return_count
    required_closes = required_returns + 1
    if len(closed) < required_closes:
        return {
            "status": "insufficient_pretrade_history",
            "required_closes": required_closes,
            "available_closes": len(closed),
        }
    selected = closed[-required_closes:]
    closes = [row["close"] for row in selected]
    returns = _returns(closes)
    if len(returns) != required_returns:
        return {"status": "invalid_return_count"}
    current = returns[-return_count:]
    variance = math.fsum(value * value for value in current)
    sigma = math.sqrt(variance)
    if not math.isfinite(sigma) or sigma <= 0:
        return {"status": "invalid_realized_volatility"}
    reference = [
        math.fsum(value * value for value in returns[index : index + return_count])
        for index in range(0, 60 * return_count, return_count)
    ]
    side_sign = 1.0 if record["side"] == "long" else -1.0
    current_bars = selected[-return_count:]
    prior_high = max(row["high"] for row in current_bars)
    prior_low = min(row["low"] for row in current_bars)
    entry = record["entry"]
    tp = record["take_profit"]
    target = prior_high if side_sign > 0 else prior_low
    target_between = (
        entry < target < tp if side_sign > 0 else tp < target < entry
    )
    values = {
        "directional_path_efficiency_h": side_sign
        * _signed_efficiency(returns[-return_count:]),
        "directional_path_efficiency_2h": side_sign
        * _signed_efficiency(returns[-2 * return_count :]),
        "directional_path_efficiency_4h": side_sign
        * _signed_efficiency(returns[-4 * return_count :]),
        "volatility_percentile_60": midrank_percentile(variance, reference),
        "target_extreme_between_entry_and_tp": 1.0 if target_between else 0.0,
    }
    return {
        "status": "evaluated",
        "interval": BINANCE_INTERVALS[interval_seconds],
        "interval_seconds": interval_seconds,
        "return_count_per_horizon": return_count,
        "data_cutoff_at": datetime.fromtimestamp(
            selected[-1]["close_time_ms"] / 1000,
            tz=timezone.utc,
        ).isoformat(),
        "sigma_horizon": sigma,
        "current_realized_variance": variance,
        "feature_values": values,
        "source_rule_ids": {
            "directional_path_efficiency_h": "M4-RULE-PATH-STRUCTURE-001",
            "directional_path_efficiency_2h": "M4-RULE-MTF-HIERARCHY-001",
            "directional_path_efficiency_4h": "M4-RULE-MTF-HIERARCHY-001",
            "volatility_percentile_60": "M4-RULE-VOLATILITY-RANK-001",
            "target_extreme_between_entry_and_tp": "M4-RULE-PRIOR-EXTREMA-001",
        },
        "pretrade_candle_sha256": kline_fingerprint(selected),
    }


def enrich_pretrade_features(
    records: list[dict],
    *,
    loader: Callable[..., list[list]] = market_data.get_klines,
) -> list[dict]:
    grouped: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for record in records:
        interval_seconds = selected_interval_seconds(
            record["time_horizon"],
            record["horizon_seconds"],
        )
        grouped[
            (
                record["symbol"],
                BINANCE_INTERVALS[interval_seconds],
                interval_seconds,
            )
        ].append(record)
    for (symbol, interval, interval_seconds), members in grouped.items():
        earliest = min(parse_utc(row["analysis_at"]) for row in members)
        latest = max(parse_utc(row["analysis_at"]) for row in members)
        maximum_horizon = max(row["horizon_seconds"] for row in members)
        start_ms = int(
            (earliest - timedelta(seconds=62 * maximum_horizon)).timestamp()
            * 1000
        )
        end_ms = int(latest.timestamp() * 1000)
        raw = fetch_klines_range(
            symbol,
            interval,
            start_ms,
            end_ms,
            loader=loader,
        )
        candles = [normalize_kline(row) for row in raw]
        for record in members:
            record["pretrade"] = derive_pretrade_features(record, candles)
    return records


def candle_hits(record: dict, candle: dict) -> tuple[bool, bool]:
    if record["side"] == "long":
        return (
            candle["low"] <= record["stop_loss"],
            candle["high"] >= record["take_profit"],
        )
    return (
        candle["high"] >= record["stop_loss"],
        candle["low"] <= record["take_profit"],
    )


def classify_outcome(
    record: dict,
    candles: list[dict],
    *,
    captured_at: datetime,
) -> dict:
    analysis_at = parse_utc(record["analysis_at"])
    expiry_at = parse_utc(record["expiry_at"])
    start_ms = int(analysis_at.timestamp() * 1000)
    expiry_ms = int(expiry_at.timestamp() * 1000)
    observed_end = min(expiry_at, captured_at)
    end_ms = int(observed_end.timestamp() * 1000)
    selected = [
        row
        for row in candles
        if row["close_time_ms"] >= start_ms and row["open_time_ms"] <= end_ms
    ]
    expected = (
        end_ms // ONE_MINUTE_MS - start_ms // ONE_MINUTE_MS + 1
        if end_ms >= start_ms
        else 0
    )
    coverage = len(selected) / expected if expected else 0.0
    if coverage < 0.98:
        return {
            "status": "excluded_missing_market_coverage",
            "label": None,
            "coverage_ratio": round(coverage, 6),
            "candle_count": len(selected),
            "expected_candle_count": expected,
            "market_sha256": kline_fingerprint(selected),
        }
    for candle in selected:
        stop_hit, target_hit = candle_hits(record, candle)
        if not stop_hit and not target_hit:
            continue
        boundary = (
            start_ms > candle["open_time_ms"]
            or end_ms < candle["close_time_ms"]
        )
        if stop_hit and target_hit:
            status = "ambiguous_same_minute"
        elif boundary:
            status = "ambiguous_boundary_minute"
        else:
            status = "resolved"
        label = None
        if status == "resolved":
            label = (
                "sl_first_within_horizon"
                if stop_hit
                else "tp_first_within_horizon"
            )
        return {
            "status": status,
            "label": label,
            "first_touch_at": datetime.fromtimestamp(
                candle["open_time_ms"] / 1000,
                tz=timezone.utc,
            ).isoformat(),
            "coverage_ratio": round(coverage, 6),
            "candle_count": len(selected),
            "expected_candle_count": expected,
            "market_sha256": kline_fingerprint(selected),
        }
    if captured_at >= expiry_at:
        return {
            "status": "resolved",
            "label": "neither_barrier_before_expiry",
            "first_touch_at": None,
            "coverage_ratio": round(coverage, 6),
            "candle_count": len(selected),
            "expected_candle_count": expected,
            "market_sha256": kline_fingerprint(selected),
        }
    return {
        "status": "right_censored_not_expired",
        "label": None,
        "first_touch_at": None,
        "coverage_ratio": round(coverage, 6),
        "candle_count": len(selected),
        "expected_candle_count": expected,
        "market_sha256": kline_fingerprint(selected),
    }


def enrich_outcomes(
    records: list[dict],
    *,
    captured_at: datetime,
    loader: Callable[..., list[list]] = market_data.get_klines,
) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["symbol"]].append(record)
    for symbol, members in grouped.items():
        ranges = []
        for record in members:
            start_ms = int(parse_utc(record["analysis_at"]).timestamp() * 1000)
            expiry = min(parse_utc(record["expiry_at"]), captured_at)
            end_ms = int(expiry.timestamp() * 1000)
            if end_ms >= start_ms:
                ranges.append(
                    (
                        start_ms - (start_ms % ONE_MINUTE_MS),
                        end_ms + ONE_MINUTE_MS,
                    )
                )
        candles = []
        for start_ms, end_ms in merge_ranges(ranges):
            raw = fetch_klines_range(
                symbol,
                "1m",
                start_ms,
                end_ms,
                loader=loader,
            )
            candles.extend(normalize_kline(row) for row in raw)
        deduplicated = {
            row["open_time_ms"]: row
            for row in candles
        }
        ordered = [deduplicated[key] for key in sorted(deduplicated)]
        for record in members:
            record["outcome"] = classify_outcome(
                record,
                ordered,
                captured_at=captured_at,
            )
    return records


def public_record(record: dict, *, include_outcome: bool) -> dict:
    result = {
        key: value
        for key, value in record.items()
        if not key.startswith("_") and key != "outcome"
    }
    if include_outcome:
        result["outcome"] = record.get("outcome")
    return result


def baseline_probabilities(record: dict) -> dict[str, float]:
    entry = record["entry"]
    direction = 1 if record["side"] == "long" else -1
    tp_distance = direction * math.log(record["take_profit"] / entry)
    sl_distance = -direction * math.log(record["stop_loss"] / entry)
    result = double_barrier_first_passage(
        tp_log_distance=tp_distance,
        sl_log_distance=sl_distance,
        sigma_horizon=record["pretrade"]["sigma_horizon"],
    )
    return {
        CLASSES[0]: result.p_tp,
        CLASSES[1]: result.p_sl,
        CLASSES[2]: result.p_expiry,
    }


def eligible_labeled_rows(records: Iterable[dict]) -> list[dict]:
    return [
        row
        for row in records
        if row.get("pretrade", {}).get("status") == "evaluated"
        and row.get("outcome", {}).get("status") == "resolved"
        and row.get("outcome", {}).get("label") in CLASSES
    ]


def empirical_probabilities(rows: list[dict]) -> dict[str, float]:
    counts = Counter(row["outcome"]["label"] for row in rows)
    total = len(rows)
    if total == 0:
        raise ValueError("empty_empirical_training_rows")
    return {name: counts[name] / total for name in CLASSES}


def metric_brier(rows: list[dict], predictions: dict[int, dict]) -> float:
    if not rows:
        return math.nan
    values = []
    for row in rows:
        predicted = predictions[row["recommendation_id"]]
        actual = row["outcome"]["label"]
        values.append(
            math.fsum(
                (predicted[name] - (1.0 if name == actual else 0.0)) ** 2
                for name in CLASSES
            )
        )
    return math.fsum(values) / len(values)


def metric_log_loss(rows: list[dict], predictions: dict[int, dict]) -> float:
    if not rows:
        return math.nan
    return -math.fsum(
        math.log(
            max(
                1e-15,
                predictions[row["recommendation_id"]][row["outcome"]["label"]],
            )
        )
        for row in rows
    ) / len(rows)


def rank_auc(scores: list[float], labels: list[int]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    wins = 0.0
    for index, label in enumerate(labels):
        if label != 1:
            continue
        for other, other_label in enumerate(labels):
            if other_label != 0:
                continue
            if scores[index] > scores[other]:
                wins += 1.0
            elif scores[index] == scores[other]:
                wins += 0.5
    return wins / (positives * negatives)


def calibration_report(rows: list[dict], predictions: dict[int, dict]) -> dict:
    class_reports = {}
    errors = []
    bin_count = max(1, min(10, len(rows) // 20))
    for class_name in CLASSES:
        ordered = sorted(
            rows,
            key=lambda row: predictions[row["recommendation_id"]][class_name],
        )
        bins = []
        for index in range(bin_count):
            start = index * len(ordered) // bin_count
            end = (index + 1) * len(ordered) // bin_count
            members = ordered[start:end]
            if not members:
                continue
            forecast = math.fsum(
                predictions[row["recommendation_id"]][class_name]
                for row in members
            ) / len(members)
            observed = sum(
                row["outcome"]["label"] == class_name for row in members
            ) / len(members)
            error = abs(forecast - observed)
            errors.append(error * len(members) / max(1, len(rows) * len(CLASSES)))
            bins.append(
                {
                    "n": len(members),
                    "mean_forecast": forecast,
                    "observed_frequency": observed,
                    "absolute_error": error,
                }
            )
        class_reports[class_name] = bins
    return {
        "bin_count": bin_count,
        "weighted_absolute_calibration_error": math.fsum(errors),
        "classes": class_reports,
    }


def evaluate_predictions(rows: list[dict], predictions: dict[int, dict]) -> dict:
    aucs = []
    auc_by_class = {}
    for class_name in CLASSES:
        scores = [
            predictions[row["recommendation_id"]][class_name]
            for row in rows
        ]
        labels = [
            1 if row["outcome"]["label"] == class_name else 0
            for row in rows
        ]
        auc = rank_auc(scores, labels)
        auc_by_class[class_name] = auc
        if auc is not None:
            aucs.append(auc)
    return {
        "n": len(rows),
        "class_counts": dict(
            Counter(row["outcome"]["label"] for row in rows)
        ),
        "brier_3c": metric_brier(rows, predictions),
        "log_loss_3c": metric_log_loss(rows, predictions),
        "macro_ovr_auc": math.fsum(aucs) / len(aucs) if aucs else None,
        "ovr_auc_by_class": auc_by_class,
        "calibration": calibration_report(rows, predictions),
    }


def standardization(rows: list[dict]) -> dict:
    result = {}
    for name in FEATURE_NAMES:
        values = [row["pretrade"]["feature_values"][name] for row in rows]
        mean = math.fsum(values) / len(values)
        variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
        scale = math.sqrt(variance)
        result[name] = {"mean": mean, "scale": scale if scale > 1e-12 else 1.0}
    return result


def standardized_features(record: dict, scaling: dict) -> dict[str, float]:
    values = {"intercept": 1.0}
    for name in FEATURE_NAMES:
        raw = record["pretrade"]["feature_values"][name]
        values[name] = (raw - scaling[name]["mean"]) / scaling[name]["scale"]
    return values


def _predict_from_intervals(
    intervals: tuple[dict, ...],
    eta_tp: float,
    eta_sl: float,
) -> tuple[float, float, float]:
    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    for interval in intervals:
        h_tp, h_sl, h_none = adjusted_interval_hazards(
            interval,
            eta_tp,
            eta_sl,
        )
        cumulative_tp += survival * h_tp
        cumulative_sl += survival * h_sl
        survival *= h_none
    return cumulative_tp, cumulative_sl, survival


def prepare_fit_rows(rows: list[dict], scaling: dict) -> list[dict]:
    prepared = []
    for row in rows:
        baseline = baseline_probabilities(row)
        direction = 1 if row["side"] == "long" else -1
        tp_distance = direction * math.log(row["take_profit"] / row["entry"])
        sl_distance = -direction * math.log(row["stop_loss"] / row["entry"])
        prepared.append(
            {
                "recommendation_id": row["recommendation_id"],
                "features": standardized_features(row, scaling),
                "label": row["outcome"]["label"],
                "baseline": baseline,
                "intervals": build_baseline_intervals(
                    tp_log_distance=tp_distance,
                    sl_log_distance=sl_distance,
                    sigma_horizon=row["pretrade"]["sigma_horizon"],
                    interval_count=24,
                ),
            }
        )
    return prepared


def competing_risk_compatibility(
    rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    compatible = []
    blocked = []
    for row in rows:
        try:
            direction = 1 if row["side"] == "long" else -1
            build_baseline_intervals(
                tp_log_distance=direction
                * math.log(row["take_profit"] / row["entry"]),
                sl_log_distance=-direction
                * math.log(row["stop_loss"] / row["entry"]),
                sigma_horizon=row["pretrade"]["sigma_horizon"],
                interval_count=24,
            )
        except Exception as exc:
            blocked.append(
                {
                    "recommendation_id": row["recommendation_id"],
                    "partition": row["partition"],
                    "symbol": row["symbol"],
                    "side": row["side"],
                    "time_horizon": row["time_horizon"],
                    "exception_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
        else:
            compatible.append(row)
    return compatible, blocked


def _linear(coefficients: dict[str, float], features: dict[str, float]) -> float:
    return math.fsum(coefficients[name] * features[name] for name in FIT_FEATURE_NAMES)


def fit_evidence_coefficients(
    rows: list[dict],
    *,
    ridge: float,
    iterations: int = 300,
    learning_rate: float = 0.04,
) -> dict:
    coefficients = {
        "tp": {name: 0.0 for name in FIT_FEATURE_NAMES},
        "sl": {name: 0.0 for name in FIT_FEATURE_NAMES},
    }
    first_moment = {
        cause: {name: 0.0 for name in FIT_FEATURE_NAMES}
        for cause in ("tp", "sl")
    }
    second_moment = {
        cause: {name: 0.0 for name in FIT_FEATURE_NAMES}
        for cause in ("tp", "sl")
    }
    epsilon = 1e-5
    for iteration in range(1, iterations + 1):
        gradients = {
            "tp": {name: 0.0 for name in FIT_FEATURE_NAMES},
            "sl": {name: 0.0 for name in FIT_FEATURE_NAMES},
        }
        for row in rows:
            x = row["features"]
            eta_tp = _linear(coefficients["tp"], x)
            eta_sl = _linear(coefficients["sl"], x)

            def loss(left: float, right: float) -> float:
                probabilities = _predict_from_intervals(
                    row["intervals"],
                    left,
                    right,
                )
                index = CLASSES.index(row["label"])
                return -math.log(max(1e-15, probabilities[index]))

            d_tp = (
                loss(eta_tp + epsilon, eta_sl)
                - loss(eta_tp - epsilon, eta_sl)
            ) / (2 * epsilon)
            d_sl = (
                loss(eta_tp, eta_sl + epsilon)
                - loss(eta_tp, eta_sl - epsilon)
            ) / (2 * epsilon)
            for name in FIT_FEATURE_NAMES:
                gradients["tp"][name] += d_tp * x[name] / len(rows)
                gradients["sl"][name] += d_sl * x[name] / len(rows)
        for cause in ("tp", "sl"):
            for name in FIT_FEATURE_NAMES:
                if name != "intercept":
                    gradients[cause][name] += (
                        ridge * coefficients[cause][name] / len(rows)
                    )
                gradient = max(-10.0, min(10.0, gradients[cause][name]))
                first_moment[cause][name] = (
                    0.9 * first_moment[cause][name] + 0.1 * gradient
                )
                second_moment[cause][name] = (
                    0.999 * second_moment[cause][name]
                    + 0.001 * gradient * gradient
                )
                corrected_first = first_moment[cause][name] / (1 - 0.9**iteration)
                corrected_second = second_moment[cause][name] / (
                    1 - 0.999**iteration
                )
                coefficients[cause][name] -= (
                    learning_rate
                    * corrected_first
                    / (math.sqrt(corrected_second) + 1e-8)
                )
    return coefficients


def build_coefficient_artifact(
    *,
    coefficients: dict,
    scaling: dict,
    training_cutoff: str,
    ridge: float,
) -> dict:
    artifact = {
        "id": f"M8-COEFFICIENTS-RIDGE-{ridge:g}-v0.1",
        "version": "0.1",
        "status": "estimated_internal_candidate",
        "provenance": "estimated_temporal_training",
        "training_cutoff": training_cutoff,
        "feature_schema_sha256": canonical_sha256(sorted(FIT_FEATURE_NAMES)),
        "coefficients": coefficients,
        "feature_standardization": scaling,
        "ridge_lambda": ridge,
        "optimizer": {
            "method": "deterministic_adam_numeric_eta_gradient",
            "iterations": 300,
            "learning_rate": 0.04,
        },
        "production_authorized": False,
    }
    artifact["artifact_sha256"] = payload_sha256(artifact)
    return artifact


def apply_temperature(probabilities: dict[str, float], temperature: float) -> dict:
    weights = {
        name: math.exp(math.log(max(1e-15, probabilities[name])) / temperature)
        for name in CLASSES
    }
    total = math.fsum(weights.values())
    return {name: value / total for name, value in weights.items()}


def candidate_predictions(
    rows: list[dict],
    artifact: dict,
    *,
    temperature: float = 1.0,
    ablate_feature: str | None = None,
) -> dict[int, dict]:
    coefficients = json.loads(json.dumps(artifact["coefficients"]))
    if ablate_feature is not None:
        coefficients["tp"][ablate_feature] = 0.0
        coefficients["sl"][ablate_feature] = 0.0
    candidate = dict(artifact)
    candidate["coefficients"] = coefficients
    predictions = {}
    scaling = artifact["feature_standardization"]
    for row in rows:
        direction = 1 if row["side"] == "long" else -1
        features = standardized_features(row, scaling)
        result = apply_competing_risk_evidence(
            tp_log_distance=direction
            * math.log(row["take_profit"] / row["entry"]),
            sl_log_distance=-direction
            * math.log(row["stop_loss"] / row["entry"]),
            sigma_horizon=row["pretrade"]["sigma_horizon"],
            interval_count=24,
            features=features,
            coefficient_artifact=candidate,
        )
        raw = {
            CLASSES[0]: result.p_tp,
            CLASSES[1]: result.p_sl,
            CLASSES[2]: result.p_expiry,
        }
        predictions[row["recommendation_id"]] = apply_temperature(
            raw,
            temperature,
        )
    return predictions


def constant_predictions(rows: list[dict], values: dict[str, float]) -> dict:
    return {row["recommendation_id"]: dict(values) for row in rows}


def baseline_predictions(rows: list[dict]) -> dict:
    return {
        row["recommendation_id"]: baseline_probabilities(row)
        for row in rows
    }


def bootstrap_paired_differences(
    rows: list[dict],
    left: dict[int, dict],
    right: dict[int, dict],
    *,
    resamples: int = 2000,
    seed: int = 20260728,
) -> dict:
    import random

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["analysis_day_utc"]].append(row)
    days = sorted(grouped)
    if len(days) < 5:
        return {
            "status": "insufficient_calendar_blocks",
            "calendar_blocks": len(days),
            "resamples": 0,
        }
    randomizer = random.Random(seed)
    brier_values = []
    log_values = []
    for _ in range(resamples):
        sampled = [
            member
            for _day in range(len(days))
            for member in grouped[randomizer.choice(days)]
        ]
        brier_values.append(
            metric_brier(sampled, left) - metric_brier(sampled, right)
        )
        log_values.append(
            metric_log_loss(sampled, left) - metric_log_loss(sampled, right)
        )

    def interval(values: list[float]) -> dict:
        ordered = sorted(values)
        return {
            "mean": math.fsum(values) / len(values),
            "lower_95": ordered[int(0.025 * (len(ordered) - 1))],
            "upper_95": ordered[int(0.975 * (len(ordered) - 1))],
        }

    return {
        "status": "evaluated",
        "calendar_blocks": len(days),
        "resamples": resamples,
        "left_minus_right": {
            "brier_3c": interval(brier_values),
            "log_loss_3c": interval(log_values),
        },
    }


def subgroup_metrics(
    rows: list[dict],
    predictions: dict[int, dict],
) -> dict:
    output = {}
    for field in ("symbol", "side", "time_horizon"):
        groups = defaultdict(list)
        for row in rows:
            groups[str(row[field])].append(row)
        output[field] = {}
        for value, members in sorted(groups.items()):
            output[field][value] = (
                evaluate_predictions(members, predictions)
                if len(members) >= 5
                else {
                    "n": len(members),
                    "status": "insufficient_subgroup_size",
                }
            )
    return output


def legacy_probability(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number / 100.0 if number > 1.0 else number


def normalize_legacy_probabilities(row: dict) -> dict[str, float] | None:
    values = [
        legacy_probability(row.get("tp_probability")),
        legacy_probability(row.get("sl_probability")),
        legacy_probability(row.get("range_probability")),
    ]
    if any(value is None for value in values):
        return None
    total = math.fsum(values)
    if total <= 0:
        return None
    return {
        name: value / total
        for name, value in zip(CLASSES, values)
    }


def add_payload_hash(payload: dict) -> dict:
    payload["canonical_payload_sha256"] = payload_sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "canonical_payload_sha256"
        }
    )
    return payload
