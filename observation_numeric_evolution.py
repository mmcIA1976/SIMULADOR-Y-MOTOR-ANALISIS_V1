"""Chronological, probability-neutral learning from existing observation facts.

No market calls, order actions or parameter fitting. Outcomes use the *sampled*
price path, not intrabar extrema. Missing futures are censored, never replaced
with the eventual trade outcome. The stored result contains sufficient summaries,
not another copy of the checkpoint series.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import lzma
from collections import Counter, defaultdict
from datetime import datetime, timezone

from observation_snapshot_codec import snapshot_rule_traces

VERSION = "observation-numeric-evolution-v1"
MAX_PAYLOAD_BYTES = 65_536
MAX_EXPANDED_BYTES = 4_000_000
MAX_CHECKPOINTS = 2_000
MAX_SERIES = 2_000
WINDOWS_MINUTES = {
    "intraday_short": (20, 60, 240),
    "intraday_wide": (60, 240, 1440),
    "short_swing": (240, 1440, 10080),
}
VALID_STATUSES = {"evaluated", "evaluated_shadow", "partially_evaluated_shadow"}
# Predeclared combinations, not combinations selected for a profitable outcome.
PAIR_RULES = (
    ("LIB-CAND-EMA-TREND-001", "LIB-CAND-CVD-SLOPE-001"),
    ("LIB-CAND-EMA-TREND-001", "LIB-CAND-ATR-EXTENSION-001"),
    ("LIB-CAND-EMA-TREND-001", "LIB-CAND-RSI-WILDER-001"),
    ("LIB-CAND-CVD-SLOPE-001", "LIB-CAND-ORDERBOOK-IMBALANCE-001"),
)
PAIR_METRICS = {
    "LIB-CAND-EMA-TREND-001": "side_adjusted_slope_atr",
    "LIB-CAND-CVD-SLOPE-001": "side_adjusted_normalized_cvd_slope",
    "LIB-CAND-ATR-EXTENSION-001": "side_adjusted_extension_atr",
    "LIB-CAND-RSI-WILDER-001": "side_adjusted_centered_rsi",
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": "persistence.top_20.side_adjusted_mean",
}
# Stable, predeclared market descriptors. All named scalar outputs retain their
# evolution; forecast comparisons use normalized signals, not raw notionals,
# sample counters, configured thresholds or duplicated transformed values.
FORECAST_METRICS = {
    "LIB-CAND-EMA-TREND-001": {"side_adjusted_slope_atr", "side_adjusted_close_vs_ema50_log", "side_adjusted_ema50_vs_ema200_log"},
    "LIB-CAND-CVD-SLOPE-001": {"side_adjusted_normalized_cvd_slope", "side_adjusted_terminal_imbalance"},
    "LIB-CAND-RSI-WILDER-001": {"side_adjusted_centered_rsi"},
    "LIB-CAND-ATR-EXTENSION-001": {"side_adjusted_extension_atr", "atr14_fraction_price"},
    "LIB-CAND-ABSORPTION-001": {"absorption_vector.aggressor_imbalance", "absorption_vector.displacement_atr", "absorption_vector.flow_opposing_wick_ratio", "absorption_vector.relative_volume"},
    "LIB-CAND-COMPRESSION-001": {"compression_vector.atr_rank", "compression_vector.bollinger_width_rank"},
    "LIB-CAND-FIBONACCI-DISTANCE-001": {"nearest_to_stop_loss.absolute_distance_sigma_horizon", "nearest_to_take_profit.absolute_distance_sigma_horizon"},
    "LIB-CAND-LIQUIDATION-ZONE-001": {"target_cascade_mass.within_2pct", "adverse_cascade_mass.within_2pct", "target_visible_path_mass_fraction", "raw_short_to_long_mass_ratio_2pct", "net_oi_skew"},
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": {"persistence.top_20.side_adjusted_mean", "persistence.top_20.side_adjusted_slope_per_minute", "persistence.top_20.sign_flip_count", "executed_flow.side_adjusted_executed_flow_imbalance", "absorption.favorable_absorption_score", "absorption.adverse_absorption_score", "change_activity.unmatched_removal_fraction", "change_activity.mean_modification_fraction_per_second"},
    "LIB-CAND-RELATIVE-VOLUME-001": {"relative_horizon_volume", "volume_midrank_60"},
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": {"adverse_path_level_count", "target_path_level_count"},
    "M4-RULE-AGGRESSOR-IMBALANCE-001": {"ATI_H"},
    "M4-RULE-MTF-HIERARCHY-001": {"directional_path_efficiency_2h", "directional_path_efficiency_4h"},
    "M4-RULE-PATH-STRUCTURE-001": {"directional_path_efficiency_h"},
    "M4-RULE-PRIOR-EXTREMA-001": {"target_extreme_between_entry_and_tp"},
    "M4-RULE-VOLATILITY-RANK-001": {"volatility_percentile_60"},
    "M4-RULE-OPEN-INTEREST-CHANGE-001": {"dOI_H"},
    "M4-RULE-PRICE-OI-STATE-001": {"D_H", "dOI_H"},
    "M4-RULE-FUNDING-STATE-001": {"settled_funding_rate_per_hour"},
}
MEASUREMENT_METADATA = {"observed_at_ms", "age_seconds", "start_ms", "end_ms",
                        "funding_time_ms", "horizon_seconds"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def timestamp(value):
    if not value:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def obj(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def scalars(value, prefix=""):
    """Array members are observations/walls, not stable named formula outputs."""
    result = {}
    if isinstance(value, dict):
        for name, item in value.items():
            result.update(scalars(item, f"{prefix}.{name}" if prefix else str(name)))
    elif finite(value) is not None:
        result[prefix] = float(value)
    return result


def sign(value):
    return 1 if value > 1e-12 else -1 if value < -1e-12 else 0


def slope(points):
    if len(points) < 2:
        return None
    times = [(p["time"] - points[0]["time"]) / 3600 for p in points]
    values = [p["value"] for p in points]
    mt, mv = sum(times) / len(times), sum(values) / len(values)
    denominator = math.fsum((t - mt) ** 2 for t in times)
    return math.fsum((t-mt)*(v-mv) for t, v in zip(times, values)) / denominator if denominator else None


def state(points):
    """Past-only descriptors; strength bins are descriptive, not trading gates."""
    last = points[-1]
    delta = last["value"] - points[-2]["value"] if len(points) > 1 else None
    recent = points[-3:]
    rate = slope(recent)
    earlier = [p["value"] for p in points[-13:-1]]
    z = None
    if len(earlier) >= 3:
        mean = math.fsum(earlier) / len(earlier)
        sd = math.sqrt(math.fsum((v-mean)**2 for v in earlier) / len(earlier))
        if sd > 1e-12:
            z = (last["value"] - mean) / sd
    strength = "unknown" if z is None else "low" if z < -1 else "high" if z > 1 else "middle"
    direction = "warming" if rate is None else "rising" if sign(rate) > 0 else "falling" if sign(rate) < 0 else "flat"
    directions = [sign(p["value"]) for p in recent]
    sustained = len(recent) == 3 and len(set(directions)) == 1
    rates = [(b["value"]-a["value"]) / ((b["time"]-a["time"])/3600) for a, b in zip(recent, recent[1:]) if b["time"] > a["time"]]
    acceleration = None
    if len(rates) == 2:
        acceleration = (rates[-1]-rates[-2]) / ((recent[-1]["time"]-recent[0]["time"])/7200)
    return {
        "delta": delta, "slope_per_hour": rate, "acceleration_per_hour2": acceleration,
        "direction": direction, "past_only_level_z": z, "relative_strength": strength,
        "three_distinct_readings_same_sign": sustained,
        "three_reading_mean": math.fsum(p["value"] for p in recent)/len(recent),
        "three_reading_min": min(p["value"] for p in recent),
        "three_reading_max": max(p["value"] for p in recent),
        "pattern": f"{sign(last['value'])}:{direction}:{strength}",
    }


def future_path(rows, index, minutes, max_gap_seconds):
    """Observed endpoint with bounded scheduling drift, no interpolation."""
    start = rows[index]
    target = start["time"] + minutes*60
    later = rows[index+1:]
    end = next((p for p in later if p["time"] >= target), None)
    if end is None:
        return None, "right_censored"
    if end["time"]-target > min(300, max(90, minutes*60*.02)):
        return None, "endpoint_not_observed"
    path = rows[index:end["index"]+1]
    if any(b["time"]-a["time"] > max_gap_seconds for a, b in zip(path, path[1:])):
        return None, "gap_in_sampled_path"
    returns = [start["side_sign"]*10000*(p["price"]/start["price"]-1) for p in path]
    return {"return_bps": returns[-1], "sampled_favorable_bps": max(returns),
            "sampled_adverse_bps": min(returns), "actual_minutes": (end["time"]-start["time"])/60}, None


def association(pairs):
    if len(pairs) < 3:
        return None
    xs, ys = zip(*pairs)
    mx, my = math.fsum(xs)/len(xs), math.fsum(ys)/len(ys)
    xx = math.fsum((v-mx)**2 for v in xs)
    yy = math.fsum((v-my)**2 for v in ys)
    return math.fsum((x-mx)*(y-my) for x,y in pairs)/math.sqrt(xx*yy) if xx*yy > 0 else None


def outcomes(samples):
    if not samples:
        return {"n": 0}
    return {"n": len(samples), "positive": sum(s["return_bps"] > 0 for s in samples),
            "_sample_ids": [s["_id"] for s in samples],
            "mean_return_bps": math.fsum(s["return_bps"] for s in samples)/len(samples),
            "mean_sampled_favorable_bps": math.fsum(s["sampled_favorable_bps"] for s in samples)/len(samples),
            "mean_sampled_adverse_bps": math.fsum(s["sampled_adverse_bps"] for s in samples)/len(samples),
            "actual_minutes_min": min(s["actual_minutes"] for s in samples),
            "actual_minutes_max": max(s["actual_minutes"] for s in samples)}


def build_evolution(operation, checkpoints, *, interval_minutes=20, include_points=False):
    if not checkpoints:
        raise ValueError("numeric_evolution_no_checkpoints")
    if operation.get("side") not in ("long", "short") or operation.get("time_horizon") not in WINDOWS_MINUTES:
        raise ValueError("numeric_evolution_invalid_operation_contract")
    if len(checkpoints) > MAX_CHECKPOINTS:
        raise ValueError("numeric_evolution_checkpoint_budget_exceeded")
    rows, series, availability = [], {}, defaultdict(Counter)
    side_sign = -1 if str(operation["side"]).lower() == "short" else 1
    if any(not c.get("observed_at") for c in checkpoints):
        raise ValueError("numeric_evolution_missing_time")
    ordered = sorted(checkpoints, key=lambda c: timestamp(c["observed_at"]))
    close_time = timestamp(operation.get("closed_at"))
    for checkpoint in ordered:
        t, price = timestamp(checkpoint["observed_at"]), finite(checkpoint.get("market_price"))
        if price is None or price <= 0 or (close_time and t > close_time):
            raise ValueError("numeric_evolution_invalid_checkpoint")
        if rows and t <= rows[-1]["time"]:
            raise ValueError("numeric_evolution_duplicate_time")
        index = len(rows)
        rows.append({"index": index, "time": t, "price": price, "side_sign": side_sign,
                     "code": checkpoint["checkpoint_code"]})
        snapshot = obj(checkpoint.get("snapshot_json"))
        traces_by_stage = snapshot_rule_traces(snapshot)
        if not traces_by_stage:
            raise ValueError("numeric_evolution_missing_rule_traces")
        for stage, traces in traces_by_stage.items():
            for trace in traces:
                rule = str(trace.get("rule_id") or "")
                availability[f"{stage}:{rule}"][str(trace.get("status") or "unknown")] += 1
                if trace.get("status") not in VALID_STATUSES:
                    continue
                contract_fields = {"catalog": snapshot.get("rule_catalog"), "rule": rule,
                                   "version": trace.get("rule_version"),
                                   "formula_ids": trace.get("formula_ids"),
                                   "runtime_version": trace.get("runtime_version")}
                if trace.get("measurement_contract_version"):
                    contract_fields["measurement_contract"] = trace["measurement_contract_version"]
                contract = digest(contract_fields)
                values = scalars(trace.get("outputs") or {})
                if trace.get("measurement_contract_version"):
                    values = {k:v for k,v in values.items() if k not in MEASUREMENT_METADATA}
                source = trace.get("source_data_sha256") or (snapshot.get("stage_contexts", {}).get(stage) or {}).get("source_data_sha256")
                # Values depending on the proposed entry may change on the same
                # candle: count numerical updates separately from source updates.
                evidence = digest({"source": source, "outputs": values})
                for metric, value in values.items():
                    active = trace.get("active_probability_outputs") or []
                    role = "active" if metric in active else "observational"
                    if not active and trace.get("probability_effect") == "analog_distance_input":
                        role = "active"
                    key = digest([stage, rule, metric, contract, role])
                    entry = series.setdefault(key, {"key": key, "stage": stage, "rule_id": rule,
                        "metric": metric, "formula_contract": contract, "role": role, "points": []})
                    entry["points"].append({"index": index, "time": t, "value": value,
                        "source": source, "evidence": evidence, "code": checkpoint["checkpoint_code"]})
        if len(series) > MAX_SERIES:
            raise ValueError("numeric_evolution_series_budget_exceeded")
    max_gap = max(90, int(interval_minutes)*60*1.5)
    future = {(i, m): future_path(rows, i, m, max_gap) for i in range(len(rows))
              for m in sorted({m for values in WINDOWS_MINUTES.values() for m in values})}
    response_catalog = []
    for response, reason in future.values():
        if reason is None:
            response["_id"] = len(response_catalog)
            response_catalog.append(response)
    state_index, results = {}, []
    for entry in series.values():
        points = entry.pop("points")
        distinct, previous = [], None
        resets = repeats = same_source = 0
        changes = []
        descriptions = []
        for p in points:
            gap = previous and (p["index"] != previous["index"]+1 or p["time"]-previous["time"] > max_gap)
            if gap:
                distinct = []
                resets += 1
            if previous and p["source"] and p["source"] == previous["source"]:
                same_source += 1
            if previous and not gap:
                changes.append(p["value"]-previous["value"])
            repeated = bool(previous and p["evidence"] == previous["evidence"])
            if repeated:
                repeats += 1
            if not repeated or not distinct:
                distinct.append(p)
            description = state(distinct)
            description["repeated_evidence"] = repeated
            description["new_source"] = bool(p["source"] and (not previous or p["source"] != previous["source"]))
            description["value"] = p["value"]
            description["code"] = p["code"]
            description["delta_since_previous_control"] = None if not previous or gap else p["value"]-previous["value"]
            descriptions.append((p, dict(description)))
            if entry["metric"] == PAIR_METRICS.get(entry["rule_id"]):
                state_index[(entry["stage"], entry["rule_id"], p["index"])] = (entry["key"], dict(description))
            previous = p
        evaluated = {}
        forecast_enabled = entry["metric"] in FORECAST_METRICS.get(entry["rule_id"], set())
        for minutes in WINDOWS_MINUTES.get(entry["stage"], ()) if forecast_enabled else ():
            excluded, samples, pairs, delta_pairs, patterns = Counter(), [], [], [], defaultdict(list)
            for p, description in descriptions:
                if description["repeated_evidence"]:
                    excluded["repeated_evidence"] += 1
                    continue
                response, reason = future[(p["index"], minutes)]
                if reason:
                    excluded[reason] += 1
                    continue
                samples.append(response)
                pairs.append((p["value"], response["return_bps"]))
                if description["delta"] is not None:
                    delta_pairs.append((description["delta"], response["return_bps"]))
                patterns[description["pattern"]].append(response)
            evaluated[str(minutes)] = {**outcomes(samples), "excluded": dict(excluded),
                "level_forward_correlation": association(pairs),
                "change_forward_correlation": association(delta_pairs),
                "patterns": {k: outcomes(v) for k,v in sorted(patterns.items())}}
        entry.update({"controls": len(points), "distinct_evidence": len(points)-repeats,
            "forecast_status": "evaluated" if forecast_enabled else "evolution_only_not_a_predeclared_forecast_variable",
            "same_source_controls": same_source, "continuity_resets": resets,
            "first": points[0]["value"], "last": points[-1]["value"],
            "minimum": min(p["value"] for p in points), "maximum": max(p["value"] for p in points),
            "increases": sum(sign(d)>0 for d in changes), "decreases": sum(sign(d)<0 for d in changes),
            "unchanged": sum(sign(d)==0 for d in changes), "latest": descriptions[-1][1], "forward": evaluated})
        if include_points:
            entry["points"] = [{**d, "observed_at": datetime.fromtimestamp(p["time"], timezone.utc).isoformat()} for p,d in descriptions]
        results.append(entry)
    joint = []
    for stage, windows in WINDOWS_MINUTES.items():
        for left, right in PAIR_RULES:
            grouped = defaultdict(list)
            previous = None
            for i in range(len(rows)):
                a, b = state_index.get((stage,left,i)), state_index.get((stage,right,i))
                if not a or not b:
                    previous = None
                    continue
                identity = (a[0], b[0], a[1]["value"], b[1]["value"])
                if identity == previous and a[1]["repeated_evidence"] and b[1]["repeated_evidence"]:
                    continue
                previous = identity
                for minutes in windows:
                    response, reason = future[(i, minutes)]
                    if not reason:
                        grouped[(a[0],b[0],minutes,a[1]["pattern"],b[1]["pattern"])].append(response)
            for (a,b,minutes,sa,sb), samples in sorted(grouped.items()):
                joint.append({"left":a,"right":b,"minutes":minutes,"left_state":sa,"right_state":sb,**outcomes(samples)})
    return {"version": VERSION, "operation_id": int(operation["id"]),
        "symbol": operation["symbol"], "side": operation["side"], "time_horizon": operation["time_horizon"],
        "started_at": operation.get("started_at"), "closed_at": operation.get("closed_at"),
        "checkpoint_count": len(rows), "series": sorted(results,key=lambda s:(s["stage"],s["rule_id"],s["metric"],s["key"])),
        "joint_patterns": joint, "response_catalog": response_catalog,
        "availability": {k:dict(v) for k,v in sorted(availability.items())},
        "semantics": {"production_effect":"none", "automatic_weight_change":False,
            "outcomes":"side_adjusted_sampled_price_returns_not_terminal_labels",
            "windows_minutes":{k:list(v) for k,v in WINDOWS_MINUTES.items()},
            "endpoint_tolerance":"2pct_of_horizon_bounded_90_to_300_seconds",
            "max_gap_seconds":max_gap, "extrema":"sampled_only_not_intrabar",
            "comparability":"same_pair_side_target_stage_formula_metric_role",
            "pattern":"numeric_sign:past_only_trend:past_only_z_bucket_not_a_trading_signal",
            "independent_episodes":1, "inference":"descriptive_not_validated_predictive_effect",
            "forecast_variables":{k:sorted(v) for k,v in FORECAST_METRICS.items()},
            "array_outputs":"not_individual_scalar_formulas", "missing_rule":"not_evaluated_not_neutral",
            "sign_semantics":"numeric_sign_is_not_favorable_adverse_interpretation",
            "source_semantics":"numeric_updates_and_new_market_sources_counted_separately"}}


def _storage_report(report):
    """Exact factoring: store each future response once, share group membership.

    No rounding, discarded variables or original candle/tick arrays. Means are
    reconstructed from exactly the same ordered members with the same formula.
    """
    import copy
    def visit(item):
        if isinstance(item, list):
            return [visit(v) for v in item]
        if not isinstance(item, dict):
            return item
        if "_sample_ids" in item:
            aggregate_keys = set(outcomes([report["response_catalog"][item["_sample_ids"][0]]]))
            return {"_members": item["_sample_ids"],
                    **{k:visit(v) for k,v in item.items() if k not in aggregate_keys}}
        return {k:visit(v) for k,v in item.items()}
    result = visit(copy.deepcopy(report))
    keys = {s.pop("key"): i for i,s in enumerate(result["series"])}
    for pair in result["joint_patterns"]:
        pair["left"], pair["right"] = keys[pair["left"]], keys[pair["right"]]
    return result


def _expand_report(report):
    catalog = report["response_catalog"]
    def visit(item):
        if isinstance(item, list):
            return [visit(v) for v in item]
        if not isinstance(item, dict):
            return item
        result = {k:visit(v) for k,v in item.items() if k != "_members"}
        if "_members" in item:
            ids = item["_members"]
            if not ids or len(ids) > MAX_CHECKPOINTS or any(type(i) is not int or not 0 <= i < len(catalog) for i in ids):
                raise ValueError("numeric_evolution_invalid_reference")
            result.update(outcomes([catalog[i] for i in ids]))
        return result
    result = visit(report)
    for s in result["series"]:
        s["key"] = digest([s["stage"],s["rule_id"],s["metric"],s["formula_contract"],s["role"]])
    for pair in result["joint_patterns"]:
        pair["left"],pair["right"] = result["series"][pair["left"]]["key"],result["series"][pair["right"]]["key"]
    return result


def pack(report):
    raw = canonical(report).encode()
    if len(raw) > MAX_EXPANDED_BYTES:
        raise ValueError("numeric_evolution_expanded_budget_exceeded")
    interned = canonical(_storage_report(report)).encode()
    result = canonical({"encoding":"lzma-base64-factored-json-v1", "sha256":hashlib.sha256(raw).hexdigest(),
                        "bytes":len(raw),"data":base64.b64encode(lzma.compress(interned,preset=6)).decode()})
    if len(result.encode()) > MAX_PAYLOAD_BYTES:
        raise ValueError("numeric_evolution_storage_budget_exceeded")
    return result


def unpack(payload):
    envelope = obj(payload)
    if len(canonical(envelope).encode()) > MAX_PAYLOAD_BYTES or envelope.get("encoding") != "lzma-base64-factored-json-v1" or not 0 < envelope.get("bytes",0) <= MAX_EXPANDED_BYTES:
        raise ValueError("numeric_evolution_invalid_payload")
    decoder = lzma.LZMADecompressor(memlimit=32*1024*1024)
    data = decoder.decompress(base64.b64decode(envelope["data"],validate=True),max_length=MAX_EXPANDED_BYTES+1)
    if len(data) > MAX_EXPANDED_BYTES or not decoder.eof or decoder.unused_data:
        raise ValueError("numeric_evolution_corrupt_payload")
    report = _expand_report(json.loads(data))
    raw = canonical(report).encode()
    if len(raw)!=envelope["bytes"] or hashlib.sha256(raw).hexdigest()!=envelope["sha256"]:
        raise ValueError("numeric_evolution_corrupt_payload")
    return report


def compare_episodes(current, historical):
    """Compare only previously closed, nonoverlapping episodes with same contract.

    Each episode contributes one mean per pattern. Control count is reported but
    is never the sample size for confidence. No auto promotion / weight fitting.
    """
    prior, intervals = [], []
    for item in sorted(historical, key=lambda r:timestamp(r.get("closed_at")) or 0):
        if item["version"] != current["version"] or any(item[k]!=current[k] for k in ("symbol","side","time_horizon")):
            continue
        start, end = timestamp(item.get("started_at")), timestamp(item.get("closed_at"))
        cutoff = timestamp(current.get("started_at"))
        if not start or not end or not cutoff or end > cutoff or any(start <= b and end >= a for a,b in intervals):
            continue
        prior.append(item)
        intervals.append((start,end))
    buckets = defaultdict(list)
    for episode in prior:
        for series in episode["series"]:
            for minutes, summary in series["forward"].items():
                for pattern, values in summary["patterns"].items():
                    buckets[(series["key"],minutes,pattern)].append(values)
    comparisons = []
    for series in current["series"]:
        for minutes, summary in series["forward"].items():
            for pattern, values in summary["patterns"].items():
                reference = buckets.get((series["key"],minutes,pattern),[])
                if not reference:
                    continue
                comparisons.append({"series_key":series["key"],"minutes":int(minutes),"pattern":pattern,
                    "prior_independent_episodes":len(reference), "prior_controls":sum(r["n"] for r in reference),
                    "prior_episode_weighted_mean_return_bps":sum(r["mean_return_bps"] for r in reference)/len(reference),
                    "current_mean_return_bps":values["mean_return_bps"],"current_controls":values["n"]})
    joint_buckets = defaultdict(list)
    joint_key = lambda row: (row["left"],row["right"],row["minutes"],row["left_state"],row["right_state"])
    for episode in prior:
        for row in episode["joint_patterns"]:
            joint_buckets[joint_key(row)].append(row)
    joint_comparisons = []
    for row in current["joint_patterns"]:
        references = joint_buckets.get(joint_key(row), [])
        if references:
            joint_comparisons.append({"left":row["left"],"right":row["right"],"minutes":row["minutes"],
                "left_state":row["left_state"],"right_state":row["right_state"],
                "prior_independent_episodes":len(references),
                "prior_episode_weighted_mean_return_bps":sum(r["mean_return_bps"] for r in references)/len(references),
                "current_mean_return_bps":row["mean_return_bps"]})
    return {"eligible_prior_episodes":len(prior),"comparisons":comparisons,"joint_comparisons":joint_comparisons,
            "status":"descriptive_comparison" if comparisons or joint_comparisons else "no_comparable_prior_episodes",
            "production_effect":"none","confidence":"not_a_probability_or_rule_validation"}
