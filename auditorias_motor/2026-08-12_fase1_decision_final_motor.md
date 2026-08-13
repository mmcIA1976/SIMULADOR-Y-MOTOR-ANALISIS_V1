# Fase 1 - Decisión final del motor de análisis

- Decisión: **`no_new_engine_promotion_keep_v0_6_frozen_only_intraday_wide_supported`**.
- Promoción nueva: **no**.
- Cambio en producción: **ninguno**.
- Escrituras en Supabase: **ninguna**.
- Borrado de motores u operaciones históricas: **ninguno**.

## Qué se ha demostrado

| Marco | Motor v0.6 actual | Calibración del baseline |
|---|---|---|
| `intraday_short` | `current_engine_predictive_value_not_demonstrated` | `calibration_supported_out_of_sample` |
| `intraday_wide` | `current_engine_supported_out_of_sample` | `calibration_not_demonstrated` |
| `short_swing` | `current_engine_predictive_value_not_demonstrated` | `calibration_not_demonstrated` |

El v0.6 aporta valor histórico estable sólo en `intraday_wide`. En `intraday_short` queda por debajo del baseline calibrado. En `short_swing` la evidencia es inconclusa por falta de semanas independientes, no por falta de filas geométricas.

## Comparación final del motor v0.6

| Marco | Comparador | Bloques independientes | Δ log-loss IC95% | Δ Brier IC95% |
|---|---|---:|---|---|
| `intraday_short` | `raw_first_passage` | 424 | [-0.011035, 0.025236] | [-0.013297, 0.005935] |
| `intraday_short` | `calibrated_baseline` | 424 | [-0.058405, -0.012865] | [-0.042351, -0.013539] |
| `intraday_wide` | `raw_first_passage` | 211 | [0.016007, 0.059181] | [0.002881, 0.028865] |
| `intraday_wide` | `calibrated_baseline` | 211 | [0.014929, 0.059030] | [0.002244, 0.028295] |
| `short_swing` | `raw_first_passage` | 29 | [-0.042959, 0.071850] | [-0.031717, 0.040090] |
| `short_swing` | `calibrated_baseline` | 29 | [-0.044216, 0.082118] | [-0.031167, 0.046930] |

## Reglas nuevas

Ninguna de las 42 combinaciones regla-marco superó a la vez desarrollo, calibración, selección temporal, intervalos por bloque y control de comparaciones múltiples. Por tanto, ninguna recibe peso probabilístico nuevo.

### Observación prioritaria, sin peso probabilístico

| Marco | Regla | Motivo | Δ log-loss selección | Δ Brier selección |
|---|---|---|---:|---:|
| `intraday_short` | `M4-RULE-VOLATILITY-RANK-001` | `positive_but_uncertainty_interval_not_conclusive` | 0.001953 | 0.000488 |
| `intraday_wide` | `M4-RULE-VOLATILITY-RANK-001` | `positive_but_failed_multiple_test_control` | 0.051323 | 0.027578 |
| `intraday_wide` | `LIB-CAND-RELATIVE-VOLUME-001` | `positive_but_failed_multiple_test_control` | 0.023421 | 0.013085 |
| `intraday_wide` | `LIB-CAND-COMPRESSION-001` | `positive_but_failed_multiple_test_control` | 0.030345 | 0.015888 |
| `short_swing` | `M4-RULE-VOLATILITY-RANK-001` | `positive_but_insufficient_independent_time_clusters` | 0.063812 | 0.038393 |
| `short_swing` | `LIB-CAND-RELATIVE-VOLUME-001` | `positive_but_insufficient_independent_time_clusters` | 0.002554 | 0.001260 |
| `short_swing` | `LIB-CAND-CVD-SLOPE-001` | `positive_but_insufficient_independent_time_clusters` | 0.004065 | 0.002455 |
| `short_swing` | `LIB-CAND-COMPRESSION-001` | `positive_but_insufficient_independent_time_clusters` | 0.000166 | 0.001196 |
| `short_swing` | `LIB-CAND-ABSORPTION-001` | `positive_but_insufficient_independent_time_clusters` | 0.007935 | 0.004415 |

## Alcance de la evidencia

- Casos resueltos: **47804 en la prueba final**, dentro de una cohorte total de 285.590 casos.
- Pares: BTC, ETH, SOL, BNB, XRP e INJ.
- Fuente: velas Binance USD-M de 5 minutos, 2023-01 a 2026-07.
- Resolución: primer TP o SL; doble toque en la misma vela excluido.
- Independencia: todas las geometrías y pares de una misma fecha-marco se agrupan en un único bloque inferencial.

## Consecuencia

La fase termina sin fabricar un candidato. Se conserva v0.6 para trazabilidad y porque sí contiene señal útil en intradía largo, pero no queda autorizado como solución fiable común a los tres marcos. No procede iniciar seguimiento prospectivo de un challenger que no ha superado la puerta histórica.
