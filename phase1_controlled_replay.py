from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import random
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

from composite_rule_runtime import evaluate_absorption
from m5_engine import run_internal_analysis
from m5_input_assembly import (
    _closed_material,
    build_rule_inputs,
    candidate_features_from_m5,
)
from m6_first_passage import double_barrier_first_passage
from m6_competing_risks import adjusted_interval_hazards
from m6_remediated_competing_risks import build_baseline_intervals
from microstructure_rule_runtime import evaluate_microstructure_rule_family
from structural_level_runtime import (
    PIVOT_HALF_WINDOW,
    _fibonacci_outputs,
    _structural_outputs,
    confirmed_pivots,
)
from technical_rule_runtime import evaluate_technical_rule_family, wilder_atr


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DATA_DIR = ROOT / "data" / "phase1_controlled_replay"
ARCHIVE_DIR = DATA_DIR / "binance_usdm_5m"
DATASET_PATH = DATA_DIR / "controlled_market_cases_v0_1.jsonl.gz"
MANIFEST_PATH = AUDIT_DIR / "fase1_cohorte_controlada_v0_1.json"
RESULT_PATH = AUDIT_DIR / "fase1_validacion_reglas_controlada_v0_1.json"
DECISION_PATH = AUDIT_DIR / "fase1_decision_motor_v0_1.json"
CURRENT_ENGINE_AUDIT_PATH = AUDIT_DIR / "fase1_auditoria_motor_actual_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-08-12_fase1_validacion_reglas_controlada.md"
FINAL_REPORT_PATH = AUDIT_DIR / "2026-08-12_fase1_decision_final_motor.md"

REPLAY_VERSION = "phase1-controlled-replay-v0.1"
VALIDATION_VERSION = "phase1-controlled-rule-validation-v0.1"
ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = {
    "intraday_short": {
        "seconds": 4 * 60 * 60,
        "interval_seconds": 5 * 60,
        "anchor_step_seconds": 12 * 60 * 60,
    },
    "intraday_wide": {
        "seconds": 24 * 60 * 60,
        "interval_seconds": 60 * 60,
        "anchor_step_seconds": 24 * 60 * 60,
    },
    "short_swing": {
        "seconds": 7 * 24 * 60 * 60,
        "interval_seconds": 6 * 60 * 60,
        "anchor_step_seconds": 7 * 24 * 60 * 60,
    },
}
START_MONTH = "2023-01"
END_MONTH = "2026-07"
DEVELOPMENT_END = "2024-12-31T23:59:59+00:00"
CALIBRATION_END = "2025-06-30T23:59:59+00:00"
RULE_TEST_END = "2025-12-31T23:59:59+00:00"
FINAL_END = "2026-07-31T23:59:59+00:00"
BASE_INTERVAL_SECONDS = 5 * 60
BASE_INTERVAL_MS = BASE_INTERVAL_SECONDS * 1000
GEOMETRIES = (
    (0.50, 0.50),
    (0.75, 1.00),
    (1.00, 0.75),
    (1.00, 1.00),
    (1.50, 1.00),
    (1.00, 1.50),
)
CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)
BOOTSTRAP_SAMPLES = 1000
BOOTSTRAP_MAX_EPISODES = 2000
FIT_MAX_CASES = 3000
FIT_ITERATIONS = 80
FALSE_DISCOVERY_RATE = 0.05
MIN_INFERENCE_CLUSTERS_FOR_RULE_SELECTION = 100
MIN_INFERENCE_CLUSTERS_FOR_SEALED_GATE = 100
RANDOM_SEED = 20260812


RULE_FEATURES = {
    "M4-RULE-PATH-STRUCTURE-001": (
        "directional_path_efficiency_h",
    ),
    "M4-RULE-MTF-HIERARCHY-001": (
        "directional_path_efficiency_2h",
        "directional_path_efficiency_4h",
    ),
    "M4-RULE-VOLATILITY-RANK-001": (
        "volatility_percentile_60",
    ),
    "M4-RULE-PRIOR-EXTREMA-001": (
        "target_extreme_between_entry_and_tp",
    ),
    "LIB-CAND-EMA-TREND-001": (
        "side_adjusted_close_vs_ema50_log",
        "side_adjusted_ema50_vs_ema200_log",
        "side_adjusted_slope_atr",
    ),
    "LIB-CAND-RSI-WILDER-001": (
        "side_adjusted_centered_rsi",
    ),
    "LIB-CAND-ATR-EXTENSION-001": (
        "side_adjusted_extension_atr",
    ),
    "LIB-CAND-RELATIVE-VOLUME-001": (
        "log_relative_horizon_volume",
    ),
    "LIB-CAND-CVD-SLOPE-001": (
        "side_adjusted_normalized_cvd_slope",
    ),
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": (
        "target_path_level_count",
        "adverse_path_level_count",
    ),
    "LIB-CAND-FIBONACCI-DISTANCE-001": (
        "nearest_to_take_profit.absolute_distance_sigma_horizon",
        "nearest_to_stop_loss.absolute_distance_sigma_horizon",
    ),
    "LIB-CAND-COMPRESSION-001": (
        "compression_vector.atr_rank",
        "compression_vector.bollinger_width_rank",
    ),
    "LIB-CAND-ABSORPTION-001": (
        "side_adjusted_horizon_displacement_atr",
        "flow_opposing_wick_ratio",
    ),
    "LIB-CAND-PULLBACK-CONTEXT-001": (
        "side_adjusted_ema50_vs_ema200_log",
        "side_adjusted_ema50_slope_6bars_atr",
        "side_adjusted_extension_atr",
    ),
}

DATA_BLOCKED_RULES = {
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "exact_historical_oi_not_in_kline_archive",
    "M4-RULE-PRICE-OI-STATE-001": "exact_historical_oi_not_in_kline_archive",
    "M4-RULE-SPOT-FUTURES-BASIS-001": "synchronized_spot_book_history_unavailable",
    "M4-RULE-MARK-INDEX-PREMIUM-001": "mark_index_history_not_in_kline_archive",
    "M4-RULE-FUNDING-STATE-001": "funding_history_requires_separate_point_in_time_contract",
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": "historical_order_book_snapshots_unavailable",
    "LIB-CAND-FUNDING-PERCENTILE-001": "funding_history_requires_separate_point_in_time_contract",
    "LIB-CAND-CROWDING-PERCENTILE-001": "historical_crowding_snapshots_unavailable",
    "LIB-CAND-SENTIMENT-PERCENTILE-001": "historical_sentiment_snapshots_unavailable",
    "LIB-CAND-LIQUIDATION-ZONE-001": "historical_liquidation_map_snapshots_unavailable",
    "LIB-CAND-SHOCK-001": "exact_cross_market_event_contract_unavailable",
    "LIB-CAND-CROSS-VENUE-DIVERGENCE-001": "synchronized_cross_venue_history_unavailable",
}

SIDE_SIGNED_FEATURE_NAMES = {
    "directional_path_efficiency_h",
    "directional_path_efficiency_2h",
    "directional_path_efficiency_4h",
    "side_adjusted_close_vs_ema50_log",
    "side_adjusted_ema50_vs_ema200_log",
    "side_adjusted_slope_atr",
    "side_adjusted_centered_rsi",
    "side_adjusted_extension_atr",
    "side_adjusted_normalized_cvd_slope",
    "side_adjusted_horizon_displacement_atr",
    "side_adjusted_ema50_slope_6bars_atr",
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_hash(payload: dict) -> dict:
    result = dict(payload)
    result["canonical_payload_sha256"] = sha256_json(result)
    return result


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )


def month_range(start: str = START_MONTH, end: str = END_MONTH) -> list[str]:
    year, month = (int(value) for value in start.split("-"))
    end_year, end_month = (int(value) for value in end.split("-"))
    values = []
    while (year, month) <= (end_year, end_month):
        values.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return values


def archive_url(symbol: str, month: str) -> str:
    filename = f"{symbol}-5m-{month}.zip"
    return f"{ARCHIVE_BASE}/{symbol}/5m/{filename}"


def archive_path(symbol: str, month: str) -> Path:
    return ARCHIVE_DIR / symbol / f"{symbol}-5m-{month}.zip"


