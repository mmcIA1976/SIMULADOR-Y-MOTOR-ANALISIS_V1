from __future__ import annotations

"""Chronological, write-isolated pilot for the autonomous contest policy.

This script deliberately reuses the frozen v0.9 artifact and the exact active
feature formulae used by production.  It does not import a second predictive
model, write to Supabase, or mutate production state.
"""

import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import random
import urllib.error
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from empirical_temporal_engine import (
    ARTIFACT_PATH,
    CONDITIONAL_CLASSES,
    CUMULATIVE_CLASSES,
    ENGINE_VERSION,
    STAGE_BOUNDS,
    _current_feature_map,
    _stage_label,
    _weighted_probabilities,
    empirical_probabilities,
    load_production_artifact,
    plan_log_distances,
    selected_stage_order,
)
from multiscale_feature_runtime import (
    STAGE_PROFILES,
    _compression_features,
    build_stage_context,
    required_candle_count,
)
from phase1_controlled_replay import (
    ARCHIVE_DIR as MONTHLY_ARCHIVE_DIR,
    BASE_INTERVAL_MS,
    BASE_INTERVAL_SECONDS,
    SYMBOLS,
    aggregate_candles,
)


ROOT = Path(__file__).resolve().parent
REPLAY_DIR = ROOT / "data" / "autonomous_threshold_replay"
DAILY_ARCHIVE_DIR = REPLAY_DIR / "binance_usdm_5m_daily"
CANDIDATE_DIR = REPLAY_DIR / "candidates_v0_1"
OUTPUT_JSON = ROOT / "auditorias_motor" / "autonomous_threshold_replay_v0_1.json"
OUTPUT_MD = ROOT / "auditorias_motor" / "2026-08-30_prueba_cronologica_participantes.md"

REPLAY_VERSION = "autonomous-threshold-replay-v0.1"
DAILY_ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/klines"
START_DAY = date(2026, 8, 1)
END_DAY = date(2026, 8, 29)
THRESHOLDS = (0.00, 0.02, 0.04, 0.06, 0.08, 0.10)
MIN_TP_PROBABILITY = 0.30
MAX_UNRESOLVED_PROBABILITY = 0.55
MIN_ANALOGS_PER_STAGE = 80
POLICIES = {
    "intraday_short": {"cadence_minutes": 15, "quota_per_utc_day": 3, "max_open": 3},
    "intraday_wide": {"cadence_minutes": 60, "quota_per_utc_day": 2, "max_open": 2},
    "short_swing": {"cadence_minutes": 360, "quota_per_utc_day": 1, "max_open": 7},
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()


def _date_range(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _daily_path(symbol: str, day: date) -> Path:
    stamp = day.isoformat()
    return DAILY_ARCHIVE_DIR / symbol / f"{symbol}-5m-{stamp}.zip"


def _daily_url(symbol: str, day: date) -> str:
    name = _daily_path(symbol, day).name
    return f"{DAILY_ARCHIVE_BASE}/{symbol}/5m/{name}"


def _download_one(symbol: str, day: date) -> dict:
    path = _daily_path(symbol, day)
    if path.exists() and path.stat().st_size > 0:
        return {
            "symbol": symbol,
            "day": day.isoformat(),
            "status": "cached",
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".zip.part")
    try:
        request = urllib.request.Request(
            _daily_url(symbol, day),
            headers={"User-Agent": f"{REPLAY_VERSION}/offline"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            temporary.write_bytes(response.read())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("archive_crc_invalid")
        temporary.replace(path)
        return {
            "symbol": symbol,
            "day": day.isoformat(),
            "status": "downloaded",
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, ValueError) as exc:
        if temporary.exists():
            temporary.unlink()
        return {
            "symbol": symbol,
            "day": day.isoformat(),
            "status": "unavailable",
            "reason": f"{type(exc).__name__}:{exc}",
        }


def download_daily_archives() -> dict:
    jobs = [(symbol, day) for symbol in SYMBOLS for day in _date_range(START_DAY, END_DAY)]
    records = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_download_one, symbol, day): (symbol, day) for symbol, day in jobs}
        for future in as_completed(futures):
            result = future.result()
            records.append(result)
            print(f"ARCHIVE {result['symbol']} {result['day']} {result['status']}", flush=True)
    records.sort(key=lambda row: (row["symbol"], row["day"]))
    payload = {
        "version": REPLAY_VERSION,
        "source": "Binance USD-M public daily kline archive",
        "interval": "5m",
        "start_day": START_DAY.isoformat(),
        "end_day": END_DAY.isoformat(),
        "records": records,
        "status_counts": dict(Counter(row["status"] for row in records)),
        "supabase_writes": 0,
    }
    payload["canonical_payload_sha256"] = _sha256_json(payload)
    manifest_path = REPLAY_DIR / "daily_archive_manifest_v0_1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if any(row["status"] == "unavailable" for row in records):
        unavailable = [f"{row['symbol']}:{row['day']}" for row in records if row["status"] == "unavailable"]
        raise RuntimeError("daily_archives_unavailable:" + ",".join(unavailable))
    return payload


def _normalize_timestamp(value: str) -> int:
    number = int(float(value))
    return number // 1000 if number > 10**15 else number


def _read_zip(path: Path, rows: dict[int, dict]) -> None:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"archive_csv_member_invalid:{path.name}")
        with archive.open(members[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8")
            for values in csv.reader(text):
                if not values or not values[0] or not values[0][0].isdigit() or len(values) < 11:
                    continue
                open_time = _normalize_timestamp(values[0])
                rows[open_time] = {
                    "open_time_ms": open_time,
                    "open": float(values[1]),
                    "high": float(values[2]),
                    "low": float(values[3]),
                    "close": float(values[4]),
                    "volume": float(values[5]),
                    "close_time_ms": _normalize_timestamp(values[6]),
                    "quote_volume": float(values[7]),
                    "taker_buy_base_volume": float(values[9]),
                    "taker_buy_quote_volume": float(values[10]),
                }


def read_replay_candles(symbol: str) -> list[dict]:
    # 427 days of 5m material are needed by the 6h stage; May 2025 is a safe boundary.
    rows: dict[int, dict] = {}
    for path in sorted((MONTHLY_ARCHIVE_DIR / symbol).glob(f"{symbol}-5m-*.zip")):
        stamp = path.stem[-7:]
        if stamp >= "2025-05":
            _read_zip(path, rows)
    for path in sorted((DAILY_ARCHIVE_DIR / symbol).glob(f"{symbol}-5m-2026-08-*.zip")):
        _read_zip(path, rows)
    candles = [rows[key] for key in sorted(rows)]
    if not candles:
        raise ValueError(f"no_replay_candles:{symbol}")
    previous = candles[0]["open_time_ms"]
    for candle in candles[1:]:
        current = candle["open_time_ms"]
        if current - previous != BASE_INTERVAL_MS:
            raise ValueError(f"gapped_5m_replay_data:{symbol}:{_iso_ms(previous)}:{_iso_ms(current)}")
        previous = current
    return candles


def _active_context(horizon: str, candles: list[dict], analysis_ms: int) -> dict:
    count = required_candle_count(horizon)
    close_times = [int(row["close_time_ms"]) for row in candles]
    end = bisect.bisect_right(close_times, analysis_ms)
    selected = candles[end - count : end]
    if len(selected) != count:
        raise ValueError(f"insufficient_context:{horizon}:{_iso_ms(analysis_ms)}")
    interval_ms = int(STAGE_PROFILES[horizon]["interval_seconds"]) * 1000
    if int(selected[-1]["close_time_ms"]) > analysis_ms:
        raise ValueError("future_candle_in_context")
    if analysis_ms - int(selected[-1]["close_time_ms"]) > interval_ms + 60_000:
        raise ValueError(f"stale_context:{horizon}:{_iso_ms(analysis_ms)}")
    if any(
        int(right["open_time_ms"]) - int(left["open_time_ms"]) != interval_ms
        for left, right in zip(selected, selected[1:])
    ):
        raise ValueError(f"gapped_stage_context:{horizon}:{_iso_ms(analysis_ms)}")

    closes = [float(row["close"]) for row in selected]
    returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:])]
    return_count = int(STAGE_PROFILES[horizon]["horizon_seconds"]) // int(
        STAGE_PROFILES[horizon]["interval_seconds"]
    )
    current_returns = returns[-return_count:]
    reference_variances = [
        math.fsum(value * value for value in returns[index : index + return_count])
        for index in range(0, 60 * return_count, return_count)
    ]
    current_variance = math.fsum(value * value for value in current_returns)

    def efficiency(values: list[float]) -> float:
        variation = math.fsum(abs(value) for value in values)
        return math.fsum(values) / variation if variation > 0.0 else 0.0

    below = sum(value < current_variance for value in reference_variances)
    equal = sum(value == current_variance for value in reference_variances)
    volatility_rank = (below + 0.5 * equal) / len(reference_variances)
    material = {"selected": selected, "return_count": return_count}
    compression = _compression_features(material)
    return {
        "horizon": horizon,
        "sigma": math.sqrt(current_variance),
        "signed_h": efficiency(returns[-return_count:]),
        "signed_2h": efficiency(returns[-2 * return_count :]),
        "signed_4h": efficiency(returns[-4 * return_count :]),
        "volatility_rank": volatility_rank,
        "compression": compression,
        "data_cutoff_at_ms": int(selected[-1]["close_time_ms"]),
        "selected": selected,
    }


