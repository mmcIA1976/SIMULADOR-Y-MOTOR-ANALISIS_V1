# Motor de analisis: reglas, fuentes y validacion

Version documentada: `rules-v0.6-timeframe-weighted`

Este documento fija la base de la Fase 1 del motor de analisis. Su objetivo es dejar claro que datos usa el sistema, que regla aplica, de donde nace la idea y que parte sigue siendo una hipotesis pendiente de validar con operaciones reales.

La regla central del proyecto es:

> El motor no debe tratar sus pesos como verdades. Debe tratarlos como hipotesis auditables que se validan con historico, resultados y comportamiento del usuario.

## 1. Principios del motor

### Separacion de conceptos

El motor separa cuatro salidas:

- Probabilidad direccional: estima si la operacion tiene mayor probabilidad de avanzar hacia TP que hacia SL.
- Esperanza matematica: calcula si el plan compensa economicamente considerando distancia a TP/SL, apalancamiento, costes estimados, spread, slippage y funding.
- Riesgo de ejecucion: mide si la operacion puede fallar por volatilidad, stop demasiado cercano, liquidez, apalancamiento, contradicciones o zona tecnica.
- Confianza del analisis: mide la alineacion entre capas. Una operacion puede tener buena esperanza matematica y baja confianza si los datos se contradicen.

### Regla critica sobre R/R

El ratio riesgo/beneficio no aumenta directamente la probabilidad de TP.

Uso correcto:

- El R/R mejora o empeora la esperanza matematica.
- El R/R ayuda a evaluar calidad del diseno de la operacion.
- El R/R no debe inflar artificialmente la probabilidad direccional.

Estado actual: aplicado correctamente en `analysis_engine.py`. El R/R entra en `calculate_expected_value()`, `operation_quality_score` y `grade_from_scores()`, no como suma directa principal de TP.

## 2. Fuentes de datos actuales

| Dato | Fuente actual | Uso en el motor | Estado |
| --- | --- | --- | --- |
| Precio spot | Binance Spot ticker | Entrada, PnL, cierre TP/SL, snapshot de analisis | Activo |
| Velas 5m, 15m, 1h, 4h, 1d, 1w | Binance Spot klines | EMAs, RSI, ATR, volumen, rango, niveles | Activo |
| Order book top 20 | Binance Spot depth | Imbalance bid/ask y spread | Activo, mejorable |
| Trades agregados spot | Binance Spot aggTrades | CVD aproximado y agresividad compradora/vendedora | Activo, mejorable |
| Ticker 24h | Binance Spot 24hr | Cambio 24h, volumen, maximo/minimo 24h | Activo |
| Funding | Binance USD-M Futures premiumIndex/funding history | Coste/saturacion de posicionamiento | Activo |
| Open Interest | Binance USD-M Futures open interest | Confirmacion o debilidad del movimiento | Activo |
| Long/short ratio | Binance USD-M Futures global long/short | Saturacion de posicionamiento | Activo |
| Taker buy/sell futures | Binance USD-M Futures taker long/short ratio | Flujo agresivo de futuros | Activo |
| Mercado global crypto | CoinGecko global | Dominancia BTC/ETH y contexto general | Activo |
| Amplitud top crypto | CoinGecko top markets | Si el mercado amplio acompana o contradice | Activo |
| Fear & Greed | Alternative.me | Riesgo de sentimiento extremo | Activo |

## 3. Marcos temporales

El motor cambia pesos segun el marco temporal seleccionado antes del analisis.

| Marco | Duracion | Timeframes principales | Confirmacion | Microestructura | Derivados | Macro/contexto |
| --- | --- | --- | --- | --- | --- | --- |
| Intradia corto | 30 min-4 h | 5m, 15m | 1h | Peso alto | Medio | Bajo |
| Intradia amplio | 4-24 h | 15m, 1h | 4h | Medio | Alto | Medio |
| Swing corto | 1-7 dias | 4h, 1d | 1w | Bajo | Alto | Alto |

Pesos actuales:

| Marco | Pesos de tendencia | Micro | Derivados | Macro | Penalizacion HTF | Funding |
| --- | --- | --- | --- | --- | --- | --- |
| Intradia corto | 5m 1.25, 15m 1.35, 1h 1.0, 4h 0.45, 1d 0.15 | 1.0 | 0.85 | 0.15 | 0.6 | 0.35 |
| Intradia amplio | 5m 0.35, 15m 1.1, 1h 1.35, 4h 1.0, 1d 0.35 | 0.55 | 1.0 | 0.35 | 1.0 | 0.75 |
| Swing corto | 5m 0.1, 15m 0.2, 1h 0.75, 4h 1.5, 1d 1.6 | 0.2 | 1.1 | 0.85 | 1.35 | 1.25 |

Fuente conceptual: estructura multi-timeframe usada en analisis tecnico y gestion temporal de operaciones.

Estado de pesos: heuristica propia. Deben validarse con historico por marco temporal.

## 4. Probabilidad direccional

Formula base:

```text
TP = 0.50
  + tendencia
  + rating tecnico
  + precio vs entrada
  + volumen
  + order book
  + momentum RSI
  + taker futures
  + CVD spot
  + open interest
  + amplitud crypto
  - volatilidad/stop
  - apalancamiento
  - liquidez/spread
  - extension contra EMA
  - funding
  - funding relativo
  - saturacion long/short
  - zona tecnica
  - sentimiento extremo
  - timeframe superior contrario
  - timing tecnico
  - barrera tecnica
  - contexto OI/precio
  - contradicciones compuestas
```

Limites actuales:

- TP minimo: 26%.
- TP maximo: 74%.
- Rango/sin resolver: 6%, 8%, 10% o 12% segun regimen y contradicciones.
- SL: resto hasta 100%, con minimo de 5%.

Fuente conceptual:

- Gestion de incertidumbre y evitacion de falsa precision.
- Separacion entre probabilidad y esperanza matematica.

Estado de la formula:

- Conceptualmente correcta.
- Pesos exactos son heuristica propia.
- Requiere calibracion con historico.

## 5. Reglas actuales por senal

### Tendencia por EMAs

Dato usado:

- EMA 9, EMA 21, EMA 50 por timeframe.
- Clasificacion: `bullish`, `bearish`, `mixed`.

Regla:

- Si las EMAs acompanan la direccion propuesta, suma.
- Si contradicen, resta.
- El peso depende del marco temporal elegido.

Umbrales actuales:

- Normalizado >= 0.55: +0.10.
- Normalizado >= 0.20: +0.05.
- Normalizado <= -0.55: -0.09.
- Normalizado <= -0.20: -0.05.

Fuente conceptual:

- Analisis tecnico de tendencia y medias moviles.

Estado:

- Concepto respaldado.
- Pesos y umbrales: heuristica propia.

Validacion futura:

- Medir acierto por combinaciones de EMAs y marco temporal.
- Separar operaciones a favor de 4h/1d frente a rebotes contra tendencia.

### Rating tecnico compuesto

Dato usado:

- EMA stack.
- Distancia del precio a EMA 21.
- RSI 14.
- Barreras tecnicas de soporte/resistencia.

Regla:

- Cada timeframe recibe score entre -1 y +1.
- Se pondera por el marco temporal.
- Genera `direction_bias`, penalizacion de timing y penalizacion de barrera.

Umbrales actuales:

- EMA bullish: +0.55.
- EMA bearish: -0.55.
- Precio sobre EMA21 > 0.08%: +0.25.
- Precio bajo EMA21 < -0.08%: -0.25.
- RSI 45-65: +0.20.
- RSI > 75: -0.25.
- RSI < 25: +0.10.
- RSI 35-45: +0.05.

Fuente conceptual:

- Momentum, tendencia, sobrecompra/sobreventa y entrada tardia.

Estado:

- Concepto respaldado.
- Pesos exactos: heuristica propia.

Validacion futura:

- Comprobar si RSI bajo favorece long en rebotes o si solo anticipa continuacion bajista segun regimen.
- Comprobar si precio extendido contra EMA21 empeora entradas.

### RSI momentum

Dato usado:

- RSI 14 del timeframe de momentum del marco elegido.

Regla actual:

- Long:
  - RSI > 72: -0.025 * peso micro.
  - RSI entre 45 y 62: +0.020 * peso micro.
- Short:
  - RSI < 28: -0.025 * peso micro.
  - RSI entre 38 y 55: +0.020 * peso micro.

Fuente conceptual:

- RSI como medida de velocidad del movimiento y riesgo de entrada tardia.

Estado:

- Concepto respaldado.
- Rangos exactos: heuristica propia.

Validacion futura:

- Medir por temporalidad si RSI extremo funciona como agotamiento o continuacion.

### ATR, rango y stop dentro del ruido

Dato usado:

- ATR 14.
- Rango reciente.
- Distancia entrada-stop.

Regla:

- Penaliza si el stop queda demasiado cerca frente al movimiento normal reciente.

Umbral actual:

```text
riesgo < max(rango_reciente, ATR) * 0.35
```

Penalizacion:

- Probabilidad: -0.07.
- Riesgo: +0.20.

Fuente conceptual:

- ATR como medida de volatilidad y ruido normal del mercado.

Estado:

- Concepto respaldado.
- Factor 0.35: heuristica propia.

Validacion futura:

- Medir si stops por debajo de 0.35 ATR/rango son barridos mas frecuentemente.

### Volumen relativo

Dato usado:

- Volumen actual frente a media de 20 velas del timeframe seleccionado.

Regla:

- Volumen alto confirma movimiento.
- Volumen bajo resta fiabilidad.

Umbrales actuales:

- Volumen ratio > 1.25: +0.025.
- Volumen ratio < 0.65: -0.015.

Fuente conceptual:

- Confirmacion por volumen.

Estado:

- Concepto respaldado.
- Umbrales: heuristica propia.

Validacion futura:

- Separar volumen de ruptura, volumen de absorcion y volumen de barrido.

### Order book

Dato usado:

- Bid notional top 20.
- Ask notional top 20.
- Imbalance.
- Spread.

Regla:

- Long: imbalance positivo favorece; negativo penaliza.
- Short: imbalance negativo favorece; positivo penaliza.
- Spread elevado penaliza liquidez.

Umbrales actuales:

- Imbalance > 0.12: +0.025 * peso micro para long.
- Imbalance < -0.12: +0.025 * peso micro para short.
- Spread > 0.04%: penalizacion de liquidez.

Fuente conceptual:

- Microestructura y presion de liquidez.

Estado:

- Concepto moderno y relevante.
- Implementacion actual limitada porque usa top 20, no bandas ni persistencia.

Validacion futura:

- Sustituir o complementar top 20 por bandas +-0.1%, +-0.25%, +-0.5%.
- Medir liquidez entre entrada-SL y entrada-TP.
- Medir persistencia/cancelacion.

### CVD spot

Dato usado:

- Binance aggTrades, 500 trades.
- Compra agresiva aproximada cuando buyer maker es falso.
- Venta agresiva aproximada cuando buyer maker es verdadero.

Regla:

- CVD a favor suma.
- CVD contra direccion resta.

Umbral actual:

- CVD ratio > 0.12: favorece long.
- CVD ratio < -0.12: favorece short.

Fuente conceptual:

- Order flow y agresividad compradora/vendedora.

Estado:

- Concepto relevante.
- Implementacion actual mejorable porque no compara CVD contra reaccion del precio.

Validacion futura:

- Crear patron `cvd_favorable_precio_acompana`.
- Crear patron `cvd_favorable_precio_no_acompana` como posible absorcion.
- Guardar ventana temporal real.

