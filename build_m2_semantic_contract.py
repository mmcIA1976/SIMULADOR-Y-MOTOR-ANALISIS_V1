from __future__ import annotations

import argparse
import hashlib
import json
from math import isclose, isfinite, log
from pathlib import Path
from typing import Any

import analysis_engine
import data_engine


ROOT = Path(__file__).resolve().parent
DEFAULT_CONTRACT_PATH = (
    ROOT / "auditorias_motor" / "contrato_semantico_m2_v0_1.json"
)
DEFAULT_AUDIT_PATH = (
    ROOT / "auditorias_motor" / "auditoria_invariantes_m2_motor_actual_v0_1.json"
)
DEFAULT_REPORT_PATH = (
    ROOT / "auditorias_motor" / "2026-07-27_M2_semantica_geometria_resultado.md"
)

SEMANTIC_VERSION = "M2-semantic-contract-v0.1"
AUDIT_VERSION = "M2-current-engine-invariants-v0.1"
PROBABILITY_TOLERANCE = 1e-12

HORIZON_LIMITS_SECONDS = {
    "intraday_short": (30 * 60, 4 * 60 * 60),
    "intraday_wide": (4 * 60 * 60, 24 * 60 * 60),
    "short_swing": (24 * 60 * 60, 7 * 24 * 60 * 60),
}

CONDITIONAL_OUTCOMES = (
    "tp_first",
    "sl_first",
    "expiry_after_entry",
)
OVERALL_OUTCOMES = (
    "tp_first",
    "sl_first",
    "expiry_after_entry",
    "no_entry",
)
VISIBLE_OUTCOMES = (
    "tp_first",
    "sl_first",
    "unresolved",
)


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


def validate_horizon(time_horizon: str, horizon_seconds: float) -> None:
    if time_horizon not in HORIZON_LIMITS_SECONDS:
        raise ValueError("invalid_time_horizon")
    if not isinstance(horizon_seconds, (int, float)) or isinstance(
        horizon_seconds, bool
    ):
        raise ValueError("invalid_horizon_seconds")
    if not isfinite(float(horizon_seconds)):
        raise ValueError("invalid_horizon_seconds")
    lower, upper = HORIZON_LIMITS_SECONDS[time_horizon]
    if not lower <= float(horizon_seconds) <= upper:
        raise ValueError("horizon_seconds_out_of_profile")


def validate_barrier_geometry(
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
) -> None:
    values = (entry, take_profit, stop_loss)
    if (
        any(not isinstance(value, (int, float)) for value in values)
        or any(isinstance(value, bool) for value in values)
        or any(not isfinite(float(value)) for value in values)
        or any(value <= 0 for value in values)
    ):
        raise ValueError("prices_must_be_positive_finite_numbers")
    if side == "long":
        valid = stop_loss < entry < take_profit
    elif side == "short":
        valid = take_profit < entry < stop_loss
    else:
        raise ValueError("invalid_side")
    if not valid:
        raise ValueError("invalid_barrier_geometry")


def derive_plan_geometry(
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    horizon_seconds: float,
) -> dict[str, float]:
    validate_barrier_geometry(side, entry, take_profit, stop_loss)
    if (
        not isinstance(horizon_seconds, (int, float))
        or isinstance(horizon_seconds, bool)
        or not isfinite(float(horizon_seconds))
        or horizon_seconds <= 0
    ):
        raise ValueError("invalid_horizon_seconds")
    side_sign = 1.0 if side == "long" else -1.0
    tp_log_distance = side_sign * log(take_profit / entry)
    sl_log_distance = -side_sign * log(stop_loss / entry)
    return {
        "side_sign": side_sign,
        "tp_log_distance": tp_log_distance,
        "sl_log_distance": sl_log_distance,
        "log_horizon_seconds": log(float(horizon_seconds)),
    }


def normalize_geometry_by_volatility(
    geometry: dict[str, float],
    horizon_volatility: float,
) -> dict[str, float]:
    if (
        not isinstance(horizon_volatility, (int, float))
        or isinstance(horizon_volatility, bool)
        or not isfinite(float(horizon_volatility))
        or horizon_volatility <= 0
    ):
        raise ValueError("invalid_horizon_volatility")
    for key in ("tp_log_distance", "sl_log_distance"):
        value = geometry.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            or value <= 0
        ):
            raise ValueError(f"invalid_geometry_distance:{key}")
    sigma_h = float(horizon_volatility)
    return {
        "horizon_volatility": sigma_h,
        "tp_volatility_units": float(geometry["tp_log_distance"]) / sigma_h,
        "sl_volatility_units": float(geometry["sl_log_distance"]) / sigma_h,
    }


def validate_probability_distribution(
    probabilities: dict[str, float],
    expected_keys: tuple[str, ...],
) -> None:
    if set(probabilities) != set(expected_keys):
        raise ValueError("probability_keys_mismatch")
    for key in expected_keys:
        value = probabilities[key]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0.0 <= float(value) <= 1.0
        ):
            raise ValueError(f"invalid_probability:{key}")
    if not isclose(
        sum(float(probabilities[key]) for key in expected_keys),
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_TOLERANCE,
    ):
        raise ValueError("probability_mass_not_one")


