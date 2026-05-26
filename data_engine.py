from __future__ import annotations

import statistics
from dataclasses import dataclass

import market_data


@dataclass(frozen=True)
class CandleSet:
    interval: str
    closes: list[float]
    highs: list[float]
    lows: list[float]
    volumes: list[float]
    taker_buy_volumes: list[float]


def fmean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    for change in changes[-period:]:
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = fmean(gains)
    avg_loss = fmean(losses)
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if len(closes) <= 1:
        return 0.0
    true_ranges = []
    start = max(1, len(closes) - period)
    for index in range(start, len(closes)):
        high = highs[index]
        low = lows[index]
        prev_close = closes[index - 1]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return fmean(true_ranges)


def parse_klines(raw_klines: list[list], interval: str) -> CandleSet:
    return CandleSet(
        interval=interval,
        closes=[float(kline[4]) for kline in raw_klines],
        highs=[float(kline[2]) for kline in raw_klines],
        lows=[float(kline[3]) for kline in raw_klines],
        volumes=[float(kline[5]) for kline in raw_klines],
        taker_buy_volumes=[float(kline[9]) for kline in raw_klines],
    )


def pct(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return (value / reference) * 100


def distance_pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return ((a - b) / b) * 100


def summarize_timeframe(candles: CandleSet, current_price: float) -> dict:
    closes = candles.closes
    highs = candles.highs
    lows = candles.lows
    volumes = candles.volumes
    taker_buy_volumes = candles.taker_buy_volumes
    ema_9 = ema(closes[-80:], 9)
    ema_21 = ema(closes[-100:], 21)
    ema_50 = ema(closes[-120:], 50)
    ema_200 = ema(closes[-220:], 200) if len(closes) >= 200 else ema(closes, min(80, len(closes)))
    atr_14 = atr(highs, lows, closes, 14)
    recent_high = max(highs[-24:])
    recent_low = min(lows[-24:])
    range_pct = pct(recent_high - recent_low, current_price)
    atr_pct = pct(atr_14, current_price)
    volume_ratio = volumes[-1] / max(fmean(volumes[-20:]), 0.000001)
    taker_buy_ratio = sum(taker_buy_volumes[-20:]) / max(sum(volumes[-20:]), 0.000001)
    last_body_pct = pct(abs(closes[-1] - closes[-2]), current_price) if len(closes) > 1 else 0
    position_in_range = (current_price - recent_low) / max(recent_high - recent_low, 0.000001)
    return {
        "interval": candles.interval,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "rsi_14": rsi(closes, 14),
        "atr_14": atr_14,
        "atr_pct": atr_pct,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "recent_range_pct": range_pct,
        "volume_ratio": volume_ratio,
        "taker_buy_ratio": taker_buy_ratio,
        "last_body_pct": last_body_pct,
        "position_in_recent_range": min(1, max(0, position_in_range)),
        "distance_to_recent_high_pct": distance_pct(recent_high, current_price),
        "distance_to_recent_low_pct": distance_pct(current_price, recent_low),
        "price_vs_ema_21_pct": distance_pct(current_price, ema_21),
        "ema_stack": classify_ema_stack(ema_9, ema_21, ema_50),
    }


def detect_levels(candles: CandleSet, current_price: float, lookback: int = 120) -> dict:
    highs = candles.highs[-lookback:]
    lows = candles.lows[-lookback:]
    closes = candles.closes[-lookback:]
    resistances = sorted(
        [price for price in highs if price > current_price],
        key=lambda price: abs(price - current_price),
    )
    supports = sorted(
        [price for price in lows if price < current_price],
        key=lambda price: abs(price - current_price),
    )
    nearest_resistance = cluster_level(resistances[:12])
    nearest_support = cluster_level(supports[:12])
    return {
        "lookback_candles": min(lookback, len(closes)),
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "distance_to_support_pct": abs(distance_pct(current_price, nearest_support)) if nearest_support else None,
        "distance_to_resistance_pct": abs(distance_pct(nearest_resistance, current_price)) if nearest_resistance else None,
    }


def cluster_level(values: list[float]) -> float | None:
    if not values:
        return None
    return fmean(values[: min(5, len(values))])


def classify_ema_stack(ema_9: float, ema_21: float, ema_50: float) -> str:
    if ema_9 > ema_21 > ema_50:
        return "bullish"
    if ema_9 < ema_21 < ema_50:
        return "bearish"
    return "mixed"


def summarize_order_book(depth: dict) -> dict:
    bids = [(float(price), float(qty)) for price, qty in depth.get("bids", [])]
    asks = [(float(price), float(qty)) for price, qty in depth.get("asks", [])]
    bid_notional = sum(price * qty for price, qty in bids)
    ask_notional = sum(price * qty for price, qty in asks)
    total = bid_notional + ask_notional
    imbalance = ((bid_notional - ask_notional) / total) if total else 0.0
    best_bid = bids[0][0] if bids else 0.0
    best_ask = asks[0][0] if asks else 0.0
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
    spread_pct = pct(best_ask - best_bid, mid) if mid else 0.0
    return {
        "bid_notional_top20": bid_notional,
        "ask_notional_top20": ask_notional,
        "imbalance": imbalance,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_pct": spread_pct,
    }


def summarize_trade_flow(trades: list[dict]) -> dict:
    buy_notional = 0.0
    sell_notional = 0.0
    cvd = 0.0
    for trade in trades:
        price = float(trade.get("p", 0))
        quantity = float(trade.get("q", 0))
        notional = price * quantity
        is_buyer_maker = bool(trade.get("m", False))
        if is_buyer_maker:
            sell_notional += notional
            cvd -= notional
        else:
            buy_notional += notional
            cvd += notional
    total = buy_notional + sell_notional
    return {
        "sample_trades": len(trades),
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "buy_ratio": buy_notional / total if total else None,
        "sell_ratio": sell_notional / total if total else None,
        "cvd_notional": cvd,
        "cvd_ratio": cvd / total if total else None,
    }


def open_interest_change(symbol: str, period: str, limit: int) -> dict:
    history = market_data.get_open_interest_history(symbol, period, limit)
    values = [float(item.get("sumOpenInterest", 0)) for item in history if item.get("sumOpenInterest") is not None]
    return {
        "period": period,
        "limit": limit,
        "change_pct": distance_pct(values[-1], values[0]) if len(values) >= 2 else None,
        "count": len(values),
    }


def summarize_derivatives(symbol: str) -> dict:
    funding = market_data.get_funding_snapshot(symbol) or {}
    open_interest = market_data.get_open_interest(symbol) or {}
    funding_history = market_data.get_funding_history(symbol, 8)
    derivative_periods = {
        "5m": {
            "open_interest": open_interest_change(symbol, "5m", 30),
            "global_long_short_ratio": market_data.get_global_long_short_ratio(symbol, "5m") or {},
            "taker_buy_sell_ratio": market_data.get_taker_long_short_ratio(symbol, "5m") or {},
        },
        "1h": {
            "open_interest": open_interest_change(symbol, "1h", 24),
            "global_long_short_ratio": market_data.get_global_long_short_ratio(symbol, "1h") or {},
            "taker_buy_sell_ratio": market_data.get_taker_long_short_ratio(symbol, "1h") or {},
        },
        "1d": {
            "open_interest": open_interest_change(symbol, "1d", 30),
            "global_long_short_ratio": market_data.get_global_long_short_ratio(symbol, "1d") or {},
            "taker_buy_sell_ratio": market_data.get_taker_long_short_ratio(symbol, "1d") or {},
        },
    }
    global_ratio = derivative_periods["5m"]["global_long_short_ratio"]
    taker_ratio = derivative_periods["5m"]["taker_buy_sell_ratio"]
    oi_change_pct = derivative_periods["5m"]["open_interest"]["change_pct"]
    funding_values = [float(item.get("fundingRate", 0)) * 100 for item in funding_history if item.get("fundingRate") is not None]
    return {
        "funding_rate_pct": float(funding.get("lastFundingRate", 0)) * 100 if funding else None,
        "funding_avg_recent_pct": fmean(funding_values) if funding_values else None,
        "funding_history_count": len(funding_values),
        "mark_price": float(funding.get("markPrice", 0)) if funding else None,
        "index_price": float(funding.get("indexPrice", 0)) if funding else None,
        "next_funding_time": funding.get("nextFundingTime") if funding else None,
        "open_interest": float(open_interest.get("openInterest", 0)) if open_interest else None,
        "open_interest_change_5m_window_pct": oi_change_pct,
        "open_interest_history_count": derivative_periods["5m"]["open_interest"]["count"],
        "global_long_short_ratio": float(global_ratio.get("longShortRatio", 0)) if global_ratio else None,
        "global_long_account_pct": float(global_ratio.get("longAccount", 0)) * 100 if global_ratio else None,
        "global_short_account_pct": float(global_ratio.get("shortAccount", 0)) * 100 if global_ratio else None,
        "taker_buy_sell_ratio": float(taker_ratio.get("buySellRatio", 0)) if taker_ratio else None,
        "taker_buy_volume": float(taker_ratio.get("buyVol", 0)) if taker_ratio else None,
        "taker_sell_volume": float(taker_ratio.get("sellVol", 0)) if taker_ratio else None,
        "by_period": {
            period: {
                "open_interest_change_pct": data["open_interest"]["change_pct"],
                "open_interest_history_count": data["open_interest"]["count"],
                "global_long_short_ratio": float(data["global_long_short_ratio"].get("longShortRatio", 0)) if data["global_long_short_ratio"] else None,
                "global_long_account_pct": float(data["global_long_short_ratio"].get("longAccount", 0)) * 100 if data["global_long_short_ratio"] else None,
                "global_short_account_pct": float(data["global_long_short_ratio"].get("shortAccount", 0)) * 100 if data["global_long_short_ratio"] else None,
                "taker_buy_sell_ratio": float(data["taker_buy_sell_ratio"].get("buySellRatio", 0)) if data["taker_buy_sell_ratio"] else None,
                "taker_buy_volume": float(data["taker_buy_sell_ratio"].get("buyVol", 0)) if data["taker_buy_sell_ratio"] else None,
                "taker_sell_volume": float(data["taker_buy_sell_ratio"].get("sellVol", 0)) if data["taker_buy_sell_ratio"] else None,
            }
            for period, data in derivative_periods.items()
        },
    }


def summarize_global_market() -> dict:
    global_data = market_data.get_global_crypto_market() or {}
    data = global_data.get("data", {}) if isinstance(global_data.get("data"), dict) else {}
    market_cap_pct = data.get("market_cap_percentage", {}) if isinstance(data.get("market_cap_percentage"), dict) else {}
    return {
        "total_market_cap_usd": (data.get("total_market_cap") or {}).get("usd") if isinstance(data.get("total_market_cap"), dict) else None,
        "total_volume_usd": (data.get("total_volume") or {}).get("usd") if isinstance(data.get("total_volume"), dict) else None,
        "btc_dominance_pct": market_cap_pct.get("btc"),
        "eth_dominance_pct": market_cap_pct.get("eth"),
        "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        "markets": data.get("markets"),
    }


def summarize_market_breadth(limit: int = 100) -> dict:
    assets = market_data.get_top_crypto_assets(limit)
    changes_1h = [float(item.get("price_change_percentage_1h_in_currency")) for item in assets if item.get("price_change_percentage_1h_in_currency") is not None]
    changes_24h = [float(item.get("price_change_percentage_24h_in_currency")) for item in assets if item.get("price_change_percentage_24h_in_currency") is not None]
    changes_7d = [float(item.get("price_change_percentage_7d_in_currency")) for item in assets if item.get("price_change_percentage_7d_in_currency") is not None]
    return {
        "sample_size": len(assets),
        "advancers_1h_pct": pct(sum(1 for value in changes_1h if value > 0), len(changes_1h)) if changes_1h else None,
        "advancers_24h_pct": pct(sum(1 for value in changes_24h if value > 0), len(changes_24h)) if changes_24h else None,
        "advancers_7d_pct": pct(sum(1 for value in changes_7d if value > 0), len(changes_7d)) if changes_7d else None,
        "median_change_1h_pct": statistics.median(changes_1h) if changes_1h else None,
        "median_change_24h_pct": statistics.median(changes_24h) if changes_24h else None,
        "median_change_7d_pct": statistics.median(changes_7d) if changes_7d else None,
        "strong_moves_24h_pct": pct(sum(1 for value in changes_24h if abs(value) >= 5), len(changes_24h)) if changes_24h else None,
    }


def summarize_sentiment() -> dict:
    fear_greed = market_data.get_fear_greed_index() or {}
    value = fear_greed.get("value")
    return {
        "fear_greed_value": int(value) if value is not None and str(value).isdigit() else None,
        "fear_greed_classification": fear_greed.get("value_classification"),
        "fear_greed_timestamp": fear_greed.get("timestamp"),
        "fear_greed_time_until_update": fear_greed.get("time_until_update"),
    }


def availability(snapshot: dict) -> dict:
    derivatives = snapshot["derivatives"]
    sentiment = snapshot["sentiment"]
    global_market = snapshot["global_market"]
    market_breadth = snapshot["market_breadth"]
    trade_flow = snapshot["trade_flow"]
    return {
        "spot_price": snapshot["current_price"] is not None,
        "spot_klines": bool(snapshot["timeframes"]),
        "order_book": bool(snapshot["order_book"].get("best_bid")),
        "spot_trade_flow": trade_flow.get("sample_trades", 0) > 0,
        "ticker_24h": snapshot["ticker_24h"].get("quote_volume", 0) > 0,
        "funding": derivatives.get("funding_rate_pct") is not None,
        "open_interest": derivatives.get("open_interest") is not None,
        "open_interest_history": derivatives.get("open_interest_change_5m_window_pct") is not None,
        "funding_history": derivatives.get("funding_avg_recent_pct") is not None,
        "long_short_ratio": derivatives.get("global_long_short_ratio") is not None,
        "taker_futures_ratio": derivatives.get("taker_buy_sell_ratio") is not None,
        "fear_greed": sentiment.get("fear_greed_value") is not None,
        "global_crypto_market": global_market.get("total_market_cap_usd") is not None,
        "market_breadth": market_breadth.get("advancers_24h_pct") is not None,
    }


def build_market_snapshot(symbol: str) -> dict:
    symbol = symbol.upper()
    current_price = market_data.get_price(symbol)
    timeframes = {
        interval: parse_klines(market_data.get_klines(symbol, interval, 240), interval)
        for interval in ("5m", "15m", "1h", "4h", "1d", "1w")
    }
    depth = market_data.get_depth(symbol)
    trades = market_data.get_agg_trades(symbol, 500)
    ticker_24h = market_data.get_24h_ticker(symbol)
    derivatives = summarize_derivatives(symbol)
    global_market = summarize_global_market()
    market_breadth = summarize_market_breadth(100)
    sentiment = summarize_sentiment()

    snapshot = {
        "symbol": symbol,
        "source": {
            "price": "binance_spot_ticker",
            "klines": "binance_spot_klines",
            "order_book": "binance_spot_depth",
            "trade_flow": "binance_spot_agg_trades",
            "ticker_24h": "binance_spot_24hr",
            "derivatives": "binance_usdm_futures_public",
            "global_market": "coingecko_global",
            "market_breadth": "coingecko_top_markets",
            "sentiment": "alternative_me_fear_greed",
        },
        "current_price": current_price,
        "timeframes": {
            interval: summarize_timeframe(candles, current_price)
            for interval, candles in timeframes.items()
        },
        "levels": {
            interval: detect_levels(candles, current_price)
            for interval, candles in timeframes.items()
        },
        "order_book": summarize_order_book(depth),
        "trade_flow": summarize_trade_flow(trades),
        "ticker_24h": {
            "price_change_pct": float(ticker_24h.get("priceChangePercent", 0)),
            "quote_volume": float(ticker_24h.get("quoteVolume", 0)),
            "high": float(ticker_24h.get("highPrice", 0)),
            "low": float(ticker_24h.get("lowPrice", 0)),
        },
        "derivatives": derivatives,
        "global_market": global_market,
        "market_breadth": market_breadth,
        "sentiment": sentiment,
    }
    snapshot["availability"] = availability(snapshot)
    return snapshot
