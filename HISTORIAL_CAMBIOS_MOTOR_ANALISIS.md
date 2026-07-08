# Historial de Cambios del Motor de Analisis

Este archivo registra cada cambio relevante del motor de analisis para poder auditar si mejora o empeora con operaciones reales posteriores.

## 2026-07-08 - learning-v0.2-underweighted-risk

Estado: aplicado como fase 1 de mejora de la base de aprendizaje.

Origen:
- Revision manual de la operacion `#204`: el plan `BTCUSDT SHORT` cerro por `stop_loss` con `-32.45 USDT`.
- La evaluacion anterior la clasificaba como `analysis_warned_risk` porque Fibonacci era desfavorable.
- La conclusion era incompleta: el motor tambien habia recomendado `simular`, setup `B`, confianza `alta`, TP `61.09%`, tecnico `80/100`, direccion `61/100` y regimen `tendencia_bajista`.
- Lectura correcta: el analisis detecto riesgos, pero la recomendacion final pudo infraponderarlos frente a senales favorables.

Cambios realizados:
- Se crea `LEARNING_EVALUATOR_VERSION = learning-v0.2-underweighted-risk`.
- `learning_evaluations.structured_json` guarda `learning_evaluator_version` y `signal_diagnostics`.
- `signal_diagnostics` separa:
  - `supporting_signals`: senales que apoyaban la operacion.
  - `opposing_signals`: senales que contradecian la operacion.
  - `internal_inconsistencies`: incoherencias entre confianza, calidad, EV y alertas.
  - `warning_detection_quality`: calidad de deteccion de riesgos.
  - `decision_quality`: si la decision fue coherente o infrapondero riesgo.
- Se anade el veredicto `analysis_warned_but_underweighted_risk`.
- Se anade la categoria `investigate_underweighted_detected_risk`.
- `learning_signal.comparable_case_key` incorpora `decision_quality` y `warning_detection_quality`.
- `learning_summary` visible en operaciones futuras distingue riesgo detectado pero subponderado frente a simple refuerzo de una alerta aislada.

Validacion local:
- `.\.venv\Scripts\python.exe -m py_compile app.py tests\test_pending_zone_analysis.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- Recalculo en modo lectura de la operacion real `#204`:
  - `analysis_verdict`: `analysis_warned_but_underweighted_risk`.
  - `learning_signal.category`: `investigate_underweighted_detected_risk`.
  - `decision_quality`: `risk_underweighted`.
  - `warning_detection_quality`: `detected_multiple_material_warnings`.
  - 8 senales favorables, 8 senales contrarias, 3 incoherencias internas.

Regla vigente:
- Esta fase no cambia probabilidades del motor de analisis.
- Primero mejora la calidad de la base de aprendizaje para que futuras auditorias no agreguen casos mal interpretados.
- La fase siguiente debe auditar operaciones cerradas con esta nueva taxonomia antes de tocar pesos del motor.

## 2026-07-08 - Auditoria read-only de riesgo subponderado

Estado: aplicado como fase 2 de mejora de aprendizaje.

Objetivo:
- Recalcular en memoria las operaciones cerradas con la taxonomia `learning-v0.2-underweighted-risk`.
- No escribir en Supabase ni sobrescribir evaluaciones historicas.
- Medir si el patron detectado en la operacion `#204` era aislado o recurrente.

Cambios realizados:
- Se crea el endpoint protegido `/api/learning/underweighted-risk-audit`.
- Se crea `build_underweighted_risk_audit_report`, que lee operaciones cerradas, recomendacion asociada y ticks, y reconstruye `build_structured_learning_evaluation` en memoria.
- Se crean funciones de auditoria:
  - `underweighted_risk_case_from_evaluation`.
  - `summarize_underweighted_risk_cases`.
  - `group_underweighted_risk_cases`.
- El informe agrupa por `analysis_verdict`, `decision_quality`, `warning_detection_quality`, version del motor, marco temporal, lado, setup y confianza.
- El informe devuelve `risk_cases` ordenados por fallo, numero de senales contrarias, incoherencias internas y tamano de PnL.

Validacion local:
- `.\.venv\Scripts\python.exe -m py_compile app.py tests\test_pending_zone_analysis.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`

Primera lectura Supabase sin escritura:
- Operaciones cerradas leidas: 98.
- Casos evaluables: 98.
- Casos resueltos para metrica dura: 93.
- Win rate global recalculado: 47.31%.
- PnL total recalculado: `-111.4915 USDT`.
- Casos `risk_underweighted`: 7 / 93 (7.53%).
- Fallos `risk_underweighted`: 3 / 49 fallos (6.12%).
- Fallos `analysis_missed_risk`: 8.
- Veredicto `analysis_warned_but_underweighted_risk`: 3 casos, 0 exitos, PnL medio `-53.7174 USDT`.
- Casos principales detectados: operaciones `#100`, `#204`, `#142`, `#170`, `#94`, `#87`, `#34`.

Lectura tecnica:
- El patron de la `#204` no es masivo, pero si existe y merece vigilancia.
- Los casos perdedores con `analysis_warned_but_underweighted_risk` son pocos pero caros.
- Tambien hay ganadores con `risk_underweighted`; por tanto no se deben aplicar frenos automaticos todavia sin revisar subpatrones.
- La siguiente fase debe estudiar los 7 casos detectados y separar que senales contrarias filtraron fallos de cuales tambien aparecieron en ganadores.

## 2026-07-08 - Auditoria de efectividad por senal

Estado: aplicado como fase 3 de mejora de aprendizaje.

Objetivo:
- Separar senales contrarias que filtran fallos de senales ambiguas que tambien aparecen en operaciones ganadoras.
- Evitar convertir una alerta aislada en freno automatico si historicamente tambien acompana buenos resultados.
- Detectar combinaciones de senales que si parecen mas peligrosas que cada senal por separado.

Cambios realizados:
- El endpoint `/api/learning/underweighted-risk-audit` incorpora:
  - `opposing_signal_effectiveness`.
  - `internal_inconsistency_effectiveness`.
  - `supporting_signal_effectiveness`.
  - `risk_underweighted_opposing_signals`.
  - `risk_underweighted_internal_inconsistencies`.
  - `risk_underweighted_signal_pairs`.
- Se crean funciones:
  - `signal_learning_read`.
  - `group_signal_effectiveness`.
  - `group_signal_pairs`.
- Cada senal queda clasificada como:
  - `candidate_risk_filter`: muestra minima, mas fallos que exitos y PnL medio negativo.
  - `ambiguous_or_winner_signal`: aparece bastante en ganadores o PnL positivo.
  - `mixed_context_needs_review`: lectura mixta.
  - `sample_too_small`: muestra insuficiente.

Validacion local:
- `.\.venv\Scripts\python.exe -m py_compile app.py tests\test_pending_zone_analysis.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`

Primera lectura Supabase sin escritura:
- Senales individuales candidatas en toda la muestra:
  - `extreme_fibonacci_risk`: 5 casos, 4 fallos, PnL medio `-28.7199`, 3 fallos `risk_underweighted`.
  - `cvd_against_plan`: 17 casos, 10 fallos, PnL medio `-1.3642`, 2 fallos `risk_underweighted`.
  - `extreme_fibonacci_entry_zone`: 3 casos, 3 fallos, PnL medio `-51.9494`, 2 fallos `risk_underweighted`.
- Senales ambiguas que NO deben ser freno automatico aislado:
  - `technical_barrier_before_target`: 52 casos, 26 exitos, 26 fallos, PnL medio positivo.
  - `extreme_sentiment_risk`: 47 casos, 27 exitos, 20 fallos, PnL medio positivo.
  - `price_overextension_risk`: 41 casos, 21 exitos, 20 fallos, PnL medio positivo.
  - `short_into_oversold_rsi`: 12 casos, 8 exitos, 4 fallos, PnL medio positivo.
- En casos `risk_underweighted`, las senales candidatas mas claras fueron:
  - `extreme_fibonacci_risk`: 4 casos, 3 fallos, PnL medio `-32.4783`.
  - `extreme_sentiment_risk`: 5 casos, 3 fallos, PnL medio `-20.3685`.
  - `short_into_oversold_rsi`: 3 casos, 2 fallos, PnL medio `-17.5012`.
  - `cvd_against_plan`: 3 casos, 2 fallos, PnL medio `-9.6697`.