### Taker buy/sell futures

Dato usado:

- Binance USD-M Futures taker buy/sell ratio por 5m, 1h o 1d segun horizonte.

Regla:

- Ratio > 1.12 favorece long.
- Ratio < 0.88 favorece short.
- Lo contrario penaliza.

Peso actual:

- +0.02 o -0.02 multiplicado por peso de derivados.

Fuente conceptual:

- Flujo agresivo de futuros.

Estado:

- Concepto relevante.
- Umbrales: heuristica propia.

Validacion futura:

- Medir si futuros contra spot aumentan fallos.
- Crear patron `spot_fuerte_futuros_debiles`.

### Open Interest

Dato usado:

- OI actual.
- Cambio de OI por periodo del horizonte.
- Cambio de precio 24h.

Reglas:

- Si OI crece y el precio va en la direccion de la operacion, suma.
- Si OI crece contra la direccion, resta.
- Si precio sube pero OI cae en long, penaliza por posible short covering.
- Si precio cae pero OI cae en short, penaliza por posible cierre de largos, no nueva conviccion.

Umbrales actuales:

- OI change < 0.2%: neutral.
- OI context penalty si precio cambia > 0.5% y OI < -0.2%.

Fuente conceptual:

- Derivados, posicionamiento y confirmacion de movimiento.

Estado:

- Concepto relevante.
- Umbrales: heuristica propia.

Validacion futura:

- Cruzar OI con precio, funding y taker flow.

### Funding

Dato usado:

- Funding actual.
- Media reciente de 8 registros.

Reglas:

- Long con funding positivo elevado penaliza.
- Short con funding negativo elevado penaliza.
- Funding actual muy superior a su media penaliza saturacion.

Umbrales actuales:

- Funding absoluto > 0.03% en contra: penalizacion 0.025 * peso funding.
- Funding / media >= 1.8 en contra: penalizacion 0.01 * peso funding.

Fuente conceptual:

- Coste de mantener posicion y saturacion de posicionamiento en perpetuos.

Estado:

- Concepto respaldado.
- Umbrales: heuristica propia.

Validacion futura:

- Medir si funding extremo anticipa barridos o continuacion.

### Long/short ratio

Dato usado:

- Global long/short ratio por horizonte.

Regla:

- Long con ratio > 2.0 penaliza saturacion.
- Short con ratio < 0.5 penaliza saturacion.

Fuente conceptual:

- Posicionamiento de cuentas y riesgo de crowding.

Estado:

- Concepto relevante.
- Umbrales: heuristica propia.

Validacion futura:

- Medir si extremos producen squeezes o continuacion.

### Soporte/resistencia

Dato usado:

- Maximos/minimos recientes del timeframe de niveles.
- Cluster simple de los niveles cercanos.

Regla:

- Long penalizado si resistencia cercana limita el recorrido al TP.
- Short penalizado si soporte cercano limita el recorrido al TP.

Umbrales actuales:

- Penalizacion si barrera < max(0.25%, reward * 0.35).
- Penalizacion tecnica adicional si barrera < reward * 0.55 o reward * 0.85.

Fuente conceptual:

- Soporte/resistencia y gestion de zonas.

Estado:

- Concepto respaldado.
- Deteccion actual simple.

Validacion futura:

- Mejorar con volumen por zona, max/min 24h, y zonas de rechazo.

### Amplitud crypto

Dato usado:

- Top 100 de CoinGecko.
- Porcentaje de activos que suben.
- Mediana de cambio 24h.

Regla:

- Long suma si >= 58% suben y mediana positiva.
- Short suma si <= 42% suben y mediana negativa.

Fuente conceptual:

- Breadth de mercado, confirmacion por participacion amplia.

Estado:

- Concepto razonable.
- Umbrales: heuristica propia.

Validacion futura:

- Separar top 100, top 300 y sector/activo.

### Fear & Greed

Dato usado:

- Alternative.me Fear & Greed.

Regla:

- Long penalizado si codicia extrema >= 75.
- Short penalizado si miedo extremo <= 25.

Fuente conceptual:

- Sentimiento extremo como riesgo de entrada tardia o contrarian.

Estado:

- Concepto util como contexto.
- Regla demasiado simple.

Validacion futura:

- Interpretar segun regimen:
  - miedo extremo + soporte + CVD positivo puede favorecer rebote;
  - miedo extremo + futuros vendedores puede penalizar long.

### Apalancamiento

Dato usado:

- Leverage elegido por usuario.

Regla:

- Penaliza por encima de x5.
- Riesgo sube fuertemente en x8-x10.

Formula actual:

- Penalizacion probabilidad: `max(0, leverage - 5) * 0.018`.
- Riesgo: +0.25 si leverage >= 8; +0.08 si leverage >= 5.
- Recomendacion: si riesgo medio-alto o superior, sugerir maximo x5.

Fuente conceptual:

- Menor margen de error y mayor probabilidad de barrido operativo.

Estado:

- Concepto respaldado.
- Penalizacion exacta: heuristica propia.

Validacion futura:

- Medir PnL por leverage y distancia SL/ATR.

## 6. Patrones compuestos actuales

El motor ya penaliza contradicciones acumuladas:

- CVD y taker futures opuestos.
- OI/precio sospechoso.
- Zona tecnica cercana.
- Timeframe superior contrario.

Penalizacion:

- 2 contradicciones: -0.018.
- 3 contradicciones: -0.032.
- 4 o mas contradicciones: -0.045.

Estado:

- Buena base.
- Falta guardar etiquetas explicitas para aprendizaje.

Patrones que deben incorporarse en fases posteriores:

- `spot_fuerte_futuros_debiles`.
- `cvd_favorable_precio_no_acompana`.
- `rebote_contra_4h`.
- `entrada_cerca_resistencia`.
- `stop_dentro_ruido_atr`.
- `funding_saturado`.
- `breakout_con_flujo`.
- `posible_absorcion`.
- `rango_sin_resolucion`.

