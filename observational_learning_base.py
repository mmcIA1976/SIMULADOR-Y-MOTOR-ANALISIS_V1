from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any, Iterable


BASE_CONTRACT_VERSION = "observational-learning-base-v0.1"
BASELINE_COHORT_KEY = "observational-rules-through-2026-09-09"
HISTORICAL_CUTOFF_AT = "2026-09-09T17:12:19.291651+00:00"
PROBABILITY_WEIGHT = 0.0
PROSPECTIVE_EPISODE_CONTRACT = "fixed-symbol-horizon-time-bucket-v0.1"
HORIZON_SECONDS = {
    "intraday_short": 4 * 60 * 60,
    "intraday_wide": 24 * 60 * 60,
    "short_swing": 7 * 24 * 60 * 60,
}
OUTCOME_CLASSES = (
    "tp_first_within_horizon",
    "sl_first_within_horizon",
    "neither_barrier_before_expiry",
)

# This is the frozen result of the observational-only historical review.  A
# pair absent from this map is deliberately not part of the retained baseline.
RETAINED_RULE_HORIZONS: dict[str, tuple[str, ...]] = {
    "LIB-CAND-CVD-SLOPE-001": ("intraday_wide",),
    "M4-RULE-AGGRESSOR-IMBALANCE-001": ("intraday_wide",),
    "LIB-CAND-ABSORPTION-001": ("intraday_wide",),
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": ("intraday_wide",),
    "LIB-CAND-RELATIVE-VOLUME-001": ("intraday_wide",),
    "LIB-CAND-FIBONACCI-DISTANCE-001": ("short_swing",),
    "M4-RULE-CONTINUOUS-REGIME-001": ("short_swing",),
    "M4-RULE-PRIOR-EXTREMA-001": ("short_swing",),
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": ("intraday_short",),
    "LIB-CAND-LIQUIDATION-ZONE-001": ("intraday_wide",),
    "M4-RULE-OPEN-INTEREST-CHANGE-001": (
        "intraday_short",
        "intraday_wide",
        "short_swing",
    ),
    "M4-RULE-PRICE-OI-STATE-001": ("intraday_short",),
    "M4-RULE-FUNDING-STATE-001": (
        "intraday_short",
        "intraday_wide",
    ),
    "LIB-CAND-EMA-TREND-001": ("intraday_wide",),
}

# One predeclared signal per rule.  These variables are semantic contracts,
# not the best-looking variable selected after seeing the historical outcome.
FROZEN_SIGNAL_VARIABLES = {
    "LIB-CAND-CVD-SLOPE-001": "side_adjusted_normalized_cvd_slope",
    "M4-RULE-AGGRESSOR-IMBALANCE-001": "__current_formula_signal",
    "LIB-CAND-ABSORPTION-001": "side_adjusted_ATI_H",
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": (
        "__adverse_minus_target_path_level_count"
    ),
    "LIB-CAND-RELATIVE-VOLUME-001": "log_relative_horizon_volume",
    "LIB-CAND-FIBONACCI-DISTANCE-001": (
        "__stop_minus_target_fibonacci_distance_sigma"
    ),
    "M4-RULE-CONTINUOUS-REGIME-001": "__current_formula_signal",
    "M4-RULE-PRIOR-EXTREMA-001": "__current_formula_signal",
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": (
        "persistence.within_20bps.side_adjusted_mean"
    ),
    "LIB-CAND-LIQUIDATION-ZONE-001": "target_visible_path_mass_fraction",
    "M4-RULE-OPEN-INTEREST-CHANGE-001": "__current_formula_signal",
    "M4-RULE-PRICE-OI-STATE-001": "__current_formula_signal",
    "M4-RULE-FUNDING-STATE-001": "__current_formula_signal",
    "LIB-CAND-EMA-TREND-001": "side_adjusted_ema50_vs_ema200_log",
}

MOVEMENT_RULE_IDS = {
    "LIB-CAND-RELATIVE-VOLUME-001",
    "M4-RULE-OPEN-INTEREST-CHANGE-001",
}

