from __future__ import annotations

import json
import math
import os
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import m8_evaluation as m8
from audit_counterfactual_rule_evidence import _iter_rule_traces
from audit_full_rule_library_closed_operations import (
    ACTIVE_PREDICTIVE_RULE_IDS,
    CandleArchive,
    STATE_RECONSTRUCTED,
    STATE_RECORDED,
    build_case,
    enrich_missing_outcomes,
    flatten_numeric,
    load_rows as load_closed_rows,
    normalized_row,
    synthetic_rule_signals,
    variable_eligibility,
)
from counterfactual_episode_grouping import build_episode_grouping
from counterfactual_learning import (
    build_counterfactual_payload,
    normalize_unlinked_recommendation,
)
from db import close_pool, connect
from predictive_rule_library import load_rule_library
from run_counterfactual_learning import evaluate_by_market_group


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
DEFAULT_OUTPUT = AUDIT_DIR / "auditoria_final_utilidad_reglas_v0_1.json"
DEFAULT_REPORT = AUDIT_DIR / "2026-08-12_auditoria_final_utilidad_reglas.md"
BASELINE_AUDIT = (
    AUDIT_DIR / "auditoria_integral_biblioteca_operaciones_cerradas_v0_1.json"
)
INCREMENTAL_AUDIT = AUDIT_DIR / "auditoria_incremental_post_baseline_v0_1.json"

AUDIT_VERSION = "final-rule-utility-audit-v0.1"
CLASSES = m8.CLASSES
MIN_EFFECTIVE_EPISODES = 50
MIN_EFFECTIVE_CLASS_MASS = 10.0
MIN_LATEST_EPISODES = 15
MIN_LATEST_CLASS_MASS = 3.0
BOOTSTRAP_SAMPLES = 2000
PERMUTATION_SAMPLES = 2000
FDR_THRESHOLD = 0.10
RANDOM_SEED = 20260812

EXACT_STATES = {STATE_RECORDED, STATE_RECONSTRUCTED}
MOVEMENT_RULE_IDS = {
    "M4-RULE-VOLATILITY-RANK-001",
    "M4-RULE-OPEN-INTEREST-CHANGE-001",
    "LIB-CAND-RELATIVE-VOLUME-001",
    "LIB-CAND-COMPRESSION-001",
}

SQL_STORED_EXACT = """
WITH latest_exact AS (
    SELECT DISTINCT ON (candidate.recommendation_id) candidate.*
    FROM recommendation_counterfactual_evaluations candidate
    WHERE candidate.contract_quality = 'exact'
      AND candidate.formal_learning_eligible
    ORDER BY candidate.recommendation_id, candidate.created_at DESC,
             candidate.id DESC
)
SELECT
    e.id AS evaluation_id,
    e.recommendation_id,
    e.user_id,
    e.source_engine_version AS engine_version,
    e.source_scoring_version AS scoring_version,
    e.symbol,
    e.side,
    e.time_horizon,
    e.analysis_at,
    e.data_cutoff_at,
    e.evaluation_expires_at,
    e.horizon_seconds,
    e.entry,
    e.take_profit,
    e.stop_loss,
    e.tp_probability,
    e.sl_probability,
    e.range_probability,
    e.evaluation_status,
    e.exclusion_code,
    e.outcome_status,
    e.outcome_label,
    e.first_touch_at,
    e.coverage_ratio,
    e.market_sha256,
    e.result_sha256,
    r.operation_id,
    CASE
        WHEN e.source_engine_version = 'TP-SL-PROBABILITY-ENGINE-v0.6-stable-global'
        THEN r.snapshot_json
        ELSE '{}'
    END AS snapshot_json,
    r.created_at
FROM latest_exact e
JOIN recommendations r ON r.id = e.recommendation_id
WHERE r.operation_id IS NULL
ORDER BY e.analysis_at, e.id
"""

SQL_UNLINKED = """
SELECT
    r.id AS recommendation_id,
    r.operation_id,
    r.user_id,
    r.symbol,
    r.side,
    r.time_horizon,
    r.tp_probability,
    r.sl_probability,
    r.range_probability,
    r.engine_version,
    r.scoring_version,
    r.snapshot_json,
    r.created_at
FROM recommendations r
WHERE r.operation_id IS NULL
  AND r.engine_version = 'TP-SL-PROBABILITY-ENGINE-v0.6-stable-global'
ORDER BY r.created_at, r.id
"""

