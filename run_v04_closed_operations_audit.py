from __future__ import annotations

import copy
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import m8_evaluation as m8
from db import close_pool, connect
from m6_predictive_rules import (
    ACTIVE_PREDICTIVE_RULE_IDS,
    PROVISIONAL_RULE_WEIGHTS,
    apply_provisional_rule_overlay,
)
from run_repaired_historical_comparison import repaired_candidate_predictions


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
COMPARISON_PATH = (
    AUDIT_DIR / "comparacion_todas_operaciones_cerradas_v0_1.json"
)
DEVELOPMENT_PATH = (
    AUDIT_DIR / "dataset_desarrollo_calibracion_m8_3_v0_1.json"
)
FINAL_PATH = AUDIT_DIR / "dataset_final_sellado_m8_3_v0_1.json"
MODEL_PATH = AUDIT_DIR / "modelo_estimado_calibrado_m8_5_v0_1.json"
FROZEN_CANDIDATE_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
OUTPUT_PATH = AUDIT_DIR / "auditoria_operaciones_cerradas_motor_v0_4.json"
REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_auditoria_operaciones_cerradas_motor_v0_4.md"
)
FEATURE_CACHE_PATH = (
    AUDIT_DIR / "cache_pretrade_operaciones_cerradas_motor_v0_4.json"
)

CLASSES = m8.CLASSES
EXACT_OVERLAY_RULES = {
    "M4-RULE-PATH-STRUCTURE-001",
    "M4-RULE-CONTINUOUS-REGIME-001",
    "M4-RULE-MARK-INDEX-PREMIUM-001",
    "M4-RULE-FUNDING-STATE-001",
}
APPROXIMATE_OVERLAY_RULES = {
    "M4-RULE-AGGRESSOR-IMBALANCE-001",
    "M4-RULE-OPEN-INTEREST-CHANGE-001",
    "M4-RULE-PRICE-OI-STATE-001",
}
BASIS_RULE = "M4-RULE-SPOT-FUTURES-BASIS-001"
FITTED_RULE_FEATURES = {
    "M4-RULE-PRIOR-EXTREMA-001": (
        "target_extreme_between_entry_and_tp",
    ),
    "M4-RULE-VOLATILITY-RANK-001": (
        "volatility_percentile_60",
    ),
    "M4-RULE-MTF-HIERARCHY-001": (
        "directional_path_efficiency_2h",
        "directional_path_efficiency_4h",
    ),
}
PERIOD_SECONDS = {"5m": 300, "1h": 3600, "1d": 86400}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def sign(value: float) -> float:
    return 1.0 if value > 0 else -1.0 if value < 0 else 0.0


def normalize_probabilities(values: dict) -> dict[str, float]:
    result = {name: float(values[name]) for name in CLASSES}
    total = math.fsum(result.values())
    if total <= 0:
        raise ValueError("invalid_probability_mass")
    return {name: value / total for name, value in result.items()}


def load_feature_records() -> dict[int, dict]:
    result = {}
    for path in (DEVELOPMENT_PATH, FINAL_PATH, FEATURE_CACHE_PATH):
        if not path.exists():
            continue
        for row in read_json(path).get("records", []):
            pretrade = row.get("pretrade") or {}
            if pretrade.get("status") == "evaluated":
                result[int(row["recommendation_id"])] = pretrade
    return result


def fetch_database_rows(recommendation_ids: list[int]) -> dict[int, dict]:
    sql = """
    SELECT
        r.id AS recommendation_id,
        r.created_at AS analysis_at,
        r.snapshot_json,
        o.id AS operation_id,
        o.entry,
        o.take_profit,
        o.stop_loss,
        o.symbol,
        o.side,
        o.time_horizon
    FROM recommendations r
    JOIN operations o ON o.id = r.operation_id
    WHERE r.id = ANY(?)
    """
    with connect() as db:
        rows = db.execute(sql, ([int(value) for value in recommendation_ids],))
        result = {int(row["recommendation_id"]): dict(row) for row in rows.fetchall()}
    close_pool()
    return result