- Combinacion mas peligrosa detectada:
  - `extreme_fibonacci_risk + extreme_sentiment_risk`: 3 casos, 3 fallos, PnL medio `-53.7174`, operaciones `#100`, `#204`, `#142`.

Lectura tecnica:
- Fibonacci extremo no debe tratarse igual que Fibonacci simplemente desfavorable.
- CVD contrario merece vigilancia, pero como freno aislado aun es moderado; funciona mejor dentro de clusters de riesgo.
- Sentimiento extremo, barreras, extension de precio y RSI extremo son peligrosos solo en combinacion; como senales aisladas filtran tambien operaciones ganadoras.
- La fase siguiente puede preparar una regla candidata conservadora para el motor: penalizar mas cuando coincidan Fibonacci extremo + sentimiento extremo, especialmente si ademas existe sobreconfianza o CVD contrario.

## 2026-07-08 - rules-v0.11-underweighted-risk-cluster

Estado: aplicado como fase 4 de mejora del motor de analisis.

Objetivo:
- Convertir la evidencia mas solida de fase 3 en un freno conservador del motor.
- No penalizar alertas aisladas que tambien aparecen en operaciones ganadoras.
- Mantener trazabilidad en `risk_calibration_context.flags`, `alerts`, scores y version del motor.

Origen:
- Auditoria `learning-v0.2-underweighted-risk`, 93 casos resueltos recalculados.
- Cluster mas peligroso:
  - `extreme_fibonacci_risk + extreme_sentiment_risk`.
  - 3 casos, 3 fallos.
  - PnL medio `-53.7174 USDT`.
  - Operaciones `#100`, `#204`, `#142`.
- Senales aisladas consideradas ambiguas y NO usadas como freno fuerte independiente:
  - `technical_barrier_before_target`.
  - `extreme_sentiment_risk`.
  - `price_overextension_risk`.
  - `short_into_oversold_rsi`.

Cambios realizados:
- El motor sube a `rules-v0.11-underweighted-risk-cluster`.
- `build_risk_calibration_context` recibe `sentiment_penalty` y `cvd_bias`.
- Se anade flag `extreme_fib_extreme_sentiment_cluster` cuando:
  - `fibonacci_context.bias == desfavorable`, y
  - `fibonacci_context.score < 30` o `entry_zone == retroceso_extremo`, y
  - `sentiment_penalty >= 0.01`.
- Penalizacion del cluster principal:
  - TP probability adjustment `-0.035`.
  - `risk_score_addition +0.08`.
  - `quality_score_penalty +12`.
  - `confidence_score_penalty +10`.
  - `expected_value_score_penalty +9`.
  - `execution_risk_score_addition +8`.
  - `grade_cap = C`.
  - No fuerza `observar`.
- Se anade flag incremental `extreme_fib_sentiment_cvd_contra` cuando el cluster anterior aparece con `cvd_bias < -0.005`.
- Penalizacion incremental:
  - TP probability adjustment `-0.015`.
  - `risk_score_addition +0.03`.
  - `quality_score_penalty +4`.
  - `confidence_score_penalty +5`.
  - `expected_value_score_penalty +4`.
  - `execution_risk_score_addition +4`.
  - `grade_cap = C`.
- La metrica visible `risk_calibration` deja de mostrar texto fijo v0.10 y usa lenguaje versionado generico.

Regla vigente:
- Fibonacci simplemente desfavorable no activa este freno v0.11.
- Sentimiento extremo aislado no activa este freno v0.11.
- CVD contrario aislado no activa este freno v0.11.
- El freno aparece solo por cluster y queda registrado en `risk_calibration_context.flags`.

Validacion local:
- `.\.venv\Scripts\python.exe -m py_compile analysis_engine.py app.py tests\test_pending_zone_analysis.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- Tests nuevos:
  - El patron tipo operacion `#204` activa `extreme_fib_extreme_sentiment_cluster` y `extreme_fib_sentiment_cvd_contra`.
  - Un Fibonacci desfavorable no extremo con sentimiento extremo no activa el freno v0.11.

Auditoria futura requerida:
- Comparar operaciones nuevas `rules-v0.11-underweighted-risk-cluster` contra v0.10.
- Medir si el cluster reduce fallos caros sin filtrar demasiados ganadores.
- No endurecer a `force_observar` hasta tener mas casos cerrados del motor v0.11.

## 2026-07-08 - RSI como agravante contextual v0.11

Estado: aplicado como fase 5 de mejora del motor de analisis.

Objetivo:
- Incorporar el RSI con peso real cuando se combina con otras senales relevantes.
- Evitar penalizar RSI extremo como senal aislada, porque la auditoria mostro que tambien aparece en operaciones ganadoras.
- Registrar el peso del RSI en `risk_calibration_context.flags` para auditarlo despues.

Lectura Supabase sin escritura:
- `short_into_oversold_rsi` en toda la muestra:
  - 12 casos.
  - 8 exitos, 4 fallos.
  - PnL medio `+8.9426`.
  - Lectura: no debe ser freno aislado.
- `short_into_oversold_rsi` dentro de `risk_underweighted`:
  - 3 casos.
  - 1 exito, 2 fallos.
  - PnL medio `-17.5012`.
  - Operaciones `#100`, `#204`, `#34`.
- Pares `risk_underweighted` con RSI que salieron candidatos:
  - `extreme_sentiment_risk + short_into_oversold_rsi`: 3 casos, PnL medio `-17.5012`.
  - `price_overextension_risk + short_into_oversold_rsi`: 3 casos, PnL medio `-17.5012`.
  - `short_into_oversold_rsi + technical_barrier_before_target`: 3 casos, PnL medio `-17.5012`.
  - `short_into_oversold_rsi + thin_expected_value_score`: 3 casos, PnL medio `-17.5012`.
- Pares con muestra menor pero todos perdedores:
  - `cvd_against_plan + short_into_oversold_rsi`: 2 casos, 2 fallos, PnL medio `-43.3556`.
  - `extreme_fibonacci_risk + short_into_oversold_rsi`: 2 casos, 2 fallos, PnL medio `-43.3556`.

Cambios realizados:
- `build_risk_calibration_context` recibe `rsi_signal`.
- Se crea helper `rsi_extreme_against_entry`.
- Se anade flag `rsi_extreme_multi_risk_cluster` cuando:
  - RSI esta extremo contra la entrada (`short` con RSI <= 30 o `long` con RSI >= 70), y
  - existen al menos dos riesgos materiales entre Fibonacci extremo, sentimiento extremo y CVD contrario.
- Penalizacion:
  - TP probability adjustment `-0.012`.
  - `risk_score_addition +0.025`.
  - `quality_score_penalty +4`.
  - `confidence_score_penalty +4`.
  - `expected_value_score_penalty +3`.
  - `execution_risk_score_addition +4`.
  - `grade_cap = C`.
- Se anade flag adicional `rsi_extreme_with_fib_sentiment_cluster` cuando el RSI extremo aparece dentro del cluster Fibonacci extremo + sentimiento extremo.
- Penalizacion adicional:
  - TP probability adjustment `-0.008`.
  - `risk_score_addition +0.015`.
  - `quality_score_penalty +3`.
  - `confidence_score_penalty +3`.
  - `expected_value_score_penalty +2`.
  - `execution_risk_score_addition +3`.
  - `grade_cap = C`.

Regla vigente:
- RSI extremo aislado no activa ningun freno.
- RSI + sentimiento extremo aislado no activa el freno si no hay otro riesgo material.
- RSI + sentimiento extremo + CVD contrario si activa `rsi_extreme_multi_risk_cluster`.
- RSI + Fibonacci extremo + sentimiento extremo activa el agravante principal y el flag adicional de cluster.

Validacion local:
- `.\.venv\Scripts\python.exe -m py_compile analysis_engine.py app.py tests\test_pending_zone_analysis.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis`
- `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- Tests nuevos:
  - El patron tipo operacion `#204` activa los flags de Fibonacci/sentimiento/CVD y tambien los flags RSI contextuales.
  - RSI extremo aislado no se penaliza.
  - RSI + sentimiento + CVD se penaliza aunque Fibonacci no sea extremo.
  - Fibonacci no extremo + sentimiento + RSI sin CVD no activa el freno RSI.