COMBINATIONS = {
    "level_entry_quality": {
        "target": "directional",
        "rules": [
            "LIB-CAND-FIBONACCI-DISTANCE-001",
            "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
            "LIB-CAND-PULLBACK-CONTEXT-001",
        ],
        "reason": "confluencia de nivel, estructura y contexto de retroceso",
    },
    "flow_confirmation": {
        "target": "directional",
        "rules": [
            "LIB-CAND-RELATIVE-VOLUME-001",
            "LIB-CAND-CVD-SLOPE-001",
            "LIB-CAND-ABSORPTION-001",
            "LIB-CAND-ORDERBOOK-IMBALANCE-001",
        ],
        "reason": "confirmacion conjunta de volumen, flujo y libro visible",
    },
    "volatility_resolution": {
        "target": "movement",
        "rules": [
            "M4-RULE-VOLATILITY-RANK-001",
            "LIB-CAND-ATR-EXTENSION-001",
            "LIB-CAND-COMPRESSION-001",
        ],
        "reason": "regimen de volatilidad, extension y compresion",
    },
    "derivatives_context": {
        "target": "directional",
        "rules": [
            "M4-RULE-FUNDING-STATE-001",
            "LIB-CAND-FUNDING-PERCENTILE-001",
            "M4-RULE-OPEN-INTEREST-CHANGE-001",
            "M4-RULE-PRICE-OI-STATE-001",
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            "LIB-CAND-CROWDING-PERCENTILE-001",
        ],
        "reason": "posicionamiento y derivados sin atribucion aislada falsa",
    },
    "liquidation_path": {
        "target": "directional",
        "rules": [
            "LIB-CAND-LIQUIDATION-ZONE-001",
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-MTF-HIERARCHY-001",
        ],
        "reason": "zona de liquidacion confirmada por trayectoria y contexto MTF",
    },
}


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _normalized_probabilities(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    result = {name: _finite(value.get(name)) for name in CLASSES}
    if any(number is None or number < 0 for number in result.values()):
        return None
    total = math.fsum(result.values())
    if total <= 0:
        return None
    return {name: float(result[name]) / total for name in CLASSES}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_database_sources() -> tuple[list[dict], list[dict]]:
    try:
        with connect() as db:
            stored = [dict(row) for row in db.execute(SQL_STORED_EXACT).fetchall()]
            unlinked = [dict(row) for row in db.execute(SQL_UNLINKED).fetchall()]
        return stored, unlinked
    finally:
        close_pool()


def use_session_pool_for_long_audit() -> None:
    """Avoid transaction-pooler stalls during the long read-only audit."""
    for key in ("SUPABASE_DATABASE_URL", "DATABASE_URL"):
        value = os.environ.get(key, "")
        if "pooler.supabase.com:6543/" in value:
            os.environ[key] = value.replace(
                "pooler.supabase.com:6543/",
                "pooler.supabase.com:5432/",
                1,
            )


def load_known_closed_outcomes() -> dict[int, dict]:
    outcomes: dict[int, dict] = {}
    for path in (BASELINE_AUDIT, INCREMENTAL_AUDIT):
        if not path.exists():
            continue
        for case in _read_json(path).get("cases", []):
            outcome = dict(case.get("outcome") or {})
            if outcome.get("status") != "resolved" or outcome.get("label") not in CLASSES:
                continue
            operation_id = int(case["operation_id"])
            previous = outcomes.get(operation_id)
            if previous and previous.get("label") != outcome.get("label"):
                raise ValueError(f"historical_outcome_conflict:{operation_id}")
            outcomes[operation_id] = {**outcome, "source": f"existing_audit:{path.name}"}
    return outcomes


def normalize_counterfactual_source(raw: dict) -> dict:
    recommendation_id = int(raw["recommendation_id"])
    normalized = normalized_row(
        {
            "operation_id": -recommendation_id,
            "recommendation_id": recommendation_id,
            "status": "COUNTERFACTUAL_CLOSED",
            "entry_type": "market",
            "started_at": raw.get("analysis_at"),
            "operation_created_at": raw.get("analysis_at"),
            "closed_at": raw.get("evaluation_expires_at"),
            "close_reason": "counterfactual_first_passage",
            "entry": raw.get("entry"),
            "stop_loss": raw.get("stop_loss"),
            "take_profit": raw.get("take_profit"),
            "margin": 100.0,
            "leverage": 1.0,
            "operation_symbol": raw.get("symbol"),
            "operation_side": raw.get("side"),
            "operation_time_horizon": raw.get("time_horizon"),
            "analysis_at": raw.get("analysis_at"),
            "symbol": raw.get("symbol"),
            "side": raw.get("side"),
            "time_horizon": raw.get("time_horizon"),
            "engine_version": raw.get("engine_version"),
            "snapshot_json": raw.get("snapshot_json"),
            "analysis_json": None,
            "tp_probability": raw.get("tp_probability"),
            "sl_probability": raw.get("sl_probability"),
            "range_probability": raw.get("range_probability"),
            "source_kind": "exact_unlinked_counterfactual",
            "source_evaluation_id": raw.get("evaluation_id"),
        }
    )
    expected_expiry = m8.parse_utc(raw.get("evaluation_expires_at"))
    calculated_expiry = m8.parse_utc(normalized.get("expiry_at"))
    if expected_expiry is None or calculated_expiry is None:
        raise ValueError(f"counterfactual_expiry_invalid:{recommendation_id}")
    if abs((expected_expiry - calculated_expiry).total_seconds()) > 1:
        raise ValueError(f"counterfactual_expiry_mismatch:{recommendation_id}")
    return normalized


def stored_counterfactual_outcome(raw: dict) -> dict:
    label = raw.get("outcome_label")
    formally_resolved = (
        raw.get("evaluation_status") == "evaluated" and label in CLASSES
    )
    return {
        "status": "resolved" if formally_resolved else "missing",
        "recorded_status": str(raw.get("outcome_status") or "missing"),
        "label": label,
        "first_touch_at": raw.get("first_touch_at"),
        "coverage_ratio": raw.get("coverage_ratio"),
        "market_sha256": raw.get("market_sha256"),
        "source": "stored_exact_unlinked_counterfactual",
    }


def _payload_as_source(payload: dict, raw: dict) -> dict:
    return {
        **payload,
        "evaluation_id": None,
        "engine_version": payload.get("source_engine_version"),
        "scoring_version": payload.get("source_scoring_version"),
        "snapshot_json": raw.get("snapshot_json"),
        "analysis_json": None,
    }


def prepare_exact_counterfactuals(
    stored: list[dict],
    unlinked: list[dict],
    *,
    captured_at: datetime,
) -> tuple[list[dict], dict]:
    stored_by_id = {int(row["recommendation_id"]): row for row in stored}
    rejection_codes: Counter = Counter()
    accepted = []
    raw_by_id = {int(row["recommendation_id"]): row for row in unlinked}
    for raw in unlinked:
        record, rejection = normalize_unlinked_recommendation(raw, captured_at=captured_at)
        if rejection:
            rejection_codes[rejection] += 1
        elif record:
            accepted.append(record)

    missing = [
        record
        for record in accepted
        if int(record["recommendation_id"]) not in stored_by_id
    ]
    completed, fetch_errors = evaluate_by_market_group(missing, captured_at=captured_at)
    fresh_payloads = [build_counterfactual_payload(record) for record in completed]
    fresh_sources = [
        _payload_as_source(payload, raw_by_id[int(payload["recommendation_id"])])
        for payload in fresh_payloads
    ]
    all_sources = [*stored, *fresh_sources]
    evaluated = [
        row
        for row in all_sources
        if row.get("evaluation_status") == "evaluated"
        and row.get("outcome_label") in CLASSES
    ]
    inventory = {
        "current_engine_unlinked_candidates_scanned": len(unlinked),
        "stored_exact_contracts": len(stored),
        "stored_exact_evaluated": sum(
            row.get("evaluation_status") == "evaluated" for row in stored
        ),
        "exact_contracts_matured_now": len(accepted),
        "new_exact_contracts_evaluated_locally": len(fresh_payloads),
        "new_exact_contracts_persisted": 0,
        "formal_exact_evaluated_total": len(evaluated),
        "rejection_codes": dict(sorted(rejection_codes.items())),
        "fetch_errors": fetch_errors,
    }
    return evaluated, inventory


def replay_consolidated_cases(
    closed_rows: list[dict],
    counterfactual_sources: list[dict],
) -> tuple[list[dict], dict]:
    known_outcomes = load_known_closed_outcomes()
    enrich_missing_outcomes(closed_rows, known_outcomes)
    normalized_counterfactuals = [
        normalize_counterfactual_source(row) for row in counterfactual_sources
    ]
    counterfactual_outcomes = {
        -int(row["recommendation_id"]): stored_counterfactual_outcome(row)
        for row in counterfactual_sources
    }
    all_rows = [*closed_rows, *normalized_counterfactuals]
    archive = CandleArchive.load()
    archive.ensure(all_rows)
    library = load_rule_library()
    catalog_rules = {rule["rule_id"]: rule for rule in library["rules"]}
    cases = []
    for index, row in enumerate(all_rows, start=1):
        outcome = (
            known_outcomes.get(int(row["operation_id"]))
            if int(row["operation_id"]) > 0
            else counterfactual_outcomes.get(int(row["operation_id"]))
        )
        case = build_case(row, catalog_rules, archive, outcome)
        case.update(
            {
                "case_id": index,
                "source_kind": row.get("source_kind") or "closed_operation",
                "source_id": (
                    int(row["operation_id"])
                    if int(row["operation_id"]) > 0
                    else int(row["recommendation_id"])
                ),
                "expiry_at": row.get("expiry_at"),
                "horizon_seconds": row.get("horizon_seconds"),
            }
        )
        cases.append(case)
    inventory = {
        "closed_operations_loaded": len(closed_rows),
        "closed_market_operations": sum(
            row.get("entry_type") == "market" for row in closed_rows
        ),
        "closed_pending_operations_separated": sum(
            row.get("entry_type") != "market" for row in closed_rows
        ),
        "closed_outcomes_resolved": sum(
            (known_outcomes.get(int(row["operation_id"])) or {}).get("label")
            in CLASSES
            for row in closed_rows
        ),
        "counterfactual_cases_loaded": len(normalized_counterfactuals),
        "combined_cases": len(cases),
    }
    return cases, inventory


def attach_episode_memberships(cases: list[dict]) -> tuple[list[dict], dict]:
    formal = [
        case
        for case in cases
        if case["entry_type"] == "market"
        and (case.get("outcome") or {}).get("status") == "resolved"
        and (case.get("outcome") or {}).get("label") in CLASSES
        and m8.parse_utc(case.get("analysis_at")) is not None
        and m8.parse_utc(case.get("expiry_at")) is not None
    ]
    source_rows = []
    for case in formal:
        identity = {
            "source_kind": case["source_kind"],
            "source_id": case["source_id"],
            "recommendation_id": case["recommendation_id"],
            "analysis_at": case["analysis_at"],
            "expiry_at": case["expiry_at"],
            "outcome": case["outcome"]["label"],
        }
        source_rows.append(
            {
                "id": int(case["case_id"]),
                "symbol": case["symbol"],
                "time_horizon": case["time_horizon"],
                "evaluation_status": "evaluated",
                "contract_quality": "exact",
                "formal_learning_eligible": True,
                "analysis_at": case["analysis_at"],
                "evaluation_expires_at": case["expiry_at"],
                "result_sha256": m8.payload_sha256(identity),
            }
        )
    run, memberships = build_episode_grouping(source_rows)
    membership_by_id = {int(row["evaluation_id"]): row for row in memberships}
    attached = []
    for case in cases:
        membership = membership_by_id.get(int(case["case_id"]))
        if membership:
            case = {
                **case,
                "episode_key": membership["formal_horizon_episode_key"],
                "episode_weight": membership["formal_horizon_weight"],
                "calendar_block_utc": membership["calendar_block_utc"],
            }
        else:
            case = {
                **case,
                "episode_key": None,
                "episode_weight": 0.0,
                "calendar_block_utc": None,
            }
        attached.append(case)
    summary = json.loads(run["summary_json"])
    return attached, {
        "grouping_version": run["grouping_version"],
        "source_dataset_sha256": run["source_dataset_sha256"],
        "formal_cases": len(formal),
        "effective_horizon_episodes": summary["formal_effective_horizon_episodes"],
        "calendar_blocks_utc": summary["formal_calendar_blocks_utc"],
        "by_horizon": summary["by_horizon"],
        "method": summary["method"],
    }


def fast_soft_auc(signals: list[float], positive_shares: list[float]) -> float | None:
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


def _episode_signal_rows(rows: Iterable[dict], target: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not row.get("episode_key"):
            continue
        if target == "directional" and row["outcome_label"] == CLASSES[2]:
            continue
        grouped[str(row["episode_key"])].append(row)
    result = []
    for episode_key, members in grouped.items():
        positive = sum(
            (
                row["outcome_label"] != CLASSES[2]
                if target == "movement"
                else row["outcome_label"] == CLASSES[0]
            )
            for row in members
        )
        result.append(
            {
                "episode_key": episode_key,
                "analysis_at": min(m8.parse_utc(row["analysis_at"]) for row in members),
                "signal": math.fsum(float(row["value"]) for row in members) / len(members),
                "positive_share": positive / len(members),
                "raw_cases": len(members),
            }
        )
    return sorted(result, key=lambda row: (row["analysis_at"], row["episode_key"]))


def _class_mass(episodes: list[dict]) -> tuple[float, float]:
    positive = math.fsum(row["positive_share"] for row in episodes)
    return positive, len(episodes) - positive


def _percentile_interval(values: list[float]) -> list[float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return [
        ordered[int(0.025 * (len(ordered) - 1))],
        ordered[int(0.975 * (len(ordered) - 1))],
    ]


def _association_inference(
    episodes: list[dict],
    *,
    orientation: int,
    seed: int,
) -> dict:
    signals = [orientation * float(row["signal"]) for row in episodes]
    shares = [float(row["positive_share"]) for row in episodes]
    auc = fast_soft_auc(signals, shares) if len(set(signals)) > 1 else None
    result = {
        "episodes": len(episodes),
        "positive_mass": _class_mass(episodes)[0],
        "negative_mass": _class_mass(episodes)[1],
        "auc": auc,
        "bootstrap_95ci": None,
        "permutation_p": None,
        "fdr_bh": None,
    }
    if auc is None or len(episodes) < MIN_LATEST_EPISODES:
        return result
    positive, negative = _class_mass(episodes)
    if positive < MIN_LATEST_CLASS_MASS or negative < MIN_LATEST_CLASS_MASS:
        return result
    rng = random.Random(seed)
    indices = list(range(len(episodes)))
    bootstrap = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sampled = [rng.choice(indices) for _ in indices]
        estimate = fast_soft_auc(
            [signals[index] for index in sampled],
            [shares[index] for index in sampled],
        )
        if estimate is not None:
            bootstrap.append(estimate)
    extreme = 0
    observed_distance = abs(auc - 0.5)
    shuffled = list(shares)
    for _ in range(PERMUTATION_SAMPLES):
        rng.shuffle(shuffled)
        estimate = fast_soft_auc(signals, shuffled)
        if estimate is not None and abs(estimate - 0.5) >= observed_distance:
            extreme += 1
    result.update(
        {
            "bootstrap_95ci": _percentile_interval(bootstrap),
            "permutation_p": (extreme + 1) / (PERMUTATION_SAMPLES + 1),
        }
    )
    return result


def _bh_adjust(items: list[dict], p_key: str = "permutation_p") -> None:
    eligible = [item for item in items if item.get(p_key) is not None]
    ordered = sorted(eligible, key=lambda item: item[p_key])
    running = 1.0
    for index in range(len(ordered) - 1, -1, -1):
        rank = index + 1
        adjusted = min(running, ordered[index][p_key] * len(ordered) / rank)
        ordered[index]["fdr_bh"] = adjusted
        running = adjusted


def horizon_cutoffs(cases: list[dict]) -> dict[str, datetime | None]:
    cutoffs = {}
    for horizon in m8.HORIZON_SECONDS:
        by_episode: dict[str, datetime] = {}
        for case in cases:
            if case.get("time_horizon") != horizon or not case.get("episode_key"):
                continue
            analysis_at = m8.parse_utc(case.get("analysis_at"))
            key = str(case["episode_key"])
            if analysis_at is not None and (
                key not in by_episode or analysis_at < by_episode[key]
            ):
                by_episode[key] = analysis_at
        ordered = sorted(by_episode.values())
        if len(ordered) < 2:
            cutoffs[horizon] = ordered[0] if ordered else None
            continue
        split = min(len(ordered) - 1, max(1, int(len(ordered) * 0.7)))
        cutoffs[horizon] = ordered[split - 1]
    return cutoffs


def extract_rule_variables(
    cases: list[dict],
    library_rules: dict[str, dict],
) -> tuple[list[dict], dict]:
    rows = []
    coverage: dict[str, dict] = {}
    for rule_id in library_rules:
        coverage[rule_id] = {
            "exact_cases": 0,
            "exact_cases_by_horizon": Counter(),
            "state_counts": Counter(),
            "state_counts_by_horizon": defaultdict(Counter),
        }
    for case in cases:
        horizon = case["time_horizon"]
        label = (case.get("outcome") or {}).get("label")
        episode_key = case.get("episode_key")
        synthetic = synthetic_rule_signals(case)
        for combined, value in synthetic.items():
            rule_id, variable = combined.split(".", 1)
            if rule_id in library_rules and episode_key and label in CLASSES:
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "rule_id": rule_id,
                        "variable": variable,
                        "time_horizon": horizon,
                        "analysis_at": case["analysis_at"],
                        "episode_key": episode_key,
                        "outcome_label": label,
                        "value": float(value),
                        "source": "current_formula_signal",
                    }
                )
        for rule_id, item in case["rules"].items():
            state = item.get("state")
            coverage[rule_id]["state_counts"][state] += 1
            coverage[rule_id]["state_counts_by_horizon"][horizon][state] += 1
            if state not in EXACT_STATES:
                continue
            coverage[rule_id]["exact_cases"] += 1
            coverage[rule_id]["exact_cases_by_horizon"][horizon] += 1
            if not episode_key or label not in CLASSES:
                continue
            for variable, value in flatten_numeric(item.get("outputs") or {}).items():
                eligible, _ = variable_eligibility(variable, library_rules[rule_id])
                if not eligible:
                    continue
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "rule_id": rule_id,
                        "variable": variable,
                        "time_horizon": horizon,
                        "analysis_at": case["analysis_at"],
                        "episode_key": episode_key,
                        "outcome_label": label,
                        "value": float(value),
                        "source": "exact_pretrade_trace",
                    }
                )
    public_coverage = {}
    for rule_id, item in coverage.items():
        public_coverage[rule_id] = {
            "exact_cases": item["exact_cases"],
            "exact_cases_by_horizon": dict(item["exact_cases_by_horizon"]),
            "state_counts": dict(item["state_counts"]),
            "state_counts_by_horizon": {
                horizon: dict(counts)
                for horizon, counts in item["state_counts_by_horizon"].items()
            },
        }
    return rows, public_coverage


