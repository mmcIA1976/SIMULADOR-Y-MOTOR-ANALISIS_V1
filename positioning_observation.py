"""Bounded, on-demand positioning measurements; never probability inputs.

OI uses base-contract quantity, exact endpoint pairs and a one-period safety
lag. This lag is a conservative policy, not proof of vendor publication time.
Funding is SETTLED funding, deliberately not the premium-index quote formula.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime

import market_data

CONTRACT_VERSION = "positioning-measurement-v1"
OI_RULE = "M4-RULE-OPEN-INTEREST-CHANGE-001"
PRICE_OI_RULE = "M4-RULE-PRICE-OI-STATE-001"
FUNDING_RULE = "M4-RULE-FUNDING-STATE-001"
_cache: OrderedDict = OrderedDict()
_lock = threading.Lock()


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cached(key, fetch, *, ttl=600):
    # Serializes only optional positioning loads, not the worker's price path.
    with _lock:
        now = time.monotonic()
        cached = _cache.get(key)
        if cached and cached[0] > now:
            _cache.move_to_end(key)
            return cached[1], cached[2], True
        try:
            rows = fetch()
            rows = rows if isinstance(rows, list) else []
        except Exception:
            rows = []
        observed_ms = int(time.time() * 1000)
        _cache[key] = (now + (ttl if rows else 60), rows, observed_ms)
        _cache.move_to_end(key)
        while len(_cache) > 64:
            _cache.popitem(last=False)
        return rows, observed_ms, False


def collect_positioning_observation(symbol: str, contexts: dict, analysis_at: str) -> dict:
    """At most one OI request/stage and one funding request, using shared budget."""
    cutoff = int(datetime.fromisoformat(analysis_at.replace("Z", "+00:00")).timestamp() * 1000)
    if cutoff > int(time.time()*1000)+5000 or cutoff < int(time.time()*1000)-3600000:
        # A live collector must not silently reconstruct past availability.
        return {"stages": {}, "reason": "historical_or_future_cutoff_requires_archived_provider"}
    stages = {}
    for stage, context in contexts.items():
        pair = context.get("positioning_price_pair") or {}
        end = int(pair.get("end_ms") or 0)
        start = int(pair.get("start_ms") or 0)
        interval = int(context.get("interval_seconds") or 0) * 1000
        if not end or not interval or end > cutoff - interval:
            stages[stage] = {"oi_rows": [], "reason": "causal_price_pair_missing"}
            continue
        period = str(context["interval"])
        rows, observed, cached = _cached(
            (symbol, period, end),
            lambda: market_data.get_open_interest_history(
                symbol, period=period, limit=min(500, (end-start)//interval + 3),
                start_time_ms=start, end_time_ms=end),
            ttl=max(600,2*interval//1000),
        )
        stages[stage] = {"oi_rows": rows, "observed_at_ms": observed, "cache_hit": cached}
    funding, observed, cached = _cached(
        (symbol, "settled_funding", cutoff // 600000),
        lambda: market_data.get_funding_history(symbol, limit=3, end_time_ms=cutoff),
    )
    return {"stages": stages, "funding_rows": funding,
            "funding_observed_at_ms": observed, "funding_cache_hit": cached}


def _trace(rule, version, outputs, reason=None):
    trace = {"rule_id": rule, "rule_version": version,
             "measurement_contract_version": CONTRACT_VERSION,
             "status": "blocked" if reason else "evaluated_shadow",
             "probability_effect": "none_observation_only",
             "active_probability_outputs": [],
             "observational_outputs": sorted(outputs),
             "reason_codes": [reason] if reason else [], "outputs": outputs}
    trace["trace_sha256"] = hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()
    market_inputs = {key: value for key, value in outputs.items()
                     if key not in {"observed_at_ms", "age_seconds"}}
    trace["source_data_sha256"] = hashlib.sha256(
        json.dumps([version,market_inputs], sort_keys=True).encode()).hexdigest()
    return trace


def evaluate_positioning_stage(context: dict, payload: dict, *, stage: str, cutoff_ms: int) -> list[dict]:
    pair = context.get("positioning_price_pair") or {}
    end, start = pair.get("end_ms"), pair.get("start_ms")
    horizon = int(context.get("horizon_seconds") or 0) * 1000
    interval = int(context.get("interval_seconds") or 0) * 1000
    provider = (payload.get("stages") or {}).get(stage) or {}
    outputs = {"source": "binance_open_interest_hist_base_quantity",
               "period": context.get("interval"), "horizon_seconds": horizon//1000,
               "observed_at_ms": provider.get("observed_at_ms"),
               "publication_policy": "one_period_safety_lag_not_verified_release_time"}
    reason = None
    if not end or not start or end-start != horizon or not interval or end > cutoff_ms-interval:
        reason = "causal_price_pair_missing"
    else:
        points = {}
        conflict = False
        for row in provider.get("oi_rows") or []:
            if not isinstance(row, dict):
                continue
            timestamp, amount = _number(row.get("timestamp")), _number(row.get("sumOpenInterest"))
            if timestamp is None or amount is None or amount <= 0 or timestamp > end:
                continue
            if timestamp != int(timestamp):
                continue
            timestamp = int(timestamp)
            if timestamp not in (start, end):
                continue
            if timestamp in points and points[timestamp] != amount:
                conflict = True
            points[timestamp] = amount
        if conflict:
            reason = "conflicting_oi_endpoint"
        elif start not in points or end not in points:
            reason = "exact_oi_endpoints_unavailable"
        else:
            outputs.update({"oi_previous": points[start], "oi_current": points[end],
                            "start_ms": start, "end_ms": end,
                            "age_seconds": (cutoff_ms-end)/1000,
                            "dOI_H": math.log(points[end]/points[start])})
    oi = _trace(OI_RULE, "base-oi-exact-lagged-v1", outputs, reason)
    price_outputs = {"source": "aligned_closed_price_and_base_oi",
                     "horizon_seconds": horizon//1000}
    previous, current = _number(pair.get("price_previous")), _number(pair.get("price_current"))
    if reason is None and previous is not None and current is not None and min(previous,current) > 0:
        displacement = math.log(current/previous)
        change = outputs["dOI_H"]
        price_outputs.update({"D_H": displacement, "dOI_H": change,
                              "price_previous": previous, "price_current": current,
                              "start_ms": start, "end_ms": end,
                              "price_sign": (displacement > 0)-(displacement < 0),
                              "oi_sign": (change > 0)-(change < 0)})
        price_reason = None
    else:
        price_reason = reason or "aligned_price_missing"
    price_oi = _trace(PRICE_OI_RULE, "price-base-oi-exact-lagged-v1", price_outputs, price_reason)
    funding_points = {}
    funding_conflict = False
    for row in payload.get("funding_rows") or []:
        if not isinstance(row, dict):
            continue
        stamp, rate = _number(row.get("fundingTime")), _number(row.get("fundingRate"))
        if stamp is not None and stamp == int(stamp) and rate is not None and stamp <= cutoff_ms:
            if int(stamp) in funding_points and funding_points[int(stamp)] != rate:
                funding_conflict = True
            funding_points[int(stamp)] = rate
    funding_outputs = {"source": "binance_settled_funding_history",
                       "observed_at_ms": payload.get("funding_observed_at_ms")}
    funding_reason = "settled_funding_unavailable"
    if funding_conflict:
        funding_reason = "conflicting_funding_event"
    elif funding_points:
        latest = max(funding_points)
        if cutoff_ms-latest > 86400000:
            funding_reason = "settled_funding_stale"
        else:
            funding_outputs.update({"last_settled_funding_rate": funding_points[latest],
                                    "funding_time_ms": latest, "age_seconds": (cutoff_ms-latest)/1000})
            prior = sorted(funding_points)[-2:-1]
            if prior:
                hours = (latest-prior[0])/3600000
                funding_outputs["observed_interval_hours"] = hours
                if 0.5 <= hours <= 24:
                    funding_outputs["settled_funding_rate_per_hour"] = funding_points[latest]/hours
                    funding_outputs["normalization_source"] = "previous_payment_gap_not_forward_schedule"
            funding_reason = None
    return [oi, price_oi, _trace(FUNDING_RULE, "settled-funding-v1", funding_outputs, funding_reason)]


def attach_positioning_observation(run: dict, proposal, *, observation_loader, analysis_at: str) -> dict:
    contexts = run.get("stage_contexts") or {}
    cutoff = int(datetime.fromisoformat(analysis_at.replace("Z", "+00:00")).timestamp()*1000)
    try:
        payload = observation_loader(str(proposal.symbol).upper(), contexts, analysis_at) if observation_loader else {}
        payload = payload if isinstance(payload, dict) else {}
        provider_reason = payload.get("reason") if observation_loader else "not_configured"
    except Exception as exc:
        payload = {}
        provider_reason = "provider_failed:" + type(exc).__name__
    statuses = {}
    for stage, context in contexts.items():
        traces = run.setdefault("stage_rule_traces", {}).setdefault(stage, [])
        traces[:] = [t for t in traces if t.get("rule_id") not in (OI_RULE, PRICE_OI_RULE, FUNDING_RULE)]
        new = evaluate_positioning_stage(context, payload, stage=stage, cutoff_ms=cutoff)
        traces.extend(new)
        statuses[stage] = {t["rule_id"]: {"status": t["status"], "reason_codes": t["reason_codes"]} for t in new}
    return {"contract_version": CONTRACT_VERSION, "stage_statuses": statuses,
            "provider_reason": provider_reason, "probability_effect": "none_observation_only",
            "stored_payload": "scalar_endpoints_only_no_history"}
