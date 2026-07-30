# Auditoria integral de reglas sobre operaciones cerradas

- Version: `full-rule-library-closed-operations-v0.1`.
- Biblioteca: `TP-SL-RULE-LIBRARY-v0.1`.
- SHA del catalogo: `c31778be090469de4390a3a89bcadc2bcce2c0dd9e5b7ca6ef183be2d0460cfa`.
- Operaciones cerradas: **244**.
- Entradas market comparables: **213**.
- Entradas pending separadas: **31**.
- Resultados TP/SL/expiry reconstruidos: **243**.

## Respuesta ejecutiva

La infraestructura de trazabilidad permite auditar las 38 fichas sin convertir ausencias historicas en valores neutros. Sin embargo, el historico anterior al motor actual no contiene todos los datos crudos necesarios para reproducir todas sus reglas.

Las reglas basadas en velas cerradas pueden reconstruirse con la formula actual. Order book completo, basis sincronizado, historiales de OI/funding/crowding/sentimiento y contexto cross-venue no pueden validarse retroactivamente cuando no fueron almacenados.

Por ello esta auditoria puede aportar evidencia historica para un subconjunto, pero no autoriza por si sola a declarar validado el motor completo ni a modificar pesos en produccion.

Resultado agregado de las 38 fichas: 7 controles deterministas quedan cubiertos en las 213 operaciones market; 16 reglas con valores exactos no muestran separacion univariante estable; 11 reglas no tienen cobertura historica exacta suficiente; 2 reglas economicas solo disponen de 6 trazas actuales; y 2 reglas siguen bloqueadas por diseno.

## Probabilidades

| Variante | N | Log-loss | Brier | Acierto clase mayor |
|---|---:|---:|---:|---:|
| stored_legacy_and_current_engine_all_closed | 243 | 1.128575 | 0.661436 | 44.03% |
| stored_legacy_and_current_engine_market_only | 213 | 1.173745 | 0.685457 | 41.31% |
| current_diffusion_baseline_replay | 213 | 0.883815 | 0.526776 | 59.15% |
| current_fitted_before_overlay_replay | 213 | 0.797358 | 0.499931 | 61.50% |
| current_exact_available_rules_replay | 213 | 0.796568 | 0.499774 | 61.50% |

### Corte temporal

| Variante | N reciente | Log-loss reciente | Brier reciente | Acierto reciente |
|---|---:|---:|---:|---:|
| stored_legacy_and_current_engine_all_closed | 73 | 1.162824 | 0.732459 | 32.88% |
| stored_legacy_and_current_engine_market_only | 64 | 1.159875 | 0.739241 | 29.69% |
| current_diffusion_baseline_replay | 64 | 0.887213 | 0.522776 | 64.06% |
| current_fitted_before_overlay_replay | 64 | 0.834262 | 0.536107 | 56.25% |
| current_exact_available_rules_replay | 64 | 0.841544 | 0.541548 | 57.81% |

La variante `current_exact_available_rules_replay` es una reproduccion parcial: aplica las formulas actuales solo donde el dato pre-trade es recuperable. No equivale al motor completo con todos sus proveedores en vivo.

En las mismas 213 entradas market, el historico almacenado obtiene log-loss 1.173745, Brier 0.685457 y 41.31% de acierto de clase. La reproduccion actual parcial obtiene 0.796568, 0.499774 y 61.50%. Es una mejora retrospectiva prometedora, pero no una comparacion independiente: los motores antiguos son heterogeneos y parte del modelo actual fue ajustada con este mismo periodo.

El paso desde el modelo ajustado previo al overlay hasta las reglas exactas disponibles solo reduce log-loss en 0.000790 y Brier en 0.000156, con acierto 61.50% frente a 61.50%. Por tanto, el beneficio observado procede principalmente del nuevo nucleo y del ajuste fitted, no queda demostrado para los overlays provisionales.