def select_and_evaluate_rule_hypotheses(
    variable_rows: list[dict],
    cutoffs: dict[str, datetime | None],
) -> tuple[list[dict], dict[tuple[str, str], dict]]:
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in variable_rows:
        grouped[(row["rule_id"], row["time_horizon"], row["variable"])].append(row)
    candidates: dict[tuple[str, str], list[dict]] = defaultdict(list)
    episode_cache: dict[tuple[str, str, str], list[dict]] = {}
    for key, rows in grouped.items():
        rule_id, horizon, variable = key
        target = "movement" if rule_id in MOVEMENT_RULE_IDS else "directional"
        episodes = _episode_signal_rows(rows, target)
        episode_cache[key] = episodes
        cutoff = cutoffs.get(horizon)
        early = [row for row in episodes if cutoff is not None and row["analysis_at"] <= cutoff]
        if len(early) < 10 or len(set(row["signal"] for row in early)) < 2:
            continue
        early_auc = fast_soft_auc(
            [row["signal"] for row in early],
            [row["positive_share"] for row in early],
        )
        if early_auc is None:
            continue
        candidates[(rule_id, horizon)].append(
            {
                "variable": variable,
                "source": rows[0]["source"],
                "target": target,
                "early_raw_auc": early_auc,
                "orientation": 1 if early_auc >= 0.5 else -1,
                "training_separation": abs(early_auc - 0.5),
                "early_episodes": len(early),
                "full_episodes": len(episodes),
            }
        )

    results = []
    selected_specs: dict[tuple[str, str], dict] = {}
    for index, ((rule_id, horizon), members) in enumerate(sorted(candidates.items())):
        selected = max(
            members,
            key=lambda item: (
                item["training_separation"],
                item["full_episodes"],
                item["variable"],
            ),
        )
        episodes = episode_cache[(rule_id, horizon, selected["variable"])]
        cutoff = cutoffs[horizon]
        early = [row for row in episodes if row["analysis_at"] <= cutoff]
        latest = [row for row in episodes if row["analysis_at"] > cutoff]
        orientation = selected["orientation"]
        full_auc = fast_soft_auc(
            [orientation * row["signal"] for row in episodes],
            [row["positive_share"] for row in episodes],
        )
        early_auc = fast_soft_auc(
            [orientation * row["signal"] for row in early],
            [row["positive_share"] for row in early],
        )
        latest_inference = _association_inference(
            latest,
            orientation=orientation,
            seed=RANDOM_SEED + index * 31,
        )
        positive, negative = _class_mass(episodes)
        formal_gate = (
            len(episodes) >= MIN_EFFECTIVE_EPISODES
            and positive >= MIN_EFFECTIVE_CLASS_MASS
            and negative >= MIN_EFFECTIVE_CLASS_MASS
        )
        result = {
            "rule_id": rule_id,
            "time_horizon": horizon,
            "target": selected["target"],
            "selected_variable": selected["variable"],
            "variable_source": selected["source"],
            "selection_method": "maximum_early_70_percent_separation_then_frozen",
            "orientation": "direct" if orientation == 1 else "inverse",
            "candidate_variables_considered": len(members),
            "raw_cases": sum(row["raw_cases"] for row in episodes),
            "effective_episodes": len(episodes),
            "effective_positive_mass": positive,
            "effective_negative_mass": negative,
            "early_70_percent_auc": early_auc,
            "full_auc": full_auc,
            "latest_30_percent": latest_inference,
            "permutation_p": latest_inference["permutation_p"],
            "fdr_bh": None,
            "formal_gate": formal_gate,
            "additional_effective_episodes_needed": max(
                0, MIN_EFFECTIVE_EPISODES - len(episodes)
            ),
            "evidence_status": "pending_fdr" if formal_gate else "insufficient_effective_evidence",
        }
        results.append(result)
        selected_specs[(rule_id, horizon)] = {
            **selected,
            "episodes": episodes,
        }
    _bh_adjust(results)
    for result in results:
        if not result["formal_gate"]:
            continue
        latest = result["latest_30_percent"]
        ci = latest.get("bootstrap_95ci")
        significant = (
            result.get("fdr_bh") is not None
            and result["fdr_bh"] <= FDR_THRESHOLD
            and ci is not None
            and not (ci[0] <= 0.5 <= ci[1])
        )
        latest_auc = latest.get("auc")
        if significant and latest_auc is not None and latest_auc > 0.5:
            result["evidence_status"] = "supported_on_frozen_latest_segment"
        elif significant and latest_auc is not None and latest_auc < 0.5:
            result["evidence_status"] = "contradicted_on_frozen_latest_segment"
        elif latest_auc is not None and abs(latest_auc - 0.5) < 0.05:
            result["evidence_status"] = "no_clear_latest_separation"
        else:
            result["evidence_status"] = "inconclusive_or_temporally_unstable"
    return results, selected_specs


