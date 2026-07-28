from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite, log, sqrt
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M2_PATH = AUDIT_DIR / "contrato_semantico_m2_v0_1.json"
M3_CATALOG_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
M4_RECONCILIATION_PATH = (
    AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json"
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "catalogo_alcanzabilidad_m4_2_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_2_alcanzabilidad_enmienda_v0_2.md"
)

VERSION = "M4.2-reachability-v0.2"
RULE_VERSION = "0.2"
MIN_RETURNS_PER_HORIZON = 24
PERIOD_RELEASE_GRACE_MS = 60_000

SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZON_LIMITS_SECONDS = {
    "intraday_short": (30 * 60, 4 * 60 * 60),
    "intraday_wide": (4 * 60 * 60, 24 * 60 * 60),
    "short_swing": (24 * 60 * 60, 7 * 24 * 60 * 60),
}
PROFILE_INTERVALS_SECONDS = {
    "intraday_short": (60, 180, 300, 900),
    "intraday_wide": (300, 900, 1800, 3600),
    "short_swing": (3600, 7200, 14400, 21600, 28800, 43200, 86400),
}
INTERVAL_NAMES = {
    60: "1m",
    180: "3m",
    300: "5m",
    900: "15m",
    1800: "30m",
    3600: "1h",
    7200: "2h",
    14400: "4h",
    21600: "6h",
    28800: "8h",
    43200: "12h",
    86400: "1d",
}