def compose_probability_tree(
    entry_execution_probability: float,
    conditional_after_entry: dict[str, float],
) -> dict[str, Any]:
    if (
        not isinstance(entry_execution_probability, (int, float))
        or isinstance(entry_execution_probability, bool)
        or not 0.0 <= float(entry_execution_probability) <= 1.0
    ):
        raise ValueError("invalid_entry_execution_probability")
    validate_probability_distribution(
        conditional_after_entry,
        CONDITIONAL_OUTCOMES,
    )
    entry_probability = float(entry_execution_probability)
    overall = {
        "tp_first": entry_probability
        * float(conditional_after_entry["tp_first"]),
        "sl_first": entry_probability
        * float(conditional_after_entry["sl_first"]),
        "expiry_after_entry": entry_probability
        * float(conditional_after_entry["expiry_after_entry"]),
        "no_entry": 1.0 - entry_probability,
    }
    validate_probability_distribution(overall, OVERALL_OUTCOMES)
    visible = {
        "tp_first": overall["tp_first"],
        "sl_first": overall["sl_first"],
        "unresolved": overall["expiry_after_entry"] + overall["no_entry"],
    }
    validate_probability_distribution(visible, VISIBLE_OUTCOMES)
    return {
        "entry": {
            "executed_by_expiry": entry_probability,
            "not_executed_by_expiry": 1.0 - entry_probability,
        },
        "conditional_after_entry": dict(conditional_after_entry),
        "overall": overall,
        "visible": visible,
        "conditional_mass": sum(conditional_after_entry.values()),
        "overall_mass": sum(overall.values()),
        "visible_mass": sum(visible.values()),
    }


def current_price_vs_entry_bias(
    side: str,
    current_price: float,
    entry: float,
) -> float:
    if side == "long":
        return 0.03 if current_price <= entry else -0.02
    if side == "short":
        return 0.03 if current_price >= entry else -0.02
    raise ValueError("invalid_side")


def current_residual_probabilities(
    tp_probability: float,
    range_probability: float,
) -> dict[str, float]:
    return {
        "tp": tp_probability,
        "sl": max(0.05, 1.0 - tp_probability - range_probability),
        "range": range_probability,
    }


