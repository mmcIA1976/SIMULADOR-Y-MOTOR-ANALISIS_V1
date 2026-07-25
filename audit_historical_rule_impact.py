from __future__ import annotations

import argparse
import base64
import gzip
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AUDIT_VERSION = "E1.4-v0.1"
TARGET_ENGINE_VERSION = "rules-v0.12.1-liquidations-readable"
TARGET_SCORING_VERSION = "scoring-v0.11-underweighted-risk-cluster"
PROBABILITY_TOLERANCE = 0.0001

PRE_TP_COMPONENTS = {
    "trend_bias": 1.0,
    "technical_direction_bias": 1.0,
    "price_vs_entry_bias": 1.0,
    "volume_bias": 1.0,
    "order_book_bias": 1.0,
    "momentum_bias": 1.0,
    "market_regime_bias": 1.0,
    "fibonacci_probability_adjustment": 1.0,
    "zone_probability_adjustment": 1.0,
    "taker_flow_bias": 1.0,
    "cvd_bias": 1.0,
    "oi_trend_bias": 1.0,
    "breadth_bias": 1.0,
    "volatility_penalty": -1.0,
    "liquidity_penalty": -1.0,
    "overextension_penalty": -1.0,
    "funding_penalty": -1.0,
    "funding_relative_penalty": -1.0,
    "crowding_penalty": -1.0,
    "level_penalty": -1.0,
    "sentiment_penalty": -1.0,
    "higher_timeframe_penalty": -1.0,
    "technical_entry_timing_penalty": -1.0,
    "technical_barrier_penalty": -1.0,
    "oi_context_penalty": -1.0,
    "contradiction_penalty": -1.0,
}

POST_TP_COMPONENT = "risk_calibration_tp_adjustment"
RANGE_COMPONENTS = (
    "zone_range_probability_adjustment",
    "risk_calibration_range_adjustment",
)
DIRECT_ABLATION_UNITS = tuple(PRE_TP_COMPONENTS) + (POST_TP_COMPONENT,) + RANGE_COMPONENTS

COMPOSITE_UNITS = {
    "risk_calibration_bundle": {
        "status": "aggregate_replayable",
        "description": (
            "Retira el agregado historico de calibracion: TP/rango, riesgo, "
            "penalizacion EV, confianza, cap de grado y force_observar."
        ),
    },
    "zone_bundle_partial": {
        "status": "partial",
        "description": (
            "Retira los tres efectos de zona registrados. No puede desactivar "
            "por separado gates de calibracion originados por la zona."
        ),
    },
    "ema_overlap_direct_bundle": {
        "status": "partial",
        "description": (
            "Retira las contribuciones directas de tendencia, rating tecnico, "
            "regimen y penalizacion HTF; no separa gates EMA de calibracion."
        ),
    },
}


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def score_to_percent(value: float, low: float, high: float) -> int:
    if high == low:
        return 50
    normalized = (value - low) / (high - low)
    return round(clamp(normalized, 0.0, 1.0) * 100)


def probability_range_base(record: dict, contradiction_value: float) -> float:
    context = record["context"]
    if context["market_regime"] in {"compresion", "mixto"}:
        return 0.12
    if contradiction_value >= 0.03:
        return 0.10
    return 0.08 if context["recent_range_pct"] < 1.2 else 0.06


def replay_probabilities(
    record: dict,
    disabled_units: set[str] | None = None,
) -> dict:
    disabled = disabled_units or set()
    components = record["score_components"]
    pre_tp = 0.5
    for key, sign in PRE_TP_COMPONENTS.items():
        value = 0.0 if key in disabled else float(components.get(key) or 0.0)
        pre_tp += sign * value

    first_tp = clamp(pre_tp, 0.26, 0.74)
    calibration_adjustment = (
        0.0
        if POST_TP_COMPONENT in disabled
        else float(components.get(POST_TP_COMPONENT) or 0.0)
    )
    tp_probability = clamp(first_tp + calibration_adjustment, 0.22, 0.74)

    contradiction = (
        0.0
        if "contradiction_penalty" in disabled
        else float(components.get("contradiction_penalty") or 0.0)
    )
    zone_range = (
        0.0
        if "zone_range_probability_adjustment" in disabled
        else float(components.get("zone_range_probability_adjustment") or 0.0)
    )
    calibration_range = (
        0.0
        if "risk_calibration_range_adjustment" in disabled
        else float(components.get("risk_calibration_range_adjustment") or 0.0)
    )
    initial_range = min(0.20, probability_range_base(record, contradiction) + zone_range)
    range_probability = clamp(initial_range + calibration_range, 0.04, 0.22)
    sl_probability = max(0.05, 1 - tp_probability - range_probability)
    return {
        "tp_probability": tp_probability,
        "sl_probability": sl_probability,
        "range_probability": range_probability,
        "pre_tp_score": pre_tp,
        "first_tp_score": first_tp,
    }


