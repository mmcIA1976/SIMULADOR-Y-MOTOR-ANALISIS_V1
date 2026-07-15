from __future__ import annotations

import json
import os
import threading
import time
import urllib.request


HYPERPERPS_BASE_URL = "https://trade.hyperperps.app/api/public/heatmap/{symbol}"
HYPERPERPS_HEADERS = {
    "User-Agent": "trading-simulator/1.0",
    "Accept": "application/json",
}
SUPPORTED_SYMBOLS = {
    "BTCUSD": "BTC",
    "BTCUSDC": "BTC",
    "BTCUSDT": "BTC",
    "ETHUSD": "ETH",
    "ETHUSDC": "ETH",
    "ETHUSDT": "ETH",
    "SOLUSD": "SOL",
    "SOLUSDC": "SOL",
    "SOLUSDT": "SOL",
}

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _safe_float(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in {float("inf"), float("-inf")} else None


def _empty_context(symbol: str, status: str, reason: str) -> dict:
    return {
        "available": False,
        "mode": "observation",
        "status": status,
        "reason": reason,
        "provider": "hyperperps",
        "scope": "hyperliquid",
        "symbol": SUPPORTED_SYMBOLS.get(symbol.upper()),
        "schema": None,
        "as_of": None,
        "age_seconds": None,
        "stale": status == "stale",
        "reference_price": None,
        "market_price": None,
        "reference_basis_pct": None,
        "sample_size": 0,
        "clusters_above": [],
        "clusters_below": [],
        "cascade_mass": {
            "long": {"within_1pct": None, "within_2pct": None, "within_5pct": None},
            "short": {"within_1pct": None, "within_2pct": None, "within_5pct": None},
        },
        "short_to_long_mass_ratio_2pct": None,
        "dominant_liquidation_side_2pct": "unknown",
        "net_oi_skew": None,
        "crowd_leverage": {"long_avg": None, "short_avg": None},
    }


def _normalize_cluster(item: object, side: str, market_price: float) -> dict | None:
    if not isinstance(item, dict):
        return None
    price = _safe_float(item.get("price"))
    notional = _safe_float(item.get("notional_usd"))
    wallets = _safe_float(item.get("wallet_count"))
    provider_distance = _safe_float(item.get("distance_pct"))
    if price is None or price <= 0 or notional is None or notional < 0:
        return None
    distance = ((price - market_price) / market_price) * 100 if market_price > 0 else None
    return {
        "position_side": side,
        "price": round(price, 8),
        "notional_usd": round(notional, 2),
        "wallet_count": int(wallets) if wallets is not None and wallets >= 0 else None,
        "distance_pct": round(distance, 4) if distance is not None else None,
        "provider_distance_pct": round(provider_distance, 4) if provider_distance is not None else None,
    }


def _normalize_mass(payload: object) -> dict:
    result = {"within_1pct": None, "within_2pct": None, "within_5pct": None}
    if not isinstance(payload, dict):
        return result
    for key in result:
        value = _safe_float(payload.get(key))
        result[key] = round(value, 2) if value is not None and value >= 0 else None
    return result


def normalize_heatmap(
    payload: object,
    symbol: str,
    market_price: float,
    *,
    now_ms: int | None = None,
    max_age_seconds: float | None = None,
) -> dict:
    symbol = symbol.upper()
    provider_symbol = SUPPORTED_SYMBOLS.get(symbol)
    if provider_symbol is None:
        return _empty_context(symbol, "unsupported", "symbol_not_supported_by_provider")
    if not isinstance(payload, dict):
        return _empty_context(symbol, "unavailable", "invalid_provider_payload")

    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    max_age_seconds = max_age_seconds or _env_float("HYPERPERPS_MAX_AGE_SECONDS", 600, 60, 3600)
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    updated_at = _safe_float(payload.get("updated_at"))
    reported_age = _safe_float(meta.get("age_seconds"))
    calculated_age = max(0.0, (now_ms - updated_at) / 1000) if updated_at is not None else None
    age_seconds = calculated_age if calculated_age is not None else reported_age
    stale = bool(meta.get("stale")) or age_seconds is None or age_seconds > max_age_seconds

    reference_price = _safe_float(payload.get("spot_at_compute"))
    market_price = _safe_float(market_price) or 0.0
    basis_pct = (
        ((reference_price - market_price) / market_price) * 100
        if reference_price is not None and market_price > 0
        else None
    )
    max_basis_pct = _env_float("HYPERPERPS_MAX_PRICE_BASIS_PCT", 1.5, 0.25, 10)
    price_mismatch = basis_pct is None or abs(basis_pct) > max_basis_pct

    longs = [
        cluster
        for cluster in (_normalize_cluster(item, "long", market_price) for item in payload.get("longs", []))
        if cluster is not None
    ]
    shorts = [
        cluster
        for cluster in (_normalize_cluster(item, "short", market_price) for item in payload.get("shorts", []))
        if cluster is not None
    ]
    longs.sort(key=lambda item: item["notional_usd"], reverse=True)
    shorts.sort(key=lambda item: item["notional_usd"], reverse=True)

    cascade = payload.get("cascade_mass") if isinstance(payload.get("cascade_mass"), dict) else {}
    long_mass = _normalize_mass(cascade.get("long"))
    short_mass = _normalize_mass(cascade.get("short"))
    long_2pct = long_mass.get("within_2pct")
    short_2pct = short_mass.get("within_2pct")
    ratio_2pct = short_2pct / long_2pct if long_2pct not in {None, 0} and short_2pct is not None else None
    if ratio_2pct is None:
        dominant_side = "unknown"
    elif ratio_2pct >= 1.2:
        dominant_side = "shorts_above"
    elif ratio_2pct <= (1 / 1.2):
        dominant_side = "longs_below"
    else:
        dominant_side = "balanced"

    has_clusters = bool(longs or shorts)
    if stale:
        status = "stale"
        reason = "provider_data_too_old"
    elif price_mismatch:
        status = "price_mismatch"
        reason = "provider_reference_price_too_far_from_market"
    elif not has_clusters:
        status = "unavailable"
        reason = "provider_returned_no_clusters"
    else:
        status = "available"
        reason = None

    crowd = payload.get("crowd_leverage") if isinstance(payload.get("crowd_leverage"), dict) else {}
    return {
        "available": status == "available",
        "mode": "observation",
        "status": status,
        "reason": reason,
        "provider": "hyperperps",
        "scope": "hyperliquid",
        "symbol": provider_symbol,
        "schema": meta.get("schema"),
        "as_of": meta.get("as_of"),
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "stale": stale,
        "reference_price": round(reference_price, 8) if reference_price is not None else None,
        "market_price": round(market_price, 8) if market_price > 0 else None,
        "reference_basis_pct": round(basis_pct, 4) if basis_pct is not None else None,
        "sample_size": int(_safe_float(payload.get("sample_size")) or 0),
        "clusters_above": shorts[:10],
        "clusters_below": longs[:10],
        "cascade_mass": {"long": long_mass, "short": short_mass},
        "short_to_long_mass_ratio_2pct": round(ratio_2pct, 4) if ratio_2pct is not None else None,
        "dominant_liquidation_side_2pct": dominant_side,
        "net_oi_skew": _safe_float(payload.get("net_oi_skew")),
        "crowd_leverage": {
            "long_avg": _safe_float(crowd.get("long_avg")),
            "short_avg": _safe_float(crowd.get("short_avg")),
        },
    }


def get_liquidation_context(symbol: str, market_price: float) -> dict:
    symbol = symbol.upper()
    if not _env_bool("HYPERPERPS_ENABLED", True):
        return _empty_context(symbol, "disabled", "provider_disabled")
    provider_symbol = SUPPORTED_SYMBOLS.get(symbol)
    if provider_symbol is None:
        return _empty_context(symbol, "unsupported", "symbol_not_supported_by_provider")

    now = time.time()
    cache_ttl = _env_float("HYPERPERPS_CACHE_TTL_SECONDS", 60, 10, 600)
    with _cache_lock:
        cached = _cache.get(provider_symbol)
    if cached and now - cached["fetched_at"] <= cache_ttl:
        return normalize_heatmap(cached["payload"], symbol, market_price)

    timeout = _env_float("HYPERPERPS_TIMEOUT_SECONDS", 4.0, 1.0, 15.0)
    url = HYPERPERPS_BASE_URL.format(symbol=provider_symbol)
    request = urllib.request.Request(url, headers=HYPERPERPS_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        with _cache_lock:
            _cache[provider_symbol] = {"fetched_at": now, "payload": payload}
        return normalize_heatmap(payload, symbol, market_price)
    except Exception as exc:
        if cached:
            context = normalize_heatmap(cached["payload"], symbol, market_price)
            context["reason"] = "provider_unavailable_using_cache"
            return context
        context = _empty_context(symbol, "unavailable", "provider_request_failed")
        context["error_type"] = type(exc).__name__
        return context
