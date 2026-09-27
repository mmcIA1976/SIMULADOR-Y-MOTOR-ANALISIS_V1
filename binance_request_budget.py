"""Bound Futures REST traffic across threads, processes and deployments.

One replaceable PostgreSQL row, no request history. Processes lease small
budgets and check the shared circuit every ten seconds, not on every tick.
The budget row lock is released before each upstream call.
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlsplit

NORMAL_WEIGHT = 1200
CRITICAL_WEIGHT = 1800
NORMAL_REQUESTS = 120
CRITICAL_REQUESTS = 150  # Also below 1000 requests / 5 min on /futures/data.
SHARED_SYNC_SECONDS = 10
_critical = ContextVar("binance_critical", default=False)


class BinanceDeferred(RuntimeError):
    """No upstream request was sent; quota/circuit needs time to recover."""

    def __init__(self, message, *, retry_after_seconds=None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@contextmanager
def critical_market_requests():
    token = _critical.set(True)
    try:
        yield
    finally:
        _critical.reset(token)


@contextmanager
def normal_market_requests():
    """Historical/optional work must not inherit an exit's critical reserve."""
    token = _critical.set(False)
    try:
        yield
    finally:
        _critical.reset(token)


def request_weight(url: str) -> int:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    endpoint = parsed.path.rsplit("/", 1)[-1]
    limit = int(query.get("limit", [500])[0])
    if endpoint == "aggTrades":
        return 20
    if endpoint == "depth":
        return 2 if limit <= 50 else 5 if limit <= 100 else 10 if limit <= 500 else 20
    if endpoint in {"klines", "continuousKlines", "indexPriceKlines", "markPriceKlines"}:
        return 1 if limit < 100 else 2 if limit < 500 else 5 if limit <= 1000 else 10
    if endpoint == "24hr":
        return 1 if "symbol" in query else 40
    if endpoint == "bookTicker":
        return 2 if "symbol" in query else 5
    if endpoint == "price":
        return 1 if "symbol" in query else 2
    if endpoint == "premiumIndex":
        return 1 if "symbol" in query else 10
    return 1  # Zero-weight data endpoints still consume the request budget.


def retry_deadline(headers, body: str, code: int, now: float) -> float:
    import re
    deadlines = [now + (120 if code == 418 else 60)]
    match = re.search(r"banned until (\d{12,})", body)
    if match:
        deadlines.append(int(match.group(1)) / 1000 + 2)
    retry = (headers or {}).get("Retry-After")
    if retry:
        try:
            deadlines.append(now + float(retry))
        except (TypeError, ValueError):
            try:
                deadlines.append(parsedate_to_datetime(retry).timestamp())
            except (TypeError, ValueError, OverflowError):
                pass
    return max(deadlines)


class PostgresBudgetStore:
    def exchange(self, *, now, weight=0, requests=0, critical=False,
                 observed=0, blocked_until=0, reason=""):
        # Lazy import avoids db -> learning -> market_data import cycles.
        from db import connect
        with connect() as db:
            db.execute("SET LOCAL statement_timeout = '2s'")
            row = dict(db.execute(
                "SELECT * FROM binance_request_budget WHERE id = 1 FOR UPDATE"
            ).fetchone())
            updated, granted = exchange_state(
                row, now=now, weight=weight, requests=requests,
                critical=critical, observed=observed,
                blocked_until=blocked_until, reason=reason,
            )
            if updated != row:
                db.execute(
                    """UPDATE binance_request_budget SET minute = ?, weight = ?,
                       requests = ?, observed = ?, blocked_until = ?, reason = ?
                       WHERE id = 1""",
                    tuple(updated[key] for key in (
                        "minute", "weight", "requests", "observed", "blocked_until", "reason"
                    )),
                )
            return updated, granted


