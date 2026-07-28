from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
M3_CONTRACT_PATH = (
    ROOT / "auditorias_motor" / "catalogo_contratos_datos_m3_v0_1.json"
)
GATE_VERSION = "M7-pretrade-data-gate-v0.1"


@dataclass(frozen=True)
class DataGateResult:
    status: str
    reason_codes: tuple[str, ...]
    checked_contract_ids: tuple[str, ...]
    analysis_at_ms: int | None
    symbol: str | None
    production_effect: str = "none"
    gate_version: str = GATE_VERSION

    def to_dict(self) -> dict:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["checked_contract_ids"] = list(self.checked_contract_ids)
        return value


@lru_cache(maxsize=1)
def contract_registry() -> dict[str, dict]:
    catalog = json.loads(M3_CONTRACT_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item for item in catalog["contracts"]}


def _timestamp(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0 or int(number) != number:
        return None
    return int(number)


def _positive_int(value: Any) -> int | None:
    return _timestamp(value)


def validate_pretrade_snapshot(
    *,
    analysis_at_ms: Any,
    symbol: Any,
    required_contract_ids: tuple[str, ...] | list[str],
    observations: tuple[dict, ...] | list[dict],
) -> DataGateResult:
    registry = contract_registry()
    reasons: list[str] = []
    analysis_at = _timestamp(analysis_at_ms)
    normalized_symbol = str(symbol or "").upper()
    required = tuple(str(item) for item in required_contract_ids)

    if analysis_at is None:
        reasons.append("invalid_analysis_at")
    if not normalized_symbol:
        reasons.append("invalid_symbol")
    if not required:
        reasons.append("required_contracts_empty")
    if len(set(required)) != len(required):
        reasons.append("duplicate_required_contract_id")
    unsupported_required = sorted(set(required) - set(registry))
    if unsupported_required:
        reasons.append("unsupported_required_contract_id")
    if not isinstance(observations, (list, tuple)):
        reasons.append("observations_must_be_sequence")
        observations = ()

    observed: dict[str, dict] = {}
    duplicate_observations = False
    for item in observations:
        if not isinstance(item, dict):
            reasons.append("observation_must_be_object")
            continue
        contract_id = str(item.get("contract_id") or "")
        if not contract_id:
            reasons.append("observation_contract_id_missing")
            continue
        if contract_id in observed:
            duplicate_observations = True
        observed[contract_id] = item
    if duplicate_observations:
        reasons.append("duplicate_observation_contract_id")

    missing = sorted(set(required) - set(observed))
    if missing:
        reasons.append("mandatory_observation_missing")

    request_times: list[int] = []
    receive_times: list[int] = []
    for contract_id in required:
        item = observed.get(contract_id)
        contract = registry.get(contract_id)
        if item is None or contract is None:
            continue
        prefix = contract_id.lower().replace("-", "_")
        if item.get("payload_status") != "complete" or item.get("partial") is True:
            reasons.append(f"{prefix}_partial_or_incomplete")
        contradictions = item.get("contradictions", [])
        if not isinstance(contradictions, (list, tuple)) or contradictions:
            reasons.append(f"{prefix}_contradictory")
        if str(item.get("symbol") or "").upper() != normalized_symbol:
            reasons.append(f"{prefix}_symbol_mismatch")
        if normalized_symbol not in contract.get("supported_symbols", []):
            reasons.append(f"{prefix}_symbol_not_supported")

        requested = _timestamp(item.get("requested_at_ms"))
        received = _timestamp(item.get("received_at_ms"))
        if requested is None:
            reasons.append(f"{prefix}_requested_at_invalid")
        if received is None:
            reasons.append(f"{prefix}_received_at_invalid")
        if requested is None or received is None or analysis_at is None:
            continue
        request_times.append(requested)
        receive_times.append(received)
        if requested > received:
            reasons.append(f"{prefix}_request_after_receive")
        if received > analysis_at:
            reasons.append(f"{prefix}_received_after_analysis")

        time_contract = contract["time_contract"]
        latency_limit = time_contract.get("request_max_latency_ms")
        freshness = time_contract.get("freshness", {})
        if latency_limit is None:
            latency_limit = freshness.get("max_request_latency_ms")
        if latency_limit is not None and received - requested > latency_limit:
            reasons.append(f"{prefix}_request_latency_exceeded")

        provider_times_value = item.get("provider_timestamps_ms")
        if not isinstance(provider_times_value, (list, tuple)):
            reasons.append(f"{prefix}_provider_timestamps_invalid")
            provider_times: list[int] = []
        else:
            provider_times = []
            for value in provider_times_value:
                timestamp = _timestamp(value)
                if timestamp is None:
                    reasons.append(f"{prefix}_provider_timestamp_invalid")
                else:
                    provider_times.append(timestamp)
        freshness_kind = freshness.get("kind")
        if not provider_times and freshness_kind != "receive_time_only":
            reasons.append(f"{prefix}_provider_timestamp_missing")
        if any(value > received for value in provider_times):
            reasons.append(f"{prefix}_provider_after_receive")
        if any(value > analysis_at for value in provider_times):
            reasons.append(f"{prefix}_future_provider_data")

        reference_time = max(provider_times, default=received)
        max_age = freshness.get("max_age_ms")
        if max_age is not None and analysis_at - reference_time > max_age:
            reasons.append(f"{prefix}_stale")

        if freshness_kind in {"closed_period", "completed_period"}:
            period = _positive_int(item.get("period_ms"))
            latest_end = _timestamp(item.get("latest_period_end_ms"))
            grace = int(freshness.get("release_grace_ms", 0))
            if period is None or latest_end is None:
                reasons.append(f"{prefix}_period_contract_incomplete")
            elif latest_end > analysis_at:
                reasons.append(f"{prefix}_open_or_future_period")
            elif analysis_at - latest_end > period + grace:
                reasons.append(f"{prefix}_completed_period_stale")

        if freshness_kind == "explicit_event_window":
            start = _timestamp(item.get("window_start_ms"))
            end = _timestamp(item.get("window_end_ms"))
            last_event = _timestamp(item.get("last_event_time_ms"))
            max_last_age = freshness.get("max_last_event_age_ms")
            if (
                start is None
                or end is None
                or last_event is None
                or end <= start
                or item.get("coverage_complete") is not True
            ):
                reasons.append(f"{prefix}_event_window_incomplete")
            else:
                if end > analysis_at or last_event > analysis_at:
                    reasons.append(f"{prefix}_future_event_window")
                if (
                    max_last_age is not None
                    and analysis_at - last_event > max_last_age
                ):
                    reasons.append(f"{prefix}_event_window_stale")

        if freshness_kind == "scheduled_event_history":
            latest_event = _timestamp(item.get("latest_event_time_ms"))
            if latest_event is None or item.get("schedule_compatible") is not True:
                reasons.append(f"{prefix}_schedule_contract_invalid")
            elif latest_event > analysis_at:
                reasons.append(f"{prefix}_future_scheduled_event")

        if contract_id == "M3-DATA-002":
            if (
                item.get("trading_status") != "TRADING"
                or item.get("contract_type") != "PERPETUAL"
                or item.get("quote_asset") != "USDT"
            ):
                reasons.append(f"{prefix}_market_identity_invalid")

    if request_times and receive_times:
        snapshot_limit = min(
            registry[item]["time_contract"].get(
                "snapshot_max_span_ms",
                15_000,
            )
            for item in required
            if item in registry
        )
        capture_span = max(receive_times) - min(request_times)
        if capture_span > snapshot_limit:
            reasons.append("snapshot_capture_span_exceeded")

    unique_reasons = tuple(dict.fromkeys(reasons))
    return DataGateResult(
        status="accepted" if not unique_reasons else "blocked",
        reason_codes=unique_reasons,
        checked_contract_ids=required,
        analysis_at_ms=analysis_at,
        symbol=normalized_symbol or None,
    )