def _losses(probabilities: dict[str, float], label: str) -> tuple[float, float]:
    log_loss = -math.log(max(float(probabilities[label]), 1e-15))
    brier = math.fsum(
        (float(probabilities[name]) - (1.0 if name == label else 0.0)) ** 2
        for name in CLASSES
    )
    return log_loss, brier


def _paired_episode_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["episode_key"])].append(row)
    episodes = []
    for episode_key, members in grouped.items():
        episodes.append(
            {
                "episode_key": episode_key,
                "analysis_at": min(m8.parse_utc(row["analysis_at"]) for row in members),
                "raw_cases": len(members),
                "log_improvement": math.fsum(row["log_improvement"] for row in members)
                / len(members),
                "brier_improvement": math.fsum(row["brier_improvement"] for row in members)
                / len(members),
                "full_log_loss": math.fsum(row["full_log_loss"] for row in members)
                / len(members),
                "without_log_loss": math.fsum(row["without_log_loss"] for row in members)
                / len(members),
                "full_brier": math.fsum(row["full_brier"] for row in members) / len(members),
                "without_brier": math.fsum(row["without_brier"] for row in members)
                / len(members),
                "tp_share": sum(row["outcome_label"] == CLASSES[0] for row in members)
                / len(members),
                "sl_share": sum(row["outcome_label"] == CLASSES[1] for row in members)
                / len(members),
            }
        )
    return sorted(episodes, key=lambda row: (row["analysis_at"], row["episode_key"]))


def _mean(items: list[float]) -> float | None:
    return math.fsum(items) / len(items) if items else None