SOURCE_REGISTRY = (
    {
        "id": "M2-SEMANTIC-CONTRACT",
        "type": "approved_internal_contract",
        "title": "M2 - Semantica, geometria e invariantes",
        "url": None,
        "supported_claim": (
            "Long/short barrier geometry, exact horizon and mandatory "
            "normalization by an approved horizon log-volatility scale."
        ),
        "does_not_support": "A volatility estimator or probability model.",
    },
    {
        "id": "M3-DATA-CONTRACTS",
        "type": "approved_internal_contract",
        "title": "M3 - Contratos de datos pre-trade",
        "url": None,
        "supported_claim": (
            "Plan identity, closed Binance USD-M klines, timestamps, "
            "freshness and missing-data behavior."
        ),
        "does_not_support": "Predictive value of price history.",
    },
    {
        "id": "BINANCE-USDM-KLINES",
        "type": "official_provider_documentation",
        "title": "Binance USD-M Futures Kline/Candlestick Data",
        "url": (
            "https://developers.binance.com/en/docs/catalog/"
            "core-trading-derivatives-trading-usd-s-m-futures/api/"
            "rest-api/market-data"
        ),
        "supported_claim": "Kline fields, intervals, timestamps and units.",
        "does_not_support": "Volatility forecasts or TP/SL prediction.",
    },
    {
        "id": "ANDERSEN-BOLLERSLEV-DIEBOLD-LABYS-2003",
        "type": "primary_academic_publication",
        "title": "Modeling and Forecasting Realized Volatility",
        "url": "https://doi.org/10.1111/1468-0262.00418",
        "supported_claim": (
            "Realized volatility constructed from high-frequency returns is "
            "linked to quadratic variation and can be modeled over time."
        ),
        "does_not_support": (
            "Using one lagged horizon as an exact forecast for crypto, a "
            "universal sampling interval, or a TP/SL probability."
        ),
    },
    {
        "id": "POETZELBERGER-WANG-2001",
        "type": "primary_academic_publication",
        "title": "Boundary Crossing Probability for Brownian Motion",
        "url": "https://doi.org/10.1239/jap/996986650",
        "supported_claim": (
            "Boundary crossing is a path-dependent first-passage problem "
            "that requires a specified stochastic process and boundary."
        ),
        "does_not_support": (
            "Brownian motion as an accepted crypto model or any project "
            "probability before M6."
        ),
    },
    {
        "id": "XIE-ET-AL-2019-BITCOIN-RV",
        "type": "primary_academic_publication",
        "title": "Forecast Bitcoin Volatility with Least Squares Model Averaging",
        "url": "https://doi.org/10.3390/econometrics7030040",
        "supported_claim": (
            "Bitcoin realized-volatility forecasting is an empirical model "
            "selection problem with competing specifications."
        ),
        "does_not_support": (
            "Transfer to all six pairs, barrier probabilities, or a fixed "
            "project estimator without independent validation."
        ),
    },
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def finite_positive(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
        and float(value) > 0
    )


def validate_horizon(time_horizon: str, horizon_seconds: int) -> None:
    if time_horizon not in HORIZON_LIMITS_SECONDS:
        raise ValueError("invalid_time_horizon")
    if (
        not isinstance(horizon_seconds, int)
        or isinstance(horizon_seconds, bool)
    ):
        raise ValueError("invalid_horizon_seconds")
    lower, upper = HORIZON_LIMITS_SECONDS[time_horizon]
    if not lower <= horizon_seconds <= upper:
        raise ValueError("horizon_seconds_out_of_profile")


def select_sampling_interval(
    time_horizon: str,
    horizon_seconds: int,
) -> dict:
    validate_horizon(time_horizon, horizon_seconds)
    eligible = [
        interval_seconds
        for interval_seconds in PROFILE_INTERVALS_SECONDS[time_horizon]
        if horizon_seconds % interval_seconds == 0
        and horizon_seconds // interval_seconds
        >= MIN_RETURNS_PER_HORIZON
    ]
    if not eligible:
        raise ValueError("horizon_not_aligned_to_supported_interval")
    interval_seconds = max(eligible)
    return {
        "interval": INTERVAL_NAMES[interval_seconds],
        "interval_seconds": interval_seconds,
        "returns_per_horizon": horizon_seconds // interval_seconds,
        "selection_policy": (
            "largest_supported_exact_divisor_with_at_least_24_returns"
        ),
    }


def derive_plan_geometry(
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    horizon_seconds: int,
) -> dict:
    if side not in {"long", "short"}:
        raise ValueError("invalid_side")
    if not all(
        finite_positive(value)
        for value in (entry, take_profit, stop_loss)
    ):
        raise ValueError("invalid_price")
    valid_geometry = (
        stop_loss < entry < take_profit
        if side == "long"
        else take_profit < entry < stop_loss
    )
    if not valid_geometry:
        raise ValueError("invalid_barrier_geometry")
    if horizon_seconds <= 0:
        raise ValueError("invalid_horizon_seconds")
    side_sign = 1 if side == "long" else -1
    tp_log_distance = side_sign * log(take_profit / entry)
    sl_log_distance = -side_sign * log(stop_loss / entry)
    return {
        "side_sign": side_sign,
        "tp_log_distance": tp_log_distance,
        "sl_log_distance": sl_log_distance,
        "log_horizon_seconds": log(horizon_seconds),
        "horizon_seconds": horizon_seconds,
    }


def closed_log_returns(closes: list[float]) -> list[float]:
    if len(closes) < 2:
        raise ValueError("insufficient_closes")
    parsed = []
    for value in closes:
        if not finite_positive(value):
            raise ValueError("invalid_close")
        parsed.append(float(value))
    return [
        log(parsed[index] / parsed[index - 1])
        for index in range(1, len(parsed))
    ]


def horizon_realized_volatility(
    *,
    closes: list[float],
    close_times_ms: list[int],
    analysis_at_ms: int,
    time_horizon: str,
    horizon_seconds: int,
    interval_seconds: int,
) -> dict:
    selection = select_sampling_interval(time_horizon, horizon_seconds)
    if interval_seconds != selection["interval_seconds"]:
        raise ValueError("interval_does_not_match_policy")
    required_returns = selection["returns_per_horizon"]
    required_closes = required_returns + 1
    if len(closes) != len(close_times_ms):
        raise ValueError("close_time_length_mismatch")
    if len(closes) < required_closes:
        raise ValueError("insufficient_horizon_history")
    window_closes = closes[-required_closes:]
    window_times = close_times_ms[-required_closes:]
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in window_times
    ):
        raise ValueError("invalid_close_time")
    expected_step_ms = interval_seconds * 1000
    if any(
        right - left != expected_step_ms
        for left, right in zip(window_times, window_times[1:])
    ):
        raise ValueError("kline_gap_or_misalignment")
    latest_close_ms = window_times[-1]
    if latest_close_ms > analysis_at_ms:
        raise ValueError("future_closed_bar")
    if (
        analysis_at_ms - latest_close_ms
        > expected_step_ms + PERIOD_RELEASE_GRACE_MS
    ):
        raise ValueError("latest_closed_bar_stale")
    returns = closed_log_returns(window_closes)
    realized_variance = sum(value * value for value in returns)
    realized_volatility = sqrt(realized_variance)
    return {
        "interval": selection["interval"],
        "interval_seconds": interval_seconds,
        "horizon_seconds": horizon_seconds,
        "return_count": len(returns),
        "window_start_close_time_ms": window_times[0],
        "window_end_close_time_ms": window_times[-1],
        "realized_variance": realized_variance,
        "realized_volatility": realized_volatility,
        "meaning": "observed_log_volatility_over_previous_exact_horizon",
        "forecast_status": "not_a_forecast",
    }


def normalize_barrier_reachability(
    geometry: dict,
    horizon_volatility: float,
) -> dict:
    if not finite_positive(horizon_volatility):
        raise ValueError("invalid_horizon_volatility")
    tp_distance = geometry.get("tp_log_distance")
    sl_distance = geometry.get("sl_log_distance")
    if not finite_positive(tp_distance) or not finite_positive(sl_distance):
        raise ValueError("invalid_barrier_distance")
    sigma = float(horizon_volatility)
    return {
        "z_tp": float(tp_distance) / sigma,
        "z_sl": float(sl_distance) / sigma,
        "distance_balance_log_ratio": log(
            float(tp_distance) / float(sl_distance)
        ),
        "probability": None,
        "interpretation": (
            "dimensionless_geometry_only; higher_z_is_farther_holding_the_"
            "future_path_law_fixed"
        ),
    }


