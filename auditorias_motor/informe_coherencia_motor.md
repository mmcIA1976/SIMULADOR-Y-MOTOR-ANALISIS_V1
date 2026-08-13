# Informe de coherencia matematica y semantica - E1.3

Version de auditoria: `E1.3-v0.1`

Estado: COMPLETADA

## Dictamen

El champion actual no satisface el contrato probabilistico de la Fase 1. La auditoria no modifica produccion: convierte sus incoherencias en casos reproducibles que serviran de requisitos negativos para el challenger.

## Resumen

- Invariantes definidos: 12
- Hallazgos: 17
- Fallos demostrados: 16
- Validez pendiente de demostrar: 1
- Severidad critica: 7
- Severidad alta: 9
- Severidad media: 1
- Produccion modificada: false
- SHA-256 del codigo auditado: `7a5ca78117d717f6042da0465fa77f7a88c011d3de8b51ca5bed83bac105f7ac`

## Hallazgos

### E1.3-F01 - tp_probability es un score aditivo acotado, no una probabilidad calibrada

- Invariante: `INV-PROB-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: El valor parte de 0.5, suma y resta biases discretos y despues aplica caps. No existe estimacion de frecuencia condicional ni calibracion fuera de muestra.
- Reproduccion: `source_formula`
- Resultado observado: `{"base": 0.5, "first_cap": [0.26, 0.74], "second_cap": [0.22, 0.74]}`
- Impacto: El porcentaje mostrado no puede interpretarse como frecuencia esperada de alcanzar TP para el plan.
- Correccion candidata: Mantener el champion solo como referencia y construir en E1.5 un modelo de alcanzabilidad entrenable y calibrado temporalmente.
- Referencias de codigo: `analysis_engine.py:231`, `analysis_engine.py:264`, `analysis_engine.py:291`

### E1.3-F02 - La probabilidad TP puede ser insensible a alejar el objetivo cinco veces

- Invariante: `INV-MONO-TP-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: En un snapshot neutral, mover el TP short de 0.5% a 2.5% conserva exactamente la misma probabilidad TP.
- Reproduccion: `end_to_end_synthetic_snapshot`
- Resultado observado: `{"delta_probability": 0.0, "far_reward_distance_pct": 2.5, "far_tp_probability": 0.53, "near_reward_distance_pct": 0.5, "near_tp_probability": 0.53}`
- Impacto: Dos planes con dificultad de recorrido materialmente distinta pueden recibir el mismo porcentaje TP.
- Correccion candidata: Modelar distancia TP normalizada por volatilidad y horizonte dentro de la funcion de alcanzabilidad, con prueba monotonica.
- Referencias de codigo: `analysis_engine.py:154`, `analysis_engine.py:231`

### E1.3-F03 - La probabilidad SL puede ser insensible a alejar el stop

- Invariante: `INV-MONO-SL-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: En un snapshot neutral, mover el SL short de 1.0% a 2.5% conserva la misma probabilidad SL.
- Reproduccion: `end_to_end_synthetic_snapshot`
- Resultado observado: `{"delta_probability": 0.0, "far_risk_distance_pct": 2.5, "far_sl_probability": 0.35, "near_risk_distance_pct": 1.0, "near_sl_probability": 0.35}`
- Impacto: El porcentaje SL no representa de forma estable la barrera concreta elegida por el usuario.
- Correccion candidata: Estimar la barrera SL con distancia normalizada, horizonte y distribucion condicional, en vez de usarla como residuo de TP y rango.
- Referencias de codigo: `analysis_engine.py:153`, `analysis_engine.py:293`

### E1.3-F04 - Cruzar la entrada por una millonesima produce un salto de cinco puntos

- Invariante: `INV-CONT-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: Para el mismo short, pasar el precio actual de 99.999999 a 100.0 cambia price_vs_entry_bias de -0.02 a +0.03.
- Reproduccion: `end_to_end_synthetic_snapshot`
- Resultado observado: `{"bias_a": -0.02, "bias_b": 0.03, "probability_delta": 0.05, "tp_probability_a": 0.48, "tp_probability_b": 0.53}`
- Impacto: Analisis practicamente simultaneos pueden diferir cinco puntos sin cambio economico material.
- Correccion candidata: Eliminar el escalon binario y modelar la distancia precio-entrada de forma continua, normalizada y separada entre activacion y alcanzabilidad.
- Referencias de codigo: `analysis_engine.py:191`, `analysis_engine.py:242`