def reconstruct_missing_features(
    cases: list[dict],
    database_rows: dict[int, dict],
    existing: dict[int, dict],
) -> dict[int, dict]:
    missing = []
    for case in cases:
        recommendation_id = int(case["recommendation_id"])
        if recommendation_id in existing:
            continue
        raw = database_rows.get(recommendation_id)
        if raw is None:
            continue
        horizon_name = str(raw["time_horizon"])
        missing.append(
            {
                "recommendation_id": recommendation_id,
                "operation_id": int(raw["operation_id"]),
                "analysis_at": m8.parse_utc(raw["analysis_at"]).isoformat(),
                "symbol": str(raw["symbol"]).upper(),
                "side": str(raw["side"]).lower(),
                "time_horizon": horizon_name,
                "horizon_seconds": m8.HORIZON_SECONDS[horizon_name],
                "entry": float(raw["entry"]),
                "take_profit": float(raw["take_profit"]),
                "stop_loss": float(raw["stop_loss"]),
            }
        )
    if not missing:
        return existing
    try:
        m8.enrich_pretrade_features(missing)
    except Exception as exc:
        print(f"PRETRADE_RECONSTRUCTION_WARNING={type(exc).__name__}:{exc}")
        return existing
    cache_records = []
    for row in missing:
        pretrade = row.get("pretrade") or {}
        if pretrade.get("status") != "evaluated":
            continue
        recommendation_id = int(row["recommendation_id"])
        existing[recommendation_id] = pretrade
        cache_records.append(
            {
                "recommendation_id": recommendation_id,
                "operation_id": row["operation_id"],
                "analysis_at": row["analysis_at"],
                "pretrade": pretrade,
            }
        )
    write_json(
        FEATURE_CACHE_PATH,
        {
            "version": "v0.4-closed-pretrade-cache-v0.1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "records": cache_records,
        },
    )
    return existing


def snapshot_object(raw: Any) -> dict:
    return m8.parse_json_object(raw)


def nearest_period(
    derivatives: dict,
    horizon_seconds: int,
) -> tuple[str | None, dict]:
    by_period = derivatives.get("by_period")
    candidates = []
    if isinstance(by_period, dict):
        for name, values in by_period.items():
            if name in PERIOD_SECONDS and isinstance(values, dict):
                candidates.append(
                    (
                        abs(math.log(horizon_seconds / PERIOD_SECONDS[name])),
                        -PERIOD_SECONDS[name],
                        name,
                        values,
                    )
                )
    if candidates:
        _, _, name, values = min(candidates)
        return name, values
    return None, derivatives