## 7. Esperanza matematica

Formula actual:

```text
notional = margen * apalancamiento
ganancia_bruta = notional * distancia_TP_pct
perdida_bruta = notional * distancia_SL_pct
coste = notional * (comision_round_trip + slippage_round_trip) + funding
ganancia_neta = ganancia_bruta - coste
perdida_neta = perdida_bruta + coste
EV = TP_prob * ganancia_neta - SL_prob * perdida_neta - rango_prob * coste
```

Costes actuales:

- Comision round trip estimada: 0.0008.
- Slippage minimo: 0.0002.
- Slippage por spread: max(spread_pct / 100, 0.0002).
- Funding: notional * abs(funding_rate_pct) / 100.

Estado:

- Conceptualmente correcto.
- Costes deben ajustarse por mercado y tipo de orden cuando implementemos ordenes.

## 8. Riesgo, setup y decision

### Riesgo

Suma penalizaciones por:

- Apalancamiento.
- Stop dentro del ruido.
- R/R bajo.
- Rango reciente alto.
- Spread alto.
- Extension contra EMA21.
- Funding.
- Crowding.
- Zona tecnica.
- Sentimiento.
- Timeframe superior contrario.
- Timing tecnico.
- Barrera tecnica.
- Contradicciones.

Clasificacion:

- >= 0.42: alto.
- >= 0.24: medio-alto.
- >= 0.12: medio.
- inferior: bajo.

Estado:

- Estructura correcta.
- Pesos pendientes de validacion.

### Setup

Clasificacion actual:

- A: TP >= 62%, riesgo < 0.20 y EV score >= 58.
- B: TP >= 52%, riesgo < 0.36 y EV score >= 50.
- C: TP >= 44% y EV score >= 42.
- D: resto.

Estado:

- Correcto para comunicacion.
- Debe calibrarse con historico.

### Decision

Regla:

- EV negativa: observar.
- Setup A/B + riesgo no alto + confianza alta/media: simular.
- Setup B/C + riesgo no alto: simular con tamano prudente.
- Resto: observar.

Estado:

- Prudente y coherente.

## 9. Aprendizaje actual

Motor de aprendizaje: `learning-descriptive-v0.2`.

Reglas:

- Menos de 30 casos similares: no modificar probabilidad.
- 30 casos o mas: calcular sugerencia.
- 100 casos o mas: senal mas fuerte.
- Ajuste maximo teorico: +-0.06.
- Ajuste automatico actual: 0. El motor no modifica pesos automaticamente.

Casos similares filtran por:

- Usuario.
- Simbolo.
- Direccion.
- Marco temporal.
- Apalancamiento.
- Nivel de riesgo.
- Etiqueta tecnica.
- Periodo de derivados.
- Timeframe de niveles.
- Regimen de mercado.

Estado:

- Prudente y correcto.
- Todavia falta enriquecer conclusiones de cierre con MFE, MAE, tiempo hasta TP/SL y calidad de gestion.

## 10. Debilidades actuales

1. Pesos no calibrados historicamente.
2. Order book limitado a top 20, sin bandas ni persistencia.
3. CVD sin comparar suficientemente contra reaccion del precio.
4. Deteccion de soportes/resistencias simple.
5. Fear & Greed demasiado lineal.
6. Amplitud crypto solo top 100, sin sector ni profundidad.
7. No hay todavia MFE/MAE completo en aprendizaje.
8. No hay validacion automatica de si el analisis acerto direccion pero fallo gestion.
9. No hay documento de cambios de pesos/reglas por version.
10. No hay backtesting estructurado sobre historico largo.

## 11. Linea correcta de crecimiento

Prioridad 1:

- Mantener el motor explicable.
- Guardar cada dato usado.
- Guardar cada razon aplicada.
- Guardar resultado y comportamiento posterior.

Prioridad 2:

- Mejorar microestructura:
  - order book por bandas;
  - CVD + precio;
  - futuros + OI + funding como patron compuesto.

Prioridad 3:

- Aprendizaje descriptivo:
  - no modificar pesos con pocos casos;
  - generar informes por patron;
  - proponer ajustes, no aplicarlos automaticamente.

Prioridad 4:

- Validacion cuantitativa:
  - tasa de TP por patron;
  - EV real por patron;
  - MFE/MAE;
- tiempo medio hasta resolucion;
- diferencia entre operaciones a favor y contra recomendacion.

## 12. Fase 2 implementada: captura ampliada de datos

Desde `feature-capture-v0.1`, cada analisis previo guarda un bloque adicional en `snapshot_json`:

- `feature_audit`: auditoria estructurada de datos usados.
- `pattern_tags`: etiquetas de patrones detectados.
- `data_quality`: cobertura de datos disponibles y datos ausentes.
- `selected_market_state`: estado de mercado seleccionado para el marco temporal.
- `score_components`: suma/resta exacta que afecto a la probabilidad.

### Objetivo

No cambia la decision del motor. Solo mejora la memoria tecnica para que, al cerrar operaciones, podamos analizar con precision que condiciones estaban presentes antes de abrir.

### Datos capturados para aprendizaje