def replay_risk_score(record: dict) -> float:
    components = record["score_components"]
    context = record["context"]
    risk_distance = context["risk_distance_pct"]
    recent_range = context["recent_range_pct"]
    atr_pct = context["atr_pct"]
    rr_ratio = context["risk_reward_ratio"]
    spread_pct = context["spread_pct"]
    risk_score = (
        (0.2 if risk_distance < max(recent_range, atr_pct) * 0.35 else 0)
        + (0.12 if rr_ratio < 1.2 else 0)
        + (0.08 if recent_range > 2.5 else 0)
        + (0.06 if spread_pct > 0.04 else 0)
        + (0.05 if components.get("overextension_penalty") else 0)
        + (0.06 if components.get("funding_penalty") else 0)
        + (0.04 if components.get("funding_relative_penalty") else 0)
        + (0.04 if components.get("crowding_penalty") else 0)
        + (0.05 if components.get("level_penalty") else 0)
        + (0.03 if components.get("sentiment_penalty") else 0)
        + (0.07 if components.get("higher_timeframe_penalty") else 0)
        + (0.05 if components.get("technical_entry_timing_penalty") else 0)
        + (0.05 if components.get("technical_barrier_penalty") else 0)
        + context["fibonacci_risk_score_addition"]
        + float(components.get("zone_risk_score_addition") or 0)
        + float(components.get("risk_calibration_score_addition") or 0)
        + (0.08 if float(components.get("contradiction_penalty") or 0) >= 0.03 else 0)
    )
    return clamp(risk_score, 0.0, 1.0)


def risk_level_from_score(risk_score: float) -> str:
    if risk_score >= 0.42:
        return "alto"
    if risk_score >= 0.24:
        return "medio-alto"
    if risk_score >= 0.12:
        return "medio"
    return "bajo"


def confidence_from_score(score: int) -> str:
    if score >= 76:
        return "alta"
    if score >= 61:
        return "media"
    if score >= 46:
        return "media-baja"
    return "baja"


def grade_from_scores(tp_probability: float, risk_score: float, ev_score: int) -> str:
    if tp_probability >= 0.62 and risk_score < 0.2 and ev_score >= 58:
        return "A"
    if tp_probability >= 0.52 and risk_score < 0.36 and ev_score >= 50:
        return "B"
    if tp_probability >= 0.44 and ev_score >= 42:
        return "C"
    return "D"


def cap_grade(grade: str, cap: str | None) -> str:
    if cap is None:
        return grade
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return cap if order[grade] < order[cap] else grade


def decision_from_context(
    grade: str,
    risk_level: str,
    confidence: str,
    expected_value_usdt: float,
    force_observar: bool,
) -> str:
    if force_observar or expected_value_usdt < 0:
        return "observar"
    if grade in {"A", "B"} and risk_level != "alto" and confidence in {"alta", "media"}:
        return "simular"
    if grade in {"B", "C"} and risk_level != "alto":
        return "simular con tamano prudente"
    return "observar"


def replay_expected_value(record: dict, probabilities: dict) -> dict:
    expected = record["context"]["expected_value"]
    value = (
        probabilities["tp_probability"] * expected["net_win_usdt"]
        - probabilities["sl_probability"] * expected["net_loss_usdt"]
        - probabilities["range_probability"] * expected["estimated_cost_usdt"]
    )
    notional = expected["notional"]
    pct_notional = (value / notional) * 100 if notional else 0.0
    return {
        "expected_value_usdt": value,
        "expected_value_pct_notional": pct_notional,
    }


