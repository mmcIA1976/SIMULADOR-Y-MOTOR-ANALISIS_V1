from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DEFAULT_CATALOG_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
DEFAULT_MATRIX_PATH = (
    AUDIT_DIR / "matriz_dato_bloque_par_horizonte_m3_v0_1.json"
)
DEFAULT_AUDIT_PATH = (
    AUDIT_DIR / "auditoria_datos_motor_actual_m3_v0_1.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M3_contrato_auditoria_datos_pretrade_resultado.md"
)
LIVE_AUDIT_PATH = (
    AUDIT_DIR / "2026-07-27_M3_verificacion_viva_fuentes.json"
)

CATALOG_VERSION = "M3-data-contracts-v0.1"
MATRIX_VERSION = "M3-data-block-pair-horizon-matrix-v0.1"
CURRENT_AUDIT_VERSION = "M3-current-data-audit-v0.1"
M3_APPROVED_AT = "2026-07-27"

SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = (
    "intraday_short",
    "intraday_wide",
    "short_swing",
)

FUTURES_DOC = (
    "https://developers.binance.com/en/docs/catalog/"
    "core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/"
    "market-data"
)
FUTURES_ACCOUNT_DOC = (
    "https://developers.binance.com/en/docs/catalog/"
    "core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/"
    "account"
)
SPOT_MARKET_DOC = (
    "https://developers.binance.com/en/docs/catalog/"
    "core-trading-spot-trading/api/rest-api/market"
)
SPOT_GENERAL_DOC = (
    "https://developers.binance.com/en/docs/catalog/"
    "core-trading-spot-trading/api/rest-api/general"
)

REALTIME_MAX_AGE_MS = 30_000
SNAPSHOT_MAX_SPAN_MS = 15_000
REQUEST_MAX_LATENCY_MS = 10_000
PERIOD_RELEASE_GRACE_MS = 60_000
METADATA_MAX_AGE_MS = 24 * 60 * 60 * 1000
COMMISSION_MAX_AGE_MS = 60 * 60 * 1000
CROSS_VENUE_CAPTURE_SKEW_MS = 2_000


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_contract(
    contract_id: str,
    name: str,
    *,
    provider: str,
    market: str,
    endpoint: str,
    authentication: str,
    fields: list[dict],
    timestamp_fields: list[dict],
    freshness: dict,
    retention: str,
    blocks: list[int],
    current_status: str,
    current_refs: list[str],
    source_status: str = "approved_public_source",
    reconstruction: str = "requires_local_capture_for_exact_replay",
    documentation_url: str = FUTURES_DOC,
    missing_effect: str = "rule_not_evaluated_never_neutral",
    limitations: list[str] | None = None,
) -> dict:
    return {
        "id": contract_id,
        "name": name,
        "priority": "P0",
        "provider": provider,
        "market": market,
        "endpoint": endpoint,
        "authentication": authentication,
        "source_status": source_status,
        "documentation_url": documentation_url,
        "fields": fields,
        "time_contract": {
            "timestamp_fields": timestamp_fields,
            "requested_at_required": True,
            "received_at_required": True,
            "analysis_rule": (
                "provider_time<=received_at<=analysis_at; future data block"
            ),
            "freshness": freshness,
            "snapshot_max_span_ms": SNAPSHOT_MAX_SPAN_MS,
            "request_max_latency_ms": REQUEST_MAX_LATENCY_MS,
        },
        "retention": retention,
        "historical_reconstruction": reconstruction,
        "supported_symbols": list(SYMBOLS),
        "supported_horizons": list(HORIZONS),
        "p0_blocks": blocks,
        "missing_effect": missing_effect,
        "current_implementation": {
            "status": current_status,
            "source_refs": current_refs,
        },
        "limitations": limitations or [],
    }


def field(name: str, meaning: str, unit: str) -> dict:
    return {"field": name, "meaning": meaning, "unit": unit}


def timestamp_field(name: str, meaning: str) -> dict:
    return {"field": name, "meaning": meaning, "unit": "unix_ms_utc"}


