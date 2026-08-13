# Fase 1 - Validacion controlada de reglas

- Version: `phase1-controlled-rule-validation-v0.1`.
- Dataset: `04d04c987fec51c37787c2bd3c272811a8002c6743fffea2e313f605df0de46e`.
- Efecto en produccion: **ninguno**.
- Escrituras en Supabase: **ninguna**.

## Resultado

Reglas-horizonte que superan desarrollo, calibracion, seleccion y bootstrap: **0**.
- Decision: **`evidence_insufficient_no_promotion`**.

## Baseline por horizonte

| Horizonte | Desarrollo n | Calibracion n | Seleccion n | Final n | Final log-loss | Final Brier |
|---|---:|---:|---:|---:|---:|---:|
| `intraday_short` | 103818 | 26064 | 26496 | 30524 | 0.971318 | 0.579467 |
| `intraday_wide` | 48240 | 13032 | 13236 | 15192 | 1.041561 | 0.628314 |
| `short_swing` | 3168 | 1872 | 1860 | 2088 | 1.022452 | 0.622461 |

## Reglas

| Regla | Horizonte | Estado | Delta log-loss seleccion | Delta Brier seleccion |
|---|---|---|---:|---:|
| `M4-RULE-PATH-STRUCTURE-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.003306 | -0.002077 |
| `M4-RULE-MTF-HIERARCHY-001` | `intraday_short` | `not_supported_for_probability_integration` | 0.000296 | 0.000186 |
| `M4-RULE-VOLATILITY-RANK-001` | `intraday_short` | `not_supported_for_probability_integration` | 0.001953 | 0.000488 |
| `M4-RULE-PRIOR-EXTREMA-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.001217 | -0.002589 |
| `LIB-CAND-EMA-TREND-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.005610 | -0.003249 |
| `LIB-CAND-RSI-WILDER-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.003721 | -0.002372 |
| `LIB-CAND-ATR-EXTENSION-001` | `intraday_short` | `not_supported_for_probability_integration` | 0.002106 | 0.000502 |
| `LIB-CAND-RELATIVE-VOLUME-001` | `intraday_short` | `not_supported_for_probability_integration` | 0.003474 | -0.000005 |
| `LIB-CAND-CVD-SLOPE-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.002194 | -0.003641 |
| `LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001` | `intraday_short` | `not_supported_for_probability_integration` | 0.001847 | 0.000092 |
| `LIB-CAND-FIBONACCI-DISTANCE-001` | `intraday_short` | `not_supported_for_probability_integration` | 0.005867 | 0.000453 |
| `LIB-CAND-COMPRESSION-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.005536 | -0.005187 |
| `LIB-CAND-ABSORPTION-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.001546 | -0.001448 |
| `LIB-CAND-PULLBACK-CONTEXT-001` | `intraday_short` | `not_supported_for_probability_integration` | -0.005394 | -0.004180 |
| `M4-RULE-PATH-STRUCTURE-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.001959 | -0.001448 |
| `M4-RULE-MTF-HIERARCHY-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.007645 | -0.008029 |
| `M4-RULE-VOLATILITY-RANK-001` | `intraday_wide` | `not_supported_after_multiple_test_control` | 0.051323 | 0.027578 |
| `M4-RULE-PRIOR-EXTREMA-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.000319 | -0.002875 |
| `LIB-CAND-EMA-TREND-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.010740 | -0.011751 |
| `LIB-CAND-RSI-WILDER-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.000545 | -0.000734 |
| `LIB-CAND-ATR-EXTENSION-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.006581 | -0.007832 |
| `LIB-CAND-RELATIVE-VOLUME-001` | `intraday_wide` | `not_supported_after_multiple_test_control` | 0.023421 | 0.013085 |
| `LIB-CAND-CVD-SLOPE-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.004601 | -0.005832 |
| `LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.002255 | -0.004684 |
| `LIB-CAND-FIBONACCI-DISTANCE-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.003085 | -0.006216 |
| `LIB-CAND-COMPRESSION-001` | `intraday_wide` | `not_supported_after_multiple_test_control` | 0.030345 | 0.015888 |
| `LIB-CAND-ABSORPTION-001` | `intraday_wide` | `not_supported_for_probability_integration` | 0.001146 | -0.001197 |
| `LIB-CAND-PULLBACK-CONTEXT-001` | `intraday_wide` | `not_supported_for_probability_integration` | -0.007807 | -0.008253 |
| `M4-RULE-PATH-STRUCTURE-001` | `short_swing` | `not_supported_for_probability_integration` | -0.000648 | -0.000526 |
| `M4-RULE-MTF-HIERARCHY-001` | `short_swing` | `not_supported_for_probability_integration` | -0.007654 | -0.004721 |
| `M4-RULE-VOLATILITY-RANK-001` | `short_swing` | `not_supported_for_probability_integration` | 0.063812 | 0.038393 |
| `M4-RULE-PRIOR-EXTREMA-001` | `short_swing` | `not_supported_for_probability_integration` | -0.002757 | -0.002116 |
| `LIB-CAND-EMA-TREND-001` | `short_swing` | `not_supported_for_probability_integration` | -0.041078 | -0.026683 |
| `LIB-CAND-RSI-WILDER-001` | `short_swing` | `not_supported_for_probability_integration` | -0.011259 | -0.008753 |
| `LIB-CAND-ATR-EXTENSION-001` | `short_swing` | `not_supported_for_probability_integration` | -0.019237 | -0.013921 |
| `LIB-CAND-RELATIVE-VOLUME-001` | `short_swing` | `not_supported_for_probability_integration` | 0.002554 | 0.001260 |
| `LIB-CAND-CVD-SLOPE-001` | `short_swing` | `not_supported_for_probability_integration` | 0.004065 | 0.002455 |
| `LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001` | `short_swing` | `not_supported_for_probability_integration` | -0.001041 | -0.000517 |
| `LIB-CAND-FIBONACCI-DISTANCE-001` | `short_swing` | `not_supported_for_probability_integration` | -0.012223 | -0.008744 |
| `LIB-CAND-COMPRESSION-001` | `short_swing` | `not_supported_for_probability_integration` | 0.000166 | 0.001196 |
| `LIB-CAND-ABSORPTION-001` | `short_swing` | `not_supported_for_probability_integration` | 0.007935 | 0.004415 |
| `LIB-CAND-PULLBACK-CONTEXT-001` | `short_swing` | `not_supported_for_probability_integration` | -0.037223 | -0.023919 |

