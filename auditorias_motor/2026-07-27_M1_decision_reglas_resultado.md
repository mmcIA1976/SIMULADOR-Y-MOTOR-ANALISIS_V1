# M1 - Decision sobre los elementos auditados del motor actual

Fecha: 2026-07-27
Estado: COMPLETADA Y APROBADA EL 2026-07-27
Version: `M1-rule-decisions-v0.1`

## 1. Objetivo

Decidir uno por uno los elementos de la matriz E1.5, distinguiendo el
motor productivo actual de la infraestructura contractual aislada.
M1 no modifica formulas, pesos, probabilidades ni produccion.

## 2. Correccion del universo

La cifra anterior de 86 elementos no equivalia a 86 elementos
productivos actuales:

- Motor productivo actual: 82.
- Infraestructura contractual aislada: 4.
- Total auditado y decidido: 86.

Los cuatro elementos contractuales son las distancias logaritmicas TP y
SL, la duracion logaritmica y la codificacion simetrica del lado. No
intervienen en la aplicacion productiva.

## 3. Reconciliacion

| Control | Resultado |
|---|---:|
| Elementos fuente | 86 |
| IDs unicos | 86 |
| Elementos decididos | 86 |
| Bloques analiticos | 34 |
| Bloques con elementos actuales | 21 |
| Bloques sin elemento actual, registrados expresamente | 13 |
| Efectos predictivos autorizados | 0 |
| Produccion modificada | no |
| Motor de aprendizaje utilizado | no |

## 4. Dictamen operativo

M1 no conserva ningun peso, umbral, gate o porcentaje por defecto.
Los datos y calculos estandar pueden conservarse solo en su papel
descriptivo o determinista. Las afirmaciones predictivas quedan sin
autorizacion hasta las fases posteriores de la hoja de ruta.

Deben salir de la ruta probabilistica actual:

- ajustes predictivos actuales: 29;
- gates empiricos actuales: 19;
- transformaciones de probabilidad que deben reemplazarse: 5.

Esta es una decision de diseno para la revision interna futura. M1 no
apaga todavia esos elementos en produccion.

## 5. Decisiones por elemento