PLAN_RESULT_TO_OUTCOME = {
    "plan_success": OUTCOME_CLASSES[0],
    "plan_would_succeed": OUTCOME_CLASSES[0],
    "plan_failure": OUTCOME_CLASSES[1],
    "plan_would_fail": OUTCOME_CLASSES[1],
    "plan_unresolved": OUTCOME_CLASSES[2],
    "contest_expiry_mark_to_market": OUTCOME_CLASSES[2],
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def prospective_episode_key(
    *,
    symbol: str,
    time_horizon: str,
    analysis_at: str | datetime,
) -> str:
    """Return a stable independence bucket without revising prior facts later."""
    horizon_seconds = HORIZON_SECONDS.get(str(time_horizon))
    if horizon_seconds is None:
        raise ValueError(f"unsupported_time_horizon:{time_horizon}")
    if isinstance(analysis_at, datetime):
        parsed = analysis_at
    else:
        parsed = datetime.fromisoformat(str(analysis_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    bucket_number = int(parsed.timestamp()) // horizon_seconds
    return payload_sha256(
        {
            "contract": PROSPECTIVE_EPISODE_CONTRACT,
            "symbol": str(symbol).upper(),
            "time_horizon": str(time_horizon),
            "bucket_number": bucket_number,
        }
    )


def parse_json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def flatten_numeric(value: Any, prefix: str = "") -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten_numeric(child, path))
    elif isinstance(value, bool):
        result[prefix] = float(value)
    elif isinstance(value, (int, float)):
        number = finite(value)
        if number is not None:
            result[prefix] = number
    return result


def _iter_traces(value: Any, horizon: str | None = None) -> Iterable[tuple[str | None, dict]]:
    if isinstance(value, dict):
        if value.get("rule_id"):
            yield horizon, value
        for key, child in value.items():
            child_horizon = str(key) if key in {
                "intraday_short",
                "intraday_wide",
                "short_swing",
            } else horizon
            yield from _iter_traces(child, child_horizon)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_traces(child, horizon)


def _synthetic_signal(
    rule_id: str,
    outputs: dict,
    *,
    side: str,
) -> float | None:
    direction = 1.0 if side == "long" else -1.0
    if rule_id == "M4-RULE-AGGRESSOR-IMBALANCE-001":
        raw = finite(outputs.get("ATI_H"))
        return direction * raw if raw is not None else None
    if rule_id == "M4-RULE-CONTINUOUS-REGIME-001":
        signed_efficiency = finite(outputs.get("signed_path_efficiency"))
        directional_efficiency = finite(
            outputs.get("directional_path_efficiency_h")
        )
        percentile = finite(
            outputs.get("volatility_percentile")
            if outputs.get("volatility_percentile") is not None
            else outputs.get("volatility_percentile_60")
        )
        if percentile is not None:
            if directional_efficiency is not None:
                return directional_efficiency * (2.0 * percentile - 1.0)
            if signed_efficiency is not None:
                return direction * signed_efficiency * (2.0 * percentile - 1.0)
    if rule_id == "M4-RULE-PRIOR-EXTREMA-001":
        return finite(outputs.get("target_extreme_between_entry_and_tp"))
    if rule_id == "M4-RULE-OPEN-INTEREST-CHANGE-001":
        raw = finite(
            outputs.get("dOI_H")
            if outputs.get("dOI_H") is not None
            else outputs.get("dOI_H_proxy")
        )
        return math.tanh(50.0 * abs(raw)) if raw is not None else None
    if rule_id == "M4-RULE-FUNDING-STATE-001":
        raw = finite(
            outputs.get("last_funding_rate")
            if outputs.get("last_funding_rate") is not None
            else outputs.get("last_funding_rate_proxy")
        )
        return -direction * math.tanh(raw / 0.0005) if raw is not None else None
    return None


def _composite_snapshot_signal(
    rule_id: str,
    traces_by_rule: dict[str, list[dict]],
    *,
    side: str,
) -> float | None:
    own = traces_by_rule.get(rule_id, [])
    if rule_id == "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001":
        for trace in own:
            outputs = trace.get("outputs") or {}
            target = finite(outputs.get("target_path_level_count"))
            adverse = finite(outputs.get("adverse_path_level_count"))
            if target is not None and adverse is not None:
                return adverse - target
    if rule_id == "LIB-CAND-FIBONACCI-DISTANCE-001":
        for trace in own:
            flat = flatten_numeric(trace.get("outputs") or {})
            target = finite(
                flat.get("nearest_to_take_profit.absolute_distance_sigma_horizon")
            )
            stop = finite(
                flat.get("nearest_to_stop_loss.absolute_distance_sigma_horizon")
            )
            if target is not None and stop is not None:
                return stop - target
    if rule_id == "M4-RULE-CONTINUOUS-REGIME-001" and not own:
        path_traces = traces_by_rule.get("M4-RULE-PATH-STRUCTURE-001", [])
        volatility_traces = traces_by_rule.get("M4-RULE-VOLATILITY-RANK-001", [])
        if path_traces and volatility_traces:
            merged = {
                **(path_traces[-1].get("outputs") or {}),
                **(volatility_traces[-1].get("outputs") or {}),
            }
            return _synthetic_signal(rule_id, merged, side=side)
    return None


def current_snapshot_rule_values(
    snapshot: dict,
    *,
    side: str,
    time_horizon: str,
    baseline_specs: Iterable[dict],
) -> tuple[dict, list[str]]:
    """Extract only frozen comparable variables; never store a raw snapshot."""
    traces_by_rule: dict[str, list[dict]] = {}
    for root_key in ("stage_rule_traces", "feature_snapshot"):
        for trace_horizon, trace in _iter_traces(snapshot.get(root_key)):
            if trace_horizon not in {None, time_horizon}:
                continue
            status = str(trace.get("status") or "")
            if status not in {
                "evaluated",
                "evaluated_shadow",
                "evaluated_observation_reconstructed",
                "partially_evaluated_shadow",
            }:
                continue
            rule_id = str(trace.get("rule_id") or "")
            traces_by_rule.setdefault(rule_id, []).append(trace)

    values: dict[str, dict] = {}
    missing: list[str] = []
    for spec in baseline_specs:
        rule_id = str(spec["rule_id"])
        variable = str(spec["selected_variable"])
        traces = traces_by_rule.get(rule_id, [])
        selected_value = None
        source_trace_sha256 = None
        available_variables: dict[str, float] = {}
        if variable.startswith("__"):
            selected_value = _composite_snapshot_signal(
                rule_id,
                traces_by_rule,
                side=side,
            )
        for trace in traces:
            outputs = trace.get("outputs")
            outputs = outputs if isinstance(outputs, dict) else {}
            flattened = flatten_numeric(outputs)
            available_variables.update(flattened)
            if variable.startswith("__"):
                candidate = selected_value
                if candidate is None:
                    candidate = _synthetic_signal(rule_id, outputs, side=side)
            else:
                candidate = flattened.get(variable)
            if candidate is not None:
                selected_value = float(candidate)
                source_trace_sha256 = trace.get("trace_sha256")
        if selected_value is None:
            missing.append(rule_id)
            continue
        values[rule_id] = {
            "value": selected_value,
            "variable": variable,
            "source": "exact_pretrade_trace",
            "trace_sha256": source_trace_sha256,
            "available_variables": {
                key: available_variables[key]
                for key in sorted(available_variables)
                if key == variable
            },
        }
    return values, sorted(set(missing))


def ensure_observational_learning_base_tables(db) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS observational_learning_cohorts (
            id BIGSERIAL PRIMARY KEY,
            cohort_key TEXT NOT NULL UNIQUE,
            contract_version TEXT NOT NULL,
            historical_cutoff_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('building', 'verified', 'sealed')),
            audit_version TEXT NOT NULL,
            audit_sha256 TEXT NOT NULL CHECK(audit_sha256 ~ '^[0-9a-f]{64}$'),
            rule_catalog_sha256 TEXT NOT NULL CHECK(rule_catalog_sha256 ~ '^[0-9a-f]{64}$'),
            source_dataset_sha256 TEXT NOT NULL CHECK(source_dataset_sha256 ~ '^[0-9a-f]{64}$'),
            compact_dataset_sha256 TEXT CHECK(
                compact_dataset_sha256 IS NULL
                OR compact_dataset_sha256 ~ '^[0-9a-f]{64}$'
            ),
            historical_case_count INTEGER NOT NULL DEFAULT 0 CHECK(historical_case_count >= 0),
            historical_episode_count INTEGER NOT NULL DEFAULT 0 CHECK(historical_episode_count >= 0),
            protocol_json TEXT NOT NULL CHECK(jsonb_typeof(protocol_json::jsonb) = 'object'),
            summary_json TEXT NOT NULL CHECK(jsonb_typeof(summary_json::jsonb) = 'object'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            verified_at TIMESTAMPTZ,
            CHECK(status = 'building' OR (compact_dataset_sha256 IS NOT NULL AND verified_at IS NOT NULL))
        );

        CREATE TABLE IF NOT EXISTS observational_rule_baselines (
            id BIGSERIAL PRIMARY KEY,
            cohort_id BIGINT NOT NULL REFERENCES observational_learning_cohorts(id) ON DELETE RESTRICT,
            rule_id TEXT NOT NULL,
            time_horizon TEXT NOT NULL CHECK(time_horizon IN ('intraday_short', 'intraday_wide', 'short_swing')),
            target TEXT NOT NULL CHECK(target IN ('directional', 'movement')),
            selected_variable TEXT NOT NULL,
            orientation TEXT NOT NULL CHECK(orientation IN ('direct', 'inverse')),
            lifecycle_status TEXT NOT NULL CHECK(lifecycle_status = 'observational'),
            probability_weight DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK(probability_weight = 0),
            formula_contract_json TEXT NOT NULL CHECK(jsonb_typeof(formula_contract_json::jsonb) = 'object'),
            formula_contract_sha256 TEXT NOT NULL CHECK(formula_contract_sha256 ~ '^[0-9a-f]{64}$'),
            historical_metrics_json TEXT NOT NULL CHECK(jsonb_typeof(historical_metrics_json::jsonb) = 'object'),
            continuation_json TEXT NOT NULL CHECK(jsonb_typeof(continuation_json::jsonb) = 'object'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(cohort_id, rule_id, time_horizon)
        );

        CREATE TABLE IF NOT EXISTS observational_learning_cases (
            id BIGSERIAL PRIMARY KEY,
            cohort_id BIGINT NOT NULL REFERENCES observational_learning_cohorts(id) ON DELETE RESTRICT,
            case_key TEXT NOT NULL UNIQUE CHECK(case_key ~ '^[0-9a-f]{64}$'),
            cohort_partition TEXT NOT NULL CHECK(cohort_partition IN ('historical', 'prospective')),
            source_kind TEXT NOT NULL,
            source_reference TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('long', 'short')),
            time_horizon TEXT NOT NULL CHECK(time_horizon IN ('intraday_short', 'intraday_wide', 'short_swing')),
            analysis_at TIMESTAMPTZ NOT NULL,
            evaluation_expires_at TIMESTAMPTZ NOT NULL,
            outcome_label TEXT NOT NULL CHECK(outcome_label IN (
                'tp_first_within_horizon',
                'sl_first_within_horizon',
                'neither_barrier_before_expiry'
            )),
            episode_key TEXT CHECK(episode_key IS NULL OR episode_key ~ '^[0-9a-f]{64}$'),
            episode_weight DOUBLE PRECISION CHECK(episode_weight IS NULL OR (episode_weight > 0 AND episode_weight <= 1)),
            probabilities_json TEXT NOT NULL CHECK(jsonb_typeof(probabilities_json::jsonb) = 'object'),
            signals_json TEXT NOT NULL CHECK(jsonb_typeof(signals_json::jsonb) = 'object'),
            signal_count INTEGER NOT NULL CHECK(signal_count >= 0),
            missing_rule_ids_json TEXT NOT NULL CHECK(jsonb_typeof(missing_rule_ids_json::jsonb) = 'array'),
            contract_version TEXT NOT NULL,
            source_identity_sha256 TEXT NOT NULL CHECK(source_identity_sha256 ~ '^[0-9a-f]{64}$'),
            payload_sha256 TEXT NOT NULL UNIQUE CHECK(payload_sha256 ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(
                (cohort_partition = 'historical' AND episode_key IS NOT NULL AND episode_weight IS NOT NULL)
                OR cohort_partition = 'prospective'
            )
        );

        CREATE INDEX IF NOT EXISTS idx_observational_cases_cohort_time
            ON observational_learning_cases(cohort_id, cohort_partition, analysis_at);
        CREATE INDEX IF NOT EXISTS idx_observational_cases_learning_slice
            ON observational_learning_cases(cohort_id, time_horizon, outcome_label, analysis_at);
        CREATE INDEX IF NOT EXISTS idx_observational_baselines_rule
            ON observational_rule_baselines(cohort_id, rule_id, time_horizon);

        ALTER TABLE observational_learning_cohorts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE observational_rule_baselines ENABLE ROW LEVEL SECURITY;
        ALTER TABLE observational_learning_cases ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE observational_learning_cohorts FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE observational_rule_baselines FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE observational_learning_cases FROM anon, authenticated;
        REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE observational_learning_cohorts FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE observational_rule_baselines FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE observational_learning_cases FROM service_role;
        GRANT SELECT, INSERT, UPDATE ON TABLE observational_learning_cohorts TO service_role;
        GRANT SELECT, INSERT ON TABLE observational_rule_baselines TO service_role;
        GRANT SELECT, INSERT ON TABLE observational_learning_cases TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE observational_learning_cohorts_id_seq TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE observational_rule_baselines_id_seq TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE observational_learning_cases_id_seq TO service_role;
        """
    )
    db.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_observational_learning_fact_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
            RAISE EXCEPTION 'observational_learning_fact_is_append_only';
        END;
        $$
        """
    )
    db.execute(
        """
        REVOKE ALL ON FUNCTION prevent_observational_learning_fact_mutation()
        FROM PUBLIC, anon, authenticated, service_role
        """
    )
    for table in (
        "observational_rule_baselines",
        "observational_learning_cases",
    ):
        trigger_name = f"{table}_append_only"
        exists = db.execute(
            """
            SELECT 1 FROM pg_trigger
            WHERE tgrelid = to_regclass(?)
              AND tgname = ?
              AND NOT tgisinternal
            """,
            (table, trigger_name),
        ).fetchone()
        if exists:
            continue
        db.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION prevent_observational_learning_fact_mutation()
            """
        )


def active_baseline_specs(db, cohort_id: int) -> list[dict]:
    return [
        dict(row)
        for row in db.execute(
            """
            SELECT rule_id, time_horizon, target, selected_variable,
                   orientation, formula_contract_sha256
            FROM observational_rule_baselines
            WHERE cohort_id = ?
            ORDER BY rule_id, time_horizon
            """,
            (int(cohort_id),),
        ).fetchall()
    ]


def _soft_auc(signals: list[float], positive_shares: list[float]) -> float | None:
    if len(signals) != len(positive_shares) or not signals:
        return None
    ordered = sorted(zip(signals, positive_shares), key=lambda item: item[0])
    total_positive = math.fsum(share for _, share in ordered)
    total_negative = math.fsum(1.0 - share for _, share in ordered)
    self_pairs = math.fsum(share * (1.0 - share) for _, share in ordered)
    denominator = total_positive * total_negative - self_pairs
    if denominator <= 0:
        return None
    numerator = 0.0
    lower_negative = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        shares = [item[1] for item in ordered[index:end]]
        group_positive = math.fsum(shares)
        group_negative = math.fsum(1.0 - share for share in shares)
        group_self = math.fsum(share * (1.0 - share) for share in shares)
        numerator += group_positive * lower_negative
        numerator += 0.5 * (group_positive * group_negative - group_self)
        lower_negative += group_negative
        index = end
    return numerator / denominator


def _compact_episode_rows(rows: Iterable[dict], target: str) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        episode_key = row.get("episode_key")
        if not episode_key:
            continue
        if target == "directional" and row["outcome_label"] == OUTCOME_CLASSES[2]:
            continue
        grouped.setdefault(str(episode_key), []).append(row)
    episodes = []
    for episode_key, members in grouped.items():
        positive = sum(
            (
                member["outcome_label"] != OUTCOME_CLASSES[2]
                if target == "movement"
                else member["outcome_label"] == OUTCOME_CLASSES[0]
            )
            for member in members
        )
        episodes.append(
            {
                "episode_key": episode_key,
                "signal": math.fsum(float(member["value"]) for member in members)
                / len(members),
                "positive_share": positive / len(members),
                "raw_cases": len(members),
            }
        )
    return sorted(episodes, key=lambda row: row["episode_key"])


def _compact_progress_metric(rows: list[dict], target: str, orientation: int) -> dict:
    episodes = _compact_episode_rows(rows, target)
    positive_mass = math.fsum(row["positive_share"] for row in episodes)
    negative_mass = len(episodes) - positive_mass
    return {
        "raw_cases": sum(row["raw_cases"] for row in episodes),
        "effective_episodes": len(episodes),
        "effective_positive_mass": positive_mass,
        "effective_negative_mass": negative_mass,
        "auc": _soft_auc(
            [orientation * row["signal"] for row in episodes],
            [row["positive_share"] for row in episodes],
        ),
    }


def observational_learning_progress(db) -> dict:
    """Evaluate the compact base alone; never reads legacy analysis history."""
    cohort = db.execute(
        """
        SELECT * FROM observational_learning_cohorts
        WHERE cohort_key = ? AND status = 'sealed'
        LIMIT 1
        """,
        (BASELINE_COHORT_KEY,),
    ).fetchone()
    if cohort is None:
        return {"status": "baseline_missing", "rules": []}
    cohort = dict(cohort)
    baselines = [
        dict(row)
        for row in db.execute(
            """
            SELECT rule_id, time_horizon, target, orientation,
                   probability_weight, historical_metrics_json
            FROM observational_rule_baselines
            WHERE cohort_id = ?
            ORDER BY rule_id, time_horizon
            """,
            (int(cohort["id"]),),
        ).fetchall()
    ]
    cases = [
        dict(row)
        for row in db.execute(
            """
            SELECT case_key, cohort_partition, time_horizon, outcome_label,
                   episode_key, signals_json
            FROM observational_learning_cases
            WHERE cohort_id = ?
            ORDER BY analysis_at, id
            """,
            (int(cohort["id"]),),
        ).fetchall()
    ]
    progress = []
    for baseline in baselines:
        signal_rows = []
        missing_episode_keys = 0
        for case in cases:
            if case["time_horizon"] != baseline["time_horizon"]:
                continue
            signals = parse_json_object(case.get("signals_json"))
            signal = signals.get(baseline["rule_id"])
            if not isinstance(signal, dict) or finite(signal.get("value")) is None:
                continue
            if not case.get("episode_key"):
                missing_episode_keys += 1
                continue
            signal_rows.append(
                {
                    "cohort_partition": case["cohort_partition"],
                    "episode_key": (
                        f"{case['cohort_partition']}:{case['episode_key']}"
                    ),
                    "outcome_label": case["outcome_label"],
                    "value": float(signal["value"]),
                }
            )
        orientation = 1 if baseline["orientation"] == "direct" else -1
        historical_rows = [
            row for row in signal_rows if row["cohort_partition"] == "historical"
        ]
        prospective_rows = [
            row for row in signal_rows if row["cohort_partition"] == "prospective"
        ]
        historical = _compact_progress_metric(
            historical_rows, baseline["target"], orientation
        )
        prospective = _compact_progress_metric(
            prospective_rows, baseline["target"], orientation
        )
        combined = _compact_progress_metric(
            signal_rows, baseline["target"], orientation
        )
        reference = parse_json_object(baseline["historical_metrics_json"])
        progress.append(
            {
                "rule_id": baseline["rule_id"],
                "time_horizon": baseline["time_horizon"],
                "target": baseline["target"],
                "probability_weight": float(baseline["probability_weight"]),
                "historical": historical,
                "prospective": prospective,
                "combined": combined,
                "historical_reference_matches": (
                    historical["raw_cases"] == int(reference.get("raw_cases") or 0)
                    and historical["effective_episodes"]
                    == int(reference.get("effective_episodes") or 0)
                    and (
                        historical["auc"] is None
                        and reference.get("full_auc") is None
                        or historical["auc"] is not None
                        and reference.get("full_auc") is not None
                        and abs(
                            historical["auc"] - float(reference["full_auc"])
                        )
                        <= 1e-12
                    )
                ),
                "missing_episode_key_cases": missing_episode_keys,
                "decision": "continue_observing_no_probability_effect",
            }
        )
    return {
        "status": "sealed",
        "cohort_id": int(cohort["id"]),
        "contract_version": cohort["contract_version"],
        "historical_cutoff_at": str(cohort["historical_cutoff_at"]),
        "compact_dataset_sha256": cohort["compact_dataset_sha256"],
        "historical_cases": int(cohort["historical_case_count"]),
        "historical_episodes": int(cohort["historical_episode_count"]),
        "rules": progress,
        "automatic_probability_changes": False,
        "legacy_history_read": False,
    }


def persist_closed_observational_case(db, operation_id: int) -> bool:
    """Append one compact prospective fact after a normal learning evaluation."""
    cohort = db.execute(
        """
        SELECT id, historical_cutoff_at
        FROM observational_learning_cohorts
        WHERE cohort_key = ? AND status = 'sealed'
        LIMIT 1
        """,
        (BASELINE_COHORT_KEY,),
    ).fetchone()
    if cohort is None:
        return False
    row = db.execute(
        """
        SELECT
            o.id AS operation_id, o.symbol, o.side, o.time_horizon,
            r.id AS recommendation_id, r.snapshot_json,
            le.plan_result, le.tp_probability, le.sl_probability,
            le.range_probability
        FROM operations o
        JOIN learning_evaluations le ON le.operation_id = o.id
        JOIN recommendations r ON r.id = (
            SELECT r2.id FROM recommendations r2
            WHERE r2.operation_id = o.id
              AND r2.analysis_type = 'pre_trade'
            ORDER BY r2.created_at DESC, r2.id DESC LIMIT 1
        )
        WHERE o.id = ? AND o.status = 'CLOSED'
        LIMIT 1
        """,
        (int(operation_id),),
    ).fetchone()
    if row is None:
        return False
    row = dict(row)
    outcome = PLAN_RESULT_TO_OUTCOME.get(str(row.get("plan_result") or ""))
    if outcome is None:
        return False
    snapshot = parse_json_object(row.get("snapshot_json"))
    analysis_at = snapshot.get("analysis_at")
    expires_at = snapshot.get("evaluation_expires_at")
    if not analysis_at or not expires_at:
        return False
    parsed_analysis = datetime.fromisoformat(str(analysis_at).replace("Z", "+00:00"))
    cutoff = cohort["historical_cutoff_at"]
    if isinstance(cutoff, str):
        cutoff = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if parsed_analysis.tzinfo is None:
        parsed_analysis = parsed_analysis.replace(tzinfo=timezone.utc)
    if parsed_analysis <= cutoff:
        return False
    specs = [
        spec
        for spec in active_baseline_specs(db, int(cohort["id"]))
        if spec["time_horizon"] == row["time_horizon"]
    ]
    signals, missing = current_snapshot_rule_values(
        snapshot,
        side=str(row["side"]),
        time_horizon=str(row["time_horizon"]),
        baseline_specs=specs,
    )
    probabilities = {
        "tp_first_within_horizon": finite(row.get("tp_probability")),
        "sl_first_within_horizon": finite(row.get("sl_probability")),
        "neither_barrier_before_expiry": finite(row.get("range_probability")),
    }
    probabilities = {
        key: value for key, value in probabilities.items() if value is not None
    }
    identity = {
        "source_kind": "closed_operation",
        "operation_id": int(row["operation_id"]),
        "recommendation_id": int(row["recommendation_id"]),
        "analysis_at": str(analysis_at),
        "outcome_label": outcome,
        "contract_version": BASE_CONTRACT_VERSION,
    }
    source_identity_sha = payload_sha256(identity)
    episode_key = prospective_episode_key(
        symbol=str(row["symbol"]),
        time_horizon=str(row["time_horizon"]),
        analysis_at=parsed_analysis,
    )
    payload = {
        **identity,
        "symbol": str(row["symbol"]),
        "side": str(row["side"]),
        "time_horizon": str(row["time_horizon"]),
        "evaluation_expires_at": str(expires_at),
        "probabilities": probabilities,
        "signals": signals,
        "missing_rule_ids": missing,
        "episode_key": episode_key,
    }
    payload_sha = payload_sha256(payload)
    cursor = db.execute(
        """
        INSERT INTO observational_learning_cases (
            cohort_id, case_key, cohort_partition, source_kind,
            source_reference, symbol, side, time_horizon, analysis_at,
            evaluation_expires_at, outcome_label, episode_key, episode_weight,
            probabilities_json, signals_json, signal_count,
            missing_rule_ids_json, contract_version, source_identity_sha256,
            payload_sha256
        )
        VALUES (?, ?, 'prospective', 'closed_operation', ?, ?, ?, ?, ?, ?, ?,
                ?, NULL, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (case_key) DO NOTHING
        """,
        (
            int(cohort["id"]),
            source_identity_sha,
            f"operation:{int(row['operation_id'])}",
            str(row["symbol"]),
            str(row["side"]),
            str(row["time_horizon"]),
            str(analysis_at),
            str(expires_at),
            outcome,
            episode_key,
            canonical_json(probabilities),
            canonical_json(signals),
            len(signals),
            canonical_json(missing),
            BASE_CONTRACT_VERSION,
            source_identity_sha,
            payload_sha,
        ),
    )
    return cursor.rowcount == 1


def backfill_prospective_observational_cases(db) -> dict:
    """Bridge closures after the frozen cutoff; idempotency prevents doubles."""
    rows = db.execute(
        """
        SELECT o.id
        FROM operations o
        JOIN learning_evaluations le ON le.operation_id = o.id
        JOIN recommendations r ON r.id = (
            SELECT r2.id FROM recommendations r2
            WHERE r2.operation_id = o.id
              AND r2.analysis_type = 'pre_trade'
            ORDER BY r2.created_at DESC, r2.id DESC LIMIT 1
        )
        WHERE o.status = 'CLOSED'
          AND (r.snapshot_json::jsonb ->> 'analysis_at')::timestamptz > ?
        ORDER BY o.id
        """,
        (HISTORICAL_CUTOFF_AT,),
    ).fetchall()
    inserted = 0
    for row in rows:
        inserted += int(persist_closed_observational_case(db, int(row["id"])))
    return {
        "eligible_operations": len(rows),
        "persist_calls_completed": inserted,
    }


__all__ = (
    "BASELINE_COHORT_KEY",
    "BASE_CONTRACT_VERSION",
    "FROZEN_SIGNAL_VARIABLES",
    "HISTORICAL_CUTOFF_AT",
    "MOVEMENT_RULE_IDS",
    "OUTCOME_CLASSES",
    "PROBABILITY_WEIGHT",
    "PROSPECTIVE_EPISODE_CONTRACT",
    "RETAINED_RULE_HORIZONS",
    "active_baseline_specs",
    "backfill_prospective_observational_cases",
    "canonical_json",
    "current_snapshot_rule_values",
    "ensure_observational_learning_base_tables",
    "payload_sha256",
    "persist_closed_observational_case",
    "prospective_episode_key",
    "observational_learning_progress",
)