INVARIANTS = [
    {
        "id": "M2-INV-PRETRADE-01",
        "category": "time",
        "requirement": (
            "analysis_at is time zero; every predictive datum and model "
            "cutoff must be <= analysis_at, and no later outcome may alter "
            "the original snapshot."
        ),
        "acceptance": "data_cutoff_at <= analysis_at < expiry_at",
    },
    {
        "id": "M2-INV-HORIZON-01",
        "category": "time",
        "requirement": (
            "A concrete horizon_seconds inside one of the three current "
            "profiles is mandatory; expiry_at=analysis_at+horizon_seconds."
        ),
        "acceptance": "No categorical-only or 3-60h fallback is accepted.",
    },
    {
        "id": "M2-INV-GEOMETRY-01",
        "category": "geometry",
        "requirement": (
            "Long requires SL<entry<TP; short requires TP<entry<SL; invalid "
            "geometry blocks the analysis."
        ),
        "acceptance": "Both inequalities are checked before any signal.",
    },
    {
        "id": "M2-INV-GEOMETRY-02",
        "category": "geometry",
        "requirement": (
            "TP and SL distances are positive signed log distances and are "
            "side-symmetric."
        ),
        "acceptance": (
            "d_tp=s*ln(TP/entry); d_sl=-s*ln(SL/entry), s=+1 long/-1 short."
        ),
    },
    {
        "id": "M2-INV-SCALE-01",
        "category": "geometry",
        "requirement": (
            "Barrier distances must also be expressed in units of an approved "
            "positive log-return volatility scale matched to the exact "
            "horizon; an unavailable or invalid scale blocks probability."
        ),
        "acceptance": (
            "z_tp=d_tp/sigma_H and z_sl=d_sl/sigma_H with finite sigma_H>0; "
            "M3 must approve its data and M4 its estimator before use."
        ),
    },
    {
        "id": "M2-INV-ACTIVATION-01",
        "category": "entry",
        "requirement": (
            "Pending entry execution is a separate event. no_entry cannot be "
            "renamed as range or expiry_after_entry."
        ),
        "acceptance": (
            "P(entry)+P(no_entry)=1 and both remain visible in the trace."
        ),
    },
    {
        "id": "M2-INV-CLOCK-01",
        "category": "entry",
        "requirement": (
            "For pending plans the clock never restarts at entry; late entry "
            "has only expiry_at-entry_at remaining."
        ),
        "acceptance": "expiry_at is fixed once at analysis_at.",
    },
    {
        "id": "M2-INV-OUTCOME-01",
        "category": "outcome",
        "requirement": (
            "Conditional on executed entry, TP_first, SL_first and "
            "expiry_after_entry are mutually exclusive and exhaustive."
        ),
        "acceptance": "Conditional probability mass equals 1.",
    },
    {
        "id": "M2-INV-OUTCOME-02",
        "category": "outcome",
        "requirement": (
            "Overall pending outcomes are TP_first, SL_first, "
            "expiry_after_entry and no_entry."
        ),
        "acceptance": "Overall probability mass equals 1.",
    },
    {
        "id": "M2-INV-OUTPUT-01",
        "category": "output",
        "requirement": (
            "The two main displayed percentages are unconditional P(TP_first) "
            "and P(SL_first) from analysis_at; unresolved is explicit."
        ),
        "acceptance": "TP+SL+unresolved=1 without residual floors.",
    },
    {
        "id": "M2-INV-MONO-TP-01",
        "category": "monotonicity",
        "requirement": (
            "With snapshot, entry, SL and horizon fixed, moving TP farther "
            "cannot increase P(TP_first) and must affect reachability."
        ),
        "acceptance": "Property test over supported sides, pairs and horizons.",
    },
    {
        "id": "M2-INV-MONO-SL-01",
        "category": "monotonicity",
        "requirement": (
            "With snapshot, entry, TP and horizon fixed, moving SL farther "
            "cannot increase P(SL_first) and must affect reachability."
        ),
        "acceptance": "Property test over supported sides, pairs and horizons.",
    },
    {
        "id": "M2-INV-MONO-HORIZON-01",
        "category": "monotonicity",
        "requirement": (
            "With all non-time inputs fixed, extending the horizon cannot "
            "increase unresolved probability."
        ),
        "acceptance": "P(unresolved,H2)<=P(unresolved,H1) for H2>H1.",
    },
    {
        "id": "M2-INV-CONTINUITY-01",
        "category": "continuity",
        "requirement": (
            "An infinitesimal continuous input change cannot create a "
            "material probability jump unless a documented discrete market "
            "event changes state."
        ),
        "acceptance": "The 5-point price/entry jump of 872/873 is forbidden.",
    },
    {
        "id": "M2-INV-SYMMETRY-01",
        "category": "symmetry",
        "requirement": (
            "Mirrored long and short plans with mirrored signed market inputs "
            "must produce mirrored geometry and equivalent reachability."
        ),
        "acceptance": "Long/short property test.",
    },
    {
        "id": "M2-INV-SEPARATION-01",
        "category": "separation",
        "requirement": (
            "Market path probability, entry execution, costs, plan quality "
            "and account risk remain separate before an explicit integration."
        ),
        "acceptance": (
            "Margin/leverage/cost policy cannot silently change market path "
            "probability."
        ),
    },
    {
        "id": "M2-INV-DATA-01",
        "category": "evidence",
        "requirement": (
            "Missing, stale, future, invalid or unapproved mandatory data "
            "produces blocked or insufficient_evidence, never neutral evidence."
        ),
        "acceptance": "No RSI=50/EMA=price style predictive fallback.",
    },
    {
        "id": "M2-INV-AMBIGUITY-01",
        "category": "labels",
        "requirement": (
            "A later observation that cannot order TP and SL is ambiguous; "
            "missing coverage or manual closure is censored."
        ),
        "acceptance": (
            "Ambiguous/censored cases remain recorded but are not forced into "
            "an outcome."
        ),
    },
    {
        "id": "M2-INV-TRACE-01",
        "category": "traceability",
        "requirement": (
            "Every output records semantic version, plan, clock, geometry, "
            "entry tree, conditional and overall masses, data cutoff and "
            "blocking reasons."
        ),
        "acceptance": "The visible explanation is generated from this trace.",
    },
]