## 2026-07-08 - Cierre fase 5: regla general de acumulacion descartada

Estado: auditado y no aplicado al motor.

Objetivo:
- Evaluar la regla propuesta de penalizar cuando existan 3 o mas alertas fuertes acumuladas.
- Aplicarla solo si mejora de verdad el motor actual.

Alertas evaluadas:
- Fibonacci desfavorable extremo.
- CVD contrario.
- RSI extremo contra entrada.
- Sentimiento extremo.
- Barrera tecnica antes del TP.
- Mismatch confianza/calidad.
- Expected value score justo o mismatch confianza/EV.

Lectura Supabase sin escritura:
- Muestra: 93 operaciones resueltas.
- Resultado global: 44 exitos, 49 fallos, win rate `47.31%`, PnL medio `-1.1988 USDT`.
- Casos con `>= 3` alertas fuertes: 46 operaciones, 25 exitos, 21 fallos, win rate `54.35%`, PnL medio `+3.6264 USDT`.
- Casos con `>= 4` alertas fuertes: 25 operaciones, 16 exitos, 9 fallos, win rate `64.00%`, PnL medio `+12.4547 USDT`.
- Casos con `>= 5` alertas fuertes: 12 operaciones, 7 exitos, 5 fallos, win rate `58.33%`, PnL medio `+16.7460 USDT`.
- Casos con `>= 6` alertas fuertes: 5 operaciones, 1 exito, 4 fallos, PnL medio `-27.6591 USDT`.

Decision tecnica:
- No se implementa la regla general `>= 3 alertas fuertes`.
- Motivo: habria penalizado demasiadas operaciones ganadoras y, con la muestra actual, empeoraria la precision del motor.
- La unica zona claramente negativa fue `>= 6` alertas, pero la muestra es demasiado pequena para endurecer reglas y varios casos ya quedan cubiertos por los clusters v0.11.

Regla vigente:
- Mantener penalizaciones por clusters concretos con evidencia.
- No penalizar por conteo bruto de alertas.
- Reauditar cuando existan suficientes operaciones nuevas generadas por `rules-v0.11-underweighted-risk-cluster`.

## 2026-07-08 - Cierre trazabilidad de aprendizaje estructurado

Estado: aplicado como cierre del plan de mejora de aprendizaje.

Objetivo:
- Evitar conclusiones decorativas tipo "reforzar Fibonacci".
- Guardar una conclusion util para auditorias futuras, especialmente en casos `analysis_warned_but_underweighted_risk`.

Cambios realizados:
- La conclusion de fallos por riesgo detectado pero subponderado queda estructurada en texto con:
  - Resultado.
  - Lectura previa.
  - Error probable.
  - Senales que apoyaban.
  - Senales que contradecian.
  - Incoherencias internas.
  - Aprendizaje accionable.
- Se mantiene el esquema actual de base de datos: el cambio mejora `learning_summary` sin requerir migracion.
- Se anade helper `signal_details_text` para reutilizar detalles de `signal_diagnostics`.

Lectura tecnica:
- El aprendizaje ya no guarda solo que una alerta existia.
- Guarda si el motor detecto riesgos, si la decision final los respeto y que contradicciones concretas estaban activas.
- Esto permite auditar despues si v0.11 reduce fallos caros sin destruir operaciones ganadoras.

## 2026-07-08 - Refresco de conclusiones antiguas de aprendizaje

Estado: aplicado como correccion del cierre de aprendizaje.

Problema detectado:
- Las operaciones que ya tenian `learning_summary` guardado conservaban la conclusion antigua.
- `refresh_learning_conclusions_with_db` solo recalculaba operaciones cerradas con `learning_summary` nulo o vacio.
- Por eso una operacion como `#204` podia seguir mostrando el texto antiguo aunque el generador nuevo ya produjera una conclusion mas precisa.

Cambios realizados:
- Se anade `STALE_LEARNING_SUMMARY_MARKERS`.
- Se anade `learning_summary_needs_refresh`.
- `refresh_learning_conclusions_with_db` tambien selecciona conclusiones obsoletas que contienen `este caso debe reforzar esas senales de riesgo`.
- Las conclusiones antiguas de fallo con advertencias se reescriben en formato estructurado para no volver a quedar marcadas como obsoletas.

Regla vigente:
- No se reescriben todas las operaciones indiscriminadamente.
- Solo se refrescan conclusiones vacias o conclusiones antiguas con marcador obsoleto.

## 2026-07-06 - rules-v0.10-risk-gated-calibration

Estado: aplicado tras auditoria completa de operaciones cerradas.

Origen:
- Auditoria total: `auditorias_aprendizaje/2026-07-06_operaciones_cerradas_184_auditoria_profunda_motor_v0_9.md`.
- Muestra revisada: 198 operaciones totales, 184 cerradas, 170 cerradas resueltas para metrica dura y 67 resueltas del motor `rules-v0.9-pending-zone-adjusted`.
- Conclusion principal: v0.9 mejoro mucho el control de dano frente a versiones previas, pero seguia mal calibrado cuando coincidian riesgo estructural alto, TP lejano, direccion debil o zona pendiente peligrosa.
- Decision tecnica: no conectar aprendizaje historico en tiempo real. Se convierten conclusiones auditadas en reglas explicitas, versionadas y auditables dentro del motor.

Cambios realizados:
- El motor sube a `rules-v0.10-risk-gated-calibration`.
- Se actualiza `ENGINE_AUDIT_REFERENCE` con la auditoria de 2026-07-06 y sus tasas de fallo clave.
- Se crea `risk_calibration_context`, guardado en el resultado y en el snapshot de cada analisis.
- `risk_calibration_context` registra flags, ajuste neto de probabilidad TP, adicion a `risk_score`, penalizaciones de calidad/confianza/esperanza, limite de grado y si fuerza `observar`.
- Se anade la metrica explicada `risk_calibration` para ver los frenos v0.10 en la respuesta del analisis, no solo en el JSON interno.
- Se penalizan los clusters que la auditoria mostro mas fragiles:
  - `sl_probability >= 0.50` y especialmente `>= 0.55`.
  - direccion probable inicial por debajo de 40/100.
  - `technical_rating.score < 40`.
  - `risk_reward_ratio >= 3` y `reward_distance_pct >= 3`.
  - `risk_distance_pct < 0.25` o `>= 3`.
  - movimiento 24h contra el lado propuesto.
  - EMA stack 15m contra el lado propuesto.
  - precio vs EMA21 1h contra el lado propuesto.
  - zona pendiente con ajuste negativo, riesgo alto de barrida, falsa ruptura y `stop_breakdown`.
- Las penalizaciones afectan a probabilidad TP, `risk_score`, `operation_quality_score`, `confidence_score`, `expected_value_score`, `execution_risk_score`, `setup_grade` y decision final.
- Fibonacci favorable deja de sumar bonus directo a probabilidad. Se conserva como contexto y confluencia descriptiva, pero no como senal positiva primaria.

Regla vigente:
- El motor sigue sin leer operaciones cerradas durante un analisis nuevo.
- El aprendizaje historico solo entra al motor mediante cambios explicitos, versionados y documentados.
- La calibracion v0.10 es conservadora: reduce optimismo en grupos fragiles; no crea nuevas bonificaciones positivas.
- Todo analisis nuevo debe guardar `risk_calibration_context` para poder medir despues si cada flag redujo fallos o tambien filtro operaciones ganadoras.

Validacion local:
- `.\.venv\Scripts\python.exe -m py_compile analysis_engine.py tests\test_pending_zone_analysis.py`
- `.\.venv\Scripts\python.exe -m unittest tests.test_pending_zone_analysis`

Auditoria futura requerida:
- Comparar operaciones nuevas `rules-v0.10-risk-gated-calibration` contra la linea base v0.9:
  - win rate, PnL medio, fallo por SL y decision final.
  - grupos con `risk_calibration_context.flags`.
  - operaciones forzadas a `observar` frente a resultado real si el usuario decide abrirlas igualmente.
  - impacto de neutralizar Fibonacci favorable.
- No relajar ni endurecer mas pesos hasta tener una muestra nueva suficiente, idealmente al menos 50 operaciones resueltas v0.10 y revision separada de operaciones abiertas contra la recomendacion.