def replay_downstream(
    record: dict,
    probabilities: dict,
    *,
    risk_score: float | None = None,
    grade_cap: str | None = None,
    force_observar: bool | None = None,
    confidence: str | None = None,
    ev_score_penalty: int | None = None,
) -> dict:
    calibration = record["context"]["risk_calibration"]
    expected = replay_expected_value(record, probabilities)
    effective_risk_score = replay_risk_score(record) if risk_score is None else risk_score
    effective_grade_cap = calibration["grade_cap"] if grade_cap is None else grade_cap
    effective_force = (
        calibration["force_observar"] if force_observar is None else force_observar
    )
    effective_confidence = record["original"]["confidence"] if confidence is None else confidence
    effective_ev_penalty = (
        calibration["expected_value_score_penalty"]
        if ev_score_penalty is None
        else ev_score_penalty
    )
    expected_value_score = max(
        0,
        score_to_percent(expected["expected_value_pct_notional"], -1.0, 1.6)
        - effective_ev_penalty,
    )
    grade = cap_grade(
        grade_from_scores(
            probabilities["tp_probability"],
            effective_risk_score,
            expected_value_score,
        ),
        effective_grade_cap,
    )
    risk_level = risk_level_from_score(effective_risk_score)
    decision = decision_from_context(
        grade,
        risk_level,
        effective_confidence,
        expected["expected_value_usdt"],
        effective_force,
    )
    return {
        **expected,
        "expected_value_score": expected_value_score,
        "risk_score": effective_risk_score,
        "risk_level": risk_level,
        "setup_grade": grade,
        "confidence": effective_confidence,
        "training_decision": decision,
    }


def replay_baseline(record: dict) -> dict:
    probabilities = replay_probabilities(record)
    downstream = replay_downstream(record, probabilities)
    return {**probabilities, **downstream}


def direct_ablation(record: dict, unit: str) -> dict:
    probabilities = replay_probabilities(record, {unit})
    return {**probabilities, **replay_downstream(record, probabilities)}


def composite_ablation(record: dict, unit: str) -> dict:
    components = record["score_components"]
    context = record["context"]
    if unit == "risk_calibration_bundle":
        probabilities = replay_probabilities(
            record,
            {
                "risk_calibration_tp_adjustment",
                "risk_calibration_range_adjustment",
            },
        )
        risk_score = clamp(
            replay_risk_score(record)
            - float(components.get("risk_calibration_score_addition") or 0),
            0.0,
            1.0,
        )
        calibration = context["risk_calibration"]
        confidence_score = min(
            95,
            context["confidence_score"] + calibration["confidence_score_penalty"],
        )
        return {
            **probabilities,
            **replay_downstream(
                record,
                probabilities,
                risk_score=risk_score,
                grade_cap="A",
                force_observar=False,
                confidence=confidence_from_score(confidence_score),
                ev_score_penalty=0,
            ),
        }
    if unit == "zone_bundle_partial":
        probabilities = replay_probabilities(
            record,
            {
                "zone_probability_adjustment",
                "zone_range_probability_adjustment",
            },
        )
        risk_score = clamp(
            replay_risk_score(record)
            - float(components.get("zone_risk_score_addition") or 0),
            0.0,
            1.0,
        )
        return {
            **probabilities,
            **replay_downstream(record, probabilities, risk_score=risk_score),
        }
    if unit == "ema_overlap_direct_bundle":
        probabilities = replay_probabilities(
            record,
            {
                "trend_bias",
                "technical_direction_bias",
                "market_regime_bias",
                "higher_timeframe_penalty",
            },
        )
        return {**probabilities, **replay_downstream(record, probabilities)}
    raise KeyError(f"Unidad compuesta desconocida: {unit}")


def empty_unit_accumulator(unit: str, kind: str, status: str) -> dict:
    return {
        "unit": unit,
        "kind": kind,
        "status": status,
        "cases": 0,
        "active_cases": 0,
        "tp_changed_cases": 0,
        "sl_changed_cases": 0,
        "range_changed_cases": 0,
        "ev_sign_changed_cases": 0,
        "grade_changed_cases": 0,
        "decision_changed_cases": 0,
        "sum_abs_tp_delta": 0.0,
        "sum_abs_tp_delta_active": 0.0,
        "sum_abs_ev_delta_usdt": 0.0,
        "max_abs_tp_delta": 0.0,
        "max_abs_ev_delta_usdt": 0.0,
    }