EDGE_CASES = [
    {
        "id": "M2-CASE-001",
        "name": "valid_long_geometry",
        "input": {"side": "long", "entry": 100, "tp": 103, "sl": 98},
        "expected": "accepted_positive_distances",
    },
    {
        "id": "M2-CASE-002",
        "name": "valid_short_mirror",
        "input": {
            "side": "short",
            "entry": 100,
            "tp": 10000 / 103,
            "sl": 10000 / 98,
        },
        "expected": "same_log_distances_as_case_001",
    },
    {
        "id": "M2-CASE-003",
        "name": "invalid_long_barriers",
        "input": {"side": "long", "entry": 100, "tp": 99, "sl": 98},
        "expected": "blocked_invalid_geometry",
    },
    {
        "id": "M2-CASE-004",
        "name": "market_entry_distribution",
        "input": {
            "p_entry": 1.0,
            "conditional": {
                "tp_first": 0.45,
                "sl_first": 0.35,
                "expiry_after_entry": 0.20,
            },
        },
        "expected": "no_entry_zero_all_masses_one",
    },
    {
        "id": "M2-CASE-005",
        "name": "pending_no_entry_separated",
        "input": {
            "p_entry": 0.60,
            "conditional": {
                "tp_first": 0.50,
                "sl_first": 0.30,
                "expiry_after_entry": 0.20,
            },
        },
        "expected": {
            "tp_first": 0.30,
            "sl_first": 0.18,
            "expiry_after_entry": 0.12,
            "no_entry": 0.40,
        },
    },
    {
        "id": "M2-CASE-006",
        "name": "late_pending_entry_does_not_restart_clock",
        "input": {
            "analysis_at_seconds": 0,
            "horizon_seconds": 14400,
            "entry_at_seconds": 13800,
        },
        "expected": {"expiry_at_seconds": 14400, "remaining_seconds": 600},
    },
    {
        "id": "M2-CASE-007",
        "name": "same_interval_tp_sl",
        "input": {"coarse_interval_touches": ["tp", "sl"], "ordered_ticks": None},
        "expected": "ambiguous_not_forced",
    },
    {
        "id": "M2-CASE-008",
        "name": "missing_exact_duration",
        "input": {"time_horizon": "intraday_short", "horizon_seconds": None},
        "expected": "blocked",
    },
    {
        "id": "M2-CASE-009",
        "name": "unknown_horizon",
        "input": {"time_horizon": "3-60h", "horizon_seconds": 10800},
        "expected": "blocked",
    },
    {
        "id": "M2-CASE-010",
        "name": "case_872_873_discontinuity",
        "input": {
            "side": "short",
            "entry": 100,
            "price_a": 99.999999,
            "price_b": 100,
        },
        "expected": "no_material_jump",
        "current_engine_observation": "-0.02 to +0.03",
    },
    {
        "id": "M2-CASE-011",
        "name": "current_probability_floor_mass",
        "input": {"tp": 0.74, "range": 0.22},
        "expected": "mass_exactly_one",
        "current_engine_observation": "mass=1.01",
    },
    {
        "id": "M2-CASE-012",
        "name": "missing_market_data",
        "input": {"candles": []},
        "expected": "blocked_or_insufficient_evidence",
        "current_engine_observation": "neutral defaults",
    },
    {
        "id": "M2-CASE-013",
        "name": "account_parameters_do_not_change_path",
        "input": {"same_plan": True, "leverage_a": 1, "leverage_b": 50},
        "expected": "same_market_path_distribution",
    },
    {
        "id": "M2-CASE-014",
        "name": "farther_barrier_sensitivity",
        "input": {"same_snapshot": True, "tp_distance_a": 0.01, "tp_distance_b": 0.03},
        "expected": "p_tp_b_not_greater_and_not_identical_without_reason",
    },
    {
        "id": "M2-CASE-015",
        "name": "missing_or_invalid_horizon_volatility",
        "input": {"horizon_volatility": None},
        "expected": "blocked_not_neutralized",
    },
]


OUTPUT_CONTRACT = {
    "status_values": [
        "probability_available",
        "blocked",
        "insufficient_evidence",
    ],
    "required_identity": [
        "semantic_version",
        "analysis_type",
        "analysis_at",
        "data_cutoff_at",
        "symbol",
        "side",
        "entry_type",
        "time_horizon",
        "horizon_seconds",
        "expiry_at",
    ],
    "required_geometry": [
        "entry",
        "take_profit",
        "stop_loss",
        "side_sign",
        "tp_log_distance",
        "sl_log_distance",
        "horizon_volatility",
        "tp_volatility_units",
        "sl_volatility_units",
    ],
    "entry_distribution": {
        "keys": ["executed_by_expiry", "not_executed_by_expiry"],
        "mass": 1.0,
        "meaning": (
            "Execution means the entry event defined by the approved execution "
            "contract occurred before the fixed expiry."
        ),
    },
    "conditional_after_entry": {
        "keys": list(CONDITIONAL_OUTCOMES),
        "mass": 1.0,
    },
    "overall_distribution": {
        "keys": list(OVERALL_OUTCOMES),
        "mass": 1.0,
        "formula": {
            "tp_first": "P(entry)*P(tp_first|entry)",
            "sl_first": "P(entry)*P(sl_first|entry)",
            "expiry_after_entry": "P(entry)*P(expiry_after_entry|entry)",
            "no_entry": "1-P(entry)",
        },
    },
    "visible_distribution": {
        "keys": list(VISIBLE_OUTCOMES),
        "mass": 1.0,
        "formula": {
            "tp_first": "overall.tp_first",
            "sl_first": "overall.sl_first",
            "unresolved": "overall.expiry_after_entry+overall.no_entry",
        },
        "labels": {
            "tp_first": "Probabilidad de alcanzar TP antes que SL",
            "sl_first": "Probabilidad de alcanzar SL antes que TP",
            "unresolved": "Probabilidad de no resolver el plan",
        },
    },
    "required_trace": [
        "entry_event_definition",
        "price_reference",
        "conditional_mass",
        "overall_mass",
        "visible_mass",
        "data_quality",
        "blocking_reasons",
        "method_version",
    ],
    "forbidden": [
        "manual_points_as_probability",
        "residual_sl_floor",
        "silent_horizon_fallback",
        "missing_as_neutral",
        "no_entry_renamed_range",
        "expiry_clock_reset_at_pending_entry",
        "hidden_renormalization",
    ],
}