## 2026-07-01 - Idempotencia de operaciones y sincronizacion concurso/lista

Estado: aplicado tras detectar contradiccion visual en operacion `#161`.

Origen:
- La operacion `#161` de MauricioMC aparecia cerrada en el ranking de concurso y abierta en otra zona de la app.
- Supabase confirmo que `operations.id=161` estaba `CLOSED` por `take_profit`, pero existian dos eventos `wallet_events` de cierre automatico para la misma operacion.
- Esto indica carrera entre refrescos concurrentes: dos peticiones podian leer una operacion como `OPEN` y ejecutar el flujo de cierre antes de que la UI quedara sincronizada.

Cambios realizados:
- Activacion de orden pendiente: el `UPDATE` exige `status = 'PENDING_ENTRY'` y solo registra tick/evento si realmente actualizo la fila.
- Cierre automatico TP/SL: el `UPDATE` exige `status = 'OPEN'` y solo registra ticks/evento wallet si realmente cerro la fila.
- Cierre manual: el `UPDATE` exige `status = 'OPEN'` para impedir doble cierre por doble request.
- Cancelacion de orden pendiente: el `UPDATE` exige `status = 'PENDING_ENTRY'`.
- Frontend: `loadOperations` usa secuencia de peticiones para que una respuesta antigua no pise un estado mas reciente.
- Frontend: el estado de concurso reconcilia las operaciones del usuario actual con la lista local para evitar ver una operacion cerrada y abierta a la vez.

Regla vigente:
- Una operacion solo puede transicionar una vez desde `PENDING_ENTRY` a `OPEN`.
- Una operacion solo puede transicionar una vez desde `OPEN` a `CLOSED`.
- Solo despues de una transicion efectiva se registran ticks operativos, eventos wallet y aprendizaje posterior.

Riesgo esperado:
- Bajo. Endurece condiciones de escritura sin cambiar reglas de calculo.
- Corrige carreras entre multiples llamadas de precio/concurso y evita registros duplicados futuros.
- Dato historico detectado: `wallet_events` de la operacion `#161` contiene un evento duplicado; el saldo/ranking actual se calcula desde `operations` y no duplica el PnL.

## 2026-07-01 - Proteccion de precio Binance Futures contra rate limit

Estado: aplicado para estabilizar la app online tras ban HTTP 418 de Binance USD-M Futures.

Origen:
- Produccion mostro errores intermitentes al cargar precio y operaciones.
- Binance devolvio `HTTP 418` indicando exceso de peticiones desde la IP de Railway y recomendando evitar REST repetitivo para datos vivos.
- El endpoint `/api/price` devolvia 502 si Binance fallaba, dejando la pantalla sin precio y generando mas reintentos desde frontend.

Cambios realizados:
- `market_data.get_price` usa cache en memoria por simbolo durante 12 segundos para agrupar peticiones simultaneas de usuarios/pestanas.
- Se detecta `HTTP 418/429`, se guarda `backoff_until` y se evita seguir golpeando Binance Futures mientras dura el limite.
- Las fuentes opcionales de Binance Futures usadas por el analisis respetan el mismo backoff.
- `/api/price` devuelve ultimo precio conocido de memoria o `price_ticks` como fallback visual si Binance esta limitado.
- Los fallbacks obsoletos se marcan con `stale=true` y no activan limit orders, no cierran TP/SL y no se guardan como ticks operativos.
- `/api/operations/check-exits` devuelve respuesta neutral cuando solo hay fallback obsoleto.
- El frontend distingue precio vivo de precio guardado, bloquea cierres manuales con precio obsoleto y baja el polling visual de 15 a 30 segundos.

Regla vigente:
- Solo un precio fresco de Binance Futures o cache servidor muy reciente puede activar entradas pendientes o cerrar TP/SL.
- Un precio guardado sirve para mantener la app visible, no para tomar decisiones operativas ni alimentar aprendizaje.
- El aprendizaje no debe registrar conclusiones basadas en cierres/activaciones con precio obsoleto.

Riesgo esperado:
- Bajo para integridad operativa: se evita actuar con datos caducados.
- Medio para experiencia durante un ban activo: la app puede mostrar ultimo precio guardado hasta que Binance permita de nuevo la IP, pero no debe simular cierres reales con ese dato.
- Pendiente futuro: sustituir polling REST vivo por fuente centralizada tipo websocket/worker para autonomia real de operaciones.

## 2026-06-30 - Separacion estricta entre analisis y aprendizaje

Estado: aplicado para restaurar el principio base del proyecto.

Origen:
- Auditoria completa del flujo `/api/analyze` detecto que el analisis ejecutaba `apply_learning_modifier`.
- Ese modificador consultaba operaciones cerradas y podia alterar probabilidades, grado, decision y resumen durante un analisis nuevo.
- Esto contradecia la regla del proyecto: el analisis debe depender solo de reglas, algoritmos y datos actuales de mercado/API; el aprendizaje debe servir para auditoria posterior e hipotesis, no para modificar resultados en tiempo real.

Cambios realizados:
- `/api/analyze` ejecuta solo `analyze_trade(proposal)`.
- Se elimina la importacion de `apply_learning_modifier` desde `app.py`.
- Se elimina `learning_engine.py`, modulo antiguo de modificador automatico basado en casos historicos.
- La UI del resultado de analisis deja de mostrar caja o chip de aprendizaje dentro del analisis.
- El aprendizaje posterior se mantiene en `operations.learning_summary`, `learning_evaluations` y auditorias agregadas, sin intervenir en nuevas probabilidades.

Regla vigente:
- Ningun analisis nuevo puede consultar operaciones cerradas ni historico de aprendizaje.
- Ningun aprendizaje modifica probabilidades, setup grade, decision o resumen del analisis.
- Cualquier mejora derivada de aprendizaje debe convertirse primero en hipotesis/auditoria y solo entrar al motor mediante cambio explicito aprobado.

Riesgo esperado:
- Bajo y deseado. Puede cambiar resultados de analisis futuros si antes estaban alterados por aprendizaje, pero esos resultados pasan a ser motor puro y trazable.

## 2026-06-30 - Robustez y rendimiento del analisis online

Estado: aplicado para evitar timeout del analisis en produccion.

Origen:
- En local el analisis funcionaba, pero online la interfaz podia mostrar error.
- Una prueba autenticada contra `/api/analyze` en Railway devolvio HTTP 200, pero tardo `31.011 ms`.
- El frontend tenia timeout global de `30.000 ms`, por lo que podia cancelar el analisis justo antes de recibir la respuesta.

Cambios realizados:
- Las fuentes opcionales externas usan el mismo timeout corto que Binance Futures, evitando esperas largas de 15 segundos.
- El snapshot del motor consulta en paralelo velas multi-timeframe, order book, trades, ticker 24h, derivados, mercado global, amplitud y sentimiento.
- La capa de derivados consulta en paralelo funding, open interest, ratios long/short y taker ratio por periodo.
- Si una fuente secundaria falla o tarda demasiado, el analisis continua con esa capa vacia en vez de bloquear todo el resultado.
- La llamada frontend de `/api/analyze` tiene timeout especifico de `90.000 ms` y mensajes de error propios de analisis.
- El aprendizaje deja de consultar `price_ticks` para operaciones cerradas por TP/SL, porque su resultado ya es definitivo; esos ticks solo se consultan para cierres manuales donde hace falta contrafactual.

Motivo:
- El analisis completo combina muchas fuentes; no debe depender de que todas respondan en cadena dentro de 30 segundos.
- Mantener disponible el motor online sin alterar las formulas de probabilidad ni los pesos de decision.

Riesgo esperado:
- Bajo. Cambia la estrategia de obtencion de datos y tolerancia a fallos, no el calculo de scoring.
- Si una fuente secundaria no responde, su disponibilidad queda reflejada en `snapshot.availability` y el motor trabaja con valores neutrales o vacios ya previstos.
- Bajo en aprendizaje. No cambia la clasificacion de operaciones ganadas/perdidas por TP/SL; reduce consultas innecesarias contra Supabase durante cada analisis.

## 2026-06-29 - Correccion cierre global TP/SL en concurso

Estado: aplicado y verificado contra operaciones reales atrasadas.