def update_unit_accumulator(
    accumulator: dict,
    record: dict,
    baseline: dict,
    counterfactual: dict,
    active: bool,
) -> None:
    original = record["original"]
    tp_delta = counterfactual["tp_probability"] - baseline["tp_probability"]
    sl_delta = counterfactual["sl_probability"] - baseline["sl_probability"]
    range_delta = counterfactual["range_probability"] - baseline["range_probability"]
    ev_delta = (
        counterfactual["expected_value_usdt"] - baseline["expected_value_usdt"]
    )
    accumulator["cases"] += 1
    accumulator["active_cases"] += int(active)
    accumulator["tp_changed_cases"] += int(abs(tp_delta) >= PROBABILITY_TOLERANCE)
    accumulator["sl_changed_cases"] += int(abs(sl_delta) >= PROBABILITY_TOLERANCE)
    accumulator["range_changed_cases"] += int(abs(range_delta) >= PROBABILITY_TOLERANCE)
    accumulator["ev_sign_changed_cases"] += int(
        (baseline["expected_value_usdt"] >= 0 > counterfactual["expected_value_usdt"])
        or (baseline["expected_value_usdt"] < 0 <= counterfactual["expected_value_usdt"])
    )
    accumulator["grade_changed_cases"] += int(
        counterfactual["setup_grade"] != original["setup_grade"]
    )
    accumulator["decision_changed_cases"] += int(
        counterfactual["training_decision"] != original["training_decision"]
    )
    accumulator["sum_abs_tp_delta"] += abs(tp_delta)
    accumulator["sum_abs_tp_delta_active"] += abs(tp_delta) if active else 0.0
    accumulator["sum_abs_ev_delta_usdt"] += abs(ev_delta)
    accumulator["max_abs_tp_delta"] = max(
        accumulator["max_abs_tp_delta"],
        abs(tp_delta),
    )
    accumulator["max_abs_ev_delta_usdt"] = max(
        accumulator["max_abs_ev_delta_usdt"],
        abs(ev_delta),
    )


def audit_records(records: list[dict]) -> dict:
    units = {
        unit: empty_unit_accumulator(unit, "direct_component", "local_ablation")
        for unit in DIRECT_ABLATION_UNITS
    }
    units.update(
        {
            unit: empty_unit_accumulator(
                unit,
                "composite",
                metadata["status"],
            )
            for unit, metadata in COMPOSITE_UNITS.items()
        }
    )
    dimensions = {
        "symbol": Counter(),
        "side": Counter(),
        "time_horizon": Counter(),
        "scoring_version": Counter(),
    }
    flags = Counter()
    replay = {
        "cases": 0,
        "probability_exact_cases": 0,
        "grade_exact_cases": 0,
        "risk_level_exact_cases": 0,
        "decision_exact_cases": 0,
        "max_tp_error": 0.0,
        "max_sl_error": 0.0,
        "max_range_error": 0.0,
    }
    excluded = Counter()

    for record in records:
        if record.get("engine_version") != TARGET_ENGINE_VERSION:
            excluded["different_engine_version"] += 1
            continue
        baseline = replay_baseline(record)
        original = record["original"]
        replay["cases"] += 1
        tp_error = abs(baseline["tp_probability"] - original["tp_probability"])
        sl_error = abs(baseline["sl_probability"] - original["sl_probability"])
        range_error = abs(
            baseline["range_probability"] - original["range_probability"]
        )
        probability_exact = max(tp_error, sl_error, range_error) <= PROBABILITY_TOLERANCE
        replay["probability_exact_cases"] += int(probability_exact)
        replay["grade_exact_cases"] += int(
            baseline["setup_grade"] == original["setup_grade"]
        )
        replay["risk_level_exact_cases"] += int(
            baseline["risk_level"] == original["risk_level"]
        )
        replay["decision_exact_cases"] += int(
            baseline["training_decision"] == original["training_decision"]
        )
        replay["max_tp_error"] = max(replay["max_tp_error"], tp_error)
        replay["max_sl_error"] = max(replay["max_sl_error"], sl_error)
        replay["max_range_error"] = max(replay["max_range_error"], range_error)
        if not probability_exact:
            excluded["probability_replay_mismatch"] += 1
            continue

        for key in dimensions:
            dimensions[key][str(record.get(key) or "sin_version")] += 1
        flags.update(record["context"]["risk_calibration"]["flags"])

        components = record["score_components"]
        for unit in DIRECT_ABLATION_UNITS:
            counterfactual = direct_ablation(record, unit)
            active = abs(float(components.get(unit) or 0)) > 1e-9
            update_unit_accumulator(
                units[unit],
                record,
                baseline,
                counterfactual,
                active,
            )
        for unit in COMPOSITE_UNITS:
            counterfactual = composite_ablation(record, unit)
            if unit == "risk_calibration_bundle":
                active = bool(record["context"]["risk_calibration"]["flags"])
            elif unit == "zone_bundle_partial":
                active = any(
                    abs(float(components.get(key) or 0)) > 1e-9
                    for key in (
                        "zone_probability_adjustment",
                        "zone_range_probability_adjustment",
                        "zone_risk_score_addition",
                    )
                )
            else:
                active = any(
                    abs(float(components.get(key) or 0)) > 1e-9
                    for key in (
                        "trend_bias",
                        "technical_direction_bias",
                        "market_regime_bias",
                        "higher_timeframe_penalty",
                    )
                )
            update_unit_accumulator(
                units[unit],
                record,
                baseline,
                counterfactual,
                active,
            )

    return {
        "audit_version": AUDIT_VERSION,
        "target_engine_version": TARGET_ENGINE_VERSION,
        "target_scoring_version": TARGET_SCORING_VERSION,
        "replay": replay,
        "excluded": dict(excluded),
        "dimensions": {
            key: dict(sorted(counter.items()))
            for key, counter in dimensions.items()
        },
        "risk_calibration_flags": dict(sorted(flags.items())),
        "units": units,
    }