def _stage_context_for_side(base: dict, side: str) -> dict:
    direction = 1.0 if side == "long" else -1.0
    horizon = base["horizon"]
    prefix = f"{horizon}::"
    feature_values = {
        prefix + "M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h": direction * base["signed_h"],
        prefix + "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h": direction * base["signed_2h"],
        prefix + "M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h": direction * base["signed_4h"],
        prefix + "M4-RULE-VOLATILITY-RANK-001::volatility_percentile_60": base["volatility_rank"],
        prefix + "LIB-CAND-COMPRESSION-001::compression_vector.atr_rank": base["compression"]["compression_vector.atr_rank"],
        prefix + "LIB-CAND-COMPRESSION-001::compression_vector.bollinger_width_rank": base["compression"]["compression_vector.bollinger_width_rank"],
    }
    # Production prefixes at _current_feature_map time, not inside stage contexts.
    feature_values = {name[len(prefix) :]: value for name, value in feature_values.items()}
    return {
        "time_horizon": horizon,
        "context_sigma": base["sigma"],
        "feature_values": feature_values,
        "data_cutoff_at_ms": base["data_cutoff_at_ms"],
    }


@dataclass
class _StageMatrix:
    vectors: np.ndarray
    analogs: list[dict]
    orientations: np.ndarray
    ids: np.ndarray
    symbols: np.ndarray