### E1.3-F05 - El suelo de SL permite una masa total de 1.01

- Invariante: `INV-PROB-02`
- Severidad: `high`
- Estado: `failed`
- Observacion: Con TP=0.74 y rango=0.22, el residuo SL es 0.04 pero se fuerza a 0.05; la suma pasa a 1.01.
- Reproduccion: `direct_formula`
- Resultado observado: `{"floored_sl_probability": 0.05, "range_probability": 0.22, "raw_sl_residual": 0.04, "sum_after_floor": 1.01, "tp_probability": 0.74}`
- Impacto: La salida conjunta puede violar una identidad probabilistica basica.
- Correccion candidata: Definir eventos mutuamente excluyentes y normalizar conjuntamente la masa despues de cualquier restriccion.
- Referencias de codigo: `analysis_engine.py:291`, `analysis_engine.py:292`, `analysis_engine.py:293`

### E1.3-F06 - Los caps destruyen sensibilidad y hacen converger evidencias distintas

- Invariante: `INV-PROB-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: Scores pre-cap 0.80 y 0.95 producen ambos 0.74; 0.20 y 0.05 producen ambos 0.26 en el primer recorte.
- Reproduccion: `direct_formula`
- Resultado observado: `{"pre_cap_0_05": 0.26, "pre_cap_0_20": 0.26, "pre_cap_0_80": 0.74, "pre_cap_0_95": 0.74}`
- Impacto: El cap oculta diferencias de evidencia, impide ordenar casos saturados y dificulta aprender la contribucion real.
- Correccion candidata: Usar una funcion probabilistica estimada y calibrada; reservar limites solo para estabilidad numerica, no para fabricar un rango de confianza.
- Referencias de codigo: `analysis_engine.py:264`, `analysis_engine.py:291`

### E1.3-F07 - El funding pierde su signo y siempre se cobra como coste

- Invariante: `INV-COST-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: Funding +0.01% y -0.01% generan exactamente el mismo coste porque se usa abs().
- Reproduccion: `pure_function`
- Resultado observado: `{"negative_estimated_cost_usdt": 0.22, "negative_ev_usdt": -0.02, "positive_estimated_cost_usdt": 0.22, "positive_ev_usdt": -0.02}`
- Impacto: El EV puede cobrar un pago que seria ingreso o aplicar el signo incorrecto para long/short.
- Correccion candidata: Calcular el flujo de funding con signo por lado y registrar por separado pago e ingreso.
- Referencias de codigo: `analysis_engine.py:1891`

### E1.3-F08 - El EV aplica una sola observacion de funding sin duracion ni numero de pagos

- Invariante: `INV-HORIZON-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: calculate_expected_value no recibe horizonte, tiempo esperado en posicion ni frecuencia de liquidacion del funding.
- Reproduccion: `function_signature_and_formula`
- Resultado observado: `{"formula": "notional * abs(funding_rate_pct) / 100", "funding_period_count_parameter": false, "time_horizon_parameter": false}`
- Impacto: Los costes no son comparables entre los tres horizontes vigentes.
- Correccion candidata: Usar calendario/frecuencia del contrato, horizonte y tiempo esperado en posicion; separar escenarios de salida anticipada.
- Referencias de codigo: `analysis_engine.py:1876`, `analysis_engine.py:1891`

### E1.3-F09 - Los rangos mostrados no son intervalos estadisticos

- Invariante: `INV-PROB-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: Se resta y suma un ancho fijo de 4, 6 u 8 puntos segun contradiccion, sin muestra, varianza, cobertura ni calibracion.
- Reproduccion: `pure_function`
- Resultado observado: `{"high": {"range": {"high": 0.125, "label": "8%-12%", "low": 0.075}, "sl": {"high": 0.44, "label": "36%-44%", "low": 0.36}, "tp": {"high": 0.54, "label": "46%-54%", "low": 0.46}}, "none": {"range": {"high": 0.12, "label": "8%-12%", "low": 0.08}, "sl": {"high": 0.42, "label": "38%-42%", "low": 0.38}, "tp": {"high": 0.52, "label": "48%-52%", "low": 0.48}}, "some": {"range": {"high": 0.125, "label": "8%-12%", "low": 0.075}, "sl": {"high": 0.43, "label": "37%-43%", "low": 0.37}, "tp": {"high": 0.53, "label": "47%-53%", "low": 0.47}}}`
- Impacto: La interfaz puede sugerir una precision cuantificada que el metodo no ha estimado.
- Correccion candidata: No llamarlos intervalos probabilisticos hasta estimar cobertura; en el challenger usar incertidumbre por bootstrap temporal o calibracion apropiada.
- Referencias de codigo: `analysis_engine.py:1857`, `analysis_engine.py:1866`