Origen:
- Auditoria de operaciones abiertas del usuario `chaval` en concurso.
- La operacion `#92` BTCUSDT SHORT seguia abierta aunque el precio actual ya estaba por debajo del TP.
- Al revisar el camino real desde la entrada, la primera salida valida fue STOP LOSS el `2026-06-10T15:46:00+00:00`, antes de cualquier TP posterior.
- La operacion `#81` ETHUSDT LONG tambien estaba abierta; al ampliar el historico se detecto que habia alcanzado TAKE PROFIT el `2026-06-15T10:54:00+00:00`.

Cambios realizados:
- `/api/price` deja de revisar TP/SL solo del usuario logueado y refresca todas las operaciones activas del simbolo consultado.
- `/api/operations/check-exits` aplica el mismo refresco global del simbolo, devolviendo al frontend solo las operaciones del usuario actual.
- Al cargar el concurso, se revisan todos los simbolos activos del concurso antes de construir ranking y capitales.
- El limite de velas 1m para buscar el primer cruce TP/SL sube de 5 paginas a 60 paginas, cubriendo operaciones mensuales largas.
- Los cierres automaticos guardan `closed_at` con la hora real del cruce detectado cuando existe vela/trade de Binance Futures, no con la hora en la que la app proceso tarde el cierre.
- Se corrigieron en Supabase operaciones atrasadas detectadas: `#92`, `#132`, `#155` y `#81`.

Motivo:
- El concurso muestra operaciones de todos los usuarios; por tanto el cierre automatico no puede depender de que cada usuario consulte su propia operacion.
- El motor de aprendizaje necesita resultado, motivo de cierre y duracion real, no la fecha tardia de procesamiento.

Riesgo esperado:
- Medio-bajo. Aumenta llamadas a Binance Futures cuando se cargan concursos con simbolos activos, pero evita estados abiertos falsos y resultados contaminados.
- La busqueda historica de 60.000 velas puede ser mas lenta en operaciones muy antiguas; se acepta para preservar exactitud en concurso mensual.

## 2026-06-27 - Limpieza de trazabilidad visual Binance Futures

Estado: aplicado tras verificacion online en Railway Singapur.

Origen:
- La app ya consultaba Binance USD-M Futures correctamente, pero la tarjeta visible de precio seguia mostrando `Binance Spot`.
- Quedaban etiquetas internas del motor describiendo velas, order book, ticker 24h y CVD como `spot`, aunque los datos actuales proceden de endpoints Futures.

Cambios realizados:
- La UI de precio en vivo muestra `Binance Futures`.
- El texto del grafico local pasa a describir velas de `Binance Futures 1m`.
- Las evidencias de activacion/cierre se presentan como Binance Futures, incluyendo compatibilidad de lectura para evidencias antiguas.
- Las metricas explicadas del motor cambian sus fuentes a Binance Futures: tendencia multi-TF, momentum, volatilidad, order book, niveles, CVD y ticker 24h.
- El simulador auxiliar de consola pasa de `/api/v3/ticker/price` a `/fapi/v1/ticker/price`.
- Se elimina codigo auxiliar Spot no usado en `market_data.py`.
- Se actualiza el cache-buster de assets para evitar que la app online muestre JS/HTML anterior.

Motivo:
- Evitar mensajes contradictorios entre fuente operativa, motor de analisis, evidencias y visualizacion.
- Mantener una unica fuente de verdad para una simulacion de futuros: Binance USD-M Futures.

Riesgo esperado:
- Bajo. No cambia pesos del motor ni reglas de decision; corrige etiquetas, trazabilidad y restos de fuente antigua.

## 2026-06-26 - Correccion fuente operativa a Binance USD-M Futures

Estado: aplicado a la capa operativa y de datos de mercado.

Origen:
- Auditoria de la operacion `#140` de `mauriciomc`, BTCUSDT SHORT en concurso.
- TP configurado: `58500`.
- Binance Spot marco minimo `58500.10`, por lo que la app no cerro.
- Binance USD-M Futures marco minimo `58388.00`, por lo que una simulacion de futuros si debia considerar tocado el TP.

Cambios realizados:
- `market_data.get_price` pasa a usar `/fapi/v1/ticker/price`.
- `market_data.get_klines` pasa a usar `/fapi/v1/klines`.
- `market_data.get_depth` pasa a usar `/fapi/v1/depth`.
- `market_data.get_24h_ticker` pasa a usar `/fapi/v1/ticker/24hr`.
- `market_data.get_agg_trades` pasa a usar `/fapi/v1/aggTrades`.
- Activacion de ordenes pendientes, cierres TP/SL, historico de mercado, evidencia de salida y expiracion de concurso quedan trazados como Binance USD-M Futures.
- La UI de fuentes de datos deja de hablar de Spot para precio, velas y CVD/delta.

Motivo:
- La app simula operativa de futuros; por tanto, la fuente que decide entradas, TP y SL debe ser Futures, no Spot.
- Evitar divergencias por mechas diferentes entre mercado spot y contrato perpetuo.

Riesgo esperado:
- Medio. Cambia la fuente de precio operativa y puede cerrar/activar operaciones cuando Futures toque niveles aunque Spot no los toque.
- Es el comportamiento correcto para una simulacion de futuros.

Seguimiento:
- Validar operacion `#140` con la nueva fuente antes de cerrarla.
- Revisar futuras operaciones con evidencia `binance_usdm_futures_*`.

## 2026-06-26 - Hipotesis de mejoras candidatas no aplicadas

Estado: documentado, no aplicado al motor.

Archivo creado:
- `HIPOTESIS_MEJORAS_MOTOR_ANALISIS.md`
- `auditorias_aprendizaje/README.md`
- `auditorias_aprendizaje/2026-06-26_operaciones_verificadas_130_hipotesis_motor_v0_9.md`

Origen:
- Auditoria de Supabase sobre operaciones, recomendaciones, ticks y evaluaciones de aprendizaje existentes.
- La auditoria detecta patrones potencialmente utiles, pero la muestra aun no justifica cambiar pesos sin validacion posterior.

Hipotesis registradas:
- Endurecer operaciones con `sl_probability >= 0.50`.
- Penalizar mas `direction_score < 50`.
- Exigir mas confirmacion para longs en `tendencia_bajista`.
- No premiar `risk_reward_ratio` alto si la estructura no acompana.
- Auditar confianza alta en setups C.
- Mantener Fibonacci como confluencia secundaria hasta tener mas muestra.
- Penalizar provisionalmente `stop_breakdown` pendiente con riesgo de falsa ruptura.
- Separar fallo tecnico de fallo por exposicion/apalancamiento.
- Dar mas peso a la decision final `observar` como advertencia real.

Motivo:
- Guardar las conclusiones sin modificar todavia el comportamiento del motor.
- Poder comprobar en el futuro si estas reglas habrian mejorado el resultado antes de implementarlas.

Riesgo esperado:
- Nulo para el motor actual. Solo documentacion y trazabilidad de hipotesis.

Seguimiento:
- Repetir auditoria cuando haya mas operaciones cerradas y evaluadas.
- No aplicar cambios hasta comparar impacto estimado sobre nuevas operaciones.
- Usar la carpeta `auditorias_aprendizaje/` para guardar cada nueva comprobacion con fecha y numero de operaciones verificadas.

## 2026-06-15 - Visualizacion explicita analisis order limit

Estado: aplicado tras auditar que el motor calculaba `zone_analysis`, pero la UI no lo mostraba con suficiente claridad.

Cambios realizados:
- El resumen de analisis muestra tarjetas especificas para ordenes pendientes:
  - `Zona orden`
  - `Activacion`
  - `Barrida`
  - `Ajuste zona`
- Los puntos criticos incluyen una linea explicita de orden pendiente con tipo de orden, zona, confluencia, probabilidad de activacion, barrida y ajuste.
- Se valida con una propuesta real `pending` SHORT BTC `price_gte` que el motor devuelve `limit_pullback`, `resistance_pullback_zone`, `zone_analysis.available = True` y metrica `pending_zone_analysis`.

Motivo:
- Evitar que el resultado visible parezca un analisis generico de mercado cuando el usuario esta analizando una orden limit/pendiente.
- Hacer visible la diferencia entre entrada a mercado y entrada por activacion de zona.