class FastFrozenAnalogRuntime:
    """Point-estimate path of v0.9, vectorized but contract-equivalent."""

    def __init__(self, artifact: dict):
        self.artifact = artifact
        self.stage_matrices: dict[str, _StageMatrix] = {}
        for stage_index, horizon in enumerate(STAGE_PROFILES):
            vectors = []
            analogs = []
            orientations = []
            ids = []
            symbols = []
            for analog in artifact["analogs"]:
                for orientation in (0, 1):
                    vectors.append(analog["feature_vectors"][stage_index][orientation])
                    analogs.append(analog)
                    orientations.append(orientation)
                    ids.append(str(analog["id"]))
                    symbols.append(str(analog["symbol"]).upper())
            self.stage_matrices[horizon] = _StageMatrix(
                vectors=np.asarray(vectors, dtype=np.float64),
                analogs=analogs,
                orientations=np.asarray(orientations, dtype=np.int8),
                ids=np.asarray(ids),
                symbols=np.asarray(symbols),
            )

    def _stage(self, *, horizon: str, current_map: dict, symbol: str, tp_distance: float, sl_distance: float) -> tuple[dict, dict]:
        names = self.artifact["feature_names"][horizon]
        scaling = self.artifact["feature_scaling"][horizon]
        current = np.asarray(
            [(float(current_map[name]) - float(center)) / float(scale) for name, (center, scale) in zip(names, scaling)],
            dtype=np.float64,
        )
        matrix = self.stage_matrices[horizon]
        squared = np.minimum(36.0, (matrix.vectors - current) ** 2)
        distances = np.sqrt(np.sum(squared, axis=1) / matrix.vectors.shape[1])
        cross_penalty = float(self.artifact["selection"]["cross_symbol_penalty"])
        distances = distances + np.where(matrix.symbols == symbol.upper(), 0.0, cross_penalty)
        order = np.lexsort((matrix.orientations, matrix.ids, distances))
        support_limit = float(
            self.artifact["selection"]["maximum_nearest_context_distance_by_horizon"][horizon]
        )
        nearest = float(distances[int(order[0])])
        if nearest > support_limit:
            raise ValueError(f"context_outside_historical_support:{horizon}:{nearest:.6f}>{support_limit:.6f}")
        start_step, end_step = STAGE_BOUNDS[horizon]
        target = int(self.artifact["selection"]["neighbor_count"])
        maximum = int(self.artifact["selection"]["maximum_scanned"])
        selected = []
        ambiguous = 0
        pre_stage = 0
        scanned = 0
        for raw_index in order[:maximum]:
            index = int(raw_index)
            scanned += 1
            label = _stage_label(
                matrix.analogs[index],
                int(matrix.orientations[index]),
                tp_distance=tp_distance,
                sl_distance=sl_distance,
                start_step=start_step,
                end_step=end_step,
            )
            if label is None:
                pre_stage += 1
                continue
            if label == "ambiguous":
                ambiguous += 1
                continue
            selected.append(
                {
                    "distance": float(distances[index]),
                    "label": label,
                    "same_symbol": bool(matrix.symbols[index] == symbol.upper()),
                    "analog_id": str(matrix.ids[index]),
                    "orientation": "long" if int(matrix.orientations[index]) == 0 else "short",
                }
            )
            if len(selected) >= target:
                break
        probabilities, trace = _weighted_probabilities(
            selected,
            probability_temperature=float(self.artifact["selection"].get("probability_temperature", 1.0)),
        )
        trace.update(
            {
                "nearest_context_distance": nearest,
                "maximum_context_distance_allowed": support_limit,
                "selected_analogs": len(selected),
                "scanned_candidates": scanned,
                "ambiguous_excluded": ambiguous,
                "resolved_before_stage_excluded": pre_stage,
            }
        )
        return probabilities, trace

    def predict(self, *, symbol: str, side: str, entry: float, take_profit: float, stop_loss: float, time_horizon: str, stage_contexts: dict[str, dict]) -> dict:
        tp_distance, sl_distance = plan_log_distances(
            side=side, entry=entry, take_profit=take_profit, stop_loss=stop_loss
        )
        survival = 1.0
        cumulative_tp = cumulative_sl = 0.0
        traces = []
        for horizon in selected_stage_order(time_horizon):
            names = self.artifact["feature_names"][horizon]
            current_map = _current_feature_map(horizon, stage_contexts, names)
            conditional, trace = self._stage(
                horizon=horizon,
                current_map=current_map,
                symbol=symbol,
                tp_distance=tp_distance,
                sl_distance=sl_distance,
            )
            cumulative_tp += survival * conditional[CONDITIONAL_CLASSES[0]]
            cumulative_sl += survival * conditional[CONDITIONAL_CLASSES[1]]
            survival *= conditional[CONDITIONAL_CLASSES[2]]
            survival += 1.0 - (cumulative_tp + cumulative_sl + survival)
            traces.append({"horizon": horizon, "conditional": conditional, **trace})
        return {
            "tp": cumulative_tp,
            "sl": cumulative_sl,
            "unresolved": survival,
            "edge": cumulative_tp - cumulative_sl,
            "traces": traces,
        }


def _geometry(entry: float, sigma: float, side: str) -> tuple[float, float]:
    if not math.isfinite(sigma) or sigma <= 0.0 or sigma >= 0.50:
        raise ValueError(f"invalid_horizon_sigma:{sigma}")
    lower = entry * (1.0 - sigma)
    upper = entry * (1.0 + sigma)
    return (upper, lower) if side == "long" else (lower, upper)


def _outcome(candles_by_open: dict[int, dict], *, entry_ms: int, horizon_seconds: int, side: str, entry: float, take_profit: float, stop_loss: float) -> dict:
    expected = int(horizon_seconds) // BASE_INTERVAL_SECONDS
    final = None
    for offset in range(expected):
        candle = candles_by_open.get(entry_ms + offset * BASE_INTERVAL_MS)
        if candle is None:
            raise ValueError(f"incomplete_future:{_iso_ms(entry_ms)}:{offset}")
        final = candle
        if side == "long":
            tp_hit = float(candle["high"]) >= take_profit
            sl_hit = float(candle["low"]) <= stop_loss
        else:
            tp_hit = float(candle["low"]) <= take_profit
            sl_hit = float(candle["high"]) >= stop_loss
        if tp_hit and sl_hit:
            return {"label": "ambiguous", "close_ms": int(candle["close_time_ms"]), "r": None}
        if tp_hit:
            return {"label": "tp", "close_ms": int(candle["close_time_ms"]), "r": 1.0}
        if sl_hit:
            return {"label": "sl", "close_ms": int(candle["close_time_ms"]), "r": -1.0}
    if final is None:
        raise AssertionError("empty_future")
    risk = abs(entry - stop_loss)
    terminal = float(final["close"])
    terminal_r = (terminal - entry) / risk if side == "long" else (entry - terminal) / risk
    return {"label": "unresolved", "close_ms": int(final["close_time_ms"]), "r": terminal_r}


