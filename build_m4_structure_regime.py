from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite, log
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M3_CATALOG_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
M4_RECONCILIATION_PATH = (
    AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json"
)
M4_REACHABILITY_PATH = (
    AUDIT_DIR / "catalogo_alcanzabilidad_m4_2_v0_2.json"
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "catalogo_regimen_estructura_mtf_m4_3_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_3_regimen_estructura_mtf_enmienda_v0_2.md"
)

VERSION = "M4.3-structure-regime-v0.2"
RULE_VERSION = "0.2"
VOLATILITY_REFERENCE_WINDOWS = 60
MTF_WINDOW_MULTIPLIERS = (1, 2, 4)
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
HORIZONS = ("intraday_short", "intraday_wide", "short_swing")

SOURCES = (
    {
        "id": "M3-DATA-CONTRACTS",
        "type": "approved_internal_contract",
        "url": None,
        "supported_claim": "Closed OHLC timestamps, plan and missing-data policy.",
        "does_not_support": "Trend, regime or level predictiveness.",
    },
    {
        "id": "M4.2-REACHABILITY",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Exact horizon sampling, log returns and previous-horizon RV."
        ),
        "does_not_support": "Directional inference or regime labels.",
    },
    {
        "id": "NIST-SINGLE-EXPONENTIAL-SMOOTHING",
        "type": "institutional_methodology",
        "url": (
            "https://www.itl.nist.gov/div898/handbook/pmc/section4/"
            "pmc431.htm"
        ),
        "supported_claim": (
            "Recursive exponential smoothing and dependence on alpha and "
            "initialization."
        ),
        "does_not_support": (
            "EMA periods 9/21/50/200, crossover signals or crypto returns."
        ),
    },
    {
        "id": "HAMILTON-1989-REGIME-SWITCHING",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.2307/1912559",
        "supported_claim": (
            "Time-series parameters may change through latent regimes that "
            "must be estimated by a specified model."
        ),
        "does_not_support": (
            "Calling arbitrary indicator bands regimes or assigning direction."
        ),
    },
    {
        "id": "CORSI-2009-HAR-RV",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1093/jjfinec/nbp001",
        "supported_claim": (
            "Realized-volatility components across heterogeneous horizons may "
            "contain distinct temporal information."
        ),
        "does_not_support": (
            "The project H/2H/4H price-direction hierarchy or fixed weights."
        ),
    },
    {
        "id": "MOSKOWITZ-OOI-PEDERSEN-2012",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1016/j.jfineco.2011.11.003",
        "supported_claim": (
            "Time-series momentum was documented for 58 traditional futures "
            "at monthly horizons."
        ),
        "does_not_support": (
            "Crypto intraday transfer, TP-first probabilities or EMA stacks."
        ),
    },
    {
        "id": "HUDSON-URQUHART-2021",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1007/s10479-019-03357-1",
        "supported_claim": (
            "Technical-rule results in cryptocurrencies vary by asset and "
            "out-of-sample period; Bitcoin lacked OOS predictability in their test."
        ),
        "does_not_support": (
            "Any selected project rule, period, threshold or pair-wide transfer."
        ),
    },
    {
        "id": "OSLER-2000-SUPPORT-RESISTANCE",
        "type": "primary_institutional_research",
        "url": (
            "https://www.newyorkfed.org/medialibrary/media/research/epr/"
            "00v06n2/0007osle.pdf"
        ),
        "supported_claim": (
            "Published FX support/resistance levels predicted some intraday "
            "trend interruptions, with performance varying by pair and firm."
        ),
        "does_not_support": (
            "Rolling extrema as equivalent levels, crypto transfer or a penalty."
        ),
    },
    {
        "id": "CURCIO-ET-AL-2014-PRICE-MEMORY",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.1038/srep04487",
        "supported_claim": (
            "Local extrema and prior bounces can be studied as price-memory "
            "candidates, with time scale and bounce count as parameters."
        ),
        "does_not_support": (
            "A universal extrema detector or project TP/SL probability."
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


def finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def positive_prices(values: list[float]) -> list[float]:
    if not values:
        raise ValueError("empty_price_series")
    if any(not finite_number(value) or float(value) <= 0 for value in values):
        raise ValueError("invalid_price")
    return [float(value) for value in values]


def exponential_smoother(values: list[float], alpha: float) -> list[float]:
    parsed = positive_prices(values)
    if (
        not finite_number(alpha)
        or not 0 < float(alpha) <= 1
    ):
        raise ValueError("invalid_alpha")
    alpha_value = float(alpha)
    smoothed = [parsed[0]]
    for value in parsed[1:]:
        smoothed.append(
            alpha_value * value
            + (1 - alpha_value) * smoothed[-1]
        )
    return smoothed


def path_structure(closes: list[float]) -> dict:
    parsed = positive_prices(closes)
    if len(parsed) < 2:
        raise ValueError("insufficient_closes")
    returns = [
        log(parsed[index] / parsed[index - 1])
        for index in range(1, len(parsed))
    ]
    displacement = sum(returns)
    total_variation = sum(abs(value) for value in returns)
    if total_variation == 0:
        signed_efficiency = 0.0
        path_status = "flat_observed_path"
    else:
        signed_efficiency = displacement / total_variation
        path_status = "nonflat_observed_path"
    direction = (
        "positive"
        if displacement > 0
        else "negative"
        if displacement < 0
        else "flat"
    )
    return {
        "log_displacement": displacement,
        "total_log_variation": total_variation,
        "path_efficiency": abs(signed_efficiency),
        "signed_path_efficiency": signed_efficiency,
        "direction_descriptor": direction,
        "path_status": path_status,
        "prediction": None,
    }


def prior_horizon_extrema(
    *,
    side: str,
    entry: float,
    take_profit: float,
    highs: list[float],
    lows: list[float],
) -> dict:
    if side not in {"long", "short"}:
        raise ValueError("invalid_side")
    if not finite_number(entry) or not finite_number(take_profit):
        raise ValueError("invalid_plan_price")
    if entry <= 0 or take_profit <= 0:
        raise ValueError("invalid_plan_price")
    parsed_highs = positive_prices(highs)
    parsed_lows = positive_prices(lows)
    if len(parsed_highs) != len(parsed_lows):
        raise ValueError("high_low_length_mismatch")
    if any(low > high for low, high in zip(parsed_lows, parsed_highs)):
        raise ValueError("invalid_high_low_bar")
    prior_high = max(parsed_highs)
    prior_low = min(parsed_lows)
    if side == "long":
        valid_geometry = entry < take_profit
        target_extreme = prior_high
        adverse_extreme = prior_low
        target_between = entry < target_extreme < take_profit
        target_distance = (
            log(target_extreme / entry)
            if target_extreme > entry
            else None
        )
    else:
        valid_geometry = take_profit < entry
        target_extreme = prior_low
        adverse_extreme = prior_high
        target_between = take_profit < target_extreme < entry
        target_distance = (
            log(entry / target_extreme)
            if target_extreme < entry
            else None
        )
    if not valid_geometry:
        raise ValueError("invalid_target_geometry")
    return {
        "prior_high": prior_high,
        "prior_low": prior_low,
        "target_side_extreme": target_extreme,
        "adverse_side_extreme": adverse_extreme,
        "target_extreme_between_entry_and_tp": target_between,
        "target_extreme_log_distance": target_distance,
        "support_resistance_label": None,
        "barrier_effect": None,
    }


def empirical_volatility_percentile(
    current_realized_variance: float,
    prior_realized_variances: list[float],
) -> dict:
    if (
        not finite_number(current_realized_variance)
        or current_realized_variance < 0
    ):
        raise ValueError("invalid_current_realized_variance")
    if len(prior_realized_variances) < VOLATILITY_REFERENCE_WINDOWS:
        raise ValueError("insufficient_volatility_reference_windows")
    reference = prior_realized_variances[-VOLATILITY_REFERENCE_WINDOWS:]
    if any(
        not finite_number(value) or float(value) < 0
        for value in reference
    ):
        raise ValueError("invalid_reference_realized_variance")
    current = float(current_realized_variance)
    less = sum(float(value) < current for value in reference)
    equal = sum(float(value) == current for value in reference)
    percentile = (
        less + 0.5 * equal
    ) / VOLATILITY_REFERENCE_WINDOWS
    return {
        "volatility_percentile": percentile,
        "reference_window_count": VOLATILITY_REFERENCE_WINDOWS,
        "ranking_method": "empirical_midrank",
        "regime_label": None,
        "directional_effect": None,
    }


def multi_timeframe_state(structures: dict[str, dict]) -> dict:
    required = {"H", "2H", "4H"}
    if set(structures) != required:
        raise ValueError("mtf_windows_mismatch")
    signed = {}
    signs = {}
    for window in ("H", "2H", "4H"):
        value = structures[window].get("signed_path_efficiency")
        if not finite_number(value) or not -1 <= float(value) <= 1:
            raise ValueError("invalid_signed_path_efficiency")
        signed[window] = float(value)
        signs[window] = (
            1 if value > 0 else -1 if value < 0 else 0
        )
    sign_values = set(signs.values())
    if sign_values == {1}:
        agreement = "all_positive"
    elif sign_values == {-1}:
        agreement = "all_negative"
    elif 0 in sign_values:
        agreement = "flat_present"
    else:
        agreement = "mixed"
    return {
        "window_multipliers": list(MTF_WINDOW_MULTIPLIERS),
        "signed_path_efficiencies": signed,
        "direction_signs": signs,
        "agreement_descriptor": agreement,
        "aggregate_score": None,
        "probability_effect": None,
    }


def continuous_regime_vector(
    volatility_percentile: float,
    signed_path_efficiency: float,
) -> dict:
    if (
        not finite_number(volatility_percentile)
        or not 0 <= float(volatility_percentile) <= 1
    ):
        raise ValueError("invalid_volatility_percentile")
    if (
        not finite_number(signed_path_efficiency)
        or not -1 <= float(signed_path_efficiency) <= 1
    ):
        raise ValueError("invalid_signed_path_efficiency")
    return {
        "volatility_percentile": float(volatility_percentile),
        "signed_path_efficiency": float(signed_path_efficiency),
        "regime_label": None,
        "directional_score": None,
        "probability_effect": None,
    }


def rule_card(
    rule_id: str,
    name: str,
    *,
    blocks: list[int],
    rule_type: str,
    objective: str,
    data_ids: list[str],
    formula: list[str],
    source_support: list[dict],
    unsupported: list[str],
    hypothesis: dict | None,
    expected_relation: str,
    related: list[str],
    double_counting: str,
    missing: str,
    invariants: list[str],
    trace: list[str],
    refutation: list[str],
    lifecycle_status: str = "documented_candidate_no_predictive_weight",
) -> dict:
    return {
        "id": rule_id,
        "version": RULE_VERSION,
        "name": name,
        "analytical_blocks": blocks,
        "concrete_objective": objective,
        "rule_type": rule_type,
        "raw_data_and_provider": {
            "provider": "Binance USD-M and immutable user plan",
            "m3_data_contract_ids": data_ids,
        },
        "market_symbol_timestamp_unit_freshness": {
            "market": "Binance USD-M perpetual",
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "time_rule": (
                "M3-compliant closed data only; every observation <= analysis_at"
            ),
            "price_unit": "quote_asset_per_base",
            "normalized_units": "log_return_or_dimensionless",
        },
        "exact_transformation_and_formula": formula,
        "cross_pair_normalization": (
            "Natural-log ratios, path ratios or within-pair empirical ranks."
        ),
        "applicable_horizons": list(HORIZONS),
        "activation_conditions": [
            "complete M4.2-compliant closed history",
            "same formula and policy for every supported pair",
        ],
        "non_application_conditions": [
            "missing, stale, future, gapped or invalid data",
            "insufficient declared history",
        ],
        "source_and_exact_supported_claim": source_support,
        "claims_not_supported_by_source": unsupported,
        "separate_predictive_hypothesis": hypothesis,
        "expected_relation_to_tp_sl_or_expiry": expected_relation,
        "related_rules": related,
        "double_counting_control": double_counting,
        "missing_data_behavior": missing,
        "unit_tests_limits_and_invariants": invariants,
        "trace_output": trace,
        "refutation_suspension_or_withdrawal": refutation,
        "lifecycle_status": lifecycle_status,
        "direct_probability_effect_authorized": False,
        "numeric_weight_authorized": False,
        "production_authorized": False,
    }


def build_rules() -> list[dict]:
    common_limits = [
        "No source supplies a project score, probability, weight or threshold.",
        "Evidence from other assets or horizons is not assumed transferable.",
    ]
    return [
        rule_card(
            "M4-RULE-EXPONENTIAL-SMOOTHER-001",
            "Operador de suavizado exponencial",
            blocks=[1, 3],
            rule_type="deterministic_operator_not_p0_evidence",
            objective=(
                "Preserve the standard recursive operator while refusing "
                "unsupported EMA periods and crossover meanings."
            ),
            data_ids=["M3-DATA-005"],
            formula=["S_0=x_0", "S_t=alpha*x_t+(1-alpha)*S_(t-1), 0<alpha<=1"],
            source_support=[
                {
                    "source_id": "NIST-SINGLE-EXPONENTIAL-SMOOTHING",
                    "level": "definition",
                    "claim": "Recursive exponential smoothing and initialization.",
                }
            ],
            unsupported=[
                *common_limits,
                "No alpha or 9/21/50/200 period is approved.",
                "Price above/below a smoother is not a directional rule.",
            ],
            hypothesis=None,
            expected_relation="None; operator is descriptive only.",
            related=["M4-RULE-PATH-STRUCTURE-001"],
            double_counting="Cannot enter P0 alongside path displacement.",
            missing="Do not calculate; never replace history with a shorter EMA.",
            invariants=[
                "0<alpha<=1",
                "explicit initialization",
                "constant input remains constant",
            ],
            trace=["alpha", "initialization", "input_count", "smoothed_value"],
            refutation=[
                "Withdraw any fixed period introduced without a new rule card."
            ],
            lifecycle_status="documented_operator_not_admitted_as_p0_evidence",
        ),
        rule_card(
            "M4-RULE-PATH-STRUCTURE-001",
            "Desplazamiento y eficiencia de trayectoria",
            blocks=[1, 24],
            rule_type="deterministic_measure_with_separate_hypothesis",
            objective=(
                "Separate net displacement from total path variation over an "
                "exact closed window."
            ),
            data_ids=["M3-DATA-005"],
            formula=[
                "D_W=sum(r_i)=ln(C_end/C_start)",
                "TV_W=sum(abs(r_i))",
                "if TV_W>0: E_W=abs(D_W)/TV_W; SE_W=D_W/TV_W",
                "if TV_W=0: E_W=0; SE_W=0; flat_path=true",
            ],
            source_support=[
                {
                    "source_id": "MOSKOWITZ-OOI-PEDERSEN-2012",
                    "level": "external_predictive_evidence",
                    "claim": (
                        "Past return sign showed momentum at monthly horizons "
                        "in traditional futures."
                    ),
                },
                {
                    "source_id": "HUDSON-URQUHART-2021",
                    "level": "external_predictive_evidence",
                    "claim": (
                        "Crypto technical-rule performance varied by asset and "
                        "failed OOS for Bitcoin in their selected test."
                    ),
                },
            ],
            unsupported=[
                *common_limits,
                "Path efficiency itself is a project deterministic measure.",
                "Positive displacement is not automatically bullish evidence.",
            ],
            hypothesis={
                "id": "M4-HYP-STRUCTURE-001",
                "status": "proposed_unverified",
                "statement": (
                    "Side-aligned signed path efficiency may condition which "
                    "barrier is reached first within the same horizon."
                ),
            },
            expected_relation=(
                "No direct effect; future models may test side-aligned SE_W "
                "under regime and horizon controls."
            ),
            related=[
                "M4-RULE-MTF-HIERARCHY-001",
                "M4-RULE-CONTINUOUS-REGIME-001",
            ],
            double_counting=(
                "D_W, E_W and SE_W are one price-path evidence family."
            ),
            missing="Block structure and all dependent combinations.",
            invariants=[
                "0<=E_W<=1",
                "-1<=SE_W<=1",
                "TV_W=0 implies E_W=SE_W=0 and flat_path=true",
                "scale invariance",
                "D_W equals log endpoint ratio",
            ],
            trace=[
                "window_seconds",
                "return_count",
                "log_displacement",
                "total_log_variation",
                "path_efficiency",
                "signed_path_efficiency",
                "direction_descriptor",
                "prediction",
            ],
            refutation=[
                "Retire hypothesis if no stable independent incremental value.",
                "Reject any implementation that thresholds SE_W without amendment.",
            ],
        ),
        rule_card(
            "M4-RULE-PRIOR-EXTREMA-001",
            "Extremos observados del horizonte anterior",
            blocks=[1, 28],
            rule_type="deterministic_measure_with_separate_hypothesis",
            objective=(
                "Record prior-H high/low and whether the target-side extreme "
                "lies strictly between entry and TP."
            ),
            data_ids=["M3-DATA-001", "M3-DATA-005"],
            formula=[
                "X_high=max(H_i), X_low=min(L_i) over previous exact H",
                "long target extreme=X_high; short target extreme=X_low",
                "between=entry<X_high<TP long; TP<X_low<entry short",
            ],
            source_support=[
                {
                    "source_id": "OSLER-2000-SUPPORT-RESISTANCE",
                    "level": "external_predictive_evidence",
                    "claim": (
                        "Published FX levels predicted some intraday trend "
                        "interruptions with heterogeneous performance."
                    ),
                },
                {
                    "source_id": "CURCIO-ET-AL-2014-PRICE-MEMORY",
                    "level": "technical_foundation",
                    "claim": (
                        "Local extrema, bounce count and time scale can be "
                        "studied as price-memory candidates."
                    ),
                },
            ],
            unsupported=[
                *common_limits,
                "A rolling high/low is not called support or resistance.",
                "An extreme between entry and TP receives no penalty.",
            ],
            hypothesis={
                "id": "M4-HYP-LEVEL-001",
                "status": "proposed_unverified",
                "statement": (
                    "A prior target-side extreme between entry and TP may "
                    "condition first-passage behavior."
                ),
            },
            expected_relation=(
                "Unknown until independently tested; both interruption and "
                "breakout continuation remain possible."
            ),
            related=["M4-RULE-BARRIER-REACHABILITY-001"],
            double_counting=(
                "Replaces support, level and technical-barrier penalties with "
                "one extrema descriptor."
            ),
            missing="Rule not evaluated; no synthetic level.",
            invariants=[
                "prior_low<=prior_high",
                "strict between relation",
                "long/short mirror handling",
                "no support/resistance label",
            ],
            trace=[
                "prior_high",
                "prior_low",
                "target_side_extreme",
                "adverse_side_extreme",
                "target_extreme_between_entry_and_tp",
                "target_extreme_log_distance",
                "barrier_effect",
            ],
            refutation=[
                "Retire hypothesis if effect is unstable by pair/horizon.",
                "A richer bounce detector requires a new rule and source claims.",
            ],
        ),
        rule_card(
            "M4-RULE-VOLATILITY-RANK-001",
            "Percentil continuo de volatilidad",
            blocks=[24, 26],
            rule_type="deterministic_context_measure",
            objective=(
                "Locate current previous-H RV within 60 strictly prior "
                "non-overlapping H windows without categorical bands."
            ),
            data_ids=["M3-DATA-005"],
            formula=[
                "q=(count(RV_j<RV_t)+0.5*count(RV_j=RV_t))/60",
                "j are 60 strictly prior non-overlapping H windows",
            ],
            source_support=[
                {
                    "source_id": "HAMILTON-1989-REGIME-SWITCHING",
                    "level": "technical_foundation",
                    "claim": "Regimes require a specified estimated state model.",
                },
                {
                    "source_id": "CORSI-2009-HAR-RV",
                    "level": "technical_foundation",
                    "claim": "Volatility contains heterogeneous temporal components.",
                },
            ],
            unsupported=[
                *common_limits,
                "Sixty windows is project policy, not a published optimum.",
                "q is not labelled low, medium or high.",
            ],
            hypothesis={
                "id": "M4-HYP-REGIME-001",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "Volatility rank may alter the reliability of structure "
                    "signals but has no directional effect alone."
                ),
            },
            expected_relation="Context only; no direct TP-versus-SL direction.",
            related=[
                "M4-RULE-REALIZED-VOLATILITY-001",
                "M4-RULE-CONTINUOUS-REGIME-001",
            ],
            double_counting=(
                "Rank is a transformation of M4.2 RV, not independent evidence."
            ),
            missing="Block regime context; retain geometry if otherwise valid.",
            invariants=[
                "0<=q<=1",
                "exactly 60 prior windows",
                "current window excluded from reference",
                "midrank tie handling",
            ],
            trace=[
                "current_realized_variance",
                "reference_window_count",
                "reference_cutoff",
                "volatility_percentile",
                "ranking_method",
                "regime_label",
            ],
            refutation=[
                "Change reference length only through versioned amendment.",
                "Retire interaction if no stable conditional value.",
            ],
        ),
        rule_card(
            "M4-RULE-MTF-HIERARCHY-001",
            "Jerarquia multi-timeframe H, 2H y 4H",
            blocks=[1, 3, 24],
            rule_type="deterministic_interaction_descriptor",
            objective=(
                "Expose structure at the plan horizon and two slower contexts "
                "without votes, weights or duplicate penalties."
            ),
            data_ids=["M3-DATA-001", "M3-DATA-005"],
            formula=[
                "calculate SE_W for W in {H,2H,4H} on the same closed grid",
                "sign_W=sign(SE_W)",
                "agreement in {all_positive,all_negative,mixed,flat_present}",
            ],
            source_support=[
                {
                    "source_id": "CORSI-2009-HAR-RV",
                    "level": "technical_foundation",
                    "claim": "Different horizons can carry distinct temporal information.",
                },
                {
                    "source_id": "HUDSON-URQUHART-2021",
                    "level": "transfer_limit",
                    "claim": "Technical-rule effects are asset and sample dependent.",
                },
            ],
            unsupported=[
                *common_limits,
                "H/2H/4H is project context policy, not a cited optimum.",
                "Agreement has no score or automatic direction.",
            ],
            hypothesis={
                "id": "M4-HYP-MTF-001",
                "status": "proposed_unverified",
                "statement": (
                    "Sign agreement across H, 2H and 4H may condition first-"
                    "passage behavior beyond H structure alone."
                ),
            },
            expected_relation=(
                "Only an interaction candidate; mixed signs are not a penalty."
            ),
            related=["M4-RULE-PATH-STRUCTURE-001"],
            double_counting=(
                "MTF consumes the three SE values once; no trend score plus "
                "HTF contradiction penalty."
            ),
            missing="Do not collapse available windows into a partial vote.",
            invariants=[
                "exact windows H,2H,4H",
                "same sampling grid",
                "no numeric aggregation",
                "order and signs preserved",
            ],
            trace=[
                "window_multipliers",
                "signed_path_efficiencies",
                "direction_signs",
                "agreement_descriptor",
                "aggregate_score",
                "probability_effect",
            ],
            refutation=[
                "Retire if no incremental value beyond H structure.",
                "Any weights require a new documented integration rule.",
            ],
        ),
        rule_card(
            "M4-RULE-CONTINUOUS-REGIME-001",
            "Vector continuo de regimen",
            blocks=[24],
            rule_type="context_vector_no_label",
            objective=(
                "Represent current state by volatility percentile and signed "
                "path efficiency without arbitrary regime names."
            ),
            data_ids=["M3-DATA-005"],
            formula=["R_t=(q_RV,t, SE_H,t)"],
            source_support=[
                {
                    "source_id": "HAMILTON-1989-REGIME-SWITCHING",
                    "level": "transfer_limit",
                    "claim": (
                        "A genuine latent regime requires model estimation; "
                        "this rule therefore remains an observed state vector."
                    ),
                }
            ],
            unsupported=[
                *common_limits,
                "The vector is not a Markov regime model.",
                "No low/high or bull/bear labels are assigned.",
            ],
            hypothesis={
                "id": "M4-HYP-REGIME-002",
                "status": "proposed_unverified_interaction_only",
                "statement": (
                    "The interaction of q_RV and SE_H may identify conditions "
                    "where directional structure behaves differently."
                ),
            },
            expected_relation="Unknown interaction; no marginal directional effect.",
            related=[
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-VOLATILITY-RANK-001",
            ],
            double_counting=(
                "Vector references its atomic inputs; it does not add evidence."
            ),
            missing="Vector unavailable if either component is unavailable.",
            invariants=[
                "q_RV in [0,1]",
                "SE_H in [-1,1]",
                "regime_label is null",
                "directional_score is null",
            ],
            trace=[
                "volatility_percentile",
                "signed_path_efficiency",
                "regime_label",
                "directional_score",
                "probability_effect",
            ],
            refutation=[
                "A categorical or latent regime requires a separate model card.",
                "Retire interaction if M8 finds no stable conditional effect.",
            ],
        ),
    ]


def validate_rules(rules: list[dict]) -> None:
    ids = [rule["id"] for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_rule_id")
    source_ids = {source["id"] for source in SOURCES}
    for rule in rules:
        used = {
            item["source_id"]
            for item in rule["source_and_exact_supported_claim"]
        }
        if not used.issubset(source_ids):
            raise ValueError(f"unknown_source:{rule['id']}")
        if (
            rule["direct_probability_effect_authorized"]
            or rule["numeric_weight_authorized"]
            or rule["production_authorized"]
        ):
            raise ValueError(f"unauthorized_effect:{rule['id']}")
        if not rule["exact_transformation_and_formula"]:
            raise ValueError(f"missing_formula:{rule['id']}")
        if not rule["claims_not_supported_by_source"]:
            raise ValueError(f"missing_transfer_limit:{rule['id']}")


def build_catalog() -> dict:
    m3 = read_json(M3_CATALOG_PATH)
    reconciliation = read_json(M4_RECONCILIATION_PATH)
    reachability = read_json(M4_REACHABILITY_PATH)
    if m3["status"] != "completed_owner_approved":
        raise ValueError("m3_not_approved")
    if reconciliation["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_1_not_completed")
    if reachability["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_2_not_completed")
    if reachability["scope"]["m4_next_subphase"] != "M4.3":
        raise ValueError("m4_2_does_not_lead_to_m4_3")
    rules = build_rules()
    validate_rules(rules)
    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.3",
        "status": "completed_internal_milestone_m4_still_in_progress",
        "date": "2026-07-27",
        "scope": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "rules": len(rules),
            "direct_probability_effects": 0,
            "numeric_weights": 0,
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m5_started": False,
            "m4_next_subphase": "M4.4",
        },
        "operational_policies": {
            "volatility_reference_windows": VOLATILITY_REFERENCE_WINDOWS,
            "volatility_reference_policy": (
                "60 strictly prior non-overlapping exact-H windows"
            ),
            "mtf_window_multipliers": list(MTF_WINDOW_MULTIPLIERS),
            "mtf_policy": "same closed sampling grid; H, 2H and 4H",
            "classification": (
                "project policies, not published optimal parameters"
            ),
            "categorical_regime_labels_allowed": False,
            "mtf_numeric_weights_allowed": False,
            "ema_periods_approved": [],
        },
        "policy_decision_records": [
            {
                "id": "M4-POLICY-VOLATILITY-REFERENCE-WINDOWS-001",
                "value": VOLATILITY_REFERENCE_WINDOWS,
                "status": "provisional_project_policy",
                "reason": (
                    "Use a fixed strictly prior sample for an empirical "
                    "midrank without future information."
                ),
                "tradeoff": (
                    "Sixty windows is reproducible but is not a published "
                    "optimum for all pairs or horizons."
                ),
                "future_test": (
                    "M7/M8 preregistered sensitivity before holdout "
                    "evaluation."
                ),
            },
            {
                "id": "M4-POLICY-MTF-WINDOW-MULTIPLIERS-001",
                "value": list(MTF_WINDOW_MULTIPLIERS),
                "status": "provisional_project_policy",
                "reason": (
                    "Expose one exact horizon and two slower contexts without "
                    "votes or duplicated evidence."
                ),
                "tradeoff": (
                    "H/2H/4H is transparent project policy, not a published "
                    "universal optimum."
                ),
                "future_test": (
                    "M7/M8 preregistered stability analysis; no post-holdout "
                    "retuning."
                ),
            },
        ],
        "sources": list(SOURCES),
        "rules": rules,
        "preregistered_hypotheses": [
            rule["separate_predictive_hypothesis"]
            for rule in rules
            if rule["separate_predictive_hypothesis"] is not None
        ],
        "evidence_families": [
            {
                "id": "M4-EVIDENCE-PRICE-PATH",
                "members": [
                    "M4-RULE-PATH-STRUCTURE-001",
                    "M4-RULE-MTF-HIERARCHY-001",
                ],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-VOLATILITY-STATE",
                "members": [
                    "M4-RULE-REALIZED-VOLATILITY-001",
                    "M4-RULE-VOLATILITY-RANK-001",
                    "M4-RULE-CONTINUOUS-REGIME-001",
                ],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-PRIOR-EXTREMA",
                "members": ["M4-RULE-PRIOR-EXTREMA-001"],
                "additive_members_allowed": False,
            },
        ],
        "supersedes_current_elements": {
            "IND-EMA-CORE": (
                "Operator retained without approved alpha or predictive role."
            ),
            "IND-EMA200-FALLBACK": "Retired; insufficient history blocks.",
            "IND-EMA-STACK": "Replaced by H/2H/4H path-state descriptor.",
            "IND-SUPPORT-RESISTANCE": (
                "Replaced by prior extrema without support/resistance label."
            ),
            "SCORE-TREND_BIAS": "Points and timeframe weights retired.",
            "SCORE-TECHNICAL_DIRECTION_BIAS": "Opaque aggregate retired.",
            "SCORE-MARKET_REGIME_BIAS": "Directional regime points retired.",
            "SCORE-OVEREXTENSION_PENALTY": "EMA-distance penalty retired.",
            "SCORE-LEVEL_PENALTY": "Merged into prior-extrema family.",
            "SCORE-HIGHER_TIMEFRAME_PENALTY": "Merged into MTF descriptor.",
            "SCORE-TECHNICAL_ENTRY_TIMING_PENALTY": "Retired without replacement.",
            "SCORE-TECHNICAL_BARRIER_PENALTY": "Merged into prior-extrema family.",
        },
        "summary": {
            "rules": len(rules),
            "p0_rule_cards": sum(
                1
                for rule in rules
                if rule["lifecycle_status"]
                != "documented_operator_not_admitted_as_p0_evidence"
            ),
            "auxiliary_operator_cards": sum(
                1
                for rule in rules
                if rule["lifecycle_status"]
                == "documented_operator_not_admitted_as_p0_evidence"
            ),
            "nonpredictive_operator_rules": sum(
                1
                for rule in rules
                if rule["lifecycle_status"]
                == "documented_operator_not_admitted_as_p0_evidence"
            ),
            "hypotheses": sum(
                1
                for rule in rules
                if rule["separate_predictive_hypothesis"] is not None
            ),
            "evidence_families": 3,
            "rules_with_probability_effect": 0,
            "rules_with_numeric_weight": 0,
            "production_modified": False,
        },
        "amendment": {
            "version": "M4.7-amendment-wave-1-v0.2",
            "supersedes_artifact": (
                "auditorias_motor/"
                "catalogo_regimen_estructura_mtf_m4_3_v0_1.json"
            ),
            "changes": [
                "complete the flat-path formula for E_W and SE_W",
                "classify exponential smoothing as an auxiliary operator",
                "register 60-window and H/2H/4H policy decisions",
                "declare canonical payload digest scope",
            ],
        },
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_sha256(path),
            }
            for path in (
                ROOT / "HOJA_RUTA_MEJORA_MOTOR_ANALISIS.md",
                M3_CATALOG_PATH,
                M4_RECONCILIATION_PATH,
                M4_REACHABILITY_PATH,
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "operational_policies": payload["operational_policies"],
                "policy_decision_records": payload[
                    "policy_decision_records"
                ],
                "sources": payload["sources"],
                "rules": payload["rules"],
                "evidence_families": payload["evidence_families"],
                "supersedes_current_elements": payload[
                    "supersedes_current_elements"
                ],
            }
        )
    )
    return payload


