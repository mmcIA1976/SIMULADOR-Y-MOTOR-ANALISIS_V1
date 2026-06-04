from __future__ import annotations

import json
import urllib.parse
import urllib.request

from trading_simulator import BINANCE_SPOT_BASE_URLS, BINANCE_SPOT_TIMEOUT_SECONDS, fetch_binance_price


BINANCE_KLINES_PATH = "/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
BINANCE_DEPTH_PATH = "/api/v3/depth?symbol={symbol}&limit=20"
BINANCE_TICKER_24H_PATH = "/api/v3/ticker/24hr?symbol={symbol}"
BINANCE_AGG_TRADES_PATH = "/api/v3/aggTrades?symbol={symbol}&limit={limit}"
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
BINANCE_OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
BINANCE_OPEN_INTEREST_HIST_URL = (
    "https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period={period}&limit={limit}"
)
BINANCE_FUNDING_HISTORY_URL = "https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit={limit}"
BINANCE_GLOBAL_LONG_SHORT_URL = (
    "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period={period}&limit=1"
)
BINANCE_TAKER_LONG_SHORT_URL = (
    "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={symbol}&period={period}&limit=1"
)
COINGECKO_MARKETS_URL = (
    "https://api.coingecko.com/api/v3/coins/markets?"
    "vs_currency=usd&order=market_cap_desc&per_page={limit}&page=1&sparkline=false"
    "&price_change_percentage=1h,24h,7d"
)
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
ALTERNATIVE_FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1&format=json"
_preferred_spot_base_url = BINANCE_SPOT_BASE_URLS[0]


def get_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "trading-trainer/0.1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json_optional(url: str) -> object | None:
    try:
        return get_json(url)
    except Exception:
        return None


def get_spot_json(path: str) -> object:
    global _preferred_spot_base_url
    last_error: Exception | None = None
    candidate_bases = (_preferred_spot_base_url,) + tuple(
        base for base in BINANCE_SPOT_BASE_URLS if base != _preferred_spot_base_url
    )
    for base_url in candidate_bases:
        url = f"{base_url}{path}"
        request = urllib.request.Request(url, headers={"User-Agent": "trading-trainer/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=BINANCE_SPOT_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            _preferred_spot_base_url = base_url
            return payload
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"No se pudo consultar Binance Spot para {path}: {last_error}")


def get_spot_json_optional(path: str) -> object | None:
    try:
        return get_spot_json(path)
    except Exception:
        return None


def get_price(symbol: str) -> float:
    return fetch_binance_price(symbol.upper())


def get_klines(
    symbol: str,
    interval: str = "5m",
    limit: int = 80,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[list]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    path = BINANCE_KLINES_PATH.format(symbol=safe_symbol, interval=interval, limit=limit)
    if start_time_ms is not None:
        path = f"{path}&startTime={start_time_ms}"
    if end_time_ms is not None:
        path = f"{path}&endTime={end_time_ms}"
    payload = get_spot_json(path)
    return payload if isinstance(payload, list) else []


def get_depth(symbol: str) -> dict:
    safe_symbol = urllib.parse.quote(symbol.upper())
    payload = get_spot_json_optional(BINANCE_DEPTH_PATH.format(symbol=safe_symbol))
    return payload if isinstance(payload, dict) else {"bids": [], "asks": []}


def get_24h_ticker(symbol: str) -> dict:
    safe_symbol = urllib.parse.quote(symbol.upper())
    payload = get_spot_json_optional(BINANCE_TICKER_24H_PATH.format(symbol=safe_symbol))
    return payload if isinstance(payload, dict) else {}


def get_agg_trades(
    symbol: str,
    limit: int = 500,
    start_time_ms: int | None = None,
    end_time_ms: int | None = None,
) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(limit, 50), 1000)
    path = BINANCE_AGG_TRADES_PATH.format(symbol=safe_symbol, limit=capped_limit)
    if start_time_ms is not None:
        path = f"{path}&startTime={start_time_ms}"
    if end_time_ms is not None:
        path = f"{path}&endTime={end_time_ms}"
    data = get_spot_json_optional(path)
    return data if isinstance(data, list) else []


def get_funding_snapshot(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_FUNDING_URL.format(symbol=safe_symbol))
    return data if isinstance(data, dict) else None


def get_open_interest(symbol: str) -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_OPEN_INTEREST_URL.format(symbol=safe_symbol))
    return data if isinstance(data, dict) else None


def get_open_interest_history(symbol: str, period: str = "5m", limit: int = 30) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(limit, 2), 500)
    data = get_json_optional(BINANCE_OPEN_INTEREST_HIST_URL.format(symbol=safe_symbol, period=period, limit=capped_limit))
    return data if isinstance(data, list) else []


def get_funding_history(symbol: str, limit: int = 8) -> list[dict]:
    safe_symbol = urllib.parse.quote(symbol.upper())
    capped_limit = min(max(limit, 1), 1000)
    data = get_json_optional(BINANCE_FUNDING_HISTORY_URL.format(symbol=safe_symbol, limit=capped_limit))
    return data if isinstance(data, list) else []


def get_global_long_short_ratio(symbol: str, period: str = "5m") -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_GLOBAL_LONG_SHORT_URL.format(symbol=safe_symbol, period=period))
    if isinstance(data, list) and data:
        return data[-1]
    return None


def get_taker_long_short_ratio(symbol: str, period: str = "5m") -> dict | None:
    safe_symbol = urllib.parse.quote(symbol.upper())
    data = get_json_optional(BINANCE_TAKER_LONG_SHORT_URL.format(symbol=safe_symbol, period=period))
    if isinstance(data, list) and data:
        return data[-1]
    return None


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
                "binance_usdt_symbol": f"{symbol}USDT",
            }
        )
    return assets


def get_global_crypto_market() -> dict | None:
    data = get_json_optional(COINGECKO_GLOBAL_URL)
    return data if isinstance(data, dict) else None


def get_fear_greed_index() -> dict | None:
    data = get_json_optional(ALTERNATIVE_FEAR_GREED_URL)
    if not isinstance(data, dict):
        return None
    values = data.get("data")
    if isinstance(values, list) and values:
        return values[0]
    return None