| Bloque | Contenido | Utilidad futura |
| --- | --- | --- |
| `proposal` | Activo, direccion, entrada, margen, apalancamiento, SL, TP, horizonte | Reconstruir el plan inicial |
| `time_horizon_profile` | Marco temporal, timeframes principales, confirmacion, periodo de derivados | Comparar resultados por horizonte |
| `data_quality` | Fuentes disponibles, fuentes ausentes, cobertura porcentual | No entrenar conclusiones con datos incompletos sin saberlo |
| `momentum` | RSI, distancia a EMA21, EMA stack del timeframe relevante | Validar si momentum favorecia o perjudicaba |
| `volatility` | ATR, rango reciente, posicion en rango | Validar stops dentro del ruido y volatilidad |
| `volume` | Volumen relativo y taker buy ratio spot | Validar confirmacion por volumen |
| `levels` | Soporte/resistencia cercana y distancias | Validar si zonas tecnicas frenaron el trade |
| `order_book` | Imbalance, spread, bid/ask notional top20 | Validar utilidad real del order book actual |
| `spot_flow` | CVD, buy/sell ratio, muestra de trades | Validar flujo spot y posible absorcion |
| `derivatives` | Funding, OI, long/short, taker futures por periodo | Validar confirmacion o contradiccion en derivados |
| `context` | Fear & Greed, dominancia BTC, amplitud crypto | Validar contexto global |
| `analysis_outputs` | Regimen, score tecnico, scores por capas, EV y tags | Agrupar operaciones por patron |

### Etiquetas de patron actuales

- `regime:*`
- `technical:*`
- `spot_favorable_futures_against`
- `spot_against_futures_favorable`
- `cvd_supports_plan`
- `cvd_against_plan`
- `futures_taker_supports_plan`
- `futures_taker_against_plan`
- `higher_timeframe_against`
- `technical_barrier_near`
- `open_interest_price_warning`
- `funding_saturation_warning`
- `mixed_signals_contradiction`
- `stop_inside_recent_noise`
- `asymmetric_reward_plan`
- `high_leverage`
- `medium_leverage`
- `order_book_supports_long`
- `order_book_supports_short`
- `order_book_against_plan`

### Uso en aprendizaje

Cuando una operacion cerrada genera `learning_evaluations.structured_json`, ahora tambien incorpora:

- version del esquema de captura;
- fecha UTC del analisis;
- cobertura de datos;
- datos ausentes;
- patrones detectados;
- estado de mercado seleccionado;
- componentes exactos del score.

Esto permite consultar en el futuro:

- que patrones ganaron o perdieron mas;
- si los fallos venian de datos incompletos;
- si el CVD aporto valor real;
- si el order book actual predice algo o genera ruido;
- si las contradicciones spot/futuros realmente empeoran resultados;
- si cada temporalidad necesita pesos distintos.

## 13. Fase 3 iniciada: microestructura de order book

Desde esta fase el motor empieza a tratar el order book con mas profundidad, sin cambiar todavia las reglas principales de probabilidad.

### Cambios implementados

- La consulta de `depth` de Binance Spot pasa de 20 a 100 niveles.
- Se mantiene el imbalance top 20 para compatibilidad con la logica actual.
- Se anaden bandas de liquidez:
  - `0.10pct`
  - `0.25pct`
  - `0.50pct`
- Cada banda guarda:
  - notional bid;
  - notional ask;
  - imbalance;
  - numero de niveles bid;
  - numero de niveles ask.
- Se guarda un perfil de liquidez del plan:
  - liquidez en el camino hacia el stop;
  - liquidez en el camino hacia el take profit;
  - niveles disponibles en cada camino;
  - ratio target/stop;
  - camino dominante.

### Nuevos patrones posibles

- `liquidity_heavier_toward_target`
- `liquidity_heavier_toward_stop`
- `cvd_price_confirmation`
- `cvd_price_absorption_warning`
- `cvd_price_against_plan`
- `price_moves_without_cvd_confirmation`
- `futures_oi_confirmation`
- `futures_oi_contradiction`
- `futures_flow_without_oi_confirmation`
- `futures_taker_against_without_oi_confirmation`
- `oi_price_divergence_warning`
- `derivatives_funding_saturation`
- `derivatives_crowding_risk`
- `derivatives_oi_price_warning`

### Objetivo

El motor deja de mirar solo si hay mas bids o asks cerca. Ahora tambien puede registrar si la liquidez relevante esta antes del stop o antes del take profit.

Ejemplo:

```text
SHORT con liquidez pesada entre entrada y TP:
puede significar zona de absorcion/soporte hacia el objetivo.

LONG con mucha liquidez entre entrada y SL:
puede significar soporte real o zona atractiva para barrido.
```

De momento estos datos se guardan para aprendizaje. No se usan aun para alterar probabilidades de forma agresiva.

### Pendiente dentro de Fase 3

- Persistencia del order book entre consultas.
- Deteccion de absorcion.
- Validacion historica de si la liquidez en cada camino ayuda o confunde.

### CVD con reaccion del precio

Desde `cvd-price-v0.1`, el motor compara el CVD spot reciente con el movimiento de precio dentro de la misma muestra de `aggTrades`.

Datos guardados:

- numero de trades de la muestra;
- primer precio;
- ultimo precio;
- cambio porcentual de precio en la muestra;
- CVD ratio;
- direccion del flujo;
- direccion del precio;
- patron detectado.

Lecturas:

| Patron | Interpretacion |
| --- | --- |
| `cvd_price_confirmation` | El CVD y el precio acompanan la direccion propuesta |
| `cvd_price_absorption_warning` | El CVD acompana, pero el precio no avanza o va en contra; posible absorcion |
| `cvd_price_against_plan` | El flujo agresivo spot va contra la operacion |
| `price_moves_without_cvd_confirmation` | El precio acompana, pero el CVD no confirma con fuerza |

De momento estas etiquetas se guardan para aprendizaje. No modifican automaticamente la probabilidad.

### Derivados compuestos

Desde `derivatives-composite-v0.1`, el motor cruza:

- taker buy/sell futures;
- cambio de Open Interest;
- cambio de precio 24h;
- funding actual;
- funding frente a media reciente;
- global long/short ratio.

Lecturas:

| Patron | Interpretacion |
| --- | --- |
| `futures_oi_confirmation` | El flujo taker de futuros y el OI acompanan la direccion propuesta |
| `futures_oi_contradiction` | El taker futures va contra la operacion con OI creciente; posible presion nueva contra el plan |
| `futures_flow_without_oi_confirmation` | El flujo taker acompana, pero el OI no confirma nueva exposicion |
| `futures_taker_against_without_oi_confirmation` | Futuros van contra el plan, pero sin confirmacion fuerte de OI |
| `oi_price_divergence_warning` | Precio y OI sugieren posible cierre de posiciones, no conviccion nueva |
| `derivatives_funding_saturation` | Funding actual o relativo sugiere saturacion |
| `derivatives_crowding_risk` | Long/short ratio sugiere exceso de posicionamiento |
| `derivatives_oi_price_warning` | Contexto precio/OI alerta de movimiento fragil |

Tambien se guarda en `feature_audit.selected_market_state.derivatives.derivatives_profile`.

De momento no modifica automaticamente las probabilidades. Su funcion es alimentar aprendizaje y auditoria.

## 14. Aprendizaje por patrones de alta senal

Desde `learning-descriptive-v0.3`, el motor de aprendizaje no compara operaciones solo por activo, direccion, marco temporal, riesgo y regimen. Tambien incorpora las etiquetas `pattern_tags` generadas durante el analisis.

La regla es prudente:

- si la operacion actual y una operacion historica tienen patrones de alta senal, deben compartir al menos uno para ser consideradas similares;
- si no hay patrones de alta senal suficientes, se mantiene la comparacion anterior para no dejar el aprendizaje sin muestra;
- no se modifican probabilidades automaticamente hasta reunir al menos 30 casos resueltos similares.

Patrones de alta senal iniciales:

- confirmacion o contradiccion CVD/precio;
- absorcion spot;
- confirmacion o contradiccion futuros/OI;
- crowding, funding saturado y divergencias OI/precio;
- liquidez mas pesada hacia objetivo o stop;
- contradicciones spot/futuros;
- tendencia superior contra la operacion;
- stop dentro del ruido reciente.

Impacto:

- mejora la calidad de los casos comparables;
- permite detectar que patrones se repiten en operaciones ganadoras o perdedoras;
- reduce el riesgo de mezclar operaciones parecidas solo en superficie pero distintas en microestructura;
- mantiene el aprendizaje en modo descriptivo hasta tener muestra suficiente.

## 15. Calibracion prudente del motor

Desde `learning-calibration-v0.4`, el aprendizaje puede afectar al analisis, pero solo bajo reglas estrictas:

- se necesitan al menos 30 operaciones resueltas similares;
- las operaciones similares deben pasar por el filtro de activo, direccion, temporalidad, riesgo, regimen y patrones de alta senal;
- el ajuste maximo permitido sobre TP es de 6 puntos porcentuales;
- el ajuste se escala por tamano de muestra: 30 casos pesan poco, 100 casos permiten senal mas fuerte;
- si el ajuste sugerido es menor de 0.5 puntos porcentuales, no se aplica;
- si se aplica ajuste, se recalculan probabilidad TP/SL, rangos, esperanza matematica, direction score, expected value score, setup y decision.

Formula inicial:

```text
observed_success_rate = plan_successes / (plan_successes + plan_failures)
raw_adjustment = (observed_success_rate - 0.50) * 0.12
confidence_scale = min(1, total_resolved_cases / 100)
tp_adjustment = clamp(raw_adjustment * confidence_scale, -0.06, +0.06)
```

Interpretacion:

- si casos similares ganan mas de lo esperado, el motor puede subir TP de forma limitada;
- si casos similares fallan mas de lo esperado, el motor puede bajar TP de forma limitada;
- el sistema no cambia pesos internos de indicadores todavia;
- el ajuste queda registrado en `learning_adjustment` con modo, delta aplicado, delta sugerido y desglose de patrones.

Esta fase mejora el motor porque empieza a convertir resultados reales en calibracion probabilistica, pero evita sobreajuste temprano.

## 16. Triple Barrier como etiqueta central

Desde `triple-barrier-v0.1`, cada evaluacion de aprendizaje guarda una etiqueta formal del resultado del plan:

- `tp_first`: el precio toca TAKE PROFIT antes que STOP LOSS.
- `sl_first`: el precio toca STOP LOSS antes que TAKE PROFIT.
- `expired`: no toca ninguna barrera antes del tiempo maximo del marco temporal.
- `manual_before_resolution`: el usuario cierra antes de que el sistema pueda resolver la barrera.
- `unresolved`: no hay datos suficientes para resolver.

La barrera vertical se toma del marco temporal:

| Marco temporal | Barrera vertical |
| --- | --- |
| Intradia corto | 240 minutos |
| Intradia amplio | 1440 minutos |
| Swing corto | 10080 minutos |

Impacto en el objetivo del proyecto:

- el aprendizaje deja de depender solo de si una operacion termino con ganancia o perdida;
- el resultado queda alineado con la pregunta real: que ocurre primero, TP, SL o expiracion;
- permite analizar si el problema fue direccion, diseno de TP/SL, horizonte temporal o decision manual;
- prepara el futuro calculo directo de `P(TP primero)`, `P(SL primero)` y `P(expiracion)`.

En esta version no se reescribe el historico ni se modifica la probabilidad inicial. La etiqueta se guarda dentro de `learning_evaluations.structured_json.triple_barrier`.

Desde el paso siguiente, el aprendizaje usa esta etiqueta como fuente primaria para clasificar el resultado del plan:

| Triple Barrier | Resultado de aprendizaje |
| --- | --- |
| `tp_first` | `plan_success` |
| `sl_first` | `plan_failure` |
| `expired` | `plan_expired` |
| `manual_before_resolution` | `manual_before_resolution` |
| `unresolved` | `plan_unresolved` |

Esto evita confundir una operacion sin resolucion temporal con una operacion realmente fallida o ganadora. Las expiradas se registran por separado y no entran en el calculo de aciertos/fallos hasta que definamos una regla especifica de EV o coste de oportunidad.