def pending_activation_distance(
    *,
    entry_type: str,
    side: str,
    trigger_condition: str | None,
    current_price: float,
    entry: float,
    horizon_volatility: float,
) -> dict:
    if entry_type not in {"market", "pending"}:
        raise ValueError("invalid_entry_type")
    if side not in {"long", "short"}:
        raise ValueError("invalid_side")
    if not finite_positive(current_price) or not finite_positive(entry):
        raise ValueError("invalid_price")
    if not finite_positive(horizon_volatility):
        raise ValueError("invalid_horizon_volatility")
    if entry_type == "market":
        if trigger_condition is not None:
            raise ValueError("market_entry_has_trigger")
        return {
            "activation_status": "active_at_analysis",
            "entry_log_distance": 0.0,
            "z_entry": 0.0,
            "entry_order_type": "market",
            "activation_probability": None,
        }
    if trigger_condition not in {"price_lte", "price_gte"}:
        raise ValueError("pending_trigger_required")
    trigger_satisfied = (
        current_price <= entry
        if trigger_condition == "price_lte"
        else current_price >= entry
    )
    if trigger_satisfied:
        raise ValueError("pending_trigger_already_satisfied")
    order_type = (
        "limit_pullback"
        if (
            (side == "long" and trigger_condition == "price_lte")
            or (side == "short" and trigger_condition == "price_gte")
        )
        else "stop_breakout"
        if side == "long"
        else "stop_breakdown"
    )
    distance = abs(log(entry / current_price))
    return {
        "activation_status": "waiting_for_trigger",
        "entry_log_distance": distance,
        "z_entry": distance / float(horizon_volatility),
        "entry_order_type": order_type,
        "activation_probability": None,
    }


def rule_card(
    rule_id: str,
    name: str,
    *,
    blocks: list[int],
    objective: str,
    rule_type: str,
    data_contracts: list[str],
    formula: list[str],
    pseudocode: list[str],
    normalization: str,
    activation: list[str],
    non_application: list[str],
    source_support: list[dict],
    unsupported_claims: list[str],
    project_hypothesis: dict | None,
    expected_relation: str,
    related_rules: list[str],
    double_counting: str,
    missing_behavior: str,
    tests_and_invariants: list[str],
    trace_fields: list[str],
    refutation: list[str],
) -> dict:
    return {
        "id": rule_id,
        "version": RULE_VERSION,
        "name": name,
        "analytical_blocks": blocks,
        "concrete_objective": objective,
        "rule_type": rule_type,
        "raw_data_and_provider": {
            "provider": "user_plan_and_binance_usdm",
            "m3_data_contract_ids": data_contracts,
        },
        "market_symbol_timestamp_unit_freshness": {
            "market": "Binance USD-M perpetual",
            "symbols": list(SYMBOLS),
            "timestamps": (
                "M3 provider close_time plus requested_at/received_at; "
                "all <= analysis_at"
            ),
            "price_unit": "quote_asset_per_base",
            "return_unit": "natural_log_return",
            "freshness": "M3-DATA-005 closed-period contract",
        },
        "exact_transformation_and_formula": formula,
        "pseudocode": pseudocode,
        "cross_pair_normalization": normalization,
        "applicable_horizons": list(HORIZON_LIMITS_SECONDS),
        "activation_conditions": activation,
        "non_application_conditions": non_application,
        "source_and_exact_supported_claim": source_support,
        "claims_not_supported_by_source": unsupported_claims,
        "separate_predictive_hypothesis": project_hypothesis,
        "expected_relation_to_tp_sl_or_expiry": expected_relation,
        "related_rules": related_rules,
        "double_counting_control": double_counting,
        "missing_data_behavior": missing_behavior,
        "unit_tests_limits_and_invariants": tests_and_invariants,
        "trace_output": trace_fields,
        "refutation_suspension_or_withdrawal": refutation,
        "lifecycle_status": "documented_candidate_no_predictive_weight",
        "direct_probability_effect_authorized": False,
        "numeric_weight_authorized": False,
        "production_authorized": False,
    }


