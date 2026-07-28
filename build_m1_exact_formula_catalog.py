from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DECISIONS_PATH = ROOT / "auditorias_motor" / "matriz_decisiones_m1_v0_1.json"
DEFAULT_CATALOG_PATH = (
    ROOT / "auditorias_motor" / "catalogo_exacto_reglas_formulas_m1_v0_1.json"
)
DEFAULT_REPORT_PATH = (
    ROOT
    / "auditorias_motor"
    / "2026-07-27_M1_A_catalogo_exacto_reglas_formulas.md"
)
CATALOG_VERSION = "M1-A-exact-formula-catalog-v0.1"


def spec(
    definition_type: str,
    *lines: str,
    refs: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "definition_type": definition_type,
        "exact_definition": list(lines),
        "additional_source_refs": list(refs),
        "notes": list(notes),
    }


DATA_SPECS = {
    "DATA-PRICE-KLINES": spec(
        "exact_data_contract",
        "price = float(provider_ticker_price)",
        "For each Binance kline k: close=float(k[4]); high=float(k[2]); "
        "low=float(k[3]); volume=float(k[5]); taker_buy_volume=float(k[9]).",
        "Snapshot intervals = {5m, 15m, 1h, 4h, 1d, 1w}; each request asks "
        "for 240 candles.",
        "This entry transports raw market fields. It has no direct TP/SL "
        "formula and no direct probability effect.",
        refs=(
            "data_engine.py:build_market_snapshot",
            "data_engine.py:parse_klines",
        ),
    ),
    "DATA-DEPTH-TRADES": spec(
        "exact_data_contract",
        "Depth rows are converted to (price=float(row[0]), "
        "quantity=float(row[1])) for bids and asks.",
        "Each aggTrade transports p=price, q=quantity and m=is_buyer_maker; "
        "the derived order-book and CVD formulas are catalogued separately.",
        "The current request limits are 20 depth levels per side and 500 "
        "aggregated trades.",
        "This entry has no direct TP/SL formula and no direct probability "
        "effect.",
    ),
    "DATA-DERIVATIVES": spec(
        "exact_data_contract",
        "funding_rate_pct = float(lastFundingRate) * 100.",
        "funding_avg_recent_pct = mean(float(fundingRate_i) * 100) over the "
        "last 8 returned funding records; None when no record exists.",
        "open_interest_change_pct = ((last_sumOpenInterest - "
        "first_sumOpenInterest) / first_sumOpenInterest) * 100, when at least "
        "2 records exist.",
        "OI windows: 30 x 5m, 24 x 1h and 30 x 1d. The selected window is 5m "
        "for intraday_short, 1h for intraday_wide and 1d for short_swing.",
        "Ratios and account percentages are direct float conversions of "
        "longShortRatio, longAccount*100, shortAccount*100, buySellRatio, "
        "buyVol and sellVol.",
        "This entry has no direct TP/SL formula; derived score rules are "
        "catalogued separately.",
        refs=("data_engine.py:open_interest_change",),
    ),
    "DATA-BREADTH": spec(
        "exact_data_contract",
        "Universe = first 100 assets returned by the CoinGecko markets query.",
        "advancers_H_pct = 100 * count(change_H > 0) / count(non-null "
        "change_H), for H in {1h, 24h, 7d}.",
        "median_change_H_pct = median(non-null change_H), for H in "
        "{1h, 24h, 7d}.",
        "strong_moves_24h_pct = 100 * count(abs(change_24h) >= 5) / "
        "count(non-null change_24h).",
        "This entry defines data only and has no direct TP/SL formula or "
        "probability effect. The 58/42 directional rule is a separate score "
        "entry.",
    ),
    "DATA-GLOBAL": spec(
        "exact_data_contract",
        "Direct fields: total_market_cap.usd, total_volume.usd, "
        "market_cap_percentage.btc, market_cap_percentage.eth, "
        "active_cryptocurrencies and markets.",
        "Missing or malformed nested objects produce None for their fields.",
        "This data is displayed/stored but has no direct TP/SL formula in the "
        "current engine.",
    ),
    "DATA-SENTIMENT": spec(
        "exact_data_contract",
        "fear_greed_value = int(provider.value) only when the value is made "
        "entirely of digits; otherwise None.",
        "value_classification, timestamp and time_until_update are transported "
        "without a predictive transformation.",
        "This entry has no direct TP/SL formula or probability effect. The "
        "75/25 score rule is catalogued separately.",
    ),
    "DATA-LIQUIDATIONS": spec(
        "exact_data_contract",
        "age_seconds = max(0, (now_ms-updated_at)/1000) when updated_at "
        "exists; otherwise provider meta.age_seconds.",
        "stale = provider_meta.stale OR age_seconds is None OR "
        "age_seconds > max_age_seconds; default max_age_seconds=600, "
        "environment-clamped to [60,3600].",
        "reference_basis_pct = 100*(reference_price-market_price)/market_price; "
        "price_mismatch when missing or abs(reference_basis_pct) exceeds "
        "default 1.5%, environment-clamped to [0.25,10].",
        "ratio_2pct = short_mass_within_2pct / long_mass_within_2pct when "
        "defined. Dominant side: shorts_above if ratio>=1.2; longs_below if "
        "ratio<=1/1.2; otherwise balanced.",
        "Clusters are sorted by notional_usd descending and the first 10 above "
        "(shorts) and below (longs) are retained.",
        "mode='observation' and this entry has no direct score or probability "
        "effect.",
    ),
}


PLAN_SPECS = {
    "PLAN-TP-LOG-DISTANCE": spec(
        "exact_executable_identity",
        "long: tp_log_distance = ln(take_profit / entry).",
        "short: tp_log_distance = ln(entry / take_profit).",
    ),
    "PLAN-SL-LOG-DISTANCE": spec(
        "exact_executable_identity",
        "long: sl_log_distance = ln(entry / stop_loss).",
        "short: sl_log_distance = ln(stop_loss / entry).",
    ),
    "PLAN-LOG-HORIZON-SECONDS": spec(
        "exact_executable_identity",
        "log_horizon_seconds = ln(horizon_seconds).",
        "The value is calculated only after horizon_seconds is finite and "
        "inside the limits declared for the selected time horizon.",
    ),
    "PLAN-SIDE-SIGN": spec(
        "exact_executable_identity",
        "side_sign = +1.0 for long; -1.0 for short.",
    ),
}


