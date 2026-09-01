from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

import liquidation_data
import market_data
from analysis_engine import TradeProposal
from empirical_temporal_engine import ENGINE_VERSION as EMPIRICAL_ENGINE_VERSION
from market_price_state import fresh_market_prices
from multiscale_feature_runtime import STAGE_PROFILES, _closed_material, required_candle_count
from order_book_observation_state import (
    get_order_book_observation_row,
    summarize_order_book_observation,
)
from sequential_production_analysis import NewEngineAnalysisError, analyze_trade
from sequential_production_runtime import fetch_klines_range, normalize_kline
from versioning import (
    APP_VERSION,
    DATA_CONTRACT_VERSION,
    DATA_SOURCE_VERSION,
    LEARNING_SCHEMA_VERSION,
    SCORING_VERSION,
    build_data_contract,
    current_version_contract,
)


logger = logging.getLogger("autonomous_contest")

POLICY_VERSION = "autonomous-contest-policy-v0.1"
STORAGE_VERSION = "autonomous-contest-storage-v0.1"
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
MIN_TP_PROBABILITY = 0.30
MAX_UNRESOLVED_PROBABILITY = 0.55
MIN_ANALOGS_PER_STAGE = 80
SCAN_RELEASE_DELAY_SECONDS = 75
NON_PANEL_STORAGE_CAP_PER_UTC_DAY = 12
OBSERVATIONAL_JSON_BYTE_BUDGET = 12_000
MAX_EXECUTION_DRIFT_SIGMA_FRACTION = 0.10
MAX_EXECUTION_DRIFT_FLOOR = 0.0002


@dataclass(frozen=True)
class ParticipantPolicy:
    code: str
    username: str
    display_name: str
    time_horizon: str
    cadence_minutes: int
    daily_operation_limit: int
    max_open_positions: int
    edge_threshold: float
    margin: float = 100.0
    leverage: float = 1.0
    symbols: tuple[str, ...] = SYMBOLS


PARTICIPANT_POLICIES = (
    ParticipantPolicy(
        code="auto_intraday_short",
        username="Bot_Intradia_Corto",
        display_name="Bot Intradia Corto",
        time_horizon="intraday_short",
        cadence_minutes=15,
        daily_operation_limit=3,
        max_open_positions=3,
        edge_threshold=0.10,
    ),
    ParticipantPolicy(
        code="auto_intraday_wide",
        username="Bot_Intradia_Medio",
        display_name="Bot Intradia Medio",
        time_horizon="intraday_wide",
        cadence_minutes=60,
        daily_operation_limit=2,
        max_open_positions=2,
        edge_threshold=0.10,
    ),
    ParticipantPolicy(
        code="auto_short_swing",
        username="Bot_Swing_Corto",
        display_name="Bot Swing Corto",
        time_horizon="short_swing",
        cadence_minutes=360,
        daily_operation_limit=1,
        max_open_positions=7,
        edge_threshold=0.02,
    ),
)

POLICY_BY_CODE = {policy.code: policy for policy in PARTICIPANT_POLICIES}


@dataclass
class Candidate:
    symbol: str
    side: str
    time_horizon: str
    analyzed_at: datetime
    entry: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    sigma: float | None = None
    tp_probability: float | None = None
    sl_probability: float | None = None
    unresolved_probability: float | None = None
    edge: float | None = None
    selected_analogs_min: int | None = None
    max_context_distance_ratio: float | None = None
    artifact_id: str | None = None
    analysis_status: str = "blocked"
    rejection_code: str | None = None
    analysis_result: dict | None = field(default=None, repr=False)
    observational_json: dict = field(default_factory=dict)

    @property
    def eligible_base(self) -> bool:
        return (
            self.analysis_status == "evaluated"
            and self.rejection_code is None
            and self.tp_probability is not None
            and self.sl_probability is not None
            and self.unresolved_probability is not None
            and self.edge is not None
            and self.tp_probability >= MIN_TP_PROBABILITY
            and self.unresolved_probability <= MAX_UNRESOLVED_PROBABILITY
            and (self.selected_analogs_min or 0) >= MIN_ANALOGS_PER_STAGE
        )

    def eligible_for(self, policy: ParticipantPolicy) -> bool:
        return self.eligible_base and float(self.edge) >= policy.edge_threshold


AnalysisRunner = Callable[..., dict]
SigmaLoader = Callable[[str, str, datetime], float]
KlineLoader = Callable[..., list[list]]