def render_report(catalog: dict) -> str:
    lines = [
        "# M4.3 - Regimen, estructura y multi-timeframe",
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
        "- Regimenes categoricos autorizados: **0**.",
        "- Periodos EMA autorizados: **0**.",
        "- Cambios productivos: **ninguno**.",
        "",
        "## 2. Variables exactas",
        "",
        "- Desplazamiento: `D_W=ln(C_end/C_start)`.",
        "- Variacion total: `TV_W=sum(abs(r_i))`.",
        "- Eficiencia: `E_W=abs(D_W)/TV_W`.",
        "- Eficiencia firmada: `SE_W=D_W/TV_W`.",
        "- Percentil RV: midrank frente a 60 ventanas H anteriores.",
        "- MTF: vector ordenado de `SE_H`, `SE_2H` y `SE_4H`.",
        "- Regimen observado: vector `(q_RV, SE_H)` sin etiqueta.",
        "- Nivel estructural: maximo/minimo del horizonte anterior, sin",
        "  llamarlo soporte o resistencia.",
        "",
        "## 3. Decisiones",
        "",
        "- EMA queda como operador matematico, no como evidencia P0.",
        "- No sobreviven periodos 9/21/50/200 ni cruces automaticos.",
        "- No hay votos ni pesos multi-timeframe.",
        "- Volatilidad, percentil y regimen son una sola familia, no tres senales.",
        "- Tendencia H y acuerdo MTF son una familia, no bonus mas penalizacion.",
        "- Un extremo entre entrada y TP se registra, pero no se penaliza.",
        "",
        "## 4. Reglas",
        "",
        "| ID | Estado | Probabilidad | Peso |",
        "|---|---|---|---|",
    ]
    for rule in catalog["rules"]:
        lines.append(
            f"| `{rule['id']}` | `{rule['lifecycle_status']}` | no | no |"
        )
    lines.extend(
        [
            "",
            "## 5. Limites de transferencia",
            "",
            "- Momentum tradicional no acredita crypto intradia.",
            "- Resultados tecnicos crypto varian por activo y fuera de muestra.",
            "- Los niveles FX publicados no equivalen a nuestros extremos.",
            "- El vector continuo no es un modelo Markov de regimen.",
            "- Los parametros 60 y H/2H/4H son politicas del proyecto.",
            "",
            "## 6. Siguiente paso",
            "",
            "`M4.4`: order flow, spot-Futures, OI y funding. Debera mantener",
            "separados actividad, direccion, basis, posicionamiento y coste.",
            "",
            "SHA-256 del payload canonico "
            "(`operational_policies`, `policy_decision_records`, `sources`, "
            "`rules`, `evidence_families`, `supersedes_current_elements`): "
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
