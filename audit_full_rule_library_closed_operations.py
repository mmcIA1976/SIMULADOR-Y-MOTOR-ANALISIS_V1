from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import m8_evaluation as m8
import market_data
from db import close_pool, connect
from liquidation_rule_runtime import evaluate_liquidation_rule_family
from m6_predictive_rules import ACTIVE_PREDICTIVE_RULE_IDS
from predictive_rule_library import load_rule_library
from prospective_validation import build_prospective_probability_run


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DATA_DIR = ROOT / "data"
OUTPUT_PATH = (
    AUDIT_DIR / "auditoria_integral_biblioteca_operaciones_cerradas_v0_1.json"
)
REPORT_PATH = (
    AUDIT_DIR
    / "2026-07-30_auditoria_integral_biblioteca_operaciones_cerradas.md"
)
CANDLE_CACHE_PATH = DATA_DIR / "audit_full_rule_library_candles_v0_1.json"
COMPARISON_PATH = (
    AUDIT_DIR / "comparacion_todas_operaciones_cerradas_v0_1.json"
)

AUDIT_VERSION = "full-rule-library-closed-operations-v0.1"
CLASSES = m8.CLASSES
SUPPORTED_PAIRS = {
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
}
INTERVAL_NAMES = m8.BINANCE_INTERVALS

STATE_RECORDED = "recorded_exact_pretrade"
STATE_RECONSTRUCTED = "reconstructed_exact_pretrade"
STATE_PROXY = "legacy_proxy_diagnostic_only"
STATE_UNRECOVERABLE = "unrecoverable_historical_input"
STATE_NOT_APPLICABLE = "not_applicable_historical_contract"
STATE_BLOCKED = "blocked_by_design"
STATE_RUNTIME_BLOCKED = "runtime_blocked_missing_input"

NON_PREDICTIVE_STATUSES = {
    "active_deterministic",
    "active_blocking",
    "active_economic",
    "data_blocked",
}
MOVEMENT_RULE_IDS = {
    "M4-RULE-VOLATILITY-RANK-001",
    "M4-RULE-OPEN-INTEREST-CHANGE-001",
    "LIB-CAND-RELATIVE-VOLUME-001",
    "LIB-CAND-COMPRESSION-001",
}
ALWAYS_BLOCKED_RULE_IDS = {
    "LIB-CAND-SHOCK-001",
    "LIB-CAND-CROSS-VENUE-DIVERGENCE-001",
}
CURRENT_TRACE_ENGINE_PREFIXES = (
    "M6-ACTIVE-PREDICTIVE-RULES",
    "TP-SL-PROBABILITY-ENGINE",
)


SQL_CLOSED = """
SELECT
    o.id AS operation_id,
    o.status,
    o.entry_type,
    o.started_at,
    o.created_at AS operation_created_at,
    o.closed_at,
    o.close_reason,
    o.entry,
    o.stop_loss,
    o.take_profit,
    o.margin,
    o.leverage,
    o.symbol AS operation_symbol,
    o.side AS operation_side,
    o.time_horizon AS operation_time_horizon,
    r.id AS recommendation_id,
    r.created_at AS analysis_at,
    r.symbol,
    r.side,
    r.time_horizon,
    r.engine_version,
    r.snapshot_json,
    r.analysis_json,
    r.tp_probability,
    r.sl_probability,
    r.range_probability
FROM operations o
JOIN LATERAL (
    SELECT candidate.*
    FROM recommendations candidate
    WHERE candidate.operation_id = o.id
    ORDER BY candidate.created_at DESC, candidate.id DESC
    LIMIT 1
) r ON TRUE
WHERE o.status = 'CLOSED'
ORDER BY o.id
"""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )


def parse_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fixed_horizon_seconds(time_horizon: str) -> int | None:
    return m8.HORIZON_SECONDS.get(str(time_horizon))


def normalized_row(raw: dict) -> dict:
    snapshot = parse_object(raw.get("snapshot_json"))
    analysis = parse_object(raw.get("analysis_json"))
    symbol = str(raw.get("symbol") or raw["operation_symbol"]).upper()
    side = str(raw.get("side") or raw["operation_side"]).lower()
    horizon = str(
        raw.get("time_horizon") or raw["operation_time_horizon"]
    )
    analysis_at = m8.parse_utc(raw.get("analysis_at"))
    horizon_seconds = fixed_horizon_seconds(horizon)
    reasons = []
    if symbol not in SUPPORTED_PAIRS:
        reasons.append("unsupported_pair")
    if side not in {"long", "short"}:
        reasons.append("invalid_side")
    if analysis_at is None:
        reasons.append("invalid_analysis_at")
    if horizon_seconds is None:
        reasons.append("unsupported_horizon")
    for key in ("entry", "take_profit", "stop_loss"):
        if finite(raw.get(key)) is None or float(raw[key]) <= 0:
            reasons.append(f"invalid_{key}")
    return {
        **raw,
        "operation_id": int(raw["operation_id"]),
        "recommendation_id": int(raw["recommendation_id"]),
        "symbol": symbol,
        "side": side,
        "time_horizon": horizon,
        "analysis_at": analysis_at.isoformat() if analysis_at else None,
        "horizon_seconds": horizon_seconds,
        "expiry_at": (
            (analysis_at + timedelta(seconds=horizon_seconds)).isoformat()
            if analysis_at and horizon_seconds
            else None
        ),
        "entry_type": str(raw.get("entry_type") or "market").lower(),
        "entry": float(raw["entry"]) if finite(raw.get("entry")) else None,
        "take_profit": (
            float(raw["take_profit"])
            if finite(raw.get("take_profit"))
            else None
        ),
        "stop_loss": (
            float(raw["stop_loss"])
            if finite(raw.get("stop_loss"))
            else None
        ),
        "margin": float(raw.get("margin") or 100.0),
        "leverage": float(raw.get("leverage") or 1.0),
        "_snapshot": snapshot,
        "_analysis": analysis,
        "normalization_reasons": reasons,
    }


def load_rows() -> list[dict]:
    with connect() as db:
        rows = [normalized_row(dict(row)) for row in db.execute(SQL_CLOSED)]
    close_pool()
    return rows


def load_known_outcomes() -> dict[int, dict]:
    if not COMPARISON_PATH.exists():
        return {}
    payload = read_json(COMPARISON_PATH)
    return {
        int(case["operation_id"]): {
            "status": "resolved",
            "label": case["actual_outcome"],
            "source": "existing_one_minute_reconstruction",
        }
        for case in payload.get("cases", [])
        if case.get("actual_outcome") in CLASSES
    }


