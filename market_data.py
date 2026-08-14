from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError

from trading_simulator import BINANCE_MARKET_TIMEOUT_SECONDS


BINANCE_USDM_BASE_URLS = (
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com",
)
BINANCE_USDM_ALL_PRICES_PATH = "/fapi/v1/ticker/price"
BINANCE_USDM_PRICE_PATH = "/fapi/v1/ticker/price?symbol={symbol}"
BINANCE_USDM_KLINES_PATH = "/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
BINANCE_USDM_DEPTH_PATH = "/fapi/v1/depth?symbol={symbol}&limit={limit}"
BINANCE_USDM_BOOK_TICKER_PATH = "/fapi/v1/ticker/bookTicker?symbol={symbol}"
BINANCE_USDM_TICKER_24H_PATH = "/fapi/v1/ticker/24hr?symbol={symbol}"
BINANCE_USDM_AGG_TRADES_PATH = "/fapi/v1/aggTrades?symbol={symbol}&limit={limit}"
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
BINANCE_FUNDING_INFO_URL = "https://fapi.binance.com/fapi/v1/fundingInfo?symbol={symbol}"
BINANCE_OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
BINANCE_OPEN_INTEREST_HIST_URL = (
    "https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period={period}&limit={limit}"
)
BINANCE_FUNDING_HISTORY_URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
BINANCE_GLOBAL_LONG_SHORT_URL = (
    "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period={period}&limit=1"
)
BINANCE_GLOBAL_LONG_SHORT_HISTORY_URL = (
    "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?"
    "symbol={symbol}&period={period}&limit={limit}"
)
BINANCE_TAKER_LONG_SHORT_URL = (
    "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={symbol}&period={period}&limit=1"
)
BINANCE_TAKER_LONG_SHORT_HISTORY_URL = (
    "https://fapi.binance.com/futures/data/takerlongshortRatio?"
    "symbol={symbol}&period={period}&limit={limit}"
)
BINANCE_SPOT_BOOK_TICKER_URL = (
    "https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
)
BINANCE_SPOT_EXCHANGE_INFO_URL = (
    "https://api.binance.com/api/v3/exchangeInfo?symbol={symbol}"
)
COINGECKO_MARKETS_URL = (
    "https://api.coingecko.com/api/v3/coins/markets?"
    "vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1&sparkline=false"
    "&price_change_percentage=1h,24h,7d"
)
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
ALTERNATIVE_FEAR_GREED_URL = (
    "https://api.alternative.me/fng/?limit={limit}&format=json"
)
_preferred_futures_base_url = BINANCE_USDM_BASE_URLS[0]
_futures_backoff_until_ms = 0
_price_cache: dict[str, dict] = {}
PRICE_CACHE_TTL_SECONDS = 12
PRICE_STALE_MAX_SECONDS = 300
RANKING_PRICE_TIMEOUT_SECONDS = 2.0
RANKING_PRICE_MAX_HOST_ATTEMPTS = 2

BINANCE_API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _parse_binance_ban_until_ms(text: str) -> int | None:
    match = re.search(r"banned until (\d{12,})", text)
    return int(match.group(1)) if match else None


def _is_binance_futures_url(url: str) -> bool:
    return any(base in url for base in BINANCE_USDM_BASE_URLS)


def futures_backoff_until_ms() -> int:
    return _futures_backoff_until_ms


def get_cached_price(symbol: str, max_age_seconds: float | None = PRICE_STALE_MAX_SECONDS) -> dict | None:
    cached = _price_cache.get(symbol.upper())
    if not cached:
        return None
    age_seconds = (_now_ms() - int(cached["captured_at_ms"])) / 1000
    if max_age_seconds is not None and age_seconds > max_age_seconds:
        return None
    return {
        "symbol": symbol.upper(),
        "price": float(cached["price"]),
        "captured_at": _iso_from_ms(int(cached["captured_at_ms"])),
        "age_seconds": age_seconds,
        "source": cached.get("source", "binance_usdm_futures_memory_cache"),
    }


def _remember_price(symbol: str, price: float, source: str = "binance_usdm_futures_ticker") -> None:
    _price_cache[symbol.upper()] = {
        "price": float(price),
        "captured_at_ms": _now_ms(),
        "source": source,
    }