EXTERNAL_AUDIT_FILTER = {
    "input_path": r"C:\Users\MSI\Downloads\auditoria_86_reglas_motor_futuros.md",
    "accepted_in_m2": [
        {
            "detail": (
                "Pending no-entry must remain separate from expiry after entry."
            ),
            "effect": "Integrated into the two-stage event tree.",
        },
        {
            "detail": (
                "Invalid horizons and missing data must block instead of "
                "falling back silently."
            ),
            "effect": "Reinforces existing M2 invariants.",
        },
    ],
    "deferred_without_authorization": [
        {
            "detail": "Time-normalized CVD/flow windows.",
            "target_phase": "M3-M4",
        },
        {
            "detail": "Robust funding percentiles by pair/horizon.",
            "target_phase": "M4",
        },
        {
            "detail": "Purged splits, embargo and unseen assets.",
            "target_phase": "M8",
        },
        {
            "detail": "Account fees, depth impact and funding periods.",
            "target_phase": "M3-M4",
        },
    ],
    "discarded_or_not_adopted": [
        {
            "detail": "General 3-60 hour horizon.",
            "reason": "Contradicts the three approved profiles.",
        },
        {
            "detail": "Predetermine logistic/GBM after M2.",
            "reason": "Method selection belongs to M6.",
        },
        {
            "detail": "Retain current score rules as features.",
            "reason": (
                "Only raw data or newly defined transformations may survive; "
                "current thresholds and points remain unauthorized."
            ),
        },
        {
            "detail": "Treat HyperPerps as an official Hyperliquid heatmap.",
            "reason": "Provider and venue scope must remain distinct.",
        },
    ],
}


def build_contract() -> dict[str, Any]:
    source_paths = [
        ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
        ROOT / "CONTRATO_FASE_1_MOTOR_ANALISIS.md",
        ROOT / "auditorias_motor" / "invariantes_coherencia_motor_v0_1.json",
        ROOT / "auditorias_motor" / "contrato_challenger_alcanzabilidad.md",
        ROOT / "auditorias_motor" / "matriz_decisiones_m1_v0_1.json",
    ]
    payload: dict[str, Any] = {
        "semantic_version": SEMANTIC_VERSION,
        "phase": "M2",
        "status": "completed_owner_approved",
        "approved_at": "2026-07-27",
        "purpose": (
            "Define the mathematical meaning, geometry, clocks, event tree "
            "and invariants required before any new predictive formula."
        ),
        "scope": {
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m3_started": False,
            "probabilistic_method_selected": False,
        },
        "supersession_on_approval": {
            "document": (
                "auditorias_motor/contrato_challenger_alcanzabilidad.md"
            ),
            "scope": (
                "Pending-order semantics and premature multinomial baseline "
                "selection only."
            ),
            "preserved": (
                "Pre-trade clock, signed log geometry, data blocking, "
                "traceability and production isolation."
            ),
        },
        "time": {
            "time_zero": "analysis_at",
            "data_rule": "data_cutoff_at <= analysis_at",
            "expiry_formula": "expiry_at=analysis_at+horizon_seconds",
            "pending_clock_restart": False,
            "profiles_seconds": {
                key: {"minimum": value[0], "maximum": value[1]}
                for key, value in HORIZON_LIMITS_SECONDS.items()
            },
        },
        "geometry": {
            "long": "stop_loss < entry < take_profit",
            "short": "take_profit < entry < stop_loss",
            "side_sign": "long=+1; short=-1",
            "tp_log_distance": "side_sign*ln(take_profit/entry)",
            "sl_log_distance": "-side_sign*ln(stop_loss/entry)",
            "volatility_normalization": (
                "z_tp=tp_log_distance/sigma_H; "
                "z_sl=sl_log_distance/sigma_H; finite sigma_H>0 must represent "
                "an approved log-return volatility scale matched to the exact "
                "horizon. M3 approves its data and M4 its estimator."
            ),
        },
        "event_tree": {
            "stage_1": (
                "entry_executed_by_expiry vs no_entry; for an ideal market "
                "entry the semantic baseline is entry probability 1."
            ),
            "stage_2_given_entry": list(CONDITIONAL_OUTCOMES),
            "overall": list(OVERALL_OUTCOMES),
            "visible": list(VISIBLE_OUTCOMES),
            "clock": (
                "All stages share the absolute expiry fixed at analysis_at."
            ),
            "execution_boundary": (
                "Touch, trigger and confirmed fill must be defined by the "
                "future execution contract; they cannot be conflated silently."
            ),
        },
        "ambiguity_and_censoring": {
            "ambiguous": (
                "Both barriers appear in the same observation and their order "
                "cannot be reconstructed."
            ),
            "censored": (
                "Coverage ends, data are missing, or manual closure occurs "
                "before a reconstructable terminal event."
            ),
            "policy": (
                "Record both states; never force them into TP, SL, expiry or "
                "no_entry."
            ),
        },
        "output_contract": OUTPUT_CONTRACT,
        "invariants": INVARIANTS,
        "edge_cases": EDGE_CASES,
        "external_audit_filter": EXTERNAL_AUDIT_FILTER,
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in source_paths
        ],
    }
    payload["contract_sha256"] = sha256_text(
        canonical_json(
            {
                "time": payload["time"],
                "geometry": payload["geometry"],
                "event_tree": payload["event_tree"],
                "ambiguity_and_censoring": payload[
                    "ambiguity_and_censoring"
                ],
                "output_contract": payload["output_contract"],
                "invariants": payload["invariants"],
                "edge_cases": payload["edge_cases"],
            }
        )
    )
    return payload