def exchange_state(row, *, now, weight=0, requests=0, critical=False,
                   observed=0, blocked_until=0, reason=""):
    row = dict(row)
    minute = int(now // 60)
    if row["minute"] != minute:
        row.update(minute=minute, weight=0, requests=0, observed=0)
    if row["reason"] and now >= row["blocked_until"]:
        row["reason"] = ""
    row["observed"] = max(row["observed"], observed)
    if blocked_until > row["blocked_until"]:
        row.update(blocked_until=blocked_until, reason=reason[:120])
    cap_w = CRITICAL_WEIGHT if critical else NORMAL_WEIGHT
    cap_r = CRITICAL_REQUESTS if critical else NORMAL_REQUESTS
    used = max(row["weight"], row["observed"])
    granted = (now >= row["blocked_until"] and used + weight <= cap_w
               and row["requests"] + requests <= cap_r)
    if granted and (weight or requests):
        row.update(weight=used + weight, requests=row["requests"] + requests)
    return row, granted


class MemoryBudgetStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.row = dict(id=1, minute=-1, weight=0, requests=0, observed=0,
                        blocked_until=0.0, reason="")

    def exchange(self, **kwargs):
        with self.lock:
            self.row, granted = exchange_state(self.row, **kwargs)
            return dict(self.row), granted


class RequestBudget:
    def __init__(self, store=None, clock=time.time):
        self.store = store
        self.clock = clock
        self.lock = threading.RLock()
        self.leases = {}
        self.minute = -1
        self.next_sync = 0.0
        self.blocked_until = 0.0
        self.observed = 0
        self.reason = ""
        self.deferred = 0
        self.sent = 0
        self.sync_error = ""
        self.endpoint_counts = {}
        self.last_observed_endpoint = None
        self.last_observed_delta = 0

    def _store(self):
        if self.store is None:
            shared = os.getenv("BINANCE_SHARED_BUDGET", "").lower()
            # Production must never silently use independent process budgets.
            self.store = (PostgresBudgetStore() if os.getenv("RAILWAY_ENVIRONMENT")
                          or shared in {"1", "true"} else MemoryBudgetStore())
        return self.store

    def _exchange(self, now, **kwargs):
        try:
            row, granted = self._store().exchange(
                now=now, observed=self.observed,
                blocked_until=self.blocked_until, reason=self.reason, **kwargs
            )
        except Exception as exc:
            self.sync_error = type(exc).__name__
            self.next_sync = now + SHARED_SYNC_SECONDS
            raise BinanceDeferred("binance_budget_store_unavailable:" + self.sync_error) from exc
        self.sync_error = ""
        self.blocked_until = max(self.blocked_until, row["blocked_until"])
        self.observed = max(self.observed, row["observed"])
        self.reason = row["reason"]
        self.next_sync = now + SHARED_SYNC_SECONDS
        return granted

    def acquire(self, url):
        with self.lock:
            now = self.clock()
            minute = int(now // 60)
            if minute != self.minute:
                self.minute, self.observed = minute, 0
                self.leases.clear()
                self.endpoint_counts.clear()
                self.last_observed_endpoint = None
                self.last_observed_delta = 0
                self.next_sync = 0
            try:
                if now < self.blocked_until:
                    raise BinanceDeferred(f"binance_circuit_open_until:{self.blocked_until:.3f}")
                if now >= self.next_sync:
                    self._exchange(now)
                if self.sync_error:
                    raise BinanceDeferred("binance_budget_store_unavailable:" + self.sync_error)
                if now < self.blocked_until:
                    raise BinanceDeferred(f"binance_circuit_open_until:{self.blocked_until:.3f}")
                critical = _critical.get()
                cost = request_weight(url)
                cap = CRITICAL_WEIGHT if critical else NORMAL_WEIGHT
                if self.observed + cost > cap:
                    raise BinanceDeferred("binance_observed_weight_budget_exhausted")
                remaining_w, remaining_r = self.leases.get(critical, (0, 0))
                if remaining_w < cost or remaining_r < 1:
                    # Unused reservations are never refunded: safe on crashes/restarts.
                    weight = max(100, cost) if remaining_w < cost else 0
                    requests = 10 if remaining_r < 1 else 0
                    if not self._exchange(now, weight=weight, requests=requests, critical=critical):
                        raise BinanceDeferred("binance_shared_budget_exhausted")
                    remaining_w += weight
                    remaining_r += requests
                self.leases[critical] = remaining_w - cost, remaining_r - 1
                self.sent += 1
                endpoint = urlsplit(url).path.rsplit("/", 1)[-1]
                category = endpoint if endpoint in {
                    "price", "klines", "depth", "aggTrades", "premiumIndex",
                    "openInterest", "openInterestHist", "fundingRate", "24hr",
                    "bookTicker", "globalLongShortAccountRatio", "takerlongshortRatio",
                } else "other"
                bucket = self.endpoint_counts.setdefault(category, {"requests": 0, "weight": 0})
                bucket["requests"] += 1
                bucket["weight"] += cost
            except BinanceDeferred as exc:
                self.deferred += 1
                if exc.retry_after_seconds is None:
                    deadline = (now + SHARED_SYNC_SECONDS if self.sync_error else
                                max(self.blocked_until, (int(now // 60) + 1) * 60 + 2))
                    exc.retry_after_seconds = max(1.0, deadline - now)
                raise

    def observe(self, headers, *, code=200, body="", url=None):
        with self.lock:
            now = self.clock()
            minute = int(now // 60)
            if minute != self.minute:
                self.minute, self.observed = minute, 0
                self.leases.clear()
                self.next_sync = 0
                self.endpoint_counts.clear()
            try:
                used = int((headers or {}).get("X-MBX-USED-WEIGHT-1M", 0))
            except (ValueError, TypeError):
                used = 0
            delta = max(0, used - self.observed)
            if delta:
                self.last_observed_endpoint = urlsplit(url).path if url else None
                self.last_observed_delta = delta
            self.observed = max(self.observed, used)
            if code in (418, 429):
                self.blocked_until = max(self.blocked_until, retry_deadline(headers, body, code, now))
                self.reason = f"binance_http_{code}"
                self.leases.clear()
                # Persist immediately, but even on DB failure the local ban remains.
                try:
                    self._exchange(now)
                except BinanceDeferred:
                    pass

    def status(self):
        with self.lock:
            return dict(blocked_until_ms=int(self.blocked_until * 1000),
                        observed_weight_1m=self.observed, requests_sent=self.sent,
                        requests_deferred=self.deferred, reason=self.reason,
                        coordination_error=self.sync_error,
                        normal_weight_limit=NORMAL_WEIGHT,
                        critical_weight_limit=CRITICAL_WEIGHT,
                        endpoint_counts={key: dict(value) for key, value in self.endpoint_counts.items()},
                        last_observed_endpoint=self.last_observed_endpoint,
                        last_observed_delta=self.last_observed_delta)


budget = RequestBudget()


def ensure_request_budget_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS binance_request_budget (
        id SMALLINT PRIMARY KEY CHECK (id = 1),
        minute BIGINT NOT NULL DEFAULT -1,
        weight INTEGER NOT NULL DEFAULT 0,
        requests INTEGER NOT NULL DEFAULT 0,
        observed INTEGER NOT NULL DEFAULT 0,
        blocked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
        reason VARCHAR(120) NOT NULL DEFAULT ''
    )""")
    db.execute("INSERT INTO binance_request_budget(id) VALUES (1) ON CONFLICT DO NOTHING")
    db.execute("ALTER TABLE binance_request_budget ENABLE ROW LEVEL SECURITY")