def _candidate_path(symbol: str) -> Path:
    return CANDIDATE_DIR / f"{symbol}.jsonl.gz"


def _scan_times(horizon: str, last_open_ms: int) -> list[int]:
    start_ms = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)
    cadence_ms = int(POLICIES[horizon]["cadence_minutes"]) * 60_000
    horizon_ms = int(STAGE_PROFILES[horizon]["horizon_seconds"]) * 1000
    last_entry = last_open_ms - horizon_ms + BASE_INTERVAL_MS
    return list(range(start_ms, last_entry + 1, cadence_ms))


def _build_interval_sets(base: list[dict]) -> dict[str, list[dict]]:
    return {
        "intraday_short": base,
        "intraday_wide": aggregate_candles(base, 60 * 60),
        "short_swing": aggregate_candles(base, 6 * 60 * 60),
    }


def generate_symbol_candidates(symbol: str, runtime: FastFrozenAnalogRuntime, *, smoke: bool = False) -> dict:
    print(f"CANDIDATES {symbol} loading", flush=True)
    base = read_replay_candles(symbol)
    by_open = {int(row["open_time_ms"]): row for row in base}
    intervals = _build_interval_sets(base)
    last_open_ms = int(base[-1]["open_time_ms"])
    rows = []
    errors = Counter()
    for horizon in STAGE_PROFILES:
        times = _scan_times(horizon, last_open_ms)
        if smoke:
            times = times[:2]
        needed_stages = selected_stage_order(horizon)
        for scan_index, analysis_ms in enumerate(times, 1):
            entry_candle = by_open.get(analysis_ms)
            if entry_candle is None:
                errors["entry_candle_missing"] += 1
                continue
            try:
                bases = {
                    stage: _active_context(stage, intervals[stage], analysis_ms)
                    for stage in needed_stages
                }
                sigma = float(bases[horizon]["sigma"])
                entry = float(entry_candle["open"])
                for side in ("long", "short"):
                    take_profit, stop_loss = _geometry(entry, sigma, side)
                    contexts = {
                        stage: _stage_context_for_side(bases[stage], side)
                        for stage in needed_stages
                    }
                    result = runtime.predict(
                        symbol=symbol,
                        side=side,
                        entry=entry,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        time_horizon=horizon,
                        stage_contexts=contexts,
                    )
                    outcome = _outcome(
                        by_open,
                        entry_ms=analysis_ms,
                        horizon_seconds=int(STAGE_PROFILES[horizon]["horizon_seconds"]),
                        side=side,
                        entry=entry,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                    )
                    rows.append(
                        {
                            "scan_at_ms": analysis_ms,
                            "scan_at": _iso_ms(analysis_ms),
                            "symbol": symbol,
                            "horizon": horizon,
                            "side": side,
                            "entry": entry,
                            "take_profit": take_profit,
                            "stop_loss": stop_loss,
                            "sigma": sigma,
                            "tp_probability": result["tp"],
                            "sl_probability": result["sl"],
                            "unresolved_probability": result["unresolved"],
                            "edge": result["edge"],
                            "minimum_selected_analogs": min(trace["selected_analogs"] for trace in result["traces"]),
                            "maximum_nearest_context_distance_ratio": max(
                                trace["nearest_context_distance"] / trace["maximum_context_distance_allowed"]
                                for trace in result["traces"]
                            ),
                            "outcome": outcome,
                        }
                    )
            except Exception as exc:
                errors[f"{type(exc).__name__}:{exc}"] += 1
            if scan_index % 192 == 0:
                print(f"CANDIDATES {symbol} {horizon} {scan_index}/{len(times)}", flush=True)
    path = _candidate_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as target:
        for row in rows:
            target.write(_canonical_json(row) + "\n")
    summary = {
        "symbol": symbol,
        "candidate_count": len(rows),
        "errors": dict(errors),
        "support_blocked_scan_count": sum(
            count
            for code, count in errors.items()
            if code.startswith("ValueError:context_outside_historical_support")
        ),
        "unexpected_error_count": sum(
            count
            for code, count in errors.items()
            if not code.startswith("ValueError:context_outside_historical_support")
        ),
        "path": str(path),
        "sha256": _sha256_file(path),
    }
    print(f"CANDIDATES {symbol} complete {len(rows)} errors={sum(errors.values())}", flush=True)
    return summary


def _generate_symbol_worker(symbol: str) -> dict:
    # Each Windows worker owns its immutable matrix; no mutable state is shared.
    return generate_symbol_candidates(
        symbol,
        FastFrozenAnalogRuntime(load_production_artifact()),
        smoke=False,
    )


def _full_stage_contexts(symbol: str, side: str, horizon: str, analysis_ms: int, entry: float, sigma: float, intervals: dict[str, list[dict]]) -> dict:
    take_profit, stop_loss = _geometry(entry, sigma, side)
    contexts = {}
    for stage in selected_stage_order(horizon):
        plan = {
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "time_horizon": stage,
            "horizon_seconds": int(STAGE_PROFILES[stage]["horizon_seconds"]),
            "analysis_at": _iso_ms(analysis_ms),
        }
        contexts[stage] = build_stage_context(plan, intervals[stage])
    return contexts