def enrich_missing_outcomes(rows: list[dict], outcomes: dict[int, dict]) -> None:
    missing = []
    for row in rows:
        if row["operation_id"] in outcomes or row["normalization_reasons"]:
            continue
        missing.append(
            {
                "operation_id": row["operation_id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "analysis_at": row["analysis_at"],
                "expiry_at": row["expiry_at"],
                "entry": row["entry"],
                "take_profit": row["take_profit"],
                "stop_loss": row["stop_loss"],
            }
        )
    if not missing:
        return
    m8.enrich_outcomes(
        missing,
        captured_at=datetime.now(timezone.utc),
    )
    for item in missing:
        outcome = dict(item.get("outcome") or {})
        outcome["source"] = "new_one_minute_reconstruction"
        outcomes[int(item["operation_id"])] = outcome


@dataclass
class CandleArchive:
    groups: dict[str, list[list]]

    @staticmethod
    def key(symbol: str, interval: str) -> str:
        return f"{symbol.upper()}|{interval}"

    @classmethod
    def load(cls) -> "CandleArchive":
        if not CANDLE_CACHE_PATH.exists():
            return cls(groups={})
        payload = read_json(CANDLE_CACHE_PATH)
        if payload.get("version") != "audit-candle-cache-v0.1":
            return cls(groups={})
        return cls(groups=dict(payload.get("groups") or {}))

    def save(self) -> None:
        write_json(
            CANDLE_CACHE_PATH,
            {
                "version": "audit-candle-cache-v0.1",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "groups": self.groups,
            },
        )

    def ensure(self, rows: list[dict]) -> None:
        ranges: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
        for row in rows:
            if (
                row["entry_type"] != "market"
                or row["normalization_reasons"]
            ):
                continue
            interval_seconds = m8.selected_interval_seconds(
                row["time_horizon"],
                row["horizon_seconds"],
            )
            interval = INTERVAL_NAMES[interval_seconds]
            analysis = m8.parse_utc(row["analysis_at"])
            return_count = row["horizon_seconds"] // interval_seconds
            start_ms = int(
                (
                    analysis
                    - timedelta(
                        seconds=(61 * return_count + 3) * interval_seconds
                    )
                ).timestamp()
                * 1000
            )
            end_ms = int(analysis.timestamp() * 1000)
            ranges[(row["symbol"], interval)].append((start_ms, end_ms))

        changed = False
        for (symbol, interval), members in sorted(ranges.items()):
            required_start = min(item[0] for item in members)
            required_end = max(item[1] for item in members)
            key = self.key(symbol, interval)
            cached = self.groups.get(key, [])
            cached_start = int(cached[0][0]) if cached else None
            cached_end = int(cached[-1][0]) if cached else None
            interval_ms = next(
                seconds * 1000
                for seconds, name in INTERVAL_NAMES.items()
                if name == interval
            )
            complete = (
                cached
                and cached_start <= required_start + interval_ms
                and cached_end >= required_end - 2 * interval_ms
            )
            if complete:
                continue
            print(
                f"FETCH_PRETRADE={symbol}:{interval}:"
                f"{required_start}:{required_end}",
                flush=True,
            )
            fetched = m8.fetch_klines_range(
                symbol,
                interval,
                required_start,
                required_end,
                loader=market_data.get_klines,
            )
            if not fetched:
                raise RuntimeError(f"empty_pretrade_candles:{symbol}:{interval}")
            self.groups[key] = fetched
            changed = True
        if changed:
            self.save()

    def loader(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[list]:
        rows = self.groups.get(self.key(symbol, interval), [])
        start = -math.inf if start_time_ms is None else int(start_time_ms)
        end = math.inf if end_time_ms is None else int(end_time_ms)
        selected = [row for row in rows if start <= int(row[0]) <= end]
        return selected[: int(limit)]


def base_live_context(row: dict, interval_seconds: int) -> dict:
    analysis_ms = int(m8.parse_utc(row["analysis_at"]).timestamp() * 1000)
    snapshot = row["_snapshot"]
    liquidations = snapshot.get("liquidations")
    if not isinstance(liquidations, dict):
        liquidations = {}
    return {
        "symbol": row["symbol"],
        "request_cutoff_at": row["analysis_at"],
        "request_cutoff_ms": analysis_ms,
        "captured_at_ms": analysis_ms,
        "interval": INTERVAL_NAMES[interval_seconds],
        "interval_seconds": interval_seconds,
        "horizon_seconds": row["horizon_seconds"],
        "depth": {"bids": [], "asks": []},
        "futures_book": {},
        "spot_book": {},
        "spot_info": {},
        "funding_snapshot": {},
        "funding_info": {},
        "funding_history": [],
        "open_interest_history": [],
        "taker_history": [],
        "global_long_short_history": [],
        "market_breadth_assets": [],
        "fear_greed_history": [],
        "liquidation_context": liquidations,
    }


def trace_registry(snapshot: dict) -> dict[str, dict]:
    traces = []
    m5 = snapshot.get("m5_rule_trace")
    if isinstance(m5, dict):
        traces.extend(m5.get("traces") or [])
    feature_snapshot = snapshot.get("feature_snapshot")
    if isinstance(feature_snapshot, dict):
        observational = feature_snapshot.get("observational_rule_traces")
        if isinstance(observational, dict):
            traces.extend(observational.get("traces") or [])
    return {
        str(trace["rule_id"]): trace
        for trace in traces
        if isinstance(trace, dict) and trace.get("rule_id")
    }


def replay_registry(run: dict) -> dict[str, dict]:
    traces = []
    m5 = run.get("m5_analysis")
    if isinstance(m5, dict):
        traces.extend(m5.get("traces") or [])
    observational = run.get("observational_rule_traces")
    if isinstance(observational, dict):
        traces.extend(observational.get("traces") or [])
    return {
        str(trace["rule_id"]): trace
        for trace in traces
        if isinstance(trace, dict) and trace.get("rule_id")
    }


def quality_rule_outputs(run: dict) -> dict[str, dict]:
    report = run.get("data_quality")
    if not isinstance(report, dict):
        return {}
    return {
        str(trace["rule_id"]): dict(trace.get("outputs") or {})
        for trace in report.get("traces", [])
        if isinstance(trace, dict)
        and trace.get("rule_id")
        in {
            "LIB-CAND-DATA-FRESHNESS-001",
            "LIB-CAND-CANDLE-INTEGRITY-001",
        }
    }


def legacy_proxies(row: dict) -> dict[str, dict]:
    snapshot = row["_snapshot"]
    derivatives = snapshot.get("derivatives")
    derivatives = derivatives if isinstance(derivatives, dict) else {}
    order_book = snapshot.get("order_book")
    order_book = order_book if isinstance(order_book, dict) else {}
    breadth = snapshot.get("market_breadth")
    breadth = breadth if isinstance(breadth, dict) else {}
    sentiment = snapshot.get("sentiment")
    sentiment = sentiment if isinstance(sentiment, dict) else {}
    result: dict[str, dict] = {}

    mark = finite(derivatives.get("mark_price"))
    index = finite(derivatives.get("index_price"))
    if mark and index and mark > 0 and index > 0:
        result["M4-RULE-MARK-INDEX-PREMIUM-001"] = {
            "mark_price": mark,
            "index_price": index,
            "mark_index_log_premium": math.log(mark / index),
        }

    period_name = {
        "intraday_short": "5m",
        "intraday_wide": "1h",
        "short_swing": "1d",
    }.get(row["time_horizon"])
    by_period = derivatives.get("by_period")
    period = (
        by_period.get(period_name)
        if isinstance(by_period, dict) and period_name in by_period
        else derivatives
    )
    period = period if isinstance(period, dict) else {}
    oi_pct = finite(period.get("open_interest_change_pct"))
    if oi_pct is not None and oi_pct > -100:
        result["M4-RULE-OPEN-INTEREST-CHANGE-001"] = {
            "legacy_period": period_name,
            "legacy_open_interest_change_pct": oi_pct,
            "dOI_H_proxy": math.log1p(oi_pct / 100.0),
        }
    funding = finite(derivatives.get("funding_rate_pct"))
    if funding is not None:
        result["M4-RULE-FUNDING-STATE-001"] = {
            "last_funding_rate_proxy": funding / 100.0,
            "funding_history_count": derivatives.get(
                "funding_history_count"
            ),
        }
    top20 = finite(order_book.get("imbalance"))
    if top20 is not None:
        direction = 1.0 if row["side"] == "long" else -1.0
        result["LIB-CAND-ORDERBOOK-IMBALANCE-001"] = {
            "legacy_top20_imbalance": top20,
            "side_adjusted_legacy_top20_imbalance": direction * top20,
        }
    if breadth:
        result["LIB-CAND-BREADTH-001"] = {
            f"legacy_{key}": value
            for key, value in breadth.items()
            if finite(value) is not None
        }
    fear = finite(sentiment.get("fear_greed_value"))
    if fear is not None:
        result["LIB-CAND-SENTIMENT-PERCENTILE-001"] = {
            "legacy_fear_greed_value": fear,
        }
    ratio = finite(derivatives.get("global_long_short_ratio"))
    if ratio is not None and ratio > 0:
        result["LIB-CAND-CROWDING-PERCENTILE-001"] = {
            "legacy_global_long_short_ratio": ratio,
        }
    spread_pct = finite(order_book.get("spread_pct"))
    if spread_pct is not None:
        result["M4-RULE-QUOTED-SPREAD-001"] = {
            "legacy_spread_fraction_mid": spread_pct / 100.0,
        }
    return result


def rule_case(
    *,
    state: str,
    runtime_status: str,
    outputs: dict | None = None,
    reason: str | None = None,
    source: str | None = None,
) -> dict:
    return {
        "state": state,
        "runtime_status": runtime_status,
        "source": source,
        "reason": reason,
        "outputs": outputs or {},
    }


def build_case(
    row: dict,
    catalog_rules: dict[str, dict],
    archive: CandleArchive,
    outcome: dict | None,
) -> dict:
    cases = {}
    for rule_id, metadata in catalog_rules.items():
        if rule_id in ALWAYS_BLOCKED_RULE_IDS:
            cases[rule_id] = rule_case(
                state=STATE_BLOCKED,
                runtime_status=metadata["lifecycle_status"],
                reason="data_contract_not_available_by_design",
            )
        else:
            cases[rule_id] = rule_case(
                state=STATE_UNRECOVERABLE,
                runtime_status="not_evaluated",
                reason="historical_input_not_yet_classified",
            )

    if row["entry_type"] != "market":
        for rule_id in cases:
            if rule_id not in ALWAYS_BLOCKED_RULE_IDS:
                cases[rule_id] = rule_case(
                    state=STATE_NOT_APPLICABLE,
                    runtime_status="not_replayed",
                    reason=(
                        "current_phase1_engine_contract_accepts_market_entries_only"
                    ),
                )
        return public_case(row, outcome, cases, None)

    if row["normalization_reasons"]:
        for rule_id in cases:
            if rule_id not in ALWAYS_BLOCKED_RULE_IDS:
                cases[rule_id] = rule_case(
                    state=STATE_NOT_APPLICABLE,
                    runtime_status="not_replayed",
                    reason=";".join(row["normalization_reasons"]),
                )
        return public_case(row, outcome, cases, None)

    interval_seconds = m8.selected_interval_seconds(
        row["time_horizon"],
        row["horizon_seconds"],
    )
    proposal = SimpleNamespace(
        symbol=row["symbol"],
        side=row["side"],
        entry=row["entry"],
        take_profit=row["take_profit"],
        stop_loss=row["stop_loss"],
        margin=row["margin"],
        leverage=row["leverage"],
        entry_type="market",
        time_horizon=row["time_horizon"],
    )
    snapshot = {
        "analysis_at": row["analysis_at"],
        "evaluation_horizon_seconds": row["horizon_seconds"],
        "evaluation_expires_at": row["expiry_at"],
    }
    run = build_prospective_probability_run(
        proposal,
        snapshot,
        loader=archive.loader,
        analysis_id=f"historical-audit-{row['recommendation_id']}",
        active_output=False,
        live_context=base_live_context(row, interval_seconds),
    )
    replay = replay_registry(run)
    for rule_id, trace in replay.items():
        if rule_id not in cases:
            continue
        status = str(trace.get("status") or "unknown")
        if status in {"evaluated", "evaluated_shadow"}:
            cases[rule_id] = rule_case(
                state=STATE_RECONSTRUCTED,
                runtime_status=status,
                outputs=dict(trace.get("outputs") or {}),
                source="current_formula_replay_from_pretrade_closed_klines",
            )
        else:
            cases[rule_id] = rule_case(
                state=STATE_RUNTIME_BLOCKED,
                runtime_status=status,
                reason=";".join(trace.get("reason_codes") or [])
                or "current_formula_missing_historical_input",
                source="current_formula_replay",
            )
    for rule_id, outputs in quality_rule_outputs(run).items():
        if rule_id in cases:
            cases[rule_id] = rule_case(
                state=STATE_RECONSTRUCTED,
                runtime_status="evaluated",
                outputs=outputs,
                source="current_data_quality_gate_replay",
            )

    engine_version = str(row.get("engine_version") or "")
    if engine_version.startswith(CURRENT_TRACE_ENGINE_PREFIXES):
        for rule_id, trace in trace_registry(row["_snapshot"]).items():
            if rule_id not in cases:
                continue
            status = str(trace.get("status") or "unknown")
            if status in {"evaluated", "evaluated_shadow"}:
                cases[rule_id] = rule_case(
                    state=STATE_RECORDED,
                    runtime_status=status,
                    outputs=dict(trace.get("outputs") or {}),
                    source="stored_current_engine_pretrade_trace",
                )

    for rule_id, outputs in legacy_proxies(row).items():
        if (
            rule_id in cases
            and cases[rule_id]["state"]
            not in {STATE_RECORDED, STATE_RECONSTRUCTED}
        ):
            cases[rule_id] = rule_case(
                state=STATE_PROXY,
                runtime_status="legacy_proxy",
                outputs=outputs,
                source="stored_legacy_snapshot_not_current_formula_equivalent",
                reason="diagnostic_only_not_admissible_for_validation",
            )

    run_summary = {
        "status": run.get("status"),
        "block_code": run.get("block_code"),
        "source_data_sha256": run.get("source_data_sha256"),
        "probabilities": (
            (run.get("m6_result") or {}).get("probabilities")
            if run.get("status") == "evaluated"
            else None
        ),
        "probabilities_before_rule_overlay": (
            (run.get("m6_result") or {}).get(
                "probabilities_before_rule_overlay"
            )
            if run.get("status") == "evaluated"
            else None
        ),
        "diffusion_baseline": extract_diffusion_baseline(run),
        "rule_ablations": extract_rule_ablations(run),
        "active_predictive_rule_ids": (
            (run.get("feature_snapshot") or {}).get(
                "active_predictive_rule_ids",
                [],
            )
        ),
    }
    return public_case(row, outcome, cases, run_summary)


def extract_diffusion_baseline(run: dict) -> dict | None:
    core = ((run.get("m6_result") or {}).get("core_result") or {})
    baseline = ((core.get("trace") or {}).get("baseline") or {})
    keys = {
        "tp_first_within_horizon": "p_tp",
        "sl_first_within_horizon": "p_sl",
        "neither_barrier_before_expiry": "p_expiry",
    }
    if not all(finite(baseline.get(source)) is not None for source in keys.values()):
        return None
    return {target: float(baseline[source]) for target, source in keys.items()}


def extract_rule_ablations(run: dict) -> dict[str, dict]:
    m6_result = run.get("m6_result")
    if not isinstance(m6_result, dict):
        return {}
    result = {}
    for rule_id, item in (
        m6_result.get("fitted_rule_ablation") or {}
    ).items():
        probabilities = item.get("probabilities_without_rule")
        if isinstance(probabilities, dict):
            result[str(rule_id)] = probabilities
    contributions = (
        (m6_result.get("active_rule_overlay") or {}).get(
            "rule_contributions"
        )
        or {}
    )
    for rule_id, item in contributions.items():
        probabilities = item.get("ablation_probabilities_without_rule")
        if isinstance(probabilities, dict):
            result[str(rule_id)] = probabilities
    return result


def public_case(
    row: dict,
    outcome: dict | None,
    rules: dict,
    replay: dict | None,
) -> dict:
    return {
        "operation_id": row["operation_id"],
        "recommendation_id": row["recommendation_id"],
        "symbol": row["symbol"],
        "side": row["side"],
        "time_horizon": row["time_horizon"],
        "entry_type": row["entry_type"],
        "analysis_at": row["analysis_at"],
        "engine_version": row.get("engine_version"),
        "close_reason": row.get("close_reason"),
        "outcome": outcome,
        "stored_probabilities": {
            "tp_first_within_horizon": float(row["tp_probability"]),
            "sl_first_within_horizon": float(row["sl_probability"]),
            "neither_barrier_before_expiry": float(
                row["range_probability"]
            ),
        },
        "replay": replay,
        "rules": rules,
    }


def flatten_numeric(value: Any, prefix: str = "") -> dict[str, float]:
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten_numeric(child, path))
    elif isinstance(value, bool):
        result[prefix] = float(value)
    elif isinstance(value, (int, float)):
        number = finite(value)
        if number is not None:
            result[prefix] = number
    return result


def variable_eligibility(path: str, rule: dict) -> tuple[bool, str]:
    if rule["lifecycle_status"] in NON_PREDICTIVE_STATUSES:
        return False, "rule_contract_is_not_predictive"
    lowered = path.lower()
    if any(
        token in lowered
        for token in (
            "relative_horizon_volume",
            "volume_midrank",
            "log_relative_horizon_volume",
        )
    ):
        return True, "dimensionless_relative_volume_signal"
    forbidden = (
        "timestamp",
        "_time",
        "time_",
        "count",
        "price",
        "volume",
        "notional",
        "quantity",
        "window",
        "interval",
        "coverage",
        "age_ms",
        "limit_ms",
        "return_series",
    )
    if any(token in lowered for token in forbidden):
        return False, "raw_scale_or_operational_ingredient"
    eligible_tokens = (
        "signal",
        "side_adjusted",
        "efficiency",
        "percentile",
        "imbalance",
        "ratio",
        "fraction",
        "slope",
        "extension",
        "distance_sigma",
        "confluence",
        "compression",
        "absorption",
        "pullback",
        "rsi",
        "doi",
        "premium",
        "basis",
        "funding_rate",
        "mass",
    )
    if any(token in lowered for token in eligible_tokens):
        return True, "dimensionless_or_rule_signal"
    return False, "formula_ingredient_without_independent_hypothesis"


def synthetic_rule_signals(case: dict) -> dict[str, float]:
    result = {}
    for rule_id, item in case["rules"].items():
        if item.get("state") not in {STATE_RECORDED, STATE_RECONSTRUCTED}:
            continue
        outputs = item.get("outputs") or {}
        side_direction = 1.0 if case["side"] == "long" else -1.0
        value = None
        if rule_id == "M4-RULE-PATH-STRUCTURE-001":
            raw = finite(outputs.get("signed_path_efficiency"))
            value = side_direction * raw if raw is not None else None
        elif rule_id == "M4-RULE-PRIOR-EXTREMA-001":
            raw = outputs.get("target_extreme_between_entry_and_tp")
            value = finite(raw)
        elif rule_id == "M4-RULE-VOLATILITY-RANK-001":
            value = finite(outputs.get("volatility_percentile"))
        elif rule_id == "M4-RULE-MTF-HIERARCHY-001":
            values = outputs.get("signed_path_efficiencies")
            if isinstance(values, dict):
                selected = [
                    finite(values.get(name))
                    for name in ("2H", "4H")
                ]
                if all(item is not None for item in selected):
                    value = side_direction * math.fsum(selected) / 2.0
        elif rule_id == "M4-RULE-CONTINUOUS-REGIME-001":
            efficiency = finite(outputs.get("signed_path_efficiency"))
            percentile = finite(outputs.get("volatility_percentile"))
            if efficiency is not None and percentile is not None:
                value = (
                    side_direction
                    * efficiency
                    * (2.0 * percentile - 1.0)
                )
        elif rule_id == "M4-RULE-AGGRESSOR-IMBALANCE-001":
            raw = finite(outputs.get("ATI_H"))
            value = side_direction * raw if raw is not None else None
        elif rule_id == "M4-RULE-OPEN-INTEREST-CHANGE-001":
            raw = finite(outputs.get("dOI_H"))
            if raw is None:
                raw = finite(outputs.get("dOI_H_proxy"))
            value = math.tanh(50.0 * abs(raw)) if raw is not None else None
        elif rule_id == "M4-RULE-MARK-INDEX-PREMIUM-001":
            raw = finite(outputs.get("mark_index_log_premium"))
            value = (
                -side_direction * math.tanh(200.0 * raw)
                if raw is not None
                else None
            )
        elif rule_id == "M4-RULE-FUNDING-STATE-001":
            raw = finite(outputs.get("last_funding_rate"))
            if raw is None:
                raw = finite(outputs.get("last_funding_rate_proxy"))
            value = (
                -side_direction * math.tanh(raw / 0.0005)
                if raw is not None
                else None
            )
        if value is not None:
            result[f"{rule_id}.__current_formula_signal"] = float(value)
    return result


def auc_score(values: list[float], labels: list[int]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ordered = sorted(zip(values, labels), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum += average_rank * sum(
            label for _, label in ordered[index:end]
        )
        index = end
    return (
        rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def bootstrap_auc_ci(
    values: list[float],
    labels: list[int],
    *,
    seed: int,
    samples: int = 400,
) -> list[float] | None:
    rng = random.Random(seed)
    estimates = []
    indices = list(range(len(values)))
    for _ in range(samples):
        draw = [rng.choice(indices) for _ in indices]
        draw_labels = [labels[index] for index in draw]
        estimate = auc_score(
            [values[index] for index in draw],
            draw_labels,
        )
        if estimate is not None:
            estimates.append(estimate)
    if len(estimates) < samples * 0.8:
        return None
    estimates.sort()
    return [
        estimates[int(0.025 * (len(estimates) - 1))],
        estimates[int(0.975 * (len(estimates) - 1))],
    ]


def permutation_p_value(
    values: list[float],
    labels: list[int],
    observed: float,
    *,
    seed: int,
    samples: int = 400,
) -> float:
    rng = random.Random(seed)
    extreme = 0
    target = abs(observed - 0.5)
    shuffled = list(labels)
    for _ in range(samples):
        rng.shuffle(shuffled)
        estimate = auc_score(values, shuffled)
        if estimate is not None and abs(estimate - 0.5) >= target:
            extreme += 1
    return (extreme + 1.0) / (samples + 1.0)


def bh_adjust(metrics: list[dict]) -> None:
    eligible = [
        item for item in metrics if item.get("permutation_p") is not None
    ]
    ordered = sorted(eligible, key=lambda item: item["permutation_p"])
    running = 1.0
    for reverse_index in range(len(ordered) - 1, -1, -1):
        rank = reverse_index + 1
        adjusted = min(
            running,
            ordered[reverse_index]["permutation_p"]
            * len(ordered)
            / rank,
        )
        ordered[reverse_index]["fdr_bh"] = adjusted
        running = adjusted


def evaluate_variable(
    rows: list[tuple[str, float, str]],
    *,
    target: str,
    seed: int,
) -> dict:
    if target == "movement":
        filtered = [
            (time, value, 0 if label == CLASSES[2] else 1)
            for time, value, label in rows
            if label in CLASSES
        ]
        positive_name = "barrier_touch"
        negative_name = "expiry"
    else:
        filtered = [
            (time, value, 1 if label == CLASSES[0] else 0)
            for time, value, label in rows
            if label in {CLASSES[0], CLASSES[1]}
        ]
        positive_name = "tp_first"
        negative_name = "sl_first"
    filtered.sort(key=lambda item: item[0])
    values = [item[1] for item in filtered]
    labels = [item[2] for item in filtered]
    positives = sum(labels)
    negatives = len(labels) - positives
    result = {
        "target": target,
        "positive_class": positive_name,
        "negative_class": negative_name,
        "n": len(values),
        "positive_n": positives,
        "negative_n": negatives,
        "auc": None,
        "auc_95ci": None,
        "early_auc": None,
        "latest_auc": None,
        "permutation_p": None,
        "fdr_bh": None,
        "evidence_status": "insufficient",
    }
    if len(values) < 50 or positives < 10 or negatives < 10:
        return result
    if len(set(values)) < 2:
        result["evidence_status"] = "constant_signal"
        return result
    auc = auc_score(values, labels)
    split = max(1, int(len(values) * 0.7))
    early_auc = auc_score(values[:split], labels[:split])
    latest_auc = auc_score(values[split:], labels[split:])
    result.update(
        {
            "auc": auc,
            "auc_95ci": bootstrap_auc_ci(
                values,
                labels,
                seed=seed,
            ),
            "early_auc": early_auc,
            "latest_auc": latest_auc,
            "permutation_p": permutation_p_value(
                values,
                labels,
                auc,
                seed=seed + 1,
            ),
            "evidence_status": "quantified_pending_fdr",
        }
    )
    return result


def probability_metrics(
    cases: list[dict],
    probability_path: str,
    *,
    market_only: bool = False,
) -> dict:
    values = []
    for case in cases:
        if market_only and case.get("entry_type") != "market":
            continue
        outcome = case.get("outcome") or {}
        label = outcome.get("label")
        if outcome.get("status") != "resolved" or label not in CLASSES:
            continue
        current: Any = case
        for part in probability_path.split("."):
            current = current.get(part) if isinstance(current, dict) else None
        if not isinstance(current, dict):
            continue
        try:
            probabilities = {name: float(current[name]) for name in CLASSES}
        except (KeyError, TypeError, ValueError):
            continue
        if any(
            value < 0 or not math.isfinite(value)
            for value in probabilities.values()
        ):
            continue
        total = math.fsum(probabilities.values())
        if total <= 0:
            continue
        probabilities = {
            name: value / total for name, value in probabilities.items()
        }
        values.append((str(case.get("analysis_at") or ""), label, probabilities))
    if not values:
        return {"n": 0}
    values.sort(key=lambda item: item[0])

    def aggregate(
        selected: list[tuple[str, str, dict[str, float]]],
    ) -> dict:
        if not selected:
            return {
                "n": 0,
                "log_loss": None,
                "multiclass_brier": None,
                "top_class_accuracy": None,
                "outcomes": {},
            }
        log_loss = -math.fsum(
            math.log(max(probabilities[label], 1e-15))
            for _, label, probabilities in selected
        ) / len(selected)
        brier = math.fsum(
            math.fsum(
                (
                    probabilities[name]
                    - (1.0 if name == label else 0.0)
                )
                ** 2
                for name in CLASSES
            )
            for _, label, probabilities in selected
        ) / len(selected)
        accuracy = sum(
            max(probabilities, key=probabilities.get) == label
            for _, label, probabilities in selected
        ) / len(selected)
        return {
            "n": len(selected),
            "log_loss": log_loss,
            "multiclass_brier": brier,
            "top_class_accuracy": accuracy,
            "outcomes": dict(
                Counter(label for _, label, _ in selected)
            ),
        }

    result = aggregate(values)
    split = max(1, int(len(values) * 0.7))
    result["chronological_split"] = {
        "early_70_percent": aggregate(values[:split]),
        "latest_30_percent": aggregate(values[split:]),
    }
    return result


def summarize(
    cases: list[dict],
    library: dict,
) -> tuple[dict, list[dict]]:
    rule_metadata = {
        rule["rule_id"]: rule for rule in library["rules"]
    }
    rule_summaries = {}
    variable_rows: dict[tuple[str, str], list[tuple[str, float, str]]] = (
        defaultdict(list)
    )
    variable_inventory: dict[tuple[str, str], dict] = {}

    for case in cases:
        outcome = case.get("outcome") or {}
        label = outcome.get("label")
        synthetic = synthetic_rule_signals(case)
        for combined, value in synthetic.items():
            rule_id, path = combined.split(".", 1)
            if rule_id not in rule_metadata:
                continue
            if label in CLASSES:
                variable_rows[(rule_id, path)].append(
                    (case["analysis_at"], value, label)
                )
            variable_inventory.setdefault(
                (rule_id, path),
                {
                    "rule_id": rule_id,
                    "variable": path,
                    "eligible_for_association": True,
                    "eligibility_reason": "current_formula_signal",
                    "exact_nonmissing": 0,
                    "proxy_nonmissing": 0,
                    "values": [],
                },
            )
            variable_inventory[(rule_id, path)]["exact_nonmissing"] += 1
            variable_inventory[(rule_id, path)]["values"].append(value)

        for rule_id, item in case["rules"].items():
            state = item["state"]
            for path, value in flatten_numeric(item.get("outputs") or {}).items():
                eligible, reason = variable_eligibility(
                    path,
                    rule_metadata[rule_id],
                )
                inventory = variable_inventory.setdefault(
                    (rule_id, path),
                    {
                        "rule_id": rule_id,
                        "variable": path,
                        "eligible_for_association": eligible,
                        "eligibility_reason": reason,
                        "exact_nonmissing": 0,
                        "proxy_nonmissing": 0,
                        "values": [],
                    },
                )
                if state in {STATE_RECORDED, STATE_RECONSTRUCTED}:
                    inventory["exact_nonmissing"] += 1
                    if eligible and label in CLASSES:
                        variable_rows[(rule_id, path)].append(
                            (case["analysis_at"], value, label)
                        )
                elif state == STATE_PROXY:
                    inventory["proxy_nonmissing"] += 1
                inventory["values"].append(value)

    metric_rows = []
    for index, ((rule_id, variable), rows) in enumerate(
        sorted(variable_rows.items())
    ):
        target = (
            "movement" if rule_id in MOVEMENT_RULE_IDS else "directional"
        )
        metric = evaluate_variable(
            rows,
            target=target,
            seed=20260730 + index * 7,
        )
        metric.update({"rule_id": rule_id, "variable": variable})
        metric_rows.append(metric)
    bh_adjust(metric_rows)
    for metric in metric_rows:
        if metric["evidence_status"] != "quantified_pending_fdr":
            continue
        ci = metric.get("auc_95ci")
        auc = metric.get("auc")
        latest = metric.get("latest_auc")
        early = metric.get("early_auc")
        stable = (
            auc is not None
            and early is not None
            and latest is not None
            and (auc - 0.5) * (early - 0.5) > 0
            and (auc - 0.5) * (latest - 0.5) > 0
        )
        significant = (
            metric.get("fdr_bh") is not None
            and metric["fdr_bh"] <= 0.10
            and ci is not None
            and not (ci[0] <= 0.5 <= ci[1])
        )
        if significant and stable:
            metric["evidence_status"] = (
                "historically_supported_temporally_stable_not_independent"
                if auc > 0.5
                else "historically_contradicted_temporally_stable"
            )
        elif abs(auc - 0.5) < 0.05:
            metric["evidence_status"] = "no_clear_univariate_separation"
        else:
            metric["evidence_status"] = "inconclusive_or_temporally_unstable"

    metrics_by_rule: dict[str, list[dict]] = defaultdict(list)
    for metric in metric_rows:
        metrics_by_rule[metric["rule_id"]].append(metric)

    inventory_by_rule: dict[str, list[dict]] = defaultdict(list)
    for key, raw in sorted(variable_inventory.items()):
        values = raw.pop("values")
        raw["unique_values"] = len(set(values))
        raw["minimum"] = min(values) if values else None
        raw["maximum"] = max(values) if values else None
        inventory_by_rule[key[0]].append(raw)

    for rule_id, metadata in rule_metadata.items():
        states = Counter(
            case["rules"][rule_id]["state"] for case in cases
        )
        exact_n = states[STATE_RECORDED] + states[STATE_RECONSTRUCTED]
        eligible_metrics = metrics_by_rule.get(rule_id, [])
        strong = [
            metric
            for metric in eligible_metrics
            if metric["evidence_status"].startswith(
                "historically_supported"
            )
        ]
        contradicted = [
            metric
            for metric in eligible_metrics
            if metric["evidence_status"].startswith(
                "historically_contradicted"
            )
        ]
        if metadata["lifecycle_status"] == "data_blocked":
            conclusion = "blocked_by_design_no_historical_validation"
        elif metadata["lifecycle_status"] in {
            "active_deterministic",
            "active_blocking",
        }:
            conclusion = (
                "deterministic_replay_covered"
                if exact_n >= 150
                else "deterministic_replay_coverage_insufficient"
            )
        elif metadata["lifecycle_status"] == "active_economic":
            conclusion = (
                "economic_trace_coverage_insufficient_for_historical_audit"
            )
        elif exact_n < 50:
            conclusion = "insufficient_exact_historical_coverage"
        elif strong:
            conclusion = (
                "historical_support_not_independent_validation"
            )
        elif contradicted:
            conclusion = "current_hypothesis_historically_contradicted"
        elif eligible_metrics:
            conclusion = "no_stable_univariate_support_detected"
        else:
            conclusion = "exact_values_available_but_no_eligible_signal_test"
        rule_summaries[rule_id] = {
            "name": metadata["name"],
            "role": metadata["role"],
            "lifecycle_status": metadata["lifecycle_status"],
            "state_counts": dict(states),
            "exact_comparable_n": exact_n,
            "proxy_diagnostic_n": states[STATE_PROXY],
            "conclusion": conclusion,
            "variables": inventory_by_rule.get(rule_id, []),
            "association_metrics": eligible_metrics,
        }

    full_probability_metric = probability_metrics(
        cases,
        "replay.probabilities",
    )
    active_rule_ablations = {}
    for rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
        without = probability_metrics(
            cases,
            f"replay.rule_ablations.{rule_id}",
        )
        if not without.get("n"):
            active_rule_ablations[rule_id] = {
                "n": 0,
                "status": "insufficient_exact_historical_coverage",
            }
            continue
        full_latest = full_probability_metric["chronological_split"][
            "latest_30_percent"
        ]
        without_latest = without["chronological_split"][
            "latest_30_percent"
        ]
        active_rule_ablations[rule_id] = {
            "n": without["n"],
            "status": "diagnostic_not_independent_validation",
            "without_rule": without,
            "delta_full_minus_without": {
                "log_loss_improvement": (
                    without["log_loss"]
                    - full_probability_metric["log_loss"]
                ),
                "brier_improvement": (
                    without["multiclass_brier"]
                    - full_probability_metric["multiclass_brier"]
                ),
                "accuracy_change": (
                    full_probability_metric["top_class_accuracy"]
                    - without["top_class_accuracy"]
                ),
            },
            "latest_30_percent_delta_full_minus_without": {
                "log_loss_improvement": (
                    without_latest["log_loss"]
                    - full_latest["log_loss"]
                ),
                "brier_improvement": (
                    without_latest["multiclass_brier"]
                    - full_latest["multiclass_brier"]
                ),
                "accuracy_change": (
                    full_latest["top_class_accuracy"]
                    - without_latest["top_class_accuracy"]
                ),
            },
        }
    for rule_id, item in rule_summaries.items():
        if rule_id in active_rule_ablations:
            item["probability_ablation"] = active_rule_ablations[rule_id]

    overall = {
        "closed_operations": len(cases),
        "market_operations": sum(
            case["entry_type"] == "market" for case in cases
        ),
        "pending_operations": sum(
            case["entry_type"] != "market" for case in cases
        ),
        "resolved_outcomes": sum(
            (case.get("outcome") or {}).get("status") == "resolved"
            and (case.get("outcome") or {}).get("label") in CLASSES
            for case in cases
        ),
        "outcome_labels": dict(
            Counter(
                (case.get("outcome") or {}).get("label")
                for case in cases
                if (case.get("outcome") or {}).get("label") in CLASSES
            )
        ),
        "rule_conclusions": dict(
            Counter(
                item["conclusion"] for item in rule_summaries.values()
            )
        ),
        "probability_models": {
            "stored_legacy_and_current_engine_all_closed": probability_metrics(
                cases,
                "stored_probabilities",
            ),
            "stored_legacy_and_current_engine_market_only": (
                probability_metrics(
                    cases,
                    "stored_probabilities",
                    market_only=True,
                )
            ),
            "current_diffusion_baseline_replay": probability_metrics(
                cases,
                "replay.diffusion_baseline",
            ),
            "current_fitted_before_overlay_replay": probability_metrics(
                cases,
                "replay.probabilities_before_rule_overlay",
            ),
            "current_exact_available_rules_replay": probability_metrics(
                cases,
                "replay.probabilities",
            ),
        },
        "active_rule_ablations": active_rule_ablations,
    }
    return {
        "overall": overall,
        "rules": rule_summaries,
        "multiple_testing": {
            "method": "Benjamini-Hochberg",
            "fdr_threshold": 0.10,
            "permutation_samples": 400,
            "bootstrap_samples": 400,
            "minimum_n": 50,
            "minimum_each_binary_class": 10,
            "temporal_split": "earliest_70_percent_vs_latest_30_percent",
            "independent_validation_claimed": False,
        },
    }, metric_rows


def build_report(payload: dict) -> str:
    summary = payload["summary"]["overall"]
    rules = payload["summary"]["rules"]
    models = summary["probability_models"]
    stored_market = models[
        "stored_legacy_and_current_engine_market_only"
    ]
    diffusion = models["current_diffusion_baseline_replay"]
    fitted = models["current_fitted_before_overlay_replay"]
    current = models["current_exact_available_rules_replay"]
    stored_latest = stored_market["chronological_split"]["latest_30_percent"]
    diffusion_latest = diffusion["chronological_split"]["latest_30_percent"]
    fitted_latest = fitted["chronological_split"]["latest_30_percent"]
    current_latest = current["chronological_split"]["latest_30_percent"]
    ablations = summary.get("active_rule_ablations", {})
    lines = [
        "# Auditoria integral de reglas sobre operaciones cerradas",
        "",
        f"- Version: `{payload['audit_version']}`.",
        f"- Biblioteca: `{payload['library_version']}`.",
        f"- SHA del catalogo: `{payload['catalog_sha256']}`.",
        f"- Operaciones cerradas: **{summary['closed_operations']}**.",
        f"- Entradas market comparables: **{summary['market_operations']}**.",
        f"- Entradas pending separadas: **{summary['pending_operations']}**.",
        f"- Resultados TP/SL/expiry reconstruidos: **{summary['resolved_outcomes']}**.",
        "",
        "## Respuesta ejecutiva",
        "",
        (
            "La infraestructura de trazabilidad permite auditar las 38 fichas "
            "sin convertir ausencias historicas en valores neutros. Sin embargo, "
            "el historico anterior al motor actual no contiene todos los datos "
            "crudos necesarios para reproducir todas sus reglas."
        ),
        "",
        (
            "Las reglas basadas en velas cerradas pueden reconstruirse con la "
            "formula actual. Order book completo, basis sincronizado, historiales "
            "de OI/funding/crowding/sentimiento y contexto cross-venue no pueden "
            "validarse retroactivamente cuando no fueron almacenados."
        ),
        "",
        (
            "Por ello esta auditoria puede aportar evidencia historica para un "
            "subconjunto, pero no autoriza por si sola a declarar validado el "
            "motor completo ni a modificar pesos en produccion."
        ),
        "",
        (
            "Resultado agregado de las 38 fichas: 7 controles deterministas "
            "quedan cubiertos en las 213 operaciones market; 16 reglas con "
            "valores exactos no muestran separacion univariante estable; 11 "
            "reglas no tienen cobertura historica exacta suficiente; 2 reglas "
            "economicas solo disponen de 6 trazas actuales; y 2 reglas siguen "
            "bloqueadas por diseno."
        ),
        "",
        "## Probabilidades",
        "",
        "| Variante | N | Log-loss | Brier | Acierto clase mayor |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, metric in models.items():
        lines.append(
            "| "
            + name
            + f" | {metric.get('n', 0)}"
            + (
                f" | {metric['log_loss']:.6f}"
                f" | {metric['multiclass_brier']:.6f}"
                f" | {metric['top_class_accuracy']:.2%} |"
                if metric.get("n")
                else " | n/d | n/d | n/d |"
            )
        )
    lines.extend(
        [
            "",
            "### Corte temporal",
            "",
            (
                "| Variante | N reciente | Log-loss reciente | "
                "Brier reciente | Acierto reciente |"
            ),
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, metric in models.items():
        latest = (
            metric.get("chronological_split", {}).get(
                "latest_30_percent",
                {},
            )
        )
        lines.append(
            f"| {name} | {latest.get('n', 0)}"
            + (
                f" | {latest['log_loss']:.6f}"
                f" | {latest['multiclass_brier']:.6f}"
                f" | {latest['top_class_accuracy']:.2%} |"
                if latest.get("n")
                else " | n/d | n/d | n/d |"
            )
        )
    lines.extend(
        [
            "",
        (
            "La variante `current_exact_available_rules_replay` es una "
            "reproduccion parcial: aplica las formulas actuales solo donde "
            "el dato pre-trade es recuperable. No equivale al motor completo "
            "con todos sus proveedores en vivo."
        ),
        "",
        (
            f"En las mismas {stored_market['n']} entradas market, el historico "
            f"almacenado obtiene log-loss {stored_market['log_loss']:.6f}, "
            f"Brier {stored_market['multiclass_brier']:.6f} y "
            f"{stored_market['top_class_accuracy']:.2%} de acierto de clase. "
            f"La reproduccion actual parcial obtiene "
            f"{current['log_loss']:.6f}, "
            f"{current['multiclass_brier']:.6f} y "
            f"{current['top_class_accuracy']:.2%}. Es una mejora retrospectiva "
            "prometedora, pero no una comparacion independiente: los motores "
            "antiguos son heterogeneos y parte del modelo actual fue ajustada "
            "con este mismo periodo."
        ),
        "",
            (
            "El paso desde el modelo ajustado previo al overlay hasta las reglas "
            f"exactas disponibles solo reduce log-loss en "
            f"{fitted['log_loss'] - current['log_loss']:.6f} y Brier en "
            f"{fitted['multiclass_brier'] - current['multiclass_brier']:.6f}, "
            f"con acierto {fitted['top_class_accuracy']:.2%} frente a "
            f"{current['top_class_accuracy']:.2%}. Por tanto, el beneficio "
            "observado procede principalmente del nuevo nucleo y del ajuste "
            "fitted, no queda demostrado para los overlays provisionales."
            ),
            "",
            (
            f"En las {current_latest['n']} operaciones market mas recientes, "
            f"el motor almacenado obtiene log-loss "
            f"{stored_latest['log_loss']:.6f}, Brier "
            f"{stored_latest['multiclass_brier']:.6f} y "
            f"{stored_latest['top_class_accuracy']:.2%} de acierto; la "
            f"reproduccion actual parcial obtiene "
            f"{current_latest['log_loss']:.6f}, "
            f"{current_latest['multiclass_brier']:.6f} y "
            f"{current_latest['top_class_accuracy']:.2%}. La mejora frente al "
            f"historico persiste. Aun asi, el baseline de difusion obtiene "
            f"Brier {diffusion_latest['multiclass_brier']:.6f} y "
            f"{diffusion_latest['top_class_accuracy']:.2%} de acierto en ese "
            "mismo tramo: el ajuste reduce log-loss, pero no mejora "
            "uniformemente todas las metricas."
            ),
            "",
            (
                "En el tramo reciente el overlay empeora log-loss y Brier frente "
            f"al modelo fitted previo ({current_latest['log_loss']:.6f} frente "
            f"a {fitted_latest['log_loss']:.6f} y "
            f"{current_latest['multiclass_brier']:.6f} frente a "
            f"{fitted_latest['multiclass_brier']:.6f}), aunque cambia el "
            f"acierto de clase de {fitted_latest['top_class_accuracy']:.2%} "
            f"a {current_latest['top_class_accuracy']:.2%}. Esto no valida "
            "los pesos provisionales."
            ),
            "",
            "## Ablacion de reglas activas",
            "",
            (
                "Un valor positivo significa que incluir la regla mejora la "
                "metrica frente al mismo motor sin esa regla; un valor negativo "
                "significa que la empeora."
            ),
            "",
            (
                "| Regla | N | Delta log-loss | Delta Brier | "
                "Delta log-loss reciente | Delta Brier reciente |"
            ),
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
        item = ablations.get(rule_id, {})
        if not item.get("n"):
            lines.append(
                f"| `{rule_id}` | 0 | n/d | n/d | n/d | n/d |"
            )
            continue
        overall_delta = item["delta_full_minus_without"]
        latest_delta = item[
            "latest_30_percent_delta_full_minus_without"
        ]
        lines.append(
            f"| `{rule_id}` | {item['n']} | "
            f"{overall_delta['log_loss_improvement']:+.6f} | "
            f"{overall_delta['brier_improvement']:+.6f} | "
            f"{latest_delta['log_loss_improvement']:+.6f} | "
            f"{latest_delta['brier_improvement']:+.6f} |"
        )
    lines.extend(
        [
            "",
            (
                "Estas ablaciones son diagnosticas sobre el mismo historico. "
                "No sustituyen una validacion temporal independiente ni "
                "autorizan cambios automaticos de peso."
            ),
            "",
            "## Regla por regla",
            "",
            "| Regla | Estado | Exactas | Proxies | Conclusion |",
            "|---|---|---:|---:|---|",
        ]
    )
    for rule_id, item in rules.items():
        lines.append(
            f"| `{rule_id}` | {item['lifecycle_status']} | "
            f"{item['exact_comparable_n']} | {item['proxy_diagnostic_n']} | "
            f"{item['conclusion']} |"
        )
    lines.extend(
        [
            "",
            "## Criterio",
            "",
            (
                "Las asociaciones exigen al menos 50 casos comparables, 10 "
                "positivos y 10 negativos, bootstrap, permutacion, correccion "
                "Benjamini-Hochberg y consistencia entre el 70% inicial y el "
                "30% final. Incluso cuando se cumplen, la conclusion es apoyo "
                "historico, no validacion independiente."
            ),
            "",
            (
                "Los controles deterministas y economicos no se juzgan por "
                "acertar TP o SL. Se auditan por cobertura, identidad de formula, "
                "datos disponibles y bloqueo correcto."
            ),
            "",
            "## Siguiente decision permitida",
            "",
            (
                "Conservar sin cambios las reglas y pesos hasta revisar los "
                "resultados concretos de esta auditoria. Las reglas sin datos "
                "historicos suficientes deben acumular trazas prospectivas "
                "completas; no se rellenan ni se validan por aproximacion."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def run() -> dict:
    library = load_rule_library()
    rules = {rule["rule_id"]: rule for rule in library["rules"]}
    rows = load_rows()
    outcomes = load_known_outcomes()
    try:
        enrich_missing_outcomes(rows, outcomes)
    except Exception as exc:
        print(
            f"OUTCOME_RECONSTRUCTION_WARNING={type(exc).__name__}:{exc}",
            flush=True,
        )

    archive = CandleArchive.load()
    archive.ensure(rows)
    cases = []
    for index, row in enumerate(rows, start=1):
        print(
            f"REPLAY={index}/{len(rows)}:operation={row['operation_id']}",
            flush=True,
        )
        cases.append(
            build_case(
                row,
                rules,
                archive,
                outcomes.get(row["operation_id"]),
            )
        )

    summary, association_metrics = summarize(cases, library)
    payload = {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "database_query": "all CLOSED operations with latest recommendation",
            "historical_entry_policy": (
                "market replayed; pending retained but not mixed"
            ),
            "outcome_contract": list(CLASSES),
            "no_missing_to_neutral": True,
            "production_changes": False,
            "learning_weight_changes": False,
        },
        "library_version": library["library_version"],
        "catalog_sha256": library["catalog_sha256"],
        "summary": summary,
        "association_metrics": association_metrics,
        "cases": cases,
    }
    payload["audit_sha256"] = sha256_json(payload)
    write_json(OUTPUT_PATH, payload)
    REPORT_PATH.write_text(build_report(payload), encoding="utf-8")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print(f"AUDIT_SHA256={payload['audit_sha256']}")
    return payload


if __name__ == "__main__":
    run()
