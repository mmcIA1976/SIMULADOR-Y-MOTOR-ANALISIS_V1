from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = (
    ROOT
    / "auditorias_motor"
    / "2026-07-27_M3_verificacion_viva_fuentes.json"
)

SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)

HEADERS = {
    "User-Agent": "trading-simulator-m3-audit/0.1",
    "Accept": "application/json",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc,
    ).isoformat()


def request_json(url: str, timeout_seconds: float) -> tuple[Any, dict]:
    requested_at_ms = now_ms()
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")
        status_code = int(response.status)
    received_at_ms = now_ms()
    return json.loads(raw), {
        "http_status": status_code,
        "requested_at": iso_from_ms(requested_at_ms),
        "received_at": iso_from_ms(received_at_ms),
        "latency_ms": received_at_ms - requested_at_ms,
    }


def require_dict_fields(payload: Any, fields: tuple[str, ...]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload_not_object")
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"missing_fields:{','.join(missing)}")


def require_list_item_fields(
    payload: Any,
    fields: tuple[str, ...],
) -> None:
    if not isinstance(payload, list) or not payload:
        raise ValueError("payload_not_nonempty_array")
    require_dict_fields(payload[-1], fields)


def validate_klines(payload: Any) -> None:
    if (
        not isinstance(payload, list)
        or not payload
        or not isinstance(payload[-1], list)
        or len(payload[-1]) < 11
    ):
        raise ValueError("invalid_kline_schema")


PER_SYMBOL_ENDPOINTS = {
    "M3-DATA-004": {
        "name": "futures_price_v2",
        "url": (
            "https://fapi.binance.com/fapi/v2/ticker/price?symbol={symbol}"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            ("symbol", "price", "time"),
        ),
    },
    "M3-DATA-005": {
        "name": "futures_klines_5m",
        "url": (
            "https://fapi.binance.com/fapi/v1/klines?"
            "symbol={symbol}&interval=5m&limit=2"
        ),
        "validator": validate_klines,
    },
    "M3-DATA-006": {
        "name": "futures_depth",
        "url": (
            "https://fapi.binance.com/fapi/v1/depth?"
            "symbol={symbol}&limit=5"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            ("lastUpdateId", "E", "T", "bids", "asks"),
        ),
    },
    "M3-DATA-007": {
        "name": "futures_aggregate_trades",
        "url": (
            "https://fapi.binance.com/fapi/v1/aggTrades?"
            "symbol={symbol}&limit=2"
        ),
        "validator": lambda payload: require_list_item_fields(
            payload,
            ("a", "p", "q", "T", "m"),
        ),
    },
    "M3-DATA-008": {
        "name": "futures_book_ticker",
        "url": (
            "https://fapi.binance.com/fapi/v1/ticker/bookTicker?"
            "symbol={symbol}"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            ("symbol", "bidPrice", "bidQty", "askPrice", "askQty", "time"),
        ),
    },
    "M3-DATA-009": {
        "name": "futures_24h_ticker",
        "url": (
            "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            (
                "symbol",
                "priceChangePercent",
                "quoteVolume",
                "highPrice",
                "lowPrice",
                "openTime",
                "closeTime",
            ),
        ),
    },
    "M3-DATA-010": {
        "name": "futures_mark_index_funding",
        "url": (
            "https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            (
                "symbol",
                "markPrice",
                "indexPrice",
                "lastFundingRate",
                "nextFundingTime",
                "time",
            ),
        ),
    },
    "M3-DATA-011": {
        "name": "futures_funding_history",
        "url": (
            "https://fapi.binance.com/fapi/v1/fundingRate?"
            "symbol={symbol}&limit=2"
        ),
        "validator": lambda payload: require_list_item_fields(
            payload,
            ("symbol", "fundingRate", "fundingTime", "markPrice"),
        ),
    },
    "M3-DATA-013": {
        "name": "futures_open_interest",
        "url": (
            "https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            ("symbol", "openInterest", "time"),
        ),
    },
    "M3-DATA-014": {
        "name": "futures_open_interest_history",
        "url": (
            "https://fapi.binance.com/futures/data/openInterestHist?"
            "symbol={symbol}&period=5m&limit=2"
        ),
        "validator": lambda payload: require_list_item_fields(
            payload,
            ("symbol", "sumOpenInterest", "sumOpenInterestValue", "timestamp"),
        ),
    },
    "M3-DATA-015": {
        "name": "futures_taker_buy_sell_volume",
        "url": (
            "https://fapi.binance.com/futures/data/takerlongshortRatio?"
            "symbol={symbol}&period=5m&limit=2"
        ),
        "validator": lambda payload: require_list_item_fields(
            payload,
            ("buySellRatio", "buyVol", "sellVol", "timestamp"),
        ),
    },
    "M3-DATA-017": {
        "name": "spot_book_ticker",
        "url": (
            "https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
        ),
        "validator": lambda payload: require_dict_fields(
            payload,
            ("symbol", "bidPrice", "bidQty", "askPrice", "askQty"),
        ),
    },
}