### 16.1. Resultado posterior al horizonte

La barrera temporal es analitica, no operativa. El sistema no cierra una operacion real o simulada solo porque expire el horizonte previsto; el usuario mantiene el control del cierre.

Desde `post-horizon-v0.1`, si el plan no toca TP ni SL dentro del horizonte elegido, el aprendizaje guarda que ocurre despues:

| Resultado posterior | Significado |
| --- | --- |
| `tp_after_horizon` | No llego a TP en el plazo previsto, pero lo alcanzo despues. |
| `sl_after_horizon` | No llego a SL en el plazo previsto, pero lo alcanzo despues. |
| `no_barrier_after_horizon` | No toca TP ni SL despues con los datos disponibles. |
| `not_available` | No hay fecha de expiracion calculable. |

Este dato separa dos problemas distintos:

- lectura direccional: si el precio finalmente fue hacia el objetivo;
- timing operativo: si lo hizo dentro del plazo planteado por el usuario.

Ejemplo: si una operacion `intradia corto` no alcanza TP en 4 horas pero lo alcanza dos dias despues, no debe contarse como exito intradia. Pero si debe quedar como senal de que la direccion podia ser correcta y que el error pudo estar en el horizonte, el objetivo o la gestion temporal.

El informe guarda ademas `timing_lesson`, una conclusion textual para que futuras auditorias puedan diferenciar rapidamente entre fallo de direccion, fallo de timing y decision manual.

Desde `learning-calibration-v0.4`, estos resultados posteriores al horizonte aparecen en el resumen de aprendizaje como `tp_after_horizon_cases` y `sl_after_horizon_cases`. No modifican todavia la probabilidad TP/SL, porque no son exito o fracaso dentro del plan temporal original. Sirven para detectar si una temporalidad esta siendo demasiado corta, si el TP esta demasiado lejos para el horizonte elegido o si una direccion suele funcionar tarde.

## 17. Documentacion base recomendada

## 17. EV neta y costes operativos

Desde `ev-net-costs-v0.2`, la esperanza matematica no se calcula solo con probabilidad, distancia a TP y distancia a SL. Incluye un modelo de costes desglosado:

| Coste | Regla actual |
| --- | --- |
| Comision entrada | 0.04% del nocional |
| Comision salida | 0.04% del nocional |
| Spread | spread actual del order book convertido a coste sobre nocional |
| Slippage | minimo conservador por temporalidad, aumentado si el spread es mayor |
| Funding | funding actual estimado por periodos de 8 horas segun duracion esperada |

Duracion esperada usada para coste de funding:

| Marco temporal | Minutos esperados |
| --- | --- |
| Intradia corto | 120 |
| Intradia amplio | 720 |
| Swing corto | 4320 |

Formula simplificada:

```text
gross_win = notional * reward_distance_pct
gross_loss = notional * risk_distance_pct
estimated_cost = fees + spread + slippage + funding
net_win = gross_win - estimated_cost
net_loss = gross_loss + estimated_cost
EV = P(TP) * net_win - P(SL) * net_loss - P(rango) * estimated_cost
```

Impacto:

- una operacion puede tener buena probabilidad pero quedar penalizada si los costes destruyen la esperanza matematica;
- una operacion swing paga mas funding estimado que una intradia;
- el motor conserva `cost_model` dentro de `expected_value` para auditar cuanto pesa cada coste;
- la recomendacion usa EV neta para decidir si simular, simular con tamano prudente u observar.

### 17.1. Umbral minimo de EV

Desde `ev-net-costs-v0.2`, EV positiva no basta. La operacion debe superar una EV minima sobre margen segun riesgo y confianza:

| Riesgo | EV minima base |
| --- | --- |
| Bajo | 0.50% |
| Medio | 1.00% |
| Medio-alto | 2.00% |
| Alto | 3.00% |

Ajuste por confianza:

- confianza baja o media-baja: suma +0.50%;
- confianza alta: resta -0.25%;
- confianza media: no modifica.

Si la EV neta no supera el umbral, el motor devuelve `observar`, aunque la EV sea positiva. Esto evita aceptar operaciones donde el beneficio esperado es demasiado pequeno para compensar costes, error de modelo, slippage o ruido de mercado.

Estos costes son aproximados y conservadores. En una futura version deberian calibrarse con comisiones reales del exchange, tipo de orden maker/taker, liquidez por par y slippage historico.

## 18. Documentacion base recomendada

## 18. Ponderacion real por temporalidad

Desde `rules-v0.6-timeframe-weighted`, el marco temporal no solo cambia los timeframes consultados; tambien cambia el peso relativo de cada familia de datos.

| Marco temporal | Foco principal | Peso microestructura | Peso derivados | Peso macro/contexto | Peso funding |
| --- | --- | ---: | ---: | ---: | ---: |
| Intradia corto | flujo inmediato, CVD, order book, RSI corto y zonas intradia | 1.00 | 0.85 | 0.15 | 0.35 |
| Intradia amplio | estructura 1h/4h, derivados por 1h, OI/funding y maximos/minimos diarios | 0.55 | 1.00 | 0.35 | 0.75 |
| Swing corto | estructura 4h/1d, amplitud crypto, sentimiento, funding acumulado y contexto macro | 0.20 | 1.10 | 0.85 | 1.25 |

Impacto practico:

- en intradia corto, CVD, order book, RSI corto y volumen pesan mas que sentimiento general;
- en intradia amplio, OI, funding y estructura 1h/4h ganan peso frente al ruido de 5m;
- en swing corto, el order book puntual pesa poco y suben sentimiento, amplitud de mercado y funding acumulado;
- crowding de derivados y sentimiento extremo ya no pesan igual en todas las temporalidades;
- el `feature_audit.time_horizon_profile` guarda los pesos usados para poder auditar el analisis.