def get_json(url: str) -> object:
    global _futures_backoff_until_ms
    now_ms = _now_ms()
    if _is_binance_futures_url(url) and _futures_backoff_until_ms and now_ms < _futures_backoff_until_ms:
        raise RuntimeError(
            "Binance USD-M Futures temporalmente limitado hasta "
            f"{_iso_from_ms(_futures_backoff_until_ms)}"
        )
    request = urllib.request.Request(url, headers=BINANCE_API_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=BINANCE_MARKET_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if _is_binance_futures_url(url) and exc.code in (418, 429):
            try:
                body = exc.read().decode("utf-8", errors="replace")[:180]
            except Exception:
                body = ""
            ban_until_ms = _parse_binance_ban_until_ms(body)
            _futures_backoff_until_ms = max(
                _futures_backoff_until_ms,
                ban_until_ms or now_ms + 60_000,
            )
        raise


def get_json_optional(url: str) -> object | None:
    try:
        return get_json(url)
    except Exception:
        return None


def get_futures_json(
    path: str,
    *,
    timeout_seconds: float = BINANCE_MARKET_TIMEOUT_SECONDS,
    max_host_attempts: int | None = None,
) -> object:
    global _preferred_futures_base_url, _futures_backoff_until_ms
    now_ms = _now_ms()
    if _futures_backoff_until_ms and now_ms < _futures_backoff_until_ms:
        raise RuntimeError(
            "Binance USD-M Futures temporalmente limitado hasta "
            f"{_iso_from_ms(_futures_backoff_until_ms)}"
        )
    errors: list[str] = []
    candidate_bases = (_preferred_futures_base_url,) + tuple(
        base for base in BINANCE_USDM_BASE_URLS if base != _preferred_futures_base_url
    )
    if max_host_attempts is not None:
        candidate_bases = candidate_bases[:max(1, int(max_host_attempts))]
    for base_url in candidate_bases:
        url = f"{base_url}{path}"
        request = urllib.request.Request(url, headers=BINANCE_API_HEADERS)
        raw = ""
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw)
            _preferred_futures_base_url = base_url
            return payload
        except HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")[:180]
            except Exception:
                body = ""
            if exc.code in (418, 429):
                ban_until_ms = _parse_binance_ban_until_ms(body)
                fallback_backoff_ms = now_ms + 60_000
                _futures_backoff_until_ms = max(
                    _futures_backoff_until_ms,
                    ban_until_ms or fallback_backoff_ms,
                )
            errors.append(f"{base_url}: HTTP {exc.code} {body}")
        except json.JSONDecodeError as exc:
            errors.append(f"{base_url}: respuesta no JSON {raw[:180]} ({exc})")
        except Exception as exc:
            errors.append(f"{base_url}: {exc}")
    error_text = " | ".join(errors) if errors else "sin detalle de error"
    raise RuntimeError(f"No se pudo consultar Binance USD-M Futures para {path}: {error_text}")


def get_futures_json_optional(path: str) -> object | None:
    try:
        return get_futures_json(path)
    except Exception:
        return None


def diagnose_futures_hosts(symbol: str) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    path = BINANCE_USDM_PRICE_PATH.format(symbol=safe_symbol)
    results = []
    for base_url in BINANCE_USDM_BASE_URLS:
        url = f"{base_url}{path}"
        request = urllib.request.Request(url, headers=BINANCE_API_HEADERS)
        item = {
            "base_url": base_url,
            "url": url,
            "ok": False,
            "status": None,
            "content_type": None,
            "json_ok": False,
            "body_prefix": "",
            "error": None,
        }
        try:
            with urllib.request.urlopen(request, timeout=BINANCE_MARKET_TIMEOUT_SECONDS) as response:
                raw_bytes = response.read()
                raw = raw_bytes.decode("utf-8", errors="replace")
                item["status"] = int(response.status)
                item["content_type"] = response.headers.get("Content-Type")
                item["body_prefix"] = raw[:240]
                try:
                    parsed = json.loads(raw)
                    item["json_ok"] = True
                    item["ok"] = isinstance(parsed, dict) and "price" in parsed
                except json.JSONDecodeError as exc:
                    item["error"] = f"json_decode_error: {exc}"
        except HTTPError as exc:
            item["status"] = int(exc.code)
            item["content_type"] = exc.headers.get("Content-Type") if exc.headers else None
            try:
                item["body_prefix"] = exc.read().decode("utf-8", errors="replace")[:240]
            except Exception:
                item["body_prefix"] = ""
            item["error"] = f"http_error: {exc}"
        except Exception as exc:
            item["error"] = str(exc)
        results.append(item)
    return results


def get_price(symbol: str, *, force_refresh: bool = False) -> float:
    cached = None if force_refresh else get_cached_price(symbol, PRICE_CACHE_TTL_SECONDS)
    if cached:
        return float(cached["price"])
    safe_symbol = urllib.parse.quote(symbol.upper())
    payload = get_futures_json(BINANCE_USDM_PRICE_PATH.format(symbol=safe_symbol))
    if not isinstance(payload, dict) or "price" not in payload:
        raise RuntimeError(f"Respuesta de precio Futures no valida para {symbol}")
    price = float(payload["price"])
    _remember_price(symbol, price)
    return price