### E1.3-F10 - Un snapshot marcado como no disponible sigue produciendo porcentajes y decision

- Invariante: `INV-DATA-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: El motor convierte campos ausentes en valores neutrales y devuelve una salida completa sin bloqueo por evidencia insuficiente.
- Reproduccion: `end_to_end_synthetic_snapshot`
- Resultado observado: `{"range_probability": 0.12, "setup_grade": "D", "sl_probability": 0.35, "tp_probability": 0.53, "training_decision": "observar"}`
- Impacto: Ausencia de evidencia puede parecer una lectura neutral valida y afectar la decision.
- Correccion candidata: Introducir reglas de bloqueo por campo/horizonte, freshness y cobertura; distinguir desconocido de neutral.
- Referencias de codigo: `data_engine.py:111`, `data_engine.py:476`, `analysis_engine.py:126`

### E1.3-F11 - La estructura EMA entra por al menos cinco rutas correlacionadas

- Invariante: `INV-DOUBLE-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: Los mismos ema_stack alimentan trend_score, technical_rating, market_regime, higher_timeframe_contra_penalty y reglas de calibracion.
- Reproduccion: `dependency_trace`
- Resultado observado: `{"incremental_validation_present": false, "paths": ["trend_bias", "technical_direction_bias", "market_regime_bias", "higher_timeframe_penalty", "risk_calibration_adjustment"]}`
- Impacto: Una sola familia de evidencia puede dominar el resultado sin medir su aporte incremental.
- Correccion candidata: Crear una representacion estructural unica y exigir ablation para cualquier interaccion adicional.
- Referencias de codigo: `analysis_engine.py:166`, `analysis_engine.py:167`, `analysis_engine.py:215`, `analysis_engine.py:218`, `analysis_engine.py:274`

### E1.3-F12 - La capa de zona reutiliza tecnica, regimen y Fibonacci y vuelve a puntuar

- Invariante: `INV-DOUBLE-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: build_zone_analysis recibe salidas ya puntuadas y genera otro ajuste de probabilidad/riesgo que se suma al resultado original.
- Reproduccion: `dependency_trace`
- Resultado observado: `{"added_again_to_tp": true, "child": "zone_probability_context", "incremental_validation_present": false}`
- Impacto: La confluencia puede ser duplicacion de evidencia, no informacion nueva.
- Correccion candidata: Definir la zona como regla combinada con padres declarados y activar su efecto solo si demuestra valor incremental por ablation.
- Referencias de codigo: `analysis_engine.py:219`, `analysis_engine.py:230`, `analysis_engine.py:250`

### E1.3-F13 - Rango mezcla mercado lateral, no activacion y no resolucion

- Invariante: `INV-SEPARATION-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: range_probability combina regimen/contradiccion con el riesgo de que una orden pendiente no se active y se muestra como rango/sin resolver.
- Reproduccion: `semantic_dependency_trace`
- Resultado observado: `{"display_label": "rango/sin resolver", "single_output": "range_probability"}`
- Impacto: No puede saberse si la masa representa lateralidad, orden no ejecutada o expiracion sin tocar barreras.
- Correccion candidata: Separar primero activacion/ejecucion de outcome condicional TP-SL-expiracion y definir el horizonte de cada evento.
- Referencias de codigo: `analysis_engine.py:268`, `analysis_engine.py:270`, `analysis_engine.py:292`

### E1.3-F14 - RSI introduce discontinuidades arbitrarias en los limites

- Invariante: `INV-CONT-01`
- Severidad: `medium`
- Estado: `failed`
- Observacion: RSI 65 aporta +0.20 al score tecnico long; RSI 65.000001 aporta 0.
- Reproduccion: `pure_function`
- Resultado observado: `{"delta": -0.2, "score_a": 0.2, "score_b": 0.0}`
- Impacto: Cambios despreciables del indicador pueden alterar capas posteriores de forma material.
- Correccion candidata: Sustituir escalones no validados por transformaciones continuas predefinidas o categorias cuya discontinuidad tenga evidencia.
- Referencias de codigo: `analysis_engine.py:2255`