| # | ID | Origen | Bloques | Decision M1 | Accion | Reemplazo |
|---:|---|---|---|---|---|---|
| 1 | `DATA-PRICE-KLINES` | productivo | 1,2,3,5,6,24,26,28 | `conservar_como_dato_sin_efecto_predictivo_directo` | M3 | M3 |
| 2 | `DATA-DEPTH-TRADES` | productivo | 7,8,29 | `conservar_como_dato_sin_efecto_predictivo_directo` | M3 | M3 |
| 3 | `DATA-DERIVATIVES` | productivo | 9,10,13 | `conservar_como_dato_sin_efecto_predictivo_directo` | M3 | M3 |
| 4 | `DATA-BREADTH` | productivo | 21 | `conservar_como_dato_sin_efecto_predictivo_directo` | M10 | M10 |
| 5 | `DATA-GLOBAL` | productivo | 21,24 | `conservar_como_dato_sin_efecto_predictivo_directo` | M3 | M3 |
| 6 | `DATA-SENTIMENT` | productivo | 22 | `conservar_como_dato_sin_efecto_predictivo_directo` | M10 | M10 |
| 7 | `DATA-LIQUIDATIONS` | productivo | 12 | `conservar_como_dato_sin_efecto_predictivo_directo` | M10 | M10 |
| 8 | `PLAN-TP-LOG-DISTANCE` | contractual | 26,28 | `conservar_calculo_contractual_aislado` | M2 | M2 |
| 9 | `PLAN-SL-LOG-DISTANCE` | contractual | 26,28,30 | `conservar_calculo_contractual_aislado` | M2 | M2 |
| 10 | `PLAN-LOG-HORIZON-SECONDS` | contractual | 26,28 | `conservar_calculo_contractual_aislado` | M2 | M2 |
| 11 | `PLAN-SIDE-SIGN` | contractual | 26,28 | `conservar_calculo_contractual_aislado` | M2 | M2 |
| 12 | `IND-EMA-CORE` | productivo | 1,2,3 | `conservar_calculo_sin_peso_predictivo` | M4 | M4 |
| 13 | `IND-EMA200-FALLBACK` | productivo | 1,2,3,34 | `desactivar_fallback_mal_etiquetado` | M4 | M4 |
| 14 | `IND-RSI14-CURRENT` | productivo | 2 | `reformular_a_definicion_estandar_o_renombrar` | M10 | M10 |
| 15 | `IND-ATR14-CURRENT` | productivo | 2,26,28 | `reformular_a_definicion_estandar_o_renombrar` | M4 | M4 |
| 16 | `IND-EMA-STACK` | productivo | 1,2,3 | `mantener_solo_como_hipotesis_estructural` | M4 | M4 |
| 17 | `IND-SUPPORT-RESISTANCE` | productivo | 1 | `reformular_detector_antes_de_uso` | M4 | M4 |
| 18 | `IND-FIBONACCI` | productivo | 4 | `retirar_efecto_predictivo_conservar_solo_investigacion` | M10 | M10 |
| 19 | `IND-ORDERBOOK-PROXY` | productivo | 8 | `reformular_proxy_sin_peso_actual` | M10 | M10 |
| 20 | `IND-CVD-PROXY` | productivo | 7 | `reformular_proxy_sin_peso_actual` | M4 | M4 |
| 21 | `IND-PENDING-ZONE` | productivo | 1,28,29 | `conservar_solo_observacional_y_reformular_interaccion` | M4 | M4 |
| 22 | `SCORE-TREND_BIAS` | productivo | 1,3 | `retirar_puntos_y_reformular` | M5 | M4 |
| 23 | `SCORE-TECHNICAL_DIRECTION_BIAS` | productivo | 1,2,3 | `retirar_puntos_y_reformular` | M5 | M4 |
| 24 | `SCORE-PRICE_VS_ENTRY_BIAS` | productivo | 26,28 | `retirar_formula_actual` | M5 | M4 |
| 25 | `SCORE-VOLUME_BIAS` | productivo | 6 | `retirar_umbral_y_reformular` | M5 | M10 |
| 26 | `SCORE-ORDER_BOOK_BIAS` | productivo | 8 | `retirar_umbral_y_reformular` | M5 | M10 |
| 27 | `SCORE-MOMENTUM_BIAS` | productivo | 2 | `retirar_umbrales_actuales` | M5 | M10 |
| 28 | `SCORE-MARKET_REGIME_BIAS` | productivo | 24 | `retirar_puntos_y_reformular` | M5 | M4 |
| 29 | `SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT` | productivo | 4,28 | `retirar_efecto_predictivo` | M5 | M4 |
| 30 | `SCORE-ZONE_PROBABILITY_ADJUSTMENT` | productivo | 1,28 | `retirar_puntos_y_reformular` | M5 | M4 |
| 31 | `SCORE-TAKER_FLOW_BIAS` | productivo | 7 | `retirar_umbral_y_reformular` | M5 | M4 |
| 32 | `SCORE-CVD_BIAS` | productivo | 7 | `retirar_puntos_y_reformular` | M5 | M4 |
| 33 | `SCORE-OI_TREND_BIAS` | productivo | 9 | `retirar_puntos_y_reformular` | M5 | M4 |
| 34 | `SCORE-BREADTH_BIAS` | productivo | 21 | `retirar_efecto_y_posponer` | M5 | M10 |
| 35 | `SCORE-VOLATILITY_PENALTY` | productivo | 26,28 | `retirar_penalizacion_y_reformular` | M5 | M4 |
| 36 | `SCORE-LIQUIDITY_PENALTY` | productivo | 8,29 | `separar_de_probabilidad_de_mercado` | M5 | M4 |
| 37 | `SCORE-OVEREXTENSION_PENALTY` | productivo | 1,2,24 | `retirar_puntos_y_reformular` | M5 | M4 |
| 38 | `SCORE-FUNDING_PENALTY` | productivo | 10 | `retirar_puntos_y_reformular` | M5 | M4 |
| 39 | `SCORE-FUNDING_RELATIVE_PENALTY` | productivo | 10 | `retirar_puntos_y_reformular` | M5 | M4 |
| 40 | `SCORE-CROWDING_PENALTY` | productivo | 13 | `retirar_puntos_y_reformular` | M5 | M10 |
| 41 | `SCORE-LEVEL_PENALTY` | productivo | 1,28 | `retirar_penalizacion_y_reformular` | M5 | M4 |
| 42 | `SCORE-SENTIMENT_PENALTY` | productivo | 22 | `retirar_efecto_y_posponer` | M5 | M10 |
| 43 | `SCORE-HIGHER_TIMEFRAME_PENALTY` | productivo | 1,3 | `retirar_duplicidad_y_reformular` | M5 | M4 |
| 44 | `SCORE-TECHNICAL_ENTRY_TIMING_PENALTY` | productivo | 1,2,24 | `retirar_puntos_y_reformular` | M5 | M4 |
| 45 | `SCORE-TECHNICAL_BARRIER_PENALTY` | productivo | 1,28 | `retirar_penalizacion_y_reformular` | M5 | M4 |
| 46 | `SCORE-OI_CONTEXT_PENALTY` | productivo | 9,24 | `retirar_puntos_y_reformular` | M5 | M4 |
| 47 | `SCORE-CONTRADICTION_PENALTY` | productivo | 24,28 | `retirar_conteo_y_reformular` | M5 | M4 |
| 48 | `SCORE-RISK_CALIBRATION_TP_ADJUSTMENT` | productivo | 28,30,32 | `retirar_ajuste_agregado` | M5 | M4 |
| 49 | `SCORE-ZONE_RANGE_PROBABILITY_ADJUSTMENT` | productivo | 28 | `separar_semanticas` | M5 | M4 |
| 50 | `SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT` | productivo | 28,30,32 | `retirar_formula_actual` | M5 | M4 |
| 51 | `GATE-SL_PROBABILITY_GTE_55` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 52 | `GATE-SL_PROBABILITY_GTE_50` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 53 | `GATE-DIRECTION_SCORE_LT_40` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 54 | `GATE-TECHNICAL_SCORE_LT_40` | productivo | 2,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 55 | `GATE-RR_RATIO_GTE_3` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 56 | `GATE-REWARD_DISTANCE_GTE_3` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 57 | `GATE-RISK_DISTANCE_LT_0_25` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 58 | `GATE-RISK_DISTANCE_GTE_3` | productivo | 28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 59 | `GATE-TICKER_24H_CONTRA_SIDE` | productivo | 1,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 60 | `GATE-EMA_STACK_15M_CONTRA_SIDE` | productivo | 1,3,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 61 | `GATE-PRICE_VS_EMA_1H_CONTRA_SIDE` | productivo | 1,3,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 62 | `GATE-PENDING_ZONE_NEGATIVE_ADJUSTMENT` | productivo | 1,28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 63 | `GATE-PENDING_STOP_BREAKDOWN` | productivo | 1,28,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 64 | `GATE-PENDING_LIQUIDITY_SWEEP_HIGH` | productivo | 1,7,8,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 65 | `GATE-PENDING_FALSE_BREAKOUT_RISK` | productivo | 1,7,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 66 | `GATE-EXTREME_FIB_EXTREME_SENTIMENT_CLUSTER` | productivo | 4,22,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 67 | `GATE-EXTREME_FIB_SENTIMENT_CVD_CONTRA` | productivo | 4,7,22,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 68 | `GATE-RSI_EXTREME_MULTI_RISK_CLUSTER` | productivo | 2,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 69 | `GATE-RSI_EXTREME_WITH_FIB_SENTIMENT_CLUSTER` | productivo | 2,4,22,30,32 | `retirar_gate_del_calculo_conservar_evidencia_historica` | M5 | no_aplica_gate_exacto_retirado |
| 70 | `OUT-TP-ADDITIVE` | productivo | 28 | `retirar_y_reconstruir_salida` | M6 | M6 |
| 71 | `OUT-TP-CAPS` | productivo | 28 | `retirar_caps_heuristicos` | M6 | M6 |
| 72 | `OUT-RANGE` | productivo | 28 | `reformular_como_expiracion` | M6 | M6 |
| 73 | `OUT-SL-RESIDUAL` | productivo | 28 | `retirar_y_reconstruir_salida` | M6 | M6 |
| 74 | `OUT-PROBABILITY-BANDS` | productivo | 28,32 | `retirar_bandas_heuristicas` | M6 | M6 |
| 75 | `OUT-EV-COST` | productivo | 29,30,32 | `conservar_identidad_reconstruir_entradas` | M7 | M7 |
| 76 | `OUT-FEE` | productivo | 29 | `reformular_coste` | M5 | M5 |
| 77 | `OUT-SLIPPAGE` | productivo | 8,29 | `reformular_coste` | M5 | M5 |
| 78 | `OUT-FUNDING-COST` | productivo | 10,29 | `reformular_coste` | M5 | M5 |
| 79 | `OUT-RISK-SCORE` | productivo | 30,32 | `reformular_capa_de_riesgo` | M5 | M5 |
| 80 | `OUT-GRADE` | productivo | 30,32 | `reformular_politica` | M5 | M5 |
| 81 | `OUT-CONFIDENCE` | productivo | 28,32 | `reformular_incertidumbre` | M5 | M5 |
| 82 | `OUT-DECISION` | productivo | 30,32 | `reformular_politica` | M5 | M5 |
| 83 | `OUT-LAYERED-SCORES` | productivo | 28,32 | `convertir_en_traza` | M5 | M5 |
| 84 | `OUT-HORIZON-FALLBACK` | productivo | 28,34 | `retirar_fallback` | M5 | M5 |
| 85 | `OUT-MISSING-DATA` | productivo | 28,34 | `retirar_defaults_neutrales` | M5 | M5 |
| 86 | `OUT-RISK-CAL-METRIC` | productivo | 32 | `presentacion_unicamente_redefinir` | M7 | M7 |