def validate_fast_runtime(runtime: FastFrozenAnalogRuntime) -> dict:
    comparisons = []
    for horizon in STAGE_PROFILES:
        selected_sample = None
        for symbol in SYMBOLS:
            base = read_replay_candles(symbol)
            intervals = _build_interval_sets(base)
            by_open = {int(row["open_time_ms"]): row for row in base}
            for day in range(1, 30):
                for hour in (0, 6, 12, 18):
                    analysis_ms = int(
                        datetime(2026, 8, day, hour, tzinfo=timezone.utc).timestamp()
                        * 1000
                    )
                    entry = float(by_open[analysis_ms]["open"])
                    bases = {
                        stage: _active_context(stage, intervals[stage], analysis_ms)
                        for stage in selected_stage_order(horizon)
                    }
                    try:
                        for side in ("long", "short"):
                            take_profit, stop_loss = _geometry(entry, bases[horizon]["sigma"], side)
                            fast_contexts = {
                                stage: _stage_context_for_side(bases[stage], side)
                                for stage in bases
                            }
                            runtime.predict(
                                symbol=symbol,
                                side=side,
                                entry=entry,
                                take_profit=take_profit,
                                stop_loss=stop_loss,
                                time_horizon=horizon,
                                stage_contexts=fast_contexts,
                            )
                    except ValueError as exc:
                        if str(exc).startswith("context_outside_historical_support"):
                            continue
                        raise
                    selected_sample = (
                        symbol,
                        intervals,
                        analysis_ms,
                        entry,
                        bases,
                    )
                    break
                if selected_sample is not None:
                    break
            if selected_sample is not None:
                break
        if selected_sample is None:
            # Preserve the production support gate.  When an entire replay
            # horizon is outside it, validate the active feature assembly
            # against production and record that probabilities are correctly
            # unavailable instead of weakening the gate to manufacture them.
            symbol = "ETHUSDT"
            base = read_replay_candles(symbol)
            intervals = _build_interval_sets(base)
            by_open = {int(row["open_time_ms"]): row for row in base}
            analysis_ms = int(
                datetime(2026, 8, 8, 12, tzinfo=timezone.utc).timestamp()
                * 1000
            )
            entry = float(by_open[analysis_ms]["open"])
            bases = {
                stage: _active_context(stage, intervals[stage], analysis_ms)
                for stage in selected_stage_order(horizon)
            }
            sigma = bases[horizon]["sigma"]
            for side in ("long", "short"):
                take_profit, stop_loss = _geometry(entry, sigma, side)
                fast_contexts = {
                    stage: _stage_context_for_side(bases[stage], side)
                    for stage in bases
                }
                full_contexts = _full_stage_contexts(
                    symbol, side, horizon, analysis_ms, entry, sigma, intervals
                )
                names = runtime.artifact["feature_names"][horizon]
                fast_map = _current_feature_map(horizon, fast_contexts, names)
                full_map = _current_feature_map(horizon, full_contexts, names)
                feature_delta = max(
                    abs(fast_map[name] - full_map[name]) for name in names
                )
                try:
                    runtime.predict(
                        symbol=symbol,
                        side=side,
                        entry=entry,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        time_horizon=horizon,
                        stage_contexts=fast_contexts,
                    )
                except ValueError as exc:
                    if not str(exc).startswith("context_outside_historical_support"):
                        raise
                    block_code = str(exc)
                else:
                    raise AssertionError("expected_support_block_missing")
                comparisons.append(
                    {
                        "horizon": horizon,
                        "side": side,
                        "symbol": symbol,
                        "analysis_at": _iso_ms(analysis_ms),
                        "validation_mode": "feature_equivalence_and_support_gate",
                        "support_block_code": block_code,
                        "maximum_active_feature_delta": feature_delta,
                        "maximum_probability_delta": None,
                    }
                )
            continue
        symbol, intervals, analysis_ms, entry, bases = selected_sample
        sigma = bases[horizon]["sigma"]
        for side in ("long", "short"):
            take_profit, stop_loss = _geometry(entry, sigma, side)
            fast_contexts = {stage: _stage_context_for_side(bases[stage], side) for stage in bases}
            full_contexts = _full_stage_contexts(
                symbol, side, horizon, analysis_ms, entry, sigma, intervals
            )
            names = runtime.artifact["feature_names"][horizon]
            fast_map = _current_feature_map(horizon, fast_contexts, names)
            full_map = _current_feature_map(horizon, full_contexts, names)
            feature_delta = max(abs(fast_map[name] - full_map[name]) for name in names)
            fast = runtime.predict(
                symbol=symbol,
                side=side,
                entry=entry,
                take_profit=take_profit,
                stop_loss=stop_loss,
                time_horizon=horizon,
                stage_contexts=fast_contexts,
            )
            full = empirical_probabilities(
                symbol=symbol,
                side=side,
                entry=entry,
                take_profit=take_profit,
                stop_loss=stop_loss,
                time_horizon=horizon,
                stage_contexts=full_contexts,
                analysis_at=_iso_ms(analysis_ms),
                artifact=runtime.artifact,
            )
            probabilities = full["probabilities"]
            probability_delta = max(
                abs(fast["tp"] - probabilities[CUMULATIVE_CLASSES[0]]),
                abs(fast["sl"] - probabilities[CUMULATIVE_CLASSES[1]]),
                abs(fast["unresolved"] - probabilities[CUMULATIVE_CLASSES[2]]),
            )
            comparisons.append(
                {
                    "horizon": horizon,
                    "side": side,
                    "symbol": symbol,
                    "analysis_at": _iso_ms(analysis_ms),
                    "validation_mode": "full_probability_equivalence",
                    "maximum_active_feature_delta": feature_delta,
                    "maximum_probability_delta": probability_delta,
                }
            )
    maximum_feature_delta = max(row["maximum_active_feature_delta"] for row in comparisons)
    probability_deltas = [
        row["maximum_probability_delta"]
        for row in comparisons
        if row["maximum_probability_delta"] is not None
    ]
    maximum_probability_delta = max(probability_deltas)
    if maximum_feature_delta > 1e-12 or maximum_probability_delta > 1e-10:
        raise AssertionError(
            f"fast_runtime_not_equivalent:features={maximum_feature_delta}:probabilities={maximum_probability_delta}"
        )
    result = {
        "status": (
            "passed_with_preserved_support_block"
            if any(row["maximum_probability_delta"] is None for row in comparisons)
            else "passed"
        ),
        "comparisons": comparisons,
        "maximum_active_feature_delta": maximum_feature_delta,
        "maximum_probability_delta": maximum_probability_delta,
    }
    print(
        f"VALIDATION passed feature_delta={maximum_feature_delta:.3g} probability_delta={maximum_probability_delta:.3g}",
        flush=True,
    )
    return result


