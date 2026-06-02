#!/usr/bin/env python3
"""
Simulador educativo de operaciones long/short con precios publicos de Binance.

No ejecuta ordenes reales ni usa claves API.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime


BINANCE_SPOT_BASE_URLS = (
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
)
BINANCE_SPOT_TIMEOUT_SECONDS = 4.5
_preferred_spot_base_by_symbol: dict[str, str] = {}
COINGECKO_TIMEOUT_SECONDS = 6.0
COINGECKO_SYMBOL_TO_ID = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
    "XRPUSDT": "ripple",
    "INJUSDT": "injective-protocol",
}


def _candidate_spot_bases(symbol: str) -> tuple[str, ...]:
    preferred = _preferred_spot_base_by_symbol.get(symbol.upper(), BINANCE_SPOT_BASE_URLS[-1])
    return (preferred,) + tuple(base for base in BINANCE_SPOT_BASE_URLS if base != preferred)


def _remember_spot_base(symbol: str, base_url: str) -> None:
    _preferred_spot_base_by_symbol[symbol.upper()] = base_url


def _fetch_coingecko_price(symbol: str) -> float | None:
    coin_id = COINGECKO_SYMBOL_TO_ID.get(symbol.upper())
    if not coin_id:
        return None
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={urllib.parse.quote(coin_id)}&vs_currencies=usd"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "trading-simulator/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=COINGECKO_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        value = float(payload.get(coin_id, {}).get("usd", 0))
        return value if value > 0 else None
    except Exception:
        return None


MAX_LEVERAGE = 10


@dataclass(frozen=True)
class TradeConfig:
    symbol: str
    side: str
    entry: float
    margin: float
    leverage: float
    stop_loss: float
    take_profit: float
    interval_seconds: int


def parse_args() -> tuple[TradeConfig, bool]:
    parser = argparse.ArgumentParser(
        description="Simula una operacion de trading con precio actual de Binance."
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Simbolo de Binance, ej. BTCUSDT.")
    parser.add_argument("--side", choices=["long", "short"], default="long")
    parser.add_argument("--entry", type=float, default=76766)
    parser.add_argument("--margin", type=float, default=200)
    parser.add_argument("--leverage", type=float, default=10)
    parser.add_argument("--stop-loss", type=float, default=76000)
    parser.add_argument("--take-profit", type=float, default=79500)
    parser.add_argument("--interval", type=int, default=120, help="Segundos entre consultas.")
    parser.add_argument("--once", action="store_true", help="Consulta una vez y termina.")
    args = parser.parse_args()

    if args.leverage <= 0:
        parser.error("El apalancamiento debe ser mayor que 0.")
    if args.leverage > MAX_LEVERAGE:
        parser.error(f"El apalancamiento maximo permitido es x{MAX_LEVERAGE}.")
    if args.margin <= 0:
        parser.error("El margen debe ser mayor que 0.")
    if args.entry <= 0:
        parser.error("La entrada debe ser mayor que 0.")
    if args.interval <= 0:
        parser.error("El intervalo debe ser mayor que 0.")

    config = TradeConfig(
        symbol=args.symbol.upper(),
        side=args.side,
        entry=args.entry,
        margin=args.margin,
        leverage=args.leverage,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
        interval_seconds=args.interval,
    )
    return config, args.once


def fetch_binance_price(symbol: str) -> float:
    last_error: Exception | None = None
    normalized_symbol = symbol.upper()
    safe_symbol = urllib.parse.quote(normalized_symbol)
    candidate_bases = _candidate_spot_bases(normalized_symbol)
    for base_url in candidate_bases:
        # Prefer bookTicker (bid/ask) for more reactive updates than last trade.
        book_url = f"{base_url}/api/v3/ticker/bookTicker?symbol={safe_symbol}"
        request = urllib.request.Request(book_url, headers={"User-Agent": "trading-simulator/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=BINANCE_SPOT_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            bid = float(payload.get("bidPrice", 0))
            ask = float(payload.get("askPrice", 0))
            if bid > 0 and ask > 0:
                _remember_spot_base(normalized_symbol, base_url)
                return (bid + ask) / 2
        except Exception as exc:
            last_error = exc

        ticker_url = f"{base_url}/api/v3/ticker/price?symbol={safe_symbol}"
        request = urllib.request.Request(ticker_url, headers={"User-Agent": "trading-simulator/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=BINANCE_SPOT_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            _remember_spot_base(normalized_symbol, base_url)
            return float(payload["price"])
        except Exception as exc:
            last_error = exc

    fallback = _fetch_coingecko_price(normalized_symbol)
    if fallback is not None:
        return fallback

    raise RuntimeError(f"No se pudo consultar precio de {normalized_symbol}: {last_error}")


def calculate_trade_state(config: TradeConfig, current_price: float) -> tuple[float, float, str]:
    raw_variation_pct = ((current_price - config.entry) / config.entry) * 100

    if config.side == "long":
        pnl = config.margin * config.leverage * (raw_variation_pct / 100)
        if current_price <= config.stop_loss:
            state = "STOP LOSS"
        elif current_price >= config.take_profit:
            state = "TAKE PROFIT"
        else:
            state = "ABIERTA"
    else:
        pnl = config.margin * config.leverage * (-raw_variation_pct / 100)
        if current_price >= config.stop_loss:
            state = "STOP LOSS"
        elif current_price <= config.take_profit:
            state = "TAKE PROFIT"
        else:
            state = "ABIERTA"

    return raw_variation_pct, pnl, state


def print_snapshot(config: TradeConfig, current_price: float) -> str:
    variation_pct, pnl, state = calculate_trade_state(config, current_price)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    output = (
        f"[{timestamp}] {config.symbol} {config.side.upper()} | "
        f"precio={current_price:.2f} | entrada={config.entry:.2f} | "
        f"variacion={variation_pct:+.4f}% | margen={config.margin:.2f} | "
        f"apalancamiento=x{config.leverage:g} | PnL aprox={pnl:+.2f} USDT | "
        f"estado={state}"
    )
    print(output, flush=True)
    return state


def run(config: TradeConfig, once: bool) -> None:
    print("Simulador iniciado. No se ejecutaran ordenes reales de trading.", flush=True)
    print(
        f"Activo={config.symbol} | lado={config.side.upper()} | entrada={config.entry} | "
        f"SL={config.stop_loss} | TP={config.take_profit} | intervalo={config.interval_seconds}s",
        flush=True,
    )

    while True:
        try:
            current_price = fetch_binance_price(config.symbol)
            state = print_snapshot(config, current_price)
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
            print(f"[{timestamp}] Error consultando precio: {exc}", flush=True)
            state = "ERROR"

        if once or state in {"STOP LOSS", "TAKE PROFIT"}:
            break

        time.sleep(config.interval_seconds)


if __name__ == "__main__":
    trade_config, run_once = parse_args()
    run(trade_config, run_once)