## 6. Cobertura de los 34 bloques

| Bloque | Prioridad | Elementos actuales | Estado M1 |
|---:|---|---:|---|
| 1 - Estructura del precio | P0 | 21 | `existing_elements_decided` |
| 2 - Indicadores tecnicos | P1 | 13 | `existing_elements_decided` |
| 3 - Multi-timeframe | P0 | 9 | `existing_elements_decided` |
| 4 - Patrones y metodologias discrecionales | P3 | 5 | `existing_elements_decided` |
| 5 - Velas japonesas | P1 | 1 | `existing_elements_decided` |
| 6 - Volumen y subasta | P1 | 2 | `existing_elements_decided` |
| 7 - Order flow | P0 | 7 | `existing_elements_decided` |
| 8 - Libro y microestructura | P1 | 6 | `existing_elements_decided` |
| 9 - Open interest | P0 | 3 | `existing_elements_decided` |
| 10 - Funding | P0 | 4 | `existing_elements_decided` |
| 11 - Prima, basis y curva | P1 | 0 | `no_current_element_explicitly_recorded` |
| 12 - Liquidaciones | P1 | 1 | `existing_elements_decided` |
| 13 - Posicionamiento long/short | P1 | 2 | `existing_elements_decided` |
| 14 - Opciones | P2 | 0 | `no_current_element_explicitly_recorded` |
| 15 - Spot contra futuros | P0 | 0 | `no_current_element_explicitly_recorded` |
| 16 - Cross-exchange y arbitraje | P3 | 0 | `no_current_element_explicitly_recorded` |
| 17 - On-chain | P2 | 0 | `no_current_element_explicitly_recorded` |
| 18 - Tokenomics y fundamental | P2 | 0 | `no_current_element_explicitly_recorded` |
| 19 - Macroeconomia | P1 | 0 | `no_current_element_explicitly_recorded` |
| 20 - Intermercado | P1 | 0 | `no_current_element_explicitly_recorded` |
| 21 - Amplitud y rotacion | P1 | 3 | `existing_elements_decided` |
| 22 - Sentimiento | P2 | 5 | `existing_elements_decided` |
| 23 - Noticias y eventos | P2 | 0 | `no_current_element_explicitly_recorded` |
| 24 - Regimen de mercado | P0 | 7 | `existing_elements_decided` |
| 25 - Estacionalidad y tiempo | P1 | 0 | `no_current_element_explicitly_recorded` |
| 26 - Estadistica y cuantitativo | P0 | 8 | `existing_elements_decided` |
| 27 - Machine learning e IA | P3 | 0 | `no_current_element_explicitly_recorded` |
| 28 - Probabilidad TP/SL | P0 | 35 | `existing_elements_decided` |
| 29 - Ejecucion y costes | P0 | 7 | `existing_elements_decided` |
| 30 - Gestion de riesgo | P0 | 26 | `existing_elements_decided` |
| 31 - Cartera | P3 | 0 | `no_current_element_explicitly_recorded` |
| 32 - Evaluacion del rendimiento | P0 | 29 | `existing_elements_decided` |
| 33 - Psicologia y conducta | P3 | 0 | `no_current_element_explicitly_recorded` |
| 34 - Riesgo operativo y contraparte | P1 | 3 | `existing_elements_decided` |