def _paired_inference(episodes: list[dict], *, seed: int) -> dict:
    log_values = [row["log_improvement"] for row in episodes]
    brier_values = [row["brier_improvement"] for row in episodes]
    result = {
        "episodes": len(episodes),
        "log_loss_improvement": _mean(log_values),
        "brier_improvement": _mean(brier_values),
        "log_loss_bootstrap_95ci": None,
        "brier_bootstrap_95ci": None,
        "permutation_p": None,
        "fdr_bh": None,
    }
    if len(episodes) < MIN_LATEST_EPISODES:
        return result
    rng = random.Random(seed)
    indices = list(range(len(episodes)))
    boot_log = []
    boot_brier = []
    for _ in range(BOOTSTRAP_SAMPLES):
        selected = [rng.choice(indices) for _ in indices]
        boot_log.append(_mean([log_values[index] for index in selected]))
        boot_brier.append(_mean([brier_values[index] for index in selected]))
    observed = abs(float(result["brier_improvement"]))
    extreme = 0
    for _ in range(PERMUTATION_SAMPLES):
        permuted = [value * (-1 if rng.random() < 0.5 else 1) for value in brier_values]
        if abs(float(_mean(permuted))) >= observed:
            extreme += 1
    result.update(
        {
            "log_loss_bootstrap_95ci": _percentile_interval(boot_log),
            "brier_bootstrap_95ci": _percentile_interval(boot_brier),
            "permutation_p": (extreme + 1) / (PERMUTATION_SAMPLES + 1),
        }
    )
    return result


def evaluate_probability_ablations(
    cases: list[dict],
    cutoffs: dict[str, datetime | None],
) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for case in cases:
        replay = case.get("replay")
        if not isinstance(replay, dict) or not case.get("episode_key"):
            continue
        label = (case.get("outcome") or {}).get("label")
        full = _normalized_probabilities(replay.get("probabilities"))
        if label not in CLASSES or full is None:
            continue
        for rule_id, without_raw in (replay.get("rule_ablations") or {}).items():
            without = _normalized_probabilities(without_raw)
            if without is None:
                continue
            full_log, full_brier = _losses(full, label)
            without_log, without_brier = _losses(without, label)
            grouped[(str(rule_id), case["time_horizon"])].append(
                {
                    "episode_key": case["episode_key"],
                    "analysis_at": case["analysis_at"],
                    "outcome_label": label,
                    "log_improvement": without_log - full_log,
                    "brier_improvement": without_brier - full_brier,
                    "full_log_loss": full_log,
                    "without_log_loss": without_log,
                    "full_brier": full_brier,
                    "without_brier": without_brier,
                }
            )
    results = []
    for index, ((rule_id, horizon), rows) in enumerate(sorted(grouped.items())):
        episodes = _paired_episode_rows(rows)
        cutoff = cutoffs[horizon]
        early = [row for row in episodes if row["analysis_at"] <= cutoff]
        latest = [row for row in episodes if row["analysis_at"] > cutoff]
        tp_mass = math.fsum(row["tp_share"] for row in episodes)
        sl_mass = math.fsum(row["sl_share"] for row in episodes)
        full = _paired_inference(episodes, seed=RANDOM_SEED + index * 43)
        latest_result = _paired_inference(latest, seed=RANDOM_SEED + index * 43 + 1)
        formal_gate = (
            len(episodes) >= MIN_EFFECTIVE_EPISODES
            and tp_mass >= MIN_EFFECTIVE_CLASS_MASS
            and sl_mass >= MIN_EFFECTIVE_CLASS_MASS
        )
        without_log = _mean([row["without_log_loss"] for row in episodes])
        without_brier = _mean([row["without_brier"] for row in episodes])
        result = {
            "rule_id": rule_id,
            "time_horizon": horizon,
            "raw_cases": len(rows),
            "effective_episodes": len(episodes),
            "effective_tp_mass": tp_mass,
            "effective_sl_mass": sl_mass,
            "full_period": full,
            "early_70_percent": {
                "episodes": len(early),
                "log_loss_improvement": _mean([row["log_improvement"] for row in early]),
                "brier_improvement": _mean([row["brier_improvement"] for row in early]),
            },
            "latest_30_percent": latest_result,
            "relative_full_log_loss_improvement": (
                full["log_loss_improvement"] / without_log
                if without_log and full["log_loss_improvement"] is not None
                else None
            ),
            "relative_full_brier_improvement": (
                full["brier_improvement"] / without_brier
                if without_brier and full["brier_improvement"] is not None
                else None
            ),
            "permutation_p": latest_result["permutation_p"],
            "fdr_bh": None,
            "formal_gate": formal_gate,
            "additional_effective_episodes_needed": max(
                0, MIN_EFFECTIVE_EPISODES - len(episodes)
            ),
            "evidence_status": "pending_fdr" if formal_gate else "insufficient_effective_evidence",
        }
        results.append(result)
    _bh_adjust(results)
    for result in results:
        if not result["formal_gate"]:
            continue
        full = result["full_period"]
        early = result["early_70_percent"]
        latest = result["latest_30_percent"]
        ci = latest.get("brier_bootstrap_95ci")
        significant = (
            result.get("fdr_bh") is not None
            and result["fdr_bh"] <= FDR_THRESHOLD
            and ci is not None
            and not (ci[0] <= 0 <= ci[1])
        )
        all_positive = all(
            item is not None and item > 0
            for item in (
                full["log_loss_improvement"],
                full["brier_improvement"],
                early["log_loss_improvement"],
                early["brier_improvement"],
                latest["log_loss_improvement"],
                latest["brier_improvement"],
            )
        )
        all_negative = all(
            item is not None and item < 0
            for item in (
                full["log_loss_improvement"],
                full["brier_improvement"],
                early["log_loss_improvement"],
                early["brier_improvement"],
                latest["log_loss_improvement"],
                latest["brier_improvement"],
            )
        )
        material = (
            (result.get("relative_full_log_loss_improvement") or 0) >= 0.02
            and (result.get("relative_full_brier_improvement") or 0) >= 0.02
        )
        if significant and all_positive and material:
            result["evidence_status"] = "supported_material_stable_ablation"
        elif significant and all_negative:
            result["evidence_status"] = "harmful_stable_ablation"
        elif abs(float(full.get("brier_improvement") or 0)) < 0.002:
            result["evidence_status"] = "negligible_probability_effect"
        else:
            result["evidence_status"] = "inconclusive_or_temporally_unstable"
    return results


def _case_variable_lookup(variable_rows: list[dict]) -> dict[tuple[int, str, str], float]:
    lookup = {}
    for row in variable_rows:
        lookup[(int(row["case_id"]), row["rule_id"], row["variable"])] = float(row["value"])
    return lookup