def build_rules() -> list[dict]:
    common_unsupported = [
        "No source supplies a project probability, score, weight or threshold.",
        "No source proves transfer to all six pairs and three horizons.",
    ]
    return [
        rule_card(
            "M4-RULE-HORIZON-SAMPLING-001",
            "Seleccion exacta de intervalo para el horizonte",
            blocks=[26],
            objective=(
                "Select a closed-kline interval that divides the exact horizon "
                "without temporal interpolation."
            ),
            rule_type="deterministic_policy",
            data_contracts=["M3-DATA-001", "M3-DATA-005"],
            formula=[
                "I={delta in profile_intervals: H mod delta=0 and H/delta>=24}",
                "delta*=max(I)",
                "N_H=H/delta*",
            ],
            pseudocode=[
                "validate horizon profile and exact H",
                "retain supported intervals that divide H exactly",
                "retain intervals with at least 24 returns",
                "select the largest retained interval or block",
            ],
            normalization=(
                "Same algorithm for every pair; only H and profile select delta."
            ),
            activation=["valid exact horizon inside approved profile"],
            non_application=["no supported exact divisor with at least 24 returns"],
            source_support=[
                {
                    "source_id": "BINANCE-USDM-KLINES",
                    "level": "definition",
                    "claim": "Supported kline intervals and timestamp fields.",
                }
            ],
            unsupported_claims=[
                *common_unsupported,
                "The minimum of 24 returns is project policy, not an academic optimum.",
            ],
            project_hypothesis=None,
            expected_relation="No TP/SL direction; data-resolution policy only.",
            related_rules=["M4-RULE-REALIZED-VOLATILITY-001"],
            double_counting="Produces one interval identity, no evidence.",
            missing_behavior="Block reachability family.",
            tests_and_invariants=[
                "H is never rounded",
                "delta divides H exactly",
                "N_H>=24",
                "selection is pair-independent",
            ],
            trace_fields=[
                "time_horizon",
                "horizon_seconds",
                "interval",
                "interval_seconds",
                "returns_per_horizon",
                "selection_policy",
            ],
            refutation=[
                "Suspend if M7 shows unstable or aliased RV at the selected grid.",
                "Change only by versioned M4 amendment before empirical testing.",
            ],
        ),
        rule_card(
            "M4-RULE-PLAN-GEOMETRY-001",
            "Geometria logaritmica long/short",
            blocks=[26, 28],
            objective="Represent TP and SL distance symmetrically across sides.",
            rule_type="deterministic_calculation",
            data_contracts=["M3-DATA-001"],
            formula=[
                "s=+1 long; s=-1 short",
                "d_TP=s*ln(TP/E)",
                "d_SL=-s*ln(SL/E)",
                "valid iff d_TP>0 and d_SL>0",
            ],
            pseudocode=[
                "validate side and positive finite prices",
                "validate side-specific barrier ordering",
                "calculate d_TP and d_SL in log-price space",
            ],
            normalization="Log ratios are dimensionless and scale-invariant.",
            activation=["valid plan geometry"],
            non_application=["invalid side, price or barrier ordering"],
            source_support=[
                {
                    "source_id": "M2-SEMANTIC-CONTRACT",
                    "level": "definition",
                    "claim": "Approved side-symmetric geometry.",
                }
            ],
            unsupported_claims=common_unsupported,
            project_hypothesis=None,
            expected_relation=(
                "Holding all else fixed, a farther same-side barrier cannot be "
                "declared easier to reach."
            ),
            related_rules=["M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002"],
            double_counting="Single canonical geometry for all later blocks.",
            missing_behavior="Block the complete analysis.",
            tests_and_invariants=[
                "long/short mirror symmetry",
                "positive distances",
                "price-scale invariance",
                "continuous response to barrier movement",
            ],
            trace_fields=[
                "side_sign",
                "entry",
                "take_profit",
                "stop_loss",
                "tp_log_distance",
                "sl_log_distance",
            ],
            refutation=["Withdraw any implementation that differs from M2."],
        ),
        rule_card(
            "M4-RULE-LOG-RETURNS-001",
            "Retornos logaritmicos de velas cerradas",
            blocks=[26],
            objective="Create the only return series used by M4.2 volatility.",
            rule_type="deterministic_calculation",
            data_contracts=["M3-DATA-005"],
            formula=["r_i=ln(C_i/C_(i-1))"],
            pseudocode=[
                "take consecutive closed adjusted-free USD-M closes",
                "reject non-positive, missing, stale, future or gapped observations",
                "calculate natural log price ratios",
            ],
            normalization="Dimensionless return; same formula for every pair.",
            activation=["M3-compliant consecutive closed klines"],
            non_application=["gap, open bar, invalid close or insufficient history"],
            source_support=[
                {
                    "source_id": "ANDERSEN-BOLLERSLEV-DIEBOLD-LABYS-2003",
                    "level": "definition",
                    "claim": "High-frequency return inputs for realized volatility.",
                },
                {
                    "source_id": "BINANCE-USDM-KLINES",
                    "level": "definition",
                    "claim": "Close price and close timestamp semantics.",
                },
            ],
            unsupported_claims=common_unsupported,
            project_hypothesis=None,
            expected_relation="No direction or probability by itself.",
            related_rules=["M4-RULE-REALIZED-VOLATILITY-001"],
            double_counting="One canonical return series per selected interval.",
            missing_behavior="Block realized volatility and dependent rules.",
            tests_and_invariants=[
                "constant price gives zero returns",
                "multiplying all prices by a constant does not change returns",
                "gaps and invalid prices block",
            ],
            trace_fields=[
                "close_count",
                "return_count",
                "first_close_time",
                "last_close_time",
                "return_series_hash",
            ],
            refutation=["Withdraw any fallback that inserts zero returns."],
        ),
        rule_card(
            "M4-RULE-REALIZED-VOLATILITY-001",
            "Volatilidad realizada del horizonte anterior",
            blocks=[26],
            objective=(
                "Measure observed log-price variation over the immediately "
                "preceding exact horizon without scaling from another horizon."
            ),
            rule_type="deterministic_measure_with_separate_hypothesis",
            data_contracts=["M3-DATA-001", "M3-DATA-005"],
            formula=[
                "RV_prev(H)=sum_(i=1..N_H)(r_i^2)",
                "sigma_prev(H)=sqrt(RV_prev(H))",
            ],
            pseudocode=[
                "select delta with M4-RULE-HORIZON-SAMPLING-001",
                "take N_H+1 consecutive closes ending at latest closed bar",
                "verify exact H span and M3 freshness",
                "calculate N_H log returns, RV and sigma",
            ],
            normalization=(
                "Log-volatility is dimensionless and calculated over the same "
                "exact H for every pair."
            ),
            activation=["complete previous-H window with at least 24 returns"],
            non_application=[
                "missing/gapped/future/stale bars",
                "zero sigma blocks normalized reachability",
            ],
            source_support=[
                {
                    "source_id": "ANDERSEN-BOLLERSLEV-DIEBOLD-LABYS-2003",
                    "level": "technical_foundation",
                    "claim": "Sum-of-squared high-frequency returns measures RV.",
                },
                {
                    "source_id": "XIE-ET-AL-2019-BITCOIN-RV",
                    "level": "external_predictive_evidence",
                    "claim": (
                        "Bitcoin RV can be forecast, but competing model "
                        "specifications matter."
                    ),
                },
            ],
            unsupported_claims=[
                *common_unsupported,
                "Lagged sigma_prev(H) is not labelled a forecast.",
                "No persistence coefficient is assumed.",
            ],
            project_hypothesis={
                "id": "M4-HYP-REACH-001",
                "status": "proposed_unverified",
                "statement": (
                    "Previous-horizon RV may provide a useful reference scale "
                    "for next-horizon barrier distance."
                ),
                "not_a_claim": (
                    "It is not assumed equal to future volatility and receives "
                    "no probability weight."
                ),
            },
            expected_relation=(
                "Higher sigma lowers both normalized barrier distances; it does "
                "not choose TP versus SL direction."
            ),
            related_rules=[
                "M4-RULE-LOG-RETURNS-001",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            ],
            double_counting=(
                "RV is one scale input. M4.3 regime may classify it but cannot "
                "re-add the same value as independent evidence."
            ),
            missing_behavior="Block all sigma-normalized M4.2 outputs.",
            tests_and_invariants=[
                "exact previous-H span",
                "RV>=0",
                "sigma=sqrt(RV)",
                "scale invariance",
                "no annualization or cross-horizon square-root scaling",
            ],
            trace_fields=[
                "interval",
                "horizon_seconds",
                "return_count",
                "window_start_close_time",
                "window_end_close_time",
                "realized_variance",
                "realized_volatility",
                "forecast_status",
            ],
            refutation=[
                "Reject M4-HYP-REACH-001 if independent evaluation shows no "
                "incremental reachability value or unstable pair behavior.",
                "A future forecast model belongs to M6 and needs a new rule ID.",
            ],
        ),
        rule_card(
            "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
            "Geometria de barreras normalizada por volatilidad",
            blocks=[26, 28],
            objective="Express both barriers in comparable horizon-volatility units.",
            rule_type="deterministic_calculation",
            data_contracts=["M3-DATA-001", "M3-DATA-005"],
            formula=[
                "z_TP=d_TP/sigma_prev(H)",
                "z_SL=d_SL/sigma_prev(H)",
                "b=ln(d_TP/d_SL)",
            ],
            pseudocode=[
                "obtain valid geometry and sigma_prev(H)>0",
                "divide each positive log distance by the common sigma",
                "record balance b without converting it to probability",
            ],
            normalization="Dimensionless z values comparable across price scales.",
            activation=["valid geometry and finite sigma_prev(H)>0"],
            non_application=["invalid geometry, missing history or sigma<=0"],
            source_support=[
                {
                    "source_id": "M2-SEMANTIC-CONTRACT",
                    "level": "definition",
                    "claim": "Mandatory z_TP and z_SL geometry.",
                },
                {
                    "source_id": "POETZELBERGER-WANG-2001",
                    "level": "technical_foundation",
                    "claim": (
                        "Actual crossing probability requires a specified path "
                        "process and boundary treatment."
                    ),
                },
            ],
            unsupported_claims=[
                *common_unsupported,
                "z is not a normal CDF input until M6 selects and validates a model.",
                "No threshold such as one or two sigma is a decision boundary.",
            ],
            project_hypothesis={
                "id": "M4-HYP-REACH-002",
                "status": "mathematical_constraint_for_future_model",
                "statement": (
                    "Holding all other state fixed, increasing only z_TP must "
                    "not increase P(TP first); likewise for z_SL and P(SL first)."
                ),
            },
            expected_relation=(
                "Continuous monotonic geometry constraint, not a probability "
                "or directional signal."
            ),
            related_rules=[
                "M4-RULE-PLAN-GEOMETRY-001",
                "M4-RULE-REALIZED-VOLATILITY-001",
            ],
            double_counting=(
                "Geometry appears once in M6. Raw percentage, ATR bands and "
                "price-vs-entry bonuses cannot re-enter separately."
            ),
            missing_behavior="Block probability publication.",
            tests_and_invariants=[
                "z_TP>0 and z_SL>0",
                "barrier monotonicity",
                "volatility monotonicity",
                "long/short mirror symmetry",
                "continuity",
            ],
            trace_fields=[
                "tp_log_distance",
                "sl_log_distance",
                "sigma_prev_horizon",
                "z_tp",
                "z_sl",
                "distance_balance_log_ratio",
                "probability",
            ],
            refutation=[
                "Any later model violating monotonicity fails M7.",
                "Withdraw any score bands attached directly to z.",
            ],
        ),
        rule_card(
            "M4-RULE-PENDING-ACTIVATION-001",
            "Distancia de activacion para entrada pendiente",
            blocks=[28],
            objective=(
                "Represent the pre-entry barrier separately from TP/SL after "
                "entry under the M2 event tree."
            ),
            rule_type="deterministic_calculation",
            data_contracts=["M3-DATA-001", "M3-DATA-004", "M3-DATA-005"],
            formula=[
                "market: d_entry=0, z_entry=0",
                "pending: d_entry=abs(ln(E/P_analysis))",
                "z_entry=d_entry/sigma_prev(H)",
            ],
            pseudocode=[
                "require entry_type and trigger_condition from the immutable plan",
                "reject a pending trigger already satisfied at analysis_at",
                "calculate distance and z_entry for a waiting trigger",
                "do not calculate activation probability in M4",
            ],
            normalization="Dimensionless log distance over the same sigma_prev(H).",
            activation=["market entry or valid unsatisfied pending trigger"],
            non_application=[
                "missing trigger_condition",
                "pending condition already satisfied",
                "invalid or stale current price",
            ],
            source_support=[
                {
                    "source_id": "M2-SEMANTIC-CONTRACT",
                    "level": "definition",
                    "claim": (
                        "No-entry and post-entry expiry are separate outcomes."
                    ),
                },
                {
                    "source_id": "M3-DATA-CONTRACTS",
                    "level": "definition",
                    "claim": (
                        "Plan trigger, analysis price and timestamps are "
                        "pre-trade data."
                    ),
                },
            ],
            unsupported_claims=[
                *common_unsupported,
                "Distance alone does not define activation probability.",
            ],
            project_hypothesis={
                "id": "M4-HYP-PENDING-001",
                "status": "mathematical_constraint_for_future_model",
                "statement": (
                    "Holding path law fixed, moving an unsatisfied entry trigger "
                    "farther away must not increase activation probability."
                ),
            },
            expected_relation=(
                "Feeds a future P(entry within H) branch; never adds points to "
                "conditional P(TP first | entry)."
            ),
            related_rules=[
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
                "M2 event tree",
            ],
            double_counting=(
                "Entry activation is evaluated once before conditional TP/SL."
            ),
            missing_behavior="Block pending-order probability analysis.",
            tests_and_invariants=[
                "market z_entry=0",
                "pending z_entry>0",
                "trigger direction preserved",
                "already-satisfied pending trigger rejected",
                "activation probability remains null",
            ],
            trace_fields=[
                "entry_type",
                "trigger_condition",
                "entry_order_type",
                "current_price",
                "entry",
                "entry_log_distance",
                "z_entry",
                "activation_status",
                "activation_probability",
            ],
            refutation=[
                "Any future activation model must preserve M2 probability mass.",
                "Withdraw any zone score or fixed activation band.",
            ],
        ),
    ]