def build_historical_signal_snapshot(
    *,
    case: dict,
    pretrade: dict | None,
    snapshot: dict,
    include_approximations: bool,
) -> tuple[dict, dict]:
    active = {}
    unavailable = {}
    provenance = {}
    side_direction = 1.0 if case["side"] == "long" else -1.0
    values = (pretrade or {}).get("feature_values") or {}

    directional_path = finite_float(
        values.get("directional_path_efficiency_h")
    )
    volatility_percentile = finite_float(
        values.get("volatility_percentile_60")
    )
    if directional_path is not None:
        active["M4-RULE-PATH-STRUCTURE-001"] = directional_path
        provenance["M4-RULE-PATH-STRUCTURE-001"] = {
            "quality": "exact_historical_reconstruction",
            "source": "closed_futures_klines_before_analysis",
        }
    else:
        unavailable["M4-RULE-PATH-STRUCTURE-001"] = "pretrade_feature_missing"
    if directional_path is not None and volatility_percentile is not None:
        active["M4-RULE-CONTINUOUS-REGIME-001"] = max(
            -1.0,
            min(
                1.0,
                directional_path * (2.0 * volatility_percentile - 1.0),
            ),
        )
        provenance["M4-RULE-CONTINUOUS-REGIME-001"] = {
            "quality": "exact_historical_reconstruction",
            "source": "closed_futures_klines_before_analysis",
        }
    else:
        unavailable["M4-RULE-CONTINUOUS-REGIME-001"] = (
            "pretrade_feature_missing"
        )

    derivatives = snapshot.get("derivatives")
    derivatives = derivatives if isinstance(derivatives, dict) else {}
    period_name, period = nearest_period(
        derivatives,
        m8.HORIZON_SECONDS[str(case["time_horizon"])],
    )
    buy = finite_float(period.get("taker_buy_volume"))
    sell = finite_float(period.get("taker_sell_volume"))
    oi_pct = finite_float(period.get("open_interest_change_pct"))
    if oi_pct is None:
        oi_pct = finite_float(
            derivatives.get("open_interest_change_5m_window_pct")
        )

    if include_approximations and buy is not None and sell is not None:
        total = buy + sell
        if total > 0:
            active["M4-RULE-AGGRESSOR-IMBALANCE-001"] = (
                side_direction * (buy - sell) / total
            )
            provenance["M4-RULE-AGGRESSOR-IMBALANCE-001"] = {
                "quality": "approximate_stored_period",
                "source": f"snapshot.derivatives.by_period.{period_name}",
                "reason": "stored period does not always cover exact H",
            }
    if "M4-RULE-AGGRESSOR-IMBALANCE-001" not in active:
        unavailable["M4-RULE-AGGRESSOR-IMBALANCE-001"] = (
            "exact_horizon_taker_window_not_stored"
        )

    doi = None
    if include_approximations and oi_pct is not None and oi_pct > -100:
        doi = math.log1p(oi_pct / 100.0)
        oi_signal = math.tanh(50.0 * abs(doi))
        active["M4-RULE-OPEN-INTEREST-CHANGE-001"] = oi_signal
        provenance["M4-RULE-OPEN-INTEREST-CHANGE-001"] = {
            "quality": "approximate_stored_period",
            "source": f"snapshot.derivatives.by_period.{period_name}",
            "reason": "stored period does not always cover exact H",
        }
    else:
        unavailable["M4-RULE-OPEN-INTEREST-CHANGE-001"] = (
            "exact_horizon_oi_pair_not_stored"
        )

    if doi is not None and directional_path is not None:
        active["M4-RULE-PRICE-OI-STATE-001"] = (
            sign(directional_path) * math.tanh(50.0 * doi)
        )
        provenance["M4-RULE-PRICE-OI-STATE-001"] = {
            "quality": "approximate_stored_period",
            "source": (
                "pretrade_path_sign_plus_"
                f"snapshot.derivatives.by_period.{period_name}"
            ),
            "reason": "stored OI period does not always cover exact H",
        }
    else:
        unavailable["M4-RULE-PRICE-OI-STATE-001"] = (
            "path_or_exact_horizon_oi_missing"
        )

    mark = finite_float(derivatives.get("mark_price"))
    index = finite_float(derivatives.get("index_price"))
    if mark is not None and index is not None and mark > 0 and index > 0:
        premium = math.log(mark / index)
        active["M4-RULE-MARK-INDEX-PREMIUM-001"] = max(
            -1.0,
            min(1.0, -side_direction * math.tanh(200.0 * premium)),
        )
        provenance["M4-RULE-MARK-INDEX-PREMIUM-001"] = {
            "quality": "exact_stored_snapshot",
            "source": "snapshot.derivatives.mark_price/index_price",
        }
    else:
        unavailable["M4-RULE-MARK-INDEX-PREMIUM-001"] = (
            "mark_or_index_missing"
        )

    funding_pct = finite_float(derivatives.get("funding_rate_pct"))
    if funding_pct is not None:
        funding_rate = funding_pct / 100.0
        active["M4-RULE-FUNDING-STATE-001"] = max(
            -1.0,
            min(
                1.0,
                -side_direction * math.tanh(funding_rate / 0.0005),
            ),
        )
        provenance["M4-RULE-FUNDING-STATE-001"] = {
            "quality": "exact_stored_snapshot",
            "source": "snapshot.derivatives.funding_rate_pct",
        }
    else:
        unavailable["M4-RULE-FUNDING-STATE-001"] = "funding_missing"

    unavailable[BASIS_RULE] = "spot_and_futures_quotes_not_stored"
    signal_snapshot = {
        "version": "historical-v0.4-replay",
        "active": {},
        "unavailable": {
            rule_id: {"status": "unavailable", "reason_codes": [reason]}
            for rule_id, reason in unavailable.items()
        },
    }
    for rule_id, signal_value in active.items():
        weight = PROVISIONAL_RULE_WEIGHTS[rule_id]
        movement = rule_id == "M4-RULE-OPEN-INTEREST-CHANGE-001"
        signal_snapshot["active"][rule_id] = {
            "signal": float(signal_value),
            "weight": float(weight),
            "effect_mode": "movement" if movement else "directional",
            "tp_log_effect": float(weight) * signal_value,
            "sl_log_effect": (
                float(weight) * signal_value
                if movement
                else -float(weight) * signal_value
            ),
            "expiry_log_effect": (
                -float(weight) * signal_value if movement else 0.0
            ),
            "signal_formula": "historical_replay_equivalent",
            "source_trace_sha256": None,
        }
    return signal_snapshot, provenance