## 7. Limites de M1

- No se han investigado aun las formulas sustitutas.
- No se han aprobado fuentes nuevas.
- No se han programado reglas nuevas.
- No se ha modificado el scoring visible.
- No se ha iniciado M2.
- Las decisiones de reformulacion indican trabajo futuro, no
  validacion conseguida.

## 8. Evidencia reproducible

- Fuente: `auditorias_motor/matriz_admisibilidad_reglas_v0_1.json`.
- SHA-256 del archivo fuente: `3bdc31e7c87f2293d2a45819e97fa275d743e793c3f502cb98140c88fc457260`.
- SHA-256 canonico de decisiones: `1a3a5248e1aaad816eab297e27e14e75b2386a62afdcd4dc7fc1e2f57e23c2ce`.
- Generador: `build_m1_rule_decisions.py`.
- Matriz: `auditorias_motor/matriz_decisiones_m1_v0_1.json`.

## 9. Criterio de cierre

M1 solo puede cerrarse cuando:

- la reconciliacion 82 + 4 = 86 sea verificada;
- las 86 decisiones y los 34 bloques esten completos;
- las pruebas del generador sean correctas;
- se confirme que no hubo cambio funcional;
- el propietario apruebe expresamente el resultado.

M2 permanece bloqueada hasta esa aprobacion.

## 10. Aprobacion y anexo posterior

El propietario aprobo expresamente el cierre de M1 el 2026-07-27.

El propietario aprobo el anexo documental M1-A el 2026-07-27.
Contiene el catalogo exacto y legible
86/86 en `auditorias_motor/2026-07-27_M1_A_catalogo_exacto_reglas_formulas.md`
y su artefacto canonico en
`auditorias_motor/catalogo_exacto_reglas_formulas_m1_v0_1.json`.
El anexo no modifica las decisiones de M1 ni altera produccion.
Con esta aprobacion, M1 y M1-A quedan completamente cerradas. M2
es la siguiente fase pendiente y todavia no se ha iniciado.