def merge_audits(audits: list[dict]) -> dict:
    merged = audit_records([])
    for audit in audits:
        for key, value in audit["replay"].items():
            if key.startswith("max_"):
                merged["replay"][key] = max(merged["replay"][key], value)
            else:
                merged["replay"][key] += value
        for key, value in audit["excluded"].items():
            merged["excluded"][key] = merged["excluded"].get(key, 0) + value
        for dimension, values in audit["dimensions"].items():
            target = merged["dimensions"][dimension]
            for key, value in values.items():
                target[key] = target.get(key, 0) + value
        for key, value in audit["risk_calibration_flags"].items():
            merged["risk_calibration_flags"][key] = (
                merged["risk_calibration_flags"].get(key, 0) + value
            )
        for unit, source in audit["units"].items():
            target = merged["units"][unit]
            for key, value in source.items():
                if key in {"unit", "kind", "status"}:
                    continue
                if key.startswith("max_"):
                    target[key] = max(target[key], value)
                else:
                    target[key] += value
    return merged


def finalize_audit(audit: dict) -> dict:
    result = json.loads(json.dumps(audit))
    for item in result["units"].values():
        cases = item["cases"]
        active_cases = item["active_cases"]
        item["mean_abs_tp_delta_all"] = round(
            item.pop("sum_abs_tp_delta") / cases if cases else 0.0,
            6,
        )
        item["mean_abs_tp_delta_active"] = (
            round(item.pop("sum_abs_tp_delta_active") / active_cases, 6)
            if active_cases
            else None
        )
        item["mean_abs_ev_delta_usdt"] = round(
            item.pop("sum_abs_ev_delta_usdt") / cases if cases else 0.0,
            6,
        )
        item["max_abs_tp_delta"] = round(item["max_abs_tp_delta"], 6)
        item["max_abs_ev_delta_usdt"] = round(
            item["max_abs_ev_delta_usdt"],
            6,
        )
    for key in ("max_tp_error", "max_sl_error", "max_range_error"):
        result["replay"][key] = round(result["replay"][key], 8)
    result["units"] = dict(
        sorted(
            result["units"].items(),
            key=lambda item: (
                -item[1]["decision_changed_cases"],
                -item[1]["grade_changed_cases"],
                -item[1]["max_abs_tp_delta"],
                item[0],
            ),
        )
    )
    return result


def decode_payload(payload_base64: str) -> list[dict]:
    compressed = base64.b64decode(payload_base64)
    return json.loads(gzip.decompress(compressed).decode("utf-8"))


def decode_json_payload(payload_base64: str) -> list[dict]:
    return json.loads(base64.b64decode(payload_base64).decode("utf-8"))


def load_records(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproduce y audita por ablation snapshots historicos preservados."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--payload-base64")
    source.add_argument("--json-payload-base64")
    source.add_argument("--accumulator-base64")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--partial",
        action="store_true",
        help="Conserva acumuladores para fusionar lotes.",
    )
    args = parser.parse_args()

    if args.accumulator_base64:
        audit = json.loads(
            base64.b64decode(args.accumulator_base64).decode("utf-8")
        )
        payload = finalize_audit(audit)
    else:
        records = (
            load_records(args.input)
            if args.input
            else (
                decode_payload(args.payload_base64)
                if args.payload_base64
                else decode_json_payload(args.json_payload_base64)
            )
        )
        audit = audit_records(records)
        payload = audit if args.partial else finalize_audit(audit)
    serialized = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