INDICATOR_SPECS = {
    "IND-EMA-CORE": spec(
        "exact_executable_formula",
        "alpha = 2 / (period + 1).",
        "EMA_0 = first value in the supplied window.",
        "EMA_t = (value_t - EMA_(t-1))*alpha + EMA_(t-1).",
        "An empty input returns 0.0.",
    ),
    "IND-EMA200-FALLBACK": spec(
        "exact_executable_branch",
        "If len(closes)>=200: ema_200 = EMA(closes[-220:], 200).",
        "Else: ema_200 = EMA(closes, min(80, len(closes))).",
        "Despite the fallback period being at most 80, the returned field is "
        "still named ema_200.",
    ),
    "IND-RSI14-CURRENT": spec(
        "exact_executable_formula",
        "If len(values)<=14: RSI=50.0.",
        "For the last 14 changes delta_i=value_i-value_(i-1): "
        "gain_i=max(delta_i,0); loss_i=max(-delta_i,0).",
        "avg_gain = arithmetic_mean(gain_i); avg_loss = "
        "arithmetic_mean(loss_i).",
        "If avg_loss==0: RSI=100.0; else RS=avg_gain/avg_loss and "
        "RSI=100-100/(1+RS).",
        "This is an SMA-window variant, not Wilder recursive smoothing.",
    ),
    "IND-ATR14-CURRENT": spec(
        "exact_executable_formula",
        "For i=max(1,len(closes)-14)..len(closes)-1: "
        "TR_i=max(high_i-low_i, abs(high_i-close_(i-1)), "
        "abs(low_i-close_(i-1))).",
        "ATR14 = arithmetic_mean(TR_i).",
        "If len(closes)<=1: ATR14=0.0.",
        "This is a simple mean over recent TR values, not Wilder recursive "
        "smoothing.",
    ),
    "IND-EMA-STACK": spec(
        "exact_executable_rule",
        "bullish iff EMA9 > EMA21 > EMA50.",
        "bearish iff EMA9 < EMA21 < EMA50.",
        "mixed otherwise.",
    ),
    "IND-SUPPORT-RESISTANCE": spec(
        "exact_executable_algorithm",
        "Use the last 120 candle highs and lows.",
        "resistance_candidates = highs strictly above current_price, sorted "
        "by abs(price-current_price).",
        "support_candidates = lows strictly below current_price, sorted by "
        "abs(price-current_price).",
        "For each side take the nearest 12 candidates, then return the "
        "arithmetic mean of the first min(5,n); None when n=0.",
        "distance_to_support_pct = abs(100*(current_price-support)/support); "
        "distance_to_resistance_pct = "
        "abs(100*(resistance-current_price)/current_price).",
        refs=("data_engine.py:cluster_level",),
    ),
    "IND-FIBONACCI": spec(
        "exact_executable_algorithm",
        "Use last 180 candles; unavailable when fewer than 34 closes or "
        "current_price<=0.",
        "min_move_pct = max(ATR14_pct*1.35, full_window_range_pct*0.18, 0.35).",
        "A pivot high/low is a unique maximum/minimum in a window of 3 candles "
        "on each side. Search pivots backwards and select the most recent end "
        "with the most recent prior opposite pivot whose move_pct is at least "
        "min_move_pct.",
        "Ratios: retracements={0.236,0.382,0.5,0.618,0.786}; "
        "extensions={1.272,1.618,2.0,2.618}.",
        "Up swing: retracement=end-move*r; extension=end+move*(r-1). "
        "Down swing: retracement=end+move*r; extension=end-move*(r-1).",
        "Zone uses retracement=(end-price)/move for up and "
        "(price-end)/move for down: extension if <-0.03; very superficial if "
        "<0.236; superficial if <0.382; golden_zone if <=0.618; deep if "
        "<=0.786; extreme if <=1.0; structure_broken otherwise.",
        refs=(
            "data_engine.py:detect_price_pivots",
            "data_engine.py:select_recent_fibonacci_swing",
            "data_engine.py:classify_fibonacci_price_zone",
        ),
    ),
    "IND-ORDERBOOK-PROXY": spec(
        "exact_executable_formula",
        "bid_notional = sum(price_i*quantity_i) over returned bids.",
        "ask_notional = sum(price_i*quantity_i) over returned asks.",
        "imbalance = (bid_notional-ask_notional)/(bid_notional+ask_notional); "
        "0.0 when denominator is 0.",
        "best_bid=bids[0].price; best_ask=asks[0].price; "
        "mid=(best_bid+best_ask)/2.",
        "spread_pct = 100*(best_ask-best_bid)/mid; 0.0 when mid is 0.",
    ),
    "IND-CVD-PROXY": spec(
        "exact_executable_formula",
        "notional_i = float(p_i)*float(q_i).",
        "If m_i is true (buyer is maker): sell_notional += notional_i and "
        "cvd -= notional_i; otherwise buy_notional += notional_i and "
        "cvd += notional_i.",
        "total=buy_notional+sell_notional; cvd_ratio=cvd/total, "
        "buy_ratio=buy_notional/total and sell_ratio=sell_notional/total; "
        "ratios are None when total=0.",
    ),
    "IND-PENDING-ZONE": spec(
        "exact_executable_composite",
        "Only pending entries are evaluated; market entries return unavailable "
        "with neutral score 50 and no activation/reaction values.",
        "distance_activation_pct=100*abs(current-entry)/abs(entry); "
        "ATR_units=distance/max(ATR_pct,1e-6); "
        "range_units=distance/max(recent_range_pct,1e-6).",
        "tolerance=max(0.18,min(0.75,ATR_pct*0.8)). Confluence starts at 50: "
        "Fib favorable +14; Fib adverse/alert -10; desired S/R within tolerance "
        "+13, within max(1.8*tolerance,0.55) +6, otherwise -5; technical>=62 "
        "+8, <=42 -8; aligned trend regime +8; countertrend bounce -7.",
        "Activation starts 0.50: distance<=0.75*ATR +0.18; else <=1.5*ATR "
        "+0.10; else >max(range,2.5*ATR) -0.16; trigger direction aligned/"
        "opposed to trend regime +/-0.06; volume_ratio>=1.25 +0.04; "
        "clamp [0.05,0.90].",
        "stop_noise=max(ATR_pct,recent_range_pct*0.35). Sweep starts 45: "
        "risk_distance<noise +28; else <1.6*noise +12; else -8; adverse "
        "order-book imbalance beyond +/-0.12 on limit pullback +8; "
        "clamp [5,95]. Sweep risk is high >=68, medium >=42, low otherwise.",
        "Limit pullback: rejection=clamp(0.34+(confluence-50)/130-"
        "(sweep-45)/220,[0.10,0.82]); breakout=clamp(0.28+(sweep-45)/180-"
        "(confluence-50)/170,[0.08,0.78]).",
        "Breakout/breakdown: breakout=clamp(0.35+(technical-50)/140+"
        "(volume_ratio-1)*0.08-(sweep-45)/260,[0.10,0.84]); "
        "rejection=clamp(0.30+(sweep-45)/180-(technical-50)/180,[0.08,0.78]).",
        "Pullback reaction is probable at rejection>=0.54, otherwise sweep "
        "zone when risk is high. Breakout reaction is probable at "
        "breakout>=0.54, otherwise false-breakout risk when sweep risk is high.",
        "invalidation_quality=round(clamp(58+risk_distance*5-sweep*0.32"
        "+(8 if Fib favorable else -6 if Fib adverse/alert else 0),[0,100])).",
        "Target path: 0 if reward<=0; 60 if no barrier; if barrier lies between "
        "entry and TP, round(clamp(35+map(barrier_distance,0..reward)*0.25,"
        "[15,55])); 70 if TP is within max(0.12,ATR*0.45) of barrier; else 62.",
        refs=(
            "analysis_engine.py:classify_entry_order_type",
            "analysis_engine.py:build_target_path_quality",
        ),
    ),
}