def validate_exchange_info(
    payload: Any,
    *,
    expected_symbols: tuple[str, ...],
) -> None:
    require_dict_fields(payload, ("symbols",))
    symbols = {
        str(item.get("symbol")): item
        for item in payload["symbols"]
        if isinstance(item, dict)
    }
    missing = [symbol for symbol in expected_symbols if symbol not in symbols]
    if missing:
        raise ValueError(f"symbols_missing:{','.join(missing)}")
    not_trading = [
        symbol
        for symbol in expected_symbols
        if symbols[symbol].get("status") != "TRADING"
    ]
    if not_trading:
        raise ValueError(f"symbols_not_trading:{','.join(not_trading)}")


GLOBAL_ENDPOINTS = {
    "M3-DATA-002": {
        "name": "futures_exchange_info",
        "url": "https://fapi.binance.com/fapi/v1/exchangeInfo",
        "validator": lambda payload: validate_exchange_info(
            payload,
            expected_symbols=SYMBOLS,
        ),
    },
    "M3-DATA-003": {
        "name": "futures_server_time",
        "url": "https://fapi.binance.com/fapi/v1/time",
        "validator": lambda payload: require_dict_fields(
            payload,
            ("serverTime",),
        ),
    },
    "M3-DATA-012": {
        "name": "futures_funding_info",
        "url": "https://fapi.binance.com/fapi/v1/fundingInfo",
        "validator": lambda payload: (
            None
            if isinstance(payload, list)
            else (_ for _ in ()).throw(ValueError("payload_not_array"))
        ),
    },
    "M3-DATA-016": {
        "name": "spot_exchange_info",
        "url": "https://api.binance.com/api/v3/exchangeInfo",
        "validator": lambda payload: validate_exchange_info(
            payload,
            expected_symbols=SYMBOLS,
        ),
    },
}


def audit_endpoint(
    contract_id: str,
    endpoint: dict,
    *,
    timeout_seconds: float,
    symbol: str | None = None,
) -> dict:
    url = endpoint["url"].format(
        symbol=urllib.parse.quote(symbol or ""),
    )
    item = {
        "contract_id": contract_id,
        "name": endpoint["name"],
        "symbol": symbol,
        "ok": False,
        "url": url,
        "http_status": None,
        "requested_at": None,
        "received_at": None,
        "latency_ms": None,
        "error": None,
    }
    try:
        payload, timing = request_json(url, timeout_seconds)
        item.update(timing)
        endpoint["validator"](payload)
        item["ok"] = True
    except Exception as exc:
        item["error"] = f"{type(exc).__name__}:{exc}"
    return item


def build_live_audit(timeout_seconds: float) -> dict:
    started_at_ms = now_ms()
    checks = [
        audit_endpoint(
            contract_id,
            endpoint,
            timeout_seconds=timeout_seconds,
        )
        for contract_id, endpoint in GLOBAL_ENDPOINTS.items()
    ]
    for symbol in SYMBOLS:
        checks.extend(
            audit_endpoint(
                contract_id,
                endpoint,
                timeout_seconds=timeout_seconds,
                symbol=symbol,
            )
            for contract_id, endpoint in PER_SYMBOL_ENDPOINTS.items()
        )
    finished_at_ms = now_ms()
    passed = sum(1 for item in checks if item["ok"])
    return {
        "audit_version": "M3-live-source-audit-v0.1",
        "status": "pass" if passed == len(checks) else "fail",
        "started_at": iso_from_ms(started_at_ms),
        "finished_at": iso_from_ms(finished_at_ms),
        "symbols": list(SYMBOLS),
        "summary": {
            "checks": len(checks),
            "passed": passed,
            "failed": len(checks) - passed,
            "per_symbol_endpoint_checks": (
                len(SYMBOLS) * len(PER_SYMBOL_ENDPOINTS)
            ),
            "global_endpoint_checks": len(GLOBAL_ENDPOINTS),
            "authenticated_checks_skipped": 1,
        },
        "authenticated_checks": [
            {
                "contract_id": "M3-DATA-018",
                "endpoint": "/fapi/v1/commissionRate",
                "status": "not_executed_authentication_required",
            }
        ],
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    audit = build_live_audit(args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"M3 live checks: {audit['summary']['passed']}/"
        f"{audit['summary']['checks']}"
    )
    if audit["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