Riesgo esperado:
- Bajo. Mejora presentacion y trazabilidad visual; no modifica probabilidades ni aprendizaje.

## 2026-06-15 - Correccion etiqueta version motor v0.9

Estado: aplicado tras detectar que el resumen visible seguia mostrando `motor v0.8`.

Cambios realizados:
- El resumen plano del analisis deja de usar texto fijo `v0.8` y usa `ENGINE_VERSION`.
- La metrica `Direccion probable` deja de mostrar una fuente fija `Motor v0.6` y usa `ENGINE_VERSION`.

Motivo:
- Evitar confusion entre la version real del motor y textos antiguos de presentacion.
- Garantizar que nuevos analisis muestren `rules-v0.9-pending-zone-adjusted` cuando usen el motor actual.

Riesgo esperado:
- Bajo. Solo corrige etiquetas/texto de trazabilidad; no modifica probabilidades, pesos ni aprendizaje.

## 2026-06-15 - Fase 9 ordenes pendientes: higiene pre-entrega

Estado: aplicado como preparacion para entrega/push seguro.

Cambios realizados:
- Se actualiza `README.md` para reflejar Supabase, motor v0.9, ordenes pendientes y validacion con tests.
- Se anaden a `.gitignore` archivos locales que no deben subirse: `.codex_backups/`, `ABRIR_APP_LOCAL.md` y `CONTINUIDAD_NUEVO_CHAT.md`.
- Se mantiene `db.py` fuera del alcance de cambios a subir, porque sigue siendo un archivo local/protegido en este proyecto.

Motivo:
- Reducir riesgo de subir archivos auxiliares locales por accidente.
- Dejar comandos de validacion alineados con la suite nueva de ordenes pendientes.
- Preparar el bloque para una revision final y push controlado por archivos.

Riesgo esperado:
- Bajo. Cambios de documentacion e higiene de repositorio; no cambian comportamiento productivo.

Criterio de revision futura:
- Antes del push, stagear solo archivos intencionados y confirmar que `db.py` no entra salvo orden expresa.

## 2026-06-15 - Fase 8 ordenes pendientes: validacion integrada local

Estado: validado en app local contra Supabase.

Comprobaciones realizadas:
- La app local arranca en `http://127.0.0.1:8766/` usando el procedimiento de `ABRIR_APP_LOCAL.md`.
- Startup FastAPI completado sin errores.
- La pagina principal responde HTTP 200.
- `/api/price?symbol=BTCUSDT&record=false` responde HTTP 200 y mantiene el contrato `activated_operations` / `closed_operations`.
- `/api/learning/pending-zone-audit` responde HTTP 401 sin sesion, confirmando que el endpoint queda protegido y no rompe la app.
- La suite `tests.test_pending_zone_analysis` pasa completa.
- Compilacion Python y revision sintactica JS pasan.

Motivo:
- Cerrar el bloque de implementacion de ordenes pendientes con una validacion end-to-end local.
- Verificar que los cambios del motor, aprendizaje, auditoria y documentacion no rompen el arranque real con Supabase.

Riesgo esperado:
- Bajo. Validacion operativa; no cambia comportamiento productivo.

Criterio de revision futura:
- Repetir esta validacion antes del push final y tras crear una orden pendiente real nueva desde la UI.

## 2026-06-15 - Fase 7 ordenes pendientes: contrato tecnico documentado

Estado: aplicado en documentacion tecnica del proyecto.

Cambios realizados:
- Se actualiza `ESPECIFICACION_MOTOR_ANALISIS.md` para reflejar el motor real v0.9.
- Se documenta que el apalancamiento es neutral para la lectura de mercado y no debe condicionar probabilidad ni recomendacion tecnica.
- Se documenta la diferencia entre entrada `market` y `pending`.
- Se documentan los tipos derivados `limit_pullback`, `stop_breakout` y `stop_breakdown`.
- Se documenta `zone_analysis`, `zone_probability_context`, sus limites de ajuste y su interpretacion correcta.
- Se documenta el aprendizaje por zonas pendientes y las categorias internas de `zone_learning`.
- Se actualiza `FUENTES_DATOS_Y_ANALISIS.md` con los datos actuales usados para zonas pendientes y las limitaciones conocidas.

Motivo:
- Evitar que futuras fases o nuevos chats vuelvan a mezclar leverage con calidad de analisis.
- Dejar claro que una orden pendiente no activada no equivale a fallo direccional.
- Dejar trazable que los ajustes de zona v0.9 son prudentes y no deben ampliarse sin muestra suficiente.

Riesgo esperado:
- Bajo. Solo documentacion; no cambia comportamiento productivo.

Criterio de revision futura:
- Actualizar esta especificacion cada vez que se cambien pesos, caps, fuentes de datos o categorias de aprendizaje del motor.

## 2026-06-15 - Fase 6 ordenes pendientes: pruebas de regresion

Estado: aplicado como suite local sin dependencias nuevas.

Cambios realizados:
- Se crea `tests/test_pending_zone_analysis.py` con `unittest` estandar.
- Se cubre una zona `limit_pullback` favorable que debe recibir ajuste positivo pequeno y sin riesgo adicional.
- Se cubre una zona mala/de barrida que debe penalizar probabilidad y sumar riesgo.
- Se cubre una orden lejana que debe aumentar `range/no ejecucion` sin castigar direccion.
- Se valida que una operacion pendiente cerrada en SL con zona advertida se clasifique como `pending_zone_liquidity_sweep` y `reinforce_warned_pending_zone_risk`.
- Se valida que la auditoria agregada agrupe correctamente casos por bucket positivo/negativo de ajuste de zona.

Motivo:
- Proteger las reglas criticas de v0.9 antes de seguir iterando.
- Evitar regresiones donde una orden no activada se interprete como fallo direccional.
- Evitar que una zona mala ganadora/perdedora genere aprendizaje ambiguo sin categoria interna.

Riesgo esperado:
- Bajo. Solo anade pruebas locales y no cambia comportamiento productivo.

Criterio de revision futura:
- Ampliar esta suite cuando se anadan nuevas familias de orden, nuevos datos de microestructura o recalibraciones de `zone_probability_context`.

## 2026-06-15 - Fase 5 ordenes pendientes: auditoria agregada de zonas

Estado: aplicado como endpoint interno de auditoria, sin cambios de probabilidades ni esquema.

Cambios realizados:
- Se crea `/api/learning/pending-zone-audit`.
- El informe lee `learning_evaluations.structured_json` y extrae casos con `analysis_context.zone`.
- Resume operaciones pendientes evaluables por motor `rules-v0.9-pending-zone-adjusted`.
- Agrupa resultados por `entry_order_type`, `entry_zone_type`, `reaction_bias`, `liquidity_sweep_risk`, bucket de ajuste de zona, categoria `zone_learning`, temporalidad y lado.
- Incluye tasa de exito, tasa de activacion, PnL total/promedio, confluencia media y probabilidad media de activacion.
- Mantiene umbral minimo de 30 casos resueltos antes de revisar pesos.

Motivo:
- La fase 4 guarda aprendizaje de zona, pero necesitabamos una forma de auditar si esos datos empiezan a ser estadisticamente utiles.
- Separar activacion de resultado: una orden puede ser buena como zona, mala como ejecucion, o simplemente no activarse.
- Preparar la futura recalibracion de `zone_probability_context` con datos agregados y no con impresiones aisladas.

Riesgo esperado:
- Bajo. Solo lectura y agregacion de datos ya guardados; no cambia operaciones, aprendizaje guardado ni probabilidades.

Criterio de revision futura:
- Usar este informe cuando haya suficientes operaciones pendientes cerradas para decidir si subir, bajar o mantener los caps de ajuste v0.9.
- Revisar primero grupos con al menos 30 casos comparables; ignorar conclusiones con muestras pequenas.

## 2026-06-15 - Fase 4 ordenes pendientes: aprendizaje por zona

Estado: aplicado sin cambios de esquema; se guarda en JSON estructurado y claves internas de comparacion.

