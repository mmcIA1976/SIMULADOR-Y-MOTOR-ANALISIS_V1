from __future__ import annotations

import hashlib
import json
import math


RUNTIME_VERSION = "liquidation-rule-runtime-v0.1"
RULE_ID = "LIB-CAND-LIQUIDATION-ZONE-001"


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _finite_positive(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name}_must_be_finite_and_positive")
    return number


def _finite_non_negative(value, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name}_must_be_finite_and_non_negative")
    return number


def _trace(
    *,
    inputs: dict,
    outputs: dict,
    status: str,
    reason_codes: list[str],
    source_payload: object,
    executed_at: str,
) -> dict:
    trace = {
        "runtime_version": RUNTIME_VERSION,
        "rule_id": RULE_ID,
        "rule_version": "0.1",
        "family_id": "FAMILY-LIQUIDATION-OBSERVATION",
        "role": "contextual",
        "parent_rule_ids": [],
        "status": status,
        "reason_codes": reason_codes,
        "formula_ids": [
            f"{RULE_ID}-FORMULA-01",
            f"{RULE_ID}-FORMULA-02",
            f"{RULE_ID}-FORMULA-03",
            f"{RULE_ID}-FORMULA-04",
        ],
        "inputs": inputs,
        "outputs": outputs,
        "source_data_sha256": canonical_sha256(source_payload),
        "executed_at": executed_at,
        "probability_effect": "none_shadow_observation",
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def _normalized_clusters(
    raw_clusters: object,
    *,
    expected_side: str,
    entry: float,
    sigma_horizon: float,
    barrier: float,
) -> list[dict]:
    if not isinstance(raw_clusters, list):
        raise ValueError("clusters_must_be_a_list")
    clusters = []
    for index, raw in enumerate(raw_clusters):
        if not isinstance(raw, dict):
            raise ValueError("cluster_must_be_an_object")
        if str(raw.get("position_side")) != expected_side:
            raise ValueError("cluster_position_side_mismatch")
        price = _finite_positive(raw.get("price"), f"cluster_price_{index}")
        notional = _finite_non_negative(
            raw.get("notional_usd"),
            f"cluster_notional_{index}",
        )
        wallets = raw.get("wallet_count")
        if wallets is not None:
            wallets = int(wallets)
            if wallets < 0:
                raise ValueError("wallet_count_must_be_non_negative")
        clusters.append(
            {
                "position_side": expected_side,
                "price": price,
                "notional_usd": notional,
                "wallet_count": wallets,
                "distance_from_entry_log_sigma": (
                    math.log(price / entry) / sigma_horizon
                ),
                "distance_to_barrier_abs_log_sigma": (
                    abs(math.log(price / barrier)) / sigma_horizon
                ),
            }
        )
    return clusters


def _between(value: float, first: float, second: float) -> bool:
    return min(first, second) <= value <= max(first, second)


def _cascade_for_side(context: dict, side: str) -> dict:
    raw = (context.get("cascade_mass") or {}).get(side) or {}
    result = {}
    for band in ("within_1pct", "within_2pct", "within_5pct"):
        value = raw.get(band)
        result[band] = (
            _finite_non_negative(value, f"{side}_{band}")
            if value is not None
            else None
        )
    return result


def evaluate_liquidation_zone(
    live_context: dict | None,
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    sigma_horizon: float,
    analysis_at: str,
) -> dict:
    context = (live_context or {}).get("liquidation_context") or {}
    normalized_side = str(side).lower()
    inputs = {
        "provider": context.get("provider"),
        "scope": context.get("scope"),
        "provider_schema": context.get("schema"),
        "provider_status": context.get("status"),
        "provider_reason": context.get("reason"),
        "supported_provider_symbols": ["BTC", "ETH", "SOL"],
        "cluster_policy": (
            "up_to_10_provider_clusters_per_position_side_"
            "ordered_by_notional"
        ),
        "side": normalized_side,
        "entry": entry,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "sigma_horizon": sigma_horizon,
    }
    if not context:
        return _trace(
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=["missing_liquidation_context"],
            source_payload={},
            executed_at=analysis_at,
        )
    if not context.get("available"):
        return _trace(
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[
                str(
                    context.get("reason")
                    or context.get("status")
                    or "liquidation_context_unavailable"
                )
            ],
            source_payload=context,
            executed_at=analysis_at,
        )
    try:
        entry = _finite_positive(entry, "entry")
        take_profit = _finite_positive(take_profit, "take_profit")
        stop_loss = _finite_positive(stop_loss, "stop_loss")
        sigma_horizon = _finite_positive(
            sigma_horizon,
            "sigma_horizon",
        )
        if normalized_side == "long":
            if not stop_loss < entry < take_profit:
                raise ValueError("invalid_long_barrier_geometry")
            target_position_side = "short"
            adverse_position_side = "long"
            target_raw = context.get("clusters_above", [])
            adverse_raw = context.get("clusters_below", [])
        elif normalized_side == "short":
            if not take_profit < entry < stop_loss:
                raise ValueError("invalid_short_barrier_geometry")
            target_position_side = "long"
            adverse_position_side = "short"
            target_raw = context.get("clusters_below", [])
            adverse_raw = context.get("clusters_above", [])
        else:
            raise ValueError("side_must_be_long_or_short")
        target_clusters = _normalized_clusters(
            target_raw,
            expected_side=target_position_side,
            entry=entry,
            sigma_horizon=sigma_horizon,
            barrier=take_profit,
        )
        adverse_clusters = _normalized_clusters(
            adverse_raw,
            expected_side=adverse_position_side,
            entry=entry,
            sigma_horizon=sigma_horizon,
            barrier=stop_loss,
        )
        target_cascade = _cascade_for_side(
            context,
            target_position_side,
        )
        adverse_cascade = _cascade_for_side(
            context,
            adverse_position_side,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        return _trace(
            inputs=inputs,
            outputs={},
            status="blocked",
            reason_codes=[str(exc) or "invalid_liquidation_payload"],
            source_payload=context,
            executed_at=analysis_at,
        )

    target_path = [
        cluster
        for cluster in target_clusters
        if _between(cluster["price"], entry, take_profit)
    ]
    adverse_path = [
        cluster
        for cluster in adverse_clusters
        if _between(cluster["price"], entry, stop_loss)
    ]
    target_mass = math.fsum(
        cluster["notional_usd"] for cluster in target_path
    )
    adverse_mass = math.fsum(
        cluster["notional_usd"] for cluster in adverse_path
    )
    path_mass = target_mass + adverse_mass
    target_fraction = (
        target_mass / path_mass if path_mass > 0 else None
    )

    def nearest(clusters: list[dict]) -> dict | None:
        return (
            min(
                clusters,
                key=lambda cluster: (
                    cluster["distance_to_barrier_abs_log_sigma"]
                ),
            )
            if clusters
            else None
        )

    outputs = {
        "provider": context.get("provider"),
        "scope": context.get("scope"),
        "schema": context.get("schema"),
        "as_of": context.get("as_of"),
        "age_seconds": context.get("age_seconds"),
        "reference_price": context.get("reference_price"),
        "market_price": context.get("market_price"),
        "reference_basis_pct": context.get("reference_basis_pct"),
        "sample_size": context.get("sample_size"),
        "target_position_side": target_position_side,
        "adverse_position_side": adverse_position_side,
        "target_visible_cluster_count": len(target_clusters),
        "adverse_visible_cluster_count": len(adverse_clusters),
        "target_path_cluster_count": len(target_path),
        "adverse_path_cluster_count": len(adverse_path),
        "target_path_visible_notional_usd": target_mass,
        "adverse_path_visible_notional_usd": adverse_mass,
        "target_visible_path_mass_fraction": target_fraction,
        "target_path_clusters": target_path,
        "adverse_path_clusters": adverse_path,
        "nearest_target_path_cluster_to_tp": nearest(target_path),
        "nearest_adverse_path_cluster_to_sl": nearest(adverse_path),
        "target_cascade_mass": target_cascade,
        "adverse_cascade_mass": adverse_cascade,
        "raw_short_to_long_mass_ratio_2pct": context.get(
            "short_to_long_mass_ratio_2pct"
        ),
        "net_oi_skew": context.get("net_oi_skew"),
        "crowd_leverage": context.get("crowd_leverage"),
    }
    return _trace(
        inputs=inputs,
        outputs=outputs,
        status="evaluated_shadow",
        reason_codes=[],
        source_payload=context,
        executed_at=analysis_at,
    )


def evaluate_liquidation_rule_family(
    live_context: dict | None,
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    sigma_horizon: float,
    analysis_at: str,
) -> dict:
    trace = evaluate_liquidation_zone(
        live_context,
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
        sigma_horizon=sigma_horizon,
        analysis_at=analysis_at,
    )
    payload = {
        "runtime_version": RUNTIME_VERSION,
        "status": (
            "evaluated_shadow"
            if trace["status"] == "evaluated_shadow"
            else "blocked"
        ),
        "evaluated_rule_count": int(
            trace["status"] == "evaluated_shadow"
        ),
        "traces": [trace],
    }
    payload["runtime_trace_sha256"] = canonical_sha256(payload)
    return payload