### E1.3-F15 - score_components no satisface la traza obligatoria por regla

- Invariante: `INV-TRACE-01`
- Severidad: `critical`
- Estado: `failed`
- Observacion: La salida enumera componentes, pero no incluye ID y version de regla, formula, entradas con unidad/fuente, antes/despues ni contribucion neta tras caps.
- Reproduccion: `output_schema_inspection`
- Resultado observado: `{"component_keys": ["breadth_bias", "contradiction_penalty", "crowding_penalty", "cvd_bias", "derivatives_period", "fibonacci_confluence_score", "fibonacci_probability_adjustment", "funding_penalty", "funding_relative_penalty", "higher_timeframe_penalty", "level_penalty", "levels_timeframe", "leverage_penalty", "leverage_policy", "liquidity_penalty", "market_regime_bias", "momentum_bias", "oi_context_penalty", "oi_trend_bias", "order_book_bias", "overextension_penalty", "price_vs_entry_bias", "risk_calibration_flags", "risk_calibration_range_adjustment", "risk_calibration_score_addition", "risk_calibration_tp_adjustment", "rr_bias", "rsi_timeframe", "sentiment_penalty", "taker_flow_bias", "technical_alignment_score", "technical_barrier_penalty", "technical_direction_bias", "technical_entry_timing_penalty", "trend_bias", "volatility_penalty", "volatility_timeframe", "volume_bias", "zone_activation_probability", "zone_confluence_score", "zone_probability_adjustment", "zone_range_probability_adjustment", "zone_risk_score_addition"], "input_units_present": false, "pre_post_cap_contribution_present": false, "rule_version_present": false, "stable_rule_id_present": false}`
- Impacto: El aprendizaje no puede atribuir de forma completa que regla ayudo, perjudico o quedo anulada por un cap.
- Correccion candidata: Crear registro ejecutable de reglas y una traza append-only con entradas, salida intermedia y delta final por regla/version.
- Referencias de codigo: `analysis_engine.py:570`

### E1.3-F16 - Los umbrales se aplican universalmente sin validacion por pares

- Invariante: `INV-PAIR-01`
- Severidad: `high`
- Estado: `unverified`
- Observacion: Los thresholds porcentuales son compartidos por todos los simbolos; no existe matriz de evidencia por par, liquidez, volatilidad u horizonte.
- Reproduccion: `configuration_trace`
- Resultado observado: `{"fallback_when_pair_unvalidated": false, "per_pair_validation_registry": false}`
- Impacto: No puede afirmarse que una regla sea valida para todos los pares admitidos.
- Correccion candidata: Evaluar cada variable normalizada por par/horizonte y bloquear reglas sin muestra comparable suficiente.
- Referencias de codigo: `analysis_engine.py:193`, `analysis_engine.py:194`, `analysis_engine.py:195`

### E1.3-F17 - La confianza es otro score heuristico, no incertidumbre estimada

- Invariante: `INV-SEPARATION-01`
- Severidad: `high`
- Estado: `failed`
- Observacion: confidence deriva de puntos manuales y penalizaciones compartidas con el score, sin relacion de cobertura observada.
- Reproduccion: `dependency_trace`
- Resultado observado: `{"calibration_error_used": false, "data_coverage_used_as_statistical_uncertainty": false, "sampling_uncertainty_used": false}`
- Impacto: Una etiqueta de confianza puede parecer precision estadistica sin serlo.
- Correccion candidata: Separar calidad de datos de incertidumbre predictiva y estimar ambas con metricas verificables.
- Referencias de codigo: `analysis_engine.py:349`, `analysis_engine.py:1930`

## Ganancia de la fase

E1.3 no mejora todavia los porcentajes de produccion. Evita corregir a ciegas: cada defecto queda asociado a un invariante, una reproduccion, una severidad y una correccion candidata. Estos casos seran pruebas de aceptacion del challenger y variables de ablation en E1.4.

## Siguiente fase

E1.4 medira sobre snapshots historicos preservados cuanto cambia cada salida al retirar o reformular cada regla, sin sobrescribir recomendaciones antiguas.
