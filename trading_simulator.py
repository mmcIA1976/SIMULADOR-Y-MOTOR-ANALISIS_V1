#!/usr/bin/env python3
"""
Simulador educativo de operaciones long/short con precios publicos de Binance Futures.

No ejecuta ordenes reales ni usa claves API.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime


BINANCE_USDM_BASE_URLS = (
    "https://fapi.binance.com",
)
BINANCE_MARKET_TIMEOUT_SECONDS = 4.5
_preferred_futures_base_url = BINANCE_USDM_BASE_URLS[0]


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
    global _preferred_futures_base_url
    last_error: Exception | None = None
    safe_symbol = urllib.parse.quote(symbol)
    candidate_bases = (_preferred_futures_base_url,) + tuple(
        base for base in BINANCE_USDM_BASE_URLS if base != _preferred_futures_base_url
    )
    for base_url in candidate_bases:
        url = f"{base_url}/fapi/v1/ticker/price?symbol={safe_symbol}"
        request = urllib.request.Request(url, headers={"User-Agent": "trading-simulator/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=BINANCE_MARKET_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            _preferred_futures_base_url = base_url
            return float(payload["price"])
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"No se pudo consultar precio de {symbol}: {last_error}")


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
