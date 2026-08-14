from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping


MARKET_PRICE_AUTHORITY = "operation_worker"
MARKET_PRICE_SOURCE = "binance_usdm_futures_ticker_batch"
MARKET_PRICE_FRESH_SECONDS = 35
MARKET_PRICE_WATCH_TTL_SECONDS = 300
MARKET_PRICE_WATCH_RENEW_SECONDS = 120

_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")


def normalize_market_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not _SYMBOL_PATTERN.fullmatch(normalized):
        raise ValueError("Simbolo de mercado no valido")
    return normalized


def _as_utc_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00").replace(" ", "T")
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_market_price_state_table(db) -> None:
    """Create the constant-size internal store used by worker and web."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS market_price_state (
            symbol TEXT PRIMARY KEY
                CHECK(symbol ~ '^[A-Z0-9]{5,20}$'),
            price DOUBLE PRECISION CHECK(price IS NULL OR price > 0),
            source TEXT,
            publisher TEXT NOT NULL DEFAULT 'operation_worker'
                CHECK(publisher = 'operation_worker'),
            captured_at TIMESTAMPTZ,
            watch_until TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(
                (price IS NULL AND captured_at IS NULL AND source IS NULL)
                OR
                (price IS NOT NULL AND captured_at IS NOT NULL
                    AND source IS NOT NULL)
            )
        )
        """
    )
    db.executescript(
        """
        ALTER TABLE market_price_state ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE market_price_state FROM anon, authenticated;
        GRANT ALL PRIVILEGES ON TABLE market_price_state TO postgres, service_role;
        """
    )


def request_market_price_watch(
    db,
    symbol: str,
    *,
    requested_at: datetime | None = None,
    ttl_seconds: int = MARKET_PRICE_WATCH_TTL_SECONDS,
    renew_seconds: int = MARKET_PRICE_WATCH_RENEW_SECONDS,
) -> str:
    """Register bounded demand without writing on every browser poll."""
    normalized = normalize_market_symbol(symbol)
    now = (requested_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    watch_until = now + timedelta(seconds=max(int(ttl_seconds), 30))
    renew_before = now + timedelta(seconds=max(int(renew_seconds), 0))
    db.execute(
        """
        INSERT INTO market_price_state (
            symbol, watch_until, requested_at, updated_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT (symbol) DO UPDATE SET
            watch_until = excluded.watch_until,
            requested_at = excluded.requested_at,
            updated_at = excluded.updated_at
        WHERE market_price_state.watch_until < ?
        RETURNING symbol
        """,
        (
            normalized,
            watch_until.isoformat(),
            now.isoformat(),
            now.isoformat(),
            renew_before.isoformat(),
        ),
    )
    return normalized


def get_market_price_row(db, symbol: str) -> dict | None:
    normalized = normalize_market_symbol(symbol)
    row = db.execute(
        """
        SELECT symbol, price, source, publisher, captured_at,
               watch_until, requested_at, updated_at
        FROM market_price_state
        WHERE symbol = ?
        """,
        (normalized,),
    ).fetchone()
    if row is None:
        return None
    return row if isinstance(row, dict) else dict(row)


def watched_market_symbols(db, *, now: datetime | None = None) -> set[str]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows = db.execute(
        """
        SELECT symbol
        FROM market_price_state
        WHERE watch_until >= ?
        ORDER BY symbol
        """,
        (current.isoformat(),),
    ).fetchall()
    return {
        normalize_market_symbol(row["symbol"] if isinstance(row, dict) else row[0])
        for row in rows
    }


def publish_market_prices(
    db,
    prices: Mapping[str, float],
    *,
    captured_at: datetime | None = None,
    source: str = MARKET_PRICE_SOURCE,
) -> int:
    """Upsert one replaceable row per symbol; no historical row growth."""
    captured = (captured_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    captured_iso = captured.isoformat()
    published = 0
    for raw_symbol, raw_price in sorted(prices.items()):
        symbol = normalize_market_symbol(raw_symbol)
        price = float(raw_price)
        if price <= 0:
            continue
        cursor = db.execute(
            """
            INSERT INTO market_price_state (
                symbol, price, source, publisher, captured_at,
                watch_until, requested_at, updated_at
            )
            VALUES (?, ?, ?, 'operation_worker', ?, ?, ?, ?)
            ON CONFLICT (symbol) DO UPDATE SET
                price = excluded.price,
                source = excluded.source,
                publisher = excluded.publisher,
                captured_at = excluded.captured_at,
                updated_at = excluded.updated_at
            WHERE market_price_state.captured_at IS NULL
               OR excluded.captured_at >= market_price_state.captured_at
            RETURNING symbol
            """,
            (
                symbol,
                price,
                str(source),
                captured_iso,
                captured_iso,
                captured_iso,
                captured_iso,
            ),
        )
        if getattr(cursor, "rowcount", 1) > 0:
            published += 1
    return published


def summarize_market_price(
    row: dict | None,
    *,
    now: datetime | None = None,
    fresh_seconds: int = MARKET_PRICE_FRESH_SECONDS,
) -> dict | None:
    if row is None or row.get("price") is None:
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    captured_at = _as_utc_datetime(row.get("captured_at"))
    if captured_at is None:
        return None
    age_seconds = max(0.0, (current - captured_at).total_seconds())
    return {
        "symbol": normalize_market_symbol(row["symbol"]),
        "price": float(row["price"]),
        "source": str(row.get("source") or MARKET_PRICE_SOURCE),
        "publisher": str(row.get("publisher") or MARKET_PRICE_AUTHORITY),
        "captured_at": captured_at.isoformat(),
        "age_seconds": age_seconds,
        "fresh": age_seconds <= max(int(fresh_seconds), 1),
        "authority": MARKET_PRICE_AUTHORITY,
    }


def fresh_market_prices(
    db,
    symbols: Iterable[str],
    *,
    now: datetime | None = None,
    fresh_seconds: int = MARKET_PRICE_FRESH_SECONDS,
) -> dict[str, float]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result: dict[str, float] = {}
    for symbol in sorted({normalize_market_symbol(value) for value in symbols}):
        summary = summarize_market_price(
            get_market_price_row(db, symbol),
            now=current,
            fresh_seconds=fresh_seconds,
        )
        if summary and summary["fresh"]:
            result[symbol] = float(summary["price"])
    return result


__all__ = (
    "MARKET_PRICE_AUTHORITY",
    "MARKET_PRICE_FRESH_SECONDS",
    "MARKET_PRICE_SOURCE",
    "ensure_market_price_state_table",
    "fresh_market_prices",
    "get_market_price_row",
    "normalize_market_symbol",
    "publish_market_prices",
    "request_market_price_watch",
    "summarize_market_price",
    "watched_market_symbols",
)