def apply_snapshots(
    base_predictions: dict[int, dict],
    snapshots: dict[int, dict],
    *,
    disabled_rule: str | None = None,
) -> dict[int, dict]:
    result = {}
    for recommendation_id, base in base_predictions.items():
        signal_snapshot = copy.deepcopy(snapshots[recommendation_id])
        if disabled_rule is not None:
            signal_snapshot["active"].pop(disabled_rule, None)
        applied = apply_provisional_rule_overlay(
            normalize_probabilities(base),
            signal_snapshot,
        )
        result[recommendation_id] = applied["probabilities_after"]
    return result


def prediction_metrics(
    rows: list[dict],
    predictions: dict[int, dict],
) -> dict:
    if not rows:
        return {"records": 0}
    brier = 0.0
    log_loss = 0.0
    correct = 0
    actual_probability = 0.0
    confusion: dict[str, Counter] = defaultdict(Counter)
    binary_rows = 0
    binary_correct = 0
    for row in rows:
        recommendation_id = int(row["recommendation_id"])
        values = normalize_probabilities(predictions[recommendation_id])
        actual = row["actual_outcome"]
        predicted = max(values, key=values.get)
        correct += predicted == actual
        actual_probability += values[actual]
        confusion[actual][predicted] += 1
        for name in CLASSES:
            observed = 1.0 if name == actual else 0.0
            brier += (values[name] - observed) ** 2
        log_loss -= math.log(max(values[actual], 1e-15))
        if actual in CLASSES[:2]:
            binary_rows += 1
            binary_correct += max(
                (CLASSES[0], CLASSES[1]),
                key=lambda name: values[name],
            ) == actual
    count = len(rows)
    return {
        "records": count,
        "brier_3c": brier / count,
        "log_loss_3c": log_loss / count,
        "top_class_correct": correct,
        "top_class_accuracy": correct / count,
        "mean_probability_actual_outcome": actual_probability / count,
        "binary_tp_sl_records": binary_rows,
        "binary_tp_sl_correct": binary_correct,
        "binary_tp_sl_accuracy": (
            binary_correct / binary_rows if binary_rows else None
        ),
        "confusion": {
            actual: dict(predicted)
            for actual, predicted in sorted(confusion.items())
        },
    }


def grouped_metrics(
    rows: list[dict],
    predictions: dict[int, dict],
    key: str,
) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {
        name: prediction_metrics(members, predictions)
        for name, members in sorted(groups.items())
    }


def coverage_summary(
    snapshots: dict[int, dict],
    provenance: dict[int, dict],
    total: int,
) -> dict:
    result = {}
    fitted = set(FITTED_RULE_FEATURES)
    for rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
        if rule_id in fitted:
            result[rule_id] = {
                "available": total,
                "missing": 0,
                "quality": "fitted_historical_pretrade_features",
            }
            continue
        available = sum(
            rule_id in snapshot["active"] for snapshot in snapshots.values()
        )
        qualities = Counter(
            details[rule_id]["quality"]
            for details in provenance.values()
            if rule_id in details
        )
        result[rule_id] = {
            "available": available,
            "missing": total - available,
            "quality_counts": dict(qualities),
        }
    return result


def metric_delta(reference: dict, candidate: dict) -> dict:
    return {
        "brier_reduction": (
            reference["brier_3c"] - candidate["brier_3c"]
        ),
        "brier_reduction_pct": (
            (
                reference["brier_3c"] - candidate["brier_3c"]
            )
            / reference["brier_3c"]
            * 100.0
        ),
        "log_loss_reduction": (
            reference["log_loss_3c"] - candidate["log_loss_3c"]
        ),
        "log_loss_reduction_pct": (
            (
                reference["log_loss_3c"] - candidate["log_loss_3c"]
            )
            / reference["log_loss_3c"]
            * 100.0
        ),
        "top_class_accuracy_delta": (
            candidate["top_class_accuracy"]
            - reference["top_class_accuracy"]
        ),
        "actual_outcome_probability_delta": (
            candidate["mean_probability_actual_outcome"]
            - reference["mean_probability_actual_outcome"]
        ),
    }