def build_current_engine_audit() -> dict[str, Any]:
    discontinuity_a = current_price_vs_entry_bias(
        "short", 99.999999, 100.0
    )
    discontinuity_b = current_price_vs_entry_bias("short", 100.0, 100.0)
    residual = current_residual_probabilities(0.74, 0.22)
    unknown_profile = analysis_engine.time_horizon_profile(
        "invalid_m2_horizon"
    )
    short_profile = analysis_engine.time_horizon_profile("intraday_short")
    empty = data_engine.CandleSet(
        interval="5m",
        closes=[],
        highs=[],
        lows=[],
        volumes=[],
        taker_buy_volumes=[],
    )
    missing_defaults = data_engine.summarize_timeframe(empty, 100.0)
    trade_plan_fields = set(analysis_engine.TradeProposal.__dataclass_fields__)

    findings = [
        {
            "id": "M2-CURRENT-FAIL-01",
            "severity": "critical",
            "invariants": [
                "M2-INV-OUTPUT-01",
                "M2-INV-OUTCOME-01",
            ],
            "observation": {
                "probabilities": residual,
                "mass": sum(residual.values()),
            },
            "reason": "The residual 5% SL floor can create mass > 1.",
            "status": "fail",
            "source_refs": ["analysis_engine.py:273", "analysis_engine.py:293"],
        },
        {
            "id": "M2-CURRENT-FAIL-02",
            "severity": "critical",
            "invariants": ["M2-INV-CONTINUITY-01"],
            "observation": {
                "price_a": 99.999999,
                "bias_a": discontinuity_a,
                "price_b": 100.0,
                "bias_b": discontinuity_b,
                "jump": discontinuity_b - discontinuity_a,
                "historical_case": "analyses 872/873",
            },
            "reason": (
                "An infinitesimal price change causes a 5-point score jump."
            ),
            "status": "fail",
            "source_refs": ["analysis_engine.py:186-193"],
        },
        {
            "id": "M2-CURRENT-FAIL-03",
            "severity": "critical",
            "invariants": ["M2-INV-HORIZON-01"],
            "observation": {
                "trade_proposal_fields": sorted(trade_plan_fields),
                "horizon_seconds_present": (
                    "horizon_seconds" in trade_plan_fields
                ),
            },
            "reason": (
                "The production TradeProposal has only a category, not an "
                "exact expiry duration."
            ),
            "status": "fail",
            "source_refs": ["analysis_engine.py:83-95"],
        },
        {
            "id": "M2-CURRENT-FAIL-04",
            "severity": "high",
            "invariants": ["M2-INV-HORIZON-01"],
            "observation": {
                "invalid_equals_intraday_short": (
                    unknown_profile == short_profile
                ),
                "resolved_label": unknown_profile["label"],
            },
            "reason": (
                "An unknown horizon silently becomes intraday_short."
            ),
            "status": "fail",
            "source_refs": ["analysis_engine.py:104-105"],
        },
        {
            "id": "M2-CURRENT-FAIL-05",
            "severity": "critical",
            "invariants": ["M2-INV-DATA-01"],
            "observation": {
                "rsi_14": missing_defaults["rsi_14"],
                "ema_21": missing_defaults["ema_21"],
                "volume_ratio": missing_defaults["volume_ratio"],
                "ema_stack": missing_defaults["ema_stack"],
            },
            "reason": (
                "Missing candles are converted into apparently neutral "
                "technical evidence."
            ),
            "status": "fail",
            "source_refs": ["data_engine.py:104-131"],
        },
        {
            "id": "M2-CURRENT-FAIL-06",
            "severity": "critical",
            "invariants": [
                "M2-INV-ACTIVATION-01",
                "M2-INV-OUTCOME-02",
            ],
            "observation": {
                "current_field": "range_probability",
                "mixed_meanings": [
                    "market_range",
                    "non_resolution",
                    "pending_no_activation",
                ],
            },
            "reason": (
                "Pending no-entry is added to range instead of remaining an "
                "independent event."
            ),
            "status": "fail",
            "source_refs": [
                "analysis_engine.py:268-272",
                "analysis_engine.py:1406-1411",
            ],
        },
        {
            "id": "M2-CURRENT-FAIL-07",
            "severity": "high",
            "invariants": ["M2-INV-SEPARATION-01"],
            "observation": {
                "execution_or_cost_inputs_in_tp_score": [
                    "spread/liquidity_penalty",
                    "funding_penalty",
                    "funding_relative_penalty",
                ],
            },
            "reason": (
                "Execution/cost concepts directly alter the market path score."
            ),
            "status": "fail",
            "source_refs": ["analysis_engine.py:253-264"],
        },
        {
            "id": "M2-CURRENT-FAIL-08",
            "severity": "critical",
            "invariants": ["M2-INV-OUTPUT-01"],
            "observation": {
                "construction": "0.5 + manual biases - penalties + caps",
            },
            "reason": (
                "The output is a heuristic score without a documented "
                "probabilistic derivation."
            ),
            "status": "fail",
            "source_refs": ["analysis_engine.py:238-293"],
        },
        {
            "id": "M2-CURRENT-FAIL-09",
            "severity": "high",
            "invariants": ["M2-INV-TRACE-01"],
            "observation": {
                "bands": "fixed width 0.04/0.06/0.08 by contradiction",
            },
            "reason": (
                "Displayed bands are not uncertainty intervals derived from "
                "evidence."
            ),
            "status": "fail",
            "source_refs": ["analysis_engine.py:1857-1873"],
        },
    ]
    return {
        "audit_version": AUDIT_VERSION,
        "semantic_version": SEMANTIC_VERSION,
        "status": "current_engine_fails_m2_contract_as_expected",
        "purpose": (
            "Prove that M2 is a specification boundary, not a claim that the "
            "current production scoring already complies."
        ),
        "summary": {
            "findings": len(findings),
            "failures": sum(item["status"] == "fail" for item in findings),
            "critical": sum(
                item["severity"] == "critical" for item in findings
            ),
            "production_modified": False,
        },
        "findings": findings,
    }