class MemoizedKlineLoader:
    """Reuse exact closed-candle pages inside one autonomous scanner cycle.

    LONG and SHORT candidates, plus the nested horizons, request many of the
    same pages. Reusing only byte-equivalent requests preserves the timestamp
    and source contract while preventing a burst of duplicate Binance calls.
    """

    def __init__(self, loader: KlineLoader = market_data.get_klines):
        self.loader = loader
        self._cache: dict[tuple, tuple[tuple, ...]] = {}
        self.requests = 0
        self.hits = 0

    def __call__(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 80,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list[list]:
        key = (
            str(symbol).upper(),
            str(interval),
            int(limit),
            int(start_time_ms) if start_time_ms is not None else None,
            int(end_time_ms) if end_time_ms is not None else None,
        )
        cached = self._cache.get(key)
        if cached is None:
            rows = self.loader(
                key[0],
                key[1],
                key[2],
                start_time_ms=key[3],
                end_time_ms=key[4],
            )
            cached = tuple(tuple(row) for row in rows)
            self._cache[key] = cached
            self.requests += 1
        else:
            self.hits += 1
        return [list(row) for row in cached]

    def stats(self) -> dict[str, int]:
        return {
            "provider_requests": self.requests,
            "cache_hits": self.hits,
            "cached_pages": len(self._cache),
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def scan_slot(policy: ParticipantPolicy, now: datetime) -> datetime:
    current = _as_utc(now) - timedelta(seconds=SCAN_RELEASE_DELAY_SECONDS)
    cadence_seconds = policy.cadence_minutes * 60
    epoch = int(current.timestamp())
    return datetime.fromtimestamp(
        epoch // cadence_seconds * cadence_seconds,
        tz=timezone.utc,
    )


def is_canonical_panel(policy: ParticipantPolicy, slot: datetime) -> bool:
    value = _as_utc(slot)
    if policy.time_horizon == "intraday_short":
        return value.minute == 0 and value.hour % 4 == 0
    return value.minute == 0 and value.hour == 0


def ensure_autonomous_storage(db) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS autonomous_contest_participants (
            id BIGSERIAL PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            display_name TEXT NOT NULL,
            time_horizon TEXT NOT NULL UNIQUE
                CHECK(time_horizon IN ('intraday_short', 'intraday_wide', 'short_swing')),
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active', 'paused')),
            policy_version TEXT NOT NULL,
            cadence_minutes INTEGER NOT NULL CHECK(cadence_minutes > 0),
            daily_operation_limit INTEGER NOT NULL CHECK(daily_operation_limit > 0),
            max_open_positions INTEGER NOT NULL CHECK(max_open_positions > 0),
            edge_threshold DOUBLE PRECISION NOT NULL CHECK(edge_threshold BETWEEN -1 AND 1),
            min_tp_probability DOUBLE PRECISION NOT NULL CHECK(min_tp_probability BETWEEN 0 AND 1),
            max_unresolved_probability DOUBLE PRECISION NOT NULL CHECK(max_unresolved_probability BETWEEN 0 AND 1),
            min_analogs_per_stage INTEGER NOT NULL CHECK(min_analogs_per_stage > 0),
            margin DOUBLE PRECISION NOT NULL CHECK(margin > 0),
            leverage DOUBLE PRECISION NOT NULL CHECK(leverage > 0),
            symbols_json JSONB NOT NULL CHECK(jsonb_typeof(symbols_json) = 'array'),
            last_scan_slot_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS autonomous_scan_runs (
            id BIGSERIAL PRIMARY KEY,
            participant_id BIGINT NOT NULL
                REFERENCES autonomous_contest_participants(id) ON DELETE CASCADE,
            contest_season_id BIGINT NOT NULL
                REFERENCES contest_seasons(id) ON DELETE CASCADE,
            scan_slot_at TIMESTAMPTZ NOT NULL,
            analyzed_at TIMESTAMPTZ,
            status TEXT NOT NULL
                CHECK(status IN (
                    'running', 'no_trade', 'would_open', 'opened',
                    'failed', 'no_cash', 'quota_reached', 'capacity_reached'
                )),
            reason_code TEXT,
            candidates_evaluated INTEGER NOT NULL DEFAULT 0,
            candidates_blocked INTEGER NOT NULL DEFAULT 0,
            candidates_eligible INTEGER NOT NULL DEFAULT 0,
            selected_symbol TEXT,
            selected_side TEXT CHECK(selected_side IS NULL OR selected_side IN ('long', 'short')),
            selected_tp_probability DOUBLE PRECISION,
            selected_sl_probability DOUBLE PRECISION,
            selected_unresolved_probability DOUBLE PRECISION,
            selected_edge DOUBLE PRECISION,
            recommendation_id BIGINT REFERENCES recommendations(id) ON DELETE SET NULL,
            operation_id BIGINT REFERENCES operations(id) ON DELETE SET NULL,
            engine_version TEXT NOT NULL,
            artifact_id TEXT,
            policy_version TEXT NOT NULL,
            dry_run BOOLEAN NOT NULL,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(participant_id, scan_slot_at)
        );

        CREATE TABLE IF NOT EXISTS autonomous_candidate_observations (
            id BIGSERIAL PRIMARY KEY,
            scan_run_id BIGINT NOT NULL
                REFERENCES autonomous_scan_runs(id) ON DELETE CASCADE,
            participant_id BIGINT NOT NULL
                REFERENCES autonomous_contest_participants(id) ON DELETE CASCADE,
            contest_season_id BIGINT NOT NULL
                REFERENCES contest_seasons(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('long', 'short')),
            time_horizon TEXT NOT NULL,
            analyzed_at TIMESTAMPTZ NOT NULL,
            evaluation_due_at TIMESTAMPTZ NOT NULL,
            entry DOUBLE PRECISION,
            take_profit DOUBLE PRECISION,
            stop_loss DOUBLE PRECISION,
            context_sigma DOUBLE PRECISION,
            tp_probability DOUBLE PRECISION,
            sl_probability DOUBLE PRECISION,
            unresolved_probability DOUBLE PRECISION,
            edge DOUBLE PRECISION,
            selected_analogs_min INTEGER,
            max_context_distance_ratio DOUBLE PRECISION,
            analysis_status TEXT NOT NULL CHECK(analysis_status IN ('evaluated', 'blocked', 'failed')),
            rejection_code TEXT,
            selected BOOLEAN NOT NULL DEFAULT FALSE,
            storage_reason TEXT NOT NULL CHECK(storage_reason IN ('panel', 'selected', 'boundary')),
            observational_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            engine_version TEXT NOT NULL,
            artifact_id TEXT,
            outcome_status TEXT NOT NULL DEFAULT 'pending'
                CHECK(outcome_status IN ('pending', 'evaluated', 'excluded')),
            first_touch TEXT CHECK(first_touch IS NULL OR first_touch IN ('tp', 'sl', 'ambiguous', 'unresolved')),
            first_touch_at TIMESTAMPTZ,
            terminal_price DOUBLE PRECISION,
            r_multiple DOUBLE PRECISION,
            evaluated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scan_run_id, symbol, side)
        );

        CREATE INDEX IF NOT EXISTS idx_autonomous_participant_status
            ON autonomous_contest_participants(status, time_horizon);
        CREATE INDEX IF NOT EXISTS idx_autonomous_scan_due
            ON autonomous_scan_runs(participant_id, scan_slot_at DESC);
        CREATE INDEX IF NOT EXISTS idx_autonomous_scan_season
            ON autonomous_scan_runs(contest_season_id, status, scan_slot_at DESC);
        CREATE INDEX IF NOT EXISTS idx_autonomous_candidate_due
            ON autonomous_candidate_observations(outcome_status, evaluation_due_at)
            WHERE outcome_status = 'pending';
        CREATE INDEX IF NOT EXISTS idx_autonomous_candidate_learning
            ON autonomous_candidate_observations(
                time_horizon, symbol, side, outcome_status, analyzed_at
            );

        ALTER TABLE autonomous_contest_participants ENABLE ROW LEVEL SECURITY;
        ALTER TABLE autonomous_scan_runs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE autonomous_candidate_observations ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE autonomous_contest_participants FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE autonomous_scan_runs FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE autonomous_candidate_observations FROM anon, authenticated;
        """
    )


def _disabled_password_hash() -> str:
    return "disabled_autonomous_participant_no_interactive_login"


def ensure_participants(db) -> list[dict]:
    rows = []
    for policy in PARTICIPANT_POLICIES:
        db.execute(
            """
            INSERT INTO users (
                username, password_hash, starting_balance, cash_balance
            ) VALUES (?, ?, 1000, 1000)
            ON CONFLICT (username) DO NOTHING
            """,
            (policy.username, _disabled_password_hash()),
        )
        user = db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (policy.username,),
        ).fetchone()
        if user is None:
            raise RuntimeError(f"autonomous_user_missing:{policy.username}")
        existing = db.execute(
            "SELECT id FROM autonomous_contest_participants WHERE code = ?",
            (policy.code,),
        ).fetchone()
        if (
            existing is None
            and str(user["password_hash"]) != _disabled_password_hash()
        ):
            raise RuntimeError(f"autonomous_username_owned_by_interactive_user:{policy.username}")
        db.execute(
            """
            INSERT INTO autonomous_contest_participants (
                code, user_id, display_name, time_horizon, status,
                policy_version, cadence_minutes, daily_operation_limit,
                max_open_positions, edge_threshold, min_tp_probability,
                max_unresolved_probability, min_analogs_per_stage,
                margin, leverage, symbols_json, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (code) DO UPDATE SET
                user_id = excluded.user_id,
                display_name = excluded.display_name,
                time_horizon = excluded.time_horizon,
                policy_version = excluded.policy_version,
                cadence_minutes = excluded.cadence_minutes,
                daily_operation_limit = excluded.daily_operation_limit,
                max_open_positions = excluded.max_open_positions,
                edge_threshold = excluded.edge_threshold,
                min_tp_probability = excluded.min_tp_probability,
                max_unresolved_probability = excluded.max_unresolved_probability,
                min_analogs_per_stage = excluded.min_analogs_per_stage,
                margin = excluded.margin,
                leverage = excluded.leverage,
                symbols_json = excluded.symbols_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                policy.code,
                int(user["id"]),
                policy.display_name,
                policy.time_horizon,
                POLICY_VERSION,
                policy.cadence_minutes,
                policy.daily_operation_limit,
                policy.max_open_positions,
                policy.edge_threshold,
                MIN_TP_PROBABILITY,
                MAX_UNRESOLVED_PROBABILITY,
                MIN_ANALOGS_PER_STAGE,
                policy.margin,
                policy.leverage,
                _json(policy.symbols),
            ),
        )
        row = db.execute(
            "SELECT * FROM autonomous_contest_participants WHERE code = ?",
            (policy.code,),
        ).fetchone()
        rows.append(dict(row))
    return rows


def ensure_contest_entries(db, participants: Iterable[dict], season: dict) -> None:
    for participant in participants:
        cursor = db.execute(
            """
            INSERT INTO contest_entries (
                season_id, user_id, starting_balance, cash_balance
            ) VALUES (?, ?, 1000, 1000)
            ON CONFLICT (season_id, user_id) DO NOTHING
            RETURNING id
            """,
            (int(season["id"]), int(participant["user_id"])),
        )
        inserted = cursor.fetchone()
        if inserted is not None:
            db.execute(
                """
                INSERT INTO wallet_events (
                    user_id, mode, event_type, amount, balance_after,
                    contest_season_id, note
                ) VALUES (?, 'contest', 'contest_monthly_start', 1000, 1000, ?, ?)
                """,
                (
                    int(participant["user_id"]),
                    int(season["id"]),
                    "Alta automatica del participante autonomo en el concurso.",
                ),
            )


def load_horizon_sigma(
    symbol: str,
    time_horizon: str,
    analysis_at: datetime,
    *,
    loader: KlineLoader = market_data.get_klines,
) -> float:
    profile = STAGE_PROFILES[time_horizon]
    count = required_candle_count(time_horizon)
    analysis = _as_utc(analysis_at)
    analysis_ms = int(analysis.timestamp() * 1000)
    start_ms = analysis_ms - (count + 2) * int(profile["interval_seconds"]) * 1000
    raw = fetch_klines_range(
        symbol,
        str(profile["interval"]),
        start_ms,
        analysis_ms,
        loader=loader,
    )
    plan = {
        "time_horizon": time_horizon,
        "analysis_at": analysis.isoformat(),
    }
    material = _closed_material(plan, [normalize_kline(row) for row in raw])
    sigma = math.sqrt(float(material["current_variance"]))
    if not math.isfinite(sigma) or sigma <= 0.0 or sigma >= 0.50:
        raise ValueError(f"invalid_horizon_sigma:{sigma}")
    return sigma


def symmetric_geometry(entry: float, sigma: float, side: str) -> tuple[float, float]:
    lower = float(entry) * (1.0 - float(sigma))
    upper = float(entry) * (1.0 + float(sigma))
    return (upper, lower) if side == "long" else (lower, upper)


def _compact_observations(result: dict) -> dict:
    snapshot = result.get("snapshot") if isinstance(result, dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    traces_by_stage = snapshot.get("stage_rule_traces")
    traces_by_stage = traces_by_stage if isinstance(traces_by_stage, dict) else {}
    items = []
    for horizon, traces in traces_by_stage.items():
        for trace in traces if isinstance(traces, list) else []:
            if not isinstance(trace, dict):
                continue
            if trace.get("probability_effect") == "analog_distance_input":
                continue
            item = {
                "time_horizon": horizon,
                "rule_id": trace.get("rule_id"),
                "status": trace.get("status"),
                "probability_effect": trace.get("probability_effect"),
                "outputs": trace.get("outputs") if isinstance(trace.get("outputs"), dict) else {},
            }
            candidate = {"traces": [*items, item]}
            if len(_json(candidate).encode("utf-8")) > OBSERVATIONAL_JSON_BYTE_BUDGET:
                break
            items.append(item)
    compact = {
        "storage_version": STORAGE_VERSION,
        "traces": items,
        "liquidation": snapshot.get("liquidation_observation") or {},
        "order_book": snapshot.get("order_book_observation") or {},
        "raw_market_payloads_stored": False,
    }
    while (
        len(_json(compact).encode("utf-8")) > OBSERVATIONAL_JSON_BYTE_BUDGET
        and compact["traces"]
    ):
        compact["traces"].pop()
    if len(_json(compact).encode("utf-8")) > OBSERVATIONAL_JSON_BYTE_BUDGET:
        compact["liquidation"] = {
            "status": compact["liquidation"].get("status"),
            "available": compact["liquidation"].get("available"),
            "provider_reason": compact["liquidation"].get("provider_reason"),
        }
        compact["order_book"] = {
            "status": compact["order_book"].get("status"),
            "available": compact["order_book"].get("available"),
            "provider_reason": compact["order_book"].get("provider_reason"),
        }
    return compact


def _support_from_result(result: dict) -> tuple[int, float, str | None]:
    model_trace = result.get("model_trace") if isinstance(result, dict) else {}
    model_trace = model_trace if isinstance(model_trace, dict) else {}
    traces = model_trace.get("stage_traces")
    traces = traces if isinstance(traces, list) else []
    selected = [int(trace.get("selected_analogs") or 0) for trace in traces]
    ratios = []
    for trace in traces:
        maximum = float(trace.get("maximum_context_distance_allowed") or 0.0)
        nearest = float(trace.get("nearest_context_distance") or 0.0)
        if maximum > 0.0:
            ratios.append(nearest / maximum)
    return (
        min(selected) if selected else 0,
        max(ratios) if ratios else math.inf,
        str(model_trace.get("artifact_id") or "") or None,
    )


def rejection_code(candidate: Candidate, policy: ParticipantPolicy) -> str | None:
    if candidate.analysis_status != "evaluated":
        return candidate.rejection_code or candidate.analysis_status
    if (candidate.selected_analogs_min or 0) < MIN_ANALOGS_PER_STAGE:
        return "insufficient_analog_support"
    tp_probability = (
        candidate.tp_probability if candidate.tp_probability is not None else 0.0
    )
    if float(tp_probability) < MIN_TP_PROBABILITY:
        return "tp_probability_below_gate"
    if float(
        candidate.unresolved_probability
        if candidate.unresolved_probability is not None
        else 1.0
    ) > MAX_UNRESOLVED_PROBABILITY:
        return "unresolved_probability_above_gate"
    edge = candidate.edge if candidate.edge is not None else -2.0
    if float(edge) < policy.edge_threshold:
        return "edge_below_horizon_gate"
    return None


def analyze_candidates(
    policy: ParticipantPolicy,
    prices: dict[str, float],
    analysis_at: datetime,
    *,
    analysis_runner: AnalysisRunner = analyze_trade,
    sigma_loader: SigmaLoader = load_horizon_sigma,
    liquidation_contexts: dict[str, dict] | None = None,
    order_book_contexts: dict[str, dict] | None = None,
    kline_loader: KlineLoader | None = None,
    symbols: Iterable[str] | None = None,
    sides: Iterable[str] = ("long", "short"),
) -> list[Candidate]:
    analyzed_at = _as_utc(analysis_at)
    liquidation_contexts = liquidation_contexts or {}
    order_book_contexts = order_book_contexts or {}
    shared_kline_loader = kline_loader or MemoizedKlineLoader()
    candidates: list[Candidate] = []
    requested_symbols = tuple(symbols) if symbols is not None else policy.symbols
    requested_sides = tuple(str(side).lower() for side in sides)
    if not requested_sides or any(side not in {"long", "short"} for side in requested_sides):
        raise ValueError("autonomous_candidate_sides_invalid")
    for symbol in requested_symbols:
        entry = prices.get(symbol)
        if entry is None:
            for side in requested_sides:
                candidates.append(
                    Candidate(
                        symbol=symbol,
                        side=side,
                        time_horizon=policy.time_horizon,
                        analyzed_at=analyzed_at,
                        analysis_status="blocked",
                        rejection_code="worker_price_unavailable",
                    )
                )
            continue
        try:
            if sigma_loader is load_horizon_sigma:
                sigma = load_horizon_sigma(
                    symbol,
                    policy.time_horizon,
                    analyzed_at,
                    loader=shared_kline_loader,
                )
            else:
                sigma = sigma_loader(symbol, policy.time_horizon, analyzed_at)
        except Exception as exc:
            for side in requested_sides:
                candidates.append(
                    Candidate(
                        symbol=symbol,
                        side=side,
                        time_horizon=policy.time_horizon,
                        analyzed_at=analyzed_at,
                        entry=float(entry),
                        analysis_status="failed",
                        rejection_code=f"sigma:{type(exc).__name__}:{exc}",
                    )
                )
            continue
        for side in requested_sides:
            take_profit, stop_loss = symmetric_geometry(float(entry), sigma, side)
            proposal = TradeProposal(
                symbol=symbol,
                side=side,
                time_horizon=policy.time_horizon,
                entry=float(entry),
                margin=policy.margin,
                leverage=policy.leverage,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_type="market",
            )
            try:
                analysis_kwargs = {
                    "context_loader": (
                        (lambda _symbol, _price, value=liquidation_contexts.get(symbol): value)
                        if symbol in liquidation_contexts
                        else None
                    ),
                    "context_market_price": float(entry),
                    "order_book_observation_loader": (
                        (lambda _symbol, value=order_book_contexts.get(symbol): value)
                        if symbol in order_book_contexts
                        else None
                    ),
                    "effective_analysis_at": analyzed_at,
                }
                if analysis_runner is analyze_trade:
                    analysis_kwargs["loader"] = shared_kline_loader
                result = analysis_runner(proposal, **analysis_kwargs)
                selected_analogs, distance_ratio, artifact_id = _support_from_result(result)
                tp_probability = float(result["tp_probability"])
                sl_probability = float(result["sl_probability"])
                unresolved = float(result["range_probability"])
                candidate = Candidate(
                    symbol=symbol,
                    side=side,
                    time_horizon=policy.time_horizon,
                    analyzed_at=analyzed_at,
                    entry=float(entry),
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                    sigma=sigma,
                    tp_probability=tp_probability,
                    sl_probability=sl_probability,
                    unresolved_probability=unresolved,
                    edge=tp_probability - sl_probability,
                    selected_analogs_min=selected_analogs,
                    max_context_distance_ratio=distance_ratio,
                    artifact_id=artifact_id,
                    analysis_status="evaluated",
                    analysis_result=result,
                    observational_json=_compact_observations(result),
                )
                candidate.rejection_code = rejection_code(candidate, policy)
                candidates.append(candidate)
            except NewEngineAnalysisError as exc:
                candidates.append(
                    Candidate(
                        symbol=symbol,
                        side=side,
                        time_horizon=policy.time_horizon,
                        analyzed_at=analyzed_at,
                        entry=float(entry),
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        sigma=sigma,
                        analysis_status="blocked",
                        rejection_code=str(exc.code or "analysis_blocked"),
                    )
                )
            except Exception as exc:
                candidates.append(
                    Candidate(
                        symbol=symbol,
                        side=side,
                        time_horizon=policy.time_horizon,
                        analyzed_at=analyzed_at,
                        entry=float(entry),
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        sigma=sigma,
                        analysis_status="failed",
                        rejection_code=f"{type(exc).__name__}:{exc}",
                    )
                )
    return candidates


def select_candidate(
    candidates: list[Candidate], policy: ParticipantPolicy
) -> Candidate | None:
    eligible = [candidate for candidate in candidates if candidate.eligible_for(policy)]
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda candidate: (
            -float(candidate.edge),
            -float(candidate.tp_probability),
            float(candidate.unresolved_probability),
            candidate.symbol,
            candidate.side,
        ),
    )[0]


def _daily_operation_count(
    db, participant: dict, season_id: int, now: datetime, *, dry_run: bool
) -> int:
    day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if dry_run:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM autonomous_scan_runs
            WHERE participant_id = ?
              AND contest_season_id = ?
              AND status = 'would_open'
              AND scan_slot_at >= ?
            """,
            (int(participant["id"]), season_id, day_start.isoformat()),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM operations
            WHERE user_id = ?
              AND mode = 'contest'
              AND contest_season_id = ?
              AND created_at >= ?
            """,
            (int(participant["user_id"]), season_id, day_start.isoformat()),
        ).fetchone()
    return int(row["count"] or 0)