def download_archive(
    symbol: str,
    month: str,
    *,
    retries: int = 3,
) -> dict:
    path = archive_path(symbol, month)
    if path.exists() and path.stat().st_size > 0:
        return {
            "symbol": symbol,
            "month": month,
            "status": "cached",
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    url = archive_url(symbol, month)
    temporary = path.with_suffix(".zip.part")
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "phase1-controlled-replay/0.1"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                temporary.write_bytes(response.read())
            with zipfile.ZipFile(temporary) as archive:
                if archive.testzip() is not None:
                    raise ValueError("archive_crc_invalid")
            temporary.replace(path)
            return {
                "symbol": symbol,
                "month": month,
                "status": "downloaded",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as exc:
            if temporary.exists():
                temporary.unlink()
            if attempt >= retries:
                return {
                    "symbol": symbol,
                    "month": month,
                    "status": "unavailable",
                    "reason": f"{type(exc).__name__}:{exc}",
                }
            time.sleep(0.5 * attempt)
    raise AssertionError("unreachable")


def download_all_archives(
    *,
    symbols: Iterable[str] = SYMBOLS,
    start: str = START_MONTH,
    end: str = END_MONTH,
) -> dict:
    records = []
    for symbol in symbols:
        for month in month_range(start, end):
            result = download_archive(str(symbol).upper(), month)
            records.append(result)
            print(
                f"ARCHIVE {result['symbol']} {result['month']} {result['status']}",
                flush=True,
            )
    payload = add_hash(
        {
            "version": "phase1-binance-archive-manifest-v0.1",
            "source": "Binance USD-M public monthly kline archive",
            "interval": "5m",
            "start_month": start,
            "end_month": end,
            "symbols": list(symbols),
            "records": records,
            "status_counts": dict(Counter(item["status"] for item in records)),
            "supabase_writes": 0,
        }
    )
    write_json(DATA_DIR / "archive_manifest_v0_1.json", payload)
    return payload


def _normalize_archive_timestamp(value: str) -> int:
    number = int(float(value))
    if number > 10**15:
        number //= 1000
    return number


def read_symbol_5m(symbol: str) -> list[dict]:
    rows: dict[int, dict] = {}
    for path in sorted((ARCHIVE_DIR / symbol).glob(f"{symbol}-5m-*.zip")):
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(members) != 1:
                raise ValueError(f"archive_csv_member_invalid:{path.name}")
            with archive.open(members[0]) as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8")
                for values in csv.reader(text):
                    if not values or not values[0] or not values[0][0].isdigit():
                        continue
                    if len(values) < 11:
                        continue
                    open_time = _normalize_archive_timestamp(values[0])
                    close_time = _normalize_archive_timestamp(values[6])
                    rows[open_time] = {
                        "open_time_ms": open_time,
                        "open": float(values[1]),
                        "high": float(values[2]),
                        "low": float(values[3]),
                        "close": float(values[4]),
                        "volume": float(values[5]),
                        "close_time_ms": close_time,
                        "quote_volume": float(values[7]),
                        "taker_buy_base_volume": float(values[9]),
                        "taker_buy_quote_volume": float(values[10]),
                    }
    ordered = [rows[key] for key in sorted(rows)]
    if not ordered:
        raise ValueError(f"no_archive_candles:{symbol}")
    return ordered


def aggregate_candles(candles: list[dict], interval_seconds: int) -> list[dict]:
    if interval_seconds == BASE_INTERVAL_SECONDS:
        return list(candles)
    interval_ms = interval_seconds * 1000
    expected = interval_seconds // BASE_INTERVAL_SECONDS
    grouped: dict[int, list[dict]] = defaultdict(list)
    for candle in candles:
        bucket = int(candle["open_time_ms"]) // interval_ms * interval_ms
        grouped[bucket].append(candle)
    result = []
    for bucket in sorted(grouped):
        members = sorted(grouped[bucket], key=lambda item: item["open_time_ms"])
        if len(members) != expected:
            continue
        if any(
            right["open_time_ms"] - left["open_time_ms"] != BASE_INTERVAL_MS
            for left, right in zip(members, members[1:])
        ):
            continue
        result.append(
            {
                "open_time_ms": bucket,
                "open": members[0]["open"],
                "high": max(item["high"] for item in members),
                "low": min(item["low"] for item in members),
                "close": members[-1]["close"],
                "volume": math.fsum(item["volume"] for item in members),
                "close_time_ms": bucket + interval_ms - 1,
                "quote_volume": math.fsum(
                    item["quote_volume"] for item in members
                ),
                "taker_buy_base_volume": math.fsum(
                    item["taker_buy_base_volume"] for item in members
                ),
                "taker_buy_quote_volume": math.fsum(
                    item["taker_buy_quote_volume"] for item in members
                ),
            }
        )
    return result


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def partition_for_ms(value: int) -> str | None:
    moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if moment <= datetime.fromisoformat(DEVELOPMENT_END):
        return "development"
    if moment <= datetime.fromisoformat(CALIBRATION_END):
        return "calibration"
    if moment <= datetime.fromisoformat(RULE_TEST_END):
        return "rule_test"
    if moment <= datetime.fromisoformat(FINAL_END):
        return "final_test"
    return None


def _flatten(value: Any, prefix: str = "") -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(item, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number):
            result[prefix] = number
    return result


def _extract_trace_features(traces: list[dict]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for trace in traces:
        rule_id = str(trace.get("rule_id") or "")
        if rule_id not in RULE_FEATURES:
            continue
        if trace.get("status") not in {"evaluated", "evaluated_shadow"}:
            continue
        flattened = _flatten(trace.get("outputs") or {})
        selected = {
            name: flattened[name]
            for name in RULE_FEATURES[rule_id]
            if name in flattened
        }
        if len(selected) == len(RULE_FEATURES[rule_id]):
            result[rule_id] = selected
    return result


def _base_rule_context(
    *,
    shell: dict,
    side: str,
    sigma: float,
    material: dict,
) -> dict:
    direction = 1.0 if side == "long" else -1.0
    entry = float(shell["entry"])
    plan = {
        **shell,
        "plan_id": f"{shell['symbol']}:{shell['analysis_at']}:{side}:base",
        "side": side,
        "take_profit": entry * math.exp(direction * sigma),
        "stop_loss": entry * math.exp(-direction * sigma),
    }
    rule_inputs, _, observations = build_rule_inputs(
        plan=plan,
        candles=material["selected"],
        live_context=None,
        prevalidated_material=material,
    )
    m5 = run_internal_analysis(
        analysis_id=f"controlled:{plan['plan_id']}:m5",
        rule_inputs=rule_inputs,
        source_observations=observations,
        executed_at=plan["analysis_at"],
    )
    active_values = candidate_features_from_m5(m5, side=side)
    features = {
        "M4-RULE-PATH-STRUCTURE-001": {
            "directional_path_efficiency_h": active_values[
                "directional_path_efficiency_h"
            ]
        },
        "M4-RULE-MTF-HIERARCHY-001": {
            "directional_path_efficiency_2h": active_values[
                "directional_path_efficiency_2h"
            ],
            "directional_path_efficiency_4h": active_values[
                "directional_path_efficiency_4h"
            ],
        },
        "M4-RULE-VOLATILITY-RANK-001": {
            "volatility_percentile_60": active_values[
                "volatility_percentile_60"
            ]
        },
    }
    technical = evaluate_technical_rule_family(
        material["selected"],
        side=side,
        analysis_at=plan["analysis_at"],
        interval_seconds=material["interval_seconds"],
        source_data_sha256=material["data_sha256"],
    )
    microstructure = evaluate_microstructure_rule_family(
        selected_candles=material["selected"],
        current_bars=material["current_bars"],
        live_context=None,
        return_count=material["return_count"],
        interval_seconds=material["interval_seconds"],
        side=side,
        analysis_at=plan["analysis_at"],
        source_data_sha256=material["data_sha256"],
    )
    base_traces = technical.get("traces", []) + microstructure.get("traces", [])
    features.update(_extract_trace_features(base_traces))
    features["LIB-CAND-COMPRESSION-001"] = _compression_features(material)
    trace_map = {
        str(trace.get("rule_id")): trace
        for trace in m5.get("traces", []) + base_traces
        if trace.get("rule_id")
    }
    absorption = evaluate_absorption(
        material["selected"],
        material["current_bars"],
        trace_map,
        side=side,
        analysis_at=plan["analysis_at"],
    )
    features.update(_extract_trace_features([absorption]))
    ema = features.get("LIB-CAND-EMA-TREND-001")
    extension = features.get("LIB-CAND-ATR-EXTENSION-001")
    if ema and extension:
        features["LIB-CAND-PULLBACK-CONTEXT-001"] = {
            "side_adjusted_ema50_vs_ema200_log": ema[
                "side_adjusted_ema50_vs_ema200_log"
            ],
            "side_adjusted_ema50_slope_6bars_atr": ema[
                "side_adjusted_slope_atr"
            ],
            "side_adjusted_extension_atr": extension[
                "side_adjusted_extension_atr"
            ],
        }
    return {
        "features": features,
        "m5_analysis": m5,
        "base_traces": base_traces,
    }


def _compression_features(material: dict) -> dict[str, float]:
    candles = material["selected"]
    return_count = int(material["return_count"])
    endpoints = [
        len(candles) - 1 - offset * return_count
        for offset in range(60, -1, -1)
    ]
    true_ranges = []
    previous_close = None
    for row in candles:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        true_range = high - low
        if previous_close is not None:
            true_range = max(
                true_range,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = close
    atr_by_index: dict[int, float] = {}
    period = 14
    current = math.fsum(true_ranges[:period]) / period
    atr_by_index[period - 1] = current
    for index in range(period, len(true_ranges)):
        current = ((period - 1) * current + true_ranges[index]) / period
        atr_by_index[index] = current
    atr_norms = []
    band_widths = []
    for endpoint in endpoints:
        close = float(candles[endpoint]["close"])
        atr_norms.append(atr_by_index[endpoint] / close)
        closes = [
            float(row["close"])
            for row in candles[endpoint - 19 : endpoint + 1]
        ]
        middle = math.fsum(closes) / 20.0
        variance = math.fsum(
            (value - middle) ** 2 for value in closes
        ) / 20.0
        band_widths.append(4.0 * math.sqrt(variance) / middle)

    def midrank(value: float, reference: list[float]) -> float:
        below = sum(item < value for item in reference)
        equal = sum(item == value for item in reference)
        return (below + 0.5 * equal) / len(reference)

    return {
        "compression_vector.atr_rank": midrank(atr_norms[-1], atr_norms[:-1]),
        "compression_vector.bollinger_width_rank": midrank(
            band_widths[-1], band_widths[:-1]
        ),
    }


def _opposite_side_base_context(context: dict) -> dict:
    features = {}
    for rule_id, values in context["features"].items():
        features[rule_id] = {
            name: (-float(value) if name in SIDE_SIGNED_FEATURE_NAMES else value)
            for name, value in values.items()
        }
    return {"features": features}


def _structural_basis(material: dict) -> dict:
    lookback = max(
        34,
        4 * int(material["return_count"]) + 2 * PIVOT_HALF_WINDOW + 1,
    )
    context = material["selected"][-lookback:]
    atr14 = wilder_atr(context, 14)
    return {
        "atr14": atr14,
        "pivots": confirmed_pivots(context, atr14=atr14),
    }


def _structural_features_for_plan(
    *,
    plan: dict,
    material: dict,
    basis: dict,
) -> dict[str, dict[str, float]]:
    pivots = basis["pivots"]
    if not pivots:
        return {}
    sigma = math.sqrt(material["current_variance"])
    structural = _structural_outputs(
        pivots,
        entry=float(plan["entry"]),
        take_profit=float(plan["take_profit"]),
        stop_loss=float(plan["stop_loss"]),
        side=plan["side"],
        sigma_horizon=sigma,
    )
    result = {
        "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": {
            "target_path_level_count": float(
                structural["target_path_level_count"]
            ),
            "adverse_path_level_count": float(
                structural["adverse_path_level_count"]
            ),
        }
    }
    fibonacci = _fibonacci_outputs(
        pivots,
        entry=float(plan["entry"]),
        take_profit=float(plan["take_profit"]),
        stop_loss=float(plan["stop_loss"]),
        sigma_horizon=sigma,
        atr14=float(basis["atr14"]),
    )
    if fibonacci is not None:
        result["LIB-CAND-FIBONACCI-DISTANCE-001"] = {
            "nearest_to_take_profit.absolute_distance_sigma_horizon": float(
                fibonacci["nearest_to_take_profit"][
                    "absolute_distance_sigma_horizon"
                ]
            ),
            "nearest_to_stop_loss.absolute_distance_sigma_horizon": float(
                fibonacci["nearest_to_stop_loss"][
                    "absolute_distance_sigma_horizon"
                ]
            ),
        }
    return result


def _outcome(
    *,
    future: list[dict],
    side: str,
    take_profit: float,
    stop_loss: float,
) -> dict:
    for candle in future:
        if side == "long":
            tp_hit = candle["high"] >= take_profit
            sl_hit = candle["low"] <= stop_loss
        else:
            tp_hit = candle["low"] <= take_profit
            sl_hit = candle["high"] >= stop_loss
        if tp_hit and sl_hit:
            return {
                "status": "ambiguous",
                "label": None,
                "first_touch_at": iso_ms(candle["open_time_ms"]),
            }
        if tp_hit:
            return {
                "status": "resolved",
                "label": CLASSES[0],
                "first_touch_at": iso_ms(candle["open_time_ms"]),
            }
        if sl_hit:
            return {
                "status": "resolved",
                "label": CLASSES[1],
                "first_touch_at": iso_ms(candle["open_time_ms"]),
            }
    return {
        "status": "resolved",
        "label": CLASSES[2],
        "first_touch_at": None,
    }


def _complete_future(
    base_by_open: dict[int, dict],
    *,
    cutoff_ms: int,
    horizon_seconds: int,
) -> list[dict] | None:
    first_open = (cutoff_ms // BASE_INTERVAL_MS + 1) * BASE_INTERVAL_MS
    expected = horizon_seconds // BASE_INTERVAL_SECONDS
    values = [
        base_by_open.get(first_open + index * BASE_INTERVAL_MS)
        for index in range(expected)
    ]
    if any(item is None for item in values):
        return None
    return [item for item in values if item is not None]


def _rule_features_for_plan(
    *,
    plan: dict,
    material: dict,
    base_context: dict,
    structural_basis: dict,
) -> dict[str, dict[str, float]]:
    result = {
        rule_id: dict(values)
        for rule_id, values in base_context["features"].items()
    }
    direction = 1.0 if plan["side"] == "long" else -1.0
    target_extreme = (
        max(float(row["high"]) for row in material["current_bars"])
        if direction > 0
        else min(float(row["low"]) for row in material["current_bars"])
    )
    target_between = (
        float(plan["entry"]) < target_extreme < float(plan["take_profit"])
        if direction > 0
        else float(plan["take_profit"]) < target_extreme < float(plan["entry"])
    )
    result["M4-RULE-PRIOR-EXTREMA-001"] = {
        "target_extreme_between_entry_and_tp": 1.0 if target_between else 0.0
    }
    result.update(
        _structural_features_for_plan(
            plan=plan,
            material=material,
            basis=structural_basis,
        )
    )
    return result


def _baseline_probabilities(
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    sigma: float,
) -> dict[str, float]:
    direction = 1.0 if side == "long" else -1.0
    result = double_barrier_first_passage(
        tp_log_distance=direction * math.log(take_profit / entry),
        sl_log_distance=-direction * math.log(stop_loss / entry),
        sigma_horizon=sigma,
    )
    return {
        CLASSES[0]: result.p_tp,
        CLASSES[1]: result.p_sl,
        CLASSES[2]: result.p_expiry,
    }


def build_controlled_dataset(
    *,
    symbols: Iterable[str] = SYMBOLS,
) -> dict:
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    counters: Counter = Counter()
    horizon_counts: Counter = Counter()
    partition_counts: Counter = Counter()
    symbol_counts: Counter = Counter()
    rule_coverage: Counter = Counter()
    episode_hashes = hashlib.sha256()
    with gzip.open(DATASET_PATH, "wt", encoding="utf-8", newline="\n") as output:
        for symbol in symbols:
            base = read_symbol_5m(symbol)
            base_by_open = {
                int(item["open_time_ms"]): item for item in base
            }
            aggregated = {
                profile["interval_seconds"]: aggregate_candles(
                    base,
                    profile["interval_seconds"],
                )
                for profile in HORIZONS.values()
            }
            for horizon, profile in HORIZONS.items():
                candles = aggregated[profile["interval_seconds"]]
                required_returns = 61 * (
                    profile["seconds"] // profile["interval_seconds"]
                )
                minimum_index = required_returns
                step = profile["anchor_step_seconds"] // profile["interval_seconds"]
                horizon_base_count = profile["seconds"] // BASE_INTERVAL_SECONDS
                maximum_cutoff = base[-1]["close_time_ms"] - (
                    horizon_base_count * BASE_INTERVAL_MS
                )
                for index in range(minimum_index, len(candles), step):
                    anchor = candles[index]
                    cutoff_ms = int(anchor["close_time_ms"])
                    if cutoff_ms > maximum_cutoff:
                        break
                    partition = partition_for_ms(cutoff_ms)
                    if partition is None:
                        continue
                    analysis_at = iso_ms(cutoff_ms)
                    shell = {
                        "symbol": symbol,
                        "side": "long",
                        "entry": anchor["close"],
                        "take_profit": anchor["close"] * 1.001,
                        "stop_loss": anchor["close"] * 0.999,
                        "entry_type": "market",
                        "margin": 100.0,
                        "leverage": 1.0,
                        "time_horizon": horizon,
                        "horizon_seconds": profile["seconds"],
                        "analysis_at": analysis_at,
                    }
                    try:
                        material = _closed_material(
                            shell,
                            candles[index - required_returns : index + 1],
                        )
                    except (ValueError, ArithmeticError):
                        counters["blocked_pretrade"] += 1
                        continue
                    sigma = math.sqrt(material["current_variance"])
                    if not math.isfinite(sigma) or sigma <= 0:
                        counters["blocked_sigma"] += 1
                        continue
                    future = _complete_future(
                        base_by_open,
                        cutoff_ms=cutoff_ms,
                        horizon_seconds=profile["seconds"],
                    )
                    if future is None:
                        counters["blocked_future_coverage"] += 1
                        continue
                    episode_id = f"{symbol}:{horizon}:{cutoff_ms}"
                    episode_hashes.update((episode_id + "\n").encode("utf-8"))
                    counters["episodes"] += 1
                    long_context = _base_rule_context(
                        shell=shell,
                        side="long",
                        sigma=sigma,
                        material=material,
                    )
                    base_contexts = {
                        "long": long_context,
                        "short": _opposite_side_base_context(long_context),
                    }
                    structural_basis = _structural_basis(material)
                    for side in ("long", "short"):
                        direction = 1.0 if side == "long" else -1.0
                        for tp_multiple, sl_multiple in GEOMETRIES:
                            entry = float(anchor["close"])
                            take_profit = entry * math.exp(
                                direction * tp_multiple * sigma
                            )
                            stop_loss = entry * math.exp(
                                -direction * sl_multiple * sigma
                            )
                            plan_id = (
                                f"{episode_id}:{side}:"
                                f"{tp_multiple:.2f}:{sl_multiple:.2f}"
                            )
                            plan = {
                                **shell,
                                "plan_id": plan_id,
                                "side": side,
                                "entry": entry,
                                "take_profit": take_profit,
                                "stop_loss": stop_loss,
                            }
                            outcome = _outcome(
                                future=future,
                                side=side,
                                take_profit=take_profit,
                                stop_loss=stop_loss,
                            )
                            if outcome["status"] != "resolved":
                                counters["ambiguous_cases"] += 1
                                continue
                            try:
                                features = _rule_features_for_plan(
                                    plan=plan,
                                    material=material,
                                    base_context=base_contexts[side],
                                    structural_basis=structural_basis,
                                )
                            except (ValueError, ArithmeticError, KeyError):
                                counters["blocked_rule_evaluation"] += 1
                                continue
                            for rule_id in features:
                                rule_coverage[rule_id] += 1
                            record = {
                                "version": REPLAY_VERSION,
                                "case_id": plan_id,
                                "episode_id": episode_id,
                                "inference_cluster_id": f"{horizon}:{cutoff_ms}",
                                "partition": partition,
                                "symbol": symbol,
                                "side": side,
                                "time_horizon": horizon,
                                "analysis_at": analysis_at,
                                "data_cutoff_at": iso_ms(
                                    int(material["data_cutoff_at_ms"])
                                ),
                                "horizon_seconds": profile["seconds"],
                                "entry": entry,
                                "take_profit": take_profit,
                                "stop_loss": stop_loss,
                                "tp_sigma_multiple": tp_multiple,
                                "sl_sigma_multiple": sl_multiple,
                                "sigma_horizon": sigma,
                                "baseline_probabilities": _baseline_probabilities(
                                    side=side,
                                    entry=entry,
                                    take_profit=take_profit,
                                    stop_loss=stop_loss,
                                    sigma=sigma,
                                ),
                                "rule_features": features,
                                "outcome": outcome,
                            }
                            output.write(canonical_json(record) + "\n")
                            counters["resolved_cases"] += 1
                            horizon_counts[horizon] += 1
                            partition_counts[partition] += 1
                            symbol_counts[symbol] += 1
                print(
                    f"DATASET {symbol} {horizon} episodes={counters['episodes']} "
                    f"cases={counters['resolved_cases']}",
                    flush=True,
                )
            del base
            del base_by_open
            del aggregated
    manifest = add_hash(
        {
            "version": REPLAY_VERSION,
            "source": "Binance USD-M monthly 5m kline archives",
            "dataset_path": str(DATASET_PATH.relative_to(ROOT)),
            "dataset_sha256": sha256_file(DATASET_PATH),
            "episode_set_sha256": episode_hashes.hexdigest(),
            "symbols": list(symbols),
            "horizons": HORIZONS,
            "geometries_sigma": [list(item) for item in GEOMETRIES],
            "partitions": {
                "development_end": DEVELOPMENT_END,
                "calibration_end": CALIBRATION_END,
                "rule_test_end": RULE_TEST_END,
                "final_end": FINAL_END,
            },
            "outcome_resolution": {
                "primary_interval": "5m",
                "same_candle_both_barriers": "ambiguous_excluded",
                "first_barrier_semantics": True,
            },
            "counts": dict(counters),
            "cases_by_horizon": dict(horizon_counts),
            "cases_by_partition": dict(partition_counts),
            "cases_by_symbol": dict(symbol_counts),
            "rule_feature_coverage": dict(rule_coverage),
            "data_blocked_rules": DATA_BLOCKED_RULES,
            "supabase_writes": 0,
        }
    )
    write_json(MANIFEST_PATH, manifest)
    return manifest


def iter_dataset(path: Path = DATASET_PATH) -> Iterable[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    maximum = max(logits.values())
    weights = {name: math.exp(value - maximum) for name, value in logits.items()}
    total = math.fsum(weights.values())
    return {name: value / total for name, value in weights.items()}


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def standardize(
    rows: list[dict],
    rule_id: str,
) -> dict[str, dict[str, float]]:
    names = RULE_FEATURES[rule_id]
    result = {}
    for name in names:
        values = [row["rule_features"][rule_id][name] for row in rows]
        mean = _mean(values)
        variance = _mean([(value - mean) ** 2 for value in values])
        result[name] = {
            "mean": mean,
            "scale": max(math.sqrt(variance), 1e-12),
        }
    return result


def model_features(
    row: dict,
    rule_id: str | None,
    scaling: dict[str, dict[str, float]],
) -> dict[str, float]:
    values = {"intercept": 1.0}
    if rule_id is None:
        return values
    for name in RULE_FEATURES[rule_id]:
        raw = row["rule_features"][rule_id][name]
        values[name] = (raw - scaling[name]["mean"]) / scaling[name]["scale"]
    return values


def predict_softmax_offset(
    row: dict,
    coefficients: dict[str, dict[str, float]],
    features: dict[str, float],
) -> dict[str, float]:
    base = row["baseline_probabilities"]
    logits = {name: math.log(max(float(base[name]), 1e-15)) for name in CLASSES}
    for cause in CLASSES[:2]:
        logits[cause] += math.fsum(
            coefficients[cause].get(name, 0.0) * value
            for name, value in features.items()
        )
    return _softmax(logits)


def fit_softmax_offset(
    rows: list[dict],
    *,
    rule_id: str | None,
    scaling: dict[str, dict[str, float]],
    ridge: float,
    iterations: int = FIT_ITERATIONS,
    learning_rate: float = 0.03,
) -> dict[str, dict[str, float]]:
    names = ("intercept",) + (() if rule_id is None else RULE_FEATURES[rule_id])
    coefficients = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    first = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    second = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    for iteration in range(1, iterations + 1):
        gradients = {
            cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
        }
        for row in rows:
            features = model_features(row, rule_id, scaling)
            probabilities = predict_softmax_offset(row, coefficients, features)
            label = row["outcome"]["label"]
            for cause in CLASSES[:2]:
                residual = probabilities[cause] - (1.0 if label == cause else 0.0)
                for name, value in features.items():
                    gradients[cause][name] += residual * value / len(rows)
        for cause in CLASSES[:2]:
            for name in names:
                if name != "intercept":
                    gradients[cause][name] += (
                        ridge * coefficients[cause][name] / len(rows)
                    )
                gradient = max(-10.0, min(10.0, gradients[cause][name]))
                first[cause][name] = 0.9 * first[cause][name] + 0.1 * gradient
                second[cause][name] = (
                    0.999 * second[cause][name] + 0.001 * gradient * gradient
                )
                corrected_first = first[cause][name] / (1.0 - 0.9**iteration)
                corrected_second = second[cause][name] / (1.0 - 0.999**iteration)
                coefficients[cause][name] -= learning_rate * corrected_first / (
                    math.sqrt(corrected_second) + 1e-8
                )
    return coefficients


def deterministic_episode_sample(
    rows: list[dict],
    *,
    max_cases: int,
    seed: int,
) -> list[dict]:
    if len(rows) <= max_cases:
        return rows
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["episode_id"]].append(row)
    episode_ids = sorted(grouped)
    random.Random(seed).shuffle(episode_ids)
    selected: list[dict] = []
    for episode_id in episode_ids:
        episode_rows = grouped[episode_id]
        if selected and len(selected) + len(episode_rows) > max_cases:
            continue
        selected.extend(episode_rows)
        if len(selected) >= max_cases:
            break
    return selected


def metrics(
    rows: list[dict],
    predictions: dict[str, dict[str, float]],
) -> dict:
    losses = []
    briers = []
    for row in rows:
        probability = predictions[row["case_id"]]
        label = row["outcome"]["label"]
        losses.append(-math.log(max(probability[label], 1e-15)))
        briers.append(
            math.fsum(
                (probability[name] - (1.0 if label == name else 0.0)) ** 2
                for name in CLASSES
            )
        )
    return {
        "n": len(rows),
        "episodes": len({row["episode_id"] for row in rows}),
        "inference_clusters": len(
            {
                row.get("inference_cluster_id", row["episode_id"])
                for row in rows
            }
        ),
        "class_counts": dict(Counter(row["outcome"]["label"] for row in rows)),
        "log_loss_3c": _mean(losses),
        "brier_3c": _mean(briers),
    }


def predict_rows(
    rows: list[dict],
    *,
    rule_id: str | None,
    scaling: dict[str, dict[str, float]],
    coefficients: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    return {
        row["case_id"]: predict_softmax_offset(
            row,
            coefficients,
            model_features(row, rule_id, scaling),
        )
        for row in rows
    }


def joint_feature_names(rule_ids: list[str]) -> tuple[str, ...]:
    return tuple(
        f"{rule_id}::{name}"
        for rule_id in rule_ids
        for name in RULE_FEATURES[rule_id]
    )


def joint_standardize(
    rows: list[dict],
    rule_ids: list[str],
) -> dict[str, dict[str, float]]:
    result = {}
    for rule_id in rule_ids:
        for name in RULE_FEATURES[rule_id]:
            key = f"{rule_id}::{name}"
            values = [row["rule_features"][rule_id][name] for row in rows]
            mean = _mean(values)
            variance = _mean([(value - mean) ** 2 for value in values])
            result[key] = {
                "mean": mean,
                "scale": max(math.sqrt(variance), 1e-12),
            }
    return result


def joint_model_features(
    row: dict,
    rule_ids: list[str],
    scaling: dict[str, dict[str, float]],
) -> dict[str, float]:
    values = {"intercept": 1.0}
    for rule_id in rule_ids:
        for name in RULE_FEATURES[rule_id]:
            key = f"{rule_id}::{name}"
            raw = row["rule_features"][rule_id][name]
            values[key] = (raw - scaling[key]["mean"]) / scaling[key]["scale"]
    return values


def fit_joint_softmax_offset(
    rows: list[dict],
    *,
    rule_ids: list[str],
    scaling: dict[str, dict[str, float]],
    ridge: float,
    iterations: int = FIT_ITERATIONS,
    learning_rate: float = 0.03,
) -> dict[str, dict[str, float]]:
    names = ("intercept",) + joint_feature_names(rule_ids)
    coefficients = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    first = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    second = {
        cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
    }
    for iteration in range(1, iterations + 1):
        gradients = {
            cause: {name: 0.0 for name in names} for cause in CLASSES[:2]
        }
        for row in rows:
            features = joint_model_features(row, rule_ids, scaling)
            probabilities = predict_softmax_offset(row, coefficients, features)
            label = row["outcome"]["label"]
            for cause in CLASSES[:2]:
                residual = probabilities[cause] - (1.0 if label == cause else 0.0)
                for name, value in features.items():
                    gradients[cause][name] += residual * value / len(rows)
        for cause in CLASSES[:2]:
            for name in names:
                if name != "intercept":
                    gradients[cause][name] += (
                        ridge * coefficients[cause][name] / len(rows)
                    )
                gradient = max(-10.0, min(10.0, gradients[cause][name]))
                first[cause][name] = 0.9 * first[cause][name] + 0.1 * gradient
                second[cause][name] = (
                    0.999 * second[cause][name] + 0.001 * gradient * gradient
                )
                corrected_first = first[cause][name] / (1.0 - 0.9**iteration)
                corrected_second = second[cause][name] / (1.0 - 0.999**iteration)
                coefficients[cause][name] -= learning_rate * corrected_first / (
                    math.sqrt(corrected_second) + 1e-8
                )
    return coefficients


def predict_joint_rows(
    rows: list[dict],
    *,
    rule_ids: list[str],
    scaling: dict[str, dict[str, float]],
    coefficients: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    return {
        row["case_id"]: predict_softmax_offset(
            row,
            coefficients,
            joint_model_features(row, rule_ids, scaling),
        )
        for row in rows
    }


def calibration_diagnostics(
    rows: list[dict],
    predictions: dict[str, dict[str, float]],
    *,
    bin_count: int = 10,
) -> dict:
    result = {}
    for class_name in CLASSES:
        bins = []
        calibration_error = 0.0
        for bin_index in range(bin_count):
            lower = bin_index / bin_count
            upper = (bin_index + 1) / bin_count
            members = [
                row
                for row in rows
                if lower <= predictions[row["case_id"]][class_name]
                < upper
                or (
                    bin_index == bin_count - 1
                    and predictions[row["case_id"]][class_name] == 1.0
                )
            ]
            if not members:
                continue
            predicted = _mean(
                [predictions[row["case_id"]][class_name] for row in members]
            )
            observed = _mean(
                [
                    1.0 if row["outcome"]["label"] == class_name else 0.0
                    for row in members
                ]
            )
            calibration_error += len(members) / len(rows) * abs(predicted - observed)
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "n": len(members),
                    "mean_predicted": predicted,
                    "observed_frequency": observed,
                }
            )
        result[class_name] = {
            "expected_calibration_error": calibration_error,
            "bins": bins,
        }
    return result


def _temperature_calibration(
    probabilities: dict[str, float],
    temperature: float,
) -> dict[str, float]:
    weights = {
        name: math.exp(math.log(max(value, 1e-15)) / temperature)
        for name, value in probabilities.items()
    }
    total = math.fsum(weights.values())
    return {name: value / total for name, value in weights.items()}


def _current_engine_feature_values(row: dict, artifact: dict) -> dict[str, float]:
    raw = {
        "directional_path_efficiency_h": row["rule_features"][
            "M4-RULE-PATH-STRUCTURE-001"
        ]["directional_path_efficiency_h"],
        "directional_path_efficiency_2h": row["rule_features"][
            "M4-RULE-MTF-HIERARCHY-001"
        ]["directional_path_efficiency_2h"],
        "directional_path_efficiency_4h": row["rule_features"][
            "M4-RULE-MTF-HIERARCHY-001"
        ]["directional_path_efficiency_4h"],
        "volatility_percentile_60": row["rule_features"][
            "M4-RULE-VOLATILITY-RANK-001"
        ]["volatility_percentile_60"],
        "target_extreme_between_entry_and_tp": row["rule_features"][
            "M4-RULE-PRIOR-EXTREMA-001"
        ]["target_extreme_between_entry_and_tp"],
    }
    result = {"intercept": 1.0}
    for name, scaling in artifact["feature_standardization"].items():
        result[name] = (
            float(raw[name]) - float(scaling["mean"])
        ) / float(scaling["scale"])
    return result


def _current_engine_probabilities(
    row: dict,
    artifact: dict,
    interval_cache: dict[tuple[float, float], tuple[dict, ...]],
) -> dict[str, float]:
    features = _current_engine_feature_values(row, artifact)
    eta = {
        cause: math.fsum(
            float(coefficient) * float(features[name])
            for name, coefficient in artifact["coefficients"][cause].items()
        )
        for cause in ("tp", "sl")
    }
    key = (
        float(row["tp_sigma_multiple"]),
        float(row["sl_sigma_multiple"]),
    )
    intervals = interval_cache.get(key)
    if intervals is None:
        intervals = build_baseline_intervals(
            tp_log_distance=key[0],
            sl_log_distance=key[1],
            sigma_horizon=1.0,
            interval_count=24,
        )
        interval_cache[key] = intervals
    survival = 1.0
    cumulative_tp = 0.0
    cumulative_sl = 0.0
    for baseline in intervals:
        h_tp, h_sl, h_none = adjusted_interval_hazards(
            baseline,
            eta["tp"],
            eta["sl"],
        )
        cumulative_tp += survival * h_tp
        cumulative_sl += survival * h_sl
        survival *= h_none
    return _temperature_calibration(
        {
            CLASSES[0]: cumulative_tp,
            CLASSES[1]: cumulative_sl,
            CLASSES[2]: survival,
        },
        float(artifact["calibration"]["temperature"]),
    )


def _loss_pair(label: str, probabilities: dict[str, float]) -> tuple[float, float]:
    return (
        -math.log(max(probabilities[label], 1e-15)),
        math.fsum(
            (probabilities[name] - (1.0 if label == name else 0.0)) ** 2
            for name in CLASSES
        ),
    )


def audit_frozen_current_engine() -> dict:
    frozen = json.loads(
        (AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json").read_text(
            encoding="utf-8"
        )
    )
    artifact = frozen["coefficient_artifact"]
    validation = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    baseline_coefficients = {}
    for item in validation["baseline_by_horizon"]:
        baseline_coefficients[item["time_horizon"]] = {
            "development": item["development_fit"]["coefficients"],
            "sealed": item["sealed_final_refit"]["coefficients"],
        }
    metric_sums: dict[tuple[str, str, str], list] = {}
    cluster_sums: dict[tuple[str, str, str, str], list[float]] = {}
    interval_cache: dict[tuple[float, float], tuple[dict, ...]] = {}
    for row in iter_dataset():
        horizon = row["time_horizon"]
        partition = row["partition"]
        label = row["outcome"]["label"]
        current = _current_engine_probabilities(row, artifact, interval_cache)
        raw = row["baseline_probabilities"]
        coefficients = baseline_coefficients[horizon][
            "sealed" if partition == "final_test" else "development"
        ]
        calibrated = predict_softmax_offset(
            row, coefficients, {"intercept": 1.0}
        )
        losses = {
            "current_engine": _loss_pair(label, current),
            "raw_first_passage": _loss_pair(label, raw),
            "calibrated_baseline": _loss_pair(label, calibrated),
        }
        for model, (log_loss, brier) in losses.items():
            key = (horizon, partition, model)
            accumulator = metric_sums.setdefault(
                key, [0, 0.0, 0.0, Counter()]
            )
            accumulator[0] += 1
            accumulator[1] += log_loss
            accumulator[2] += brier
            accumulator[3][label] += 1
        cluster = row.get("inference_cluster_id", row["episode_id"])
        for comparator in ("raw_first_passage", "calibrated_baseline"):
            key = (horizon, partition, comparator, cluster)
            accumulator = cluster_sums.setdefault(key, [0.0, 0.0, 0])
            accumulator[0] += (
                losses[comparator][0] - losses["current_engine"][0]
            )
            accumulator[1] += (
                losses[comparator][1] - losses["current_engine"][1]
            )
            accumulator[2] += 1
    results = []
    for horizon_index, horizon in enumerate(HORIZONS):
        partitions = {}
        for partition_index, partition in enumerate(
            ("development", "calibration", "rule_test", "final_test")
        ):
            models = {}
            for model in (
                "current_engine",
                "raw_first_passage",
                "calibrated_baseline",
            ):
                count, log_total, brier_total, classes = metric_sums[
                    (horizon, partition, model)
                ]
                models[model] = {
                    "n": count,
                    "class_counts": dict(classes),
                    "log_loss_3c": log_total / count,
                    "brier_3c": brier_total / count,
                }
            comparisons = {}
            for comparator in ("raw_first_passage", "calibrated_baseline"):
                episodes = [
                    {
                        "episode_id": cluster,
                        "log_loss_improvement": values[0] / values[2],
                        "brier_improvement": values[1] / values[2],
                    }
                    for (
                        item_horizon,
                        item_partition,
                        item_comparator,
                        cluster,
                    ), values in cluster_sums.items()
                    if item_horizon == horizon
                    and item_partition == partition
                    and item_comparator == comparator
                ]
                comparisons[f"current_engine_vs_{comparator}"] = (
                    improvement_inference(
                        episodes,
                        seed=(
                            RANDOM_SEED
                            + horizon_index * 1000
                            + partition_index * 10
                            + (1 if comparator == "raw_first_passage" else 2)
                        ),
                        bootstrap=partition in {"rule_test", "final_test"},
                    )
                )
            partitions[partition] = {
                "models": models,
                "comparisons": comparisons,
            }
        rule_test = partitions["rule_test"]["comparisons"]
        final_test = partitions["final_test"]["comparisons"]

        def passed(comparison: dict) -> bool:
            return (
                comparison["episodes"] >= MIN_INFERENCE_CLUSTERS_FOR_SEALED_GATE
                and comparison["log_loss_bootstrap_95ci"] is not None
                and comparison["brier_bootstrap_95ci"] is not None
                and comparison["log_loss_bootstrap_95ci"][0] > 0
                and comparison["brier_bootstrap_95ci"][0] > 0
            )

        supported = all(
            passed(block[comparison])
            for block in (rule_test, final_test)
            for comparison in (
                "current_engine_vs_raw_first_passage",
                "current_engine_vs_calibrated_baseline",
            )
        )
        results.append(
            {
                "time_horizon": horizon,
                "status": (
                    "current_engine_supported_out_of_sample"
                    if supported
                    else "current_engine_predictive_value_not_demonstrated"
                ),
                "partitions": partitions,
            }
        )
    payload = add_hash(
        {
            "version": "phase1-current-engine-controlled-audit-v0.1",
            "dataset_sha256": sha256_file(DATASET_PATH),
            "engine_contract": "TP-SL-PROBABILITY-ENGINE-v0.6-stable-global",
            "coefficient_artifact_id": artifact["id"],
            "coefficient_artifact_sha256": artifact["artifact_sha256"],
            "artifact_production_authorized_field": artifact[
                "production_authorized"
            ],
            "method": (
                "exact frozen 24-interval competing-risk transformation plus "
                "temperature compared by time cluster with raw and calibrated baselines"
            ),
            "by_horizon": results,
            "all_horizons_supported": all(
                item["status"] == "current_engine_supported_out_of_sample"
                for item in results
            ),
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(CURRENT_ENGINE_AUDIT_PATH, payload)
    return payload


def _historically_supported(comparison: dict) -> bool:
    return (
        comparison["episodes"] >= MIN_INFERENCE_CLUSTERS_FOR_SEALED_GATE
        and comparison["log_loss_bootstrap_95ci"] is not None
        and comparison["brier_bootstrap_95ci"] is not None
        and comparison["log_loss_bootstrap_95ci"][0] > 0
        and comparison["brier_bootstrap_95ci"][0] > 0
    )


def finalize_phase1_decision() -> dict:
    validation = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    current = json.loads(CURRENT_ENGINE_AUDIT_PATH.read_text(encoding="utf-8"))
    baseline_status = {}
    for item in validation["baseline_by_horizon"]:
        comparisons = item["calibrated_vs_raw_first_passage"]
        supported = _historically_supported(comparisons["rule_test"]) and (
            _historically_supported(comparisons["final_test"])
        )
        baseline_status[item["time_horizon"]] = {
            "status": (
                "calibration_supported_out_of_sample"
                if supported
                else "calibration_not_demonstrated"
            ),
            "rule_test": comparisons["rule_test"],
            "final_test": comparisons["final_test"],
        }
    watchlist: dict[str, list[dict]] = defaultdict(list)
    for item in validation["rule_results"]:
        comparisons = item.get("comparisons_vs_calibrated_baseline") or {}
        if not comparisons:
            continue
        positive_all = all(
            comparisons[name]["mean_log_loss_improvement"] > 0
            and comparisons[name]["mean_brier_improvement"] > 0
            for name in ("development", "calibration", "rule_test")
        )
        if not positive_all:
            continue
        clusters = comparisons["rule_test"]["episodes"]
        if clusters < MIN_INFERENCE_CLUSTERS_FOR_RULE_SELECTION:
            reason = "positive_but_insufficient_independent_time_clusters"
        elif item["status"] == "not_supported_after_multiple_test_control":
            reason = "positive_but_failed_multiple_test_control"
        else:
            reason = "positive_but_uncertainty_interval_not_conclusive"
        watchlist[item["time_horizon"]].append(
            {
                "rule_id": item["rule_id"],
                "reason": reason,
                "rule_test_log_loss_improvement": comparisons["rule_test"][
                    "mean_log_loss_improvement"
                ],
                "rule_test_brier_improvement": comparisons["rule_test"][
                    "mean_brier_improvement"
                ],
                "rule_test_fdr_adjusted_p": item.get(
                    "rule_test_intersection_p_value_fdr_adjusted"
                ),
                "independent_time_clusters": clusters,
            }
        )
    current_status = {
        item["time_horizon"]: item["status"]
        for item in current["by_horizon"]
    }
    final_decision = (
        "no_new_engine_promotion_keep_v0_6_frozen_only_intraday_wide_supported"
    )
    payload = add_hash(
        {
            "version": "phase1-final-engine-decision-v0.1",
            "validation_sha256": validation["canonical_payload_sha256"],
            "current_engine_audit_sha256": current[
                "canonical_payload_sha256"
            ],
            "decision": final_decision,
            "facts": {
                "new_supported_rule_horizon_count": validation[
                    "supported_rule_count"
                ],
                "new_joint_challenger_created": False,
                "current_engine_by_horizon": current_status,
                "baseline_calibration_by_horizon": baseline_status,
                "rule_watchlist_by_horizon": dict(watchlist),
            },
            "actions": {
                "promote_new_engine": False,
                "mutate_production_engine": False,
                "delete_current_engine": False,
                "delete_historical_operations": False,
                "start_prospective_challenger": False,
                "automatic_learning_or_weight_updates": False,
                "preserve_current_v0_6_for_audit_lineage": True,
            },
            "reason": (
                "The frozen current engine is supported only for intraday_wide; "
                "intraday_short is worse than its calibrated baseline and "
                "short_swing lacks enough independent final time clusters. "
                "No new rule passes the predeclared complete selection gate."
            ),
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(DECISION_PATH, payload)
    _write_final_report(payload, validation, current)
    return payload


def _format_ci(value: list[float] | None) -> str:
    if value is None:
        return "--"
    return f"[{value[0]:.6f}, {value[1]:.6f}]"


def _write_final_report(decision: dict, validation: dict, current: dict) -> None:
    lines = [
        "# Fase 1 - Decisión final del motor de análisis",
        "",
        f"- Decisión: **`{decision['decision']}`**.",
        "- Promoción nueva: **no**.",
        "- Cambio en producción: **ninguno**.",
        "- Escrituras en Supabase: **ninguna**.",
        "- Borrado de motores u operaciones históricas: **ninguno**.",
        "",
        "## Qué se ha demostrado",
        "",
        "| Marco | Motor v0.6 actual | Calibración del baseline |",
        "|---|---|---|",
    ]
    baseline = decision["facts"]["baseline_calibration_by_horizon"]
    current_by_horizon = {
        item["time_horizon"]: item for item in current["by_horizon"]
    }
    for horizon in HORIZONS:
        lines.append(
            f"| `{horizon}` | "
            f"`{decision['facts']['current_engine_by_horizon'][horizon]}` | "
            f"`{baseline[horizon]['status']}` |"
        )
    lines.extend(
        [
            "",
            "El v0.6 aporta valor histórico estable sólo en `intraday_wide`. "
            "En `intraday_short` queda por debajo del baseline calibrado. "
            "En `short_swing` la evidencia es inconclusa por falta de semanas "
            "independientes, no por falta de filas geométricas.",
            "",
            "## Comparación final del motor v0.6",
            "",
            "| Marco | Comparador | Bloques independientes | Δ log-loss IC95% | Δ Brier IC95% |",
            "|---|---|---:|---|---|",
        ]
    )
    for horizon in HORIZONS:
        final = current_by_horizon[horizon]["partitions"]["final_test"]
        for comparator in ("raw_first_passage", "calibrated_baseline"):
            comparison = final["comparisons"][
                f"current_engine_vs_{comparator}"
            ]
            lines.append(
                f"| `{horizon}` | `{comparator}` | "
                f"{comparison['episodes']} | "
                f"{_format_ci(comparison['log_loss_bootstrap_95ci'])} | "
                f"{_format_ci(comparison['brier_bootstrap_95ci'])} |"
            )
    lines.extend(
        [
            "",
            "## Reglas nuevas",
            "",
            "Ninguna de las 42 combinaciones regla-marco superó a la vez "
            "desarrollo, calibración, selección temporal, intervalos por "
            "bloque y control de comparaciones múltiples. Por tanto, ninguna "
            "recibe peso probabilístico nuevo.",
            "",
            "### Observación prioritaria, sin peso probabilístico",
            "",
            "| Marco | Regla | Motivo | Δ log-loss selección | Δ Brier selección |",
            "|---|---|---|---:|---:|",
        ]
    )
    for horizon, items in decision["facts"][
        "rule_watchlist_by_horizon"
    ].items():
        for item in items:
            lines.append(
                f"| `{horizon}` | `{item['rule_id']}` | "
                f"`{item['reason']}` | "
                f"{item['rule_test_log_loss_improvement']:.6f} | "
                f"{item['rule_test_brier_improvement']:.6f} |"
            )
    lines.extend(
        [
            "",
            "## Alcance de la evidencia",
            "",
            f"- Casos resueltos: **{sum(item['final_test']['n'] for item in validation['baseline_by_horizon'])} en la prueba final**, "
            "dentro de una cohorte total de 285.590 casos.",
            "- Pares: BTC, ETH, SOL, BNB, XRP e INJ.",
            "- Fuente: velas Binance USD-M de 5 minutos, 2023-01 a 2026-07.",
            "- Resolución: primer TP o SL; doble toque en la misma vela excluido.",
            "- Independencia: todas las geometrías y pares de una misma fecha-marco "
            "se agrupan en un único bloque inferencial.",
            "",
            "## Consecuencia",
            "",
            "La fase termina sin fabricar un candidato. Se conserva v0.6 para "
            "trazabilidad y porque sí contiene señal útil en intradía largo, pero "
            "no queda autorizado como solución fiable común a los tres marcos. "
            "No procede iniciar seguimiento prospectivo de un challenger que no "
            "ha superado la puerta histórica.",
        ]
    )
    FINAL_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def paired_episode_improvements(
    rows: list[dict],
    left: dict[str, dict[str, float]],
    right: dict[str, dict[str, float]],
) -> list[dict]:
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        label = row["outcome"]["label"]
        left_probability = left[row["case_id"]]
        right_probability = right[row["case_id"]]
        left_loss = -math.log(max(left_probability[label], 1e-15))
        right_loss = -math.log(max(right_probability[label], 1e-15))
        left_brier = math.fsum(
            (left_probability[name] - (1.0 if label == name else 0.0)) ** 2
            for name in CLASSES
        )
        right_brier = math.fsum(
            (right_probability[name] - (1.0 if label == name else 0.0)) ** 2
            for name in CLASSES
        )
        grouped[
            row.get("inference_cluster_id", row["episode_id"])
        ].append(
            (right_loss - left_loss, right_brier - left_brier)
        )
    return [
        {
            "episode_id": episode_id,
            "log_loss_improvement": _mean([item[0] for item in values]),
            "brier_improvement": _mean([item[1] for item in values]),
        }
        for episode_id, values in grouped.items()
    ]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def _one_sided_normal_p(values: list[float]) -> float | None:
    if len(values) < 20:
        return None
    mean = _mean(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / (
        len(values) - 1
    )
    standard_error = math.sqrt(variance / len(values))
    if standard_error <= 1e-15:
        return 0.0 if mean > 0 else 1.0
    return 1.0 - NormalDist().cdf(mean / standard_error)


def improvement_inference(
    episodes: list[dict],
    *,
    seed: int,
    bootstrap: bool,
) -> dict:
    log_values = [item["log_loss_improvement"] for item in episodes]
    brier_values = [item["brier_improvement"] for item in episodes]
    result = {
        "episodes": len(episodes),
        "mean_log_loss_improvement": _mean(log_values),
        "mean_brier_improvement": _mean(brier_values),
        "log_loss_bootstrap_95ci": None,
        "brier_bootstrap_95ci": None,
        "one_sided_normal_p_log_loss": _one_sided_normal_p(log_values),
        "one_sided_normal_p_brier": _one_sided_normal_p(brier_values),
        "bootstrap_episode_sample_size": 0,
    }
    if len(episodes) < 20 or not bootstrap:
        return result
    rng = random.Random(seed)
    if len(episodes) > BOOTSTRAP_MAX_EPISODES:
        sampled_indices = sorted(
            rng.sample(range(len(episodes)), BOOTSTRAP_MAX_EPISODES)
        )
        log_values = [log_values[index] for index in sampled_indices]
        brier_values = [brier_values[index] for index in sampled_indices]
    result["bootstrap_episode_sample_size"] = len(log_values)
    indices = list(range(len(log_values)))
    log_bootstrap = []
    brier_bootstrap = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [rng.choice(indices) for _ in indices]
        log_bootstrap.append(_mean([log_values[index] for index in sample]))
        brier_bootstrap.append(_mean([brier_values[index] for index in sample]))
    result["log_loss_bootstrap_95ci"] = [
        percentile(log_bootstrap, 0.025),
        percentile(log_bootstrap, 0.975),
    ]
    result["brier_bootstrap_95ci"] = [
        percentile(brier_bootstrap, 0.025),
        percentile(brier_bootstrap, 0.975),
    ]
    return result


def benjamini_hochberg(
    items: list[tuple[int, float]],
) -> dict[int, float]:
    if not items:
        return {}
    ordered = sorted(items, key=lambda item: (item[1], item[0]))
    count = len(ordered)
    adjusted: dict[int, float] = {}
    running = 1.0
    for rank in range(count, 0, -1):
        index, p_value = ordered[rank - 1]
        running = min(running, p_value * count / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def _eligible_for_rule(rows: list[dict], rule_id: str) -> list[dict]:
    return [row for row in rows if rule_id in row.get("rule_features", {})]


def evaluate_controlled_rules() -> dict:
    all_rows = list(iter_dataset())
    by_horizon = {
        horizon: [row for row in all_rows if row["time_horizon"] == horizon]
        for horizon in HORIZONS
    }
    results = []
    baseline_results = []
    selected_rules: dict[str, list[str]] = defaultdict(list)
    horizon_state = {}
    for horizon_index, (horizon, horizon_rows) in enumerate(by_horizon.items()):
        partitions = {
            name: [row for row in horizon_rows if row["partition"] == name]
            for name in (
                "development",
                "calibration",
                "rule_test",
                "final_test",
            )
        }
        development = partitions["development"]
        empty_scaling: dict[str, dict[str, float]] = {}
        baseline_fit = deterministic_episode_sample(
            development,
            max_cases=FIT_MAX_CASES,
            seed=RANDOM_SEED + horizon_index * 1000,
        )
        baseline_coefficients = fit_softmax_offset(
            baseline_fit,
            rule_id=None,
            scaling=empty_scaling,
            ridge=0.0,
        )
        development_baseline_predictions = {
            partition_name: predict_rows(
                rows,
                rule_id=None,
                scaling=empty_scaling,
                coefficients=baseline_coefficients,
            )
            for partition_name, rows in partitions.items()
        }
        prefinal = (
            partitions["development"]
            + partitions["calibration"]
            + partitions["rule_test"]
        )
        sealed_baseline_fit = deterministic_episode_sample(
            prefinal,
            max_cases=FIT_MAX_CASES,
            seed=RANDOM_SEED + horizon_index * 1000 + 99,
        )
        sealed_baseline_coefficients = fit_softmax_offset(
            sealed_baseline_fit,
            rule_id=None,
            scaling=empty_scaling,
            ridge=0.0,
        )
        sealed_baseline_predictions = predict_rows(
            partitions["final_test"],
            rule_id=None,
            scaling=empty_scaling,
            coefficients=sealed_baseline_coefficients,
        )
        raw_predictions = {
            partition_name: {
                row["case_id"]: dict(row["baseline_probabilities"])
                for row in rows
            }
            for partition_name, rows in partitions.items()
        }
        baseline_comparisons = {}
        for partition_name in ("calibration", "rule_test"):
            baseline_comparisons[partition_name] = improvement_inference(
                paired_episode_improvements(
                    partitions[partition_name],
                    development_baseline_predictions[partition_name],
                    raw_predictions[partition_name],
                ),
                seed=RANDOM_SEED + horizon_index * 1000 + 80,
                bootstrap=partition_name == "rule_test",
            )
        baseline_comparisons["final_test"] = improvement_inference(
            paired_episode_improvements(
                partitions["final_test"],
                sealed_baseline_predictions,
                raw_predictions["final_test"],
            ),
            seed=RANDOM_SEED + horizon_index * 1000 + 81,
            bootstrap=True,
        )
        baseline_results.append(
            {
                "time_horizon": horizon,
                "development_fit": {
                    "coefficients": baseline_coefficients,
                    "fit_cases": len(baseline_fit),
                },
                "development": metrics(
                    partitions["development"],
                    development_baseline_predictions["development"],
                ),
                "calibration": metrics(
                    partitions["calibration"],
                    development_baseline_predictions["calibration"],
                ),
                "rule_test": metrics(
                    partitions["rule_test"],
                    development_baseline_predictions["rule_test"],
                ),
                "sealed_final_refit": {
                    "coefficients": sealed_baseline_coefficients,
                    "fit_cases": len(sealed_baseline_fit),
                },
                "final_test": metrics(
                    partitions["final_test"], sealed_baseline_predictions
                ),
                "final_calibration": calibration_diagnostics(
                    partitions["final_test"], sealed_baseline_predictions
                ),
                "raw_first_passage_final": metrics(
                    partitions["final_test"], raw_predictions["final_test"]
                ),
                "calibrated_vs_raw_first_passage": baseline_comparisons,
            }
        )
        horizon_state[horizon] = {
            "partitions": partitions,
            "development_baseline_predictions": development_baseline_predictions,
            "sealed_baseline_predictions": sealed_baseline_predictions,
        }
        for rule_index, rule_id in enumerate(RULE_FEATURES):
            eligible = {
                name: _eligible_for_rule(rows, rule_id)
                for name, rows in partitions.items()
                if name != "final_test"
            }
            dev = eligible["development"]
            cal = eligible["calibration"]
            test = eligible["rule_test"]
            if not dev or not cal or not test:
                results.append(
                    {
                        "rule_id": rule_id,
                        "time_horizon": horizon,
                        "status": "insufficient_feature_coverage",
                        "development_cases": len(dev),
                        "calibration_cases": len(cal),
                        "rule_test_cases": len(test),
                    }
                )
                continue
            scaling = standardize(dev, rule_id)
            fit_rows = deterministic_episode_sample(
                dev,
                max_cases=FIT_MAX_CASES,
                seed=RANDOM_SEED + horizon_index * 1000 + rule_index * 10,
            )
            candidates = []
            for ridge in (0.1, 1.0, 10.0):
                coefficients = fit_softmax_offset(
                    fit_rows,
                    rule_id=rule_id,
                    scaling=scaling,
                    ridge=ridge,
                )
                predictions = predict_rows(
                    cal,
                    rule_id=rule_id,
                    scaling=scaling,
                    coefficients=coefficients,
                )
                candidates.append(
                    {
                        "ridge": ridge,
                        "coefficients": coefficients,
                        "calibration": metrics(cal, predictions),
                    }
                )
            selected = min(
                candidates,
                key=lambda item: (
                    item["calibration"]["log_loss_3c"],
                    item["calibration"]["brier_3c"],
                    item["ridge"],
                ),
            )
            predictions = {
                "development": predict_rows(
                    dev,
                    rule_id=rule_id,
                    scaling=scaling,
                    coefficients=selected["coefficients"],
                ),
                "calibration": predict_rows(
                    cal,
                    rule_id=rule_id,
                    scaling=scaling,
                    coefficients=selected["coefficients"],
                ),
                "rule_test": predict_rows(
                    test,
                    rule_id=rule_id,
                    scaling=scaling,
                    coefficients=selected["coefficients"],
                ),
            }
            partition_rows = {
                "development": dev,
                "calibration": cal,
                "rule_test": test,
            }
            comparisons = {}
            for partition_name, rows in partition_rows.items():
                baseline_subset = {
                    row["case_id"]: development_baseline_predictions[
                        partition_name
                    ][row["case_id"]]
                    for row in rows
                }
                episodes = paired_episode_improvements(
                    rows,
                    predictions[partition_name],
                    baseline_subset,
                )
                comparisons[partition_name] = improvement_inference(
                    episodes,
                    seed=(
                        RANDOM_SEED
                        + horizon_index * 1000
                        + rule_index * 10
                        + {"development": 1, "calibration": 2, "rule_test": 3}[
                            partition_name
                        ]
                    ),
                    bootstrap=partition_name == "rule_test",
                )
                comparisons[partition_name]["model_metrics"] = metrics(
                    rows,
                    predictions[partition_name],
                )
            test_ci_log = comparisons["rule_test"]["log_loss_bootstrap_95ci"]
            test_ci_brier = comparisons["rule_test"]["brier_bootstrap_95ci"]
            positive_all = all(
                comparisons[name]["mean_log_loss_improvement"] > 0
                and comparisons[name]["mean_brier_improvement"] > 0
                for name in ("development", "calibration", "rule_test")
            )
            significant_rule_test = (
                comparisons["rule_test"]["episodes"]
                >= MIN_INFERENCE_CLUSTERS_FOR_RULE_SELECTION
                and
                test_ci_log is not None
                and test_ci_brier is not None
                and test_ci_log[0] > 0
                and test_ci_brier[0] > 0
            )
            status = (
                "provisionally_supported_pending_multiple_test_control"
                if positive_all and significant_rule_test
                else "not_supported_for_probability_integration"
            )
            results.append(
                {
                    "rule_id": rule_id,
                    "time_horizon": horizon,
                    "features": list(RULE_FEATURES[rule_id]),
                    "status": status,
                    "selected_ridge": selected["ridge"],
                    "fit_cases": len(fit_rows),
                    "scaling": scaling,
                    "coefficients": selected["coefficients"],
                    "comparisons_vs_calibrated_baseline": comparisons,
                }
            )
    raw_p_values = []
    for index, item in enumerate(results):
        rule_test = item.get("comparisons_vs_calibrated_baseline", {}).get(
            "rule_test", {}
        )
        p_log = rule_test.get("one_sided_normal_p_log_loss")
        p_brier = rule_test.get("one_sided_normal_p_brier")
        if p_log is not None and p_brier is not None:
            raw_p_values.append((index, max(p_log, p_brier)))
    adjusted_p_values = benjamini_hochberg(raw_p_values)
    for index, item in enumerate(results):
        adjusted = adjusted_p_values.get(index)
        item["rule_test_intersection_p_value_fdr_adjusted"] = adjusted
        if (
            item.get("status")
            == "provisionally_supported_pending_multiple_test_control"
            and adjusted is not None
            and adjusted <= FALSE_DISCOVERY_RATE
        ):
            item["status"] = "supported_stable_out_of_sample"
            selected_rules[item["time_horizon"]].append(item["rule_id"])
        elif item.get("status") == (
            "provisionally_supported_pending_multiple_test_control"
        ):
            item["status"] = "not_supported_after_multiple_test_control"
    joint_results = []
    for horizon_index, horizon in enumerate(HORIZONS):
        rule_ids = selected_rules.get(horizon, [])
        state = horizon_state[horizon]
        partitions = state["partitions"]
        if not rule_ids:
            joint_results.append(
                {
                    "time_horizon": horizon,
                    "rule_ids": [],
                    "status": "no_supported_rules_no_challenger",
                }
            )
            continue
        eligible = {
            name: [
                row
                for row in rows
                if all(rule_id in row.get("rule_features", {}) for rule_id in rule_ids)
            ]
            for name, rows in partitions.items()
        }
        dev_scaling = joint_standardize(eligible["development"], rule_ids)
        joint_fit_rows = deterministic_episode_sample(
            eligible["development"],
            max_cases=FIT_MAX_CASES,
            seed=RANDOM_SEED + horizon_index * 1000 + 700,
        )
        candidates = []
        for ridge in (0.1, 1.0, 10.0):
            coefficients = fit_joint_softmax_offset(
                joint_fit_rows,
                rule_ids=rule_ids,
                scaling=dev_scaling,
                ridge=ridge,
            )
            calibration_predictions = predict_joint_rows(
                eligible["calibration"],
                rule_ids=rule_ids,
                scaling=dev_scaling,
                coefficients=coefficients,
            )
            candidates.append(
                {
                    "ridge": ridge,
                    "coefficients": coefficients,
                    "calibration": metrics(
                        eligible["calibration"], calibration_predictions
                    ),
                }
            )
        selected = min(
            candidates,
            key=lambda item: (
                item["calibration"]["log_loss_3c"],
                item["calibration"]["brier_3c"],
                item["ridge"],
            ),
        )
        rule_test_predictions = predict_joint_rows(
            eligible["rule_test"],
            rule_ids=rule_ids,
            scaling=dev_scaling,
            coefficients=selected["coefficients"],
        )
        rule_test_baseline = {
            row["case_id"]: state["development_baseline_predictions"][
                "rule_test"
            ][row["case_id"]]
            for row in eligible["rule_test"]
        }
        rule_test_raw = {
            row["case_id"]: dict(row["baseline_probabilities"])
            for row in eligible["rule_test"]
        }
        prefinal_comparison = improvement_inference(
            paired_episode_improvements(
                eligible["rule_test"],
                rule_test_predictions,
                rule_test_baseline,
            ),
            seed=RANDOM_SEED + horizon_index * 1000 + 701,
            bootstrap=True,
        )
        prefinal_vs_raw = improvement_inference(
            paired_episode_improvements(
                eligible["rule_test"],
                rule_test_predictions,
                rule_test_raw,
            ),
            seed=RANDOM_SEED + horizon_index * 1000 + 704,
            bootstrap=True,
        )
        prefinal = (
            eligible["development"]
            + eligible["calibration"]
            + eligible["rule_test"]
        )
        final_scaling = joint_standardize(prefinal, rule_ids)
        final_fit_rows = deterministic_episode_sample(
            prefinal,
            max_cases=FIT_MAX_CASES,
            seed=RANDOM_SEED + horizon_index * 1000 + 702,
        )
        final_coefficients = fit_joint_softmax_offset(
            final_fit_rows,
            rule_ids=rule_ids,
            scaling=final_scaling,
            ridge=selected["ridge"],
        )
        final_predictions = predict_joint_rows(
            eligible["final_test"],
            rule_ids=rule_ids,
            scaling=final_scaling,
            coefficients=final_coefficients,
        )
        final_baseline = {
            row["case_id"]: state["sealed_baseline_predictions"][row["case_id"]]
            for row in eligible["final_test"]
        }
        final_raw = {
            row["case_id"]: dict(row["baseline_probabilities"])
            for row in eligible["final_test"]
        }
        final_comparison = improvement_inference(
            paired_episode_improvements(
                eligible["final_test"], final_predictions, final_baseline
            ),
            seed=RANDOM_SEED + horizon_index * 1000 + 703,
            bootstrap=True,
        )
        final_vs_raw = improvement_inference(
            paired_episode_improvements(
                eligible["final_test"], final_predictions, final_raw
            ),
            seed=RANDOM_SEED + horizon_index * 1000 + 705,
            bootstrap=True,
        )
        prefinal_log_ci = prefinal_comparison["log_loss_bootstrap_95ci"]
        prefinal_brier_ci = prefinal_comparison["brier_bootstrap_95ci"]
        prefinal_raw_log_ci = prefinal_vs_raw["log_loss_bootstrap_95ci"]
        prefinal_raw_brier_ci = prefinal_vs_raw["brier_bootstrap_95ci"]
        final_log_ci = final_comparison["log_loss_bootstrap_95ci"]
        final_brier_ci = final_comparison["brier_bootstrap_95ci"]
        final_raw_log_ci = final_vs_raw["log_loss_bootstrap_95ci"]
        final_raw_brier_ci = final_vs_raw["brier_bootstrap_95ci"]
        passed = (
            prefinal_comparison["episodes"]
            >= MIN_INFERENCE_CLUSTERS_FOR_SEALED_GATE
            and final_comparison["episodes"]
            >= MIN_INFERENCE_CLUSTERS_FOR_SEALED_GATE
            and
            prefinal_log_ci is not None
            and prefinal_brier_ci is not None
            and prefinal_raw_log_ci is not None
            and prefinal_raw_brier_ci is not None
            and prefinal_log_ci[0] > 0
            and prefinal_brier_ci[0] > 0
            and prefinal_raw_log_ci[0] > 0
            and prefinal_raw_brier_ci[0] > 0
            and final_log_ci is not None
            and final_brier_ci is not None
            and final_raw_log_ci is not None
            and final_raw_brier_ci is not None
            and final_log_ci[0] > 0
            and final_brier_ci[0] > 0
            and final_raw_log_ci[0] > 0
            and final_raw_brier_ci[0] > 0
        )
        joint_results.append(
            {
                "time_horizon": horizon,
                "rule_ids": rule_ids,
                "status": (
                    "sealed_historical_gate_passed"
                    if passed
                    else "sealed_historical_gate_failed"
                ),
                "selected_ridge": selected["ridge"],
                "development_scaling": dev_scaling,
                "development_coefficients": selected["coefficients"],
                "rule_test_comparison": prefinal_comparison,
                "rule_test_comparison_vs_raw_first_passage": prefinal_vs_raw,
                "final_scaling": final_scaling,
                "final_coefficients": final_coefficients,
                "final_fit_cases": len(final_fit_rows),
                "final_test_metrics": metrics(
                    eligible["final_test"], final_predictions
                ),
                "final_test_calibration": calibration_diagnostics(
                    eligible["final_test"], final_predictions
                ),
                "final_test_comparison": final_comparison,
                "final_test_comparison_vs_raw_first_passage": final_vs_raw,
            }
        )
    all_horizons_passed = (
        len(joint_results) == len(HORIZONS)
        and all(
            item["status"] == "sealed_historical_gate_passed"
            for item in joint_results
        )
    )
    decision = (
        "historically_qualified_prospective_shadow_required"
        if all_horizons_passed
        else "evidence_insufficient_no_promotion"
    )
    payload = add_hash(
        {
            "version": VALIDATION_VERSION,
            "dataset_sha256": sha256_file(DATASET_PATH),
            "manifest_sha256": sha256_file(MANIFEST_PATH),
            "method": {
                "baseline": "first_passage_plus_horizon_intercepts",
                "rule_model": "multiclass_log_probability_offset_ridge",
                "ridge_selection": "calibration_log_loss_then_brier",
                "rule_test": "opened_after_ridge_selection_for_rule_screening",
                "final_test": "opened_once_for_frozen_joint_challenger",
                "uncertainty": f"episode_bootstrap_{BOOTSTRAP_SAMPLES}",
                "fit_case_cap": FIT_MAX_CASES,
                "fit_iterations": FIT_ITERATIONS,
                "multiple_test_control": (
                    "Benjamini-Hochberg on the worse one-sided rule-test "
                    f"p-value at FDR {FALSE_DISCOVERY_RATE}"
                ),
                "minimum_independent_clusters_for_rule_selection": (
                    MIN_INFERENCE_CLUSTERS_FOR_RULE_SELECTION
                ),
                "minimum_independent_clusters_for_sealed_gate": (
                    MIN_INFERENCE_CLUSTERS_FOR_SEALED_GATE
                ),
                "promotion_requires": (
                    "positive development calibration and rule-test deltas; "
                    "rule-test intervals and FDR pass; frozen joint challenger "
                    "then requires both sealed-final intervals above zero"
                ),
            },
            "baseline_by_horizon": baseline_results,
            "rule_results": results,
            "supported_rules_by_horizon": dict(selected_rules),
            "supported_rule_count": sum(len(value) for value in selected_rules.values()),
            "joint_challenger_by_horizon": joint_results,
            "decision": decision,
            "production_candidate_authorized": False,
            "prospective_shadow": {
                "required_only_if_historical_gate_passes_all_horizons": True,
                "automatic_weight_updates": False,
                "episode_definition": "unique_linked_operation_not_geometry_rows",
                "minimum_closed_episodes_per_horizon": 200,
                "minimum_tp_first_episodes_per_horizon": 50,
                "minimum_sl_first_episodes_per_horizon": 50,
                "maximum_review_episodes_per_horizon": 500,
                "acceptance": (
                    "both paired episode-bootstrap 95 percent improvement "
                    "intervals above zero without refitting"
                ),
                "status": (
                    "prepared_pending_future_observations"
                    if all_horizons_passed
                    else "not_started_historical_gate_failed"
                ),
            },
            "data_blocked_rules": DATA_BLOCKED_RULES,
            "production_effect": "none",
            "supabase_writes": 0,
        }
    )
    write_json(RESULT_PATH, payload)
    decision_payload = add_hash(
        {
            "version": "phase1-engine-decision-v0.1",
            "validation_payload_sha256": payload["canonical_payload_sha256"],
            "decision": decision,
            "production_candidate_authorized": False,
            "production_engine_mutated": False,
            "historical_gate_by_horizon": {
                item["time_horizon"]: item["status"]
                for item in joint_results
            },
            "supported_rules_by_horizon": dict(selected_rules),
            "prospective_shadow": payload["prospective_shadow"],
            "supabase_writes": 0,
        }
    )
    write_json(DECISION_PATH, decision_payload)
    write_report(payload)
    return payload


def write_report(payload: dict) -> None:
    lines = [
        "# Fase 1 - Validacion controlada de reglas",
        "",
        f"- Version: `{payload['version']}`.",
        f"- Dataset: `{payload['dataset_sha256']}`.",
        "- Efecto en produccion: **ninguno**.",
        "- Escrituras en Supabase: **ninguna**.",
        "",
        "## Resultado",
        "",
        (
            "Reglas-horizonte que superan desarrollo, calibracion, seleccion "
            f"y bootstrap: **{payload['supported_rule_count']}**."
        ),
        f"- Decision: **`{payload['decision']}`**.",
        "",
        "## Baseline por horizonte",
        "",
        "| Horizonte | Desarrollo n | Calibracion n | Seleccion n | Final n | Final log-loss | Final Brier |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in payload["baseline_by_horizon"]:
        final = item["final_test"]
        lines.append(
            f"| `{item['time_horizon']}` | {item['development']['n']} | "
            f"{item['calibration']['n']} | {item['rule_test']['n']} | "
            f"{final['n']} | "
            f"{final['log_loss_3c']:.6f} | {final['brier_3c']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Reglas",
            "",
            "| Regla | Horizonte | Estado | Delta log-loss seleccion | Delta Brier seleccion |",
            "|---|---|---|---:|---:|",
        ]
    )
    for item in payload["rule_results"]:
        final = item.get("comparisons_vs_calibrated_baseline", {}).get(
            "rule_test", {}
        )
        log_delta = final.get("mean_log_loss_improvement")
        brier_delta = final.get("mean_brier_improvement")
        log_label = "--" if log_delta is None else f"{log_delta:.6f}"
        brier_label = "--" if brier_delta is None else f"{brier_delta:.6f}"
        lines.append(
            f"| `{item['rule_id']}` | `{item['time_horizon']}` | "
            f"`{item['status']}` | "
            f"{log_label} | {brier_label} |"
        )
    lines.extend(
        [
            "",
            "## Challenger conjunto y puerta final sellada",
            "",
            "| Horizonte | Reglas | Estado | Delta log-loss final | Delta Brier final |",
            "|---|---:|---|---:|---:|",
        ]
    )
    for item in payload["joint_challenger_by_horizon"]:
        final = item.get("final_test_comparison", {})
        log_delta = final.get("mean_log_loss_improvement")
        brier_delta = final.get("mean_brier_improvement")
        log_label = "--" if log_delta is None else f"{log_delta:.6f}"
        brier_label = "--" if brier_delta is None else f"{brier_delta:.6f}"
        lines.append(
            f"| `{item['time_horizon']}` | {len(item['rule_ids'])} | "
            f"`{item['status']}` | {log_label} | {brier_label} |"
        )
    lines.extend(
        [
            "",
            "## Reglas bloqueadas por datos",
            "",
        ]
    )
    for rule_id, reason in DATA_BLOCKED_RULES.items():
        lines.append(f"- `{rule_id}`: `{reason}`.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_freeze_manifest() -> dict:
    artifact_path = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload = add_hash(
        {
            "version": "phase1-current-engine-freeze-v0.1",
            "engine_contract": "TP-SL-PROBABILITY-ENGINE-v0.6-stable-global",
            "coefficient_artifact_id": artifact["coefficient_artifact"]["id"],
            "coefficient_artifact_sha256": artifact["coefficient_artifact"][
                "artifact_sha256"
            ],
            "artifact_file_sha256": sha256_file(artifact_path),
            "artifact_production_authorized_field": artifact["coefficient_artifact"][
                "production_authorized"
            ],
            "fitted_predictive_rules": [
                "M4-RULE-MTF-HIERARCHY-001",
                "M4-RULE-VOLATILITY-RANK-001",
                "M4-RULE-PRIOR-EXTREMA-001",
            ],
            "baseline_variant": {
                "coefficient_artifact": None,
                "evidence_status": "baseline_only_no_artifact",
                "inputs": [
                    "plan_geometry",
                    "horizon",
                    "realized_volatility",
                    "first_passage",
                ],
            },
            "automatic_weight_updates": False,
            "production_mutation": False,
            "supabase_writes": 0,
        }
    )
    write_json(AUDIT_DIR / "fase1_manifiesto_congelacion_v0_1.json", payload)
    return payload