def render_report(contract: dict[str, Any], audit: dict[str, Any]) -> str:
    lines = [
        "# M2 - Semantica, geometria e invariantes del resultado",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADA Y APROBADA EL 2026-07-27",
        "",
        "## 1. Limite de la fase",
        "",
        "M2 define que debe significar el resultado antes de elegir datos, reglas",
        "o modelo. No crea un motor nuevo, no selecciona regresion, GBM, first",
        "passage ni otro metodo, y no modifica el scoring productivo.",
        "",
        "La auditoria externa de las 86 reglas se usa solo como apoyo. Se integra",
        "la separacion entre no entrada y expiracion posterior a entrada. Las",
        "recomendaciones de datos, features, costes y validacion se aplazan a su",
        "fase. Se descartan 3-60 h y cualquier eleccion anticipada de modelo.",
        "",
        "## 2. Tiempo cero y horizonte",
        "",
        "- `analysis_at` es el tiempo cero pre-trade.",
        "- `data_cutoff_at <= analysis_at` para toda evidencia predictiva.",
        "- Es obligatorio `horizon_seconds` dentro del marco elegido.",
        "- `expiry_at = analysis_at + horizon_seconds`.",
        "- El reloj no se reinicia si una orden pendiente entra tarde.",
        "- No existe fallback a 3-60 h ni a otro marco.",
        "",
        "| Marco | Minimo | Maximo |",
        "|---|---:|---:|",
        "| `intraday_short` | 30 min | 4 h |",
        "| `intraday_wide` | 4 h | 24 h |",
        "| `short_swing` | 1 dia | 7 dias |",
        "",
        "## 3. Geometria",
        "",
        "```text",
        "s = +1 para long; -1 para short",
        "d_tp = s * ln(TP / entrada)",
        "d_sl = -s * ln(SL / entrada)",
        "z_tp = d_tp / sigma_H",
        "z_sl = d_sl / sigma_H",
        "```",
        "",
        "Long exige `SL < entrada < TP`; short exige `TP < entrada < SL`.",
        "Las dos distancias son positivas y simetricas. `sigma_H` debe ser una",
        "escala positiva de volatilidad de retornos logaritmicos correspondiente",
        "al horizonte exacto. Si falta o no es valida, la probabilidad se",
        "bloquea. M3 debe aprobar el dato y M4 definir el estimador antes de",
        "que M6 lo integre; M2 no inventa aqui ninguna de esas decisiones.",
        "",
        "## 4. Arbol de eventos",
        "",
        "Para entrada a mercado, el baseline semantico ideal usa `P(entrada)=1`.",
        "Para una orden pendiente se separa primero:",
        "",
        "```text",
        "entrada ejecutada antes del vencimiento",
        "no_entry: entrada no ejecutada antes del vencimiento",
        "```",
        "",
        "Condicionado a entrada ejecutada:",
        "",
        "```text",
        "TP_first",
        "SL_first",
        "expiry_after_entry",
        "```",
        "",
        "Las probabilidades globales son:",
        "",
        "```text",
        "P(TP_first)            = P(entry) * P(TP_first | entry)",
        "P(SL_first)            = P(entry) * P(SL_first | entry)",
        "P(expiry_after_entry)  = P(entry) * P(expiry_after_entry | entry)",
        "P(no_entry)            = 1 - P(entry)",
        "```",
        "",
        "Las cuatro suman uno. La interfaz mantiene como resultados principales",
        "`P(TP_first)` y `P(SL_first)` y muestra:",
        "",
        "```text",
        "P(unresolved) = P(expiry_after_entry) + P(no_entry)",
        "P(TP_first) + P(SL_first) + P(unresolved) = 1",
        "```",
        "",
        "`no_entry` y `expiry_after_entry` nunca se confunden en la traza.",
        "Touch, trigger y fill deberan definirse en el contrato de ejecucion;",
        "M2 prohibe tratarlos como sinonimos silenciosos.",
        "",
        "## 5. Ambiguedad y censura",
        "",
        "- TP y SL en la misma observacion sin secuencia resoluble: ambiguo.",
        "- Fin de cobertura, huecos o cierre manual previo: censurado.",
        "- Ambos estados se conservan y no se fuerzan a ningun outcome.",
        "- El outcome posterior nunca reescribe el snapshot pre-trade.",
        "",
        f"## 6. Invariantes ({len(contract['invariants'])})",
        "",
        "| ID | Categoria | Exigencia |",
        "|---|---|---|",
    ]
    for item in contract["invariants"]:
        lines.append(
            f"| `{item['id']}` | `{item['category']}` | "
            f"{item['requirement']} |"
        )
    lines.extend(
        [
            "",
            f"## 7. Casos limite ({len(contract['edge_cases'])})",
            "",
            "| ID | Caso | Resultado exigido |",
            "|---|---|---|",
        ]
    )
    for item in contract["edge_cases"]:
        expected = (
            canonical_json(item["expected"])
            if isinstance(item["expected"], dict)
            else item["expected"]
        )
        lines.append(f"| `{item['id']}` | `{item['name']}` | `{expected}` |")
    lines.extend(
        [
            "",
            "El caso `M2-CASE-010` conserva expresamente la reproduccion 872/873:",
            "pasar el precio short de `99.999999` a `100` con entrada `100` no",
            "puede cambiar cinco puntos una supuesta probabilidad.",
            "",
            "## 8. Contrato de salida",
            "",
            "Una salida aprobable debe declarar identidad, reloj, geometria,",
            "distribucion de entrada, outcomes condicionales, outcomes globales,",
            "las tres masas, calidad de datos, metodo/version y bloqueos.",
            "",
            "Estados permitidos:",
            "",
            "- `probability_available`;",
            "- `blocked`;",
            "- `insufficient_evidence`.",
            "",
            "Quedan prohibidos puntos manuales presentados como probabilidad, SL",
            "residual con suelo, fallback silencioso, ausencia neutral, mezclar",
            "no entrada con rango, reiniciar el reloj y renormalizar ocultando",
            "eventos.",
            "",
            "## 9. Resultado contra el motor actual",
            "",
            f"El scoring productivo falla **{audit['summary']['failures']}**",
            "comprobaciones M2, de ellas",
            f"**{audit['summary']['critical']}** criticas. Es el resultado",
            "esperado: M2 especifica el contrato que la revision futura debera",
            "cumplir; no certifica el score vigente.",
            "",
            "| Hallazgo | Severidad | Motivo |",
            "|---|---|---|",
        ]
    )
    for finding in audit["findings"]:
        lines.append(
            f"| `{finding['id']}` | `{finding['severity']}` | "
            f"{finding['reason']} |"
        )
    lines.extend(
        [
            "",
            "## 10. Relacion con E1.5",
            "",
            "Se conservan del contrato E1.5: tiempo cero pre-trade, distancias",
            "logaritmicas, horizonte concreto, bloqueo por datos, traza y",
            "aislamiento de produccion.",
            "",
            "La aprobacion de M2 supera dos puntos de E1.5:",
            "",
            "1. una orden pendiente no activada ya no se mezcla con expiracion",
            "   despues de entrada;",
            "2. el baseline multinomial deja de estar preseleccionado; M6 debera",
            "   comparar y justificar el metodo.",
            "",
            "`challenger_engine.py` sigue siendo infraestructura inerte",
            "`contract-only`; M2 no lo modifica ni lo convierte en motor nuevo.",
            "",
            "## 11. Estado y siguiente fase",
            "",
            f"SHA-256 del contrato: `{contract['contract_sha256']}`.",
            "",
            "M2 queda completada y aprobada expresamente por el propietario el",
            "2026-07-27. M3 no se ha iniciado y es la siguiente fase:",
            "contratos y auditoria de datos pre-trade.",
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
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    contract = build_contract()
    audit = build_current_engine_audit()
    report = render_report(contract, audit)
    write_or_check(
        args.contract,
        json.dumps(contract, ensure_ascii=True, indent=2) + "\n",
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