def _load_candidates() -> list[dict]:
    rows = []
    for symbol in SYMBOLS:
        with gzip.open(_candidate_path(symbol), "rt", encoding="utf-8") as source:
            rows.extend(json.loads(line) for line in source if line.strip())
    return rows


def _simulate_threshold(rows: list[dict], horizon: str, threshold: float) -> dict:
    policy = POLICIES[horizon]
    by_scan: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if row["horizon"] == horizon:
            by_scan[int(row["scan_at_ms"])].append(row)
    open_positions: list[dict] = []
    selected = []
    daily_counts = Counter()
    eligible_scan_count = 0
    for scan_ms in sorted(by_scan):
        open_positions = [row for row in open_positions if int(row["outcome"]["close_ms"]) > scan_ms]
        utc_day = datetime.fromtimestamp(scan_ms / 1000, tz=timezone.utc).date().isoformat()
        if daily_counts[utc_day] >= int(policy["quota_per_utc_day"]):
            continue
        if len(open_positions) >= int(policy["max_open"]):
            continue
        candidates = [
            row
            for row in by_scan[scan_ms]
            if float(row["edge"]) >= threshold
            and float(row["tp_probability"]) >= MIN_TP_PROBABILITY
            and float(row["unresolved_probability"]) <= MAX_UNRESOLVED_PROBABILITY
            and int(row["minimum_selected_analogs"]) >= MIN_ANALOGS_PER_STAGE
            and not any(
                active["symbol"] == row["symbol"] and active["side"] == row["side"]
                for active in open_positions
            )
        ]
        if not candidates:
            continue
        eligible_scan_count += 1
        candidates.sort(
            key=lambda row: (
                -float(row["edge"]),
                -float(row["tp_probability"]),
                float(row["unresolved_probability"]),
                row["symbol"],
                row["side"],
            )
        )
        chosen = candidates[0]
        selected.append(chosen)
        open_positions.append(chosen)
        daily_counts[utc_day] += 1

    outcomes = Counter(row["outcome"]["label"] for row in selected)
    strict_r = math.fsum(
        -1.0 if row["outcome"]["label"] == "ambiguous" else float(row["outcome"]["r"])
        for row in selected
    )
    optimistic_r = math.fsum(
        1.0 if row["outcome"]["label"] == "ambiguous" else float(row["outcome"]["r"])
        for row in selected
    )
    unambiguous = [row for row in selected if row["outcome"]["label"] != "ambiguous"]
    brier_values = []
    log_losses = []
    class_names = ("tp", "sl", "unresolved")
    for row in unambiguous:
        label = row["outcome"]["label"]
        probabilities = {
            "tp": float(row["tp_probability"]),
            "sl": float(row["sl_probability"]),
            "unresolved": float(row["unresolved_probability"]),
        }
        brier_values.append(math.fsum((probabilities[name] - (1.0 if name == label else 0.0)) ** 2 for name in class_names))
        log_losses.append(-math.log(max(probabilities[label], 1e-15)))
    days = len({datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date() for ms in by_scan})
    maximum_trades = days * int(policy["quota_per_utc_day"])
    resolved = outcomes["tp"] + outcomes["sl"]
    calendar_days = sorted(
        {datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat() for ms in by_scan}
    )
    rows_by_day: dict[str, list[dict]] = defaultdict(list)
    for row in selected:
        selected_day = datetime.fromtimestamp(
            int(row["scan_at_ms"]) / 1000, tz=timezone.utc
        ).date().isoformat()
        rows_by_day[selected_day].append(row)

    def strict_row_r(row: dict) -> float:
        return (
            -1.0
            if row["outcome"]["label"] == "ambiguous"
            else float(row["outcome"]["r"])
        )

    rng = random.Random(
        int(hashlib.sha256(f"{horizon}|{threshold:.6f}".encode()).hexdigest()[:16], 16)
    )
    bootstrap_mean_r = []
    bootstrap_period_r = []
    for _ in range(4000):
        drawn = [rng.choice(calendar_days) for _ in calendar_days]
        drawn_rows = [row for day_key in drawn for row in rows_by_day.get(day_key, [])]
        total = math.fsum(strict_row_r(row) for row in drawn_rows)
        bootstrap_period_r.append(total)
        if drawn_rows:
            bootstrap_mean_r.append(total / len(drawn_rows))

    def interval(values: list[float]) -> dict | None:
        if not values:
            return None
        ordered = sorted(values)
        return {
            "low": ordered[int(0.025 * len(ordered))],
            "high": ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))],
            "method": "utc_day_cluster_bootstrap_4000",
        }

    return {
        "horizon": horizon,
        "edge_threshold": threshold,
        "scan_count": len(by_scan),
        "eligible_scan_count": eligible_scan_count,
        "trade_count": len(selected),
        "maximum_possible_by_daily_quota": maximum_trades,
        "quota_utilization": len(selected) / maximum_trades if maximum_trades else 0.0,
        "outcomes": dict(outcomes),
        "resolved_win_rate": outcomes["tp"] / resolved if resolved else None,
        "strict_total_r_ambiguous_as_loss": strict_r,
        "strict_mean_r": strict_r / len(selected) if selected else None,
        "strict_mean_r_95pct": interval(bootstrap_mean_r),
        "strict_period_r_95pct": interval(bootstrap_period_r),
        "optimistic_total_r_ambiguous_as_win": optimistic_r,
        "mean_three_class_brier": math.fsum(brier_values) / len(brier_values) if brier_values else None,
        "mean_log_loss": math.fsum(log_losses) / len(log_losses) if log_losses else None,
        "selected_trade_keys": [
            f"{row['scan_at']}|{row['symbol']}|{row['side']}" for row in selected
        ],
    }