def validate_rule_cards(rules: list[dict]) -> None:
    required = {
        "id",
        "version",
        "name",
        "analytical_blocks",
        "concrete_objective",
        "rule_type",
        "raw_data_and_provider",
        "market_symbol_timestamp_unit_freshness",
        "exact_transformation_and_formula",
        "pseudocode",
        "cross_pair_normalization",
        "applicable_horizons",
        "activation_conditions",
        "non_application_conditions",
        "source_and_exact_supported_claim",
        "claims_not_supported_by_source",
        "separate_predictive_hypothesis",
        "expected_relation_to_tp_sl_or_expiry",
        "related_rules",
        "double_counting_control",
        "missing_data_behavior",
        "unit_tests_limits_and_invariants",
        "trace_output",
        "refutation_suspension_or_withdrawal",
        "lifecycle_status",
        "direct_probability_effect_authorized",
        "numeric_weight_authorized",
        "production_authorized",
    }
    ids = [rule["id"] for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_rule_id")
    source_ids = {source["id"] for source in SOURCE_REGISTRY}
    for rule in rules:
        if set(rule) != required:
            raise ValueError(f"incomplete_rule_card:{rule.get('id')}")
        used_sources = {
            item["source_id"]
            for item in rule["source_and_exact_supported_claim"]
        }
        if not used_sources.issubset(source_ids):
            raise ValueError(f"unknown_source:{rule['id']}")
        if (
            rule["direct_probability_effect_authorized"]
            or rule["numeric_weight_authorized"]
            or rule["production_authorized"]
        ):
            raise ValueError(f"unauthorized_effect:{rule['id']}")


def build_catalog() -> dict:
    m2 = read_json(M2_PATH)
    m3 = read_json(M3_CATALOG_PATH)
    reconciliation = read_json(M4_RECONCILIATION_PATH)
    if m2["status"] != "completed_owner_approved":
        raise ValueError("m2_not_approved")
    if m3["status"] != "completed_owner_approved":
        raise ValueError("m3_not_approved")
    clarification_ids = {
        item["id"] for item in m3["post_closure_clarifications"]
    }
    if "M3-CLARIFICATION-001" not in clarification_ids:
        raise ValueError("pending_trigger_contract_not_clarified")
    if reconciliation["scope"]["m4_next_subphase"] != "M4.2":
        raise ValueError("m4_1_does_not_lead_to_m4_2")
    rules = build_rules()
    validate_rule_cards(rules)
    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.2",
        "status": "completed_internal_milestone_m4_still_in_progress",
        "date": "2026-07-27",
        "scope": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZON_LIMITS_SECONDS),
            "rule_cards": len(rules),
            "direct_probability_effects": 0,
            "numeric_weights": 0,
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m5_started": False,
            "m4_next_subphase": "M4.3",
        },
        "operational_sampling_policy": {
            "minimum_returns_per_horizon": MIN_RETURNS_PER_HORIZON,
            "classification": (
                "project resolution policy, not an academic optimum"
            ),
            "horizon_limits_seconds": {
                key: list(value)
                for key, value in HORIZON_LIMITS_SECONDS.items()
            },
            "profile_intervals_seconds": {
                key: list(value)
                for key, value in PROFILE_INTERVALS_SECONDS.items()
            },
            "selection": (
                "largest supported interval dividing H exactly with >=24 returns"
            ),
            "rounding_allowed": False,
        },
        "policy_decision_records": [
            {
                "id": "M4-POLICY-SAMPLING-MIN-RETURNS-001",
                "value": MIN_RETURNS_PER_HORIZON,
                "status": "provisional_project_policy",
                "reason": (
                    "Require a minimally populated exact-H return grid while "
                    "avoiding interpolation."
                ),
                "tradeoff": (
                    "The value is reproducible but is not a published optimum."
                ),
                "future_test": (
                    "M7/M8 preregistered resolution sensitivity; no retuning "
                    "after opening the holdout."
                ),
            }
        ],
        "sources": list(SOURCE_REGISTRY),
        "rules": rules,
        "preregistered_hypotheses": [
            rule["separate_predictive_hypothesis"]
            for rule in rules
            if rule["separate_predictive_hypothesis"] is not None
        ],
        "supersedes_current_elements": {
            "IND-ATR14-CURRENT": (
                "Not used as P0 horizon scale; P1 ATR remains deferred."
            ),
            "IND-PENDING-ZONE": "Replaced by deterministic activation distance.",
            "SCORE-PRICE_VS_ENTRY_BIAS": "Retired; M2 log geometry is canonical.",
            "SCORE-ZONE_PROBABILITY_ADJUSTMENT": (
                "Retired; activation remains a separate future event."
            ),
            "SCORE-VOLATILITY_PENALTY": (
                "Retired; continuous z_TP/z_SL geometry replaces bands."
            ),
            "SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT": (
                "Retired; no-entry and expiry-after-entry remain separate."
            ),
        },
        "summary": {
            "rules": len(rules),
            "deterministic_or_measure_rules": len(rules),
            "hypotheses": sum(
                1
                for rule in rules
                if rule["separate_predictive_hypothesis"] is not None
            ),
            "rules_with_probability_effect": 0,
            "rules_with_numeric_weight": 0,
            "production_modified": False,
        },
        "amendment": {
            "version": "M4.7-amendment-wave-1-v0.2",
            "supersedes_artifact": (
                "auditorias_motor/catalogo_alcanzabilidad_m4_2_v0_1.json"
            ),
            "changes": [
                "rename normalized barrier geometry without probability claim",
                "register the 24-return policy decision",
                "declare canonical payload digest scope",
            ],
            "legacy_rule_id_map": {
                "M4-RULE-BARRIER-REACHABILITY-001": (
                    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002"
                )
            },
        },
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in (
                ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
                M2_PATH,
                M3_CATALOG_PATH,
                M4_RECONCILIATION_PATH,
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "operational_sampling_policy": payload[
                    "operational_sampling_policy"
                ],
                "policy_decision_records": payload[
                    "policy_decision_records"
                ],
                "sources": payload["sources"],
                "rules": payload["rules"],
                "supersedes_current_elements": payload[
                    "supersedes_current_elements"
                ],
            }
        )
    )
    return payload