Cambios realizados:
- El aprendizaje estructurado guarda `pending_entry_context` con tipo de entrada, condicion, tipo de orden, precio solicitado, activacion y precio/hora de disparo.
- `analysis_context.zone` guarda zona pendiente, confluencia, probabilidad de activacion, sesgo de reaccion, riesgo de barrida, calidad de invalidacion/TP y ajustes v0.9.
- Se crea `zone_learning` para clasificar cada caso como zona favorable reforzada, zona favorable fallida, riesgo de zona confirmado, exito contra advertencia o contexto no concluyente.
- `classify_analysis_verdict` considera advertencias de zona: ajuste negativo, riesgo anadido o barrida alta.
- `classify_failure_type` puede clasificar fallos como `pending_zone_liquidity_sweep`, `pending_zone_risk_confirmed` o `pending_zone_target_path_blocked`.
- `learning_engine.py` incorpora tipo de orden, sesgo de reaccion, riesgo de barrida, bucket de confluencia y bucket de ajuste de zona al filtrado de casos similares.
- Los desgloses agregados de aprendizaje incluyen familias de orden pendiente y buckets de zona.
- El texto interno de patron guardado incorpora orden, zona, reaccion, barrida y ajuste de zona cuando aplica.

Motivo:
- El objetivo no es solo saber si una operacion gano o perdio, sino si el motor evaluo bien la zona que iba a activar la orden.
- Evitar que una orden pendiente ganadora refuerce senales equivocadas si el motor habia advertido mala zona.
- Evitar que una orden pendiente no activada se trate como fallo direccional.
- Preparar muestras comparables para recalibrar `zone_probability_context` con datos reales.

Riesgo esperado:
- Bajo. No cambia probabilidades ni esquema de base de datos; solo mejora aprendizaje, clasificacion y trazabilidad interna.

Criterio de revision futura:
- Cuando haya suficientes operaciones pendientes cerradas, auditar `zone_learning.category` por `entry_order_type`, `reaction_bias`, `liquidity_sweep_risk` y `zone_probability_adjustment_bucket`.
- Revisar especialmente fallos con `reinforce_favorable_pending_zone` y exitos con `investigate_success_against_pending_zone_warning`.

## 2026-06-15 - rules-v0.9-pending-zone-adjusted

Estado: aplicado como primera integracion prudente del analisis de zona en ordenes pendientes.

Base de partida:
- Version anterior: `rules-v0.8-leverage-neutral-analysis`.
- Fase previa: `zone_analysis` descriptivo guardado en resultado y snapshot, sin alterar probabilidades.

Cambios realizados:
- El motor sube a `rules-v0.9-pending-zone-adjusted`.
- Se crea `zone_probability_context` para convertir la calidad de zona pendiente en ajustes pequenos y auditables.
- La probabilidad direccional solo se ajusta en ordenes pendientes y con limites estrictos: maximo `+0.025` y minimo `-0.035`.
- La probabilidad de activacion se separa de la probabilidad de TP: si la orden esta lejos o con activacion incierta, aumenta el escenario `range/no ejecucion` en vez de inflar o castigar directamente el TP.
- El riesgo de zona puede sumar riesgo si hay barrida probable, falsa ruptura, mala invalidacion o barreras antes del TP.
- El snapshot guarda `zone_probability_context` y los componentes `zone_probability_adjustment`, `zone_range_probability_adjustment`, `zone_risk_score_addition`, `zone_confluence_score` y `zone_activation_probability`.

Motivo:
- Las ordenes limit/stop no se comportan igual que una entrada a mercado: primero deben activarse, y despues la zona debe reaccionar.
- Evitar dos errores de aprendizaje: premiar una orden solo porque se activo, o castigar una orden buena simplemente porque nunca llego al precio.
- Empezar a usar la informacion de zonas sin sobreajustar antes de tener muestra suficiente.

Riesgo esperado:
- Moderado-bajo. Cambia probabilidades solo en ordenes pendientes y con caps pequenos.
- Puede necesitar recalibracion cuando existan suficientes operaciones pendientes cerradas y evaluadas.

Criterio de revision futura:
- Auditar por separado ordenes `limit_pullback`, `stop_breakout` y `stop_breakdown`.
- Comparar `zone_probability_adjustment` positivo, neutral y negativo contra TP/SL, MFE/MAE, activacion/no activacion y cierre manual.
- No aumentar los caps hasta tener al menos 30 casos comparables por familia de orden o una evidencia estadistica clara.

## 2026-06-15 - Fase 2 ordenes pendientes: analisis interno de zona

Estado: aplicado como capa descriptiva sin modificar todavia probabilidades finales.

Cambios realizados:
- `TradeProposal` incorpora contexto de entrada: `entry_type`, `trigger_condition` y `entry_order_type`.
- El motor calcula `zone_analysis` para ordenes pendientes y lo guarda en el resultado y en el snapshot.
- `zone_analysis` registra distancia a activacion, unidades de ATR/rango, confluencia de zona, probabilidad estimada de activacion, sesgo de reaccion, riesgo de barrida, calidad de pullback/ruptura, invalidacion y camino al TP.
- Se anade una metrica explicada `pending_zone_analysis` para auditar la lectura sin convertirla todavia en ajuste de probabilidad.
- El endpoint `/api/analyze` pasa al motor si el analisis corresponde a entrada a mercado o a orden pendiente.

Motivo:
- Una orden pendiente no debe evaluarse igual que una entrada a mercado: importa si el precio debe caer/subir hasta una zona, si esa zona es soporte/resistencia defendible, si parece barrida de liquidez o ruptura, y si el TP queda libre o bloqueado por niveles.
- Preparar datos comparables para aprendizaje futuro antes de tocar pesos del motor.

Riesgo esperado:
- Bajo. Es enriquecimiento interno y trazabilidad; no altera `tp_probability`, `sl_probability`, `range_probability`, EV ni decision final.

Criterio de revision futura:
- Tras suficientes ordenes pendientes cerradas, auditar `zone_confluence_score`, `reaction_bias`, `liquidity_sweep_risk`, `target_path_quality` y `activation_probability` frente a activaciones, MFE/MAE, TP, SL y cierres manuales.

## 2026-06-15 - Visualizacion de disparo y activacion de orden pendiente

Estado: aplicado tras verificar una orden pendiente real activada por vela de 1 minuto.

Cambios realizados:
- El grafico muestra el nivel de una orden `PENDING_ENTRY` como `Disparo` en color amarillo.
- Cuando una orden pendiente ya fue activada, el grafico marca el punto `auto_entry` con linea vertical y etiqueta `Activada`.
- El marcador usa el tick de activacion o, si no existe, la hora `triggered_at` mas cercana.

Motivo:
- Hacer auditable visualmente la diferencia entre nivel planificado, activacion real y posterior seguimiento de la operacion.
- Facilitar la revision manual de si la orden pendiente se activo en el punto correcto antes de evaluar TP/SL.

Riesgo esperado:
- Bajo. Solo afecta visualizacion y trazabilidad; no cambia datos de mercado, probabilidades ni aprendizaje.

## 2026-06-15 - Validacion backend del enlace analisis orden pendiente

Estado: aplicado tras probar una orden pendiente real que paso a operacion abierta.

Cambios realizados:
- Al crear una operacion desde un analisis previo, el backend valida que el analisis corresponda al mismo simbolo, direccion y marco temporal.
- Para ordenes pendientes, tambien valida `entry_type`, `trigger_condition`, `entry_order_type` y precio solicitado.
- Se impide enlazar una operacion pendiente a un analisis a mercado, o una condicion de activacion distinta a la analizada.

Motivo:
- Proteger la trazabilidad analisis -> orden -> activacion -> resultado.
- Evitar que el aprendizaje futuro use conclusiones de una operacion con un analisis que no corresponde exactamente al plan ejecutado.

Riesgo esperado:
- Bajo. Endurece validacion de coherencia; no cambia la formula de probabilidad ni la lectura tecnica.

## 2026-06-15 - Trazabilidad de orden pendiente en analisis

Estado: aplicado tras auditar un analisis pre-trade creado como orden pendiente.

Cambios realizados:
- El endpoint de analisis acepta y valida `entry_type` y `trigger_condition`.
- El JSON interno del analisis guarda `entry_order_context` con tipo de entrada, condicion de activacion, tipo de orden derivado y precio solicitado.
- Se mantiene intacto el calculo de probabilidades: la orden pendiente no altera por si sola la probabilidad, pero queda registrada para auditoria y aprendizaje posterior.