def build_audit() -> dict:
    comparison = read_json(COMPARISON_PATH)
    cases = [dict(row) for row in comparison["cases"]]
    recommendation_ids = [
        int(row["recommendation_id"]) for row in cases
    ]
    database_rows = fetch_database_rows(recommendation_ids)
    features = reconstruct_missing_features(
        cases,
        database_rows,
        load_feature_records(),
    )

    snapshots_strict = {}
    snapshots_extended = {}
    provenance_strict = {}
    provenance_extended = {}
    rows = []
    old_predictions = {}
    core_predictions = {}
    for case in cases:
        recommendation_id = int(case["recommendation_id"])
        raw = database_rows.get(recommendation_id, {})
        snapshot = snapshot_object(raw.get("snapshot_json"))
        strict, strict_provenance = build_historical_signal_snapshot(
            case=case,
            pretrade=features.get(recommendation_id),
            snapshot=snapshot,
            include_approximations=False,
        )
        extended, extended_provenance = build_historical_signal_snapshot(
            case=case,
            pretrade=features.get(recommendation_id),
            snapshot=snapshot,
            include_approximations=True,
        )
        snapshots_strict[recommendation_id] = strict
        snapshots_extended[recommendation_id] = extended
        provenance_strict[recommendation_id] = strict_provenance
        provenance_extended[recommendation_id] = extended_provenance
        old_predictions[recommendation_id] = normalize_probabilities(
            case["old_engine"]
        )
        core_predictions[recommendation_id] = normalize_probabilities(
            case["new_candidate"]
        )
        analysis_at = m8.parse_utc(raw.get("analysis_at"))
        rows.append(
            {
                **case,
                "analysis_at": (
                    analysis_at.isoformat() if analysis_at else None
                ),
                "analysis_day_utc": (
                    analysis_at.date().isoformat() if analysis_at else None
                ),
                "entry": float(raw["entry"]),
                "take_profit": float(raw["take_profit"]),
                "stop_loss": float(raw["stop_loss"]),
                "pretrade": features.get(recommendation_id),
                "outcome": {"label": case["actual_outcome"]},
            }
        )

    strict_predictions = apply_snapshots(
        core_predictions,
        snapshots_strict,
    )
    extended_predictions = apply_snapshots(
        core_predictions,
        snapshots_extended,
    )
    metrics = {
        "old_engine": prediction_metrics(rows, old_predictions),
        "new_core_three_fitted_rules": prediction_metrics(
            rows,
            core_predictions,
        ),
        "new_strict_seven_rule_replay": prediction_metrics(
            rows,
            strict_predictions,
        ),
        "new_extended_ten_rule_replay": prediction_metrics(
            rows,
            extended_predictions,
        ),
    }
    metrics["strict_vs_old"] = metric_delta(
        metrics["old_engine"],
        metrics["new_strict_seven_rule_replay"],
    )
    metrics["extended_vs_old"] = metric_delta(
        metrics["old_engine"],
        metrics["new_extended_ten_rule_replay"],
    )
    metrics["extended_vs_core"] = metric_delta(
        metrics["new_core_three_fitted_rules"],
        metrics["new_extended_ten_rule_replay"],
    )
    metrics["paired_bootstrap"] = {
        "strict_vs_old": m8.bootstrap_paired_differences(
            rows,
            strict_predictions,
            old_predictions,
        ),
        "extended_vs_old": m8.bootstrap_paired_differences(
            rows,
            extended_predictions,
            old_predictions,
        ),
    }

    artifact = read_json(FROZEN_CANDIDATE_PATH)["coefficient_artifact"]
    temperature = float(artifact["calibration"]["temperature"])
    recomputed_core = repaired_candidate_predictions(
        rows,
        artifact,
        temperature=temperature,
    )
    core_max_absolute_difference = max(
        abs(
            core_predictions[int(row["recommendation_id"])][class_name]
            - recomputed_core[int(row["recommendation_id"])][class_name]
        )
        for row in rows
        for class_name in CLASSES
    )
    ablations = {}
    for rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
        if rule_id in FITTED_RULE_FEATURES:
            candidate = copy.deepcopy(artifact)
            for feature_name in FITTED_RULE_FEATURES[rule_id]:
                candidate["coefficients"]["tp"][feature_name] = 0.0
                candidate["coefficients"]["sl"][feature_name] = 0.0
            fitted_rows = [
                row for row in rows
                if (row.get("pretrade") or {}).get("status") == "evaluated"
            ]
            base_without = repaired_candidate_predictions(
                fitted_rows,
                candidate,
                temperature=temperature,
            )
            snapshots_without = {
                int(row["recommendation_id"]): snapshots_extended[
                    int(row["recommendation_id"])
                ]
                for row in fitted_rows
            }
            predictions_without = apply_snapshots(
                base_without,
                snapshots_without,
            )
            full_subset = {
                int(row["recommendation_id"]): extended_predictions[
                    int(row["recommendation_id"])
                ]
                for row in fitted_rows
            }
            full_metrics = prediction_metrics(fitted_rows, full_subset)
            without_metrics = prediction_metrics(
                fitted_rows,
                predictions_without,
            )
        else:
            predictions_without = apply_snapshots(
                core_predictions,
                snapshots_extended,
                disabled_rule=rule_id,
            )
            full_metrics = metrics["new_extended_ten_rule_replay"]
            without_metrics = prediction_metrics(rows, predictions_without)
        ablations[rule_id] = {
            "records": full_metrics["records"],
            "full_brier": full_metrics["brier_3c"],
            "without_rule_brier": without_metrics["brier_3c"],
            "brier_improvement_from_rule": (
                without_metrics["brier_3c"]
                - full_metrics["brier_3c"]
            ),
            "full_log_loss": full_metrics["log_loss_3c"],
            "without_rule_log_loss": without_metrics["log_loss_3c"],
            "log_loss_improvement_from_rule": (
                without_metrics["log_loss_3c"]
                - full_metrics["log_loss_3c"]
            ),
            "accuracy_change_from_rule": (
                full_metrics["top_class_accuracy"]
                - without_metrics["top_class_accuracy"]
            ),
        }

    cases_output = []
    outcome_probability_wins = Counter()
    for row in rows:
        recommendation_id = int(row["recommendation_id"])
        actual = row["actual_outcome"]
        old_actual = old_predictions[recommendation_id][actual]
        new_actual = extended_predictions[recommendation_id][actual]
        comparison_name = (
            "new" if new_actual > old_actual
            else "old" if old_actual > new_actual
            else "tie"
        )
        outcome_probability_wins[comparison_name] += 1
        cases_output.append(
            {
                "operation_id": row["operation_id"],
                "recommendation_id": recommendation_id,
                "analysis_at": row["analysis_at"],
                "symbol": row["symbol"],
                "side": row["side"],
                "time_horizon": row["time_horizon"],
                "actual_outcome": actual,
                "old_engine": old_predictions[recommendation_id],
                "new_core": core_predictions[recommendation_id],
                "new_strict_replay": strict_predictions[recommendation_id],
                "new_extended_replay": extended_predictions[
                    recommendation_id
                ],
                "higher_probability_for_actual_outcome": comparison_name,
                "rule_provenance": provenance_extended[
                    recommendation_id
                ],
                "unavailable_rules": snapshots_extended[
                    recommendation_id
                ]["unavailable"],
            }
        )

    coverage = coverage_summary(
        snapshots_extended,
        provenance_extended,
        len(rows),
    )
    full_feature_records = sum(
        (row.get("pretrade") or {}).get("status") == "evaluated"
        for row in rows
    )
    final_ids = {
        int(row["recommendation_id"])
        for row in read_json(FINAL_PATH).get("records", [])
    }
    final_rows = [
        row
        for row in rows
        if int(row["recommendation_id"]) in final_ids
    ]
    final_metrics = {
        "records": len(final_rows),
        "old_engine": prediction_metrics(final_rows, old_predictions),
        "new_core": prediction_metrics(final_rows, core_predictions),
        "new_strict_replay": prediction_metrics(
            final_rows,
            strict_predictions,
        ),
        "new_extended_replay": prediction_metrics(
            final_rows,
            extended_predictions,
        ),
    }
    final_metrics["extended_vs_old"] = metric_delta(
        final_metrics["old_engine"],
        final_metrics["new_extended_replay"],
    )
    payload = {
        "version": "closed-operations-v0.4-rule-audit-v0.1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "finalized_database_records": comparison["coverage"][
                "finalized_operations_found"
            ],
            "closed_executed_database_records": comparison["coverage"][
                "closed_executed_operations"
            ],
            "cancelled_database_records": comparison["coverage"][
                "cancelled_operations"
            ],
            "resolved_unambiguous_operations_audited": len(rows),
            "closed_operations_excluded": (
                comparison["coverage"]["closed_executed_operations"]
                - len(rows)
            ),
            "formal_exact_horizon_records": comparison["coverage"][
                "formal_exact_horizon_comparisons"
            ],
            "policy_reconstructed_horizon_records": (
                len(rows)
                - comparison["coverage"][
                    "formal_exact_horizon_comparisons"
                ]
            ),
            "pretrade_candle_feature_records": full_feature_records,
        },
        "replay_definitions": {
            "old_engine": "probabilities stored at original analysis time",
            "new_core": "calibrated M6 candidate with 3 fitted rules",
            "strict_replay": (
                "3 fitted rules plus every exact historical overlay available; "
                "up to 7 rules per record"
            ),
            "extended_replay": (
                "strict replay plus taker, OI and price-OI reconstructed "
                "from the nearest stored derivative period; up to 10 rules"
            ),
            "basis_policy": (
                "neutralized because synchronized spot/futures quotes were "
                "not stored in historical recommendation snapshots"
            ),
        },
        "rule_coverage": coverage,
        "metrics": metrics,
        "sealed_final_test_metrics": final_metrics,
        "integrity_checks": {
            "recomputed_core_max_absolute_probability_difference": (
                core_max_absolute_difference
            ),
            "recomputed_core_matches_stored_comparison": (
                core_max_absolute_difference <= 1e-12
            ),
        },
        "outcome_probability_comparison_extended_vs_old": dict(
            outcome_probability_wins
        ),
        "breakdowns_extended": {
            "by_symbol": grouped_metrics(
                rows,
                extended_predictions,
                "symbol",
            ),
            "by_side": grouped_metrics(
                rows,
                extended_predictions,
                "side",
            ),
            "by_time_horizon": grouped_metrics(
                rows,
                extended_predictions,
                "time_horizon",
            ),
        },
        "rule_ablations": ablations,
        "cases": cases_output,
        "conclusion": {
            "strict_replay_better_than_old": (
                metrics["strict_vs_old"]["brier_reduction"] > 0
                and metrics["strict_vs_old"]["log_loss_reduction"] > 0
            ),
            "extended_replay_better_than_old": (
                metrics["extended_vs_old"]["brier_reduction"] > 0
                and metrics["extended_vs_old"]["log_loss_reduction"] > 0
            ),
            "full_eleven_rule_historical_replay_possible": False,
            "reason": (
                "Historical snapshots do not contain synchronized "
                "spot/futures quotes and do not always retain exact-H "
                "taker/OI windows."
            ),
            "production_change_authorized_by_this_audit": False,
        },
    }
    return m8.add_payload_hash(payload)