def evaluate_predefined_combinations(
    cases: list[dict],
    variable_rows: list[dict],
    selected_specs: dict[tuple[str, str], dict],
    cutoffs: dict[str, datetime | None],
) -> list[dict]:
    lookup = _case_variable_lookup(variable_rows)
    results = []
    for combination_name, definition in COMBINATIONS.items():
        for horizon in m8.HORIZON_SECONDS:
            target = definition["target"]
            components = []
            for rule_id in definition["rules"]:
                spec = selected_specs.get((rule_id, horizon))
                expected_target = "movement" if rule_id in MOVEMENT_RULE_IDS else "directional"
                if spec and expected_target == target:
                    components.append(
                        {
                            "rule_id": rule_id,
                            "variable": spec["variable"],
                            "orientation": spec["orientation"],
                        }
                    )
            if len(components) < 2:
                results.append(
                    {
                        "combination_id": combination_name,
                        "time_horizon": horizon,
                        "target": target,
                        "configured_rule_ids": definition["rules"],
                        "available_components": components,
                        "evidence_status": "insufficient_component_coverage",
                        "effective_episodes": 0,
                    }
                )
                continue

            cutoff = cutoffs[horizon]
            component_training_values: dict[str, list[float]] = defaultdict(list)
            raw_case_values = []
            for case in cases:
                if (
                    case.get("time_horizon") != horizon
                    or not case.get("episode_key")
                    or (case.get("outcome") or {}).get("label") not in CLASSES
                ):
                    continue
                values = {}
                for component in components:
                    raw = lookup.get(
                        (case["case_id"], component["rule_id"], component["variable"])
                    )
                    if raw is not None:
                        values[component["rule_id"]] = component["orientation"] * raw
                        if m8.parse_utc(case["analysis_at"]) <= cutoff:
                            component_training_values[component["rule_id"]].append(
                                component["orientation"] * raw
                            )
                if len(values) >= 2:
                    raw_case_values.append((case, values))
            scaling = {}
            for component in components:
                values = component_training_values[component["rule_id"]]
                mean = _mean(values)
                variance = (
                    _mean([(value - mean) ** 2 for value in values])
                    if values and mean is not None
                    else None
                )
                scale = math.sqrt(variance) if variance is not None and variance > 0 else None
                if mean is not None and scale:
                    scaling[component["rule_id"]] = {"mean": mean, "scale": scale}
            combination_rows = []
            for case, values in raw_case_values:
                standardized = [
                    (value - scaling[rule_id]["mean"]) / scaling[rule_id]["scale"]
                    for rule_id, value in values.items()
                    if rule_id in scaling
                ]
                if len(standardized) < 2:
                    continue
                combination_rows.append(
                    {
                        "episode_key": case["episode_key"],
                        "analysis_at": case["analysis_at"],
                        "outcome_label": case["outcome"]["label"],
                        "value": _mean(standardized),
                    }
                )
            episodes = _episode_signal_rows(combination_rows, target)
            early = [row for row in episodes if row["analysis_at"] <= cutoff]
            latest = [row for row in episodes if row["analysis_at"] > cutoff]
            early_auc = fast_soft_auc(
                [row["signal"] for row in early],
                [row["positive_share"] for row in early],
            )
            orientation = 1 if early_auc is None or early_auc >= 0.5 else -1
            latest_result = _association_inference(
                latest,
                orientation=orientation,
                seed=RANDOM_SEED + len(results) * 59,
            )
            positive, negative = _class_mass(episodes)
            formal_gate = (
                len(episodes) >= MIN_EFFECTIVE_EPISODES
                and positive >= MIN_EFFECTIVE_CLASS_MASS
                and negative >= MIN_EFFECTIVE_CLASS_MASS
            )
            results.append(
                {
                    "combination_id": combination_name,
                    "reason": definition["reason"],
                    "time_horizon": horizon,
                    "target": target,
                    "configured_rule_ids": definition["rules"],
                    "available_components": components,
                    "raw_cases": len(combination_rows),
                    "effective_episodes": len(episodes),
                    "effective_positive_mass": positive,
                    "effective_negative_mass": negative,
                    "orientation": "direct" if orientation == 1 else "inverse",
                    "early_70_percent_auc": (
                        early_auc if orientation == 1 or early_auc is None else 1.0 - early_auc
                    ),
                    "full_auc": fast_soft_auc(
                        [orientation * row["signal"] for row in episodes],
                        [row["positive_share"] for row in episodes],
                    ),
                    "latest_30_percent": latest_result,
                    "permutation_p": latest_result["permutation_p"],
                    "fdr_bh": None,
                    "formal_gate": formal_gate,
                    "evidence_status": (
                        "pending_fdr" if formal_gate else "insufficient_effective_evidence"
                    ),
                }
            )
    _bh_adjust(results)
    for result in results:
        if not result.get("formal_gate"):
            continue
        latest = result["latest_30_percent"]
        ci = latest.get("bootstrap_95ci")
        significant = (
            result.get("fdr_bh") is not None
            and result["fdr_bh"] <= FDR_THRESHOLD
            and ci is not None
            and not (ci[0] <= 0.5 <= ci[1])
        )
        if significant and latest.get("auc") is not None and latest["auc"] > 0.5:
            result["evidence_status"] = "supported_on_frozen_latest_segment"
        elif significant and latest.get("auc") is not None and latest["auc"] < 0.5:
            result["evidence_status"] = "contradicted_on_frozen_latest_segment"
        else:
            result["evidence_status"] = "inconclusive_or_temporally_unstable"
    return results


def derive_current_runtime_state(counterfactual_sources: list[dict]) -> dict:
    ordered = sorted(
        counterfactual_sources,
        key=lambda row: (
            m8.parse_utc(row.get("analysis_at")) or datetime.min.replace(tzinfo=timezone.utc),
            int(row["recommendation_id"]),
        ),
    )
    if not ordered:
        return {
            "source_engine_version": None,
            "exact_cases": 0,
            "production_fitted_rule_ids": [],
            "shadow_challenger_rule_ids": [],
            "observational_rule_ids": [],
        }
    current_engine = str(ordered[-1].get("engine_version") or "unknown")
    current = [row for row in ordered if str(row.get("engine_version") or "unknown") == current_engine]
    fitted_ids: set[str] = set()
    shadow_ids: set[str] = set()
    observed_ids: set[str] = set()
    for row in current:
        snapshot = _json_object(row.get("snapshot_json"))
        probability_trace = snapshot.get("m6_probability_trace")
        probability_trace = probability_trace if isinstance(probability_trace, dict) else {}
        fitted = probability_trace.get("fitted_rule_ablation")
        if isinstance(fitted, dict):
            fitted_ids.update(str(rule_id) for rule_id in fitted)
        shadow = probability_trace.get("shadow_challenger")
        if isinstance(shadow, dict) and shadow.get("status") == "evaluated_shadow":
            shadow_ids.update(str(rule_id) for rule_id in shadow.get("active_rule_ids") or [])
        feature = snapshot.get("feature_snapshot")
        feature = feature if isinstance(feature, dict) else {}
        for trace in _iter_rule_traces(feature.get("observational_rule_traces")):
            if trace.get("status") == "evaluated_shadow" and trace.get("rule_id"):
                observed_ids.add(str(trace["rule_id"]))
    return {
        "source_engine_version": current_engine,
        "exact_cases": len(current),
        "production_fitted_rule_ids": sorted(fitted_ids),
        "shadow_challenger_rule_ids": sorted(shadow_ids),
        "observational_rule_ids": sorted(observed_ids),
        "production_change_from_this_audit": False,
    }