def get_prices(
    symbols: list[str] | tuple[str, ...] | set[str],
    *,
    allow_stale: bool = True,
) -> dict[str, float]:
    """Resolve several Futures prices with at most one Binance request.

    Fresh in-process values are reused first. If any symbol is missing, the
    all-tickers endpoint is fetched once and only the requested symbols are
    retained. Callers that make execution decisions set ``allow_stale=False``;
    display-only legacy callers may still opt into the bounded stale cache.
    """
    normalized_symbols = sorted({str(symbol).upper() for symbol in symbols if str(symbol).strip()})
    if not normalized_symbols:
        return {}

    prices: dict[str, float] = {}
    missing: list[str] = []
    for symbol in normalized_symbols:
        cached = get_cached_price(symbol, PRICE_CACHE_TTL_SECONDS)
        if cached:
            prices[symbol] = float(cached["price"])
        else:
            missing.append(symbol)

    if not missing:
        return prices

    try:
        payload = get_futures_json(
            BINANCE_USDM_ALL_PRICES_PATH,
            timeout_seconds=RANKING_PRICE_TIMEOUT_SECONDS,
            max_host_attempts=RANKING_PRICE_MAX_HOST_ATTEMPTS,
        )
    except Exception:
        payload = []

    requested = set(missing)
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            if symbol not in requested:
                continue
            try:
                price = float(item["price"])
            except (KeyError, TypeError, ValueError):
                continue
            prices[symbol] = price
            _remember_price(symbol, price, source="binance_usdm_futures_all_tickers")

    for symbol in missing:
        if symbol in prices:
            continue
        stale = (
            get_cached_price(symbol, PRICE_STALE_MAX_SECONDS)
            if allow_stale
            else None
        )
        if stale:
            prices[symbol] = float(stale["price"])
    return prices