def render_report(payload: dict) -> str:
    scope = payload["scope"]
    metrics = payload["metrics"]
    old = metrics["old_engine"]
    core = metrics["new_core_three_fitted_rules"]
    strict = metrics["new_strict_seven_rule_replay"]
    extended = metrics["new_extended_ten_rule_replay"]
    strict_delta = metrics["strict_vs_old"]
    extended_delta = metrics["extended_vs_old"]
    wins = payload["outcome_probability_comparison_extended_vs_old"]
    ablations = sorted(
        payload["rule_ablations"].items(),
        key=lambda item: item[1]["brier_improvement_from_rule"],
        reverse=True,
    )
    lines = [
        "# Auditoria de operaciones cerradas: motor v0.4",
        "",
        "## Cobertura",
        "",
        (
            f"- Registros finalizados en base de datos: "
            f"{scope['finalized_database_records']}."
        ),
        (
            f"- Operaciones ejecutadas y cerradas: "
            f"{scope['closed_executed_database_records']}."
        ),
        (
            f"- Operaciones con desenlace inequívoco auditadas: "
            f"{scope['resolved_unambiguous_operations_audited']}."
        ),
        (
            f"- Operaciones cerradas excluidas por desenlace ambiguo: "
            f"{scope['closed_operations_excluded']}."
        ),
        (
            f"- Casos con variables preoperación de velas: "
            f"{scope['pretrade_candle_feature_records']}."
        ),
        "",
        "## Resultado global",
        "",
        "| Motor | Brier | Log-loss | Acierto principal | Prob. media al resultado real |",
        "|---|---:|---:|---:|---:|",
        (
            f"| Antiguo | {old['brier_3c']:.6f} | "
            f"{old['log_loss_3c']:.6f} | "
            f"{old['top_class_accuracy']:.2%} | "
            f"{old['mean_probability_actual_outcome']:.2%} |"
        ),
        (
            f"| Nuevo, núcleo 3 reglas | {core['brier_3c']:.6f} | "
            f"{core['log_loss_3c']:.6f} | "
            f"{core['top_class_accuracy']:.2%} | "
            f"{core['mean_probability_actual_outcome']:.2%} |"
        ),
        (
            f"| Nuevo, repetición estricta, hasta 7 reglas | "
            f"{strict['brier_3c']:.6f} | "
            f"{strict['log_loss_3c']:.6f} | "
            f"{strict['top_class_accuracy']:.2%} | "
            f"{strict['mean_probability_actual_outcome']:.2%} |"
        ),
        (
            f"| Nuevo, repetición ampliada, hasta 10 reglas | "
            f"{extended['brier_3c']:.6f} | "
            f"{extended['log_loss_3c']:.6f} | "
            f"{extended['top_class_accuracy']:.2%} | "
            f"{extended['mean_probability_actual_outcome']:.2%} |"
        ),
        "",
        (
            "- Mejora estricta frente al antiguo: "
            f"Brier {strict_delta['brier_reduction_pct']:.2f}%, "
            f"log-loss {strict_delta['log_loss_reduction_pct']:.2f}%."
        ),
        (
            "- Mejora ampliada frente al antiguo: "
            f"Brier {extended_delta['brier_reduction_pct']:.2f}%, "
            f"log-loss {extended_delta['log_loss_reduction_pct']:.2f}%."
        ),
        (
            "- Mayor probabilidad asignada al resultado real: "
            f"nuevo {wins.get('new', 0)}, antiguo {wins.get('old', 0)}, "
            f"empate {wins.get('tie', 0)}."
        ),
        "",
        "## Prueba final independiente",
        "",
        (
            f"- Casos sellados: "
            f"{payload['sealed_final_test_metrics']['records']}."
        ),
        (
            "- Brier antiguo frente a repetición ampliada: "
            f"{payload['sealed_final_test_metrics']['old_engine']['brier_3c']:.6f} "
            "frente a "
            f"{payload['sealed_final_test_metrics']['new_extended_replay']['brier_3c']:.6f}."
        ),
        (
            "- Log-loss antiguo frente a repetición ampliada: "
            f"{payload['sealed_final_test_metrics']['old_engine']['log_loss_3c']:.6f} "
            "frente a "
            f"{payload['sealed_final_test_metrics']['new_extended_replay']['log_loss_3c']:.6f}."
        ),
        (
            "- Acierto principal antiguo frente a repetición ampliada: "
            f"{payload['sealed_final_test_metrics']['old_engine']['top_class_accuracy']:.2%} "
            "frente a "
            f"{payload['sealed_final_test_metrics']['new_extended_replay']['top_class_accuracy']:.2%}."
        ),
        "",
        "## Ablacion por regla",
        "",
        "| Regla | Mejora Brier | Mejora log-loss |",
        "|---|---:|---:|",
    ]
    for rule_id, values in ablations:
        lines.append(
            f"| `{rule_id}` | "
            f"{values['brier_improvement_from_rule']:+.6f} | "
            f"{values['log_loss_improvement_from_rule']:+.6f} |"
        )
    lines.extend(
        [
            "",
            "## Limite de la repeticion",
            "",
            (
                "- El basis spot/futuros queda neutralizado: las cotizaciones "
                "sincronizadas no se almacenaron en los analisis antiguos."
            ),
            (
                "- Taker, OI y precio-OI usan el periodo historico almacenado "
                "mas cercano; no siempre coincide exactamente con H."
            ),
            (
                "- Por ello, la repeticion de hasta 7 reglas usa solo datos "
                "exactos disponibles y la de hasta 10 es diagnostica. No existe "
                "una repeticion historica exacta de las 11."
            ),
            (
                "- Solo "
                f"{scope['formal_exact_horizon_records']} caso guardo H exacto; "
                f"{scope['policy_reconstructed_horizon_records']} usan la "
                "politica temporal congelada reconstruida."
            ),
            "",
            (
                "Motor ampliado mejor que el antiguo en Brier y log-loss: "
                f"{'si' if payload['conclusion']['extended_replay_better_than_old'] else 'no'}."
            ),
            "Cambio de produccion autorizado por esta auditoria: no.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    payload = build_audit()
    write_json(OUTPUT_PATH, payload)
    report = render_report(payload)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
