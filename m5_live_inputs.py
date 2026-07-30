from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable

import liquidation_data
import market_data
from m8_evaluation import BINANCE_INTERVALS


POSITIONING_REFERENCE_COUNT = 60


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _safe_future(future, fallback):
    try:
        value = future.result()
    except Exception:
        return fallback
    return fallback if value is None else value


def collect_live_rule_context(
    *,
    symbol: str,
    horizon_seconds: int,
    interval_seconds: int,
    request_cutoff_at: str,
    client: Any = market_data,
    liquidation_client: Any | None = None,
    market_price: float | None = None,
    now_ms: Callable[[], int] = utc_now_ms,
) -> dict:
    parsed = datetime.fromisoformat(
        str(request_cutoff_at).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    request_cutoff_ms = int(parsed.astimezone(timezone.utc).timestamp() * 1000)
    interval = BINANCE_INTERVALS[int(interval_seconds)]
    interval_ms = int(interval_seconds) * 1000
    horizon_ms = int(horizon_seconds) * 1000
    history_start_ms = request_cutoff_ms - horizon_ms - 2 * interval_ms
    sample_limit = min(
        500,
        max(4, int(horizon_seconds) // int(interval_seconds) + 4),
    )
    funding_limit = POSITIONING_REFERENCE_COUNT
    liquidation_client = (
        liquidation_data
        if liquidation_client is None and client is market_data
        else liquidation_client or client
    )
    try:
        normalized_market_price = float(market_price)
    except (TypeError, ValueError):
        normalized_market_price = 0.0

    with ThreadPoolExecutor(max_workers=13) as executor:
        futures = {
            "depth": executor.submit(client.get_depth, symbol, 100),
            "futures_book": executor.submit(
                client.get_futures_book_ticker,
                symbol,
            ),
            "spot_book": executor.submit(client.get_spot_book_ticker, symbol),
            "spot_info": executor.submit(client.get_spot_exchange_info, symbol),
            "funding_snapshot": executor.submit(
                client.get_funding_snapshot,
                symbol,
            ),
            "funding_info": executor.submit(client.get_funding_info, symbol),
            "funding_history": executor.submit(
                client.get_funding_history,
                symbol,
                funding_limit,
                None,
                request_cutoff_ms,
            ),
            "open_interest_history": executor.submit(
                client.get_open_interest_history,
                symbol,
                interval,
                sample_limit,
                history_start_ms,
                request_cutoff_ms,
            ),
            "taker_history": executor.submit(
                client.get_taker_long_short_ratio_history,
                symbol,
                interval,
                sample_limit,
                history_start_ms,
                request_cutoff_ms,
            ),
            "global_long_short_history": executor.submit(
                client.get_global_long_short_ratio_history,
                symbol,
                interval,
                POSITIONING_REFERENCE_COUNT + 1,
                None,
                request_cutoff_ms,
            ),
            "market_breadth_assets": executor.submit(
                client.get_top_crypto_assets,
                100,
            ),
            "fear_greed_history": executor.submit(
                client.get_fear_greed_history,
                POSITIONING_REFERENCE_COUNT + 1,
            ),
        }
        if normalized_market_price > 0:
            futures["liquidation_context"] = executor.submit(
                liquidation_client.get_liquidation_context,
                symbol,
                normalized_market_price,
            )

    captured_at_ms = int(now_ms())
    return {
        "symbol": symbol.upper(),
        "request_cutoff_at": request_cutoff_at,
        "request_cutoff_ms": request_cutoff_ms,
        "captured_at_ms": captured_at_ms,
        "interval": interval,
        "interval_seconds": int(interval_seconds),
        "horizon_seconds": int(horizon_seconds),
        "depth": _safe_future(futures["depth"], {"bids": [], "asks": []}),
        "futures_book": _safe_future(futures["futures_book"], {}),
        "spot_book": _safe_future(futures["spot_book"], {}),
        "spot_info": _safe_future(futures["spot_info"], {}),
        "funding_snapshot": _safe_future(futures["funding_snapshot"], {}),
        "funding_info": _safe_future(futures["funding_info"], {}),
        "funding_history": _safe_future(futures["funding_history"], []),
        "open_interest_history": _safe_future(
            futures["open_interest_history"],
            [],
        ),
        "taker_history": _safe_future(futures["taker_history"], []),
        "global_long_short_history": _safe_future(
            futures["global_long_short_history"],
            [],
        ),
        "market_breadth_assets": _safe_future(
            futures["market_breadth_assets"],
            [],
        ),
        "fear_greed_history": _safe_future(
            futures["fear_greed_history"],
            [],
        ),
        "liquidation_context": (
            _safe_future(futures["liquidation_context"], {})
            if "liquidation_context" in futures
            else {}
        ),
    }