En las 64 operaciones market mas recientes, el motor almacenado obtiene log-loss 1.159875, Brier 0.739241 y 29.69% de acierto; la reproduccion actual parcial obtiene 0.841544, 0.541548 y 57.81%. La mejora frente al historico persiste. Aun asi, el baseline de difusion obtiene Brier 0.522776 y 64.06% de acierto en ese mismo tramo: el ajuste reduce log-loss, pero no mejora uniformemente todas las metricas.

En el tramo reciente el overlay empeora log-loss y Brier frente al modelo fitted previo (0.841544 frente a 0.834262 y 0.541548 frente a 0.536107), aunque cambia el acierto de clase de 56.25% a 57.81%. Esto no valida los pesos provisionales.

## Ablacion de reglas activas

Un valor positivo significa que incluir la regla mejora la metrica frente al mismo motor sin esa regla; un valor negativo significa que la empeora.

| Regla | N | Delta log-loss | Delta Brier | Delta log-loss reciente | Delta Brier reciente |
|---|---:|---:|---:|---:|---:|
| `M4-RULE-PATH-STRUCTURE-001` | 213 | +0.000894 | +0.000421 | -0.006865 | -0.005217 |
| `M4-RULE-PRIOR-EXTREMA-001` | 213 | +0.006993 | +0.003262 | +0.011764 | +0.003526 |
| `M4-RULE-VOLATILITY-RANK-001` | 213 | +0.027147 | +0.011060 | +0.026960 | +0.006312 |
| `M4-RULE-MTF-HIERARCHY-001` | 213 | +0.015722 | +0.012116 | -0.017865 | -0.013714 |
| `M4-RULE-CONTINUOUS-REGIME-001` | 213 | -0.000197 | -0.000314 | +0.000335 | +0.000327 |
| `M4-RULE-AGGRESSOR-IMBALANCE-001` | 213 | -0.000083 | -0.000093 | -0.000777 | -0.000540 |
| `M4-RULE-OPEN-INTEREST-CHANGE-001` | 0 | n/d | n/d | n/d | n/d |
| `M4-RULE-PRICE-OI-STATE-001` | 0 | n/d | n/d | n/d | n/d |
| `M4-RULE-SPOT-FUTURES-BASIS-001` | 0 | n/d | n/d | n/d | n/d |
| `M4-RULE-MARK-INDEX-PREMIUM-001` | 0 | n/d | n/d | n/d | n/d |
| `M4-RULE-FUNDING-STATE-001` | 0 | n/d | n/d | n/d | n/d |

Estas ablaciones son diagnosticas sobre el mismo historico. No sustituyen una validacion temporal independiente ni autorizan cambios automaticos de peso.

## Regla por regla