Esta fase reduce un error frecuente: interpretar una senal de scalping como si fuera swing, o una senal macro como si decidiera una operacion de 30 minutos.

## 19. Documentacion base recomendada

## 19. Microestructura avanzada

Desde `rules-v0.6-timeframe-weighted`, el order book incorpora tres lecturas adicionales:

| Dato | Que mide | Uso actual |
| --- | --- | --- |
| `microprice` | Precio teorico ponderado por cantidad en best bid/best ask | Detecta presion inmediata dentro del spread |
| `microprice_bias_pct` | Distancia del microprice frente al mid price | Sesgo leve a favor/contra de la direccion |
| `book_slope` | Liquidez ponderada por cercania en los 20 primeros niveles | Detecta si la liquidez esta mas densa en bids o asks |

Regla actual:

- si el microprice queda por encima del mid, favorece levemente el long y penaliza levemente el short;
- si queda por debajo del mid, favorece levemente el short y penaliza levemente el long;
- si la pendiente del libro muestra bids mas densas cerca del precio, favorece long;
- si muestra asks mas densas cerca del precio, favorece short;
- el ajuste total esta limitado a ±1.8 puntos antes de aplicar el peso temporal.

Impacto por temporalidad:

- intradia corto: senal mas util, se aplica con peso completo;
- intradia amplio: senal secundaria;
- swing corto: senal muy reducida, porque el order book puntual puede cambiar demasiado rapido.

Riesgo de mala interpretacion:

- spoofing o retirada de liquidez;
- book puntual no persistente;
- pares con poca profundidad pueden dar slope ruidoso.

Por eso esta senal no decide una operacion por si sola. Solo ajusta ligeramente la probabilidad direccional y queda guardada en `feature_audit.selected_market_state.order_book`.

Ademas, desde este paso se generan etiquetas de aprendizaje:

- `microprice_bid_pressure`
- `microprice_ask_pressure`
- `book_slope_bid_dense`
- `book_slope_ask_dense`
- `microstructure_supports_plan`
- `microstructure_against_plan`

Estas etiquetas entran en `pattern_tags` y tambien en `HIGH_SIGNAL_PATTERN_TAGS`. Eso permite que, cuando tengamos suficientes operaciones, el motor compare casos donde la microestructura apoyaba o contradecia el plan y mida si realmente aporto ventaja.

## 20. Documentacion base recomendada

## 20. Diagnostico post-trade del motor

Desde `engine-diagnostics-v0.1`, cada operacion evaluada guarda una auditoria tecnica del motor dentro de `learning_evaluations.structured_json.engine_diagnostics`.

El objetivo no es explicar trading al usuario. El objetivo es identificar que parte del motor funciono o fallo para mejorar futuras reglas.

Ejes guardados:

| Eje | Pregunta que responde |
| --- | --- |
| `direction_diagnosis` | La direccion estimada fue correcta, incorrecta o solo funciono tarde |
| `timing_diagnosis` | El horizonte temporal fue correcto, demasiado corto o no resolvio |
| `tp_design_diagnosis` | El TP era alcanzable, ambicioso o demasiado lejos para el movimiento real |
| `sl_design_diagnosis` | El SL estaba bien dimensionado o dentro del ruido reciente |
| `ev_diagnosis` | La EV neta filtro correctamente o sobreestimo la ventaja |
| `microstructure_diagnosis` | Microprice/slope apoyaron el plan y acertaron o fallaron |
| `derivatives_diagnosis` | Taker flow/OI/funding confirmaron, contradijeron o enganaron |
| `main_failure_axis` | Eje principal probable del fallo cuando el plan falla o expira |

Tambien se guardan `diagnostic_flags`, que resumen los puntos tecnicos que deben contarse por patrones similares.

El aprendizaje ya lee:

- `main_failure_axis`;
- `diagnostic_flags`.

Esto permite contar, por ejemplo:

- cuantas operaciones fallaron por timing;
- cuantas por TP demasiado ambicioso;
- cuantas por SL dentro del ruido;
- cuantas por EV sobreestimada;
- cuantas tenian microestructura a favor pero aun asi fallaron;
- cuantas tenian derivados en contra y acabaron fallando.

Esta capa no modifica probabilidades directamente. Sirve para acumular evidencia y decidir futuros cambios de reglas solo cuando exista muestra suficiente.

## 21. Documentacion base recomendada

Fuentes conceptuales y tecnicas que sirven como base del motor:

- J. Welles Wilder, `New Concepts in Technical Trading Systems`: RSI y ATR como conceptos base.
- John J. Murphy, `Technical Analysis of the Financial Markets`: tendencia, medias moviles, soporte/resistencia y volumen.
- Binance Spot/Futures API docs: ticker, klines, depth, aggTrades, funding, open interest, taker flow y long/short ratio.
- `The New Quant: A Survey of Large Language Models in Financial Prediction and Trading`: arquitectura auditable, RAG, leakage temporal, evaluacion y control de riesgos.
- `AI-Trader`: agentes, competicion, evaluacion en mercados y relevancia del control de riesgo.
- `Market-Bench`: necesidad de validar PnL, backtesting y calculos.
- `ClusterLOB`: importancia de order book por patrones y clustering.
- `Explainable Patterns in Cryptocurrency Microstructure`: microestructura crypto, SHAP, CatBoost y patrones explicables.
- Informes ESMA/IOSCO/Bank of England 2025-2026: gobernanza, explicabilidad, auditoria, riesgos de IA y responsabilidad.

## 22. Regla de gobierno del motor

Cualquier cambio futuro en una regla debe documentar:

1. Regla anterior.
2. Regla nueva.
3. Motivo del cambio.
4. Datos que justifican el cambio.
5. Numero de operaciones analizadas.
6. Impacto esperado.
7. Version nueva del motor.

Sin esta trazabilidad, el aprendizaje dejaria de ser cientifico y se convertiria en improvisacion.