def get_klines(
    symbol: str,
    interval: str = "5m",
    limit: int = 80,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[list]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    path = BINANCE_USDM_KLINES_PATH.format(symbol=safe_symbol, interval=interval, limit=limit)
    if start_time_ms is not None:
        path = f"{path}&startTime={start_time_ms}"
    if end_time_ms is not None:
        path = f"{path}&endTime={end_time_ms}"
    payload = get_futures_json(path)
    return payload if isinstance(payload, list) else []


def get_depth(symbol: str, limit: int = 20) -> dict:
    safe_symbol = urllib.parse.quote(symbol.upper())
    allowed_limits = (5, 10, 20, 50, 100, 500, 1000)
    selected_limit = min(
        allowed_limits,
        key=lambda value: abs(value - min(max(int(limit), 5), 1000)),
    )
    received_at_ms = _now_ms()
    payload = get_futures_json_optional(
        BINANCE_USDM_DEPTH_PATH.format(
            symbol=safe_symbol,
            limit=selected_limit,
        )
    )
    if not isinstance(payload, dict):
        return {"bids": [], "asks": []}
    return {
        **payload,
        "receivedAt": max(received_at_ms, _now_ms()),
    }


def get_futures_book_ticker(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    received_at_ms = _now_ms()
    payload = get_futures_json_optional(
        BINANCE_USDM_BOOK_TICKER_PATH.format(symbol=safe_symbol)
    )
    if not isinstance(payload, dict):
        return None
    return {
        **payload,
        "receivedAt": max(received_at_ms, _now_ms()),
    }


def get_spot_book_ticker(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    payload = get_json_optional(
        BINANCE_SPOT_BOOK_TICKER_URL.format(symbol=safe_symbol)
    )
    if not isinstance(payload, dict):
        return None
    return {
        **payload,
        "receivedAt": _now_ms(),
    }


def get_spot_exchange_info(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    payload = get_json_optional(
        BINANCE_SPOT_EXCHANGE_INFO_URL.format(symbol=safe_symbol)
    )
    return payload if isinstance(payload, dict) else None


def get_24h_ticker(symbol: str) -> dict:
    safe_symbol = urllib.parse.quote(symbol.upper())
    payload = get_futures_json_optional(BINANCE_USDM_TICKER_24H_PATH.format(symbol=safe_symbol))
    return payload if isinstance(payload, dict) else {}


def get_agg_trades(
    symbol: str,
    limit: int = 500,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(limit, 50), 1000)
    path = BINANCE_USDM_AGG_TRADES_PATH.format(symbol=safe_symbol, limit=capped_limit)
    if start_time_ms is not None:
        path = f"{path}&startTime={start_time_ms}"
    if end_time_ms is not None:
        path = f"{path}&endTime={end_time_ms}"
    data = get_futures_json_optional(path)
    return data if isinstance(data, list) else []


def get_funding_snapshot(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_FUNDING_URL.format(symbol=safe_symbol))
    return data if isinstance(data, dict) else None


def get_open_interest(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_OPEN_INTEREST_URL.format(symbol=safe_symbol))
    return data if isinstance(data, dict) else None


def get_open_interest_history(
    symbol: str,
    period: str = "5m",
    limit: int = 30,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(limit, 2), 500)
    url = BINANCE_OPEN_INTEREST_HIST_URL.format(
        symbol=safe_symbol,
        period=period,
        limit=capped_limit,
    )
    if start_time_ms is not None:
        url = f"{url}&startTime={int(start_time_ms)}"
    if end_time_ms is not None:
        url = f"{url}&endTime={int(end_time_ms)}"
    data = get_json_optional(url)
    return data if isinstance(data, list) else []


def get_funding_history(
    symbol: str,
    limit: int = 8,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(limit, 1), 1000)
    url = BINANCE_FUNDING_HISTORY_URL.format(
        symbol=safe_symbol,
        limit=capped_limit,
    )
    if start_time_ms is not None:
        url = f"{url}&startTime={int(start_time_ms)}"
    if end_time_ms is not None:
        url = f"{url}&endTime={int(end_time_ms)}"
    data = get_json_optional(url)
    return data if isinstance(data, list) else []


def get_funding_info(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(
        BINANCE_FUNDING_INFO_URL.format(symbol=safe_symbol)
    )
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        normalized = symbol.upper()
        return next(
            (
                item
                for item in data
                if isinstance(item, dict)
                and str(item.get("symbol", "")).upper() == normalized
            ),
            None,
        )
    return None


def get_global_long_short_ratio(symbol: str, period: str = "5m") -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_GLOBAL_LONG_SHORT_URL.format(symbol=safe_symbol, period=period))
    if isinstance(data, list) and data:
        return data[-1]
    return None


def get_global_long_short_ratio_history(
    symbol: str,
    period: str = "5m",
    limit: int = 30,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(int(limit), 1), 500)
    url = BINANCE_GLOBAL_LONG_SHORT_HISTORY_URL.format(
        symbol=safe_symbol,
        period=period,
        limit=capped_limit,
    )
    if start_time_ms is not None:
        url = f"{url}&startTime={int(start_time_ms)}"
    if end_time_ms is not None:
        url = f"{url}&endTime={int(end_time_ms)}"
    data = get_json_optional(url)
    return data if isinstance(data, list) else []


def get_taker_long_short_ratio(symbol: str, period: str = "5m") -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_TAKER_LONG_SHORT_URL.format(symbol=safe_symbol, period=period))
    if isinstance(data, list) and data:
        return data[-1]
    return None


def get_taker_long_short_ratio_history(
    symbol: str,
    period: str = "5m",
    limit: int = 30,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(int(limit), 1), 500)
    url = BINANCE_TAKER_LONG_SHORT_HISTORY_URL.format(
        symbol=safe_symbol,
        period=period,
        limit=capped_limit,
    )
    if start_time_ms is not None:
        url = f"{url}&startTime={int(start_time_ms)}"
    if end_time_ms is not None:
        url = f"{url}&endTime={int(end_time_ms)}"
    data = get_json_optional(url)
    return data if isinstance(data, list) else []


def get_top_crypto_assets(limit: int = 100) -> list[dict]:
    data = get_json_optional(COINGECKO_MARKETS_URL.format(limit=limit))
    if not isinstance(data, list):
        return []
    assets = []
    for item in data:
        symbol = str(item.get("symbol", "")).upper()
        assets.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "symbol": symbol,
                "market_cap_rank": item.get("market_cap_rank"),
                "market_cap": item.get("market_cap"),
                "current_price": item.get("current_price"),
                "total_volume": item.get("total_volume"),
                "price_change_percentage_1h_in_currency": item.get("price_change_percentage_1h_in_currency"),
                "price_change_percentage_24h_in_currency": item.get("price_change_percentage_24h_in_currency"),
                "price_change_percentage_7d_in_currency": item.get("price_change_percentage_7d_in_currency"),
                "last_updated": item.get("last_updated"),
                "binance_usdt_symbol": f"{symbol}USDT",
            }
        )
    return assets


def get_global_crypto_market() -> dict | None:
    data = get_json_optional(COINGECKO_GLOBAL_URL)
    return data if isinstance(data, dict) else None


def get_fear_greed_index() -> dict | None:
    values = get_fear_greed_history(1)
    return values[0] if values else None


def get_fear_greed_history(limit: int = 61) -> list[dict]:
    capped_limit = min(max(int(limit), 1), 1000)
    data = get_json_optional(
        ALTERNATIVE_FEAR_GREED_URL.format(limit=capped_limit)
    )
    if not isinstance(data, dict):
        return []
    values = data.get("data")
    return values if isinstance(values, list) else []