def _render_report(payload: dict) -> str:
    lines = [
        "# Prueba cronológica mínima de participantes autónomos",
        "",
        f"- Motor: `{payload['engine']['version']}` / artefacto `{payload['engine']['artifact_id']}`.",
        f"- Ventana: {payload['window']['start']} a {payload['window']['end']} (UTC).",
        "- Entrada simulada: apertura de la vela de 5 minutos inmediatamente posterior al corte de datos.",
        "- Geometría: TP y SL simétricos a una sigma del horizonte; resultado bruto en R, sin costes.",
        "- Producción y Supabase: cero escrituras.",
        f"- Contextos evaluados: {payload['evaluated_scan_context_count']}; bloqueados por soporte: "
        f"{payload['support_blocked_scan_count']} ({payload['support_block_rate'] * 100:.2f}%); "
        f"errores inesperados: {payload['unexpected_candidate_error_count']}.",
        "",
        "## Equivalencia con producción",
        "",
        f"Validación `{payload['runtime_validation']['status']}`. Diferencia máxima de features activas: "
        f"`{payload['runtime_validation']['maximum_active_feature_delta']:.3g}`; diferencia máxima de probabilidad: "
        f"`{payload['runtime_validation']['maximum_probability_delta']:.3g}`.",
        "",
        "## Resultados por umbral",
        "",
        "| Horizonte | Umbral edge | Trades | Cuota | TP | SL | Sin resolver | Ambiguos | Win rate resuelto | R estricto | R/trade (IC 95%) | Brier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["results"]:
        outcomes = row["outcomes"]
        win_rate = "—" if row["resolved_win_rate"] is None else f"{row['resolved_win_rate'] * 100:.1f}%"
        mean_r = "—" if row["strict_mean_r"] is None else f"{row['strict_mean_r']:.3f}"
        if row["strict_mean_r_95pct"] is not None:
            mean_r += (
                f" ({row['strict_mean_r_95pct']['low']:.3f}, "
                f"{row['strict_mean_r_95pct']['high']:.3f})"
            )
        brier = "—" if row["mean_three_class_brier"] is None else f"{row['mean_three_class_brier']:.3f}"
        lines.append(
            f"| {row['horizon']} | {row['edge_threshold'] * 100:.0f} pp | {row['trade_count']} | "
            f"{row['quota_utilization'] * 100:.1f}% | {outcomes.get('tp', 0)} | {outcomes.get('sl', 0)} | "
            f"{outcomes.get('unresolved', 0)} | {outcomes.get('ambiguous', 0)} | {win_rate} | "
            f"{row['strict_total_r_ambiguous_as_loss']:.3f} | {mean_r} | {brier} |"
        )
    best_by_horizon = {}
    for horizon in STAGE_PROFILES:
        horizon_rows = [row for row in payload["results"] if row["horizon"] == horizon]
        best_by_horizon[horizon] = max(
            horizon_rows,
            key=lambda row: row["strict_total_r_ambiguous_as_loss"],
        )
    lines.extend(["", "## Lectura operativa", ""])
    for horizon, row in best_by_horizon.items():
        ci = row["strict_mean_r_95pct"]
        lines.append(
            f"- `{horizon}`: mejor resultado descriptivo con {row['edge_threshold'] * 100:.0f} pp, "
            f"{row['trade_count']} operaciones y {row['strict_total_r_ambiguous_as_loss']:.3f} R; "
            f"IC 95% del R medio ({ci['low']:.3f}, {ci['high']:.3f})."
        )
    lines.extend(
        [
            "- Ningún umbral queda validado como rentable si su intervalo incluye cero; el ganador de esta ventana es una hipótesis para seguimiento, no un peso aprendido.",
            "- Los resultados por horizonte no autorizan un umbral universal: el filtro debe conservar identidad por participante/horizonte.",
        ]
    )
    lines.extend(
        [
            "",
            "## Límites de interpretación",
            "",
            "Esta es una prueba prospectiva histórica corta y exploratoria. Sirve para descartar umbrales inviables y "
            "detectar si las cuotas fuerzan entradas débiles; no basta por sí sola para declarar rentabilidad. Los casos "
            "en los que TP y SL aparecen dentro de la misma vela de 5 minutos se contabilizan como pérdida en el R estricto "
            "y como victoria únicamente en la cota optimista.",
            "",
        ]
    )
    return "\n".join(lines)


def run(*, smoke: bool = False) -> dict:
    artifact = load_production_artifact()
    latest_analog = max(float(row["analysis_epoch"]) for row in artifact["analogs"])
    latest_analog_at = datetime.fromtimestamp(latest_analog, tz=timezone.utc)
    replay_start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    if latest_analog_at + timedelta(days=7) > replay_start:
        raise RuntimeError("artifact_future_not_fully_mature_at_replay_start")
    runtime = FastFrozenAnalogRuntime(artifact)
    validation = validate_fast_runtime(runtime)
    if smoke:
        candidate_summaries = [
            generate_symbol_candidates(symbol, runtime, smoke=True)
            for symbol in SYMBOLS
        ]
    else:
        candidate_summaries = []
        with ProcessPoolExecutor(max_workers=len(SYMBOLS)) as pool:
            futures = {
                pool.submit(_generate_symbol_worker, symbol): symbol
                for symbol in SYMBOLS
            }
            for future in as_completed(futures):
                candidate_summaries.append(future.result())
        candidate_summaries.sort(key=lambda row: list(SYMBOLS).index(row["symbol"]))
    candidates = _load_candidates()
    results = [
        _simulate_threshold(candidates, horizon, threshold)
        for horizon in STAGE_PROFILES
        for threshold in THRESHOLDS
    ]
    evaluated_scans = len(candidates) // 2
    support_blocks = sum(
        summary["support_blocked_scan_count"] for summary in candidate_summaries
    )
    payload = {
        "version": REPLAY_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "smoke" if smoke else "complete",
        "window": {"start": START_DAY.isoformat(), "end": END_DAY.isoformat(), "timezone": "UTC"},
        "engine": {
            "version": ENGINE_VERSION,
            "artifact_id": artifact["artifact_id"],
            "artifact_sha256": artifact["artifact_sha256"],
            "artifact_path": str(ARTIFACT_PATH),
            "latest_analog_at": latest_analog_at.isoformat(),
            "full_seven_day_maturity_before_replay": True,
            "parallel_or_shadow_engines": 0,
        },
        "policy": {
            "symbols": list(SYMBOLS),
            "sides": ["long", "short"],
            "entry_type": "market",
            "thresholds": list(THRESHOLDS),
            "minimum_tp_probability": MIN_TP_PROBABILITY,
            "maximum_unresolved_probability": MAX_UNRESOLVED_PROBABILITY,
            "minimum_analogs_per_stage": MIN_ANALOGS_PER_STAGE,
            "profiles": POLICIES,
            "one_trade_maximum_per_scan": True,
            "duplicate_open_symbol_side_blocked": True,
        },
        "runtime_validation": validation,
        "candidate_summaries": candidate_summaries,
        "candidate_count": len(candidates),
        "candidate_errors": sum(sum(summary["errors"].values()) for summary in candidate_summaries),
        "evaluated_scan_context_count": evaluated_scans,
        "support_blocked_scan_count": support_blocks,
        "support_block_rate": (
            support_blocks / (evaluated_scans + support_blocks)
            if evaluated_scans + support_blocks
            else 0.0
        ),
        "unexpected_candidate_error_count": sum(
            summary["unexpected_error_count"] for summary in candidate_summaries
        ),
        "results": results,
        "writes": {"supabase": 0, "production": 0, "local_artifacts_only": True},
        "interpretation": {
            "status": "exploratory_threshold_screen",
            "not_a_profitability_claim": True,
            "costs_included": False,
            "ambiguous_primary_policy": "count_as_loss",
        },
    }
    payload["canonical_payload_sha256"] = _sha256_json(payload)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(_render_report(payload), encoding="utf-8")
    print(f"RESULT {OUTPUT_JSON}", flush=True)
    print(f"REPORT {OUTPUT_MD}", flush=True)
    return payload


def summarize_existing() -> dict:
    artifact = load_production_artifact()
    candidates = _load_candidates()
    prior = json.loads(OUTPUT_JSON.read_text(encoding="utf-8")) if OUTPUT_JSON.exists() else {}
    results = [
        _simulate_threshold(candidates, horizon, threshold)
        for horizon in STAGE_PROFILES
        for threshold in THRESHOLDS
    ]
    candidate_summaries = prior.get("candidate_summaries") or []
    for summary in candidate_summaries:
        errors = summary.get("errors") or {}
        summary["support_blocked_scan_count"] = sum(
            int(count)
            for code, count in errors.items()
            if code.startswith("ValueError:context_outside_historical_support")
        )
        summary["unexpected_error_count"] = sum(
            int(count)
            for code, count in errors.items()
            if not code.startswith("ValueError:context_outside_historical_support")
        )
    support_blocks = sum(
        int(summary.get("support_blocked_scan_count") or 0)
        for summary in candidate_summaries
    )
    unexpected_errors = sum(
        int(summary.get("unexpected_error_count") or 0)
        for summary in candidate_summaries
    )
    evaluated_scans = len(candidates) // 2
    payload = {
        **prior,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "engine": prior.get("engine")
        or {
            "version": ENGINE_VERSION,
            "artifact_id": artifact["artifact_id"],
            "artifact_sha256": artifact["artifact_sha256"],
        },
        "candidate_count": len(candidates),
        "candidate_summaries": candidate_summaries,
        "evaluated_scan_context_count": evaluated_scans,
        "support_blocked_scan_count": support_blocks,
        "support_block_rate": (
            support_blocks / (evaluated_scans + support_blocks)
            if evaluated_scans + support_blocks
            else 0.0
        ),
        "unexpected_candidate_error_count": unexpected_errors,
        "results": results,
    }
    payload.pop("canonical_payload_sha256", None)
    payload["canonical_payload_sha256"] = _sha256_json(payload)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    OUTPUT_MD.write_text(_render_report(payload), encoding="utf-8")
    print(f"RESULT {OUTPUT_JSON}", flush=True)
    print(f"REPORT {OUTPUT_MD}", flush=True)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    args = parser.parse_args()
    if args.summarize_only:
        summarize_existing()
        return
    if not args.skip_download:
        download_daily_archives()
    if not args.download_only:
        run(smoke=args.smoke)


if __name__ == "__main__":
    main()