HORIZON_WEIGHTS = (
    "Horizon weights: intraday_short trend={5m:1.25,15m:1.35,1h:1.0,"
    "4h:0.45,1d:0.15}, micro=1.0, derivatives=0.85, macro=0.15, "
    "htf=0.60, funding=0.35; intraday_wide trend={5m:0.35,15m:1.10,"
    "1h:1.35,4h:1.0,1d:0.35}, micro=0.55, derivatives=1.0, macro=0.35, "
    "htf=1.0, funding=0.75; short_swing trend={5m:0.10,15m:0.20,"
    "1h:0.75,4h:1.50,1d:1.60}, micro=0.20, derivatives=1.10, macro=0.85, "
    "htf=1.35, funding=1.25."
)


SCORE_SPECS = {
    "SCORE-TREND_BIAS": spec(
        "exact_executable_score_rule",
        "Map each EMA stack to bullish=+1, bearish=-1, mixed=0. "
        "raw=sum(stack_value_tf*trend_weight_tf); multiply raw by -1 for short.",
        "normalized=raw/sum(available trend weights). Return +0.10 if "
        "normalized>=0.55; +0.05 if >=0.20; -0.09 if <=-0.55; -0.05 if "
        "<=-0.20; 0 otherwise.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-TECHNICAL_DIRECTION_BIAS": spec(
        "exact_executable_score_rule",
        "Per timeframe start s=0: EMA bullish +0.55, bearish -0.55; "
        "price_vs_EMA21>0.08 +0.25, <-0.08 -0.25; RSI 45..65 +0.20, "
        ">75 -0.25, <25 +0.10, 35..45(excluding 45) +0.05. Multiply s by -1 "
        "for short and clamp [-1,1].",
        "normalized=sum(s_tf*trend_weight_tf)/sum(available weights). "
        "direction_bias=+0.035 if normalized>=0.45; +0.015 if >=0.15; "
        "-0.040 if <=-0.45; -0.020 if <=-0.15; 0 otherwise.",
        HORIZON_WEIGHTS,
        refs=("analysis_engine.py:technical_timeframe_score",),
    ),
    "SCORE-PRICE_VS_ENTRY_BIAS": spec(
        "exact_executable_score_rule",
        "long: +0.03 when current_price<=entry, else -0.02.",
        "short: +0.03 when current_price>=entry, else -0.02.",
    ),
    "SCORE-VOLUME_BIAS": spec(
        "exact_executable_score_rule",
        "raw=+0.025 if volume_ratio>1.25; -0.015 if volume_ratio<0.65; "
        "0 otherwise.",
        "volume_bias = raw * max(0.5,micro_weight).",
        HORIZON_WEIGHTS,
    ),
    "SCORE-ORDER_BOOK_BIAS": spec(
        "exact_executable_score_rule",
        "long raw=+0.016 if imbalance>0.12; -0.016 if imbalance<-0.12; "
        "0 otherwise.",
        "short raw=+0.016 if imbalance<-0.12; -0.016 if imbalance>0.12; "
        "0 otherwise.",
        "order_book_bias=raw*micro_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-MOMENTUM_BIAS": spec(
        "exact_executable_score_rule",
        "long raw=-0.025 if RSI>72; +0.020 if 45<=RSI<=62; 0 otherwise.",
        "short raw=-0.025 if RSI<28; +0.020 if 38<=RSI<=55; 0 otherwise.",
        "momentum_bias=raw*micro_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-MARKET_REGIME_BIAS": spec(
        "exact_executable_score_rule",
        "Regime: compression if recent_range_pct<0.45 and ATR_pct<0.08; "
        "else uptrend if >=3 bullish stacks; else downtrend if >=3 bearish "
        "stacks; else countertrend bounce if 4h stack opposes side; else mixed.",
        "weight=0.85 intraday_short, 1.0 intraday_wide, 1.15 short_swing. "
        "Aligned trend returns +0.024*weight; opposing trend returns "
        "-0.028*weight; countertrend bounce returns "
        "-0.018*htf_penalty_weight; compression/mixed return 0.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT": spec(
        "exact_executable_score_rule",
        "Fib score starts 50. Swing aligned +10 else -14; golden-zone entry "
        "+14; superficial +6; extension/very-superficial -8; extreme/broken "
        "-12; entry near a named retracement +4; TP near extension +5 else TP "
        "in extension -5; SL near retracement -4; S/R confluence +6.",
        "Near tolerance=max(0.18,min(0.70,ATR_pct*0.65)); target tolerance is "
        "max(that,0.35). Clamp rounded score to [18,88].",
        "score>=68: adjustment=0, risk_addition=0, execution=-4. "
        "score<=38: adjustment=-0.02 if swing not aligned else -0.01, "
        "risk=+0.04, execution=+8. score<=46: adjustment=-0.01, risk=+0.02, "
        "execution=+5. Otherwise all 0.",
    ),
    "SCORE-ZONE_PROBABILITY_ADJUSTMENT": spec(
        "exact_executable_score_rule",
        "Start adjustment=0 and risk_addition=0. Limit pullback: probable "
        "rebound with confluence>=65 and non-high sweep adds +0.018; sweep "
        "zone or high sweep adds -0.025 TP and +0.035 risk.",
        "Stop breakout/breakdown: probable breakout with confluence>=60 and "
        "target_path>=55 adds +0.014; false-breakout or high sweep adds "
        "-0.025 TP and +0.035 risk.",
        "Exceptional confluence>=78, target_path>=62, invalidation>=52 and "
        "non-high sweep adds +0.007. Confluence<=42 subtracts 0.012 and adds "
        "0.012 risk; target_path<=40 subtracts 0.012 and adds 0.010 risk; "
        "invalidation<=38 subtracts 0.012 and adds 0.012 risk.",
        "Activation>0.72 with high sweep adds 0.010 risk. Final TP adjustment "
        "is rounded clamp [-0.035,+0.025]; risk addition rounded clamp [0,0.06].",
    ),
    "SCORE-TAKER_FLOW_BIAS": spec(
        "exact_executable_score_rule",
        "If ratio is missing/zero return 0. Long: +0.020 if ratio>1.12, "
        "-0.020 if ratio<0.88, else 0. Short is symmetric.",
        "taker_flow_bias=raw*derivatives_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-CVD_BIAS": spec(
        "exact_executable_score_rule",
        "If CVD ratio is None return 0. Long: +0.018 if ratio>0.12, -0.018 "
        "if ratio<-0.12, else 0. Short is symmetric.",
        "cvd_bias=raw*micro_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-OI_TREND_BIAS": spec(
        "exact_executable_score_rule",
        "If OI change is None, OI change<0.2, or 24h price change is zero: 0.",
        "price_direction=sign(price_change_24h). directional_pressure="
        "price_direction for long and -price_direction for short. Return "
        "+0.020 if pressure>0 else -0.020.",
        "oi_trend_bias=raw*derivatives_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-BREADTH_BIAS": spec(
        "exact_executable_score_rule",
        "bullish_breadth iff advancers_24h_pct>=58 and median_change_24h_pct>0; "
        "bearish_breadth iff advancers<=42 and median<0.",
        "Long returns +0.020 bullish, -0.020 bearish, else 0; short symmetric.",
        "breadth_bias=raw*max(0.5,macro_weight).",
        HORIZON_WEIGHTS,
    ),
    "SCORE-VOLATILITY_PENALTY": spec(
        "exact_executable_score_rule",
        "risk_distance_pct=100*abs(stop_loss-entry)/entry.",
        "volatility_penalty=0.07 if risk_distance_pct < "
        "max(recent_range_pct,ATR_pct)*0.35; otherwise 0.",
    ),
    "SCORE-LIQUIDITY_PENALTY": spec(
        "exact_executable_score_rule",
        "liquidity_penalty=0.03 if spread_pct>0.04; otherwise 0.",
    ),
    "SCORE-OVEREXTENSION_PENALTY": spec(
        "exact_executable_score_rule",
        "overextension_penalty=0.025 if abs(price_vs_EMA21_pct) > "
        "max(0.5,ATR_pct*1.8); otherwise 0.",
    ),
    "SCORE-FUNDING_PENALTY": spec(
        "exact_executable_score_rule",
        "raw=0.025 for long when funding_rate_pct>0.03, or for short when "
        "funding_rate_pct<-0.03; 0 when missing or otherwise.",
        "funding_penalty=raw*funding_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-FUNDING_RELATIVE_PENALTY": spec(
        "exact_executable_score_rule",
        "Return 0 when current/mean funding is missing or "
        "abs(mean)<0.000001.",
        "relative_multiple=abs(current_funding)/max(abs(mean_funding),1e-6). "
        "raw=0.010 when multiple>=1.8 and current funding is positive for long "
        "or negative for short; otherwise 0.",
        "funding_relative_penalty=raw*funding_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-CROWDING_PENALTY": spec(
        "exact_executable_score_rule",
        "Return 0 if ratio is missing/zero. Return 0.015 when long and "
        "global_long_short_ratio>2.0, or short and ratio<0.5; else 0.",
    ),
    "SCORE-LEVEL_PENALTY": spec(
        "exact_executable_score_rule",
        "reward_distance_pct=100*abs(TP-entry)/entry.",
        "For long use distance_to_resistance; for short use "
        "distance_to_support. Return 0.025 when the selected distance is "
        "defined and <max(0.25,reward_distance_pct*0.35); else 0.",
    ),
    "SCORE-SENTIMENT_PENALTY": spec(
        "exact_executable_score_rule",
        "Return 0 when Fear & Greed is missing. Return 0.015 for long when "
        "value>=75 or short when value<=25; otherwise 0.",
    ),
    "SCORE-HIGHER_TIMEFRAME_PENALTY": spec(
        "exact_executable_score_rule",
        "Confirmation timeframe: 1h intraday_short, 4h intraday_wide, "
        "1w short_swing; fall back to 4h when absent.",
        "base=0.018*htf_penalty_weight. Return base if confirmation EMA stack "
        "is bearish for long or bullish for short; else 0.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-TECHNICAL_ENTRY_TIMING_PENALTY": spec(
        "exact_executable_score_rule",
        "Use the first primary timeframe. stretch=max(0.45,ATR_pct*1.7).",
        "Penalty=0.020 when long and RSI>=72 and price_vs_EMA21>stretch, or "
        "short and RSI<=28 and price_vs_EMA21<-stretch; otherwise 0.",
    ),
    "SCORE-TECHNICAL_BARRIER_PENALTY": spec(
        "exact_executable_score_rule",
        "Use resistance distance for long and support distance for short. "
        "When barrier is defined and reward_distance>0: penalty=0.025 if "
        "barrier_distance<0.55*reward; else 0.012 if <0.85*reward; else 0.",
    ),
    "SCORE-OI_CONTEXT_PENALTY": spec(
        "exact_executable_score_rule",
        "Return 0 if OI change is missing. Return 0.012 when long with "
        "price_change_24h>0.5 and OI_change<-0.2, or short with "
        "price_change_24h<-0.5 and OI_change<-0.2; otherwise 0.",
        "oi_context_penalty=raw*derivatives_weight.",
        HORIZON_WEIGHTS,
    ),
    "SCORE-CONTRADICTION_PENALTY": spec(
        "exact_executable_score_rule",
        "Count one contradiction for opposite non-zero signs between "
        "cvd_bias and taker_flow_bias; one each when oi_context_penalty, "
        "level_penalty or htf_penalty is non-zero.",
        "Return 0.045 for count>=4; 0.032 for count=3; 0.018 for count=2; "
        "0 for count<2.",
    ),
    "SCORE-RISK_CALIBRATION_TP_ADJUSTMENT": spec(
        "exact_executable_aggregate",
        "tp_adjustment=sum(tp_delta of every active GATE entry in this "
        "catalogue).",
        "Returned value=round(max(-0.16,tp_adjustment),4). All current gate "
        "TP deltas are non-positive, so there is no positive contribution.",
    ),
    "SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT": spec(
        "exact_executable_score_rule",
        "range_adjustment=+0.04 if activation<0.28; else +0.02 if "
        "activation<0.42; otherwise 0.",
        "Returned value=round(clamp(range_adjustment,[0,0.04]),4).",
    ),
    "SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT": spec(
        "exact_executable_constant",
        "range_adjustment is initialized to 0.0 and no current gate changes it.",
        "Returned value=round(range_adjustment,4)=0.0 for every input.",
    ),
}


GATE_DEFINITIONS = {
    "GATE-SL_PROBABILITY_GTE_55": (
        "sl_probability>=0.55",
        (-0.045, 0.10, 12, 10, 10, 10, "D", True),
        "This is the first branch; the >=0.50 gate is skipped.",
    ),
    "GATE-SL_PROBABILITY_GTE_50": (
        "0.50<=sl_probability<0.55",
        (-0.025, 0.06, 8, 6, 6, 6, "C", False),
        "This is the elif branch after the >=0.55 test.",
    ),
    "GATE-DIRECTION_SCORE_LT_40": (
        "first_pass_tp_probability<0.40",
        (-0.025, 0.07, 8, 8, 6, 6, "D", True),
        "",
    ),
    "GATE-TECHNICAL_SCORE_LT_40": (
        "technical_rating.score<40 (missing score defaults to 50)",
        (-0.020, 0.07, 8, 8, 6, 6, "C", False),
        "",
    ),
    "GATE-RR_RATIO_GTE_3": (
        "risk_reward_ratio>=3.0",
        ("-0.035 if reward_distance>=3.0 else -0.020", 0.08, 15, 5, 12, 8, "C", False),
        "",
    ),
    "GATE-REWARD_DISTANCE_GTE_3": (
        "reward_distance_pct>=3.0",
        (-0.025, 0.07, 10, 4, 10, 6, "C", False),
        "Can activate together with the R/R>=3 gate.",
    ),
    "GATE-RISK_DISTANCE_LT_0_25": (
        "risk_distance_pct<0.25",
        (-0.025, 0.10, 10, 6, 8, 12, "C", False),
        "This is the first branch; the >=3.0 branch is skipped.",
    ),
    "GATE-RISK_DISTANCE_GTE_3": (
        "risk_distance_pct>=3.0",
        (0.0, 0.08, 10, 4, 8, 6, "C", False),
        "This is the elif branch after the <0.25 test.",
    ),
    "GATE-TICKER_24H_CONTRA_SIDE": (
        "(long and price_change_24h<=-0.25) OR "
        "(short and price_change_24h>=0.25)",
        (-0.025, 0.05, 6, 6, 4, 4, "C", False),
        "Missing price change does not activate the gate.",
    ),
    "GATE-EMA_STACK_15M_CONTRA_SIDE": (
        "(long and EMA_stack_15m=='bearish') OR "
        "(short and EMA_stack_15m=='bullish')",
        (-0.020, 0.04, 6, 6, 4, 4, "C", False),
        "Missing timeframe does not activate the gate.",
    ),
    "GATE-PRICE_VS_EMA_1H_CONTRA_SIDE": (
        "(long and price_vs_EMA21_1h<=-0.08) OR "
        "(short and price_vs_EMA21_1h>=0.08)",
        (-0.020, 0.04, 6, 6, 4, 4, "C", False),
        "Missing value does not activate the gate.",
    ),
    "GATE-PENDING_ZONE_NEGATIVE_ADJUSTMENT": (
        "zone_probability_adjustment<0",
        (-0.015, 0.04, 6, 5, 4, 4, "C", False),
        "",
    ),
    "GATE-PENDING_STOP_BREAKDOWN": (
        "entry_order_type=='stop_breakdown'",
        (-0.030, 0.08, 10, 8, 8, 8, "D", True),
        "",
    ),
    "GATE-PENDING_LIQUIDITY_SWEEP_HIGH": (
        "liquidity_sweep_risk=='alto'",
        (-0.020, 0.05, 7, 6, 5, 6, "C", False),
        "",
    ),
    "GATE-PENDING_FALSE_BREAKOUT_RISK": (
        "reaction_bias=='falsa_ruptura_riesgo'",
        (-0.020, 0.05, 7, 6, 5, 6, "C", False),
        "",
    ),
    "GATE-EXTREME_FIB_EXTREME_SENTIMENT_CLUSTER": (
        "extreme_fibonacci AND extreme_sentiment, where "
        "extreme_fibonacci=(Fib bias=='desfavorable' AND "
        "(Fib score<30 OR entry_zone=='retroceso_extremo')) and "
        "extreme_sentiment=(sentiment_penalty>=0.01)",
        (-0.035, 0.08, 12, 10, 9, 8, "C", False),
        "",
    ),
    "GATE-EXTREME_FIB_SENTIMENT_CVD_CONTRA": (
        "extreme_fibonacci AND extreme_sentiment AND cvd_bias<-0.005",
        (-0.015, 0.03, 4, 5, 4, 4, "C", False),
        "Nested inside the preceding Fib+sentiment gate.",
    ),
    "GATE-RSI_EXTREME_MULTI_RISK_CLUSTER": (
        "rsi_extreme AND material_risk_count>=2, where rsi_extreme="
        "(short and RSI<=30) OR (long and RSI>=70), and material_risk_count="
        "count_true(extreme_fibonacci,extreme_sentiment,cvd_bias<-0.005)",
        (-0.012, 0.025, 4, 4, 3, 4, "C", False),
        "",
    ),
    "GATE-RSI_EXTREME_WITH_FIB_SENTIMENT_CLUSTER": (
        "rsi_extreme AND extreme_fibonacci AND extreme_sentiment",
        (-0.008, 0.015, 3, 3, 2, 3, "C", False),
        "Nested inside the RSI-extreme multi-risk gate.",
    ),
}


def gate_specs() -> dict[str, dict[str, Any]]:
    results = {}
    for rule_id, (condition, effects, interaction) in GATE_DEFINITIONS.items():
        tp, risk, quality, confidence, ev, execution, cap, force = effects
        lines = [
            f"Condition: {condition}.",
            "On activation: "
            f"tp_delta={tp}; risk_delta={risk}; quality_penalty+={quality}; "
            f"confidence_penalty+={confidence}; EV_score_penalty+={ev}; "
            f"execution_risk_addition+={execution}; grade_cap={cap}; "
            f"force_observar={force}.",
            "All active gates accumulate. Aggregate caps: TP adjustment has "
            "floor -0.16; risk addition cap 0.28; quality penalty cap 35; "
            "confidence penalty cap 28; EV-score penalty cap 30; execution "
            "risk addition cap 32. The strictest grade cap wins.",
        ]
        if interaction:
            lines.append(interaction)
        results[rule_id] = spec("exact_executable_gate", *lines)
    return results


OUTPUT_SPECS = {
    "OUT-TP-ADDITIVE": spec(
        "exact_executable_output",
        "tp_raw=0.50 + trend_bias + technical_direction_bias + "
        "price_vs_entry_bias + volume_bias + order_book_bias + momentum_bias "
        "+ regime_bias + fibonacci_adjustment + zone_adjustment + "
        "taker_flow_bias + cvd_bias + oi_trend_bias + breadth_bias "
        "- volatility_penalty - liquidity_penalty - overextension_penalty "
        "- funding_penalty - funding_relative_penalty - crowding_penalty "
        "- level_penalty - sentiment_penalty - htf_penalty "
        "- technical_entry_timing_penalty - technical_barrier_penalty "
        "- oi_context_penalty - contradiction_penalty.",
        "Every named term is defined as its own SCORE entry in this catalogue.",
    ),
    "OUT-TP-CAPS": spec(
        "exact_executable_output",
        "first_pass_tp = min(0.74,max(0.26,tp_raw)).",
        "final_tp = min(0.74,max(0.22,first_pass_tp + "
        "risk_calibration_tp_adjustment)).",
    ),
    "OUT-RANGE": spec(
        "exact_executable_output",
        "base_range=0.12 for regime compression/mixed; else 0.10 when "
        "contradiction_penalty>=0.03; else 0.08 when recent_range_pct<1.2; "
        "else 0.06.",
        "first_range=min(0.20,base_range+zone_range_adjustment).",
        "final_range=min(0.22,max(0.04,first_range+"
        "risk_calibration_range_adjustment)).",
    ),
    "OUT-SL-RESIDUAL": spec(
        "exact_executable_output",
        "first_pass_sl=max(0.05,1-first_pass_tp-first_range).",
        "final_sl=max(0.05,1-final_tp-final_range).",
        "There is no final renormalization; TP+SL+range can exceed 1 when the "
        "0.05 SL floor binds.",
    ),
    "OUT-PROBABILITY-BANDS": spec(
        "exact_executable_output",
        "width=0.04 if contradiction_penalty==0; 0.06 if "
        "0<contradiction_penalty<0.03; 0.08 otherwise.",
        "For TP and SL: low=max(0.01,p-width/2), high=min(0.99,p+width/2).",
        "For range use min(width,0.05) in the same formula. Values are rounded "
        "to 4 decimals; label formats unrounded bounds as whole percentages.",
    ),
    "OUT-EV-COST": spec(
        "exact_executable_identity",
        "notional=margin*leverage; gross_win=notional*(reward_distance_pct/100); "
        "gross_loss=notional*(risk_distance_pct/100).",
        "estimated_cost=notional*(fee_rate_round_trip+"
        "slippage_rate_round_trip)+funding_cost.",
        "net_win=gross_win-estimated_cost; net_loss=gross_loss+estimated_cost.",
        "EV_USDT=TP*net_win - SL*net_loss - range*estimated_cost.",
        "EV_pct_margin=100*EV_USDT/margin when margin!=0 else 0; "
        "EV_pct_notional=100*EV_USDT/notional when notional!=0 else 0.",
    ),
    "OUT-FEE": spec(
        "exact_executable_cost_rule",
        "fee_rate_round_trip=0.0008.",
        "fee_component=notional*0.0008.",
    ),
    "OUT-SLIPPAGE": spec(
        "exact_executable_cost_rule",
        "slippage_rate_round_trip=max(spread_pct/100,0.0002).",
        "slippage_component=notional*slippage_rate_round_trip.",
    ),
    "OUT-FUNDING-COST": spec(
        "exact_executable_cost_rule",
        "funding_cost=notional*abs(funding_rate_pct or 0)/100.",
        "The current formula applies one unsigned funding observation, without "
        "multiplying by expected holding periods.",
    ),
    "OUT-RISK-SCORE": spec(
        "exact_executable_output",
        "risk_raw=(0.20 if stop_too_close else 0)+(0.12 if R/R<1.2 else 0)"
        "+(0.08 if recent_range_pct>2.5 else 0)+(0.06 if spread_pct>0.04 else 0)"
        "+(0.05 if overextension_penalty else 0)+(0.06 if funding_penalty else 0)"
        "+(0.04 if funding_relative_penalty else 0)+(0.04 if crowding_penalty else 0)"
        "+(0.05 if level_penalty else 0)+(0.03 if sentiment_penalty else 0)"
        "+(0.07 if htf_penalty else 0)+(0.05 if timing_penalty else 0)"
        "+(0.05 if barrier_penalty else 0)+Fib_risk+zone_risk+calibration_risk"
        "+(0.08 if contradiction_penalty>=0.03 else 0).",
        "risk_score=clamp(risk_raw,[0,1]). Level: high>=0.42; medium-high>=0.24; "
        "medium>=0.12; low otherwise.",
    ),
    "OUT-GRADE": spec(
        "exact_executable_policy",
        "A iff TP>=0.62 and risk_score<0.20 and EV_score>=58.",
        "Else B iff TP>=0.52 and risk_score<0.36 and EV_score>=50.",
        "Else C iff TP>=0.44 and EV_score>=42; else D.",
        "Then apply the strictest active calibration grade cap using order "
        "A<B<C<D; a cap can only worsen the grade.",
    ),
    "OUT-CONFIDENCE": spec(
        "exact_executable_policy",
        "confidence='alta' if confidence_score>=76; 'media' if >=61; "
        "'media-baja' if >=46; 'baja' otherwise.",
    ),
    "OUT-DECISION": spec(
        "exact_executable_policy",
        "In order: if force_observar then 'observar'; else if EV_USDT<0 then "
        "'observar'; else if grade in {A,B}, risk!='alto' and confidence in "
        "{alta,media}, then 'simular'; else if grade in {B,C} and "
        "risk!='alto', then 'simular con tamano prudente'; else 'observar'.",
    ),
    "OUT-LAYERED-SCORES": spec(
        "exact_executable_output",
        "map100(x,lo,hi)=round(clamp((x-lo)/(hi-lo),[0,1])*100), or 50 if "
        "hi==lo. direction_score=round(TP*100).",
        "risk_design_penalty=min(22,risk_distance_pct*4.5); "
        "ev_design_score=map100(EV_pct_notional,-0.8,1.2).",
        "quality=round(clamp(42+0.16*map100(R/R,0.8,3.2)"
        "+0.22*ev_design_score+0.12*(Fib_score-50)-risk_design_penalty,[0,100])); "
        "then max(0,quality-calibration_quality_penalty).",
        "execution=round(clamp(30+220*volatility_penalty+300*level_penalty"
        "+Fib_execution+250*liquidity_penalty+calibration_execution"
        "+0.35*map100(spread_pct,0,0.08),[0,100])).",
        "alignment starts 70; subtract round(700*contradiction_penalty) when "
        "non-zero; subtract 12 when HTF penalty; add round(420*regime_bias); "
        "subtract 12 when taker_flow_bias*cvd_bias<0; add technical "
        "confidence_adjustment; subtract calibration confidence penalty. "
        "confidence_score=clamp(alignment,[15,95]).",
        "EV_score=max(0,map100(EV_pct_notional,-1.0,1.6)-"
        "calibration_EV_penalty).",
        refs=("analysis_engine.py:score_to_percent",),
    ),
    "OUT-HORIZON-FALLBACK": spec(
        "exact_executable_fallback",
        "profile = TIME_HORIZON_PROFILES.get(requested_value, "
        "TIME_HORIZON_PROFILES['intraday_short']).",
        "Every unknown horizon silently uses intraday_short parameters.",
    ),
    "OUT-MISSING-DATA": spec(
        "exact_executable_fallback",
        "When a timeframe lacks any of closes/highs/lows/volumes/"
        "taker_buy_volumes: EMA9=EMA21=EMA50=EMA200=current_price; RSI=50; "
        "ATR=ATR_pct=range=last_body=distances=price_vs_EMA=0; "
        "volume_ratio=1; taker_buy_ratio=0.5; position_in_range=0.5; "
        "EMA_stack='mixed'.",
        "Other current neutralizations include missing score inputs returning "
        "0 in their individual SCORE rules and missing derivatives falling "
        "back from selected period to the legacy 5m fields.",
    ),
    "OUT-RISK-CAL-METRIC": spec(
        "exact_executable_presentation",
        "If at least one calibration flag is active: "
        "display_score=max(0,100-10*len(flags)-round(100*risk_addition)); "
        "bias='desfavorable'.",
        "If no flag is active: display_score=82 and bias='neutral'.",
        "This is presentation only and does not feed TP, SL, grade or decision.",
    ),
}


def exact_specs() -> dict[str, dict[str, Any]]:
    groups = (
        DATA_SPECS,
        PLAN_SPECS,
        INDICATOR_SPECS,
        SCORE_SPECS,
        gate_specs(),
        OUTPUT_SPECS,
    )
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        overlap = set(merged) & set(group)
        if overlap:
            raise ValueError(f"Duplicate exact specs: {sorted(overlap)}")
        merged.update(group)
    return merged


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_source_ref(ref: str) -> dict[str, Any]:
    try:
        file_name, symbol = ref.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"Invalid source ref {ref!r}") from exc
    path = ROOT / file_name
    if not path.is_file():
        raise ValueError(f"Missing source file for {ref}: {path}")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == symbol
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one function {symbol!r} in {file_name}, "
            f"found {len(matches)}"
        )
    node = matches[0]
    lines = source.splitlines(keepends=True)
    snippet = "".join(lines[node.lineno - 1 : node.end_lineno])
    return {
        "reference": ref,
        "file": file_name,
        "symbol": symbol,
        "start_line": node.lineno,
        "end_line": node.end_lineno,
        "function_sha256": sha256_text(snippet),
    }


def build_catalog() -> dict[str, Any]:
    decisions_payload = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    decisions = decisions_payload["decisions"]
    specs = exact_specs()
    decision_ids = [item["id"] for item in decisions]
    missing = set(decision_ids) - set(specs)
    extra = set(specs) - set(decision_ids)
    if missing or extra:
        raise ValueError(
            f"Exact catalog mismatch; missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )

    entries = []
    source_cache: dict[str, dict[str, Any]] = {}
    for index, decision in enumerate(decisions, start=1):
        rule_spec = specs[decision["id"]]
        refs = list(
            dict.fromkeys(
                decision["implementation_refs"]
                + rule_spec["additional_source_refs"]
            )
        )
        anchors = []
        for ref in refs:
            if ref not in source_cache:
                source_cache[ref] = resolve_source_ref(ref)
            anchors.append(source_cache[ref])
        entries.append(
            {
                "catalog_index": index,
                "id": decision["id"],
                "name": decision["name"],
                "origin": decision["origin"],
                "current_layer": decision["current_layer"],
                "current_kind": decision["current_kind"],
                "definition_type": rule_spec["definition_type"],
                "current_formula_summary": decision["formula"],
                "exact_definition": rule_spec["exact_definition"],
                "definition_complete_for_current_implementation": True,
                "source_anchors": anchors,
                "source_ids": decision["source_ids"],
                "published_support": decision["published_support"],
                "transfer_limit": decision["transfer_limit"],
                "reliability_tier": decision["reliability_tier"],
                "notes": rule_spec["notes"],
                "m1_decision": decision["m1_decision"],
                "required_action": decision["required_action"],
                "initial_action_phase": decision["initial_action_phase"],
                "replacement_phase": decision["replacement_phase"],
                "direct_probability_authorized": decision[
                    "direct_probability_authorized"
                ],
            }
        )

    payload: dict[str, Any] = {
        "catalog_version": CATALOG_VERSION,
        "status": "completed_owner_approved_2026_07_27",
        "purpose": (
            "Exact 86/86 inventory of the formulas, data contracts, "
            "algorithms, gates, outputs and policies in the audited universe."
        ),
        "scope": {
            "m1_closed": True,
            "m1_a_closed": True,
            "m1_reopened": False,
            "m2_started": False,
            "production_modified": False,
            "learning_engine_used": False,
        },
        "source": {
            "m1_decisions_path": str(DECISIONS_PATH.relative_to(ROOT)),
            "m1_decisions_sha256": file_sha256(DECISIONS_PATH),
            "m1_decisions_catalog_sha256": decisions_payload[
                "decisions_sha256"
            ],
        },
        "summary": {
            "entries": len(entries),
            "unique_ids": len({item["id"] for item in entries}),
            "current_production_entries": sum(
                item["origin"] == "current_production_engine"
                for item in entries
            ),
            "contract_infrastructure_entries": sum(
                item["origin"] == "contract_infrastructure_only"
                for item in entries
            ),
            "complete_current_definitions": sum(
                item["definition_complete_for_current_implementation"]
                for item in entries
            ),
            "definition_type_counts": dict(
                sorted(Counter(item["definition_type"] for item in entries).items())
            ),
            "kind_counts": dict(
                sorted(Counter(item["current_kind"] for item in entries).items())
            ),
            "direct_probability_authorized": sum(
                item["direct_probability_authorized"] for item in entries
            ),
            "resolved_source_references": len(source_cache),
        },
        "entries": entries,
    }
    payload["catalog_sha256"] = sha256_text(canonical_json(entries))
    return payload


def render_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# M1-A - Catalogo exacto de reglas y formulas actuales",
        "",
        "Fecha: 2026-07-27",
        "Estado: COMPLETADO Y APROBADO EL 2026-07-27",
        "",
        "## 1. Alcance y garantia",
        "",
        "Este anexo expande las 86 entradas decididas en M1. No identifica solo",
        "su nombre: conserva la definicion ejecutable actual, todas las constantes",
        "y ramas relevantes, su orden o caps cuando aplican, y la enlaza con la",
        "funcion concreta y su SHA-256.",
        "",
        "La palabra `exacta` significa exacta respecto al codigo actual. No",
        "significa que la regla sea valida, fiable o autorizada como predictor.",
        "Los contratos de datos se documentan como contratos; no se les inventa",
        "una formula predictiva.",
        "",
        f"- Entradas: **{summary['entries']} / 86**.",
        f"- Motor productivo actual: **{summary['current_production_entries']}**.",
        f"- Infraestructura contractual aislada: "
        f"**{summary['contract_infrastructure_entries']}**.",
        f"- Definiciones actuales completas: "
        f"**{summary['complete_current_definitions']} / 86**.",
        f"- Referencias de funcion resueltas: "
        f"**{summary['resolved_source_references']}**.",
        f"- Efectos predictivos autorizados por M1-A: "
        f"**{summary['direct_probability_authorized']}**.",
        f"- SHA-256 del catalogo: `{payload['catalog_sha256']}`.",
        "",
        "M1 permanece cerrada y aprobada. M2 no se ha iniciado y el motor",
        "productivo no ha sido modificado.",
        "",
        "## 2. Tipos de definicion",
        "",
        "| Tipo | Cantidad |",
        "|---|---:|",
    ]
    for definition_type, count in summary["definition_type_counts"].items():
        lines.append(f"| `{definition_type}` | {count} |")

    lines.extend(
        [
            "",
            "## 3. Listado exacto 86/86",
            "",
        ]
    )
    for item in payload["entries"]:
        lines.extend(
            [
                f"### {item['catalog_index']:02d}. {item['id']} - {item['name']}",
                "",
                f"- Origen: `{item['origin']}`.",
                f"- Capa/tipo actual: `{item['current_layer']}` / "
                f"`{item['current_kind']}`.",
                f"- Tipo de definicion exacta: `{item['definition_type']}`.",
                f"- Resumen anterior: {item['current_formula_summary']}",
                "",
                "Definicion exacta actual:",
                "",
                "```text",
                *item["exact_definition"],
                "```",
                "",
                "Anclajes ejecutables:",
                "",
            ]
        )
        for anchor in item["source_anchors"]:
            lines.append(
                f"- `{anchor['file']}:{anchor['start_line']}-"
                f"{anchor['end_line']}` (`{anchor['symbol']}`), SHA-256 "
                f"`{anchor['function_sha256']}`."
            )
        lines.extend(
            [
                "",
                f"Respaldo declarado: {item['published_support']}",
                "",
                f"Limite de transferencia: {item['transfer_limit']}",
                "",
                f"Decision M1: `{item['m1_decision']}`. "
                f"Accion inicial `{item['initial_action_phase']}`; posible "
                f"reemplazo `{item['replacement_phase']}`.",
                "",
            ]
        )
        if item["notes"]:
            lines.append("Notas:")
            lines.append("")
            lines.extend(f"- {note}" for note in item["notes"])
            lines.append("")

    lines.extend(
        [
            "## 4. Regla de mantenimiento",
            "",
            "El JSON es el artefacto canonico. El generador vuelve a resolver cada",
            "funcion y recalcula su SHA-256. `--check` falla si el informe o el",
            "JSON dejan de coincidir con el generador; las pruebas fallan si falta",
            "una entrada, una definicion o un anclaje.",
            "",
            "Este anexo describe lo que existe y no legitima ninguna heuristica.",
            "El propietario aprobo M1-A el 2026-07-27. M1 queda completamente",
            "cerrada y M2 pasa a ser la siguiente fase pendiente, todavia no",
            "iniciada.",
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
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    payload = build_catalog()
    catalog_text = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
    report_text = render_report(payload)
    write_or_check(args.catalog, catalog_text, args.check)
    write_or_check(args.report, report_text, args.check)


if __name__ == "__main__":
    main()