def build_source_contracts() -> list[dict]:
    contracts = [
        source_contract(
            "M3-DATA-001",
            "Plan propuesto por el usuario",
            provider="application_user_input",
            market="binance_usdm_perpetual_plan",
            endpoint="POST /api/analyze",
            authentication="application_session",
            fields=[
                field("symbol", "USD-M Futures symbol", "symbol"),
                field("side", "long or short", "enum"),
                field("entry_type", "market or pending", "enum"),
                field(
                    "trigger_condition",
                    "pending trigger: price_lte or price_gte; null for market",
                    "enum_or_null",
                ),
                field("entry", "planned entry price", "quote_asset_per_base"),
                field(
                    "margin",
                    "user-requested margin allocation",
                    "quote_asset",
                ),
                field(
                    "leverage",
                    "user-requested exposure multiple",
                    "multiple",
                ),
                field("take_profit", "planned TP barrier", "quote_asset_per_base"),
                field("stop_loss", "planned SL barrier", "quote_asset_per_base"),
                field("time_horizon", "approved horizon profile", "enum"),
                field("horizon_seconds", "exact analysis duration", "seconds"),
            ],
            timestamp_fields=[
                timestamp_field(
                    "request_received_at",
                    "server receipt of the immutable proposal",
                )
            ],
            freshness={
                "kind": "request_identity",
                "rule": "request_received_at defines the proposal cutoff",
            },
            retention="stored_with_recommendation",
            blocks=[1, 26, 28, 29, 30, 32],
            current_status="implemented_noncompliant",
            current_refs=["app.py:92-102", "app.py:4055-4100"],
            source_status="approved_internal_source",
            reconstruction="stored_values_available_but_exact_request_time_missing",
            limitations=[
                "horizon_seconds is stamped after analysis, not received with the plan",
                "symbol is not checked against exchangeInfo before collection",
            ],
        ),
        source_contract(
            "M3-DATA-002",
            "Reglas y metadatos USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/exchangeInfo",
            authentication="public",
            fields=[
                field("symbols[].status", "trading status", "enum"),
                field("symbols[].contractType", "contract type", "enum"),
                field("symbols[].baseAsset", "base asset", "asset"),
                field("symbols[].quoteAsset", "quote asset", "asset"),
                field("symbols[].filters", "price quantity and notional rules", "object"),
                field("symbols[].marketTakeBound", "market order price bound", "ratio"),
            ],
            timestamp_fields=[],
            freshness={
                "kind": "captured_configuration",
                "max_age_ms": METADATA_MAX_AGE_MS,
                "rule": "symbol must be TRADING and contract/quote must match",
            },
            retention="current_configuration_only",
            blocks=[1, 3, 7, 9, 10, 15, 24, 26, 28, 29, 30],
            current_status="not_implemented",
            current_refs=["market_data.py"],
            limitations=[
                "exchangeInfo serverTime is explicitly not the clock source",
            ],
        ),
        source_contract(
            "M3-DATA-003",
            "Reloj del proveedor USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/time",
            authentication="public",
            fields=[field("serverTime", "Binance server time", "unix_ms_utc")],
            timestamp_fields=[
                timestamp_field("serverTime", "provider clock at response")
            ],
            freshness={
                "kind": "clock_alignment",
                "max_age_ms": REALTIME_MAX_AGE_MS,
                "rule": "record server offset and never infer provider time locally",
            },
            retention="current_only",
            blocks=[1, 3, 7, 9, 10, 15, 24, 26, 28, 29],
            current_status="not_implemented",
            current_refs=["market_data.py"],
        ),
        source_contract(
            "M3-DATA-004",
            "Ultimo precio USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v2/ticker/price",
            authentication="public",
            fields=[
                field("symbol", "contract symbol", "symbol"),
                field("price", "latest traded price", "quote_asset_per_base"),
                field("time", "transaction time", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("time", "transaction time")
            ],
            freshness={
                "kind": "realtime_event",
                "max_age_ms": REALTIME_MAX_AGE_MS,
            },
            retention="current_only",
            blocks=[1, 15, 24, 26, 28, 29],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:21", "market_data.py:234-244"],
            limitations=[
                "production uses deprecated v1 route and returns only float",
                "memory-cache capture time is hidden from the snapshot",
            ],
        ),
        source_contract(
            "M3-DATA-005",
            "Velas USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/klines",
            authentication="public",
            fields=[
                field("[0]", "open time", "unix_ms_utc"),
                field("[1]", "open", "quote_asset_per_base"),
                field("[2]", "high", "quote_asset_per_base"),
                field("[3]", "low", "quote_asset_per_base"),
                field("[4]", "close", "quote_asset_per_base"),
                field("[5]", "base volume", "base_asset"),
                field("[6]", "close time", "unix_ms_utc"),
                field("[7]", "quote volume", "quote_asset"),
                field("[8]", "trade count", "count"),
                field("[9]", "taker buy base volume", "base_asset"),
                field("[10]", "taker buy quote volume", "quote_asset"),
            ],
            timestamp_fields=[
                timestamp_field("[0]", "bar open time"),
                timestamp_field("[6]", "bar close time"),
            ],
            freshness={
                "kind": "closed_period",
                "rule": (
                    "only close_time<=analysis_at is closed; latest closed "
                    "bar gap must be <= interval_ms+60000"
                ),
                "release_grace_ms": PERIOD_RELEASE_GRACE_MS,
            },
            retention="provider_retention_not_committed",
            blocks=[1, 3, 24, 26, 28],
            current_status="implemented_noncompliant",
            current_refs=["data_engine.py:11", "data_engine.py:74-82", "data_engine.py:539-544"],
            reconstruction=(
                "REST pagination can reconstruct available history but local "
                "raw storage is required for guaranteed reproducibility"
            ),
            limitations=[
                "production discards open and close timestamps",
                "production does not separate the open partial candle",
                "production substitutes neutral indicators when candles are missing",
            ],
        ),
        source_contract(
            "M3-DATA-006",
            "Profundidad USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/depth",
            authentication="public",
            fields=[
                field("lastUpdateId", "order book update id", "identifier"),
                field("E", "message output time", "unix_ms_utc"),
                field("T", "transaction time", "unix_ms_utc"),
                field("bids[][0]", "bid price", "quote_asset_per_base"),
                field("bids[][1]", "bid quantity", "base_asset"),
                field("asks[][0]", "ask price", "quote_asset_per_base"),
                field("asks[][1]", "ask quantity", "base_asset"),
            ],
            timestamp_fields=[
                timestamp_field("E", "message output time"),
                timestamp_field("T", "transaction time"),
            ],
            freshness={
                "kind": "realtime_snapshot",
                "max_age_ms": REALTIME_MAX_AGE_MS,
            },
            retention="current_snapshot_only",
            blocks=[7, 29],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:23", "data_engine.py:334-352"],
            limitations=[
                "production requests only 20 levels and discards E/T/update id",
                "standard depth excludes RPI orders by provider definition",
                "visible depth is not guaranteed executable depth",
            ],
        ),
        source_contract(
            "M3-DATA-007",
            "Operaciones agregadas USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/aggTrades",
            authentication="public",
            fields=[
                field("a", "aggregate trade id", "identifier"),
                field("p", "trade price", "quote_asset_per_base"),
                field("q", "quantity", "base_asset"),
                field("T", "trade time", "unix_ms_utc"),
                field("m", "buyer was maker", "boolean"),
            ],
            timestamp_fields=[
                timestamp_field("T", "aggregate trade timestamp")
            ],
            freshness={
                "kind": "explicit_event_window",
                "max_last_event_age_ms": REALTIME_MAX_AGE_MS,
                "rule": (
                    "startTime/endTime and a duration selected in M4 are "
                    "mandatory; a last-N sample is forbidden"
                ),
            },
            retention="only_last_24_hours_by_provider",
            blocks=[7, 29],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:276-290", "data_engine.py:355-379"],
            limitations=[
                "production uses latest 500 trades with variable elapsed time",
                "RPI fills are aggregated without a distinguishing tag",
                "insurance fund and ADL trades are excluded",
            ],
        ),
        source_contract(
            "M3-DATA-008",
            "Mejor bid/ask USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/ticker/bookTicker",
            authentication="public",
            fields=[
                field("bidPrice", "best bid", "quote_asset_per_base"),
                field("bidQty", "best bid quantity", "base_asset"),
                field("askPrice", "best ask", "quote_asset_per_base"),
                field("askQty", "best ask quantity", "base_asset"),
                field("time", "transaction time", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("time", "book transaction time")
            ],
            freshness={
                "kind": "realtime_event",
                "max_age_ms": REALTIME_MAX_AGE_MS,
            },
            retention="current_only",
            blocks=[15, 29],
            current_status="not_implemented",
            current_refs=["market_data.py"],
            limitations=["RPI orders are excluded by provider definition"],
        ),
        source_contract(
            "M3-DATA-009",
            "Estadistica movil 24h USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/ticker/24hr",
            authentication="public",
            fields=[
                field("priceChangePercent", "rolling price change", "percent"),
                field("quoteVolume", "rolling quote volume", "quote_asset"),
                field("highPrice", "rolling high", "quote_asset_per_base"),
                field("lowPrice", "rolling low", "quote_asset_per_base"),
                field("openTime", "rolling window start", "unix_ms_utc"),
                field("closeTime", "rolling window end", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("openTime", "rolling window start"),
                timestamp_field("closeTime", "rolling window end"),
            ],
            freshness={
                "kind": "rolling_window",
                "max_age_ms": REALTIME_MAX_AGE_MS,
            },
            retention="current_rolling_window_only",
            blocks=[24],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:24", "data_engine.py:597-602"],
            limitations=[
                "production discards openTime/closeTime",
                "missing payload becomes zero-valued evidence",
            ],
        ),
        source_contract(
            "M3-DATA-010",
            "Mark, indice y funding actual USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/premiumIndex",
            authentication="public",
            fields=[
                field("markPrice", "mark price", "quote_asset_per_base"),
                field("indexPrice", "index price", "quote_asset_per_base"),
                field("lastFundingRate", "latest funding rate", "ratio"),
                field("nextFundingTime", "next funding time", "unix_ms_utc"),
                field("time", "snapshot time", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("time", "provider snapshot time"),
                timestamp_field("nextFundingTime", "scheduled next funding"),
            ],
            freshness={
                "kind": "realtime_snapshot",
                "max_age_ms": REALTIME_MAX_AGE_MS,
            },
            retention="current_only",
            blocks=[10, 15, 29],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:26", "data_engine.py:426-431"],
            limitations=["production discards provider snapshot time"],
        ),
        source_contract(
            "M3-DATA-011",
            "Historial de funding USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/fundingRate",
            authentication="public",
            fields=[
                field("fundingRate", "settled funding rate", "ratio"),
                field("fundingTime", "funding settlement time", "unix_ms_utc"),
                field("markPrice", "mark price for funding charge", "quote_asset_per_base"),
            ],
            timestamp_fields=[
                timestamp_field("fundingTime", "funding settlement time")
            ],
            freshness={
                "kind": "scheduled_event_history",
                "rule": (
                    "latest fundingTime must be compatible with the current "
                    "fundingIntervalHours and <=analysis_at"
                ),
            },
            retention="provider_retention_not_committed",
            blocks=[10, 29],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:31", "data_engine.py:424-428"],
            limitations=[
                "production averages eight rates without preserving timestamps",
                "production does not account for funding interval changes",
            ],
        ),
        source_contract(
            "M3-DATA-012",
            "Configuracion del intervalo de funding",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/fundingInfo",
            authentication="public",
            fields=[
                field("symbol", "contract symbol", "symbol"),
                field("fundingIntervalHours", "current funding interval", "hours"),
                field("adjustedFundingRateCap", "adjusted cap", "ratio"),
                field("adjustedFundingRateFloor", "adjusted floor", "ratio"),
            ],
            timestamp_fields=[],
            freshness={
                "kind": "captured_configuration",
                "max_age_ms": METADATA_MAX_AGE_MS,
                "rule": (
                    "absence from response means no documented adjustment; "
                    "capture time remains mandatory"
                ),
            },
            retention="current_adjustments_only",
            blocks=[10, 29],
            current_status="not_implemented",
            current_refs=["market_data.py"],
        ),
        source_contract(
            "M3-DATA-013",
            "Open interest actual USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /fapi/v1/openInterest",
            authentication="public",
            fields=[
                field("openInterest", "present open interest", "base_asset"),
                field("time", "transaction time", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("time", "provider transaction time")
            ],
            freshness={
                "kind": "realtime_snapshot",
                "max_age_ms": REALTIME_MAX_AGE_MS,
            },
            retention="current_only",
            blocks=[9],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:27", "data_engine.py:432"],
            limitations=["production discards provider time"],
        ),
        source_contract(
            "M3-DATA-014",
            "Historial de open interest USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /futures/data/openInterestHist",
            authentication="public",
            fields=[
                field("sumOpenInterest", "total open interest", "base_asset"),
                field("sumOpenInterestValue", "total open interest value", "quote_asset"),
                field("timestamp", "period end time", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("timestamp", "period end time")
            ],
            freshness={
                "kind": "completed_period",
                "rule": (
                    "latest timestamp<=analysis_at and lag<="
                    "period_ms+60000"
                ),
                "release_grace_ms": PERIOD_RELEASE_GRACE_MS,
            },
            retention="latest_one_month_only",
            blocks=[9],
            current_status="implemented_noncompliant",
            current_refs=["data_engine.py:382-390", "data_engine.py:393-454"],
            limitations=[
                "production discards all period timestamps",
                "no local archive exists beyond provider retention",
            ],
        ),
        source_contract(
            "M3-DATA-015",
            "Volumen taker buy/sell USD-M Futures",
            provider="binance",
            market="usd_m_futures",
            endpoint="GET /futures/data/takerlongshortRatio",
            authentication="public",
            fields=[
                field("buySellRatio", "taker buy/sell ratio", "ratio"),
                field("buyVol", "taker buy volume", "base_asset"),
                field("sellVol", "taker sell volume", "base_asset"),
                field("timestamp", "period start time", "unix_ms_utc"),
            ],
            timestamp_fields=[
                timestamp_field("timestamp", "period start time")
            ],
            freshness={
                "kind": "completed_period",
                "rule": (
                    "period must be complete at analysis_at and release lag "
                    "must be <=period_ms+60000"
                ),
                "release_grace_ms": PERIOD_RELEASE_GRACE_MS,
            },
            retention="latest_30_days_only",
            blocks=[7],
            current_status="implemented_noncompliant",
            current_refs=["market_data.py:35-37", "data_engine.py:438-450"],
            limitations=[
                "production requests one row and discards timestamp",
                "no local archive exists beyond provider retention",
            ],
        ),
        source_contract(
            "M3-DATA-016",
            "Reglas y metadatos Binance Spot",
            provider="binance",
            market="spot",
            endpoint="GET /api/v3/exchangeInfo",
            authentication="public",
            fields=[
                field("symbols[].status", "spot trading status", "enum"),
                field("symbols[].baseAsset", "base asset", "asset"),
                field("symbols[].quoteAsset", "quote asset", "asset"),
                field("symbols[].filters", "spot execution filters", "object"),
            ],
            timestamp_fields=[],
            freshness={
                "kind": "captured_configuration",
                "max_age_ms": METADATA_MAX_AGE_MS,
            },
            retention="current_configuration_only",
            blocks=[15],
            current_status="not_implemented",
            current_refs=["market_data.py"],
            documentation_url=SPOT_GENERAL_DOC,
        ),
        source_contract(
            "M3-DATA-017",
            "Mejor bid/ask Binance Spot",
            provider="binance",
            market="spot",
            endpoint="GET /api/v3/ticker/bookTicker",
            authentication="public",
            fields=[
                field("bidPrice", "best spot bid", "quote_asset_per_base"),
                field("bidQty", "best spot bid quantity", "base_asset"),
                field("askPrice", "best spot ask", "quote_asset_per_base"),
                field("askQty", "best spot ask quantity", "base_asset"),
            ],
            timestamp_fields=[],
            freshness={
                "kind": "receive_time_only",
                "max_request_latency_ms": REQUEST_MAX_LATENCY_MS,
                "cross_venue_capture_skew_ms": CROSS_VENUE_CAPTURE_SKEW_MS,
                "rule": (
                    "provider supplies no event timestamp; requested_at and "
                    "received_at plus cross-venue skew are mandatory"
                ),
            },
            retention="current_only",
            blocks=[15],
            current_status="not_implemented",
            current_refs=["market_data.py"],
            documentation_url=SPOT_MARKET_DOC,
            limitations=[
                "REST response has no provider event timestamp",
                "basis quality is lower than same-timestamp index basis",
            ],
        ),
        source_contract(
            "M3-DATA-018",
            "Comision efectiva del usuario USD-M Futures",
            provider="binance",
            market="usd_m_futures_account",
            endpoint="GET /fapi/v1/commissionRate",
            authentication="signed_user_data",
            fields=[
                field("makerCommissionRate", "account maker commission", "ratio"),
                field("takerCommissionRate", "account taker commission", "ratio"),
                field("rpiCommissionRate", "account RPI commission", "ratio"),
            ],
            timestamp_fields=[],
            freshness={
                "kind": "authenticated_configuration",
                "max_age_ms": COMMISSION_MAX_AGE_MS,
                "rule": (
                    "without authenticated or explicitly user-configured "
                    "rates, exact execution economics are unavailable"
                ),
            },
            retention="current_account_configuration_only",
            blocks=[29],
            current_status="not_implemented",
            current_refs=["analysis_engine.py:1889-1892"],
            source_status="approved_conditional_auth_source",
            documentation_url=FUTURES_ACCOUNT_DOC,
            missing_effect=(
                "market_path_may_remain_available_but_exact_ev_and_execution_"
                "decision_blocked"
            ),
            limitations=[
                "not anonymously accessible",
                "M3 live audit intentionally did not use account credentials",
            ],
        ),
    ]
    return contracts


P0_BLOCK_DATA = {
    1: {
        "name": "Estructura del precio",
        "required": ["M3-DATA-001", "M3-DATA-002", "M3-DATA-003", "M3-DATA-005"],
        "conditional": ["M3-DATA-004"],
    },
    3: {
        "name": "Multi-timeframe",
        "required": ["M3-DATA-002", "M3-DATA-003", "M3-DATA-005"],
        "conditional": [],
    },
    7: {
        "name": "Order flow",
        "required": ["M3-DATA-002", "M3-DATA-003", "M3-DATA-007", "M3-DATA-015"],
        "conditional": ["M3-DATA-006"],
    },
    9: {
        "name": "Open interest",
        "required": ["M3-DATA-002", "M3-DATA-003", "M3-DATA-013", "M3-DATA-014"],
        "conditional": [],
    },
    10: {
        "name": "Funding",
        "required": [
            "M3-DATA-002",
            "M3-DATA-003",
            "M3-DATA-010",
            "M3-DATA-011",
            "M3-DATA-012",
        ],
        "conditional": [],
    },
    15: {
        "name": "Spot contra futuros",
        "required": [
            "M3-DATA-002",
            "M3-DATA-003",
            "M3-DATA-008",
            "M3-DATA-016",
            "M3-DATA-017",
        ],
        "conditional": ["M3-DATA-010"],
    },
    24: {
        "name": "Regimen de mercado",
        "required": ["M3-DATA-002", "M3-DATA-003", "M3-DATA-005"],
        "conditional": ["M3-DATA-009"],
    },
    26: {
        "name": "Estadistica y cuantitativo",
        "required": ["M3-DATA-001", "M3-DATA-002", "M3-DATA-003", "M3-DATA-005"],
        "conditional": [],
    },
    28: {
        "name": "Probabilidad TP/SL",
        "required": ["M3-DATA-001", "M3-DATA-002", "M3-DATA-003", "M3-DATA-005"],
        "conditional": [
            "M3-DATA-007",
            "M3-DATA-010",
            "M3-DATA-014",
            "M3-DATA-015",
            "M3-DATA-017",
        ],
    },
    29: {
        "name": "Ejecucion y costes",
        "required": [
            "M3-DATA-001",
            "M3-DATA-002",
            "M3-DATA-003",
            "M3-DATA-006",
            "M3-DATA-008",
            "M3-DATA-010",
            "M3-DATA-011",
            "M3-DATA-012",
            "M3-DATA-018",
        ],
        "conditional": ["M3-DATA-017"],
    },
    30: {
        "name": "Gestion de riesgo",
        "required": ["M3-DATA-001", "M3-DATA-002"],
        "conditional": [],
    },
    32: {
        "name": "Evaluacion del rendimiento",
        "required": ["M3-DATA-001"],
        "conditional": [],
        "note": (
            "M3 covers only the immutable pre-trade identity; outcome data "
            "remain outside this phase."
        ),
    },
}


def validate_observation_time(
    *,
    provider_time_ms: int | None,
    requested_at_ms: int,
    received_at_ms: int,
    analysis_at_ms: int,
    max_age_ms: int,
) -> dict:
    for name, value in (
        ("requested_at_ms", requested_at_ms),
        ("received_at_ms", received_at_ms),
        ("analysis_at_ms", analysis_at_ms),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"invalid_{name}")
    if provider_time_ms is not None and (
        not isinstance(provider_time_ms, int)
        or isinstance(provider_time_ms, bool)
        or provider_time_ms < 0
    ):
        raise ValueError("invalid_provider_time_ms")
    if not requested_at_ms <= received_at_ms <= analysis_at_ms:
        raise ValueError("invalid_capture_order")
    if received_at_ms - requested_at_ms > REQUEST_MAX_LATENCY_MS:
        raise ValueError("request_latency_exceeded")
    evidence_time_ms = (
        provider_time_ms if provider_time_ms is not None else received_at_ms
    )
    if evidence_time_ms > analysis_at_ms:
        raise ValueError("future_data")
    age_ms = analysis_at_ms - evidence_time_ms
    if age_ms > max_age_ms:
        raise ValueError("stale_data")
    return {
        "status": "valid",
        "evidence_time_ms": evidence_time_ms,
        "age_ms": age_ms,
        "timestamp_quality": (
            "provider_time"
            if provider_time_ms is not None
            else "receive_time_only"
        ),
    }


def closed_klines_before_analysis(
    raw_klines: list[list],
    *,
    analysis_at_ms: int,
    interval_ms: int,
) -> list[list]:
    if interval_ms <= 0:
        raise ValueError("invalid_interval_ms")
    valid = []
    previous_open = None
    for item in raw_klines:
        if not isinstance(item, list) or len(item) < 11:
            raise ValueError("invalid_kline_schema")
        open_time = int(item[0])
        close_time = int(item[6])
        if previous_open is not None and open_time <= previous_open:
            raise ValueError("klines_not_strictly_ordered")
        previous_open = open_time
        if close_time <= analysis_at_ms:
            valid.append(item)
    if not valid:
        raise ValueError("no_closed_klines")
    latest_close = int(valid[-1][6])
    if analysis_at_ms - latest_close > interval_ms + PERIOD_RELEASE_GRACE_MS:
        raise ValueError("closed_klines_stale")
    return valid


def validate_snapshot_capture(
    observations: list[dict],
    *,
    analysis_at_ms: int,
) -> dict:
    if not observations:
        raise ValueError("empty_snapshot_capture")
    validated = [
        validate_observation_time(
            provider_time_ms=item.get("provider_time_ms"),
            requested_at_ms=item["requested_at_ms"],
            received_at_ms=item["received_at_ms"],
            analysis_at_ms=analysis_at_ms,
            max_age_ms=int(item.get("max_age_ms", REALTIME_MAX_AGE_MS)),
        )
        for item in observations
    ]
    received_times = [item["received_at_ms"] for item in observations]
    capture_span_ms = max(received_times) - min(received_times)
    if capture_span_ms > SNAPSHOT_MAX_SPAN_MS:
        raise ValueError("snapshot_capture_span_exceeded")
    return {
        "status": "valid",
        "observation_count": len(observations),
        "capture_span_ms": capture_span_ms,
        "provider_timestamp_count": sum(
            1 for item in validated if item["timestamp_quality"] == "provider_time"
        ),
        "receive_time_only_count": sum(
            1
            for item in validated
            if item["timestamp_quality"] == "receive_time_only"
        ),
    }


def read_live_audit() -> dict:
    if not LIVE_AUDIT_PATH.exists():
        raise FileNotFoundError(LIVE_AUDIT_PATH)
    return json.loads(LIVE_AUDIT_PATH.read_text(encoding="utf-8"))


def build_catalog() -> dict:
    contracts = build_source_contracts()
    live_audit = read_live_audit()
    source_files = [
        ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
        ROOT / "CONTRATO_FASE_1_MOTOR_ANALISIS.md",
        AUDIT_DIR / "contrato_semantico_m2_v0_1.json",
        AUDIT_DIR / "matriz_decisiones_m1_v0_1.json",
        ROOT / "market_data.py",
        ROOT / "data_engine.py",
        ROOT / "analysis_engine.py",
        ROOT / "app.py",
        LIVE_AUDIT_PATH,
    ]
    statuses: dict[str, int] = {}
    for item in contracts:
        status = item["current_implementation"]["status"]
        statuses[status] = statuses.get(status, 0) + 1
    payload = {
        "catalog_version": CATALOG_VERSION,
        "phase": "M3",
        "status": "completed_owner_approved",
        "approved_at": M3_APPROVED_AT,
        "scope": {
            "production_modified": False,
            "analysis_engine_modified": False,
            "m4_started": False,
            "predictive_rules_defined": False,
            "learning_engine_used": False,
            "p1_liquidations_included": False,
        },
        "post_closure_clarifications": [
            {
                "id": "M3-CLARIFICATION-001",
                "identified_in_phase": "M4.2",
                "date": "2026-07-27",
                "contract_id": "M3-DATA-001",
                "field_added": "trigger_condition",
                "reason": (
                    "Pending-entry activation cannot be reconstructed from "
                    "entry_type and price alone. The field already exists in "
                    "POST /api/analyze and was omitted from the M3 field list."
                ),
                "source_or_endpoint_changed": False,
                "production_modified": False,
                "m3_conclusions_changed": False,
            },
            {
                "id": "M3-CLARIFICATION-002",
                "identified_in_phase": "M4.5",
                "date": "2026-07-27",
                "contract_id": "M3-DATA-001",
                "fields_added": ["margin", "leverage"],
                "reason": (
                    "Plan exposure and loss on requested margin cannot be "
                    "reconstructed from price geometry alone. Both fields "
                    "already exist in POST /api/analyze and were omitted "
                    "from the M3 field list."
                ),
                "source_or_endpoint_changed": False,
                "production_modified": False,
                "m3_conclusions_changed": False,
            },
        ],
        "universe": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "futures_market": "Binance USD-M perpetual",
            "spot_market": "Binance Spot",
        },
        "operational_policies": {
            "classification": (
                "project limits, not latency guarantees made by Binance"
            ),
            "realtime_max_age_ms": REALTIME_MAX_AGE_MS,
            "snapshot_max_span_ms": SNAPSHOT_MAX_SPAN_MS,
            "request_max_latency_ms": REQUEST_MAX_LATENCY_MS,
            "period_release_grace_ms": PERIOD_RELEASE_GRACE_MS,
            "metadata_max_age_ms": METADATA_MAX_AGE_MS,
            "commission_max_age_ms": COMMISSION_MAX_AGE_MS,
            "cross_venue_capture_skew_ms": CROSS_VENUE_CAPTURE_SKEW_MS,
        },
        "global_invariants": [
            {
                "id": "M3-INV-PRETRADE-01",
                "rule": (
                    "Every provider timestamp, request and response must be "
                    "<=analysis_at."
                ),
            },
            {
                "id": "M3-INV-CAPTURE-01",
                "rule": (
                    "requested_at and received_at are mandatory per source; "
                    "the complete snapshot capture span is bounded."
                ),
            },
            {
                "id": "M3-INV-MISSING-01",
                "rule": (
                    "Missing, stale, invalid, unsupported or future data is "
                    "never converted to neutral evidence."
                ),
            },
            {
                "id": "M3-INV-CLOSED-BAR-01",
                "rule": (
                    "Closed and partial candles are distinct; only bars with "
                    "close_time<=analysis_at satisfy the closed-bar contract."
                ),
            },
            {
                "id": "M3-INV-PAIR-01",
                "rule": (
                    "Symbol, market, quote asset, contract type and TRADING "
                    "status must be validated from exchangeInfo."
                ),
            },
            {
                "id": "M3-INV-UNIT-01",
                "rule": (
                    "Raw units are retained; normalization is explicit and "
                    "belongs to the future rule contract."
                ),
            },
            {
                "id": "M3-INV-RETENTION-01",
                "rule": (
                    "Provider retention is not local history; exact replay "
                    "requires immutable raw local capture."
                ),
            },
            {
                "id": "M3-INV-SEPARATION-01",
                "rule": (
                    "Unavailable cost data may block EV/execution decisions "
                    "without changing market-path probability."
                ),
            },
            {
                "id": "M3-INV-SOURCE-01",
                "rule": (
                    "Official source semantics validate a datum, not its "
                    "predictive value."
                ),
            },
        ],
        "contracts": contracts,
        "summary": {
            "contracts": len(contracts),
            "public_or_internal_approved": sum(
                1
                for item in contracts
                if item["source_status"]
                in {"approved_public_source", "approved_internal_source"}
            ),
            "conditional_auth": sum(
                1
                for item in contracts
                if item["source_status"] == "approved_conditional_auth_source"
            ),
            "current_statuses": statuses,
            "live_checks": live_audit["summary"]["checks"],
            "live_passed": live_audit["summary"]["passed"],
            "live_failed": live_audit["summary"]["failed"],
        },
        "live_verification": {
            "path": str(LIVE_AUDIT_PATH.relative_to(ROOT)),
            "sha256": file_sha256(LIVE_AUDIT_PATH),
            "status": live_audit["status"],
            "started_at": live_audit["started_at"],
            "finished_at": live_audit["finished_at"],
        },
        "official_sources": [
            {
                "provider": "Binance USD-M Futures",
                "url": FUTURES_DOC,
                "scope": "public market data and exchange metadata",
            },
            {
                "provider": "Binance USD-M Futures",
                "url": FUTURES_ACCOUNT_DOC,
                "scope": "signed user commission rate",
            },
            {
                "provider": "Binance Spot",
                "url": SPOT_MARKET_DOC,
                "scope": "public spot market data",
            },
            {
                "provider": "Binance Spot",
                "url": SPOT_GENERAL_DOC,
                "scope": "spot exchange metadata and server time",
            },
        ],
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in source_files
        ],
    }
    payload["catalog_sha256"] = sha256_text(
        canonical_json(
            {
                "universe": payload["universe"],
                "operational_policies": payload["operational_policies"],
                "global_invariants": payload["global_invariants"],
                "contracts": payload["contracts"],
            }
        )
    )
    return payload


def build_matrix(catalog: dict) -> dict:
    contracts_by_id = {
        item["id"]: item
        for item in catalog["contracts"]
    }
    rows = []
    for block_id, block in P0_BLOCK_DATA.items():
        for symbol in SYMBOLS:
            for horizon in HORIZONS:
                required_statuses = {
                    contract_id: contracts_by_id[contract_id][
                        "current_implementation"
                    ]["status"]
                    for contract_id in block["required"]
                }
                current_ready = all(
                    value == "implemented_compliant"
                    for value in required_statuses.values()
                )
                rows.append(
                    {
                        "block_id": block_id,
                        "block_name": block["name"],
                        "rule_contract_status": "not_defined_until_M4",
                        "symbol": symbol,
                        "time_horizon": horizon,
                        "required_data_ids": block["required"],
                        "conditional_data_ids": block["conditional"],
                        "current_required_statuses": required_statuses,
                        "rigorous_candidate_ready": current_ready,
                        "missing_policy": (
                            "block_block_or_rule; never synthesize neutral "
                            "evidence"
                        ),
                        "note": block.get("note"),
                    }
                )
    payload = {
        "matrix_version": MATRIX_VERSION,
        "phase": "M3",
        "status": "completed_owner_approved",
        "approved_at": M3_APPROVED_AT,
        "meaning": (
            "M3 maps data to P0 analytical blocks, pairs and horizons. Exact "
            "rule IDs do not exist until M4 and are not fabricated here."
        ),
        "summary": {
            "p0_blocks": len(P0_BLOCK_DATA),
            "symbols": len(SYMBOLS),
            "horizons": len(HORIZONS),
            "rows": len(rows),
            "current_ready_rows": sum(
                1 for row in rows if row["rigorous_candidate_ready"]
            ),
        },
        "rows": rows,
    }
    payload["matrix_sha256"] = sha256_text(canonical_json(rows))
    return payload


def build_current_audit() -> dict:
    market_source = (ROOT / "market_data.py").read_text(encoding="utf-8")
    data_source = (ROOT / "data_engine.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    analysis_source = (ROOT / "analysis_engine.py").read_text(encoding="utf-8")
    findings = [
        {
            "id": "M3-CURRENT-FAIL-01",
            "severity": "critical",
            "reason": (
                "analysis_at is stamped after analyze_trade finishes and no "
                "analysis_started_at or source-level data_cutoff is recorded."
            ),
            "observation": {
                "analyze_before_stamp": (
                    app_source.index("result = analyze_trade(proposal)")
                    < app_source.index(
                        'stamp_pre_trade_horizon(result["snapshot"]'
                    )
                )
            },
            "source_refs": ["app.py:4080", "app.py:4096"],
        },
        {
            "id": "M3-CURRENT-FAIL-02",
            "severity": "critical",
            "reason": (
                "P0 Binance observations do not retain requested_at, "
                "received_at and provider timestamps in the snapshot."
            ),
            "observation": {
                "candle_fields": [
                    "interval",
                    "closes",
                    "highs",
                    "lows",
                    "volumes",
                    "taker_buy_volumes",
                ],
                "source_level_capture_metadata": False,
            },
            "source_refs": ["data_engine.py:17-23", "data_engine.py:74-82"],
        },
        {
            "id": "M3-CURRENT-FAIL-03",
            "severity": "critical",
            "reason": (
                "The current open candle is not distinguished from closed "
                "candles before indicators are calculated."
            ),
            "observation": {
                "close_time_parsed": "kline[6]" in data_source,
                "current_open_bar_filter": "close_time" in data_source,
            },
            "source_refs": ["data_engine.py:74-82", "data_engine.py:104-166"],
        },
        {
            "id": "M3-CURRENT-FAIL-04",
            "severity": "critical",
            "reason": (
                "Missing candles become neutral-looking EMA, RSI, ATR and "
                "volume values instead of blocking evidence."
            ),
            "observation": {
                "neutral_rsi": '"rsi_14": 50.0' in data_source,
                "neutral_volume": '"volume_ratio": 1.0' in data_source,
            },
            "source_refs": ["data_engine.py:110-131"],
        },
        {
            "id": "M3-CURRENT-FAIL-05",
            "severity": "critical",
            "reason": (
                "Optional HTTP helpers and future_value suppress provider "
                "errors into None, empty objects or empty arrays without a "
                "field-level failure reason."
            ),
            "observation": {
                "optional_helper_present": "def get_json_optional" in market_source,
                "future_default_present": "def future_value" in data_source,
            },
            "source_refs": ["market_data.py:133-137", "data_engine.py:97-101"],
        },
        {
            "id": "M3-CURRENT-FAIL-06",
            "severity": "high",
            "reason": (
                "Order flow uses the latest 500 aggregate trades, so its "
                "elapsed time changes with market activity."
            ),
            "observation": {
                "fixed_last_n_call": (
                    "get_agg_trades, symbol, 500" in data_source
                ),
                "explicit_time_window": False,
            },
            "source_refs": ["data_engine.py:531", "data_engine.py:355-379"],
        },
        {
            "id": "M3-CURRENT-FAIL-07",
            "severity": "critical",
            "reason": (
                "OI and taker period timestamps are discarded, so freshness "
                "and completed-period status cannot be proved."
            ),
            "observation": {
                "oi_timestamp_retained": False,
                "taker_timestamp_retained": False,
            },
            "source_refs": ["data_engine.py:382-454"],
        },
        {
            "id": "M3-CURRENT-FAIL-08",
            "severity": "high",
            "reason": (
                "OI and taker history are provider-limited to about one month "
                "and no immutable local raw archive exists."
            ),
            "observation": {
                "provider_oi_retention": "latest_one_month",
                "provider_taker_retention": "latest_30_days",
                "local_raw_archive": False,
            },
            "source_refs": ["market_data.py:305-310", "market_data.py:327-332"],
        },
        {
            "id": "M3-CURRENT-FAIL-09",
            "severity": "high",
            "reason": (
                "Funding history is averaged over eight rows without funding "
                "interval metadata or retained event times."
            ),
            "observation": {
                "funding_history_limit": 8,
                "funding_info_endpoint_integrated": (
                    "/fapi/v1/fundingInfo" in market_source
                ),
            },
            "source_refs": ["data_engine.py:400", "data_engine.py:424-428"],
        },
        {
            "id": "M3-CURRENT-FAIL-10",
            "severity": "critical",
            "reason": (
                "The P0 spot-versus-futures block has no Binance Spot source "
                "in the current market snapshot."
            ),
            "observation": {
                "spot_api_present": "api.binance.com/api/v3" in market_source,
                "spot_snapshot_field_present": '"spot"' in data_source,
            },
            "source_refs": ["market_data.py", "data_engine.py:525-610"],
        },
        {
            "id": "M3-CURRENT-FAIL-11",
            "severity": "critical",
            "reason": (
                "Commission and minimum slippage are hardcoded rather than "
                "captured from account and market data."
            ),
            "observation": {
                "hardcoded_round_trip_fee": (
                    "fee_rate_round_trip = 0.0008" in analysis_source
                ),
                "hardcoded_slippage_floor": (
                    "slippage_rate_round_trip = max" in analysis_source
                ),
            },
            "source_refs": ["analysis_engine.py:1889-1892"],
        },
        {
            "id": "M3-CURRENT-FAIL-12",
            "severity": "high",
            "reason": (
                "Symbol status, contract type, quote asset and exchange "
                "precision are not validated through exchangeInfo."
            ),
            "observation": {
                "futures_exchange_info_integrated": (
                    "/fapi/v1/exchangeInfo" in market_source
                ),
                "spot_exchange_info_integrated": (
                    "/api/v3/exchangeInfo" in market_source
                ),
            },
            "source_refs": ["market_data.py", "app.py:4064-4079"],
        },
        {
            "id": "M3-CURRENT-FAIL-13",
            "severity": "high",
            "reason": (
                "The current price route is deprecated v1 instead of the "
                "documented v2 route and its time field is discarded."
            ),
            "observation": {
                "current_path": (
                    "/fapi/v1/ticker/price"
                    if "/fapi/v1/ticker/price" in market_source
                    else None
                ),
                "v2_path_present": "/fapi/v2/ticker/price" in market_source,
            },
            "source_refs": ["market_data.py:21", "market_data.py:234-244"],
        },
        {
            "id": "M3-CURRENT-FAIL-14",
            "severity": "critical",
            "reason": (
                "A missing 24h ticker becomes zero change, zero volume and "
                "zero barriers while analysis continues."
            ),
            "observation": {
                "zero_price_change_fallback": (
                    'ticker_24h.get("priceChangePercent", 0)' in data_source
                ),
                "zero_volume_fallback": (
                    'ticker_24h.get("quoteVolume", 0)' in data_source
                ),
            },
            "source_refs": ["data_engine.py:597-602"],
        },
        {
            "id": "M3-CURRENT-FAIL-15",
            "severity": "critical",
            "reason": (
                "No field-level quality, capture span or blocking-reason "
                "contract exists for the assembled snapshot."
            ),
            "observation": {
                "availability_is_boolean_only": True,
                "snapshot_capture_span_recorded": False,
                "blocking_reasons_recorded": False,
            },
            "source_refs": ["data_engine.py:499-522", "data_engine.py:567-610"],
        },
    ]
    for item in findings:
        item["status"] = "fail"
    return {
        "audit_version": CURRENT_AUDIT_VERSION,
        "phase": "M3",
        "status": "current_data_pipeline_fails_m3_contract_as_expected",
        "summary": {
            "findings": len(findings),
            "failures": len(findings),
            "critical": sum(
                1 for item in findings if item["severity"] == "critical"
            ),
            "high": sum(
                1 for item in findings if item["severity"] == "high"
            ),
            "production_modified": False,
        },
        "findings": findings,
    }


def render_report(
    catalog: dict,
    matrix: dict,
    audit: dict,
) -> str:
    summary = catalog["summary"]
    lines = [
        "# M3 - Contrato y auditoria de datos pre-trade",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADA Y APROBADA EL 2026-07-27",
        "",
        "## 1. Limite de la fase",
        "",
        "M3 certifica significado, origen, mercado, campos, unidades, tiempo,",
        "frescura, cobertura, retencion y politica de ausencia de los datos P0.",
        "No define reglas predictivas, indicadores, pesos ni modelo probabilistico.",
        "No modifica la aplicacion productiva y M4 no se ha iniciado.",
        "",
        "La documentacion oficial acredita que el dato existe y que significan",
        "sus campos. No acredita que el dato prediga TP o SL; esa hipotesis",
        "debera formularse en M4 y verificarse despues.",
        "",
        "## 2. Universo comprobado",
        "",
        "Pares: " + ", ".join(f"`{item}`" for item in SYMBOLS) + ".",
        "",
        "Marcos: " + ", ".join(f"`{item}`" for item in HORIZONS) + ".",
        "",
        "Mercados: Binance USD-M Futures perpetuos y Binance Spot.",
        "",
        "La auditoria viva fechada paso "
        f"**{summary['live_passed']}/{summary['live_checks']}** comprobaciones",
        "publicas de esquema y cobertura. La comision de usuario no se consulto",
        "porque exige credenciales y firma; su fuente queda aprobada de forma",
        "condicional, no fingida como dato anonimo.",
        "",
        "Liquidaciones HyperPerps/Hyperliquid quedan fuera de M3 porque el bloque",
        "12 es P1. Su integracion actual no se usa para certificar el nucleo P0.",
        "",
        "Aclaracion posterior al cierre `M3-CLARIFICATION-001`: M4.2 detecto",
        "que `trigger_condition` ya era recibido por `POST /api/analyze` pero",
        "faltaba en la lista de campos de `M3-DATA-001`. Se incorpora para",
        "reconstruir entradas pendientes. No cambia proveedor, endpoint,",
        "conclusiones ni produccion.",
        "",
        "Aclaracion posterior al cierre `M3-CLARIFICATION-002`: M4.5 detecto",
        "que `margin` y `leverage` ya eran recibidos por `POST /api/analyze`",
        "pero faltaban en `M3-DATA-001`. Se incorporan para separar geometria",
        "de mercado, exposicion y perdida sobre margen. No cambia proveedor,",
        "endpoint, conclusiones ni produccion.",
        "",
        "## 3. Contratos de datos",
        "",
        f"Se definen **{summary['contracts']} contratos**:",
        "",
        "| ID | Dato | Endpoint | Fuente | Estado actual |",
        "|---|---|---|---|---|",
    ]
    for item in catalog["contracts"]:
        lines.append(
            f"| `{item['id']}` | {item['name']} | `{item['endpoint']}` | "
            f"`{item['source_status']}` | "
            f"`{item['current_implementation']['status']}` |"
        )
    lines.extend(
        [
            "",
            "Las fuentes son viables; eso no significa que la ruta productiva",
            "actual las capture con el contrato exigido. Ningun dato incompleto",
            "queda autorizado por defecto para M4.",
            "",
            "## 4. Politica temporal",
            "",
            "- Cada consulta registra `requested_at` y `received_at`.",
            "- Cada timestamp del proveedor se conserva sin sustituirlo.",
            "- Todo timestamp predictivo debe ser anterior o igual a `analysis_at`.",
            f"- Datos de tiempo real: antiguedad maxima de {REALTIME_MAX_AGE_MS // 1000} s.",
            f"- Captura completa del snapshot: maximo {SNAPSHOT_MAX_SPAN_MS // 1000} s.",
            f"- Latencia maxima por consulta: {REQUEST_MAX_LATENCY_MS // 1000} s.",
            "- Las velas abiertas se separan; solo una vela cuyo cierre sea",
            "  anterior a `analysis_at` cumple el contrato de vela cerrada.",
            "- OI y taker periodicos conservan timestamp y periodo exactos.",
            "- Los limites anteriores son politica operativa del proyecto, no",
            "  promesas de latencia atribuidas a Binance.",
            "",
            "## 5. Ausencia y degradacion",
            "",
            "- Dato obligatorio ausente, stale, futuro, invalido o no soportado:",
            "  bloquea el bloque o produce evidencia insuficiente.",
            "- Dato condicional ausente: la regla futura no se evalua.",
            "- Nunca se crean RSI=50, volumen=1, cambio=0 u otra evidencia neutral.",
            "- Comision exacta ausente: puede mantenerse separada la probabilidad",
            "  de mercado, pero no se publica EV ni decision exacta de ejecucion.",
            "- La calidad y el motivo de bloqueo forman parte de la traza.",
            "",
            "## 6. Reconstruccion historica",
            "",
            "La API no equivale a un archivo historico propio:",
            "",
            "- `aggTrades` USD-M: solo las ultimas 24 horas;",
            "- historial de OI: aproximadamente un mes;",
            "- volumen taker: 30 dias;",
            "- profundidad, book ticker, precio y configuraciones: estado actual;",
            "- velas y funding permiten consulta historica, pero Binance no",
            "  compromete en estas fichas una retencion ilimitada.",
            "",
            "Para reproducir exactamente un analisis futuro, M5 debera almacenar",
            "el payload bruto, sus timestamps, parametros, version y hash al",
            "momento del analisis. No se declarara reconstruible lo que no lo sea.",
            "",
            "## 7. Matriz P0",
            "",
            f"La matriz contiene **{matrix['summary']['rows']} filas**:",
            f"{matrix['summary']['p0_blocks']} bloques x",
            f"{matrix['summary']['symbols']} pares x",
            f"{matrix['summary']['horizons']} marcos.",
            "",
            "M3 vincula datos con bloques. Los identificadores de reglas exactas",
            "siguen como `not_defined_until_M4`; inventarlos en esta fase violaria",
            "la hoja de ruta. Actualmente hay "
            f"**{matrix['summary']['current_ready_rows']}** filas listas para una",
            "revision rigurosa porque las rutas actuales no cumplen aun los",
            "contratos temporales y de ausencia.",
            "",
            "## 8. Fallos del pipeline actual",
            "",
            f"Se reproducen **{audit['summary']['findings']} fallos**,",
            f"**{audit['summary']['critical']} criticos** y",
            f"**{audit['summary']['high']} altos**:",
            "",
            "| ID | Severidad | Hallazgo |",
            "|---|---|---|",
        ]
    )
    for item in audit["findings"]:
        lines.append(
            f"| `{item['id']}` | `{item['severity']}` | {item['reason']} |"
        )
    lines.extend(
        [
            "",
            "Los fallos no significan que Binance carezca de los datos. Significan",
            "que el snapshot actual no conserva pruebas suficientes sobre su",
            "tiempo, calidad, cobertura o ausencia para un motor riguroso.",
            "",
            "## 9. Decisiones principales",
            "",
            "1. Binance oficial cubre gratuitamente el nucleo P0 de mercado.",
            "2. Los seis pares existen hoy en Futures y Spot.",
            "3. Spot-futuros es viable pero aun no esta implementado.",
            "4. La comision exacta requiere autenticacion o configuracion explicita.",
            "5. OI, taker y trades requieren captura local para superar su retencion.",
            "6. El snapshot productivo debe reconstruirse en M5; M3 no lo modifica.",
            "7. HyperPerps/liquidaciones permanecen P1 y fuera de esta fase.",
            "",
            "## 10. Fuentes oficiales",
            "",
        ]
    )
    for source in catalog["official_sources"]:
        lines.append(
            f"- {source['provider']} - {source['scope']}: {source['url']}"
        )
    lines.extend(
        [
            "",
            "## 11. Estado y siguiente fase",
            "",
            f"SHA-256 del catalogo: `{catalog['catalog_sha256']}`.",
            f"SHA-256 de la matriz: `{matrix['matrix_sha256']}`.",
            "",
            "M3 queda completada y aprobada expresamente por el propietario el",
            "2026-07-27. Produccion no ha cambiado. M4 no se ha iniciado; sera",
            "la definicion formal de reglas y combinaciones P0.",
            "",
        ]
    )
    return "\n".join(lines)


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            raise SystemExit(f"Generated artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    catalog = build_catalog()
    matrix = build_matrix(catalog)
    audit = build_current_audit()
    report = render_report(catalog, matrix, audit)

    write_or_check(
        args.catalog,
        json.dumps(catalog, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(
        args.matrix,
        json.dumps(matrix, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(
        args.audit,
        json.dumps(audit, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, report, args.check)


if __name__ == "__main__":
    main()
