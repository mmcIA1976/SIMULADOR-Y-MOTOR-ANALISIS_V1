from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

import market_data
from app import (
    ONE_MINUTE_MS,
    expire_due_pending_limit_operations,
    finalize_due_observations,
    get_operation_klines_1m,
    refresh_learning_conclusions,
    refresh_learning_evaluations,
    refresh_symbol_active_operations,
)
from db import close_pool, connect
from market_price_state import (
    MARKET_PRICE_SOURCE,
    ensure_market_price_state_table,
    publish_market_prices,
    watched_market_symbols,
)
from order_book_observation import OrderBookObservationTracker
from order_book_observation_state import (
    ensure_order_book_observation_state_table,
    publish_order_book_observations,
)
from operation_worker_status import ensure_worker_status_table, upsert_worker_status
from versioning import APP_VERSION, ENGINE_VERSION


logger = logging.getLogger("operation_worker")


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(float(raw), minimum)
    except ValueError:
        return default


def env_int(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(int(raw), minimum)
    except ValueError:
        return default


@dataclass(frozen=True)
class WorkerSettings:
    poll_seconds: float = 10.0
    reconcile_seconds: float = 60.0
    heartbeat_seconds: float = 60.0
    reconcile_overlap_minutes: int = 2
    startup_lookback_minutes: int = 10_080
    startup_max_kline_pages: int = 12
    recent_max_kline_pages: int = 2
    persist_exit_window: bool = False
    dry_run: bool = False
    order_book_observation_enabled: bool = False
    order_book_window_seconds: int = 60
    order_book_publish_seconds: int = 30

    @classmethod
    def from_env(cls) -> "WorkerSettings":
        return cls(
            poll_seconds=env_float("OPERATION_WORKER_POLL_SECONDS", 10.0, 2.0),
            reconcile_seconds=env_float("OPERATION_WORKER_RECONCILE_SECONDS", 60.0, 15.0),
            heartbeat_seconds=env_float("OPERATION_WORKER_HEARTBEAT_SECONDS", 60.0, 15.0),
            reconcile_overlap_minutes=env_int("OPERATION_WORKER_RECONCILE_OVERLAP_MINUTES", 2, 1),
            startup_lookback_minutes=env_int("OPERATION_WORKER_STARTUP_LOOKBACK_MINUTES", 10_080, 60),
            startup_max_kline_pages=env_int("OPERATION_WORKER_STARTUP_MAX_KLINE_PAGES", 12, 1),
            recent_max_kline_pages=env_int("OPERATION_WORKER_RECENT_MAX_KLINE_PAGES", 2, 1),
            persist_exit_window=env_bool("OPERATION_WORKER_PERSIST_EXIT_WINDOW", False),
            dry_run=env_bool("OPERATION_WORKER_DRY_RUN", True),
            order_book_observation_enabled=env_bool(
                "ORDER_BOOK_OBSERVATION_ENABLED",
                True,
            ),
            order_book_window_seconds=env_int(
                "ORDER_BOOK_OBSERVATION_WINDOW_SECONDS",
                60,
                20,
            ),
            order_book_publish_seconds=env_int(
                "ORDER_BOOK_OBSERVATION_PUBLISH_SECONDS",
                30,
                10,
            ),
        )


@dataclass
class WorkerState:
    last_reconcile_ms: int | None = None
    cycles: int = 0
    order_book_tracker: OrderBookObservationTracker = field(
        default_factory=OrderBookObservationTracker
    )
    order_book_last_publish_ms: dict[str, int] = field(default_factory=dict)
    order_book_last_published_status: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SymbolMarketInput:
    symbol: str
    price: float
    klines: list[list]


ConnectFactory = Callable[[], AbstractContextManager]
PriceLoader = Callable[[str], float]
KlineLoader = Callable[..., list[list]]
DepthLoader = Callable[..., dict]
TradeLoader = Callable[..., list[dict]]


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def timestamp_ms(value) -> int:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def log_event(event: str, **fields) -> None:
    logger.info(
        json.dumps(
            {
                "event": event,
                "app_version": APP_VERSION,
                "engine_version": ENGINE_VERSION,
                **fields,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def publish_runtime_status(
    settings: WorkerSettings,
    started_at: str,
    lifecycle_status: str,
    result: dict | None = None,
    last_error: str | None = None,
    connect_factory: ConnectFactory = connect,
) -> bool:
    """Publish one replaceable heartbeat row without interrupting the worker."""
    heartbeat_at = datetime.now(timezone.utc).isoformat()
    try:
        with connect_factory() as db:
            upsert_worker_status(
                db,
                lifecycle_status=lifecycle_status,
                app_version=APP_VERSION,
                engine_version=ENGINE_VERSION,
                dry_run=settings.dry_run,
                persist_exit_window=settings.persist_exit_window,
                poll_seconds=settings.poll_seconds,
                reconcile_seconds=settings.reconcile_seconds,
                heartbeat_seconds=settings.heartbeat_seconds,
                started_at=started_at,
                heartbeat_at=heartbeat_at,
                result=result,
                last_error=last_error,
            )
        return True
    except Exception as exc:
        log_event(
            "worker_status_publish_failed",
            lifecycle_status=lifecycle_status,
            error=str(exc),
        )
        return False


def load_active_symbol_starts(connect_factory: ConnectFactory = connect) -> dict[str, int]:
    """Read active symbols and their earliest relevant market time without writing."""
    with connect_factory() as db:
        rows = db.execute(
            """
            SELECT
                symbol,
                MIN(
                    COALESCE(
                        NULLIF(started_at, '')::timestamptz,
                        created_at::timestamptz
                    )
                ) AS scan_start
            FROM operations
            WHERE status IN ('OPEN', 'PENDING_ENTRY')
            GROUP BY symbol
            ORDER BY symbol
            """
        ).fetchall()
    starts: dict[str, int] = {}
    for row in rows:
        symbol = str(row["symbol"]).upper()
        try:
            starts[symbol] = timestamp_ms(row["scan_start"])
        except (TypeError, ValueError):
            starts[symbol] = utc_now_ms() - ONE_MINUTE_MS
    return starts


def load_watched_market_symbols(
    connect_factory: ConnectFactory = connect,
) -> set[str]:
    """Read temporary UI demand without creating an unbounded queue."""
    with connect_factory() as db:
        return watched_market_symbols(db)


def collect_market_inputs(
    symbol_starts: dict[str, int],
    watched_symbols: set[str],
    state: WorkerState,
    settings: WorkerSettings,
    now_ms: int,
    price_loader: PriceLoader = market_data.get_price,
    kline_loader: KlineLoader = get_operation_klines_1m,
) -> tuple[list[SymbolMarketInput], bool, int, dict[str, float]]:
    reconcile_due = (
        state.last_reconcile_ms is None
        or now_ms - state.last_reconcile_ms >= int(settings.reconcile_seconds * 1000)
    )
    first_reconciliation = state.last_reconcile_ms is None
    inputs: list[SymbolMarketInput] = []
    failures = 0
    requested_symbols = sorted(set(symbol_starts).union(watched_symbols))
    if price_loader is market_data.get_price:
        price_snapshot = market_data.get_prices(
            requested_symbols,
            allow_stale=False,
        )
    else:
        price_snapshot = {}
        for symbol in requested_symbols:
            try:
                price_snapshot[symbol] = float(price_loader(symbol))
            except Exception as exc:
                failures += 1
                log_event(
                    "worker_market_price_failed",
                    symbol=symbol,
                    error=str(exc),
                )
    for symbol in requested_symbols:
        if symbol not in price_snapshot:
            if price_loader is market_data.get_price:
                failures += 1
                log_event(
                    "worker_market_price_failed",
                    symbol=symbol,
                    error="batch_price_missing",
                )
            continue
        price = float(price_snapshot[symbol])
        earliest_start_ms = symbol_starts.get(symbol)
        try:
            klines: list[list] = []
            if reconcile_due and earliest_start_ms is not None:
                if first_reconciliation:
                    startup_floor_ms = now_ms - settings.startup_lookback_minutes * ONE_MINUTE_MS
                    scan_start_ms = max(earliest_start_ms, startup_floor_ms)
                    max_pages = settings.startup_max_kline_pages
                else:
                    overlap_ms = settings.reconcile_overlap_minutes * ONE_MINUTE_MS
                    scan_start_ms = max(earliest_start_ms, int(state.last_reconcile_ms) - overlap_ms)
                    max_pages = settings.recent_max_kline_pages
                klines = kline_loader(
                    symbol,
                    scan_start_ms,
                    now_ms,
                    max_pages=max_pages,
                )
            inputs.append(SymbolMarketInput(symbol=symbol, price=price, klines=klines))
        except Exception as exc:
            failures += 1
            log_event("worker_market_input_failed", symbol=symbol, error=str(exc))
    return inputs, reconcile_due, failures, price_snapshot


def collect_order_book_observations(
    state: WorkerState,
    symbols: set[str],
    now_ms: int,
    *,
    depth_loader: DepthLoader = market_data.get_depth,
    trade_loader: TradeLoader = market_data.get_agg_trades,
) -> tuple[dict[str, dict], int]:
    observations: dict[str, dict] = {}
    failures = 0
    for symbol in sorted(symbols):
        try:
            depth = depth_loader(symbol, 100)
            try:
                observation_capture_ms = int(
                    depth.get("receivedAt") or now_ms
                )
            except (AttributeError, TypeError, ValueError, OverflowError):
                observation_capture_ms = int(now_ms)
            trade_start = state.order_book_tracker.trade_start_time_ms(
                symbol,
                observation_capture_ms,
            )
            trades = trade_loader(
                symbol,
                1000,
                start_time_ms=trade_start,
                end_time_ms=observation_capture_ms,
            )
            observations[symbol] = state.order_book_tracker.observe(
                symbol,
                depth,
                trades,
                captured_at_ms=observation_capture_ms,
            )
        except Exception as exc:
            failures += 1
            log_event(
                "worker_order_book_observation_failed",
                symbol=symbol,
                error=str(exc),
            )
    return observations, failures


def run_worker_cycle(
    state: WorkerState,
    settings: WorkerSettings,
    *,
    connect_factory: ConnectFactory = connect,
    price_loader: PriceLoader = market_data.get_price,
    kline_loader: KlineLoader = get_operation_klines_1m,
    depth_loader: DepthLoader = market_data.get_depth,
    trade_loader: TradeLoader = market_data.get_agg_trades,
    now_ms: int | None = None,
) -> dict:
    """Process one cycle; quotes replace state instead of appending history."""
    cycle_started_ms = now_ms if now_ms is not None else utc_now_ms()
    symbol_starts = load_active_symbol_starts(connect_factory)
    watched_symbols = load_watched_market_symbols(connect_factory)
    market_inputs, reconcile_due, failures, price_snapshot = collect_market_inputs(
        symbol_starts,
        watched_symbols,
        state,
        settings,
        cycle_started_ms,
        price_loader=price_loader,
        kline_loader=kline_loader,
    )
    order_book_observations: dict[str, dict] = {}
    order_book_observation_failures = 0
    if settings.order_book_observation_enabled and price_snapshot:
        (
            order_book_observations,
            order_book_observation_failures,
        ) = collect_order_book_observations(
            state,
            set(price_snapshot),
            cycle_started_ms,
            depth_loader=depth_loader,
            trade_loader=trade_loader,
        )

    activated: list[dict] = []
    closed: list[dict] = []
    finalized: list[dict] = []
    published_price_states = 0
    published_order_book_states = 0
    if not settings.dry_run:
        if price_snapshot:
            try:
                with connect_factory() as db:
                    published_price_states = publish_market_prices(
                        db,
                        price_snapshot,
                        captured_at=datetime.fromtimestamp(
                            cycle_started_ms / 1000,
                            tz=timezone.utc,
                        ),
                        source=MARKET_PRICE_SOURCE,
                    )
            except Exception as exc:
                failures += 1
                log_event("worker_market_price_publish_failed", error=str(exc))
        due_order_book = {
            symbol: observation
            for symbol, observation in order_book_observations.items()
            if (
                symbol not in state.order_book_last_publish_ms
                or str(observation.get("status"))
                != state.order_book_last_published_status.get(symbol)
                or cycle_started_ms - state.order_book_last_publish_ms[symbol]
                >= int(settings.order_book_publish_seconds * 1000)
            )
        }
        if due_order_book:
            try:
                with connect_factory() as db:
                    published_order_book_states = publish_order_book_observations(
                        db,
                        due_order_book,
                    )
                for symbol in due_order_book:
                    state.order_book_last_publish_ms[symbol] = cycle_started_ms
                    state.order_book_last_published_status[symbol] = str(
                        due_order_book[symbol].get("status")
                    )
            except Exception as exc:
                order_book_observation_failures += 1
                log_event(
                    "worker_order_book_observation_publish_failed",
                    error=str(exc),
                )
        market_symbols = {item.symbol for item in market_inputs}
        for missing_symbol in set(symbol_starts).difference(market_symbols):
            try:
                with connect_factory() as db:
                    expired_by_id = expire_due_pending_limit_operations(
                        db,
                        missing_symbol,
                    )
                closed.extend(expired_by_id.values())
            except Exception as exc:
                failures += 1
                log_event(
                    "worker_limit_clock_processing_failed",
                    symbol=missing_symbol,
                    error=str(exc),
                )
        for market_input in market_inputs:
            if market_input.symbol not in symbol_starts:
                continue
            try:
                with connect_factory() as db:
                    activated_by_id, closed_by_id = refresh_symbol_active_operations(
                        db,
                        market_input.symbol,
                        market_input.price,
                        market_klines=market_input.klines,
                        persist_exit_window=settings.persist_exit_window,
                    )
            except Exception as exc:
                failures += 1
                log_event(
                    "worker_symbol_processing_failed",
                    symbol=market_input.symbol,
                    error=str(exc),
                )
                continue
            activated.extend(activated_by_id.values())
            closed.extend(closed_by_id.values())

        if closed:
            with connect_factory() as db:
                refresh_learning_conclusions(db)
                refresh_learning_evaluations(db)
        if reconcile_due:
            with connect_factory() as db:
                finalized = finalize_due_observations(db)

    # If any symbol failed, keep the old cursor so the next cycle replays the
    # missed market interval instead of silently skipping it.
    if reconcile_due and failures == 0:
        state.last_reconcile_ms = cycle_started_ms
    state.cycles += 1
    return {
        "cycle": state.cycles,
        "active_symbols": len(symbol_starts),
        "watched_symbols": len(watched_symbols),
        "requested_symbols": len(set(symbol_starts).union(watched_symbols)),
        "market_symbols": len(market_inputs),
        "activated": len(activated),
        "closed": len(closed),
        "finalized_observations": len(finalized),
        "failures": failures,
        "reconciled": reconcile_due,
        "persisted_price_samples": 0,
        "published_price_states": published_price_states,
        "order_book_observation_enabled": settings.order_book_observation_enabled,
        "order_book_observation_symbols": len(order_book_observations),
        "order_book_observation_failures": order_book_observation_failures,
        "published_order_book_states": published_order_book_states,
        "order_book_storage_strategy": "single_row_upsert_per_symbol_no_raw_depth",
        "persist_exit_window": settings.persist_exit_window,
        "dry_run": settings.dry_run,
    }


def run_forever(settings: WorkerSettings | None = None) -> None:
    settings = settings or WorkerSettings.from_env()
    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    state = WorkerState(
        order_book_tracker=OrderBookObservationTracker(
            window_seconds=settings.order_book_window_seconds,
        )
    )
    last_heartbeat = 0.0
    started_at = datetime.now(timezone.utc).isoformat()
    last_result: dict | None = None
    try:
        with connect() as db:
            ensure_market_price_state_table(db)
            ensure_worker_status_table(db)
            ensure_order_book_observation_state_table(db)
    except Exception as exc:
        log_event("worker_status_storage_failed", error=str(exc))
    publish_runtime_status(settings, started_at, "starting")
    log_event(
        "operation_worker_started",
        poll_seconds=settings.poll_seconds,
        reconcile_seconds=settings.reconcile_seconds,
        persist_exit_window=settings.persist_exit_window,
        dry_run=settings.dry_run,
        order_book_observation_enabled=settings.order_book_observation_enabled,
        order_book_window_seconds=settings.order_book_window_seconds,
        order_book_publish_seconds=settings.order_book_publish_seconds,
    )
    try:
        while not stop_event.is_set():
            cycle_started = time.monotonic()
            try:
                result = run_worker_cycle(state, settings)
                last_result = result
            except Exception as exc:
                logger.exception(
                    json.dumps(
                        {
                            "event": "operation_worker_cycle_failed",
                            "error": str(exc),
                            "app_version": APP_VERSION,
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    )
                )
                result = None
                publish_runtime_status(
                    settings,
                    started_at,
                    "degraded",
                    result=last_result,
                    last_error=str(exc),
                )
            now_monotonic = time.monotonic()
            if result is not None and (
                result["activated"]
                or result["closed"]
                or result["finalized_observations"]
                or result["failures"]
                or result["order_book_observation_failures"]
                or now_monotonic - last_heartbeat >= settings.heartbeat_seconds
            ):
                lifecycle_status = "degraded" if result["failures"] else "running"
                publish_runtime_status(
                    settings,
                    started_at,
                    lifecycle_status,
                    result=result,
                    last_error=(
                        "Uno o mas simbolos fallaron en el ultimo ciclo; consultar logs."
                        if result["failures"]
                        else None
                    ),
                )
                log_event("operation_worker_heartbeat", **result)
                last_heartbeat = now_monotonic
            wait_seconds = max(0.0, settings.poll_seconds - (time.monotonic() - cycle_started))
            stop_event.wait(wait_seconds)
    finally:
        publish_runtime_status(
            settings,
            started_at,
            "stopped",
            result=last_result,
        )
        close_pool()
        log_event("operation_worker_stopped", cycles=state.cycles)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
    run_forever()
