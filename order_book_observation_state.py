from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping

from market_price_state import normalize_market_symbol


ORDER_BOOK_OBSERVATION_AUTHORITY = "operation_worker"
ORDER_BOOK_OBSERVATION_FRESH_SECONDS = 45


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


def ensure_order_book_observation_state_table(db) -> None:
    """Create the constant-size internal worker/web hand-off table."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS order_book_observation_state (
            symbol TEXT PRIMARY KEY
                CHECK(symbol ~ '^[A-Z0-9]{5,20}$'),
            summary_json JSONB NOT NULL,
            source TEXT NOT NULL,
            publisher TEXT NOT NULL DEFAULT 'operation_worker'
                CHECK(publisher = 'operation_worker'),
            captured_at TIMESTAMPTZ NOT NULL,
            window_started_at TIMESTAMPTZ NOT NULL,
            sample_count INTEGER NOT NULL CHECK(sample_count >= 1),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.executescript(
        """
        ALTER TABLE order_book_observation_state ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE order_book_observation_state FROM anon, authenticated;
        GRANT ALL PRIVILEGES ON TABLE order_book_observation_state TO postgres, service_role;
        """
    )


def publish_order_book_observations(
    db,
    observations: Mapping[str, dict],
) -> int:
    """Replace one compact summary per symbol; never append raw snapshots."""
    published = 0
    for raw_symbol, summary in sorted(observations.items()):
        symbol = normalize_market_symbol(raw_symbol)
        if not isinstance(summary, dict) or not summary.get("available"):
            continue
        captured_at_ms = int(summary["captured_at_ms"])
        window_started_at_ms = int(summary["window_started_at_ms"])
        captured_at = datetime.fromtimestamp(
            captured_at_ms / 1000,
            tz=timezone.utc,
        ).isoformat()
        window_started_at = datetime.fromtimestamp(
            window_started_at_ms / 1000,
            tz=timezone.utc,
        ).isoformat()
        cursor = db.execute(
            """
            INSERT INTO order_book_observation_state (
                symbol, summary_json, source, publisher, captured_at,
                window_started_at, sample_count, updated_at
            )
            VALUES (?, ?::jsonb, ?, 'operation_worker', ?, ?, ?, ?)
            ON CONFLICT (symbol) DO UPDATE SET
                summary_json = excluded.summary_json,
                source = excluded.source,
                publisher = excluded.publisher,
                captured_at = excluded.captured_at,
                window_started_at = excluded.window_started_at,
                sample_count = excluded.sample_count,
                updated_at = excluded.updated_at
            WHERE order_book_observation_state.captured_at IS NULL
               OR excluded.captured_at >= order_book_observation_state.captured_at
            RETURNING symbol
            """,
            (
                symbol,
                json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
                str(summary.get("source") or "binance_usdm_depth_100_and_aggtrades"),
                captured_at,
                window_started_at,
                int(summary.get("sample_count") or 1),
                captured_at,
            ),
        )
        if getattr(cursor, "rowcount", 1) > 0:
            published += 1
    return published


def get_order_book_observation_row(db, symbol: str) -> dict | None:
    normalized = normalize_market_symbol(symbol)
    row = db.execute(
        """
        SELECT symbol, summary_json, source, publisher, captured_at,
               window_started_at, sample_count, updated_at
        FROM order_book_observation_state
        WHERE symbol = ?
        """,
        (normalized,),
    ).fetchone()
    if row is None:
        return None
    return row if isinstance(row, dict) else dict(row)


def summarize_order_book_observation(
    row: dict | None,
    *,
    now: datetime | None = None,
    fresh_seconds: int = ORDER_BOOK_OBSERVATION_FRESH_SECONDS,
) -> dict | None:
    if row is None:
        return None
    payload = row.get("summary_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    captured_at = _as_utc_datetime(row.get("captured_at"))
    if captured_at is None:
        return None
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_seconds = max(0.0, (current - captured_at).total_seconds())
    fresh = age_seconds <= max(int(fresh_seconds), 1)
    return {
        **payload,
        "symbol": normalize_market_symbol(row["symbol"]),
        "source": str(row.get("source") or payload.get("source") or "unknown"),
        "publisher": str(row.get("publisher") or ORDER_BOOK_OBSERVATION_AUTHORITY),
        "captured_at": captured_at.isoformat(),
        "age_seconds": age_seconds,
        "fresh": fresh,
        "authority": ORDER_BOOK_OBSERVATION_AUTHORITY,
        "available": bool(payload.get("available")) and fresh,
        "state_reason": None if fresh else "worker_order_book_observation_stale",
    }


__all__ = (
    "ORDER_BOOK_OBSERVATION_AUTHORITY",
    "ORDER_BOOK_OBSERVATION_FRESH_SECONDS",
    "ensure_order_book_observation_state_table",
    "get_order_book_observation_row",
    "publish_order_book_observations",
    "summarize_order_book_observation",
)