def classify_rule_library(
    library: dict,
    coverage: dict,
    hypothesis_metrics: list[dict],
    ablations: list[dict],
    combinations: list[dict],
    runtime_state: dict,
) -> list[dict]:
    hypothesis_by_rule: dict[str, list[dict]] = defaultdict(list)
    for metric in hypothesis_metrics:
        hypothesis_by_rule[metric["rule_id"]].append(metric)
    ablation_by_rule: dict[str, list[dict]] = defaultdict(list)
    for metric in ablations:
        ablation_by_rule[metric["rule_id"]].append(metric)
    combination_by_rule: dict[str, list[dict]] = defaultdict(list)
    for metric in combinations:
        for rule_id in metric.get("configured_rule_ids", []):
            combination_by_rule[rule_id].append(
                {
                    "combination_id": metric["combination_id"],
                    "time_horizon": metric["time_horizon"],
                    "evidence_status": metric["evidence_status"],
                }
            )

    fitted = set(runtime_state["production_fitted_rule_ids"])
    challenger = set(runtime_state["shadow_challenger_rule_ids"])
    observational = set(runtime_state["observational_rule_ids"])
    output = []
    for rule in library["rules"]:
        rule_id = rule["rule_id"]
        lifecycle = rule["lifecycle_status"]
        hypotheses = hypothesis_by_rule.get(rule_id, [])
        rule_ablations = ablation_by_rule.get(rule_id, [])
        supported_hypotheses = [
            item for item in hypotheses
            if item["evidence_status"] == "supported_on_frozen_latest_segment"
        ]
        contradicted_hypotheses = [
            item for item in hypotheses
            if item["evidence_status"] == "contradicted_on_frozen_latest_segment"
        ]
        formal_hypotheses = [item for item in hypotheses if item.get("formal_gate")]
        supported_ablations = [
            item for item in rule_ablations
            if item["evidence_status"] == "supported_material_stable_ablation"
        ]
        harmful_ablations = [
            item for item in rule_ablations
            if item["evidence_status"] == "harmful_stable_ablation"
        ]
        formal_ablations = [item for item in rule_ablations if item.get("formal_gate")]

        if lifecycle in {"active_deterministic", "active_blocking"}:
            decision = "keep_as_deterministic_control"
            reason = "control necesario; no debe recibir peso probabilistico propio"
        elif lifecycle == "active_economic":
            decision = "keep_as_execution_cost_control"
            reason = "afecta ejecutabilidad y coste, no la probabilidad TP/SL aislada"
        elif lifecycle == "data_blocked":
            decision = "blocked_until_exact_data_contract_exists"
            reason = "no hay dato pretrade exacto para una evaluacion valida"
        elif lifecycle == "active_provisional":
            if supported_ablations:
                decision = "retain_only_supported_horizon_probability_role"
                reason = "ablacion material y estable en al menos un horizonte"
            elif harmful_ablations:
                decision = "remove_from_next_challenger_or_reformulate"
                reason = "la ablacion indica perjuicio estable; no se cambia produccion automaticamente"
            elif formal_ablations:
                decision = "recalibrate_or_use_only_in_interactions"
                reason = "hay muestra suficiente pero no utilidad probabilistica estable"
            else:
                decision = "hold_current_role_without_new_weight"
                reason = "faltan episodios independientes para decidir con rigor"
        elif lifecycle == "implemented_shadow":
            if supported_hypotheses:
                directional_support = any(
                    item["target"] == "directional" for item in supported_hypotheses
                )
                if directional_support:
                    decision = "candidate_for_horizon_directional_challenger"
                    reason = (
                        "la hipotesis congelada conserva separacion TP frente a SL "
                        "en el tramo reciente"
                    )
                else:
                    decision = "candidate_for_horizon_movement_challenger"
                    reason = (
                        "predice resolucion frente a expiry, no TP frente a SL; "
                        "solo puede probarse como puerta de movimiento"
                    )
            elif contradicted_hypotheses:
                decision = "reformulate_before_more_observation"
                reason = "la direccion aprendida en el historico falla en el tramo reciente"
            elif formal_hypotheses:
                decision = "do_not_promote_current_hypothesis"
                reason = "muestra suficiente sin evidencia reciente estable"
            else:
                decision = "continue_shadow_observation"
                reason = "cobertura independiente aun insuficiente; no se inventa peso"
        else:
            decision = "manual_review"
            reason = "estado de ciclo de vida no reconocido por la auditoria"

        if rule_id in fitted:
            runtime_role = "production_fitted"
        elif rule_id in challenger:
            runtime_role = "shadow_challenger"
        elif rule_id in observational:
            runtime_role = "observational_shadow"
        elif rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
            runtime_role = "active_library_rule_not_seen_in_latest_exact_trace"
        else:
            runtime_role = "control_or_not_active_in_latest_probability_trace"
        output.append(
            {
                "rule_id": rule_id,
                "name": rule["name"],
                "family_id": rule["family_id"],
                "lifecycle_status": lifecycle,
                "runtime_role": runtime_role,
                "coverage": coverage.get(rule_id, {}),
                "hypothesis_slices": hypotheses,
                "probability_ablation_slices": rule_ablations,
                "combination_slices": combination_by_rule.get(rule_id, []),
                "decision": decision,
                "decision_reason": reason,
                "production_change_authorized": False,
            }
        )
    if len(output) != 38 or len({item["rule_id"] for item in output}) != 38:
        raise ValueError("final_rule_classification_not_complete")
    return output


def _fmt(value: Any, digits: int = 3) -> str:
    number = _finite(value)
    return "--" if number is None else f"{number:.{digits}f}"


