from __future__ import annotations

import argparse
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M3_CATALOG_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
M4_RECONCILIATION_PATH = AUDIT_DIR / "reconciliacion_candidatos_m4_v0_1.json"
M4_REACHABILITY_PATH = AUDIT_DIR / "catalogo_alcanzabilidad_m4_2_v0_2.json"
M4_DERIVATIVES_PATH = AUDIT_DIR / "catalogo_contexto_derivados_m4_4_v0_2.json"
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "catalogo_ejecucion_riesgo_m4_5_v0_2.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-27_M4_5_ejecucion_costes_riesgo_enmienda_v0_2.md"
)

VERSION = "M4.5-execution-risk-v0.2"
RULE_VERSION = "0.2"
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
        "id": "M2-SEMANTICS",
        "type": "approved_internal_contract",
        "url": None,
        "supported_claim": (
            "Pre-trade outcome space, TP/SL geometry, pending-entry branches "
            "and immutable analysis identity."
        ),
        "does_not_support": "Probabilities, trading costs or decision policy.",
    },
    {
        "id": "M3-DATA-CONTRACTS",
        "type": "approved_internal_contract",
        "url": None,
        "supported_claim": (
            "Available bid/ask, depth, mark/funding, exchange filters, "
            "user-plan margin/leverage and authenticated commission fields."
        ),
        "does_not_support": (
            "Future exit liquidity, future funding, account liquidation "
            "price or predictive effects."
        ),
    },
    {
        "id": "M4.2-REACHABILITY",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": "Direction-safe TP/SL price geometry.",
        "does_not_support": "Monetary exposure or expected value.",
    },
    {
        "id": "M4.4-DERIVATIVES",
        "type": "completed_internal_milestone",
        "url": None,
        "supported_claim": (
            "Observed funding state and the prohibition on treating the last "
            "funding rate as a future rate."
        ),
        "does_not_support": "Exact future funding cash flows.",
    },
    {
        "id": "BINANCE-USD-M-MARKET-DATA",
        "type": "official_provider_documentation",
        "url": (
            "https://developers.binance.com/en/docs/catalog/"
            "core-trading-derivatives-trading-usd-s-m-futures/api/"
            "rest-api/market-data"
        ),
        "supported_claim": (
            "Official availability and field meanings for order-book, "
            "best-quote, mark-price and funding observations."
        ),
        "does_not_support": (
            "Guaranteed fills, future order-book state, slippage thresholds "
            "or TP/SL probability."
        ),
    },
    {
        "id": "BINANCE-USD-M-ACCOUNT",
        "type": "official_provider_documentation",
        "url": (
            "https://developers.binance.com/en/docs/catalog/"
            "core-trading-derivatives-trading-usd-s-m-futures/api/"
            "rest-api/account"
        ),
        "supported_claim": (
            "Authenticated maker, taker and RPI commission-rate fields."
        ),
        "does_not_support": (
            "A universal rate, the liquidity role of an unknown future fill "
            "or future exit notional."
        ),
    },
    {
        "id": "FINRA-INSTITUTIONAL-ORDER-HANDLING-2019",
        "type": "primary_regulatory_research",
        "url": (
            "https://www.finra.org/sites/default/files/"
            "OCE_WP_jan2019.pdf"
        ),
        "supported_claim": (
            "Implementation shortfall compares signed execution VWAP with "
            "the arrival midpoint; fill rate and unfilled quantity matter."
        ),
        "does_not_support": (
            "Crypto-specific impact coefficients, future exit slippage or a "
            "fixed minimum slippage."
        ),
    },
    {
        "id": "ALMGREN-CHRISS-2001",
        "type": "primary_academic_publication",
        "url": "https://doi.org/10.21314/JOR.2001.041",
        "supported_claim": (
            "Execution has transaction-cost, market-impact and timing-risk "
            "components."
        ),
        "does_not_support": (
            "The exact project book-sweep estimator, universal parameters or "
            "directional market probability."
        ),
    },
    {
        "id": "HE-MANELA-ROSS-VON-WACHTER-2022",
        "type": "primary_academic_preprint",
        "url": "https://arxiv.org/abs/2212.06888",
        "supported_claim": (
            "Positive perpetual funding transfers value from long positions "
            "to short positions and anchors perpetual prices."
        ),
        "does_not_support": (
            "Future Binance funding rates, a standalone return forecast or "
            "project probability weights."
        ),
    },
    {
        "id": "INVESTOR-GOV-LEVERAGED-INVESTING",
        "type": "official_investor_guidance",
        "url": (
            "https://www.investor.gov/introduction-investing/"
            "general-resources/news-alerts/alerts-bulletins/"
            "investor-bulletins/leveraged-investing-strategies-know-risks-"
            "using-these-advanced-investment-tools"
        ),
        "supported_claim": (
            "Leverage magnifies gains and losses relative to invested capital."
        ),
        "does_not_support": (
            "Binance perpetual liquidation mechanics, maintenance-margin "
            "brackets or a safe leverage threshold."
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


def positive_number(value: Any, error: str) -> float:
    if not finite_number(value) or float(value) <= 0:
        raise ValueError(error)
    return float(value)


def nonnegative_number(value: Any, error: str) -> float:
    if not finite_number(value) or float(value) < 0:
        raise ValueError(error)
    return float(value)


def quoted_spread(best_bid: float, best_ask: float) -> dict:
    bid = positive_number(best_bid, "invalid_best_bid")
    ask = positive_number(best_ask, "invalid_best_ask")
    if ask < bid:
        raise ValueError("crossed_book")
    midpoint = (bid + ask) / 2.0
    spread = ask - bid
    return {
        "best_bid": bid,
        "best_ask": ask,
        "midpoint": midpoint,
        "spread_quote": spread,
        "spread_fraction_mid": spread / midpoint,
    }


def depth_sweep(
    *,
    side: str,
    requested_quantity: float,
    bids: list[list[float]],
    asks: list[list[float]],
) -> dict:
    if side not in {"buy", "sell"}:
        raise ValueError("invalid_side")
    requested = positive_number(
        requested_quantity,
        "invalid_requested_quantity",
    )
    if not bids or not asks:
        raise ValueError("empty_book_side")

    def normalize(levels: list[list[float]], name: str) -> list[tuple[float, float]]:
        normalized = []
        for level in levels:
            if not isinstance(level, (list, tuple)) or len(level) != 2:
                raise ValueError(f"invalid_{name}_level")
            price = positive_number(level[0], f"invalid_{name}_price")
            quantity = positive_number(level[1], f"invalid_{name}_quantity")
            normalized.append((price, quantity))
        return normalized

    normalized_bids = normalize(bids, "bid")
    normalized_asks = normalize(asks, "ask")
    if any(
        normalized_bids[index][0] < normalized_bids[index + 1][0]
        for index in range(len(normalized_bids) - 1)
    ):
        raise ValueError("bids_not_descending")
    if any(
        normalized_asks[index][0] > normalized_asks[index + 1][0]
        for index in range(len(normalized_asks) - 1)
    ):
        raise ValueError("asks_not_ascending")

    best_bid = normalized_bids[0][0]
    best_ask = normalized_asks[0][0]
    quote = quoted_spread(best_bid, best_ask)
    consumed = normalized_asks if side == "buy" else normalized_bids
    remaining = requested
    filled = 0.0
    quote_value = 0.0
    levels_used = 0
    for price, available in consumed:
        take = min(remaining, available)
        quote_value += take * price
        filled += take
        remaining -= take
        if take > 0:
            levels_used += 1
        if remaining <= 1e-12:
            remaining = 0.0
            break

    fill_ratio = filled / requested
    vwap_filled = quote_value / filled if filled > 0 else None
    complete = remaining == 0.0
    direction = 1.0 if side == "buy" else -1.0
    filled_shortfall_quote = (
        direction * (quote_value - quote["midpoint"] * filled)
        if filled > 0
        else None
    )
    filled_shortfall_fraction_mid = (
        filled_shortfall_quote / (quote["midpoint"] * filled)
        if filled > 0
        else None
    )
    return {
        "side": side,
        "requested_quantity": requested,
        "filled_quantity": filled,
        "unfilled_quantity": remaining,
        "fill_ratio": fill_ratio,
        "levels_used": levels_used,
        "vwap_filled": vwap_filled,
        "vwap": vwap_filled if complete else None,
        "arrival_midpoint": quote["midpoint"],
        "filled_implementation_shortfall_quote": filled_shortfall_quote,
        "filled_implementation_shortfall_fraction_mid": (
            filled_shortfall_fraction_mid
        ),
        "implementation_shortfall_fraction_mid": (
            filled_shortfall_fraction_mid if complete else None
        ),
        "status": "complete_visible_sweep" if complete else "insufficient_visible_depth",
        "future_exit_estimate_authorized": False,
    }


def fee_cost_bounds(
    *,
    notional: float,
    allowed_roles: list[str],
    rates: dict[str, float | None],
    observed_execution: bool = False,
    fee_asset: str | None = None,
) -> dict:
    amount = nonnegative_number(notional, "invalid_notional")
    if not isinstance(observed_execution, bool):
        raise ValueError("invalid_observed_execution_flag")
    if not allowed_roles:
        raise ValueError("empty_allowed_roles")
    valid_roles = {"maker", "taker", "rpi"}
    if any(role not in valid_roles for role in allowed_roles):
        raise ValueError("invalid_liquidity_role")
    unique_roles = list(dict.fromkeys(allowed_roles))
    if observed_execution and len(unique_roles) != 1:
        raise ValueError("observed_execution_requires_one_role")
    if observed_execution and (
        not isinstance(fee_asset, str) or not fee_asset.strip()
    ):
        raise ValueError("observed_execution_requires_fee_asset")
    available = {}
    for role in unique_roles:
        rate = rates.get(role)
        if rate is None:
            continue
        available[role] = nonnegative_number(
            rate,
            f"invalid_{role}_commission_rate",
        )
    if len(available) != len(unique_roles):
        return {
            "status": "blocked_missing_authenticated_rate",
            "allowed_roles": unique_roles,
            "missing_roles": [
                role for role in unique_roles if role not in available
            ],
            "lower_cost": None,
            "upper_cost": None,
            "exact": False,
            "value_quality": {
                "lower_cost": "unavailable",
                "upper_cost": "unavailable",
            },
            "notional_basis": (
                "executed_notional"
                if observed_execution
                else "assumed_pretrade_notional"
            ),
            "fee_asset": fee_asset,
        }
    costs = {role: amount * rate for role, rate in available.items()}
    if observed_execution:
        status = "observed_exact_from_executed_notional_and_rate"
        value_quality = {
            "cost_by_role": "observed_exact",
            "lower_cost": "observed_exact",
            "upper_cost": "observed_exact",
        }
    elif len(costs) == 1:
        status = "single_role_pretrade_scenario"
        value_quality = {
            "cost_by_role": "scenario_point",
            "lower_cost": "scenario_point",
            "upper_cost": "scenario_point",
        }
    else:
        status = "bounded_role_scenario"
        value_quality = {
            "cost_by_role": "scenario_point",
            "lower_cost": "scenario_lower_bound",
            "upper_cost": "scenario_upper_bound",
        }
    return {
        "status": status,
        "allowed_roles": unique_roles,
        "cost_by_role": costs,
        "lower_cost": min(costs.values()),
        "upper_cost": max(costs.values()),
        "exact": observed_execution,
        "value_quality": value_quality,
        "notional_basis": (
            "executed_notional"
            if observed_execution
            else "assumed_pretrade_notional"
        ),
        "fee_asset": fee_asset,
    }


def funding_cashflow(
    *,
    side: str,
    quantity: float,
    events: list[dict],
) -> dict:
    if side not in {"long", "short"}:
        raise ValueError("invalid_position_side")
    position_quantity = positive_number(quantity, "invalid_position_quantity")
    position_sign = 1.0 if side == "long" else -1.0
    cashflow = 0.0
    for event in events:
        mark_price = positive_number(
            event.get("mark_price"),
            "invalid_funding_mark_price",
        )
        rate = event.get("funding_rate")
        if not finite_number(rate):
            raise ValueError("invalid_funding_rate")
        cashflow += -position_sign * position_quantity * mark_price * float(rate)
    return {
        "side": side,
        "event_count": len(events),
        "cashflow_quote": cashflow,
        "basis": "provided_or_realized_events_only",
        "future_rate_forecast_authorized": False,
    }


def plan_exposure(
    *,
    side: str,
    entry: float,
    take_profit: float,
    stop_loss: float,
    margin: float,
    leverage: float,
) -> dict:
    if side not in {"long", "short"}:
        raise ValueError("invalid_position_side")
    entry_price = positive_number(entry, "invalid_entry")
    tp = positive_number(take_profit, "invalid_take_profit")
    sl = positive_number(stop_loss, "invalid_stop_loss")
    margin_amount = positive_number(margin, "invalid_margin")
    leverage_multiple = positive_number(leverage, "invalid_leverage")
    if side == "long" and not (sl < entry_price < tp):
        raise ValueError("invalid_long_geometry")
    if side == "short" and not (tp < entry_price < sl):
        raise ValueError("invalid_short_geometry")

    notional = margin_amount * leverage_multiple
    quantity = notional / entry_price
    direction = 1.0 if side == "long" else -1.0
    gross_tp_pnl = direction * quantity * (tp - entry_price)
    gross_sl_pnl = direction * quantity * (sl - entry_price)
    reward = gross_tp_pnl
    risk = -gross_sl_pnl
    return {
        "side": side,
        "notional_quote": notional,
        "quantity_base": quantity,
        "gross_tp_pnl_quote": gross_tp_pnl,
        "gross_sl_pnl_quote": gross_sl_pnl,
        "gross_reward_quote": reward,
        "gross_risk_quote": risk,
        "gross_reward_to_risk": reward / risk,
        "gross_reward_fraction_margin": reward / margin_amount,
        "gross_risk_fraction_margin": risk / margin_amount,
        "market_probability_effect_authorized": False,
        "liquidation_price_available": False,
        "account_risk_available": False,
    }


def net_outcome_payoffs(outcomes: dict[str, dict]) -> dict:
    if not outcomes:
        raise ValueError("empty_outcome_set")
    result = {}
    complete = True
    for outcome_id, components in outcomes.items():
        entered = components.get("entered")
        if entered is False:
            result[outcome_id] = {
                "status": "direct_cashflow_zero_no_entry",
                "net_payoff_quote": 0.0,
                "opportunity_cost_included": False,
            }
            continue
        if entered is not True:
            raise ValueError(f"invalid_entered_state:{outcome_id}")
        required = (
            "gross_price_pnl",
            "fee_cost",
            "execution_shortfall_cost",
            "funding_cashflow",
        )
        if any(components.get(field) is None for field in required):
            complete = False
            result[outcome_id] = {
                "status": "incomplete_components",
                "net_payoff_quote": None,
                "missing": [
                    field for field in required if components.get(field) is None
                ],
            }
            continue
        gross = components["gross_price_pnl"]
        fee = components["fee_cost"]
        execution = components["execution_shortfall_cost"]
        funding = components["funding_cashflow"]
        if not finite_number(gross) or not finite_number(funding):
            raise ValueError(f"invalid_signed_component:{outcome_id}")
        fee_amount = nonnegative_number(fee, f"invalid_fee_cost:{outcome_id}")
        execution_amount = nonnegative_number(
            execution,
            f"invalid_execution_cost:{outcome_id}",
        )
        result[outcome_id] = {
            "status": "complete",
            "net_payoff_quote": (
                float(gross)
                - fee_amount
                - execution_amount
                + float(funding)
            ),
        }
    return {
        "status": "complete" if complete else "incomplete",
        "outcomes": result,
    }


def expected_value(
    *,
    probabilities: dict[str, float],
    payoffs: dict[str, float],
) -> float:
    if not probabilities or set(probabilities) != set(payoffs):
        raise ValueError("outcome_keys_mismatch")
    total_probability = 0.0
    result = 0.0
    for outcome_id, probability in probabilities.items():
        if (
            not finite_number(probability)
            or float(probability) < 0
            or float(probability) > 1
        ):
            raise ValueError(f"invalid_probability:{outcome_id}")
        payoff = payoffs[outcome_id]
        if not finite_number(payoff):
            raise ValueError(f"invalid_payoff:{outcome_id}")
        total_probability += float(probability)
        result += float(probability) * float(payoff)
    if not isclose(total_probability, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("probabilities_do_not_sum_to_one")
    return result


def evaluation_readiness(statuses: dict[str, str]) -> dict:
    required = {
        "market_probabilities",
        "entry_execution",
        "exit_execution",
        "fees",
        "funding",
        "payoffs",
        "account_risk",
    }
    if set(statuses) != required:
        raise ValueError("invalid_readiness_keys")
    accepted = {"available", "not_applicable", "unavailable", "scenario_only"}
    if any(status not in accepted for status in statuses.values()):
        raise ValueError("invalid_readiness_status")
    economic_keys = {
        "market_probabilities",
        "entry_execution",
        "exit_execution",
        "fees",
        "funding",
        "payoffs",
    }
    economic_ready = all(
        statuses[key] in {"available", "not_applicable"}
        for key in economic_keys
    )
    account_risk_ready = statuses["account_risk"] == "available"
    return {
        "economic_evaluation_ready": economic_ready,
        "account_risk_ready": account_risk_ready,
        "governance_policy_defined": False,
        "decision_authorized": False,
        "missing_or_scenario": sorted(
            key
            for key, status in statuses.items()
            if status not in {"available", "not_applicable"}
        ),
        "numeric_quality_score": None,
        "grade": None,
    }


SOURCE_CLAIM_LEVELS = {
    "M2-SEMANTICS": "internal_definition",
    "M3-DATA-CONTRACTS": "internal_definition",
    "M4.2-REACHABILITY": "internal_methodology",
    "M4.4-DERIVATIVES": "internal_methodology",
    "BINANCE-USD-M-MARKET-DATA": "definition",
    "BINANCE-USD-M-ACCOUNT": "definition",
    "FINRA-INSTITUTIONAL-ORDER-HANDLING-2019": "technical_foundation",
    "ALMGREN-CHRISS-2001": "technical_foundation",
    "HE-MANELA-ROSS-VON-WACHTER-2022": "technical_foundation",
    "INVESTOR-GOV-LEVERAGED-INVESTING": "technical_foundation",
}


def source_claim(source_id: str, claim: str) -> dict:
    return {
        "source_id": source_id,
        "level": SOURCE_CLAIM_LEVELS[source_id],
        "claim": claim,
    }


def common_rule(
    *,
    rule_id: str,
    name: str,
    family: str,
    analytical_blocks: list[int],
    inputs: list[str],
    formula: list[str],
    output: str,
    sources: list[dict],
    unsupported: list[str],
    limits: list[str],
    rejection: list[str],
) -> dict:
    return {
        "id": rule_id,
        "version": RULE_VERSION,
        "name": name,
        "kind": "deterministic_economic_operator",
        "analytical_blocks": analytical_blocks,
        "concrete_objective": output,
        "rule_type": "deterministic_economic_operator",
        "evidence_family": family,
        "symbols": list(SYMBOLS),
        "horizons": list(HORIZONS),
        "inputs": inputs,
        "raw_data_and_provider": inputs,
        "market_symbol_timestamp_unit_freshness": [
            "symbol must belong to the six-pair scope",
            "timestamps and freshness follow the referenced M3 contracts",
            "price and money use quote asset; quantity uses base asset",
            "rates and fractions are dimensionless unless explicitly stated",
        ],
        "exact_transformation_and_formula": formula,
        "output": output,
        "cross_pair_normalization": (
            "Dimensionless ratios remain comparable; quote-money outputs are "
            "never compared across pairs without explicit normalization."
        ),
        "applicable_horizons": list(HORIZONS),
        "activation_conditions": [
            "all declared inputs are present and valid",
            "the operator belongs to the applicable execution, exposure or "
            "economic branch",
        ],
        "non_application_conditions": rejection,
        "source_and_exact_supported_claim": sources,
        "claims_not_supported_by_source": unsupported,
        "transfer_and_observability_limits": limits,
        "rejection_or_block_conditions": rejection,
        "expected_relation_to_tp_sl_or_expiry": (
            "No direct market-probability relation is authorized. The output "
            "describes execution, exposure or payoff after market outcomes."
        ),
        "related_rules": [family],
        "double_counting_control": (
            "Use the canonical M4.6 slot for this family; derived values, "
            "containers and overlapping costs are not additional votes."
        ),
        "missing_data_behavior": (
            "Block the unavailable result and expose the missing component; "
            "do not use a neutral value or universal constant."
        ),
        "unit_tests_limits_and_invariants": limits
        + [
            "long/short signs must follow the declared direction",
            "no execution or exposure value may change market probability",
        ],
        "trace_output": [
            "rule id and version",
            "input values and units",
            "provider/receive timestamps when market data is used",
            "formula branch, output and availability status",
        ],
        "refutation_suspension_or_withdrawal": rejection
        + [
            "Suspend if provider semantics or units no longer match the "
            "documented contract."
        ],
        "lifecycle_status": (
            "formal_documented_operator_not_implemented_in_production"
        ),
        "direct_probability_effect_authorized": False,
        "numeric_weight_authorized": False,
        "production_authorized": False,
        "separate_predictive_hypothesis": None,
    }


def build_rules() -> list[dict]:
    return [
        common_rule(
            rule_id="M4-RULE-QUOTED-SPREAD-001",
            name="Spread cotizado en el instante de llegada",
            family="M4-EVIDENCE-CURRENT-EXECUTION",
            analytical_blocks=[29],
            inputs=["best_bid>0", "best_ask>=best_bid", "receive_time"],
            formula=[
                "mid=(best_bid+best_ask)/2",
                "spread_quote=best_ask-best_bid",
                "spread_fraction_mid=spread_quote/mid",
            ],
            output="Descriptor actual de coste cotizado; no penalizacion.",
            sources=[
                source_claim(
                    "BINANCE-USD-M-MARKET-DATA",
                    "Bid y ask son observables oficiales del mercado.",
                ),
                source_claim(
                    "FINRA-INSTITUTIONAL-ORDER-HANDLING-2019",
                    "El midpoint de llegada es referencia de ejecucion.",
                ),
            ],
            unsupported=[
                "Que un spread concreto prediga TP o SL.",
                "Que el spread actual sea el spread de salida futuro.",
            ],
            limits=["Snapshot actual; puede cambiar antes de ejecutar."],
            rejection=["Libro cruzado, dato no positivo o timestamp ausente."],
        ),
        common_rule(
            rule_id="M4-RULE-DEPTH-SWEEP-001",
            name="Barrido visible e implementation shortfall",
            family="M4-EVIDENCE-CURRENT-EXECUTION",
            analytical_blocks=[29],
            inputs=[
                "side buy|sell",
                "base_quantity>0",
                "bids descendentes",
                "asks ascendentes",
                "arrival midpoint",
            ],
            formula=[
                "buy consume asks; sell consume bids",
                "VWAP_filled=sum(price_i*filled_qty_i)/filled_qty",
                "D=+1 buy, -1 sell",
                "IS_filled_quote=D*(sum(price_i*filled_qty_i)-arrival_mid*filled_qty)",
                "IS_filled_fraction=IS_filled_quote/(arrival_mid*filled_qty)",
                "complete_VWAP=VWAP_filled iff filled_qty=requested_qty",
                "fill_ratio=filled_qty/requested_qty",
            ],
            output=(
                "VWAP y shortfall del tramo llenado siempre que exista fill; "
                "coste completo solo si fill_ratio=1."
            ),
            sources=[
                source_claim(
                    "FINRA-INSTITUTIONAL-ORDER-HANDLING-2019",
                    "VWAP firmado contra midpoint mide shortfall.",
                ),
                source_claim(
                    "ALMGREN-CHRISS-2001",
                    "Coste e impacto pertenecen al problema de ejecucion.",
                ),
            ],
            unsupported=[
                "Impacto permanente exacto.",
                "Slippage de una salida futura.",
                "Minimo universal de 0.02%.",
            ],
            limits=[
                "Solo profundidad visible solicitada.",
                "No garantiza fills ni incorpora latencia o cola.",
                "El coste del tramo llenado no representa el coste de la "
                "cantidad no llenada.",
                "El IS desde midpoint ya contiene medio spread y barrido; "
                "no se suma de nuevo el spread.",
            ],
            rejection=[
                "Fill ratio menor que uno bloquea el coste completo.",
                "Orden o niveles invalidos bloquean.",
            ],
        ),
        common_rule(
            rule_id="M4-RULE-FEE-SCENARIOS-001",
            name="Comision por rol de liquidez autenticado",
            family="M4-EVIDENCE-FEES",
            analytical_blocks=[29],
            inputs=[
                "notional>=0",
                "allowed_roles subset maker|taker|rpi",
                "authenticated commission rates",
                "observed_execution flag",
                "fee_asset required for observed exact cost",
            ],
            formula=[
                "fee(role)=notional*commission_rate(role)",
                "lower=min(fee(role)); upper=max(fee(role))",
                "pretrade one-role input is a scenario point, not an observation",
                "exact iff execution is observed, role is unique, notional is executed and fee_asset is known",
            ],
            output=(
                "Coste observado exacto tras ejecucion o escenario "
                "pre-trade puntual/acotado."
            ),
            sources=[
                source_claim(
                    "BINANCE-USD-M-ACCOUNT",
                    "La cuenta expone tasas maker, taker y RPI.",
                )
            ],
            unsupported=[
                "Comision universal de ida y vuelta de 0.08%.",
                "Rol de liquidez de una salida futura desconocida.",
            ],
            limits=[
                "RPI solo entra cuando el tipo de orden lo permite.",
                "Cada tramo y resultado usa su propio notional y rol.",
                "El basis bruto no se netea con comisiones; ambos conservan "
                "campos y unidades separados.",
            ],
            rejection=[
                "Sin autenticacion o tasa requerida, el coste exacto bloquea."
            ],
        ),
        common_rule(
            rule_id="M4-RULE-FUNDING-CASHFLOW-001",
            name="Flujo monetario firmado de funding",
            family="M4-EVIDENCE-FUNDING-CASHFLOW",
            analytical_blocks=[10, 29],
            inputs=[
                "side long|short",
                "base_quantity>0",
                "event mark_price>0",
                "event funding_rate signed",
            ],
            formula=[
                "position_sign=+1 long, -1 short",
                "cashflow_event=-position_sign*quantity*mark_price*rate",
                "cashflow_total=sum(cashflow_event)",
            ],
            output="Flujo firmado para eventos realizados o escenarios explicitos.",
            sources=[
                source_claim(
                    "HE-MANELA-ROSS-VON-WACHTER-2022",
                    "Funding positivo transfiere de largos a cortos.",
                ),
                source_claim(
                    "M4.4-DERIVATIVES",
                    "La ultima tasa observada no es una tasa futura.",
                ),
            ],
            unsupported=[
                "Usar abs(rate) una vez como coste para ambas direcciones.",
                "Proyectar la ultima tasa durante todo el horizonte.",
            ],
            limits=[
                "Antes del cierre solo admite escenarios, no forecast exacto."
            ],
            rejection=[
                "Eventos futuros desconocidos bloquean el funding exacto."
            ],
        ),
        common_rule(
            rule_id="M4-RULE-PLAN-EXPOSURE-001",
            name="Exposicion monetaria lineal del plan",
            family="M4-EVIDENCE-EXPOSURE-RISK",
            analytical_blocks=[30],
            inputs=[
                "side",
                "entry, TP, SL",
                "margin>0",
                "leverage>0",
            ],
            formula=[
                "notional=margin*leverage",
                "quantity=notional/entry",
                "gross_pnl(P)=direction*quantity*(P-entry)",
                "gross_reward=gross_pnl(TP)",
                "gross_risk=-gross_pnl(SL)",
                "gross_RR=gross_reward/gross_risk",
                "risk_fraction_margin=gross_risk/margin",
            ],
            output=(
                "Exposicion, recompensa y perdida brutas; sin score ni "
                "probabilidad."
            ),
            sources=[
                source_claim(
                    "M2-SEMANTICS",
                    "La geometria valida depende de la direccion.",
                ),
                source_claim(
                    "INVESTOR-GOV-LEVERAGED-INVESTING",
                    "El apalancamiento amplifica ganancias y perdidas.",
                ),
                source_claim(
                    "M3-DATA-CONTRACTS",
                    "Margen y apalancamiento pertenecen al plan de usuario.",
                ),
            ],
            unsupported=[
                "Que el apalancamiento altere la probabilidad de mercado.",
                "RR minimo 3 o distancias 0.25%/3% como universales.",
                "Precio de liquidacion exacto.",
            ],
            limits=[
                "Modelo lineal USD-M bruto, antes de costes.",
                "No incluye equity, margin mode ni maintenance brackets.",
            ],
            rejection=[
                "Geometria direccional invalida o entrada/margen/leverage no "
                "positivos.",
            ],
        ),
        common_rule(
            rule_id="M4-RULE-NET-PAYOFFS-001",
            name="Vector monetario neto por resultado",
            family="M4-EVIDENCE-ECONOMIC-EVALUATION",
            analytical_blocks=[32],
            inputs=[
                "gross_price_pnl by outcome",
                "fee_cost by outcome",
                "execution_shortfall_cost by outcome",
                "signed funding_cashflow by outcome",
            ],
            formula=[
                "net_payoff_k=gross_price_pnl_k-fee_k-IS_cost_k+funding_k",
                "no_entry direct trading cashflow=0",
            ],
            output="Payoff neto separado para TP, SL, expiry y no-entry.",
            sources=[
                source_claim(
                    "M2-SEMANTICS",
                    "Cada rama pre-trade es un resultado distinto.",
                ),
                source_claim(
                    "FINRA-INSTITUTIONAL-ORDER-HANDLING-2019",
                    "La ejecucion aporta coste y falta de fill observables.",
                ),
            ],
            unsupported=[
                "Un unico coste restado a todas las ramas.",
                "Incluir opportunity cost no modelado en no-entry.",
            ],
            limits=[
                "Si un coste de una rama falta, esa rama queda incompleta."
            ],
            rejection=[
                "Payoff exacto bloqueado por cualquier componente desconocido."
            ],
        ),
        common_rule(
            rule_id="M4-RULE-EXPECTED-VALUE-001",
            name="Identidad de valor esperado por resultados",
            family="M4-EVIDENCE-ECONOMIC-EVALUATION",
            analytical_blocks=[32],
            inputs=[
                "coherent probabilities p_k",
                "complete net payoff y_k for identical outcomes",
            ],
            formula=[
                "0<=p_k<=1",
                "sum(p_k)=1",
                "EV=sum(p_k*y_k)",
            ],
            output="Valor esperado monetario, solo cuando todos los datos existen.",
            sources=[
                source_claim(
                    "M2-SEMANTICS",
                    "Las probabilidades y payoffs deben compartir resultados.",
                )
            ],
            unsupported=[
                "El EV actual calculado con TP% y SL% no calibrados.",
                "Una decision automatica basada solo en EV.",
            ],
            limits=[
                "Probabilidades coherentes no existiran antes de M6.",
                "Costes futuros incompletos impiden un EV exacto.",
            ],
            rejection=[
                "Claves distintas, probabilidades que no suman uno o payoff "
                "incompleto.",
            ],
        ),
        common_rule(
            rule_id="M4-RULE-EVALUATION-READINESS-001",
            name="Estado explicito de disponibilidad economica",
            family="M4-EVIDENCE-ECONOMIC-EVALUATION",
            analytical_blocks=[30, 32],
            inputs=[
                "status market probabilities",
                "status entry and exit execution",
                "status fees and funding",
                "status payoffs and account risk",
            ],
            formula=[
                "economic_ready=all(required economic statuses available|N/A)",
                "account_risk_ready=(account_risk status=available)",
                "decision_authorized=false until governance is defined",
            ],
            output="Estados y faltantes; nunca score, grade o recomendacion.",
            sources=[
                source_claim(
                    "M3-DATA-CONTRACTS",
                    "Ausencia y degradacion deben declararse por dato.",
                )
            ],
            unsupported=[
                "Convertir disponibilidad en confianza numerica.",
                "Grados A/B/C o GO/NO-GO sin politica validada.",
            ],
            limits=[
                "Es control de completitud, no evidencia de rentabilidad."
            ],
            rejection=[
                "Claves o estados fuera del contrato.",
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
        if rule["separate_predictive_hypothesis"] is not None:
            raise ValueError(f"unexpected_predictive_hypothesis:{rule['id']}")
        if not rule["exact_transformation_and_formula"]:
            raise ValueError(f"missing_formula:{rule['id']}")
        if not rule["claims_not_supported_by_source"]:
            raise ValueError(f"missing_transfer_limit:{rule['id']}")


def build_catalog() -> dict:
    m3 = read_json(M3_CATALOG_PATH)
    reconciliation = read_json(M4_RECONCILIATION_PATH)
    reachability = read_json(M4_REACHABILITY_PATH)
    derivatives = read_json(M4_DERIVATIVES_PATH)
    if m3["status"] != "completed_owner_approved":
        raise ValueError("m3_not_approved")
    if reconciliation["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_1_not_completed")
    if reachability["scope"]["m4_next_subphase"] != "M4.3":
        raise ValueError("m4_2_contract_invalid")
    if derivatives["status"] != (
        "completed_internal_milestone_m4_still_in_progress"
    ):
        raise ValueError("m4_4_not_completed")
    if derivatives["scope"]["m4_next_subphase"] != "M4.5":
        raise ValueError("m4_4_does_not_lead_to_m4_5")

    rules = build_rules()
    validate_rules(rules)
    payload = {
        "version": VERSION,
        "phase": "M4",
        "subphase": "M4.5",
        "status": "completed_internal_milestone_m4_still_in_progress",
        "date": "2026-07-27",
        "scope": {
            "symbols": list(SYMBOLS),
            "horizons": list(HORIZONS),
            "p0_blocks": [29, 30, 32],
            "rules": len(rules),
            "predictive_hypotheses": 0,
            "direct_probability_effects": 0,
            "numeric_weights": 0,
            "production_modified": False,
            "analysis_engine_modified": False,
            "learning_engine_used": False,
            "m5_started": False,
            "m4_next_subphase": "M4.6",
        },
        "separation_contract": {
            "market_probability": (
                "Only M4 predictive families and M6 calibration may estimate "
                "TP/SL/expiry probabilities."
            ),
            "execution": (
                "Spread, depth, fees and fill state describe execution cost "
                "or observability, not market direction."
            ),
            "basis_and_fees": (
                "Raw basis and commissions remain separate trace fields; "
                "neither is silently netted into the other."
            ),
            "exposure": (
                "Margin and leverage scale quantity and monetary PnL, not "
                "market probability."
            ),
            "economic_evaluation": (
                "EV combines coherent probabilities with a complete payoff "
                "vector; it is unavailable before M6 and complete costs."
            ),
            "governance": (
                "Grades and decisions require a later explicit policy and "
                "are not derived in M4.5."
            ),
        },
        "blocking_contract": {
            "future_exit_book": "unobservable_pretrade_exact_cost_blocked",
            "future_funding_rates": "unobservable_pretrade_exact_cost_blocked",
            "commission_without_auth": "exact_fee_blocked",
            "insufficient_visible_depth": "complete_entry_sweep_blocked",
            "account_liquidation_inputs": "account_risk_blocked",
            "probabilities_before_m6": "expected_value_blocked",
            "unknown_governance_policy": "grade_and_decision_blocked",
        },
        "amendment": {
            "supersedes_version": "M4.5-execution-risk-v0.1",
            "reason": (
                "Correct partial-fill VWAP/shortfall semantics and reserve "
                "exact fee status for observed executions with a known role, "
                "executed notional and fee asset."
            ),
            "production_effect": False,
        },
        "sources": list(SOURCES),
        "rules": rules,
        "preregistered_hypotheses": [],
        "evidence_families": [
            {
                "id": "M4-EVIDENCE-CURRENT-EXECUTION",
                "members": [
                    "M4-RULE-QUOTED-SPREAD-001",
                    "M4-RULE-DEPTH-SWEEP-001",
                ],
                "additive_members_allowed": False,
                "reason": (
                    "IS desde midpoint ya incorpora spread y barrido visible."
                ),
            },
            {
                "id": "M4-EVIDENCE-FEES",
                "members": ["M4-RULE-FEE-SCENARIOS-001"],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-FUNDING-CASHFLOW",
                "members": ["M4-RULE-FUNDING-CASHFLOW-001"],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-EXPOSURE-RISK",
                "members": ["M4-RULE-PLAN-EXPOSURE-001"],
                "additive_members_allowed": False,
            },
            {
                "id": "M4-EVIDENCE-ECONOMIC-EVALUATION",
                "members": [
                    "M4-RULE-NET-PAYOFFS-001",
                    "M4-RULE-EXPECTED-VALUE-001",
                    "M4-RULE-EVALUATION-READINESS-001",
                ],
                "additive_members_allowed": False,
                "reason": "Son etapas dependientes de un mismo calculo.",
            },
        ],
        "supersedes_current_elements": {
            "SCORE-LIQUIDITY_PENALTY": (
                "Retirado: ejecucion separada de probabilidad de mercado."
            ),
            "OUT-FEE": (
                "Sustituido por tasa autenticada y rol por cada tramo."
            ),
            "OUT-SLIPPAGE": (
                "Sustituido por barrido visible actual; no minimo fijo."
            ),
            "OUT-FUNDING-COST": (
                "Sustituido por flujo firmado por evento; futuro bloqueado."
            ),
            "OUT-RISK-SCORE": (
                "Retirado: exposicion monetaria sin score arbitrario."
            ),
            "OUT-EV-COST": (
                "Identidad conservada; salida bloqueada hasta M6 y costes "
                "completos."
            ),
            "OUT-GRADE": "Retirado hasta politica de gobierno documentada.",
            "OUT-CONFIDENCE": (
                "Disponibilidad no se convierte en confianza numerica."
            ),
            "OUT-DECISION": "Retirado hasta politica posterior validada.",
            "OUT-LAYERED-SCORES": (
                "Retirado: no mezcla mercado, ejecucion, plan y riesgo."
            ),
            "GATE-RR_RATIO_GTE_3": "Umbral universal retirado.",
            "GATE-RISK_DISTANCE_LT_0_25": "Umbral universal retirado.",
            "GATE-RISK_DISTANCE_GTE_3": "Umbral universal retirado.",
            "GATE-REWARD_DISTANCE_GTE_3": "Umbral universal retirado.",
        },
        "summary": {
            "rules": len(rules),
            "predictive_hypotheses": 0,
            "evidence_families": 5,
            "direct_probability_effects": 0,
            "numeric_weights": 0,
            "production_modified": False,
            "current_ev_authorized": False,
            "grade_authorized": False,
            "decision_authorized": False,
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
                M4_DERIVATIVES_PATH,
            )
        ],
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                "separation_contract": payload["separation_contract"],
                "blocking_contract": payload["blocking_contract"],
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
        "# M4.5 - Ejecucion, costes, riesgo y evaluacion",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADA INTERNAMENTE; M4 SIGUE EN CURSO",
        "",
        "## 1. Resultado",
        "",
        f"- {catalog['summary']['rules']} fichas economicas formales.",
        "- 0 hipotesis predictivas: esta subfase no predice mercado.",
        "- 0 probabilidades, puntos, pesos o efectos productivos.",
        "- Produccion y aprendizaje permanecen congelados.",
        "",
        "## 2. Separacion obligatoria",
        "",
        "- Mercado: probabilidades TP/SL/expiry, calibradas mas adelante.",
        "- Ejecucion: spread, profundidad, fill, comisiones y slippage.",
        "- Exposicion: margen, apalancamiento, cantidad y PnL monetario.",
        "- Economia: payoff por resultado y EV solo con entradas completas.",
        "- Gobierno: grade y decision quedan sin definir.",
        "",
        "## 3. Formulas",
        "",
        "- `mid=(bid+ask)/2`; `spread=(ask-bid)/mid`.",
        "- `VWAP_filled=sum(p_i*q_i)/filled_qty` sobre el tramo visible llenado.",
        "- `IS_filled=D*(sum(p_i*q_i)-mid*filled_qty)`; el coste completo exige fill total.",
        "- `fee=notional*rate(role)` para maker, taker o RPI.",
        "- `funding=-position_sign*quantity*mark*rate` por evento.",
        "- `notional=margin*leverage`; `quantity=notional/entry`.",
        "- `PnL(P)=direction*quantity*(P-entry)`.",
        "- `payoff_k=gross_k-fee_k-IS_k+funding_k`.",
        "- `EV=sum(p_k*payoff_k)`, si `sum(p_k)=1`.",
        "",
        "## 4. Bloqueos reales",
        "",
        "- El libro futuro de salida no es observable en pre-trade.",
        "- Las tasas futuras de funding no se conocen exactamente.",
        "- Sin autenticacion no existe comision exacta de la cuenta.",
        "- Sin equity, margin mode y maintenance brackets no hay riesgo de",
        "  liquidacion ni riesgo de cuenta completo.",
        "- Sin probabilidades calibradas M6 no existe EV autorizado.",
        "- Sin politica documentada no existe grade ni decision autorizada.",
        "",
        "## 5. Reglas",
        "",
        "| ID | Probabilidad | Peso | Produccion |",
        "|---|---|---|---|",
    ]
    for rule in catalog["rules"]:
        lines.append(f"| `{rule['id']}` | no | no | no |")
    lines.extend(
        [
            "",
            "## 6. Elementos actuales retirados o sustituidos",
            "",
        ]
    )
    for element, decision in catalog["supersedes_current_elements"].items():
        lines.append(f"- `{element}`: {decision}")
    lines.extend(
        [
            "",
            "## 7. Siguiente paso",
            "",
            "`M4.6`: combinaciones, doble conteo y reconciliacion final.",
            "No se inicia M5 ni se modifica el motor productivo.",
            "",
            "SHA-256 del payload canonico (contratos, fuentes, reglas, "
            "familias y sustituciones): "
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