def _open_position_count(
    db, participant: dict, season_id: int, now: datetime, *, dry_run: bool
) -> int:
    if dry_run:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM autonomous_candidate_observations c
            JOIN autonomous_scan_runs s ON s.id = c.scan_run_id
            WHERE c.participant_id = ?
              AND c.contest_season_id = ?
              AND c.selected = TRUE
              AND s.status = 'would_open'
              AND c.evaluation_due_at > ?
            """,
            (int(participant["id"]), season_id, now.isoformat()),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM operations
            WHERE user_id = ?
              AND mode = 'contest'
              AND contest_season_id = ?
              AND status IN ('OPEN', 'PENDING_ENTRY')
            """,
            (int(participant["user_id"]), season_id),
        ).fetchone()
    return int(row["count"] or 0)


def _available_contest_cash(db, user_id: int, season_id: int) -> float:
    entry = db.execute(
        """
        SELECT starting_balance
        FROM contest_entries
        WHERE user_id = ? AND season_id = ?
        """,
        (user_id, season_id),
    ).fetchone()
    if entry is None:
        return 0.0
    totals = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN final_pnl ELSE 0 END), 0) AS closed_pnl,
            COALESCE(SUM(CASE WHEN status IN ('OPEN', 'PENDING_ENTRY') THEN margin ELSE 0 END), 0) AS active_margin
        FROM operations
        WHERE user_id = ? AND mode = 'contest' AND contest_season_id = ?
        """,
        (user_id, season_id),
    ).fetchone()
    return (
        float(entry["starting_balance"])
        + float(totals["closed_pnl"] or 0.0)
        - float(totals["active_margin"] or 0.0)
    )


def _claim_scan(db, participant: dict, season_id: int, slot: datetime, dry_run: bool) -> int | None:
    cursor = db.execute(
        """
        INSERT INTO autonomous_scan_runs (
            participant_id, contest_season_id, scan_slot_at, status,
            engine_version, policy_version, dry_run
        ) VALUES (?, ?, ?, 'running', ?, ?, ?)
        ON CONFLICT (participant_id, scan_slot_at) DO NOTHING
        RETURNING id
        """,
        (
            int(participant["id"]),
            season_id,
            slot.isoformat(),
            EMPIRICAL_ENGINE_VERSION,
            POLICY_VERSION,
            bool(dry_run),
        ),
    )
    row = cursor.fetchone()
    return int(row["id"]) if row is not None else None


def _candidate_storage_selection(
    db,
    policy: ParticipantPolicy,
    slot: datetime,
    candidates: list[Candidate],
    selected: Candidate | None,
) -> dict[tuple[str, str], str]:
    if is_canonical_panel(policy, slot):
        return {(candidate.symbol, candidate.side): "panel" for candidate in candidates}
    result = {}
    day_start = datetime(slot.year, slot.month, slot.day, tzinfo=timezone.utc)
    non_panel_count = int(
        db.execute(
            """
            SELECT COUNT(*) AS count
            FROM autonomous_candidate_observations
            WHERE storage_reason IN ('selected', 'boundary') AND analyzed_at >= ?
            """,
            (day_start.isoformat(),),
        ).fetchone()["count"]
        or 0
    )
    remaining_slots = NON_PANEL_STORAGE_CAP_PER_UTC_DAY - non_panel_count
    if remaining_slots <= 0:
        return result
    if selected is not None:
        result[(selected.symbol, selected.side)] = "selected"
        remaining_slots -= 1
    if remaining_slots > 0:
        remaining = [
            candidate
            for candidate in candidates
            if (candidate.symbol, candidate.side) not in result
            and candidate.analysis_status == "evaluated"
        ]
        if remaining:
            boundary = sorted(
                remaining,
                key=lambda candidate: (
                    abs(float(candidate.edge or 0.0) - policy.edge_threshold),
                    -float(candidate.tp_probability or 0.0),
                    candidate.symbol,
                    candidate.side,
                ),
            )[0]
            result[(boundary.symbol, boundary.side)] = "boundary"
    return result


def _persist_candidate_observations(
    db,
    *,
    scan_run_id: int,
    participant: dict,
    season_id: int,
    policy: ParticipantPolicy,
    slot: datetime,
    candidates: list[Candidate],
    selected: Candidate | None,
) -> int:
    selected_keys = _candidate_storage_selection(db, policy, slot, candidates, selected)
    persisted = 0
    for candidate in candidates:
        key = (candidate.symbol, candidate.side)
        storage_reason = selected_keys.get(key)
        if storage_reason is None:
            continue
        due_at = candidate.analyzed_at + timedelta(
            seconds=int(STAGE_PROFILES[policy.time_horizon]["horizon_seconds"])
        )
        db.execute(
            """
            INSERT INTO autonomous_candidate_observations (
                scan_run_id, participant_id, contest_season_id,
                symbol, side, time_horizon, analyzed_at, evaluation_due_at,
                entry, take_profit, stop_loss, context_sigma,
                tp_probability, sl_probability, unresolved_probability, edge,
                selected_analogs_min, max_context_distance_ratio,
                analysis_status, rejection_code, selected, storage_reason,
                observational_json, engine_version, artifact_id, outcome_status
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?::jsonb, ?, ?, ?
            )
            ON CONFLICT (scan_run_id, symbol, side) DO NOTHING
            """,
            (
                scan_run_id,
                int(participant["id"]),
                season_id,
                candidate.symbol,
                candidate.side,
                candidate.time_horizon,
                candidate.analyzed_at.isoformat(),
                due_at.isoformat(),
                candidate.entry,
                candidate.take_profit,
                candidate.stop_loss,
                candidate.sigma,
                candidate.tp_probability,
                candidate.sl_probability,
                candidate.unresolved_probability,
                candidate.edge,
                candidate.selected_analogs_min,
                candidate.max_context_distance_ratio,
                candidate.analysis_status,
                candidate.rejection_code,
                candidate is selected,
                storage_reason,
                _json(candidate.observational_json),
                EMPIRICAL_ENGINE_VERSION,
                candidate.artifact_id,
                "pending" if candidate.analysis_status == "evaluated" else "excluded",
            ),
        )
        persisted += 1
    return persisted


def execution_drift_is_acceptable(
    candidate: Candidate,
    execution_entry: float,
) -> bool:
    if candidate.entry is None or candidate.sigma is None or candidate.entry <= 0:
        return False
    drift = abs(float(execution_entry) / float(candidate.entry) - 1.0)
    maximum = max(
        MAX_EXECUTION_DRIFT_FLOOR,
        float(candidate.sigma) * MAX_EXECUTION_DRIFT_SIGMA_FRACTION,
    )
    return drift <= maximum


def _prepare_selected_analysis(
    candidate: Candidate,
    *,
    execution_entry: float,
    execution_take_profit: float,
    execution_stop_loss: float,
    executed_at: datetime,
) -> dict:
    result = dict(candidate.analysis_result or {})
    analysis_entry = float(candidate.entry)
    execution_drift = abs(float(execution_entry) / analysis_entry - 1.0)
    entry_context = {
        "entry_type": "market",
        "trigger_condition": None,
        "entry_order_type": None,
        "requested_entry": execution_entry,
        "activation_rule": "market_entry_at_fresh_worker_execution_price",
        "selection_authority": POLICY_VERSION,
        "analysis_entry": analysis_entry,
        "execution_entry": execution_entry,
        "execution_drift_ratio": execution_drift,
        "analysis_completed_at": executed_at.isoformat(),
        "analysis_to_execution_seconds": max(
            0.0,
            (executed_at - candidate.analyzed_at).total_seconds(),
        ),
        "execution_price_authority": "operation_worker",
    }
    result["entry_order_context"] = entry_context
    snapshot = result.setdefault("snapshot", {})
    snapshot.update(
        {
            "entry": execution_entry,
            "take_profit": execution_take_profit,
            "stop_loss": execution_stop_loss,
            "entry_order_context": entry_context,
            "analysis_reference_geometry": {
                "entry": analysis_entry,
                "take_profit": candidate.take_profit,
                "stop_loss": candidate.stop_loss,
                "context_sigma": candidate.sigma,
            },
            "execution_geometry": {
                "entry": execution_entry,
                "take_profit": execution_take_profit,
                "stop_loss": execution_stop_loss,
                "context_sigma": candidate.sigma,
            },
        }
    )
    result["training_decision"] = "seleccion_autonoma"
    version_contract = current_version_contract()
    version_contract["autonomous_policy_version"] = POLICY_VERSION
    result["version_contract"] = version_contract
    snapshot["version_contract"] = version_contract
    result["data_contract"] = build_data_contract(
        pre_trade_features=snapshot
    )
    return result


def _open_selected_operation(
    db,
    *,
    participant: dict,
    season_id: int,
    candidate: Candidate,
    policy: ParticipantPolicy,
    execution_entry: float,
    executed_at: datetime,
) -> tuple[int, int]:
    if candidate.analysis_result is None:
        raise ValueError("selected_candidate_analysis_missing")
    user_id = int(participant["user_id"])
    if _daily_operation_count(
        db,
        participant,
        season_id,
        executed_at,
        dry_run=False,
    ) >= policy.daily_operation_limit:
        raise ValueError("autonomous_daily_quota_reached")
    if _open_position_count(
        db,
        participant,
        season_id,
        executed_at,
        dry_run=False,
    ) >= policy.max_open_positions:
        raise ValueError("autonomous_open_capacity_reached")
    cash = _available_contest_cash(db, user_id, season_id)
    if cash < policy.margin:
        raise ValueError("autonomous_contest_cash_insufficient")
    execution_take_profit, execution_stop_loss = symmetric_geometry(
        execution_entry,
        float(candidate.sigma),
        candidate.side,
    )
    result = _prepare_selected_analysis(
        candidate,
        execution_entry=execution_entry,
        execution_take_profit=execution_take_profit,
        execution_stop_loss=execution_stop_loss,
        executed_at=executed_at,
    )
    operation_cursor = db.execute(
        """
        INSERT INTO operations (
            user_id, symbol, side, time_horizon, entry, margin, leverage,
            stop_loss, take_profit, status, started_at, mode,
            contest_season_id, entry_type, requested_entry,
            trigger_condition, entry_order_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, 'contest', ?, 'market', ?, NULL, NULL)
        """,
        (
            user_id,
            candidate.symbol,
            candidate.side,
            policy.time_horizon,
            execution_entry,
            policy.margin,
            policy.leverage,
            execution_stop_loss,
            execution_take_profit,
            executed_at.isoformat(),
            season_id,
            execution_entry,
        ),
    )
    operation_id = int(operation_cursor.lastrowid)
    recommendation_cursor = db.execute(
        """
        INSERT INTO recommendations (
            operation_id, user_id, analysis_type, symbol, side,
            tp_probability, sl_probability, range_probability, risk_level,
            setup_grade, confidence, training_decision, time_horizon,
            parameter_advice_json, reasons_json, alerts_json, snapshot_json,
            analysis_json, engine_version, app_version, scoring_version,
            learning_schema_version, data_source_version, data_contract_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            user_id,
            result["analysis_type"],
            candidate.symbol,
            candidate.side,
            result["tp_probability"],
            result["sl_probability"],
            result["range_probability"],
            result["risk_level"],
            result["setup_grade"],
            result["confidence"],
            result["training_decision"],
            policy.time_horizon,
            _json(result["parameter_advice"]),
            _json(result["reasons"]),
            _json(result["alerts"]),
            _json(result["snapshot"]),
            _json(result),
            result.get("engine_version", EMPIRICAL_ENGINE_VERSION),
            APP_VERSION,
            SCORING_VERSION,
            LEARNING_SCHEMA_VERSION,
            DATA_SOURCE_VERSION,
            DATA_CONTRACT_VERSION,
        ),
    )
    recommendation_id = int(recommendation_cursor.lastrowid)
    db.execute(
        """
        INSERT INTO price_ticks (
            operation_id, symbol, price, source, captured_at
        ) VALUES (?, ?, ?, 'autonomous_market_entry_worker_price', ?)
        """,
        (
            operation_id,
            candidate.symbol,
            execution_entry,
            executed_at.isoformat(),
        ),
    )
    balance_after = cash - policy.margin
    db.execute(
        """
        INSERT INTO wallet_events (
            user_id, mode, event_type, amount, balance_after,
            operation_id, contest_season_id, note
        ) VALUES (?, 'contest', 'margin_reserved', ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            -policy.margin,
            balance_after,
            operation_id,
            season_id,
            f"Operacion elegida por {POLICY_VERSION}.",
        ),
    )
    db.execute(
        """
        UPDATE contest_entries SET cash_balance = ?
        WHERE season_id = ? AND user_id = ?
        """,
        (balance_after, season_id, user_id),
    )
    return operation_id, recommendation_id


def _load_order_book_contexts(db, symbols: Iterable[str], now: datetime) -> dict:
    order_books = {}
    for symbol in symbols:
        summary = summarize_order_book_observation(
            get_order_book_observation_row(db, symbol),
            now=now,
        )
        if summary is not None:
            order_books[symbol] = summary
    return order_books


def _load_liquidation_contexts(prices: dict[str, float]) -> dict:
    liquidations = {}
    for symbol, price in prices.items():
        try:
            liquidations[symbol] = liquidation_data.get_liquidation_context(
                symbol,
                float(price),
            )
        except Exception as exc:
            liquidations[symbol] = {
                "available": False,
                "status": "unavailable",
                "reason": f"{type(exc).__name__}:{exc}",
            }
    return liquidations


def run_due_scans(
    connect_factory,
    season_loader: Callable[[Any], dict],
    *,
    dry_run: bool,
    now: datetime | None = None,
    analysis_runner: AnalysisRunner = analyze_trade,
    sigma_loader: SigmaLoader = load_horizon_sigma,
    kline_loader: KlineLoader = market_data.get_klines,
    bootstrap: bool = True,
) -> dict:
    current = _as_utc(now or utc_now())
    started = time.perf_counter()
    shared_kline_loader = MemoizedKlineLoader(kline_loader)
    with connect_factory() as db:
        if bootstrap:
            ensure_autonomous_storage(db)
        season = season_loader(db)
        participants = (
            ensure_participants(db)
            if bootstrap
            else [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM autonomous_contest_participants"
                ).fetchall()
            ]
        )
        ensure_contest_entries(db, participants, season)
        prices = fresh_market_prices(db, SYMBOLS, now=current)
    missing_prices = sorted(set(SYMBOLS).difference(prices))
    if missing_prices:
        return {
            "policy_version": POLICY_VERSION,
            "dry_run": dry_run,
            "season_id": int(season["id"]),
            "status": "waiting_for_worker_prices",
            "missing_price_symbols": missing_prices,
            "fresh_price_symbols": len(prices),
            "kline_cache": shared_kline_loader.stats(),
            "scans": [],
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
    participant_by_code = {row["code"]: row for row in participants}
    scans = []
    for policy in PARTICIPANT_POLICIES:
        participant = participant_by_code[policy.code]
        if str(participant.get("status")) != "active":
            continue
        slot = scan_slot(policy, current)
        last_slot = participant.get("last_scan_slot_at")
        if last_slot is not None and _as_utc(last_slot) >= slot:
            continue
        with connect_factory() as db:
            daily_count = _daily_operation_count(
                db, participant, int(season["id"]), current, dry_run=dry_run
            )
            open_count = _open_position_count(
                db, participant, int(season["id"]), current, dry_run=dry_run
            )
            if daily_count >= policy.daily_operation_limit:
                db.execute(
                    "UPDATE autonomous_contest_participants SET last_scan_slot_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (slot.isoformat(), int(participant["id"])),
                )
                continue
            if open_count >= policy.max_open_positions:
                db.execute(
                    "UPDATE autonomous_contest_participants SET last_scan_slot_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (slot.isoformat(), int(participant["id"])),
                )
                continue
        # One immutable market panel per scanner cycle makes the three nested
        # horizons comparable and lets them reuse identical closed-candle pages.
        analysis_at = current
        with connect_factory() as db:
            prices = fresh_market_prices(db, SYMBOLS, now=analysis_at)
            order_books = _load_order_book_contexts(db, SYMBOLS, analysis_at)
        missing_prices = sorted(set(SYMBOLS).difference(prices))
        if missing_prices:
            scans.append(
                {
                    "participant": policy.code,
                    "scan_run_id": None,
                    "slot": slot.isoformat(),
                    "status": "waiting_for_worker_prices",
                    "reason": "worker_prices_became_unavailable_before_claim",
                    "evaluated": 0,
                    "blocked": 0,
                    "eligible": 0,
                    "operation_id": None,
                }
            )
            continue
        with connect_factory() as db:
            scan_run_id = _claim_scan(
                db, participant, int(season["id"]), slot, dry_run
            )
        if scan_run_id is None:
            continue
        liquidations = _load_liquidation_contexts(prices)
        scan_started = time.perf_counter()
        candidates = analyze_candidates(
            policy,
            prices,
            analysis_at,
            analysis_runner=analysis_runner,
            sigma_loader=sigma_loader,
            liquidation_contexts=liquidations,
            order_book_contexts=order_books,
            kline_loader=shared_kline_loader,
        )
        selected = select_candidate(candidates, policy)
        confirmation_reason = None
        if selected is not None:
            confirmation_at = current if now is not None else utc_now()
            with connect_factory() as db:
                confirmation_prices = fresh_market_prices(
                    db,
                    (selected.symbol,),
                    now=confirmation_at,
                )
                confirmation_order_books = _load_order_book_contexts(
                    db,
                    (selected.symbol,),
                    confirmation_at,
                )
            if selected.symbol not in confirmation_prices:
                confirmation_reason = "selected_confirmation_worker_price_unavailable"
                selected.rejection_code = confirmation_reason
                selected = None
            else:
                confirmation_liquidations = _load_liquidation_contexts(
                    confirmation_prices
                )
                confirmed = analyze_candidates(
                    policy,
                    confirmation_prices,
                    confirmation_at,
                    analysis_runner=analysis_runner,
                    sigma_loader=sigma_loader,
                    liquidation_contexts=confirmation_liquidations,
                    order_book_contexts=confirmation_order_books,
                    kline_loader=shared_kline_loader,
                    symbols=(selected.symbol,),
                    sides=(selected.side,),
                )[0]
                for index, candidate in enumerate(candidates):
                    if (
                        candidate.symbol == confirmed.symbol
                        and candidate.side == confirmed.side
                    ):
                        candidates[index] = confirmed
                        break
                if confirmed.eligible_for(policy):
                    selected = confirmed
                else:
                    confirmation_reason = (
                        "selected_candidate_failed_final_confirmation:"
                        + str(confirmed.rejection_code or confirmed.analysis_status)
                    )
                    selected = None
        evaluated = sum(candidate.analysis_status == "evaluated" for candidate in candidates)
        blocked = len(candidates) - evaluated
        eligible = sum(candidate.eligible_for(policy) for candidate in candidates)
        decision_analyzed_at = max(
            (candidate.analyzed_at for candidate in candidates),
            default=analysis_at,
        )
        status = "no_trade"
        reason = confirmation_reason or "no_candidate_passed_horizon_policy"
        operation_id = recommendation_id = None
        try:
            with connect_factory() as db:
                if selected is not None:
                    season_id = int(season["id"])
                    execution_at = current if now is not None else utc_now()
                    execution_prices = fresh_market_prices(
                        db,
                        (selected.symbol,),
                        now=execution_at,
                    )
                    execution_entry = execution_prices.get(selected.symbol)
                    if execution_entry is None:
                        status = "no_trade"
                        reason = "fresh_worker_execution_price_unavailable"
                    elif not execution_drift_is_acceptable(
                        selected,
                        execution_entry,
                    ):
                        status = "no_trade"
                        reason = "execution_price_moved_beyond_analysis_contract"
                    elif dry_run:
                        status = "would_open"
                        reason = "dry_run_best_eligible_candidate"
                    else:
                        live_daily_count = _daily_operation_count(
                            db,
                            participant,
                            season_id,
                            execution_at,
                            dry_run=False,
                        )
                        live_open_count = _open_position_count(
                            db,
                            participant,
                            season_id,
                            execution_at,
                            dry_run=False,
                        )
                        live_cash = _available_contest_cash(
                            db,
                            int(participant["user_id"]),
                            season_id,
                        )
                        if live_daily_count >= policy.daily_operation_limit:
                            status = "quota_reached"
                            reason = "quota_reached_during_analysis"
                        elif live_open_count >= policy.max_open_positions:
                            status = "capacity_reached"
                            reason = "capacity_reached_during_analysis"
                        elif live_cash < policy.margin:
                            status = "no_cash"
                            reason = "insufficient_contest_cash_during_analysis"
                        else:
                            operation_id, recommendation_id = _open_selected_operation(
                                db,
                                participant=participant,
                                season_id=season_id,
                                candidate=selected,
                                policy=policy,
                                execution_entry=execution_entry,
                                executed_at=execution_at,
                            )
                            status = "opened"
                            reason = "best_eligible_candidate_opened"
                _persist_candidate_observations(
                    db,
                    scan_run_id=scan_run_id,
                    participant=participant,
                    season_id=int(season["id"]),
                    policy=policy,
                    slot=slot,
                    candidates=candidates,
                    selected=selected,
                )
                db.execute(
                    """
                    UPDATE autonomous_scan_runs
                    SET analyzed_at = ?, status = ?, reason_code = ?,
                        candidates_evaluated = ?, candidates_blocked = ?,
                        candidates_eligible = ?, selected_symbol = ?,
                        selected_side = ?, selected_tp_probability = ?,
                        selected_sl_probability = ?,
                        selected_unresolved_probability = ?, selected_edge = ?,
                        recommendation_id = ?, operation_id = ?, artifact_id = ?,
                        duration_ms = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'running'
                    """,
                    (
                        decision_analyzed_at.isoformat(),
                        status,
                        reason,
                        evaluated,
                        blocked,
                        eligible,
                        selected.symbol if selected else None,
                        selected.side if selected else None,
                        selected.tp_probability if selected else None,
                        selected.sl_probability if selected else None,
                        selected.unresolved_probability if selected else None,
                        selected.edge if selected else None,
                        recommendation_id,
                        operation_id,
                        selected.artifact_id if selected else None,
                        round((time.perf_counter() - scan_started) * 1000),
                        scan_run_id,
                    ),
                )
                db.execute(
                    "UPDATE autonomous_contest_participants SET last_scan_slot_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (slot.isoformat(), int(participant["id"])),
                )
        except Exception as exc:
            with connect_factory() as db:
                db.execute(
                    """
                    UPDATE autonomous_scan_runs
                    SET status = 'failed', reason_code = ?, duration_ms = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'running'
                    """,
                    (
                        f"{type(exc).__name__}:{exc}",
                        round((time.perf_counter() - scan_started) * 1000),
                        scan_run_id,
                    ),
                )
            logger.exception("autonomous scan persistence failed")
            status = "failed"
            reason = f"{type(exc).__name__}:{exc}"
        scans.append(
            {
                "participant": policy.code,
                "scan_run_id": scan_run_id,
                "slot": slot.isoformat(),
                "status": status,
                "reason": reason,
                "evaluated": evaluated,
                "blocked": blocked,
                "eligible": eligible,
                "operation_id": operation_id,
            }
        )
    return {
        "policy_version": POLICY_VERSION,
        "dry_run": dry_run,
        "season_id": int(season["id"]),
        "fresh_price_symbols": len(prices),
        "kline_cache": shared_kline_loader.stats(),
        "scans": scans,
        "duration_ms": round((time.perf_counter() - started) * 1000),
    }


def _evaluate_path(
    candles: list[dict],
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
) -> dict:
    terminal = None
    for candle in candles:
        terminal = float(candle["close"])
        if side == "long":
            tp_hit = float(candle["high"]) >= take_profit
            sl_hit = float(candle["low"]) <= stop_loss
        else:
            tp_hit = float(candle["low"]) <= take_profit
            sl_hit = float(candle["high"]) >= stop_loss
        if tp_hit and sl_hit:
            return {
                "first_touch": "ambiguous",
                "first_touch_at": datetime.fromtimestamp(
                    int(candle["open_time_ms"]) / 1000, tz=timezone.utc
                ).isoformat(),
                "terminal_price": terminal,
                "r_multiple": None,
            }
        if tp_hit or sl_hit:
            label = "tp" if tp_hit else "sl"
            return {
                "first_touch": label,
                "first_touch_at": datetime.fromtimestamp(
                    int(candle["open_time_ms"]) / 1000, tz=timezone.utc
                ).isoformat(),
                "terminal_price": take_profit if tp_hit else stop_loss,
                "r_multiple": 1.0 if tp_hit else -1.0,
            }
    if terminal is None:
        raise ValueError("candidate_future_path_empty")
    risk = abs(entry - stop_loss)
    terminal_r = (
        (terminal - entry) / risk
        if side == "long"
        else (entry - terminal) / risk
    )
    return {
        "first_touch": "unresolved",
        "first_touch_at": None,
        "terminal_price": terminal,
        "r_multiple": terminal_r,
    }


def evaluate_due_candidates(
    connect_factory,
    *,
    now: datetime | None = None,
    loader: KlineLoader = market_data.get_klines,
    max_groups: int = 6,
) -> dict:
    current = _as_utc(now or utc_now())
    with connect_factory() as db:
        rows = [
            dict(row)
            for row in db.execute(
                """
                SELECT *
                FROM autonomous_candidate_observations
                WHERE outcome_status = 'pending'
                  AND analysis_status = 'evaluated'
                  AND evaluation_due_at <= ?
                ORDER BY evaluation_due_at ASC, id ASC
                LIMIT 96
                """,
                (current.isoformat(),),
            ).fetchall()
        ]
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (
            row["symbol"],
            str(row["analyzed_at"]),
            str(row["evaluation_due_at"]),
        )
        groups.setdefault(key, []).append(row)
    evaluated = failures = 0
    for (symbol, analyzed_at, due_at), members in list(groups.items())[:max_groups]:
        start_ms = int(_as_utc(analyzed_at).timestamp() * 1000)
        end_ms = int(_as_utc(due_at).timestamp() * 1000)
        try:
            raw = fetch_klines_range(
                symbol,
                "1m",
                start_ms,
                end_ms,
                loader=loader,
            )
            candles = [
                normalize_kline(row)
                for row in raw
                if int(row[0]) >= start_ms and int(row[0]) < end_ms
            ]
            if not candles:
                raise ValueError("candidate_future_klines_unavailable")
            with connect_factory() as db:
                for member in members:
                    outcome = _evaluate_path(
                        candles,
                        side=str(member["side"]),
                        entry=float(member["entry"]),
                        take_profit=float(member["take_profit"]),
                        stop_loss=float(member["stop_loss"]),
                    )
                    db.execute(
                        """
                        UPDATE autonomous_candidate_observations
                        SET outcome_status = 'evaluated', first_touch = ?,
                            first_touch_at = ?, terminal_price = ?,
                            r_multiple = ?, evaluated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND outcome_status = 'pending'
                        """,
                        (
                            outcome["first_touch"],
                            outcome["first_touch_at"],
                            outcome["terminal_price"],
                            outcome["r_multiple"],
                            int(member["id"]),
                        ),
                    )
                    evaluated += 1
        except Exception:
            failures += 1
            logger.exception("autonomous candidate evaluation failed")
    return {
        "evaluated_candidates": evaluated,
        "failed_groups": failures,
        "pending_rows_read": len(rows),
    }


def scanner_enabled_from_env() -> bool:
    return os.environ.get("AUTONOMOUS_CONTEST_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


__all__ = (
    "NON_PANEL_STORAGE_CAP_PER_UTC_DAY",
    "PARTICIPANT_POLICIES",
    "POLICY_VERSION",
    "ParticipantPolicy",
    "SYMBOLS",
    "analyze_candidates",
    "ensure_autonomous_storage",
    "ensure_contest_entries",
    "ensure_participants",
    "evaluate_due_candidates",
    "is_canonical_panel",
    "load_horizon_sigma",
    "run_due_scans",
    "scan_slot",
    "scanner_enabled_from_env",
    "select_candidate",
    "symmetric_geometry",
)