Motivo:
- Evitar que un analisis hecho para una orden pendiente quede guardado como si fuera una entrada a mercado.
- Mejorar la trazabilidad entre analisis previo, activacion real y resultado final de la operacion.

Riesgo esperado:
- Bajo. Es enriquecimiento de contexto guardado; no cambia pesos, probabilidades ni decisiones del motor.

## 2026-06-11 - rules-v0.8-leverage-neutral-analysis

Estado de auditoria: cambio aplicado para separar lectura de mercado y gestion monetaria.

Base de partida:
- Version anterior: `rules-v0.7-fibonacci-confluence`.
- Se detecta que el motor estaba penalizando demasiado operaciones por apalancamiento alto, convirtiendo el leverage en una razon para `observar`.

Cambios realizados:
- El apalancamiento deja de restar probabilidad al TP.
- El apalancamiento deja de sumar riesgo al `risk_level`.
- El apalancamiento deja de penalizar la calidad del setup y el score de EV usado para graduar A/B/C/D.
- La recomendacion ya no sugiere reducir leverage como condicion del analisis.
- La tarjeta de apalancamiento queda neutral: informa exposicion/PnL, pero no afecta setup, probabilidad ni decision.
- El aprendizaje deja de clasificar fallos como `excessive_leverage`.

Motivo:
- El mercado no cambia su probabilidad de alcanzar TP o SL por el apalancamiento elegido por el usuario.
- El leverage solo escala ganancia o perdida sobre margen; pertenece a gestion monetaria, no a direccion, confluencia o calidad de la operacion.
- Evitar que el motor sea excesivamente defensivo y termine casi siempre en `observar` por una variable que no altera el movimiento del precio.

Criterio de revision futura:
- Auditar si aparecen mas setups operables A/B/C sin aumentar fallos no anticipados.
- Vigilar por separado riesgo de mercado y exposicion monetaria; no volver a mezclar leverage con probabilidad direccional.

## 2026-06-09 - rules-v0.7-fibonacci-confluence

Estado de auditoria: implementacion inicial pendiente de validacion con operaciones cerradas.

Base de partida:
- Version anterior: `rules-v0.6-audit-calibrated`.
- Baseline v0.6: 68 operaciones cerradas evaluables.
- Se conserva la regla central: el R/R no infla directamente la probabilidad direccional.

Cambios realizados:
- Se anade deteccion automatica de swings por temporalidad usando pivotes objetivos y filtro minimo por ATR/rango.
- Se calculan retrocesos Fibonacci `0.236`, `0.382`, `0.5`, `0.618`, `0.786`.
- Se calculan extensiones `1.272`, `1.618`, `2.0`, `2.618`.
- Se incorpora `fibonacci_context` al resultado y snapshot del analisis.
- Se crea una metrica explicada `fibonacci_confluence`.
- Fibonacci se usa como confluencia de zona, calidad de entrada, calidad de TP/SL y riesgo de ejecucion.
- El ajuste directo sobre probabilidad queda limitado a `-0.02` / `+0.02`.
- El aprendizaje descriptivo empieza a registrar sesgo, zona de entrada y puntuacion Fibonacci dentro del patron guardado.
- Se endurece la validacion backend para impedir analisis u operaciones con SL/TP en el lado incorrecto de la entrada.
- `refresh_learning_evaluations` deja de recalcular historico cerrado ya evaluado; solo crea evaluaciones faltantes y omite cierres manuales todavia en observacion.
- Se corrige la conclusion de aprendizaje para diferenciar operaciones ganadoras respaldadas por el analisis frente a operaciones ganadoras contra advertencias previas (`observar`, setup debil, TP < SL, EV negativa o Fibonacci en alerta).
- Se aplica el mismo criterio a operaciones que alcanzan STOP LOSS: si el motor las apoyaba, se guardan como riesgo no anticipado/subestimado; si ya habia advertencias, refuerzan esas senales de riesgo.
- Se anade una senal interna de aprendizaje en `structured_json` con categoria, interpretacion, criterio `aggregate_only`, minimo de 30 casos comparables y clave de comparacion por activo, lado, horizonte, setup, regimen, EV y Fibonacci.

Motivo:
- Incorporar Fibonacci como sistema de zonas medibles, no como predictor aislado.
- Mejorar la lectura de entrada, invalidacion y objetivos cuando coinciden con estructura tecnica existente.
- Crear trazabilidad para auditar si las zonas Fibonacci aportan valor real por activo, lado y temporalidad.
- Evitar que un TAKE PROFIT refuerce erroneamente todas las condiciones del analisis cuando el propio motor habia recomendado prudencia.
- Evitar que un STOP LOSS recomendado por el motor se interprete como confirmacion de patrones favorables.
- Preparar el aprendizaje para auditorias internas futuras sin necesidad de visualizar estos datos en la app.

Riesgo esperado:
- Posible sobreajuste si se da demasiado peso a Fibonacci antes de tener muestra suficiente.
- Posible ruido en mercados laterales o con swings poco limpios.
- Los pivotes automaticos pueden elegir un impulso distinto al que usaria un analista visual.

Estado pendiente de validacion:
- Auditar tras al menos 30 operaciones cerradas con `rules-v0.7-fibonacci-confluence`.
- Comparar operaciones con `fibonacci_context.bias = favorable` frente a neutral/desfavorable.
- Medir por separado `golden_zone`, retroceso superficial, entrada extendida, LONG/SHORT y temporalidad.

## 2026-06-07 - rules-v0.6-audit-calibrated

Estado de auditoria: aplicada tras auditoria de operaciones cerradas.

Muestra auditada:
- Operaciones cerradas evaluables: 68.
- Acierto global del analisis previo frente al resultado del plan: 77,94%.
- Mejor rendimiento observado: `technical_score` 85,7%, `market_regime` 80,0%, `asset_24h_move` 78,8%, `direction_score` 76,7%.
- Peor rendimiento observado: `risk_reward_ratio` 32,7%, `operation_quality` 33,3%, `cvd_spot` 52,1%, `order_book_imbalance` 57,9%.

Cambios realizados:
- Se sube la version del motor a `rules-v0.6-audit-calibrated`.
- Se anade `ENGINE_AUDIT_REFERENCE` al resultado y al snapshot guardado de cada analisis.
- Se incorpora `market_regime_bias` como ajuste direccional prudente, porque el regimen de mercado fue una de las capas con mejor tasa de acierto.
- Se reduce el impacto directo del `order_book_imbalance` en la probabilidad direccional.
- Se reduce el impacto directo del `cvd_spot` en la probabilidad direccional.
- Se recalibra `operation_quality_score` para que dependa menos del R/R y mas de EV neta y riesgo sobre margen.
- Se mantiene `risk_reward_ratio` fuera de la probabilidad direccional; sigue afectando a EV, break-even y calidad de diseno.

Hipotesis de mejora:
- El motor deberia mejorar especialmente en `intraday_wide`, donde estructura tecnica y regimen ya mostraban mejor comportamiento.
- El motor deberia ser menos vulnerable a falsas lecturas de CVD/order book aislados.
- El motor deberia dejar de sobrevalorar operaciones con buen R/R pero mala direccion probable.

Riesgos vigilados:
- No aumentar demasiado la confianza en tendencias ya agotadas.
- No penalizar en exceso rebotes contra tendencia que puedan funcionar por timing.
- Revisar si los shorts siguen quedando penalizados por capas no tecnicas.

Criterio de revision futura:
- Repetir auditoria tras al menos 30 nuevas operaciones cerradas con `rules-v0.6-audit-calibrated`.
- Comparar por separado: global, LONG, SHORT, `intraday_short`, `intraday_wide`, `short_swing`, BTC y altcoins.
- Si `risk_reward_ratio` o `operation_quality_score` siguen por debajo del 50%, mantenerlos fuera de la probabilidad direccional y usarlos solo como EV/diseno.

## Baseline Anterior - rules-v0.5-technical-ratings

Estado de auditoria: baseline comparativo.

Resumen:
- Funcionaba bien en estructura tecnica y regimen.
- Mostraba debilidad al interpretar R/R como parte de la calidad general.
- CVD y order book eran utiles como contexto, pero insuficientes como senales aisladas.
- La decision final era mas fiable en LONG que en SHORT.