| Regla | Estado | Exactas | Proxies | Conclusion |
|---|---|---:|---:|---|
| `M4-RULE-HORIZON-SAMPLING-001` | active_deterministic | 213 | 0 | deterministic_replay_covered |
| `M4-RULE-PLAN-GEOMETRY-001` | active_deterministic | 213 | 0 | deterministic_replay_covered |
| `M4-RULE-LOG-RETURNS-001` | active_deterministic | 213 | 0 | deterministic_replay_covered |
| `M4-RULE-REALIZED-VOLATILITY-001` | active_deterministic | 213 | 0 | deterministic_replay_covered |
| `M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002` | active_deterministic | 213 | 0 | deterministic_replay_covered |
| `M4-RULE-PATH-STRUCTURE-001` | active_provisional | 213 | 0 | no_stable_univariate_support_detected |
| `M4-RULE-PRIOR-EXTREMA-001` | active_provisional | 213 | 0 | no_stable_univariate_support_detected |
| `M4-RULE-VOLATILITY-RANK-001` | active_provisional | 213 | 0 | no_stable_univariate_support_detected |
| `M4-RULE-MTF-HIERARCHY-001` | active_provisional | 213 | 0 | no_stable_univariate_support_detected |
| `M4-RULE-CONTINUOUS-REGIME-001` | active_provisional | 213 | 0 | no_stable_univariate_support_detected |
| `M4-RULE-AGGRESSOR-IMBALANCE-001` | active_provisional | 213 | 0 | no_stable_univariate_support_detected |
| `M4-RULE-OPEN-INTEREST-CHANGE-001` | active_provisional | 6 | 105 | insufficient_exact_historical_coverage |
| `M4-RULE-PRICE-OI-STATE-001` | active_provisional | 6 | 0 | insufficient_exact_historical_coverage |
| `M4-RULE-SPOT-FUTURES-BASIS-001` | active_provisional | 6 | 0 | insufficient_exact_historical_coverage |
| `M4-RULE-MARK-INDEX-PREMIUM-001` | active_provisional | 6 | 112 | insufficient_exact_historical_coverage |
| `M4-RULE-FUNDING-STATE-001` | active_provisional | 6 | 112 | insufficient_exact_historical_coverage |
| `M4-RULE-QUOTED-SPREAD-001` | active_economic | 6 | 205 | economic_trace_coverage_insufficient_for_historical_audit |
| `M4-RULE-DEPTH-SWEEP-001` | active_economic | 6 | 0 | economic_trace_coverage_insufficient_for_historical_audit |
| `LIB-CAND-EMA-TREND-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-RSI-WILDER-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-ATR-EXTENSION-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-RELATIVE-VOLUME-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-ORDERBOOK-IMBALANCE-001` | implemented_shadow | 2 | 205 | insufficient_exact_historical_coverage |
| `LIB-CAND-CVD-SLOPE-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-BREADTH-001` | implemented_shadow | 0 | 202 | insufficient_exact_historical_coverage |
| `LIB-CAND-FIBONACCI-DISTANCE-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-FUNDING-PERCENTILE-001` | implemented_shadow | 0 | 0 | insufficient_exact_historical_coverage |
| `LIB-CAND-CROWDING-PERCENTILE-001` | implemented_shadow | 0 | 112 | insufficient_exact_historical_coverage |
| `LIB-CAND-SENTIMENT-PERCENTILE-001` | implemented_shadow | 0 | 202 | insufficient_exact_historical_coverage |
| `LIB-CAND-COMPRESSION-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-SHOCK-001` | data_blocked | 0 | 0 | blocked_by_design_no_historical_validation |
| `LIB-CAND-ABSORPTION-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-PULLBACK-CONTEXT-001` | implemented_shadow | 213 | 0 | no_stable_univariate_support_detected |
| `LIB-CAND-LIQUIDATION-ZONE-001` | implemented_shadow | 23 | 0 | insufficient_exact_historical_coverage |
| `LIB-CAND-DATA-FRESHNESS-001` | active_blocking | 213 | 0 | deterministic_replay_covered |
| `LIB-CAND-CANDLE-INTEGRITY-001` | active_blocking | 213 | 0 | deterministic_replay_covered |
| `LIB-CAND-CROSS-VENUE-DIVERGENCE-001` | data_blocked | 0 | 0 | blocked_by_design_no_historical_validation |

## Criterio

Las asociaciones exigen al menos 50 casos comparables, 10 positivos y 10 negativos, bootstrap, permutacion, correccion Benjamini-Hochberg y consistencia entre el 70% inicial y el 30% final. Incluso cuando se cumplen, la conclusion es apoyo historico, no validacion independiente.

Los controles deterministas y economicos no se juzgan por acertar TP o SL. Se auditan por cobertura, identidad de formula, datos disponibles y bloqueo correcto.

## Siguiente decision permitida

Conservar sin cambios las reglas y pesos hasta revisar los resultados concretos de esta auditoria. Las reglas sin datos historicos suficientes deben acumular trazas prospectivas completas; no se rellenan ni se validan por aproximacion.
