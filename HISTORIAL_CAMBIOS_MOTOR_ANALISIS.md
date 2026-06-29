# Historial de Cambios del Motor de Analisis

Este archivo registra cada cambio relevante del motor de analisis para poder auditar si mejora o empeora con operaciones reales posteriores.

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