def build_report(payload: dict) -> str:
    cohort = payload["cohort"]
    episodes = payload["episodes"]
    decisions = payload["rule_decisions"]
    hypothesis = payload["individual_rule_hypotheses"]
    ablations = payload["active_probability_ablations"]
    combinations = payload["predefined_combinations"]
    decision_counts = Counter(item["decision"] for item in decisions)
    supported_rules = [
        item for item in decisions
        if item["decision"] in {
            "candidate_for_horizon_directional_challenger",
            "candidate_for_horizon_movement_challenger",
            "retain_only_supported_horizon_probability_role",
        }
    ]
    supported_directional = [
        item
        for item in hypothesis
        if item["target"] == "directional"
        and item["evidence_status"] == "supported_on_frozen_latest_segment"
    ]
    supported_movement = [
        item
        for item in hypothesis
        if item["target"] == "movement"
        and item["evidence_status"] == "supported_on_frozen_latest_segment"
    ]
    lines = [
        "# Auditoria final de utilidad de las 38 reglas",
        "",
        f"- Version: `{payload['audit_version']}`.",
        f"- Motor observado: `{payload['current_runtime_state']['source_engine_version']}`.",
        "- Efecto sobre produccion: **ninguno**.",
        "- Escrituras en Supabase: **ninguna**.",
        "",
        "## Respuesta ejecutiva",
        "",
        (
            f"La cohorte consolidada contiene **{episodes['formal_cases']} casos market "
            f"con resultado exacto**, procedentes de operaciones cerradas y contrafactuales "
            "exactos. Los analisis solapados se han reducido a episodios independientes "
            "antes de medir cualquier regla."
        ),
        "",
        (
            f"Reglas con evidencia suficiente para conservar o entrar en un challenger "
            f"por horizonte: **{len(supported_rules)}**. Ninguna decision de esta auditoria "
            "modifica el campeon online: primero identifica que merece una prueba controlada."
        ),
        (
            f"Soporte para distinguir **TP frente a SL**: **{len(supported_directional)} reglas**. "
            f"Soporte para distinguir **movimiento frente a expiry**: "
            f"**{len(supported_movement)} reglas**. No se confunden ambos objetivos."
        ),
        "",
        "## Paso 1 - Cohorte valida y sin duplicar mercado",
        "",
        f"- Operaciones cerradas cargadas: **{cohort['closed_operations_loaded']}**.",
        f"- Operaciones market: **{cohort['closed_market_operations']}**.",
        f"- Pending separadas del replay market: **{cohort['closed_pending_operations_separated']}**.",
        f"- Contrafactuales exactos evaluados: **{cohort['formal_exact_counterfactuals']}**.",
        f"- Casos exactos combinados y resolubles: **{episodes['formal_cases']}**.",
        "",
        "| Horizonte | Casos | Episodios independientes | Bloques UTC |",
        "|---|---:|---:|---:|",
    ]
    for horizon, item in episodes["by_horizon"].items():
        lines.append(
            f"| `{horizon}` | {item['formal_cases']} | "
            f"{item['formal_effective_horizon_episodes']} | "
            f"{item['formal_calendar_blocks_utc']} |"
        )
    lines.extend(
        [
            "",
            "## Paso 2 - Reconstruccion con las reglas actuales",
            "",
            (
                f"Se reejecutaron las formulas actuales sobre **{cohort['combined_cases']}** "
                "casos. Los datos ausentes permanecen ausentes: no se convierten en cero ni "
                "en una senal neutra. Las ordenes pending no se mezclan con el contrato market."
            ),
            "",
            "## Paso 3 - Reglas individuales por horizonte",
            "",
            (
                "Cada variable candidata se eligio solo en el 70% antiguo; su orientacion se "
                "congelo y se valido en el 30% reciente. El minimo formal es 50 episodios y "
                "10 unidades efectivas por clase, con bootstrap/permutacion de 2.000 y FDR BH."
            ),
            "",
            "| Regla | Horizonte | Episodios | Variable congelada | AUC reciente | Estado |",
            "|---|---|---:|---|---:|---|",
        ]
    )
    for item in hypothesis:
        lines.append(
            f"| `{item['rule_id']}` | `{item['time_horizon']}` | "
            f"{item['effective_episodes']} | `{item['selected_variable']}` | "
            f"{_fmt(item['latest_30_percent'].get('auc'))} | "
            f"`{item['evidence_status']}` |"
        )
    lines.extend(
        [
            "",
            "### Ablaciones de reglas que ya pueden afectar probabilidades",
            "",
            "| Regla | Horizonte | Episodios | Mejora Brier total | Mejora Brier reciente | Estado |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for item in ablations:
        lines.append(
            f"| `{item['rule_id']}` | `{item['time_horizon']}` | "
            f"{item['effective_episodes']} | "
            f"{_fmt(item['full_period'].get('brier_improvement'), 5)} | "
            f"{_fmt(item['latest_30_percent'].get('brier_improvement'), 5)} | "
            f"`{item['evidence_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Paso 4 - Combinaciones predefinidas",
            "",
            "| Combinacion | Horizonte | Componentes disponibles | Episodios | AUC reciente | Estado |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for item in combinations:
        lines.append(
            f"| `{item['combination_id']}` | `{item['time_horizon']}` | "
            f"{len(item.get('available_components', []))} | "
            f"{item.get('effective_episodes', 0)} | "
            f"{_fmt((item.get('latest_30_percent') or {}).get('auc'))} | "
            f"`{item['evidence_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Paso 5 - Decision de las 38 reglas",
            "",
            "| Regla | Estado actual | Papel runtime | Decision |",
            "|---|---|---|---|",
        ]
    )
    for item in decisions:
        lines.append(
            f"| `{item['rule_id']}` | `{item['lifecycle_status']}` | "
            f"`{item['runtime_role']}` | `{item['decision']}` |"
        )
    lines.extend(
        [
            "",
            "### Recuento de decisiones",
            "",
        ]
    )
    for decision, count in sorted(decision_counts.items()):
        lines.append(f"- `{decision}`: **{count}** reglas.")
    lines.extend(
        [
            "",
            "## Que se ha aprendido de verdad",
            "",
            (
                "Una regla solo se considera util si conserva efecto fuera del tramo donde "
                "se eligio. Si falta cobertura, la conclusion correcta es esperar; si hay "
                "muestra y no separa, no se promociona; si contradice el tramo antiguo, se "
                "reformula. Esto permite auditar operaciones de versiones distintas sin "
                "mezclar sus probabilidades servidas: el outcome es comun, pero cada formula "
                "actual se reconstruye con datos disponibles en el instante pretrade."
            ),
            "",
            "No se asigna ningun peso automaticamente. Las candidatas que superen el filtro "
            "deben entrar primero en un challenger en sombra especifico para su horizonte.",
            "",
        ]
    )
    return "\n".join(lines)


def run_final_audit() -> dict:
    captured_at = datetime.now(timezone.utc)
    use_session_pool_for_long_audit()
    print("FINAL_AUDIT_STAGE=load_database_sources", flush=True)
    stored, unlinked = load_database_sources()
    print(
        f"FINAL_AUDIT_STAGE=prepare_counterfactuals:stored={len(stored)}:unlinked={len(unlinked)}",
        flush=True,
    )
    counterfactual_sources, counterfactual_inventory = prepare_exact_counterfactuals(
        stored,
        unlinked,
        captured_at=captured_at,
    )
    print(
        f"FINAL_AUDIT_STAGE=load_closed_operations:counterfactuals={len(counterfactual_sources)}",
        flush=True,
    )
    closed_rows = load_closed_rows()
    print(
        f"FINAL_AUDIT_STAGE=replay_rules:closed={len(closed_rows)}",
        flush=True,
    )
    cases, cohort = replay_consolidated_cases(closed_rows, counterfactual_sources)
    print(f"FINAL_AUDIT_STAGE=group_episodes:cases={len(cases)}", flush=True)
    cases, episodes = attach_episode_memberships(cases)
    library = load_rule_library()
    library_rules = {rule["rule_id"]: rule for rule in library["rules"]}
    variable_rows, coverage = extract_rule_variables(cases, library_rules)
    cutoffs = horizon_cutoffs(cases)
    print(
        f"FINAL_AUDIT_STAGE=evaluate_individual_rules:variables={len(variable_rows)}",
        flush=True,
    )
    hypotheses, selected_specs = select_and_evaluate_rule_hypotheses(
        variable_rows,
        cutoffs,
    )
    print("FINAL_AUDIT_STAGE=evaluate_ablations", flush=True)
    ablations = evaluate_probability_ablations(cases, cutoffs)
    print("FINAL_AUDIT_STAGE=evaluate_combinations", flush=True)
    combinations = evaluate_predefined_combinations(
        cases,
        variable_rows,
        selected_specs,
        cutoffs,
    )
    print("FINAL_AUDIT_STAGE=classify_38_rules", flush=True)
    runtime_state = derive_current_runtime_state(counterfactual_sources)
    decisions = classify_rule_library(
        library,
        coverage,
        hypotheses,
        ablations,
        combinations,
        runtime_state,
    )
    cohort.update(
        {
            "formal_exact_counterfactuals": len(counterfactual_sources),
            "counterfactual_inventory": counterfactual_inventory,
            "variable_rows_evaluated": len(variable_rows),
        }
    )
    deterministic = {
        "audit_version": AUDIT_VERSION,
        "library_version": library["library_version"],
        "catalog_sha256": library["catalog_sha256"],
        "production_effect": "none",
        "supabase_writes": 0,
        "protocol": {
            "independent_unit": "overlapping_episode_by_symbol_and_horizon",
            "minimum_effective_episodes": MIN_EFFECTIVE_EPISODES,
            "minimum_effective_class_mass": MIN_EFFECTIVE_CLASS_MASS,
            "temporal_validation": "select_on_earliest_70_percent_validate_on_latest_30_percent",
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "permutation_samples": PERMUTATION_SAMPLES,
            "multiple_testing": "Benjamini-Hochberg",
            "fdr_threshold": FDR_THRESHOLD,
            "automatic_weight_change": False,
        },
        "cohort": cohort,
        "episodes": episodes,
        "current_runtime_state": runtime_state,
        "individual_rule_hypotheses": hypotheses,
        "active_probability_ablations": ablations,
        "predefined_combinations": combinations,
        "rule_decisions": decisions,
        "decision_summary": dict(Counter(item["decision"] for item in decisions)),
    }
    deterministic["audit_sha256"] = m8.payload_sha256(deterministic)
    return {**deterministic, "generated_at": captured_at.isoformat()}