## Challenger conjunto y puerta final sellada

| Horizonte | Reglas | Estado | Delta log-loss final | Delta Brier final |
|---|---:|---|---:|---:|
| `intraday_short` | 0 | `no_supported_rules_no_challenger` | -- | -- |
| `intraday_wide` | 0 | `no_supported_rules_no_challenger` | -- | -- |
| `short_swing` | 0 | `no_supported_rules_no_challenger` | -- | -- |

## Reglas bloqueadas por datos

- `M4-RULE-OPEN-INTEREST-CHANGE-001`: `exact_historical_oi_not_in_kline_archive`.
- `M4-RULE-PRICE-OI-STATE-001`: `exact_historical_oi_not_in_kline_archive`.
- `M4-RULE-SPOT-FUTURES-BASIS-001`: `synchronized_spot_book_history_unavailable`.
- `M4-RULE-MARK-INDEX-PREMIUM-001`: `mark_index_history_not_in_kline_archive`.
- `M4-RULE-FUNDING-STATE-001`: `funding_history_requires_separate_point_in_time_contract`.
- `LIB-CAND-ORDERBOOK-IMBALANCE-001`: `historical_order_book_snapshots_unavailable`.
- `LIB-CAND-FUNDING-PERCENTILE-001`: `funding_history_requires_separate_point_in_time_contract`.
- `LIB-CAND-CROWDING-PERCENTILE-001`: `historical_crowding_snapshots_unavailable`.
- `LIB-CAND-SENTIMENT-PERCENTILE-001`: `historical_sentiment_snapshots_unavailable`.
- `LIB-CAND-LIQUIDATION-ZONE-001`: `historical_liquidation_map_snapshots_unavailable`.
- `LIB-CAND-SHOCK-001`: `exact_cross_market_event_contract_unavailable`.
- `LIB-CAND-CROSS-VENUE-DIVERGENCE-001`: `synchronized_cross_venue_history_unavailable`.