def render_report(catalog: dict) -> str:
    lines = [
        "# M4.2 - Alcanzabilidad por geometria, volatilidad y horizonte",
        "",
        "Fecha: 2026-07-27",
        "Estado: HITO INTERNO COMPLETADO; M4 SIGUE EN CURSO",
        "",
        "## 1. Resultado",
        "",
        f"- Fichas formales: **{catalog['summary']['rules']}**.",
        f"- Hipotesis separadas: **{catalog['summary']['hypotheses']}**.",
        "- Efectos probabilisticos autorizados: **0**.",
        "- Pesos numericos autorizados: **0**.",
        "- Cambios productivos: **ninguno**.",
        "",
        "M4.2 define calculos y restricciones. No convierte distancia o",
        "volatilidad en porcentajes. La integracion probabilistica pertenece a",
        "M6 y debera respetar monotonicidad, masa y primer cruce de barreras.",
        "",
        "## 2. Formulas",
        "",
        "- Geometria: `d_TP=s*ln(TP/E)` y `d_SL=-s*ln(SL/E)`.",
        "- Retorno: `r_i=ln(C_i/C_(i-1))`.",
        "- Varianza realizada anterior: `RV_prev(H)=sum(r_i^2)`.",
        "- Escala observada: `sigma_prev(H)=sqrt(RV_prev(H))`.",
        "- Alcanzabilidad: `z_TP=d_TP/sigma_prev(H)` y",
        "  `z_SL=d_SL/sigma_prev(H)`.",
        "- Entrada pendiente: `z_entry=abs(ln(E/P_analysis))/sigma_prev(H)`.",
        "",
        "`sigma_prev(H)` se etiqueta como observacion del horizonte anterior,",
        "no como prediccion del siguiente. Su utilidad futura es una hipotesis",
        "prerregistrada que debera verificarse independientemente.",
        "",
        "## 3. Politica temporal",
        "",
        "- El horizonte exacto nunca se redondea.",
        "- El intervalo debe dividir exactamente H.",
        "- Se exigen al menos 24 retornos cerrados dentro de H.",
        "- Se elige el mayor intervalo soportado que cumpla ambas condiciones.",
        "- Huecos, barras abiertas, futuras u obsoletas bloquean la familia.",
        "- La cifra 24 es politica de resolucion del proyecto, no optimo publicado.",
        "",
        "## 4. Reglas",
        "",
        "| ID | Tipo | Bloques | Probabilidad |",
        "|---|---|---|---|",
    ]
    for rule in catalog["rules"]:
        blocks = ", ".join(str(value) for value in rule["analytical_blocks"])
        lines.append(
            f"| `{rule['id']}` | `{rule['rule_type']}` | {blocks} | no |"
        )
    lines.extend(
        [
            "",
            "## 5. Sustituciones",
            "",
        ]
    )
    for current_id, decision_text in catalog[
        "supersedes_current_elements"
    ].items():
        lines.append(f"- `{current_id}`: {decision_text}")
    lines.extend(
        [
            "",
            "## 6. Limites",
            "",
            "- La literatura respalda realized volatility y primer cruce como",
            "  problemas tecnicos, no los porcentajes de esta aplicacion.",
            "- No se presupone persistencia exacta de volatilidad.",
            "- No se presupone Brownian motion, normalidad ni drift constante.",
            "- No se usan ATR, bandas sigma ni thresholds como probabilidades.",
            "- La entrada pendiente conserva `no_entry` separado de la expiracion.",
            "",
            "## 7. Siguiente paso",
            "",
            "`M4.3`: regimen, estructura y jerarquia multi-timeframe. No puede",
            "reutilizar la misma volatilidad o tendencia bajo nombres distintos.",
            "",
            "SHA-256 del payload canonico "
            "(`operational_sampling_policy`, `policy_decision_records`, "
            "`sources`, `rules`, `supersedes_current_elements`): "
            f"`{catalog['canonical_payload_sha256']}`.",
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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    catalog = build_catalog()
    report = render_report(catalog)
    write_or_check(
        args.output,
        json.dumps(catalog, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, report, args.check)


if __name__ == "__main__":
    main()
